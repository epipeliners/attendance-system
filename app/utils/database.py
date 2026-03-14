"""
Database connection and query helpers.
"""
import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import g
from app.config import config

# Ambil konfigurasi aktif
active_config = config[os.environ.get('FLASK_CONFIG', 'default')]
DATABASE_URL = active_config.DATABASE_URL

def get_db():
    """
    Mendapatkan koneksi database berdasarkan environment.
    - Jika DATABASE_URL postgres -> pakai PostgreSQL
    - Jika tidak -> pakai SQLite lokal (attendance.db)
    """
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        # PostgreSQL connection
        if not hasattr(g, '_database'):
            g._database = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return g._database
    else:
        # SQLite connection (untuk development lokal)
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect('attendance.db')
            db.row_factory = sqlite3.Row
        return db

def close_db(e=None):
    """
    Menutup koneksi database setelah request selesai.
    Dipanggil otomatis oleh Flask.
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """
    Menjalankan query SELECT dan mengembalikan hasil.
    
    Args:
        query: SQL query string
        args: tuple/list of arguments untuk query
        one: jika True, hanya kembalikan satu baris
    
    Returns:
        List of rows, atau satu row jika one=True
    """
    from flask import current_app
    try:
        conn = get_db()
        
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            # PostgreSQL
            cur = conn.cursor()
            # Ganti placeholder ? dengan %s untuk PostgreSQL
            pg_query = query.replace('?', '%s')
            cur.execute(pg_query, args)
            rv = cur.fetchall()
            cur.close()
            return (rv[0] if rv else None) if one else rv
        else:
            # SQLite
            cur = conn.execute(query, args)
            rv = cur.fetchall()
            cur.close()
            return (rv[0] if rv else None) if one else rv
            
    except Exception as e:
        current_app.logger.error(f"Database query error: {str(e)}")
        raise

def execute_db(query, args=()):
    """
    Menjalankan query INSERT, UPDATE, DELETE.
    
    Args:
        query: SQL query string
        args: tuple/list of arguments untuk query
    
    Returns:
        lastrowid untuk INSERT, None untuk lainnya
    """
    from flask import current_app
    try:
        conn = get_db()
        
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            # PostgreSQL
            cur = conn.cursor()
            pg_query = query.replace('?', '%s')
            cur.execute(pg_query, args)
            conn.commit()
            cur.close()
            return None
        else:
            # SQLite
            cur = conn.execute(query, args)
            conn.commit()
            return cur.lastrowid
            
    except Exception as e:
        current_app.logger.error(f"Database execute error: {str(e)}")
        raise

def init_db():
    """
    Inisialisasi database: membuat semua tabel jika belum ada.
    Akan dipanggil saat aplikasi pertama kali jalan.
    """
    from flask import current_app
    try:
        conn = get_db()
        using_postgres = DATABASE_URL and DATABASE_URL.startswith('postgres')
        
        if using_postgres:
            cur = conn.cursor()
            
            # Buat tabel users
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    default_shift TEXT DEFAULT 'auto'
                )
            ''')
            
            # Buat tabel attendance
            cur.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    note TEXT,
                    shift TEXT,
                    late_minutes INTEGER,
                    penalty_level INTEGER,
                    expected_checkout TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Buat tabel breaks
            cur.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    break_type TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    phone_used BOOLEAN DEFAULT FALSE,
                    note TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Buat tabel rules
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rules (
                    id SERIAL PRIMARY KEY,
                    rule_name TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')
            
            # Buat tabel ip_logs
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
            
            # Insert default admin jika tabel users kosong
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()['count'] == 0:
                from werkzeug.security import generate_password_hash
                admin_password = 'admin123'
                hashed = generate_password_hash(admin_password)
                cur.execute(
                    "INSERT INTO users (username, password, role, default_shift) VALUES (%s, %s, %s, %s)",
                    ('admin', hashed, 'admin', 'auto')
                )
                current_app.logger.info(f"Admin created with password: {admin_password}")
            
            # Insert default rules jika tabel rules kosong
            cur.execute("SELECT COUNT(*) FROM rules")
            if cur.fetchone()['count'] == 0:
                default_rules = [
                    ('max_breaks_per_day', '3'),
                    ('max_smoking_minutes', '10')
                ]
                for name, val in default_rules:
                    cur.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (name, val))
            
            conn.commit()
            cur.close()
            
        else:
            # SQLite
            # Buat tabel users
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    default_shift TEXT DEFAULT 'auto'
                )
            ''')
            
            # Buat tabel attendance
            conn.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    note TEXT,
                    shift TEXT,
                    late_minutes INTEGER,
                    penalty_level INTEGER,
                    expected_checkout DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Buat tabel breaks
            conn.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    break_type TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    duration INTEGER,
                    phone_used BOOLEAN DEFAULT 0,
                    note TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            
            # Buat tabel rules
            conn.execute('''
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')
            
            # Buat tabel ip_logs
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
            
            # Insert default admin jika tabel users kosong
            cur = conn.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                from werkzeug.security import generate_password_hash
                admin_password = 'admin123'
                hashed = generate_password_hash(admin_password)
                conn.execute(
                    "INSERT INTO users (username, password, role, default_shift) VALUES (?, ?, ?, ?)",
                    ('admin', hashed, 'admin', 'auto')
                )
                current_app.logger.info(f"Admin created with password: {admin_password}")
            
            # Insert default rules jika tabel rules kosong
            cur = conn.execute("SELECT COUNT(*) FROM rules")
            if cur.fetchone()[0] == 0:
                default_rules = [
                    ('max_breaks_per_day', '3'),
                    ('max_smoking_minutes', '10')
                ]
                for name, val in default_rules:
                    conn.execute("INSERT INTO rules (rule_name, value) VALUES (?, ?)", (name, val))
            
            conn.commit()
        
        current_app.logger.info("Database initialized successfully")
        
    except Exception as e:
        current_app.logger.error(f"Database initialization error: {str(e)}")
        raise