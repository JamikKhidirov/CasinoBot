import asyncio
import logging
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "7042929053:AAEsz4mIBA6P2ZKoPRiMuad1UIdR8dS9TQE"
ADMIN_ID = 1819756249
COMMISSION_RATE = Decimal("0.1")
DB_NAME = "casino.db"
PROXY_URL = None  # Например "http://proxy:8080" или "socks5://proxy:1080"
INITIAL_BALANCE = 1000
INITIAL_BOT_BALANCE = 500
DAILY_BONUS = 500
DAILY_BOT_BONUS = 200

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
router = Router()
dp.include_router(router)

GAMES_CONFIG = {
    "куб": {"command": "куб", "emoji": "🎲", "timeout": 30},
    "боулинг": {"command": "боулинг", "emoji": "🎳", "timeout": 30},
    "дротики": {"command": "дротики", "emoji": "🎯", "timeout": 30},
    "баскетбол": {"command": "баскетбол", "emoji": "🏀", "timeout": 30},
    "футбол": {"command": "футбол", "emoji": "⚽", "timeout": 30},
}


class DepositState(StatesGroup):
    waiting_for_amount = State()


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
                bot_balance INTEGER DEFAULT 500,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                last_bonus DATE,
                is_muted INTEGER DEFAULT 0,
                muted_until TEXT
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
            CREATE TABLE IF NOT EXISTS muted_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                reason TEXT,
                muted_at TEXT,
                muted_until TEXT
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
            "INSERT OR IGNORE INTO users (user_id, username, balance, bot_balance) VALUES (?, ?, ?, ?)",
            (tg_user.id, username, INITIAL_BALANCE, INITIAL_BOT_BALANCE),
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


async def update_bot_balance(user_id: int, amount: int, tr_type: str) -> None:
    conn = await get_db()
    try:
        timestamp = datetime.now().isoformat()
        await conn.execute(
            "UPDATE users SET bot_balance = bot_balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, amount, tr_type, timestamp),
        )
        await conn.commit()
    finally:
        await conn.close()


async def is_user_muted(user_id: int) -> bool:
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT is_muted, muted_until FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False
        if row["is_muted"] == 0:
            return False
        if row["muted_until"]:
            try:
                until = datetime.fromisoformat(row["muted_until"])
                if datetime.now() > until:
                    await conn.execute(
                        "UPDATE users SET is_muted = 0, muted_until = NULL WHERE user_id = ?",
                        (user_id,),
                    )
                    await conn.commit()
                    return False
            except (ValueError, TypeError):
                pass
        return True
    finally:
        await conn.close()


async def get_all_users_list() -> list[dict]:
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, balance, bot_balance, is_muted FROM users ORDER BY user_id"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def find_user_by_username(username: str) -> Optional[dict]:
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, username, balance, bot_balance, is_muted FROM users WHERE username = ?",
            (username.lstrip("@"),),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


def mute_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔇 Замутить игрока", callback_data="admin_mute_list")],
            [InlineKeyboardButton(text="🔊 Размутить игрока", callback_data="admin_unmute_list")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ]
    )


# ─── Game Room ────────────────────────────────────────────────────────────────


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


def game_keyboard(room_id: str, label: str = "🎮 Присоединиться к игре") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"join_{room_id}")]
        ]
    )


def roll_keyboard(room_id: str, player_id: int, emoji: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Бросить {emoji}", callback_data=f"roll_{room_id}_{player_id}")]
        ]
    )


# ─── Handlers ─────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message):
    await create_user(message.from_user)
    text = (
        f"🎰 Добро пожаловать в Casino Bot, {message.from_user.first_name}!\n\n"
        "🕹 Доступные команды:\n"
        "/профиль — Ваш игровой профиль (баланс PVP + бот-монеты)\n"
        "/топ — Топ игроков\n"
        "/бонус — Ежедневный бонус (PVP)\n"
        "/ботбонус — Ежедневный бонус (бот-монеты)\n"
        "/игры — Меню выбора режима\n"
        "/активные — Активные игры\n"
        "/разблокировать — Отменить все свои игры и получить возврат\n"
        "\n🎮 Режимы игры:\n"
        "🤖 `/сботом [игра] [ставка]` — Игра с ботом (в ЛС, бот-монеты)\n"
        "👥 `/игры` → \"С игроками\" — PVP (только в группе)\n"
        "\n🕹 Игры: куб 🎲, боулинг 🎳, дротики 🎯, баскетбол 🏀, футбол ⚽"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Выбрать режим игры", callback_data="games_menu")],
            [InlineKeyboardButton(text="📊 Профиль", callback_data="myprofile")],
        ]
    )
    await message.answer(text, reply_markup=markup)


