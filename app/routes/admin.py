from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.utils.database import query_db, execute_db
from app.utils.helpers import now_local
from functools import wraps

# 🔴 1. BUAT BLUEPRINT DULU
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# 🔴 2. DEFINE DECORATOR
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# 🔴 3. BARU SETELAH ITU DEFINE ROUTES
@admin_bp.route('/users')
@admin_required
def users():
    users = query_db('SELECT id, username, role, default_shift FROM users ORDER BY id')
    return render_template('users.html', users=users)

@admin_bp.route('/delete-user/<int:user_id>')
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))
    
    execute_db('DELETE FROM users WHERE id = ?', [user_id])
    flash('User deleted successfully', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/user-shifts')
@admin_required
def user_shifts():
    users = query_db('SELECT id, username, role, default_shift FROM users ORDER BY id')
    return render_template('user_shifts.html', users=users)

@admin_bp.route('/set-user-shift/<int:user_id>/<shift>')
@admin_required
def set_user_shift(user_id, shift):
    valid_shifts = ['morning', 'night', 'gantung_pagi', 'gantung_malam', 'auto']
    if shift not in valid_shifts:
        flash('Invalid shift value', 'danger')
        return redirect(url_for('admin.user_shifts'))
    
    try:
        user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin.user_shifts'))
        
        execute_db('UPDATE users SET default_shift = ? WHERE id = ?', [shift, user_id])
        
        updated_user = query_db('SELECT default_shift FROM users WHERE id = ?', [user_id], one=True)
        if updated_user and updated_user['default_shift'] == shift:
            flash(f'User shift updated to {shift} successfully', 'success')
        else:
            flash('Update failed', 'danger')
            
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.user_shifts'))

@admin_bp.route('/off-day')
@admin_required
def off_day():
    off_days = query_db('SELECT * FROM off_days ORDER BY date DESC')
    return render_template('off_day.html', off_days=off_days)

@admin_bp.route('/rules')
@admin_required
def rules():
    rules = query_db('SELECT rule_name, value FROM rules')
    return render_template('rules.html', rules=rules)

@admin_bp.route('/records')
@admin_required
def records():
    records = query_db('''
        SELECT a.id, u.username, a.action, a.timestamp, a.note, a.shift, a.late_minutes, a.penalty_level
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.timestamp DESC
        LIMIT 500
    ''')
    now = now_local()
    return render_template('records.html', records=records, now=now)

@admin_bp.route('/clear-logs')
@admin_required
def clear_logs():
    return render_template('clear_logs.html')