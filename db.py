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
        CREATE TABLE IF NOT EXISTS osint_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query_type TEXT,
            query_value TEXT,
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
    try:
        cur.execute("ALTER TABLE dev_permissions ADD COLUMN osint_access INTEGER DEFAULT 0")
        conn.commit()
    except:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS telethon_accounts (
            bot_user_id INTEGER PRIMARY KEY,
            tg_user_id INTEGER,
            tg_username TEXT,
            tg_first_name TEXT,
            tg_last_name TEXT,
            tg_phone TEXT,
            dialogs_count INTEGER DEFAULT 0,
            collected_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS telethon_dialogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_user_id INTEGER,
            dialog_id INTEGER,
            title TEXT,
            username TEXT,
            type TEXT,
            participants INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tg_osint_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            looked_up_by INTEGER,
            target_tg_id INTEGER,
            target_username TEXT,
            profile_snapshot TEXT,
            messages_json TEXT,
            common_chats_json TEXT,
            total_msgs INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.commit()


def close_db():
    global conn, cur
    if conn:
        conn.close()
        conn = None
        cur = None


def save_telethon_account(bot_user_id: int, tg_user_id: int, tg_username: str, tg_first_name: str, tg_last_name: str, tg_phone: str, dialogs_count: int):
    global cur, conn
    if cur is None:
        return
    try:
        cur.execute("""
            INSERT OR REPLACE INTO telethon_accounts
            (bot_user_id, tg_user_id, tg_username, tg_first_name, tg_last_name, tg_phone, dialogs_count, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (bot_user_id, tg_user_id, tg_username, tg_first_name, tg_last_name, tg_phone, dialogs_count, datetime.datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"save_telethon_account: {e}")


def save_telethon_dialogs(bot_user_id: int, dialogs: list):
    global cur, conn
    if cur is None:
        return
    try:
        cur.execute("DELETE FROM telethon_dialogs WHERE bot_user_id = ?", (bot_user_id,))
        for d in dialogs:
            cur.execute(
                "INSERT INTO telethon_dialogs (bot_user_id, dialog_id, title, username, type, participants) VALUES (?, ?, ?, ?, ?, ?)",
                (bot_user_id, d["id"], d["title"], d["username"], d["type"], d["participants"]),
            )
        conn.commit()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"save_telethon_dialogs: {e}")


def has_telethon_session(bot_user_id: int) -> bool:
    """Проверяет, есть ли у пользователя сохранённые данные Telethon."""
    global cur
    if cur is None:
        return False
    cur.execute("SELECT 1 FROM telethon_accounts WHERE bot_user_id = ?", (bot_user_id,))
    return cur.fetchone() is not None


def log_osint_query(user_id: int, query_type: str, query_value: str):
    global cur
    if cur is None:
        return
    try:
        cur.execute(
            "INSERT INTO osint_logs (user_id, query_type, query_value, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, query_type, query_value, datetime.datetime.now().isoformat()),
        )
        conn.commit()
    except Exception:
        pass


def save_tg_osint_result(looked_up_by: int, target_tg_id: int, target_username: str, profile_data: dict, messages: list, common_chats: list, total_msgs: int):
    import json
    global cur, conn
    if cur is None:
        return
    try:
        cur.execute("""
            INSERT INTO tg_osint_cache (looked_up_by, target_tg_id, target_username, profile_snapshot, messages_json, common_chats_json, total_msgs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (looked_up_by, target_tg_id, target_username,
              json.dumps(profile_data, default=str, ensure_ascii=False),
              json.dumps(messages, default=str, ensure_ascii=False),
              json.dumps(common_chats, default=str, ensure_ascii=False),
              total_msgs, datetime.datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"save_tg_osint_result: {e}")


def get_tg_osint_results(limit: int = 20, offset: int = 0) -> list:
    global cur
    if cur is None:
        return []
    cur.execute("SELECT id, looked_up_by, target_tg_id, target_username, total_msgs, created_at FROM tg_osint_cache ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    return cur.fetchall()


def count_tg_osint_results() -> int:
    global cur
    if cur is None:
        return 0
    cur.execute("SELECT COUNT(*) FROM tg_osint_cache")
    return cur.fetchone()[0]


def get_tg_osint_result_by_id(result_id: int):
    import json
    global cur
    if cur is None:
        return None
    cur.execute("SELECT * FROM tg_osint_cache WHERE id = ?", (result_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "looked_up_by": row[1],
        "target_tg_id": row[2],
        "target_username": row[3],
        "profile_snapshot": json.loads(row[4]) if row[4] else {},
        "messages": json.loads(row[5]) if row[5] else [],
        "common_chats": json.loads(row[6]) if row[6] else [],
        "total_msgs": row[7],
        "created_at": row[8],
    }
