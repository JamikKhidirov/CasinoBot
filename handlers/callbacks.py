from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.user import active_users, waiting_users
from utils.helpers import is_banned, is_admin, is_dev, can_read_chats
from utils.keyboards import main_kb, chat_kb, search_kb
from config import OWNER_ID

router = Router()


def _show_osint(uid: int) -> bool:
    return is_dev(uid)


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
    sa = is_admin(uid)
    await call.bot.send_message(partner, "❌ Собеседник вышел.", reply_markup=main_kb(show_osint=so, show_admin=sa))
    await call.message.edit_text("👋 Чат завершён.", reply_markup=main_kb(show_osint=so, show_admin=sa))


@router.callback_query(F.data == "cancel_search")
async def cb_cancel_search(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in waiting_users:
        await call.answer("❌ Вы не в поиске.", show_alert=True)
        return
    waiting_users.remove(uid)
    await call.message.edit_text("❌ Поиск отменён.", reply_markup=main_kb(show_osint=_show_osint(uid), show_admin=is_admin(uid)))
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
    await call.message.edit_text(text, reply_markup=main_kb(show_osint=_show_osint(uid), show_admin=is_admin(uid)))
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
    await call.message.edit_text(text, reply_markup=main_kb(show_osint=_show_osint(uid), show_admin=is_admin(uid)))
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
    await call.message.edit_text("👋 Главное меню", reply_markup=main_kb(show_chat=show_chat, show_osint=_show_osint(uid), show_admin=is_admin(uid)))
    await call.answer()


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("❌ Доступ только администраторам.", show_alert=True)
        return
    # Устанавливаем админ-команды для этого чата
    from main import ADMIN_COMMANDS
    from aiogram.types import BotCommandScopeChat
    try:
        bot = call.bot
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=uid))
    except:
        pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats"),
         InlineKeyboardButton(text="🛡 Модерация", callback_data="admin_mod")],
        [InlineKeyboardButton(text="💬 Чат-лог", callback_data="admin_chatlog"),
         InlineKeyboardButton(text="📋 Команды", callback_data="admin_commands")],
        [InlineKeyboardButton(text="🎰 Админ-панель казино", callback_data="casino_admin")],
        [InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")],
    ])
    await call.message.edit_text("<b>🛡 Админ-панель</b>\nВыберите раздел:", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data == "admin_commands")
async def cb_admin_commands(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    is_dev_user = uid == OWNER_ID
    can_chat = can_read_chats(uid)

    parts = ["<b>📋 Все команды</b>\n"]

    # Основные (для всех)
    parts.append("\n<b>🎮 Основные</b>")
    parts.append("/start — главное меню")
    parts.append("/help — справка")

    # Казино (для всех)
    parts.append("\n<b>🎰 Казино</b>")
    parts.append("/profile — профиль игрока")
    parts.append("/bonus — ежедневный бонус")
    parts.append("/top — топ игроков")
    parts.append("/games — список игр")
    parts.append("/dice [ставка] — кости")
    parts.append("/bowling [ставка] — боулинг")
    parts.append("/darts [ставка] — дротики")
    parts.append("/basket [ставка] — баскетбол")
    parts.append("/football [ставка] — футбол")
    parts.append("/active — активные игры")
    parts.append("/unlock — отменить свои игры")

    # OSINT (только для разработчика)
    if is_dev_user:
        parts.append("\n<b>🔍 OSINT-пробив</b>")
        parts.append("/phone [номер] — пробив телефона")
        parts.append("/hackphone [номер] — хакерский скан")
        parts.append("/card [номер] — пробив карты по BIN")
        parts.append("/email [email] — пробив email")
        parts.append("/user [username] — поиск по соцсетям")
        parts.append("/ip [ip] — геолокация IP")
        parts.append("/domain [домен] — инфо по домену")

    # Админ (для всех админов)
    parts.append("\n<b>🛡 Админ-команды</b>")
    parts.append("/stats — статистика бота")
    parts.append("/mod — панель модерации")
    parts.append("/ban [id] — забанить")
    parts.append("/unban [id] — разбанить")
    parts.append("/mute [id] [мин] — замутить")
    parts.append("/unmute [id] — размутить")
    parts.append("/warn [id] — выдать варн")
    parts.append("/check [id] — проверить")
    parts.append("/warns [id] — варны")
    parts.append("/admin — админ-панель казино")
    parts.append("/players — список игроков")

    if can_chat:
        parts.append("\n<b>💬 Чат-лог (доступ по разрешению)</b>")
        parts.append("/chatlog [id] — переписка")
        parts.append("/chatlog [id1] [id2] — диалог")

    if is_dev_user:
        parts.append("\n<b>🔧 Разработчик (только OWNER)</b>")
        parts.append("/dev_addadmin [id] — сделать админом")
        parts.append("/dev_removeadmin [id] — снять админа")
        parts.append("/dev_admins — список админов")
        parts.append("/dev_grantchat [id] — дать доступ к чатам")
        parts.append("/dev_revokechat [id] — отозвать доступ")
        parts.append("/dev_chataccess — кто читает чаты")
        parts.append("/dev_users [N] — топ пользователей")
        parts.append("/dev_userinfo [id] — инфо о пользователе")
        parts.append("/dev_resetuser [id] — удалить пользователя")
        parts.append("/dev_broadcast [текст] — рассылка всем")
        parts.append("/dev_say [chat_id] [текст] — сказать от бота")
        parts.append("/dev_leavechat [chat_id] — выйти из чата")
        parts.append("/dev_setcoins [id] [сумма] — баланс казино")
        parts.append("/dev_db — статистика БД")
        parts.append("/dev_export [таблица] — экспорт")
        parts.append("/dev_log [N] — последние N строк лога")
        parts.append("/dev_sync_cmds — синхр. команды")

    text = "\n".join(parts)
    if len(text) > 4000:
        text = text[:3997] + "..."

    await call.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")]
        ])
    )
    await call.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    import db
    import datetime
    db.cur.execute("SELECT COUNT(*) FROM users")
    total = db.cur.fetchone()[0]
    db.cur.execute("SELECT COUNT(*) FROM bans WHERE ban_until IS NULL OR ban_until > ?",
                   (datetime.datetime.now().isoformat(),))
    banned = db.cur.fetchone()[0]
    db.cur.execute("SELECT COUNT(*) FROM messages")
    msgs = db.cur.fetchone()[0]
    await call.message.edit_text(
        f"<b>📊 Статистика бота</b>\n\n"
        f"👥 Пользователей: {total}\n"
        f"🚫 Забанено: {banned}\n"
        f"💬 Сообщений: {msgs}\n"
        f"🆔 Ваш ID: {uid}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")]
        ])
    )
    await call.answer()


