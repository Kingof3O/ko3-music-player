import os
import sys
import logging
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, 
    Boolean, Text, func, ForeignKey, UniqueConstraint, inspect
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, scoped_session, relationship
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

# Ensure logs directory exists
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure logging
LOG_FILE = os.path.join(LOGS_DIR, 'database.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Ensure the database directory exists
DATABASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATABASE_DIR, exist_ok=True)

# Database path
DATABASE_PATH = os.path.join(DATABASE_DIR, 'spotify_downloads.db')

# SQLAlchemy setup
Base = declarative_base()
engine = create_engine(
    f'sqlite:///{DATABASE_PATH}', 
    echo=False, 
    connect_args={'check_same_thread': False},
    poolclass=StaticPool
)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

class DatabaseContextManager:
    """Context manager for database sessions."""
    def __init__(self, session_factory=Session):
        self.session = session_factory()

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
                logger.error(f"Database transaction failed: {exc_val}")
        except Exception as e:
            logger.error(f"Error in database context manager: {e}")
        finally:
            self.session.close()

class DownloadedTrack(Base):
    """Model to track downloaded Spotify/YouTube tracks with enhanced metadata."""
    __tablename__ = 'downloaded_tracks'

    id = Column(Integer, primary_key=True)
    track_id = Column(String, unique=True, nullable=False)
    spotify_uri = Column(String, nullable=True)  
    youtube_id = Column(String)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    album = Column(String)
    duration = Column(Integer)  
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)  
    download_date = Column(DateTime, default=datetime.now)
    last_played = Column(DateTime)
    play_count = Column(Integer, default=0)
    is_video = Column(Boolean, default=False)
    download_source = Column(String)  
    audio_format = Column(String)  
    audio_quality = Column(String)  
    lyrics_file = Column(String)
    subtitle_file = Column(String)
    thumbnail_url = Column(String)
    additional_metadata = Column(String)  

    def __repr__(self):
        return f"<Track {self.title} by {self.artist}>"

class Playlist(Base):
    """Model to manage playlists."""
    __tablename__ = 'playlists'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    spotify_id = Column(String(100), unique=True, index=True)
    created_date = Column(DateTime, default=datetime.now, nullable=False)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_public = Column(Boolean, default=True)
    owner = Column(String(100))
    thumbnail_url = Column(String(1000))

    def __repr__(self):
        return f"<Playlist {self.name}>"

class PlaylistTrack(Base):
    """Association table for playlist tracks with position."""
    __tablename__ = 'playlist_tracks'

    playlist_id = Column(Integer, ForeignKey('playlists.id', ondelete='CASCADE'), primary_key=True)
    track_id = Column(Integer, ForeignKey('downloaded_tracks.id', ondelete='CASCADE'), primary_key=True)
    position = Column(Integer, nullable=False)
    date_added = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('playlist_id', 'position', name='unique_track_position'),
    )

class DownloadHistory(Base):
    """Track download history and statistics."""
    __tablename__ = 'download_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_downloads = Column(Integer, default=0)
    total_video_downloads = Column(Integer, default=0)
    total_audio_downloads = Column(Integer, default=0)
    total_playlists = Column(Integer, default=0)
    last_download_date = Column(DateTime)
    total_file_size = Column(Integer, default=0)  
    spotify_downloads = Column(Integer, default=0)
    youtube_downloads = Column(Integer, default=0)
    failed_downloads = Column(Integer, default=0)
    last_error = Column(Text)
    last_error_date = Column(DateTime)

    def __repr__(self):
        return f"<DownloadHistory total:{self.total_downloads}>"

