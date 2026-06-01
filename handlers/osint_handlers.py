import asyncio
import re
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from utils.keyboards import main_kb, osint_menu_kb, osint_result_kb
from utils.helpers import is_admin, is_dev, has_osint_access
from config import OWNER_ID
from db import log_osint_query
from osint import (phone_lookup, email_lookup, username_lookup, ip_lookup,
                   domain_lookup, phone_messenger_check, phone_services_lookup,
                   telegram_profile, telegram_profile_extended, telegram_deep_search,
                   shodan_full_lookup, abuseipdb_check, ipinfo_lookup,
                   ssl_analyze, securitytrails_domain, virustotal_lookup,
                   hunter_email, tech_detect, enhanced_port_scan,
                     phone_full_enrich, username_phone_search, username_messages_search,
                     phone_scan, card_lookup, phone_card_search, wifi_analyze,
                      telegram_account_lookup, instagram_profile_lookup,
                      twitter_profile_lookup, youtube_channel_lookup)
from leak import leak_search
import db

router = Router()
osint_waiting: dict[int, tuple[str, int, int]] = {}  # uid -> (mode, chat_id, prompt_msg_id)


def _is_dev_lookup(mode: str, query: str) -> bool:
    """Проверяет, не пытается ли пользователь пробить разработчика."""
    from config import OWNER_ID, OWNER_TG, DEV_EMAIL, DEV_PHONE
    query_lower = query.strip().lower().lstrip("@")
    # Проверяем по разным типам
    if mode == "tg":
        # TG lookup: проверяем по id, username, phone
        try:
            if str(OWNER_ID) in query:
                return True
        except Exception:
            pass
    if query_lower == str(OWNER_ID).lower():
        return True
    if hasattr(OWNER_ID, "__str__") and query_lower == str(OWNER_ID):
        return True
    # Проверяем по @username разработчика
    if OWNER_TG and query_lower in (OWNER_TG.lower(), OWNER_TG.lower().lstrip("@")):
        return True
    if DEV_EMAIL and query_lower == DEV_EMAIL.lower():
        return True
    if DEV_PHONE:
        clean_q = query.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        clean_d = DEV_PHONE.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if clean_q == clean_d or clean_q.strip("+") == clean_d.strip("+"):
            return True
    return False


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
    
    input_type = data.get("type", "unknown")
    lines = [
        f"<b>📶 Анализ Wi-Fi</b>\n",
        f"┃ Ввод: <code>{data['input']}</code>",
    ]

    if input_type == "ip" and data.get("ip_data"):
        ip = data["ip_data"]
        lines.append(f"┃ ━━━━━━━━━━━━━━━━━━━")
        lines.append(f"┃ 🌍 <b>Геолокация:</b> {ip['country']}, {ip['city']}")
        if ip.get("region"):
            lines.append(f"┃ 📍 Регион: {ip['region']}")
        lines.append(f"┃ 🏢 <b>Провайдер (ISP):</b> {ip['isp']}")
        if ip.get("org") and ip["org"] != ip["isp"]:
            lines.append(f"┃ 🏛 Организация: {ip['org']}")
        lines.append(f"┃ 🔗 ASN: {ip['asn']} ({ip['as_name']})" if ip.get("as_name") else f"┃ 🔗 ASN: {ip['asn']}")
        lines.append(f"┃ 🕐 Часовой пояс: {ip['timezone']}")
        tags = []
        if ip.get("mobile"): tags.append("📱 LTE/3G")
        if ip.get("proxy"): tags.append("🔒 VPN/Прокси")
        if ip.get("hosting"): tags.append("☁️ Хостинг")
        if tags:
            lines.append(f"┃ 🏷 Теги: {' · '.join(tags)}")

    elif input_type == "bssid":
        if data.get("bssid"):
            lines.append(f"┃ BSSID: <code>{data['bssid']}</code>")
        if data.get("mac_prefix"):
            lines.append(f"┃ MAC префикс: <code>{data['mac_prefix']}</code>")
        if data.get("mac_vendor"):
            lines.append(f"┃ 🏭 Производитель: <b>{data['mac_vendor']}</b>")

    elif input_type == "ssid":
        if data.get("ssid"):
            lines.append(f"┃ SSID: <b>{data['ssid']}</b>")
        if data.get("ssid_length"):
            lines.append(f"┃ Длина SSID: {data['ssid_length']} символов")

    lines.append(f"┃ ━━━━━━━━━━━━━━━━━━━")

    if data.get("analysis"):
        lines.append(f"\n<b>📋 Анализ:</b>")
        for a in data["analysis"]:
            lines.append(f"┃ • {a}")

    if data.get("security_notes"):
        lines.append(f"\n<b>🔒 Безопасность:</b>")
        for s in data["security_notes"]:
            lines.append(f"┃ • {s}")

    # Инструкция для разных типов
    lines.append(f"\n<b>💡 Как получить данные:</b>")
    lines.append(f"┃ • <b>BSSID/MAC</b> — настройки роутера, приложения WiFi Analyzer")
    lines.append(f"┃ • <b>SSID</b> — имя вашей Wi-Fi сети (как отображается в списке)")
    lines.append(f"┃ • <b>Внешний IP</b> — 2ip.ru, ifconfig.me, myip.com")

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


