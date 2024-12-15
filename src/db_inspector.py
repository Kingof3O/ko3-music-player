import sys
import os
import traceback

# Add the src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager, DownloadedTrack

def inspect_db():
    """Interactive database inspection."""
    session = DatabaseManager.get_session()
    try:
        # Total tracks
        total_tracks = session.query(DownloadedTrack).count()
        print(f"Total Tracks: {total_tracks}")
        
        # Recent tracks
        recent_tracks = session.query(DownloadedTrack).order_by(DownloadedTrack.id.desc()).limit(10)
        print("\nMost Recent Tracks:")
        for track in recent_tracks:
            print(f"ID: {track.id}, Title: {track.title}, Artist: {track.artist}, Album: {track.album}")
        
        # Unique artists
        unique_artists = session.query(DownloadedTrack.artist).distinct().count()
        print(f"\nUnique Artists: {unique_artists}")
        
        # Unique albums
        unique_albums = session.query(DownloadedTrack.album).distinct().count()
        print(f"Unique Albums: {unique_albums}")
        
    except Exception as e:
        print(f"Error inspecting database: {e}")
    finally:
        session.close()

def debug_track_saving():
    """
    Debug function to test track saving functionality.
    """
    print("🔍 Debugging Track Saving Functionality 🔍")
    
    # Test track information
    test_tracks = [
        {
            'track_id': 'test_track_1',
            'title': 'Test Track 1',
            'artist': 'Test Artist 1',
            'file_path': '/path/to/test/track1.mp3',
            'is_video': False
        },
        {
            'track_id': 'test_track_2',
            'title': 'Test Track 2',
            'artist': 'Test Artist 2',
            'file_path': '/path/to/test/track2.mp4',
            'is_video': True
        }
    ]
    
    for track in test_tracks:
        print(f"\nTesting track: {track['title']}")
        try:
            # Attempt to save track
            result = DatabaseManager.add_track(
                track_id=track['track_id'],
                title=track['title'],
                artist=track['artist'],
                file_path=track['file_path'],
                is_video=track['is_video']
            )
            
            if result:
                print(f"✅ Successfully saved track: {track['title']}")
                print(f"   Track ID in DB: {result.id}")
            else:
                print(f"❌ Failed to save track: {track['title']}")
        
        except Exception as e:
            print(f"❌ Error saving track: {e}")
            traceback.print_exc()

def main():
    # Initialize database first
    DatabaseManager.init_db()
    
    # Run debug function
    debug_track_saving()
    
    # List all tracks after debugging
    print("\n📋 Current Database Contents:")
    tracks = DatabaseManager.search_tracks()
    for track in tracks:
        print(f"ID: {track.id}, Title: {track.title}, Artist: {track.artist}, File: {track.file_path}")

    # Run inspect_db function
    inspect_db()

if __name__ == '__main__':
    main()
