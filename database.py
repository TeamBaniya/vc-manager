import sqlite3
import pickle

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('sessions.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                user_id INTEGER,
                first_name TEXT,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Groups table (stored groups for VC)
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
        
        # Sudo users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sudo_users (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_session(self, session_string, user_id, first_name, username):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (session_string, user_id, first_name, username) VALUES (?, ?, ?, ?)",
            (session_string, user_id, first_name, username)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_sessions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sessions")
        return cursor.fetchall()
    
    def get_session_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions")
        return cursor.fetchone()[0]
    
    def add_group(self, group_id, group_name, group_type, username, invite_link, chat_id, added_by):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO groups (group_id, group_name, group_type, username, invite_link, chat_id, added_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, group_name, group_type, username, invite_link, chat_id, added_by)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_active_group(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM groups ORDER BY id DESC LIMIT 1")
        return cursor.fetchone()
    
    def add_sudo(self, user_id, added_by):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO sudo_users (user_id, added_by) VALUES (?, ?)", (user_id, added_by))
        self.conn.commit()
    
    def remove_sudo(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sudo_users WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    def is_sudo(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM sudo_users WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None
    
    def get_all_sudo(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM sudo_users")
        return [row[0] for row in cursor.fetchall()]
    
    def clear_sessions(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sessions")
        self.conn.commit()

db = Database()
