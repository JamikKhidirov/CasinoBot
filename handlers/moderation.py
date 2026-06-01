from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import (
    is_admin, is_banned, is_muted, get_warns, add_warn,
    ban_user, unban_user, mute_user, unmute_user, can_moderate, get_username_safe,
    get_user_display, can_read_chats, resolve_user, is_dev,
    has_osint_access, grant_osint_access, revoke_osint_access, list_osint_users,
)
from handlers.user import active_users, waiting_users
import db
import datetime

router = Router()


def mod_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="mod_ban"),
         InlineKeyboardButton(text="✅ Разбанить", callback_data="mod_unban")],
        [InlineKeyboardButton(text="🔇 Замутить", callback_data="mod_mute"),
         InlineKeyboardButton(text="🔊 Размутить", callback_data="mod_unmute")],
        [InlineKeyboardButton(text="⚠️ Варн", callback_data="mod_warn"),
         InlineKeyboardButton(text="📊 Проверить", callback_data="mod_check")],
        [InlineKeyboardButton(text="💬 Чат-админка", callback_data="mod_chats"),
         InlineKeyboardButton(text="🔑 OSINT доступ", callback_data="mod_osint")],
        [InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")],
    ])


@router.message(Command("mod"))
async def cmd_mod(message: Message):
    uid = message.from_user.id
    if not is_admin(uid):
        await message.answer("❌ Доступ только для администраторов.")
        return
    await message.answer(
        "<b>🛠 Панель модерации</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=mod_kb(),
    )


@router.callback_query(F.data.startswith("mod_"))
async def cb_mod(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return

    action = call.data.split("_", 1)[1]
    back_btn = [[InlineKeyboardButton(text="◀️ Назад", callback_data="back_mod")]]

    help_texts = {
        "ban": ("🚫 <b>Бан пользователя</b>\n\nФормат: <code>/ban user_id [причина]</code>\nПример: <code>/ban 123456789 Спам</code>",),
        "unban": ("✅ <b>Разбан пользователя</b>\n\nФормат: <code>/unban user_id</code>\nПример: <code>/unban 123456789</code>",),
        "mute": ("🔇 <b>Мут пользователя</b>\n\nФормат: <code>/mute user_id минуты</code>\nПример: <code>/mute 123456789 30</code>",),
        "unmute": ("🔊 <b>Размут пользователя</b>\n\nФормат: <code>/unmute user_id</code>\nПример: <code>/unmute 123456789</code>",),
        "warn": ("⚠️ <b>Варн пользователя</b>\n\n3/3 варнов → автоматический бан.\nФормат: <code>/warn user_id [причина]</code>",),
        "check": ("📊 <b>Проверка пользователя</b>\n\nФормат: <code>/check user_id</code>\nПример: <code>/check 123456789</code>",),
    }

    if action == "chats":
        await _show_chat_admin(call.message)
    elif action == "osint":
        users = list_osint_users()
        lines = ["<b>🔑 Управление OSINT доступом</b>\n\n"]
        if users:
            lines.append("┃ <b>Есть доступ:</b>")
            for u in users:
                name = u["nickname"] or u["username"] or "unknown"
                lines.append(f"┃ • {name} | <code>{u['user_id']}</code>")
        else:
            lines.append("┃ Нет пользователей с доступом.")
        lines.append("\n┃ <b>Команды:</b>")
        lines.append("┃ /grant_osint &lt;id&gt; — выдать доступ")
        lines.append("┃ /revoke_osint &lt;id&gt; — отозвать доступ")
        lines.append("┃ /osint_users — список")
        await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_mod")]
        ]))
    elif action in help_texts:
        await call.message.edit_text(help_texts[action][0], parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=back_btn))
    else:
        await call.answer("❌ Неизвестное действие.", show_alert=True)

    await call.answer()


