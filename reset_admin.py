import sqlite3
from werkzeug.security import generate_password_hash
import secrets

# Koneksi ke database
conn = sqlite3.connect('attendance.db')
cursor = conn.cursor()

# Generate password baru
new_password = secrets.token_urlsafe(8)
hashed = generate_password_hash(new_password)

# Update password admin
cursor.execute("UPDATE users SET password = ? WHERE username = 'admin'", [hashed])

# Jika user admin tidak ada, buat baru
if cursor.rowcount == 0:
    cursor.execute(
        "INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)",
        ['admin', hashed, 'admin', 'auto']
    )
    print("✅ User admin baru dibuat")

conn.commit()
conn.close()

print(f"✅ Password admin baru: {new_password}")
print("⚠️  Catat password ini!")