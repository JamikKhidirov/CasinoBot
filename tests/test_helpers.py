import datetime

import db
from config import OWNER_ID
from utils import helpers


def _now_iso():
    return datetime.datetime.now().isoformat()


def test_is_dev_owner_true(db_memory):
    assert helpers.is_dev(OWNER_ID) is True


def test_is_dev_other_false(db_memory):
    assert helpers.is_dev(999) is False


def test_is_admin_owner_true(db_memory):
    assert helpers.is_admin(OWNER_ID) is True


def test_is_admin_db_true(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (123, 'u', 1)")
    conn.commit()
    assert helpers.is_admin(123) is True


def test_is_admin_db_false(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (124, 'u', 0)")
    conn.commit()
    assert helpers.is_admin(124) is False


def test_is_admin_unknown(db_memory):
    assert helpers.is_admin(99999) is False


def test_is_banned_unlimited(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO bans (user_id, reason, banned_at) VALUES (5, 'r', ?)", (_now_iso(),))
    conn.commit()
    assert helpers.is_banned(5) is True


def test_is_banned_expired(db_memory):
    conn, cur = db_memory
    past = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
    cur.execute("INSERT INTO bans (user_id, reason, banned_at, ban_until) VALUES (6, 'r', ?, ?)", (_now_iso(), past))
    conn.commit()
    assert helpers.is_banned(6) is False


def test_is_banned_not_banned(db_memory):
    assert helpers.is_banned(777) is False


def test_get_warns_default_zero(db_memory):
    assert helpers.get_warns(1) == 0


def test_add_warn_increments(db_memory):
    conn, cur = db_memory
    w1 = helpers.add_warn(1, OWNER_ID)
    assert w1 == 1
    w2 = helpers.add_warn(1, OWNER_ID)
    assert w2 == 2
    w3 = helpers.add_warn(1, OWNER_ID)
    assert w3 == 3
    assert helpers.get_warns(1) == 3


def test_add_warn_triggers_ban(db_memory):
    conn, cur = db_memory
    helpers.add_warn(2, OWNER_ID)
    helpers.add_warn(2, OWNER_ID)
    helpers.add_warn(2, OWNER_ID)
    assert helpers.is_banned(2) is True


def test_ban_and_unban(db_memory):
    helpers.ban_user(3, OWNER_ID, "spam")
    assert helpers.is_banned(3) is True
    helpers.unban_user(3)
    assert helpers.is_banned(3) is False


def test_mute_and_unmute(db_memory):
    conn, cur = db_memory
    future = (datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat()
    helpers.mute_user(4, OWNER_ID, 10)
    assert helpers.is_muted(4) is True
    helpers.unmute_user(4)
    row = cur.execute("SELECT muted_until FROM moderation WHERE user_id = 4").fetchone()
    assert row[0] is None


def test_can_moderate_owner_can_anyone(db_memory):
    assert helpers.can_moderate(OWNER_ID, 123) is True


def test_can_moderate_cannot_owner_target(db_memory):
    assert helpers.can_moderate(123, OWNER_ID) is False


def test_can_moderate_admin_on_non_admin(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (10, 'a', 1)")
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (20, 'b', 0)")
    conn.commit()
    assert helpers.can_moderate(10, 20) is True


def test_can_moderate_admin_on_admin_false(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (10, 'a', 1)")
    cur.execute("INSERT INTO users (user_id, username, is_admin) VALUES (20, 'b', 1)")
    conn.commit()
    assert helpers.can_moderate(10, 20) is False


def test_resolve_user_numeric(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username) VALUES (42, 'user42')")
    conn.commit()
    assert helpers.resolve_user("42") == 42


def test_resolve_user_at_username(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username) VALUES (43, 'User43')")
    conn.commit()
    assert helpers.resolve_user("@User43") == 43
    assert helpers.resolve_user("user43") == 43


def test_resolve_user_not_found(db_memory):
    assert helpers.resolve_user("nope") is None


def test_save_message(db_memory):
    conn, cur = db_memory
    helpers.save_message(1, 2, "hello")
    row = cur.execute("SELECT message FROM messages WHERE sender_id=1 AND receiver_id=2").fetchone()
    assert row[0] == "hello"


def test_update_user_activity(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username) VALUES (50, 'old')")
    conn.commit()
    helpers.update_user_activity(50, username="new")
    row = cur.execute("SELECT username, last_active FROM users WHERE user_id=50").fetchone()
    assert row[0] == "new"
    assert row[1] is not None


def test_get_username_safe(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, nickname) VALUES (60, 'u60', 'Ник')")
    conn.commit()
    assert helpers.get_username_safe(60) == "Ник"


def test_get_user_display(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO users (user_id, username, nickname) VALUES (61, 'u61', 'Ник61')")
    conn.commit()
    disp = helpers.get_user_display(61)
    assert "Ник61" in disp
    assert "@u61" in disp
    assert "<code>61</code>" in disp


def test_can_read_chats_owner(db_memory):
    assert helpers.can_read_chats(OWNER_ID) is True


def test_can_read_chats_permission(db_memory):
    conn, cur = db_memory
    cur.execute("INSERT INTO dev_permissions (user_id, chat_access) VALUES (70, 1)")
    conn.commit()
    assert helpers.can_read_chats(70) is True


def test_can_read_chats_no_permission(db_memory):
    assert helpers.can_read_chats(80) is False


def test_strip_html():
    assert helpers.strip_html("<b>привет</b> <i>мир</i>") == "привет мир"
    assert helpers.strip_html("просто текст") == "просто текст"
