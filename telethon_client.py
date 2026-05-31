import asyncio
import logging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from config import TELETHON_API_ID, TELETHON_API_HASH

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


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

    if not await _client.is_user_authorized():
        raise RuntimeError(
            "Telethon сессия не авторизована.\n"
            "Выполните авторизацию вручную:\n"
            "1. Создайте файл setup_telethon.py:\n"
            "   from telethon import TelegramClient\n"
            "   import asyncio\n"
            "   async def main():\n"
            "       client = TelegramClient('telethon_session', API_ID, API_HASH)\n"
            "       await client.start()\n"
            "       await client.disconnect()\n"
            "   asyncio.run(main())\n"
            "2. Запустите: python setup_telethon.py\n"
            "3. Введите телефон и код из Telegram"
        )

    return _client


async def close_telethon_client():
    global _client
    if _client:
        await _client.disconnect()
        _client = None
        logger.info("Telethon client closed")
