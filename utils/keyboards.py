from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_kb(show_chat: bool = True, show_osint: bool = True, show_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📸 Instagram", callback_data="osint_instagram"),
        InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu"),
    )
    if show_osint:
        builder.row(InlineKeyboardButton(text="🔍 OSINT-пробив", callback_data="osint_menu"))
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


def osint_menu_kb(full_access: bool = True):
    builder = InlineKeyboardBuilder()
    if full_access:
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
    else:
        builder.row(InlineKeyboardButton(text="📸 Instagram", callback_data="osint_instagram"))
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


def osint_result_kb(mode: str, data: dict = None):
    """Кнопки действий для результата OSINT-поиска."""
    builder = InlineKeyboardBuilder()

    if mode == "tg" and data:
        total = data.get("total_msgs", 0)
        cc = data.get("common_chats", [])
        voice = sum(1 for m in data.get("author_messages", []) if m.get("has_voice"))
        nav = []
        if total:
            nav.append(InlineKeyboardButton(text=f"💬 Сообщения ({total})", callback_data="tg_browse_msgs"))
        if cc:
            nav.append(InlineKeyboardButton(text=f"📋 Каналы ({len(cc)})", callback_data="tg_browse_chats"))
        if voice:
            nav.append(InlineKeyboardButton(text=f"🎤 Голосовые ({voice})", callback_data="tg_browse_voices"))
        if nav:
            builder.row(*nav[:2])
            if len(nav) > 2:
                builder.row(nav[2])
    elif mode == "instagram" and data:
        builder.row(InlineKeyboardButton(text="📸 Открыть Instagram", url=f"https://instagram.com/{data['input']}"))
    elif mode == "twitter" and data:
        builder.row(InlineKeyboardButton(text="🐦 Открыть Twitter/X", url=f"https://x.com/{data['input']}"))
    elif mode == "youtube" and data:
        builder.row(InlineKeyboardButton(text="▶️ Открыть YouTube", url=f"https://youtube.com/@{data['input']}"))
    elif mode == "phone" and data:
        phone = data.get("e164", "")
        if phone:
            builder.row(InlineKeyboardButton(text="📱 Открыть в Telegram", url=f"https://t.me/{phone}"))
    elif mode == "username" and data:
        uname = data.get("username", "")
        if uname:
            builder.row(InlineKeyboardButton(text="🔍 Искать везде", url=f"https://www.google.com/search?q=%22{uname}%22"))

    builder.row(InlineKeyboardButton(text="◀️ Назад в OSINT", callback_data="osint_menu"))
    return builder.as_markup()
