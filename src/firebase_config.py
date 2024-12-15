import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token
from google.auth.transport import requests
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

def init_firebase():
    """Initialize Firebase with error handling"""
    try:
        # Check if already initialized
        if not firebase_admin._apps:
            # Try to get credentials from environment variables first
            if os.getenv('FIREBASE_CREDENTIALS'):
                cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
                cred = credentials.Certificate(cred_dict)
            else:
                # Fall back to file-based credentials
                cred_path = os.path.join('config', 'firebase-key.json')
                if not os.path.exists(cred_path):
                    template_path = os.path.join('config', 'firebase-credentials-template.json')
                    logger.error(f"Firebase credentials not found. Please copy {template_path} to {cred_path} and fill in your credentials.")
                    raise FileNotFoundError(f"Firebase credentials not found. See {template_path} for required format.")

                cred = credentials.Certificate(cred_path)
            
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")

        return firestore.client()
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")
        raise

def verify_google_token(token):
    """Verify Google ID token"""
    try:
        # Get client ID from environment variable or config
        client_id = os.getenv('GOOGLE_CLIENT_ID', '994704832149-i9sff9ergovs86n0nt0vkburkcp9m1ai.apps.googleusercontent.com')
        
        # Verify the token
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)
        
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Invalid issuer')
            
        return idinfo
    except Exception as e:
        logger.error(f"Error verifying Google token: {e}")
        return None

# Initialize Firestore client
try:
    db = init_firebase()
    logger.info("Firestore client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Firestore client: {e}")
    db = None
