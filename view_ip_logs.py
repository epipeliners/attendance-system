import sqlite3

conn = sqlite3.connect('attendance.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("="*80)
print("IP LOGS DATABASE")
print("="*80)

# Lihat users
cursor.execute("SELECT id, username, role FROM users")
users = cursor.fetchall()
print("\n📋 USERS:")
for user in users:
    print(f"  {user['id']}: {user['username']} ({user['role']})")

# Lihat IP logs
cursor.execute("""
    SELECT l.*, u.username 
    FROM ip_logs l 
    JOIN users u ON l.user_id = u.id 
    ORDER BY l.created_at DESC 
    LIMIT 20
""")
logs = cursor.fetchall()

print("\n📊 RECENT IP LOGS:")
print(f"{'ID':<5} {'Username':<15} {'IP Address':<20} {'Action':<10} {'Created At'}")
print("-"*80)

for log in logs:
    print(f"{log['id']:<5} {log['username']:<15} {log['ip_address']:<20} {log['action']:<10} {log['created_at']}")

# Statistik
cursor.execute("""
    SELECT 
        u.username,
        COUNT(l.id) as total_logins,
        COUNT(DISTINCT l.ip_address) as unique_ips,
        MAX(l.created_at) as last_login
    FROM users u
    LEFT JOIN ip_logs l ON u.id = l.user_id
    GROUP BY u.id, u.username
    ORDER BY last_login DESC
""")
stats = cursor.fetchall()

print("\n📈 STATISTICS:")
for stat in stats:
    print(f"  {stat['username']}: {stat['total_logins']} logins, {stat['unique_ips']} unique IPs, last: {stat['last_login']}")

conn.close()