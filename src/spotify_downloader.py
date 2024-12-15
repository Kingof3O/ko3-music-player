"""
Title: Spotify Playlist Audio Downloader

Description:
This script automates the process of downloading audio files from a specified Spotify playlist. 
For each track, it retrieves the audio from YouTube, downloads associated subtitles, 
and embeds a thumbnail as cover art for the audio file. The script uses the Spotify API 
to access playlist information, yt-dlp for downloading audio and subtitles from YouTube, 
and the Mutagen library to handle audio metadata.

Requirements:
- Spotipy: for Spotify API interactions
- yt-dlp: for downloading YouTube audio and subtitles
- Requests: for fetching thumbnail images
- Mutagen: for modifying audio file metadata
- Python 3.x

Usage:
1. Set your Spotify API credentials in the environment variables SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.
2. Specify the desired Spotify playlist ID.
3. Run the script to download audio files, thumbnails, and subtitles.

"""

import os
import sys
import json
import logging
import requests
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from emit_utils import emit_progress, emit_message
from firebase_service import FirebaseService
from mutagen.mp4 import MP4, MP4Cover
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spotify_downloader.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Get Spotify credentials from environment variables
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if not CLIENT_ID or not CLIENT_SECRET:
    logging.error("Spotify API credentials not found in environment variables")
    sys.exit(1)

# Set up authentication with Spotify
try:
    credentials = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    sp = spotipy.Spotify(client_credentials_manager=credentials)
    logging.info("Successfully initialized Spotify client")
except Exception as e:
    logging.error(f"Error during Spotify authentication: {e}")
    sys.exit(1)

# Constants for download directory
DOWNLOAD_DIR = Path.cwd() / "downloaded_content"  # Directory to save downloaded content

# Fetch the top YouTube URL for a song using a search query
def fetch_youtube_url(search_query: str) -> Optional[str]:
    """
    Fetch the top YouTube URL for a given search query using yt-dlp's search functionality.
    
    :param search_query: The query to search on YouTube (e.g., song title and artist).
    :return: The URL of the top YouTube video result or None if not found.
    """
    try:
        logging.info(f"Searching YouTube for: {search_query}")
        
        # Add 'official video' to search query for better results
        search_query = f"{search_query} official video"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch1:',
            'format': 'bestaudio/best'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                
                if not info or 'entries' not in info or not info['entries']:
                    logging.warning(f"No YouTube video found for: {search_query}")
                    return None
                
                top_result = info['entries'][0]
                video_url = f"https://www.youtube.com/watch?v={top_result['id']}"
                
                logging.info(f"Found YouTube URL for {search_query}: {video_url}")
                return video_url
                
            except yt_dlp.utils.DownloadError as e:
                logging.error(f"YouTube search error for {search_query}: {e}")
                return None
    
    except Exception as e:
        logging.error(f"Error fetching YouTube URL for {search_query}: {e}")
        return None

