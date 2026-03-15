import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(app):
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    handler = RotatingFileHandler('logs/attendance.log', maxBytes=10240, backupCount=10)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Attendance application startup')