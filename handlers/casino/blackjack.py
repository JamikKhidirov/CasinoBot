import asyncio
import random
import uuid
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, get_username,
    BlackjackRoom, active_blackjack_games, active_games_lock,
    INITIAL_BALANCE, logger,
    save_active_game, delete_active_game,
)
from .keyboards import blackjack_join_keyboard, blackjack_action_keyboard

MAX_MSG_LEN = 3997

router = Router()

CARD_SUITS = ["♠", "♥", "♦", "♣"]
CARD_NAMES = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K",
}
CARD_VALUES = {
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
    7: 7, 8: 8, 9: 9, 10: 10, 11: 10, 12: 10, 13: 10,
}


def create_deck(shuffle: bool = True) -> list[dict]:
    deck = []
    for suit in CARD_SUITS:
        for rank in range(1, 14):
            deck.append({"rank": rank, "suit": suit})
    if shuffle:
        random.shuffle(deck)
    return deck


def draw_card(deck: list[dict]) -> dict:
    return deck.pop()


def hand_value(cards: list[dict]) -> int:
    total = sum(CARD_VALUES[c["rank"]] for c in cards)
    aces = sum(1 for c in cards if c["rank"] == 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def cards_str(cards: list[dict]) -> str:
    parts = []
    for c in cards:
        name = CARD_NAMES[c["rank"]]
        suit = c["suit"]
        parts.append(f"{name}{suit}")
    return " ".join(parts)


def hand_emoji(val: int) -> str:
    if val == 21: return "🃏"
    if val > 21: return "💥"
    return "🎴"


@router.message(Command("блекджек"))
async def cmd_blackjack(message: Message):
    if message.chat.type == "private":
        await message.reply("🃏 Блэкджек доступен только в группах! Добавьте бота в группу.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply(
            "🃏 <b>Блэкджек</b>\n\n"
            "Формат: /блекджек [ставка]\n"
            "Пример: /блекджек 50\n\n"
            "Правила: наберите 21 или близко к 21, не перебирая.\n"
            "До 6 игроков за столом. Каждый играет против дилера."
        )
        return

    try:
        bet = int(parts[1])
    except ValueError:
        await message.reply("❌ Ставка должна быть числом!")
        return

    if bet < 10:
        await message.reply("❌ Минимальная ставка — 10 монет!")
        return

    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user)
        user = await get_user(message.from_user.id)

    bj_bal = user["balance"] if user["balance"] is not None else INITIAL_BALANCE
    if bj_bal < bet:
        await message.reply(f"❌ Недостаточно средств для блэкджека! Баланс: {bj_bal} монет")
        return

    await update_balance(message.from_user.id, -bet, "bj_reserve")

    room_id = f"bj-{uuid.uuid4()}"
    game = BlackjackRoom(room_id, bet, message.from_user.id, message.chat.id)
    game.players[message.from_user.id] = []
    game.player_names[message.from_user.id] = await get_username(message.from_user.id)

    async with active_games_lock:
        active_blackjack_games[room_id] = game
    await save_active_game(room_id, "blackjack", message.from_user.id, 0, bet)

    players_str = await get_username(message.from_user.id)
    msg = await message.answer(
        f"🃏 <b>Блэкджек стол!</b>\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"👤 Игроки за столом:\n{players_str}\n\n"
        f"Нажмите «Присоединиться» или «Старт» для начала.",
        reply_markup=blackjack_join_keyboard(room_id),
    )
    game.join_message_id = msg.message_id
    game.phase = "joining"

    asyncio.ensure_future(blackjack_join_timeout(room_id, 60))


async def blackjack_join_timeout(room_id: str, delay: int):
    await asyncio.sleep(delay)
    async with active_games_lock:
        game = active_blackjack_games.get(room_id)
        if not game or game.is_finished or game.phase != "joining":
            return
        if len(game.players) < 2:
            try:
                await get_bot().send_message(game.chat_id, "⏰ Никто не присоединился. Нажмите «Старт» чтобы играть соло против дилера.")
            except Exception:
                pass