# Download subtitles from YouTube for the corresponding video
def download_subtitles(video_url: str, m4a_file_path: Path, language_code='en', auto_subtitles=True):
    """
    Downloads subtitles for the given video URL and saves them in the same directory as the m4a file.
    
    :param video_url: The URL of the video to download subtitles from.
    :param m4a_file_path: Path to the m4a file where the corresponding subtitle file will be saved.
    :param language_code: The language code for the subtitles (e.g., 'en' for English).
    :param auto_subtitles: Boolean to determine whether to download auto-generated subtitles if official ones are unavailable.
    """
    # Logging configuration
    logging.info(f"Attempting to download subtitles for: {video_url}")
    logging.info(f"Target subtitle file: {m4a_file_path}")
    logging.info(f"Language code: {language_code}")
    logging.info(f"Auto subtitles enabled: {auto_subtitles}")

    # Create subtitle file path with the same name as the m4a file but with the .srt extension
    srt_file_path = m4a_file_path.with_suffix('.srt')
    base_filename = str(srt_file_path.with_suffix(''))  # Remove extension for yt-dlp

    # YT-DLP options to download subtitles
    ydl_opts = {
        'writesubtitles': True,             # Write subtitles
        'writeautomaticsub': auto_subtitles, # Download auto-generated subtitles if available
        'subtitleslangs': [language_code],   # Only try the specified language
        'subtitlesformat': 'srt',            # Download in SRT format
        'skip_download': True,              # Do not download the video itself
        'outtmpl': base_filename,           # Base filename without extension
        'postprocessors': [{
            'key': 'FFmpegSubtitlesConvertor',
            'format': 'srt',
        }],
        'verbose': True  # Add verbose logging for yt-dlp
    }

    # Using yt_dlp to extract and download subtitles
    try:
        # First, extract info to check subtitle availability
        with yt_dlp.YoutubeDL({'skip_download': True}) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            
            # Enhanced logging for subtitle availability
            logging.info(f"Video Info Keys: {info_dict.keys()}")
            
            # Check subtitle availability
            has_manual_subs = 'subtitles' in info_dict and language_code in info_dict['subtitles']
            has_auto_subs = 'automatic_captions' in info_dict and language_code in info_dict['automatic_captions']

            logging.info(f"Manual Subtitles Available: {has_manual_subs}")
            logging.info(f"Auto Subtitles Available: {has_auto_subs}")
            logging.info(f"Subtitles Info: {info_dict.get('subtitles', {})}")
            logging.info(f"Auto Captions Info: {info_dict.get('automatic_captions', {})}")

        # Attempt to download subtitles
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Attempt to download subtitles
            ydl.download([video_url])

        # Find and rename subtitle files
        subtitle_found = False
        possible_extensions = ['.srt', '.en.srt', '.vtt', '.en.vtt']
        possible_language_codes = [language_code, f'{language_code}-orig', 'en', 'en-US']

        for ext in possible_extensions:
            for lang_code in possible_language_codes:
                potential_file = Path(f"{base_filename}.{lang_code}{ext}")
                logging.info(f"Checking potential subtitle file: {potential_file}")
                
                if potential_file.exists():
                    # Rename to match m4a filename
                    potential_file.rename(srt_file_path)
                    logging.info(f"Subtitle file found and saved as: {srt_file_path}")
                    subtitle_found = True
                    break
            
            if subtitle_found:
                break

        if not subtitle_found:
            logging.warning(f"No subtitle file found for {video_url}")
            # List all files in the directory to help diagnose
            logging.info("Files in download directory:")
            for file in m4a_file_path.parent.glob('*'):
                logging.info(f"  {file}")

    except Exception as e:
        logging.error(f"Error downloading subtitles: {e}")
        logging.exception("Subtitle download traceback:")
        
    # Always return None, as this is a side effect function
    return None

def parse_subtitle_file(subtitle_path: str) -> List[Dict[str, str]]:
    """
    Parse a subtitle file (SRT or VTT) and return a list of lyrics with timestamps.
    
    Args:
        subtitle_path (str): Path to the subtitle file
        
    Returns:
        List[Dict[str, str]]: List of dictionaries containing start_time, end_time, and text
    """
    lyrics = []
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Remove WEBVTT header if present
        if content.strip().startswith('WEBVTT'):
            # Split by double newline and remove the header
            blocks = content.split('\n\n')[1:]
        else:
            blocks = content.strip().split('\n\n')
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 2:  # Valid subtitle block
                # Find timestamp line (skip numeric ID if present)
                timestamp_line = None
                for line in lines:
                    if ' --> ' in line:
                        timestamp_line = line
                        break
                
                if timestamp_line:
                    # Parse timestamp line
                    times = timestamp_line.split(' --> ')
                    start_time = times[0].strip()
                    end_time = times[1].split(' ')[0].strip()  # Remove any alignment tags
                    
                    # Get text (all lines after timestamp)
                    text_lines = lines[lines.index(timestamp_line) + 1:]
                    text = ' '.join(text_lines)
                    
                    # Clean up text - remove ♪ and brackets, and extra whitespace
                    text = text.replace('♪', '').replace('[', '').replace(']', '')
                    text = ' '.join(text.split())  # Remove extra whitespace
                    
                    if text:  # Only add if there's actual text
                        # Convert VTT timestamps to SRT format if needed
                        if '.' in start_time:
                            start_time = start_time.replace('.', ',')
                        if '.' in end_time:
                            end_time = end_time.replace('.', ',')
                        
                        lyrics.append({
                            'start_time': start_time,
                            'end_time': end_time,
                            'text': text
                        })
        
        return lyrics
    except Exception as e:
        logging.error(f"Error parsing subtitle file: {str(e)}")
        return []

