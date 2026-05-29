from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, get_username,
    is_casino_admin, has_perm, get_admin_perms, ADMIN_ID, PERMISSIONS, logger,
)
from .keyboards import casino_admin_kb
from utils.helpers import resolve_user, ban_user, unban_user, mute_user, unmute_user, add_warn, get_warns, is_banned, is_muted, can_moderate


class AdminModState(StatesGroup):
    waiting_target = State()

router = Router()

ADMIN_ERROR = "❌ Доступ запрещён!"


@router.callback_query(F.data == "casino_admin")
async def cb_casino_admin(call: CallbackQuery):
    uid = call.from_user.id
    if not await is_casino_admin(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    perms = await get_admin_perms(uid)
    await call.message.edit_text(
        "<b>⚙️ Админ-панель казино</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=casino_admin_kb(perms),
    )
    await call.answer()


@router.callback_query(F.data == "casino_admin_players")
async def cb_casino_admin_players(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "view_players"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT user_id, username, balance FROM users ORDER BY user_id")
        players = await cursor.fetchall()
    finally:
        await conn.close()

    if not players:
        await call.message.edit_text("👥 Игроки не найдены.")
        await call.answer()
        return

    lines = ["<b>👥 Список игроков:</b>\n"]
    for p in players[:20]:
        name = f"@{p['username']}" if p["username"] else f"ID {p['user_id']}"
        lines.append(f"┣ {name}\n┃ 🆔 <code>{p['user_id']}</code> | 💰 {p['balance']} 🪙")
    if len(players) > 20:
        lines.append(f"\n┃ <i>...и ещё {len(players) - 20} игроков</i>")
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")]
        ])
    )
    await call.answer()


@router.callback_query(F.data == "casino_admin_stats")
async def cb_casino_admin_stats(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "view_stats"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM users")
        total_users = (await cursor.fetchone())["cnt"]
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM users WHERE games_played > 0")
        active_players = (await cursor.fetchone())["cnt"]
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM deposit_requests WHERE status = 'pending'"
        )
        pending = (await cursor.fetchone())["cnt"]
        cursor = await conn.execute("SELECT SUM(balance) as total FROM users")
        row = await cursor.fetchone()
        total_balance = row["total"] if row and row["total"] else 0
    finally:
        await conn.close()

    text = (
        f"📊 <b>Статистика казино</b>\n\n"
        f"┣ 👥 Всего игроков: {total_users}\n"
        f"┣ 🎮 Активных: {active_players}\n"
        f"┣ 💰 Баланс: {total_balance} монет\n"
        f"┣ 📋 Ожидающих запросов: {pending}"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "casino_admin_pending")
