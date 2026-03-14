"""
2FA utilities using Google Authenticator.
"""
import pyotp
import qrcode
import io
import base64
import os

class TwoFA:
    @staticmethod
    def generate_secret():
        """Generate a new secret key for 2FA."""
        return pyotp.random_base32()
    
    @staticmethod
    def get_qr_code_uri(username, secret, issuer="Attendance System"):
        """Generate QR code URI for Google Authenticator."""
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name=issuer
        )
    
    @staticmethod
    def generate_qr_code_base64(uri):
        """Generate QR code image and return as base64 string."""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for embedding in HTML
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    
    @staticmethod
    def verify_code(secret, code):
        """Verify the 6-digit code from Google Authenticator."""
        totp = pyotp.TOTP(secret)
        return totp.verify(code)