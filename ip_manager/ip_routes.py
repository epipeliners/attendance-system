"""
Routes untuk mengelola IP address.
"""
from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from ip_manager.ip_model import IPModel
from ip_manager.ip_utils import get_client_ip, get_user_agent, log_user_ip
from utils.database import query_db
from utils.helpers import now_local
from functools import wraps

# Buat blueprint
ip_bp = Blueprint('ip', __name__, url_prefix='/ip')

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
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
    stats = IPModel.get_stats_by_user()
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
    IPModel.delete_user_logs(user_id)
    flash(f'All IP logs for user deleted.', 'success')
    return redirect(url_for('ip.user_ips', user_id=user_id))