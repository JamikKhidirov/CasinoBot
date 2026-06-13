import asyncio
import logging
import uuid
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, get_username,
    GAMES_CONFIG, GameRoom, BlackjackRoom, active_games, active_blackjack_games, active_games_lock,
    GameStates, COMMISSION_RATE, INITIAL_BALANCE, logger,
    save_active_game, delete_active_game,
)
from .keyboards import blackjack_join_keyboard
from .blackjack import blackjack_join_timeout

router = Router()


async def create_game_for_user(message: Message, tg_user, user_id: int, game_type: str, bet: int):
    if message.chat.type == "private":
        bot_username = (await get_bot().me()).username
        text = (
            "👥 <b>Игра с игроками</b> доступна <b>только в групповых чатах</b>!\n\n"
            "📌 <b>Как играть:</b>\n"
            "1. Добавьте бота в группу: @{}\n"
            "2. Напишите в группе команду\n\n"
            "🤖 <b>Хотите сыграть с ботом?</b> Используйте `/сботом {} [ставка]` в ЛС!"
        ).format(bot_username, GAMES_CONFIG[game_type]["command"])
        await message.reply(text)
        return

    user = await get_user(user_id)
    if not user:
        await create_user(tg_user)
        user = await get_user(user_id)

    if user["balance"] < bet:
        await message.reply(f"❌ Недостаточно средств! Баланс: {user['balance']} монет")
        return

    await update_balance(user_id, -bet, "reserve")

    room_id = str(uuid.uuid4())
    game = GameRoom(room_id, game_type, bet, user_id)
    game.chat_id = message.chat.id

    async with active_games_lock:
        for g in active_games.values():
            if not g.is_finished and user_id in (g.player1, g.player2):
                await update_balance(user_id, bet, "refund")
                await message.reply("❌ Вы уже участвуете в другой игре!")
                return
        active_games[room_id] = game
        await save_active_game(room_id, game_type, user_id, 0, bet)

    config = GAMES_CONFIG[game_type]
    p1_name = await get_username(user_id)

    sent = await message.reply(
        f"🎉 <b>Новая игра</b> в {config['emoji']}!\n"
        f"💵 Ставка: {bet} монет\n"
        f"⏳ Ожидание второго игрока...\n\n"
        f"Игрок 1: {p1_name}\n"
        f"Места: 1/2\n\n"
        f"Игра отменится через 30 секунд, если никто не присоединится.",
        reply_markup=game_keyboard(room_id, user_id),
    )
    game.message_id = sent.message_id

    asyncio.ensure_future(game_timeout(room_id, 30))


async def game_timeout(room_id: str, delay: int):
    await asyncio.sleep(delay)
    game = None
    need_auto_roll = False

    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            return

        if game.player2 is None:
            await update_balance(game.player1, game.bet, "refund")
            try:
                await get_bot().edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.message_id,
                    text="⏰ Игра отменена, никто не присоединился.\n💰 Ставка возвращена.",
                )
            except Exception:
                await get_bot().send_message(game.chat_id, "⏰ Игра отменена, никто не присоединился.\n💰 Ставка возвращена.")
            game.is_finished = True
            del active_games[room_id]
            await delete_active_game(room_id)
            return
        else:
            need_auto_roll = True

    if need_auto_roll and game:
        await auto_roll_dice(game)


@router.callback_query(F.data.startswith("join_"))
async def cb_join_game(call: CallbackQuery):
    try:
        joiner_id = call.from_user.id
        room_id = call.data.split("_", 1)[1]
        logger.info(f"join_game: user {joiner_id} пытается присоединиться к {room_id}")

        async with active_games_lock:
            for rid, g in active_games.items():
                if not g.is_finished and joiner_id in (g.player1, g.player2) and rid != room_id:
                    await call.answer("❌ Вы уже участвуете в другой игре!", show_alert=True)
                    return

            game = active_games.get(room_id)
            if not game or game.is_finished or game.player2 is not None:
                await call.answer("❌ Игра уже началась или завершена!", show_alert=True)
                return

            user = await get_user(joiner_id)
            if not user or user["balance"] < game.bet:
                await call.answer("❌ Недостаточно средств для присоединения!", show_alert=True)
                return

            if game.player1 == joiner_id:
                await call.answer("❌ Вы не можете присоединиться к своей же игре!", show_alert=True)
                return

            await update_balance(joiner_id, -game.bet, "reserve")
            game.add_player(joiner_id)
            logger.info(f"join_game: user {joiner_id} присоединился к {room_id}")

        await call.answer("✅ Вы присоединились к игре!")
        await start_game(game)

    except Exception as e:
        logger.exception(f"Ошибка в join_game: {e}")
        await call.answer("❌ Произошла ошибка!", show_alert=True)


