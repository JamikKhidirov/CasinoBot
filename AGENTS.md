# AGENTS.md

## Проект

Telegram-бот с двумя режимами: **OSINT-пробив** (телефон, email, username, IP, домен) и **анонимный чат** (поиск собеседника, переписка, жалобы, баны, апелляции).

## Запуск

```bash
python main.py
```

Бот работает на `aiogram` 3.x (асинхронный, `Dispatcher.start_polling`).

## Структура

| Файл | Назначение |
|------|-----------|
| `main.py` | Точка входа, создание Bot/Dispatcher, запуск polling |
| `config.py` | `BOT_TOKEN`, `OWNER_ID`, `ADMINS`, `VERSION`, `PROXY_URL` |
| `db.py` | Инициализация SQLite (`chat.db`), таблицы `users`, `bans`, `messages`, `osint_logs` |
| `osint.py` | Движок OSINT: `phone_lookup`, `email_lookup`, `username_lookup`, `ip_lookup`, `domain_lookup` |
| `handlers/osint_handlers.py` | Обработчики OSINT-команд (меню + ввод) |
| `handlers/text_handler.py` | Диспетчер текстовых сообщений (OSINT vs чат) |
| `handlers/user.py` | Хендлер `/start`, состояние `active_users`/`waiting_users` для чата |
| `handlers/callbacks.py` | Callback'и чата: старт/выход |
| `handlers/admin.py` | Админ-команды: `/stats` |
| `utils/keyboards.py` | Inline-клавиатуры (главное меню, OSINT, чат) |
| `utils/helpers.py` | Хелперы: `is_admin`, `is_banned`, `save_message` |
| `requirements.txt` | `aiogram>=3.12`, `phonenumbers`, `httpx`, `dnspython` |
| `casino/` | Отдельный проект — CasinoBot (aiogram 3.x, FSM, игры) |

## Важные замечания

- **Токен в `config.py`** — жёстко зашит. Для продакшена вынести в переменные окружения.
- **Прокси** — если Telegram API заблокирован (ошибка `ConnectTimeout`), задайте `PROXY_URL` в `config.py` (например `"http://proxy:8080"` или `"socks5://proxy:1080"`).
- **Все OSINT-функции в `osint.py`** — асинхронные (кроме `phone_lookup`, он синхронный через библиотеку phonenumbers).
- **Username search** проверяет 22 площадки через HTTP. Twitter/Instagram могут не отвечать из-за rate-limit.
- **IP lookup** использует `ip-api.com` (бесплатно, без ключа, 45 запросов/мин с одного IP).
- **Для email** проверяется формат, MX-записи и Gravatar.
- **Для домена** — DNS A/AAAA/MX/NS/TXT/SOA + HTTP/HTTPS проверка.
- **База данных** — SQLite (`chat.db`). Инициализация таблиц при первом запуске.
- **Логи** пишутся в `bot_errors.log`.
- **Ветки**: `master` и `develop`.

## Команды бота (Telegram)

- `/start` — главное меню (OSINT + чат)
- `/phone <номер>` — пробив телефона (или через меню)
- `/email <email>` — пробив email
- `/user <username>` — поиск username в соцсетях
- `/ip <ip>` — геолокация IP
- `/domain <домен>` — информация о домене
- `/help` — справка по всем командам
- `/stats` — статистика (только для админов)

Все OSINT-команды работают в двух режимах:
1. **Быстрый**: `/phone +79123456789` — результат сразу
2. **Пошаговый**: `/phone` → бот запросит номер → отправляете

Либо через кнопки: `/start` → **OSINT-пробив** → выбрать тип → ввести данные.

## Обработка ошибок

- `is_admin()` — исправлен (двойной fetchone — баг).
- **DB-импорт**: используйте `import db` и `db.cur`, а не `from db import cur` (иначе получите `None`).
- При превышении лимита 4096 символов ответ обрезается до `[:3997] + "..."`.
- Все HTTP-запросы OSINT имеют таймаут 8–15 секунд (не блокируют бота).
