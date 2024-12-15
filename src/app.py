from flask import Flask, render_template, request, jsonify, Response, send_file, redirect, url_for, session
from flask_socketio import SocketIO
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from firebase_config import init_firebase, verify_google_token, db
from models.user import User
from pathlib import Path
from spotify_downloader import main, format_duration, parse_subtitle_file, sp
import threading
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from database import DatabaseManager, DatabaseContextManager, DownloadedTrack, Playlist, PlaylistTrack, DownloadHistory
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
import re
import urllib.parse
import sys
import json
import time
import traceback

# Load environment variables from .env file
load_dotenv()

# Initialize logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(logs_dir, exist_ok=True)
log_file = os.path.join(logs_dir, 'app.log')

handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=1)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Explicitly set the template and static folders
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Create Flask app with explicit template and static folders
app = Flask(__name__, 
            template_folder=TEMPLATE_DIR, 
            static_folder=STATIC_DIR)

# Configure Flask app
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Print debugging information
logger.info(f"Base Directory: {BASE_DIR}")
logger.info(f"Template Directory: {TEMPLATE_DIR}")
logger.info(f"Static Directory: {STATIC_DIR}")
logger.info(f"Index HTML Path: {os.path.join(TEMPLATE_DIR, 'index.html')}")
logger.info(f"Index HTML Exists: {os.path.exists(os.path.join(TEMPLATE_DIR, 'index.html'))}")

# Initialize Flask-SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Import after socketio initialization to avoid circular imports
from emit_utils import set_socketio_instance
set_socketio_instance(socketio)

# Initialize Firebase
init_firebase()
db = db

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id, db)

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/auth/google', methods=['POST'])
def google_auth():
    try:
        # Get the credential from form data
        credential = request.form.get('credential')
        if not credential:
            return jsonify({'error': 'No credential provided'}), 400

        # Verify the Google token
        user_info = verify_google_token(credential)
        if not user_info:
            return jsonify({'error': 'Invalid token'}), 400

        # Get or create user
        user = User.get(user_info['sub'], db)
        if not user:
            user = User(
                user_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                profile_pic=user_info.get('picture')
            )
            user.save_to_db(db)

        # Log in the user
        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('library')})

    except Exception as e:
        logger.error(f"Error in Google authentication: {e}")
        return jsonify({'error': 'Authentication failed'}), 500

@app.route('/auth/google/callback', methods=['GET', 'POST'])
def google_callback():
    try:
        # Get the credential from POST data
        credential = request.form.get('credential')
        if not credential:
            app.logger.error("No credential provided in callback")
            return redirect(url_for('login'))

        # Verify the Google token
        user_info = verify_google_token(credential)
        if not user_info:
            app.logger.error("Invalid token in callback")
            return redirect(url_for('login'))

        # Get or create user
        user = User.get(user_info['sub'], db)
        if not user:
            user = User(
                user_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                profile_pic=user_info.get('picture')
            )
            user.save_to_db(db)
            app.logger.info(f"Created new user: {user.email}")

        # Log in the user
        login_user(user)
        app.logger.info(f"User logged in successfully: {user.email}")
        
        # Redirect to library page
        return redirect(url_for('library'))

    except Exception as e:
        app.logger.error(f"Error in Google callback: {e}")
        return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
def index():
    """Home page route that serves index.html"""
    return render_template('index.html')

@app.route('/home')
def home():
    """Route for handling authentication redirects"""
    if current_user.is_authenticated:
        return redirect(url_for('library'))
    return redirect(url_for('login'))

