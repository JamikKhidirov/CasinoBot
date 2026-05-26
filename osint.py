import phonenumbers
from phonenumbers import carrier, geocoder, timezone as pn_tz
import re
import ipaddress
import hashlib
import dns.resolver
import httpx
import asyncio

HTTP_TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

EMAIL_REGEX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

SOCIAL_PLATFORMS = {
    "VK": ("https://vk.com/{}", lambda r: r.status_code == 200 and "id=\"profile" in r.text),
    "Telegram": ("https://t.me/{}", lambda r: r.status_code == 200 and "tgme_page_title" in r.text),
    "GitHub": ("https://github.com/{}", lambda r: r.status_code == 200),
    "Instagram": ("https://www.instagram.com/{}/", lambda r: r.status_code == 200),
    "Twitter / X": ("https://twitter.com/{}", lambda r: r.status_code == 200),
    "Reddit": ("https://www.reddit.com/user/{}", lambda r: r.status_code == 200 and "page-not-found" not in r.text),
    "YouTube": ("https://www.youtube.com/@{}", lambda r: r.status_code == 200),
    "TikTok": ("https://www.tiktok.com/@{}", lambda r: r.status_code == 200),
    "Pinterest": ("https://www.pinterest.com/{}/", lambda r: r.status_code == 200),
    "Twitch": ("https://www.twitch.tv/{}", lambda r: r.status_code == 200),
    "Steam": ("https://steamcommunity.com/id/{}", lambda r: r.status_code == 200),
    "OK": ("https://ok.ru/{}", lambda r: r.status_code == 200),
    "Pikabu": ("https://pikabu.ru/@{}", lambda r: r.status_code == 200),
    "SoundCloud": ("https://soundcloud.com/{}", lambda r: r.status_code == 200),
    "Medium": ("https://medium.com/@{}", lambda r: r.status_code == 200),
    "Habr": ("https://habr.com/users/{}/", lambda r: r.status_code == 200),
    "Replit": ("https://replit.com/@{}", lambda r: r.status_code == 200),
    "Codeforces": ("https://codeforces.com/profile/{}", lambda r: r.status_code == 200),
    "Chess.com": ("https://www.chess.com/member/{}", lambda r: r.status_code == 200),
    "DEV.to": ("https://dev.to/{}", lambda r: r.status_code == 200),
    "Boosty": ("https://boosty.to/{}", lambda r: r.status_code == 200),
    "Product Hunt": ("https://www.producthunt.com/@{}", lambda r: r.status_code == 200),
}

PHONE_CARRIER_RU = {
    "Теле2": ["900", "901", "902", "903", "904", "905", "906", "908", "909", "950", "951", "952", "953", "958", "977", "999"],
    "МТС": ["910", "911", "912", "913", "914", "915", "916", "917", "918", "919", "980", "981", "982", "983", "984", "985", "986", "987", "988", "989"],
    "Билайн": ["960", "961", "962", "963", "964", "965", "966", "967", "968", "969", "970", "971", "972", "973", "974", "975", "976", "978", "979"],
    "МегаФон": ["920", "921", "922", "923", "924", "925", "926", "927", "928", "929", "930", "931", "932", "933", "934", "935", "936", "937", "938", "939"],
    "Yota": ["996", "997", "998", "999"],
    "Tinkoff Mobile": ["999"],
}


def phone_lookup(number: str):
    try:
        num = phonenumbers.parse(number, "RU")
    except:
        try:
            num = phonenumbers.parse(number, None)
        except Exception as e:
            return {"error": f"Не удалось распарсить номер: {e}"}

    if not phonenumbers.is_possible_number(num):
        return {"error": "Невозможный номер (неправильная длина)"}
    if not phonenumbers.is_valid_number(num):
        return {"error": "Невалидный номер"}

    country = geocoder.description_for_number(num, "ru") or "Неизвестно"
    national = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)
    intern = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    tz = pn_tz.time_zones_for_number(num)
    num_type = phonenumbers.number_type(num)

    type_map = {
        phonenumbers.PhoneNumberType.MOBILE: "Мобильный",
        phonenumbers.PhoneNumberType.FIXED_LINE: "Городской",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Городской/Мобильный",
        phonenumbers.PhoneNumberType.TOLL_FREE: "Бесплатный",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "Премиум",
        phonenumbers.PhoneNumberType.SHARED_COST: "С разделением стоимости",
        phonenumbers.PhoneNumberType.VOIP: "VoIP",
        phonenumbers.PhoneNumberType.PAGER: "Пейджер",
        phonenumbers.PhoneNumberType.UAN: "UAN",
        phonenumbers.PhoneNumberType.VOICEMAIL: "Голосовая почта",
    }

    carr = carrier.name_for_number(num, "ru") or carrier.name_for_number(num, "en") or "Неизвестно"

    def_code = e164[2:5] if e164.startswith("+7") else None
    carrier_ru = None
    if def_code:
        for op, codes in PHONE_CARRIER_RU.items():
            if def_code in codes:
                carrier_ru = op
                break

    region = geocoder.description_for_valid_number(num, "ru") or "Неизвестно"

    return {
        "valid": True,
        "international": intern,
        "national": national,
        "e164": e164,
        "country": country,
        "region": region,
        "carrier_ru": carrier_ru or carr,
        "carrier_raw": carr,
        "type": type_map.get(num_type, "Неизвестно"),
        "timezone": ", ".join(tz) if tz else "Неизвестно",
        "country_code": f"+{num.country_code}",
    }


