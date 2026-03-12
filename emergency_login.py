from app import app
from utils.database import query_db, execute_db
from werkzeug.security import generate_password_hash
import secrets

print("🚑 Emergency Login Helper")
print("========================")

with app.app_context():
    # Cek admin
    admin = query_db("SELECT * FROM users WHERE username = 'admin'", one=True)
    
    if admin:
        # Reset password
        new_pass = 'admin123'
        hashed = generate_password_hash(new_pass)
        execute_db("UPDATE users SET password = ? WHERE username = 'admin'", [hashed])
        print(f"✅ Password admin direset: {new_pass}")
    else:
        # Buat admin baru
        new_pass = 'admin123'
        hashed = generate_password_hash(new_pass)
        execute_db(
            "INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)",
            ['admin', hashed, 'admin', 'auto']
        )
        print(f"✅ Admin baru dibuat dengan password: {new_pass}")
    
    print("\n🔐 Silakan login dengan:")
    print("   Username: admin")
    print(f"   Password: {new_pass}")