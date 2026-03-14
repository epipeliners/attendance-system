from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.models.user import User
from app.utils.helpers import now_local
from app.utils.database import execute_db, query_db
from werkzeug.security import check_password_hash, generate_password_hash
from app.utils.email import send_reset_email, init_mail, mail
from app.utils.token import generate_reset_token, verify_reset_token, generate_2fa_token, verify_2fa_token
from app.utils.twofa import TwoFA
import os

auth_bp = Blueprint('auth', __name__)

# Initialize mail when blueprint is registered
@auth_bp.record_once
def on_load(state):
    init_mail(state.app)

@auth_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        
        if user and check_password_hash(user['password'], password):
            # Check if 2FA is enabled for this user
            if user.get('twofa_enabled'):
                # Store user ID temporarily and redirect to 2FA verification
                session['pre_2fa_user_id'] = user['id']
                return redirect(url_for('auth.verify_2fa'))
            
            # No 2FA, login directly
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """Verify 2FA code during login."""
    if 'pre_2fa_user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        code = request.form.get('code', '')
        user_id = session['pre_2fa_user_id']
        
        user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
        
        if user and user.get('twofa_secret'):
            if TwoFA.verify_code(user['twofa_secret'], code):
                # Code correct, complete login
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session.pop('pre_2fa_user_id', None)
                flash('2FA verification successful', 'success')
                return redirect(url_for('main.dashboard'))
            else:
                flash('Invalid verification code', 'danger')
        else:
            flash('2FA not properly configured', 'danger')
            session.pop('pre_2fa_user_id', None)
            return redirect(url_for('auth.login'))
    
    return render_template('verify_2fa.html')

@auth_bp.route('/setup-2fa')
def setup_2fa():
    """Start 2FA setup process."""
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
    
    # Generate new secret
    secret = TwoFA.generate_secret()
    
    # Store secret temporarily in session
    session['temp_2fa_secret'] = secret
    
    # Generate QR code
    uri = TwoFA.get_qr_code_uri(user['username'], secret)
    qr_code = TwoFA.generate_qr_code_base64(uri)
    
    return render_template('setup_2fa.html', secret=secret, qr_code=qr_code)

@auth_bp.route('/verify-2fa-setup', methods=['POST'])
def verify_2fa_setup():
    """Verify and enable 2FA."""
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('auth.login'))
    
    code = request.form.get('code', '')
    secret = request.form.get('secret', '')
    
    if not secret or not code:
        flash('Missing information', 'danger')
        return redirect(url_for('auth.setup_2fa'))
    
    # Verify the code
    if TwoFA.verify_code(secret, code):
        # Save to database
        user_id = session['user_id']
        execute_db(
            "UPDATE users SET twofa_secret = ?, twofa_enabled = ? WHERE id = ?",
            [secret, 1, user_id]
        )
        
        session.pop('temp_2fa_secret', None)
        flash('2FA successfully enabled!', 'success')
        return redirect(url_for('main.dashboard'))
    else:
        flash('Invalid verification code', 'danger')
        return redirect(url_for('auth.setup_2fa'))

@auth_bp.route('/disable-2fa', methods=['POST'])
def disable_2fa():
    """Disable 2FA for current user."""
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('auth.login'))
    
    # Require password confirmation
    password = request.form.get('password', '')
    user_id = session['user_id']
    
    user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
    
    if user and check_password_hash(user['password'], password):
        execute_db(
            "UPDATE users SET twofa_enabled = ? WHERE id = ?",
            [0, user_id]
        )
        flash('2FA disabled successfully', 'success')
    else:
        flash('Invalid password', 'danger')
    
    return redirect(url_for('main.dashboard'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset email."""
    if request.method == 'POST':
        email = request.form.get('email', '')
        
        # Find user by email
        user = query_db('SELECT * FROM users WHERE email = ?', [email], one=True)
        
        if user:
            # Generate reset token
            token = generate_reset_token(user['id'], user['email'])
            
            # Create reset link
            reset_link = url_for('auth.reset_password', token=token, _external=True)
            
            # Send email
            send_reset_email(user['email'], reset_link)
            
            flash('Password reset link sent to your email', 'success')
        else:
            # Don't reveal if email exists or not (security)
            flash('If email exists, reset link will be sent', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password using token."""
    # Verify token
    payload = verify_reset_token(token)
    
    if not payload:
        flash('Invalid or expired reset link', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if password != confirm:
            flash('Passwords do not match', 'danger')
            return render_template('reset_password.html', token=token)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return render_template('reset_password.html', token=token)
        
        # Update password
        hashed = generate_password_hash(password)
        execute_db(
            "UPDATE users SET password = ? WHERE id = ?",
            [hashed, payload['user_id']]
        )
        
        flash('Password reset successful. Please login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('reset_password.html', token=token)

@auth_bp.route('/profile')
def profile():
    """User profile page for managing 2FA and email."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
    
    return render_template('profile.html', user=user)

@auth_bp.route('/update-email', methods=['POST'])
def update_email():
    """Update user email address."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    email = request.form.get('email', '')
    user_id = session['user_id']
    
    if not email:
        flash('Email is required', 'danger')
        return redirect(url_for('auth.profile'))
    
    try:
        execute_db(
            "UPDATE users SET email = ?, email_verified = ? WHERE id = ?",
            [email, 0, user_id]
        )
        flash('Email updated successfully', 'success')
    except Exception as e:
        flash('Email already in use', 'danger')
    
    return redirect(url_for('auth.profile'))
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Register new user (hanya untuk admin atau public)."""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        email = request.form.get('email', '')
        
        # Validasi sederhana
        if not username or not password:
            flash('Username and password required', 'danger')
            return render_template('register.html')
        
        # Cek apakah user sudah ada
        existing = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        if existing:
            flash('Username already exists', 'danger')
            return render_template('register.html')
        
        # Buat user baru
        from werkzeug.security import generate_password_hash
        hashed = generate_password_hash(password)
        
        try:
            execute_db('''
                INSERT INTO users (username, password, email, role, default_shift)
                VALUES (?, ?, ?, ?, ?)
            ''', [username, hashed, email, 'cs', 'auto'])
            
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('auth.login'))