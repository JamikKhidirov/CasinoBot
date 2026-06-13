import asyncio
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, get_username,
    GameRoom, active_games, active_games_lock,
    GameStates, logger,
    save_active_game, delete_active_game,
)

router = Router()
_rps_choices: dict[str, dict[int, str]] = {}
_rps_pm_msgs: dict[str, dict[int, int]] = {}

RULES = "🪨 → ✂️ → 📄 → 🪨"
_RPS_MAP = {"rock": "🪨", "scissors": "✂️", "paper": "📄"}
_RPS_REV = {"🪨": "rock", "✂️": "scissors", "📄": "paper"}


def _rps_winner(c1: str, c2: str) -> int:
    if c1 == c2:
        return 0
    if (c1 == "🪨" and c2 == "✂️") or (c1 == "✂️" and c2 == "📄") or (c1 == "📄" and c2 == "🪨"):
        return 1
    return 2


def _rps_pick_kb(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪨 Камень", callback_data=f"rps_pick_{room_id}_rock"),
         InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_pick_{room_id}_scissors"),
         InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_pick_{room_id}_paper")]
    ])


async def _send_choice_pm(pid: int, game: GameRoom, opponent_name: str):
    try:
        msg = await get_bot().send_message(
            pid,
            f"✂️ <b>Камень-Ножницы-Бумага!</b>\n"
            f"💵 Ставка: {game.bet} 🪙\n"
            f"👤 Против: {opponent_name}\n"
            f"📖 {RULES}\n\n"
            f"Выберите жест:",
            reply_markup=_rps_pick_kb(game.room_id),
        )
        return msg.message_id
    except Exception:
        return None


async def _start_rps(game: GameRoom):
    game.player1_turn = False
    _rps_choices[game.room_id] = {}
    _rps_pm_msgs[game.room_id] = {}

    p1_name = await get_username(game.player1)
    p2_name = await get_username(game.player2)

    failed = []
    for pid, opp_name in [(game.player1, p2_name), (game.player2, p1_name)]:
        mid = await _send_choice_pm(pid, game, opp_name)
        if mid:
            _rps_pm_msgs[game.room_id][pid] = mid
        else:
            failed.append(await get_username(pid))

    if failed:
        await get_bot().send_message(game.chat_id, f"❌ {' и '.join(failed)} не доступны в ЛС. Игра отменена.")
        game.is_finished = True
        async with active_games_lock:
            if game.room_id in active_games:
                del active_games[game.room_id]
        await delete_active_game(game.room_id)
        for pid in (game.player1, game.player2):
            await update_balance(pid, game.bet, "refund_rps")
        _rps_choices.pop(game.room_id, None)
        _rps_pm_msgs.pop(game.room_id, None)
        return

    bot_username = (await get_bot().me()).username
    await get_bot().edit_message_text(
        chat_id=game.chat_id,
        message_id=game.message_id,
        text=(
            f"✂️ <b>Камень-Ножницы-Бумага!</b>\n"
            f"💵 Ставка: {game.bet} 🪙\n\n"
            f"🪨 {p1_name}  vs  {p2_name} ✂️\n\n"
            f"⏳ Ожидаем выбор обоих игроков...\n"
            f"📖 {RULES}"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Перейти в ЛС", url=f"https://t.me/{bot_username}")]
        ]),
    )

    asyncio.ensure_future(_rps_timeout(game))


async def _rps_timeout(game: GameRoom):
    await asyncio.sleep(30)
    if game.is_finished:
        return
    choices = _rps_choices.get(game.room_id, {})
    remained = [pid for pid in (game.player1, game.player2) if pid not in choices]
    if not remained:
        return
    async with active_games_lock:
        if game.room_id not in active_games:
            return
        game.is_finished = True
        del active_games[game.room_id]
    await delete_active_game(game.room_id)

    for pid in (game.player1, game.player2):
        await update_balance(pid, game.bet, "refund_rps")
    names = ", ".join([await get_username(pid) for pid in remained])
    await get_bot().send_message(game.chat_id, f"⏰ {names} не сделали выбор. Игра отменена, ставки возвращены.")
    _rps_choices.pop(game.room_id, None)
    _rps_pm_msgs.pop(game.room_id, None)


