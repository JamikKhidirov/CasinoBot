from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .base import ADMIN_ID, GAMES_CONFIG


def game_keyboard(room_id: str, creator_id: int, label: str = "🎮 Присоединиться к игре") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"join_{room_id}")],
            [InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"cancelgame_{room_id}")],
        ]
    )


def roll_keyboard(room_id: str, player_id: int, emoji: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Бросить {emoji}", callback_data=f"roll_{room_id}_{player_id}")]
        ]
    )


def blackjack_join_keyboard(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🃏 Присоединиться к блэкджеку", callback_data=f"bj_join_{room_id}")],
            [InlineKeyboardButton(text="▶️ Старт", callback_data=f"bj_start_{room_id}")],
        ]
    )


def blackjack_action_keyboard(room_id: str, player_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👊 Ещё", callback_data=f"bj_hit_{room_id}_{player_id}"),
                InlineKeyboardButton(text="✋ Стоп", callback_data=f"bj_stand_{room_id}_{player_id}"),
            ]
        ]
    )


def casino_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎮 Игры", callback_data="casino_games")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="casino_profile"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="casino_top")],
        [InlineKeyboardButton(text="🎲 Активные", callback_data="casino_active"),
         InlineKeyboardButton(text="🔓 Разблокировать", callback_data="casino_unlock")],
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="casino_admin")])
    buttons.append([InlineKeyboardButton(text="◀️ На главную", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blackjack_bet_kb() -> InlineKeyboardMarkup:
    bets = [10, 50, 100, 500, 1000]
    row = []
    buttons = []
    for bet in bets:
        row.append(InlineKeyboardButton(
            text=f"{bet}🪙",
            callback_data=f"casino_bj_bet_{bet}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="✏️ Своя сумма", callback_data="casino_bj_bet_custom")
    ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def solo_game_selection_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for gt, cfg in GAMES_CONFIG.items():
        builder.button(text=f"{cfg['emoji']} {gt.capitalize()}", callback_data=f"casino_solo_pick_{gt}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="👥 С игроками", callback_data="casino_play_pvp"),
        InlineKeyboardButton(text="🃏 Блэкджек", callback_data="casino_blackjack_info"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games"),
    )
    return builder.as_markup()


def solo_bet_selection_kb(game_type: str) -> InlineKeyboardMarkup:
    bets = [10, 50, 100, 500, 1000]
    row = []
    buttons = []
    for bet in bets:
        row.append(InlineKeyboardButton(
            text=f"{bet}🪙",
            callback_data=f"casino_solo_bet_{game_type}_{bet}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="✏️ Своя сумма", callback_data=f"casino_solo_bet_{game_type}_custom"
        )
    ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_play_bot")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def game_selection_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🤖 Игра с ботом", callback_data="casino_play_bot"),
        InlineKeyboardButton(text="👥 С игроками", callback_data="casino_play_pvp"),
    )
    builder.row(
        InlineKeyboardButton(text="🃏 Блэкджек", callback_data="casino_blackjack_info"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu"),
    )
    return builder.as_markup()


def pvp_game_selection_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for gt, cfg in GAMES_CONFIG.items():
        builder.button(text=f"{cfg['emoji']} {gt.capitalize()}", callback_data=f"casino_pick_game_{gt}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🃏 Блэкджек", callback_data="casino_blackjack_info"),
        InlineKeyboardButton(text="🤖 С ботом", callback_data="casino_play_bot"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games"),
    )
    return builder.as_markup()


def bet_selection_kb(game_type: str) -> InlineKeyboardMarkup:
    bets = [10, 50, 100, 500, 1000]
    row = []
    buttons = []
    for bet in bets:
        row.append(InlineKeyboardButton(
            text=f"{bet}🪙",
            callback_data=f"casino_pick_bet_{game_type}_{bet}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="✏️ Своя сумма", callback_data=f"casino_pick_bet_{game_type}_custom"
        )
    ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def casino_admin_kb(perms: Optional[list[str]] = None) -> InlineKeyboardMarkup:
    if perms is None:
        perms = []
    buttons = []
    if "view_players" in perms:
        buttons.append([InlineKeyboardButton(text="👥 Список игроков", callback_data="casino_admin_players")])
    if "view_stats" in perms:
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="casino_admin_stats")])
    if "add_balance" in perms:
        buttons.append([InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="casino_admin_add")])
    if "approve_deposits" in perms:
        buttons.append([InlineKeyboardButton(text="📋 Запросы на пополнение", callback_data="casino_admin_pending")])
    if "approve_withdrawals" in perms:
        buttons.append([InlineKeyboardButton(text="💸 Запросы на вывод", callback_data="casino_admin_withdrawals")])
    if "manage_admins" in perms:
        buttons.append([InlineKeyboardButton(text="👑 Управление админами", callback_data="casino_admin_manage")])
    if "create_promos" in perms:
        buttons.append([InlineKeyboardButton(text="🎟 Промокоды", callback_data="casino_admin_promos")])
    row = []
    row.append(InlineKeyboardButton(text="🚫 Бан", callback_data="adm_ban"))
    row.append(InlineKeyboardButton(text="🔇 Мут", callback_data="adm_mute"))
    row.append(InlineKeyboardButton(text="⚠️ Варн", callback_data="adm_warn"))
    row.append(InlineKeyboardButton(text="📋 Чек", callback_data="adm_check"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🤖 Пополнить счёт (бот)", callback_data="casino_admin_addbot")])
    buttons.append([InlineKeyboardButton(text="🃏 Пополнить счёт (блэкджек)", callback_data="casino_admin_addbj")])
    buttons.append([InlineKeyboardButton(text="💰 Пополнить PVP-счёт", callback_data="casino_admin_add")])
    buttons.append([InlineKeyboardButton(text="⭐ Топ с ботом", callback_data="casino_admin_solotop")])
    buttons.append([InlineKeyboardButton(text="📖 Команды /admin", callback_data="casino_admin_help")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="casino_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
