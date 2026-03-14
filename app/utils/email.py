"""
Email sending utilities for password reset and 2FA.
"""
from flask import current_app, render_template
from flask_mail import Mail, Message
import threading
import os

mail = Mail()

def init_mail(app):
    """Initialize mail with app config."""
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@attendance.com')
    
    mail.init_app(app)

def send_async_email(app, msg):
    """Send email asynchronously to avoid blocking."""
    with app.app_context():
        try:
            mail.send(msg)
            app.logger.info(f"Email sent to {msg.recipients}")
        except Exception as e:
            app.logger.error(f"Failed to send email: {str(e)}")

def send_reset_email(user_email, reset_link):
    """Send password reset email."""
    from flask import current_app
    
    msg = Message(
        subject="Password Reset Request - Attendance System",
        recipients=[user_email]
    )
    
    msg.body = f"""
    To reset your password, click the following link:
    
    {reset_link}
    
    This link will expire in 30 minutes.
    
    If you did not request this, please ignore this email.
    """
    
    msg.html = f"""
    <h2>Password Reset Request</h2>
    <p>Click the button below to reset your password:</p>
    <a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 14px 20px; text-align: center; text-decoration: none; display: inline-block; border-radius: 4px;">Reset Password</a>
    <p>Or copy this link: <a href="{reset_link}">{reset_link}</a></p>
    <p><small>This link will expire in 30 minutes.</small></p>
    <p>If you did not request this, please ignore this email.</p>
    """
    
    thr = threading.Thread(target=send_async_email, args=[current_app._get_current_object(), msg])
    thr.start()
    
def send_2fa_setup_email(user_email, qr_code_path):
    """Send email with 2FA setup instructions."""
    from flask import current_app
    
    msg = Message(
        subject="2FA Setup - Attendance System",
        recipients=[user_email]
    )
    
    msg.body = f"""
    You have enabled 2-Factor Authentication.
    
    Please scan the QR code with Google Authenticator app.
    If you cannot scan, use this secret key: [SECRET KEY HERE]
    
    Keep this key safe!
    """
    
    with current_app.open_resource(qr_code_path) as fp:
        msg.attach("qrcode.png", "image/png", fp.read())
    
    thr = threading.Thread(target=send_async_email, args=[current_app._get_current_object(), msg])
    thr.start()