@router.callback_query(F.data.startswith("cancelgame_"))
async def cb_cancel_game(call: CallbackQuery):
    room_id = call.data.split("_", 1)[1]
    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            await call.answer("❌ Игра уже завершена!", show_alert=True)
            return
        if call.from_user.id != game.player1:
            await call.answer("❌ Только создатель может отменить игру!", show_alert=True)
            return
        await update_balance(game.player1, game.bet, "refund")
        if game.player2:
            await update_balance(game.player2, game.bet, "refund")
        game.is_finished = True
        del active_games[room_id]
    await call.answer("✅ Игра отменена!")
    try:
        await get_bot().edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text="❌ Игра отменена создателем.",
        )
    except Exception:
        pass


async def start_game(game: GameRoom):
    try:
        logger.info(f"start_game: {game.room_id}, {game.game_type}, bet={game.bet}, p1={game.player1}, p2={game.player2}")
        config = GAMES_CONFIG[game.game_type]
        p1_name = await get_username(game.player1)
        p2_name = await get_username(game.player2)

        text = (
            f"🎉 Игра в {config['emoji']} началась!\n"
            f"💵 Ставка: {game.bet} монет\n"
            f"Игрок 1: {p1_name}\n"
            f"Игрок 2: {p2_name}\n\n"
            f"⏳ Ожидаем бросок от {p1_name}..."
        )

        try:
            await get_bot().edit_message_text(
                chat_id=game.chat_id,
                message_id=game.message_id,
                text=text,
                reply_markup=roll_keyboard(game.room_id, game.player1, config["emoji"]),
            )
        except Exception:
            sent = await get_bot().send_message(game.chat_id, text, reply_markup=roll_keyboard(game.room_id, game.player1, config["emoji"]))
            game.message_id = sent.message_id

        await ask_for_dice_roll(game, game.player1)

    except Exception as e:
        logger.error(f"Ошибка в start_game: {e}")


async def ask_for_dice_roll(game: GameRoom, player_id: int):
    try:
        config = GAMES_CONFIG[game.game_type]
        opponent_id = game.player2 if player_id == game.player1 else game.player1
        opp_name = await get_username(opponent_id)

        msg = await get_bot().send_message(
            player_id,
            f"🎮 Ваш ход против {opp_name} в игре {config['emoji']}!\n"
            f"💵 Ставка: {game.bet} монет\n\n"
            "Нажмите кнопку ниже, чтобы сделать бросок:",
            reply_markup=roll_keyboard(game.room_id, player_id, config["emoji"]),
        )

        if player_id == game.player1:
            game.player1_button_message_id = msg.message_id
        else:
            game.player2_button_message_id = msg.message_id

    except Exception as e:
        logger.error(f"Ошибка при отправке кнопки броска: {e}")


@router.callback_query(F.data.startswith("roll_"))
async def cb_roll_dice(call: CallbackQuery):
    try:
        _, room_id, player_id_str = call.data.split("_", 2)
        player_id = int(player_id_str)

        async with active_games_lock:
            game = active_games.get(room_id)
            if not game or game.is_finished:
                await call.answer("❌ Игра завершена или не найдена!", show_alert=True)
                return

            if call.from_user.id not in (game.player1, game.player2):
                await call.answer("❌ Вы не участник этой игры!", show_alert=True)
                return

            current = game.player1 if game.player1_turn else game.player2
            if call.from_user.id != current:
                await call.answer("❌ Сейчас не ваш ход!", show_alert=True)
                return

            if call.from_user.id in game.results:
                await call.answer("❌ Вы уже сделали бросок!", show_alert=True)
                return

            game.results[call.from_user.id] = -1

        config = GAMES_CONFIG[game.game_type]
        player_name = await get_username(call.from_user.id)

        try:
            if game.last_roll_message_id:
                await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
        except Exception:
            pass

        roll_msg = await get_bot().send_message(game.chat_id, f"{player_name} {config['action']}...")
        game.last_roll_message_id = roll_msg.message_id

        dice_msg = await get_bot().send_dice(game.chat_id, emoji=config["emoji"], disable_notification=True)

        if call.from_user.id == game.player1:
            game.player1_dice_message_id = dice_msg.message_id
        else:
            game.player2_dice_message_id = dice_msg.message_id

        try:
            btn_id = game.player1_button_message_id if call.from_user.id == game.player1 else game.player2_button_message_id
            if btn_id:
                await get_bot().delete_message(call.from_user.id, btn_id)
                if call.from_user.id == game.player1:
                    game.player1_button_message_id = None
                else:
                    game.player2_button_message_id = None
        except Exception:
            pass

        await process_dice_roll(game, call.from_user.id, dice_msg.dice.value)
        await call.answer()

    except Exception as e:
        logger.error(f"Ошибка в roll_dice_callback: {e}")
        await call.answer("❌ Ошибка при броске костей!", show_alert=True)


