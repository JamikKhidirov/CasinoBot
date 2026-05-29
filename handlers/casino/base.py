import asyncio
import logging
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import aiosqlite
from aiogram import Bot
from aiogram.fsm.state import State, StatesGroup

from config import OWNER_ID as ADMIN_ID
from utils.helpers import is_dev, is_admin, ban_user, unban_user, mute_user, unmute_user, add_warn, is_banned, is_muted, get_warns

logger = logging.getLogger(__name__)

COMMISSION_RATE = Decimal("0.1")
DB_NAME = "casino.db"
INITIAL_BALANCE = 1000
INITIAL_BLACKJACK_BALANCE = 1000
INITIAL_BOT_BALANCE = 500
DAILY_BONUS = 500
DAILY_BOT_BONUS = 200

_bot: Optional[Bot] = None


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Casino router not initialized")
    return _bot


def setup(bot_instance: Bot):
    global _bot
    _bot = bot_instance


GAMES_CONFIG = {
    "куб": {"command": "куб", "emoji": "🎲", "timeout": 30, "action": "бросает кубик"},
    "боулинг": {"command": "боулинг", "emoji": "🎳", "timeout": 30, "action": "бросает шар"},
    "дротики": {"command": "дротики", "emoji": "🎯", "timeout": 30, "action": "бросает дротик"},
    "баскетбол": {"command": "баскетбол", "emoji": "🏀", "timeout": 30, "action": "бросает мяч"},
    "футбол": {"command": "футбол", "emoji": "⚽", "timeout": 30, "action": "забивает пенальти"},
}

GAME_LIST_STRING = ", ".join(f"/{v['command']}" for v in GAMES_CONFIG.values())


class DepositState(StatesGroup):
    waiting_for_amount = State()


class PaymentProvideState(StatesGroup):
    waiting_for_details = State()


class WithdrawState(StatesGroup):
    waiting_for_card = State()


class GameStates(StatesGroup):
    waiting_for_bet = State()


class AdminAction(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()
    waiting_minutes = State()
    waiting_reason = State()


class MuteState(StatesGroup):
    waiting_for_details = State()


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
                blackjack_balance INTEGER DEFAULT 1000,
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
                created TEXT,
                payment_details TEXT
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
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                card_details TEXT,
                status TEXT DEFAULT 'pending',
                created TEXT
            );
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                amount INTEGER NOT NULL,
                created_by INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS promo_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                activated_at TEXT,
                FOREIGN KEY (code) REFERENCES promocodes(code)
            );
            CREATE TABLE IF NOT EXISTS solo_scores (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS blackjack_games (
                room_id TEXT PRIMARY KEY,
                bet INTEGER,
                creator_id INTEGER,
                chat_id INTEGER,
                created TEXT,
                is_finished INTEGER DEFAULT 0
            );
        """)
        await conn.commit()
    finally:
        await conn.close()

    # migration: add columns for existing DBs
    col_migrations = [
        ("payment_details", "TEXT"),
        ("bot_balance", "INTEGER DEFAULT 500"),
        ("blackjack_balance", "INTEGER DEFAULT 1000"),
        ("is_muted", "INTEGER DEFAULT 0"),
        ("muted_until", "TEXT"),
    ]
    for col_name, col_type in col_migrations:
        try:
            c2 = await get_db()
            await c2.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            await c2.commit()
            await c2.close()
        except Exception:
            try:
                await c2.close()
            except Exception:
                pass


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
            "INSERT OR IGNORE INTO users (user_id, username, balance, bot_balance, blackjack_balance) VALUES (?, ?, ?, ?, ?)",
            (tg_user.id, username, INITIAL_BALANCE, INITIAL_BOT_BALANCE, INITIAL_BLACKJACK_BALANCE),
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


async def update_blackjack_balance(user_id: int, amount: int, tr_type: str) -> None:
    conn = await get_db()
    try:
        timestamp = datetime.now().isoformat()
        await conn.execute(
            "UPDATE users SET blackjack_balance = blackjack_balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, amount, tr_type, timestamp),
        )
        await conn.commit()
    finally:
        await conn.close()


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


async def get_username(user_id: int) -> str:
    user = await get_user(user_id)
    if user and user["username"]:
        return "@" + user["username"]
    return f"Игрок {user_id}"


class BlackjackRoom:
    def __init__(self, room_id: str, bet: int, creator_id: int, chat_id: int):
        self.room_id = room_id
        self.bet = bet
        self.players: dict[int, list[int]] = {}
        self.player_names: dict[int, str] = {}
        self.dealer_cards: list[int] = []
        self.player_status: dict[int, str] = {}
        self.created = datetime.now()
        self.is_finished = False
        self.chat_id = chat_id
        self.message_id: Optional[int] = None
        self.creator_id = creator_id
        self.join_message_id: Optional[int] = None
        self.phase = "joining"


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
        self.timer_task: Optional[asyncio.Task] = None

    def add_player(self, player2: int) -> bool:
        if self.player2 is None:
            self.player2 = player2
            return True
        return False


active_games: dict[str, GameRoom] = {}
active_blackjack_games: dict[str, BlackjackRoom] = {}
active_games_lock = asyncio.Lock()

PERMISSIONS = {
    "view_players": "👥 Просмотр списка игроков",
    "view_stats": "📊 Просмотр статистики",
    "add_balance": "💰 Пополнение баланса",
    "approve_deposits": "📋 Одобрение запросов",
    "approve_withdrawals": "💸 Вывод средств (одобрение)",
    "create_promos": "🎟 Создание промокодов",
    "manage_games": "🎮 Управление играми",
}

GAME_EMOJIS = {cfg["emoji"]: gt for gt, cfg in GAMES_CONFIG.items()}


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


async def get_users_with_perm(permission: str) -> list[int]:
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT admin_id FROM admin_permissions WHERE permission = ?", (permission,)
        )
        rows = await cursor.fetchall()
        result = [r["admin_id"] for r in rows]
    finally:
        await conn.close()
    if ADMIN_ID not in result:
        result.append(ADMIN_ID)
    return result


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
