from flask_login import UserMixin
import logging
import json
import os

logger = logging.getLogger(__name__)

class User(UserMixin):
    # Local storage path for development
    LOCAL_STORAGE_PATH = 'data/users.json'

    def __init__(self, user_id, email, name=None, profile_pic=None):
        self.id = user_id
        self.email = email
        self.name = name
        self.profile_pic = profile_pic

    @staticmethod
    def _ensure_local_storage():
        """Ensure local storage directory and file exist"""
        os.makedirs('data', exist_ok=True)
        if not os.path.exists(User.LOCAL_STORAGE_PATH):
            with open(User.LOCAL_STORAGE_PATH, 'w') as f:
                json.dump({}, f)

    @staticmethod
    def _get_local_users():
        """Get users from local storage"""
        User._ensure_local_storage()
        try:
            with open(User.LOCAL_STORAGE_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading local storage: {e}")
            return {}

    @staticmethod
    def _save_local_users(users):
        """Save users to local storage"""
        User._ensure_local_storage()
        try:
            with open(User.LOCAL_STORAGE_PATH, 'w') as f:
                json.dump(users, f)
            return True
        except Exception as e:
            logger.error(f"Error writing to local storage: {e}")
            return False

    @staticmethod
    def get(user_id, db):
        try:
            # Try Firestore first
            if db:
                try:
                    user_doc = db.collection('users').document(user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        return User(
                            user_id=user_id,
                            email=user_data.get('email'),
                            name=user_data.get('name'),
                            profile_pic=user_data.get('profile_pic')
                        )
                except Exception as e:
                    logger.error(f"Error getting user from Firestore: {e}")

            # Fallback to local storage
            users = User._get_local_users()
            if user_id in users:
                user_data = users[user_id]
                return User(
                    user_id=user_id,
                    email=user_data.get('email'),
                    name=user_data.get('name'),
                    profile_pic=user_data.get('profile_pic')
                )
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    def save_to_db(self, db):
        try:
            # Try Firestore first
            if db:
                try:
                    db.collection('users').document(self.id).set({
                        'email': self.email,
                        'name': self.name,
                        'profile_pic': self.profile_pic
                    })
                except Exception as e:
                    logger.error(f"Error saving user to Firestore: {e}")

            # Always save to local storage as backup
            users = User._get_local_users()
            users[self.id] = {
                'email': self.email,
                'name': self.name,
                'profile_pic': self.profile_pic
            }
            return User._save_local_users(users)
        except Exception as e:
            logger.error(f"Error saving user: {e}")
            return False

    def get_id(self):
        return self.id
