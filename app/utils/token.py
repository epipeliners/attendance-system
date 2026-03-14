"""
JWT token utilities for password reset and 2FA.
"""
import jwt
from datetime import datetime, timedelta
from flask import current_app

def generate_reset_token(user_id, email, expires_in=1800):  # 30 minutes default
    """Generate JWT token for password reset."""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'type': 'reset'
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def verify_reset_token(token):
    """Verify and decode reset token."""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        if payload.get('type') != 'reset':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token expired
    except jwt.InvalidTokenError:
        return None  # Invalid token

def generate_2fa_token(user_id, expires_in=600):  # 10 minutes for 2FA setup
    """Generate token for 2FA setup verification."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'type': '2fa_setup'
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def verify_2fa_token(token):
    """Verify 2FA setup token."""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        if payload.get('type') != '2fa_setup':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None