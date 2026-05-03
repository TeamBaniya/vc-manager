import sqlite3
import json
from datetime import datetime

class Database:
    def __init__(self, db_file="vc_manager.db"):
        self.db_file = db_file
        self.conn = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Create database connection"""
        try:
            self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            print(f"✅ Database connected: {self.db_file}")
        except Exception as e:
            print(f"❌ Database connection error: {e}")
    
    def create_tables(self):
        """Create all required tables"""
        cursor = self.conn.cursor()
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                user_id INTEGER,
                first_name TEXT,
                username TEXT,
                phone TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Groups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                group_name TEXT,
                group_type TEXT,
                username TEXT,
                invite_link TEXT,
                chat_id INTEGER,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sudo users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sudo_users (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Voice chat history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vc_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                group_name TEXT,
                account_name TEXT,
                account_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                left_at TIMESTAMP
            )
        ''')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        print("✅ Tables created successfully")
    
    # ==================== SESSIONS METHODS ====================
    
    def add_session(self, session_string, user_id, first_name, username, phone=None):
        """Add a new session"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (session_string, user_id, first_name, username, phone)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_string, user_id, first_name, username, phone))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_sessions(self):
        """Get all sessions"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE is_active = 1 ORDER BY id DESC')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_session_by_id(self, session_id):
        """Get session by ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE id = ? AND is_active = 1', (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_session_by_user_id(self, user_id):
        """Get session by user ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE user_id = ? AND is_active = 1', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_session_count(self):
        """Get total number of sessions"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM sessions WHERE is_active = 1')
        return cursor.fetchone()['count']
    
    def update_session(self, session_id, **kwargs):
        """Update session details"""
        cursor = self.conn.cursor()
        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(session_id)
        query = f'UPDATE sessions SET {", ".join(fields)} WHERE id = ?'
        cursor.execute(query, values)
        self.conn.commit()
        return cursor.rowcount > 0
    
    def delete_session(self, session_id):
        """Soft delete a session"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE id = ?', (session_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def delete_all_sessions(self):
        """Delete all sessions"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM sessions')
        self.conn.commit()
        return cursor.rowcount
    
    # ==================== GROUPS METHODS ====================
    
    def add_group(self, group_id, group_name, group_type, username, invite_link, chat_id, added_by):
        """Add a new group"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO groups (group_id, group_name, group_type, username, invite_link, chat_id, added_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (group_id, group_name, group_type, username, invite_link, chat_id, added_by))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_groups(self):
        """Get all groups"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM groups ORDER BY id DESC')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_group_by_id(self, group_db_id):
        """Get group by database ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM groups WHERE id = ?', (group_db_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_group_by_chat_id(self, chat_id):
        """Get group by chat ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM groups WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_active_group(self):
        """Get the most recently added group"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM groups ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def update_group(self, group_db_id, **kwargs):
        """Update group details"""
        cursor = self.conn.cursor()
        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(group_db_id)
        query = f'UPDATE groups SET {", ".join(fields)} WHERE id = ?'
        cursor.execute(query, values)
        self.conn.commit()
        return cursor.rowcount > 0
    
    def delete_group(self, group_db_id):
        """Delete a group"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM groups WHERE id = ?', (group_db_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_groups_count(self):
        """Get total number of groups"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM groups')
        return cursor.fetchone()['count']
    
    # ==================== SUDO USERS METHODS ====================
    
    def add_sudo(self, user_id, added_by):
        """Add a sudo user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sudo_users (user_id, added_by)
            VALUES (?, ?)
        ''', (user_id, added_by))
        self.conn.commit()
        return True
    
    def remove_sudo(self, user_id):
        """Remove a sudo user"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM sudo_users WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def is_sudo(self, user_id):
        """Check if user is sudo"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM sudo_users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None
    
    def get_all_sudo(self):
        """Get all sudo users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM sudo_users')
        return [row['user_id'] for row in cursor.fetchall()]
    
    def get_sudo_count(self):
        """Get total number of sudo users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM sudo_users')
        return cursor.fetchone()['count']
    
    # ==================== VC HISTORY METHODS ====================
    
    def add_vc_history(self, group_id, group_name, account_name, account_id):
        """Add VC join history"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO vc_history (group_id, group_name, account_name, account_id)
            VALUES (?, ?, ?, ?)
        ''', (group_id, group_name, account_name, account_id))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_vc_left(self, history_id):
        """Update VC left time"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE vc_history SET left_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (history_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_vc_history(self, limit=50):
        """Get VC history"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM vc_history 
            ORDER BY joined_at DESC 
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_vc_history_by_group(self, group_id, limit=50):
        """Get VC history by group"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM vc_history 
            WHERE group_id = ? 
            ORDER BY joined_at DESC 
            LIMIT ?
        ''', (group_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    # ==================== SETTINGS METHODS ====================
    
    def set_setting(self, key, value):
        """Set a setting"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, json.dumps(value)))
        self.conn.commit()
        return True
    
    def get_setting(self, key, default=None):
        """Get a setting"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row['value'])
        return default
    
    def get_all_settings(self):
        """Get all settings"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        return {row['key']: json.loads(row['value']) for row in cursor.fetchall()}
    
    # ==================== UTILITY METHODS ====================
    
    def backup_database(self, backup_file):
        """Backup database"""
        import shutil
        try:
            shutil.copy2(self.db_file, backup_file)
            return True
        except Exception as e:
            print(f"Backup error: {e}")
            return False
    
    def clear_all_data(self):
        """Clear all data from tables"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM sessions')
        cursor.execute('DELETE FROM groups')
        cursor.execute('DELETE FROM vc_history')
        self.conn.commit()
        return True
    
    def get_stats(self):
        """Get database statistics"""
        cursor = self.conn.cursor()
        stats = {}
        
        cursor.execute('SELECT COUNT(*) as count FROM sessions WHERE is_active = 1')
        stats['total_sessions'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM groups')
        stats['total_groups'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM sudo_users')
        stats['total_sudo'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM vc_history')
        stats['total_vc_joins'] = cursor.fetchone()['count']
        
        return stats
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("Database connection closed")

# Create a global database instance
db = Database()