@router.callback_query(F.data.startswith("bj_join_"))
async def cb_bj_join(call: CallbackQuery):
    room_id = call.data.split("_", 2)[2]
    async with active_games_lock:
        game = active_blackjack_games.get(room_id)
        if not game or game.is_finished or game.phase != "joining":
            await call.answer("❌ Игра уже началась или завершена!", show_alert=True)
            return

        if call.from_user.id in game.players:
            await call.answer("✅ Вы уже за этим столом!", show_alert=True)
            return

        if len(game.players) >= 6:
            await call.answer("❌ За столом уже 6 игроков!", show_alert=True)
            return

        user = await get_user(call.from_user.id)
        if not user:
            await create_user(call.from_user)
            user = await get_user(call.from_user.id)

        bj_bal = user["balance"] if user["balance"] is not None else INITIAL_BALANCE
        if bj_bal < game.bet:
            await call.answer("❌ Недостаточно средств для блэкджека!", show_alert=True)
            return

        await update_balance(call.from_user.id, -game.bet, "bj_reserve")
        game.players[call.from_user.id] = []
        game.player_names[call.from_user.id] = await get_username(call.from_user.id)

    players_list = "\n".join(game.player_names.values())
    try:
        await get_bot().edit_message_text(
            chat_id=game.chat_id,
            message_id=game.join_message_id,
            text=(
                f"🃏 <b>Блэкджек стол!</b>\n"
                f"💵 Ставка: {game.bet} монет\n\n"
                f"👤 Игроки за столом ({len(game.players)}/6):\n{players_list}\n\n"
                f"Нажмите «Старт» для начала игры."
            ),
            reply_markup=blackjack_join_keyboard(room_id),
        )
    except Exception:
        pass

    await call.answer("✅ Вы присоединились к блэкджеку!")


@router.callback_query(F.data.startswith("bj_start_"))
async def cb_bj_start(call: CallbackQuery):
    room_id = call.data.split("_", 2)[2]
    async with active_games_lock:
        game = active_blackjack_games.get(room_id)
        if not game or game.is_finished:
            try:
                conn = await get_db()
                cur = await conn.execute("SELECT * FROM active_game_sessions WHERE room_id = ? AND state = 'active'", (room_id,))
                row = await cur.fetchone()
                await conn.close()
                if row and row["game_type"] == "blackjack":
                    chat_id = call.message.chat.id
                    bet = row["bet"]
                    p1 = row["player1"]
                    game = BlackjackRoom(room_id, bet, p1, chat_id)
                    game.players[p1] = []
                    game.player_names[p1] = await get_username(p1)
                    game.phase = "joining"
                    active_blackjack_games[room_id] = game
                    logger.info(f"bj_start: recovered game {room_id} from DB")
                else:
                    await call.answer("❌ Игра не найдена!", show_alert=True)
                    return
            except Exception as e:
                logger.exception(f"bj_start recovery error: {e}")
                await call.answer("❌ Игра не найдена!", show_alert=True)
                return

        if call.from_user.id != game.creator_id:
            await call.answer("❌ Только создатель стола может начать игру!", show_alert=True)
            return

        if game.phase != "joining":
            await call.answer("❌ Игра уже началась!", show_alert=True)
            return

        if len(game.players) < 1:
            await call.answer("❌ Нет игроков за столом!", show_alert=True)
            return

        game.phase = "playing"

    await start_blackjack_round(game)
    await call.answer()


async def start_blackjack_round(game: BlackjackRoom):
    game.deck = create_deck()
    game.dealer_cards = [draw_card(game.deck), draw_card(game.deck)]

    for pid in game.players:
        game.players[pid] = [draw_card(game.deck), draw_card(game.deck)]
        game.player_status[pid] = "playing"

    dealer_visible = cards_str([game.dealer_cards[0]]) + "🂠"
    players_text = ""
    for pid, cards in game.players.items():
        name = game.player_names[pid]
        val = hand_value(cards)
        emoji = hand_emoji(val)
        players_text += f"{emoji} {name}: {cards_str(cards)} = <b>{val}</b>\n"

    text = (
        f"🃏 <b>Блэкджек начался!</b>\n"
        f"💵 Ставка: {game.bet} 🪙\n\n"
        f"🎴 Дилер: {dealer_visible}\n\n"
        f"👤 Игроки:\n{players_text}\n"
        f"➖➖➖➖➖➖\n"
        f"⏳ Первым ходит: {game.player_names[game.creator_id]}"
    )

    try:
        if game.join_message_id and game.chat_id:
            await get_bot().delete_message(game.chat_id, game.join_message_id)
    except Exception:
        pass

    bot_user = await get_bot().me()
    pm_url = f"https://t.me/{bot_user.username}"
    sent = await get_bot().send_message(
        game.chat_id, text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Перейти в ЛС", url=pm_url)]
        ]),
    )
    game.message_id = sent.message_id

    await ask_bj_player_decision(game, game.creator_id)


async def cancel_bj_timer(game: BlackjackRoom):
    if game.timer_task and not game.timer_task.done():
        current = asyncio.current_task()
        if game.timer_task is not current:
            game.timer_task.cancel()
        game.timer_task = None
    if game.timer_message_id:
        try:
            await get_bot().delete_message(game.chat_id, game.timer_message_id)
        except Exception:
            pass
        game.timer_message_id = None


