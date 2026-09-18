import os

# Значения ниже — дефолт. Их можно переопределить переменными окружения
# (см. .env.example), что обязательно при запуске в Docker.
_DEFAULT_BOT_TOKEN = "8374862323:AAFqyGFcJLhI8426GpRdhKYU7BGa05DvtUo"
_DEFAULT_OWNER_ID = 1819756249


def _env(name: str, default: str = "") -> str:
    """Читает переменную окружения, убирая лишние пробелы."""
    return (os.getenv(name) or "").strip() or default


def _env_int(name: str, default: int) -> int:
    """Читает int из переменной окружения (безопасно, с fallback)."""
    try:
        return int(_env(name))
    except (TypeError, ValueError):
        return default


def _env_ids(name: str) -> list[int]:
    """Читает список ID из строки вида '111,222' или '111;222'."""
    raw = _env(name)
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


BOT_TOKEN = _env("BOT_TOKEN", _DEFAULT_BOT_TOKEN)
OWNER_ID = _env_int("OWNER_ID", _DEFAULT_OWNER_ID)
OWNER_TG = _env("OWNER_TG", "jamik_khidirov")

# OWNER_ID всегда входит в список админов
_extra_admins = _env_ids("ADMINS")
ADMINS = list(dict.fromkeys([OWNER_ID, *_extra_admins])) if _extra_admins else [OWNER_ID]

VERSION = _env("VERSION", "8.0.0")
PROJECT_NAME = _env("PROJECT_NAME", "CasinoBot")
DB_NAME = _env("DB_NAME", "chat.db")

# Прокси для Telegram API (если API заблокирован): http://user:pass@host:8080
PROXY_URL = _env("PROXY_URL") or None