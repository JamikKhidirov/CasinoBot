from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from utils.keyboards import main_kb, osint_menu_kb
from db import log_osint_query
from osint import phone_lookup, email_lookup, username_lookup, ip_lookup, domain_lookup, check_messenger

router = Router()
osint_waiting: dict[int, str] = {}


def _fmt_phone(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [
        f"📱 *Результат по номеру:*",
        f"┣ Номер: `{data['international']}`",
        f"┣ Нац. формат: `{data['national']}`",
        f"┣ Страна: {data['country']} ({data['country_code']})",
        f"┣ Регион: {data['region']}",
        f"┣ Оператор: {data['carrier_ru']}",
        f"┣ Тип: {data['type']}",
        f"┣ Часовой пояс: {data['timezone']}",
    ]
    mg = data.get("messengers")
    if mg:
        lines.append(f"\n📡 *Мессенджеры:*")
        if mg.get("telegram"):
            lines.append(f"┣ [Telegram]({mg['telegram']})")
        if mg.get("whatsapp"):
            lines.append(f"┣ [WhatsApp]({mg['whatsapp']})")
        if mg.get("viber"):
            lines.append(f"┣ [Viber]({mg['viber']})")
    return "\n".join(lines)


def _fmt_email(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [f"📧 *Результат по email:*", f"┣ Email: `{data['email']}`", f"┣ Домен: `{data['domain']}`"]
    mx = data.get("mx", [])
    if mx:
        lines.append(f"┣ MX-записи ({len(mx)}): " + ", ".join(f"`{m}`" for m in mx[:5]))
    else:
        lines.append("┣ MX-записи: ❌ не найдены")
    grav = data.get("gravatar")
    if grav:
        name = grav.get("name", "есть") if grav.get("name") else "аккаунт есть"
        lines.append(f"┣ Gravatar: {name}")
        if grav.get("urls"):
            for u in grav["urls"][:3]:
                lines.append(f"┃ • {u}")
    er = data.get("emailrep")
    if er:
        rep = er.get("reputation", "unknown")
        susp = "⚠️ Подозрительный" if er.get("suspicious") else "✅ Нормальный"
        lines.append(f"┣ Репутация: {rep} {susp}")
    return "\n".join(lines)


def _fmt_username(data: dict) -> str:
    lines = [
        f"🔎 *Результат по username:*",
        f"┣ Username: `{data['username']}`",
        f"┣ Проверено: {data['checked']} площадок",
        f"┣ Найдено: {data['found']} совпадений",
    ]
    for r in data["results"]:
        lines.append(f"┃ • [{r['platform']}]({r['url']})")
    lines.append(
        "\n⚠️ *Важно:* найти номер телефона, дату регистрации\n"
        "или историю сообщений в группах по username\n"
        "через Telegram Bot API — **невозможно**.\n"
        "Эти данные не раскрываются публично."
    )
    return "\n".join(lines)


def _fmt_ip(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    parts = [f"🌐 *IP:* `{data['ip']}`"]
    if data.get("country"): parts.append(f"┣ Страна: {data['country']}")
    if data.get("region"): parts.append(f"┣ Регион: {data['region']}")
    if data.get("city"): parts.append(f"┣ Город: {data['city']}")
    if data.get("zip"): parts.append(f"┣ Индекс: {data['zip']}")
    if data.get("lat") and data.get("lon"):
        parts.append(f"┣ Координаты: `{data['lat']}, {data['lon']}`")
    if data.get("isp"): parts.append(f"┣ Провайдер: {data['isp']}")
    if data.get("org"): parts.append(f"┣ Организация: {data['org']}")
    if data.get("asn"): parts.append(f"┣ ASN: {data['asn']}")
    if data.get("timezone"): parts.append(f"┣ Часовой пояс: {data['timezone']}")
    flags = []
    if data.get("mobile"): flags.append("📱 Мобильный")
    if data.get("proxy"): flags.append("🔒 Прокси/VPN")
    if data.get("hosting"): flags.append("☁ Хостинг")
    if flags: parts.append(f"┣ {' | '.join(flags)}")
    return "\n".join(parts)


def _fmt_domain(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    parts = [f"🏛 *Домен:* `{data['domain']}`"]
    for rtype in ("A", "AAAA", "NS"):
        if data.get(rtype):
            vals = data[rtype][:5]
            parts.append(f"┣ {rtype}: " + ", ".join(f"`{v}`" for v in vals))
    if data.get("MX"):
        vals = data["MX"][:5]
        parts.append(f"┣ MX: " + ", ".join(f"`{v}`" for v in vals))
    if "http_status" in data:
        ico = "✅" if data["http_status"] == 200 else "⚠️"
        parts.append(f"┣ HTTP: {ico} {data['http_status']}")
    if data.get("server"): parts.append(f"┣ Сервер: {data['server']}")
    if "ssl" in data: parts.append(f"┣ SSL: {'✅ Есть' if data['ssl'] else '❌ Нет'}")
    return "\n".join(parts)


async def _execute_lookup(message: Message, mode: str, query: str):
    """Выполняет OSINT-поиск и отправляет результат."""
    await message.answer("⏳ Выполняю поиск...")
    uid = message.from_user.id
    try:
        if mode == "phone":
            result = phone_lookup(query)
            log_osint_query(uid, "phone", query)
            if "error" not in result and result.get("e164"):
                result["messengers"] = await check_messenger(result["e164"])
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(query)
            log_osint_query(uid, "email", query)
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(query)
            log_osint_query(uid, "username", query)
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
        if command.args:
            await _execute_lookup(message, mode, command.args)
        else:
            osint_waiting[message.from_user.id] = mode
            await message.answer(f"{prompt}\nПример: `{example}`", parse_mode="Markdown")
    return handler


router.message.register(_cmd_shortcut("phone", "📱 Введите номер телефона:", "+79123456789"), Command("phone"))
router.message.register(_cmd_shortcut("email", "📧 Введите email:", "example@mail.ru"), Command("email"))
router.message.register(_cmd_shortcut("username", "🔎 Введите username:", "ivanov"), Command("user"))
router.message.register(_cmd_shortcut("ip", "🌐 Введите IP:", "8.8.8.8"), Command("ip"))
router.message.register(_cmd_shortcut("domain", "🏛 Введите домен:", "google.com"), Command("domain"))


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "👋 *Команды бота:*\n\n"
        "🔍 *OSINT-пробив*\n"
        "┣ По кнопкам: `/start` → OSINT-пробив\n"
        "┣ `/phone <номер>` — пробив телефона\n"
        "┣ `/email <email>` — пробив email\n"
        "┣ `/user <username>` — поиск по соцсетям\n"
        "┣ `/ip <ip>` — геолокация IP\n"
        "┣ `/domain <домен>` — инфо по домену\n\n"
        "🎲 *Анонимный чат*\n"
        "┣ `/start` → Начать чат — поиск собеседника\n"
        "┣ Кнопка «Завершить чат» — выход\n\n"
        "🎰 *Казино*\n"
        "┣ `/профиль` — профиль игрока\n"
        "┣ `/игры` — список игр\n"
        "┣ `/бонус` — ежедневный бонус\n"
        "┣ `/топ` — топ игроков\n"
        "┣ `/куб [ставка]` — игра в кости\n\n"
        "⚙️ *Прочее*\n"
        "┣ `/start` — главное меню\n"
        "┣ `/stats` — статистика (только админ)\n"
        "┣ `/help` — эта справка\n\n"
        "💡 *Подсказка:* можно писать команду сразу с данными:\n"
        "`/phone +79123456789` — без лишних вопросов"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=main_kb())


@router.callback_query(F.data.startswith("osint_"))
async def osint_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data

    if data == "osint_menu":
        await call.message.edit_text("🔍 *OSINT-пробив*\nВыберите тип данных:", parse_mode="Markdown",
                                     reply_markup=osint_menu_kb())
        return

    prompts = {
        "osint_phone": ("📱 Введите номер телефона\nПример: `+79123456789`", "phone"),
        "osint_email": ("📧 Введите email\nПример: `example@mail.ru`", "email"),
        "osint_username": ("🔎 Введите username\nПример: `ivanov`", "username"),
        "osint_ip": ("🌐 Введите IP-адрес\nПример: `8.8.8.8`", "ip"),
        "osint_domain": ("🏛 Введите домен\nПример: `google.com`", "domain"),
    }

    if data in prompts:
        msg, mode = prompts[data]
        osint_waiting[uid] = mode
        await call.message.edit_text(msg, parse_mode="Markdown")
        return

    await call.answer()


async def osint_text_handler(message: Message):
    uid = message.from_user.id
    mode = osint_waiting.pop(uid)
    text = message.text.strip()

    await message.answer("⏳ Выполняю поиск...")

    try:
        if mode == "phone":
            result = phone_lookup(text)
            log_osint_query(uid, "phone", text)
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(text)
            log_osint_query(uid, "email", text)
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(text)
            log_osint_query(uid, "username", text)
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

    await message.answer(formatted, parse_mode="Markdown", disable_web_page_preview=True)
    await message.answer("Выберите действие:", reply_markup=osint_menu_kb())