@router.callback_query(F.data == "back_mod")
async def cb_back_mod(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return
    await call.message.edit_text(
        "<b>🛠 Панель модерации</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=mod_kb(),
    )
    await call.answer()


# ─── Chat admin panel ────────────────────────────────────────────────


async def _show_chat_admin(msg: Message):
    uid = msg.chat.id
    active = len(active_users) // 2
    waiting = len(waiting_users)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Активные чаты", callback_data="chatadmin_active"),
         InlineKeyboardButton(text="📋 Переписки", callback_data="chatadmin_logs")],
        [InlineKeyboardButton(text="📊 Статистика чатов", callback_data="chatadmin_stats"),
         InlineKeyboardButton(text="🔄 Очистить поиск", callback_data="chatadmin_clearwaiting")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_mod")],
    ])
    text = (
        "<b>💬 Чат-админка</b>\n\n"
        f"┃ 👥 Активных чатов: <b>{active}</b>\n"
        f"┃ 🔍 В поиске: <b>{waiting}</b>\n\n"
        "Выберите действие:"
    )
    await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("chatadmin_"))
async def cb_chat_admin(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return

    action = call.data.split("_", 1)[1]

    if action == "active":
        await _show_active_chats(call.message)
    elif action == "logs":
        await _show_chat_logs(call.message)
    elif action == "stats":
        await _show_chat_stats(call.message)
    elif action == "clearwaiting":
        waiting_users.clear()
        await call.message.edit_text("✅ Очередь поиска очищена.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")]
        ]))

    await call.answer()


async def _show_active_chats(msg: Message):
    pairs = {}
    seen = set()
    for u1, u2 in list(active_users.items()):
        if u1 not in seen and u2 not in seen:
            if u1 not in pairs and u2 not in pairs:
                pairs[u1] = u2
                seen.add(u1)
                seen.add(u2)
            elif u2 in pairs:
                if u1 not in pairs:
                    pairs[u2] = u1
                    seen.add(u2)
                    seen.add(u1)

    if not pairs:
        await msg.edit_text("❌ Нет активных чатов.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")]
        ]))
        return

    text = "<b>👥 Активные чаты:</b>\n\n"
    buttons = []
    for u1, u2 in list(pairs.items())[:15]:
        n1 = get_username_safe(u1)
        n2 = get_username_safe(u2)
        text += f"┃ {get_user_display(u1)}\n┃ ↔ {get_user_display(u2)}\n\n"
        buttons.append([InlineKeyboardButton(text=f"💬 {n1[:12]} ↔ {n2[:12]}", callback_data=f"chatread_{u1}_{u2}")])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")])
    await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def _show_chat_logs(msg: Message):
    try:
        db.cur.execute(
            "SELECT sender_id, receiver_id, COUNT(*) as cnt, MAX(timestamp) as last "
            "FROM messages GROUP BY sender_id, receiver_id ORDER BY last DESC LIMIT 20"
        )
        rows = db.cur.fetchall()
    except:
        rows = []

    if not rows:
        await msg.edit_text("❌ Нет сохранённых переписок.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")]
        ]))
        return

    text = "<b>📋 Последние переписки:</b>\n\n"
    buttons = []
    for i, row in enumerate(rows[:10], 1):
        text += f"┃ {i}. {get_user_display(row[0])}\n┃ ↔ {get_user_display(row[2])} | {row[3]} сообщ.\n\n"
        n1 = get_username_safe(row[0])
        n2 = get_username_safe(row[2])
        buttons.append([InlineKeyboardButton(text=f"📖 #{i}  {n1[:8]}↔{n2[:8]}", callback_data=f"chatread_{row[0]}_{row[2]}")])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")])
    await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def _show_chat_stats(msg: Message):
    try:
        db.cur.execute("SELECT COUNT(*) FROM messages")
        total_msgs = db.cur.fetchone()[0]
        db.cur.execute("SELECT COUNT(DISTINCT sender_id) FROM messages")
        total_users = db.cur.fetchone()[0]
        db.cur.execute("SELECT COUNT(*) FROM reports")
        total_reports = db.cur.fetchone()[0]
        db.cur.execute("SELECT COUNT(*) FROM users")
        registered = db.cur.fetchone()[0]
    except:
        total_msgs = total_users = total_reports = registered = 0

    text = (
        "<b>📊 Статистика чатов</b>\n\n"
        f"┃ 📝 Всего сообщений: <b>{total_msgs}</b>\n"
        f"┃ 👥 Писало в чат: <b>{total_users}</b>\n"
        f"┃ 📋 Зарегистрировано: <b>{registered}</b>\n"
        f"┃ ⚠️ Жалоб: <b>{total_reports}</b>\n"
        f"┃ 🎮 Активных чатов: <b>{len(active_users) // 2}</b>\n"
        f"┃ 🔍 В поиске: <b>{len(waiting_users)}</b>"
    )
    await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")]
    ]))


