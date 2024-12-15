import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class FirebaseService:
    _instance = None
    
    def __init__(self):
        if not firebase_admin._apps:
            # Initialize Firebase Admin SDK
            cred = credentials.Certificate('firebase-credentials.json')
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def add_track(self, track_data):
        """Add a track to Firestore"""
        try:
            # Convert datetime objects to timestamps
            if isinstance(track_data.get('download_date'), datetime):
                track_data['download_date'] = firestore.SERVER_TIMESTAMP
            
            # Convert any other datetime objects in additional_metadata
            if 'additional_metadata' in track_data:
                for key, value in track_data['additional_metadata'].items():
                    if isinstance(value, datetime):
                        track_data['additional_metadata'][key] = value.isoformat()
            
            # Add the track to Firestore
            doc_ref = self.db.collection('tracks').document()
            doc_ref.set(track_data)
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Error adding track to Firestore: {e}")
            return None
    
    def get_all_tracks(self):
        """Get all tracks from Firestore"""
        try:
            tracks_ref = self.db.collection('tracks')
            docs = tracks_ref.order_by('download_date', direction=firestore.Query.DESCENDING).stream()
            return [doc.to_dict() | {'id': doc.id} for doc in docs]
        except Exception as e:
            logger.error(f"Error getting tracks from Firestore: {e}")
            return []
    
    def delete_track(self, track_id):
        """Delete a track from Firestore"""
        try:
            self.db.collection('tracks').document(track_id).delete()
            return True
        except Exception as e:
            logger.error(f"Error deleting track from Firestore: {e}")
            return False
    
    def update_track(self, track_id, track_data):
        """Update a track in Firestore"""
        try:
            self.db.collection('tracks').document(track_id).update(track_data)
            return True
        except Exception as e:
            logger.error(f"Error updating track in Firestore: {e}")
            return False
    
    def add_playlist(self, playlist_data):
        """Add a playlist to Firestore"""
        try:
            doc_ref = self.db.collection('playlists').document()
            doc_ref.set(playlist_data)
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error adding playlist to Firestore: {e}")
            return None
    
    def get_all_playlists(self):
        """Get all playlists from Firestore"""
        try:
            playlists_ref = self.db.collection('playlists')
            docs = playlists_ref.stream()
            return [doc.to_dict() | {'id': doc.id} for doc in docs]
        except Exception as e:
            logger.error(f"Error getting playlists from Firestore: {e}")
            return []
    
    def add_track_to_playlist(self, playlist_id, track_id):
        """Add a track to a playlist"""
        try:
            playlist_track = {
                'track_id': track_id,
                'added_date': firestore.SERVER_TIMESTAMP
            }
            self.db.collection('playlists').document(playlist_id)\
                .collection('tracks').add(playlist_track)
            return True
        except Exception as e:
            logger.error(f"Error adding track to playlist: {e}")
            return False
    
    def get_playlist_tracks(self, playlist_id):
        """Get all tracks in a playlist"""
        try:
            tracks_ref = self.db.collection('playlists').document(playlist_id)\
                .collection('tracks').order_by('added_date').stream()
            track_ids = [doc.to_dict()['track_id'] for doc in tracks_ref]
            
            # Get track details
            tracks = []
            for track_id in track_ids:
                track_doc = self.db.collection('tracks').document(track_id).get()
                if track_doc.exists:
                    track_data = track_doc.to_dict()
                    track_data['id'] = track_doc.id
                    tracks.append(track_data)
            
            return tracks
        except Exception as e:
            logger.error(f"Error getting playlist tracks: {e}")
            return []