def save_track_to_db(track_metadata: dict, file_path: str, is_video: bool = False):
    """
    Save track information to Firebase.
    
    :param track_metadata: Dictionary containing track metadata
    :param file_path: Path where the file is saved
    :param is_video: Whether the download is a video
    """
    try:
        # Get file size
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
        
        # Check for subtitle files
        has_subtitles = check_for_subtitles(file_path)
        
        # Extract required metadata
        track_data = {
            'spotify_id': track_metadata.get('id', ''),
            'title': track_metadata.get('name', ''),
            'artist': ', '.join([artist['name'] for artist in track_metadata.get('artists', [])]),
            'album': track_metadata.get('album_name', ''),
            'duration': track_metadata.get('duration_ms', 0),
            'spotify_uri': track_metadata.get('uri', ''),
            'file_path': file_path,
            'is_video': is_video,
            'file_size': file_size,
            'has_subtitles': has_subtitles,
            'download_date': datetime.now(),
            'download_source': 'spotify',
            'audio_format': os.path.splitext(file_path)[1][1:] if file_path else None,
        }
        
        # Add thumbnail URL if available
        if track_metadata.get('album_images'):
            track_data['thumbnail_url'] = track_metadata['album_images'][0].get('url') if track_metadata['album_images'] else None
        
        # Add additional metadata
        track_data['additional_metadata'] = {
            'album_id': track_metadata.get('album_id'),
            'album_type': track_metadata.get('album_type'),
            'album_release_date': track_metadata.get('album_release_date'),
            'album_total_tracks': track_metadata.get('album_total_tracks'),
            'track_number': track_metadata.get('track_number'),
            'disc_number': track_metadata.get('disc_number'),
            'popularity': track_metadata.get('popularity'),
            'explicit': track_metadata.get('explicit')
        }
        
        # Save to Firebase
        firebase = FirebaseService.get_instance()
        track_id = firebase.add_track(track_data)
        
        if track_id:
            logging.info(f"Successfully saved track to Firebase: {track_data['title']}")
            return True
        else:
            logging.error("Failed to save track to Firebase")
            return False
            
    except Exception as e:
        logging.error(f"Error saving track to Firebase: {str(e)}")
        logging.error("Full traceback:", exc_info=True)
        return False

def check_for_subtitles(file_path: str) -> bool:
    """
    Check if subtitle files exist for the given media file.
    
    Args:
        file_path (str): Path to the media file
        
    Returns:
        bool: True if subtitle files exist, False otherwise
    """
    base_path = os.path.splitext(file_path)[0]
    subtitle_formats = ['.srt', '.en.srt', '.vtt', '.en.vtt']
    
    for ext in subtitle_formats:
        subtitle_path = base_path + ext
        if os.path.exists(subtitle_path):
            return True
    
    return False