async def _check_both_choices(game: GameRoom):
    choices = _rps_choices.get(game.room_id, {})
    k1 = choices.get(game.player1)
    k2 = choices.get(game.player2)
    if not k1 or not k2:
        return

    c1 = _RPS_MAP.get(k1, k1)
    c2 = _RPS_MAP.get(k2, k2)
    result = _rps_winner(c1, c2)
    p1_name = await get_username(game.player1)
    p2_name = await get_username(game.player2)

    if result == 0:
        text = (
            f"✂️ <b>Ничья!</b>\n\n"
            f"🪨 {p1_name}: {c1}\n"
            f"📄 {p2_name}: {c2}\n\n"
            f"🎭 Ставка возвращена."
        )
        await update_balance(game.player1, game.bet, "rps_tie")
        await update_balance(game.player2, game.bet, "rps_tie")
    elif result == 1:
        text = (
            f"🏆 <b>Победил {p1_name}!</b>\n\n"
            f"🪨 {p1_name}: {c1}\n"
            f"📄 {p2_name}: {c2}\n\n"
            f"💰 {p1_name} получает +{game.bet * 2} 🪙"
        )
        await update_balance(game.player1, game.bet * 2, "rps_win")
    else:
        text = (
            f"🏆 <b>Победил {p2_name}!</b>\n\n"
            f"🪨 {p1_name}: {c1}\n"
            f"📄 {p2_name}: {c2}\n\n"
            f"💰 {p2_name} получает +{game.bet * 2} 🪙"
        )
        await update_balance(game.player2, game.bet * 2, "rps_win")

    game.is_finished = True
    async with active_games_lock:
        if game.room_id in active_games:
            del active_games[game.room_id]
    await delete_active_game(game.room_id)

    try:
        await get_bot().edit_message_text(chat_id=game.chat_id, message_id=game.message_id, text=text)
    except Exception:
        await get_bot().send_message(game.chat_id, text)

    pm_msgs = _rps_pm_msgs.pop(game.room_id, {})
    for pid, mid in pm_msgs.items():
        try:
            win = (result == 1 and pid == game.player1) or (result == 2 and pid == game.player2)
            if result == 0:
                await get_bot().send_message(pid, f"🎭 <b>Ничья!</b> Ставка возвращена.")
            elif win:
                await get_bot().send_message(pid, f"🏆 <b>Вы победили!</b> +{game.bet * 2} 🪙")
            else:
                await get_bot().send_message(pid, f"❌ <b>Вы проиграли.</b> -{game.bet} 🪙")
        except Exception:
            pass
    _rps_choices.pop(game.room_id, None)


@router.callback_query(F.data.startswith("rps_pick_"))
async def cb_rps_pick(call: CallbackQuery):
    uid = call.from_user.id
    parts = call.data.rsplit("_", 1)
    if len(parts) < 2:
        await call.answer("❌ Ошибка.", show_alert=True)
        return
    room_id = parts[0].replace("rps_pick_", "")
    choice_key = parts[1]
    choice = _RPS_MAP.get(choice_key)
    if not choice:
        await call.answer("❌ Ошибка выбора.", show_alert=True)
        return

    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            await call.answer("❌ Игра завершена.", show_alert=True)
            return
        if uid not in (game.player1, game.player2):
            await call.answer("❌ Вы не участвуете в этой игре.", show_alert=True)
            return

    choices = _rps_choices.setdefault(room_id, {})
    if uid in choices:
        chosen_emoji = _RPS_MAP.get(choices[uid], choices[uid])
        await call.answer(f"✅ Вы уже выбрали {chosen_emoji}", show_alert=True)
        return

    choices[uid] = choice_key
    await call.answer(f"✅ Вы выбрали {choice}", show_alert=False)
    try:
        await call.message.edit_text(
            f"✂️ <b>Вы выбрали:</b> {choice}\n\n"
            f"⏳ Ожидаем выбор соперника...\n"
            f"📖 {RULES}"
        )
    except Exception:
        pass

    other_pid = game.player2 if uid == game.player1 else game.player1
    if other_pid not in choices:
        try:
            await get_bot().send_message(other_pid, "👀 Ваш соперник сделал выбор! Ожидаем вас.")
        except Exception:
            pass

    await _check_both_choices(game)


@router.callback_query(F.data == "casino_rps_info")
async def cb_rps_info(call: CallbackQuery):
    bot_username = (await get_bot().me()).username
    if call.message.chat.type == "private":
        text = (
            "✂️ <b>Камень-Ножницы-Бумага</b>\n\n"
            "📖 <b>Правила:</b>\n"
            "🪨 Камень бьёт ✂️ Ножницы\n"
            "✂️ Ножницы бьют 📄 Бумагу\n"
            "📄 Бумага бьёт 🪨 Камень\n\n"
            "📌 <b>Как играть:</b>\n"
            "1. Добавьте бота в группу: @{}\n"
            "2. Выберите ставку\n"
            "3. Второй игрок присоединяется\n"
            "4. Оба получают выбор в ЛС\n"
            "5. Победитель забирает ставку!"
        ).format(bot_username)
        await call.message.edit_text(text)
    else:
        await call.message.edit_text(
            "✂️ <b>Камень-Ножницы-Бумага</b>\n\n⬇️ <b>Выберите ставку:</b>",
            reply_markup=_rps_bet_kb(),
        )
    await call.answer()


