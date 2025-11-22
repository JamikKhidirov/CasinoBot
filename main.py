import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import BadRequest

# Настройка логгирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT = "7042929053:AAEsz4mIBA6P2ZKoPRiMuad1UIdR8dS9TQE"

# Хранилище данных: {user_id: chat_partner_id}
active_users = {}
waiting_users = []

# База данных
DB_NAME = "chat.db"
conn = None
cur = None

# Администраторы (замените на реальные ID)
ADMINS = [1819756249]  # Добавьте ID администраторов

# Клавиатура для чата
chat_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Завершить чат ❌", callback_data="leave_chat"),
     InlineKeyboardButton("Пожаловаться ⚠️", callback_data="report_chat")]
])

# Клавиатура для старта
start_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Начать чат 🔍", callback_data="start_chat")]
])

# Клавиатура для отмены поиска
cancel_search_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Отменить поиск ❌", callback_data="cancel_search")]
])


# Инициализация базы данных
def init_db():
    global conn, cur
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                joined_at TEXT,
                total_chats INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                message TEXT,
                timestamp TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bans (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                banned_at TEXT,
                ban_until TEXT,
                can_appeal INTEGER DEFAULT 1
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER,
                reported_id INTEGER,
                reason TEXT,
                timestamp TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS appeals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                timestamp TEXT
            )
        ''')
        # Добавляем столбцы, если они отсутствуют
        for table, column, column_type in [
            ('users', 'total_chats', 'INTEGER DEFAULT 0'),
            ('users', 'total_messages', 'INTEGER DEFAULT 0'),
            ('bans', 'ban_until', 'TEXT'),
            ('bans', 'can_appeal', 'INTEGER DEFAULT 1')
        ]:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise


# Закрытие соединения с базой данных
def close_db():
    global conn, cur
    if cur:
        cur.close()
    if conn:
        conn.close()


# Получение username по user_id
def get_username(user_id):
    try:
        cur.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        return result[0] if result else "unknown"
    except Exception as e:
        logger.error(f"Ошибка получения username для user_id {user_id}: {e}")
        return "unknown"


# Добавление пользователя в БД
def add_user(user_id, username):
    try:
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (user_id, username, joined_at) VALUES (?, ?, ?)",
                        (user_id, username, datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя {user_id}: {e}")


# Обновление статистики пользователя
def update_user_stats(user_id, chats=0, messages=0):
    try:
        cur.execute(
            "UPDATE users SET total_chats = total_chats + ?, total_messages = total_messages + ? WHERE user_id = ?",
            (chats, messages, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления статистики пользователя {user_id}: {e}")


# Проверка на бан
def is_banned(user_id):
    try:
        now = datetime.now().isoformat()
        cur.execute("SELECT * FROM bans WHERE user_id = ? AND (ban_until IS NULL OR ban_until > ?)", (user_id, now))
        return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки бана для user_id {user_id}: {e}")
        return False


# Получение информации о бане
def get_ban_info(user_id):
    try:
        cur.execute("SELECT reason, ban_until, can_appeal FROM bans WHERE user_id = ?", (user_id,))
        return cur.fetchone() or (None, None, None)
    except Exception as e:
        logger.error(f"Ошибка получения информации о бане для user_id {user_id}: {e}")
        return None, None, None


# Сохранение сообщения в БД
def save_message(sender_id, receiver_id, message):
    try:
        cur.execute("INSERT INTO messages (sender_id, receiver_id, message, timestamp) VALUES (?, ?, ?, ?)",
                    (sender_id, receiver_id, message, datetime.now().isoformat()))
        conn.commit()
        update_user_stats(sender_id, messages=1)
    except Exception as e:
        logger.error(f"Ошибка сохранения сообщения от {sender_id} к {receiver_id}: {e}")


# Сохранение жалобы
def save_report(reporter_id, reported_id, reason):
    try:
        cur.execute("INSERT INTO reports (reporter_id, reported_id, reason, timestamp) VALUES (?, ?, ?, ?)",
                    (reporter_id, reported_id, reason, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения жалобы от {reporter_id} на {reported_id}: {e}")


# Сохранение апелляции
def save_appeal(user_id, message):
    try:
        cur.execute("INSERT INTO appeals (user_id, message, timestamp) VALUES (?, ?, ?)",
                    (user_id, message, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения апеллии от {user_id}: {e}")


# Парсинг длительности бана
def parse_duration(duration_str):
    try:
        duration_str = duration_str.lower()
        if duration_str == "forever":
            return None
        if duration_str.endswith('d'):
            days = int(duration_str[:-1])
            return datetime.now() + timedelta(days=days)
        elif duration_str.endswith('h'):
            hours = int(duration_str[:-1])
            return datetime.now() + timedelta(hours=hours)
        elif duration_str.endswith('m'):
            minutes = int(duration_str[:-1])
            return datetime.now() + timedelta(minutes=minutes)
        else:
            raise ValueError("Неверный формат duration (используйте forever, Nd, Nh, Nm)")
    except ValueError as e:
        raise ValueError(f"Ошибка в формате длительности: {str(e)}")


# Команда /admin
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    admin_text = """
    Админ-команды:
     /stats - Статистика бота
     /active_chats - Активные чаты
     /banned - Список забаненных пользователей
     /ban <user_id> <duration> <reason> - Бан (duration: forever или Nd/Nh/Nm, например 3d для 3 дней)
     /unban <user_id> - Разбан
     /noappeal <user_id> - Запретить апеллии
     /allowappeal <user_id> - Разрешить апеллии
     /logs <user_id> - Логи пользователя
     /reports - Последние жалобы
     /appeals - Последние апеллии
     /broadcast <message> - Разослать сообщение всем пользователям
     /reply <user_id> <message> - Отправить сообщение одному пользователю
"""
    if user_id in ADMINS:
        await update.message.reply_text(admin_text)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    add_user(user_id, username)

    if is_banned(user_id):
        ban_info = get_ban_info(user_id)
        ban_text = f"Вы забанены по причине: {ban_info[0]}."
        if ban_info[1]:
            ban_text += f" Бан истекает {ban_info[1]}."
        else:
            ban_text += " Это постоянный бан."
        if ban_info[2]:
            ban_text += "\nВы можете подать апелляцию с помощью /appeal <message>."
        await update.message.reply_text(ban_text)
        return

    if user_id in active_users:
        await update.message.reply_text("Вы уже в чате! Напишите сообщение.", reply_markup=chat_keyboard)
        return

    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Хотите отменить?",
                                        reply_markup=cancel_search_keyboard)
        return

    welcome_text = """
👋 *Добро пожаловать в анонимный чат!*  

Нажми *Начать чат*, чтобы найти собеседника.

Другие команды:
 /help - Помощь
 /mystats - Моя статистика
 /rules - Правила чата
 /appeal <message> - Обжаловать бан (если забанены)
 /banstatus - Проверить статус бана
    """
    await update.message.reply_text(welcome_text, reply_markup=start_keyboard, parse_mode="Markdown")

    if user_id in ADMINS:
        await update.message.reply_text("/admin - Админ команды")


# Команда /banstatus
async def ban_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    if not is_banned(user_id):
        await update.message.reply_text("Вы не забанены.")
        return

    ban_info = get_ban_info(user_id)
    ban_text = f"Вы забанены по причине: {ban_info[0]}."
    if ban_info[1]:
        ban_text += f" Бан истекает {ban_info[1]}."
    else:
        ban_text += " Это постоянный бан."
    if ban_info[2]:
        ban_text += "\nВы можете подать апелляцию с помощью /appeal <message>."
    await update.message.reply_text(ban_text)


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    help_text = """
*Доступные команды:*
 /start - Начать использование бота
 /help - Показать эту помощь
 /mystats - Посмотреть свою статистику
 /rules - Правила чата
 /appeal <message> - Обжаловать бан (если забанены)
 /banstatus - Проверить статус бана

В чате:
 - Напишите сообщение, чтобы отправить собеседнику
 - Нажмите "Завершить чат" для выхода
 - Нажмите "Пожаловаться" для жалобы на собеседника (жалоба отправится админам в ЛС)
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

    if user_id in ADMINS:
        await update.message.reply_text("/admin - Админ команды")


# Команда /rules
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    rules_text = """
*Правила чата:*
1. Будьте уважительны к собеседникам.
2. Не спамьте и не флудите.
3. Запрещены оскорбления, угрозы и незаконный контент.
4. При нарушении - бан (временный или постоянный).
5. Чаты анонимны, но админы могут наблюдать за активностью.
6. Апеллии на бан возможны через /appeal, если не запрещено.
    """
    await update.message.reply_text(rules_text, parse_mode="Markdown")


# Команда /mystats
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    try:
        cur.execute("SELECT COALESCE(total_chats, 0), COALESCE(total_messages, 0) FROM users WHERE user_id = ?",
                    (user_id,))
        stats = cur.fetchone()
        if stats:
            text = f"Ваша статистика:\nЧатов: {stats[0]}\nСообщений: {stats[1]}"
        else:
            text = "Нет статистики. Начните чат с помощью /start."
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка получения статистики для user_id {user_id}: {e}")
        await update.message.reply_text("Ошибка при получении статистики.")


# Поиск собеседника
async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if is_banned(user_id):
        ban_info = get_ban_info(user_id)
        ban_text = f"Вы забанены по причине: {ban_info[0]}."
        if ban_info[1]:
            ban_text += f" Бан истекает {ban_info[1]}."
        else:
            ban_text += " Это постоянный бан."
        await update.callback_query.answer(ban_text)
        return

    if user_id in active_users:
        await update.callback_query.answer("Вы уже в чате!")
        return

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        if is_banned(partner_id):
            waiting_users.append(user_id)
            await update.callback_query.edit_message_text("🔎 Ищем собеседника...", reply_markup=None)
            return

        active_users[user_id] = partner_id
        active_users[partner_id] = user_id
        update_user_stats(user_id, chats=1)
        update_user_stats(partner_id, chats=1)

        try:
            await context.bot.send_message(partner_id, "Собеседник найден! Напишите что-нибудь.",
                                           reply_markup=chat_keyboard)
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for partner {partner_id}")
                await update.callback_query.edit_message_text(
                    "Собеседник недоступен. Попробуйте снова с помощью /start.", reply_markup=start_keyboard)
                return
            else:
                raise
        await update.callback_query.edit_message_text("Собеседник найден! Напишите что-нибудь.",
                                                      reply_markup=chat_keyboard)

        # Уведомление админам о новом чате
        user_name = get_username(user_id)
        partner_name = get_username(partner_id)
        for admin in ADMINS:
            try:
                await context.bot.send_message(
                    admin,
                    f"Новый чат: @{user_name} (<code>{user_id}</code>) <-> @{partner_name} (<code>{partner_id}</code>)",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить админа {admin}: {e}")

    else:
        if user_id not in waiting_users:
            waiting_users.append(user_id)
            await update.callback_query.edit_message_text("🔎 Ищем собеседника...", reply_markup=cancel_search_keyboard)
        else:
            await update.callback_query.answer("Поиск уже идет...")


# Отмена поиска
async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        await update.callback_query.edit_message_text("Поиск отменен. Нажмите /start для начала.",
                                                      reply_markup=start_keyboard)
    else:
        await update.callback_query.answer("Вы не в поиске.")


# Отправка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        ban_info = get_ban_info(user_id)
        ban_text = f"Вы забанены по причине: {ban_info[0]}."
        if ban_info[1]:
            ban_text += f" Бан истекает {ban_info[1]}."
        else:
            ban_text += " Это постоянный бан."
        await update.message.reply_text(ban_text)
        return

    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    if user_id not in active_users:
        await update.message.reply_text("Нажмите /start для начала.", reply_markup=start_keyboard)
        return

    partner_id = active_users[user_id]
    message_text = update.message.text
    save_message(user_id, partner_id, message_text)
    try:
        await context.bot.send_message(partner_id, f"👤: {message_text}", reply_markup=chat_keyboard)
    except BadRequest as e:
        if "Chat not found" in str(e):
            logger.warning(f"Chat not found for partner {partner_id}")
            del active_users[user_id]
            if partner_id in active_users:
                del active_users[partner_id]
            await update.message.reply_text("Собеседник недоступен. Нажмите /start для нового чата.",
                                            reply_markup=start_keyboard)
        else:
            raise


# Жалоба на чат
async def report_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if user_id not in active_users:
        await update.callback_query.answer("Вы не в чате!")
        return

    partner_id = active_users[user_id]
    await update.callback_query.answer("Жалоба отправлена администраторам.")

    # Сохраняем жалобу
    save_report(user_id, partner_id, "Жалоба из чата")

    # Отправляем уведомление админам
    user_name = get_username(user_id)
    partner_name = get_username(partner_id)
    report_text = f"Пользователь @{user_name} (<code>{user_id}</code>) пожаловался на @{partner_name} (<code>{partner_id}</code>)."

    report_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Показать последний чат", callback_data=f"show_last_{user_id}_{partner_id}"),
         InlineKeyboardButton("Показать весь чат", callback_data=f"show_full_{user_id}_{partner_id}")]
    ])

    for admin in ADMINS:
        try:
            await context.bot.send_message(admin, report_text, reply_markup=report_keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось отправить жалобу админу {admin}: {e}")


# Обработчик для показа чата
async def show_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    admin_id = query.from_user.id
    if admin_id not in ADMINS:
        await query.answer("У вас нет прав.")
        return

    try:
        if data.startswith("show_last_"):
            parts = data.split("_")
            reporter_id = int(parts[2])
            reported_id = int(parts[3])
            limit = 10
            chat_text = "Последние 10 сообщений в чате:\n"
        elif data.startswith("show_full_"):
            parts = data.split("_")
            reporter_id = int(parts[2])
            reported_id = int(parts[3])
            limit = None
            chat_text = "Весь чат:\n"
        else:
            return

        cur.execute(
            "SELECT * FROM messages WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) ORDER BY timestamp ASC" + (
                f" LIMIT {limit}" if limit else ""),
            (reporter_id, reported_id, reported_id, reporter_id))
        messages = cur.fetchall()
        if not messages:
            await query.edit_message_text(query.message.text + "\nНет сообщений в чате.",
                                          reply_markup=query.message.reply_markup, parse_mode="HTML")
            return

        for msg in messages:
            sender_name = get_username(msg[1])
            receiver_name = get_username(msg[2])
            chat_text += f"\n@{sender_name} (<code>{msg[1]}</code>) -> @{receiver_name} (<code>{msg[2]}</code>): {msg[3]} ({msg[4]})"

        if len(chat_text) + len(query.message.text) > 4096:
            chat_text = chat_text[:4093 - len(query.message.text)] + "..."

        await query.edit_message_text(query.message.text + "\n" + chat_text, reply_markup=query.message.reply_markup,
                                      parse_mode="HTML")
        await query.answer("Чат показан.")
    except Exception as e:
        logger.error(f"Ошибка показа чата: {e}")
        await query.answer("Произошла ошибка.")


# Выход из чата
async def leave_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if user_id not in active_users:
        await update.callback_query.answer("Вы не в чате!")
        return

    partner_id = active_users[user_id]
    del active_users[user_id]
    if partner_id in active_users:
        del active_users[partner_id]
        try:
            await context.bot.send_message(partner_id, "❌ Собеседник покинул чат. Нажмите /start для нового.",
                                           reply_markup=start_keyboard)
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for partner {partner_id}")
            else:
                raise

    await update.callback_query.edit_message_text("Чат завершен. Нажмите /start для нового.",
                                                  reply_markup=start_keyboard)

    # Уведомление админам
    user_name = get_username(user_id)
    partner_name = get_username(partner_id)
    for admin in ADMINS:
        try:
            await context.bot.send_message(
                admin,
                f"Чат завершен: @{user_name} (<code>{user_id}</code>) -> @{partner_name} (<code>{partner_id}</code>)",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin}: {e}")


# Команда /active_chats (для админов)
async def active_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    if not active_users:
        await update.message.reply_text("Нет активных чатов.")
        return

    text = "Активные чаты:\n"
    visited = set()
    for uid, pid in active_users.items():
        if uid not in visited:
            u_name = get_username(uid)
            p_name = get_username(pid)
            text += f"@{u_name} (<code>{uid}</code>) - @{p_name} (<code>{pid}</code>)\n"
            visited.add(uid)
            visited.add(pid)
    await update.message.reply_text(text, parse_mode="HTML")


# Команда /banned (для админов)
async def banned_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    try:
        cur.execute("SELECT user_id, reason, ban_until FROM bans")
        bans = cur.fetchall()
        if not bans:
            await update.message.reply_text("Нет забаненных пользователей.")
            return

        text = "Забаненные пользователи:\n"
        for ban in bans:
            u_id, reason, ban_until = ban
            u_name = get_username(u_id)
            duration = "навсегда" if not ban_until else f"до {ban_until}"
            text += f"@{u_name} (<code>{u_id}</code>): {reason} ({duration})\n"
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при получении списка забаненных: {e}")
        await update.message.reply_text("Произошла ошибка при получении списка.")


# Команда /ban (для админов)
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Использование: /ban <user_id> <duration> <reason> (duration: forever или Nd/Nh/Nm, например 3d для 3 дней)")
        return

    try:
        target_id = int(args[0])
        duration_str = args[1]
        reason = " ".join(args[2:])
        ban_until = parse_duration(duration_str)
        ban_until_str = ban_until.isoformat() if ban_until else None

        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        if not cur.fetchone():
            await update.message.reply_text(f"Пользователь с ID {target_id} не найден.")
            return

        cur.execute(
            "INSERT OR REPLACE INTO bans (user_id, reason, banned_at, ban_until, can_appeal) VALUES (?, ?, ?, ?, ?)",
            (target_id, reason, datetime.now().isoformat(), ban_until_str, 1))
        conn.commit()

        ban_text = f"Вы забанены по причине: {reason}."
        if ban_until:
            ban_text += f" Бан истекает {ban_until_str}."
        else:
            ban_text += " Это постоянный бан."
        ban_text += "\nИспользуйте /banstatus для проверки статуса."

        if target_id in active_users:
            partner_id = active_users[target_id]
            del active_users[target_id]
            if partner_id in active_users:
                del active_users[partner_id]
                try:
                    await context.bot.send_message(partner_id, "Чат завершен из-за бана собеседника.")
                except BadRequest as e:
                    if "Chat not found" in str(e):
                        logger.warning(f"Chat not found for partner {partner_id}")
                    else:
                        raise
        try:
            await context.bot.send_message(target_id, ban_text)
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for banned user {target_id}")
            else:
                raise

        target_name = get_username(target_id)
        await update.message.reply_text(f"Пользователь @{target_name} (<code>{target_id}</code>) забанен.",
                                        parse_mode="HTML")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка при бане пользователя: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Команда /unban (для админов)
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /unban <user_id>")
        return

    try:
        target_id = int(args[0])
        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        if not cur.fetchone():
            await update.message.reply_text(f"Пользователь с ID {target_id} не найден.")
            return

        cur.execute("DELETE FROM bans WHERE user_id = ?", (target_id,))
        conn.commit()
        target_name = get_username(target_id)
        try:
            await context.bot.send_message(target_id, "Вы были разбанены и можете использовать чат.")
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for unbanned user {target_id}")
            else:
                raise
        await update.message.reply_text(f"Пользователь @{target_name} (<code>{target_id}</code>) разбанен.",
                                        parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
    except Exception as e:
        logger.error(f"Ошибка при разбане пользователя: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Команда /noappeal (для админов)
async def no_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /noappeal <user_id>")
        return

    try:
        target_id = int(args[0])
        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        if not cur.fetchone():
            await update.message.reply_text(f"Пользователь с ID {target_id} не найден.")
            return

        cur.execute("UPDATE bans SET can_appeal = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        target_name = get_username(target_id)
        try:
            await context.bot.send_message(target_id, "Вам запрещено подавать апеллии на бан.")
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for user {target_id}")
            else:
                raise
        await update.message.reply_text(f"Апеллии запрещены для @{target_name} (<code>{target_id}</code>).",
                                        parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
    except Exception as e:
        logger.error(f"Ошибка при запрете апелляций: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Команда /allowappeal (для админов)
async def allow_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /allowappeal <user_id>")
        return

    try:
        target_id = int(args[0])
        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        if not cur.fetchone():
            await update.message.reply_text(f"Пользователь с ID {target_id} не найден.")
            return

        cur.execute("UPDATE bans SET can_appeal = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        target_name = get_username(target_id)
        try:
            await context.bot.send_message(target_id, "Вам разрешено подавать апеллии на бан.")
        except BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Chat not found for user {target_id}")
            else:
                raise
        await update.message.reply_text(f"Апеллии разрешены для @{target_name} (<code>{target_id}</code>).",
                                        parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
    except Exception as e:
        logger.error(f"Ошибка при разрешении апелляций: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Команда /logs (для админов)
async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /logs <user_id>")
        return

    try:
        target_id = int(args[0])
        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        if not cur.fetchone():
            await update.message.reply_text(f"Пользователь с ID {target_id} не найден.")
            return

        cur.execute("SELECT * FROM messages WHERE sender_id = ? OR receiver_id = ? ORDER BY timestamp DESC LIMIT 50",
                    (target_id, target_id))
        messages = cur.fetchall()
        if not messages:
            await update.message.reply_text("Нет сообщений для этого пользователя.")
            return

        target_name = get_username(target_id)
        log_text = f"Последние сообщения для @{target_name} (<code>{target_id}</code>):"
        for msg in messages:
            sender_name = get_username(msg[1])
            receiver_name = get_username(msg[2])
            log_text += f"\n@{sender_name} (<code>{msg[1]}</code>) -> @{receiver_name} (<code>{msg[2]}</code>): {msg[3]} ({msg[4]})"
        if len(log_text) > 4096:
            log_text = log_text[:4093] + "..."
        await update.message.reply_text(log_text, parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
    except Exception as e:
        logger.error(f"Ошибка при получении логов: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Команда /reports (для админов)
async def view_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    try:
        cur.execute("SELECT * FROM reports ORDER BY timestamp DESC LIMIT 20")
        reports = cur.fetchall()
        if not reports:
            await update.message.reply_text("Нет жалоб.")
            return

        text = "Последние жалобы:"
        for rep in reports:
            reporter_name = get_username(rep[1])
            reported_name = get_username(rep[2])
            text += f"\n@{reporter_name} (<code>{rep[1]}</code>) жалуется на @{reported_name} (<code>{rep[2]}</code>): {rep[3]} ({rep[4]})"
        if len(text) > 4096:
            text = text[:4093] + "..."
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при получении жалоб: {e}")
        await update.message.reply_text("Произошла ошибка при получении жалоб.")


# Команда /appeals (для админов)
async def view_appeals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    try:
        cur.execute("SELECT * FROM appeals ORDER BY timestamp DESC LIMIT 20")
        appeals = cur.fetchall()
        if not appeals:
            await update.message.reply_text("Нет апелляций.")
            return

        text = "Последние апеллии:"
        for app in appeals:
            user_name = get_username(app[1])
            text += f"\n@{user_name} (<code>{app[1]}</code>): {app[2]} ({app[3]})"
        if len(text) > 4096:
            text = text[:4093] + "..."
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при получении апелляций: {e}")
        await update.message.reply_text("Произошла ошибка при получении апелляций.")


# Команда /stats (для админов)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    try:
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bans WHERE ban_until IS NULL OR ban_until > ?", (datetime.now().isoformat(),))
        banned_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages")
        total_messages = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM reports")
        total_reports = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appeals")
        total_appeals = cur.fetchone()[0]

        stats_text = f"""
*Статистика:*
Всего пользователей: {total_users}
Забаненных: {banned_users}
Всего сообщений: {total_messages}
Всего жалоб: {total_reports}
Всего апелляций: {total_appeals}
Активных чатов: {len(active_users) // 2}
Ожидающих: {len(waiting_users)}
        """
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.message.reply_text("Произошла ошибка при получении статистики.")


# Команда /broadcast (для админов)
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Использование: /broadcast <message>")
        return

    message = " ".join(args)
    try:
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        sent_count = 0
        for uid in users:
            try:
                await context.bot.send_message(uid[0], f"📢 Сообщение от админа: {message}")
                sent_count += 1
            except Exception as e:
                logger.warning(f"Не удалось отправить рассылку пользователю {uid[0]}: {e}")
        await update.message.reply_text(f"Рассылка завершена. Отправлено: {sent_count} пользователям.")
    except Exception as e:
        logger.error(f"Ошибка при выполнении рассылки: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении рассылки.")


# Команда /reply (для админов)
async def reply_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав на эту команду.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /reply <user_id> <message>")
        return

    try:
        target_id = int(args[0])
        message = " ".join(args[1:])
        await context.bot.send_message(target_id, f"Сообщение от админа: {message}")
        await update.message.reply_text("Сообщение отправлено.")
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения пользователю: {e}")
        await update.message.reply_text("Произошла ошибка при отправке.")


# Команда /appeal
async def appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in waiting_users:
        await update.message.reply_text("Вы в поиске собеседника. Чтобы использовать команды, отмените поиск.",
                                        reply_markup=cancel_search_keyboard)
        return

    args = context.args
    if not args:
        await update.message.reply_text("Использование: /appeal <message>")
        return

    if not is_banned(user_id):
        await update.message.reply_text("Вы не забанены.")
        return

    ban_info = get_ban_info(user_id)
    if ban_info[2] == 0:
        await update.message.reply_text("Вам запрещено подавать апеллии.")
        return

    message = " ".join(args)
    save_appeal(user_id, message)

    user_name = get_username(user_id)
    appeal_text = f"Апеллия от @{user_name} (<code>{user_id}</code>): {message}"

    for admin in ADMINS:
        try:
            await context.bot.send_message(admin, appeal_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось отправить апелляцию админу {admin}: {e}")

    await update.message.reply_text("Ваша апеллия отправлена администраторам.")


# Обработка ошибок
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        try:
            await update.message.reply_text("Произошла ошибка. Попробуйте снова позже.")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")


# Запуск бота
def main():
    try:
        init_db()
        application = Application.builder().token(BOT).build()

        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", admin))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("rules", rules))
        application.add_handler(CommandHandler("mystats", my_stats))
        application.add_handler(CommandHandler("banstatus", ban_status))
        application.add_handler(CommandHandler("appeal", appeal))
        application.add_handler(CommandHandler("ban", ban_user))
        application.add_handler(CommandHandler("unban", unban_user))
        application.add_handler(CommandHandler("noappeal", no_appeal))
        application.add_handler(CommandHandler("allowappeal", allow_appeal))
        application.add_handler(CommandHandler("logs", view_logs))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("active_chats", active_chats))
        application.add_handler(CommandHandler("reports", view_reports))
        application.add_handler(CommandHandler("appeals", view_appeals))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CommandHandler("reply", reply_user))
        application.add_handler(CommandHandler("banned", banned_users))
        application.add_handler(CallbackQueryHandler(start_chat, pattern="start_chat"))
        application.add_handler(CallbackQueryHandler(leave_chat, pattern="leave_chat"))
        application.add_handler(CallbackQueryHandler(report_chat, pattern="report_chat"))
        application.add_handler(CallbackQueryHandler(cancel_search, pattern="cancel_search"))
        application.add_handler(CallbackQueryHandler(show_chat, pattern="^(show_last_|show_full_)"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error)

        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        close_db()


if __name__ == "__main__":
    main()