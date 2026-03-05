import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash, generate_password_hash

import io
from datetime import datetime, timedelta
import openpyxl
from openpyxl.styles import Font, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from flask import send_file, make_response

# ---------- Timezone setup ----------
import pytz
TIMEZONE = pytz.timezone('Asia/Jakarta')  # Change to your local timezone

def now_local():
    return datetime.now(TIMEZONE)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-to-a-secure-random-key')

# ---------- Database connection helpers ----------
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
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
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    conn = get_db()
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        cur = conn.cursor()
        cur.execute(query.replace('?', '%s'), args)
        rv = cur.fetchall()
        cur.close()
    else:
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
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
    
def get_monthly_report(tahun, bulan, user_id=None, role=None):
    """Ambil data attendance untuk bulan tertentu. Jika admin, semua user; jika bukan, hanya user sendiri."""
    start_date = f"{tahun:04d}-{bulan:02d}-01"
    # Hitung akhir bulan
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

# ---------- Database initialization ----------
def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        cur = conn.cursor()
        # Users table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
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
        # ---------- NEW: User debt table ----------
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_debt (
                user_id INTEGER PRIMARY KEY,
                owed_minutes INTEGER DEFAULT 0,
                updated_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # Insert default rules if missing
        cur.execute("SELECT COUNT(*) FROM rules")
        if cur.fetchone()['count'] == 0:
            default_rules = [
                ('max_breaks_per_day', '3'),
                ('max_smoking_minutes', '10'),
                ('normal_work_hours', '8')
            ]
            for name, val in default_rules:
                cur.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (name, val))
        conn.commit()
        cur.close()
    else:
        # SQLite
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
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
        # ---------- NEW: User debt table ----------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_debt (
                user_id INTEGER PRIMARY KEY,
                owed_minutes INTEGER DEFAULT 0,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cur = conn.execute("SELECT COUNT(*) FROM rules")
        if cur.fetchone()[0] == 0:
            default_rules = [
                ('max_breaks_per_day', '3'),
                ('max_smoking_minutes', '10'),
                ('normal_work_hours', '8')
            ]
            for name, val in default_rules:
                conn.execute("INSERT INTO rules (rule_name, value) VALUES (?, ?)", (name, val))
        conn.commit()

with app.app_context():
    init_db()

# ---------- Login decorators ----------
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

# ---------- Helper functions for business logic ----------
def get_active_break(user_id, break_type):
    """Return the active break (end_time NULL) for this user and type, or None."""
    row = query_db('''SELECT * FROM breaks 
                       WHERE user_id = ? AND break_type = ? AND end_time IS NULL 
                       ORDER BY start_time DESC LIMIT 1''', 
                    [user_id, break_type], one=True)
    if row:
        # Convert to dict to allow modification
        row_dict = dict(row)
        start_naive = datetime.strptime(row_dict['start_time'], '%Y-%m-%d %H:%M:%S')
        row_dict['start_time'] = TIMEZONE.localize(start_naive)
        return row_dict
    return None

def count_breaks_today(user_id, break_type=None):
    """Return number of breaks started today. If break_type specified, count only that type."""
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
    return result['cnt'] if result else 0

def count_monthly_late_level4(user_id, current_date):
    """Count how many times this month the user has been late at level >=4 (excluding today)."""
    first_day = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
    today_str = current_date.strftime('%Y-%m-%d')
    result = query_db('''SELECT COUNT(*) as cnt FROM attendance 
                         WHERE user_id = ? AND action = 'Check In' 
                           AND penalty_level >= 4 
                           AND timestamp >= ? 
                           AND DATE(timestamp) < DATE(?)''',
                      [user_id, first_day_str, today_str], one=True)
    return result['cnt'] if result else 0

def determine_shift_and_official_start(now):
    """
    Determine shift based on current time (aware datetime).
    Morning shift: official 10:00 same day (if between 06:00 and 15:00)
    Night shift: official 22:00 of previous day (if after midnight) or same day (if before midnight)
    Returns (shift, official_start_datetime) or (None, None) if outside shift windows.
    """
    local_time = now.astimezone(TIMEZONE)
    if 6 <= local_time.hour < 15:
        shift = 'morning'
        official = local_time.replace(hour=10, minute=0, second=0, microsecond=0)
    elif local_time.hour >= 20 or local_time.hour < 6:
        shift = 'night'
        if local_time.hour < 6:
            previous_day = local_time - timedelta(days=1)
            official = previous_day.replace(hour=22, minute=0, second=0, microsecond=0)
        else:
            official = local_time.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        return None, None
    return shift, official

