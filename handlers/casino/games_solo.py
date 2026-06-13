import asyncio
import logging
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from .base import (
    get_bot, get_db, get_user, create_user, update_bot_balance, get_username,
    GAMES_CONFIG, INITIAL_BOT_BALANCE, SoloBetState, logger,
    save_active_game, delete_active_game,
)
from .keyboards import solo_bet_selection_kb

router = Router()

# Временные состояния игр с ботом
_solo_games: dict[int, dict] = {}


@router.message(Command("сботом"))
@router.message(Command("solo"))
async def cmd_solo_bot(message: Message):
    if message.chat.type != "private":
        await message.reply("🤖 Игра с ботом доступна только в ЛС! Напишите боту в личку.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        text = "🤖 <b>Игра с ботом</b>\n\nФормат: `/сботом [игра] [ставка]`\n\n"
        for game_type, cfg in GAMES_CONFIG.items():
            text += f"/сботом {cfg['command']} [ставка] — {game_type} {cfg['emoji']}\n"
        text += "\nПример: `/сботом куб 50`\n\n"
        text += "Бот кидает кубик одновременно. Кто выиграл — забирает ставку."
        await message.reply(text)
        return

    cmd = parts[1].lower()
    game_type = None
    for gt, cfg in GAMES_CONFIG.items():
        if cfg["command"] == cmd:
            game_type = gt
            break
    if not game_type:
        await message.reply(f"❌ Игра «{cmd}» не найдена. Доступные: {', '.join(cfg['command'] for cfg in GAMES_CONFIG.values())}")
        return

    if len(parts) < 3:
        await message.reply(f"❌ Укажите ставку. Пример: `/сботом {cmd} 50`")
        return

    try:
        bet = int(parts[2])
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

    await solo_game_play(message, game_type, bet)


async def solo_game_play(message: Message, game_type: str, bet: int, user_id: int = None):
    uid = user_id or message.from_user.id
    user = await get_user(uid)
    if not user:
        from aiogram.types import User
        await create_user(User(id=uid, first_name="Player", is_bot=False, username=f"user_{uid}"))
        user = await get_user(uid)

    bal = user["bot_balance"]
    if bal is None:
        bal = INITIAL_BOT_BALANCE
    if bal < bet:
        await message.reply(f"❌ Недостаточно средств! Баланс: {bal} монет для игры с ботом")
        return

    # Если у юзера уже есть активная игра — не даём начать новую
    if uid in _solo_games:
        await message.reply("❌ У вас уже есть активная игра! Завершите её.")
        return

    await update_bot_balance(uid, -bet, "solo_reserve")

    config = GAMES_CONFIG[game_type]
    player_tag = await get_username(uid)

    msg = await message.reply(
        f"🤖 <b>Игра с ботом</b> {config['emoji']}\n"
        f"💵 Ставка: {bet} монет\n"
        f"💰 Ваш счёт: {bal} монет\n\n"
        f"{player_tag}, нажмите кнопку👇 или отправьте {config['emoji']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Бросить {config['emoji']}", callback_data=f"solo_roll_{uid}")]
        ])
    )

    _solo_games[uid] = {"game_type": game_type, "bet": bet, "msg": msg, "player_tag": player_tag, "bal": bal}
    await save_active_game(f"solo_{uid}", "solo", uid, 0, bet, message.chat.id, msg.message_id)


