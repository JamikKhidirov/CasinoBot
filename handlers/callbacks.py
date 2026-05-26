from aiogram import Router, F
from aiogram.types import CallbackQuery
from handlers.user import active_users, waiting_users
from utils.helpers import is_banned
from utils.keyboards import main_kb, chat_kb, search_kb
from config import OWNER_ID

router = Router()


def _show_osint(uid: int) -> bool:
    return uid == OWNER_ID


@router.callback_query(F.data == "start_chat")
async def cb_start_chat(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("❌ Анонимный чат доступен только в личных сообщениях.", show_alert=True)
        return
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
        await call.message.edit_text("🔍 Ищем собеседника…", reply_markup=search_kb())


@router.callback_query(F.data == "leave_chat")
async def cb_leave_chat(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in active_users:
        await call.answer("❌ Не в чате.", show_alert=True)
        return
    partner = active_users.pop(uid)
    active_users.pop(partner, None)
    so = _show_osint(uid)
    await call.bot.send_message(partner, "❌ Собеседник вышел.", reply_markup=main_kb(show_osint=so))
    await call.message.edit_text("👋 Чат завершён.", reply_markup=main_kb(show_osint=so))


@router.callback_query(F.data == "cancel_search")
async def cb_cancel_search(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in waiting_users:
        await call.answer("❌ Вы не в поиске.", show_alert=True)
        return
    waiting_users.remove(uid)
    await call.message.edit_text("❌ Поиск отменён.", reply_markup=main_kb(show_osint=_show_osint(uid)))
    await call.answer()


@router.callback_query(F.data == "myprofile")
async def cb_my_profile(call: CallbackQuery):
    uid = call.from_user.id
    import db
    db.cur.execute("SELECT username, joined_at, last_active FROM users WHERE user_id = ?", (uid,))
    row = db.cur.fetchone()
    if row:
        text = (
            f"👤 Профиль\n\n"
            f"🆔 ID: {uid}\n"
            f"👤 Username: @{row[0] or 'не указан'}\n"
            f"📅 Регистрация: {row[1] or 'неизвестно'}\n"
            f"⏱ Последняя активность: {row[2] or 'неизвестно'}"
        )
    else:
        text = f"👤 Профиль\n\n🆔 ID: {uid}\n📝 Зарегистрируйтесь через /start"
    await call.message.edit_text(text, reply_markup=main_kb(show_osint=_show_osint(uid)))
    await call.answer()


@router.callback_query(F.data == "mystats")
async def cb_my_stats(call: CallbackQuery):
    uid = call.from_user.id
    import db
    db.cur.execute("SELECT COUNT(*) FROM osint_logs WHERE user_id = ?", (uid,))
    osint_count = db.cur.fetchone()[0]
    from handlers.user import active_users
    in_chat = "✅ Да" if uid in active_users else "❌ Нет"
    text = (
        f"📊 Статистика\n\n"
        f"🆔 ID: {uid}\n"
        f"🔍 OSINT-запросов: {osint_count}\n"
        f"💬 В чате: {in_chat}\n"
        f"🎰 Казино: используйте /казино"
    )
    await call.message.edit_text(text, reply_markup=main_kb(show_osint=_show_osint(uid)))
    await call.answer()


@router.callback_query(F.data == "report_chat")
async def cb_report_chat(call: CallbackQuery):
    uid = call.from_user.id
    from handlers.user import active_users
    if uid not in active_users:
        await call.answer("❌ Вы не в чате.", show_alert=True)
        return
    partner = active_users[uid]
    await call.bot.send_message(
        partner,
        "⚠️ Ваш собеседник пожаловался на вас.\n"
        "Пожалуйста, соблюдайте правила общения."
    )
    await call.answer("✅ Жалоба отправлена собеседнику.", show_alert=True)


@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery):
    uid = call.from_user.id
    show_chat = call.message.chat.type == "private"
    await call.message.edit_text("👋 Главное меню", reply_markup=main_kb(show_chat=show_chat, show_osint=_show_osint(uid)))
    await call.answer()


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    uid = call.from_user.id
    show_osint = _show_osint(uid)
    parts = ["<b>👋 Команды бота</b>\n"]
    if show_osint:
        parts.append(
            "<b>🔍 OSINT-пробив</b>\n"
            "┃ <code>/phone</code> — пробив телефона\n"
            "┃ <code>/email</code> — пробив email\n"
            "┃ <code>/user</code> — поиск по соцсетям\n"
            "┃ <code>/ip</code> — геолокация IP\n"
            "┃ <code>/domain</code> — инфо по домену\n"
        )
    parts.append(
        "<b>🎲 Анонимный чат</b>\n"
        "┃ Кнопка «Анонимный чат» — поиск собеседника\n"
        "┃ «Завершить чат» — выход\n\n"
        "<b>🎰 Казино</b>\n"
        "┃ Кнопка «Казино» — меню\n"
        "┃ <code>/куб [ставка]</code> — кости\n\n"
        "<b>⚙️ Прочее</b>\n"
        "┃ <code>/start</code> — главное меню\n"
        "┃ <code>/help</code> — эта справка\n"
        "┃ <code>/stats</code> — статистика (админ)\n\n"
        "💡 <code>/phone +79123456789</code> — без лишних вопросов"
    )
    text = "\n".join(parts)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=main_kb(show_osint=show_osint))
    await call.answer()
