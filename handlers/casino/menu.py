from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, get_username,
    GAMES_CONFIG, active_games, active_blackjack_games, active_games_lock,
    ADMIN_ID, is_casino_admin, has_perm, init_db,
)
from .keyboards import casino_menu_kb, game_selection_kb, pvp_game_selection_kb, solo_game_selection_kb, solo_bet_selection_kb, blackjack_bet_kb, bet_selection_kb, casino_admin_kb

router = Router()


@router.callback_query(F.data == "casino_menu")
async def cb_casino_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)
    bj = user["blackjack_balance"] if user["blackjack_balance"] else 1000
    bbot = user["bot_balance"] if user["bot_balance"] else 500
    await call.message.edit_text(
        f"🎰 <b>Меню казино</b>\n\n"
        f"┃ 💰 <b>PVP:</b> {user['balance']} 🪙\n"
        f"┃ 🤖 <b>С ботом:</b> {bbot} 🤖\n"
        f"┃ 🃏 <b>Блэкджек:</b> {bj} 🪙\n"
        f"┃ 🏆 <b>Побед:</b> {user['wins']} / {user['games_played']} игр",
        parse_mode="HTML",
        reply_markup=casino_menu_kb(user_id=call.from_user.id),
    )
    await call.answer()


@router.callback_query(F.data == "casino_games")
async def cb_casino_games(call: CallbackQuery):
    text = "<b>🎮 Выберите режим игры:</b>\n\n"
    text += "🤖 <b>Игра с ботом</b> — в ЛС, бот кидает кубик, своя валюта\n"
    text += "👥 <b>С игроками</b> — в группе, PVP, создание комнаты\n"
    text += "🃏 <b>Блэкджек</b> — в группе, до 6 игроков, против дилера\n\n"
    text += "💡 Нажмите /<b>профиль</b> чтобы посмотреть баланс"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=game_selection_kb())
    await call.answer()


@router.callback_query(F.data == "casino_profile")
async def cb_casino_profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)

    bj_bal = user["blackjack_balance"] if user["blackjack_balance"] else 1000
    bbot = user["bot_balance"] if user["bot_balance"] else 500
    conn = await get_db()
    solo_row = None
    try:
        cur = await conn.execute("SELECT score, games_played FROM solo_scores WHERE user_id = ?", (call.from_user.id,))
        solo_row = await cur.fetchone()
    except Exception:
        pass
    finally:
        await conn.close()
    solo_score = solo_row["score"] if solo_row else 0
    solo_games = solo_row["games_played"] if solo_row else 0
    text = (
        f"<b>📊 Профиль игрока</b> {call.from_user.first_name}\n\n"
        f"┃ 🆔 ID: <code>{user['user_id']}</code>\n"
        f"┃ 💰 <b>PVP баланс:</b> {user['balance']} 🪙\n"
        f"┃ 🤖 <b>С ботом:</b> {bbot} 🤖\n"
        f"┃ 🃏 <b>Блэкджек:</b> {bj_bal} 🪙\n"
        f"┃ ⭐ <b>Соло очки:</b> {solo_score} ({solo_games} игр)\n"
        f"┃ 🎮 <b>Сыграно PVP игр:</b> {user['games_played']}\n"
        f"┃ 🏆 <b>Побед PVP:</b> {user['wins']}\n"
    )
    markup = _inline_keyboard([
        [("💳 Пополнить PVP", "deposit"), ("💸 Вывести", "withdraw")],
        [("🎮 В игры", "games_menu")],
    ])
    await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "casino_top")
async def cb_casino_top(call: CallbackQuery):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Топ казино (PVP)", callback_data="casino_top_pvp")],
        [InlineKeyboardButton(text="⭐ Топ соло", callback_data="casino_top_solo")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")],
    ])
    await call.message.edit_text(
        "<b>🏆 Выберите топ:</b>\n\n"
        "🏆 <b>Топ казино</b> — игроки с самым большим PVP-балансом\n"
        "⭐ <b>Топ соло</b> — игроки с наибольшими очками в соло-играх",
        parse_mode="HTML",
        reply_markup=markup,
    )
    await call.answer()


@router.callback_query(F.data == "casino_top_pvp")
async def cb_casino_top_pvp(call: CallbackQuery):
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()

    if not rows:
        await call.message.answer("❌ Пока нет данных о пользователях.")
    else:
        text = "<b>🏆 Топ 10 казино (PVP)</b>\n\n"
        for i, row in enumerate(rows, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
            if row["username"]:
                display = f"@{row['username']}"
            else:
                display = f"ID {row['user_id']}"
            text += f"{medal} <b>{i}.</b> {display}  →  {row['balance']} 🪙\n"
        await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "casino_top_solo")
