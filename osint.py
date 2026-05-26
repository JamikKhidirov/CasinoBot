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
    "VK": ("https://vk.com/{}", lambda r: r.status_code == 200 and 'id="profile' in r.text),
    "Telegram": ("https://t.me/{}", lambda r: r.status_code == 200 and "tgme_page_title" in r.text),
    "GitHub": ("https://github.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Instagram": ("https://www.instagram.com/{}/", lambda r: r.status_code == 200 and "page isn't available" not in r.text.lower() and "Страница недоступна" not in r.text),
    "Twitter / X": ("https://x.com/{}", lambda r: r.status_code == 200 and "This account doesn't exist" not in r.text and "/i/flow/login" not in r.text[:2000] and "profile" in r.text.lower()),
    "Reddit": ("https://www.reddit.com/user/{}/", lambda r: r.status_code == 200 and "page-not-found" not in r.text and "nobody" not in r.text.lower()[:5000]),
    "YouTube": ("https://www.youtube.com/@{}", lambda r: r.status_code == 200 and "Not Found" not in r.text and "This page doesn't exist" not in r.text and "channel" in r.text.lower()),
    "TikTok": ("https://www.tiktok.com/@{}", lambda r: r.status_code == 200 and "Couldn't find this account" not in r.text),
    "Pinterest": ("https://www.pinterest.com/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Twitch": ("https://www.twitch.tv/{}", lambda r: r.status_code == 200 and "Page Not Found" not in r.text and "Sorry" not in r.text[:5000]),
    "Steam": ("https://steamcommunity.com/id/{}", lambda r: r.status_code == 200 and "The specified profile could not be found" not in r.text),
    "OK": ("https://ok.ru/{}", lambda r: r.status_code == 200 and "Пользователь не найден" not in r.text),
    "Pikabu": ("https://pikabu.ru/@{}", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text),
    "SoundCloud": ("https://soundcloud.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Medium": ("https://medium.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Habr": ("https://habr.com/ru/users/{}/", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "Пользователь не найден" not in r.text),
    "Replit": ("https://replit.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Codeforces": ("https://codeforces.com/profile/{}", lambda r: r.status_code == 200 and "is not found" not in r.text),
    "Chess.com": ("https://www.chess.com/member/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "DEV.to": ("https://dev.to/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Boosty": ("https://boosty.to/{}", lambda r: r.status_code not in (404, 410) and "Страница не найдена" not in r.text),
    "Product Hunt": ("https://www.producthunt.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Facebook": ("https://www.facebook.com/{}", lambda r: r.status_code == 200 and "This content isn't available" not in r.text and "Sorry, this page isn't available" not in r.text and "login" not in r.url),
    "LinkedIn": ("https://www.linkedin.com/in/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "profile" in r.text.lower()),
    "Snapchat": ("https://www.snapchat.com/add/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()),
    "GitLab": ("https://gitlab.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Bitbucket": ("https://bitbucket.org/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Behance": ("https://www.behance.net/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Dribbble": ("https://dribbble.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Flickr": ("https://www.flickr.com/people/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Spotify": ("https://open.spotify.com/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "VSCO": ("https://vsco.co/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Imgur": ("https://imgur.com/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:3000]),
    "Rutube": ("https://rutube.ru/u/{}/", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "404" not in r.text[:2000]),
    "Last.fm": ("https://www.last.fm/user/{}", lambda r: r.status_code == 200 and "User not found" not in r.text),
    "Teletype": ("https://teletype.in/@{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Patreon": ("https://www.patreon.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Telegram DB": ("https://tgdb.ru/user/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Tgstat": ("https://tgstat.ru/user/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "LeakCheck": ("https://leakcheck.io/search?check={}&type=username", lambda r: r.status_code == 200),
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

    # Additional checks: name from public databases
    extra_services = []
    for op, codes in PHONE_CARRIER_RU.items():
        if def_code and def_code in codes:
            extra_services.append(f"Оператор {op}")
            break

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
        "carrier_def": def_code,
        "services": extra_services,
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


MESSENGER_PLATFORMS = {
    "WhatsApp": ("https://wa.me/{}", lambda r: r.status_code == 200 and "WhatsApp" in r.text),
    "Viber": ("https://viber.com/{}", lambda r: r.status_code == 200 or "viber" in r.text.lower()),
    "Telegram": ("tg://resolve?domain={}", lambda r: False),
}


async def phone_messenger_check(phone_e164: str) -> list:
    phone_clean = phone_e164.lstrip("+")
    results = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as c:
        tasks = []
        for platform, (url, check) in MESSENGER_PLATFORMS.items():
            if platform == "Telegram":
                continue
            tasks.append(_check_platform(c, platform, url.format(phone_clean), check))
        messenger_results = await asyncio.gather(*tasks)
        for r in messenger_results:
            if r["found"]:
                results.append(r)
    return results


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


async def telegram_profile(username: str) -> dict:
    """Extract Telegram profile info from t.me page."""
    username = username.strip().lstrip("@")
    url = f"https://t.me/{username}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                return {"found": False, "username": username}
            text = r.text
            import re
            name = ""
            m = re.search(r'<div class="tgme_page_title">(.+?)</div>', text, re.DOTALL)
            if m:
                name = m.group(1).strip()
                name = re.sub(r'<[^>]+>', '', name)
            bio = ""
            m = re.search(r'<div class="tgme_page_description">(.+?)</div>', text, re.DOTALL)
            if m:
                bio = m.group(1).strip()
                bio = re.sub(r'<[^>]+>', '', bio)
                bio = bio.replace('<br/>', '\n').replace('<br>', '\n')
            extra = ""
            m = re.search(r'<div class="tgme_page_extra">(.+?)</div>', text, re.DOTALL)
            if m:
                extra = m.group(1).strip()
                extra = re.sub(r'<[^>]+>', '', extra)
            has_photo = "tgme_page_photo_image" in text
            is_channel = "tgme_channel_info" in text
            return {
                "found": True,
                "username": username,
                "name": name,
                "bio": bio[:300] if bio else "",
                "extra": extra[:200] if extra else "",
                "url": url,
                "has_photo": has_photo,
                "type": "channel" if is_channel else "user",
            }
    except Exception as e:
        return {"found": False, "username": username, "error": str(e)}


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

    try:
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

    # Additional checks
    try:
        txt_records = result.get("TXT", [])
        for t in txt_records:
            t_lower = t.lower()
            if "spf" in t_lower:
                result["spf"] = t
            if "dkim" in t_lower or "v=dkim" in t_lower:
                result["dkim"] = t
            if "dmarc" in t_lower or "v=dmarc" in t_lower:
                result["dmarc"] = t
    except:
        pass

    # Try to get server IP geolocation
    if result.get("A"):
        try:
            ip_from_domain = result["A"][0]
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"http://ip-api.com/json/{ip_from_domain}?fields=country,regionName,city,isp,org",
                                headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    geo = r.json()
                    if geo.get("status") != "fail":
                        result["hosting_country"] = geo.get("country", "")
                        result["hosting_isp"] = geo.get("isp", "")
                        result["hosting_org"] = geo.get("org", "")
        except:
            pass

    return result
