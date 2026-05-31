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
    "Danycom": ["999", "944"],
    "MTS (Дальний Восток)": ["950", "951"],
}

# Карты банков по номеру (виртуальные операторы → банк)
PHONE_BANK_MAP = {
    "SberMobile": "💳 Сбербанк",
    "Tinkoff Mobile": "💳 Тинькофф",
    "Danycom": "💳 Даньком/VTBMobile",
}

# Провайдеры VoIP (номера без привязки к банкам)
PHONE_VOIP_RU = ["940", "941", "942", "943", "944", "945", "946", "947", "948", "949"]

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


# ==================== РАСШИРЕННЫЙ ПОИСК ПО ТЕЛЕФОНУ ====================

async def phone_web_search(phone_e164: str) -> dict:
    """Поиск упоминаний номера в открытых источниках."""
    phone_clean = phone_e164.lstrip("+")
    phone_pretty = f"+7 ({phone_clean[1:4]}) {phone_clean[4:7]}-{phone_clean[7:9]}-{phone_clean[9:]}"
    result = {"mentions": [], "tags": []}

    async def check_whocalls():
        """who-calls.ru — кто звонил."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://who-calls.ru/{phone_clean}",
                                headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    text = r.text
                    not_found = ("не найдена" in text[:3000] or "Неизвестный" in text[:3000]
                                 or "неизвестный" in text[:3000] or "404" in text[:2000])
                    if not not_found:
                        # Пробуем найти имя в заголовках h1/h2
                        for m in re.finditer(r'<h[12][^>]*>([^<]{5,})</h[12]>', text):
                            val = m.group(1).strip()
                            if phone_clean not in val and len(val) > 3:
                                result["tags"].append(f"📞 who-calls: {val}")
                                result["mentions"].append("who-calls.ru")
                                break
                        # Ищем в title
                        title_m = re.search(r'<title>([^<]+)</title>', text)
                        if title_m:
                            title = title_m.group(1).strip()
                            if phone_clean not in title and "кто звонит" not in title.lower() and len(title) > 5:
                                result["tags"].append(f"📞 who-calls: {title}")
                                result["mentions"].append("who-calls.ru")
        except:
            pass

    async def check_callfilter():
        """callfilter.ru — отзывы о номере."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://callfilter.ru/{phone_clean}/",
                                headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "404" not in r.text[:2000] and "не найден" not in r.text.lower()[:3000]:
                    for m in re.finditer(r'<title>([^<]{5,})</title>', r.text):
                        title = m.group(1).strip()
                        if phone_clean not in title and len(title) > 3:
                            result["tags"].append(f"📞 callfilter: {title}")
                            result["mentions"].append("callfilter.ru")
        except:
            pass

    async def check_ktozvonil():
        """ktozvonil.com — кто звонил."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://ktozvonil.com/phone/{phone_clean}",
                                headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "не найден" not in r.text.lower()[:3000]:
                    for m in re.finditer(r'<h1[^>]*>([^<]{5,})</h1>', r.text):
                        val = m.group(1).strip()
                        if phone_clean not in val and len(val) > 3:
                            result["tags"].append(f"📞 ktozvonil: {val}")
                            result["mentions"].append("ktozvonil.com")
                            break
        except:
            pass

    async def check_spravka():
        """spravka.net — телефонный справочник РФ."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://spravka.net/phone/{phone_clean}/")
                if r.status_code == 200 and "не найден" not in r.text.lower()[:2000]:
                    for m in re.finditer(r'class="[^"]*name[^"]*"[^>]*>([^<]{2,})<', r.text):
                        val = m.group(1).strip()
                        if len(val) > 3 and not any(d in val for d in "0123456789"):
                            result["tags"].append(f"📞 spravka: {val}")
                            result["mentions"].append("spravka.net")
                            break
        except:
            pass

    async def check_poiskovo():
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://poiskovo.ru/n/{phone_clean}")
                if r.status_code == 200 and "не найдено" not in r.text.lower()[:2000]:
                    result["mentions"].append("poiskovo.ru")
        except:
            pass

    async def check_avito_phone():
        """Avito — поиск объявлений по номеру телефона."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://www.avito.ru/items/phone/{phone_clean}",
                                headers={"User-Agent": USER_AGENT,
                                         "Accept": "application/json, text/plain, */*"})
                if r.status_code == 200:
                    text = r.text
                    # Avito возвращает JSON или HTML с данными
                    if "email" in text or "profile" in text or "name" in text:
                        result["mentions"].append("Avito")
                        # Пробуем извлечь имя
                        for m in re.finditer(r'"name"\s*:\s*"([^"]{2,})"', text):
                            name = m.group(1)
                            if name and not any(d in name for d in "0123456789"):
                                result["tags"].append(f"🛒 Avito: {name}")
        except:
            pass

    async def check_google_phone():
        """Google — поиск упоминаний номера (через публичный Google Custom Search)."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.google.com/search?q={phone_clean}+OR+{phone_pretty.replace(' ', '+')}",
                    headers={"User-Agent": USER_AGENT + " (Linux; Android 12)"}
                )
                if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                    result["mentions"].append("Google")
                    # Извлекаем сниппеты
                    for m in re.finditer(r'<span[^>]*class="[^"]*BNeawe[^"]*"[^>]*>([^<]{10,})</span>', r.text):
                        snippet = m.group(1).strip()
                        if phone_clean in snippet or phone_pretty in snippet:
                            result["tags"].append(f"🔍 Google: {snippet[:150]}")
        except:
            pass

    await asyncio.gather(
        check_whocalls(), check_callfilter(), check_ktozvonil(),
        check_spravka(), check_poiskovo(), check_avito_phone(),
        check_google_phone()
    )

    result["found"] = len(result["mentions"]) > 0 or len(result["tags"]) > 0
    return result