async def bj_player_timer(game: BlackjackRoom, player_id: int, total: int = 30):
    try:
        for remaining in range(total, 0, -1):
            if game.is_finished or game.player_status.get(player_id) != "playing":
                return
            game.timer_seconds = remaining
            if remaining % 5 == 0 or remaining <= 5:
                text = f"⏱ <b>{game.player_names[player_id]}</b>: <b>{remaining}</b> сек осталось"
                if game.timer_message_id:
                    try:
                        await get_bot().edit_message_text(text, chat_id=game.chat_id, message_id=game.timer_message_id)
                    except Exception:
                        try:
                            sent = await get_bot().send_message(game.chat_id, text)
                            game.timer_message_id = sent.message_id
                        except Exception:
                            pass
                else:
                    try:
                        sent = await get_bot().send_message(game.chat_id, text)
                        game.timer_message_id = sent.message_id
                    except Exception:
                        pass
            await asyncio.sleep(1)

        if not game.is_finished and game.player_status.get(player_id) == "playing":
            name = game.player_names[player_id]
            game.player_status[player_id] = "stand"
            await get_bot().send_message(game.chat_id, f"⏰ <b>{name}</b> — время вышло! Авто-стоп.")
            await next_bj_player(game, player_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Ошибка в таймере блэкджека (player={player_id}): {e}")
        try:
            await get_bot().send_message(game.chat_id, "❌ Ошибка в таймере, игра завершена.")
        except Exception:
            pass
        game.is_finished = True
        game.phase = "finished"
        async with active_games_lock:
            if game.room_id in active_blackjack_games:
                del active_blackjack_games[game.room_id]
        await delete_active_game(game.room_id)


async def ask_bj_player_decision(game: BlackjackRoom, player_id: int):
    await cancel_bj_timer(game)
    game.current_player = player_id

    cards = game.players[player_id]
    val = hand_value(cards)
    name = game.player_names[player_id]

    if val == 21:
        game.player_status[player_id] = "stand"
        await get_bot().send_message(game.chat_id, f"🎉 {name} набрал 21! Авто-стоп.")
        await next_bj_player(game, player_id)
        return

    if val > 21:
        game.player_status[player_id] = "bust"
        await get_bot().send_message(game.chat_id, f"💥 {name} перебрал ({val})! Вы проиграли.")
        await next_bj_player(game, player_id)
        return

    game.timer_task = asyncio.ensure_future(bj_player_timer(game, player_id, 30))

    try:
        await get_bot().send_message(
            player_id,
            f"🃏 <b>Ваш ход!</b>\n"
            f"💵 Ставка: {game.bet} 🪙\n"
            f"🎴 Ваши карты: {cards_str(cards)} = <b>{val}</b>\n"
            f"🎴 Дилер: {cards_str([game.dealer_cards[0]])} + 🂠\n\n"
            f"⏱ У вас 30 секунд!\n"
            f"👊 Ещё — взять карту\n"
            f"✋ Стоп — оставить как есть",
            reply_markup=blackjack_action_keyboard(game.room_id, player_id),
        )
    except Exception:
        await get_bot().send_message(
            game.chat_id,
            f"⏭ {name} недоступен в ЛС. Авто-стоп.",
        )
        game.player_status[player_id] = "stand"
        await cancel_bj_timer(game)
        await next_bj_player(game, player_id)


async def next_bj_player(game: BlackjackRoom, current_player_id: int):
    await cancel_bj_timer(game)
    player_ids = list(game.players.keys())
    current_idx = player_ids.index(current_player_id)
    next_idx = current_idx + 1

    while next_idx < len(player_ids):
        next_pid = player_ids[next_idx]
        if game.player_status.get(next_pid) == "playing":
            await ask_bj_player_decision(game, next_pid)
            return
        next_idx += 1

    await play_bj_dealer(game)


@router.callback_query(F.data.startswith("bj_hit_"))
async def cb_bj_hit(call: CallbackQuery):
    parts = call.data.split("_")
    room_id = parts[2]
    player_id = int(parts[3])

    if call.from_user.id != player_id:
        await call.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return

    async with active_games_lock:
        game = active_blackjack_games.get(room_id)
        if not game or game.is_finished or game.phase != "playing":
            await call.answer("❌ Игра завершена!", show_alert=True)
            return

        if game.player_status.get(player_id) != "playing":
            await call.answer("❌ Вы уже остановились!", show_alert=True)
            return

        card = draw_card(game.deck)
        game.players[player_id].append(card)
        val = hand_value(game.players[player_id])
        name = game.player_names[player_id]
        cards = game.players[player_id]

    await cancel_bj_timer(game)
    await call.message.edit_text(f"🎴 {name} берёт: {cards_str(cards)} = <b>{val}</b>")

    if val > 21:
        game.player_status[player_id] = "bust"
        await get_bot().send_message(game.chat_id, f"💥 {name} перебрал {hand_emoji(val)} (<b>{val}</b>)")
        await next_bj_player(game, player_id)
    elif val == 21:
        game.player_status[player_id] = "stand"
        await get_bot().send_message(game.chat_id, f"🃏 {name} набрал 21! Blackjack!")
        await next_bj_player(game, player_id)
    else:
        await ask_bj_player_decision(game, player_id)

    await call.answer()


@router.callback_query(F.data.startswith("bj_stand_"))
async def cb_bj_stand(call: CallbackQuery):
    parts = call.data.split("_")
    room_id = parts[2]
    player_id = int(parts[3])

    if call.from_user.id != player_id:
        await call.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return

    async with active_games_lock:
        game = active_blackjack_games.get(room_id)
        if not game or game.is_finished or game.phase != "playing":
            await call.answer("❌ Игра завершена!", show_alert=True)
            return

        if game.player_status.get(player_id) != "playing":
            await call.answer("❌ Вы уже остановились!", show_alert=True)
            return

        game.player_status[player_id] = "stand"
        name = game.player_names[player_id]
        cards = game.players[player_id]
        val = hand_value(cards)

    await cancel_bj_timer(game)
    await call.message.edit_text(f"✋ {name} остановился. Очки: <b>{val}</b>")
    await next_bj_player(game, player_id)
    await call.answer()


async def play_bj_dealer(game: BlackjackRoom):
    await cancel_bj_timer(game)
    dealer = game.dealer_cards
    dealer_val = hand_value(dealer)
    while dealer_val < 17:
        card = draw_card(game.deck)
        dealer.append(card)
        dealer_val = hand_value(dealer)

    dealer_str = cards_str(dealer)
    result = (
        f"🎴 <b>Дилер:</b> {dealer_str} = <b>{dealer_val}</b>\n"
        f"➖➖➖➖➖➖\n"
        f"📊 <b>Результаты:</b>\n"
    )

    for pid, cards in game.players.items():
        name = game.player_names[pid]
        player_val = hand_value(cards)
        if player_val > 21:
            result += f"❌ {name}: <b>{player_val}</b> — перебор\n"
        elif dealer_val > 21 or player_val > dealer_val:
            result += f"🏆 {name}: <b>{player_val}</b> — победа! +{game.bet * 2} 🪙\n"
            await update_balance(pid, game.bet * 2, "bj_win")
        elif player_val == dealer_val:
            result += f"🎭 {name}: <b>{player_val}</b> — ничья\n"
            await update_balance(pid, game.bet, "bj_tie")
        else:
            result += f"❌ {name}: <b>{player_val}</b> — проигрыш\n"

    if len(result) > MAX_MSG_LEN:
        result = result[:MAX_MSG_LEN] + "\n\n... (обрезано)"
    await get_bot().send_message(game.chat_id, result)
    game.is_finished = True
    game.phase = "finished"

    async with active_games_lock:
        if game.room_id in active_blackjack_games:
            del active_blackjack_games[game.room_id]
    await delete_active_game(game.room_id)


@router.callback_query(F.data.startswith("casino_bj_bet_"))
async def cb_casino_bj_bet(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type == "private":
        await call.answer("❌ Блэкджек только в группах!", show_alert=True)
        return

    from .base import GameStates as BJBetState

    bet_str = call.data.split("_", 3)[3]

    if bet_str == "custom":
        await state.set_state(BJBetState.waiting_for_bet)
        await state.update_data(game_type="blackjack")
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

    bj_bal = user["balance"] if user["balance"] is not None else INITIAL_BALANCE
    if bj_bal < bet:
        await call.answer(f"❌ Недостаточно средств! Баланс: {bj_bal}", show_alert=True)
        return

    await update_balance(call.from_user.id, -bet, "bj_reserve")

    room_id = f"bj-{uuid.uuid4()}"
    game = BlackjackRoom(room_id, bet, call.from_user.id, call.message.chat.id)
    game.players[call.from_user.id] = []
    game.player_names[call.from_user.id] = await get_username(call.from_user.id)

    async with active_games_lock:
        active_blackjack_games[room_id] = game
    await save_active_game(room_id, "blackjack", call.from_user.id, 0, bet)

    sent = await call.message.answer(
        f"🃏 <b>Блэкджек стол!</b>\n"
        f"💵 Ставка: {bet} 🪙\n"
        f"👤 {game.player_names[call.from_user.id]} (создатель)\n"
        f"👥 Места: 1/6\n\n"
        f"⏳ Ожидание игроков...\n\n"
        f"Нажмите «Присоединиться» или «Старт» для начала.",
        reply_markup=blackjack_join_keyboard(room_id),
    )
    game.join_message_id = sent.message_id
    game.phase = "joining"
    await call.message.delete()
    await call.answer()
    asyncio.ensure_future(blackjack_join_timeout(room_id, 60))