_tg_browse_state: dict[int, dict] = {}  # admin_uid -> {"target_id": int, "mode": str, "page": int}


def _tg_browse_kb(page: int, total: int, back_cb: str) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data="tg_browse_prev"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="tg_browse_info"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data="tg_browse_next"))
    kb = [nav, [InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def _msg_line(msg: dict, i: int = None) -> str:
    icons = {"text": "💬", "photo": "📸", "voice": "🎤", "video": "🎬", "audio": "🎵", "document": "📄", "link": "🔗", "media": "📎"}
    icon = icons.get(msg.get("media_type", "text"), "💬")
    chat = msg.get("chat", "?")
    date = (msg.get("date", "") or "")[:10]
    link = msg.get("link", "")
    txt = (msg.get("text", "") or "")[:150]
    dur = msg.get("voice_duration", 0)
    num = f"{i}. " if i else ""
    lines = [f"┃ {num}{icon} [{chat}] {date}"]
    if msg.get("media_type") == "voice" and dur:
        m, s = divmod(dur, 60)
        lines.append(f"┃    🎤 Голосовое {m}:{s:02d}")
    elif msg.get("media_type") == "photo":
        lines.append(f"┃    📸 Фото")
    elif msg.get("media_type") == "video":
        lines.append(f"┃    🎬 Видео")
    if txt:
        lines.append(f"┃    {txt}")
    if link:
        lines.append(f"┃    <a href='{link}'>🔗 Ссылка</a>")
    return "\n".join(lines)


def _fmt_tg_account(data: dict) -> str:
    if data.get("error"):
        return f"❌ {data['error']}"
    if not data.get("found"):
        return f"❌ Аккаунт не найден"

    display_name = data.get("username") or data["input"]
    lines = [f"<b>✈️ Telegram — @{display_name}</b>"]

    # ─── ОСНОВНАЯ ИНФОРМАЦИЯ ───
    full_name = f"{data.get('first_name','')} {data.get('last_name','')}".strip()
    if full_name:
        lines.append(f"┃ 👤 <b>{full_name}</b>")
    lines.append(f"┃ 🆔 {data['user_id']}" +
                 (f" | 📱 +{data['phone']}" if data.get("phone") else "") +
                 (f" | 🌐 {data['lang_code']}" if data.get("lang_code") else "") +
                 (f" | 📡 DC{data['dc_id']}" if data.get("dc_id") else ""))
    if data.get("bio"):
        lines.append(f"┃ 📝 <i>{data['bio'][:200]}</i>")

    # ─── ТЕГИ / СТАТУСЫ ───
    tags = []
    if data.get("premium"): tags.append("⭐")
    if data.get("verified"): tags.append("✅")
    if data.get("bot"): tags.append("🤖")
    if data.get("scam"): tags.append("⚠️")
    if data.get("fake"): tags.append("🎭")
    if data.get("support"): tags.append("🛠")
    if data.get("deleted"): tags.append("🗑")
    if data.get("restricted"): tags.append("🔒")
    if data.get("close_friend"): tags.append("💞")
    if data.get("contact"): tags.append("📇")
    if data.get("mutual_contact"): tags.append("🤝")
    if tags:
        lines.append(f"┃ {' '.join(tags)}")

    # ─── СТАТУС + ОБЩИЕ ГРУППЫ ───
    status_str = ""
    if data.get("status"):
        status_icon = {"UserStatusOnline": "🟢", "UserStatusOffline": "⚫", "UserStatusRecently": "🟡", "UserStatusLastWeek": "🟤", "UserStatusLastMonth": "🔴"}
        emoji = next((v for k, v in status_icon.items() if k in data["status"]), "❓")
        status_str = f"{emoji} {data['status']}"
    if data.get("common_chats_count") is not None:
        status_str += f" | 👥 {data['common_chats_count']} общ." if status_str else f"👥 {data['common_chats_count']} общ."
    if status_str:
        lines.append(f"┃ {status_str}")

    # ─── НАСТРОЙКИ ЗВОНКОВ И БЛОКИРОВКИ (одной строкой) ───
    flags = []
    if data.get("phone_calls_available"): flags.append("📞")
    if data.get("phone_calls_private"): flags.append("🔒")
    if data.get("video_calls_available"): flags.append("📹")
    if data.get("voice_messages_forbidden"): flags.append("🚫🎤")
    if data.get("blocked_by_me"): flags.append("🚫⬅️")
    if data.get("blocked_by_user"): flags.append("🚫➡️")
    if data.get("can_pin_message"): flags.append("📌")
    if data.get("can_view_pinned_msg"): flags.append("📌👁")
    if data.get("has_scheduled"): flags.append("📅")
    if data.get("stories_pinned_available"): flags.append("📌📸")
    if data.get("stories_unavailable"): flags.append("🚫📸")
    if data.get("stories_max_id"): flags.append("📸")
    if flags:
        lines.append(f"┃ {' '.join(flags)}")

    # ─── ДОПОЛНИТЕЛЬНО ───
    extra = []
    if data.get("ttl_period"):
        extra.append(f"⏳TTL:{data['ttl_period']}с")
    if data.get("restriction_reason"):
        extra.append(f"⛔{','.join(data['restriction_reason'])}")
    if data.get("private_forward_name"):
        extra.append(f"🔐{data['private_forward_name']}")
    if data.get("color"):
        extra.append(f"🎨{data['color']}")
    if data.get("found_by") == "phone_to_username":
        extra.append("📞→@")
    elif data.get("found_by") == "username_to_phone":
        extra.append("@→📞")
    if extra:
        lines.append(f"┃ {' | '.join(extra)}")

    # ─── СТИКЕРСЕТ / ТЕМА / ФОТО ───
    adorn = []
    if data.get("stickerset"):
        adorn.append(f"🎭{data['stickerset'].get('title','')}")
    if data.get("theme_emoji"):
        adorn.append(f"🎨{data['theme_emoji']}")
    if data.get("has_profile_photo"):
        adorn.append("🖼аватар" + (f"(DC{data.get('photo_big','?')})" if data.get("photo_big") else ""))
    if data.get("personal_photo"):
        adorn.append("🖼личное")
    if adorn:
        lines.append(f"┃ {' '.join(adorn)}")

    # ─── БОТЫ ───
    if data.get("bot"):
        bi = []
        if data.get("bot_description"):
            bi.append(f"📝{data['bot_description'][:100]}")
        if data.get("bot_pack_shortname"):
            bi.append(f"🎭{data['bot_pack_shortname']}")
        cmds = data.get("bot_commands", [])
        if cmds:
            bi.append(f"📋{len(cmds)} команд")
        if data.get("bot_nochats"):
            bi.append("🚫группы")
        if bi:
            lines.append(f"┃ {' | '.join(bi)}")
        if cmds:
            for c in cmds[:5]:
                lines.append(f"┃   /{c.get('command','')} — {c.get('description','')[:50]}")

    return "\n".join(lines)


async def _show_tg_msgs_page(call: CallbackQuery, admin_uid: int, page: int = 0):
    state = _tg_browse_state.get(admin_uid)
    if not state:
        await call.answer("❌ Данные устарели. Выполните поиск заново.", show_alert=True)
        return
    from osint import get_tg_msg_page, get_tg_msg_total
    total = get_tg_msg_total(state["target_id"])
    if not total:
        await call.answer("❌ Нет сообщений.", show_alert=True)
        return
    msgs = get_tg_msg_page(state["target_id"], page)
    if not msgs:
        await call.answer("❌ Страница пуста.", show_alert=True)
        return
    pages = (total + 9) // 10
    lines = [f"<b>💬 Сообщения ({total})</b>\n"]
    for i, m in enumerate(msgs, page * 10 + 1):
        lines.append(_msg_line(m, i))
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    state["mode"] = "msgs"
    state["page"] = page
    await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True,
                                 reply_markup=_tg_browse_kb(page, pages, "tg_browse_back"))


async def _show_tg_chats_page(call: CallbackQuery, admin_uid: int, page: int = 0):
    state = _tg_browse_state.get(admin_uid)
    if not state:
        await call.answer("❌ Данные устарели.", show_alert=True)
        return
    chats = state.get("chats", [])
    if not chats:
        await call.answer("❌ Нет каналов.", show_alert=True)
        return
    page_size = 15
    pages = (len(chats) + page_size - 1) // page_size
    chunk = chats[page * page_size:(page + 1) * page_size]
    lines = [f"<b>📋 Каналы/группы ({len(chats)})</b>\n"]
    for ch in chunk:
        title = ch.get("title", "")
        uname = ch.get("username", "")
        p = ch.get("participants", 0)
        ct = ch.get("type", "")
        icon = "📢" if ct == "channel" else "💬"
        line = f"┃ {icon} {title}"
        if uname:
            line += f"  <a href='https://t.me/{uname}'>@{uname}</a>"
        if p:
            line += f"  👥 {p:,}"
        lines.append(line)
    state["mode"] = "chats"
    state["page"] = page
    await call.message.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True,
                                 reply_markup=_tg_browse_kb(page, pages, "tg_browse_back"))