async def _process_solo_roll(msg: Message, uid: int, game_state: dict):
    """Выполняет бросок пользователя и ответный бросок бота."""
    game_type = game_state["game_type"]
    bet = game_state["bet"]
    player_tag = game_state["player_tag"]
    bal = game_state["bal"]
    config = GAMES_CONFIG[game_type]
    conn = None
    player_dice = None
    bot_dice_msg = None

    try:
        def _result_label(val: int) -> str:
            if game_type == "футбол":
                return "⚽ ГОЛ!" if val > 3 else "❌ Промах"
            if game_type == "баскетбол":
                return "🏀 Попадание!" if val > 3 else "❌ Промах"
            return str(val)

        # Убираем кнопку — ждём результат
        await game_state["msg"].edit_text(
            f"🤖 <b>Игра с ботом</b> {config['emoji']}\n"
            f"💵 Ставка: {bet} монет\n"
            f"💰 Ваш счёт: {bal} монет\n\n"
            f"{player_tag} бросает..."
        )

        await asyncio.sleep(0.5)
        player_dice = await msg.answer_dice(emoji=config["emoji"])
        await asyncio.sleep(5)

        player_raw = player_dice.dice.value
        player_adj = player_raw - 1 if game_type in ("дротики", "боулинг") else player_raw

        await game_state["msg"].edit_text(
            f"🤖 <b>Игра с ботом</b> {config['emoji']}\n"
            f"💵 Ставка: {bet} монет\n\n"
            f"{player_tag}: {_result_label(player_adj)}\n"
            f"🤖 Бот бросает..."
        )

        bot_dice_msg = await msg.answer_dice(emoji=config["emoji"])
        bot_dice = bot_dice_msg.dice.value
        await asyncio.sleep(5)

        bot_adj = bot_dice - 1 if game_type in ("дротики", "боулинг") else bot_dice

        await game_state["msg"].edit_text(
            f"🤖 <b>Игра с ботом</b> {config['emoji']}\n"
            f"💵 Ставка: {bet} монет\n\n"
            f"{player_tag}: {_result_label(player_adj)}\n"
            f"🤖 Бот: {_result_label(bot_adj)}"
        )

        await asyncio.sleep(1)
        new_user = await get_user(uid)
        new_bal = new_user["bot_balance"] if new_user else bal

        def is_player_win() -> str:
            if game_type in ("футбол", "баскетбол"):
                p_hit = player_adj > 3
                b_hit = bot_adj > 3
                if p_hit and not b_hit: return "win"
                if b_hit and not p_hit: return "lose"
                return "tie"
            if player_adj > bot_adj: return "win"
            if bot_adj > player_adj: return "lose"
            return "tie"

        result = is_player_win()
        if result == "win":
            prize = bet * 2
            await update_bot_balance(uid, prize, "solo_win")
            await msg.answer(
                f"🏆 <b>Вы выиграли!</b> +{prize} монет\n"
                f"💰 Ваш счёт: {new_bal + prize} монет",
                reply_markup=_after_game_kb(game_type),
            )
            conn = await get_db()
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET score = score + ?, games_played = games_played + 1",
                (uid, player_tag, prize, prize),
            )
            await conn.commit()
        elif result == "lose":
            await update_bot_balance(uid, 0, "solo_lose")
            await msg.answer(
                f"❌ <b>Бот выиграл!</b> -{bet} монет\n"
                f"💰 Ваш счёт: {new_bal} монет",
                reply_markup=_after_game_kb(game_type),
            )
            conn = await get_db()
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, 0, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET games_played = games_played + 1",
                (uid, player_tag),
            )
            await conn.commit()
        else:
            await update_bot_balance(uid, bet, "solo_tie")
            await msg.answer(
                f"🎭 <b>Ничья!</b> Ставка возвращена.\n"
                f"💰 Ваш счёт: {new_bal + bet} монет",
                reply_markup=_after_game_kb(game_type),
            )
            conn = await get_db()
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET score = score + ?, games_played = games_played + 1",
                (uid, player_tag, bet, bet),
            )
            await conn.commit()

    except Exception as e:
        logger.error(f"Solo roll error for {uid}: {e}")
    finally:
        # Cleanup: delete dice animation messages
        try:
            await asyncio.sleep(1)
            cleanup_ids = []
            if player_dice and hasattr(player_dice, 'message_id'):
                cleanup_ids.append(player_dice.message_id)
            if bot_dice_msg and hasattr(bot_dice_msg, 'message_id'):
                cleanup_ids.append(bot_dice_msg.message_id)
            for mid in cleanup_ids:
                try:
                    await msg.bot.delete_message(msg.chat.id, mid)
                except:
                    pass
        except:
            pass

        if conn:
            try:
                await conn.close()
            except Exception:
                pass

        # Удаляем из активных игр
        _solo_games.pop(uid, None)
        await delete_active_game(f"solo_{uid}")


def _after_game_kb(game_type: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎮 Играть ещё {GAMES_CONFIG[game_type]['emoji']}", callback_data=f"casino_solo_pick_{game_type}"),
         InlineKeyboardButton(text="🎲 Другие игры", callback_data="casino_play_bot")],
        [InlineKeyboardButton(text="🏠 Казино", callback_data="casino_menu")],
    ])


@router.callback_query(F.data.startswith("solo_roll_"))
async def cb_solo_roll(call: CallbackQuery):
    uid = call.from_user.id
    game = _solo_games.get(uid)
    if not game:
        await call.answer("❌ Игра не найдена или уже завершена", show_alert=True)
        return
    await call.answer()
    await _process_solo_roll(call.message, uid, game)


@router.message(F.text.in_(list({cfg["emoji"]: gt for gt, cfg in GAMES_CONFIG.items()}.keys())))
async def solo_emoji_throw(message: Message):
    uid = message.from_user.id
    game = _solo_games.get(uid)
    if not game:
        return
    text = message.text.strip()
    cfg = GAMES_CONFIG[game["game_type"]]
    if text != cfg["emoji"]:
        return
    await _process_solo_roll(message, uid, game)


@router.callback_query(F.data.startswith("casino_solo_pick_"))
async def cb_casino_solo_pick(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("❌ Игра с ботом только в ЛС!", show_alert=True)
        return
    parts = call.data.split("_", 3)
    game_type = parts[3]
    if game_type not in GAMES_CONFIG:
        await call.answer("❌ Игра не найдена!", show_alert=True)
        return
    cfg = GAMES_CONFIG[game_type]
    await call.message.edit_text(
        f"<b>{cfg['emoji']} {game_type.capitalize()} — с ботом</b>\n\n"
        f"Выберите ставку:",
        parse_mode="HTML",
        reply_markup=solo_bet_selection_kb(game_type),
    )
    await call.answer()


@router.callback_query(F.data.startswith("casino_solo_bet_"))
async def cb_casino_solo_bet(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type != "private":
        await call.answer("❌ Игра с ботом только в ЛС!", show_alert=True)
        return
    parts = call.data.split("_", 3)
    remaining = parts[3]
    game_type, bet_str = remaining.split("_", 1)

    if game_type not in GAMES_CONFIG:
        await call.answer("❌ Игра не найдена!", show_alert=True)
        return

    if bet_str == "custom":
        await state.set_state(SoloBetState.waiting_for_bet)
        await state.update_data(game_type=game_type)
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

    await call.message.edit_text(f"🎲 <b>{GAMES_CONFIG[game_type]['emoji']} Игра с ботом</b>\nЗапускаем...")
    await call.answer()
    await solo_game_play(call.message, game_type, bet, call.from_user.id)


@router.message(SoloBetState.waiting_for_bet)
async def process_solo_custom_bet(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.startswith("/"):
        await state.clear()
        return

    data = await state.get_data()
    game_type = data.get("game_type")
    if not game_type:
        await message.answer("❌ Ошибка: не выбран тип игры.")
        await state.clear()
        return

    try:
        bet = int(text)
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return

    if bet < 10:
        await message.answer("❌ Минимальная ставка — 10!")
        return

    await state.clear()
    await solo_game_play(message, game_type, bet)