@router.message(Command("профиль"))
async def cmd_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден! Напишите /start")
        return

    if message.chat.type != "private":
        await message.reply("ℹ️ Для просмотра профиля и пополнения баланса перейдите в личные сообщения с ботом.")
        return

    text = (
        f"📊 Профиль игрока {message.from_user.first_name}\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"💰 Баланс (PVP): {user['balance']} монет\n"
        f"🤖 Баланс (бот): {user['bot_balance']} бот-монет\n"
        f"🎮 Сыграно игр: {user['games_played']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"📅 Последний бонус: {user['last_bonus'] or 'ещё не получал'}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить PVP баланс", callback_data="deposit")],
            [InlineKeyboardButton(text="🎮 В игры", callback_data="games_menu")],
        ]
    )
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "deposit")
async def cb_deposit(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type != "private":
        await call.answer("ℹ️ Для пополнения баланса перейдите в личные сообщения с ботом.", show_alert=True)
        bot_username = (await bot.me()).username
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
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Запрос на пополнение:\n\n"
            f"👤 Пользователь: {username}\n"
            f"🆔 ID: {user_id}\n"
            f"💵 Сумма: {amount} монет",
            reply_markup=markup,
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления админу: {e}")


@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def cb_admin_decision(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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
            await bot.send_message(user_id, f"✅ Ваш баланс пополнен на {amount} монет!")
        else:
            status = "rejected"
            await bot.send_message(user_id, "❌ Ваш запрос на пополнение был отклонён.")

        await conn.execute(
            "UPDATE deposit_requests SET status = ? WHERE user_id = ? AND amount = ? AND status = 'pending'",
            (status, user_id, amount),
        )
        await conn.commit()
    finally:
        await conn.close()

    await call.answer(f"Статус обновлён: {status}")
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass


@router.message(Command("пополнить"))
async def cmd_admin_add_balance(message: Message):
    if message.from_user.id != ADMIN_ID:
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
    await bot.send_message(user_id, f"Администратор пополнил ваш баланс на {amount} монет! 🎉")


@router.message(Command("бонус"))
async def cmd_daily_bonus(message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if not user:
        await message.reply("❌ Пользователь не найден! Напишите /start")
        return

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
            logging.error(f"Ошибка даты бонуса для {user_id}: {e}")

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
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Играть с ботом (в ЛС)", callback_data="play_bot_menu")],
            [InlineKeyboardButton(text="👥 Играть с игроками (в группе)", callback_data="play_pvp_menu")],
            [InlineKeyboardButton(text="📊 Профиль", callback_data="myprofile")],
        ]
    )
    await message.answer(
        "🎮 **Выберите режим игры:**\n\n"
        "🤖 **С ботом** — играйте один на один с ботом в личных сообщениях\n"
        "   *Отдельная валюта (бот-монеты), ежедневный бонус*\n\n"
        "👥 **С игроками** — соревнуйтесь с другими игроками\n"
        "   *Только в групповых чатах. Добавьте бота в группу!*",
        reply_markup=markup,
    )


@router.callback_query(F.data == "games_menu")
async def cb_games_menu(call: CallbackQuery):
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Играть с ботом (в ЛС)", callback_data="play_bot_menu")],
            [InlineKeyboardButton(text="👥 Играть с игроками (в группе)", callback_data="play_pvp_menu")],
            [InlineKeyboardButton(text="📊 Профиль", callback_data="myprofile")],
        ]
    )
    await call.message.edit_text(
        "🎮 **Выберите режим игры:**\n\n"
        "🤖 **С ботом** — играйте один на один с ботом в личных сообщениях\n"
        "   *Отдельная валюта (бот-монеты), ежедневный бонус*\n\n"
        "👥 **С игроками** — соревнуйтесь с другими игроками\n"
        "   *Только в групповых чатах. Добавьте бота в группу!*",
        reply_markup=markup,
    )
    await call.answer()


@router.callback_query(F.data == "play_bot_menu")
async def cb_play_bot_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("🤖 Играть с ботом можно только в ЛС!", show_alert=True)
        return
    text = "🤖 **Игра с ботом**\n\nВыберите игру и укажите ставку:\n\n"
    for game_type, cfg in GAMES_CONFIG.items():
        text += f"/сботом {cfg['command']} [ставка] — {game_type} {cfg['emoji']}\n"
    text += "\nПример: `/сботом куб 50`"
    await call.message.edit_text(text)
    await call.answer()