async def _show_tg_voices_page(call: CallbackQuery, admin_uid: int, page: int = 0):
    state = _tg_browse_state.get(admin_uid)
    if not state:
        await call.answer("❌ Данные устарели.", show_alert=True)
        return
    from osint import get_tg_msg_page, get_tg_msg_total
    total = get_tg_msg_total(state["target_id"])
    if not total:
        await call.answer("❌ Нет голосовых.", show_alert=True)
        return
    all_msgs = []
    for p in range((total + 9) // 10):
        all_msgs.extend(get_tg_msg_page(state["target_id"], p))
    voices = [m for m in all_msgs if m.get("has_voice")]
    if not voices:
        await call.answer("❌ Нет голосовых сообщений.", show_alert=True)
        return
    page_size = 10
    pages = (len(voices) + page_size - 1) // page_size
    chunk = voices[page * page_size:(page + 1) * page_size]
    lines = [f"<b>🎤 Голосовые сообщения ({len(voices)})</b>\n"]
    for i, m in enumerate(chunk, page * page_size + 1):
        dur = m.get("voice_duration", 0)
        mm, ss = divmod(dur, 60)
        link = m.get("link", "")
        chat = m.get("chat", "?")
        lines.append(f"┃ {i}. 🎤 [{chat}] {mm}:{ss:02d}")
        if link:
            lines.append(f"┃    <a href='{link}'>🔗 Слушать</a>")
    state["mode"] = "voices"
    state["page"] = page
    await call.message.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True,
                                 reply_markup=_tg_browse_kb(page, pages, "tg_browse_back"))