@app.route('/library')
@login_required
def library():
    # Add debug logging
    app.logger.info(f"User accessing library: {current_user.name} ({current_user.email})")
    try:
        # Fetch user's tracks
        tracks = get_user_tracks()  # Implement this method to retrieve user's tracks
        
        # Get the currently playing track (if any)
        current_track = None
        try:
            # Implement logic to get the current track 
            # This could be from a session, database, or current playback
            current_track = get_current_playing_track()
        except Exception as track_error:
            app.logger.warning(f"Error fetching current track: {track_error}")
        
        # Render the library template with tracks and current track
        return render_template('library.html', 
                               tracks=tracks, 
                               current_track=current_track)

    except Exception as e:
        logger.error(f"Error in library route: {e}")
        return render_template('error.html', error=str(e))

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    spotify_url = data.get('url')
    download_format = data.get('format', 'audio')
    
    if not spotify_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if download_format not in ['audio', 'video']:
        return jsonify({'error': 'Invalid download format'}), 400

    def download_thread(spotify_url):
        try:
            # Start download message
            socketio.emit('status_message', {
                'message': 'Starting download...',
                'type': 'info'
            })

            # Get track info from Spotify
            try:
                if not spotify_url:
                    app.logger.error('No Spotify URL provided.')
                    return
                app.logger.info(f"Extracting track ID from URL: {spotify_url}")
                
                # Clean up the URL in case it contains log messages
                if 'https://' in spotify_url:
                    spotify_url = 'https://' + spotify_url.split('https://')[-1].split()[0]
                
                playlist_name = None
                playlist_thumbnail = None
                album_name = None
                album_thumbnail = None

                # Handle album URLs
                if 'album' in spotify_url:
                    album_id = spotify_url.split('album/')[1].split('?')[0]
                    album_info = sp.album(album_id)
                    album_name = album_info['name']
                    album_thumbnail = album_info['images'][0]['url'] if album_info['images'] else None
                    app.logger.info(f"Album info - Name: {album_name}, Thumbnail: {album_thumbnail}")
                    tracks = fetch_all_album_tracks(album_id)
                    emit_message(f"Starting {download_format} download of album: {album_name}", "info")
                # Handle playlist URLs
                elif 'playlist' in spotify_url:
                    playlist_id = spotify_url.split('playlist/')[1].split('?')[0]
                    playlist = sp.playlist(playlist_id)
                    playlist_name = playlist['name']
                    if playlist['images']:
                        playlist_thumbnail = playlist['images'][0]['url']
                    app.logger.info(f"Playlist info - Name: {playlist_name}, Thumbnail: {playlist_thumbnail}")
                    # Get the track ID from the playlist URL if present
                    if '?track=' in spotify_url:
                        track_id = spotify_url.split('track=')[1].split('&')[0]
                    else:
                        track_id = None
                # Handle track URLs
                else:
                    track_id = spotify_url.split('track/')[1].split('?')[0]
                
                app.logger.info(f"Track ID: {track_id}")
                
                if track_id:
                    app.logger.info("Fetching track from Spotify...")
                    track = sp.track(track_id)
                    app.logger.info("Track data received from Spotify")
                    
                    track_name = track['name']
                    artist_name = track['artists'][0]['name']
                    
                    # Debug track data
                    app.logger.info(f"Track data: {json.dumps(track, indent=2)}")
                    
                    # Get album images
                    album_images = track.get('album', {}).get('images', [])
                    app.logger.info(f"Album images: {json.dumps(album_images, indent=2)}")
                    
                    # Get the highest quality thumbnail
                    thumbnail_url = None
                    if album_images:
                        # Sort images by size and get the largest one
                        images = sorted(album_images, key=lambda x: x.get('width', 0) * x.get('height', 0), reverse=True)
                        if images:
                            thumbnail_url = images[0]['url']
                            app.logger.info(f"Selected thumbnail URL: {thumbnail_url}")
                        else:
                            app.logger.warning("No valid images found in sorted list")
                    else:
                        app.logger.warning("No album images found in track data")
                    
                    app.logger.info(f"Got track info - Name: {track_name}, Artist: {artist_name}, Thumbnail: {thumbnail_url}")
                else:
                    track_name = None
                    artist_name = None
                    thumbnail_url = None

            except Exception as e:
                app.logger.error(f"Error getting Spotify track info: {e}")
                app.logger.error(f"Error type: {type(e)}")
                app.logger.error(f"Error traceback: {traceback.format_exc()}")
                track_name = None
                artist_name = None
                thumbnail_url = None

            # Call main function with debug logging
            app.logger.info(f"Starting download for URL: {spotify_url}")
            result = main(spotify_url, download_format)
            app.logger.info(f"Download result: {result}")

            if result:
                try:
                    # Get file path
                    file_path = str(result)
                    app.logger.info(f"File path: {file_path}")
                    
                    if os.path.exists(file_path):
                        # If we couldn't get track info from Spotify, extract from filename
                        if not track_name or not artist_name:
                            file_name = os.path.basename(file_path)
                            name_without_ext = os.path.splitext(file_name)[0]
                            
                            if ' - ' in name_without_ext:
                                parts = name_without_ext.split(' - ')
                                track_name = parts[0].strip()
                                artist_name = parts[1].strip()
                            else:
                                track_name = name_without_ext
                                artist_name = 'Unknown Artist'

                        # Create download data
                        download_data = {
                            'title': track_name,
                            'artist': artist_name,
                            'format': download_format,
                            'timestamp': datetime.now().isoformat(),
                            'file_path': file_path,
                            'thumbnail': thumbnail_url,
                            'playlist_name': playlist_name,
                            'playlist_thumbnail': playlist_thumbnail,
                            'album_name': album_name,
                            'album_thumbnail': album_thumbnail
                        }
                        
                        app.logger.info(f"Download data: {json.dumps(download_data, indent=2)}")

                        # Save to Firebase if configured
                        try:
                            if 'db' in globals() and db is not None:
                                user_id = 'anonymous'  # Default user ID
                                if 'current_user' in globals() and current_user is not None and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                                    user_id = current_user.id
                                
                                db.collection('downloads').add({
                                    **download_data,
                                    'user_id': user_id
                                })
                                app.logger.info("Successfully saved to Firebase")
                        except Exception as e:
                            app.logger.error(f"Firebase error: {e}")
                            # Continue even if Firebase fails

                        # Emit success events
                        socketio.emit('download_complete', download_data)
                        socketio.emit('status_message', {
                            'message': 'Download completed successfully!',
                            'type': 'success'
                        })
                        return
                    else:
                        raise Exception("Downloaded file not found")

                except Exception as e:
                    app.logger.error(f"Error processing download: {e}")
                    socketio.emit('status_message', {
                        'message': 'Download completed but failed to process metadata',
                        'type': 'warning'
                    })
            else:
                socketio.emit('status_message', {
                    'message': 'Download failed',
                    'type': 'error'
                })

        except Exception as e:
            app.logger.error(f"Download thread error: {e}")
            socketio.emit('status_message', {
                'message': f'Download failed: {str(e)}',
                'type': 'error'
            })

    # Start download thread
    thread = threading.Thread(target=download_thread, args=(spotify_url,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Download started'}), 200

@app.route('/download-history', methods=['GET'])
@login_required
def get_download_history():
    try:
        # Get user's downloads from Firebase
        downloads = db.collection('downloads')\
            .where('user_id', '==', current_user.id)\
            .order_by('timestamp', direction='DESCENDING')\
            .limit(20)\
            .stream()
            
        history = []
        for doc in downloads:
            data = doc.to_dict()
            # Convert timestamp to string if it's a datetime
            if isinstance(data.get('timestamp'), datetime):
                data['timestamp'] = data['timestamp'].isoformat()
            history.append(data)
            
        return jsonify({'history': history}), 200
    except Exception as e:
        app.logger.error(f"Error fetching download history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    try:
        # Delete user's downloads from Firebase
        batch = db.batch()
        docs = db.collection('downloads')\
            .where('user_id', '==', current_user.id)\
            .stream()
            
        for doc in docs:
            batch.delete(doc.reference)
            
        batch.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        app.logger.error(f"Error clearing history: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_spotify_metadata(url):
    try:
        # Extract track/album ID from URL
        if 'track' in url:
            track_id = url.split('track/')[1].split('?')[0]
            # Use spotify API to get track info
            # This is a placeholder - implement actual Spotify API call
            return {
                'title': 'Track Title',
                'artist': 'Artist Name',
                'thumbnail': '/static/img/default-album.png'
            }
        elif 'album' in url:
            album_id = url.split('album/')[1].split('?')[0]
            # Use spotify API to get album info
            # This is a placeholder - implement actual Spotify API call
            return {
                'title': 'Album Title',
                'artist': 'Artist Name',
                'thumbnail': '/static/img/default-album.png'
            }
    except Exception as e:
        app.logger.error(f"Error getting Spotify metadata: {str(e)}")
        return None

@app.route('/play/<path:file_path>')
def play_media(file_path):
    """Stream media files (audio/video) with proper content type handling."""
    try:
        # Decode the URL-encoded file path
        file_path = urllib.parse.unquote(file_path)
        
        # Convert forward slashes to backslashes for Windows
        file_path = file_path.replace('/', '\\')
        
        if not os.path.isfile(file_path):
            logger.error(f"File not found: {file_path}")
            return "File not found", 404

        # Determine content type based on file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        content_type = {
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.wav': 'audio/wav',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm'
        }.get(file_ext, 'application/octet-stream')

        # Get file size for range requests
        file_size = os.path.getsize(file_path)
        
        # Handle range requests for proper streaming
        range_header = request.headers.get('Range', None)
        if range_header:
            byte1, byte2 = 0, None
            match = re.search(r'(\d+)-(\d*)', range_header)  
            groups = match.groups()

            if groups[0]:
                byte1 = int(groups[0])
            if groups[1]:
                byte2 = int(groups[1])

            if byte2 is None:
                byte2 = file_size - 1
            
            length = byte2 - byte1 + 1
            
            resp = Response(
                partial_file_sender(file_path, byte1, byte2),
                status=206,
                mimetype=content_type,
                direct_passthrough=True
            )
            
            resp.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            resp.headers.add('Accept-Ranges', 'bytes')
            resp.headers.add('Content-Length', str(length))
        else:
            resp = Response(
                partial_file_sender(file_path, 0, file_size - 1),
                status=200,
                mimetype=content_type,
                direct_passthrough=True
            )
            resp.headers.add('Content-Length', str(file_size))

        return resp

    except Exception as e:
        logger.error(f"Error streaming file {file_path}: {str(e)}")
        return str(e), 500

@app.route('/subtitles/<path:file_path>')
def get_subtitles(file_path):
    """Serve subtitle file for video"""
    try:
        # Decode the URL-encoded file path
        file_path = urllib.parse.unquote(file_path)
        
        # Convert forward slashes to backslashes for Windows
        file_path = file_path.replace('/', '\\')
        
        # Get the potential SRT file paths
        base_path = os.path.splitext(file_path)[0]
        srt_paths = [
            base_path + '.srt',
            base_path + '.en.srt'
        ]
        
        # Find the first existing subtitle file
        srt_path = next((path for path in srt_paths if os.path.isfile(path)), None)
        
        if not srt_path:
            return "No subtitles found", 404

        # Convert SRT to WebVTT format (required for HTML5 video)
        def srt_to_vtt(srt_content):
            # Add WebVTT header
            vtt = "WEBVTT\n\n"
            
            # Convert SRT timestamps to WebVTT format (same format, just different header)
            vtt += srt_content.replace(',', '.')
            
            return vtt

        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
            vtt_content = srt_to_vtt(srt_content)

        response = Response(vtt_content, mimetype='text/vtt')
        response.headers['Content-Type'] = 'text/vtt'
        return response

    except Exception as e:
        logger.error(f"Error serving subtitles for {file_path}: {str(e)}")
        return str(e), 500

@app.route('/get_lyrics/<path:file_path>')
def get_lyrics(file_path):
    """Get lyrics for an audio file from its subtitle file (SRT or VTT)."""
    try:
        # Clean up the file path
        file_path = urllib.parse.unquote(file_path)
        
        # Convert to absolute path if needed
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        
        logging.info(f"Looking for lyrics file. Base path: {file_path}")
        
        # Check for subtitle files in different formats
        base_path = os.path.splitext(file_path)[0]
        subtitle_formats = ['.srt', '.en.srt', '.vtt', '.en.vtt']
        subtitle_path = None
        
        for fmt in subtitle_formats:
            temp_path = base_path + fmt
            logging.info(f"Checking for subtitle file: {temp_path}")
            if os.path.exists(temp_path):
                subtitle_path = temp_path
                logging.info(f"Found subtitle file: {subtitle_path}")
                break
        
        if subtitle_path:
            lyrics = parse_subtitle_file(subtitle_path)
            if lyrics:
                logging.info(f"Successfully parsed lyrics: {len(lyrics)} lines")
                return jsonify({'success': True, 'lyrics': lyrics})
            else:
                logging.warning(f"No lyrics parsed from file: {subtitle_path}")
                return jsonify({'success': False, 'error': 'No lyrics found in subtitle file'})
        else:
            logging.warning(f"No subtitle file found for: {base_path}")
            return jsonify({'success': False, 'error': 'No lyrics file found'})
    except Exception as e:
        logging.error(f"Error getting lyrics: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/track/<track_id>', methods=['GET', 'PUT', 'DELETE'])
def track_api(track_id):
    """API endpoint for managing individual tracks"""
    try:
        # Get Firebase instance
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        if request.method == 'GET':
            # Get all tracks and find the one with matching ID
            tracks = firebase.get_all_tracks()
            track = next((t for t in tracks if t.get('id') == track_id), None)
            
            if not track:
                return jsonify({'error': 'Track not found'}), 404
                
            return jsonify({
                'id': track.get('id'),
                'title': track.get('title'),
                'artist': track.get('artist'),
                'album': track.get('album'),
                'file_path': track.get('file_path')
            })

        elif request.method == 'PUT':
            data = request.get_json()
            success = firebase.update_track(track_id, {
                'title': data.get('title'),
                'artist': data.get('artist'),
                'album': data.get('album')
            })
            
            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Failed to update track'}), 500

        elif request.method == 'DELETE':
            # Get track info first
            tracks = firebase.get_all_tracks()
            track = next((t for t in tracks if t.get('id') == track_id), None)
            
            if not track:
                return jsonify({'error': 'Track not found'}), 404
                
            # Delete the actual file if it exists
            file_path = track.get('file_path')
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    # Also try to remove subtitle files if they exist
                    base_path = os.path.splitext(file_path)[0]
                    for ext in ['.srt', '.en.srt', '.vtt', '.en.vtt']:
                        sub_path = base_path + ext
                        if os.path.exists(sub_path):
                            os.remove(sub_path)
                except Exception as e:
                    logger.error(f"Error deleting files: {e}")
            
            # Delete from Firebase
            success = firebase.delete_track(track_id)
            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Failed to delete track from Firebase'}), 500

    except Exception as e:
        logger.error(f"Error in track_api: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_playlists')
def get_playlists():
    """API endpoint to get all playlists"""
    try:
        # Get Firebase instance
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        playlists = firebase.get_all_playlists()
        return jsonify([{
            'id': p.get('id'),
            'name': p.get('name')
        } for p in playlists])
    except Exception as e:
        logger.error(f"Error getting playlists: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/track/<int:track_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_track(track_id):
    """Manage track metadata and deletion"""
    try:
        # Get Firebase instance
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        track = firebase.get_track(track_id)
        
        if not track:
            return jsonify({'error': 'Track not found'}), 404
        
        if request.method == 'GET':
            return jsonify({
                'id': track.get('id'),
                'title': track.get('title'),
                'artist': track.get('artist'),
                'album': track.get('album')
            })
            
        elif request.method == 'PUT':
            data = request.get_json()
            success = firebase.update_track(track_id, {
                'title': data.get('title'),
                'artist': data.get('artist'),
                'album': data.get('album')
            })
            
            if success:
                return jsonify({'message': 'Track updated successfully'})
            else:
                return jsonify({'error': 'Failed to update track'}), 500
                
        elif request.method == 'DELETE':
            # Delete the actual file if it exists
            file_path = track.get('file_path')
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    # Also try to remove subtitle files if they exist
                    base_path = os.path.splitext(file_path)[0]
                    for ext in ['.srt', '.en.srt', '.vtt', '.en.vtt']:
                        sub_path = base_path + ext
                        if os.path.exists(sub_path):
                            os.remove(sub_path)
                except Exception as e:
                    logger.error(f"Error deleting files: {e}")
            
            # Delete from Firebase
            success = firebase.delete_track(track_id)
            if success:
                return jsonify({'message': 'Track deleted successfully'})
            else:
                return jsonify({'error': 'Failed to delete track from Firebase'}), 500
                
    except Exception as e:
        logger.error(f"Error managing track: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlist', methods=['GET', 'POST'])
def manage_playlists():
    """Create and list playlists"""
    try:
        # Get Firebase instance
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        if request.method == 'GET':
            playlists = firebase.get_all_playlists()
            return jsonify([{
                'id': p.get('id'),
                'name': p.get('name'),
                'description': p.get('description'),
                'created_date': p.get('created_date')
            } for p in playlists])
            
        elif request.method == 'POST':
            data = request.get_json()
            new_playlist = firebase.create_playlist({
                'name': data['name'],
                'description': data.get('description', ''),
                'created_date': datetime.now().isoformat()
            })
            return jsonify({
                'id': new_playlist.get('id'),
                'message': 'Playlist created successfully'
            })
            
    except Exception as e:
        logger.error(f"Error managing playlists: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/playlist/<int:playlist_id>/tracks', methods=['GET', 'POST', 'DELETE'])
def manage_playlist_tracks(playlist_id):
    """Manage tracks in a playlist"""
    try:
        # Get Firebase instance
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        playlist = firebase.get_playlist(playlist_id)
        if not playlist:
            return jsonify({'error': 'Playlist not found'}), 404
        
        if request.method == 'GET':
            tracks = firebase.get_playlist_tracks(playlist_id)
            return jsonify([{
                'id': t.get('id'),
                'title': t.get('title'),
                'artist': t.get('artist'),
                'album': t.get('album')
            } for t in tracks])
            
        elif request.method == 'POST':
            data = request.get_json()
            track_id = data.get('track_id')
            if not track_id:
                return jsonify({'error': 'Track ID required'}), 400
                
            # Check if track exists
            track = firebase.get_track(track_id)
            if not track:
                return jsonify({'error': 'Track not found'}), 404
                
            # Add track to playlist
            success = firebase.add_track_to_playlist(playlist_id, track_id)
            if success:
                return jsonify({'message': 'Track added to playlist'})
            else:
                return jsonify({'error': 'Failed to add track to playlist'}), 500
                
        elif request.method == 'DELETE':
            data = request.get_json()
            track_id = data.get('track_id')
            if not track_id:
                return jsonify({'error': 'Track ID required'}), 400
                
            # Remove track from playlist
            success = firebase.remove_track_from_playlist(playlist_id, track_id)
            if success:
                return jsonify({'message': 'Track removed from playlist'})
            else:
                return jsonify({'error': 'Failed to remove track from playlist'}), 500
                
    except Exception as e:
        logger.error(f"Error managing playlist tracks: {e}")
        return jsonify({'error': str(e)}), 500

def partial_file_sender(file_path, start=0, end=None, chunk_size=8192):
    """Generator to stream file in chunks with support for range requests."""
    try:
        with open(file_path, 'rb') as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk_size = min(chunk_size, remaining)
                data = f.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
    except Exception as e:
        logger.error(f"Error in partial_file_sender for {file_path}: {str(e)}")
        yield b''

def get_user_tracks():
    """
    Retrieve tracks associated with the current user.
    """
    try:
        # Import Firebase service if not already imported
        from firebase_service import FirebaseService
        firebase = FirebaseService.get_instance()
        
        # Fetch tracks from Firebase
        tracks = firebase.get_all_tracks()
        
        # Process tracks to add additional information
        for track in tracks:
            file_path = track.get('file_path', '')
            file_ext = os.path.splitext(file_path)[1].lower()
            track['file_type'] = 'video' if file_ext == '.mp4' else 'audio'
            
            # Check for subtitle file
            if track['file_type'] == 'video':
                base_path = os.path.splitext(file_path)[0]
                srt_paths = [
                    base_path + '.srt',
                    base_path + '.en.srt'
                ]
                track['has_subtitles'] = any(os.path.exists(path) for path in srt_paths)
            else:
                track['has_subtitles'] = False
            
            # Format file size
            if track.get('file_size'):
                size = track['file_size']
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024:
                        track['formatted_size'] = f"{size:.1f} {unit}"
                        break
                    size /= 1024
            else:
                track['formatted_size'] = "Unknown"
            
            track['formatted_duration'] = format_duration(track.get('duration', 0))
            track['file_exists'] = os.path.exists(file_path)
        
        return tracks
    except Exception as e:
        app.logger.error(f"Error retrieving tracks: {e}")
        return []

def get_current_playing_track():
    """
    Retrieve the currently playing track.
    This is a placeholder and should be replaced with actual track tracking logic.
    """
    try:
        # Placeholder for current track information
        current_track = {
            'title': 'No track playing',
            'artist': 'Unknown',
            'thumbnail_url': '/static/img/default-album.png'
        }
        
        # TODO: Implement actual current track tracking logic
        # This could involve:
        # - Checking a database or session for the last played track
        # - Retrieving track information from a music player service
        # - Using a global variable or state management system
        
        return current_track
    except Exception as e:
        app.logger.error(f"Error fetching current track: {e}")
        return None

if __name__ == '__main__':
    # Initialize database
    try:
        if DatabaseManager.needs_migration():
            logger.info("Database needs migration, performing migration...")
            if DatabaseManager.migrate_database():
                logger.info("Database migration completed successfully")
            else:
                logger.error("Database migration failed")
        else:
            DatabaseManager.init_db()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

    socketio.run(app, debug=True)