class DatabaseManager:
    """Comprehensive database management utility."""
    
    @classmethod
    def init_db(cls):
        """Initialize the database with comprehensive error handling and verification."""
        try:
            logger.info("Starting database initialization...")
            
            # Create tables
            logger.info("Creating database tables...")
            Base.metadata.create_all(engine)
            
            # Verify tables were created
            inspector = inspect(engine)
            expected_tables = {'downloaded_tracks', 'playlists', 'playlist_tracks', 'download_history'}
            actual_tables = set(inspector.get_table_names())
            
            logger.info(f"Expected tables: {expected_tables}")
            logger.info(f"Actual tables: {actual_tables}")
            
            if not expected_tables.issubset(actual_tables):
                missing_tables = expected_tables - actual_tables
                raise Exception(f"Missing tables: {missing_tables}")
            
            # Initialize download history if it doesn't exist
            with Session() as session:
                history = session.query(DownloadHistory).first()
                if not history:
                    logger.info("Creating initial download history record...")
                    history = DownloadHistory(
                        total_downloads=0,
                        total_video_downloads=0,
                        total_audio_downloads=0,
                        total_playlists=0,
                        total_file_size=0,
                        spotify_downloads=0,
                        youtube_downloads=0,
                        failed_downloads=0
                    )
                    session.add(history)
                    session.commit()
                    logger.info("Download history initialized successfully")
                else:
                    logger.info("Download history record already exists")
                
                # Log current statistics
                logger.info(f"Current download history: {history}")
                
            logger.info("Database initialization completed successfully")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error during database initialization: {str(e)}")
            logger.exception("Full traceback:")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during database initialization: {str(e)}")
            logger.exception("Full traceback:")
            raise

    @classmethod
    def migrate_database(cls):
        """Migrate the database to the latest schema."""
        try:
            logger.info("Starting database migration...")
            
            # Create backup of existing database
            if os.path.exists(DATABASE_PATH):
                backup_path = f"{DATABASE_PATH}.backup"
                import shutil
                shutil.copy2(DATABASE_PATH, backup_path)
                logger.info(f"Created database backup at: {backup_path}")
            
            # Drop all tables and recreate with new schema
            Base.metadata.drop_all(engine)
            logger.info("Dropped existing tables")
            
            # Create new tables
            Base.metadata.create_all(engine)
            logger.info("Created new tables with updated schema")
            
            # Initialize download history
            with Session() as session:
                history = DownloadHistory()
                session.add(history)
                session.commit()
                logger.info("Initialized new download history")
            
            logger.info("Database migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during database migration: {e}")
            logger.exception("Full traceback:")
            return False

    @classmethod
    def needs_migration(cls):
        """Check if database needs migration."""
        try:
            inspector = inspect(engine)
            if not os.path.exists(DATABASE_PATH):
                return True
                
            # Check for all expected columns in downloaded_tracks
            columns = {c['name'] for c in inspector.get_columns('downloaded_tracks')}
            expected_columns = {
                'id', 'track_id', 'spotify_uri', 'youtube_id', 'title', 'artist',
                'album', 'duration', 'file_path', 'file_size', 'download_date',
                'last_played', 'play_count', 'is_video', 'download_source',
                'audio_format', 'audio_quality', 'lyrics_file', 'subtitle_file',
                'thumbnail_url', 'additional_metadata'
            }
            
            missing_columns = expected_columns - columns
            if missing_columns:
                logger.info(f"Database needs migration. Missing columns: {missing_columns}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking migration status: {e}")
            return True

    @staticmethod
    def add_track(
            track_id: str, 
            title: str, 
            artist: str, 
            file_path: str, 
            album: Optional[str] = None,
            is_video: bool = False,
            spotify_uri: Optional[str] = None,
            youtube_id: Optional[str] = None,
            duration: Optional[int] = None,
            file_size: Optional[int] = None,
            audio_format: Optional[str] = None,
            audio_quality: Optional[str] = None,
            thumbnail_url: Optional[str] = None,
            download_source: Optional[str] = None,
            has_subtitles: bool = False,
            additional_metadata: Optional[str] = None
        ):
        """
        Add a track to the database with comprehensive metadata.
        
        :param track_id: Unique identifier for the track
        :param title: Track title
        :param artist: Track artist(s)
        :param file_path: Path to the downloaded file
        :param album: Album name
        :param is_video: Whether the track is a video
        :param spotify_uri: Spotify URI for the track
        :param duration: Track duration in milliseconds
        :param file_size: Size of the downloaded file
        :param thumbnail_url: URL of the track's thumbnail
        :param download_source: Source of the download (e.g., 'spotify', 'youtube')
        :param audio_format: Format of the audio file
        :param has_subtitles: Whether subtitles are available
        :param additional_metadata: JSON string of additional track metadata
        """
        logger.info(f"=== Adding track to database ===")
        logger.info(f"Track ID: {track_id}")
        logger.info(f"Title: {title}")
        logger.info(f"Artist: {artist}")
        logger.info(f"Album: {album}")
        logger.info(f"File Path: {file_path}")

        try:
            with DatabaseContextManager() as session:
                # Check if track already exists by track_id
                existing_track = session.query(DownloadedTrack).filter_by(track_id=track_id).first()
                
                if existing_track:
                    logger.info(f"Track already exists in database: {title}")
                    # Update existing track with new information if needed
                    if spotify_uri and not existing_track.spotify_uri:
                        existing_track.spotify_uri = spotify_uri
                    if youtube_id and not existing_track.youtube_id:
                        existing_track.youtube_id = youtube_id
                    if thumbnail_url and not existing_track.thumbnail_url:
                        existing_track.thumbnail_url = thumbnail_url
                    session.commit()
                    return existing_track

                # Create new track
                track = DownloadedTrack(
                    track_id=track_id,
                    title=title,
                    artist=artist,
                    album=album,
                    file_path=file_path,
                    is_video=is_video,
                    spotify_uri=spotify_uri if spotify_uri else None,  
                    youtube_id=youtube_id,
                    duration=duration,
                    file_size=file_size,
                    download_date=datetime.now(),
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                    thumbnail_url=thumbnail_url,
                    download_source=download_source,
                    subtitle_file=None if not has_subtitles else f"{os.path.splitext(file_path)[0]}.vtt",
                    additional_metadata=additional_metadata
                )

                try:
                    # Add track to session
                    session.add(track)
                    session.flush()  
                    logger.info(f"Added track to session, ID: {track.id}")
                    
                    # Update download history
                    history = session.query(DownloadHistory).first()
                    if history:
                        history.total_downloads += 1
                        if is_video:
                            history.total_video_downloads += 1
                        else:
                            history.total_audio_downloads += 1
                        history.total_file_size += file_size if file_size else 0
                        history.last_download_date = datetime.now()
                        if download_source == 'Spotify':
                            history.spotify_downloads += 1
                        elif download_source == 'YouTube':
                            history.youtube_downloads += 1
                    else:
                        logger.warning("No download history found, creating new record")
                        history = DownloadHistory(
                            total_downloads=1,
                            total_video_downloads=1 if is_video else 0,
                            total_audio_downloads=0 if is_video else 1,
                            total_file_size=file_size if file_size else 0,
                            spotify_downloads=1 if download_source == 'Spotify' else 0,
                            youtube_downloads=1 if download_source == 'YouTube' else 0,
                            last_download_date=datetime.now()
                        )
                        session.add(history)
                    
                    # Commit the transaction
                    session.commit()
                    logger.info(f"Successfully committed track to database: {title}")
                    return track
                    
                except SQLAlchemyError as e:
                    session.rollback()
                    logger.error(f"Database error while saving track {title}: {e}")
                    logger.exception("Database error traceback:")
                    return None

        except Exception as e:
            logger.error(f"Unexpected error adding track {title}: {e}")
            logger.exception("Full error traceback:")
            return None

    @staticmethod
    def get_track_by_id(track_id: str) -> Optional[DownloadedTrack]:
        """Retrieve a track by its track_id."""
        try:
            with DatabaseContextManager() as session:
                return session.query(DownloadedTrack).filter_by(track_id=track_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving track: {e}")
            return None

    @staticmethod
    def search_tracks(
        query: Optional[str] = None, 
        artist: Optional[str] = None, 
        album: Optional[str] = None,
        is_video: Optional[bool] = None
    ) -> List[DownloadedTrack]:
        """
        Advanced track search with multiple filters.
        
        :param query: Search term across title, artist, album
        :param artist: Filter by artist
        :param album: Filter by album
        :param is_video: Filter by video/audio type
        :return: List of matching tracks
        """
        try:
            with DatabaseContextManager() as session:
                search_query = session.query(DownloadedTrack)
                
                if query:
                    search_query = search_query.filter(
                        (DownloadedTrack.title.ilike(f'%{query}%')) | 
                        (DownloadedTrack.artist.ilike(f'%{query}%')) |
                        (DownloadedTrack.album.ilike(f'%{query}%'))
                    )
                
                if artist:
                    search_query = search_query.filter(DownloadedTrack.artist.ilike(f'%{artist}%'))
                
                if album:
                    search_query = search_query.filter(DownloadedTrack.album.ilike(f'%{album}%'))
                
                if is_video is not None:
                    search_query = search_query.filter(DownloadedTrack.is_video == is_video)
                
                return search_query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error searching tracks: {e}")
            return []

    @staticmethod
    def get_download_statistics() -> Dict[str, Any]:
        """
        Retrieve comprehensive download statistics.
        
        :return: Dictionary of download statistics
        """
        try:
            with DatabaseContextManager() as session:
                history = session.query(DownloadHistory).first()
                
                # Additional statistics
                total_artists = session.query(func.count(DownloadedTrack.artist.distinct())).scalar()
                total_albums = session.query(func.count(DownloadedTrack.album.distinct())).scalar()
                
                return {
                    'total_downloads': history.total_downloads,
                    'total_video_downloads': history.total_video_downloads,
                    'total_audio_downloads': history.total_audio_downloads,
                    'last_download_date': history.last_download_date,
                    'total_file_size_bytes': history.total_file_size,
                    'total_unique_artists': total_artists,
                    'total_unique_albums': total_albums
                }
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving download statistics: {e}")
            return {}

    @classmethod
    def display_database_contents(cls):
        """Display all contents of the database for debugging purposes."""
        try:
            with Session() as session:
                # Display all tracks
                print("\n=== Downloaded Tracks ===")
                tracks = session.query(DownloadedTrack).all()
                if tracks:
                    for track in tracks:
                        print(f"\nTrack: {track.title}")
                        print(f"Artist: {track.artist}")
                        print(f"Album: {track.album}")
                        print(f"File: {track.file_path}")
                        print(f"Download Date: {track.download_date}")
                        print(f"Is Video: {track.is_video}")
                        print(f"File exists: {os.path.exists(track.file_path)}")
                else:
                    print("No tracks found in database")

                # Display all playlists
                print("\n=== Playlists ===")
                playlists = session.query(Playlist).all()
                if playlists:
                    for playlist in playlists:
                        print(f"\nPlaylist: {playlist.name}")
                        track_count = session.query(PlaylistTrack).filter_by(playlist_id=playlist.id).count()
                        print(f"Track Count: {track_count}")
                        print(f"Created: {playlist.created_date}")
                else:
                    print("No playlists found in database")

                # Display download history
                print("\n=== Download History ===")
                history = session.query(DownloadHistory).first()
                if history:
                    print(f"Total Downloads: {history.total_downloads}")
                    print(f"Video Downloads: {history.total_video_downloads}")
                    print(f"Audio Downloads: {history.total_audio_downloads}")
                    print(f"Failed Downloads: {history.failed_downloads}")
                    print(f"Total File Size: {history.total_file_size} bytes")
                    print(f"Last Download: {history.last_download_date}")
                    if history.last_error:
                        print(f"Last Error: {history.last_error}")
                        print(f"Last Error Date: {history.last_error_date}")
                else:
                    print("No download history found")

        except Exception as e:
            print(f"Error displaying database contents: {e}")

def main():
    """Command-line interface for database operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Spotify Downloads Database Utility")
    parser.add_argument('--init', action='store_true', help='Initialize the database')
    parser.add_argument('--stats', action='store_true', help='Show download statistics')
    parser.add_argument('--search', type=str, help='Search tracks by query')
    parser.add_argument('--display', action='store_true', help='Display database contents')
    parser.add_argument('--migrate', action='store_true', help='Migrate the database')
    
    args = parser.parse_args()
    
    if args.init:
        DatabaseManager.init_db()
    elif args.stats:
        stats = DatabaseManager.get_download_statistics()
        for key, value in stats.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
    elif args.search:
        tracks = DatabaseManager.search_tracks(query=args.search)
        for track in tracks:
            print(f"{track.title} by {track.artist} (Album: {track.album})")
    elif args.display:
        DatabaseManager.display_database_contents()
    elif args.migrate:
        if DatabaseManager.needs_migration():
            DatabaseManager.migrate_database()
        else:
            print("Database is up to date")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
