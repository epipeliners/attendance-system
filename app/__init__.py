"""
Inisialisasi package app.
"""
from flask import Flask
from app.config import config  # ← HAPUS 'app.' dari depan
from app.extensions import setup_logger  # ← HAPUS 'app.' dari depan
from app.utils.database import close_db, init_db  # ← HAPUS 'app.' dari depan

def create_app(config_name=None):
    """Factory function untuk membuat aplikasi Flask."""
    import os
    
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Setup logging
    setup_logger(app)
    
    # Setup database
    app.teardown_appcontext(close_db)
    
    # Initialize database tables
    with app.app_context():
        init_db()
    
    # Register blueprints
    from app.routes.auth import auth_bp  # ← HAPUS 'app.' dari depan
    from app.routes.main import main_bp  # ← HAPUS 'app.' dari depan
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    
    return app