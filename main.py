import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.exceptions import TelegramNetworkError
import config
from db import init_db, close_db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from handlers.callbacks import router as callbacks_router
from handlers.osint_handlers import router as osint_router
from handlers.text_handler import router as text_router
from handlers.casino import router as casino_router, setup as casino_setup, init_db as casino_init_db

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
        handlers=[
            logging.FileHandler("bot_errors.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)

    try:
        init_db()
        await casino_init_db()
        logger.info("Базы данных инициализированы")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return

    bot = Bot(token=config.BOT_TOKEN)
    casino_setup(bot)
    dp = Dispatcher()

    dp.include_routers(
        user_router,
        admin_router,
        callbacks_router,
        osint_router,
        casino_router,
        text_router,
    )

    await bot.set_my_commands(COMMANDS)
    logger.info("Команды зарегистрированы")

    logger.info("Бот запущен")

    retries = 0
    max_retries = 10
    while retries < max_retries:
        try:
            await dp.start_polling(bot, drop_pending_updates=True)
            logger.info("Polling завершён (без ошибки)")
            break
        except TelegramNetworkError as e:
            retries += 1
            logger.warning(f"Ошибка сети ({retries}/{max_retries}): {e}")
            if "getaddrinfo failed" in str(e) or "Cannot connect" in str(e):
                print("\n❌ Telegram API заблокирован. Включите VPN.\n")
            if retries >= max_retries:
                logger.critical("Превышено число попыток. Завершение.")
                break
            await asyncio.sleep(5 * retries)
        except Exception as e:
            logger.critical(f"Неизвестная ошибка: {e}")
            break

    await bot.session.close()
    close_db()


if __name__ == "__main__":
    asyncio.run(main())
