from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, update_bot_balance, get_username,
    is_casino_admin, is_owner, has_perm, get_admin_perms, ADMIN_ID, PERMISSIONS, AdminAction, logger,
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
    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")]
        ])
    )
    await call.answer()


# ---------- ADD PVP BALANCE ----------
class AdminAddPVPState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


@router.callback_query(F.data == "casino_admin_add")
async def cb_casino_admin_add(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not await has_perm(uid, "add_balance"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminAddPVPState.waiting_user_id)
    await call.message.edit_text("💰 Введите ID или @username пользователя для пополнения PVP баланса:")
    await call.answer()


@router.message(AdminAddPVPState.waiting_user_id)
async def process_admin_add_pvp_user(message: Message, state: FSMContext):
    target_id = resolve_user(message.text)
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите числовой ID или @username.")
        return
    await state.update_data(target_id=target_id)
    await state.set_state(AdminAddPVPState.waiting_amount)
    await message.answer(f"💰 Введите сумму для пополнения PVP баланса пользователю <code>{target_id}</code>:", parse_mode="HTML")


@router.message(AdminAddPVPState.waiting_amount)
async def process_admin_add_pvp_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_id")
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return
    if amount < 1:
        await message.answer("❌ Сумма должна быть больше 0.")
        return
    await update_balance(target_id, amount, "admin_add")
    await state.clear()
    await message.answer(f"✅ PVP баланс пользователя <code>{target_id}</code> пополнен на <b>{amount}</b> монет!", parse_mode="HTML")
    try:
        admin_name = message.from_user.username or "Администратор"
        await get_bot().send_message(
            target_id,
            f"💰 <b>Баланс пополнен!</b>\n\n+{amount} 🪙\nПополнил: @{admin_name}",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ---------- PROMOCODES ----------
class AdminPromoState(StatesGroup):
    waiting_code = State()
    waiting_amount = State()


class AdminPromoDeleteState(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "casino_admin_promos")
async def cb_casino_admin_promos(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "create_promos"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        promos = await cursor.fetchall()
    finally:
        await conn.close()

    lines = ["<b>🎟 Промокоды</b>\n\n"]
    if not promos:
        lines.append("Нет созданных промокодов.\n")
    else:
        for p in promos:
            conn2 = await get_db()
            try:
                cur2 = await conn2.execute(
                    "SELECT COUNT(*) as cnt FROM promo_activations WHERE code = ?", (p["code"],)
                )
                cnt_row = await cur2.fetchone()
                activations = cnt_row["cnt"] if cnt_row else 0
            finally:
                await conn2.close()
            lines.append(f"┃ <code>{p['code']}</code> — {p['amount']} 🪙  |  активаций: {activations}\n")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промо", callback_data="casino_admin_create_promo")],
        [InlineKeyboardButton(text="❌ Удалить промо", callback_data="casino_admin_delete_promo")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")],
    ])
    await call.message.edit_text("".join(lines), parse_mode="HTML", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "casino_admin_create_promo")
async def cb_casino_admin_create_promo(call: CallbackQuery, state: FSMContext):
    if not await has_perm(call.from_user.id, "create_promos"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminPromoState.waiting_code)
    await call.message.edit_text("🎟 Введите код промокода (латиница и цифры):")
    await call.answer()


@router.message(AdminPromoState.waiting_code)
async def process_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Код должен содержать только буквы и цифры.")
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoState.waiting_amount)
    await message.answer(f"💰 Введите сумму для промокода <code>{code}</code>:", parse_mode="HTML")


@router.message(AdminPromoState.waiting_amount)
async def process_promo_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return
    if amount < 1:
        await message.answer("❌ Сумма должна быть больше 0.")
        return
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT 1 FROM promocodes WHERE code = ?", (code,))
        if await cursor.fetchone():
            await message.answer(f"❌ Промокод <code>{code}</code> уже существует.")
            await state.clear()
            return
        from datetime import datetime
        await conn.execute(
            "INSERT INTO promocodes (code, amount, created_by, created_at) VALUES (?, ?, ?, ?)",
            (code, amount, message.from_user.id, datetime.now().isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()
    await state.clear()
    await message.answer(f"✅ Промокод <code>{code}</code> на <b>{amount}</b> монет создан!", parse_mode="HTML")


@router.callback_query(F.data == "casino_admin_delete_promo")
async def cb_casino_admin_delete_promo(call: CallbackQuery, state: FSMContext):
    if not await has_perm(call.from_user.id, "create_promos"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminPromoDeleteState.waiting_code)
    await call.message.edit_text("❌ Введите код промокода для удаления:")
    await call.answer()


@router.message(AdminPromoDeleteState.waiting_code)
async def process_delete_promo(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    conn = await get_db()
    try:
        await conn.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        await conn.commit()
    finally:
        await conn.close()
    await state.clear()
    await message.answer(f"✅ Промокод <code>{code}</code> удалён.", parse_mode="HTML")


# ---------- ADMIN MANAGEMENT ----------
class AdminManageState(StatesGroup):
    waiting_target = State()


@router.callback_query(F.data == "casino_admin_manage")
async def cb_casino_admin_manage(call: CallbackQuery):
    uid = call.from_user.id
    if not is_owner(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT a.admin_id, a.added_at, COALESCE(u.username, '?') as username "
            "FROM casino_admins a LEFT JOIN users u ON a.admin_id = u.user_id ORDER BY a.added_at"
        )
        admins = await cursor.fetchall()
    finally:
        await conn.close()

    lines = ["<b>👑 Управление админами казино</b>\n\n"]
    if not admins:
        lines.append("Нет добавленных администраторов.\n")
    else:
        for a in admins:
            name = f"@{a['username']}" if a["username"] and a["username"] != "?" else f"ID {a['admin_id']}"
            lines.append(f"┃ {name}  |  🆔 <code>{a['admin_id']}</code>\n")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="casino_admin_add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="casino_admin_remove_admin")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")],
    ])
    await call.message.edit_text("".join(lines), parse_mode="HTML", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "casino_admin_add_admin")
