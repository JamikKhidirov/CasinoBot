import datetime
import re
from typing import Optional
import db
from config import OWNER_ID

def get_username_safe(user_id: int) -> str:
    try:
        db.cur.execute("SELECT username, nickname FROM users WHERE user_id = ?", (user_id,))
        row = db.cur.fetchone()
        return row[1] or row[0] or "unknown"
    except: return "unknown"

def is_dev(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        db.cur.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = db.cur.fetchone()
        return row is not None and row[0] == 1
    except:
        return False

def is_banned(user_id: int) -> bool:
    now = datetime.datetime.now().isoformat()
    db.cur.execute("SELECT 1 FROM bans WHERE user_id = ? AND (ban_until IS NULL OR ban_until > ?)", (user_id, now))
    return db.cur.fetchone() is not None

def is_muted(user_id: int) -> bool:
    now = datetime.datetime.now().isoformat()
    db.cur.execute("SELECT muted_until FROM moderation WHERE user_id = ?", (user_id,))
    row = db.cur.fetchone()
    if row and row[0]:
        return row[0] > now
    return False

def get_warns(user_id: int) -> int:
    try:
        db.cur.execute("SELECT warns FROM moderation WHERE user_id = ?", (user_id,))
        row = db.cur.fetchone()
        return row[0] if row else 0
    except:
        return 0

def add_warn(user_id: int, mod_id: int) -> int:
    warns = get_warns(user_id) + 1
    db.cur.execute(
        "INSERT INTO moderation (user_id, warns, modded_by) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET warns = ?",
        (user_id, warns, str(mod_id), warns),
    )
    db.conn.commit()
    if warns >= 3:
        ban_user(user_id, mod_id, "3/3 варнов →自动 бан")
    return warns

def ban_user(user_id: int, mod_id: int, reason: str = "") -> None:
    now = datetime.datetime.now().isoformat()
    db.cur.execute(
        "INSERT INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET reason = ?, banned_at = ?, ban_until = NULL",
        (user_id, reason, now, reason, now),
    )
    db.conn.commit()

def unban_user(user_id: int) -> None:
    db.cur.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    db.conn.commit()

def mute_user(user_id: int, mod_id: int, minutes: int) -> None:
    until = (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).isoformat()
    db.cur.execute(
        "INSERT INTO moderation (user_id, muted_until, modded_by) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET muted_until = ?",
        (user_id, until, str(mod_id), until),
    )
    db.conn.commit()

def unmute_user(user_id: int) -> None:
    db.cur.execute("UPDATE moderation SET muted_until = NULL WHERE user_id = ?", (user_id,))
    db.conn.commit()

def can_moderate(mod_id: int, target_id: int) -> bool:
    if target_id == OWNER_ID:
        return False
    if mod_id == OWNER_ID:
        return True
    if is_admin(mod_id) and not is_admin(target_id):
        return True
    return False

def save_message(sender: int, receiver: int, text: str) -> None:
    db.cur.execute("INSERT INTO messages (sender_id, receiver_id, message, timestamp) VALUES (?,?,?,?)",
                   (sender, receiver, text, datetime.datetime.now().isoformat()))
    db.conn.commit()


def can_read_chats(uid: int) -> bool:
    """Только OWNER и те, кому выдано разрешение (dev_permissions.chat_access=1)."""
    if uid == OWNER_ID:
        return True
    try:
        db.cur.execute("SELECT chat_access FROM dev_permissions WHERE user_id = ?", (uid,))
        row = db.cur.fetchone()
        return row is not None and row[0] == 1
    except:
        return False


def resolve_user(text: str) -> int | None:
    """Resolve @username or numeric ID to user_id."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    username = text[1:].lower() if text.startswith("@") else text.lower()
    try:
        db.cur.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (username,))
        row = db.cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def strip_html(text: str) -> str:
    """Remove all HTML tags from string for safe Telegram display."""
    return re.sub(r'<[^>]+>', '', text)


def update_user_activity(user_id: int, username: str = None, nickname: str = None):
    """Обновляет данные пользователя при каждом взаимодействии."""
    now = datetime.datetime.now().isoformat()
    try:
        if username:
            db.cur.execute(
                "UPDATE users SET username = ?, last_active = ? WHERE user_id = ?",
                (username, now, user_id),
            )
        else:
            db.cur.execute(
                "UPDATE users SET last_active = ? WHERE user_id = ?",
                (now, user_id),
            )
        if nickname:
            db.cur.execute(
                "UPDATE users SET nickname = ? WHERE user_id = ?",
                (nickname, user_id),
            )
        db.conn.commit()
    except:
        pass