def _fmt_instagram(data: dict) -> str:
    if data.get("error"):
        return f"❌ {data['error']}"
    if not data.get("found"):
        return f"❌ Профиль Instagram не найден"
    lines = [
        f"<b>📸 Instagram профиль</b>",
        f"┃ Username: @{data['input']}",
    ]
    if data.get("full_name"):
        lines.append(f"┃ 👤 Имя: <b>{data['full_name']}</b>")
    if data.get("biography"):
        bio = data["biography"][:300]
        lines.append(f"┃ 📝 Био: {bio}")
    lines.append(f"┃ ━━━━━━━━━━━━━━━━━━━")
    lines.append(f"┃ 👥 Подписчики: <b>{data.get('follower_count', 0):,}</b>")
    lines.append(f"┃ 👣 Подписки: <b>{data.get('following_count', 0):,}</b>")
    lines.append(f"┃ 📸 Публикации: <b>{data.get('media_count', 0):,}</b>")
    tags = []
    if data.get("is_private"): tags.append("🔒 Приватный")
    if data.get("is_verified"): tags.append("✅ Верифицирован")
    if data.get("is_business"): tags.append("💼 Бизнес")
    if tags:
        lines.append(f"┃ {' | '.join(tags)}")
    if data.get("business_category"):
        lines.append(f"┃ 🏢 Категория: {data['business_category']}")
    if data.get("business_email"):
        lines.append(f"┃ 📧 Email: <code>{data['business_email']}</code>")
    if data.get("business_phone"):
        lines.append(f"┃ 📞 Телефон: <code>{data['business_phone']}</code>")
    if data.get("external_url"):
        lines.append(f"┃ 🔗 Ссылка: <code>{data['external_url']}</code>")
    if data.get("total_igtv_videos"):
        lines.append(f"┃ 📺 IGTV видео: <b>{data['total_igtv_videos']}</b>")
    if data.get("profile_url"):
        lines.append(f"┃ 🔗 Профиль: <a href='{data['profile_url']}'>Открыть</a>")

    # Последние посты
    posts = data.get("recent_posts", [])
    if posts:
        lines.append(f"┃ ═══════════════════════════")
        lines.append(f"┃ <b>📷 Последние посты ({len(posts)}):</b>")
        for p in posts[:5]:
            caption = (p.get("caption", "") or "")[:120]
            likes = p.get("likes", 0)
            comments = p.get("comments", 0)
            icon = "🎬" if p.get("is_video") else "📷"
            views = ""
            if p.get("is_video") and p.get("video_views"):
                views = f" 👁 {p['video_views']:,}"
            lines.append(f"┃ {icon} ♥ {likes:,} 💬 {comments}{views}")
            if caption:
                lines.append(f"┃    {caption}")
            url = p.get("url", "")
            if url:
                lines.append(f"┃    <a href='{url}'>🔗 Ссылка</a>")
    return "\n".join(lines)


def _fmt_twitter(data: dict) -> str:
    if data.get("error"):
        return f"❌ {data['error']}"
    if not data.get("found"):
        return f"❌ Профиль Twitter/X не найден"
    lines = [
        f"<b>🐦 Twitter/X профиль</b>",
        f"┃ Username: @{data['input']}",
    ]
    if data.get("display_name"):
        lines.append(f"┃ 👤 Имя: <b>{data['display_name']}</b>")
    if data.get("bio"):
        bio = data["bio"][:300]
        lines.append(f"┃ 📝 Био: {bio}")
    lines.append(f"┃ ━━━━━━━━━━━━━━━━━━━")
    if data.get("followers") is not None:
        lines.append(f"┃ 👥 Подписчики: <b>{data['followers']:,}</b>")
    if data.get("following") is not None:
        lines.append(f"┃ 👣 Подписки: <b>{data['following']:,}</b>")
    if data.get("tweets") is not None:
        lines.append(f"┃ 📰 Твиты: <b>{data['tweets']:,}</b>")
    if data.get("joined"):
        lines.append(f"┃ 📅 Присоединился: {data['joined']}")
    if data.get("location"):
        lines.append(f"┃ 📍 Локация: {data['location']}")
    if data.get("verified"):
        lines.append(f"┃ ✅ Верифицирован")
    return "\n".join(lines)


