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
from handlers.moderation import router as mod_router
from handlers.developer import router as dev_router

PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Справка по командам"),
    # Казино
    BotCommand(command="profile", description="🎰 Профиль игрока"),
    BotCommand(command="top", description="🏆 Топ игроков"),
    BotCommand(command="games", description="🎮 Список игр"),
    BotCommand(command="dice", description="🎲 Игра в кости [ставка]"),
    BotCommand(command="bowling", description="🎳 Боулинг [ставка]"),
    BotCommand(command="darts", description="🎯 Дротики [ставка]"),
    BotCommand(command="basket", description="🏀 Баскетбол [ставка]"),
    BotCommand(command="football", description="⚽ Футбол [ставка]"),
    BotCommand(command="active", description="🕹 Активные игры"),
    BotCommand(command="unlock", description="🔓 Отменить свои игры"),
]

ADMIN_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Справка по командам"),
    BotCommand(command="stats", description="📊 Статистика бота"),
    BotCommand(command="admin", description="👑 Админ-панель казино"),
    BotCommand(command="players", description="👥 Список игроков казино"),
    BotCommand(command="mod", description="🛡 Панель модерации"),
    BotCommand(command="ban", description="🚫 Забанить"),
    BotCommand(command="unban", description="✅ Разбанить"),
    BotCommand(command="mute", description="🔇 Замутить"),
    BotCommand(command="unmute", description="🔊 Размутить"),
    BotCommand(command="warn", description="⚠️ Варн"),
    BotCommand(command="check", description="📋 Проверить"),
    BotCommand(command="chatlog", description="💬 Переписка"),
    BotCommand(command="warns", description="⚠️ Варны"),
    BotCommand(command="phone", description="📱 Пробив номера"),
    BotCommand(command="hackphone", description="☠️ Скан номера"),
    BotCommand(command="email", description="📧 Пробив email"),
    BotCommand(command="user", description="🔎 Поиск username"),
    BotCommand(command="ip", description="🌐 Геолокация IP"),
    BotCommand(command="domain", description="🏛 Инфо домена"),
    BotCommand(command="card", description="💳 Пробив карты"),
    BotCommand(command="wifi", description="📶 Анализ Wi-Fi"),
    BotCommand(command="promo", description="🎟 Активировать промокод"),
    BotCommand(command="createpromo", description="🎟 Создать промокод"),
    BotCommand(command="deletepromo", description="🎟 Удалить промокод"),
    BotCommand(command="promo_list", description="🎟 Список промокодов"),
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
        mod_router,
        dev_router,
        text_router,
    )

    from aiogram.types import BotCommandScopeDefault, BotCommandScopeChat

    OWNER_ID = config.OWNER_ID

    logger.info("Бот запущен")

    retries = 0
    max_retries = 10
    while retries < max_retries:
        try:
            await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=OWNER_ID))
            logger.info("Команды зарегистрированы")
            await dp.start_polling(bot, drop_pending_updates=True)      
            logger.info("Polling завершён (без ошибки)")
            break
        except TelegramNetworkError as e:
            retries += 1
            logger.warning(f"Ошибка сети ({retries}/{max_retries}): {e}")
            if "getaddrinfo failed" in str(e) or "Cannot connect" in str(e):
                try:
                    print("\n❌ Telegram API заблокирован. Включите VPN.\n")
                except UnicodeEncodeError:
                    print("\n[!] Telegram API blocked. Enable VPN.\n")
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
