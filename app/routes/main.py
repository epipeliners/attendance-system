from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.models.user import User
from app.utils.helpers import now_local
from app.utils.database import query_db, execute_db

main_bp = Blueprint('main', __name__)

@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    now = now_local()
    today = now.strftime('%Y-%m-%d')
    
    # Ambil user debt dengan aman
    try:
        user_debt_row = query_db('SELECT owed_minutes FROM user_debt WHERE user_id = ?', [user_id], one=True)
        user_debt = user_debt_row['owed_minutes'] if user_debt_row else 0
    except:
        # Buat tabel user_debt jika belum ada
        execute_db('''
            CREATE TABLE IF NOT EXISTS user_debt (
                user_id INTEGER PRIMARY KEY,
                owed_minutes INTEGER DEFAULT 0,
                updated_at DATETIME
            )
        ''')
        user_debt = 0
    
    # Ambil aturan
    rules = query_db('SELECT rule_name, value FROM rules')
    
    # Ambil check-in hari ini
    check_ins = query_db('''
        SELECT action, timestamp, note FROM attendance
        WHERE user_id = ? AND DATE(timestamp) = ?
        ORDER BY timestamp
    ''', [user_id, today])
    
    # Ambil breaks hari ini
    breaks_today = query_db('''
        SELECT break_type, start_time, end_time, duration, note FROM breaks
        WHERE user_id = ? AND DATE(start_time) = ?
        ORDER BY start_time
    ''', [user_id, today])
    
    # Ambil active breaks
    active_smoking = query_db('''
        SELECT * FROM breaks 
        WHERE user_id = ? AND break_type = 'smoking' AND end_time IS NULL
        ORDER BY start_time DESC LIMIT 1
    ''', [user_id], one=True)
    
    active_toilet = query_db('''
        SELECT * FROM breaks 
        WHERE user_id = ? AND break_type = 'toilet' AND end_time IS NULL
        ORDER BY start_time DESC LIMIT 1
    ''', [user_id], one=True)
    
    # Hitung max smoking dari rules
    max_smoking = 10
    for r in rules:
        if r['rule_name'] == 'max_smoking_minutes':
            try:
                max_smoking = int(r['value'])
            except:
                pass
            break
    
    return render_template('dashboard.html',
                          user=user,
                          today=today,
                          user_debt=user_debt,
                          rules=rules,
                          records=check_ins,
                          breaks=breaks_today,
                          active_smoking=active_smoking,
                          active_toilet=active_toilet,
                          max_smoking=max_smoking)

# 🔥 ROUTE RECORD_ACTION - TAMBAHKAN INI
@main_bp.route('/action/<path:action>')
def record_action(action):
    """Record various actions (check in/out, breaks)."""
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('auth.login'))
    
    allowed_actions = [
        'Check In', 'Check Out', 'Sick Check Out',
        'Smoking Start', 'Smoking Stop',
        'Toilet Start', 'Toilet Stop'
    ]
    
    if action not in allowed_actions:
        flash('Invalid action', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user_id = session['user_id']
    
    # Sementara cuma flash untuk testing
    flash(f'{action} recorded (placeholder)', 'success')
    return redirect(url_for('main.dashboard'))