@router.callback_query(F.data == "admin_mod")
async def cb_admin_mod(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    await call.message.edit_text(
        "<b>🛡 Модерация</b>\n"
        "Используйте команды:\n"
        "• <code>/mod</code> — панель модерации\n"
        "• <code>/ban &lt;id&gt;</code> — забанить\n"
        "• <code>/unban &lt;id&gt;</code> — разбанить\n"
        "• <code>/mute &lt;id&gt; &lt;мин&gt;</code> — замутить\n"
        "• <code>/unmute &lt;id&gt;</code> — размутить\n"
        "• <code>/warn &lt;id&gt;</code> — выдать варн\n"
        "• <code>/check &lt;id&gt;</code> — проверить\n"
        "• <code>/warns &lt;id&gt;</code> — варны\n"
        "• <code>/chatlog &lt;id&gt;</code> — переписка",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")]
        ])
    )
    await call.answer()


# ─── Чат-лог (админ-панель) ─────────────────────────────────────

@router.callback_query(F.data == "admin_chatlog")
async def cb_admin_chatlog(call: CallbackQuery):
    uid = call.from_user.id
    if not can_read_chats(uid):
        await call.answer("❌ Доступ только для разработчика или назначенных.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все пользователи с чатами", callback_data="chatlog_users")],
        [InlineKeyboardButton(text="💬 Последние 20 сообщений", callback_data="chatlog_recent")],
        [InlineKeyboardButton(text="🔍 Поиск по ID пользователя", callback_data="chatlog_search")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")],
    ])
    await call.message.edit_text("<b>💬 Чат-лог анонимного чата</b>\nВыберите действие:", parse_mode="HTML", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "chatlog_recent")
async def cb_chatlog_recent(call: CallbackQuery):
    uid = call.from_user.id
    if not can_read_chats(uid):
        return
    import db
    db.cur.execute("SELECT sender_id, receiver_id, message, timestamp FROM messages ORDER BY id DESC LIMIT 20")
    rows = db.cur.fetchall()
    if not rows:
        await call.message.edit_text("❌ Нет сообщений.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_chatlog")]]))
        return
    lines = ["<b>💬 Последние 20 сообщений</b>\n"]
    for row in rows:
        sender, receiver, msg, ts = row
        lines.append(f"┃ <b>{sender}</b> → <b>{receiver}</b>")
        lines.append(f"┃ {str(msg)[:80]}")
        lines.append(f"┃ 🕐 {str(ts)[:19]}")
        lines.append("")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_chatlog")]]))
    await call.answer()