@router.callback_query(F.data.startswith("chatread_"))
async def cb_chat_read(call: CallbackQuery):
    uid = call.from_user.id
    if not is_admin(uid):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return

    parts = call.data.split("_", 2)
    if len(parts) < 3:
        await call.answer("❌ Ошибка.", show_alert=True)
        return
    try:
        u1 = int(parts[1])
        u2 = int(parts[2])
    except ValueError:
        await call.answer("❌ Ошибка ID.", show_alert=True)
        return

    try:
        db.cur.execute(
            "SELECT sender_id, message, timestamp FROM messages "
            "WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) "
            "ORDER BY timestamp ASC LIMIT 30",
            (u1, u2, u2, u1),
        )
        rows = db.cur.fetchall()
    except:
        rows = []

    if not rows:
        await call.answer("❌ Переписка пуста.", show_alert=True)
        return

    lines = [f"<b>💬 Переписка</b>\n┃ {get_user_display(u1)}\n┃ ↔ {get_user_display(u2)}\n"]
    for row in rows:
        sender = "➡️" if row[0] == u1 else "⬅️"
        ts = row[2][:19] if row[2] else ""
        txt = row[1][:150] if row[1] else ""
        lines.append(f"┃ {sender} [{ts}] {txt}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"chatread_{u1}_{u2}"),
         InlineKeyboardButton(text="◀️ Назад", callback_data="mod_chats")]
    ]))


# ─── Moderation commands ──────────────────────────────────────────────