@router.callback_query(F.data == "play_pvp_menu")
async def cb_play_pvp_menu(call: CallbackQuery):
    if call.message.chat.type == "private":
        bot_username = (await bot.me()).username
        text = (
            "👥 **Игра с игроками**\n\n"
            "❌ Этот режим работает **только в групповых чатах**!\n\n"
            "📌 **Как играть с игроками:**\n"
            "1. Добавьте бота в группу: `@{}`\n"
            "2. Напишите в группе: `/куб 100`\n"
            "3. Другой игрок нажимает «Присоединиться»\n\n"
            "💡 Дайте боту права администратора в группе, "
            "чтобы он мог отправлять сообщения и реагировать на команды."
        ).format(bot_username)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Копировать username", callback_data=f"copy_{bot_username}")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")],
            ]
        )
        await call.message.edit_text(text, reply_markup=markup)
        await call.answer("Добавьте бота в группу!", show_alert=False)
        return

    text = "👥 **Игра с игроками**\n\nВыберите игру и укажите ставку:\n\n"
    for game_type, cfg in GAMES_CONFIG.items():
        text += f"/{cfg['command']} [ставка] — {game_type} {cfg['emoji']}\n"
    text += "\nПример: `/куб 100`"
    await call.message.edit_text(text)
    await call.answer()


@router.callback_query(F.data == "myprofile")
async def cb_myprofile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден!", show_alert=True)
        return
    text = (
        f"📊 Профиль игрока {call.from_user.first_name}\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"💰 Баланс (PVP): {user['balance']} монет\n"
        f"🤖 Баланс (бот): {user['bot_balance']} бот-монет\n"
        f"🎮 Сыграно игр: {user['games_played']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"📅 Последний бонус: {user['last_bonus'] or 'ещё не получал'}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить PVP баланс", callback_data="deposit")],
            [InlineKeyboardButton(text="🎮 В игры", callback_data="games_menu")],
        ]
    )
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)
    await call.answer()


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
                    logging.error(f"Refund error: {e}")
                to_remove.append(rid)

        for rid in to_remove:
            del active_games[rid]

    await message.reply(
        f"✅ Все ваши игры отменены! Возвращено: {refunded} монет\n"
        "Теперь вы можете создавать новые игры!"
    )


@router.message(Command("игроки"))
async def cmd_all_players(message: Message):
    if message.from_user.id != ADMIN_ID:
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


# ─── Play with Bot ────────────────────────────────────────────────────────────


async def bot_player1_roll(room_id: str, game: GameRoom):
    config = GAMES_CONFIG[game.game_type]
    await asyncio.sleep(2)
    bot_value = random.randint(1, 6)
    game.results[0] = bot_value
    await bot.send_message(
        game.chat_id,
        f"🤖 Бот выбрасывает {config['emoji']}... **{bot_value}**!",
    )
    if len(game.results) == 2:
        await determine_bot_winner(game)


async def determine_bot_winner(game: GameRoom):
    try:
        await asyncio.sleep(1)
        p1_score = game.results.get(game.player1, 0)
        bot_score = game.results.get(0, 0)

        total_bet = game.bet * 2
        result_msg = ""
        winner = None

        if p1_score > bot_score:
            winner = game.player1
            prize = game.bet
            await update_bot_balance(game.player1, prize, "bot_win")
            result_msg = f"🏆 Вы победили бота! Выигрыш: {prize} бот-монет!"
        elif bot_score > p1_score:
            result_msg = f"❌ Бот победил! Вы проиграли {game.bet} бот-монет."
        else:
            await update_bot_balance(game.player1, game.bet, "bot_tie")
            result_msg = "🎭 Ничья! Ставка возвращена."

        conn = await get_db()
        try:
            await conn.execute(
                "UPDATE users SET games_played = games_played + 1, wins = wins + 1 WHERE user_id = ?",
                (winner,),
            ) if winner else await conn.execute(
                "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
                (game.player1,),
            )
            await conn.commit()
        finally:
            await conn.close()

        final = (
            f"🎲 **Результат игры с ботом** {game.game_type}:\n"
            f"Вы: {p1_score}\n"
            f"🤖 Бот: {bot_score}\n\n"
            f"{result_msg}"
        )

        try:
            if game.player1_dice_message_id:
                await bot.delete_message(game.chat_id, game.player1_dice_message_id)
            if game.last_roll_message_id:
                await bot.delete_message(game.chat_id, game.last_roll_message_id)
            if game.message_id:
                await bot.delete_message(game.chat_id, game.message_id)
        except Exception:
            pass

        await bot.send_message(game.chat_id, final)
        game.is_finished = True

        async with active_games_lock:
            if game.room_id in active_games:
                del active_games[game.room_id]

    except Exception as e:
        logging.error(f"Ошибка в determine_bot_winner: {e}")