async def process_dice_roll(game: GameRoom, player_id: int, dice_value: int):
    if game.is_finished:
        return
    if game.results.get(player_id, -1) > 0:
        return
    stored = dice_value - 1 if game.game_type in ("дротики", "боулинг") else dice_value
    game.results[player_id] = stored
    player_name = await get_username(player_id)
    config = GAMES_CONFIG[game.game_type]

    try:
        if game.last_roll_message_id:
            await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
    except Exception:
        pass

    log_value = f"{dice_value}→{stored}" if game.game_type in ("дротики", "боулинг") else str(dice_value)
    logger.info(f"🎲 Бросок в игре {game.game_type}: {player_name} = {log_value} (комната {game.room_id})")

    wait_msg = await get_bot().send_message(game.chat_id, f"⏳ {player_name} {config['action']}, ожидаем результат...")
    game.last_roll_message_id = wait_msg.message_id

    async def show_result():
        try:
            await asyncio.sleep(6)
            try:
                await get_bot().delete_message(game.chat_id, wait_msg.message_id)
            except Exception:
                pass

            adjusted = dice_value - 1 if game.game_type in ("дротики", "боулинг") else dice_value
            score_text = {
                "⚽": f"{'⚽ ГОЛ!' if dice_value > 2 else '❌ Промах!'}",
                "🏀": f"{'🏀 Попадание!' if dice_value > 2 else '❌ Промах!'}",
                "🎯": f"{adjusted}",
                "🎳": f"{adjusted}",
            }.get(config["emoji"], f"{dice_value}")
            result_msg = await get_bot().send_message(
                game.chat_id, f"{player_name}: {score_text} {config['emoji']}"
            )
            game.last_roll_message_id = result_msg.message_id

            if len(game.results) == 2 and all(v >= 0 for v in game.results.values()):
                await determine_winner(game)
            else:
                game.player1_turn = not game.player1_turn
                next_player = game.player2 if player_id == game.player1 else game.player1
                await send_turn_notification(game, next_player)

        except Exception as e:
            logger.error(f"Ошибка при отправке результата: {e}")

    asyncio.ensure_future(show_result())


async def send_turn_notification(game: GameRoom, next_player: int):
    try:
        config = GAMES_CONFIG[game.game_type]
        next_name = await get_username(next_player)

        text = (
            f"🎉 Игра в {config['emoji']} продолжается!\n"
            f"💵 Ставка: {game.bet} монет\n"
            f"Игрок 1: {await get_username(game.player1)}\n"
            f"Игрок 2: {await get_username(game.player2)}\n\n"
            f"⏳ Ожидаем бросок от {next_name}..."
        )

        try:
            await get_bot().edit_message_text(
                chat_id=game.chat_id,
                message_id=game.message_id,
                text=text,
                reply_markup=roll_keyboard(game.room_id, next_player, config["emoji"]),
            )
        except Exception:
            sent = await get_bot().send_message(game.chat_id, text, reply_markup=roll_keyboard(game.room_id, next_player, config["emoji"]))
            game.message_id = sent.message_id

        await ask_for_dice_roll(game, next_player)

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о ходе: {e}")


