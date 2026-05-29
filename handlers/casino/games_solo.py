import asyncio
import logging
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_bot_balance, get_username,
    GAMES_CONFIG, INITIAL_BOT_BALANCE, SoloBetState, logger,
)
from .keyboards import solo_bet_selection_kb

router = Router()


@router.message(Command("сботом"))
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


async def solo_game_play(message: Message, game_type: str, bet: int):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user)
        user = await get_user(message.from_user.id)

    bal = user["bot_balance"]
    if bal is None:
        bal = INITIAL_BOT_BALANCE
    if bal < bet:
        await message.reply(f"❌ Недостаточно средств! Баланс: {bal} монет для игры с ботом")
        return

    await update_bot_balance(message.from_user.id, -bet, "solo_reserve")

    config = GAMES_CONFIG[game_type]
    player_name = message.from_user.first_name or f"Игрок {message.from_user.id}"

    msg = await message.reply(
        f"🎲 <b>Игра с ботом</b> {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"{player_name} бросает..."
    )

    player_dice = await message.answer_dice(emoji=config["emoji"])
    await asyncio.sleep(4.5)

    await msg.edit_text(
        f"🎲 <b>Игра с ботом</b> {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"{player_name}: {player_dice.dice.value}\n"
        f"🤖 Бот бросает..."
    )

    bot_dice_msg = await message.answer_dice(emoji=config["emoji"])
    bot_dice = bot_dice_msg.dice.value
    await asyncio.sleep(4.5)

    bot_adjusted = bot_dice - 1 if game_type in ("дротики", "боулинг") else bot_dice
    player_adjusted = player_dice.dice.value - 1 if game_type in ("дротики", "боулинг") else player_dice.dice.value

    await msg.edit_text(
        f"🎲 <b>Игра с ботом</b> {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"{player_name}: {player_adjusted}\n"
        f"🤖 Бот: {bot_adjusted}"
    )

    conn = None
    if player_adjusted > bot_adjusted:
        prize = bet * 2
        await update_bot_balance(message.from_user.id, prize, "solo_win")
        await message.answer(f"🏆 <b>Вы выиграли!</b> +{prize} монет")
        conn = await get_db()
        try:
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET score = score + ?, games_played = games_played + 1",
                (message.from_user.id, message.from_user.username or f"user_{message.from_user.id}", prize, prize),
            )
            await conn.commit()
        except Exception:
            pass
    elif bot_adjusted > player_adjusted:
        await update_bot_balance(message.from_user.id, 0, "solo_lose")
        await message.answer(f"❌ <b>Бот выиграл!</b> -{bet} монет")
        conn = await get_db()
        try:
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, 0, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET games_played = games_played + 1",
                (message.from_user.id, message.from_user.username or f"user_{message.from_user.id}"),
            )
            await conn.commit()
        except Exception:
            pass
    else:
        await update_bot_balance(message.from_user.id, bet, "solo_tie")
        await message.answer(f"🎭 <b>Ничья!</b> Ставка возвращена.")
        conn = await get_db()
        try:
            await conn.execute(
                "INSERT INTO solo_scores (user_id, username, score, games_played) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET score = score + ?, games_played = games_played + 1",
                (message.from_user.id, message.from_user.username or f"user_{message.from_user.id}", bet, bet),
            )
            await conn.commit()
        except Exception:
            pass

    if conn:
        try:
            await conn.close()
        except Exception:
            pass


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
    await solo_game_play(call.message, game_type, bet)


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
