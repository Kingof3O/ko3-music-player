# Spotify Downloader Database Usage Guide

## Overview
The database management system for the Spotify Downloader provides robust tracking and querying capabilities for downloaded tracks.

## Key Features
- Comprehensive track metadata tracking
- Advanced search and filtering
- Download statistics
- Logging and error handling
- Flexible database operations

## Database Models

### DownloadedTrack
Tracks individual downloaded songs/videos with detailed metadata:
- `id`: Unique database identifier
- `track_id`: Unique track identifier
- `spotify_uri`: Spotify track URI
- `title`: Track title
- `artist`: Track artist
- `album`: Album name
- `file_path`: Local file path
- `download_date`: Download timestamp
- `is_video`: Video/audio type flag
- `file_size`: File size in bytes
- `download_source`: Download origin (Spotify/YouTube)
- `additional_metadata`: Extra track information

### DownloadHistory
Tracks overall download statistics:
- `total_downloads`: Total number of downloads
- `total_video_downloads`: Video download count
- `total_audio_downloads`: Audio download count
- `last_download_date`: Timestamp of most recent download
- `total_file_size`: Cumulative size of all downloads

## Usage Examples

### Command-line Operations
```bash
# Initialize database
python src/database.py --init

# Search tracks
python src/database.py --search "Beatles"

# Get download statistics
python src/database.py --stats
```

### Programmatic Usage in Python

#### Initialization
```python
from database import DatabaseManager

# Initialize database (create tables)
DatabaseManager.init_db()
```

#### Adding a Track
```python
track = DatabaseManager.add_track(
    track_id='spotify:track:123',
    title='Hey Jude',
    artist='The Beatles',
    file_path='/downloads/hey_jude.mp3',
    album='The Beatles (White Album)',
    is_video=False,
    file_size=5242880,  # 5 MB
    download_source='Spotify'
)
```

#### Searching Tracks
```python
# Search by query
tracks = DatabaseManager.search_tracks(query='Beatles')

# Filter by artist
tracks = DatabaseManager.search_tracks(artist='The Beatles')

# Filter by video/audio type
video_tracks = DatabaseManager.search_tracks(is_video=True)
```

#### Retrieving Track
```python
# Get track by track ID
track = DatabaseManager.get_track_by_id('spotify:track:123')
```

#### Get Download Statistics
```python
stats = DatabaseManager.get_download_statistics()
print(f"Total Downloads: {stats['total_downloads']}")
print(f"Total File Size: {stats['total_file_size_bytes']} bytes")
```

## Best Practices
1. Always use `DatabaseManager` methods for database interactions
2. Handle potential `None` returns from database methods
3. Use context managers for database sessions
4. Log and handle database-related exceptions

## Logging
- Logs are stored in `logs/database.log`
- Includes timestamps, log levels, and detailed error messages

## Error Handling
- Comprehensive error logging
- Graceful handling of database exceptions
- Rollback mechanisms for failed transactions

## Performance Considerations
- Uses SQLAlchemy's scoped session for connection pooling
- Indexed columns for faster querying
- Lightweight logging to minimize performance impact

## Security
- No direct credential storage in database
- Supports storing additional metadata securely
- Follows best practices for database interactions

## Troubleshooting
- Check `logs/database.log` for detailed error information
- Ensure database file permissions are correct
- Verify SQLAlchemy and SQLite dependencies are installed
