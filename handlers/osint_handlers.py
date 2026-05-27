import asyncio
import re
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from utils.keyboards import main_kb, osint_menu_kb
from utils.helpers import is_admin, is_dev
from config import OWNER_ID
from db import log_osint_query
from osint import (phone_lookup, email_lookup, username_lookup, ip_lookup,
                   domain_lookup, phone_messenger_check, phone_services_lookup,
                   telegram_profile, telegram_profile_extended, telegram_deep_search,
                   shodan_full_lookup, abuseipdb_check, ipinfo_lookup,
                   ssl_analyze, securitytrails_domain, virustotal_lookup,
                   hunter_email, tech_detect, enhanced_port_scan,
                     phone_full_enrich, username_phone_search, username_messages_search,
                     phone_scan, card_lookup, phone_card_search, wifi_analyze)
from leak import leak_search

router = Router()
osint_waiting: dict[int, tuple[str, int, int]] = {}  # uid -> (mode, chat_id, prompt_msg_id)


def _fmt_phone(data: dict, full: bool = False) -> str:
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

    # 👤 Имя владельца (самое важное — показываем первым)
    all_names = data.get("all_names", [])
    if all_names:
        lines.append("")
        lines.append("<b>👤 Найденные данные владельца:</b>")
        seen_sources = set()
        for entry in all_names[:10]:
            name = entry.get("name", "")
            source = entry.get("source", "?")
            bdate = entry.get("bdate", "")
            line = f"┃ 📛 {name}"
            if bdate:
                line += f" | 🎂 {bdate}"
            if source and source not in seen_sources:
                line += f" | 📡 {source}"
                seen_sources.add(source)
            lines.append(line)

    # Банк по оператору (виртуальные операторы)
    enrichment = data.get("enrichment")
    if enrichment:
        if enrichment.get("bank"):
            lines.append(f"┃ {enrichment['bank']}")

    accounts = data.get("accounts")
    if accounts and accounts.get("found_services"):
        lines.append("")
        lines.append("<b>👤 Привязанные аккаунты:</b>")
        for svc in accounts["found_services"]:
            emoji = {"WhatsApp": "💬", "Viber": "💬", "Signal": "🔒", "Telegram": "✈️",
                     "VK": "📘", "Facebook": "📘", "Truecaller": "📞", "GetContact": "📞"}
            lines.append(f"┃ {emoji.get(svc, '📱')} {svc}")

    messengers = data.get("messengers")
    if messengers:
        lines.append("")
        lines.append("<b>📡 Мессенджеры:</b>")
        for m in messengers:
            lines.append(f"┃ {m}")

    # Социальные профили по номеру с именами
    social = data.get("social_profiles")
    if social and social.get("profiles"):
        lines.append("")
        lines.append("<b>👤 Профили по номеру:</b>")
        seen_platforms = set()
        for p in social["profiles"]:
            platform = p.get("platform", "")
            if platform in seen_platforms:
                continue
            seen_platforms.add(platform)
            url = p.get("url", "")
            name = p.get("name", "")
            bdate = p.get("bdate", "")
            parts_info = [platform]
            if name:
                parts_info.append(name)
            if bdate:
                parts_info.append(f"🎂 {bdate}")
            line = f"┃ {' | '.join(parts_info)}"
            if url:
                line += f"\n┃ └ <a href='{url}'>ссылка</a>"
            lines.append(line)

    # Упоминания в открытых источниках
    web = data.get("web_mentions")
    if web and web.get("found"):
        lines.append("")
        lines.append("<b>🌐 Упоминания в сети:</b>")
        if web.get("tags"):
            for tag in web["tags"][:5]:
                lines.append(f"┃ {tag}")
        if web.get("mentions"):
            lines.append(f"┃ Площадки: {', '.join(web['mentions'][:5])}")

    # Утечки
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

    # Вывод записей из утечек с именами отдельно
    leak_names = data.get("leak_names", {})
    if leak_names.get("records"):
        lines.append("")
        lines.append("<b>🔓 Имена из утечек:</b>")
        for rec in leak_names["records"][:5]:
            name = rec.get("name", "")
            src = rec.get("source", "?")
            email = rec.get("email", "")
            line = f"┃ {name}"
            if email:
                line += f" | ✉️ {email}"
            if src:
                line += f" | 📡 {src}"
            lines.append(line)

    # === ХАКЕРСКИЙ СКАН (phone_scan) ===
    scan = data.get("scan")
    if scan:
        # Мессенджеры
        lines.append("")
        lines.append("<b>📡 Присутствие в мессенджерах:</b>")
        for name, key in [("WhatsApp", "whatsapp"), ("Viber", "viber"), ("Telegram", "telegram"), ("Signal", "signal")]:
            icon = "✅" if scan.get(key) else "❌"
            lines.append(f"┃ {icon} <b>{name}</b>")

        # Спам-базы
        spam = scan.get("spam_sites", [])
        if spam:
            lines.append("")
            lines.append("<b>🚫 Отмечен в спам-базах:</b>")
            for s in spam:
                lines.append(f"┃ 🔴 <code>{s}</code>")
            if scan.get("spam_note"):
                lines.append(f"┃ └ {scan['spam_note']}")

        # Соцсети (из скана)
        social = scan.get("social", [])
        if social:
            lines.append("")
            lines.append("<b>🌐 Привязки к соцсетям (по номеру):</b>")
            for s in social[:5]:
                line = f"┃ ✅ <b>{s.get('platform', '?')}</b>"
                if s.get("name"):
                    line += f" — {s['name']}"
                lines.append(line)
                if s.get("url"):
                    lines.append(f"┃ └ <code>{s['url']}</code>")

        # Google-футпринт
        google = scan.get("google_mentions", [])
        if google:
            lines.append("")
            lines.append("<b>🌍 Google/Яндекс-футпринт:</b>")
            for g in google[:3]:
                lines.append(f"┃ 📄 {g[:150]}")

        # Email'ы, найденные по номеру
        emails = scan.get("emails", [])
        if emails:
            lines.append("")
            lines.append("<b>📧 Email'ы по номеру:</b>")
            for e in emails:
                lines.append(f"┃ ✉️ <code>{e}</code>")

        # GetContact теги
        gc_tags = scan.get("gc_tags", [])
        if gc_tags:
            lines.append("")
            lines.append("<b>🏷 GetContact теги:</b>")
            for t in gc_tags:
                lines.append(f"┃ #{t}")

        # Sync.me
        if scan.get("syncme_name"):
            lines.append(f"┃ Sync.me: {scan['syncme_name']}")

        # TG ссылки
        tg_links = scan.get("tg_links", [])
        if tg_links:
            lines.append("")
            lines.append("<b>✈️ Telegram ссылки с номером:</b>")
            for l in tg_links:
                lines.append(f"┃ <code>{l}</code>")

        # Банковские карты, найденные по номеру
        cards = data.get("cards")
        if cards and cards.get("found") and cards.get("cards"):
            lines.append("")
            lines.append("<b>💳 Найденные карты:</b>")
            for c in cards["cards"][:5]:
                line = f"┃ 🏦 {c.get('number', '?')}"
                bi = c.get("bin_info")
                if bi:
                    parts = []
                    if bi.get("bank_name") and bi["bank_name"] != "—":
                        parts.append(bi["bank_name"])
                    if bi.get("scheme") and bi["scheme"] != "—":
                        parts.append(bi["scheme"].upper())
                    if bi.get("type") and bi["type"] != "—":
                        parts.append(bi["type"])
                    if bi.get("country") and bi["country"] != "—":
                        parts.append(bi["country"])
                    if parts:
                        line += f" | {' / '.join(parts)}"
                line += f" | 📡 {c.get('source', '?')}"
                lines.append(line)

        # Риск-скоринг
        lines.append("")
        lines.append("<b>🎯 Оценка риска:</b>")
        lines.append(f"┃ {scan.get('risk_label', '🟢 Безопасный')} (score: {scan.get('risk_score', 0)}/100)")

    return "\n".join(lines)