async def cb_casino_top_solo(call: CallbackQuery):
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
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
        if row["username"]:
            display = row["username"]
        else:
            display = f"ID {row['user_id']}"
        avg = round(row["score"] / row["games_played"], 1) if row["games_played"] else 0
        text += f"{medal} <b>{i}.</b> {display}  →  {row['score']} ⭐  ({row['games_played']} игр, ср. {avg})\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "casino_active")
async def cb_casino_active(call: CallbackQuery):
    async with active_games_lock:
        if not active_games and not active_blackjack_games:
            await call.message.answer("Сейчас нет активных игр.")
            await call.answer()
            return

        text = "<b>🎮 Активные игры:</b>\n\n"
        for g in active_games.values():
            if g.is_finished:
                continue
            p1 = await get_username(g.player1)
            p2 = await get_username(g.player2) if g.player2 else "⏳ Ожидает"
            text += (
                f"┃ {GAMES_CONFIG[g.game_type]['emoji']} <b>{GAMES_CONFIG[g.game_type]['action']}</b>\n"
                f"┃ 💵 Ставка: <b>{g.bet}</b> 🪙\n"
                f"┃ 👤 {p1} vs {p2}\n\n"
            )
        for g in active_blackjack_games.values():
            if g.is_finished:
                continue
            players = ", ".join(g.player_names.values())
            text += (
                f"┃ 🃏 <b>Блэкджек</b>\n"
                f"┃ 💵 Ставка: <b>{g.bet}</b> 🪙\n"
                f"┃ 👤 {players} ({len(g.players)}/6)\n\n"
            )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "casino_unlock")
async def cb_casino_unlock(call: CallbackQuery):
    user_id = call.from_user.id
    refunded = 0

    async with active_games_lock:
        to_remove = []
        for rid, g in active_games.items():
            if user_id in (g.player1, g.player2):
                try:
                    await update_balance(g.player1, g.bet, "refund")
                    refunded += g.bet
                    if g.player2:
                        await update_balance(g.player2, g.bet, "refund")
                        refunded += g.bet
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Refund error: {e}")
                to_remove.append(rid)

        for rid in to_remove:
            del active_games[rid]

    await call.message.answer(
        f"✅ <b>Все ваши игры отменены!</b>\n🔙 Возвращено: <b>{refunded}</b> 🪙\n"
        "Теперь вы можете создавать новые игры!",
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data == "casino_play_bot")
async def cb_casino_play_bot(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_username = (await get_bot().me()).username
        text = (
            "🤖 <b>Игра с ботом</b> доступна <b>только в ЛС</b>!\n\n"
            "📌 Напишите боту в личку и отправьте:\n"
            "/сботом [игра] [ставка]\n\n"
            "Пример: `/сботом куб 50`\n\n"
            "Или просто нажмите: @{}"
        ).format(bot_username)
        await call.message.edit_text(text)
        await call.answer()
        return
    text = "🤖 <b>Игра с ботом</b>\n\n⬇️ <b>Выберите игру:</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=solo_game_selection_kb())
    await call.answer()


@router.callback_query(F.data == "casino_play_pvp")
async def cb_casino_play_pvp(call: CallbackQuery):
    if call.message.chat.type == "private":
        bot_username = (await get_bot().me()).username
        text = (
            "👥 <b>Игра с игроками</b> работает <b>только в групповых чатах</b>!\n\n"
            "📌 <b>Как играть:</b>\n"
            "1. Добавьте бота в группу: `@{}`\n"
            "2. Дайте боту права администратора\n"
            "3. Выберите игру и ставку ниже\n"
            "4. Другой игрок нажимает «Присоединиться»\n\n"
            "⬇️ <b>Выберите игру:</b>"
        ).format(bot_username)
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=pvp_game_selection_kb())
        await call.answer()
        return

    text = "👥 <b>Игра с игроками</b>\n\n⬇️ <b>Выберите игру:</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=pvp_game_selection_kb())
    await call.answer()


@router.callback_query(F.data == "casino_blackjack_info")
async def cb_casino_blackjack_info(call: CallbackQuery):
    if call.message.chat.type == "private":
        bot_username = (await get_bot().me()).username
        text = (
            "🃏 <b>Блэкджек</b> доступен <b>только в групповых чатах</b>!\n\n"
            "📌 <b>Как играть:</b>\n"
            "1. Добавьте бота в группу: `@{}`\n"
            "2. Напишите в группе: `/блекджек 50`\n"
            "3. Игроки нажимают «Присоединиться»\n"
            "4. Создатель нажимает «Старт» для начала\n\n"
            "Правила: наберите 21 или близко к 21, не перебирая. "
            "До 6 игроков за столом. Каждый играет против дилера."
        ).format(bot_username)
        await call.message.edit_text(text)
    else:
        text = (
            "🃏 <b>Блэкджек</b>\n\n⬇️ <b>Выберите ставку:</b>"
        )
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=blackjack_bet_kb())
    await call.answer()


