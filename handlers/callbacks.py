from aiogram import Router, F
from aiogram.types import CallbackQuery
from handlers.user import active_users, waiting_users
from utils.helpers import is_banned
from utils.keyboards import main_kb, chat_kb

router = Router()


@router.callback_query(F.data == "start_chat")
async def cb_start_chat(call: CallbackQuery):
    uid = call.from_user.id
    if is_banned(uid):
        await call.answer("⚠️ Вы забанены.", show_alert=True)
        return
    if uid in active_users:
        await call.answer("✅ Уже в чате.", show_alert=True)
        return
    if uid in waiting_users:
        await call.answer("🔍 Уже ищете.", show_alert=True)
        return

    if waiting_users and waiting_users[0] != uid:
        partner_id = waiting_users.pop(0)
        if is_banned(partner_id):
            waiting_users.append(uid)
            await call.message.edit_text("🔍 Ищем собеседника…")
            return

        active_users[uid] = partner_id
        active_users[partner_id] = uid

        await call.message.edit_text("✅ Собеседник найден! Напишите что-нибудь.", reply_markup=chat_kb())
        await call.bot.send_message(partner_id, "✅ Собеседник найден! Напишите что-нибудь.", reply_markup=chat_kb())
    else:
        if uid not in waiting_users:
            waiting_users.append(uid)
        await call.message.edit_text("🔍 Ищем собеседника…")


@router.callback_query(F.data == "leave_chat")
async def cb_leave_chat(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in active_users:
        await call.answer("❌ Не в чате.", show_alert=True)
        return
    partner = active_users.pop(uid)
    active_users.pop(partner, None)
    await call.bot.send_message(partner, "❌ Собеседник вышел.", reply_markup=main_kb())
    await call.message.edit_text("👋 Чат завершён.", reply_markup=main_kb())