async def phone_social_search(phone_e164: str) -> dict:
    """Поиск профилей соцсетей по номеру телефона + извлечение ФИО."""
    phone_clean = phone_e164.lstrip("+")
    phone_dotted = f"{phone_clean[:1]} {phone_clean[1:4]} {phone_clean[4:7]} {phone_clean[7:9]} {phone_clean[9:]}".strip()
    phone_formats = [phone_clean, phone_e164, phone_dotted]
    result = {"profiles": [], "names": [], "possible_names": []}

    async def check_vk_by_phone():
        """VK — поиск профиля по номеру через HTML страницы поиска."""
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                         headers={"User-Agent": USER_AGENT}) as c:
                # 1. Поиск через страницу VK Search (рендерится сервером)
                r = await c.get("https://vk.com/search",
                                params={"c[q]": phone_clean, "c[section]": "people"})
                text = r.text if r.status_code == 200 else ""

                if "Ничего не найдено" in text or "не найдено" in text.lower()[:5000]:
                    pass  # ничего не нашли
                elif r.status_code == 200:
                    # Пробуем разные паттерны поиска имён в HTML VK
                    # Pattern 1: data-name (современный VK)
                    for m in re.finditer(r'data-name="([^"]{2,})"', text):
                        name = m.group(1).strip()
                        if name and not any(d in name for d in "0123456789"):
                            result["names"].append({"source": "VK", "name": name})
                    # Pattern 2: search_row_name class
                    for m in re.finditer(r'search_row_name[^>]*>([^<]{3,})<', text):
                        name = m.group(1).strip()
                        if name and not any(d in name for d in "0123456789"):
                            result["names"].append({"source": "VK", "name": name})
                    # Pattern 3: JSON-данные в script тегах
                    for m in re.finditer(r'"name"\s*:\s*"([^"]{3,})"', text):
                        name = m.group(1).strip()
                        if name and len(name) > 3 and not any(d in name for d in "0123456789"):
                            result["names"].append({"source": "VK", "name": name})
                    # Pattern 4: ссылки на профили с именами
                    for m in re.finditer(r'href="/(id\d+)"[^>]*>([^<]{3,})<', text):
                        name = m.group(2).strip()
                        uid = m.group(1)
                        if name and not any(d in name for d in "0123456789"):
                            result["profiles"].append({
                                "platform": "VK", "name": name,
                                "url": f"https://vk.com/{uid}"
                            })
                            result["names"].append({"source": "VK", "name": name})

                # 2. VK API (работает без токена для базового поиска)
                try:
                    r2 = await c.get(
                        "https://api.vk.com/method/users.search",
                        params={"q": phone_clean, "count": "10", "v": "5.131",
                                "fields": "photo_50,sex,bdate,city,country,home_town,status,last_seen,online,has_photo,can_write_private_message,contacts,connections"},
                        headers={"User-Agent": USER_AGENT,
                                 "Accept": "application/json"}
                    )
                    if r2.status_code == 200:
                        data = r2.json()
                        if "response" in data and data["response"].get("items"):
                            for u in data["response"]["items"]:
                                fn = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                                if fn:
                                    info = {"platform": "VK", "method": "api", "name": fn}
                                    if u.get("bdate"):
                                        info["bdate"] = u["bdate"]
                                    if u.get("city", {}).get("title"):
                                        info["city"] = u["city"]["title"]
                                    if u.get("country", {}).get("title"):
                                        info["country"] = u["country"]["title"]
                                    if u.get("online") is not None:
                                        info["online"] = "🟢 Онлайн" if u["online"] else "🔴 Офлайн"
                                    if u.get("last_seen"):
                                        info["last_seen"] = u["last_seen"].get("time", "")
                                    if u.get("has_photo"):
                                        info["has_photo"] = True
                                    if u.get("status"):
                                        info["status"] = u["status"][:100]
                                    if u.get("home_town"):
                                        info["home_town"] = u["home_town"]
                                    result["profiles"].append(info)
                                    result["names"].append({"source": "VK API", "name": fn, "bdate": u.get("bdate", "")})
                except:
                    pass

                # 3. VK FOAF — открытые данные профиля (если знаем ID)
                foaf_ids = re.findall(r'/al_im\.php\?sel=(\d+)', text)
                for fid in foaf_ids[:3]:
                    try:
                        r3 = await c.get(f"https://vk.com/foaf.php?id={fid}")
                        if r3.status_code == 200:
                            name_m = re.search(r'<name>([^<]+)</name>', r3.text)
                            if name_m:
                                result["names"].append({"source": "VK FOAF", "name": name_m.group(1).strip()})
                    except:
                        pass
        except:
            pass

    async def check_truecaller():
        """Truecaller — поиск имени через web."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.truecaller.com/search/ru/{phone_clean}",
                    headers={"User-Agent": USER_AGENT,
                             "Accept": "text/html,application/xhtml+xml"}
                )
                if r.status_code == 200:
                    # Truecaller выводит имя в заголовке или JSON-LD
                    for m in re.finditer(r'"name"\s*:\s*"([^"]{2,})"', r.text):
                        name = m.group(1).strip()
                        if name and name != "Truecaller" and "truecaller" not in name.lower():
                            result["names"].append({"source": "Truecaller", "name": name})
                    # JSON-LD разметка
                    for m in re.finditer(r'"alternateName"\s*:\s*"([^"]{2,})"', r.text):
                        name = m.group(1).strip()
                        if name and not any(d in name for d in "0123456789"):
                            result["names"].append({"source": "Truecaller", "name": name})
        except:
            pass

    async def check_facebook_by_phone():
        """Facebook — поиск по номеру."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.facebook.com/search/people/?q={phone_clean}",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200 and "People" in r.text and "Search results" not in r.text[:3000]:
                    for m in re.finditer(r'aria-label="([^"]{3,})"', r.text):
                        n = m.group(1).strip()
                        if any(c.isalpha() for c in n) and len(n) > 3 and not any(d in n for d in "0123456789"):
                            result["possible_names"].append({"source": "Facebook", "name": n})
                    result["profiles"].append({"platform": "Facebook", "method": "phone_search"})
        except:
            pass

    async def check_instagram_by_phone():
        """Instagram — проверка регистрации номера через public API."""
        for fmt in [phone_clean, phone_e164]:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    # Account recovery endpoint (public, не требует авторизации)
                    r = await c.post(
                        "https://www.instagram.com/api/v1/users/lookup/",
                        data={"q": fmt, "include_reel": "false"},
                        headers={
                            "User-Agent": USER_AGENT,
                            "X-IG-App-ID": "936619743392459",
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": "https://www.instagram.com/",
                            "Accept": "application/json, text/plain, */*",
                        }
                    )
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("user", False) or data.get("message") == "checkpoint_required":
                            result["profiles"].append({
                                "platform": "Instagram",
                                "method": "phone_lookup",
                                "registered": True,
                                "message": "Номер привязан к Instagram"
                            })
                            result["names"].append({
                                "source": "Instagram", "name": "✓ Номер найден в Instagram"
                            })
                            break
                    elif r.status_code == 400:
                        data = r.json()
                        if data.get("message") == "Неверный пароль":
                            # Это значит, что аккаунт с таким номером существует!
                            result["profiles"].append({
                                "platform": "Instagram",
                                "method": "phone_lookup",
                                "registered": True
                            })
                            break
            except:
                pass

    async def check_telegram_by_phone():
        """Telegram — проверка регистрации номера (через t.me и API)."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                # Пробуем через Telegram API auth.checkPhone (публичный эндпоинт)
                r = await c.post(
                    "https://my.telegram.org/auth/send_password",
                    data={"phone": phone_e164},
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("user_exists") or data.get("registered") or data.get("phone_registered"):
                        result["profiles"].append({
                            "platform": "Telegram", "method": "api",
                            "registered": True, "name": data.get("user", {}).get("first_name", "")
                        })
                # Альтернативный способ: проверка через t.me
                for fmt in [phone_clean, phone_e164]:
                    r2 = await c.get(f"https://t.me/{fmt}",
                                     headers={"User-Agent": USER_AGENT})
                    if r2.status_code == 200 and "tgme_page_title" in r2.text:
                        name_m = re.search(r'<div class="tgme_page_title">(.+?)</div>', r2.text, re.DOTALL)
                        name = ""
                        if name_m:
                            name = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
                        result["profiles"].append({
                            "platform": "Telegram", "url": f"https://t.me/{fmt}",
                            "name": name, "method": "phone_username"
                        })
                        if name:
                            result["names"].append({"source": "Telegram", "name": name})
        except:
            pass

    async def check_phone_sites():
        """Проверка на сайтах отзывов о номерах."""
        sites = [
            ("ktozvonil.com", f"https://ktozvonil.com/phone/{phone_clean}",
             lambda t: re.search(r'<h1[^>]*>([^<]{5,})</h1>', t)),
            ("callfilter.ru", f"https://callfilter.ru/{phone_clean}",
             lambda t: re.search(r'<div class="name"[^>]*>([^<]{3,})</div>', t)),
        ]
        for site_name, url, parser in sites:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    r = await c.get(url, headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200 and "404" not in r.text[:2000]:
                        m = parser(r.text)
                        if m:
                            name = m.group(1).strip()
                            if phone_clean not in name and len(name) > 3:
                                result["names"].append({"source": site_name, "name": name})
                                result["profiles"].append({"platform": site_name, "name": name})
            except:
                pass

    await asyncio.gather(
        check_vk_by_phone(), check_truecaller(), check_facebook_by_phone(),
        check_instagram_by_phone(), check_telegram_by_phone(),
        check_phone_sites()
    )

    # Дедупликация
    seen = set()
    unique_names = []
    for n in result["names"]:
        key = n.get("name", "")
        if key and key not in seen:
            seen.add(key)
            unique_names.append(n)
    result["names"] = unique_names

    return result


async def phone_leak_name_search(phone_e164: str) -> dict:
    """Извлечение имени/фамилии/года рождения из утечек."""
    from leak import leak_search
    result = {"found": False, "names": [], "records": []}

    leak_data = await leak_search(phone_e164, "phone")
    if leak_data.get("found"):
        result["found"] = True
        for detail in leak_data.get("details", []):
            for sample in detail.get("sample", []):
                sample_str = str(sample)
                record = {}
                # Парсим строку на возможные паттерны: email:password, name:phone:etc
                if ":" in sample_str:
                    parts = sample_str.split(":")
                    # Часто в утечках формат: email:password:name:phone:...
                    for i, part in enumerate(parts):
                        part = part.strip()
                        # Ищем email
                        if "@" in part and "." in part:
                            record["email"] = part
                        # Ищем имя (кириллица или латиница, 2+ слова)
                        elif any(c.isalpha() for c in part) and len(part) > 2:
                            if any(c in "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ" for c in part):
                                record["name"] = part
                # Паттерн: имя и телефон рядом
                phone_in_sample = phone_e164.lstrip("+") in sample_str or phone_e164 in sample_str
                if phone_in_sample:
                    # Ищем русские имена рядом с номером
                    name_patterns = re.findall(r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)', sample_str)
                    for np in name_patterns[:3]:
                        if np not in [r.get("name", "") for r in result["records"]]:
                            result["records"].append({"name": np, "source": detail.get("source", "leak")})
                if record:
                    result["records"].append(record)
    return result


async def phone_owner_enrich(phone_e164: str, carrier_ru: str = "") -> dict:
    """Обогащение данных: банк, возможный владелец, дополнительные теги."""
    phone_clean = phone_e164.lstrip("+")
    def_code = phone_clean[1:4] if phone_clean.startswith("7") else phone_clean[:3]
    result = {
        "bank": None,
        "possible_banks": [],
        "operator_type": "Мобильный",
        "voip": def_code in PHONE_VOIP_RU if hasattr(PHONE_VOIP_RU, '__iter__') else False,
    }

    # Банк по оператору
    if carrier_ru in PHONE_BANK_MAP:
        result["bank"] = PHONE_BANK_MAP[carrier_ru]
        result["possible_banks"].append(PHONE_BANK_MAP[carrier_ru])

    # Проверка на виртуальные номера
    virtual_operators = {
        "7-977": "Tele2",
        "7-999": "Tinkoff Mobile / Tele2 / Danycom",
    }
    prefix = f"7-{def_code}" if phone_clean.startswith("7") else def_code
    if prefix in virtual_operators:
        result["operator_type"] = f"Виртуальный ({virtual_operators[prefix]})"

    result["possible_banks"] = list(set(result["possible_banks"]))
    return result


async def phone_full_enrich(phone_e164: str, carrier_ru: str = "") -> dict:
    """Полное обогащение номера: все источники параллельно."""
    web, social, owner, leak_names = await asyncio.gather(
        phone_web_search(phone_e164),
        phone_social_search(phone_e164),
        phone_owner_enrich(phone_e164, carrier_ru),
        phone_leak_name_search(phone_e164),
    )
    # Собираем все найденные имена в одно место
    all_names = []
    seen_names = set()
    for n in social.get("names", []):
        key = n.get("name", "")
        if key and key not in seen_names:
            seen_names.add(key)
            all_names.append(n)
    for n in leak_names.get("records", []):
        key = n.get("name", "")
        if key and key not in seen_names:
            seen_names.add(key)
            all_names.append({**n, "source": f"leak:{n.get('source', 'unknown')}"})
    for n in web.get("tags", []):
        if n not in seen_names:
            seen_names.add(n)
            all_names.append({"name": n, "source": "web"})

    return {
        "web_mentions": web,
        "social_profiles": social,
        "enrichment": owner,
        "leak_names": leak_names,
        "all_names": all_names,
        "person_found": len(all_names) > 0,
        "primary_name": all_names[0].get("name", "") if all_names else None,
        "primary_source": all_names[0].get("source", "") if all_names else None,
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


# ==================== ПОИСК ТЕЛЕФОНА ПО USERNAME ====================

# Регулярка для поиска телефонов разных стран
PHONE_REGEX = re.compile(
    r'(?:\+?\d{1,3})?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}'
)

TG_PHONE_RU = re.compile(r'(?:\+?7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')

async def username_phone_search(username: str) -> dict:
    """Поиск номера телефона по Telegram username."""
    username = username.strip().lstrip("@")
    result = {"phone_numbers": [], "sources": [], "tg_info": {}}

    async def from_tg_web():
        """Проверка t.me (работает) + парсинг номера из описания."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                r = await c.get(f"https://t.me/{username}", headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "tgme_page_title" in r.text:
                    name_m = re.search(r'<div class="tgme_page_title">(.+?)</div>', r.text, re.DOTALL)
                    if name_m:
                        result["tg_info"]["name"] = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
                    bio_m = re.search(r'<div class="tgme_page_description">(.+?)</div>', r.text, re.DOTALL)
                    if bio_m:
                        bio = re.sub(r'<[^>]+>', '', bio_m.group(1)).strip()
                        result["tg_info"]["bio"] = bio
                        for ph_m in re.finditer(r'(?:\+?7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}', bio):
                            clean = re.sub(r'[\s\-\(\)]', '', ph_m.group(0))
                            result["phone_numbers"].append({"phone": clean, "source": "t.me/bio", "context": "био TG"})
                            result["sources"].append("t.me")
                    if "tgme_page_extra" in r.text:
                        extra_m = re.search(r'<div class="tgme_page_extra">(.+?)</div>', r.text, re.DOTALL)
                        if extra_m:
                            result["tg_info"]["subscribers"] = re.sub(r'<[^>]+>', '', extra_m.group(1)).strip()
        except:
            pass

    async def from_tg_channel_export():
        """Поиск номера в сообщениях публичных TG-каналов."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(f"https://tg.i-c-a.su/json/{username}", headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    data = r.json()
                    posts = data if isinstance(data, list) else (data.get("messages", []) if isinstance(data, dict) else [])
                    for p in posts[:30]:
                        text = p.get("text", p.get("message", ""))
                        if isinstance(text, list):
                            text = " ".join(str(t) if isinstance(t, str) else t.get("text", "") for t in text)
                        if isinstance(text, str):
                            for ph_m in re.finditer(r'(?:\+?7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}', text):
                                clean = re.sub(r'[\s\-\(\)]', '', ph_m.group(0))
                                if clean not in [p["phone"] for p in result["phone_numbers"]]:
                                    result["phone_numbers"].append({"phone": clean, "source": "tg.i-c-a.su", "context": f"сообщение: {text[:80]}"})
                                    result["sources"].append("tg.i-c-a.su")
        except:
            pass

    async def from_leaks():
        """Поиск номера в утечках через leaksearch."""
        try:
            from leak import leak_search
            leak_data = await leak_search(username, "username")
            if leak_data.get("found"):
                for detail in leak_data.get("details", []):
                    for sample in detail.get("sample", []):
                        sample_str = str(sample)
                        for p in TG_PHONE_RU.findall(sample_str):
                            clean = re.sub(r'[\s\-\(\)]', '', p)
                            if clean not in [ph["phone"] for ph in result["phone_numbers"]]:
                                result["phone_numbers"].append({"phone": clean, "source": detail.get("source", "leak"), "context": sample_str[:100]})
                                result["sources"].append(detail.get("source", "leak"))
                        if not result.get("leak_found"):
                            result["leak_found"] = True
                            result["leak_sources"] = leak_data.get("sources", [])
        except:
            pass

    async def from_vk():
        """VK API — поиск по username."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get("https://api.vk.com/method/users.get",
                    params={"user_ids": username, "v": "5.131",
                            "fields": "contacts,connections,phone,screen_name,has_mobile,last_seen,online,sex,bdate,city,country"},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                if r.status_code == 200:
                    for u in r.json().get("response", []):
                        for phone_key in ("mobile_phone", "home_phone"):
                            ph = u.get(phone_key)
                            if ph:
                                clean = re.sub(r'[\s\-\(\)]', '', str(ph))
                                result["phone_numbers"].append({"phone": clean, "source": "VK API", "context": f"{u.get('first_name','')} {u.get('last_name','')}"})
                                result["sources"].append("VK")
                        fn = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                        if fn:
                            result["tg_info"]["vk_name"] = fn
                            result["tg_info"]["vk_url"] = f"https://vk.com/{u.get('screen_name', u.get('id', ''))}"
        except:
            pass

    async def from_google():
        """Google-поиск: username + телефон."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
                r = await c.get("https://www.google.com/search", params={"q": f'"{username}" телефон|phone|+7|+7', "hl": "ru"}, headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    for ph_m in re.finditer(r'(?:\+?7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}', r.text):
                        clean = re.sub(r'[\s\-\(\)]', '', ph_m.group(0))
                        if clean not in [p["phone"] for p in result["phone_numbers"]]:
                            result["phone_numbers"].append({"phone": clean, "source": "Google", "context": "поиск username+phone"})
                            result["sources"].append("Google")
        except:
            pass

    await asyncio.gather(from_tg_web(), from_tg_channel_export(), from_leaks(), from_vk(), from_google())

    result["found"] = len(result["phone_numbers"]) > 0
    return result


# ==================== ПОИСК ПУБЛИЧНЫХ СООБЩЕНИЙ ПО USERNAME ====================

async def username_messages_search(username: str) -> dict:
    """Поиск сообщений пользователя в публичных чатах/каналах/форумах."""
    result = {"messages": [], "sources": []}

    async def from_telegram():
        """Telegram: посты канала/сообщения через tg.i-c-a.su + tgsearch."""
        sources = [
            (f"https://tg.i-c-a.su/json/{username}", "tg.i-c-a.su"),
            (f"https://tg.i-c-a.su/_/json/{username}", "tg.i-c-a.su"),
        ]
        for url, src in sources:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    r = await c.get(url, headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200:
                        data = r.json()
                        posts = []
                        if isinstance(data, list):
                            posts = data[:10]
                        elif isinstance(data, dict) and "messages" in data:
                            posts = data["messages"][:10]
                        for p in posts:
                            if isinstance(p, dict):
                                text = p.get("text", p.get("message", ""))
                                if isinstance(text, list):
                                    text = " ".join(str(t) if isinstance(t, str) else t.get("text", "") for t in text)
                                if text and len(str(text)) > 10:
                                    result["messages"].append({
                                        "source": src,
                                        "text": str(text)[:500],
                                        "date": p.get("date", p.get("time", "")),
                                        "url": f"https://t.me/{username}/{(p.get('id', p.get('post_id', '')))}"
                                    })
                                    if src not in result["sources"]:
                                        result["sources"].append(src)
            except:
                pass
        # Поиск по tg.i-c-a.su search
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://tg.i-c-a.su/json/_search?q={username}&limit=5",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        for item in data[:5]:
                            text = str(item.get("text", item.get("message", "")))[:300]
                            result["messages"].append({
                                "source": "tg.i-c-a.su/search",
                                "text": text,
                                "context": f"поиск по username: {username}"
                            })
                            if "tg.i-c-a.su/search" not in result["sources"]:
                                result["sources"].append("tg.i-c-a.su/search")
        except:
            pass

    async def from_vk_wall():
        """VK: посты со стены пользователя."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    "https://api.vk.com/method/wall.get",
                    params={"domain": username, "count": "5", "v": "5.131",
                            "fields": "text,date,attachments"},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
                )
                if r.status_code == 200:
                    data = r.json()
                    posts = data.get("response", {}).get("items", [])
                    for p in posts:
                        text = p.get("text", "")
                        if text and len(text) > 10:
                            result["messages"].append({
                                "source": "VK",
                                "text": text[:500],
                                "date": p.get("date", ""),
                                "url": f"https://vk.com/{username}?w=wall{p.get('from_id', '')}_{p.get('id', '')}"
                            })
                            if "VK" not in result["sources"]:
                                result["sources"].append("VK")
        except:
            pass

    async def from_reddit():
        """Reddit: комментарии и посты пользователя."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.reddit.com/user/{username}.json?limit=5",
                    headers={"User-Agent": USER_AGENT + " (Reddit OSINT bot)"}
                )
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("data", {}).get("children", [])
                    for item in items[:5]:
                        d = item.get("data", {})
                        text = d.get("title", "") + " " + d.get("body", d.get("selftext", ""))
                        if text.strip() and len(text.strip()) > 10:
                            result["messages"].append({
                                "source": "Reddit",
                                "text": text.strip()[:500],
                                "date": d.get("created_utc", ""),
                                "url": f"https://reddit.com{d.get('permalink', '')}"
                            })
                            if "Reddit" not in result["sources"]:
                                result["sources"].append("Reddit")
        except:
            pass

    async def from_google():
        """Google: поиск упоминаний username в публичном доступе."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.google.com/search?q=%22{username}%22+site:forum+OR+site:chat+OR+site:comment",
                    headers={"User-Agent": USER_AGENT + " (Linux; Android 12)"}
                )
                if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                    for m in re.finditer(r'<span[^>]*class="[^"]*BNeawe[^"]*"[^>]*>([^<]{30,})</span>', r.text):
                        snippet = m.group(1).strip()
                        if username.lower() in snippet.lower() and len(snippet) > 30:
                            result["messages"].append({
                                "source": "Google", "text": snippet[:500],
                                "context": "сниппет поиска"
                            })
                            if "Google" not in result["sources"]:
                                result["sources"].append("Google")
        except:
            pass

    async def from_instagram():
        """Instagram: проверка username через публичный профиль."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.instagram.com/{username}/",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200 and "page isn't available" not in r.text.lower()[:3000]:
                    # Пробуем извлечь описание профиля
                    desc_match = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', r.text)
                    if desc_match:
                        desc = desc_match.group(1)
                        result["messages"].append({
                            "source": "Instagram",
                            "text": f"Профиль: {desc[:500]}",
                            "context": "описание профиля"
                        })
                        if "Instagram" not in result["sources"]:
                            result["sources"].append("Instagram")
        except:
            pass

    async def from_tiktok():
        """TikTok: проверка профиля по username."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://www.tiktok.com/@{username}",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200 and "Couldn't find this account" not in r.text:
                    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', r.text)
                    if desc_match:
                        desc = desc_match.group(1)[:500]
                        result["messages"].append({
                            "source": "TikTok",
                            "text": f"Профиль: {desc}",
                        })
                        if "TikTok" not in result["sources"]:
                            result["sources"].append("TikTok")
        except:
            pass

    async def from_twitter():
        """Twitter/X: профиль пользователя."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(
                    f"https://x.com/{username}",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200 and "This account doesn't exist" not in r.text:
                    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', r.text)
                    if desc_match:
                        desc = desc_match.group(1)[:500]
                        result["messages"].append({
                            "source": "Twitter/X",
                            "text": f"Профиль: {desc}",
                        })
                        if "Twitter/X" not in result["sources"]:
                            result["sources"].append("Twitter/X")
        except:
            pass

    await asyncio.gather(from_telegram(), from_vk_wall(), from_reddit(), from_google(),
                         from_instagram(), from_tiktok(), from_twitter())

    result["found"] = len(result["messages"]) > 0
    return result


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


# ==================== НОВЫЕ API-ИНТЕГРАЦИИ ====================
# Все функции работают без ключей (graceful fallback), но с ключами дают больше данных

async def _safe_api_get(url: str, headers: dict = None, params: dict = None, timeout: float = 10.0) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url, headers=headers or {"User-Agent": USER_AGENT}, params=params)
            return r.json() if r.status_code == 200 else None
    except:
        return None


async def _safe_api_post(url: str, headers: dict = None, json_data: dict = None, timeout: float = 10.0) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.post(url, headers=headers or {"User-Agent": USER_AGENT}, json=json_data)
            return r.json() if r.status_code == 200 else None
    except:
        return None


async def shodan_full_lookup(ip: str) -> dict:
    """Shodan — полные данные по IP: порты, сервисы, уязвимости, баннеры."""
    from config import SHODAN_API_KEY
    result = {}
    if SHODAN_API_KEY:
        data = await _safe_api_get(
            f"https://api.shodan.io/shodan/host/{ip}?key={SHODAN_API_KEY}",
            timeout=10.0
        )
        if data:
            ports = data.get("ports", [])
            services = []
            for item in data.get("data", []):
                services.append({
                    "port": item.get("port"),
                    "transport": item.get("transport", "tcp"),
                    "product": item.get("product", ""),
                    "version": item.get("version", ""),
                    "banner": (item.get("data", "") or "")[:200],
                })
            result["shodan"] = {
                "ports": ports,
                "services": services[:15],
                "hostnames": data.get("hostnames", []),
                "os": data.get("os", ""),
                "vulns": data.get("vulns", []),
                "country": data.get("country_name", ""),
                "city": data.get("city", ""),
                "org": data.get("org", ""),
                "isp": data.get("isp", ""),
            }
    # Fallback — InternetDB (без ключа)
    data = await _safe_api_get(f"https://internetdb.shodan.io/{ip}", timeout=8.0)
    if data:
        result["internetdb"] = {
            "ports": data.get("ports", []),
            "hostnames": data.get("hostnames", []),
            "cpes": data.get("cpes", []),
            "tags": data.get("tags", []),
        }
    return result


async def abuseipdb_check(ip: str) -> dict:
    """AbuseIPDB — репутация IP (спам/атаки/abuse)."""
    from config import ABUSEIPDB_API_KEY
    if not ABUSEIPDB_API_KEY:
        return {}
    data = await _safe_api_get(
        "https://api.abuseipdb.com/api/v2/check",
        headers={"Key": ABUSEIPDB_API_KEY, "Accept": "application/json"},
        params={"ipAddress": ip, "maxAgeInDays": "90", "verbose": ""},
        timeout=8.0
    )
    if data and "data" in data:
        d = data["data"]
        return {
            "abuse_score": d.get("abuseConfidenceScore", 0),
            "total_reports": d.get("totalReports", 0),
            "last_reported": d.get("lastReportedAt", ""),
            "country": d.get("countryCode", ""),
            "isp": d.get("isp", ""),
            "domain": d.get("domain", ""),
            "usage_type": d.get("usageType", ""),
        }
    return {}


async def ipinfo_lookup(ip: str) -> dict:
    """IPinfo — дополнительная IP-геолокация + провайдер."""
    from config import IPINFO_API_KEY
    token = f"?token={IPINFO_API_KEY}" if IPINFO_API_KEY else ""
    data = await _safe_api_get(f"https://ipinfo.io/{ip}{token}", timeout=8.0)
    if data:
        return {
            "city": data.get("city", ""),
            "region": data.get("region", ""),
            "country": data.get("country", ""),
            "loc": data.get("loc", ""),
            "org": data.get("org", ""),
            "postal": data.get("postal", ""),
            "timezone": data.get("timezone", ""),
            "asn": data.get("asn", {}).get("asn", "") if isinstance(data.get("asn"), dict) else data.get("asn", ""),
            "asn_name": data.get("asn", {}).get("name", "") if isinstance(data.get("asn"), dict) else "",
            "company": data.get("company", {}).get("name", "") if isinstance(data.get("company"), dict) else "",
            "privacy": data.get("privacy", {}),
            "domains": data.get("domains", {}).get("domains", [])[:5] if isinstance(data.get("domains"), dict) else [],
        }
    return {}


async def ssl_analyze(domain: str) -> dict:
    """SSL Labs — анализ SSL-сертификата."""
    data = await _safe_api_get(
        f"https://api.ssllabs.com/api/v3/analyze?host={domain}&maxAge=24",
        timeout=15.0
    )
    if data and data.get("status") != "ERROR" and data.get("endpoints"):
        ep = data.get("endpoints", [{}])[0]
        grade = ep.get("grade", "N/A")
        details = {}
        if ep.get("details"):
            det = ep["details"]
            cert = det.get("cert", {})
            details = {
                "protocol": det.get("protocol", ""),
                "cert_subject": cert.get("subject", ""),
                "cert_issuer": cert.get("issuer", ""),
                "cert_valid_from": cert.get("notBefore", ""),
                "cert_valid_to": cert.get("notAfter", ""),
                "cert_commonName": cert.get("commonName", []),
                "cert_altNames": cert.get("altNames", [])[:10],
                "has_sni": det.get("sniRequired", False),
                "dh_bits": det.get("dhBits", 0),
            }
        return {"grade": grade, "details": details}
    return {}


async def securitytrails_domain(domain: str) -> dict:
    """SecurityTrails — DNS-история, поддомены, WHOIS."""
    from config import SECURITYTRAILS_API_KEY
    result = {}
    api_key = SECURITYTRAILS_API_KEY
    if not api_key:
        return result
    headers = {"APIKEY": api_key, "Accept": "application/json"}

    subdomains_data = await _safe_api_get(
        f"https://api.securitytrails.com/v1/domain/{domain}/subdomains",
        headers=headers, timeout=10.0
    )
    if subdomains_data and "subdomains" in subdomains_data:
        subs = subdomains_data["subdomains"][:50]
        result["subdomains"] = [f"{s}.{domain}" for s in subs]

    dns_history = await _safe_api_get(
        f"https://api.securitytrails.com/v1/history/{domain}/dns/a",
        headers=headers, timeout=10.0
    )
    if dns_history and "records" in dns_history:
        records = dns_history["records"][:10]
        result["dns_history"] = [
            {"ip": r.get("values", [{}])[0].get("ip", ""), "first_seen": r.get("first_seen", "")}
            for r in records if r.get("values")
        ]

    whois_data = await _safe_api_get(
        f"https://api.securitytrails.com/v1/domain/{domain}/whois",
        headers=headers, timeout=10.0
    )
    if whois_data:
        result["whois"] = {
            "registrar": whois_data.get("registrarName", ""),
            "created": whois_data.get("createdDate", ""),
            "expires": whois_data.get("expiresDate", ""),
            "emails": whois_data.get("contactEmail", ""),
        }
    return result


async def virustotal_lookup(target: str, target_type: str = "domain") -> dict:
    """VirusTotal — репутация домена/IP/IP-адреса."""
    from config import VIRUSTOTAL_API_KEY
    if not VIRUSTOTAL_API_KEY:
        return {}
    url_map = {
        "domain": f"https://www.virustotal.com/api/v3/domains/{target}",
        "ip": f"https://www.virustotal.com/api/v3/ip_addresses/{target}",
        "url": f"https://www.virustotal.com/api/v3/urls/{target}",
    }
    url = url_map.get(target_type)
    if not url:
        return {}
    data = await _safe_api_get(
        url, headers={"x-apikey": VIRUSTOTAL_API_KEY}, timeout=10.0
    )
    if data and "data" in data:
        attrs = data["data"].get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        cats = attrs.get("categories", {})
        return {
            "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0),
            "harmless": stats.get("harmless", 0),
            "undetected": stats.get("undetected", 0),
            "total_engines": sum(stats.values()) if stats else 0,
            "categories": list(cats.values())[:5] if cats else [],
            "reputation": attrs.get("reputation", 0),
        }
    return {}


async def hunter_email(email: str) -> dict:
    """Hunter.io — верификация email + метаданные."""
    from config import HUNTER_API_KEY
    if not HUNTER_API_KEY:
        return {}
    data = await _safe_api_get(
        "https://api.hunter.io/v2/email-verifier",
        params={"email": email, "api_key": HUNTER_API_KEY},
        timeout=8.0
    )
    if data and "data" in data:
        d = data["data"]
        return {
            "status": d.get("status", "unknown"),
            "result": d.get("result", "unknown"),
            "score": d.get("score", 0),
            "regexp": d.get("regexp", False),
            "gibberish": d.get("gibberish", False),
            "disposable": d.get("disposable", False),
            "webmail": d.get("webmail", False),
            "mx_records": d.get("mx_records", False),
            "smtp_server": d.get("smtp_server", False),
            "smtp_check": d.get("smtp_check", False),
            "accept_all": d.get("accept_all", False),
            "block": d.get("block", False),
            "sources": d.get("sources", [])[:3],
        }
    return {}


async def breach_check_email(email: str) -> dict:
    """Have I Been Pwned + LeakCheck — проверка утечек email."""
    from config import VIRUSTOTAL_API_KEY
    result = {"hibp": [], "sources": []}

    # HIBP v3 (без ключа, но с User-Agent)
    import hashlib
    h = hashlib.sha1(email.encode()).hexdigest().upper()
    prefix, suffix = h[:5], h[5:]
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"User-Agent": USER_AGENT, "Add-Padding": "true"},
            )
            if r.status_code == 200:
                hashes = [line.split(":") for line in r.text.strip().split("\n")]
                for hs, count in hashes:
                    if hs == suffix:
                        result["hibp"].append({"count": int(count)})
                        result["sources"].append("Have I Been Pwned")
                        break
    except:
        pass

    # IntelX / leakcheck via leak.py
    try:
        from leak import leak_search
        leak_data = await leak_search(email, "email")
        if leak_data.get("found"):
            result["sources"].extend(leak_data.get("sources", []))
            result["leak_details"] = leak_data.get("details", [])
    except:
        pass

    return result


async def tech_detect(url: str) -> dict:
    """Определение технологий сайта (Wappalyzer-like через публичный API)."""
    result = {}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            r = await c.get(f"https://{url}", headers={"User-Agent": USER_AGENT})
            headers = dict(r.headers)
            html = r.text[:50000]

        tech = []

        # Сервер
        server = headers.get("Server", "")
        if server and server != "N/A":
            tech.append({"name": server, "category": "Веб-сервер"})

        # CMS / фреймворки
        cms_checks = {
            "WordPress": ['wp-content', 'wp-includes', 'wordpress'],
            "Joomla": ['joomla', 'com_content'],
            "Drupal": ['drupal', 'Drupal.settings'],
            "Bitrix": ['bitrix', 'bx-'],
            "Tilda": ['tilda', 'tilda.ws'],
            "Wix": ['wix', 'X-Wix'],
            "Shopify": ['shopify', 'myshopify'],
            "OpenCart": ['opencart', 'OC_CART'],
            "PrestaShop": ['prestashop', 'ps_'],
            "Laravel": ['laravel', 'LARAVEL'],
            "Django": ['django', 'csrftoken'],
            "Flask": ['flask', 'flask-framework'],
            "Express": ['express', 'connect.sid'],
            "Next.js": ['next.js', '__NEXT_DATA__'],
            "Nuxt.js": ['nuxt', '__NUXT__'],
        }
        for name, needles in cms_checks.items():
            for needle in needles:
                if needle.lower() in html.lower() or needle.lower() in str(headers).lower():
                    tech.append({"name": name, "category": "CMS/Фреймворк"})
                    break

        # Аналитика / CDN
        header_tech = {
            "cf-ray": {"name": "Cloudflare", "cat": "CDN"},
            "x-amz-cf-id": {"name": "AWS CloudFront", "cat": "CDN"},
            "x-served-by": {"name": "Nginx", "cat": "Веб-сервер"},
            "x-powered-by": {"name": "PHP", "cat": "Язык"},
            "x-aspnet-version": {"name": "ASP.NET", "cat": "Фреймворк"},
            "x-generator": {"name": "CMS", "cat": "CMS"},
        }
        for hdr, info in header_tech.items():
            if hdr in headers:
                val = headers[hdr]
                if not any(t["name"] == info["name"] for t in tech):
                    tech.append({"name": f"{info['name']} ({val})" if val != info['name'] else info['name'], "category": info["cat"]})

        result["tech"] = tech
        result["headers"] = dict(list(headers.items())[:15])
    except:
        pass
    return result


async def dns_enum(domain: str) -> dict:
    """DNS-перечисление: все типы записей + DNSSEC."""
    result = {"records": {}}
    for rtype in ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME", "PTR", "SRV", "CAA", "NAPTR", "DS", "DNSKEY"]:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=5)
            vals = [str(r) for r in answers]
            if vals:
                result["records"][rtype] = vals
        except:
            pass
    result["total_records"] = sum(len(v) for v in result["records"].values())
    return result


async def enhanced_port_scan(ip: str) -> dict:
    """Сканирование портов через Shodan InternetDB."""
    data = await _safe_api_get(f"https://internetdb.shodan.io/{ip}", timeout=8.0)
    if data and data.get("ports"):
        ports = data["ports"]
        return {
            "ports": sorted(ports),
            "count": len(ports),
            "total": len(ports),
            "hostnames": data.get("hostnames", []),
        }
    return {}


BASE_GN = re.compile(r'@?\w{3,32}$')


# ==================== ХАКЕРСКИЙ СКАН НОМЕРА (KALI-STYLE) ====================
# Модули: WhatsApp, Viber, Telegram, соцсети, утечки, Google, спам, риск-скоринг

async def phone_scan(phone: str) -> dict:
    """Полный хакерский скан номера телефона (PhoneInfoga-style)."""
    clean = re.sub(r'[^\d+]', '', phone)
    result = {
        "input": phone,
        "clean": clean,
        "whatsapp": False,
        "viber": False,
        "telegram": False,
        "signal": False,
        "social": [],
        "spam_sites": [],
        "leaks": [],
        "google_mentions": [],
        "carrier": "",
        "risk_score": 0,
        "risk_label": "🟢 Безопасный",
        "breach_count": 0,
    }

    async def _check_whatsapp():
        """WhatsApp — проверка регистрации номера через api.whatsapp.com."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                num = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://api.whatsapp.com/send/?phone={num}", headers={"User-Agent": USER_AGENT})
                text = r.text.lower()
                if "continue to chat" in text or "open whatsapp" in text or "send" in text[:500]:
                    result["whatsapp"] = True
                elif "not registered" in text or "invalid" in text or "doesn't have" in text:
                    result["whatsapp"] = False
                else:
                    result["whatsapp"] = r.status_code in (200, 302) and "send" in r.url.lower()
        except:
            pass

    async def _check_viber():
        """Viber — проверка регистрации номера через pa.tl/viber."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                num = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://pa.tl/viber/{num}", headers={"User-Agent": USER_AGENT})
                if r.status_code < 400 and "invalid" not in r.text.lower()[:1000]:
                    result["viber"] = True
        except:
            pass
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                r = await c.get(f"https://chats.viber.com/{num}", headers={"User-Agent": USER_AGENT})
                if r.status_code < 400 and "Invalid phone number" not in r.text:
                    result["viber"] = True
        except:
            pass

    async def _check_telegram():
        """Telegram — проверка регистрации номера через t.me/+."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                num = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://t.me/+{num}", headers={"User-Agent": USER_AGENT})
                result["telegram"] = r.status_code == 200 and "tgme_page" in r.text
        except:
            pass

    async def _check_signal():
        """Signal — проверка регистрации (через signal.me)."""
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                num = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://signal.me/#p/{num}", headers={"User-Agent": USER_AGENT})
                result["signal"] = r.status_code == 200
        except:
            pass

    async def _check_social():
        """Поиск привязок к соцсетям (VK, OK, Facebook по номеру)."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                # VK поиск по номеру
                r = await c.get("https://api.vk.com/method/users.search",
                    params={"q": raw, "count": 3, "v": "5.131",
                            "fields": "photo_50,sex,bdate,city,country,home_town,status,last_seen,online,has_photo,contacts"},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                if r.status_code == 200:
                    for u in r.json().get("response", {}).get("items", []):
                        result["social"].append({
                            "platform": "VK",
                            "name": f"{u.get('first_name','')} {u.get('last_name','')}",
                            "url": f"https://vk.com/id{u.get('id')}",
                            "city": u.get("city", {}).get("title", "") if isinstance(u.get("city"), dict) else "",
                            "has_phone": u.get("has_mobile", False) or bool(u.get("mobile_phone")),
                        })
        except:
            pass
        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                # OK (Одноклассники) — открытая ссылка с номером
                r = await c.get(f"https://ok.ru/search?st.query={clean}&st.g=0", headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "loginLayer" not in r.text[:5000]:
                    result["social"].append({"platform": "OK", "note": "найден в поиске OK"})
        except:
            pass

    async def _check_spam():
        """Проверка во всех спам-базах: 10+ источников."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                spam_sources = [
                    (f"https://callfilter.ru/{raw}/", "callfilter.ru", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://who-calls.ru/{raw}", "who-calls.ru", lambda t: "не найдена" not in t.lower()[:2000] and "404" not in t[:2000]),
                    (f"https://ktozvonil.com/phone/{raw}", "ktozvonil.com", lambda t: "не найдено" not in t.lower()[:2000]),
                    (f"https://spravka.net/phone/{raw}/", "spravka.net", lambda t: "не найден" not in t.lower()[:2000] and "404" not in t[:2000]),
                    (f"https://abonent.me/{raw}", "abonent.me", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://phonbook.net/{raw}", "phonbook.net", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://telinfo.me/{raw}", "telinfo.me", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://www.phonebook.ru/phone/{raw}", "phonebook.ru", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://1000-nomerov.ru/phone/{raw}", "1000-nomerov.ru", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://everyon.me/phone/{raw}", "everyon.me", lambda t: "не найден" not in t.lower()[:2000]),
                    (f"https://spamhaus.org/query/phone/{raw}", "spamhaus", lambda t: "listed" in t.lower()),
                    (f"https://www.avito.ru/items/phone/{raw}", "avito.ru", lambda t: "найдено" in t.lower()[:2000]),
                ]
                for url, name, check in spam_sources:
                    try:
                        r = await c.get(url, headers={"User-Agent": USER_AGENT})
                        if r.status_code == 200 and check(r.text):
                            result["spam_sites"].append(name)
                            if name == "callfilter.ru":
                                m = re.search(r'рейтинг[^<]*<[^>]*>([^<]+)', r.text[:5000], re.I)
                                if m:
                                    result["spam_note"] = m.group(1).strip()
                    except:
                        pass
        except:
            pass

    async def _check_breaches():
        """Поиск номера в утечках через leaksearch."""
        try:
            from leak import leak_search
            leak_data = await leak_search(clean, "phone")
            if leak_data.get("found"):
                for src in leak_data.get("sources", []):
                    result["leaks"].append(src)
                result["breach_count"] = len(leak_data.get("sources", []))
        except:
            pass

    async def _check_google():
        """Google-футпринт: поиск номера в разных форматах."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
                raw = re.sub(r'[^\d]', '', clean)
                for fmt in (raw, raw[:1] + " (" + raw[1:4] + ") " + raw[4:7] + "-" + raw[7:9] + "-" + raw[9:]):
                    r = await c.get("https://www.google.com/search",
                        params={"q": fmt, "hl": "ru", "num": 5},
                        headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                        snippets = re.findall(r'<span[^>]*class="[^"]*BNeawe[^"]*"[^>]*>([^<]{30,})</span>', r.text)
                        for s in snippets[:3]:
                            if raw in s or fmt in s:
                                result["google_mentions"].append(s[:200])
        except:
            pass

    async def _check_carrier():
        """Определение оператора + MNP."""
        try:
            from phonenumbers import carrier as ph_carrier
            import phonenumbers
            try:
                pn = phonenumbers.parse(clean, "RU")
                result["carrier"] = ph_carrier.name_for_number(pn, "ru") or ph_carrier.name_for_number(pn, "en") or ""
            except:
                pass
        except:
            pass

    async def _check_yandex():
        """Yandex-футпринт: поиск номера в Яндексе."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get("https://yandex.ru/search/",
                    params={"text": raw, "lr": 213},
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                    snippets = re.findall(r'<span[^>]*class="[^"]*[Oo]rganic[^"]*"[^>]*>([^<]{30,})</span>', r.text)
                    for s in snippets[:3]:
                        if raw in s:
                            result["google_mentions"].append(f"Яндекс: {s[:200]}")
        except:
            pass

    async def _check_email_by_phone():
        """Поиск email'ов, привязанных к номеру, через утечки."""
        try:
            from leak import leak_search
            leak_data = await leak_search(clean, "phone")
            if leak_data.get("found"):
                emails_found = set()
                for src in leak_data.get("details", []):
                    for s in src.get("sample", []):
                        s_str = str(s)
                        if "@" in s_str:
                            m = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', s_str)
                            if m:
                                emails_found.add(m.group())
                if emails_found:
                    result["emails"] = list(emails_found)[:5]
        except:
            pass

    async def _check_getcontact():
        """GetContact — попытка проверить теги номера."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://getcontact.com/phone/{raw}",
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "not found" not in r.text.lower()[:2000]:
                    # Пробуем найти теги
                    tags = re.findall(r'class="[^"]*tag[^"]*"[^>]*>([^<]+)<', r.text)
                    if tags:
                        result["gc_tags"] = [t.strip() for t in tags[:5] if t.strip()]
        except:
            pass

    async def _check_syncme():
        """Sync.me — проверка регистрации."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://sync.me/{raw}",
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "user not found" not in r.text.lower()[:2000]:
                    name_m = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text)
                    if name_m:
                        result["syncme_name"] = name_m.group(1).strip()
        except:
            pass

    async def _check_insta_by_phone():
        """Instagram — поиск по номеру через login/identifiers."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                # Попытка поиска через публичные endpoints
                r = await c.get(f"https://www.instagram.com/accounts/account_recovery_send_ajax/phone/{raw}",
                    headers={"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"})
                # Этот метод часто блокируется, но попробуем
        except:
            pass

    async def _check_tg_phone_group():
        """Telegram — поиск номера в публичных группах (через Google dork)."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get("https://www.google.com/search",
                    params={"q": f'"{raw}" site:t.me', "hl": "ru", "num": 5},
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                    links = re.findall(r'href="https://t\.me/[^"]+"', r.text)
                    if links:
                        result["tg_links"] = [l.replace('href="','').replace('"','') for l in links[:3]]
                        result["social"].append({"platform": "TG Group", "url": result["tg_links"][0]})
        except:
            pass

    async def _check_mailru_phone():
        """Mail.ru — поиск номера в открытом профиле."""
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://e.mail.ru/cgi-bin/phone_search?phone={raw}",
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "user found" in r.text.lower():
                    result["social"].append({"platform": "Mail.ru"})
        except:
            pass

    async def _check_facebook_phone():
        """Facebook — поиск по номеру (через m.facebook.com)."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                raw = re.sub(r'[^\d]', '', clean)
                r = await c.get(f"https://m.facebook.com/search/top/?q={raw}",
                    headers={"User-Agent": USER_AGENT})
                if r.status_code == 200 and "search" in r.url.path:
                    if "people" in r.text[:10000] or "profile" in r.text[:10000]:
                        result["social"].append({"platform": "Facebook", "note": "найден по номеру"})
        except:
            pass

    async def _check_numerous_dbs():
        """Проверка в дополнительных российских базах номеров."""
        raw = re.sub(r'[^\d]', '', clean)
        extra_sources = [
            (f"https://nomerorg.com/phone/{raw}", "nomerorg.com"),
            (f"https://phones-info.ru/{raw}", "phones-info.ru"),
            (f"https://phone-number.ru/{raw}", "phone-number.ru"),
        ]
        for url, name in extra_sources:
            try:
                async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                    r = await c.get(url, headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200 and "не найден" not in r.text.lower()[:2000] and "404" not in r.text[:2000]:
                        result["spam_sites"].append(name)
            except:
                pass

    await asyncio.gather(
        _check_whatsapp(), _check_viber(), _check_telegram(), _check_signal(),
        _check_social(), _check_spam(), _check_breaches(), _check_google(),
        _check_carrier(), _check_yandex(), _check_email_by_phone(),
        _check_getcontact(), _check_syncme(), _check_insta_by_phone(),
        _check_tg_phone_group(), _check_mailru_phone(), _check_facebook_phone(),
        _check_numerous_dbs()
    )

    # Расчёт риска
    risk = 0
    if result["whatsapp"]: risk += 10
    if result["viber"]: risk += 10
    if result["telegram"]: risk += 15
    if result["signal"]: risk += 5
    if result["spam_sites"]: risk += 20
    if result["breach_count"] > 0:
        risk += min(result["breach_count"] * 10, 40)
    if result["social"]:
        risk += min(len(result["social"]) * 5, 15)
    risk = min(risk, 100)

    result["risk_score"] = risk
    if risk >= 70:
        result["risk_label"] = "🔴 Высокий риск"
    elif risk >= 40:
        result["risk_label"] = "🟡 Средний риск"
    elif risk >= 15:
        result["risk_label"] = "🔵 Низкий риск"
    else:
        result["risk_label"] = "🟢 Безопасный"

    return result


CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


async def phone_card_search(phone_e164: str) -> dict:
    """Поиск банковских карт, привязанных к номеру телефона (через утечки и веб)."""
    phone_clean = phone_e164.lstrip("+")
    phone_pretty = f"+7 ({phone_clean[1:4]}) {phone_clean[4:7]}-{phone_clean[7:9]}-{phone_clean[9:]}"
    result = {"found": False, "cards": [], "card_count": 0, "sources": []}

    async def search_leaks():
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                r = await c.get(
                    f"https://leakcheck.io/api/public?check={phone_clean}&type=phone",
                    headers={"User-Agent": USER_AGENT}
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success") and data.get("data"):
                        lines = data["data"]
                        card_lines = [str(s) for s in lines if len(re.sub(r"\D", "", str(s))) >= 13]
                        if card_lines:
                            for cl in card_lines[:10]:
                                clean_num = re.sub(r"\D", "", cl)
                                if 13 <= len(clean_num) <= 19:
                                    result["cards"].append({
                                        "number": cl[:50],
                                        "source": "LeakCheck",
                                        "bin": clean_num[:8],
                                    })
                            result["found"] = True
                            result["sources"].append("LeakCheck")
                            result["card_count"] = len(card_lines)
        except:
            pass

    async def search_google():
        dorks = [
            f'"{phone_clean}" карта OR банковская OR visa OR mastercard OR "номер карты"',
            f'"{phone_clean}" "банковская карта" OR "дебетовая" OR "кредитная"',
            f'"{phone_clean}" card OR "credit card" OR visa OR mastercard',
            f'"{phone_pretty}" карта OR банк',
        ]
        seen = set()
        for dork in dorks:
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                    r = await c.get(
                        f"https://www.google.com/search?q={dork.replace(' ', '+')}",
                        headers={"User-Agent": USER_AGENT + " (Linux; Android 12)"}
                    )
                    if r.status_code == 200 and "captcha" not in r.text.lower()[:3000]:
                        found_cards = CARD_REGEX.findall(r.text)
                        for fc in found_cards:
                            clean_fc = re.sub(r"[ -]", "", fc)
                            if 13 <= len(clean_fc) <= 19 and clean_fc not in seen:
                                seen.add(clean_fc)
                                result["cards"].append({
                                    "number": clean_fc[:8] + "*" * (len(clean_fc) - 8),
                                    "source": "Google",
                                    "bin": clean_fc[:8],
                                })
                                result["found"] = True
                        if found_cards:
                            result["sources"].append("Google")
            except:
                pass

    async def search_spam_dbs():
        spam_sites = [
            f"https://who-calls.ru/{phone_clean}",
            f"https://callfilter.ru/{phone_clean}/",
            f"https://ktozvonil.com/phone/{phone_clean}",
        ]
        for url in spam_sites:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    r = await c.get(url, headers={"User-Agent": USER_AGENT})
                    if r.status_code == 200:
                        found = CARD_REGEX.findall(r.text)
                        for fc in found:
                            clean_fc = re.sub(r"[ -]", "", fc)
                            if 13 <= len(clean_fc) <= 19:
                                result["cards"].append({
                                    "number": clean_fc[:8] + "*" * (len(clean_fc) - 8),
                                    "source": "spam-site",
                                    "bin": clean_fc[:8],
                                })
                                result["found"] = True
            except:
                pass

    await asyncio.gather(search_leaks(), search_google(), search_spam_dbs())

    # Дедупликация карт
    seen_bins = set()
    unique_cards = []
    for card in result["cards"]:
        if card["bin"] not in seen_bins:
            seen_bins.add(card["bin"])
            unique_cards.append(card)
    result["cards"] = unique_cards
    result["card_count"] = len(unique_cards)

    # BIN lookup для каждой найденной карты
    if result["cards"]:
        bin_tasks = [card_lookup(c["bin"]) for c in result["cards"]]
        bin_results = await asyncio.gather(*bin_tasks, return_exceptions=True)
        for i, br in enumerate(bin_results):
            if i < len(result["cards"]) and isinstance(br, dict) and "error" not in br:
                result["cards"][i]["bin_info"] = br

    return result


# ==================== WIFI / BSSID / NETWORK ANALYSIS ====================

WIFI_OUI_URL = "https://api.macvendors.com/{}"
WIFI_BSSID_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
WIFI_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# Известные SSID по умолчанию для популярных роутеров
KNOWN_DEFAULT_SSIDS = {
    "TP-Link": ["TP-LINK", "TP-Link", "TP-Link_", "TP-LINK_"],
    "D-Link": ["D-Link", "D-LINK", "dlink", "DIR-", "DES-"],
    "ASUS": ["ASUS", "ASUS_", "ASUS-"],
    "Xiaomi": ["Xiaomi", "MIWIFI", "Redmi"],
    "Huawei": ["Huawei", "HUAWEI", "HUAWEI-", "Huawei-"],
    "ZTE": ["ZTE", "ZTE_", "ZTE-"],
    "MikroTik": ["MikroTik", "MikroTik-"],
    "Ubiquiti": ["Ubiquiti", "UBNT", "UniFi"],
    "Netgear": ["NETGEAR", "Netgear", "NETGEAR-"],
    "Linksys": ["Linksys", "LINKSYS"],
    "Tenda": ["Tenda", "TENDA"],
    "Mercusys": ["Mercusys", "MERCUSYS"],
    "Keenetic": ["Keenetic", "KEENETIC"],
    "Apple": ["Apple", "Apple-"],
    "Google": ["Google", "Google-", "Google Fiber"],
    "Starlink": ["Starlink", "STARLINK"],
}


async def wifi_analyze(data: str) -> dict:
    """Анализ Wi-Fi сети: BSSID (MAC), SSID, или IP-адрес точки."""
    clean = data.strip()
    result = {
        "input": clean,
        "type": None,
        "bssid": None,
        "mac_vendor": None,
        "ssid": None,
        "ssid_length": None,
        "mac_prefix": None,
        "ip_data": None,
        "analysis": [],
        "security_notes": [],
    }

    # --- 1) IP-адрес ---
    if WIFI_IP_RE.match(clean):
        try:
            ipaddress.ip_address(clean)
            result["type"] = "ip"
            # используем ip-api.com как в ip_lookup
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
                r = await c.get(
                    f"http://ip-api.com/json/{clean}?fields=status,message,country,regionName,city,zip,lat,lon,isp,org,as,asname,timezone,query,mobile,proxy,hosting",
                    headers={"User-Agent": USER_AGENT},
                )
                ip_data = r.json()
            if ip_data.get("status") != "fail":
                result["ip_data"] = {
                    "ip": ip_data.get("query", clean),
                    "country": ip_data.get("country", ""),
                    "region": ip_data.get("regionName", ""),
                    "city": ip_data.get("city", ""),
                    "isp": ip_data.get("isp", ""),
                    "org": ip_data.get("org", ""),
                    "asn": ip_data.get("as", ""),
                    "as_name": ip_data.get("asname", ""),
                    "timezone": ip_data.get("timezone", ""),
                    "mobile": ip_data.get("mobile", False),
                    "proxy": ip_data.get("proxy", False),
                    "hosting": ip_data.get("hosting", False),
                }
                d = result["ip_data"]
                result["analysis"].append(f"🌍 Страна: {d['country']}, {d['city']} ({d['region']})")
                result["analysis"].append(f"🏢 Провайдер: {d['isp']}")
                if d["org"] and d["org"] != d["isp"]:
                    result["analysis"].append(f"🏛 Организация: {d['org']}")
                result["analysis"].append(f"🔗 ASN: {d['asn']} ({d['as_name']})")
                result["analysis"].append(f"🕐 Часовой пояс: {d['timezone']}")
                if d["mobile"]:
                    result["analysis"].append("📱 IP принадлежит мобильному оператору — вероятно LTE/3G-роутер")
                if d["proxy"]:
                    result["security_notes"].append("⚠️ IP определяется как VPN/прокси — возможно скрытие местоположения")
                if d["hosting"]:
                    result["security_notes"].append("⚠️ IP принадлежит хостинг-провайдеру — возможен облачный роутер/VPS")
            else:
                result["analysis"].append(f"❌ IP не найден в базе")
        except Exception as e:
            result["analysis"].append(f"❌ Ошибка IP-запроса: {e}")
        return result

    # --- 2) BSSID (MAC-адрес точки доступа) ---
    if WIFI_BSSID_RE.match(clean):
        result["type"] = "bssid"
        result["bssid"] = clean.upper()
        result["mac_prefix"] = clean[:8].upper().replace(":", "-")
        # OUI lookup
        try:
            url = WIFI_OUI_URL.format(result["mac_prefix"])
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200:
                    vendor = resp.text.strip()
                    result["mac_vendor"] = vendor
                    result["analysis"].append(f"🏭 Производитель оборудования: {vendor}")
                elif resp.status_code == 404:
                    result["analysis"].append("🏭 Производитель не найден в публичной базе OUI")
                else:
                    result["analysis"].append(f"🏭 Ошибка OUI lookup (HTTP {resp.status_code})")
        except Exception as e:
            result["analysis"].append(f"🏭 Ошибка OUI запроса: {e}")

        # Анализ MAC-адреса
        first_byte = int(clean[:2], 16)
        second_byte = int(clean[3:5], 16) if ":" in clean else int(clean[2:4], 16)

        # Unicast / Multicast
        if first_byte & 1:
            result["security_notes"].append("⚠️ Multicast MAC — некорректный BSSID точки доступа")
        else:
            result["analysis"].append("✅ Unicast MAC — корректный индивидуальный адрес")

        # Locally Administered / Globally Unique
        if first_byte & 2:
            result["security_notes"].append("⚠️ Locally Administered MAC — возможно подмена MAC-адреса (spoofing)")
        else:
            result["analysis"].append("✅ Globally Unique MAC — официально зарегистрированный префикс")

        # OUI анализ
        if result["mac_vendor"]:
            vendor_lower = result["mac_vendor"].lower()
            obsolete = ["cisco", "3com", "nortel", "alcatel", "siemens", "fujitsu", "d-link", "2wire", "aztech"]
            for obs in obsolete:
                if obs in vendor_lower:
                    result["security_notes"].append(
                        f"⚠️ Производитель '{result['mac_vendor']}' — возможно устаревшее оборудование (риски безопасности)"
                    )
                    break
            known_ap = ["aruba", "ruckus", "ubiquiti", "mikrotik", "cisco", "hp", "huawei", "ruckus", "meraki"]
            for ap in known_ap:
                if ap in vendor_lower:
                    result["analysis"].append(f"📡 Производитель часто используется в точках доступа корпоративного уровня")

        result["analysis"].append("┃ Каждый BSSID уникален для конкретной точки доступа")
        result["analysis"].append("┃ Последние 3 октета — уникальный идентификатор устройства")

        return result

    # --- 3) SSID (имя сети) ---
    result["type"] = "ssid"
    result["ssid"] = clean
    result["ssid_length"] = len(clean)

    # Проверка на дефолтные SSID
    matched_vendor = None
    for vendor, patterns in KNOWN_DEFAULT_SSIDS.items():
        for pat in patterns:
            if pat.lower() in clean.lower():
                matched_vendor = vendor
                result["analysis"].append(f"🏭 SSID похож на стандартный для <b>{vendor}</b>")
                result["security_notes"].append(f"⚠️ Стандартный SSID {vendor}. Рекомендуется сменить имя сети для безопасности")
                break
        if matched_vendor:
            break
    if not matched_vendor:
        result["analysis"].append("✅ SSID не похож на стандартный — вероятно, имя изменено вручную")

    # Оценка безопасности SSID
    ssid_lower = clean.lower()
    if "free" in ssid_lower or "wi-fi" in ssid_lower or "wifi" in ssid_lower or "guest" in ssid_lower:
        result["security_notes"].append("⚠️ SSID содержит признаки публичной/гостевой сети (риск перехвата трафика)")
    if "fbi" in ssid_lower or "police" in ssid_lower or "gov" in ssid_lower or "admin" in ssid_lower:
        result["security_notes"].append("⚠️ SSID может быть ложным/фишинговым (социальная инженерия)")
    if "virus" in ssid_lower or "malware" in ssid_lower or "hack" in ssid_lower:
        result["security_notes"].append("⚠️ SSID содержит подозрительные слова — возможна вредоносная точка")
    if "5g" in ssid_lower or "5ghz" in ssid_lower:
        result["analysis"].append("📡 Сеть работает на частоте 5 ГГц (высокая скорость, меньше помех)")
    if "2.4" in ssid_lower or "2g" in ssid_lower:
        result["analysis"].append("📡 Сеть работает на частоте 2.4 ГГц (больше дальность, больше помех)")
    if "mesh" in ssid_lower:
        result["analysis"].append("🕸 SSID содержит 'mesh' — возможна Mesh-сеть (несколько точек доступа)")
    if "iot" in ssid_lower or "smart" in ssid_lower or "home" in ssid_lower:
        result["analysis"].append("🏠 SSID похож на сеть умного дома/IoT-устройств")

    # Длина SSID
    if result["ssid_length"] < 3:
        result["security_notes"].append("⚠️ Слишком короткий SSID (<3 символов) — возможна путаница с соседними сетями")
    elif result["ssid_length"] > 20:
        result["analysis"].append("Длинный SSID (>20 символов) — может использоваться для скрытой передачи данных (стеганография)")

    # SSID из цифр/символов
    if not any(c.isalpha() for c in clean):
        result["analysis"].append("SSID состоит только из цифр/символов — возможно скрытая/служебная сеть")

    # Unicode / необычные символы
    if any(ord(c) > 127 for c in clean):
        result["security_notes"].append("⚠️ SSID содержит не-ASCII символы (Unicode) — возможна фишинговая сеть с визуально похожим именем")

    return result


async def card_lookup(card_number: str) -> dict:
    """Bank card BIN lookup — определяет банк, тип, страну по первым 6-8 цифрам карты"""
    clean = re.sub(r"\D", "", card_number)
    if len(clean) < 6:
        return {"error": "❌ Номер карты слишком короткий. Нужно минимум 6 цифр (BIN)."}
    bin_digits = clean[:8]  # до 8 цифр для точности
    url = f"https://lookup.binlist.net/{bin_digits}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                result = {
                    "scheme": data.get("scheme", "—"),
                    "type": data.get("type", "—"),
                    "brand": data.get("brand", "—"),
                    "prepaid": data.get("prepaid", "—"),
                    "country": (data.get("country") or {}).get("name", "—"),
                    "country_code": (data.get("country") or {}).get("alpha2", "—"),
                    "bank_name": (data.get("bank") or {}).get("name", "—"),
                    "bank_url": (data.get("bank") or {}).get("url", "—"),
                    "bank_phone": (data.get("bank") or {}).get("phone", "—"),
                    "bin": bin_digits,
                }
                return result
            elif resp.status_code == 404:
                return {"error": f"❌ BIN {bin_digits} не найден в базе."}
            else:
                return {"error": f"❌ Ошибка API (HTTP {resp.status_code})."}
    except Exception as e:
        logger.warning(f"card_lookup error: {e}")
        return {"error": f"❌ Ошибка запроса: {e}"}


# ==================== TELEGRAM ACCOUNT ANALYSIS (TELETHON) ====================

PHONE_LIKE = re.compile(r'^\+?\d{7,15}$')


# Глобальный кеш сообщений для пагинации: tg_msg_cache[user_id] = [entry, ...]
_tg_msg_cache: dict[int, list[dict]] = {}
_tg_page_size = 10


def get_tg_msg_page(user_id: int, page: int = 0) -> list[dict]:
    msgs = _tg_msg_cache.get(user_id, [])
    start = page * _tg_page_size
    return msgs[start:start + _tg_page_size]


def get_tg_msg_total(user_id: int) -> int:
    return len(_tg_msg_cache.get(user_id, []))


def clear_tg_msg_cache(user_id: int = None):
    if user_id:
        _tg_msg_cache.pop(user_id, None)
    else:
        _tg_msg_cache.clear()


async def telegram_account_lookup(input_str: str) -> dict:
    """Telegram аккаунт: username↔номер + все группы + сообщения + медиа + ссылки."""
    result = {"input": input_str, "found": False, "type": None, "error": None}

    try:
        from telethon_client import get_telethon_client
        from telethon.errors import UsernameInvalidError, FloodWaitError
        from telethon.tl.functions.users import GetFullUserRequest
        from telethon.tl.functions.messages import GetCommonChatsRequest, SearchGlobalRequest, SearchRequest
        from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty, MessageMediaPhoto, MessageMediaDocument

        client = await get_telethon_client()

        text = input_str.strip()
        if text.startswith("@"):
            text = text[1:]

        clean = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        is_phone = bool(PHONE_LIKE.match(clean)) and len(clean) >= 10

        try:
            entity = await client.get_entity(clean if not is_phone else ("+" + clean if not clean.startswith("+") else clean))
        except ValueError:
            try:
                entity = await client.get_entity(clean)
            except Exception as e2:
                result["error"] = f"Аккаунт не найден: {e2}"
                return result
        except UsernameInvalidError:
            result["error"] = "Такой username не существует."
            return result
        except FloodWaitError as e:
            result["error"] = f"⏳ Rate limit. Подождите {e.seconds} сек."
            return result

        result["found"] = True
        result["type"] = "phone" if is_phone else "username"
        result["user_id"] = entity.id
        result["username"] = entity.username
        result["first_name"] = entity.first_name or ""
        result["last_name"] = entity.last_name or ""
        result["phone"] = entity.phone
        result["bot"] = entity.bot
        result["premium"] = getattr(entity, "premium", False)
        result["verified"] = getattr(entity, "verified", False)
        result["scam"] = getattr(entity, "scam", False)
        result["fake"] = getattr(entity, "fake", False)
        result["restricted"] = getattr(entity, "restricted", False)

        if hasattr(entity, "status") and entity.status:
            result["status"] = str(entity.status)

        if is_phone and entity.username:
            result["found_by"] = "phone_to_username"
        elif not is_phone and entity.phone:
            result["found_by"] = "username_to_phone"
        else:
            result["found_by"] = "general"

        # ==================== РАСШИРЕННЫЕ ДАННЫЕ ====================

        def _make_msg_link(chat_entity, msg_id: int) -> str:
            username = getattr(chat_entity, "username", None)
            if username:
                return f"https://t.me/{username}/{msg_id}"
            cid = getattr(chat_entity, "id", 0)
            if cid < 0:
                cid = -cid
            s = str(cid)
            if s.startswith("100"):
                s = s[3:]
            return f"https://t.me/c/{s}/{msg_id}"

        def _media_type(msg) -> str:
            if not msg.media:
                return "text"
            if isinstance(msg.media, MessageMediaPhoto):
                return "photo"
            if isinstance(msg.media, MessageMediaDocument):
                doc = msg.media.document
                mime = getattr(doc, "mime_type", "") if doc else ""
                if "video" in mime:
                    return "video"
                if any(x in mime for x in ("audio", "ogg")):
                    return "audio"
                if msg.media.voice or "ogg" in mime:
                    return "voice"
                return "document"
            return "media"

        async def get_full_user():
            try:
                full = await client(GetFullUserRequest(entity.id))
                fu = full.full_user
                result["bio"] = getattr(fu, "about", None) or ""
                result["common_chats_count"] = getattr(fu, "common_chats_count", 0)
                result["has_profile_photo"] = getattr(fu, "profile_photo", None) is not None
                result["personal_photo"] = getattr(fu, "personal_photo", None) is not None
                result["ttl_period"] = getattr(fu, "ttl_period", None)
                if hasattr(fu, "bot_info") and fu.bot_info:
                    result["bot_description"] = getattr(fu.bot_info, "description", "")
            except Exception as e:
                logger.debug(f"GetFullUserRequest: {e}")

        async def get_common_chats():
            """Все общие группы и каналы (до 100)."""
            try:
                common = await client(GetCommonChatsRequest(user_id=entity.id, max_id=0, limit=100))
                chats = []
                if hasattr(common, "chats"):
                    for chat in common.chats:
                        chats.append({
                            "title": getattr(chat, "title", ""),
                            "username": getattr(chat, "username", ""),
                            "id": chat.id,
                            "participants": getattr(chat, "participants_count", 0),
                            "type": "channel" if hasattr(chat, "megagroup") and chat.megagroup is False else "group",
                            "verified": getattr(chat, "verified", False),
                            "scam": getattr(chat, "scam", False),
                        })
                if chats:
                    result["common_chats"] = chats
                    result["common_chats_found"] = len(chats)
            except Exception as e:
                logger.debug(f"GetCommonChats: {e}")

        async def search_author_messages():
            """Ищет сообщения, отправленные пользователем в общих чатах."""
            from telethon.tl.types import InputPeerChannel

            chats = result.get("common_chats", [])
            if not chats:
                return

            author_msgs = []
            seen_links_a = set()

            for chat_info in chats[:10]:
                cid = chat_info["id"]
                try:
                    peer = InputPeerChannel(cid, 0)
                    sres = await client(SearchRequest(
                        peer=peer, q="", filter=InputMessagesFilterEmpty(),
                        min_date=None, max_date=None,
                        offset_id=0, add_offset=0, limit=5,
                        max_id=0, min_id=0,
                        from_id=entity.id, hash=0,
                    ))
                    if hasattr(sres, "messages") and sres.messages:
                        for msg in sres.messages[:5]:
                            if getattr(msg, "from_id", None) is None:
                                continue
                            link = _make_msg_link(chat_info, msg.id)
                            if link in seen_links_a:
                                continue
                            seen_links_a.add(link)
                            mt = _media_type(msg)
                            text = (msg.text or "")[:300]
                            author_msgs.append({
                                "chat": chat_info.get("title", ""),
                                "chat_username": chat_info.get("username", ""),
                                "text": text,
                                "link": link,
                                "media_type": mt,
                                "has_voice": mt == "voice",
                                "date": str(getattr(msg, "date", ""))[:19],
                                "msg_id": msg.id,
                            })
                except Exception as e:
                    logger.debug(f"SearchRequest(chat={cid}): {e}")

            author_msgs.sort(key=lambda x: x.get("date", ""), reverse=True)
            if author_msgs:
                result["author_messages"] = author_msgs[:50]

        async def search_public_messages():
            """Ищет сообщения с упоминанием пользователя (username/имя) в публичных чатах."""
            queries = []
            if entity.username:
                queries.append(f"@{entity.username}")
            if is_phone and len(clean) >= 7:
                queries.append(clean)
            if entity.first_name:
                queries.append(entity.first_name)

            all_msgs = []
            seen_links = set()

            for q in queries:
                if not q or len(q) < 2:
                    continue
                try:
                    search = await client(SearchGlobalRequest(
                        q=q, filter=InputMessagesFilterEmpty(),
                        min_date=None, max_date=None,
                        offset_rate=0, offset_peer=InputPeerEmpty(),
                        offset_id=0, limit=10,
                    ))
                    if hasattr(search, "messages") and search.messages:
                        for msg in search.messages:
                            try:
                                chat_entity = await client.get_entity(msg.peer_id)
                            except:
                                continue
                            link = _make_msg_link(chat_entity, msg.id)
                            if link in seen_links:
                                continue
                            seen_links.add(link)

                            chat_title = getattr(chat_entity, "title", "") or getattr(chat_entity, "username", "") or str(chat_entity.id)
                            chat_username = getattr(chat_entity, "username", "")
                            mt = _media_type(msg)
                            text = (msg.text or "")[:300]

                            entry = {
                                "chat": chat_title,
                                "chat_username": chat_username,
                                "text": text,
                                "link": link,
                                "media_type": mt,
                                "has_voice": mt == "voice",
                                "date": str(getattr(msg, "date", ""))[:19],
                                "msg_id": msg.id,
                            }

                            if mt == "voice" and msg.media and hasattr(msg.media, "voice") and msg.media.voice:
                                entry["voice_duration"] = getattr(msg.media.voice, "duration", 0)
                                entry["voice_id"] = msg.media.voice.id

                            all_msgs.append(entry)
                except Exception as e:
                    logger.debug(f"SearchGlobal(q={q}): {e}")

            all_msgs.sort(key=lambda x: x.get("date", ""), reverse=True)
            if all_msgs:
                result["public_messages"] = all_msgs[:20]

        await asyncio.gather(get_full_user(), get_common_chats(), search_public_messages(), search_author_messages())

        # Кешируем все сообщения для пагинации
        all_found = []
        all_found.extend(result.get("public_messages", []))
        all_found.extend(result.get("author_messages", []))
        seen = set()
        deduped = []
        for m in all_found:
            if m.get("link") and m["link"] not in seen:
                seen.add(m["link"])
                deduped.append(m)
        deduped.sort(key=lambda x: x.get("date", ""), reverse=True)
        if deduped:
            _tg_msg_cache[entity.id] = deduped
            result["total_msgs"] = len(deduped)
            result["msg_offset"] = 0
            result["msg_page_size"] = _tg_page_size

    except RuntimeError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Ошибка Telethon: {type(e).__name__}: {e}"
        logger.warning(f"telegram_account_lookup: {e}")

    return result


# ==================== INSTAGRAM PROFILE LOOKUP ====================

async def instagram_profile_lookup(username: str) -> dict:
    """Instagram — детальный профиль по username через публичные источники."""
    username = username.strip().lstrip("@")
    result = {"input": username, "found": False, "error": None}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            # 1 — через OG-теги публичной страницы (всегда работает)
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
            r = await c.get(f"https://www.instagram.com/{username}/", headers=headers)

            if r.status_code == 200 and "The link you followed may be broken" not in r.text:
                text = r.text
                result["found"] = True

                m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', text)
                if m:
                    result["full_name"] = m.group(1)

                m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', text)
                if m:
                    desc = m.group(1)
                    result["biography"] = desc[:500]
                    parts = desc.split("·")
                    if len(parts) >= 3:
                        result["media_count"] = parts[0].strip().split()[0] if parts[0].strip() else "?"
                        result["follower_count"] = parts[1].strip().split()[0] if len(parts) > 1 else "?"

                m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text)
                if m:
                    result["profile_pic"] = m.group(1)

                if '"is_verified":true' in text:
                    result["is_verified"] = True
                if '"is_private":true' in text:
                    result["is_private"] = True
                if '"is_business_account":true' in text:
                    result["is_business"] = True

                m = re.search(r'"follower_count":(\d+)', text)
                if m:
                    result["follower_count"] = int(m.group(1))
                m = re.search(r'"following_count":(\d+)', text)
                if m:
                    result["following_count"] = int(m.group(1))
                m = re.search(r'"media_count":(\d+)', text)
                if m:
                    result["media_count"] = int(m.group(1))
            else:
                # 2 — fallback через публичный API
                api_headers = {
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "X-IG-App-ID": "936619743392459",
                }
                r2 = await c.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers=api_headers,
                )
                if r2.status_code == 200:
                    user = r2.json().get("data", {}).get("user", {})
                    if user:
                        result["found"] = True
                        result["full_name"] = user.get("full_name", "")
                        result["biography"] = user.get("biography", "")
                        result["follower_count"] = user.get("edge_followed_by", {}).get("count", 0)
                        result["following_count"] = user.get("edge_follow", {}).get("count", 0)
                        result["media_count"] = user.get("edge_owner_to_timeline_media", {}).get("count", 0)
                        result["profile_pic"] = user.get("profile_pic_url_hd", "")
                        result["is_private"] = user.get("is_private", False)
                        result["is_verified"] = user.get("is_verified", False)
                        result["is_business"] = user.get("is_business_account", False)
                        result["external_url"] = user.get("external_url", "")
                else:
                    result["error"] = f"Пользователь не найден или Instagram заблокировал запрос"

    except Exception as e:
        result["error"] = f"Ошибка Instagram: {type(e).__name__}: {e}"

    return result


# ==================== TIKTOK PROFILE LOOKUP ====================

async def tiktok_profile_lookup(username: str) -> dict:
    """TikTok — детальный профиль по username через публичные источники."""
    username = username.strip().lstrip("@")
    result = {"input": username, "found": False, "error": None}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            # 1 — OG-теги публичной страницы
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
            r = await c.get(f"https://www.tiktok.com/@{username}", headers=headers)

            if r.status_code != 200 or "Couldn't find this account" in r.text:
                result["error"] = "Пользователь не найден"
                return result

            text = r.text
            result["found"] = True

            m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', text)
            if m:
                result["nickname"] = m.group(1)

            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', text)
            if m:
                result["bio"] = m.group(1)[:500]

            m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text)
            if m:
                result["avatar"] = m.group(1)

            # 2 — TikTok API (без авторизации)
            api_headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Referer": f"https://www.tiktok.com/@{username}",
            }
            r2 = await c.get(
                f"https://www.tiktok.com/api/user/detail/?uniqueId={username}&lang=en",
                headers=api_headers,
            )
            if r2.status_code == 200:
                j = r2.json()
                user = j.get("userInfo", {}).get("user", {}) or j.get("data", {}).get("user", {})
                if user:
                    result["nickname"] = user.get("nickname", result.get("nickname", ""))
                    result["bio"] = user.get("signature", result.get("bio", ""))
                    result["avatar"] = user.get("avatarLarger", user.get("avatarMedium", user.get("avatarThumb", "")))
                    result["followerCount"] = user.get("followerCount", 0)
                    result["followingCount"] = user.get("followingCount", 0)
                    result["videoCount"] = user.get("videoCount", 0)
                    result["heartCount"] = user.get("heartCount", 0)
                    result["verified"] = user.get("verified", False)
                    result["privateAccount"] = user.get("privateAccount", False)
                    result["region"] = user.get("region", "")
                    result["tt_unique_id"] = user.get("uniqueId", "")

            if not result.get("followerCount") and not result.get("videoCount"):
                for pat in [
                    r'"followerCount":(\d+)', r'"followingCount":(\d+)',
                    r'"videoCount":(\d+)', r'"heartCount":(\d+)',
                    r'"verified":(true|false)', r'"privateAccount":(true|false)',
                ]:
                    m = re.search(pat, text)
                    if m:
                        key = pat.split(":")[0].strip('"')
                        val = m.group(1)
                        if val in ("true", "false"):
                            result[key] = val == "true"
                        else:
                            result[key] = int(val)

    except Exception as e:
        result["error"] = f"Ошибка TikTok: {type(e).__name__}: {e}"

    return result


# ==================== TWITTER / X PROFILE LOOKUP ====================

async def twitter_profile_lookup(username: str) -> dict:
    """Twitter/X — детальный профиль по username через публичный профиль."""
    username = username.strip().lstrip("@")
    result = {"input": username, "found": False, "error": None}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
            r = await c.get(f"https://x.com/{username}", headers=headers)

            if r.status_code != 200 or "This account doesn't exist" in r.text:
                result["error"] = "Пользователь не найден"
                return result

            text = r.text
            result["found"] = True

            m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', text)
            if m:
                result["display_name"] = m.group(1)

            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', text)
            if m:
                result["bio"] = m.group(1)[:500]

            m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text)
            if m:
                result["avatar"] = m.group(1)

            for pat in [
                (r'"followersCount":(\d+)', "followers"),
                (r'"followingCount":(\d+)', "following"),
                (r'"tweetCount":(\d+)', "tweets"),
                (r'"statusesCount":(\d+)', "tweets"),
                (r'"verified":(true|false)', "verified"),
                (r'"joined":"([^"]+)"', "joined"),
                (r'"location":"([^"]+)"', "location"),
            ]:
                m = re.search(pat[0], text)
                if m:
                    val = m.group(1)
                    result[pat[1]] = int(val) if val.isdigit() else (val == "true" if val in ("true","false") else val)

    except Exception as e:
        result["error"] = f"Ошибка Twitter/X: {type(e).__name__}: {e}"

    return result


# ==================== YOUTUBE CHANNEL LOOKUP ====================

async def youtube_channel_lookup(username: str) -> dict:
    """YouTube — профиль канала по @handle через публичную страницу."""
    username = username.strip().lstrip("@")
    result = {"input": username, "found": False, "error": None}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
            r = await c.get(f"https://www.youtube.com/@{username}", headers=headers)

            if r.status_code != 200 or "Not Found" in r.text or "This page doesn't exist" in r.text:
                result["error"] = "Канал не найден"
                return result

            text = r.text
            result["found"] = True

            m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', text)
            if m:
                result["title"] = m.group(1)

            m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', text)
            if m:
                result["description"] = m.group(1)[:500]

            m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text)
            if m:
                result["avatar"] = m.group(1)

            for pat in [
                (r'"subscriberCount":(\d+)', "subscribers"),
                (r'"videoCount":(\d+)', "videos"),
                (r'"viewCount":(\d+)', "views"),
                (r'"channelIdentifier":"([^"]+)"', "channel_id"),
                (r'"externalId":"([^"]+)"', "youtube_id"),
                (r'"verified":(true|false)', "verified"),
                (r'"country":"([^"]+)"', "country"),
            ]:
                m = re.search(pat[0], text)
                if m:
                    val = m.group(1)
                    result[pat[1]] = int(val) if val.isdigit() else (val == "true" if val in ("true","false") else val)

            m = re.search(r'"joinedDateText":\s*\{[^}]*"simpleText":"([^"]+)"', text)
            if m:
                result["joined"] = m.group(1)

    except Exception as e:
        result["error"] = f"Ошибка YouTube: {type(e).__name__}: {e}"

    return result