def _fmt_hackphone(data: dict) -> str:
    lines = [
        f"<b>☠️ Хакерский скан номера</b>\n",
        f"┃ Номер: <code>{data.get('input', '')}</code>",
        f"┃ Очищенный: <code>{data.get('clean', '')}</code>",
        f"┃ Оператор: {data.get('carrier', '—')}",
    ]

    # Мессенджеры
    lines.append("")
    lines.append("<b>📡 Присутствие в мессенджерах:</b>")
    messengers = [
        ("WhatsApp", data.get("whatsapp", False), "https://wa.me/" + re.sub(r'[^\d]', '', data.get("clean", ""))),
        ("Viber", data.get("viber", False), None),
        ("Telegram", data.get("telegram", False), "https://t.me/+ " + re.sub(r'[^\d]', '', data.get("clean", ""))),
        ("Signal", data.get("signal", False), None),
    ]
    for name, present, url in messengers:
        icon = "✅" if present else "❌"
        line = f"┃ {icon} <b>{name}</b>"
        if present and url:
            line += f" | <code>{url}</code>"
        lines.append(line)

    # Соцсети
    social = data.get("social", [])
    if social:
        lines.append("")
        lines.append("<b>🌐 Привязки к соцсетям:</b>")
        for s in social[:5]:
            line = f"┃ ✅ <b>{s.get('platform', '?')}</b>"
            if s.get("name"):
                line += f" — {s['name']}"
            if s.get("city"):
                line += f" ({s['city']})"
            lines.append(line)
            if s.get("url"):
                lines.append(f"┃ └ <code>{s['url']}</code>")

    # Спам-базы
    spam = data.get("spam_sites", [])
    if spam:
        lines.append("")
        lines.append("<b>🚫 Отмечен в спам-базах:</b>")
        for s in spam:
            lines.append(f"┃ 🔴 <code>{s}</code>")
        if data.get("spam_note"):
            lines.append(f"┃ └ {data['spam_note']}")

    # Утечки
    leaks = data.get("leaks", [])
    if leaks:
        lines.append("")
        lines.append("<b>🔓 Утечки данных:</b>")
        for l in leaks:
            lines.append(f"┃ 🔴 <code>{l}</code>")

    # Google-футпринт
    google = data.get("google_mentions", [])
    if google:
        lines.append("")
        lines.append("<b>🌍 Google-футпринт:</b>")
        for g in google[:3]:
            lines.append(f"┃ 📄 {g[:150]}")

    # Яндекс-футпринт
    yandex = data.get("google_mentions", [])
    if yandex:
        yandex_items = [y for y in yandex if y.startswith("Яндекс:")]
        if yandex_items:
            lines.append("")
            lines.append("<b>🌍 Яндекс-футпринт:</b>")
            for y in yandex_items[:3]:
                lines.append(f"┃ 📄 {y[7:150]}")

    # Email'ы
    emails = data.get("emails", [])
    if emails:
        lines.append("")
        lines.append("<b>📧 Email'ы по номеру:</b>")
        for e in emails:
            lines.append(f"┃ ✉️ <code>{e}</code>")

    # GetContact
    gc_tags = data.get("gc_tags", [])
    if gc_tags:
        lines.append("")
        lines.append("<b>🏷 GetContact теги:</b>")
        for t in gc_tags:
            lines.append(f"┃ #{t}")

    # Sync.me
    if data.get("syncme_name"):
        lines.append("")
        lines.append(f"┃ Sync.me: {data['syncme_name']}")

    # TG ссылки
    tg_links = data.get("tg_links", [])
    if tg_links:
        lines.append("")
        lines.append("<b>✈️ TG ссылки с номером:</b>")
        for l in tg_links:
            lines.append(f"┃ <code>{l}</code>")

    # Банковские карты по номеру
    cards = data.get("cards")
    if cards and cards.get("found") and cards.get("cards"):
        lines.append("")
        lines.append("<b>💳 Найденные карты:</b>")
        for c in cards["cards"][:5]:
            line = f"┃ 🏦 {c.get('number', '?')}"
            bi = c.get("bin_info")
            if bi:
                parts = []
                if bi.get("bank_name") and bi["bank_name"] != "—":
                    parts.append(bi["bank_name"])
                if bi.get("scheme") and bi["scheme"] != "—":
                    parts.append(bi["scheme"].upper())
                if bi.get("type") and bi["type"] != "—":
                    parts.append(bi["type"])
                if parts:
                    line += f" | {' / '.join(parts)}"
            line += f" | 📡 {c.get('source', '?')}"
            lines.append(line)

    # Риск-скоринг
    lines.append("")
    lines.append("<b>🎯 Оценка риска:</b>")
    lines.append(f"┃ {data.get('risk_label', '🟢 Безопасный')} (score: {data.get('risk_score', 0)}/100)")

    return "\n".join(lines)