def format_duration(duration_ms: Optional[int]) -> str:
    """
    Format duration from milliseconds to HH:MM:SS or MM:SS format.
    
    :param duration_ms: Duration in milliseconds
    :return: Formatted duration string
    """
    if not duration_ms:
        return "0:00"
    
    total_seconds = int(duration_ms / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:   
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def download_content(track_name: str, artist_name: str, download_path: Path, format_type: str = 'audio', thumbnail_url: Optional[str] = None, track_metadata: Optional[dict] = None) -> Optional[str]:
    """
    Download content from YouTube with enhanced features.
    
    :param track_name: Name of the track
    :param artist_name: Name of the artist
    :param download_path: Path to save the downloaded content
    :param format_type: Type of content to download ('audio' or 'video')
    :param thumbnail_url: URL of the thumbnail image
    :param track_metadata: Additional track metadata
    :return: Path to the downloaded file if successful, None otherwise
    """
    try:
        search_query = f"{track_name} {artist_name} official video"
        emit_message(f"Searching YouTube for: {search_query}", "info")
        
        # Get video URL
        video_url = fetch_youtube_url(search_query)
        if not video_url:
            emit_message(f"No YouTube results found for: {search_query}", "error")
            return None
            
        emit_message(f"Found YouTube URL: {video_url}", "info")
        
        # Prepare output template
        sanitized_name = f"{sanitize_filename(track_name)} - {sanitize_filename(artist_name)}"
        output_template = str(download_path / sanitized_name)
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best' if format_type == 'audio' else 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]',
            'outtmpl': output_template,
            'progress_hooks': [download_progress_callback],
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'subtitlesformat': 'srt',
            'postprocessors': [{
                'key': 'FFmpegSubtitlesConvertor',
                'format': 'srt',
            }],
        }
        
        # Add format-specific post-processors
        if format_type == 'audio':
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            })
        else:
            ydl_opts.update({
                'merge_output_format': 'mp4',
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]'
            })
        
        # Download the content
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Extract video info first
                info_dict = ydl.extract_info(video_url, download=False)
                
                # Download video and subtitles
                ydl.download([video_url])
                
                # Determine the output file path
                if format_type == 'audio':
                    output_file = f"{output_template}.m4a"
                else:
                    output_file = f"{output_template}.mp4"
                
                # Set thumbnail for audio files
                if format_type == 'audio' and thumbnail_url:
                    try:
                        audiofile = MP4(output_file)
                        response = requests.get(thumbnail_url)
                        if response.status_code == 200:
                            audiofile['covr'] = [MP4Cover(response.content, MP4Cover.FORMAT_JPEG)]
                            audiofile.save()
                            emit_message("Added album artwork", "info")
                    except Exception as e:
                        emit_message(f"Error setting thumbnail: {e}", "warning")
                
                # Save to database
                if track_metadata:
                    save_track_to_db(track_metadata, output_file, is_video=(format_type == 'video'))
                
                emit_message(f"Successfully downloaded: {track_name}", "success")
                return output_file
                
            except Exception as e:
                emit_message(f"Error during download: {str(e)}", "error")
                return None
                
    except Exception as e:
        emit_message(f"Error in download process: {str(e)}", "error")
        return None

def download_progress_callback(progress_data):
    """Callback function to handle download progress"""
    try:
        if isinstance(progress_data, dict):
            progress = progress_data.get('progress', 0)
            if progress:
                # Ensure progress is between 0 and 100
                progress = min(100, max(0, progress))
                emit_message(f"Download progress: {progress}%", "info")
                emit_progress({
                    'progress': progress,
                    'status': 'downloading'
                })
    except Exception as e:
        logging.error(f"Error in progress callback: {str(e)}")

def get_track_metadata(track_obj: Dict) -> Dict[str, Optional[str]]:
    """
    Extract comprehensive track metadata from Spotify track object.
    
    :param track_obj: Dictionary containing track information from Spotify
    :return: Dictionary containing formatted track metadata
    """
    try:
        # Get the track object (handle both playlist and direct track objects)
        track = track_obj.get('track', track_obj)
        
        # Extract basic track information
        track_data = {
            'id': track.get('id'),
            'name': track.get('name'),
            'artists': track.get('artists', []),
            'duration_ms': track.get('duration_ms'),
            'uri': track.get('uri'),
        }
        
        # Extract album information
        if 'album' in track:
            album = track['album']
            track_data.update({
                'album_name': album.get('name'),
                'album_id': album.get('id'),
                'album_type': album.get('album_type'),
                'album_release_date': album.get('release_date'),
                'album_total_tracks': album.get('total_tracks'),
                'album_images': album.get('images', []),
            })
        
        # Extract additional metadata
        track_data.update({
            'track_number': track.get('track_number'),
            'disc_number': track.get('disc_number'),
            'popularity': track.get('popularity'),
            'explicit': track.get('explicit'),
            'external_urls': track.get('external_urls'),
            'preview_url': track.get('preview_url'),
            'artist_id': [artist['id'] for artist in track['artists']],
            'isrc': track.get('external_ids', {}).get('isrc')
        })
        
        return track_data
        
    except Exception as e:
        logging.error(f"Error extracting track metadata: {e}")
        logging.error("Track object:", track_obj)
        return {
            'id': None,
            'name': 'Unknown Track',
            'artists': [{'name': 'Unknown Artist'}],
            'duration_ms': 0,
            'uri': None,
            'album_name': 'Unknown Album',
            'album_images': []
        }

