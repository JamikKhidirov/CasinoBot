from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault
from config import OWNER_ID
from utils.helpers import is_admin, can_read_chats
import db
import datetime
import asyncio
import logging

router = Router()
logger = logging.getLogger(__name__)


def is_dev(uid: int) -> bool:
    return uid == OWNER_ID


# ========== УПРАВЛЕНИЕ АДМИНАМИ ==========

@router.message(Command("dev_addadmin"))
async def cmd_dev_addadmin(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_addadmin <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    db.cur.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (uid,))
    if db.cur.rowcount == 0:
        db.cur.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin, joined_at) VALUES (?, '', 1, ?)",
                       (uid, datetime.datetime.now().isoformat()))
    db.conn.commit()
    # Даём команды админу
    from main import ADMIN_COMMANDS
    try:
        bot = message.bot
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=uid))
    except:
        pass
    await message.answer(f"✅ Пользователь {uid} теперь администратор!")


@router.message(Command("dev_removeadmin"))
async def cmd_dev_removeadmin(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_removeadmin <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    if uid == OWNER_ID:
        await message.answer("❌ Нельзя снять права с владельца")
        return
    db.cur.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (uid,))
    db.conn.commit()
    # Возвращаем публичные команды
    from main import PUBLIC_COMMANDS
    try:
        bot = message.bot
        await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeChat(chat_id=uid))
    except:
        pass
    await message.answer(f"✅ Пользователь {uid} больше не администратор")


@router.message(Command("dev_admins"))
async def cmd_dev_admins(message: Message):
    if not is_dev(message.from_user.id):
        return
    db.cur.execute("SELECT user_id, username FROM users WHERE is_admin = 1 ORDER BY user_id")
    rows = db.cur.fetchall()
    parts = ["<b>👑 Администраторы</b>\n"]
    for row in rows:
        name = f"@{row[1]}" if row[1] else f"ID{row[0]}"
        parts.append(f"┃ {name} — <code>{row[0]}</code>")
    await message.answer("\n".join(parts) if len(parts) > 1 else "❌ Нет администраторов", parse_mode="HTML")


# ========== ДОСТУП К ЧАТАМ ==========

