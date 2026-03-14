import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask

def setup_logger(app):
    """Setup logging untuk aplikasi."""
    log_dir = app.config.get('LOG_DIR', 'logs')
    
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    
    max_bytes = app.config.get('LOG_MAX_BYTES', 10240)
    backup_count = app.config.get('LOG_BACKUP_COUNT', 10)
    
    file_handler = RotatingFileHandler(
        f'{log_dir}/attendance.log', 
        maxBytes=max_bytes, 
        backupCount=backup_count
    )
    
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    
    app.logger.info('Attendance application startup')