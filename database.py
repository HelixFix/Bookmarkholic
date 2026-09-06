import sqlite3
from config import DB_NAME

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            description TEXT,
            tags TEXT,
            add_date INTEGER,
            private INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()