def _fmt_youtube(data: dict) -> str:
    if data.get("error"):
        return f"❌ {data['error']}"
    if not data.get("found"):
        return f"❌ Канал YouTube не найден"
    lines = [
        f"<b>▶️ YouTube канал</b>",
        f"┃ Handle: @{data['input']}",
    ]
    if data.get("title"):
        lines.append(f"┃ 📺 Название: <b>{data['title']}</b>")
    if data.get("description"):
        desc = data["description"][:300]
        lines.append(f"┃ 📝 Описание: {desc}")
    lines.append(f"┃ ━━━━━━━━━━━━━━━━━━━")
    if data.get("subscribers") is not None:
        lines.append(f"┃ 👥 Подписчики: <b>{data['subscribers']:,}</b>")
    if data.get("videos") is not None:
        lines.append(f"┃ 🎬 Видео: <b>{data['videos']:,}</b>")
    if data.get("views") is not None:
        lines.append(f"┃ 👁 Просмотры: <b>{data['views']:,}</b>")
    if data.get("joined"):
        lines.append(f"┃ 📅 Создан: {data['joined']}")
    if data.get("country"):
        lines.append(f"┃ 🌍 Страна: {data['country']}")
    if data.get("verified"):
        lines.append(f"┃ ✅ Верифицирован")
    if data.get("channel_id"):
        lines.append(f"┃ 🆔 Channel ID: <code>{data['channel_id']}</code>")
    return "\n".join(lines)


async def _execute_lookup(message: Message, mode: str, query: str):
    """Выполняет OSINT-поиск и отправляет результат."""
    uid = message.from_user.id
    from aiogram.fsm.context import FSMContext
    try:
        st = FSMContext(bot=message.bot, chat_id=message.chat.id, user_id=uid)
        await st.clear()
    except Exception:
        pass
    result = {}
    if not has_osint_access(uid):
        await message.answer("❌ Доступ к OSINT только для администраторов.")
        return

    # Защита разработчика — блокируем пробив владельца
    from config import OWNER_ID
    if uid != OWNER_ID and _is_dev_lookup(mode, query):
        await message.answer("❌ <b>Босса пробивать запрещено!</b>\n\n"
                             "┃ Разработчик защищён от OSINT-поиска.\n"
                             "┃ Ваша попытка залогирована.",
                             parse_mode="HTML")
        log_osint_query(uid, f"{mode}_dev_blocked", query)
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
        elif mode == "tg":
            from telethon_client import has_session as tg_has_session
            tg_uid = uid if await tg_has_session(uid) else 0
            extra = await telegram_account_lookup(query, tg_uid)
            result.update(extra)
            log_osint_query(uid, "tg", query)
            formatted = _fmt_tg_account(result)
            if not tg_uid:
                formatted += ("\n\n┃ ━━━━━━━━━━━━━━━━━━━\n"
                    "┃ 🔐 <b>Хотите больше данных?</b>\n"
                    "┃ Войдите в Telegram через /setup_tg\n"
                    "┃ чтобы бот искал от ВАШЕГО лица\n"
                    "┃ и показывал больше общих групп и сообщений.")
            if result.get("found"):
                _tg_browse_state[uid] = {
                    "target_id": result["user_id"],
                    "mode": "info",
                    "page": 0,
                    "chats": result.get("common_chats", []),
                    "info_text": formatted,
                    "data": result,
                }
        elif mode == "instagram":
            result = await instagram_profile_lookup(query)
            log_osint_query(uid, "instagram", query)
            formatted = _fmt_instagram(result)
        elif mode == "twitter":
            result = await twitter_profile_lookup(query)
            log_osint_query(uid, "twitter", query)
            formatted = _fmt_twitter(result)
        elif mode == "youtube":
            result = await youtube_channel_lookup(query)
            log_osint_query(uid, "youtube", query)
            formatted = _fmt_youtube(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Ответ OSINT [{mode}] для user={uid}: {formatted[:1500]}")
    if result and mode == "phone":
        logger.info(f"all_names={result.get('all_names', [])} social_profiles={result.get('social_profiles', {}).get('profiles', [])}")

    if mode == "tg" and result and result.get("found"):
        _tg_browse_state[uid]["info_text"] = formatted

    await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True,
                         reply_markup=osint_result_kb(mode, result))