async def check_messenger(phone_e164: str) -> dict:
    result = {}
    result["telegram"] = f"https://t.me/{phone_e164.lstrip('+')}"
    result["whatsapp"] = f"https://wa.me/{phone_e164.lstrip('+')}"
    result["viber"] = f"https://viber.com/{phone_e164.lstrip('+')}"
    return result


async def email_lookup(email: str):
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        return {"error": "Неверный формат email"}

    domain = email.split("@")[1]
    result = {
        "email": email,
        "domain": domain,
        "valid_format": True,
    }

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        result["mx"] = [str(r.exchange) for r in answers]
    except dns.resolver.NXDOMAIN:
        return {**result, "error": "Домен не существует"}
    except Exception:
        result["mx"] = []
    result["mx_ok"] = len(result.get("mx", [])) > 0

    h = hashlib.md5(email.encode()).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://www.gravatar.com/{h}.json", headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                entry = r.json().get("entry", [{}])[0]
                result["gravatar"] = {
                    "name": entry.get("displayName"),
                    "avatar": f"https://www.gravatar.com/avatar/{h}?s=200",
                    "urls": [u.get("value") for u in entry.get("urls", []) if u.get("value")],
                }
    except:
        pass

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://emailrep.io/{email}", headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                er = r.json()
                result["emailrep"] = {
                    "reputation": er.get("reputation", "unknown"),
                    "suspicious": er.get("suspicious", False),
                    "details": er.get("details", {}),
                }
    except:
        pass

    return result


async def username_lookup(username: str):
    username = username.strip()
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as c:
        tasks = []
        for platform, (url, check) in SOCIAL_PLATFORMS.items():
            tasks.append(_check_platform(c, platform, url.format(username), check))
        results = await asyncio.gather(*tasks)

    found = [r for r in results if r["found"]]
    return {
        "username": username,
        "checked": len(SOCIAL_PLATFORMS),
        "found": len(found),
        "results": found,
    }


async def _check_platform(client, platform, url, check_fn):
    try:
        r = await client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        return {"platform": platform, "url": url, "found": check_fn(r)}
    except:
        return {"platform": platform, "url": url, "found": False}


async def ip_lookup(ip: str):
    ip = ip.strip()
    try:
        ipaddress.ip_address(ip)
    except:
        return {"error": "Неверный IP-адрес"}

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,zip,lat,lon,isp,org,as,asname,timezone,query,mobile,proxy,hosting",
                        headers={"User-Agent": USER_AGENT})
        data = r.json()

    if data.get("status") == "fail":
        return {"error": data.get("message", "Ошибка запроса"), "ip": ip}

    return {
        "ip": data.get("query", ip),
        "country": data.get("country", ""),
        "region": data.get("regionName", ""),
        "city": data.get("city", ""),
        "zip": data.get("zip", ""),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "isp": data.get("isp", ""),
        "org": data.get("org", ""),
        "asn": data.get("as", ""),
        "as_name": data.get("asname", ""),
        "timezone": data.get("timezone", ""),
        "mobile": data.get("mobile", False),
        "proxy": data.get("proxy", False),
        "hosting": data.get("hosting", False),
    }


async def domain_lookup(domain: str):
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    result = {"domain": domain}

    for rtype in ["A", "AAAA", "MX", "NS", "TXT", "SOA"]:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=5)
            result[rtype] = [str(r) for r in answers]
        except dns.resolver.NXDOMAIN:
            return {"error": "Домен не существует", "domain": domain}
        except:
            pass

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        try:
            r = await c.get(f"https://{domain}", headers={"User-Agent": USER_AGENT})
            result["http_status"] = r.status_code
            result["server"] = r.headers.get("Server", "N/A")
            result["ssl"] = True
        except httpx.SSLError:
            result["ssl"] = False
            try:
                r = await c.get(f"http://{domain}", headers={"User-Agent": USER_AGENT})
                result["http_status"] = r.status_code
                result["server"] = r.headers.get("Server", "N/A")
            except:
                result["http_error"] = "Таймаут"
        except:
            result["http_error"] = "Таймаут"

    return result