@router.message(Command("сботом"))
async def cmd_play_with_bot(message: Message):
    if message.chat.type != "private":
        await message.reply("❌ Игра с ботом доступна только в личных сообщениях!\nНапишите /start в ЛС.")
        return

    if await is_user_muted(message.from_user.id):
        await message.reply("❌ Вы замучены и не можете играть.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❌ Формат: `/сботом [игра] [ставка]`\nПример: `/сботом куб 50`")
        return

    game_name = parts[1].lower()
    if game_name not in GAMES_CONFIG:
        games_list = ", ".join(GAMES_CONFIG.keys())
        await message.reply(f"❌ Неизвестная игра. Доступны: {games_list}")
        return

    try:
        bet = int(parts[2])
    except ValueError:
        await message.reply("❌ Ставка должна быть числом!")
        return

    if bet < 5:
        await message.reply("❌ Минимальная ставка с ботом — 5 бот-монет!")
        return

    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user)
        user = await get_user(message.from_user.id)

    bot_bal = user["bot_balance"]
    if bot_bal < bet:
        await message.reply(f"❌ Недостаточно бот-монет! Баланс: {bot_bal} бот-монет\nПолучите бонус: /ботбонус")
        return

    await update_bot_balance(message.from_user.id, -bet, "bot_reserve")

    config = GAMES_CONFIG[game_name]
    room_id = f"botgame-{uuid.uuid4()}"
    game = GameRoom(room_id, game_name, bet, message.from_user.id)

    async with active_games_lock:
        active_games[room_id] = game

    player_name = await get_username(message.from_user.id)
    msg = await message.answer(
        f"🤖 **Игра с ботом в {config['emoji']}!**\n"
        f"💵 Ставка: {bet} бот-монет\n\n"
        f"Нажмите кнопку, чтобы сделать бросок:",
        reply_markup=roll_keyboard(room_id, message.from_user.id, config["emoji"]),
    )

    game.chat_id = message.chat.id
    game.message_id = msg.message_id
    logging.info(f"Создана игра с ботом: room_id={room_id}, game_type={game_name}, player1={message.from_user.id}")


# Override roll handler for bot games
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

            if room_id.startswith("botgame-"):
                if call.from_user.id != game.player1:
                    await call.answer("❌ Это не ваша игра!", show_alert=True)
                    return
                if call.from_user.id in game.results:
                    await call.answer("❌ Вы уже сделали бросок!", show_alert=True)
                    return
                is_bot_game = True
            else:
                current = game.player1 if game.player1_turn else game.player2
                if call.from_user.id != current:
                    await call.answer("❌ Сейчас не ваш ход!", show_alert=True)
                    return
                if call.from_user.id in game.results:
                    await call.answer("❌ Вы уже сделали бросок!", show_alert=True)
                    return
                is_bot_game = False

        config = GAMES_CONFIG[game.game_type]
        player_name = await get_username(call.from_user.id)

        try:
            if game.last_roll_message_id:
                await bot.delete_message(game.chat_id, game.last_roll_message_id)
        except Exception:
            pass

        roll_msg = await bot.send_message(game.chat_id, f"{player_name} бросает {config['emoji']}...")
        game.last_roll_message_id = roll_msg.message_id

        dice_msg = await bot.send_dice(game.chat_id, emoji=config["emoji"], disable_notification=True)

        if call.from_user.id == game.player1:
            game.player1_dice_message_id = dice_msg.message_id
        else:
            game.player2_dice_message_id = dice_msg.message_id

        try:
            btn_id = game.player1_button_message_id if call.from_user.id == game.player1 else game.player2_button_message_id
            if btn_id:
                await bot.delete_message(call.from_user.id, btn_id)
                if call.from_user.id == game.player1:
                    game.player1_button_message_id = None
                else:
                    game.player2_button_message_id = None
        except Exception as e:
            logging.error(f"Ошибка удаления кнопки: {e}")

        game.results[call.from_user.id] = dice_msg.dice.value

        if is_bot_game:
            asyncio.ensure_future(process_bot_roll(game, call.from_user.id, dice_msg.dice.value))
        else:
            await process_pvp_roll(game, call.from_user.id, dice_msg.dice.value)

        await call.answer()

    except Exception as e:
        logging.error(f"Ошибка в roll_dice_callback: {e}")
        await call.answer("❌ Ошибка при броске костей!", show_alert=True)


async def process_bot_roll(game: GameRoom, player_id: int, dice_value: int):
    player_name = await get_username(player_id)
    config = GAMES_CONFIG[game.game_type]

    try:
        if game.last_roll_message_id:
            await bot.delete_message(game.chat_id, game.last_roll_message_id)
    except Exception:
        pass

    result_msg = await bot.send_message(
        game.chat_id, f"{player_name} выбросил {dice_value} {config['emoji']}!"
    )
    game.last_roll_message_id = result_msg.message_id

    await asyncio.sleep(1)
    await bot_player1_roll(game.room_id, game)


