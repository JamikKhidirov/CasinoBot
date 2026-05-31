import asyncio
from telethon import TelegramClient

API_ID = 23414580
API_HASH = "c3043d8e62fae95f0298de45e444dc8b"


async def main():
    client = TelegramClient("telethon_session", API_ID, API_HASH,
                            system_version="4.16.30-vxCUSTOM")
    await client.start()
    print("✅ Telethon сессия создана! Теперь можно запускать бота.")
    me = await client.get_me()
    print(f"👤 Аккаунт: {me.first_name} @{me.username} (ID: {me.id})")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
