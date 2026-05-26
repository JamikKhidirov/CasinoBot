from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.helpers import is_admin
import db
import datetime

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    db.cur.execute("SELECT COUNT(*) FROM users")
    total = db.cur.fetchone()[0]
    db.cur.execute("SELECT COUNT(*) FROM bans WHERE ban_until IS NULL OR ban_until > ?",
                   (datetime.datetime.now().isoformat(),))
    banned = db.cur.fetchone()[0]
    await message.answer(f"📊 Пользователей: {total}\n🚫 Забанено: {banned}")
