from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_kb(show_chat: bool = True, show_osint: bool = True, show_admin: bool = False):
    builder = InlineKeyboardBuilder()
    if show_osint:
        builder.row(InlineKeyboardButton(text="🔍 OSINT-пробив", callback_data="osint_menu"))
    if show_chat:
        builder.row(InlineKeyboardButton(text="🎲 Анонимный чат", callback_data="start_chat"))
    builder.row(InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu"))
    builder.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="myprofile"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="mystats"),
    )
    if show_admin:
        builder.row(InlineKeyboardButton(text="🛡 Админ-панель", callback_data="admin_panel"))
    builder.row(InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
    return builder.as_markup()


def osint_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 ЛЮДИ", callback_data="osint_people_header"))
    builder.row(
        InlineKeyboardButton(text="📱 Телефон", callback_data="osint_phone"),
        InlineKeyboardButton(text="☠️ Хакскан", callback_data="osint_hackphone"),
    )
    builder.row(
        InlineKeyboardButton(text="📧 Email", callback_data="osint_email"),
        InlineKeyboardButton(text="💳 Карта", callback_data="osint_card"),
    )
    builder.row(
        InlineKeyboardButton(text="🔎 Username", callback_data="osint_username"),
    )
    builder.row(InlineKeyboardButton(text="🌐 СОЦСЕТИ", callback_data="osint_social_header"))
    builder.row(
        InlineKeyboardButton(text="✈️ Telegram", callback_data="osint_tg"),
        InlineKeyboardButton(text="📸 Instagram", callback_data="osint_instagram"),
    )
    builder.row(
        InlineKeyboardButton(text="🎵 TikTok", callback_data="osint_tiktok"),
        InlineKeyboardButton(text="🐦 Twitter/X", callback_data="osint_twitter"),
    )
    builder.row(InlineKeyboardButton(text="▶️ YouTube", callback_data="osint_youtube"))
    builder.row(InlineKeyboardButton(text="🌍 СЕТЬ", callback_data="osint_net_header"))
    builder.row(
        InlineKeyboardButton(text="🌐 IP-адрес", callback_data="osint_ip"),
        InlineKeyboardButton(text="🏛 Домен", callback_data="osint_domain"),
    )
    builder.row(
        InlineKeyboardButton(text="🔌 Порты", callback_data="osint_ports"),
        InlineKeyboardButton(text="🔒 SSL", callback_data="osint_ssl"),
    )
    builder.row(
        InlineKeyboardButton(text="🔧 Технологии", callback_data="osint_tech"),
        InlineKeyboardButton(text="📶 Wi-Fi", callback_data="osint_wifi"),
    )
    builder.row(InlineKeyboardButton(text="◀️ На главную", callback_data="back_main"))
    return builder.as_markup()


def chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="leave_chat"),
         InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report_chat")]
    ])


def search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")]
    ])