def calculate_penalty(late_minutes, user_id, now):
    """
    Return (penalty_level, note) based on late minutes and monthly history.
    Level 0: on time (<=1 min)
    Level 1: 2-10 min -> Extend 1 Jam
    Level 2: 11-30 min -> Extend 2 Jam
    Level 3: 31-59 min -> Extend 2 Jam 3 Hari
    Level 4: >=60 min, with cumulative monthly sanctions
    """
    if late_minutes <= 1:
        return 0, 'On time'
    elif late_minutes <= 10:
        return 1, 'Extend 1 Jam'
    elif late_minutes <= 30:
        return 2, 'Extend 2 Jam'
    elif late_minutes <= 59:
        return 3, 'Extend 2 Jam 3 Hari'
    else:
        count_l4 = count_monthly_late_level4(user_id, now)
        if count_l4 == 0:
            return 4, 'Extend 2 Jam 3 Hari dan hangus OFFDAY 1x dalam 1 bulan.'
        elif count_l4 == 1:
            return 4, 'Hangus Bonus Semester.'
        else:
            return 4, 'Selamat anda Dipecat, Silakan membayar denda 50Juta untuk mengambil data anda dikantor.'
        
def get_monthly_report(tahun, bulan, user_id=None, role=None):
    """Ambil data attendance untuk bulan tertentu. Jika admin, semua user; jika bukan, hanya user sendiri."""
    start_date = f"{tahun:04d}-{bulan:02d}-01"
    # Hitung akhir bulan
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

# ---------- NEW: Debt helpers ----------
def get_user_debt(user_id):
    """Return owed minutes for user, default 0."""
    row = query_db('SELECT owed_minutes FROM user_debt WHERE user_id = ?', [user_id], one=True)
    return row['owed_minutes'] if row else 0

def update_user_debt(user_id, delta_minutes):
    """Add delta_minutes to user's debt (can be negative). Debt never goes below 0."""
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
        # SQLite: REPLACE works because user_id is PRIMARY KEY
        execute_db('REPLACE INTO user_debt (user_id, owed_minutes, updated_at) VALUES (?, ?, ?)',
                   [user_id, new_debt, now_str])
    return new_debt

# ---------- Routes ----------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    role = session['role']
    now = now_local()
    today = now.strftime('%Y-%m-%d')
    # Get today's actions
    check_ins = query_db('''SELECT action, timestamp, note FROM attendance
                            WHERE user_id = ? AND DATE(timestamp) = ?
                            ORDER BY timestamp''', [user_id, today])
    breaks_today = query_db('''SELECT break_type, start_time, end_time, duration, note FROM breaks
                               WHERE user_id = ? AND DATE(start_time) = ?
                               ORDER BY start_time''', [user_id, today])
    rules = query_db('SELECT rule_name, value FROM rules')

    # Ambil max_smoking_minutes dari rules (default 10)
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
    # NEW: Get user debt
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

