import datetime
from typing import Optional
import db

def get_username_safe(user_id: int) -> str:
    try:
        db.cur.execute("SELECT username, nickname FROM users WHERE user_id = ?", (user_id,))
        row = db.cur.fetchone()
        return row[1] or row[0] or "unknown"
    except: return "unknown"

def is_admin(user_id: int) -> bool:
    db.cur.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    row = db.cur.fetchone()
    return row is not None and row[0] == 1

def is_banned(user_id: int) -> bool:
    now = datetime.datetime.now().isoformat()
    db.cur.execute("SELECT 1 FROM bans WHERE user_id = ? AND (ban_until IS NULL OR ban_until > ?)", (user_id, now))
    return db.cur.fetchone() is not None

def save_message(sender: int, receiver: int, text: str) -> None:
    db.cur.execute("INSERT INTO messages (sender_id, receiver_id, message, timestamp) VALUES (?,?,?,?)",
                   (sender, receiver, text, datetime.datetime.now().isoformat()))
    db.conn.commit()