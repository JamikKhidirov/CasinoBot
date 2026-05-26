import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand
import config
from db import init_db, close_db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from handlers.callbacks import router as callbacks_router
from handlers.osint_handlers import router as osint_router
from handlers.text_handler import router as text_router

COMMANDS = [
    BotCommand(command="start", description="Главное меню (OSINT + чат)"),
    BotCommand(command="phone", description="Пробив по номеру телефона"),
    BotCommand(command="email", description="Пробив по email"),
    BotCommand(command="user", description="Поиск username в соцсетях"),
    BotCommand(command="ip", description="Геолокация по IP-адресу"),
    BotCommand(command="domain", description="Информация о домене"),
    BotCommand(command="help", description="Справка по командам"),
    BotCommand(command="stats", description="Статистика (админ)"),
]


async def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        filename="bot_errors.log",
        encoding="utf-8",
    )
    logger = logging.getLogger(__name__)

    try:
        init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return

    session = None
    if config.PROXY_URL:
        session = AiohttpSession(proxy=config.PROXY_URL)
        logger.info(f"Прокси: {config.PROXY_URL}")

    bot = Bot(token=config.BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.include_routers(
        user_router,
        admin_router,
        callbacks_router,
        osint_router,
        text_router,
    )

    await bot.set_my_commands(COMMANDS)
    logger.info("Команды зарегистрированы")

    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()
        close_db()


if __name__ == "__main__":
    asyncio.run(main())
