import phonenumbers
from phonenumbers import carrier, geocoder, timezone as pn_tz
import re
import ipaddress
import hashlib
import dns.resolver
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)
HTTP_TIMEOUT = 12.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

EMAIL_REGEX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# ==================== ЧЕКЕРЫ ПЛАТФОРМ (username ~250+) ====================

def _ok_status(r):
    return r.status_code == 200 and "not found" not in r.text.lower()[:2000] and "404" not in r.text[:2000]

SOCIAL_PLATFORMS = {
    # ========== СОЦИАЛЬНЫЕ СЕТИ (55) ==========
    "VK": ("https://vk.com/{}", lambda r: r.status_code == 200 and ('id="profile"' in r.text or 'id="public_page' in r.text or 'page_name' in r.text or '/id' in r.url)),
    "Telegram": ("https://t.me/{}", lambda r: r.status_code == 200 and "tgme_page_title" in r.text),
    "Instagram": ("https://www.instagram.com/{}/", lambda r: r.status_code == 200 and "page isn't available" not in r.text.lower()[:3000] and "login" not in r.text[:2000].lower() and ("profilePage" in r.text[:8000] or r.text.count('"') > 100)),
    "Twitter / X": ("https://x.com/{}", lambda r: r.status_code == 200 and "This account doesn't exist" not in r.text and "/i/flow/login" not in r.text[:2000] and ("profile" in r.text.lower() or "followers" in r.text.lower())),
    "Facebook": ("https://www.facebook.com/{}", lambda r: r.status_code == 200 and "This content isn't available" not in r.text and "Sorry, this page isn't available" not in r.text and "login" not in r.url and "not found" not in r.text.lower()[:2000]),
    "OK": ("https://ok.ru/{}", lambda r: r.status_code == 200 and "Пользователь не найден" not in r.text and "login" not in r.url),
    "Myspace": ("https://myspace.com/{}", lambda r: _ok_status(r) and "myspace" in r.text.lower()),
    "Tumblr": ("https://{}.tumblr.com/", lambda r: r.status_code == 200 and "There's nothing here" not in r.text and "Not Found" not in r.text),
    "Snapchat": ("https://www.snapchat.com/add/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Pinterest": ("https://www.pinterest.com/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "Pinterest" in r.text),
    "Reddit": ("https://www.reddit.com/user/{}/", lambda r: r.status_code == 200 and "page-not-found" not in r.text and "nobody" not in r.text.lower()[:5000] and "User not found" not in r.text),
    "LinkedIn": ("https://www.linkedin.com/in/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "profile" in r.text.lower()[:5000]),
    "Pikabu": ("https://pikabu.ru/@{}", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "404" not in r.text[:2000]),
    "Fishki": ("https://fishki.net/{}/", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "404" not in r.text[:1000]),
    "Minds": ("https://www.minds.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text[:1500] and 'data-minds' in r.text),
    "Gab": ("https://gab.com/{}", lambda r: r.status_code == 200 and "page not found" not in r.text.lower()[:2000] and "login" not in r.url and "gab" in r.text.lower()),
    "Parler": ("https://parler.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Threads": ("https://www.threads.net/@{}", lambda r: r.status_code == 200 and "page isn't available" not in r.text.lower()[:2000] and "couldn't find" not in r.text.lower()[:2000]),
    "Bluesky": ("https://bsky.app/profile/{}", lambda r: r.status_code == 200 and "Profile not found" not in r.text and "couldn't find" not in r.text.lower()[:2000]),
    "Clubhouse": ("https://www.joinclubhouse.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Mastodon.social": ("https://mastodon.social/@{}", lambda r: r.status_code == 200 and "page not found" not in r.text.lower()[:2000] and "mastodon" in r.text.lower()),
    "Gettr": ("https://gettr.com/user/{}", lambda r: r.status_code == 200 and "User not found" not in r.text and "gettr" in r.text.lower()),
    "Weibo": ("https://weibo.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "微博" in r.text),
    "VK Play": ("https://play.vk.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Triller": ("https://triller.co/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Badoo": ("https://badoo.com/en/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "badoo" in r.text.lower()),
    "Twoo": ("https://www.twoo.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Tinder": ("https://tinder.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Bumble": ("https://bumble.com/en/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "bumble" in r.text.lower()),
    "Rumble": ("https://rumble.com/user/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000] and "channel" in r.text.lower()),
    "Odysee": ("https://odysee.com/@{}", lambda r: r.status_code == 200 and "channel" in r.text.lower()[:5000]),
    "Patreon": ("https://www.patreon.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "patreon" in r.text.lower()),
    "OnlyFans": ("https://onlyfans.com/{}", lambda r: _ok_status(r) and "onlyfans" in r.text.lower()),

    # ========== ВИДЕО / СТРИМИНГ (25) ==========
    "YouTube": ("https://www.youtube.com/@{}", lambda r: r.status_code == 200 and "Not Found" not in r.text and "This page doesn't exist" not in r.text and "channel" in r.text.lower()),
    "TikTok": ("https://www.tiktok.com/@{}", lambda r: r.status_code == 200 and "Couldn't find this account" not in r.text and "Page not found" not in r.text and "profile" in r.text.lower()),
    "Twitch": ("https://www.twitch.tv/{}", lambda r: r.status_code == 200 and "Page Not Found" not in r.text and "Sorry" not in r.text[:5000] and "profile" in r.text.lower()),
    "Vimeo": ("https://vimeo.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "Sorry, we couldn" not in r.text[:3000]),
    "Dailymotion": ("https://www.dailymotion.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "profile" in r.text.lower()[:5000]),
    "Coub": ("https://coub.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and 'og:title' in r.text),
    "Rutube": ("https://rutube.ru/u/{}/", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "404" not in r.text[:2000]),
    "Mixer": ("https://mixer.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "mixer" in r.text.lower()),
    "DLive": ("https://dlive.tv/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Trovo": ("https://trovo.live/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "trovo" in r.text.lower()),
    "Kick": ("https://kick.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "kick" in r.text.lower()),
    "Facebook Watch": ("https://www.facebook.com/watch/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Periscope": ("https://www.pscp.tv/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "YouNow": ("https://www.younow.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "younow" in r.text.lower()),
    "Streamable": ("https://streamable.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "LBRY": ("https://lbry.tv/@{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "VidMe": ("https://vid.me/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Vine": ("https://vine.co/{}", lambda r: r.status_code != 404 and "page" not in r.text.lower()[:1000]),

    # ========== МУЗЫКА (15) ==========
    "SoundCloud": ("https://soundcloud.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "Not Found" not in r.text and "soundcloud" in r.text.lower()),
    "Spotify": ("https://open.spotify.com/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "Profile not found" not in r.text and "Spotify" in r.text),
    "Bandcamp": ("https://bandcamp.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "bandcamp" in r.text.lower()),
    "MixCloud": ("https://mixcloud.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()[:2000] and "mixcloud" in r.text.lower()),
    "Last.fm": ("https://www.last.fm/user/{}", lambda r: r.status_code == 200 and "User not found" not in r.text and "last.fm" in r.text.lower()),
    "Deezer": ("https://www.deezer.com/en/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "deezer" in r.text.lower()),
    "Apple Music": ("https://music.apple.com/profile/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "apple" in r.text.lower()),
    "Shazam": ("https://www.shazam.com/artist/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Napster": ("https://us.napster.com/artist/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Genius": ("https://genius.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "genius" in r.text.lower()),
    "ReverbNation": ("https://www.reverbnation.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Tidal": ("https://tidal.com/artist/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),

    # ========== ИГРЫ (20) ==========
    "Steam": ("https://steamcommunity.com/id/{}", lambda r: r.status_code == 200 and "The specified profile could not be found" not in r.text),
    "PlayStation": ("https://psnprofiles.com/{}", lambda r: r.status_code == 200 and "profile not found" not in r.text.lower()),
    "Xbox": ("https://xboxgamertag.com/search/{}", lambda r: r.status_code == 200 and "Gamertag not found" not in r.text and "Not Found" not in r.text),
    "Epic Games": ("https://www.epicgames.com/id/{}", lambda r: _ok_status(r) and "epic" in r.text.lower()),
    "Battle.net": ("https://playoverwatch.com/en-us/career/pc/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Chess.com": ("https://www.chess.com/member/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Codeforces": ("https://codeforces.com/profile/{}", lambda r: r.status_code == 200 and "is not found" not in r.text),
    "Minecraft": ("https://namemc.com/profile/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Roblox": ("https://www.roblox.com/user.aspx?username={}", lambda r: _ok_status(r) and "roblox" in r.text.lower()),
    "FortniteTracker": ("https://fortnitetracker.com/profile/all/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Apex Legends": ("https://apex.tracker.gg/apex/profile/origin/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Faceit": ("https://www.faceit.com/en/players/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "ESO": ("https://eso.database.gg/player/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "WoT": ("https://worldoftanks.eu/en/community/accounts/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Warframe": ("https://www.warframe.com/account/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "DestinyTracker": ("https://destinytracker.com/destiny-2/profile/steam/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Smite": ("https://smite.guru/profile/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),

    # ========== КОДИНГ / IT (25) ==========
    "GitHub": ("https://github.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "GitLab": ("https://gitlab.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Bitbucket": ("https://bitbucket.org/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "StackOverflow": ("https://stackoverflow.com/users/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "User not found" not in r.text),
    "LeetCode": ("https://leetcode.com/u/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Codewars": ("https://www.codewars.com/users/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "HackerRank": ("https://www.hackerrank.com/profile/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Codepen": ("https://codepen.io/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000] and "codepen" in r.text.lower()),
    "Replit": ("https://replit.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "replit" in r.text.lower()),
    "Kaggle": ("https://www.kaggle.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "kaggle" in r.text.lower()),
    "JSFiddle": ("https://jsfiddle.net/user/{}/", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "CodeSandbox": ("https://codesandbox.io/u/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "SourceForge": ("https://sourceforge.net/u/{}", lambda r: _ok_status(r) and "sourceforge" in r.text.lower()),
    "NPM": ("https://www.npmjs.com/~{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "PyPI": ("https://pypi.org/user/{}/", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Docker Hub": ("https://hub.docker.com/u/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "NuGet": ("https://www.nuget.org/profiles/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "RubyGems": ("https://rubygems.org/profiles/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Crates.io": ("https://crates.io/users/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Packagist": ("https://packagist.org/packages/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Gravatar": ("https://en.gravatar.com/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000] and "gravatar" in r.text.lower()),
    "BitBucket (Wiki)": ("https://bitbucket.org/{}/wiki/", lambda r: _ok_status(r) and "bitbucket" in r.text.lower()),
    "Gitee": ("https://gitee.com/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Hugging Face": ("https://huggingface.co/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),

    # ========== БЛОГИ / ПУБЛИКАЦИИ (15) ==========
    "Medium": ("https://medium.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and ("Member since" in r.text or "member" in r.text.lower()[:5000])),
    "Habr": ("https://habr.com/ru/users/{}/", lambda r: r.status_code == 200 and "Страница не найдена" not in r.text and "Пользователь не найден" not in r.text),
    "DEV.to": ("https://dev.to/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "dev.to" in r.text.lower()),
    "Hashnode": ("https://hashnode.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Teletype": ("https://teletype.in/@{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000] and "teletype" in r.text.lower()),
    "Telegra.ph": ("https://telegra.ph/{}", lambda r: r.status_code == 200 and "Not found" not in r.text and "404" not in r.text[:2000] and "telegra.ph" in r.text.lower()),
    "WordPress": ("https://{}.wordpress.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Ghost": ("https://{}.ghost.io/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Blogger": ("https://{}.blogspot.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Write.as": ("https://write.as/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Notion": ("https://{}.notion.site/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Substack": ("https://{}.substack.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Tistory": ("https://{}.tistory.com/", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "Naver": ("https://blog.naver.com/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),

    # ========== ДИЗАЙН / КРЕАТИВ (20) ==========
    "Behance": ("https://www.behance.net/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Dribbble": ("https://dribbble.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Flickr": ("https://www.flickr.com/people/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "500px": ("https://500px.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "DeviantArt": ("https://www.deviantart.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Unsplash": ("https://unsplash.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Imgur": ("https://imgur.com/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:3000]),
    "VSCO": ("https://vsco.co/{}/gallery", lambda r: r.status_code == 200 and "Page not found" not in r.text and "vsco" in r.text.lower()),
    "ArtStation": ("https://www.artstation.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Cargo": ("https://cargo.site/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Ello": ("https://ello.co/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "ello" in r.text.lower()),
    "Designspiration": ("https://www.designspiration.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Polyvore": ("https://polyvore.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Newgrounds": ("https://{}.newgrounds.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Instructables": ("https://www.instructables.com/member/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Crevado": ("https://{}.crevado.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Portfoliobox": ("https://{}.portfoliobox.net/", lambda r: r.status_code == 200 and "Page not found" not in r.text),

    # ========== ФРИЛАНС / БИЗНЕС (20) ==========
    "Product Hunt": ("https://www.producthunt.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Boosty": ("https://boosty.to/{}", lambda r: r.status_code not in (404, 410) and "Страница не найдена" not in r.text and "boosty" in r.text.lower()),
    "Fiverr": ("https://www.fiverr.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Freelancer": ("https://www.freelancer.com/u/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "freelancer" in r.text.lower()),
    "Upwork": ("https://www.upwork.com/freelancers/~{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "HH.ru": ("https://hh.ru/resume/{}", lambda r: r.status_code == 200 and "Резюме не найдено" not in r.text),
    "Fl.ru": ("https://www.fl.ru/users/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Freelancehunt": ("https://freelancehunt.com/freelancer/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Weebly": ("https://{}.weebly.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Wix": ("https://{}.wixsite.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Squarespace": ("https://{}.squarespace.com/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "AngelList": ("https://angel.co/u/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "nobody" not in r.text.lower()[:2000]),
    "Crunchbase": ("https://www.crunchbase.com/person/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Gumroad": ("https://gumroad.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Trello": ("https://trello.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),

    # ========== ВОПРОСЫ / ОБРАТНАЯ СВЯЗЬ (15) ==========
    "AskFM": ("https://ask.fm/{}", lambda r: r.status_code == 200 and "This user doesn't exist" not in r.text and "Page not found" not in r.text and "ask.fm" in r.text.lower()),
    "CuriousCat": ("https://curiouscat.live/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "nobody" not in r.text.lower()[:2000]),
    "Tellonym": ("https://tellonym.me/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000] and "tellonym" in r.text.lower()),
    "Quora": ("https://www.quora.com/profile/{}", lambda r: _ok_status(r) and "Page not found" not in r.text),
    "Answers.com": ("https://www.answers.com/u/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "WizIQ": ("https://www.wiziq.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "StackExchange": ("https://stackexchange.com/users/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "ProductHunt (maker)": ("https://www.producthunt.com/makers/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "HackerNews": ("https://news.ycombinator.com/user?id={}", lambda r: r.status_code == 200 and "No such user" not in r.text and "user" in r.text.lower()),

    # ========== КОНТЕНТ / МЕДИА (20) ==========
    "Letterboxd": ("https://letterboxd.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "MyAnimeList": ("https://myanimelist.net/profile/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "myanimelist" in r.text.lower()),
    "Goodreads": ("https://www.goodreads.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "Wattpad": ("https://www.wattpad.com/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "AO3": ("https://archiveofourown.org/users/{}/profile", lambda r: r.status_code == 200 and "Not Found" not in r.text and "404" not in r.text[:2000]),
    "Flickr (blog)": ("https://www.flickr.com/photos/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "ImgUp": ("https://imgup.net/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "ImageShack": ("https://imageshack.us/user/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "SlideShare": ("https://www.slideshare.net/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Scribd": ("https://www.scribd.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Issuu": ("https://issuu.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Pastebin": ("https://pastebin.com/u/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Gist": ("https://gist.github.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Medium (archive)": ("https://medium.com/{}/archive", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Pocket": ("https://getpocket.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Flipboard": ("https://flipboard.com/@{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),

    # ========== БЕЗОПАСНОСТЬ (10) ==========
    "Keybase": ("https://keybase.io/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "couldn't find" not in r.text.lower()),
    "HackTheBox": ("https://app.hackthebox.com/profile/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "profile" in r.text.lower()),
    "Bugcrowd": ("https://bugcrowd.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "User not found" not in r.text),
    "HackerOne": ("https://hackerone.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "not found" not in r.text.lower()[:2000]),
    "TryHackMe": ("https://tryhackme.com/p/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "RootMe": ("https://www.root-me.org/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),
    "CTFtime": ("https://ctftime.org/user/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),

    # ========== КРИПТО / ФИНАНСЫ (8) ==========
    "Etherscan": ("https://etherscan.io/address/{}", lambda r: r.status_code == 200 and "Invalid Address" not in r.text and "Page not found" not in r.text),
    "Blockchain": ("https://www.blockchain.com/btc/address/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Coinbase": ("https://www.coinbase.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "BitcoinTalk": ("https://bitcointalk.org/index.php?action=profile;u={}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "PayPal": ("https://www.paypal.com/paypalme/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "paypal" in r.text.lower()),
    "BuyMeACoffee": ("https://www.buymeacoffee.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Ko-fi": ("https://ko-fi.com/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "DonationAlerts": ("https://www.donationalerts.com/r/{}", lambda r: r.status_code == 200 and "страница не найдена" not in r.text.lower()),

    # ========== ВИЗИТКИ / ПРОФИЛИ (12) ==========
    "About.me": ("https://about.me/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000] and "about.me" in r.text.lower()),
    "Linktree": ("https://linktr.ee/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text and "404" not in r.text[:2000]),
    "Bio.link": ("https://bio.link/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Carrd": ("https://{}.carrd.co/", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Beacons": ("https://beacons.ai/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Taplink": ("https://taplink.cc/{}", lambda r: r.status_code == 200 and "страница не найдена" not in r.text.lower()),
    "Mssg.me": ("https://mssg.me/{}", lambda r: r.status_code == 200 and "not found" not in r.text.lower()[:2000]),

    # ========== КОНФЕРЕНЦИИ / ФОРУМЫ (10) ==========
    "Telegram DB": ("https://tgdb.ru/user/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Tgstat": ("https://tgstat.ru/user/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Lolzteam": ("https://lolzteam.net/members/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Zelenka.guru": ("https://zelenka.guru/members/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Nnmclub": ("https://nnmclub.to/forum/profile.php?mode=viewprofile&u={}", lambda r: r.status_code == 200 and "Profile" in r.text),
    "Pvp": ("https://pvp.games/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "JoyReactor": ("https://joyreactor.cc/user/{}", lambda r: r.status_code == 200 and "не найден" not in r.text),
    "Ycombinator": ("https://news.ycombinator.com/user?id={}", lambda r: r.status_code == 200 and "No such user" not in r.text),
    "DigitalOcean": ("https://www.digitalocean.com/community/users/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
    "Bitchute": ("https://www.bitchute.com/channel/{}", lambda r: r.status_code == 200 and "Page not found" not in r.text),
}

# ==================== ТЕЛЕФОННЫЕ ОПЕРАТОРЫ РФ ====================
PHONE_CARRIER_RU = {
    "Теле2": ["900", "901", "902", "903", "904", "905", "906", "908", "909", "950", "951", "952", "953", "958", "977", "999"],
    "МТС": ["910", "911", "912", "913", "914", "915", "916", "917", "918", "919", "980", "981", "982", "983", "984", "985", "986", "987", "988", "989"],
    "Билайн": ["960", "961", "962", "963", "964", "965", "966", "967", "968", "969", "970", "971", "972", "973", "974", "975", "976", "978", "979"],
    "МегаФон": ["920", "921", "922", "923", "924", "925", "926", "927", "928", "929", "930", "931", "932", "933", "934", "935", "936", "937", "938", "939"],
    "Yota": ["996", "997", "998", "999"],
    "Tinkoff Mobile": ["999"],
    "SberMobile": ["996"],
    "Danycom": ["999"],
    "MTS (Дальний Восток)": ["950", "951"],
}

# ==================== ТЕЛЕФОННЫЙ ПРОБИВ (БАЗОВЫЙ) ====================

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
        "carrier_def": def_code,
    }

# ==================== ПРОВЕРКА МЕССЕНДЖЕРОВ ПО ТЕЛЕФОНУ ====================

async def phone_messenger_check(phone_e164: str) -> list:
    phone_clean = phone_e164.lstrip("+")
    results = []
    tasks = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as c:
        # WhatsApp
        tasks.append(_check_platform(c, "WhatsApp", f"https://wa.me/{phone_clean}",
            lambda r: r.status_code in (200, 302) and "send" in r.url.lower()))
        # Viber
        tasks.append(_check_platform(c, "Viber", f"https://chats.viber.com/{phone_clean}",
            lambda r: r.status_code == 200 and "Invalid phone number" not in r.text and "viber/live" in r.text.lower()))
        # Signal (лучшая попытка — не гарантируется)
        tasks.append(_check_platform(c, "Signal", f"https://signal.me/#p/{phone_clean}",
            lambda r: r.status_code == 200 and "safety number" in r.text.lower()))

        messenger_results = await asyncio.gather(*tasks)
        for r in messenger_results:
            if r.get("found"):
                results.append(r)
    return results


async def _check_platform(client, platform, url, check_fn):
    try:
        r = await client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=6)
        return {"platform": platform, "url": url, "found": check_fn(r)}
    except:
        return {"platform": platform, "url": url, "found": False}

# ==================== ПОИСК АККАУНТОВ ПО НОМЕРУ ТЕЛЕФОНА ====================

async def phone_services_lookup(phone_e164: str) -> dict:
    phone_clean = phone_e164.lstrip("+")
    services = {}

    async def check_signal():
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                r = await c.get(f"https://signal.me/#p/{phone_clean}", headers={"User-Agent": USER_AGENT})
                services["Signal"] = r.status_code == 200 and "safety number" in r.text.lower()
        except:
            services["Signal"] = False

    async def check_whatsapp():
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                r = await c.get(f"https://wa.me/{phone_clean}", headers={"User-Agent": USER_AGENT})
                services["WhatsApp"] = r.status_code in (200, 302) and "send" in str(r.url)
        except:
            services["WhatsApp"] = False

    async def check_viber():
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                r = await c.get(f"https://chats.viber.com/{phone_clean}", headers={"User-Agent": USER_AGENT})
                services["Viber"] = r.status_code == 200 and "Invalid phone number" not in r.text
        except:
            services["Viber"] = False

    async def check_telegram():
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                r = await c.get(f"https://t.me/{phone_clean}", headers={"User-Agent": USER_AGENT})
                services["Telegram"] = "tgme_page_title" in r.text
        except:
            services["Telegram"] = False

    await asyncio.gather(
        check_signal(), check_whatsapp(), check_viber(),
        check_telegram(),
    )

    found_services = [name for name, found in services.items() if found]
    return {
        "phone": phone_e164,
        "checked": len(services),
        "found_services": found_services,
        "services": services,
    }

# ==================== EMAIL LOOKUP ====================

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


# ==================== TELEGRAM DEEP SEARCH ====================

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

# ==================== TELEGRAM PROFILE (РАСШИРЕННЫЙ) ====================

async def telegram_profile(username: str) -> dict:
    """Extract Telegram profile info from t.me page and additional sources."""
    username = username.strip().lstrip("@")
    url = f"https://t.me/{username}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                return {"found": False, "username": username}
            text = r.text
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
            is_bot = username.endswith("bot") and "bot" in name.lower()

            subscriber_count = ""
            if is_channel:
                m = re.search(r'<div class="tgme_page_extra">(.+?)</div>', text, re.DOTALL)
                if m:
                    subscriber_count = m.group(1).strip()
                    subscriber_count = re.sub(r'<[^>]+>', '', subscriber_count)

            # Дополнительная проверка через tgdb.ru
            tgdb_info = None
            try:
                async with httpx.AsyncClient(timeout=6) as c2:
                    r2 = await c2.get(f"https://tgdb.ru/user/{username}",
                                      headers={"User-Agent": USER_AGENT})
                    if r2.status_code == 200 and "не найден" not in r2.text:
                        tgdb_text = r2.text
                        tgdb_name = ""
                        m = re.search(r'<title>(.+?)</title>', tgdb_text)
                        if m:
                            tgdb_name = m.group(1).strip()
                        tgdb_info = {"found": True, "name": tgdb_name}
            except:
                pass

            return {
                "found": True,
                "username": username,
                "name": name,
                "bio": bio[:300] if bio else "",
                "extra": extra[:200] if extra else "",
                "url": url,
                "has_photo": has_photo,
                "type": "bot" if is_bot else ("channel" if is_channel else "user"),
                "subscriber_count": subscriber_count,
                "tgdb_info": tgdb_info,
            }
    except Exception as e:
        return {"found": False, "username": username, "error": str(e)}


async def telegram_profile_extended(username: str) -> dict:
    """Extended Telegram profile with data from tgstat, tgdb, and t.me."""
    base = await telegram_profile(username)
    if not base.get("found"):
        return base

    # Tgstat.ru info
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"https://tgstat.ru/user/{username}",
                            headers={"User-Agent": USER_AGENT})
            if r.status_code == 200 and "не найден" not in r.text:
                text = r.text
                tgstat_data = {}
                m = re.search(r'<span class="stat-value">([^<]+)</span>', text)
                if m:
                    tgstat_data["members"] = m.group(1).strip()
                m = re.search(r'<span class="stat-label">([^<]+)</span>', text)
                if m:
                    tgstat_data["label"] = m.group(1).strip()
                base["tgstat"] = tgstat_data if tgstat_data else None
    except:
        pass

    return base


async def telegram_deep_search(username: str) -> dict:
    """Расширенный TG OSINT: профиль + tgstat + сообщения канала."""
    base = await telegram_profile_extended(username)
    if not base.get("found"):
        return base

    # Сбор последних сообщений (для публичных каналов через rsshub)
    if base.get("type") in ("channel", "user"):
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                rss_url = f"https://tg.i-c-a.su/json/{username}"
                r = await c.get(rss_url, headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    posts = r.json()
                    if isinstance(posts, list):
                        base["recent_posts"] = posts[:3]
                    elif isinstance(posts, dict) and "messages" in posts:
                        base["recent_posts"] = posts["messages"][:3]
                # Tgdatabase.ru — ID пользователя
                id_url = f"https://tginfo.me/{username}"
                r2 = await c.get(id_url, headers={"User-Agent": USER_AGENT})
                if r2.status_code == 200 and "not found" not in r2.text.lower()[:2000]:
                    id_match = re.search(r'ID[:\s]*(-?\d+)', r2.text)
                    if id_match:
                        base["tg_id"] = id_match.group(1)
                    reg_match = re.search(r'(\d{4}-\d{2}-\d{2})', r2.text)
                    if reg_match:
                        base["registration_date"] = reg_match.group(1)
        except:
            pass

    # Сбор данных с tgstat.ru (альтернативный URL)
    if not base.get("tgstat"):
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(f"https://tgstat.ru/user/{username}",
                                headers={"User-Agent": USER_AGENT + " (compatible; Bot)"})
                if r.status_code == 200 and "не найден" not in r.text:
                    text = r.text
                    tgstat_data = {}
                    m = re.search(r'<span class="stat-value">([^<]+)</span>', text)
                    if m:
                        tgstat_data["members"] = m.group(1).strip()
                    base["tgstat"] = tgstat_data
        except:
            pass

    return base


# ==================== IP LOOKUP ====================

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

    result = {
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

    # Проверка через Shodan (публичный, без ключа)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://internetdb.shodan.io/{ip}",
                            headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                sd = r.json()
                if sd.get("ports"):
                    result["shodan_ports"] = sd["ports"]
                if sd.get("hostnames"):
                    result["shodan_hostnames"] = sd["hostnames"]
                if sd.get("cpes"):
                    result["shodan_cpes"] = sd["cpes"]
    except:
        pass

    return result


# ==================== DOMAIN LOOKUP ====================

async def domain_lookup(domain: str):
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    result = {"domain": domain}

    for rtype in ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"]:
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

    # Whois (через публичный API)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://whois.freeaiapi.com/?domain={domain}",
                            headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                w = r.json()
                if w.get("registrar"):
                    result["whois_registrar"] = w["registrar"]
                if w.get("creation_date"):
                    result["whois_created"] = w["creation_date"]
    except:
        pass

    return result


BASE_GN = re.compile(r'@?\w{3,32}$')
