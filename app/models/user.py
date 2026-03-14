"""
Model untuk User.
"""
from app.utils.database import query_db, execute_db
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session

class User:
    """Class untuk mengelola data user."""
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID."""
        return query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
    
    @staticmethod
    def get_by_username(username):
        """Get user by username."""
        return query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
    
    @staticmethod
    def create(username, password, role='cs'):
        """Create new user."""
        hashed = generate_password_hash(password)
        return execute_db(
            'INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)',
            [username, hashed, role, 'auto']
        )
    
    @staticmethod
    def delete(user_id):
        """Delete user by ID."""
        return execute_db('DELETE FROM users WHERE id = ?', [user_id])
    
    @staticmethod
    def update_shift(user_id, shift):
        """Update user's default shift."""
        if shift not in ['morning', 'night', 'gantung_pagi', 'gantung_malam', 'auto']:
            return False
        return execute_db('UPDATE users SET default_shift = ? WHERE id = ?', [shift, user_id])
    
    @staticmethod
    def get_all():
        """Get all users."""
        return query_db('SELECT id, username, role, default_shift FROM users ORDER BY id')
    
    @staticmethod
    def check_password(user, password):
        """Check if password matches."""
        return check_password_hash(user['password'], password)
    
    @staticmethod
    def login(username, password):
        """
        Attempt to login user.
        Returns user dict if successful, None otherwise.
        """
        user = User.get_by_username(username)
        if user and User.check_password(user, password):
            return user
        return None
    
    @staticmethod
    def change_password(user_id, new_password):
        """Change user password."""
        hashed = generate_password_hash(new_password)
        return execute_db('UPDATE users SET password = ? WHERE id = ?', [hashed, user_id])