async def cb_casino_admin_add_admin(call: CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminManageState.waiting_target)
    await state.update_data(action="add_admin")
    await call.message.edit_text("➕ Введите ID или @username пользователя для добавления в админы:")
    await call.answer()


@router.callback_query(F.data == "casino_admin_remove_admin")
async def cb_casino_admin_remove_admin(call: CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminManageState.waiting_target)
    await state.update_data(action="remove_admin")
    await call.message.edit_text("➖ Введите ID или @username пользователя для удаления из админов:")
    await call.answer()


@router.message(AdminManageState.waiting_target)
async def process_admin_manage_target(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    target_id = resolve_user(message.text)
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите числовой ID или @username.")
        return

    conn = await get_db()
    try:
        if action == "add_admin":
            cursor = await conn.execute("SELECT 1 FROM casino_admins WHERE admin_id = ?", (target_id,))
            if await cursor.fetchone():
                await message.answer(f"❌ Пользователь <code>{target_id}</code> уже является админом.")
                await state.clear()
                return
            from datetime import datetime
            await conn.execute(
                "INSERT INTO casino_admins (admin_id, added_by, added_at) VALUES (?, ?, ?)",
                (target_id, message.from_user.id, datetime.now().isoformat()),
            )
            await conn.commit()
            await message.answer(f"✅ Пользователь <code>{target_id}</code> назначен администратором казино!")
        elif action == "remove_admin":
            await conn.execute("DELETE FROM casino_admins WHERE admin_id = ?", (target_id,))
            await conn.execute("DELETE FROM admin_permissions WHERE admin_id = ?", (target_id,))
            await conn.commit()
            await message.answer(f"✅ Администратор <code>{target_id}</code> удалён.")
    finally:
        await conn.close()
    await state.clear()


# ---------- ADMIN HELP ----------
@router.callback_query(F.data == "casino_admin_help")
async def cb_casino_admin_help(call: CallbackQuery):
    uid = call.from_user.id
    if not await is_casino_admin(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    text = (
        "<b>📖 Команды администратора казино</b>\n\n"
        "<b>Управление балансом:</b>\n"
        "┃ <code>/пополнить @user сумма</code> — пополнить PVP баланс\n"
        "┃ <code>/addbotcoins @user сумма</code> — пополнить счёт (бот)\n\n"
        "<b>Промокоды:</b>\n"
        "┃ <code>/createpromo КОД сумма</code> — создать промокод\n"
        "┃ <code>/deletepromo КОД</code> — удалить промокод\n"
        "┃ <code>/promo_list</code> — список всех промокодов\n"
        "┃ <code>/promo КОД</code> — активировать промокод\n\n"
        "<b>Запросы:</b>\n"
        "┃ <code>/выводы</code> — просмотр запросов на вывод\n"
        "┃ <code>/одобрить ID</code> — одобрить депозит\n\n"
        "<b>Игроки:</b>\n"
        "┃ <code>/игроки</code> — список всех игроков\n"
        "┃ <code>/solotop</code> — топ с ботом\n\n"
        "<b>Модерация:</b>\n"
        "┃ Кнопки 🚫🔇⚠️📋 в админ-панели\n\n"
        "💡 Все команды также доступны через админ-панель (кнопки выше)."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_admin")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
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


@router.callback_query(F.data == "casino_admin_addbot")
async def cb_casino_admin_addbot(call: CallbackQuery, state: FSMContext):
    if not await is_casino_admin(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await state.set_state(AdminAction.waiting_user_id)
    await state.update_data(action="addbotcoins")
    await call.message.edit_text("🤖 Введите ID или @username пользователя для пополнения счёта (бот):")
    await call.answer()


@router.message(AdminAction.waiting_user_id)
async def process_admin_addbot_user(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("action") != "addbotcoins":
        await state.clear()
        return

    target_id = resolve_user(message.text)
    if target_id is None:
        await message.answer("❌ Пользователь не найден. Укажите числовой ID или @username.")
        return

    await state.update_data(target_id=target_id)
    await state.set_state(AdminAction.waiting_amount)
    await message.answer(f"💰 Введите сумму для пополнения счёта (бот) пользователю <code>{target_id}</code>:", parse_mode="HTML")


@router.message(AdminAction.waiting_amount)
async def process_admin_addbot_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("action") != "addbotcoins":
        await state.clear()
        return

    target_id = data.get("target_id")
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return

    if amount < 1:
        await message.answer("❌ Сумма должна быть больше 0.")
        return

    await update_bot_balance(target_id, amount, "admin_add_bot")
    await state.clear()

    await message.answer(
        f"✅ Счёт (бот) пользователя <code>{target_id}</code> пополнен на <b>{amount}</b> монет!",
        parse_mode="HTML",
    )

    try:
        admin_name = message.from_user.username or "Администратор"
        await get_bot().send_message(
            target_id,
            f"🤖 <b>Счёт для игры с ботом пополнен!</b>\n\n"
            f"💰 +{amount} монет\n"
            f"👤 Пополнил: @{admin_name}\n\n"
            f"🎉 Приятной игры!",
            parse_mode="HTML",
        )
    except Exception:
        pass


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
        await call.message.answer("❌ Пока никто не играл с ботом.")
        await call.answer()
        return
    text = "<b>⭐ Топ 10 с ботом</b>\n\n"
    for i, row in enumerate(rows, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
        if row["username"]:
            display = row["username"]
        else:
            display = f"ID {row['user_id']}"
        avg = round(row["score"] / row["games_played"], 1) if row["games_played"] else 0
        text += f"{medal} <b>{i}.</b> {display}  →  {row['score']} ⭐  ({row['games_played']} игр, ср. {avg})\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.message(Command("addbotcoins"))
async def cmd_addbotcoins(message: Message):
    if not await is_casino_admin(message.from_user.id):
        await message.reply("❌ Доступ запрещён!")
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("❌ Формат: <code>/addbotcoins user_id сумма</code>")
        return
    target_id = resolve_user(parts[1])
    if target_id is None:
        await message.reply("❌ Пользователь не найден. Укажите ID или @username.")
        return
    try:
        amount = int(parts[2])
    except ValueError:
        await message.reply("❌ Сумма должна быть числом.")
        return
    if amount < 1:
        await message.reply("❌ Сумма должна быть больше 0.")
        return
    await update_bot_balance(target_id, amount, "admin_add_bot")
    await message.reply(f"✅ Счёт (бот) пользователя <code>{target_id}</code> пополнен на <b>{amount}</b> монет!", parse_mode="HTML")
    try:
        admin_name = message.from_user.username or "Администратор"
        await get_bot().send_message(
            target_id,
            f"🤖 <b>Счёт для игры с ботом пополнен!</b>\n\n"
            f"💰 +{amount} монет\n"
            f"👤 Пополнил: @{admin_name}\n\n"
            f"🎉 Приятной игры!",
            parse_mode="HTML",
        )
    except Exception:
        pass
