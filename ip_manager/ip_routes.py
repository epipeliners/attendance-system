"""
Routes untuk mengelola IP address.
"""
from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from functools import wraps
import re

# Import dari ip_model yang sudah dimodifikasi
from ip_manager.ip_model import IPModel, query_db, execute_db

# Buat blueprint
ip_bp = Blueprint('ip', __name__, url_prefix='/ip')

# Decorators
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

# Routes untuk user biasa
@ip_bp.route('/my-ips')
@login_required
def my_ips():
    """Lihat riwayat IP sendiri."""
    user_id = session['user_id']
    ips = IPModel.get_user_ips(user_id, limit=100)
    unique_ips = IPModel.get_unique_ips_for_user(user_id)
    return render_template('my_ips.html', ips=ips, unique_ips=unique_ips)

# Routes untuk admin
@ip_bp.route('/admin/all-ips')
@admin_required
def all_ips():
    """Admin lihat semua IP dengan statistik."""
    ips = IPModel.get_all_ips(limit=5000)
    
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
        ORDER BY last_login DESC NULLS LAST
    ''')
    
    return render_template('all_ips.html', ips=ips, stats=stats)

@ip_bp.route('/admin/user-ips/<int:user_id>')
@admin_required
def user_ips(user_id):
    """Admin lihat IP specific user."""
    user = query_db('SELECT username FROM users WHERE id = ?', [user_id], one=True)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('ip.all_ips'))
    
    ips = IPModel.get_user_ips(user_id, limit=1000)
    unique_ips = IPModel.get_unique_ips_for_user(user_id)
    return render_template('user_ips.html', ips=ips, unique_ips=unique_ips, 
                          username=user['username'], user_id=user_id)

@ip_bp.route('/admin/clean-old-logs')
@admin_required
def clean_old_logs():
    """Hapus log IP lama."""
    days = request.args.get('days', 30, type=int)
    IPModel.delete_old_logs(days)
    flash(f'Deleted IP logs older than {days} days.', 'success')
    return redirect(url_for('ip.all_ips'))

@ip_bp.route('/admin/delete-user-logs/<int:user_id>')
@admin_required
def delete_user_logs(user_id):
    """Hapus semua log untuk user tertentu."""
    execute_db('DELETE FROM ip_logs WHERE user_id = ?', [user_id])
    flash(f'All IP logs for user deleted.', 'success')
    return redirect(url_for('ip.user_ips', user_id=user_id))