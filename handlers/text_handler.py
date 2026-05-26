from aiogram import Router, F
from aiogram.types import Message
from handlers.osint_handlers import osint_waiting, osint_text_handler
from handlers.user import active_users, handle_chat_text

router = Router()


@router.message(F.text)
async def text_dispatcher(message: Message):
    # Пропускаем команды — они обрабатываются своими хендлерами
    if message.text.startswith("/"):
        return

    uid = message.from_user.id

    if uid in osint_waiting:
        await osint_text_handler(message)
        return

    if uid in active_users:
        await handle_chat_text(message)
        return

    await message.answer("👋 Нажмите /start для начала.")
