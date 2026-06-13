import sqlite3
import datetime
import os
import logging

DATA_DIR = "/data" if os.path.exists("/data") else "."
DB_NAME = os.path.join(DATA_DIR, "chat.db")
conn: sqlite3.Connection | None = None
cur: sqlite3.Cursor | None = None


def init_db():
    global conn, cur
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            joined_at TEXT,
            last_active TEXT,
            total_chats INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            timestamp TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_at TEXT,
            ban_until TEXT,
            can_appeal INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            reported_id INTEGER,
            reason TEXT,
            timestamp TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            timestamp TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS moderation (
            user_id INTEGER PRIMARY KEY,
            warns INTEGER DEFAULT 0,
            muted_until TEXT,
            modded_by TEXT
        )
    """)

    conn.commit()

    # migration for existing DBs
    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()
    except:
        pass
    try:
        cur.execute("ALTER TABLE bans ADD COLUMN warned_by TEXT")
        conn.commit()
    except:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN chat_access INTEGER DEFAULT 0")
        conn.commit()
    except:
        pass
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS dev_permissions (user_id INTEGER PRIMARY KEY, chat_access INTEGER DEFAULT 0)")
        conn.commit()
    except:
        pass
    conn.commit()


def close_db():
    global conn, cur
    if conn:
        conn.close()
        conn = None
        cur = None