def fetch_all_playlist_tracks(playlist_id: str) -> List[Dict[str, Optional[str]]]:
    """
    Fetch all tracks from a Spotify playlist with comprehensive metadata.
    
    :param playlist_id: Spotify playlist ID
    :return: List of track metadata dictionaries
    """
    tracks = []
    results = sp.playlist_tracks(playlist_id)
    
    while results:
        for item in results['items']:
            if item and 'track' in item and item['track']:
                tracks.append(item)  # Keep the full item with track nested
        
        if results['next']:
            results = sp.next(results)
        else:
            break
    
    return tracks

def fetch_all_album_tracks(album_id: str) -> List[Dict[str, Optional[str]]]:
    """
    Fetch all tracks from a Spotify album with comprehensive metadata.
    
    :param album_id: Spotify album ID
    :return: List of track metadata dictionaries
    """
    logging.info(f"Fetching tracks from album: {album_id}")
    
    try:
        # Get full album details first
        album = sp.album(album_id)
        album_name = album['name']
        album_artist = album['artists'][0]['name']
        album_images = album.get('images', [])
        
        logging.info(f"Album: {album_name} by {album_artist}")
        
        tracks = []
        results = sp.album_tracks(album_id)
        
        # Fetch all pages
        while True:
            for track in results['items']:
                # Create track data with album information
                track_data = {
                    'track': {
                        'id': track['id'],
                        'name': track['name'],
                        'artists': track['artists'],
                        'duration_ms': track['duration_ms'],
                        'uri': track['uri'],
                        'album': {
                            'name': album_name,
                            'id': album_id,
                            'artists': album['artists'],
                            'images': album_images,
                            'release_date': album.get('release_date'),
                            'total_tracks': album.get('total_tracks'),
                            'album_type': album.get('album_type')
                        }
                    }
                }
                tracks.append(track_data)
            
            if not results['next']:
                break
            results = sp.next(results)
        
        logging.info(f"Successfully fetched {len(tracks)} tracks from album")
        return tracks
        
    except Exception as e:
        logging.error(f"Error fetching album tracks: {e}")
        return []

# Set the thumbnail as the icon for the media file
def set_folder_icon(folder_path: str, image_url: str) -> bool:
    """
    Set a custom icon for a folder using Windows desktop.ini
    
    :param folder_path: Path to the folder
    :param image_url: URL of the image to use as icon
    :return: True if successful, False otherwise
    """
    try:
        # Download the high-quality image
        response = requests.get(image_url)
        if response.status_code != 200:
            logging.error(f"Failed to download image from {image_url}")
            return False
            
        # Convert image to ICO using PIL
        from PIL import Image
        import io
        
        # Load image from bytes and convert to RGBA
        image = Image.open(io.BytesIO(response.content))
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # Use only larger sizes for better quality
        icon_sizes = [(256, 256), (128, 128), (64, 64)]
        icon_images = []
        
        # Create high-quality versions for each size
        for size in icon_sizes:
            # Calculate aspect ratio
            aspect = image.width / image.height
            if aspect > 1:
                new_width = size[0]
                new_height = int(size[0] / aspect)
            else:
                new_height = size[1]
                new_width = int(size[1] * aspect)
                
            # Resize with high-quality settings
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create new image with alpha
            final_image = Image.new('RGBA', size, (0, 0, 0, 0))
            
            # Paste resized image in center
            paste_x = (size[0] - new_width) // 2
            paste_y = (size[1] - new_height) // 2
            final_image.paste(resized, (paste_x, paste_y))
            
            icon_images.append(final_image)
            
        # Save as ICO with high quality
        icon_path = os.path.join(folder_path, 'folder.ico')
        icon_images[0].save(
            icon_path,
            format='ICO',
            sizes=[(im.width, im.height) for im in icon_images],
            append_images=icon_images[1:],
            optimize=False,
            quality=100
        )
        
        # Get absolute paths
        abs_folder_path = os.path.abspath(folder_path)
        abs_icon_path = os.path.abspath(icon_path)
        
        try:
            # Create desktop.ini with absolute paths
            ini_path = os.path.join(abs_folder_path, 'desktop.ini')
            with open(ini_path, 'w', encoding='utf-8') as f:
                f.write("[.ShellClassInfo]\n")
                f.write(f"IconFile={abs_icon_path}\n")
                f.write("IconIndex=0\n")
                f.write("InfoTip=Spotify Album Folder\n")
                f.write("[ViewState]\n")
                f.write("Mode=4\n")
                f.write("Vid=\n")
                f.write("FolderType=Music\n")
                f.write(f"Logo={abs_icon_path}\n")
            
            # Set proper attributes in correct order
            subprocess.run(['attrib', '+s', folder_path], check=True)
            subprocess.run(['attrib', '+h', icon_path], check=True)
            subprocess.run(['attrib', '+s', '+h', ini_path], check=True)
            
            # Refresh icon cache without restarting explorer
            try:
                subprocess.run(['ie4uinit.exe', '-show'], shell=True, check=False)
            except Exception as e:
                logging.warning(f"Failed to refresh icon cache: {e}")
            
            logging.info(f"Successfully set folder icon for: {folder_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error setting folder attributes: {e}")
            # Clean up files if setting attributes failed
            try:
                if os.path.exists(icon_path):
                    os.remove(icon_path)
                if os.path.exists(ini_path):
                    os.remove(ini_path)
            except:
                pass
            return False
            
    except Exception as e:
        logging.error(f"Error setting folder icon: {e}")
        return False