def _inline_keyboard(rows: list[list[tuple[str, str]]]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
            for row in rows
        ]
    )


@router.message(Command("игры"))
@router.message(Command("games"))
async def cmd_games(message: Message):
    text = "<b>🕹 Доступные игры:</b>\n\n"
    for game_type, cfg in GAMES_CONFIG.items():
        text += f"┃ {cfg['emoji']} <b>{game_type.capitalize()}</b>  →  <code>/{cfg['command']} [ставка]</code> (PVP)\n"
    text += "┃ 🃏 <b>Блэкджек</b>  →  <code>/блекджек [ставка]</code> (в группе, до 6 игроков)\n"
    text += "┃ 🤖 <b>С ботом</b>  →  <code>/сботом [игра] [ставка]</code> (в ЛС)\n"
    text += "\n💡 Нажмите /<b>профиль</b> чтобы посмотреть баланс"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("активные"))
@router.message(Command("active"))
async def cmd_active_games(message: Message):
    async with active_games_lock:
        if not active_games and not active_blackjack_games:
            await message.reply("Сейчас нет активных игр.")
            return

        text = "🎮 Активные игры:\n\n"
        for g in active_games.values():
            if g.is_finished:
                continue
            p1 = await get_username(g.player1)
            p2 = await get_username(g.player2) if g.player2 else "Ожидает второго игрока"
            text += (
                f"🔹 Игра в {GAMES_CONFIG[g.game_type]['emoji']}\n"
                f"💵 Ставка: {g.bet} монет\n"
                f"Игрок 1: {p1}\n"
                f"Игрок 2: {p2}\n"
                f"ID: {g.room_id}\n\n"
            )
        for g in active_blackjack_games.values():
            if g.is_finished:
                continue
            players = ", ".join(g.player_names.values())
            text += (
                f"🃏 Блэкджек\n"
                f"💵 Ставка: {g.bet} монет\n"
                f"Игроки: {players} ({len(g.players)}/6)\n\n"
            )
    await message.reply(text)


@router.message(Command("разблокировать"))
@router.message(Command("unlock"))
async def cmd_force_unlock(message: Message):
    user_id = message.from_user.id
    refunded = 0

    async with active_games_lock:
        to_remove = []
        for rid, g in active_games.items():
            if user_id in (g.player1, g.player2):
                try:
                    await update_balance(g.player1, g.bet, "refund")
                    refunded += g.bet
                    if g.player2:
                        await update_balance(g.player2, g.bet, "refund")
                        refunded += g.bet
                except:
                    pass
                to_remove.append(rid)

        for rid in to_remove:
            del active_games[rid]

    await message.reply(
        f"✅ Все ваши игры отменены! Возвращено: {refunded} монет\n"
        "Теперь вы можете создавать новые игры!"
    )


@router.message(Command("игроки"))
@router.message(Command("players"))
async def cmd_all_players(message: Message):
    if not await has_perm(message.from_user.id, "view_players"):
        from .base import is_casino_admin
        if not await is_casino_admin(message.from_user.id):
            await message.reply("❌ Доступ запрещён!")
            return

    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT * FROM users ORDER BY user_id")
        players = await cursor.fetchall()
    finally:
        await conn.close()

    if not players:
        await message.reply("❌ Нет зарегистрированных игроков.")
        return

    parts = []
    chunk = []
    for p in players:
        name = f"@{p['username']}" if p["username"] else f"ID {p['user_id']}"
        chunk.append(
            f"👤 <code>{p['user_id']}</code> | {name}\n"
            f"💰 {p['balance']} | 🎮 {p['games_played']} | 🏆 {p['wins']}\n"
            f"{'─' * 20}"
        )
        if len(chunk) == 10:
            parts.append("\n".join(chunk))
            chunk = []

    if chunk:
        parts.append("\n".join(chunk))

    header = f"<b>👥 Все игроки ({len(players)}):</b>\n\n"
    for i, part in enumerate(parts):
        text = header if i == 0 else ""
        await message.answer(text + part, parse_mode="HTML")


@router.message(Command("solotop"))
async def cmd_solo_top(message: Message):
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, score, games_played FROM solo_scores ORDER BY score DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    if not rows:
        await message.answer("❌ Пока никто не играл в соло-казино.")
        return
    text = "<b>⭐ Топ 10 соло-казино</b>\n\n"
    for i, row in enumerate(rows, 1):
        name = row["username"] or f"user_{row['user_id']}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
        avg = round(row["score"] / row["games_played"], 1) if row["games_played"] else 0
        text += f"{medal} <b>{i}.</b> {name}  →  {row['score']} ⭐  ({row['games_played']} игр, ср. {avg})\n"
    await message.answer(text, parse_mode="HTML")
