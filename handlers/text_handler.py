from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from handlers.osint_handlers import osint_waiting, osint_text_handler
from handlers.user import active_users, handle_chat_text
from utils.helpers import is_banned, is_muted

router = Router()


@router.message(F.text)
async def text_dispatcher(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return

    uid = message.from_user.id

    if message.chat.type != "private":
        return

    current_state = await state.get_state()
    if current_state is not None:
        return

    if uid in osint_waiting:
        await osint_text_handler(message)
        return

    if uid in active_users:
        if is_banned(uid):
            await message.answer("🚫 Вы забанены и не можете отправлять сообщения.")
            return
        if is_muted(uid):
            await message.answer("🔇 Вы замучены. Подождите окончания наказания.")
            return
        await handle_chat_text(message)
        return

    await message.answer("👋 Нажмите /start для начала.")