@router.message(Command("dev_grantchat"))
async def cmd_dev_grantchat(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_grantchat <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    db.cur.execute("INSERT OR REPLACE INTO dev_permissions (user_id, chat_access) VALUES (?, 1)", (uid,))
    db.conn.commit()
    await message.answer(f"✅ Пользователь {uid} получил доступ к чтению чатов")


@router.message(Command("dev_revokechat"))
async def cmd_dev_revokechat(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_revokechat <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    if uid == OWNER_ID:
        await message.answer("❌ Нельзя отозвать доступ у владельца")
        return
    db.cur.execute("DELETE FROM dev_permissions WHERE user_id = ?", (uid,))
    db.conn.commit()
    await message.answer(f"✅ Доступ к чатам отозван у {uid}")


@router.message(Command("dev_chataccess"))
async def cmd_dev_chataccess(message: Message):
    if not is_dev(message.from_user.id):
        return
    db.cur.execute("""
        SELECT dp.user_id, u.username FROM dev_permissions dp
        LEFT JOIN users u ON u.user_id = dp.user_id
        WHERE dp.chat_access = 1
    """)
    rows = db.cur.fetchall()
    parts = ["<b>💬 Доступ к чатам имеют:</b>\n", f"┃ 👑 {OWNER_ID} (владелец)"]
    for row in rows:
        name = f"@{row[1]}" if row[1] else f"ID{row[0]}"
        parts.append(f"┃ {name} — <code>{row[0]}</code>")
    await message.answer("\n".join(parts), parse_mode="HTML")


# ========== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ==========

@router.message(Command("dev_users"))
async def cmd_dev_users(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    # /dev_users — все, /dev_users 10 — первые 10
    limit = 100
    if command.args:
        try:
            limit = min(int(command.args.strip()), 500)
        except:
            pass
    db.cur.execute(f"SELECT user_id, username, total_messages, is_admin FROM users ORDER BY total_messages DESC LIMIT {limit}")
    rows = db.cur.fetchall()
    parts = [f"<b>👥 Пользователи (топ {limit})</b>\n"]
    for row in rows:
        name = f"@{row[1]}" if row[1] else f"ID{row[0]}"
        admin = " 👑" if row[3] else ""
        parts.append(f"┃ {name} — {row[2]} сообщ.{admin}")
    text = "\n".join(parts)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await message.answer(text, parse_mode="HTML")


@router.message(Command("dev_userinfo"))
async def cmd_dev_userinfo(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_userinfo <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    db.cur.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    row = db.cur.fetchone()
    if not row:
        await message.answer(f"❌ Пользователь {uid} не найден в БД")
        return
    columns = [d[0] for d in db.cur.description]
    lines = [f"<b>📋 Информация о {uid}</b>\n"]
    for i, col in enumerate(columns):
        val = row[i] if i < len(row) else "—"
        if val is None: val = "—"
        lines.append(f"┃ {col}: <code>{val}</code>")
    # Проверка чатов
    db.cur.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ? OR receiver_id = ?", (uid, uid))
    msg_count = db.cur.fetchone()[0]
    lines.append(f"┃ messages_total: <code>{msg_count}</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ========== БРОДКАСТ ==========

@router.message(Command("dev_broadcast"))
async def cmd_dev_broadcast(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Напишите текст: /dev_broadcast <текст>")
        return
    text = command.args
    db.cur.execute("SELECT user_id FROM users")
    uids = [r[0] for r in db.cur.fetchall()]
    sent = 0
    failed = 0
    for uid in uids:
        try:
            await message.bot.send_message(uid, f"📢 <b>Сообщение от разработчика</b>\n\n{text}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await message.answer(f"✅ Отправлено: {sent}\n❌ Ошибок: {failed}")


# ========== СКАЗАТЬ ОТ ЛИЦА БОТА ==========

@router.message(Command("dev_say"))
async def cmd_dev_say(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args or " " not in command.args:
        await message.answer("❌ Формат: /dev_say <chat_id> <текст>")
        return
    parts = command.args.split(" ", 1)
    try:
        chat_id = int(parts[0].strip())
    except ValueError:
        await message.answer("❌ chat_id должен быть числом")
        return
    msg = parts[1].strip()
    try:
        await message.bot.send_message(chat_id, msg, parse_mode="HTML")
        await message.answer(f"✅ Отправлено в {chat_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ========== ВЫЙТИ ИЗ ЧАТА ==========

@router.message(Command("dev_leavechat"))
async def cmd_dev_leavechat(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите chat_id: /dev_leavechat <chat_id>")
        return
    try:
        chat_id = int(command.args.strip())
    except ValueError:
        await message.answer("❌ chat_id должен быть числом")
        return
    try:
        await message.bot.leave_chat(chat_id)
        await message.answer(f"✅ Вышел из чата {chat_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ========== БАЛАНС КАЗИНО ==========

@router.message(Command("dev_setcoins"))
async def cmd_dev_setcoins(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args or " " not in command.args:
        await message.answer("❌ Формат: /dev_setcoins <id> <сумма>")
        return
    parts = command.args.split(" ", 1)
    try:
        uid = int(parts[0].strip())
        amount = int(parts[1].strip())
    except ValueError:
        await message.answer("❌ ID и сумма должны быть числами")
        return
    try:
        from casino.casino import CasinoDB
        casino_db = CasinoDB()
        casino_db.set_balance(uid, amount)
        await message.answer(f"✅ Баланс {uid} = {amount} монет")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ========== ЛОГИ ==========

@router.message(Command("dev_log"))
async def cmd_dev_log(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    lines_count = 20
    if command.args:
        try:
            lines_count = min(int(command.args.strip()), 200)
        except:
            pass
    try:
        with open("bot_errors.log", "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines_count:]
        text = "".join(tail)
        if len(text) > 4000:
            text = text[-3997:]
        await message.answer(f"<b>📋 Последние {lines_count} строк лога</b>\n<code>{text}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения лога: {e}")


# ========== СТАТИСТИКА БД ==========

@router.message(Command("dev_db"))
async def cmd_dev_db(message: Message):
    if not is_dev(message.from_user.id):
        return
    stats = []
    tables = ["users", "messages", "bans", "reports", "appeals", "osint_logs", "moderation", "dev_permissions"]
    for t in tables:
        db.cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = db.cur.fetchone()[0]
        stats.append(f"┃ {t}: {cnt}")
    size = 0
    try:
        import os
        size = os.path.getsize("chat.db") // 1024
    except:
        pass
    await message.answer(f"<b>🗄 Статистика БД</b>\n" + "\n".join(stats) + f"\n┃ Размер: {size} KB" if size else "\n".join(stats), parse_mode="HTML")


# ========== СБРОС ПОЛЬЗОВАТЕЛЯ ==========

@router.message(Command("dev_resetuser"))
async def cmd_dev_resetuser(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Укажите ID: /dev_resetuser <id>")
        return
    try:
        uid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    if uid == OWNER_ID:
        await message.answer("❌ Нельзя сбросить владельца")
        return
    db.cur.execute("DELETE FROM users WHERE user_id = ?", (uid,))
    db.cur.execute("DELETE FROM messages WHERE sender_id = ? OR receiver_id = ?", (uid, uid))
    db.cur.execute("DELETE FROM bans WHERE user_id = ?", (uid,))
    db.cur.execute("DELETE FROM moderation WHERE user_id = ?", (uid,))
    db.cur.execute("DELETE FROM reports WHERE reporter_id = ? OR reported_id = ?", (uid, uid))
    db.conn.commit()
    await message.answer(f"✅ Данные пользователя {uid} удалены")


# ========== ЭКСПОРТ ==========

@router.message(Command("dev_export"))
async def cmd_dev_export(message: Message, command: CommandObject):
    if not is_dev(message.from_user.id):
        return
    table = "users"
    if command.args:
        t = command.args.strip()
        if t in ("users", "messages", "bans", "reports", "appeals", "osint_logs", "moderation"):
            table = t
    db.cur.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 50")
    rows = db.cur.fetchall()
    if not rows:
        await message.answer(f"❌ Таблица {table} пуста")
        return
    columns = [d[0] for d in db.cur.description]
    lines = [f"<b>📦 {table} (последние 50)</b>\n"]
    for row in rows:
        line_parts = []
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else ""
            if val is None: val = ""
            s = str(val)[:40]
            line_parts.append(f"{col}={s}")
        lines.append(f"┃ {' | '.join(line_parts)}")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await message.answer(text, parse_mode="HTML")


# ========== ВОССТАНОВИТЬ КОМАНДЫ ==========

@router.message(Command("dev_sync_cmds"))
async def cmd_dev_sync_cmds(message: Message):
    if not is_dev(message.from_user.id):
        return
    from main import PUBLIC_COMMANDS, ADMIN_COMMANDS
    bot = message.bot
    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=OWNER_ID))
    await message.answer("✅ Команды синхронизированы")


# ========== ПОМОЩЬ РАЗРАБОТЧИКА ==========
# Удалена — все команды доступны в админ-панели (📋 Команды)
