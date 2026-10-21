import asyncio
import sqlite3
import os
import sys

import pytest

# Убедимся, что корень проекта в пути
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("DB_NAME", ":memory:")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def db_memory():
    """Подменяет db.conn / db.cur на in-memory sqlite с инициализированными таблицами."""
    import db

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            joined_at TEXT,
            last_active TEXT,
            total_chats INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            chat_access INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_at TEXT,
            ban_until TEXT,
            can_appeal INTEGER DEFAULT 1,
            warned_by TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            reported_id INTEGER,
            reason TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS moderation (
            user_id INTEGER PRIMARY KEY,
            warns INTEGER DEFAULT 0,
            muted_until TEXT,
            modded_by TEXT
        );
        CREATE TABLE IF NOT EXISTS dev_permissions (
            user_id INTEGER PRIMARY KEY,
            chat_access INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()

    # Подменяем модульные переменные
    db.conn = conn
    db.cur = cur
    yield conn, cur
    conn.close()
