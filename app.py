import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file
from werkzeug.security import check_password_hash, generate_password_hash
import secrets
import logging
from logging.handlers import RotatingFileHandler
import io
import openpyxl
from openpyxl.styles import Font, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
import pytz
import re

# Import IP Manager
from ip_manager.ip_routes import ip_bp
from ip_manager.ip_model import IPModel

# ---------- Timezone setup ----------
TIMEZONE = pytz.timezone('Asia/Jakarta')

def now_local():
    """Return current datetime in the configured timezone (aware)."""
    return datetime.now(TIMEZONE)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Setup logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/attendance.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Attendance application startup')

# Register Blueprint
app.register_blueprint(ip_bp)

# ---------- Database connection helpers ----------
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    """Get database connection based on environment."""
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        if not hasattr(g, '_database'):
            g._database = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return g._database
    else:
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect('attendance.db')
            db.row_factory = sqlite3.Row
        return db

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection at end of request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Execute a query and return results."""
    try:
        conn = get_db()
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            cur = conn.cursor()
            cur.execute(query.replace('?', '%s'), args)
            rv = cur.fetchall()
            cur.close()
            return (rv[0] if rv else None) if one else rv
        else:
            cur = conn.execute(query, args)
            rv = cur.fetchall()
            cur.close()
            return (rv[0] if rv else None) if one else rv
    except Exception as e:
        app.logger.error(f"Database query error: {str(e)}")
        raise

def execute_db(query, args=()):
    """Execute a query that modifies the database."""
    try:
        conn = get_db()
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            cur = conn.cursor()
            cur.execute(query.replace('?', '%s'), args)
            conn.commit()
            cur.close()
            return None
        else:
            cur = conn.execute(query, args)
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        app.logger.error(f"Database execute error: {str(e)}")
        raise

# ---------- Helper Functions ----------
def validate_username(username):
    """Validate username format."""
    if not username or len(username) < 3 or len(username) > 50:
        return False, "Username must be between 3 and 50 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, None

def validate_password(password):
    """Validate password strength."""
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters"
    if len(password) > 100:
        return False, "Password too long"
    return True, None

def validate_date(date_str):
    """Validate date format YYYY-MM-DD."""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True, None
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD"

def validate_time(time_str):
    """Validate time format HH:MM."""
    try:
        datetime.strptime(time_str, '%H:%M')
        return True, None
    except ValueError:
        return False, "Invalid time format. Use HH:MM"

def sanitize_input(input_str):
    """Sanitize user input to prevent XSS."""
    if input_str is None:
        return None
    return re.sub(r'<[^>]*>', '', input_str.strip())

def get_count_from_result(result):
    """Helper function to get count from different result types."""
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

# ---------- IP Address Functions ----------
def get_client_ip():
    """Dapatkan IP address client dari request."""
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr
    return ip

def log_user_ip(user_id, action='login'):
    """Catat IP address user ke database."""
    try:
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent')
        now_str = now_local().strftime('%Y-%m-%d %H:%M:%S')
        
        execute_db('''
            INSERT INTO ip_logs (user_id, ip_address, user_agent, action, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', [user_id, ip_address, user_agent, action, now_str])
        
        app.logger.info(f"IP logged for user {user_id}: {ip_address}")
    except Exception as e:
        app.logger.error(f"Error logging IP: {str(e)}")

# ---------- IP Whitelist Functions ----------
def is_ip_whitelist_enabled():
    """Cek apakah fitur whitelist sedang aktif."""
    result = query_db("SELECT setting_value FROM app_settings WHERE setting_key = 'ip_whitelist_enabled'", one=True)
    return result and result['setting_value'].lower() == 'true'

def is_ip_allowed(ip_address, user_role=None):
    """
    Cek apakah IP diizinkan.
    Jika exclude_admins = True, admin selalu diizinkan.
    """
    # ADMIN SELALU DIIZINKAN
    if user_role == 'admin':
        return True, "Admin always allowed"
    
    # Cek apakah whitelist aktif
    if not is_ip_whitelist_enabled():
        return True, "Whitelist disabled"
    
    # Cek apakah IP ada di whitelist
    result = query_db('SELECT * FROM ip_whitelist WHERE ip_address = ? AND is_active = 1', [ip_address], one=True)
    
    if result:
        return True, "IP allowed"
    else:
        return False, "IP not in whitelist"

def whitelist_decorator(f):
    """Decorator untuk mengecek whitelist di setiap route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.endpoint in ['login', 'static']:
            return f(*args, **kwargs)
        
        ip = get_client_ip()
        user_role = session.get('role')
        allowed, message = is_ip_allowed(ip, user_role)
        
        if not allowed:
            app.logger.warning(f"Blocked access from IP {ip} to {request.path}")
            return render_template('ip_blocked.html', ip=ip), 403
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required_with_whitelist(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        
        ip = get_client_ip()
        allowed, message = is_ip_allowed(ip, 'admin')
        
        if not allowed:
            app.logger.warning(f"Blocked admin access from IP {ip}")
            return render_template('ip_blocked.html', ip=ip), 403
        
        return f(*args, **kwargs)
    return decorated_function

# ---------- Database initialization ----------
def init_db():
    """Create tables if they don't exist."""
    try:
        conn = get_db()
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            cur = conn.cursor()
            
            # Users table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    default_shift TEXT DEFAULT 'auto'
                )
            ''')
            
            # Attendance table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    note TEXT,
                    shift TEXT,
                    late_minutes INTEGER,
                    penalty_level INTEGER,
                    expected_checkout TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Breaks table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    break_type TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    phone_used BOOLEAN DEFAULT FALSE,
                    note TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Off days table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS off_days (
                    id SERIAL PRIMARY KEY,
                    date DATE UNIQUE NOT NULL,
                    description TEXT
                )
            ''')
            
            # Rules table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rules (
                    id SERIAL PRIMARY KEY,
                    rule_name TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')
            
            # User debt table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_debt (
                    user_id INTEGER PRIMARY KEY,
                    owed_minutes INTEGER DEFAULT 0,
                    updated_at TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # IP Logs table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS ip_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    action TEXT DEFAULT 'login',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_user_id ON ip_logs(user_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_created_at ON ip_logs(created_at)')
            
            # IP Whitelist table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS ip_whitelist (
                    id SERIAL PRIMARY KEY,
                    ip_address TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                )
            ''')
            
            # App Settings table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    id SERIAL PRIMARY KEY,
                    setting_key TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Check if admin exists
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()['count'] == 0:
                admin_password = secrets.token_urlsafe(12)
                hashed_password = generate_password_hash(admin_password)
                cur.execute(
                    "INSERT INTO users (username, password, role, default_shift) VALUES (%s, %s, %s, %s)",
                    ('admin', hashed_password, 'admin', 'auto')
                )
                app.logger.info(f"Admin user created with password: {admin_password}")
                print(f"\n⚠️  ADMIN PASSWORD GENERATED: {admin_password}")
                print("⚠️  SAVE THIS PASSWORD - IT WILL NOT BE SHOWN AGAIN!\n")
            
            # Insert default rules
            cur.execute("SELECT COUNT(*) FROM rules")
            if cur.fetchone()['count'] == 0:
                default_rules = [
                    ('max_breaks_per_day', '3'),
                    ('max_smoking_minutes', '10')
                ]
                for name, val in default_rules:
                    cur.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (name, val))
            
            # Insert default settings
            cur.execute("SELECT COUNT(*) FROM app_settings WHERE setting_key = 'ip_whitelist_enabled'")
            if cur.fetchone()['count'] == 0:
                cur.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (%s, %s)", 
                           ('ip_whitelist_enabled', 'false'))
            
            cur.execute("SELECT COUNT(*) FROM app_settings WHERE setting_key = 'whitelist_exclude_admins'")
            if cur.fetchone()['count'] == 0:
                cur.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (%s, %s)", 
                           ('whitelist_exclude_admins', 'true'))
            
            conn.commit()
            cur.close()
            
        else:
            # SQLite
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    default_shift TEXT DEFAULT 'auto'
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    note TEXT,
                    shift TEXT,
                    late_minutes INTEGER,
                    penalty_level INTEGER,
                    expected_checkout DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    break_type TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    duration INTEGER,
                    phone_used BOOLEAN DEFAULT 0,
                    note TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS off_days (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE NOT NULL,
                    description TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_debt (
                    user_id INTEGER PRIMARY KEY,
                    owed_minutes INTEGER DEFAULT 0,
                    updated_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ip_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    action TEXT DEFAULT 'login',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_user_id ON ip_logs(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_created_at ON ip_logs(created_at)')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ip_whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_by INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Check if admin exists
            cur = conn.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                admin_password = secrets.token_urlsafe(12)
                hashed_password = generate_password_hash(admin_password)
                conn.execute(
                    "INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)",
                    ('admin', hashed_password, 'admin', 'auto')
                )
                app.logger.info(f"Admin user created with password: {admin_password}")
                print(f"\n⚠️  ADMIN PASSWORD GENERATED: {admin_password}")
                print("⚠️  SAVE THIS PASSWORD - IT WILL NOT BE SHOWN AGAIN!\n")
            
            # Insert default rules
            cur = conn.execute("SELECT COUNT(*) FROM rules")
            if cur.fetchone()[0] == 0:
                default_rules = [
                    ('max_breaks_per_day', '3'),
                    ('max_smoking_minutes', '10')
                ]
                for name, val in default_rules:
                    conn.execute("INSERT INTO rules (rule_name, value) VALUES (?, ?)", (name, val))
            
            # Insert default settings
            cur = conn.execute("SELECT COUNT(*) FROM app_settings WHERE setting_key = 'ip_whitelist_enabled'")
            if cur.fetchone()[0] == 0:
                conn.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)", 
                           ('ip_whitelist_enabled', 'false'))
            
            cur = conn.execute("SELECT COUNT(*) FROM app_settings WHERE setting_key = 'whitelist_exclude_admins'")
            if cur.fetchone()[0] == 0:
                conn.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)", 
                           ('whitelist_exclude_admins', 'true'))
            
            conn.commit()
            
    except Exception as e:
        app.logger.error(f"Database initialization error: {str(e)}")
        raise

with app.app_context():
    init_db()
    IPModel.create_table()
    print("✅ Tabel IP logs siap")

# ---------- Business Logic Functions ----------
def get_active_break(user_id, break_type):
    """Return the active break (end_time NULL) for this user and type, or None."""
    try:
        row = query_db('''SELECT * FROM breaks 
                           WHERE user_id = ? AND break_type = ? AND end_time IS NULL 
                           ORDER BY start_time DESC LIMIT 1''', 
                        [user_id, break_type], one=True)
        if row:
            row_dict = dict(row)
            start_naive = datetime.strptime(row_dict['start_time'], '%Y-%m-%d %H:%M:%S')
            row_dict['start_time'] = TIMEZONE.localize(start_naive)
            return row_dict
        return None
    except Exception as e:
        app.logger.error(f"Error in get_active_break: {str(e)}")
        return None

def count_breaks_today(user_id, break_type=None):
    """Return number of breaks started today. If break_type specified, count only that type."""
    try:
        now = now_local()
        today_str = now.strftime('%Y-%m-%d')
        if break_type:
            result = query_db('''SELECT COUNT(*) as cnt FROM breaks 
                                 WHERE user_id = ? AND break_type = ? AND DATE(start_time) = ?''',
                              [user_id, break_type, today_str], one=True)
        else:
            result = query_db('''SELECT COUNT(*) as cnt FROM breaks 
                                 WHERE user_id = ? AND DATE(start_time) = ?''',
                              [user_id, today_str], one=True)
        return get_count_from_result(result)
    except Exception as e:
        app.logger.error(f"Error in count_breaks_today: {str(e)}")
        return 0

def count_monthly_late_level4(user_id, current_date):
    """Count how many times this month the user has been late at level >=4 (excluding today)."""
    try:
        first_day = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
        today_str = current_date.strftime('%Y-%m-%d')
        result = query_db('''SELECT COUNT(*) as cnt FROM attendance 
                             WHERE user_id = ? AND action = 'Check In' 
                               AND penalty_level >= 4 
                               AND timestamp >= ? 
                               AND DATE(timestamp) < DATE(?)''',
                          [user_id, first_day_str, today_str], one=True)
        return get_count_from_result(result)
    except Exception as e:
        app.logger.error(f"Error in count_monthly_late_level4: {str(e)}")
        return 0

def determine_user_shift(user_id, now):
    """
    Determine shift for a user based on their default_shift setting.
    Returns (shift, official_start_datetime, warning_note, is_auto)
    Options: 'morning', 'night', 'gantung_pagi', 'gantung_malam', 'auto'
    """
    try:
        user = query_db('SELECT default_shift FROM users WHERE id = ?', [user_id], one=True)
        user_shift = user['default_shift'] if user and user['default_shift'] else 'auto'
        
        local_time = now.astimezone(TIMEZONE)
        current_hour = local_time.hour
        warning_note = None
        
        # MORNING SHIFT (10:00 - 22:00)
        if user_shift == 'morning':
            shift = 'morning'
            official = local_time.replace(hour=10, minute=0, second=0, microsecond=0)
            if current_hour < 10 or current_hour >= 22:
                warning_note = f"Warning: Check-in at {current_hour}:00 outside morning shift hours (10:00-22:00)"
            return shift, official, warning_note, False
        
        # NIGHT SHIFT (22:00 - 10:00)
        elif user_shift == 'night':
            shift = 'night'
            if current_hour < 10:
                # After midnight, official start yesterday 22:00
                yesterday = local_time - timedelta(days=1)
                official = yesterday.replace(hour=22, minute=0, second=0, microsecond=0)
            else:
                official = local_time.replace(hour=22, minute=0, second=0, microsecond=0)
            
            if 10 <= current_hour < 22:
                warning_note = f"Warning: Check-in at {current_hour}:00 outside night shift hours (22:00-10:00)"
            return shift, official, warning_note, False
        
        # GANTUNG PAGI (12:00 - 00:00)
        elif user_shift == 'gantung_pagi':
            shift = 'gantung_pagi'
            official = local_time.replace(hour=12, minute=0, second=0, microsecond=0)
            
            # Cek apakah dalam rentang 12:00 - 00:00
            if current_hour < 12:  # 0-11 = pagi (di luar jam)
                warning_note = f"Warning: Check-in at {current_hour}:00 outside gantung pagi hours (12:00-00:00)"
            return shift, official, warning_note, False
        
        # GANTUNG MALAM (00:00 - 12:00)
        elif user_shift == 'gantung_malam':
            shift = 'gantung_malam'
            
            if current_hour < 12:
                # Masih dalam rentang yang sama (00:00-12:00)
                official = local_time.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                # Sudah lewat jam 12, berarti official start hari ini jam 00:00 sudah lewat
                # Tapi kita tetap catat warning
                official = local_time.replace(hour=0, minute=0, second=0, microsecond=0)
                warning_note = f"Warning: Check-in at {current_hour}:00 outside gantung malam hours (00:00-12:00)"
            
            return shift, official, warning_note, False
        
        # AUTO SHIFT - BEBAS TOTAL
        else:
            shift = 'auto'
            official = local_time
            return shift, official, None, True
        
    except Exception as e:
        app.logger.error(f"Error in determine_user_shift: {str(e)}")
        return 'auto', now, None, True
        
def get_user_debt(user_id):
    """Return owed minutes for user, default 0."""
    try:
        row = query_db('SELECT owed_minutes FROM user_debt WHERE user_id = ?', [user_id], one=True)
        return row['owed_minutes'] if row else 0
    except Exception as e:
        app.logger.error(f"Error in get_user_debt: {str(e)}")
        return 0

def update_user_debt(user_id, delta_minutes):
    """Add delta_minutes to user's debt (can be negative). Debt never goes below 0."""
    try:
        current = get_user_debt(user_id)
        new_debt = max(0, current + delta_minutes)
        now_str = now_local().strftime('%Y-%m-%d %H:%M:%S')
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            execute_db('''
                INSERT INTO user_debt (user_id, owed_minutes, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET owed_minutes = EXCLUDED.owed_minutes, updated_at = EXCLUDED.updated_at
            ''', [user_id, new_debt, now_str])
        else:
            execute_db('REPLACE INTO user_debt (user_id, owed_minutes, updated_at) VALUES (?, ?, ?)',
                       [user_id, new_debt, now_str])
        return new_debt
    except Exception as e:
        app.logger.error(f"Error in update_user_debt: {str(e)}")
        return get_user_debt(user_id)

def get_monthly_report(tahun, bulan, user_id=None, role=None):
    """Ambil data attendance untuk bulan tertentu."""
    try:
        start_date = f"{tahun:04d}-{bulan:02d}-01"
        if bulan == 12:
            end_date = f"{tahun+1:04d}-01-01"
        else:
            end_date = f"{tahun:04d}-{bulan+1:02d}-01"
        
        query = '''
            SELECT u.username, a.action, a.timestamp, a.shift, a.late_minutes, a.penalty_level, a.note, a.expected_checkout
            FROM attendance a
            JOIN users u ON a.user_id = u.id
            WHERE a.timestamp >= ? AND a.timestamp < ?
        '''
        params = [start_date, end_date]
        
        if role != 'admin' and user_id is not None:
            query += " AND a.user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY a.timestamp"
        
        return query_db(query, params)
    except Exception as e:
        app.logger.error(f"Error in get_monthly_report: {str(e)}")
        return []

# ---------- Decorators ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Routes ----------
@app.route('/')
def index():
    try:
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    except Exception as e:
        app.logger.error(f"Error in index route: {str(e)}")
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('login.html')
        
        user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Catat IP address
            log_user_ip(user['id'], 'login')
            
            # Auto-add admin IP to whitelist
            if user['role'] == 'admin':
                ip = get_client_ip()
                try:
                    execute_db(
                        "INSERT OR IGNORE INTO ip_whitelist (ip_address, description, is_active) VALUES (?, ?, ?)",
                        [ip, 'Auto-added admin IP', 1]
                    )
                    app.logger.info(f"Admin IP {ip} auto-added to whitelist")
                except:
                    pass
            
            flash('Login successful.', 'success')
            app.logger.info(f"User {username} logged in successfully")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            app.logger.warning(f"Failed login attempt for username: {username}")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    try:
        username = session.get('username', 'Unknown')
        session.clear()
        flash('You have been logged out.', 'info')
        app.logger.info(f"User {username} logged out")
    except Exception as e:
        app.logger.error(f"Error in logout route: {str(e)}")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        user_id = session['user_id']
        role = session['role']
        now = now_local()
        today = now.strftime('%Y-%m-%d')
        
        check_ins = query_db('''SELECT action, timestamp, note FROM attendance
                                WHERE user_id = ? AND DATE(timestamp) = ?
                                ORDER BY timestamp''', [user_id, today])
        
        breaks_today = query_db('''SELECT break_type, start_time, end_time, duration, note FROM breaks
                                   WHERE user_id = ? AND DATE(start_time) = ?
                                   ORDER BY start_time''', [user_id, today])
        
        rules = query_db('SELECT rule_name, value FROM rules')
        
        max_smoking = 10
        for r in rules:
            if r['rule_name'] == 'max_smoking_minutes':
                try:
                    max_smoking = int(r['value'])
                except:
                    pass
                break
        
        active_smoking = get_active_break(user_id, 'smoking')
        active_toilet = get_active_break(user_id, 'toilet')
        user_debt = get_user_debt(user_id)
        
        return render_template('dashboard.html',
                               records=check_ins,
                               breaks=breaks_today,
                               rules=rules,
                               role=role,
                               active_smoking=active_smoking,
                               active_toilet=active_toilet,
                               user_debt=user_debt,
                               max_smoking=max_smoking)
    except Exception as e:
        app.logger.error(f"Error in dashboard route: {str(e)}")
        flash('An error occurred loading dashboard.', 'danger')
        return redirect(url_for('logout'))

@app.route('/action/<path:action>')
@login_required
def record_action(action):
    try:
        allowed_actions = [
            'Check In', 'Check Out', 'Sick Check Out',
            'Smoking Start', 'Smoking Stop',
            'Toilet Start', 'Toilet Stop'
        ]
        if action not in allowed_actions:
            flash('Invalid action.', 'danger')
            return redirect(url_for('dashboard'))

        user_id = session['user_id']
        now = now_local()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        today = now.strftime('%Y-%m-%d')

        # ----- Check In -----
        if action == 'Check In':
            existing = query_db('''SELECT id FROM attendance 
                                   WHERE user_id = ? AND DATE(timestamp) = ? AND action = 'Check In' ''',
                                [user_id, today], one=True)
            if existing:
                flash('Already checked in today.', 'warning')
                return redirect(url_for('dashboard'))

            # Tentukan shift berdasarkan user preference
            shift, official_start, warning_note, is_auto = determine_user_shift(user_id, now)
            
            if is_auto:
                # AUTO MODE - BEBAS TOTAL
                level = 0
                penalty_note = 'Auto shift - no rules'
                extra_hours = 0
                late_minutes = 0
                combined_note = 'Free mode (auto shift)'
                
                # Expected checkout = check-in + 12 jam
                work_hours = 12
                expected_checkout = now + timedelta(hours=work_hours)
                expected_str = expected_checkout.strftime('%Y-%m-%d %H:%M:%S')
                
            else:
                # MODE BIASA (morning/night) - dengan aturan
                # Catat warning note jika ada
                final_note = warning_note if warning_note else None

                # Hitung keterlambatan (menit)
                late_minutes = max(0, (now - official_start).total_seconds() / 60.0)
                
                # Tentukan penalti berdasarkan keterlambatan
                if late_minutes <= 1:
                    level, penalty_note = 0, 'On time'
                    extra_hours = 0
                elif late_minutes <= 10:
                    level, penalty_note = 1, 'Extend 1 Jam'
                    extra_hours = 1
                elif late_minutes <= 30:
                    level, penalty_note = 2, 'Extend 2 Jam'
                    extra_hours = 2
                elif late_minutes <= 59:
                    level, penalty_note = 3, 'Extend 2 Jam 3 Hari'
                    extra_hours = 2
                else:  # >= 60 menit
                    # Cek riwayat keterlambatan level 4 bulan ini
                    count_l4 = count_monthly_late_level4(user_id, now)
                    if count_l4 == 0:
                        level, penalty_note = 4, 'Extend 2 Jam 3 Hari dan hangus OFFDAY 1x dalam 1 bulan.'
                    elif count_l4 == 1:
                        level, penalty_note = 4, 'Hangus Bonus Semester.'
                    else:
                        level, penalty_note = 4, 'Selamat anda Dipecat, Silakan membayar denda 50Juta untuk mengambil data anda dikantor.'
                    extra_hours = 2

                # Gabungkan note
                if final_note:
                    combined_note = f"{penalty_note} | {final_note}"
                else:
                    combined_note = penalty_note

                # Expected checkout = check-in time + 12 jam + extra hours
                work_hours = 12 + extra_hours
                expected_checkout = now + timedelta(hours=work_hours)
                expected_str = expected_checkout.strftime('%Y-%m-%d %H:%M:%S')

            # Simpan ke database (sama untuk auto maupun biasa)
            execute_db('''INSERT INTO attendance 
                          (user_id, action, timestamp, note, shift, late_minutes, penalty_level, expected_checkout)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                       [user_id, action, now_str, combined_note, shift, late_minutes, level, expected_str])

            app.logger.info(f"User {user_id} checked in at {now_str}")
            flash(f'Check In recorded at {now_str}. {combined_note}', 'success')
            return redirect(url_for('dashboard'))

        # ----- Check Out or Sick Check Out -----
        elif action in ('Check Out', 'Sick Check Out'):
            checkin = query_db('''SELECT * FROM attendance 
                                WHERE user_id = ? AND DATE(timestamp) = ? AND action = 'Check In'
                                ORDER BY timestamp DESC LIMIT 1''',
                            [user_id, today], one=True)
            if not checkin:
                flash('No check-in found for today.', 'warning')
                return redirect(url_for('dashboard'))

            checkout_exists = query_db('''SELECT id FROM attendance 
                                        WHERE user_id = ? AND DATE(timestamp) = ? AND action IN ('Check Out', 'Sick Check Out')''',
                                    [user_id, today], one=True)
            if checkout_exists:
                flash('Already checked out today.', 'warning')
                return redirect(url_for('dashboard'))

            # Parse check-in time
            checkin_time = datetime.strptime(checkin['timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=TIMEZONE)
            
            # Hitung expected check-out (check-in + 12 jam)
            expected = checkin_time + timedelta(hours=12)
            expected_str = expected.strftime('%Y-%m-%d %H:%M:%S')
            
            # Hitung jam kerja yang sudah dilakukan
            work_duration = (now - checkin_time).total_seconds() / 3600  # dalam jam
            
            if action == 'Check Out':
                # Normal checkout - harus sudah 12 jam
                if work_duration < 12:
                    remaining = 12 - work_duration
                    flash(f'Anda harus bekerja minimal 12 jam. Sisa {remaining:.1f} jam lagi.', 'danger')
                    return redirect(url_for('dashboard'))
                
                # Jika checkout setelah expected (lembur), kurangi utang
                if now > expected:
                    surplus_minutes = (now - expected).total_seconds() / 60.0
                    if surplus_minutes > 0:
                        update_user_debt(user_id, -int(surplus_minutes))
                
                execute_db('INSERT INTO attendance (user_id, action, timestamp) VALUES (?, ?, ?)',
                        [user_id, action, now_str])
                flash(f'{action} recorded at {now_str}', 'success')
            
            else:  # Sick Check Out
                # Hitung defisit (berapa jam yang belum dipenuhi)
                # Rumus: 12 jam - jam kerja yang sudah dilakukan
                deficit_hours = max(0, 12 - work_duration)
                
                note = None
                if deficit_hours > 0:
                    deficit_minutes = int(deficit_hours * 60)
                    new_debt = update_user_debt(user_id, deficit_minutes)
                    hours = new_debt // 60
                    minutes = new_debt % 60
                    note = f'Sisa anda extend tinggal {hours} jam {minutes} menit.'
                    flash(f'Sick check-out: {deficit_hours:.1f} jam akan ditagih di hari berikutnya.', 'warning')
                
                execute_db('INSERT INTO attendance (user_id, action, timestamp, note) VALUES (?, ?, ?, ?)',
                        [user_id, action, now_str, note])
                app.logger.info(f"User {user_id} sick checked out at {now_str}. Worked: {work_duration:.1f} hours, Deficit: {deficit_hours:.1f} hours")
                flash(f'{action} recorded at {now_str}', 'success')
            
            return redirect(url_for('dashboard'))

        # ----- Break Actions -----
        else:
            break_type = action.split()[0].lower()
            subaction = action.split()[1]

            if subaction == 'Start':
                active = get_active_break(user_id, break_type)
                if active:
                    flash(f'You already have an active {break_type} break.', 'warning')
                    return redirect(url_for('dashboard'))

                if break_type == 'smoking':
                    # Enforce maximum smoking breaks per day
                    rule = query_db('SELECT value FROM rules WHERE rule_name = ?', ['max_breaks_per_day'], one=True)
                    max_smoking = int(rule['value']) if rule else 3
                    if count_breaks_today(user_id, break_type='smoking') >= max_smoking:
                        flash(f'Maximum smoking breaks per day ({max_smoking}) reached.', 'danger')
                        return redirect(url_for('dashboard'))

                    phone_used = 1 if request.args.get('phone') == '1' else 0
                    note = None
                    if phone_used:
                        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
                        count_phone = query_db('''SELECT COUNT(*) as cnt FROM breaks 
                                                  WHERE user_id = ? AND break_type = 'smoking' 
                                                    AND phone_used = 1 AND start_time >= ?''',
                                               [user_id, first_day_str], one=True)
                        # ✅ FIX 5: Use helper function to get count
                        phone_count = get_count_from_result(count_phone)
                        if phone_count == 1:
                            note = 'Tidak ada WIFI Kantor, beli kuota internet dengan uang makan saja.'
                else:
                    # Toilet – no limit, no phone tracking
                    phone_used = 0
                    note = None

                execute_db('''INSERT INTO breaks 
                              (user_id, break_type, start_time, phone_used, note)
                              VALUES (?, ?, ?, ?, ?)''',
                           [user_id, break_type, now_str, phone_used, note])
                app.logger.info(f"User {user_id} started {break_type} break")
                flash(f'{action} recorded.', 'success')
                return redirect(url_for('dashboard'))

            elif subaction == 'Stop':
                active = get_active_break(user_id, break_type)
                if not active:
                    flash(f'No active {break_type} break to stop.', 'warning')
                    return redirect(url_for('dashboard'))

                start = active['start_time']
                duration = (now - start).total_seconds() / 60.0
                duration_int = int(duration)

                note = active['note']
                if break_type == 'smoking':
                    rule = query_db('SELECT value FROM rules WHERE rule_name = ?', ['max_smoking_minutes'], one=True)
                    max_smoking = int(rule['value']) if rule else 10
                    if duration > max_smoking:
                        violation = f'Exceeded {max_smoking} minutes'
                        note = (note + '; ' + violation) if note else violation

                execute_db('''UPDATE breaks SET end_time = ?, duration = ?, note = ? 
                              WHERE id = ?''',
                           [now_str, duration_int, note, active['id']])

                app.logger.info(f"User {user_id} stopped {break_type} break after {duration_int} minutes")
                flash(f'{action} recorded. Duration: {duration_int} minutes.', 'success')
                return redirect(url_for('dashboard'))
    except Exception as e:
        app.logger.error(f"Error in record_action route: {str(e)}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('dashboard'))

# ---------- Admin routes ----------
@app.route('/off-day', methods=['GET', 'POST'])
@login_required
@admin_required
def off_day():
    try:
        if request.method == 'POST':
            date = sanitize_input(request.form.get('date', ''))
            description = sanitize_input(request.form.get('description', ''))
            
            # ✅ FIX 3: Input validation
            valid, msg = validate_date(date)
            if not valid:
                flash(msg, 'danger')
                return redirect(url_for('off_day'))
            
            try:
                execute_db('INSERT INTO off_days (date, description) VALUES (?, ?)',
                           [date, description])
                flash('Off day added.', 'success')
                app.logger.info(f"Off day added: {date}")
            except Exception:
                flash('Date already exists as off day.', 'warning')
            return redirect(url_for('off_day'))
        
        off_days = query_db('SELECT * FROM off_days ORDER BY date DESC')
        return render_template('off_day.html', off_days=off_days)
    except Exception as e:
        app.logger.error(f"Error in off_day route: {str(e)}")
        flash('An error occurred.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/delete-off-day/<int:off_id>')
@login_required
@admin_required
def delete_off_day(off_id):
    try:
        execute_db('DELETE FROM off_days WHERE id = ?', [off_id])
        flash('Off day removed.', 'success')
        app.logger.info(f"Off day deleted: {off_id}")
    except Exception as e:
        app.logger.error(f"Error deleting off day: {str(e)}")
        flash('An error occurred.', 'danger')
    return redirect(url_for('off_day'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    try:
        if request.method == 'POST':
            username = sanitize_input(request.form.get('username', ''))
            password = request.form.get('password', '')
            role = request.form.get('role', '')
            
            # ✅ FIX 3: Input validation
            valid_username, msg = validate_username(username)
            if not valid_username:
                flash(msg, 'danger')
                return redirect(url_for('users'))
            
            valid_password, msg = validate_password(password)
            if not valid_password:
                flash(msg, 'danger')
                return redirect(url_for('users'))
            
            if role not in ['admin', 'cs', 'joker']:
                flash('Invalid role selected.', 'danger')
                return redirect(url_for('users'))
            
            hashed_password = generate_password_hash(password)
            try:
                execute_db('INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)',
                           [username, hashed_password, role, 'auto'])
                flash(f'User {username} added successfully.', 'success')
                app.logger.info(f"User {username} added by admin")
            except Exception:
                flash(f'Username {username} already exists.', 'danger')
            return redirect(url_for('users'))
        
        user_list = query_db('SELECT id, username, role, default_shift FROM users ORDER BY id')
        return render_template('users.html', users=user_list)
    except Exception as e:
        app.logger.error(f"Error in users route: {str(e)}")
        flash('An error occurred.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/delete-user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    try:
        if user_id == session['user_id']:
            flash('Cannot delete your own account.', 'danger')
            return redirect(url_for('users'))
        
        execute_db('DELETE FROM users WHERE id = ?', [user_id])
        flash('User deleted successfully.', 'success')
        app.logger.info(f"User {user_id} deleted by admin")
    except Exception as e:
        app.logger.error(f"Error deleting user: {str(e)}")
        flash('An error occurred.', 'danger')
    return redirect(url_for('users'))

@app.route('/user-shifts')
@login_required
@admin_required
def user_shifts():
    try:
        users = query_db('SELECT id, username, role, default_shift FROM users ORDER BY id')
        return render_template('user_shifts.html', users=users)
    except Exception as e:
        app.logger.error(f"Error in user_shifts route: {str(e)}")
        flash('An error occurred.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/set-user-shift/<int:user_id>/<shift>')
@login_required
@admin_required
def set_user_shift(user_id, shift):
    if shift not in ['morning', 'night', 'gantung_pagi', 'gantung_malam', 'auto']:
        flash('Invalid shift value.', 'danger')
        return redirect(url_for('user_shifts'))
    
    execute_db('UPDATE users SET default_shift = ? WHERE id = ?', [shift, user_id])
    flash(f'User shift updated to {shift}.', 'success')
    return redirect(url_for('user_shifts'))

@app.route('/rules', methods=['GET', 'POST'])
@login_required
@admin_required
def rules():
    try:
        if request.method == 'POST':
            for key, value in request.form.items():
                if key.startswith('rule_'):
                    rule_name = key[5:]
                    # ✅ FIX 3: Sanitize rule value
                    sanitized_value = sanitize_input(value)
                    execute_db('UPDATE rules SET value = ? WHERE rule_name = ?', [sanitized_value, rule_name])
            flash('Rules updated.', 'success')
            app.logger.info("Rules updated by admin")
            return redirect(url_for('rules'))
        
        rules_list = query_db('SELECT rule_name, value FROM rules')
        return render_template('rules.html', rules=rules_list)
    except Exception as e:
        app.logger.error(f"Error in rules route: {str(e)}")
        flash('An error occurred.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/records')
@login_required
def records():
    """Tampilkan semua records termasuk breaks."""
    try:
        user_id = session['user_id']
        role = session['role']
        
        if role == 'admin':
            # Admin melihat semua data (attendance + breaks)
            
            # Ambil attendance records
            attendance = query_db('''
                SELECT 
                    a.id,
                    u.username,
                    a.action,
                    a.timestamp,
                    a.note,
                    a.shift,
                    a.late_minutes,
                    a.penalty_level,
                    a.expected_checkout,
                    'attendance' as record_type
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                ORDER BY a.timestamp DESC
                LIMIT 1000
            ''')
            
            # Ambil break records
            breaks = query_db('''
                SELECT 
                    b.id,
                    u.username,
                    b.break_type || ' ' || CASE WHEN b.end_time IS NULL THEN 'Start' ELSE 'Stop' END as action,
                    b.start_time as timestamp,
                    b.note,
                    NULL as shift,
                    b.duration as late_minutes,
                    NULL as penalty_level,
                    NULL as expected_checkout,
                    'break' as record_type
                FROM breaks b
                JOIN users u ON b.user_id = u.id
                ORDER BY b.start_time DESC
                LIMIT 1000
            ''')
            
            # Gabungkan attendance dan breaks
            from itertools import chain
            records = list(chain(attendance, breaks))
            
            # Urutkan berdasarkan timestamp (terbaru dulu)
            records.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Batasi 500 records terbaru
            records = records[:500]
            
        else:
            # User biasa melihat data sendiri (attendance + breaks)
            
            # Ambil attendance records user
            attendance = query_db('''
                SELECT 
                    a.id,
                    u.username,
                    a.action,
                    a.timestamp,
                    a.note,
                    a.shift,
                    a.late_minutes,
                    a.penalty_level,
                    a.expected_checkout,
                    'attendance' as record_type
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                WHERE a.user_id = ?
                ORDER BY a.timestamp DESC
                LIMIT 500
            ''', [user_id])
            
            # Ambil break records user
            breaks = query_db('''
                SELECT 
                    b.id,
                    u.username,
                    b.break_type || ' ' || CASE WHEN b.end_time IS NULL THEN 'Start' ELSE 'Stop' END as action,
                    b.start_time as timestamp,
                    b.note,
                    NULL as shift,
                    b.duration as late_minutes,
                    NULL as penalty_level,
                    NULL as expected_checkout,
                    'break' as record_type
                FROM breaks b
                JOIN users u ON b.user_id = u.id
                WHERE b.user_id = ?
                ORDER BY b.start_time DESC
                LIMIT 500
            ''', [user_id])
            
            # Gabungkan attendance dan breaks
            from itertools import chain
            records = list(chain(attendance, breaks))
            
            # Urutkan berdasarkan timestamp (terbaru dulu)
            records.sort(key=lambda x: x['timestamp'], reverse=True)
        
        now = datetime.now()
        return render_template('records.html', records=records, now=now)
        
    except Exception as e:
        app.logger.error(f"Error in records route: {str(e)}")
        flash('Error loading records', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/my-ips')
@login_required
def my_ips():
    """Lihat riwayat IP sendiri."""
    try:
        user_id = session['user_id']
        
        # Ambil riwayat IP
        ips = query_db('''
            SELECT * FROM ip_logs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 100
        ''', [user_id])
        
        # Jika tidak ada data, buat list kosong
        if not ips:
            ips = []
        
        # Ambil IP unik
        unique_ips = query_db('''
            SELECT ip_address, COUNT(*) as count, MAX(created_at) as last_seen
            FROM ip_logs 
            WHERE user_id = ? 
            GROUP BY ip_address
            ORDER BY last_seen DESC
        ''', [user_id])
        
        if not unique_ips:
            unique_ips = []
        
        return render_template('my_ips.html', ips=ips, unique_ips=unique_ips)
        
    except Exception as e:
        app.logger.error(f"Error in my_ips: {str(e)}")
        flash('Error loading IP history', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/export/excel/<int:tahun>/<int:bulan>')
@login_required
def export_excel(tahun, bulan):
    try:
        user_id = session['user_id']
        role = session['role']
        data = get_monthly_report(tahun, bulan, user_id, role)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Laporan {bulan}-{tahun}"

        headers = ['Username', 'Action', 'Timestamp', 'Shift', 'Late (min)', 'Penalty Level', 'Note', 'Expected Checkout']
        ws.append(headers)

        for col in range(1, 9):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        for row in data:
            
            # Format late_minutes ke jam dan menit
            late_minutes = row['late_minutes']
            if late_minutes and late_minutes > 0:
                hours = int(late_minutes // 60)
                mins = int(late_minutes % 60)
                if hours > 0 and mins > 0:
                    late_str = f"{hours} jam {mins} menit"
                elif hours > 0:
                    late_str = f"{hours} jam"
                else:
                    late_str = f"{mins} menit"
            else:
                late_str = ""

            ws.append([
                row['username'],
                row['action'],
                row['timestamp'],
                row['shift'] or '',
                late_str,
                row['penalty_level'] or '',
                row['note'] or '',
                row['expected_checkout'] or ''
            ])

        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2) * 1.2
            ws.column_dimensions[col_letter].width = min(adjusted_width, 50)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"attendance_{tahun:04d}_{bulan:02d}.xlsx"
        app.logger.info(f"Excel export for {tahun}-{bulan} by user {user_id}")
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        app.logger.error(f"Error exporting Excel: {str(e)}")
        flash('Error generating Excel file.', 'danger')
        return redirect(url_for('records'))

@app.route('/export/pdf/<int:tahun>/<int:bulan>')
@login_required
def export_pdf(tahun, bulan):
    try:
        user_id = session['user_id']
        role = session['role']
        data = get_monthly_report(tahun, bulan, user_id, role)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=1*cm, leftMargin=1*cm, topMargin=1.5*cm, bottomMargin=1*cm)
        elements = []

        styles = getSampleStyleSheet()
        title = f"Laporan Attendance Bulan {bulan:02d}-{tahun:04d}"
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Spacer(1, 0.5*cm))

        table_data = [['Username', 'Action', 'Timestamp', 'Shift', 'Late', 'Penalty', 'Note', 'Expected']]
        for row in data:
            note = (row['note'][:30] + '...') if row['note'] and len(row['note']) > 30 else (row['note'] or '')
            
            # Format late_minutes ke jam dan menit
            late_minutes = row['late_minutes']
            if late_minutes and late_minutes > 0:
                hours = int(late_minutes // 60)
                mins = int(late_minutes % 60)
                if hours > 0 and mins > 0:
                    late_str = f"{hours} jam {mins} menit"
                elif hours > 0:
                    late_str = f"{hours} jam"
                else:
                    late_str = f"{mins} menit"
            else:
                late_str = ""

            table_data.append([
                row['username'],
                row['action'],
                row['timestamp'],
                row['shift'] or '',
                late_str,
                str(row['penalty_level'] or ''),
                note,
                row['expected_checkout'] or ''
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))

        elements.append(table)
        doc.build(elements)

        buffer.seek(0)
        filename = f"attendance_{tahun:04d}_{bulan:02d}.pdf"
        app.logger.info(f"PDF export for {tahun}-{bulan} by user {user_id}")
        return send_file(buffer, download_name=filename, as_attachment=True, mimetype='application/pdf')
    except Exception as e:
        app.logger.error(f"Error exporting PDF: {str(e)}")
        flash('Error generating PDF file.', 'danger')
        return redirect(url_for('records'))

@app.route('/admin/clear-logs', methods=['GET', 'POST'])
@login_required
@admin_required
def clear_logs():
    try:
        if request.method == 'POST':
            days = request.form.get('days', type=int)
            table = request.form.get('table')
            confirm = request.form.get('confirm')
            
            if confirm != 'DELETE':
                flash('Please type DELETE to confirm.', 'danger')
                return redirect(url_for('clear_logs'))
            
            if table == 'attendance':
                if days and days > 0:
                    cutoff = now_local() - timedelta(days=days)
                    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
                    execute_db('DELETE FROM attendance WHERE timestamp < ?', [cutoff_str])
                    flash(f'Deleted attendance records older than {days} days.', 'success')
                    app.logger.info(f"Admin deleted attendance records older than {days} days")
                else:
                    execute_db('DELETE FROM attendance')
                    flash('Deleted all attendance records.', 'success')
                    app.logger.warning("Admin deleted ALL attendance records")
            elif table == 'breaks':
                if days and days > 0:
                    cutoff = now_local() - timedelta(days=days)
                    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
                    execute_db('DELETE FROM breaks WHERE start_time < ?', [cutoff_str])
                    flash(f'Deleted break records older than {days} days.', 'success')
                else:
                    execute_db('DELETE FROM breaks')
                    flash('Deleted all break records.', 'success')
            elif table == 'user_debt':
                execute_db('UPDATE user_debt SET owed_minutes = 0, updated_at = ?', [now_local().strftime('%Y-%m-%d %H:%M:%S')])
                flash('All user debts have been reset to 0.', 'success')
                app.logger.info("Admin reset all user debts")
            else:
                flash('Invalid selection.', 'danger')
            
            return redirect(url_for('dashboard'))
        
        return render_template('clear_logs.html')
    except Exception as e:
        app.logger.error(f"Error in clear_logs route: {str(e)}")
        flash('An error occurred.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/admin/ip-logs')
@login_required
@admin_required
def admin_ip_logs():
    """Tampilkan semua log IP address."""
    try:
        # Ambil semua log IP
        logs = query_db('''
            SELECT 
                l.id,
                l.user_id,
                u.username,
                l.ip_address,
                l.user_agent,
                l.action,
                l.created_at
            FROM ip_logs l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT 500
        ''')
        
        if not logs:
            logs = []
        
        # Statistik per user
        stats = query_db('''
            SELECT 
                u.username,
                COUNT(l.id) as total_logins,
                COUNT(DISTINCT l.ip_address) as unique_ips,
                MAX(l.created_at) as last_login
            FROM users u
            LEFT JOIN ip_logs l ON u.id = l.user_id
            GROUP BY u.id, u.username
            ORDER BY last_login DESC
        ''')
        
        if not stats:
            stats = []
        
        return render_template('admin_ip_logs.html', logs=logs, stats=stats)
        
    except Exception as e:
        app.logger.error(f"Error in admin_ip_logs: {str(e)}")
        flash('Error loading IP logs', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/admin/all-ips')
@login_required
@admin_required
def all_ips():
    """Admin lihat semua IP."""
    # Statistik per user
    stats = query_db('''
        SELECT 
            u.id as user_id,
            u.username,
            COUNT(DISTINCT l.ip_address) as unique_ips,
            COUNT(l.id) as total_logins,
            MAX(l.created_at) as last_login,
            (
                SELECT ip_address FROM ip_logs l2 
                WHERE l2.user_id = u.id 
                ORDER BY created_at DESC LIMIT 1
            ) as last_ip
        FROM users u
        LEFT JOIN ip_logs l ON u.id = l.user_id
        GROUP BY u.id, u.username
        ORDER BY last_login DESC
    ''')
    
    # Semua log terbaru
    logs = query_db('''
        SELECT l.*, u.username 
        FROM ip_logs l
        JOIN users u ON l.user_id = u.id
        ORDER BY l.created_at DESC 
        LIMIT 1000
    ''')
    
    return render_template('all_ips.html', stats=stats, logs=logs)

@app.route('/admin/whitelist')
@admin_required_with_whitelist
def whitelist_list():
    """Lihat daftar IP whitelist."""
    ips = query_db('''
        SELECT w.*, u.username as creator_name
        FROM ip_whitelist w
        LEFT JOIN users u ON w.created_by = u.id
        ORDER BY w.created_at DESC
    ''')
    
    # Ambil settings
    settings = {}
    rows = query_db("SELECT setting_key, setting_value FROM app_settings")
    for row in rows:
        settings[row['setting_key']] = row['setting_value']
    
    return render_template('whitelist_list.html', ips=ips, settings=settings)

@app.route('/admin/whitelist/add', methods=['POST'])
@admin_required_with_whitelist
def whitelist_add():
    """Tambah IP ke whitelist."""
    ip = request.form.get('ip_address', '').strip()
    description = request.form.get('description', '').strip()
    
    if not ip:
        flash('IP address is required.', 'danger')
        return redirect(url_for('whitelist_list'))
    
    # Validasi format IP sederhana
    import re
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$|^[a-fA-F0-9:]+$'  # IPv4 atau IPv6 sederhana
    if not re.match(ip_pattern, ip):
        flash('Invalid IP address format.', 'danger')
        return redirect(url_for('whitelist_list'))
    
    try:
        execute_db('''
            INSERT INTO ip_whitelist (ip_address, description, created_by)
            VALUES (?, ?, ?)
        ''', [ip, description, session['user_id']])
        flash(f'IP {ip} added to whitelist.', 'success')
        app.logger.info(f"Admin added IP {ip} to whitelist")
    except Exception as e:
        flash(f'IP already exists or error: {str(e)}', 'danger')
    
    return redirect(url_for('whitelist_list'))

@app.route('/admin/whitelist/toggle/<int:ip_id>')
@admin_required_with_whitelist
def whitelist_toggle(ip_id):
    """Aktif/nonaktifkan IP."""
    ip = query_db('SELECT ip_address FROM ip_whitelist WHERE id = ?', [ip_id], one=True)
    execute_db('''
        UPDATE ip_whitelist 
        SET is_active = NOT is_active 
        WHERE id = ?
    ''', [ip_id])
    
    status = "activated" if execute_db else "deactivated"
    flash(f'IP {ip["ip_address"]} {status}.', 'success')
    return redirect(url_for('whitelist_list'))

@app.route('/admin/whitelist/delete/<int:ip_id>')
@admin_required_with_whitelist
def whitelist_delete(ip_id):
    """Hapus IP dari whitelist."""
    ip = query_db('SELECT ip_address FROM ip_whitelist WHERE id = ?', [ip_id], one=True)
    execute_db('DELETE FROM ip_whitelist WHERE id = ?', [ip_id])
    flash(f'IP {ip["ip_address"]} removed from whitelist.', 'success')
    app.logger.info(f"Admin removed IP {ip['ip_address']} from whitelist")
    return redirect(url_for('whitelist_list'))

@app.route('/admin/whitelist/settings', methods=['POST'])
@admin_required_with_whitelist
def whitelist_settings():
    """Update pengaturan whitelist."""
    enabled = 'true' if request.form.get('enabled') == 'on' else 'false'
    exclude_admins = 'true' if request.form.get('exclude_admins') == 'on' else 'false'
    
    execute_db("UPDATE app_settings SET setting_value = ? WHERE setting_key = 'ip_whitelist_enabled'", [enabled])
    execute_db("UPDATE app_settings SET setting_value = ? WHERE setting_key = 'whitelist_exclude_admins'", [exclude_admins])
    
    flash('Whitelist settings updated.', 'success')
    app.logger.info(f"Admin updated whitelist settings: enabled={enabled}, exclude_admins={exclude_admins}")
    return redirect(url_for('whitelist_list'))

@app.route('/admin/ip-logs/<int:user_id>')
@login_required
@admin_required
def user_ip_logs(user_id):
    """Tampilkan IP logs untuk user tertentu."""
    
    user = query_db('SELECT username FROM users WHERE id = ?', [user_id], one=True)
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('admin_ip_logs'))
    
    logs = query_db('''
        SELECT * FROM ip_logs 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', [user_id])
    
    # IP unik
    unique_ips = query_db('''
        SELECT DISTINCT ip_address, COUNT(*) as count, MAX(created_at) as last_seen
        FROM ip_logs 
        WHERE user_id = ?
        GROUP BY ip_address
        ORDER BY last_seen DESC
    ''', [user_id])
    
    return render_template('user_ip_logs.html', logs=logs, unique_ips=unique_ips, user=user)

@app.route('/emergency-reset')
def emergency_reset():
    """Route darurat untuk reset password admin."""
    try:
        from werkzeug.security import generate_password_hash
        new_password = 'admin123'
        hashed = generate_password_hash(new_password)
        
        # Hapus admin lama
        execute_db("DELETE FROM users WHERE username = 'admin'")
        
        # Buat admin baru
        execute_db(
            "INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)",
            ['admin', hashed, 'admin', 'auto']
        )
        
        return "✅ Password admin direset ke: admin123. Silakan login."
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False for production