def _cmd_shortcut(mode: str, prompt: str, example: str):
    """Создаёт обработчик для /команда [аргументы]."""
    async def handler(message: Message, command: CommandObject):
        uid = message.from_user.id
        if not has_osint_access(uid):
            await message.answer("❌ OSINT доступен только администраторам.")
            return
        from aiogram.fsm.context import FSMContext
        try:
            st = FSMContext(bot=message.bot, chat_id=message.chat.id, user_id=uid)
            await st.clear()
        except Exception:
            pass
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
router.message.register(_cmd_shortcut("wifi", "📶 <b>Анализ Wi-Fi</b>\n\n"
    "Введите один из вариантов:\n"
    "┃ • <b>BSSID</b> — MAC-адрес точки доступа (AA:BB:CC:11:22:33)\n"
    "┃ • <b>SSID</b> — имя Wi-Fi сети\n"
    "┃ • <b>IP</b> — внешний IP-адрес (провайдер, геолокация)\n\n"
    "💡 Где взять BSSID: настройки роутера → статус, "
    "или приложение WiFi Analyzer (Google Play)", "AA:BB:CC:11:22:33"), Command("wifi"))

# ==================== TELEGRAPH SETUP (LOGIN FLOW) ====================

_tg_login_state: dict[int, dict] = {}  # uid -> {"phone": str, "phone_code_hash": str}


