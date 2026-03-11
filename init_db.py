#!/usr/bin/env python3
"""
Database initialization and migration script for Attendance System.
Run this script to create or migrate database tables.
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# ---------- Configuration ----------
DATABASE_URL = os.environ.get('DATABASE_URL', 'attendance.db')

def print_step(message):
    """Print step with formatting."""
    print(f"\n🔧 {message}")

def print_success(message):
    """Print success message."""
    print(f"✅ {message}")

def print_error(message):
    """Print error message."""
    print(f"❌ {message}")

def print_warning(message):
    """Print warning message."""
    print(f"⚠️ {message}")

def init_sqlite(db_path='attendance.db'):
    """Initialize SQLite database."""
    print_step("Initializing SQLite database...")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # CEK TABEL users
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print_step("Membuat tabel users...")
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        print_success("Tabel users berhasil dibuat")
        
        # Buat default admin (password: admin123)
        from werkzeug.security import generate_password_hash
        hashed = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', hashed, 'admin')
        )
        print_success("User admin default dibuat (password: admin123)")
    else:
        print_success("Tabel users sudah ada")
        
        # CEK KOLOM default_shift
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'default_shift' not in columns:
            print_step("Menambahkan kolom default_shift ke tabel users...")
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN default_shift TEXT DEFAULT "auto"')
                print_success("Kolom default_shift berhasil ditambahkan")
            except Exception as e:
                print_error(f"Gagal menambah kolom: {e}")
        else:
            print_success("Kolom default_shift sudah ada")
    
    # CEK TABEL attendance
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'")
    if not cursor.fetchone():
        print_step("Membuat tabel attendance...")
        cursor.execute('''
            CREATE TABLE attendance (
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
        print_success("Tabel attendance berhasil dibuat")
    else:
        print_success("Tabel attendance sudah ada")
        
        # CEK KOLOM-KOLOM attendance
        cursor.execute("PRAGMA table_info(attendance)")
        columns = [col[1] for col in cursor.fetchall()]
        
        needed_columns = ['shift', 'late_minutes', 'penalty_level', 'expected_checkout']
        for col in needed_columns:
            if col not in columns:
                print_step(f"Menambahkan kolom {col} ke tabel attendance...")
                try:
                    cursor.execute(f'ALTER TABLE attendance ADD COLUMN {col} TEXT')
                    print_success(f"Kolom {col} berhasil ditambahkan")
                except Exception as e:
                    print_error(f"Gagal menambah kolom {col}: {e}")
    
    # CEK TABEL breaks
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='breaks'")
    if not cursor.fetchone():
        print_step("Membuat tabel breaks...")
        cursor.execute('''
            CREATE TABLE breaks (
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
        print_success("Tabel breaks berhasil dibuat")
    else:
        print_success("Tabel breaks sudah ada")
    
    # CEK TABEL off_days
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='off_days'")
    if not cursor.fetchone():
        print_step("Membuat tabel off_days...")
        cursor.execute('''
            CREATE TABLE off_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                description TEXT
            )
        ''')
        print_success("Tabel off_days berhasil dibuat")
    else:
        print_success("Tabel off_days sudah ada")
    
    # CEK TABEL rules
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rules'")
    if not cursor.fetchone():
        print_step("Membuat tabel rules...")
        cursor.execute('''
            CREATE TABLE rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        ''')
        print_success("Tabel rules berhasil dibuat")
        
        # Insert default rules
        default_rules = [
            ('max_breaks_per_day', '3'),
            ('max_smoking_minutes', '10')
        ]
        for name, val in default_rules:
            cursor.execute("INSERT INTO rules (rule_name, value) VALUES (?, ?)", (name, val))
        print_success("Default rules berhasil ditambahkan")
    else:
        print_success("Tabel rules sudah ada")
        
        # CEK APAKAH DEFAULT RULES ADA
        cursor.execute("SELECT COUNT(*) FROM rules")
        if cursor.fetchone()[0] == 0:
            default_rules = [
                ('max_breaks_per_day', '3'),
                ('max_smoking_minutes', '10')
            ]
            for name, val in default_rules:
                cursor.execute("INSERT INTO rules (rule_name, value) VALUES (?, ?)", (name, val))
            print_success("Default rules berhasil ditambahkan")
    
    # CEK TABEL user_debt
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_debt'")
    if not cursor.fetchone():
        print_step("Membuat tabel user_debt...")
        cursor.execute('''
            CREATE TABLE user_debt (
                user_id INTEGER PRIMARY KEY,
                owed_minutes INTEGER DEFAULT 0,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        print_success("Tabel user_debt berhasil dibuat")
    else:
        print_success("Tabel user_debt sudah ada")
    
    conn.commit()
    conn.close()
    print_success("SQLite database initialization complete!")

def init_postgres(db_url):
    """Initialize PostgreSQL database."""
    print_step("Initializing PostgreSQL database...")
    
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    # CEK TABEL users
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'users'
        )
    """)
    table_exists = cur.fetchone()['exists']
    
    if not table_exists:
        print_step("Membuat tabel users...")
        cur.execute('''
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        print_success("Tabel users berhasil dibuat")
        
        # Buat default admin
        from werkzeug.security import generate_password_hash
        hashed = generate_password_hash('admin123')
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ('admin', hashed, 'admin')
        )
        print_success("User admin default dibuat (password: admin123)")
    else:
        print_success("Tabel users sudah ada")
        
        # CEK KOLOM default_shift
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='default_shift'
        """)
        if not cur.fetchone():
            print_step("Menambahkan kolom default_shift ke tabel users...")
            try:
                cur.execute('ALTER TABLE users ADD COLUMN default_shift TEXT DEFAULT \'auto\'')
                print_success("Kolom default_shift berhasil ditambahkan")
            except Exception as e:
                print_error(f"Gagal menambah kolom: {e}")
        else:
            print_success("Kolom default_shift sudah ada")
    
    # CEK TABEL attendance
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'attendance'
        )
    """)
    if not cur.fetchone()['exists']:
        print_step("Membuat tabel attendance...")
        cur.execute('''
            CREATE TABLE attendance (
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
        print_success("Tabel attendance berhasil dibuat")
    else:
        print_success("Tabel attendance sudah ada")
    
    # CEK TABEL breaks
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'breaks'
        )
    """)
    if not cur.fetchone()['exists']:
        print_step("Membuat tabel breaks...")
        cur.execute('''
            CREATE TABLE breaks (
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
        print_success("Tabel breaks berhasil dibuat")
    else:
        print_success("Tabel breaks sudah ada")
    
    # CEK TABEL off_days
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'off_days'
        )
    """)
    if not cur.fetchone()['exists']:
        print_step("Membuat tabel off_days...")
        cur.execute('''
            CREATE TABLE off_days (
                id SERIAL PRIMARY KEY,
                date DATE UNIQUE NOT NULL,
                description TEXT
            )
        ''')
        print_success("Tabel off_days berhasil dibuat")
    else:
        print_success("Tabel off_days sudah ada")
    
    # CEK TABEL rules
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'rules'
        )
    """)
    if not cur.fetchone()['exists']:
        print_step("Membuat tabel rules...")
        cur.execute('''
            CREATE TABLE rules (
                id SERIAL PRIMARY KEY,
                rule_name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        ''')
        print_success("Tabel rules berhasil dibuat")
        
        # Insert default rules
        default_rules = [
            ('max_breaks_per_day', '3'),
            ('max_smoking_minutes', '10')
        ]
        for name, val in default_rules:
            cur.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (name, val))
        print_success("Default rules berhasil ditambahkan")
    else:
        print_success("Tabel rules sudah ada")
        
        # CEK APAKAH DEFAULT RULES ADA
        cur.execute("SELECT COUNT(*) FROM rules")
        if cur.fetchone()['count'] == 0:
            default_rules = [
                ('max_breaks_per_day', '3'),
                ('max_smoking_minutes', '10')
            ]
            for name, val in default_rules:
                cur.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (name, val))
            print_success("Default rules berhasil ditambahkan")
    
    # CEK TABEL user_debt
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'user_debt'
        )
    """)
    if not cur.fetchone()['exists']:
        print_step("Membuat tabel user_debt...")
        cur.execute('''
            CREATE TABLE user_debt (
                user_id INTEGER PRIMARY KEY,
                owed_minutes INTEGER DEFAULT 0,
                updated_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        print_success("Tabel user_debt berhasil dibuat")
    else:
        print_success("Tabel user_debt sudah ada")
    
    conn.commit()
    cur.close()
    conn.close()
    print_success("PostgreSQL database initialization complete!")

def show_tables_sqlite(db_path='attendance.db'):
    """Show all tables in SQLite database."""
    print_step("Menampilkan struktur database SQLite...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Dapatkan semua tabel
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print(f"\n📊 Daftar tabel ({len(tables)}):")
    for table in tables:
        table_name = table[0]
        print(f"\n  📁 {table_name}:")
        
        # Tampilkan kolom untuk setiap tabel
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        for col in columns:
            pk = "🔑 PRIMARY KEY" if col[5] else ""
            print(f"    • {col[1]} ({col[2]}) {pk}")
    
    conn.close()

def main():
    """Main function."""
    print("\n" + "="*60)
    print(" DATABASE INITIALIZATION FOR ATTENDANCE SYSTEM")
    print("="*60)
    
    # Cek tipe database
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        print(f"📡 Using PostgreSQL: {DATABASE_URL[:30]}...")
        init_postgres(DATABASE_URL)
    else:
        db_path = 'attendance.db'
        print(f"💾 Using SQLite: {db_path}")
        init_sqlite(db_path)
        show_tables_sqlite(db_path)
    
    print("\n" + "="*60)
    print("✅ DATABASE INITIALIZATION COMPLETE!")
    print("="*60)
    print("\n📝 Default admin login:")
    print("   Username: admin")
    print("   Password: admincoy123")
    print("\n⚠️  JANGAN LUPA UBAH PASSWORD ADMIN SETELAH LOGIN PERTAMA!")
    print("="*60)

if __name__ == '__main__':
    main()