"""
Model untuk mengelola IP address user.
"""
from utils.database import query_db, execute_db
from utils.helpers import now_local, format_datetime

class IPModel:
    """Class untuk mengelola data IP address."""
    
    @staticmethod
    def create_table():
        """Buat tabel ip_logs jika belum ada."""
        from config import Config
        from utils.database import get_db
        
        conn = get_db()
        if Config.DATABASE_URL and Config.DATABASE_URL.startswith('postgres'):
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS ip_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    action TEXT DEFAULT 'login',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_user_id ON ip_logs(user_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_created_at ON ip_logs(created_at)')
            conn.commit()
            cur.close()
        else:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ip_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    action TEXT DEFAULT 'login',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_user_id ON ip_logs(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip_logs_created_at ON ip_logs(created_at)')
            conn.commit()
    
    @staticmethod
    def log(user_id, ip_address, user_agent=None, action='login'):
        """Catat IP address user."""
        now = format_datetime(now_local())
        return execute_db('''
            INSERT INTO ip_logs (user_id, ip_address, user_agent, action, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', [user_id, ip_address, user_agent, action, now])
    
    @staticmethod
    def get_user_ips(user_id, limit=50):
        """Dapatkan riwayat IP untuk user tertentu."""
        return query_db('''
            SELECT * FROM ip_logs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', [user_id, limit])
    
    @staticmethod
    def get_all_ips(limit=1000):
        """Dapatkan semua riwayat IP (untuk admin)."""
        return query_db('''
            SELECT l.*, u.username 
            FROM ip_logs l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC 
            LIMIT ?
        ''', [limit])
    
    @staticmethod
    def get_user_last_ip(user_id):
        """Dapatkan IP terakhir user."""
        return query_db('''
            SELECT * FROM ip_logs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        ''', [user_id], one=True)
    
    @staticmethod
    def get_unique_ips_for_user(user_id):
        """Dapatkan daftar IP unik yang pernah digunakan user."""
        return query_db('''
            SELECT DISTINCT ip_address, COUNT(*) as count, MAX(created_at) as last_seen
            FROM ip_logs 
            WHERE user_id = ? 
            GROUP BY ip_address
            ORDER BY last_seen DESC
        ''', [user_id])
    
    @staticmethod
    def get_stats_by_user():
        """Dapatkan statistik IP per user untuk admin."""
        return query_db('''
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
    
    @staticmethod
    def delete_old_logs(days=30):
        """Hapus log IP lebih dari X hari."""
        from datetime import timedelta
        cutoff = now_local() - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        return execute_db('DELETE FROM ip_logs WHERE created_at < ?', [cutoff_str])
    
    @staticmethod
    def delete_user_logs(user_id):
        """Hapus semua log untuk user tertentu."""
        return execute_db('DELETE FROM ip_logs WHERE user_id = ?', [user_id])