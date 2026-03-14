"""
Helper functions umum.
"""
from datetime import datetime
from app.config import config
import os

active_config = config[os.environ.get('FLASK_CONFIG', 'default')]
TIMEZONE = active_config.TIMEZONE

def now_local():
    """Return current datetime in the configured timezone."""
    return datetime.now(TIMEZONE)

def format_datetime(dt):
    """Format datetime to string."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def format_minutes(minutes):
    """Convert minutes to readable format (X jam Y menit)."""
    if minutes is None or minutes == 0:
        return "-"
    
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    
    if hours > 0 and mins > 0:
        return f"{hours} jam {mins} menit"
    elif hours > 0:
        return f"{hours} jam"
    elif mins > 0:
        return f"{mins} menit"
    else:
        return "-"

def get_count_from_result(result):
    """Get count from different result types (PostgreSQL vs SQLite)."""
    if result is None:
        return 0
    if isinstance(result, dict):
        return result.get('cnt', 0)
    elif isinstance(result, tuple):
        return result[0] if result else 0
    elif hasattr(result, 'cnt'):
        return result.cnt
    else:
        return 0