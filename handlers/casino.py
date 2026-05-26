import asyncio
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import OWNER_ID as ADMIN_ID

COMMISSION_RATE = Decimal("0.1")
DB_NAME = "casino.db"
INITIAL_BALANCE = 1000
DAILY_BONUS = 500

_bot: Optional[Bot] = None


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Casino router not initialized")
    return _bot


def setup(bot_instance: Bot):
    global _bot
    _bot = bot_instance


router = Router()

GAMES_CONFIG = {
    "куб": {"command": "куб", "emoji": "🎲", "timeout": 30},
    "боулинг": {"command": "боулинг", "emoji": "🎳", "timeout": 30},
    "дротики": {"command": "дротики", "emoji": "🎯", "timeout": 30},
    "баскетбол": {"command": "баскетбол", "emoji": "🏀", "timeout": 30},
    "футбол": {"command": "футбол", "emoji": "⚽", "timeout": 30},
}


class DepositState(StatesGroup):
    waiting_for_amount = State()


class GameStates(StatesGroup):
    waiting_for_bet = State()


async def get_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_NAME)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db():
    conn = await get_db()
    try:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 1000,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                last_bonus DATE
            );
            CREATE TABLE IF NOT EXISTS games (
                room_id TEXT PRIMARY KEY,
                game_type TEXT,
                bet INTEGER,
                player1 INTEGER,
                player2 INTEGER,
                created DATETIME
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created TEXT
            );
            CREATE TABLE IF NOT EXISTS casino_admins (
                admin_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT
            );
            CREATE TABLE IF NOT EXISTS admin_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                permission TEXT,
                UNIQUE(admin_id, permission)
            );
        """)
        await conn.commit()
    finally:
        await conn.close()


async def get_user(user_id: int) -> Optional[aiosqlite.Row]:
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()
    finally:
        await conn.close()


async def create_user(tg_user) -> None:
    username = tg_user.username or tg_user.first_name or f"user_{tg_user.id}"
    conn = await get_db()
    try:
        await conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, ?)",
            (tg_user.id, username, INITIAL_BALANCE),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_balance(user_id: int, amount: int, tr_type: str) -> None:
    conn = await get_db()
    try:
        timestamp = datetime.now().isoformat()
        await conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, amount, tr_type, timestamp),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_username(user_id: int) -> str:
    user = await get_user(user_id)
    if user and user["username"]:
        return "@" + user["username"]
    return f"Игрок {user_id}"


class GameRoom:
    def __init__(self, room_id: str, game_type: str, bet: int, player1: int):
        self.room_id = room_id
        self.game_type = game_type
        self.bet = bet
        self.player1 = player1
        self.player2: Optional[int] = None
        self.results: dict[int, int] = {}
        self.created = datetime.now()
        self.is_finished = False
        self.player1_turn = True
        self.chat_id: Optional[int] = None
        self.message_id: Optional[int] = None
        self.last_roll_message_id: Optional[int] = None
        self.player1_button_message_id: Optional[int] = None
        self.player2_button_message_id: Optional[int] = None
        self.player1_dice_message_id: Optional[int] = None
        self.player2_dice_message_id: Optional[int] = None

    def add_player(self, player2: int) -> bool:
        if self.player2 is None:
            self.player2 = player2
            return True
        return False


active_games: dict[str, GameRoom] = {}
active_games_lock = asyncio.Lock()


def game_keyboard(room_id: str, creator_id: int, label: str = "🎮 Присоединиться к игре") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"join_{room_id}")],
            [InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"cancelgame_{room_id}")],
        ]
    )


def roll_keyboard(room_id: str, player_id: int, emoji: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Бросить {emoji}", callback_data=f"roll_{room_id}_{player_id}")]
        ]
    )


def casino_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎮 Игры", callback_data="casino_games")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="casino_profile"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="casino_top")],
        [InlineKeyboardButton(text="🎁 Бонус", callback_data="casino_bonus"),
         InlineKeyboardButton(text="🎲 Активные", callback_data="casino_active")],
        [InlineKeyboardButton(text="🔓 Разблокировать", callback_data="casino_unlock")],
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="casino_admin")])
    buttons.append([InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def game_selection_kb() -> InlineKeyboardMarkup:
    buttons = []
    for game_type, cfg in GAMES_CONFIG.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{cfg['emoji']} {game_type.capitalize()}",
                callback_data=f"casino_pick_game_{game_type}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def bet_selection_kb(game_type: str) -> InlineKeyboardMarkup:
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


def casino_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список игроков", callback_data="casino_admin_players")],
        [InlineKeyboardButton(text="📋 Запросы на пополнение", callback_data="casino_admin_pending")],
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="casino_admin_add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")],
    ])


@router.callback_query(F.data == "casino_menu")
async def cb_casino_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)
    await call.message.answer(
        f"🎰 <b>Меню казино</b>\n\n"
        f"💰 Ваш баланс: {user['balance']} монет\n"
        f"🏆 Побед: {user['wins']} / {user['games_played']} игр",
        reply_markup=casino_menu_kb(user_id=call.from_user.id),
    )
    await call.answer()


@router.callback_query(F.data == "casino_games")
async def cb_casino_games(call: CallbackQuery):
    text = "🎮 <b>Выберите игру:</b>\n\n"
    for game_type, cfg in GAMES_CONFIG.items():
        text += f"{cfg['emoji']} <b>{game_type.capitalize()}</b> — /{cfg['command']} [ставка]\n"
    await call.message.edit_text(text, reply_markup=game_selection_kb())
    await call.answer()


@router.callback_query(F.data == "casino_profile")
async def cb_casino_profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await create_user(call.from_user)
        user = await get_user(call.from_user.id)

    text = (
        f"📊 Профиль игрока {call.from_user.first_name}\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"💰 Баланс: {user['balance']} монет\n"
        f"🎮 Сыграно игр: {user['games_played']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"📅 Последний бонус: {user['last_bonus'] or 'ещё не получал'}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="deposit")]
        ]
    )
    await call.message.answer(text, reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "casino_top")
async def cb_casino_top(call: CallbackQuery):
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
        text = "🏆 Топ 10 игроков:\n\n"
        for i, row in enumerate(rows, 1):
            name = row["username"] or f"user_{row['user_id']}"
            text += f"{i}. @{name} — {row['balance']} монет\n"
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "casino_bonus")
async def cb_casino_bonus(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user(user_id)

    if not user:
        await create_user(call.from_user)
        user = await get_user(user_id)

    last_bonus_val = user["last_bonus"]
    today_d = date.today()

    if last_bonus_val:
        try:
            if isinstance(last_bonus_val, str):
                last_date = datetime.strptime(last_bonus_val, "%Y-%m-%d").date()
            else:
                last_date = last_bonus_val
            if today_d <= last_date:
                await call.message.answer("💰 Вы уже получили свой сегодняшний бонус!")
                await call.answer()
                return
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка даты бонуса для {user_id}: {e}")

    await update_balance(user_id, DAILY_BONUS, "bonus")
    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET last_bonus = ? WHERE user_id = ?",
            (today_d.strftime("%Y-%m-%d"), user_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    await call.message.answer(f"🎉 Вы получили ежедневный бонус в размере {DAILY_BONUS} монет!")
    await call.answer()


@router.callback_query(F.data == "casino_active")
async def cb_casino_active(call: CallbackQuery):
    async with active_games_lock:
        if not active_games:
            await call.message.answer("Сейчас нет активных игр.")
            await call.answer()
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
    await call.message.answer(text)
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
                    logger.error(f"Refund error: {e}")
                to_remove.append(rid)

        for rid in to_remove:
            del active_games[rid]

    await call.message.answer(
        f"✅ Все ваши игры отменены! Возвращено: {refunded} монет\n"
        "Теперь вы можете создавать новые игры!"
    )
    await call.answer()


@router.message(Command("профиль"))
async def cmd_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user)
        user = await get_user(message.from_user.id)

    if message.chat.type != "private":
        await message.reply("ℹ️ Для просмотра профиля и пополнения баланса перейдите в личные сообщения с ботом.")
        return

    text = (
        f"📊 Профиль игрока {message.from_user.first_name}\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"💰 Баланс: {user['balance']} монет\n"
        f"🎮 Сыграно игр: {user['games_played']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"📅 Последний бонус: {user['last_bonus'] or 'ещё не получал'}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="deposit")]
        ]
    )
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "deposit")
async def cb_deposit(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type != "private":
        await call.answer("ℹ️ Для пополнения баланса перейдите в личные сообщения с ботом.", show_alert=True)
        bot_username = (await get_bot().me()).username
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти в бота", url=f"https://t.me/{bot_username}")]
            ]
        )
        await call.message.answer(
            f"💳 {call.from_user.first_name}, для пополнения баланса перейдите в личные сообщения с ботом:",
            reply_markup=markup,
        )
        return

    await call.message.answer("Введите сумму пополнения (от 100 до 10000 монет):")
    await state.set_state(DepositState.waiting_for_amount)
    await call.answer()


@router.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        if not (100 <= amount <= 10000):
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Некорректная сумма! Используйте целое число от 100 до 10000.")
        await state.clear()
        return

    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT * FROM deposit_requests WHERE user_id = ? AND status = 'pending'",
            (message.from_user.id,),
        )
        if await cursor.fetchone():
            await message.answer("❌ У вас уже есть активный запрос на пополнение!")
            await state.clear()
            return

        await conn.execute(
            "INSERT INTO deposit_requests (user_id, amount, created) VALUES (?, ?, ?)",
            (message.from_user.id, amount, datetime.now().isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()

    await send_admin_notification(message.from_user.id, amount)
    await message.answer("✅ Запрос отправлен администратору. Ожидайте подтверждения.")
    await state.clear()


async def send_admin_notification(user_id: int, amount: int):
    try:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}_{amount}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{amount}"),
                ]
            ]
        )
        username = await get_username(user_id)
        await get_bot().send_message(
            ADMIN_ID,
            f"🆕 Запрос на пополнение:\n\n"
            f"👤 Пользователь: {username}\n"
            f"🆔 ID: {user_id}\n"
            f"💵 Сумма: {amount} монет",
            reply_markup=markup,
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления админу: {e}")


@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def cb_admin_decision(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_deposits"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    action, user_id_str, amount_str = call.data.split("_")
    user_id = int(user_id_str)
    amount = int(amount_str)

    conn = await get_db()
    try:
        if action == "approve":
            await update_balance(user_id, amount, "deposit")
            status = "approved"
            await get_bot().send_message(user_id, f"✅ Ваш баланс пополнен на {amount} монет!")
        else:
            status = "rejected"
            await get_bot().send_message(user_id, "❌ Ваш запрос на пополнение был отклонён.")

        await conn.execute(
            "UPDATE deposit_requests SET status = ? WHERE user_id = ? AND amount = ? AND status = 'pending'",
            (status, user_id, amount),
        )
        await conn.commit()
    finally:
        await conn.close()

    await call.answer(f"Статус обновлён: {status}")
    try:
        await get_bot().delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass


@router.message(Command("пополнить"))
async def cmd_admin_add_balance(message: Message):
    if not await has_perm(message.from_user.id, "add_balance"):
        await message.reply("❌ Доступ запрещён!")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("❌ Формат: /пополнить [user_id] [кол-во монет]")
        return

    try:
        user_id = int(parts[1])
        amount = int(parts[2])
    except (ValueError, IndexError):
        await message.reply("❌ Формат: /пополнить [user_id] [кол-во монет]")
        return

    await update_balance(user_id, amount, "admin_add")
    await message.reply(f"Баланс пользователя {user_id} пополнен на {amount} монет! ✅")
    await get_bot().send_message(user_id, f"Администратор пополнил ваш баланс на {amount} монет! 🎉")


@router.message(Command("бонус"))
async def cmd_daily_bonus(message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if not user:
        await create_user(message.from_user)
        user = await get_user(user_id)

    last_bonus_val = user["last_bonus"]
    today_d = date.today()

    if last_bonus_val:
        try:
            if isinstance(last_bonus_val, str):
                last_date = datetime.strptime(last_bonus_val, "%Y-%m-%d").date()
            else:
                last_date = last_bonus_val
            if today_d <= last_date:
                await message.reply("💰 Вы уже получили свой сегодняшний бонус!")
                return
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка даты бонуса для {user_id}: {e}")

    await update_balance(user_id, DAILY_BONUS, "bonus")
    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET last_bonus = ? WHERE user_id = ?",
            (today_d.strftime("%Y-%m-%d"), user_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"🎉 Вы получили ежедневный бонус в размере {DAILY_BONUS} монет!")


@router.message(Command("топ"))
async def cmd_top(message: Message):
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()

    if not rows:
        await message.answer("❌ Пока нет данных о пользователях.")
        return

    text = "🏆 Топ 10 игроков:\n\n"
    for i, row in enumerate(rows, 1):
        name = row["username"] or f"user_{row['user_id']}"
        text += f"{i}. @{name} — {row['balance']} монет\n"

    await message.answer(text)


@router.message(Command("игры"))
async def cmd_games(message: Message):
    text = "🕹 Доступные игры:\n\n"
    for game_type, cfg in GAMES_CONFIG.items():
        text += f"/{cfg['command']} [ставка] — {game_type} {cfg['emoji']}\n"
    await message.answer(text)


@router.message(Command("активные"))
async def cmd_active_games(message: Message):
    async with active_games_lock:
        if not active_games:
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
    await message.reply(text)


@router.message(Command("разблокировать"))
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
                except Exception as e:
                    logger.error(f"Refund error: {e}")
                to_remove.append(rid)

        for rid in to_remove:
            del active_games[rid]

    await message.reply(
        f"✅ Все ваши игры отменены! Возвращено: {refunded} монет\n"
        "Теперь вы можете создавать новые игры!"
    )


@router.message(Command("игроки"))
async def cmd_all_players(message: Message):
    if not await has_perm(message.from_user.id, "view_players"):
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
        name = f"@{p['username']}" if p["username"] else f"ID_{p['user_id']}"
        chunk.append(
            f"👤 ID: {p['user_id']} | {name}\n"
            f"💰 {p['balance']} | 🎮 {p['games_played']} | 🏆 {p['wins']}\n"
            f"📅 Бонус: {p['last_bonus'] or 'нет'}\n"
            f"{'─' * 20}"
        )
        if len(chunk) == 10:
            parts.append("\n".join(chunk))
            chunk = []

    if chunk:
        parts.append("\n".join(chunk))
        chunk = []

    header = f"👥 Все игроки ({len(players)}):\n\n"
    for i, part in enumerate(parts):
        text = header if i == 0 else ""
        await message.answer(text + part)


# ─── Permission system ──────────────────────────────────────────────

PERMISSIONS = {
    "view_players": "👥 Просмотр списка игроков",
    "view_stats": "📊 Просмотр статистики",
    "add_balance": "💰 Пополнение баланса",
    "approve_deposits": "📋 Одобрение запросов",
    "manage_games": "🎮 Управление играми",
}


def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def get_admin_perms(user_id: int) -> list[str]:
    if is_owner(user_id):
        return list(PERMISSIONS.keys()) + ["manage_admins"]
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT permission FROM admin_permissions WHERE admin_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        return [r["permission"] for r in rows]
    finally:
        await conn.close()


async def has_perm(user_id: int, permission: str) -> bool:
    if is_owner(user_id):
        return True
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT 1 FROM admin_permissions WHERE admin_id = ? AND permission = ?",
            (user_id, permission),
        )
        return await cursor.fetchone() is not None
    finally:
        await conn.close()


async def is_casino_admin(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT 1 FROM casino_admins WHERE admin_id = ?", (user_id,)
        )
        return await cursor.fetchone() is not None
    finally:
        await conn.close()


def casino_admin_kb(perms: Optional[list[str]] = None) -> InlineKeyboardMarkup:
    if perms is None:
        perms = []
    buttons = []
    if "view_players" in perms:
        buttons.append([InlineKeyboardButton(text="👥 Список игроков", callback_data="casino_admin_players")])
    if "view_stats" in perms:
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="casino_admin_stats")])
    if "add_balance" in perms:
        buttons.append([InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="casino_admin_add")])
    if "approve_deposits" in perms:
        buttons.append([InlineKeyboardButton(text="📋 Запросы на пополнение", callback_data="casino_admin_pending")])
    if "manage_admins" in perms:
        buttons.append([InlineKeyboardButton(text="👑 Управление админами", callback_data="casino_admin_manage")])
    buttons.append([InlineKeyboardButton(text="📖 Команды /admin", callback_data="casino_admin_help")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Admin panel callbacks ──────────────────────────────────────────

ADMIN_ERROR = "❌ Доступ запрещён!"


@router.callback_query(F.data == "casino_admin")
async def cb_casino_admin(call: CallbackQuery):
    uid = call.from_user.id
    if not await is_casino_admin(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    perms = await get_admin_perms(uid)
    await call.message.edit_text(
        "⚙️ <b>Админ-панель казино</b>\n\n"
        "Выберите действие:",
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
        cursor = await conn.execute("SELECT * FROM users ORDER BY user_id")
        players = await cursor.fetchall()
    finally:
        await conn.close()

    if not players:
        await call.message.answer("❌ Нет зарегистрированных игроков.")
        await call.answer()
        return

    parts = []
    chunk = []
    for p in players:
        name = f"@{p['username']}" if p["username"] else f"ID_{p['user_id']}"
        chunk.append(
            f"👤 ID: {p['user_id']} | {name}\n"
            f"💰 {p['balance']} | 🎮 {p['games_played']} | 🏆 {p['wins']}"
        )
        if len(chunk) == 15:
            parts.append("\n".join(chunk))
            chunk = []
    if chunk:
        parts.append("\n".join(chunk))

    for i, part in enumerate(parts):
        await call.message.answer(f"👥 Игроки ({len(players)}):\n\n{part}" if i == 0 else part)
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
        f"👥 Всего игроков: {total_users}\n"
        f"🎮 Активных игроков: {active_players}\n"
        f"💰 Общий баланс: {total_balance} монет\n"
        f"📋 Ожидающих запросов: {pending}"
    )
    await call.message.answer(text)
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
        await call.message.answer("📋 Нет ожидающих запросов на пополнение.")
    else:
        text = "📋 <b>Ожидающие запросы:</b>\n\n"
        for req in pending:
            username = await get_username(req["user_id"])
            text += f"👤 {username}\n💵 {req['amount']} монет\n📅 {req['created']}\n\n"
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "casino_admin_add")
async def cb_casino_admin_add(call: CallbackQuery):
    uid = call.from_user.id
    if not await has_perm(uid, "add_balance"):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await call.message.answer(
        "💰 Чтобы пополнить баланс пользователя, используйте:\n\n"
        "<code>/пополнить user_id сумма</code>\n\n"
        "Пример: <code>/пополнить 123456789 1000</code>"
    )
    await call.answer()


@router.callback_query(F.data == "casino_admin_manage")
async def cb_casino_admin_manage(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    text = (
        "👑 <b>Управление админами</b>\n\n"
        "Команды для управления:\n\n"
        "<code>/addadmin user_id</code> — добавить админа\n"
        "<code>/removeadmin user_id</code> — удалить админа\n"
        "<code>/admins</code> — список админов\n"
        "<code>/setperm user_id право</code> — выдать право\n"
        "<code>/removeperm user_id право</code> — отозвать право\n"
        "<code>/perms user_id</code> — права пользователя\n\n"
        "<b>Права (permissions):</b>\n"
    )
    for perm, desc in PERMISSIONS.items():
        text += f"  • <code>{perm}</code> — {desc}\n"
    await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "casino_admin_help")
async def cb_casino_admin_help(call: CallbackQuery):
    uid = call.from_user.id
    if not await is_casino_admin(uid):
        await call.answer(ADMIN_ERROR, show_alert=True)
        return
    await _send_admin_help(call.message, uid)
    await call.answer()


# ─── Admin commands ──────────────────────────────────────────────────

ADMIN_COMMANDS = {
    "/admin": "📖 Справка по всем админ-командам",
    "/addadmin <id>": "👑 Добавить администратора (только владелец)",
    "/removeadmin <id>": "👑 Удалить администратора (только владелец)",
    "/admins": "👑 Список всех администраторов (только владелец)",
    "/setperm <id> <право>": "🔑 Выдать право админу (только владелец)",
    "/removeperm <id> <право>": "🔑 Отозвать право у админа (только владелец)",
    "/perms <id>": "🔑 Посмотреть права пользователя",
    "/игроки": "👥 Список всех игроков (право: view_players)",
    "/пополнить <id> <сумма>": "💰 Пополнить баланс (право: add_balance)",
}


async def _send_admin_help(target, user_id: int):
    perms = await get_admin_perms(user_id)
    text = "📖 <b>Админ-команды казино</b>\n\n"
    for cmd, desc in ADMIN_COMMANDS.items():
        text += f"<code>{cmd}</code>\n└ {desc}\n\n"
    text += f"<b>Ваши права:</b> {', '.join(perms) if perms else 'нет прав'}"
    await target.answer(text)


@router.message(Command("admin"))
async def cmd_admin_help(message: Message):
    uid = message.from_user.id
    if not await is_casino_admin(uid):
        await message.reply("❌ Доступ запрещён!")
        return
    await _send_admin_help(message, uid)


@router.message(Command("addadmin"))
async def cmd_add_admin(message: Message):
    if not is_owner(message.from_user.id):
        await message.reply("❌ Только владелец может добавлять админов!")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("❌ Укажите ID пользователя.\nФормат: <code>/addadmin user_id</code>")
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await message.reply("❌ Некорректный ID!")
        return

    conn = await get_db()
    try:
        await conn.execute(
            "INSERT OR IGNORE INTO casino_admins (admin_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, message.from_user.id, datetime.now().isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Пользователь {user_id} добавлен в администраторы!\n"
                        f"Выдайте ему права командой:\n<code>/setperm {user_id} право</code>")


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message):
    if not is_owner(message.from_user.id):
        await message.reply("❌ Только владелец может удалять админов!")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("❌ Укажите ID пользователя.")
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await message.reply("❌ Некорректный ID!")
        return

    if is_owner(user_id):
        await message.reply("❌ Нельзя удалить владельца!")
        return

    conn = await get_db()
    try:
        await conn.execute("DELETE FROM casino_admins WHERE admin_id = ?", (user_id,))
        await conn.execute("DELETE FROM admin_permissions WHERE admin_id = ?", (user_id,))
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Пользователь {user_id} удалён из администраторов.")


@router.message(Command("admins"))
async def cmd_list_admins(message: Message):
    if not is_owner(message.from_user.id):
        await message.reply("❌ Только владелец может просматривать список админов!")
        return

    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT a.admin_id, a.added_at, GROUP_CONCAT(p.permission, ', ') as perms "
            "FROM casino_admins a LEFT JOIN admin_permissions p ON a.admin_id = p.admin_id "
            "GROUP BY a.admin_id"
        )
        admins = await cursor.fetchall()
    finally:
        await conn.close()

    text = f"👑 <b>Администраторы казино</b>\n\n👤 Владелец: <code>{ADMIN_ID}</code> (полные права)\n\n"
    if not admins:
        text += "Нет других администраторов."
    else:
        for a in admins:
            text += (
                f"👤 <code>{a['admin_id']}</code>\n"
                f"📅 {a['added_at']}\n"
                f"🔑 Права: {a['perms'] or 'не назначены'}\n\n"
            )
    await message.answer(text)


@router.message(Command("setperm"))
async def cmd_set_perm(message: Message):
    if not is_owner(message.from_user.id):
        await message.reply("❌ Только владелец может назначать права!")
        return

    parts = message.text.split()
    if len(parts) < 3:
        perms_list = "\n".join(f"• <code>{k}</code> — {v}" for k, v in PERMISSIONS.items())
        await message.reply(
            f"❌ Укажите ID и право.\nФормат: <code>/setperm user_id право</code>\n\n"
            f"Доступные права:\n{perms_list}"
        )
        return

    try:
        user_id = int(parts[1])
        permission = parts[2]
    except (ValueError, IndexError):
        await message.reply("❌ Некорректный формат!")
        return

    if permission not in PERMISSIONS:
        await message.reply(f"❌ Неизвестное право <code>{permission}</code>!\n"
                            f"Доступные: {', '.join(PERMISSIONS.keys())}")
        return

    conn = await get_db()
    try:
        await conn.execute(
            "INSERT OR IGNORE INTO admin_permissions (admin_id, permission) VALUES (?, ?)",
            (user_id, permission),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Право <code>{permission}</code> выдано пользователю {user_id}.")


@router.message(Command("removeperm"))
async def cmd_remove_perm(message: Message):
    if not is_owner(message.from_user.id):
        await message.reply("❌ Только владелец может отзывать права!")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("❌ Укажите ID и право.\nФормат: <code>/removeperm user_id право</code>")
        return

    try:
        user_id = int(parts[1])
        permission = parts[2]
    except (ValueError, IndexError):
        await message.reply("❌ Некорректный формат!")
        return

    conn = await get_db()
    try:
        await conn.execute(
            "DELETE FROM admin_permissions WHERE admin_id = ? AND permission = ?",
            (user_id, permission),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Право <code>{permission}</code> отозвано у пользователя {user_id}.")


@router.message(Command("perms"))
async def cmd_show_perms(message: Message):
    uid = message.from_user.id
    if not await is_casino_admin(uid) and not is_owner(uid):
        await message.reply("❌ Доступ запрещён!")
        return

    parts = message.text.split()
    target_id = uid
    if len(parts) >= 2 and is_owner(uid):
        try:
            target_id = int(parts[1])
        except ValueError:
            await message.reply("❌ Некорректный ID!")
            return

    perms = await get_admin_perms(target_id)
    if is_owner(target_id):
        text = f"👑 Владелец <code>{target_id}</code> — полные права."
    elif perms:
        text = f"👤 <code>{target_id}</code>\n🔑 Права: {', '.join(perms)}"
    else:
        text = f"👤 <code>{target_id}</code>\n🔑 Нет прав."

    await message.answer(text)


# ─── Extra Admin Commands ────────────────────────────────────────────


@router.message(Command("setbalance"))
async def cmd_set_balance(message: Message):
    uid = message.from_user.id
    if not await has_perm(uid, "add_balance"):
        await message.reply("❌ Доступ запрещён!")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("❌ Формат: <code>/setbalance user_id сумма</code>")
        return

    try:
        target_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.reply("❌ Некорректные ID или сумма!")
        return

    conn = await get_db()
    try:
        await conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, target_id))
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Баланс пользователя {target_id} установлен на {amount} монет.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    uid = message.from_user.id
    if not is_owner(uid):
        await message.reply("❌ Только владелец может делать рассылку!")
        return

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.reply("❌ Напишите сообщение для рассылки.\nФормат: <code>/broadcast текст</code>")
        return

    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    finally:
        await conn.close()

    sent = 0
    failed = 0
    for row in users:
        try:
            await get_bot().send_message(row["user_id"], f"📢 Рассылка:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.reply(f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")


# ─── Cancel game / leave all games ──────────────────────────────────


@router.callback_query(F.data.startswith("cancelgame_"))
async def cb_cancel_game(call: CallbackQuery):
    room_id = call.data.split("_", 1)[1]
    caller = call.from_user.id
    logger.info(f"cancel_game: user {caller} пытается отменить {room_id}")
    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            logger.warning(f"cancel_game: {room_id} уже завершена")
            await call.answer("❌ Игра уже завершена!", show_alert=True)
            return
        if game.player1 != caller:
            logger.warning(f"cancel_game: user {caller} не создатель {room_id} (creator={game.player1})")
            await call.answer("❌ Только создатель может отменить игру!", show_alert=True)
            return
        if game.player2 is not None:
            await call.answer("❌ Игра уже началась! Нельзя отменить.", show_alert=True)
            return
        await update_balance(game.player1, game.bet, "refund")
        game.is_finished = True
        del active_games[room_id]
        logger.info(f"cancel_game: {room_id} отменена, ставка {game.bet} возвращена")
    await call.message.edit_text("❌ Игра отменена создателем.\n💰 Ставка возвращена.")
    await call.answer("✅ Игра отменена, ставка возвращена.", show_alert=True)


@router.message(Command("отменитьвсе"))
async def cmd_cancel_all_games(message: Message):
    uid = message.from_user.id
    refunded = 0
    total_refund = 0
    async with active_games_lock:
        to_delete = []
        for rid, g in active_games.items():
            if g.is_finished:
                to_delete.append(rid)
                continue
            if g.player1 == uid and g.player2 is None:
                await update_balance(uid, g.bet, "refund")
                refunded += 1
                total_refund += g.bet
                g.is_finished = True
                to_delete.append(rid)
            elif uid in (g.player1, g.player2) and g.player2 is not None:
                await message.reply("❌ Нельзя отменить игру, которая уже началась.")
                return
        for rid in to_delete:
            del active_games[rid]
    if refunded:
        await message.reply(f"✅ Отменено игр: {refunded}\n💰 Возвращено: {total_refund} монет.")
    else:
        await message.reply("❌ Нет активных игр для отмены.")


@router.message(Command("cancel"))
async def cmd_cancel_fsm(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.reply("❌ Действие отменено.")
    else:
        await message.reply("❌ Нет активного действия для отмены.")


async def create_game_for_user(
    target_msg: Message,
    tg_user,
    user_id: int,
    game_type: str,
    bet: int,
) -> bool:
    try:
        async with active_games_lock:
            finished = [rid for rid, g in active_games.items() if g.is_finished]
            for rid in finished:
                del active_games[rid]
            if finished:
                logger.info(f"create_game: очищено {len(finished)} завершённых игр, активных: {len(active_games)}")
            for g in active_games.values():
                if not g.is_finished and user_id in (g.player1, g.player2):
                    logger.warning(f"create_game: user {user_id} уже в игре {g.room_id} (finished={g.is_finished})")
                    await target_msg.reply("❌ Вы уже участвуете в другой игре! Дождитесь её завершения.")
                    return False

        if bet < 10:
            await target_msg.reply("❌ Минимальная ставка — 10 монет!")
            return False

        user = await get_user(user_id)
        if not user:
            await create_user(tg_user)
            user = await get_user(user_id)
        if user["balance"] < bet:
            await target_msg.reply("❌ Недостаточно средств на балансе!")
            return False

        await update_balance(user_id, -bet, "reserve")
        room_id = f"game-{uuid.uuid4()}"
        game = GameRoom(room_id, game_type, bet, user_id)
        async with active_games_lock:
            active_games[room_id] = game

        player1_name = await get_username(user_id)
        group_msg = (
            f"🎉 Создана новая игра в {GAMES_CONFIG[game_type]['emoji']}!\n"
            f"💵 Ставка: {bet} монет\n"
            f"⏳ Время на присоединение: {GAMES_CONFIG[game_type]['timeout']} сек\n"
            f"Игрок 1: {player1_name}\n"
            f"Места: 1/2"
        )
        sent = await target_msg.answer(group_msg, reply_markup=game_keyboard(room_id, user_id))
        game.chat_id = target_msg.chat.id
        game.message_id = sent.message_id
        asyncio.ensure_future(game_timeout(room_id, GAMES_CONFIG[game_type]["timeout"]))
        logger.info(f"Создана игра: room_id={room_id}, game_type={game_type}, player1={user_id}")
        return True

    except ValueError:
        await target_msg.reply("❌ Некорректная ставка! Используйте числовое значение.")
        return False
    except Exception as e:
        logger.error(f"Ошибка при создании игры: {e}")
        await target_msg.reply("❌ Произошла ошибка при создании игры!")
        try:
            await update_balance(user_id, bet, "refund")
        except Exception:
            pass
        return False


def make_game_handler(game_type: str):
    @router.message(Command(GAMES_CONFIG[game_type]["command"]))
    async def handler(message: Message):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply(f"❌ Укажите ставку! Пример: /{GAMES_CONFIG[game_type]['command']} [ставка]")
                return
            bet = int(parts[1])
        except ValueError:
            await message.reply("❌ Некорректная ставка! Используйте числовое значение.")
            return
        await create_game_for_user(message, message.from_user, message.from_user.id, game_type, bet)
    return handler


for gt in GAMES_CONFIG:
    make_game_handler(gt)


@router.callback_query(F.data.startswith("casino_pick_game_"))
async def cb_casino_game_select(call: CallbackQuery):
    game_type = call.data[len("casino_pick_game_"):]
    if game_type not in GAMES_CONFIG:
        await call.answer("❌ Неизвестная игра!", show_alert=True)
        return
    cfg = GAMES_CONFIG[game_type]
    await call.message.edit_text(
        f"{cfg['emoji']} <b>{game_type.capitalize()}</b>\n\n"
        f"💰 Выберите ставку:",
        reply_markup=bet_selection_kb(game_type),
    )
    await call.answer()


@router.callback_query(F.data.startswith("casino_pick_bet_"))
async def cb_casino_bet_select(call: CallbackQuery, state: FSMContext):
    prefix = "casino_pick_bet_"
    suffix = call.data[len(prefix):]
    game_type, amount_str = suffix.rsplit("_", 1)

    if amount_str == "custom":
        await state.set_state(GameStates.waiting_for_bet)
        await state.update_data(game_type=game_type)
        await call.message.edit_text(
            f"💰 Введите сумму ставки (целое число, минимум 10):\n"
            f"Игра: {GAMES_CONFIG[game_type]['emoji']} {game_type.capitalize()}"
        )
        await call.answer()
        return

    try:
        bet = int(amount_str)
    except ValueError:
        await call.answer("❌ Некорректная сумма!", show_alert=True)
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

    await state.clear()
    await create_game_for_user(message, message.from_user, message.from_user.id, game_type, bet)


@router.callback_query(F.data.startswith("join_"))
async def cb_join_game(call: CallbackQuery):
    try:
        joiner_id = call.from_user.id
        room_id = call.data.split("_", 1)[1]
        logger.info(f"join_game: user {joiner_id} пытается присоединиться к {room_id}")

        async with active_games_lock:
            for rid, g in active_games.items():
                if not g.is_finished and joiner_id in (g.player1, g.player2) and rid != room_id:
                    logger.warning(f"join_game: user {joiner_id} уже в другой игре {rid}")
                    await call.answer("❌ Вы уже участвуете в другой игре!", show_alert=True)
                    return

            game = active_games.get(room_id)
            if not game or game.is_finished or game.player2 is not None:
                logger.warning(f"join_game: {room_id} недоступна (exists={game is not None}, finished={game.is_finished if game else 'N/A'})")
                await call.answer("❌ Игра уже началась или завершена!", show_alert=True)
                return

            user = await get_user(joiner_id)
            if not user or user["balance"] < game.bet:
                logger.warning(f"join_game: user {joiner_id} недостаточно средств (balance={user['balance'] if user else 'N/A'}, need={game.bet})")
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

        config = GAMES_CONFIG[game.game_type]
        player_name = await get_username(call.from_user.id)

        try:
            if game.last_roll_message_id:
                await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
        except Exception:
            pass

        roll_msg = await get_bot().send_message(game.chat_id, f"{player_name} бросает {config['emoji']}...")
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
        except Exception as e:
            logger.error(f"Ошибка удаления кнопки: {e}")

        await process_dice_roll(game, call.from_user.id, dice_msg.dice.value)
        await call.answer()

    except Exception as e:
        logger.error(f"Ошибка в roll_dice_callback: {e}")
        await call.answer("❌ Ошибка при броске костей!", show_alert=True)


async def process_dice_roll(game: GameRoom, player_id: int, dice_value: int):
    game.results[player_id] = dice_value
    player_name = await get_username(player_id)
    config = GAMES_CONFIG[game.game_type]

    try:
        if game.last_roll_message_id:
            await get_bot().delete_message(game.chat_id, game.last_roll_message_id)
    except Exception:
        pass

    wait_msg = await get_bot().send_message(game.chat_id, f"⏳ {player_name} бросил {config['emoji']}, ожидаем результат...")
    game.last_roll_message_id = wait_msg.message_id

    async def show_result():
        try:
            await asyncio.sleep(6)
            try:
                await get_bot().delete_message(game.chat_id, wait_msg.message_id)
            except Exception:
                pass

            result_msg = await get_bot().send_message(
                game.chat_id, f"{player_name} выбросил {dice_value} {config['emoji']}!"
            )
            game.last_roll_message_id = result_msg.message_id

            if len(game.results) == 2:
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
                final = "⏰ Игра отменена — один из игроков не сделал бросок.\nСтавки возвращены обоим игрокам."
            else:
                final = "⏰ Игра отменена — никто не присоединился."
        else:
            if game.game_type == "футбол":
                p1_score_goal = p1_score == 5
                p2_score_goal = p2_score == 5
                if p1_score_goal and p2_score_goal:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "⚽ Оба забили гол! Ничья — ставки возвращены."
                elif p1_score_goal:
                    winner = game.player1
                    result_msg = f"⚽ Гол! {await get_username(winner)} забивает и побеждает!\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                elif p2_score_goal:
                    winner = game.player2
                    result_msg = f"⚽ Гол! {await get_username(winner)} забивает и побеждает!\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "⚽ Оба промахнулись! Ничья — ставки возвращены."
            elif game.game_type == "баскетбол":
                p1_basket = p1_score == 6
                p2_basket = p2_score == 6
                if p1_basket and p2_basket:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🏀 Оба попали в кольцо! Ничья — ставки возвращены."
                elif p1_basket:
                    winner = game.player1
                    result_msg = f"🏀 Попадание! {await get_username(winner)} выигрывает матч!\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                elif p2_basket:
                    winner = game.player2
                    result_msg = f"🏀 Попадание! {await get_username(winner)} выигрывает матч!\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🏀 Оба промахнулись! Ничья — ставки возвращены."
            elif game.game_type != "куб":
                if p1_score < 2 and p2_score < 2:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🎭 Оба игрока проиграли (результат < 2)! Ставки возвращены."
                elif p1_score < 2:
                    winner = game.player2
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет\n❌ {await get_username(game.player1)} проиграл (результат < 2)"
                elif p2_score < 2:
                    winner = game.player1
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет\n❌ {await get_username(game.player2)} проиграл (результат < 2)"
                elif p1_score > p2_score:
                    winner = game.player1
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                elif p2_score > p1_score:
                    winner = game.player2
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🎭 Ничья! Ставки возвращены обоим игрокам."
            else:
                if p1_score > p2_score:
                    winner = game.player1
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                elif p2_score > p1_score:
                    winner = game.player2
                    result_msg = f"🏆 Победитель: {await get_username(winner)}\n💰 Выигрыш: {prize} монет\n💼 Комиссия: {commission} монет"
                else:
                    await update_balance(game.player1, game.bet, "refund")
                    await update_balance(game.player2, game.bet, "refund")
                    result_msg = "🎭 Ничья! Ставки возвращены обоим игрокам."

            if winner:
                await update_balance(winner, prize, "win")
                conn = await get_db()
                try:
                    await conn.execute(
                        "UPDATE users SET games_played = games_played + 1, wins = wins + 1 WHERE user_id = ?",
                        (winner,),
                    )
                    loser = game.player2 if winner == game.player1 else game.player1
                    await conn.execute(
                        "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
                        (loser,),
                    )
                    await conn.commit()
                finally:
                    await conn.close()

            final = (
                f"🎲 Результаты игры в {GAMES_CONFIG[game.game_type]['emoji']}:\n"
                f"{await get_username(game.player1)}: {p1_score}\n"
                f"{await get_username(game.player2)}: {p2_score}\n\n"
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

        await get_bot().send_message(game.chat_id, final)

        if game.player2:
            await get_bot().send_message(game.player1, f"🎮 Игра завершена!\n{final}")
            await get_bot().send_message(game.player2, f"🎮 Игра завершена!\n{final}")
        else:
            await get_bot().send_message(game.player1, f"🎮 Игра завершена!\n{final}")

        game.is_finished = True

        async with active_games_lock:
            if game.room_id in active_games:
                del active_games[game.room_id]

        logger.info(f"Игра завершена: room_id={game.room_id}, winner={winner}")

    except Exception as e:
        logger.error(f"Ошибка в determine_winner: {e}")
        try:
            await get_bot().send_message(game.chat_id, "❌ Произошла ошибка при завершении игры!")
        except Exception:
            pass
        async with active_games_lock:
            if game.room_id in active_games:
                game.is_finished = True
                del active_games[game.room_id]


async def game_timeout(room_id: str, delay: int):
    await asyncio.sleep(delay)

    game = None
    need_auto_roll = False

    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            logger.info(f"game_timeout: {room_id} уже завершена, пропускаем")
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
            logger.info(f"game_timeout: {room_id} отменена (нет второго игрока)")
            return
        else:
            need_auto_roll = True

    if need_auto_roll and game:
        await auto_roll_dice(game)


async def auto_roll_dice(game: GameRoom):
    config = GAMES_CONFIG[game.game_type]
    if game.player1 not in game.results:
        d1 = await get_bot().send_dice(game.chat_id, emoji=config["emoji"])
        game.results[game.player1] = d1.dice.value
    if game.player2 not in game.results:
        d2 = await get_bot().send_dice(game.chat_id, emoji=config["emoji"])
        game.results[game.player2] = d2.dice.value

    await determine_winner(game)
