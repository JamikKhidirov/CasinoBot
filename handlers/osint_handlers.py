from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from utils.keyboards import main_kb, osint_menu_kb
from config import OWNER_ID
from db import log_osint_query
from osint import phone_lookup, email_lookup, username_lookup, ip_lookup, domain_lookup, phone_messenger_check, telegram_profile
from leak import leak_search

router = Router()
osint_waiting: dict[int, tuple[str, int, int]] = {}  # uid -> (mode, chat_id, prompt_msg_id)


def _fmt_phone(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [
        f"<b>📱 Результат по номеру</b>\n",
        f"┃ Номер: <code>{data['international']}</code>",
        f"┃ Нац. формат: <code>{data['national']}</code>",
        f"┃ Страна: {data['country']} ({data['country_code']})",
        f"┃ Регион: {data['region']}",
        f"┃ Оператор: {data['carrier_ru']}",
        f"┃ Тип: {data['type']}",
        f"┃ Часовой пояс: {data['timezone']}",
    ]
    if data.get("services"):
        lines.append(f"┃ Сервисы: {', '.join(data['services'])}")
    messengers = data.get("messengers")
    if messengers:
        lines.append("")
        lines.append("<b>📡 Мессенджеры:</b>")
        for m in messengers:
            lines.append(f"┃ {m}")
    leak = data.get("leak")
    if leak and leak.get("found"):
        lines.append("")
        lines.append("<b>🔓 Утечки данных:</b>")
        for src in leak.get("details", []):
            lines.append(f"┃ {src['source']}: найдено {src.get('count', '?')} записей")
            if src.get("sample"):
                for s in src["sample"][:3]:
                    clean = str(s)[:80]
                    lines.append(f"┃ <code>{clean}</code>")
    return "\n".join(lines)


def _fmt_email(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [
        f"<b>📧 Результат по email:</b>",
        f"┃ Email: <code>{data['email']}</code>",
        f"┃ Домен: <code>{data['domain']}</code>",
        f"┃ MX-записи: {'✅ Есть' if data.get('mx_ok') else '❌ Нет'}",
    ]
    if data.get("mx"):
        for mx in data["mx"][:3]:
            lines.append(f"┃ └ <code>{mx}</code>")
    if data.get("gravatar"):
        g = data["gravatar"]
        lines.append(f"┃ Gravatar: <b>{g.get('name', '—')}</b>")
        if g.get("urls"):
            for u in g["urls"][:3]:
                lines.append(f"┃ └ <code>{u}</code>")
    if data.get("emailrep"):
        er = data["emailrep"]
        rep = er.get("reputation", "unknown")
        rep_emoji = "🟢" if rep == "high" else "🟡" if rep == "medium" else "🔴"
        lines.append(f"┃ Репутация: {rep_emoji} {rep}")
        if er.get("suspicious"):
            lines.append(f"┃ ⚠️ Подозрительный")
    return "\n".join(lines)


def _fmt_username(data: dict) -> str:
    lines = [
        f"<b>🔎 Результат по username:</b>",
        f"┃ Username: <code>{data['username']}</code>",
        f"┃ Проверено: {data['checked']} площадок",
        f"┃ Найдено: {data['found']} совпадений",
    ]
    tg = data.get("telegram")
    if tg and tg.get("found"):
        lines.append("")
        lines.append("<b>📡 Telegram профиль:</b>")
        lines.append(f"┃ 👤 Имя: <b>{tg.get('name', '—')}</b>")
        if tg.get("bio"):
            lines.append(f"┃ 📝 О себе: {tg['bio'][:200]}")
        if tg.get("extra"):
            lines.append(f"┃ ℹ️ {tg['extra']}")
        lines.append(f"┃ 🔗 <code>{tg['url']}</code>")
        lines.append(f"┃ 🖼 Фото: {'✅ Есть' if tg.get('has_photo') else '❌ Нет'}")
        lines.append(f"┃ 📋 Тип: {tg['type']}")
    if data['results']:
        lines.append("")
        lines.append("<b>🌐 Найден на площадках:</b>")
        for r in data["results"]:
            lines.append(f"┃ ✅ <b>{r['platform']}</b>\n┃ └ <code>{r['url']}</code>")
    else:
        lines.append("┃")
        lines.append("┃ ❌ Не найдено ни одного профиля")
    return "\n".join(lines)
    return "\n".join(lines)


def _fmt_ip(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    parts = [
        f"<b>🌐 Результат по IP:</b>",
        f"┃ IP: <code>{data['ip']}</code>",
        f"┃ Страна: {data.get('country', '—')}",
        f"┃ Регион: {data.get('region', '—')}",
        f"┃ Город: {data.get('city', '—')}",
        f"┃ Индекс: {data.get('zip', '—')}",
        f"┃ Координаты: {data.get('lat', '—')}, {data.get('lon', '—')}",
        f"┃ Провайдер: {data.get('isp', '—')}",
        f"┃ Организация: {data.get('org', '—')}",
        f"┃ ASN: {data.get('asn', '—')}",
        f"┃ Часовой пояс: {data.get('timezone', '—')}",
    ]
    flags = []
    if data.get("mobile"): flags.append("📱 Мобильный")
    if data.get("proxy"): flags.append("🔒 Прокси/VPN")
    if data.get("hosting"): flags.append("☁️ Хостинг")
    if flags:
        parts.append(f"┃ Флаги: {', '.join(flags)}")
    return "\n".join(parts)


def _fmt_domain(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    parts = [
        f"<b>🏛 Результат по домену:</b>",
        f"┃ Домен: <code>{data['domain']}</code>",
    ]
    for rtype in ["A", "AAAA", "MX", "NS", "TXT", "SOA"]:
        vals = data.get(rtype)
        if vals:
            lines = [f"┃ {rtype} ({len(vals)}):"]
            for v in vals[:6]:
                lines.append(f"┃ └ <code>{v}</code>")
            if len(vals) > 6:
                lines.append(f"┃ └ ...и ещё {len(vals) - 6}")
            parts.append("\n".join(lines))
    if data.get("http_status"):
        parts.append(f"┃ HTTP: <b>{data['http_status']}</b>")
    if data.get("server"):
        parts.append(f"┃ Сервер: {data['server']}")
    if "ssl" in data:
        parts.append(f"┃ SSL: {'✅ Есть' if data['ssl'] else '❌ Нет'}")
    if data.get("spf"):
        parts.append(f"┃ SPF: ✅")
    if data.get("dkim"):
        parts.append(f"┃ DKIM: ✅")
    if data.get("dmarc"):
        parts.append(f"┃ DMARC: ✅")
    if data.get("hosting_country"):
        parts.append(f"┃ 🌍 Хостинг: {data.get('hosting_country', '')}, {data.get('hosting_isp', '')}")
    return "\n".join(parts)


async def _execute_lookup(message: Message, mode: str, query: str):
    """Выполняет OSINT-поиск и отправляет результат."""
    uid = message.from_user.id
    if uid != OWNER_ID:
        await message.answer("❌ OSINT доступен только администраторам.")
        return

    await message.answer("⏳ Выполняю поиск...")
    try:
        if mode == "phone":
            result = phone_lookup(query)
            log_osint_query(uid, "phone", query)
            if "error" not in result and result.get("e164"):
                result["leak"] = await leak_search(result["e164"], "phone")
                messengers = await phone_messenger_check(result["e164"])
                if messengers:
                    result["messengers"] = [f"{m['platform']} — <code>{m['url']}</code>" for m in messengers]
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(query)
            log_osint_query(uid, "email", query)
            if "error" not in result:
                result["leak"] = await leak_search(query, "email")
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(query)
            log_osint_query(uid, "username", query)
            tg = await telegram_profile(query)
            if tg.get("found"):
                result["telegram"] = tg
            formatted = _fmt_username(result)
        elif mode == "ip":
            result = await ip_lookup(query)
            log_osint_query(uid, "ip", query)
            formatted = _fmt_ip(result)
        elif mode == "domain":
            result = await domain_lookup(query)
            log_osint_query(uid, "domain", query)
            formatted = _fmt_domain(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    await message.answer(formatted, parse_mode="Markdown", disable_web_page_preview=True)
    await message.answer("Выберите действие:", reply_markup=osint_menu_kb())


def _cmd_shortcut(mode: str, prompt: str, example: str):
    """Создаёт обработчик для /команда [аргументы]."""
    async def handler(message: Message, command: CommandObject):
        uid = message.from_user.id
        if uid != OWNER_ID:
            await message.answer("❌ OSINT доступен только администраторам.")
            return
        if command.args:
            await _execute_lookup(message, mode, command.args)
        else:
            osint_waiting[uid] = (mode, message.chat.id, message.message_id)
            await message.answer(f"{prompt}\nПример: <code>{example}</code>", parse_mode="HTML")
    return handler


router.message.register(_cmd_shortcut("phone", "📱 Введите номер телефона:", "+79123456789"), Command("phone"))
router.message.register(_cmd_shortcut("email", "📧 Введите email:", "example@mail.ru"), Command("email"))
router.message.register(_cmd_shortcut("username", "🔎 Введите username:", "ivanov"), Command("user"))
router.message.register(_cmd_shortcut("ip", "🌐 Введите IP:", "8.8.8.8"), Command("ip"))
router.message.register(_cmd_shortcut("domain", "🏛 Введите домен:", "google.com"), Command("domain"))


@router.message(Command("help"))
async def cmd_help(message: Message):
    uid = message.from_user.id
    show_osint = uid == OWNER_ID
    text = (
        "<b>👋 Команды бота</b>\n\n"
        + ("<b>🔍 OSINT-пробив</b>\n"
           "┃ По кнопкам: /start → OSINT-пробив\n"
           "┃ <code>/phone</code> — пробив телефона\n"
           "┃ <code>/email</code> — пробив email\n"
           "┃ <code>/user</code> — поиск по соцсетям\n"
           "┃ <code>/ip</code> — геолокация IP\n"
           "┃ <code>/domain</code> — инфо по домену\n\n" if show_osint else "")
        + "<b>🎲 Анонимный чат</b>\n"
        "┃ /start → Начать чат — поиск собеседника\n"
        "┃ Кнопка «Завершить чат» — выход\n\n"
        "<b>🎰 Казино</b>\n"
        "┃ <code>/профиль</code> — профиль игрока\n"
        "┃ <code>/игры</code> — список игр\n"
        "┃ <code>/бонус</code> — ежедневный бонус\n"
        "┃ <code>/топ</code> — топ игроков\n"
        "┃ <code>/куб [ставка]</code> — игра в кости\n\n"
        "<b>⚙️ Прочее</b>\n"
        "┃ <code>/start</code> — главное меню\n"
        "┃ <code>/stats</code> — статистика (админ)\n"
        "┃ <code>/help</code> — эта справка\n\n"
        "💡 Подсказка: можно писать команду сразу с данными:\n"
        "<code>/phone +79123456789</code> — без лишних вопросов"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_kb(show_osint=show_osint))


@router.callback_query(F.data.startswith("osint_"))
async def osint_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data

    if data == "osint_menu":
        if uid != OWNER_ID:
            await call.answer("❌ OSINT доступен только администраторам.", show_alert=True)
            return
        await call.message.edit_text("<b>🔍 OSINT-пробив</b>\nВыберите тип данных:", parse_mode="HTML",
                                     reply_markup=osint_menu_kb())
        return

    prompts = {
        "osint_phone": ("📱 Введите номер телефона\nПример: <code>+79123456789</code>", "phone"),
        "osint_email": ("📧 Введите email\nПример: <code>example@mail.ru</code>", "email"),
        "osint_username": ("🔎 Введите username\nПример: <code>ivanov</code>", "username"),
        "osint_ip": ("🌐 Введите IP-адрес\nПример: <code>8.8.8.8</code>", "ip"),
        "osint_domain": ("🏛 Введите домен\nПример: <code>google.com</code>", "domain"),
    }

    if data in prompts:
        if uid != OWNER_ID:
            await call.answer("❌ OSINT доступен только администраторам.", show_alert=True)
            return
        msg, mode = prompts[data]
        await call.message.edit_text(msg, parse_mode="HTML")
        osint_waiting[uid] = (mode, call.message.chat.id, call.message.message_id)
        return

    await call.answer()


async def osint_text_handler(message: Message):
    uid = message.from_user.id
    if uid not in osint_waiting:
        return
    mode, chat_id, prompt_msg_id = osint_waiting.pop(uid)
    text = message.text.strip()

    bot = message.bot
    try:
        await bot.edit_message_text("⏳ Выполняю поиск...", chat_id, prompt_msg_id)
    except:
        pass

    try:
        if mode == "phone":
            result = phone_lookup(text)
            log_osint_query(uid, "phone", text)
            if "error" not in result and result.get("e164"):
                result["leak"] = await leak_search(result["e164"], "phone")
                messengers = await phone_messenger_check(result["e164"])
                if messengers:
                    result["messengers"] = [f"{m['platform']} — <code>{m['url']}</code>" for m in messengers]
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(text)
            log_osint_query(uid, "email", text)
            if "error" not in result:
                result["leak"] = await leak_search(text, "email")
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(text)
            log_osint_query(uid, "username", text)
            tg = await telegram_profile(text)
            if tg.get("found"):
                result["telegram"] = tg
            formatted = _fmt_username(result)
        elif mode == "ip":
            result = await ip_lookup(text)
            log_osint_query(uid, "ip", text)
            formatted = _fmt_ip(result)
        elif mode == "domain":
            result = await domain_lookup(text)
            log_osint_query(uid, "domain", text)
            formatted = _fmt_domain(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    try:
        await bot.edit_message_text(
            text=formatted,
            chat_id=chat_id,
            message_id=prompt_msg_id,
            parse_mode="HTML",
            reply_markup=osint_menu_kb(),
            disable_web_page_preview=True,
        )
    except Exception:
        sent = await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True)
        await message.answer("Выберите действие:", reply_markup=osint_menu_kb())