@app.route('/action/<path:action>')
@login_required
def record_action(action):
    # NEW: Added 'Sick Check Out'
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

        shift, official_start = determine_shift_and_official_start(now)
        if not shift:
            flash('Check‑in time is outside recognised shift hours (morning 06:00-15:00, night 20:00-05:59).', 'danger')
            return redirect(url_for('dashboard'))

        late_minutes = max(0, (now - official_start).total_seconds() / 60.0)
        level, note = calculate_penalty(late_minutes, user_id, now)

        rule = query_db('SELECT value FROM rules WHERE rule_name = ?', ['normal_work_hours'], one=True)
        normal_hours = int(rule['value']) if rule else 8
        extra_hours = 0
        if level == 1:
            extra_hours = 1
        elif level >= 2:
            extra_hours = 2
        expected_checkout = official_start + timedelta(hours=normal_hours + extra_hours)
        expected_str = expected_checkout.strftime('%Y-%m-%d %H:%M:%S')

        execute_db('''INSERT INTO attendance 
                      (user_id, action, timestamp, note, shift, late_minutes, penalty_level, expected_checkout)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                   [user_id, action, now_str, note, shift, late_minutes, level, expected_str])

        flash(f'Check In recorded at {now_str}. {note}', 'success')
        return redirect(url_for('dashboard'))

    # ----- Check Out or Sick Check Out -----
    elif action in ('Check Out', 'Sick Check Out'):
        checkin = query_db('''SELECT * FROM attendance 
                              WHERE user_id = ? AND DATE(timestamp) = ? AND action = 'Check In'
                              ORDER BY timestamp DESC LIMIT 1''',
                           [user_id, today], one=True)
        if not checkin:
            flash('No check‑in found for today.', 'warning')
            return redirect(url_for('dashboard'))

        # Check if already checked out (any kind)
        checkout_exists = query_db('''SELECT id FROM attendance 
                                      WHERE user_id = ? AND DATE(timestamp) = ? AND action IN ('Check Out', 'Sick Check Out')''',
                                   [user_id, today], one=True)
        if checkout_exists:
            flash('Already checked out today.', 'warning')
            return redirect(url_for('dashboard'))

        expected_naive = datetime.strptime(checkin['expected_checkout'], '%Y-%m-%d %H:%M:%S')
        expected = TIMEZONE.localize(expected_naive)

        if action == 'Check Out':
            # Normal checkout: must be after expected
            if now < expected:
                flash(f'You cannot check out before {expected.strftime("%H:%M")}. Please complete your extended hours.', 'danger')
                return redirect(url_for('dashboard'))
            # Compute surplus (positive if later)
            diff_minutes = (now - expected).total_seconds() / 60.0
            if diff_minutes > 0:
                update_user_debt(user_id, -int(diff_minutes))
            # Record without special note
            execute_db('INSERT INTO attendance (user_id, action, timestamp) VALUES (?, ?, ?)',
                       [user_id, action, now_str])
            flash(f'{action} recorded at {now_str}', 'success')
        else:  # Sick Check Out
            # Compute deficit (how much they left early)
            diff_minutes = (expected - now).total_seconds() / 60.0  # positive if early
            note = None
            if diff_minutes > 0:
                new_debt = update_user_debt(user_id, int(diff_minutes))
                hours = new_debt // 60
                minutes = new_debt % 60
                note = f'Sisa anda extend tinggal {hours} jam {minutes} menit.'
            # Record with note
            execute_db('INSERT INTO attendance (user_id, action, timestamp, note) VALUES (?, ?, ?, ?)',
                       [user_id, action, now_str, note])
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
                                           [user_id, first_day_str], one=True)['cnt']
                    if count_phone == 1:
                        note = 'Tidak ada WIFI Kantor, beli kuota internet dengan uang makan saja.'
            else:
                # Toilet – no limit, no phone tracking
                phone_used = 0
                note = None

            execute_db('''INSERT INTO breaks 
                          (user_id, break_type, start_time, phone_used, note)
                          VALUES (?, ?, ?, ?, ?)''',
                       [user_id, break_type, now_str, phone_used, note])
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

            flash(f'{action} recorded. Duration: {duration_int} minutes.', 'success')
            return redirect(url_for('dashboard'))

# ---------- Admin routes (unchanged) ----------
@app.route('/off-day', methods=['GET', 'POST'])
@login_required
@admin_required
def off_day():
    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        try:
            execute_db('INSERT INTO off_days (date, description) VALUES (?, ?)',
                       [date, description])
            flash('Off day added.', 'success')
        except Exception:
            flash('Date already exists as off day.', 'warning')
        return redirect(url_for('off_day'))
    off_days = query_db('SELECT * FROM off_days ORDER BY date DESC')
    return render_template('off_day.html', off_days=off_days)

@app.route('/delete-off-day/<int:off_id>')
@login_required
@admin_required
def delete_off_day(off_id):
    execute_db('DELETE FROM off_days WHERE id = ?', [off_id])
    flash('Off day removed.', 'success')
    return redirect(url_for('off_day'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        hashed_password = generate_password_hash(password)
        try:
            execute_db('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                       [username, hashed_password, role])
            flash(f'User {username} added successfully.', 'success')
        except Exception:
            flash(f'Username {username} already exists.', 'danger')
        return redirect(url_for('users'))
    user_list = query_db('SELECT id, username, role FROM users ORDER BY id')
    return render_template('users.html', users=user_list)

@app.route('/delete-user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('users'))
    execute_db('DELETE FROM users WHERE id = ?', [user_id])
    flash('User deleted successfully.', 'success')
    return redirect(url_for('users'))

@app.route('/rules', methods=['GET', 'POST'])
@login_required
@admin_required
def rules():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('rule_'):
                rule_name = key[5:]
                execute_db('UPDATE rules SET value = ? WHERE rule_name = ?', [value, rule_name])
        flash('Rules updated.', 'success')
        return redirect(url_for('rules'))
    rules_list = query_db('SELECT rule_name, value FROM rules')
    return render_template('rules.html', rules=rules_list)

@app.route('/records')
@login_required
def records():
    user_id = session['user_id']
    role = session['role']
    if role == 'admin':
        records = query_db('''SELECT a.id, u.username, a.action, a.timestamp, a.note, a.shift, a.late_minutes, a.penalty_level, a.expected_checkout
                              FROM attendance a JOIN users u ON a.user_id = u.id
                              ORDER BY a.timestamp DESC''')
    else:
        records = query_db('''SELECT a.id, u.username, a.action, a.timestamp, a.note, a.shift, a.late_minutes, a.penalty_level, a.expected_checkout
                              FROM attendance a JOIN users u ON a.user_id = u.id
                              WHERE a.user_id = ?
                              ORDER BY a.timestamp DESC''', [user_id])
    now = datetime.now()  # <--- tambahkan ini
    return render_template('records.html', records=records, now=now)  # <--- kirim ke template

@app.route('/export/excel/<int:tahun>/<int:bulan>')
@login_required
def export_excel(tahun, bulan):
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
        ws.append([
            row['username'],
            row['action'],
            row['timestamp'],
            row['shift'] or '',
            row['late_minutes'] or '',
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
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/export/pdf/<int:tahun>/<int:bulan>')
@login_required
def export_pdf(tahun, bulan):
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
        table_data.append([
            row['username'],
            row['action'],
            row['timestamp'],
            row['shift'] or '',
            str(row['late_minutes'] or ''),
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
    return send_file(buffer, download_name=filename, as_attachment=True, mimetype='application/pdf')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)