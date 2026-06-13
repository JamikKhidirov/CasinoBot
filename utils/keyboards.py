from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_kb(show_chat: bool = True, show_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu"),
    )
    if show_chat:
        builder.row(InlineKeyboardButton(text="🎲 Анонимный чат", callback_data="start_chat"))
    builder.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="myprofile"),
        InlineKeyboardButton(text="🏆 Топ", callback_data="casino_top"),
    )
    if show_admin:
        builder.row(InlineKeyboardButton(text="🛡 Админ-панель", callback_data="admin_panel"))
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="mystats"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
    )
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
