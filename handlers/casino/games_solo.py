import asyncio
import logging
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_bot_balance, get_username,
    GAMES_CONFIG, INITIAL_BOT_BALANCE, logger,
)

router = Router()


@router.message(Command("сботом"))
async def cmd_solo_bot(message: Message):
    if message.chat.type != "private":
        await message.reply("🤖 Игра с ботом доступна только в ЛС! Напишите боту в личку.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        text = "🤖 **Игра с ботом**\n\nФормат: `/сботом [игра] [ставка]`\n\n"
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

    bal = user.get("bot_balance")
    if bal is None:
        bal = INITIAL_BOT_BALANCE
    if bal < bet:
        await message.reply(f"❌ Недостаточно средств! Баланс: {bal} монет для игры с ботом")
        return

    await update_bot_balance(message.from_user.id, -bet, "solo_reserve")

    config = GAMES_CONFIG[game_type]
    player_name = await get_username(message.from_user.id)

    msg = await message.reply(
        f"🎲 **Игра с ботом** {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"{player_name} бросает..."
    )

    player_dice = await message.answer_dice(emoji=config["emoji"])
    await asyncio.sleep(2)

    bot_dice = random.randint(1, 6)
    bot_adjusted = bot_dice - 1 if game_type in ("дротики", "боулинг") else bot_dice
    player_adjusted = player_dice.dice.value - 1 if game_type in ("дротики", "боулинг") else player_dice.dice.value

    await msg.edit_text(
        f"🎲 **Игра с ботом** {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n\n"
        f"{player_name}: {player_adjusted}\n"
        f"🤖 Бот: {bot_adjusted}"
    )

    winner = None
    if player_adjusted > bot_adjusted:
        winner = message.from_user.id
        prize = bet * 2
        await update_bot_balance(message.from_user.id, prize, "solo_win")
        await message.answer(f"🏆 **Вы выиграли!** +{prize} монет")
    elif bot_adjusted > player_adjusted:
        await message.answer(f"❌ **Бот выиграл!** -{bet} монет")
    else:
        await update_bot_balance(message.from_user.id, bet, "solo_tie")
        await message.answer(f"🎭 **Ничья!** Ставка возвращена.")

    if winner:
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
        finally:
            await conn.close()