def _check_access(message: Message) -> bool:
    if not is_admin(message.from_user.id):
        return False
    return True


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/ban user_id [причина]</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Вы не можете забанить этого пользователя.")
        return
    reason = parts[2] if len(parts) > 2 else "Нарушение правил"
    ban_user(target_id, message.from_user.id, reason)
    if target_id in active_users:
        partner = active_users.pop(target_id)
        active_users.pop(partner, None)
    if target_id in waiting_users:
        waiting_users.remove(target_id)
    await message.answer(f"✅ Забанен: {get_user_display(target_id)}\nПричина: {reason}", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/unban user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Вы не можете разбанить этого пользователя.")
        return
    unban_user(target_id)
    await message.answer(f"✅ Разбанен: {get_user_display(target_id)}", parse_mode="HTML")


@router.message(Command("mute"))
async def cmd_mute(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Формат: <code>/mute user_id минуты</code>\nПример: <code>/mute 123456789 30</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    try:
        minutes = int(parts[2])
    except ValueError:
        await message.answer("❌ Некорректное время.")
        return
    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Вы не можете замутить этого пользователя.")
        return
    mute_user(target_id, message.from_user.id, minutes)
    await message.answer(f"✅ Замучен: {get_user_display(target_id)}\n⏱ На {minutes} мин.", parse_mode="HTML")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/unmute user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Вы не можете размутить этого пользователя.")
        return
    unmute_user(target_id)
    await message.answer(f"✅ Размучен: {get_user_display(target_id)}", parse_mode="HTML")


@router.message(Command("warn"))
async def cmd_warn(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/warn user_id [причина]</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Вы не можете варнуть этого пользователя.")
        return
    reason = parts[2] if len(parts) > 2 else ""
    warns = add_warn(target_id, message.from_user.id)
    text = f"⚠️ Варн: {get_user_display(target_id)} ({warns}/3)"
    if reason:
        text += f"\nПричина: {reason}"
    if warns >= 3:
        text += "\n\n🚫 3/3 варнов — пользователь автоматически забанен!"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("check"))
async def cmd_check(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/check user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    name = get_username_safe(target_id)
    banned = "🚫 Да" if is_banned(target_id) else "✅ Нет"
    muted = is_muted(target_id)
    mute_status = f"🔇 Да (до {muted})" if muted else "🔊 Нет"
    warns = get_warns(target_id)
    in_chat = "💬 Да" if target_id in active_users else "💤 Нет"
    in_search = "🔍 Да" if target_id in waiting_users else "—"
    try:
        db.cur.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ? OR receiver_id = ?", (target_id, target_id))
        msg_count = db.cur.fetchone()[0]
    except:
        msg_count = 0
    text = (
        f"<b>📊 Информация о пользователе</b>\n\n"
        f"┃ {get_user_display(target_id)}\n"
        f"┃ 🚫 Забанен: {banned}\n"
        f"┃ {mute_status}\n"
        f"┃ ⚠️ Варны: {warns}/3\n"
        f"┃ {in_chat}\n"
        f"┃ {in_search}\n"
        f"┃ 📝 Сообщений: {msg_count}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("chatlog"))
async def cmd_chatlog(message: Message):
    uid = message.from_user.id
    if not can_read_chats(uid):
        await message.answer("❌ Доступ только для разработчика или назначенных.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/chatlog user_id</code>\nИли: <code>/chatlog user1 user2</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    target_id2 = None
    if len(parts) > 2:
        target_id2 = await resolve_user(parts[2])
        if target_id2 is None:
            await message.answer("❌ Второй пользователь не найден. Укажите ID или @username.")
            return

    if target_id2:
        query = "SELECT sender_id, message, timestamp FROM messages WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)) ORDER BY timestamp ASC LIMIT 50"
        params = (target_id, target_id2, target_id2, target_id)
    else:
        query = "SELECT sender_id, message, timestamp FROM messages WHERE sender_id = ? OR receiver_id = ? ORDER BY timestamp DESC LIMIT 50"
        params = (target_id, target_id)

    try:
        db.cur.execute(query, params)
        rows = db.cur.fetchall()
    except:
        rows = []

    if not rows:
        await message.answer("❌ Сообщения не найдены.")
        return

    lines = [f"<b>💬 История чатов</b>\n┃ {get_user_display(target_id)}\n"]
    for row in reversed(rows):
        sender = "➡️" if row[0] == target_id else "⬅️"
        ts = row[2][:19] if row[2] else ""
        txt = row[1][:100] if row[1] else ""
        lines.append(f"┃ {sender} [{ts}] {txt}")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await message.answer(text, parse_mode="HTML")


@router.message(Command("warns"))
async def cmd_warns(message: Message):
    if not _check_access(message):
        await message.answer("❌ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/warns user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите ID или @username.")
        return
    warns = get_warns(target_id)
    await message.answer(f"⚠️ Варны: {get_user_display(target_id)}: {warns}/3", parse_mode="HTML")


# ─── OSINT access management ─────────────────────────────────────────


@router.message(Command("grant_osint"))
async def cmd_grant_osint(message: Message):
    if not is_dev(message.from_user.id):
        await message.answer("❌ Только разработчик.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/grant_osint user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден.")
        return
    grant_osint_access(target_id)
    await message.answer(f"✅ OSINT доступ выдан: {get_user_display(target_id)}", parse_mode="HTML")
    # Уведомляем пользователя о выдаче доступа
    try:
        await message.bot.send_message(
            target_id,
            "🔍 <b>Вам выдан доступ к OSINT-пробиву!</b>\n\n"
            "┃ Вы можете использовать команды:\n"
            "┃ <code>/phone</code> <code>/email</code> <code>/user</code>\n"
            "┃ <code>/ip</code> <code>/domain</code> <code>/tg</code> и другие\n\n"
            "┃ ⚠️ <b>Правила использования:</b>\n"
            "┃ • Пробив других пользователей только с разрешения разработчика\n"
            "┃ • Попытка пробить разработчика (@<code>{OWNER_ID}</code>) запрещена\n"
            "┃ • Все действия логируются\n\n"
            "┃ Для начала используйте /start → OSINT-пробив",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("revoke_osint"))
async def cmd_revoke_osint(message: Message):
    if not is_dev(message.from_user.id):
        await message.answer("❌ Только разработчик.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>/revoke_osint user_id</code>", parse_mode="HTML")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.answer("❌ Пользователь не найден.")
        return
    revoke_osint_access(target_id)
    await message.answer(f"❌ OSINT доступ отозван: {get_user_display(target_id)}", parse_mode="HTML")


@router.message(Command("osint_users"))
async def cmd_osint_users(message: Message):
    if not is_dev(message.from_user.id):
        await message.answer("❌ Только разработчик.")
        return
    users = list_osint_users()
    if not users:
        await message.answer("📋 Нет пользователей с OSINT доступом.")
        return
    lines = ["<b>📋 Пользователи с OSINT доступом:</b>\n"]
    for u in users:
        name = u["nickname"] or u["username"] or "unknown"
        lines.append(f"┃ {name} | <code>{u['user_id']}</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Telethon аккаунты (собранные данные после /setup_tg) ───

@router.message(Command("tgaccounts"))
async def cmd_tgaccounts(message: Message):
    """Показывает все аккаунты Telegram, вошедшие через бота."""
    if not is_dev(message.from_user.id):
        await message.answer("❌ Только разработчик.")
        return
    cur = db.cur
    if cur is None:
        await message.answer("❌ База данных не инициализирована.")
        return
    cur.execute("SELECT * FROM telethon_accounts ORDER BY collected_at DESC")
    rows = cur.fetchall()
    if not rows:
        await message.answer("📋 Нет сохранённых Telethon аккаунтов.")
        return
    lines = [f"<b>📋 Telethon аккаунты ({len(rows)}):</b>\n"]
    for r in rows:
        lines.append(
            f"┃ 👤 <b>@{r['tg_username']}</b> ({r['tg_first_name']} {r['tg_last_name']})\n"
            f"┃ 🆔 TG: <code>{r['tg_user_id']}</code> | Бот: <code>{r['bot_user_id']}</code>\n"
            f"┃ 📱 {r['tg_phone']} | 💬 {r['dialogs_count']} диалогов\n"
            f"┃ 🕐 {r['collected_at'][:19]}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="📋 Диалоги аккаунтов", callback_data="tgaccounts_dialogs")]
                         ]))


@router.callback_query(F.data == "tgaccounts_dialogs")
async def cb_tgaccounts_dialogs(call: CallbackQuery):
    """Показывает все диалоги из Telethon аккаунтов."""
    if not is_dev(call.from_user.id):
        await call.answer("❌ Только разработчик.", show_alert=True)
        return
    cur = db.cur
    if cur is None:
        await call.answer("❌ База данных недоступна.", show_alert=True)
        return
    # Сначала показываем список пользователей
    cur.execute("SELECT bot_user_id, tg_username, tg_first_name FROM telethon_accounts ORDER BY collected_at DESC")
    accounts = cur.fetchall()
    if not accounts:
        await call.answer("❌ Нет аккаунтов.", show_alert=True)
        return
    buttons = []
    for a in accounts:
        name = f"@{a['tg_username']}" if a['tg_username'] else a['tg_first_name']
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"tgadialog_{a['bot_user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    await call.message.edit_text(
        "<b>📋 Выберите аккаунт для просмотра диалогов:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("tgadialog_"))
async def cb_tgaccount_dialog_detail(call: CallbackQuery):
    """Показывает диалоги конкретного пользователя."""
    if not is_dev(call.from_user.id):
        await call.answer("❌ Только разработчик.", show_alert=True)
        return
    bot_uid = int(call.data.split("_", 1)[1])
    cur = db.cur
    cur.execute("SELECT tg_username, tg_first_name, tg_phone FROM telethon_accounts WHERE bot_user_id = ?", (bot_uid,))
    acc = cur.fetchone()
    cur.execute("SELECT * FROM telethon_dialogs WHERE bot_user_id = ? ORDER BY participants DESC LIMIT 50", (bot_uid,))
    dialogs = cur.fetchall()
    if not dialogs:
        await call.answer("❌ Нет диалогов.", show_alert=True)
        return
    name = f"@{acc['tg_username']}" if acc and acc['tg_username'] else (acc['tg_first_name'] if acc else str(bot_uid))
    lines = [f"<b>📋 Диалоги {name}</b>  ({len(dialogs)})\n"]
    for d in dialogs:
        title = d['title'] or "?"
        uname = d['username'] or ""
        typ = d['type']
        icon = {"user": "👤", "group": "💬", "channel": "📢"}.get(typ, "❓")
        parts = d['participants'] or 0
        line = f"┃ {icon} {title}"
        if uname:
            line += f" @{uname}"
        if parts:
            line += f" 👥{parts}"
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await call.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="tgaccounts_dialogs")]
        ]),
    )