@router.callback_query(F.data.startswith("casino_rps_bet_"))
async def cb_rps_bet(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type == "private":
        await call.answer("❌ PVP режим только в группах!", show_alert=True)
        return

    bet_str = call.data.split("_", 3)[3]
    if bet_str == "custom":
        await state.set_state(GameStates.waiting_for_bet)
        await state.update_data(game_type="rps")
        await call.message.edit_text("💰 Введите сумму ставки (от 10):")
        await call.answer()
        return

    try:
        bet = int(bet_str)
    except ValueError:
        await call.answer("❌ Некорректная ставка!", show_alert=True)
        return
    if bet < 10:
        await call.answer("❌ Минимальная ставка — 10!", show_alert=True)
        return

    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)
    if user["balance"] < bet:
        await call.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
        return

    await update_balance(call.from_user.id, -bet, "rps_reserve")
    room_id = str(uuid.uuid4())
    game = GameRoom(room_id, "rps", bet, call.from_user.id)
    game.chat_id = call.message.chat.id

    async with active_games_lock:
        for g in active_games.values():
            if not g.is_finished and call.from_user.id in (g.player1, g.player2):
                await update_balance(call.from_user.id, bet, "refund")
                await call.answer("❌ Вы уже участвуете в другой игре!", show_alert=True)
                return
        active_games[room_id] = game
    await save_active_game(room_id, "rps", call.from_user.id, 0, bet)

    bot_user = await get_bot().me()
    pm_url = f"https://t.me/{bot_user.username}"
    p1_name = await get_username(call.from_user.id)
    sent = await call.message.answer(
        f"✂️ <b>Камень-Ножницы-Бумага!</b>\n"
        f"💵 Ставка: {bet} 🪙\n"
        f"⏳ Ожидание второго игрока...\n\n"
        f"Игрок 1: {p1_name}\n"
        f"Места: 1/2\n\n"
        f"Игра отменится через 60 секунд, если никто не присоединится.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✂️ Присоединиться", callback_data=f"rps_join_{room_id}")],
            [InlineKeyboardButton(text="💬 Перейти в ЛС", url=pm_url)],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"rps_cancel_{room_id}")],
        ]),
    )
    game.message_id = sent.message_id
    await call.message.delete()
    await call.answer()
    asyncio.ensure_future(_rps_join_timeout(room_id, 60))


async def _rps_join_timeout(room_id: str, delay: int):
    await asyncio.sleep(delay)
    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished or game.player2 is not None:
            return
        await update_balance(game.player1, game.bet, "refund_rps")
        game.is_finished = True
        del active_games[room_id]
    await delete_active_game(room_id)
    try:
        await get_bot().edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text="⏰ Игра отменена, никто не присоединился.\n💰 Ставка возвращена.",
        )
    except Exception:
        await get_bot().send_message(game.chat_id, "⏰ Игра отменена, никто не присоединился.\n💰 Ставка возвращена.")


@router.callback_query(F.data.startswith("rps_join_"))
async def cb_rps_join(call: CallbackQuery):
    uid = call.from_user.id
    room_id = call.data.replace("rps_join_", "")

    async with active_games_lock:
        game = active_games.get(room_id)
        if not game:
            await call.answer("❌ Игра не найдена.", show_alert=True)
            return
        if game.is_finished:
            await call.answer("❌ Игра уже завершена.", show_alert=True)
            return
        if game.player2 is not None:
            await call.answer("❌ Место уже занято.", show_alert=True)
            return
        if game.player1 == uid:
            await call.answer("❌ Вы создали эту игру!", show_alert=True)
            return

        for g in active_games.values():
            if not g.is_finished and uid in (g.player1, g.player2) and g.room_id != room_id:
                await call.answer("❌ Вы уже участвуете в другой игре!", show_alert=True)
                return

        user = await get_user(uid)
        if not user:
            await create_user(call.from_user)
            user = await get_user(uid)
        if user["balance"] < game.bet:
            await call.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
            return

        await update_balance(uid, -game.bet, "rps_reserve")
        game.player2 = uid

    await call.answer("✅ Вы присоединились!")
    await _start_rps(game)


@router.callback_query(F.data.startswith("rps_cancel_"))
async def cb_rps_cancel(call: CallbackQuery):
    uid = call.from_user.id
    room_id = call.data.replace("rps_cancel_", "")
    async with active_games_lock:
        game = active_games.get(room_id)
        if not game:
            await call.answer("❌ Игра не найдена.", show_alert=True)
            return
        if uid != game.player1:
            await call.answer("❌ Только создатель может отменить.", show_alert=True)
            return
        if game.player2 is not None:
            await call.answer("❌ Игра уже началась!", show_alert=True)
            return
        game.is_finished = True
        del active_games[room_id]
    await delete_active_game(room_id)
    await update_balance(uid, game.bet, "refund_rps")
    try:
        await get_bot().edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text="❌ Игра отменена создателем.\n💰 Ставка возвращена.",
        )
    except Exception:
        pass
    await call.answer("✅ Игра отменена.")


def _rps_bet_kb() -> InlineKeyboardMarkup:
    bets = [10, 50, 100, 500, 1000]
    row = []
    buttons = []
    for bet in bets:
        row.append(InlineKeyboardButton(text=f"{bet}🪙", callback_data=f"casino_rps_bet_{bet}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="casino_rps_bet_custom")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
