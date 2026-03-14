from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.models.user import User
from app.models.attendance import Attendance
from app.utils.helpers import now_local

main_bp = Blueprint('main', __name__)

@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    now = now_local()
    today = now.strftime('%Y-%m-%d')
    
    return render_template('dashboard.html', user=user, today=today)