def get_track_info(track, sp):
    """
    Extract track information from Spotify track object.
    
    :param track: Spotify track object
    :param sp: Spotipy client instance
    :return: Tuple of (track_name, artist_name, thumbnail_url, track_metadata)
    """
    try:
        track_name = track['name']
        artist_name = ", ".join(artist['name'] for artist in track['artists'])
        track_metadata = {}
        
        # Get full album info if available
        if track.get('album'):
            album_info = sp.album(track['album']['id'])
            thumbnail_url = album_info['images'][0]['url'] if album_info['images'] else None
            track_metadata['album'] = album_info['name']
            track_metadata['album_id'] = album_info['id']
            track_metadata['album_type'] = album_info['album_type']
            track_metadata['album_total_tracks'] = album_info['total_tracks']
            track_metadata['release_date'] = album_info['release_date']
        else:
            thumbnail_url = None
            track_metadata['album'] = 'Unknown Album'
            logging.warning(f"No album info found for track: {track_name}")
        
        # Get duration from track object
        duration_ms = track.get('duration_ms')
        if duration_ms:
            track_metadata['duration_ms'] = duration_ms
            track_metadata['formatted_duration'] = format_duration(duration_ms)
            logging.info(f"Track duration from Spotify: {track_metadata['formatted_duration']}")
        
        # Add other track metadata
        track_metadata.update({
            'spotify_uri': track.get('uri'),
            'track_number': track.get('track_number'),
            'disc_number': track.get('disc_number'),
            'popularity': track.get('popularity'),
            'explicit': track.get('explicit'),
            'external_urls': track.get('external_urls'),
            'preview_url': track.get('preview_url'),
            'artist_id': [artist['id'] for artist in track['artists']],
            'isrc': track.get('external_ids', {}).get('isrc')
        })
        
        return track_name, artist_name, thumbnail_url, track_metadata
        
    except Exception as e:
        logging.error(f"Error extracting track info: {e}")
        return track.get('name', 'Unknown Track'), 'Unknown Artist', None, {'album': 'Unknown Album'}

def sanitize_filename(filename: str) -> str:
    """
    Sanitize the filename/foldername to be valid for Windows.
    Removes or replaces invalid characters.
    
    :param filename: The original filename/foldername
    :return: A sanitized filename safe for Windows
    """
    # Characters not allowed in Windows filenames
    invalid_chars = r'<>:"/\|?*'
    
    # Replace invalid characters with underscore
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove trailing periods and spaces (not allowed in Windows)
    filename = filename.rstrip('. ')
    
    # If filename is empty after sanitization, provide a default
    if not filename:
        filename = "unnamed"
        
    return filename

