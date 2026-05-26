from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 OSINT-пробив", callback_data="osint_menu")],
        [InlineKeyboardButton(text="🎲 Анонимный чат", callback_data="start_chat")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="myprofile"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="mystats")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])


def osint_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 По номеру телефона", callback_data="osint_phone")],
        [InlineKeyboardButton(text="📧 По email", callback_data="osint_email")],
        [InlineKeyboardButton(text="🔎 По username", callback_data="osint_username")],
        [InlineKeyboardButton(text="🌐 По IP-адресу", callback_data="osint_ip")],
        [InlineKeyboardButton(text="🏛 По домену", callback_data="osint_domain")],
        [InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")]
    ])


def chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="leave_chat"),
         InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report_chat")]
    ])