async def determine_winner(game: GameRoom):
    try:
        if game.is_finished:
            return
        await asyncio.sleep(3)

        p1_score = game.results.get(game.player1, 0)
        p2_score = game.results.get(game.player2, 0) if game.player2 in game.results else None

        total_bet = game.bet * 2
        commission = int(total_bet * COMMISSION_RATE)
        prize = total_bet - commission

        winner = None
        result_msg = ""

        if p2_score is None:
            await update_balance(game.player1, game.bet, "refund")
            if game.player2:
                await update_balance(game.player2, game.bet, "refund")
                result_msg = "⏰ Игра отменена — один из игроков не сделал бросок.\nСтавки возвращены обоим игрокам."
            else:
                result_msg = "⏰ Игра отменена — никто не присоединился."
        else:
            is_goal_game = game.game_type in ("футбол", "баскетбол")
            if is_goal_game:
                p1_hit = p1_score > 2
                p2_hit = p2_score > 2
                if p1_hit and p2_hit:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = f"{GAMES_CONFIG[game.game_type]['emoji']} Оба забили! Ничья — ставки возвращены."
                elif p1_hit:
                    winner = game.player1
                elif p2_hit:
                    winner = game.player2
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = f"{GAMES_CONFIG[game.game_type]['emoji']} Оба промахнулись! Ничья — ставки возвращены."
            elif game.game_type in ("дротики", "боулинг"):
                if p1_score > p2_score:
                    winner = game.player1
                elif p2_score > p1_score:
                    winner = game.player2
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🎭 Ничья! Ставки возвращены."
            else:
                if p1_score > p2_score:
                    winner = game.player1
                elif p2_score > p1_score:
                    winner = game.player2
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🎭 Ничья! Ставки возвращены."

            if winner and not result_msg:
                await update_balance(winner, prize, "win")
                emoji = GAMES_CONFIG[game.game_type]["emoji"]
                result_msg = (
                    f"🏆 Победитель: {await get_username(winner)}\n"
                    f"💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                )
                conn = await get_db()
                try:
                    await conn.execute(
                        "UPDATE users SET games_played = games_played + 1, wins = wins + 1 WHERE user_id = ?",
                        (winner,),
                    )
                    loser_id = game.player2 if winner == game.player1 else game.player1
                    if loser_id:
                        await conn.execute(
                            "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
                            (loser_id,),
                        )
                    await conn.commit()
                except Exception:
                    pass
                finally:
                    await conn.close()

        p1_label = str(p1_score)
        p2_label = str(p2_score)
        if game.game_type in ("футбол", "баскетбол"):
            p1_label = "✅ Гол" if p1_score > 2 else "❌ Промах"
            p2_label = "✅ Гол" if p2_score > 2 else "❌ Промах"
        elif game.game_type in ("дротики", "боулинг"):
            p1_label = f"🎯 {p1_score}"
            p2_label = f"🎯 {p2_score}"

        emoji = GAMES_CONFIG[game.game_type]["emoji"]
        final = (
            f"🎲 Игра {emoji} завершена!\n\n"
            f"{await get_username(game.player1)}: {p1_label}\n"
            f"{await get_username(game.player2)}: {p2_label}\n\n"
            f"{result_msg}"
        )

        try:
            if game.player1_dice_message_id:
                await get_bot().delete_message(game.chat_id, game.player1_dice_message_id)
            if game.player2_dice_message_id:
                await get_bot().delete_message(game.chat_id, game.player2_dice_message_id)
            if game.last_roll_message_id:
                await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
            if game.player1_button_message_id:
                await get_bot().delete_message(game.player1, game.player1_button_message_id)
            if game.player2_button_message_id and game.player2:
                await get_bot().delete_message(game.player2, game.player2_button_message_id)
            if game.message_id:
                await get_bot().delete_message(game.chat_id, game.message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщений: {e}")

        await get_bot().send_message(game.chat_id, final, parse_mode="HTML")

        for pid in (game.player1, game.player2):
            if pid:
                await get_bot().send_message(pid, f"🎮 Игра завершена!\n{final}", parse_mode="HTML")

        game.is_finished = True

        async with active_games_lock:
            if game.room_id in active_games:
                del active_games[game.room_id]

        logger.info(f"Игра завершена: room_id={game.room_id}, winner={winner}")

    except Exception as e:
        logger.error(f"Ошибка в determine_winner: {e}", exc_info=True)
        try:
            err_text = "❌ Произошла ошибка при завершении игры!"
            await get_bot().send_message(game.chat_id, err_text)
        except Exception:
            pass
        async with active_games_lock:
            if game.room_id in active_games:
                game.is_finished = True
                del active_games[game.room_id]


async def auto_roll_dice(game: GameRoom):
    config = GAMES_CONFIG[game.game_type]
    if game.results.get(game.player1, -1) < 0:
        d1 = await get_bot().send_dice(game.chat_id, emoji=config["emoji"])
        stored = d1.dice.value - 1 if game.game_type in ("дротики", "боулинг") else d1.dice.value
        game.results[game.player1] = stored
        logger.info(f"🎲 Авто-бросок {game.game_type}: {await get_username(game.player1)} = {d1.dice.value}→{stored}")
    if game.player2 and game.results.get(game.player2, -1) < 0:
        d2 = await get_bot().send_dice(game.chat_id, emoji=config["emoji"])
        stored = d2.dice.value - 1 if game.game_type in ("дротики", "боулинг") else d2.dice.value
        game.results[game.player2] = stored
        logger.info(f"🎲 Авто-бросок {game.game_type}: {await get_username(game.player2)} = {d2.dice.value}→{stored}")

    await determine_winner(game)


@router.message(F.text.in_(list({cfg["emoji"]: gt for gt, cfg in GAMES_CONFIG.items()}.keys())))
async def handle_game_emoji(message: Message):
    uid = message.from_user.id
    emoji = message.text.strip()
    GAME_EMOJIS = {cfg["emoji"]: gt for gt, cfg in GAMES_CONFIG.items()}
    game_type = GAME_EMOJIS.get(emoji)
    if not game_type:
        return

    async with active_games_lock:
        game = None
        for g in active_games.values():
            if g.is_finished:
                continue
            if uid in (g.player1, g.player2) and g.game_type == game_type:
                game = g
                break

        if not game:
            # If user has a solo game, let the solo handler process the emoji
            try:
                from .games_solo import _solo_games
                if uid in _solo_games:
                    return
            except ImportError:
                pass
            await message.answer("❌ У вас нет активной игры этого типа.")
            return

        current = game.player1 if game.player1_turn else game.player2
        if uid != current:
            await message.answer("❌ Сейчас не ваш ход!")
            return

        if uid in game.results:
            await message.answer("❌ Вы уже сделали бросок!")
            return

        game.results[uid] = -1

    config = GAMES_CONFIG[game.game_type]
    player_name = await get_username(uid)

    try:
        if game.last_roll_message_id:
            await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
    except Exception:
        pass

    roll_msg = await get_bot().send_message(game.chat_id, f"{player_name} {config['action']}...")
    game.last_roll_message_id = roll_msg.message_id

    dice_msg = await get_bot().send_dice(game.chat_id, emoji=config["emoji"], disable_notification=True)

    if uid == game.player1:
        game.player1_dice_message_id = dice_msg.message_id
    else:
        game.player2_dice_message_id = dice_msg.message_id

    try:
        btn_id = game.player1_button_message_id if uid == game.player1 else game.player2_button_message_id
        if btn_id:
            await get_bot().delete_message(uid, btn_id)
            if uid == game.player1:
                game.player1_button_message_id = None
            else:
                game.player2_button_message_id = None
    except Exception:
        pass

    await process_dice_roll(game, uid, dice_msg.dice.value)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("куб"))
@router.message(Command("боулинг"))
@router.message(Command("дротики"))
@router.message(Command("баскетбол"))
@router.message(Command("футбол"))
async def cmd_pvp_game(message: Message):
    cmd = message.text.split()[0][1:].lower()
    game_type = None
    for gt, cfg in GAMES_CONFIG.items():
        if cfg["command"] == cmd:
            game_type = gt
            break
    if not game_type:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply(
            f"🎮 <b>{game_type.capitalize()}</b> {GAMES_CONFIG[game_type]['emoji']}\n\n"
            f"Формат: `/{cmd} [ставка]`\n"
            f"Пример: `/{cmd} 50`\n\n"
            f"Игроки по очереди кидают кубик. Кто больше — побеждает."
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

    await create_game_for_user(message, message.from_user, message.from_user.id, game_type, bet)


@router.callback_query(F.data.startswith("casino_pick_game_"))
async def cb_casino_pick_game(call: CallbackQuery):
    game_type = call.data.split("_", 3)[3]
    if game_type not in GAMES_CONFIG:
        await call.answer("❌ Игра не найдена!", show_alert=True)
        return
    cfg = GAMES_CONFIG[game_type]
    await call.message.edit_text(
        f"<b>{cfg['emoji']} {game_type.capitalize()}</b>\n\n"
        f"Выберите ставку:",
        parse_mode="HTML",
        reply_markup=bet_selection_kb(game_type),
    )
    await call.answer()


@router.callback_query(F.data.startswith("casino_pick_bet_"))
async def cb_casino_pick_bet(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_", 3)
    remaining = parts[3]
    game_type, bet_str = remaining.split("_", 1)

    if game_type not in GAMES_CONFIG:
        await call.answer("❌ Игра не найдена!", show_alert=True)
        return

    if bet_str == "custom":
        await state.set_state(GameStates.waiting_for_bet)
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

    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)

    if user["balance"] < bet:
        await call.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}", show_alert=True)
        return

    await call.answer()
    await create_game_for_user(call.message, call.from_user, call.from_user.id, game_type, bet)


@router.message(GameStates.waiting_for_bet)
async def process_custom_bet(message: Message, state: FSMContext):
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

    if game_type == "blackjack":
        if message.chat.type == "private":
            await message.answer("❌ Блэкджек только в группах!")
            return
        user = await get_user(message.from_user.id)
        if not user:
            await create_user(message.from_user)
            user = await get_user(message.from_user.id)
        bj_bal = user["balance"] if user["balance"] is not None else INITIAL_BALANCE
        if bj_bal < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {bj_bal}")
            return
        await update_balance(message.from_user.id, -bet, "bj_reserve")
        room_id = f"bj-{uuid.uuid4()}"
        game = BlackjackRoom(room_id, bet, message.from_user.id, message.chat.id)
        game.players[message.from_user.id] = []
        game.player_names[message.from_user.id] = await get_username(message.from_user.id)
        async with active_games_lock:
            active_blackjack_games[room_id] = game
        sent = await message.answer(
            f"🃏 <b>Блэкджек стол!</b>\n"
            f"💵 Ставка: {bet} 🪙\n"
            f"👤 {game.player_names[message.from_user.id]} (создатель)\n"
            f"👥 Места: 1/6\n\n"
            f"⏳ Ожидание игроков...\n\n"
            f"Нажмите «Присоединиться» или «Старт» для начала.",
            reply_markup=blackjack_join_keyboard(room_id),
        )
        game.join_message_id = sent.message_id
        game.phase = "joining"
        asyncio.ensure_future(blackjack_join_timeout(room_id, 60))
        return

    if game_type == "rps":
        if message.chat.type == "private":
            await message.answer("❌ Камень-Ножницы-Бумага только в группах!")
            return
        user = await get_user(message.from_user.id)
        if not user:
            await create_user(message.from_user)
            user = await get_user(message.from_user.id)
        if user["balance"] < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']}")
            return
        await update_balance(message.from_user.id, -bet, "rps_reserve")
        room_id = str(uuid.uuid4())
        game = GameRoom(room_id, "rps", bet, message.from_user.id)
        game.chat_id = message.chat.id
        async with active_games_lock:
            for g in active_games.values():
                if not g.is_finished and message.from_user.id in (g.player1, g.player2):
                    await update_balance(message.from_user.id, bet, "refund")
                    await message.answer("❌ Вы уже участвуете в другой игре!")
                    return
            active_games[room_id] = game
        await save_active_game(room_id, "rps", message.from_user.id, 0, bet)
        p1_name = await get_username(message.from_user.id)
        from .keyboards import InlineKeyboardMarkup, InlineKeyboardButton
        sent = await message.answer(
            f"✂️ <b>Камень-Ножницы-Бумага!</b>\n"
            f"💵 Ставка: {bet} 🪙\n"
            f"⏳ Ожидание второго игрока...\n\n"
            f"Игрок 1: {p1_name}\n"
            f"Места: 1/2\n\n"
            f"Игра отменится через 60 секунд, если никто не присоединится.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✂️ Присоединиться", callback_data=f"rps_join_{room_id}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"rps_cancel_{room_id}")],
            ]),
        )
        game.message_id = sent.message_id
        import asyncio
        from .games_rps import _rps_join_timeout
        asyncio.ensure_future(_rps_join_timeout(room_id, 60))
        return

    await create_game_for_user(message, message.from_user, message.from_user.id, game_type, bet)


def game_keyboard(room_id: str, creator_id: int, label: str = "🎮 Присоединиться к игре"):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"join_{room_id}")],
            [InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"cancelgame_{room_id}")],
        ]
    )


def roll_keyboard(room_id: str, player_id: int, emoji: str):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Бросить {emoji}", callback_data=f"roll_{room_id}_{player_id}")]
        ]
    )


def bet_selection_kb(game_type: str):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    bets = [10, 50, 100, 500, 1000]
    row = []
    buttons = []
    for bet in bets:
        row.append(InlineKeyboardButton(
            text=f"{bet}🪙",
            callback_data=f"casino_pick_bet_{game_type}_{bet}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="✏️ Своя сумма", callback_data=f"casino_pick_bet_{game_type}_custom"
        )
    ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
