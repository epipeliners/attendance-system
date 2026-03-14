import os
import secrets
import pytz

class Config:
    """Konfigurasi dasar aplikasi."""
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    DATABASE_URL = os.environ.get('DATABASE_URL')
    TIMEZONE = pytz.timezone('Asia/Jakarta')
    DEBUG = False
    LOG_DIR = 'logs'
    LOG_MAX_BYTES = 10240
    LOG_BACKUP_COUNT = 10

class DevelopmentConfig(Config):
    """Konfigurasi untuk development."""
    DEBUG = True

class ProductionConfig(Config):
    """Konfigurasi untuk production."""
    DEBUG = False

# Dictionary untuk memudahkan pemilihan config
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}