def display_database_content():
    """Display all tracks in the database with formatted information."""
    try:
        firebase = FirebaseService.get_instance()
        tracks = firebase.get_all_tracks()
        
        if not tracks:
            print("\nNo tracks found in database.")
            return
                
        print("\n=== Database Content ===")
        print(f"Total tracks: {len(tracks)}\n")
        
        for track in tracks:
            # Get additional metadata
            metadata = track.get('additional_metadata', {})
            
            # Format duration
            duration = format_duration(track.get('duration')) if track.get('duration') else "Unknown"
            
            # Format file size
            file_size_mb = f"{track.get('file_size', 0) / (1024 * 1024):.1f} MB" if track.get('file_size') else "Unknown"
            
            print(f"Track: {track.get('title')}")
            print(f"Artist: {track.get('artist')}")
            print(f"Album: {track.get('album')}")
            print(f"Duration: {duration}")
            print(f"File Size: {file_size_mb}")
            print(f"Download Date: {track.get('download_date')}")
            print(f"Format: {track.get('audio_format') or 'Unknown'}")
            print(f"Type: {'Video' if track.get('is_video') else 'Audio'}")
            
            # Print additional metadata if available
            if metadata:
                print("Additional Info:")
                if metadata.get('track_number'):
                    print(f"  Track Number: {metadata['track_number']}")
                if metadata.get('disc_number'):
                    print(f"  Disc Number: {metadata['disc_number']}")
                if metadata.get('release_date'):
                    print(f"  Release Date: {metadata['release_date']}")
                if metadata.get('popularity'):
                    print(f"  Popularity: {metadata['popularity']}")
                if metadata.get('isrc'):
                    print(f"  ISRC: {metadata['isrc']}")
            
            print("-" * 50)
                
    except Exception as e:
        print(f"Error displaying database content: {e}")
        logging.error(f"Error displaying database content: {e}")

def get_spotify_url_type(url: str) -> str:
    """
    Determine the type of Spotify URL (track, album, or playlist).
    
    Args:
        url (str): The Spotify URL to analyze
        
    Returns:
        str: The type of content ('track', 'album', or 'playlist')
        
    Raises:
        ValueError: If the URL is not a valid Spotify URL
    """
    url = url.lower()
    if "track" in url:
        return "track"
    elif "album" in url:
        return "album"
    elif "playlist" in url:
        return "playlist"
    else:
        raise ValueError("Invalid Spotify URL. Must be a track, album, or playlist URL.")

def close_spotify_session():
    """
    Safely closes the Spotify session to prevent resource leaks.
    Handles any potential errors during session closure.
    """
    try:
        if hasattr(sp, '_session'):
            sp._session.close()
            logging.info("Spotify session closed successfully")
        else:
            logging.info("No active Spotify session to close")
    except Exception as e:
        logging.error(f"Error closing Spotify session: {str(e)}")

def extract_track_metadata(video_info):
    """
    Extract comprehensive track metadata including thumbnail URL
    """
    try:
        # Extract thumbnail URL
        thumbnail_url = video_info.get('thumbnail', 
            video_info.get('thumbnails', [{}])[0].get('url', '/static/img/default-album.png')
        )
        
        return {
            'title': video_info.get('title', 'Unknown Title'),
            'artist': video_info.get('artist', 'Unknown Artist'),
            'thumbnail_url': thumbnail_url,
            # Other existing metadata extraction
            'file_path': None,
            'duration': None,
        }
    except Exception as e:
        logging.error(f"Error extracting track metadata: {e}")
        return {
            'title': 'Unknown Title',
            'artist': 'Unknown Artist',
            'thumbnail_url': '/static/img/default-album.png'
        }

