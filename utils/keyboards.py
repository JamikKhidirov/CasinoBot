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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 По номеру телефона", callback_data="osint_phone")],
        [InlineKeyboardButton(text="📧 По email", callback_data="osint_email")],
        [InlineKeyboardButton(text="🔎 По username", callback_data="osint_username")],
        [InlineKeyboardButton(text="🌐 По IP-адресу", callback_data="osint_ip")],
        [InlineKeyboardButton(text="🏛 По домену", callback_data="osint_domain")],
        [InlineKeyboardButton(text="🔌 Сканировать порты IP", callback_data="osint_ports")],
        [InlineKeyboardButton(text="☠️ Хакерский скан номера", callback_data="osint_hackphone")],
        [InlineKeyboardButton(text="💳 Пробив карты", callback_data="osint_card")],
        [InlineKeyboardButton(text="🕵️ Анализ SSL домена", callback_data="osint_ssl")],
        [InlineKeyboardButton(text="🔬 Определить технологии", callback_data="osint_tech")],
        [InlineKeyboardButton(text="📶 Анализ Wi-Fi (BSSID/SSID)", callback_data="osint_wifi")],
        [InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")]
    ])


def chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="leave_chat"),
         InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report_chat")]
    ])


def search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")]
    ])