async def process_pvp_roll(game: GameRoom, player_id: int, dice_value: int):
    player_name = await get_username(player_id)
    config = GAMES_CONFIG[game.game_type]

    try:
        if game.last_roll_message_id:
            await bot.delete_message(game.chat_id, game.last_roll_message_id)
    except Exception:
        pass

    wait_msg = await bot.send_message(game.chat_id, f"⏳ {player_name} бросил {config['emoji']}, ожидаем результат...")
    game.last_roll_message_id = wait_msg.message_id

    async def show_result():
        try:
            await asyncio.sleep(4)
            try:
                await bot.delete_message(game.chat_id, wait_msg.message_id)
            except Exception:
                pass

            result_msg = await bot.send_message(
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
            logging.error(f"Ошибка при отправке результата: {e}")

    asyncio.ensure_future(show_result())


@router.message(Command("ботбонус"))
async def cmd_bot_daily_bonus(message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if not user:
        await message.reply("❌ Пользователь не найден! Напишите /start")
        return

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
            logging.error(f"Ошибка даты бонуса для {user_id}: {e}")

    await update_bot_balance(user_id, DAILY_BOT_BONUS, "bot_bonus")
    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET last_bonus = ? WHERE user_id = ?",
            (today_d.strftime("%Y-%m-%d"), user_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"🎉 Вы получили ежедневный бонус: {DAILY_BOT_BONUS} бот-монет!\n"
                        f"Теперь у вас {user['bot_balance'] + DAILY_BOT_BONUS} бот-монет.")


# ─── Admin: Mute/Unute by Username ────────────────────────────────────────────


@router.message(Command("админы"))
async def cmd_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Доступ запрещён!")
        return
    text = (
        "👑 **Админ-панель**\n\n"
        "🔹 `/админы` — это меню\n"
        "🔹 `/игроки` — все игроки\n"
        "🔹 `/мут [@username или ID] [длительность] [причина]` — замутить\n"
        "🔹 `/размут [@username или ID]` — размутить\n"
        "🔹 `/пополнить [ID] [сумма]` — пополнить PVP баланс\n\n"
        "Длительность: `forever`, `1d`, `2h`, `30m`\n"
        "Пример: `/мут @user 1d Спам`"
    )
    markup = mute_keyboard()
    await message.reply(text, reply_markup=markup)


@router.callback_query(F.data == "admin_mute_list")
async def cb_admin_mute_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    users = await get_all_users_list()
    if not users:
        await call.answer("Нет пользователей.", show_alert=True)
        return

    rows = []
    for u in users:
        name = f"@{u['username']}" if u['username'] else f"ID {u['user_id']}"
        muted = "🔇" if u['is_muted'] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{muted} {name}",
                callback_data=f"mute_user_{u['user_id']}",
            )
        ])

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    await call.message.edit_text("👥 **Выберите пользователя для мута:**", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "admin_unmute_list")
async def cb_admin_unmute_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    users = await get_all_users_list()
    muted_users_list = [u for u in users if u['is_muted'] == 1]
    if not muted_users_list:
        await call.answer("Нет замученных пользователей.", show_alert=True)
        return

    rows = []
    for u in muted_users_list:
        name = f"@{u['username']}" if u['username'] else f"ID {u['user_id']}"
        rows.append([
            InlineKeyboardButton(
                text=f"🔊 {name}",
                callback_data=f"unmute_user_{u['user_id']}",
            )
        ])

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    await call.message.edit_text("👥 **Выберите пользователя для размута:**", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("mute_user_"))
async def cb_mute_user_select(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    user_id = int(call.data.split("_")[2])
    user = await get_user(user_id)
    if not user:
        await call.answer("❌ Пользователь не найден!", show_alert=True)
        return

    name = f"@{user['username']}" if user['username'] else f"ID {user['user_id']}"
    text = (
        f"🔇 **Мут пользователя {name}**\n\n"
        f"Напишите причину и длительность мута одним сообщением.\n\n"
        f"Формат: `причина | длительность`\n"
        f"Длительность: `forever`, `1d`, `2h`, `30m`\n\n"
        f"Пример: `Спам | 1d`"
    )
    await call.message.edit_text(text)
    await call.answer()


@router.callback_query(F.data.startswith("unmute_user_"))
async def cb_unmute_user_select(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    target_id = int(call.data.split("_")[2])
    user = await get_user(target_id)
    if not user:
        await call.answer("❌ Пользователь не найден!", show_alert=True)
        return

    conn = await get_db()
    try:
        await conn.execute("UPDATE users SET is_muted = 0, muted_until = NULL WHERE user_id = ?", (target_id,))
        await conn.execute("DELETE FROM muted_users WHERE user_id = ?", (target_id,))
        await conn.commit()
    finally:
        await conn.close()

    name = f"@{user['username']}" if user['username'] else f"ID {user['user_id']}"
    await call.message.edit_text(f"✅ {name} размучен!")
    await call.answer("✅ Пользователь размучен!")

    try:
        await bot.send_message(target_id, "✅ Вы были размучены и снова можете играть!")
    except Exception:
        pass


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return
    markup = mute_keyboard()
    text = (
        "👑 **Админ-панель**\n\n"
        "🔹 `/админы` — это меню\n"
        "🔹 `/игроки` — все игроки\n"
        "🔹 `/мут [@username или ID] [длительность] [причина]` — замутить\n"
        "🔹 `/размут [@username или ID]` — размутить\n"
        "🔹 `/пополнить [ID] [сумма]` — пополнить PVP баланс\n\n"
        "Длительность: `forever`, `1d`, `2h`, `30m`\n"
        "Пример: `/мут @user 1d Спам`"
    )
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()


@router.message(Command("мут"))
async def cmd_mute_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.reply("❌ Формат: `/мут [@username или ID] [длительность] [причина]`\n"
                            "Пример: `/мут @user 1d Спам`\n"
                            "Длительность: forever, 1d, 2h, 30m")
        return

    target = parts[1].lstrip("@")
    duration_str = parts[2].lower()
    reason = parts[3] if len(parts) > 3 else "Без причины"

    target_id = None
    target_username = target

    try:
        target_id = int(target)
    except ValueError:
        user_data = await find_user_by_username(target)
        if user_data:
            target_id = user_data["user_id"]
        else:
            await message.reply(f"❌ Пользователь @{target} не найден в базе!")
            return

    user = await get_user(target_id)
    if not user:
        await message.reply(f"❌ Пользователь с ID {target_id} не найден!")
        return

    try:
        if duration_str == "forever":
            muted_until = None
        elif duration_str.endswith("d"):
            days = int(duration_str[:-1])
            muted_until = (datetime.now() + timedelta(days=days)).isoformat()
        elif duration_str.endswith("h"):
            hours = int(duration_str[:-1])
            muted_until = (datetime.now() + timedelta(hours=hours)).isoformat()
        elif duration_str.endswith("m"):
            minutes = int(duration_str[:-1])
            muted_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        else:
            await message.reply("❌ Неверный формат длительности! Используйте: forever, 1d, 2h, 30m")
            return
    except ValueError:
        await message.reply("❌ Неверный формат длительности!")
        return

    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET is_muted = 1, muted_until = ? WHERE user_id = ?",
            (muted_until, target_id),
        )
        await conn.execute(
            "INSERT OR REPLACE INTO muted_users (user_id, username, reason, muted_at, muted_until) VALUES (?, ?, ?, ?, ?)",
            (target_id, user["username"], reason, datetime.now().isoformat(), muted_until),
        )
        await conn.commit()
    finally:
        await conn.close()

    name = f"@{user['username']}" if user['username'] else f"ID {user['user_id']}"
    duration_text = "навсегда" if not muted_until else f"до {muted_until}"
    await message.reply(f"✅ {name} замучен {duration_text}.\nПричина: {reason}")

    try:
        await bot.send_message(
            target_id,
            f"🔇 Вы замучены!\nПричина: {reason}\nСрок: {duration_text}",
        )
    except Exception:
        pass

    if target_id in [g.player1 for g in active_games.values()] or target_id in [g.player2 for g in active_games.values() if g.player2]:
        async with active_games_lock:
            for rid, g in list(active_games.items()):
                if target_id in (g.player1, g.player2) and not g.is_finished:
                    g.is_finished = True
                    del active_games[rid]
                    await bot.send_message(g.chat_id, f"⏹ Игра отменена — игрок {name} замучен.")


@router.message(Command("размут"))
async def cmd_unmute_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❌ Формат: `/размут [@username или ID]`")
        return

    target = parts[1].lstrip("@")
    target_id = None

    try:
        target_id = int(target)
    except ValueError:
        user_data = await find_user_by_username(target)
        if user_data:
            target_id = user_data["user_id"]
        else:
            await message.reply(f"❌ Пользователь @{target} не найден!")
            return

    user = await get_user(target_id)
    if not user:
        await message.reply(f"❌ Пользователь с ID {target_id} не найден!")
        return

    conn = await get_db()
    try:
        await conn.execute("UPDATE users SET is_muted = 0, muted_until = NULL WHERE user_id = ?", (target_id,))
        await conn.execute("DELETE FROM muted_users WHERE user_id = ?", (target_id,))
        await conn.commit()
    finally:
        await conn.close()

    name = f"@{user['username']}" if user['username'] else f"ID {user['user_id']}"
    await message.reply(f"✅ {name} размучен!")

    try:
        await bot.send_message(target_id, "✅ Вы были размучены и снова можете играть!")
    except Exception:
        pass


# ─── Game Creation ────────────────────────────────────────────────────────────


def make_game_handler(game_type: str):
    @router.message(Command(GAMES_CONFIG[game_type]["command"]))
    async def handler(message: Message):
        try:
            if message.chat.type == "private":
                bot_username = (await bot.me()).username
                text = (
                    "👥 **Игра с игроками** доступна **только в групповых чатах**!\n\n"
                    "📌 **Как играть:**\n"
                    "1. Добавьте бота в группу: @{}\n"
                    "2. Напишите в группе команду\n\n"
                    "🤖 **Хотите сыграть с ботом?** Используйте `/сботом {} [ставка]` в ЛС!"
                ).format(bot_username, GAMES_CONFIG[game_type]["command"])
                await message.reply(text)
                return

            if await is_user_muted(message.from_user.id):
                await message.reply("❌ Вы замучены и не можете играть.")
                return

            async with active_games_lock:
                finished = [rid for rid, g in active_games.items() if g.is_finished]
                for rid in finished:
                    del active_games[rid]

                for g in active_games.values():
                    if not g.is_finished and message.from_user.id in (g.player1, g.player2):
                        await message.reply("❌ Вы уже участвуете в другой игре! Дождитесь её завершения.")
                        return

            parts = message.text.split()
            if len(parts) < 2:
                await message.reply(f"❌ Укажите ставку! Пример: /{GAMES_CONFIG[game_type]['command']} [ставка]")
                return

            bet = int(parts[1])
            if bet < 10:
                await message.reply("❌ Минимальная ставка — 10 монет!")
                return

            user = await get_user(message.from_user.id)
            if not user or user["balance"] < bet:
                await message.reply("❌ Недостаточно средств на балансе!")
                return

            await update_balance(message.from_user.id, -bet, "reserve")

            room_id = f"game-{uuid.uuid4()}"
            game = GameRoom(room_id, game_type, bet, message.from_user.id)

            async with active_games_lock:
                active_games[room_id] = game

            player1_name = await get_username(message.from_user.id)
            group_msg = (
                f"🎉 Создана новая игра в {GAMES_CONFIG[game_type]['emoji']}!\n"
                f"💵 Ставка: {bet} монет\n"
                f"⏳ Время на присоединение: {GAMES_CONFIG[game_type]['timeout']} сек\n"
                f"Игрок 1: {player1_name}\n"
                f"Места: 1/2"
            )
            sent = await message.answer(group_msg, reply_markup=game_keyboard(room_id))

            game.chat_id = message.chat.id
            game.message_id = sent.message_id

            asyncio.ensure_future(game_timeout(room_id, GAMES_CONFIG[game_type]["timeout"]))

            logging.info(f"Создана игра: room_id={room_id}, game_type={game_type}, player1={message.from_user.id}")

        except ValueError:
            await message.reply("❌ Некорректная ставка! Используйте числовое значение.")
        except Exception as e:
            logging.error(f"Ошибка при создании игры: {e}")
            await message.reply("❌ Произошла ошибка при создании игры!")
            try:
                await update_balance(message.from_user.id, bet, "refund")
            except Exception:
                pass

    return handler


for gt in GAMES_CONFIG:
    make_game_handler(gt)


# ─── Join Game ────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("join_"))
async def cb_join_game(call: CallbackQuery):
    try:
        room_id = call.data.split("_", 1)[1]

        async with active_games_lock:
            for rid, g in active_games.items():
                if not g.is_finished and call.from_user.id in (g.player1, g.player2) and rid != room_id:
                    await call.answer("❌ Вы уже участвуете в другой игре!", show_alert=True)
                    return

            game = active_games.get(room_id)
            if not game or game.is_finished or game.player2 is not None:
                await call.answer("❌ Игра уже началась или завершена!", show_alert=True)
                return

            user = await get_user(call.from_user.id)
            if not user or user["balance"] < game.bet:
                await call.answer("❌ Недостаточно средств для присоединения!", show_alert=True)
                return

            if game.player1 == call.from_user.id:
                await call.answer("❌ Вы не можете присоединиться к своей же игре!", show_alert=True)
                return

            await update_balance(call.from_user.id, -game.bet, "reserve")
            game.add_player(call.from_user.id)

        await call.answer("✅ Вы присоединились к игре!")
        await start_game(game)

    except Exception as e:
        logging.exception(f"Ошибка в join_game: {e}")
        await call.answer("❌ Произошла ошибка!", show_alert=True)


async def start_game(game: GameRoom):
    try:
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
            await bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game.message_id,
                text=text,
                reply_markup=roll_keyboard(game.room_id, game.player1, config["emoji"]),
            )
        except Exception:
            sent = await bot.send_message(game.chat_id, text, reply_markup=roll_keyboard(game.room_id, game.player1, config["emoji"]))
            game.message_id = sent.message_id

        await ask_for_dice_roll(game, game.player1)

    except Exception as e:
        logging.error(f"Ошибка в start_game: {e}")