# Main function to orchestrate the entire download process
def main(spotify_url=None, download_format='audio'):
    """
    Main function to handle downloads from Spotify.
    
    :param spotify_url: Spotify URL to download from
    :param download_format: Format to download in ('audio' or 'video')
    :return: Path to the downloaded file if successful, None otherwise
    """
    print("Welcome to Spotify Downloader!")
    if not spotify_url:
        spotify_url = input("Please enter the Spotify link for a track, album, or playlist: ")
    url_type = get_spotify_url_type(spotify_url)
    folder_name = ""
    folder_thumbnail = None
    downloaded_file = None
    
    try:
        if url_type == "playlist":
            playlist_id = spotify_url.split("playlist/")[1].split("?")[0]
            playlist_info = sp.playlist(playlist_id)
            folder_name = sanitize_filename(playlist_info['name'])
            folder_thumbnail = playlist_info['images'][0]['url'] if playlist_info['images'] else None
            tracks = fetch_all_playlist_tracks(playlist_id)
            emit_message(f"Starting {download_format} download of playlist: {folder_name}", "info")
            
        elif url_type == "album":
            album_id = spotify_url.split("album/")[1].split("?")[0]
            album_info = sp.album(album_id)
            folder_name = sanitize_filename(album_info['name'])
            folder_thumbnail = album_info['images'][0]['url'] if album_info['images'] else None
            tracks = fetch_all_album_tracks(album_id)
            emit_message(f"Starting {download_format} download of album: {folder_name}", "info")
            
        elif url_type == "track":
            track_id = spotify_url.split("track/")[1].split("?")[0]
            track = sp.track(track_id)
            
            # Get album info for single track
            if track.get('album'):
                album_info = sp.album(track['album']['id'])
                folder_name = sanitize_filename(album_info['name'])
                folder_thumbnail = album_info['images'][0]['url'] if album_info['images'] else None
            else:
                folder_name = 'Singles'
                folder_thumbnail = track['album']['images'][0]['url'] if track['album'].get('images') else None
            
            tracks = [{'track': track}]
            emit_message(f"Starting {download_format} download of track: {track['name']}", "info")
            
        else:
            emit_message("Invalid Spotify URL. Please provide a valid track, album, or playlist URL.", "error")
            return None
        
        # Create download directory
        download_path = Path("downloaded_content") / folder_name
        download_path.mkdir(parents=True, exist_ok=True)
        
        # Set folder icon if thumbnail available
        if folder_thumbnail:
            try:
                set_folder_icon(str(download_path), folder_thumbnail)
                emit_message(f"Set folder icon for: {folder_name}", "info")
            except Exception as e:
                logging.error(f"Error setting folder icon: {e}")
                emit_message(f"Could not set folder icon: {str(e)}", "warning")
        
        # Download each track
        total_tracks = len(tracks)
        for index, track_item in enumerate(tracks, 1):
            try:
                track_metadata = get_track_metadata(track_item)
                track_name = track_metadata['name']
                artists = [artist['name'] for artist in track_metadata['artists']]
                artist_name = ", ".join(artists)
                
                emit_message(f"Downloading {index}/{total_tracks}: {track_name} by {artist_name}", "info")
                
                # Get thumbnail URL from track metadata
                thumbnail_url = None
                if track_metadata['album_images']:
                    thumbnail_url = track_metadata['album_images'][0]['url']
                
                # Download the track
                downloaded_file = download_content(
                    track_name=track_name,
                    artist_name=artist_name,
                    download_path=download_path,
                    format_type=download_format,
                    thumbnail_url=thumbnail_url,
                    track_metadata=track_metadata
                )
                
                if downloaded_file:
                    emit_message(f"Successfully downloaded: {track_name}", "success")
                    # For single tracks, return the downloaded file path
                    if url_type == "track":
                        return downloaded_file
                else:
                    emit_message(f"Failed to download: {track_name}", "error")
                
            except Exception as e:
                logging.error(f"Error processing track: {e}")
                emit_message(f"Error processing track: {str(e)}", "error")
                continue
        
        emit_message("Download completed! Check the 'downloaded_content' folder.", "success")
        # For playlists/albums, return the last downloaded file
        return downloaded_file
        
    except Exception as e:
        logging.error(f"Error during download process: {e}")
        emit_message(f"Error during download process: {str(e)}", "error")
        return None
    
    finally:
        close_spotify_session()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--show-db":
        display_database_content()
    else:
        main()