from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.keyboards import main_kb
from utils.helpers import is_banned, save_message, is_admin, update_user_activity
from config import OWNER_ID
import db
import datetime

router = Router()

active_users: dict[int, int] = {}
waiting_users: list[int] = []


@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username or "unknown"
    db.cur.execute("INSERT OR IGNORE INTO users (user_id, username, joined_at, last_active) VALUES (?,?,?,?)",
                   (uid, uname, datetime.datetime.now().isoformat(), datetime.datetime.now().isoformat()))
    db.conn.commit()
    update_user_activity(uid, username=uname)
    if is_banned(uid):
        await message.answer("⚠️ Вы забанены.")
        return
    if uid in active_users:
        await message.answer("✅ Вы уже в чате.")
        return
    if uid in waiting_users:
        await message.answer("🔍 Вы в поиске собеседника.")
        return
    show_chat = message.chat.type == "private"
    show_admin = is_admin(uid)
    await message.answer(
        "👋 Добро пожаловать!",
        reply_markup=main_kb(show_chat=show_chat, show_admin=show_admin)
    )


async def handle_chat_text(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username
    update_user_activity(uid, username=uname)
    if uid not in active_users:
        await message.answer("👋 Нажмите /start для начала.")
        return
    if is_banned(uid):
        await message.answer("⚠️ Вы забанены.")
        return
    partner = active_users[uid]
    text = message.text
    save_message(uid, partner, text)
    try:
        await message.bot.send_message(partner, f"👤: {text}")
    except Exception:
        active_users.pop(uid, None)
        active_users.pop(partner, None)
        await message.answer("❌ Собеседник недоступен. Поиск нового...")