async def ask_for_dice_roll(game: GameRoom, player_id: int):
    try:
        config = GAMES_CONFIG[game.game_type]
        opponent_id = game.player2 if player_id == game.player1 else game.player1
        opp_name = await get_username(opponent_id)

        msg = await bot.send_message(
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
        logging.error(f"Ошибка при отправке кнопки броска: {e}")


# ─── Winner Determination ──────────────────────────────────────────────────────


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
            await bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game.message_id,
                text=text,
                reply_markup=roll_keyboard(game.room_id, next_player, config["emoji"]),
            )
        except Exception:
            sent = await bot.send_message(game.chat_id, text, reply_markup=roll_keyboard(game.room_id, next_player, config["emoji"]))
            game.message_id = sent.message_id

        await ask_for_dice_roll(game, next_player)

    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления о ходе: {e}")


async def determine_winner(game: GameRoom):
    try:
        await asyncio.sleep(2)

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
            if game.game_type != "куб":
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

        # ── Cleanup messages ──
        try:
            if game.player1_dice_message_id:
                await bot.delete_message(game.chat_id, game.player1_dice_message_id)
            if game.player2_dice_message_id:
                await bot.delete_message(game.chat_id, game.player2_dice_message_id)
            if game.last_roll_message_id:
                await bot.delete_message(game.chat_id, game.last_roll_message_id)
            if game.player1_button_message_id:
                await bot.delete_message(game.player1, game.player1_button_message_id)
            if game.player2_button_message_id and game.player2:
                await bot.delete_message(game.player2, game.player2_button_message_id)
            if game.message_id:
                await bot.delete_message(game.chat_id, game.message_id)
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщений: {e}")

        await bot.send_message(game.chat_id, final)

        if game.player2:
            await bot.send_message(game.player1, f"🎮 Игра завершена!\n{final}")
            await bot.send_message(game.player2, f"🎮 Игра завершена!\n{final}")
        else:
            await bot.send_message(game.player1, f"🎮 Игра завершена!\n{final}")

        game.is_finished = True

        async with active_games_lock:
            if game.room_id in active_games:
                del active_games[game.room_id]

        logging.info(f"Игра завершена: room_id={game.room_id}, winner={winner}")

    except Exception as e:
        logging.error(f"Ошибка в determine_winner: {e}")
        try:
            await bot.send_message(game.chat_id, "❌ Произошла ошибка при завершении игры!")
        except Exception:
            pass
        async with active_games_lock:
            if game.room_id in active_games:
                game.is_finished = True
                del active_games[game.room_id]


