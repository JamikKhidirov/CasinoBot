from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.keyboards import main_kb
from utils.helpers import is_banned, save_message
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
    await message.answer(
        "👋 Добро пожаловать!\n🔍 OSINT-пробив — поиск информации" + ("\n🎲 Анонимный чат — общение" if show_chat else ""),
        reply_markup=main_kb(show_chat=show_chat)
    )


async def handle_chat_text(message: Message):
    uid = message.from_user.id
    if uid not in active_users:
        await message.answer("👋 Нажмите /start для начала.")
        return
    if is_banned(uid):
        await message.answer("⚠️ Вы забанены.")
        return
    partner = active_users[uid]
    text = message.text
    save_message(uid, partner, text)
    await message.bot.send_message(partner, f"👤: {text}")
