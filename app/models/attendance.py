"""
Model untuk Attendance.
"""
from app.utils.database import query_db, execute_db
from app.utils.helpers import now_local, format_datetime
from app.config import config
import os

active_config = config[os.environ.get('FLASK_CONFIG', 'default')]
TIMEZONE = active_config.TIMEZONE

class Attendance:
    """Class untuk mengelola data attendance."""
    
    @staticmethod
    def get_today_checkin(user_id):
        """Get today's check-in record."""
        today = now_local().strftime('%Y-%m-%d')
        return query_db('''SELECT * FROM attendance 
                          WHERE user_id = ? AND DATE(timestamp) = ? AND action = 'Check In'
                          ORDER BY timestamp DESC LIMIT 1''',
                       [user_id, today], one=True)
    
    @staticmethod
    def get_today_checkout(user_id):
        """Get today's check-out record."""
        today = now_local().strftime('%Y-%m-%d')
        return query_db('''SELECT id FROM attendance 
                          WHERE user_id = ? AND DATE(timestamp) = ? 
                          AND action IN ('Check Out', 'Sick Check Out')''',
                       [user_id, today], one=True)
    
    @staticmethod
    def create(user_id, action, note=None, shift=None, late_minutes=None, 
               penalty_level=None, expected_checkout=None):
        """Create new attendance record."""
        now_str = format_datetime(now_local())
        return execute_db('''INSERT INTO attendance 
            (user_id, action, timestamp, note, shift, late_minutes, penalty_level, expected_checkout)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            [user_id, action, now_str, note, shift, late_minutes, penalty_level, expected_checkout])
    
    @staticmethod
    def get_user_records(user_id, role='user', limit=500):
        """Get records for specific user."""
        from itertools import chain
        
        if role == 'admin':
            # Admin melihat semua
            attendance = query_db('''
                SELECT a.*, u.username 
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                ORDER BY a.timestamp DESC
                LIMIT ?
            ''', [limit])
            
            breaks = query_db('''
                SELECT b.*, u.username 
                FROM breaks b
                JOIN users u ON b.user_id = u.id
                ORDER BY b.start_time DESC
                LIMIT ?
            ''', [limit])
        else:
            # User melihat sendiri
            attendance = query_db('''
                SELECT a.*, u.username 
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                WHERE a.user_id = ?
                ORDER BY a.timestamp DESC
                LIMIT ?
            ''', [user_id, limit])
            
            breaks = query_db('''
                SELECT b.*, u.username 
                FROM breaks b
                JOIN users u ON b.user_id = u.id
                WHERE b.user_id = ?
                ORDER BY b.start_time DESC
                LIMIT ?
            ''', [user_id, limit])
        
        # Gabungkan dan beri label tipe
        for rec in attendance:
            rec['record_type'] = 'attendance'
        for rec in breaks:
            rec['record_type'] = 'break'
            rec['timestamp'] = rec['start_time']  # untuk sorting
        
        # Gabungkan dan urutkan
        records = list(chain(attendance, breaks))
        records.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Tambahkan nomor urut
        for idx, rec in enumerate(records, 1):
            rec['no'] = idx
        
        return records[:limit]
    
    @staticmethod
    def delete_old_records(days):
        """Delete records older than specified days."""
        from datetime import timedelta
        cutoff = now_local() - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        return execute_db('DELETE FROM attendance WHERE timestamp < ?', [cutoff_str])
    
    @staticmethod
    def delete_all():
        """Delete all attendance records."""
        return execute_db('DELETE FROM attendance')