# ─── Timeout ──────────────────────────────────────────────────────────────────


async def game_timeout(room_id: str, delay: int):
    await asyncio.sleep(delay)

    async with active_games_lock:
        game = active_games.get(room_id)
        if not game or game.is_finished:
            return

        if game.player2 is None:
            await update_balance(game.player1, game.bet, "refund")
            try:
                await bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.message_id,
                    text="⏰ Игра отменена, никто не присоединился.",
                )
                if game.player1_button_message_id:
                    await bot.delete_message(game.player1, game.player1_button_message_id)
            except Exception:
                await bot.send_message(game.chat_id, "⏰ Игра отменена, никто не присоединился.")
        else:
            await auto_roll_dice(game)

        game.is_finished = True
        if game.room_id in active_games:
            del active_games[room_id]


async def auto_roll_dice(game: GameRoom):
    config = GAMES_CONFIG[game.game_type]
    if game.player1 not in game.results:
        d1 = await bot.send_dice(game.chat_id, emoji=config["emoji"])
        game.results[game.player1] = d1.dice.value
    if game.player2 not in game.results:
        d2 = await bot.send_dice(game.chat_id, emoji=config["emoji"])
        game.results[game.player2] = d2.dice.value

    await determine_winner(game)


# ─── Startup ──────────────────────────────────────────────────────────────────


async def main():
    await init_db()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