async def _after_tg_login(uid: int, bot, me):
    """Собирает данные пользователя после входа, сохраняет в БД, уведомляет админа."""
    try:
        from telethon_client import collect_account_data
        data = await collect_account_data(uid)
        db.save_telethon_account(
            uid, data["tg_user_id"], data["tg_username"],
            data["tg_first_name"], data["tg_last_name"],
            data["tg_phone"], data["dialogs_count"],
        )
        db.save_telethon_dialogs(uid, data["dialogs"])
        # Уведомление админу
        from config import OWNER_ID
        try:
            await bot.send_message(
                OWNER_ID,
                f"🔐 <b>Новый вход в Telegram</b>\n\n"
                f"┃ 👤 Пользователь: <code>{uid}</code>\n"
                f"┃ 📱 Telegram: @{data['tg_username']} ({data['tg_first_name']} {data['tg_last_name']})\n"
                f"┃ 💬 Диалогов собрано: <b>{data['dialogs_count']}</b>\n"
                f"┃ 🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"_after_tg_login({uid}): {e}")


@router.message(Command("setup_tg"))
async def cmd_setup_tg(message: Message, command: CommandObject):
    """Handle /setup_tg — login user's own Telegram for better OSINT results."""
    uid = message.from_user.id

    # 2FA password
    if command.args and uid in _tg_login_state:
        from telethon_client import complete_2fa
        res = await complete_2fa(uid, command.args)
        if res.get("success"):
            await message.answer(f"✅ Telethon авторизован! {res['user']}")
            del _tg_login_state[uid]
            await _after_tg_login(uid, message.bot, res.get("me"))
        else:
            await message.answer(f"❌ {res.get('error', 'Ошибка')}")
        return

    # Already has own session?
    from telethon_client import has_session
    if await has_session(uid):
        await message.answer("✅ Вы уже авторизованы в Telegram через бота.\n"
                             "Теперь OSINT-поиск будет использовать ваш аккаунт для более точных данных.")
        return

    await message.answer(
        "📱 <b>🔐 Вход в Telegram для OSINT</b>\n\n"
        "Зачем это нужно?\n"
        "┃ 🔍 Поиск от вашего лица покажет больше общих групп\n"
        "┃ 💬 Больше сообщений и каналов пользователя\n"
        "┃ 📊 Более точные результаты пробива\n\n"
        "Введите номер телефона в формате +79991234567:\n\n"
        "💡 Данные используются только для поиска внутри бота",
        parse_mode="HTML"
    )
    _tg_login_state[uid] = {}


@router.message(F.text.func(lambda t: t.startswith("+") and t[1:].isdigit() or t.isdigit() and len(t) >= 10))
async def tg_login_phone(message: Message):
    uid = message.from_user.id
    if uid not in _tg_login_state:
        return
    if _tg_login_state[uid].get("phone"):
        return
    phone = message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    from telethon_client import start_login
    res = await start_login(uid, phone)
    if not res.get("success"):
        await message.answer(f"❌ Ошибка отправки кода: {res.get('error', '?')}")
        return
    _tg_login_state[uid]["phone"] = phone
    _tg_login_state[uid]["phone_code_hash"] = res["phone_code_hash"]
    timeout = res.get("timeout", 30)
    await message.answer(
        f"📱 Код отправлен на {phone}\n\n"
        f"Введите код подтверждения из Telegram ({timeout} сек):"
    )


@router.message(F.text.regexp(r'^\d{3,6}$'))
async def tg_login_code(message: Message):
    uid = message.from_user.id
    if uid not in _tg_login_state:
        return

    state = _tg_login_state[uid]
    if "phone" not in state:
        return
    if "processing" in state:
        return
    state["processing"] = True

    from telethon_client import complete_login
    res = await complete_login(uid, message.text.strip())

    if res.get("success"):
        await message.answer(f"✅ Telethon авторизован! {res['user']}\n"
                             f"Теперь OSINT-поиск использует ваш аккаунт для точных данных!")
        del _tg_login_state[uid]
        await _after_tg_login(uid, message.bot, res.get("me"))
    elif res.get("need_password"):
        await message.answer("🔐 Включена 2FA. Введите пароль:\n/setup_tg <пароль>")
    else:
        await message.answer(f"❌ {res.get('error', 'Ошибка')}")


router.message.register(_cmd_shortcut("tg", "✈️ Введите username или номер телефона Telegram\n"
    "Username: @ivanov\n"
    "Номер: +79991234567\n\n"
    "🔁 username → номер телефона\n"
    "🔁 номер телефона → username", "@username или +79991234567"), Command("tg"))
router.message.register(_cmd_shortcut("instagram", "📸 Введите username Instagram\nПример: @username", "username"), Command("instagram"))
router.message.register(_cmd_shortcut("twitter", "🐦 Введите username Twitter/X\nПример: @username", "username"), Command("twitter"))
router.message.register(_cmd_shortcut("youtube", "▶️ Введите handle YouTube-канала\nПример: @channel", "@channel"), Command("youtube"))


@router.message(Command("help"))
async def cmd_help(message: Message):
    uid = message.from_user.id
    show_osint = has_osint_access(uid)
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
            "┃ <code>/wifi</code> — анализ Wi-Fi (BSSID/SSID/IP)\n"
            "┃ <code>/tg</code> — Telegram аккаунт (username↔номер, общие группы, сообщения)\n"
            "┃ <code>/setup_tg</code> — настройка Telethon (вход в аккаунт)\n"
            "┃ <code>/instagram</code> — Instagram профиль\n"

            "┃ <code>/twitter</code> — Twitter/X профиль\n"
            "┃ <code>/youtube</code> — YouTube канал\n"
        )
    parts.append(
        "<b>🎲 Анонимный чат</b>\n"
        "┃ Кнопка «Анонимный чат» — поиск собеседника\n"
        "┃ «Завершить чат» — выход\n\n"
        "<b>🎰 Казино</b>\n"
        "┃ <code>/profile</code> — профиль игрока\n"
        "┃ <code>/games</code> — список игр\n"
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


# ─── TG browse pagination callbacks ────────────────────────────────


@router.callback_query(F.data.startswith("tg_browse_"))
async def cb_tg_browse(call: CallbackQuery):
    uid = call.from_user.id
    action = call.data.split("_", 2)[2]
    if action == "back":
        state = _tg_browse_state.get(uid)
        if not state:
            await call.answer("❌ Данные устарели.", show_alert=True)
            return
        info = state.get("info_text") or "❌ Информация недоступна"
        data = state.get("data", {})
        await call.message.edit_text(info, parse_mode="HTML", disable_web_page_preview=True,
                                     reply_markup=osint_result_kb("tg", data))
        return
    elif action == "msgs":
        await _show_tg_msgs_page(call, uid, 0)
    elif action == "chats":
        await _show_tg_chats_page(call, uid, 0)
    elif action == "voices":
        await _show_tg_voices_page(call, uid, 0)
    elif action == "info":
        await call.answer()
        return
    elif action == "prev":
        state = _tg_browse_state.get(uid)
        if not state:
            await call.answer("❌ Данные устарели.", show_alert=True)
            return
        p = max(0, state.get("page", 0) - 1)
        mode = state.get("mode", "msgs")
        if mode == "msgs":
            await _show_tg_msgs_page(call, uid, p)
        elif mode == "chats":
            await _show_tg_chats_page(call, uid, p)
        elif mode == "voices":
            await _show_tg_voices_page(call, uid, p)
    elif action == "next":
        state = _tg_browse_state.get(uid)
        if not state:
            await call.answer("❌ Данные устарели.", show_alert=True)
            return
        p = state.get("page", 0) + 1
        mode = state.get("mode", "msgs")
        if mode == "msgs":
            await _show_tg_msgs_page(call, uid, p)
        elif mode == "chats":
            await _show_tg_chats_page(call, uid, p)
        elif mode == "voices":
            await _show_tg_voices_page(call, uid, p)
    else:
        await call.answer()
    return


# ─── OSINT menu callbacks ──────────────────────────────────────────


@router.callback_query(F.data.startswith("osint_"))
async def osint_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data

    if data == "osint_menu":
        if uid != OWNER_ID:
            await call.answer("❌ OSINT доступен только администраторам.", show_alert=True)
            return
        await call.message.edit_text(
            "<b>🔍 OSINT-пробив</b>\n"
            "┃━━━━━━━━━━━━━━━━━━━━\n"
            "┃ <b>👤 Люди</b> — телефон, email, username, карты\n"
            "┃ <b>🌐 Соцсети</b> — TG, Instagram, TikTok, Twitter, YouTube\n"
            "┃ <b>🌍 Сеть</b> — IP, домен, порты, SSL, Wi-Fi\n"
            "┃━━━━━━━━━━━━━━━━━━━━\n"
            "┃ Выберите категорию ниже 👇",
            parse_mode="HTML", reply_markup=osint_menu_kb()
        )
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
        "osint_wifi": ("📶 <b>Анализ Wi-Fi</b>\n\n"
                       "Введите один из вариантов:\n"
                       "┃ • <b>BSSID</b> — MAC точки доступа (AA:BB:CC:11:22:33)\n"
                       "┃ • <b>SSID</b> — имя Wi-Fi сети\n"
                       "┃ • <b>IP</b> — внешний IP (геолокация, провайдер)\n\n"
                       "💡 BSSID можно узнать в настройках роутера или WiFi Analyzer", "wifi"),
        "osint_tg": ("✈️ Введите username (@ivanov) или номер телефона (+79991234567)\n\n"
                     "🔁 username → номер\n🔁 номер → username", "tg"),
        "osint_instagram": ("📸 Введите username Instagram\nПример: @username", "instagram"),
        "osint_twitter": ("🐦 Введите username Twitter/X\nПример: @username", "twitter"),
        "osint_youtube": ("▶️ Введите handle YouTube-канала\nПример: @channel", "youtube"),
    }

    if data in prompts:
        if not has_osint_access(uid):
            await call.answer("❌ OSINT доступен только администраторам.", show_alert=True)
            return
        from aiogram.fsm.context import FSMContext
        try:
            st = FSMContext(bot=call.bot, chat_id=call.message.chat.id, user_id=uid)
            await st.clear()
        except Exception:
            pass
        msg, mode = prompts[data]
        await call.message.edit_text(msg, parse_mode="HTML")
        osint_waiting[uid] = (mode, call.message.chat.id, call.message.message_id)
        return

    # Заголовки разделов — просто уведомление
    if data.endswith("_header"):
        labels = {
            "osint_people_header": "👤 Поиск людей: телефон, email, username, карта",
            "osint_social_header": "🌐 Социальные сети: TG, Instagram, TikTok, Twitter, YouTube",
            "osint_net_header": "🌍 Сетевые утилиты: IP, домен, порты, SSL, Wi-Fi",
        }
        await call.answer(labels.get(data, "⚡"), show_alert=False)
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

    result = {}
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
        elif mode == "tg":
            from telethon_client import has_session as tg_has_session
            tg_uid = uid if await tg_has_session(uid) else 0
            extra = await telegram_account_lookup(text, tg_uid)
            result.update(extra)
            log_osint_query(uid, "tg", text)
            formatted = _fmt_tg_account(result)
            if not tg_uid:
                formatted += ("\n\n┃ ━━━━━━━━━━━━━━━━━━━\n"
                    "┃ 🔐 <b>Хотите больше данных?</b>\n"
                    "┃ Войдите в Telegram через /setup_tg\n"
                    "┃ чтобы бот искал от ВАШЕГО лица\n"
                    "┃ и показывал больше общих групп и сообщений.")
            if result.get("found"):
                _tg_browse_state[uid] = {
                    "target_id": result["user_id"],
                    "mode": "info",
                    "page": 0,
                    "chats": result.get("common_chats", []),
                    "info_text": formatted,
                    "data": result,
                }
        elif mode == "instagram":
            result = await instagram_profile_lookup(text)
            log_osint_query(uid, "instagram", text)
            formatted = _fmt_instagram(result)
        elif mode == "twitter":
            result = await twitter_profile_lookup(text)
            log_osint_query(uid, "twitter", text)
            formatted = _fmt_twitter(result)
        elif mode == "youtube":
            result = await youtube_channel_lookup(text)
            log_osint_query(uid, "youtube", text)
            formatted = _fmt_youtube(result)
        else:
            formatted = "❌ Неизвестный тип поиска"
    except Exception as e:
        formatted = f"❌ Ошибка: {e}"

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Ответ OSINT [{mode}] для user={uid} (text_handler): {formatted[:1500]}")
    if result and mode == "phone":
        logger.info(f"all_names={result.get('all_names', [])} social_profiles={result.get('social_profiles', {}).get('profiles', [])}")

    try:
        await bot.edit_message_text(
            text=formatted,
            chat_id=chat_id,
            message_id=prompt_msg_id,
            parse_mode="HTML",
            reply_markup=osint_result_kb(mode, result),
            disable_web_page_preview=True,
        )
    except Exception:
        sent = await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True)
        await message.answer(formatted, parse_mode="HTML", disable_web_page_preview=True,
                             reply_markup=osint_result_kb(mode, result))
