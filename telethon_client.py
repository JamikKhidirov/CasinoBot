import asyncio
import logging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from config import TELETHON_API_ID, TELETHON_API_HASH

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None
_auth_state: dict = {}  # user_id -> {"phone": str, "phone_code_hash": str, "client": TelegramClient}


async def get_telethon_client() -> TelegramClient:
    global _client
    if _client is not None and _client.is_connected():
        return _client

    if not TELETHON_API_ID or not TELETHON_API_HASH:
        raise RuntimeError(
            "Telethon не настроен.\n"
            "1. Зайдите на https://my.telegram.org/apps\n"
            "2. Получите API_ID и API_HASH\n"
            "3. Укажите их в config.py"
        )

    _client = TelegramClient("telethon_session", TELETHON_API_ID, TELETHON_API_HASH,
                             system_version="4.16.30-vxCUSTOM")
    await _client.connect()

    if await _client.is_user_authorized():
        logger.info("Telethon: сессия активна")
        return _client

    raise RuntimeError(
        "❌ Telethon не авторизован.\n"
        "Используйте /setup_tg для входа через бота\n"
        "или запустите setup_telethon.py вручную"
    )


async def try_init_client() -> tuple[bool, str]:
    """Пробует инициализировать клиент при старте бота. Не блокирует."""
    global _client
    try:
        if not TELETHON_API_ID or not TELETHON_API_HASH:
            return False, "API_ID/API_HASH не заданы в config.py"
        _client = TelegramClient("telethon_session", TELETHON_API_ID, TELETHON_API_HASH,
                                 system_version="4.16.30-vxCUSTOM")
        await _client.connect()
        if await _client.is_user_authorized():
            me = await _client.get_me()
            logger.info(f"Telethon авторизован: {me.first_name} @{me.username}")
            return True, f"✅ Telethon: @{me.username}"
        else:
            return False, "ℹ️ Telethon: сессия не найдена. Используйте /setup_tg"
    except Exception as e:
        logger.warning(f"Telethon init: {e}")
        return False, f"⚠️ Telethon: {e}"


async def start_login(phone: str) -> dict:
    """Отправляет код подтверждения на номер телефона."""
    global _client
    if _client is None:
        _client = TelegramClient("telethon_session", TELETHON_API_ID, TELETHON_API_HASH,
                                 system_version="4.16.30-vxCUSTOM")
        await _client.connect()

    try:
        sent = await _client.send_code_request(phone)
        return {
            "success": True,
            "phone_code_hash": sent.phone_code_hash,
            "timeout": sent.timeout or 30,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def complete_login(code: str, phone: str, phone_code_hash: str) -> dict:
    """Завершает вход по коду подтверждения."""
    global _client
    try:
        await _client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        me = await _client.get_me()
        logger.info(f"Telethon: вход выполнен {me.first_name} @{me.username}")
        return {"success": True, "user": f"{me.first_name} @{me.username}"}
    except SessionPasswordNeededError:
        return {"success": False, "need_password": True,
                "error": "Включена двухфакторка. Введите пароль через /setup_tg <пароль>"}
    except PhoneCodeInvalidError:
        return {"success": False, "error": "Неверный код. Попробуйте ещё раз."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def complete_2fa(password: str) -> dict:
    """Завершает вход с двухфакторным паролем."""
    global _client
    try:
        await _client.sign_in(password=password)
        me = await _client.get_me()
        logger.info(f"Telethon: 2FA вход выполнен {me.first_name} @{me.username}")
        return {"success": True, "user": f"{me.first_name} @{me.username}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def close_telethon_client():
    global _client
    if _client:
        await _client.disconnect()
        _client = None
        logger.info("Telethon client closed")


async def is_authorized() -> bool:
    global _client
    if _client is None:
        return False
    return await _client.is_user_authorized()
