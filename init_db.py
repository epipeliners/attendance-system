import os
import psycopg2
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get('DATABASE_URL')  # set this later

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id SERIAL PRIMARY KEY,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'cs')''')
    
    c. execute_db('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
           [username, hashed_password, role])

    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance
                 (id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  action TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  note TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Rules table
    c.execute('''CREATE TABLE IF NOT EXISTS rules
                 (id SERIAL PRIMARY KEY,
                  rule_name TEXT UNIQUE NOT NULL,
                  value TEXT NOT NULL)''')

    # Off days table
    c.execute('''CREATE TABLE IF NOT EXISTS off_days
                 (id SERIAL PRIMARY KEY,
                  date TEXT UNIQUE NOT NULL,
                  description TEXT)''')

    # Insert default admin user (username: admin, password: admin123)
    admin_pass = generate_password_hash('admin123')
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  ('admin', admin_pass, 'admin'))
    except psycopg2.IntegrityError:
        conn.rollback()
    else:
        conn.commit()

    # Default rules
    default_rules = [
        ('work_start', '00:00'),
        ('work_end', '10:00'),
        ('grace_period', '00'),
        ('break_start', '00:00'),
        ('break_end', '00:00'),
        ('max_early_minutes', '10')
    ]
    for rule, val in default_rules:
        try:
            c.execute("INSERT INTO rules (rule_name, value) VALUES (%s, %s)", (rule, val))
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()

    conn.commit()
    conn.close()
    print("PostgreSQL database initialized.")


if __name__ == '__main__':
    init_db()