@router.callback_query(F.data == "chatlog_users")
async def cb_chatlog_users(call: CallbackQuery):
    uid = call.from_user.id
    if not can_read_chats(uid):
        return
    import db
    db.cur.execute("""
        SELECT DISTINCT u.user_id, u.username, u.total_messages,
            (SELECT COUNT(*) FROM messages WHERE sender_id = u.user_id OR receiver_id = u.user_id) as msg_count
        FROM users u ORDER BY msg_count DESC LIMIT 30
    """)
    rows = db.cur.fetchall()
    if not rows:
        await call.message.edit_text("❌ Нет пользователей.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_chatlog")]]))
        return
    lines = ["<b>👥 Пользователи с чатами</b>\n"]
    for row in rows:
        uid2, uname, total, msg_count = (row[0], row[1], row[2], row[3]) if len(row) >= 4 else (row[0], row[1], 0, 0)
        name = f"@{uname}" if uname else f"ID{uid2}"
        lines.append(f"┃ {name} — {msg_count} сообщ.")
    if len(lines) > 40:
        lines = lines[:40]
    text = "\n".join(lines)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_chatlog")]]))
    await call.answer()


@router.callback_query(F.data == "chatlog_search")
async def cb_chatlog_search(call: CallbackQuery):
    uid = call.from_user.id
    if not can_read_chats(uid):
        return
    await call.message.edit_text(
        "🔍 <b>Поиск чата пользователя</b>\n\n"
        "Отправьте ID пользователя:\n"
        "<code>/chatlog 123456789</code> — все сообщения пользователя\n"
        "<code>/chatlog 123456789 987654321</code> — переписка двух\n\n"
        "Или нажмите на пользователя ниже:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_chatlog")]
        ])
    )
    await call.answer()


@router.callback_query(F.data.startswith("chatlog_user_"))
async def cb_chatlog_user(call: CallbackQuery):
    uid = call.from_user.id
    if not can_read_chats(uid):
        return
    target_id = int(call.data.split("_")[2])
    import db
    db.cur.execute("SELECT sender_id, message, timestamp FROM messages WHERE sender_id = ? OR receiver_id = ? ORDER BY id DESC LIMIT 30", (target_id, target_id))
    rows = db.cur.fetchall()
    if not rows:
        await call.answer("❌ Нет сообщений у этого пользователя.", show_alert=True)
        return
    lines = [f"<b>💬 Чат пользователя {target_id}</b>\n"]
    for row in rows:
        sender = row[0]
        msg = str(row[1])[:100]
        ts = str(row[2])[:19] if row[2] else ""
        arrow = "➡️" if sender == target_id else "⬅️"
        lines.append(f"┃ {arrow} [{ts}] {msg}")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="chatlog_users")]]))
    await call.answer()


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    uid = call.from_user.id
    show_osint = _show_osint(uid)
    is_adm = is_admin(uid)
    parts = ["<b>👋 Команды бота</b>\n"]
    if show_osint:
        parts.append(
            "<b>🔍 OSINT-пробив (только разработчик)</b>\n"
            "┃ <code>/phone</code> — пробив телефона\n"
            "┃ <code>/hackphone</code> — хакерский скан номера\n"
            "┃ <code>/card</code> — пробив банковской карты\n"
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
        "┃ <code>/profile</code> — профиль игрока\n"
        "┃ <code>/games</code> — игры\n"
        "┃ <code>/dice [ставка]</code> — кости\n"
        "┃ <code>/bowling [ставка]</code> — боулинг\n"
        "┃ <code>/darts [ставка]</code> — дротики\n"
        "┃ <code>/basket [ставка]</code> — баскетбол\n"
        "┃ <code>/football [ставка]</code> — футбол\n"
    )
    if is_adm:
        parts.append(
            "<b>🛡 Админ-команды</b>\n"
            "┃ <code>/stats</code> — статистика бота\n"
            "┃ <code>/mod</code> — панель модерации\n"
            "┃ <code>/ban</code> — забанить\n"
            "┃ <code>/unban</code> — разбанить\n"
            "┃ <code>/mute</code> — замутить\n"
            "┃ <code>/unmute</code> — размутить\n"
            "┃ <code>/warn</code> — выдать варн\n"
            "┃ <code>/check</code> — проверить пользователя\n"
            "┃ <code>/warns</code> — варны пользователя\n"
            "┃ <code>/chatlog</code> — переписка\n"
            "┃ <code>/admin</code> — админ-панель казино\n"
            "┃ <code>/players</code> — список игроков казино\n"
        )
    parts.append(
        "<b>⚙️ Прочее</b>\n"
        "┃ <code>/start</code> — главное меню\n"
        "┃ <code>/help</code> — эта справка"
    )
    if show_osint:
        parts.append("💡 <code>/phone +79123456789</code> — Быстрый пробив")
    text = "\n".join(parts)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=main_kb(show_osint=show_osint, show_admin=is_adm))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=main_kb(show_osint=show_osint, show_admin=is_adm))
    await call.answer()