async def cb_casino_admin_pending(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "approve_deposits"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT * FROM deposit_requests WHERE status = 'pending' ORDER BY created"
        )
        pending = await cursor.fetchall()
    finally:
        await conn.close()

    if not pending:
        await call.message.edit_text("📋 Нет ожидающих запросов на пополнение.")
        await call.answer()
        return

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    text = "<b>📋 Ожидающие запросы:</b>\n\n"
    buttons = []
    for req in pending[:10]:
        username = await get_username(req["user_id"])
        text += (
            f"┃ <b>#{req['id']}</b>\n"
            f"┃ 👤 {username}\n"
            f"┃ 🆔 <code>{req['user_id']}</code>\n"
            f"┃ 💵 {req['amount']} монет\n"
            f"┃ 📅 {req['created']}\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"💳 #{req['id']}", callback_data=f"provide_{req['id']}"),
            InlineKeyboardButton(text="❌", callback_data=f"admin_reject_{req['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")])

    if len(pending) > 10:
        text += f"┃ <i>...и ещё {len(pending) - 10} запросов</i>\n\n"

    text += "💡 Нажмите кнопку с номером запроса, чтобы обработать."
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data == "casino_admin_withdrawals")
async def cb_casino_admin_withdrawals(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "approve_withdrawals"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT * FROM withdraw_requests WHERE status = 'pending' ORDER BY created"
        )
        pending = await cursor.fetchall()
    finally:
        await conn.close()

    if not pending:
        await call.message.edit_text("💸 Нет ожидающих запросов на вывод.")
        await call.answer()
        return

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    text = "<b>💸 Ожидающие запросы на вывод:</b>\n\n"
    buttons = []
    for req in pending[:10]:
        username = await get_username(req["user_id"])
        text += (
            f"┃ <b>#{req['id']}</b>\n"
            f"┃ 👤 {username}\n"
            f"┃ 🆔 <code>{req['user_id']}</code>\n"
            f"┃ 💵 {req['amount']} монет\n"
            f"┃ 💳 {req['card_details'][:40]}{'...' if len(req['card_details']) > 40 else ''}\n"
            f"┃ 📅 {req['created']}\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"✅ #{req['id']}", callback_data=f"withdraw_approve_{req['id']}"),
            InlineKeyboardButton(text="❌", callback_data=f"admin_withdraw_reject_{req['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")])

    if len(pending) > 10:
        text += f"┃ <i>...и ещё {len(pending) - 10} запросов</i>\n\n"

    text += "💡 Нажмите кнопку с номером запроса, чтобы обработать."
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data.startswith("admin_withdraw_reject_"))
async def cb_admin_withdraw_reject(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_withdrawals"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    withdraw_id = int(call.data.split("_", 3)[3])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id FROM withdraw_requests WHERE id = ? AND status = 'pending'",
            (withdraw_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return
        await conn.execute(
            "UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?",
            (withdraw_id,),
        )
        await conn.commit()
        await get_bot().send_message(row["user_id"], "❌ Ваш запрос на вывод был отклонён.")
    finally:
        await conn.close()
    await call.answer("❌ Отклонено")
    await cb_casino_admin_withdrawals(call)


@router.callback_query(F.data.startswith("admin_reject_"))
async def cb_admin_reject_deposit(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_deposits"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    deposit_id = int(call.data.split("_", 2)[2])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount, status FROM deposit_requests WHERE id = ?",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row or row["status"] in ("approved", "rejected"):
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return
        await conn.execute(
            "UPDATE deposit_requests SET status = 'rejected' WHERE id = ?",
            (deposit_id,),
        )
        await conn.commit()
        await get_bot().send_message(row["user_id"], "❌ Ваш запрос на пополнение был отклонён.")
    finally:
        await conn.close()
    await call.answer("❌ Отклонено")
    await cb_casino_admin_pending(call)


@router.callback_query(F.data == "adm_ban")
async def cb_adm_ban(call: CallbackQuery, state: FSMContext):
    if not await is_casino_admin(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminModState.waiting_target)
    await state.update_data(action="ban")
    await call.message.edit_text("🚫 Введите ID или @username пользователя для бана:")
    await call.answer()


@router.callback_query(F.data == "adm_mute")
async def cb_adm_mute(call: CallbackQuery, state: FSMContext):
    if not await is_casino_admin(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminModState.waiting_target)
    await state.update_data(action="mute")
    await call.message.edit_text("🔇 Введите ID или @username пользователя для мута:")
    await call.answer()


@router.callback_query(F.data == "adm_warn")
async def cb_adm_warn(call: CallbackQuery, state: FSMContext):
    if not await is_casino_admin(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminModState.waiting_target)
    await state.update_data(action="warn")
    await call.message.edit_text("⚠️ Введите ID или @username пользователя для варна:")
    await call.answer()


@router.callback_query(F.data == "adm_check")
async def cb_adm_check(call: CallbackQuery, state: FSMContext):
    if not await is_casino_admin(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminModState.waiting_target)
    await state.update_data(action="check")
    await call.message.edit_text("📋 Введите ID или @username пользователя для проверки:")
    await call.answer()


@router.message(AdminModState.waiting_target)
async def process_admin_target(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")

    target_id = resolve_user(message.text)
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите числовой ID или @username.")
        return

    if not can_moderate(message.from_user.id, target_id):
        await message.answer("❌ Нельзя модерировать этого пользователя.")
        return

    mod_id = message.from_user.id

    if action == "ban":
        ban_user(target_id, mod_id, "Бан из админ-панели казино")
        await message.answer(f"✅ Пользователь <code>{target_id}</code> забанен.")

    elif action == "mute":
        mute_user(target_id, mod_id, 60)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> замучен на 60 мин.")

    elif action == "warn":
        warns = add_warn(target_id, mod_id)
        await message.answer(f"⚠️ Пользователь <code>{target_id}</code> получил варн ({warns}/3).")

    elif action == "check":
        banned = is_banned(target_id)
        muted = is_muted(target_id)
        warns = get_warns(target_id)
        lines = [
            f"📋 <b>Проверка пользователя</b> <code>{target_id}</code>",
            f"┃ 🚫 Бан: {'✅ Да' if banned else '❌ Нет'}",
            f"┃ 🔇 Мут: {'✅ Да' if muted else '❌ Нет'}",
            f"┃ ⚠️ Варны: {warns}/3",
        ]
        await message.answer("\n".join(lines), parse_mode="HTML")

    await state.clear()


@router.callback_query(F.data == "casino_admin_solotop")
async def cb_casino_admin_solotop(call: CallbackQuery):
    uid = call.from_user.id
    if not await is_casino_admin(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, score, games_played FROM solo_scores ORDER BY score DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    if not rows:
        await call.message.answer("❌ Пока никто не играл в соло-казино.")
        await call.answer()
        return
    text = "<b>⭐ Топ 10 соло-казино</b>\n\n"
    for i, row in enumerate(rows, 1):
        name = row["username"] or f"user_{row['user_id']}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
        avg = round(row["score"] / row["games_played"], 1) if row["games_played"] else 0
        text += f"{medal} <b>{i}.</b> {name}  →  {row['score']} ⭐  ({row['games_played']} игр, ср. {avg})\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()
