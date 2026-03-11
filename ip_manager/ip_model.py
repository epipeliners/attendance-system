"""
Model untuk mengelola IP address user.
"""
from flask import g
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os

# Ambil DATABASE_URL dari environment
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    """Get database connection - copy dari app.py"""
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        if not hasattr(g, '_database'):
            g._database = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return g._database
    else:
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect('attendance.db')
            db.row_factory = sqlite3.Row
        return db

def query_db(query, args=(), one=False):
    """Execute query - copy dari app.py"""
    conn = get_db()
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        cur = conn.cursor()
        cur.execute(query.replace('?', '%s'), args)
        rv = cur.fetchall()
        cur.close()
        return (rv[0] if rv else None) if one else rv
    else:
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        cur.close()
        return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Execute query that modifies database - copy dari app.py"""
    conn = get_db()
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        cur = conn.cursor()
        cur.execute(query.replace('?', '%s'), args)
        conn.commit()
        cur.close()
        return None
    else:
        cur = conn.execute(query, args)
        conn.commit()
        return cur.lastrowid

def now_local():
    """Return current datetime - simple version"""
    from pytz import timezone
    return datetime.now(timezone('Asia/Jakarta'))

def format_datetime(dt):
    """Format datetime to string"""
    if isinstance(dt, str):
        return dt
    return dt.strftime('%Y-%m-%d %H:%M:%S')

class IPModel:
    """Class untuk mengelola data IP address."""
    
    @staticmethod
    def create_table():
        """Buat tabel ip_logs jika belum ada."""
        conn = get_db()
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
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
    def delete_old_logs(days=30):
        """Hapus log IP lebih dari X hari."""
        from datetime import timedelta
        cutoff = now_local() - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        return execute_db('DELETE FROM ip_logs WHERE created_at < ?', [cutoff_str])