def _fmt_card(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [
        f"<b>💳 Информация о карте</b>\n",
        f"┃ BIN: <code>{data.get('bin', '—')}</code>",
        f"┃ Платёжная система: <b>{data.get('scheme', '—').upper()}</b>",
        f"┃ Тип: {data.get('type', '—')}",
        f"┃ Бренд: {data.get('brand', '—')}",
        f"┃ Prepaid: {'✅ Да' if data.get('prepaid') else '❌ Нет'}",
    ]
    if data.get("bank_name") and data["bank_name"] != "—":
        lines.append(f"┃ 🏦 Банк: <b>{data['bank_name']}</b>")
        if data.get("bank_url") and data["bank_url"] != "—":
            lines.append(f"┃ └ Сайт: <code>{data['bank_url']}</code>")
        if data.get("bank_phone") and data["bank_phone"] != "—":
            lines.append(f"┃ └ Телефон: <code>{data['bank_phone']}</code>")
    if data.get("country") and data["country"] != "—":
        lines.append(f"┃ 🌍 Страна: {data['country']} ({data.get('country_code', '—')})")
    return "\n".join(lines)


def _fmt_wifi(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    lines = [
        f"<b>📶 Анализ Wi-Fi</b>\n",
        f"┃ Ввод: <code>{data['input']}</code>",
    ]
    if data.get("bssid"):
        lines.append(f"┃ BSSID: <code>{data['bssid']}</code>")
    if data.get("ssid"):
        lines.append(f"┃ SSID: <b>{data['ssid']}</b>")
    if data.get("mac_prefix"):
        lines.append(f"┃ MAC префикс: <code>{data['mac_prefix']}</code>")
    if data.get("mac_vendor"):
        lines.append(f"┃ 🏭 Производитель: <b>{data['mac_vendor']}</b>")

    if data.get("analysis"):
        lines.append("\n<b>📋 Анализ:</b>")
        for a in data["analysis"]:
            lines.append(f"┃ • {a}")

    if data.get("security_notes"):
        lines.append("\n<b>🔒 Заметки безопасности:</b>")
        for s in data["security_notes"]:
            lines.append(f"┃ • {s}")

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

    hunter = data.get("hunter")
    if hunter:
        status = hunter.get("status", "unknown")
        result = hunter.get("result", "unknown")
        status_map = {"valid": "✅", "invalid": "❌", "unknown": "❓", "risky": "⚠️", "accept_all": "🟡"}
        icon = status_map.get(result, "❓")
        lines.append(f"┃ {icon} Hunter: <b>{result}</b> (score: {hunter.get('score', 0)})")
        if hunter.get("disposable"):
            lines.append(f"┃ └ 📬 Одноразовый: да")
        if hunter.get("webmail"):
            lines.append(f"┃ └ 📧 Webmail: да")
        if hunter.get("accept_all"):
            lines.append(f"┃ └ 📨 Accept-all: да")
        if hunter.get("smtp_check") is False:
            lines.append(f"┃ └ SMTP: не прошёл")
        if hunter.get("sources"):
            for src in hunter["sources"][:2]:
                if isinstance(src, dict):
                    lines.append(f"┃ └ {src.get('domain', '')} ({src.get('uri', '')[:60]})")

    return "\n".join(lines)


def _fmt_username(data: dict) -> str:
    all_found = data.get("found", 0)
    lines = [
        f"<b>🔎 Результат по username: <code>{data['username']}</code></b>",
        f"┃ Проверено: <b>{data['checked']}</b> площадок",
        f"┃ Найдено: <b>{all_found}</b> совпадений",
    ]
    leaks = data.get("leak")
    if leaks and leaks.get("found"):
        lines.append(f"┃ 🔓 <b>Утечки:</b> {', '.join(leaks.get('sources', []))}")

    # 📞 Номера телефонов, найденные по username
    phones = data.get("username_phones")
    if phones and len(phones.get("phone_numbers", [])) > 0:
        lines.append("")
        lines.append("<b>📞 Найденные номера телефонов:</b>")
        for ph in phones.get("phone_numbers", []):
            phone = ph.get("phone", "")
            src = ph.get("source", "?")
            ctx = ph.get("context", "")
            line = f"┃ 📞 <code>{phone}</code> | 📡 {src}"
            if ctx and "телефон" not in ctx and len(ctx) < 50:
                line += f" | {ctx}"
            lines.append(line)

    # 💬 Публичные сообщения пользователя
    msgs = data.get("username_messages")
    if msgs and msgs.get("found"):
        lines.append("")
        lines.append("<b>💬 Публичные сообщения:</b>")
        for m in msgs.get("messages", [])[:5]:
            text = m.get("text", "")[:150]
            src = m.get("source", "")
            url = m.get("url", "")
            date = m.get("date", "")
            line = f"┃ [{src}]"
            if date:
                line += f" ({str(date)[:10]})"
            lines.append(line)
            lines.append(f"┃ └ {text}")
            if url:
                lines.append(f"┃ └ <a href='{url}'>ссылка</a>")

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
        if tg.get("subscriber_count"):
            lines.append(f"┃ 👥 {tg['subscriber_count']}")
        if tg.get("tgdb_info"):
            lines.append(f"┃ 🆔 TGDB: {tg['tgdb_info'].get('name', 'найден')}")
        if tg.get("tg_id"):
            lines.append(f"┃ 🆔 ID: <code>{tg['tg_id']}</code>")
        if tg.get("registration_date"):
            lines.append(f"┃ 📅 Регистрация: {tg['registration_date']}")
        if tg.get("tgstat"):
            ts = tg["tgstat"]
            if ts.get("members"):
                lines.append(f"┃ 📊 Tgstat: {ts.get('members', '')} {ts.get('label', '')}")
        recent = tg.get("recent_posts")
        if recent:
            lines.append(f"┃ 📰 Последние посты:")
            for p in recent[:3]:
                if isinstance(p, dict):
                    txt = p.get("text", p.get("message", ""))[:100]
                    lines.append(f"┃ ├ <code>{txt}</code>")
    if data['results']:
        lines.append("")
        lines.append("<b>🌐 Найден на площадках:</b>")
        for r in data["results"]:
            lines.append(f"┃ ✅ <b>{r['platform']}</b>\n┃ └ <code>{r['url']}</code>")
    else:
        lines.append("┃")
        lines.append("┃ ❌ Не найдено ни одного профиля")
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

    # Shodan
    shodan = data.get("shodan", {})
    if shodan:
        internetdb = shodan.get("internetdb", {})
        if internetdb.get("ports"):
            ports_str = ", ".join(str(p) for p in internetdb["ports"][:20])
            parts.append(f"┃ 🔌 Порты: <code>{ports_str}</code>{'...' if len(internetdb['ports']) > 20 else ''}")
        if internetdb.get("hostnames"):
            for h in internetdb["hostnames"][:3]:
                parts.append(f"┃ └ <code>{h}</code>")
        sfull = shodan.get("shodan", {})
        if sfull:
            if sfull.get("os"):
                parts.append(f"┃ 💻 ОС: {sfull['os']}")
            if sfull.get("vulns"):
                parts.append(f"┃ 🛡 Уязвимости ({len(sfull['vulns'])}): {', '.join(sfull['vulns'][:10])}")
            services = sfull.get("services", [])
            for svc in services[:5]:
                prod = svc.get("product", "")
                ver = svc.get("version", "")
                banner = svc.get("banner", "")
                line = f"┃  {svc['port']}/{svc['transport']}"
                if prod: line += f" — {prod} {ver}"
                if banner: line += f" | {banner[:80]}"
                parts.append(line)

    # AbuseIPDB
    abuse = data.get("abuseipdb", {})
    if abuse:
        score = abuse.get("abuse_score", 0)
        icon = "🔴" if score > 50 else "🟡" if score > 10 else "🟢"
        parts.append(f"┃ {icon} Репутация: {score}% ({abuse.get('total_reports', 0)} репортов)")
        if abuse.get("usage_type"):
            parts.append(f"┃ └ Тип: {abuse['usage_type']}")

    # IPinfo
    ipinfo = data.get("ipinfo", {})
    if ipinfo:
        if ipinfo.get("org"):
            parts.append(f"┃ 🏢 Орг: {ipinfo['org']}")
        if ipinfo.get("privacy"):
            p = ipinfo["privacy"]
            if p.get("vpn"): parts.append(f"┃ 🔒 VPN: да")
            if p.get("proxy"): parts.append(f"┃ 🔒 Прокси: да")
            if p.get("tor"): parts.append(f"┃ 🧅 Tor: да")
            if p.get("hosting"): parts.append(f"┃ ☁️ Хостинг: да")
        if ipinfo.get("domains"):
            parts.append(f"┃ 🌐 Связанные домены: {', '.join(ipinfo['domains'][:5])}")
        if ipinfo.get("company"):
            parts.append(f"┃ 🏢 Компания: {ipinfo['company']}")

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

    # SSL Labs
    ssl_data = data.get("ssl")
    if ssl_data and ssl_data.get("grade"):
        parts.append(f"┃ 🔒 SSL Labs: <b>{ssl_data['grade']}</b>")
        det = ssl_data.get("details", {})
        if det.get("cert_issuer"):
            parts.append(f"┃ └ Issuer: {det['cert_issuer']}")
        if det.get("cert_valid_to"):
            parts.append(f"┃ └ Действителен до: {det['cert_valid_to']}")
        if det.get("protocol"):
            parts.append(f"┃ └ Протокол: {det['protocol']}")

    # SecurityTrails
    st = data.get("securitytrails", {})
    if st:
        if st.get("subdomains"):
            subs = st["subdomains"][:15]
            parts.append(f"┃ 🗂 Поддомены ({len(subs)}):")
            for s in subs:
                parts.append(f"┃ └ <code>{s}</code>")
        if st.get("dns_history"):
            parts.append(f"┃ 📜 DNS-история:")
            for h in st["dns_history"][:3]:
                parts.append(f"┃ └ {h.get('ip', '')} (с {h.get('first_seen', '')})")
        if st.get("whois"):
            w = st["whois"]
            if w.get("registrar"):
                parts.append(f"┃ 📋 Регистратор: {w['registrar']}")
            if w.get("created"):
                parts.append(f"┃ └ Создан: {w['created']}")
            if w.get("expires"):
                parts.append(f"┃ └ Истекает: {w['expires']}")

    # VirusTotal
    vt = data.get("virustotal", {})
    if vt:
        parts.append(f"┃ 🦠 VirusTotal: <b>{vt.get('malicious', 0)}</b> вред. / <b>{vt.get('suspicious', 0)}</b> подозр.")
        if vt.get("categories"):
            parts.append(f"┃ └ Категории: {', '.join(vt['categories'][:3])}")

    # Технологии
    tech = data.get("tech", [])
    if tech:
        tech_groups = {}
        for t in tech:
            cat = t.get("category", "Прочее")
            tech_groups.setdefault(cat, []).append(t["name"])
        for cat, names in tech_groups.items():
            parts.append(f"┃ 🔧 {cat}: {', '.join(set(names))}")

    # WHOIS
    if data.get("whois_registrar"):
        parts.append(f"┃ 📋 WHOIS: {data.get('whois_registrar', '')}")
    if data.get("whois_created"):
        parts.append(f"┃ └ Создан: {data['whois_created']}")

    return "\n".join(parts)


def _fmt_ports(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    ports = data.get("ports", [])
    if not ports:
        return "❌ Открытые порты не найдены"
    parts = [
        f"<b>🔌 Сканирование портов</b>",
        f"┃ Всего открыто: <b>{len(ports)}</b> портов",
        f"┃ Порты: <code>{', '.join(str(p) for p in ports[:50])}</code>",
    ]
    if len(ports) > 50:
        parts.append(f"┃ ...и ещё {len(ports) - 50}")
    if data.get("hostnames"):
        for h in data["hostnames"][:5]:
            parts.append(f"┃ 🌐 <code>{h}</code>")
    return "\n".join(parts)


def _fmt_ssl(data: dict) -> str:
    if not data or not data.get("grade"):
        return "❌ Не удалось проанализировать SSL"
    parts = [
        f"<b>🔒 SSL Labs анализ</b>",
        f"┃ Оценка: <b>{data['grade']}</b>",
    ]
    det = data.get("details", {})
    if det.get("protocol"):
        parts.append(f"┃ Протокол: {det['protocol']}")
    if det.get("cert_subject"):
        parts.append(f"┃ Субъект: {det['cert_subject'][:60]}")
    if det.get("cert_issuer"):
        parts.append(f"┃ Issuer: {det['cert_issuer'][:60]}")
    if det.get("cert_commonName"):
        parts.append(f"┃ CN: {', '.join(det['cert_commonName'])}")
    if det.get("cert_altNames"):
        parts.append(f"┃ SAN ({len(det['cert_altNames'])}): {', '.join(det['cert_altNames'][:8])}")
    if det.get("cert_valid_from"):
        parts.append(f"┃ 🕐 Выдан: {det['cert_valid_from']}")
    if det.get("cert_valid_to"):
        parts.append(f"┃ ⏳ Истекает: {det['cert_valid_to']}")
    if det.get("has_sni"):
        parts.append(f"┃ SNI: обязателен")
    return "\n".join(parts)


def _fmt_tech(data: dict) -> str:
    tech = data.get("tech", [])
    if not tech:
        return "❌ Не удалось определить технологии"
    parts = ["<b>🔬 Технологии сайта</b>"]
    groups = {}
    for t in tech:
        cat = t.get("category", "Прочее")
        groups.setdefault(cat, []).append(t["name"])
    for cat, names in groups.items():
        parts.append(f"┃ <b>{cat}</b>: {', '.join(sorted(set(names)))}")
    headers = data.get("headers", {})
    if headers:
        parts.append("\n┃ <b>Заголовки:</b>")
        for k, v in list(headers.items())[:10]:
            parts.append(f"┃ {k}: <code>{v[:80]}</code>")
    return "\n".join(parts)


async def _execute_lookup(message: Message, mode: str, query: str):
    """Выполняет OSINT-поиск и отправляет результат."""
    uid = message.from_user.id
    if not is_dev(uid) and not is_admin(uid):
        await message.answer("❌ OSINT доступен только администраторам.")
        return

    await message.answer("⏳ Выполняю поиск...")
    try:
        if mode == "phone":
            result = phone_lookup(query)
            log_osint_query(uid, "phone", query)
            if "error" not in result and result.get("e164"):
                e164 = result["e164"]
                leak_task = leak_search(e164, "phone")
                messenger_task = phone_messenger_check(e164)
                accounts_task = phone_services_lookup(e164)
                enrich_task = phone_full_enrich(e164, result.get("carrier_ru", ""))
                scan_task = phone_scan(e164)
                card_task = phone_card_search(e164)
                results = await asyncio.gather(leak_task, messenger_task, accounts_task, enrich_task, scan_task, card_task)
                result["leak"] = results[0]
                if results[1]:
                    result["messengers"] = [f"{m['platform']} — <code>{m['url']}</code>" for m in results[1]]
                result["accounts"] = results[2]
                enrich = results[3]
                scan = results[4]
                result["cards"] = results[5]
                if enrich:
                    result["web_mentions"] = enrich.get("web_mentions", {})
                    result["social_profiles"] = enrich.get("social_profiles", {})
                    result["enrichment"] = enrich.get("enrichment", {})
                    result["all_names"] = enrich.get("all_names", [])
                    result["leak_names"] = enrich.get("leak_names", {})
                    result["person_found"] = enrich.get("person_found", False)
                    result["primary_name"] = enrich.get("primary_name")
                if scan:
                    result["scan"] = scan
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(query)
            log_osint_query(uid, "email", query)
            if "error" not in result:
                result["leak"] = await leak_search(query, "email")
                hunter = await hunter_email(query)
                if hunter:
                    result["hunter"] = hunter
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(query)
            log_osint_query(uid, "username", query)
            tg_task = telegram_deep_search(query)
            leak_task = leak_search(query, "username")
            phone_task = username_phone_search(query)
            msgs_task = username_messages_search(query)
            tg, leak, phone_info, msgs = await asyncio.gather(tg_task, leak_task, phone_task, msgs_task)
            if tg.get("found"):
                result["telegram"] = tg
            result["leak"] = leak
            if phone_info and len(phone_info.get("phone_numbers", [])) > 0:
                result["username_phones"] = phone_info
            if msgs and msgs.get("found"):
                result["username_messages"] = msgs
            formatted = _fmt_username(result)
        elif mode == "ip":
            result = await ip_lookup(query)
            log_osint_query(uid, "ip", query)
            shodan, abuse, ipinfo = await asyncio.gather(
                shodan_full_lookup(query), abuseipdb_check(query), ipinfo_lookup(query)
            )
            if shodan: result["shodan"] = shodan
            if abuse: result["abuseipdb"] = abuse
            if ipinfo: result["ipinfo"] = ipinfo
            formatted = _fmt_ip(result)
        elif mode == "domain":
            result = await domain_lookup(query)
            log_osint_query(uid, "domain", query)
            st, vt, ssl_res, tech_res = await asyncio.gather(
                securitytrails_domain(query), virustotal_lookup(query, "domain"),
                ssl_analyze(query), tech_detect(query)
            )
            if st: result["securitytrails"] = st
            if vt: result["virustotal"] = vt
            if ssl_res: result["ssl"] = ssl_res
            if tech_res and tech_res.get("tech"):
                result["tech"] = tech_res.get("tech")
                result["headers"] = tech_res.get("headers", {})
            formatted = _fmt_domain(result)
        elif mode == "ports":
            result = await enhanced_port_scan(query)
            log_osint_query(uid, "ports", query)
            formatted = _fmt_ports(result)
        elif mode == "ssl":
            result = await ssl_analyze(query)
            log_osint_query(uid, "ssl", query)
            formatted = _fmt_ssl(result)
        elif mode == "tech":
            result = await tech_detect(query)
            log_osint_query(uid, "tech", query)
            formatted = _fmt_tech(result)
        elif mode == "hackphone":
            result = await phone_scan(query)
            log_osint_query(uid, "hackphone", query)
            formatted = _fmt_hackphone(result)
        elif mode == "card":
            result = await card_lookup(query)
            log_osint_query(uid, "card", query)
            formatted = _fmt_card(result)
        elif mode == "wifi":
            result = await wifi_analyze(query)
            log_osint_query(uid, "wifi", query)
            formatted = _fmt_wifi(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Ответ OSINT [{mode}] для user={uid}: {formatted[:1500]}")

    await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True)
    await message.answer("Выберите действие:", reply_markup=osint_menu_kb())


def _cmd_shortcut(mode: str, prompt: str, example: str):
    """Создаёт обработчик для /команда [аргументы]."""
    async def handler(message: Message, command: CommandObject):
        uid = message.from_user.id
        if not is_dev(uid) and not is_admin(uid):
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
router.message.register(_cmd_shortcut("hackphone", "☠️ Введите номер для хакерского скана:", "+79123456789"), Command("hackphone"))
router.message.register(_cmd_shortcut("card", "💳 Введите номер карты (первые 6-8 цифр):", "427612345678"), Command("card"))
router.message.register(_cmd_shortcut("wifi", "📶 Введите BSSID (MAC) или SSID сети:", "AA:BB:CC:11:22:33"), Command("wifi"))


@router.message(Command("help"))
async def cmd_help(message: Message):
    uid = message.from_user.id
    show_osint = is_dev(uid) or is_admin(uid)
    is_adm = is_admin(uid)
    parts = ["<b>👋 Команды бота</b>\n"]
    if show_osint:
        parts.append(
            "<b>🔍 OSINT-пробив (только разработчик)</b>\n"
            "┃ <code>/phone</code> — пробив телефона\n"
            "┃ <code>/hackphone</code> — хакерский скан номера\n"
            "┃ <code>/card</code> — пробив банковской карты\n"
            "┃ <code>/email</code> — пробив email\n"
            "┃ <code>/user</code> — поиск по соцсетям\n"
            "┃ <code>/ip</code> — геолокация IP\n"
            "┃ <code>/domain</code> — инфо по домену\n"
            "┃ <code>/wifi</code> — анализ Wi-Fi (BSSID/SSID)\n"
        )
    parts.append(
        "<b>🎲 Анонимный чат</b>\n"
        "┃ Кнопка «Анонимный чат» — поиск собеседника\n"
        "┃ «Завершить чат» — выход\n\n"
        "<b>🎰 Казино</b>\n"
        "┃ <code>/profile</code> — профиль игрока\n"
        "┃ <code>/games</code> — список игр\n"
        "┃ <code>/bonus</code> — ежедневный бонус\n"
        "┃ <code>/top</code> — топ игроков\n"
        "┃ <code>/dice [ставка]</code> — игра в кости\n"
        "┃ <code>/bowling [ставка]</code> — боулинг\n"
        "┃ <code>/darts [ставка]</code> — дротики\n"
        "┃ <code>/basket [ставка]</code> — баскетбол\n"
        "┃ <code>/football [ставка]</code> — футбол\n"
    )
    if is_adm:
        parts.append(
            "<b>🛡 Админ-команды</b>\n"
            "┃ <code>/stats</code> — статистика бота\n"
            "┃ <code>/mod</code> — панель модерации\n"
            "┃ <code>/ban</code> — забанить\n"
            "┃ <code>/unban</code> — разбанить\n"
            "┃ <code>/mute</code> — замутить\n"
            "┃ <code>/unmute</code> — размутить\n"
            "┃ <code>/warn</code> — выдать варн\n"
            "┃ <code>/check</code> — проверить пользователя\n"
            "┃ <code>/warns</code> — варны пользователя\n"
            "┃ <code>/chatlog</code> — переписка\n"
            "┃ <code>/admin</code> — админ-панель казино\n"
            "┃ <code>/players</code> — список игроков казино\n"
        )
    parts.append(
        "<b>⚙️ Прочее</b>\n"
        "┃ <code>/start</code> — главное меню\n"
        "┃ <code>/help</code> — эта справка"
    )
    if show_osint:
        parts.append("💡 <code>/phone +79123456789</code> — Быстрый пробив")
    text = "\n".join(parts)
    await message.answer(text, parse_mode="HTML", reply_markup=main_kb(show_osint=show_osint, show_admin=is_adm))


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
        "osint_ports": ("🔌 Введите IP для сканирования портов\nПример: <code>8.8.8.8</code>", "ports"),
        "osint_ssl": ("🔒 Введите домен для анализа SSL\nПример: <code>google.com</code>", "ssl"),
        "osint_tech": ("🔬 Введите домен для определения технологий\nПример: <code>google.com</code>", "tech"),
        "osint_hackphone": ("☠️ Введите номер для хакерского скана\nПример: <code>+79123456789</code>", "hackphone"),
        "osint_card": ("💳 Введите номер карты (первые 6-8 цифр BIN)\nПример: <code>427612345678</code>", "card"),
        "osint_wifi": ("📶 Введите BSSID (MAC) или SSID сети\nПример: <code>AA:BB:CC:11:22:33</code>", "wifi"),
    }

    if data in prompts:
        if not is_dev(uid) and not is_admin(uid):
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
                e164 = result["e164"]
                leak_task = leak_search(e164, "phone")
                messenger_task = phone_messenger_check(e164)
                accounts_task = phone_services_lookup(e164)
                enrich_task = phone_full_enrich(e164, result.get("carrier_ru", ""))
                scan_task = phone_scan(e164)
                card_task = phone_card_search(e164)
                results = await asyncio.gather(leak_task, messenger_task, accounts_task, enrich_task, scan_task, card_task)
                result["leak"] = results[0]
                if results[1]:
                    result["messengers"] = [f"{m['platform']} — <code>{m['url']}</code>" for m in results[1]]
                result["accounts"] = results[2]
                enrich = results[3]
                scan = results[4]
                result["cards"] = results[5]
                if enrich:
                    result["web_mentions"] = enrich.get("web_mentions", {})
                    result["social_profiles"] = enrich.get("social_profiles", {})
                    result["enrichment"] = enrich.get("enrichment", {})
                    result["all_names"] = enrich.get("all_names", [])
                    result["leak_names"] = enrich.get("leak_names", {})
                    result["person_found"] = enrich.get("person_found", False)
                    result["primary_name"] = enrich.get("primary_name")
                if scan:
                    result["scan"] = scan
            formatted = _fmt_phone(result)
        elif mode == "email":
            result = await email_lookup(text)
            log_osint_query(uid, "email", text)
            if "error" not in result:
                result["leak"] = await leak_search(text, "email")
                hunter = await hunter_email(text)
                if hunter:
                    result["hunter"] = hunter
            formatted = _fmt_email(result)
        elif mode == "username":
            result = await username_lookup(text)
            log_osint_query(uid, "username", text)
            tg_task = telegram_deep_search(text)
            leak_task = leak_search(text, "username")
            phone_task = username_phone_search(text)
            msgs_task = username_messages_search(text)
            tg, leak, phone_info, msgs = await asyncio.gather(tg_task, leak_task, phone_task, msgs_task)
            if tg.get("found"):
                result["telegram"] = tg
            result["leak"] = leak
            if phone_info and len(phone_info.get("phone_numbers", [])) > 0:
                result["username_phones"] = phone_info
            if msgs and msgs.get("found"):
                result["username_messages"] = msgs
            formatted = _fmt_username(result)
        elif mode == "ip":
            result = await ip_lookup(text)
            log_osint_query(uid, "ip", text)
            shodan, abuse, ipinfo = await asyncio.gather(
                shodan_full_lookup(text), abuseipdb_check(text), ipinfo_lookup(text)
            )
            if shodan: result["shodan"] = shodan
            if abuse: result["abuseipdb"] = abuse
            if ipinfo: result["ipinfo"] = ipinfo
            formatted = _fmt_ip(result)
        elif mode == "domain":
            result = await domain_lookup(text)
            log_osint_query(uid, "domain", text)
            st, vt, ssl_res, tech_res = await asyncio.gather(
                securitytrails_domain(text), virustotal_lookup(text, "domain"),
                ssl_analyze(text), tech_detect(text)
            )
            if st: result["securitytrails"] = st
            if vt: result["virustotal"] = vt
            if ssl_res: result["ssl"] = ssl_res
            if tech_res and tech_res.get("tech"):
                result["tech"] = tech_res.get("tech")
                result["headers"] = tech_res.get("headers", {})
            formatted = _fmt_domain(result)
        elif mode == "ports":
            result = await enhanced_port_scan(text)
            log_osint_query(uid, "ports", text)
            formatted = _fmt_ports(result)
        elif mode == "ssl":
            result = await ssl_analyze(text)
            log_osint_query(uid, "ssl", text)
            formatted = _fmt_ssl(result)
        elif mode == "tech":
            result = await tech_detect(text)
            log_osint_query(uid, "tech", text)
            formatted = _fmt_tech(result)
        elif mode == "hackphone":
            result = await phone_scan(text)
            log_osint_query(uid, "hackphone", text)
            formatted = _fmt_hackphone(result)
        elif mode == "card":
            result = await card_lookup(text)
            log_osint_query(uid, "card", text)
            formatted = _fmt_card(result)
        elif mode == "wifi":
            result = await wifi_analyze(text)
            log_osint_query(uid, "wifi", text)
            formatted = _fmt_wifi(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Ответ OSINT [{mode}] для user={uid} (text_handler): {formatted[:1500]}")
    logger.info(f"all_names={result.get('all_names', [])} social_profiles={result.get('social_profiles', {}).get('profiles', [])}" if mode == "phone" else "")

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
