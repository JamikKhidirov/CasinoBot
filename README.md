<!-- ════════════════════════ Анимированный баннер ═════════════════════════ -->

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:f7b32b&height=230&section=header&text=CasinoBot&fontSize=76&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=%F0%9F%8E%B0+%D0%9A%D0%B0%D0%B7%D0%B8%D0%BD%D0%BE+%E2%80%A2+%F0%9F%92%AC+%D0%90%D0%BD%D0%BE%D0%BD%D0%B8%D0%BC%D0%BD%D1%8B%D0%B9+%D1%87%D0%B0%D1%82+%E2%80%A2+%F0%9F%9B%A1+%D0%9C%D0%BE%D0%B4%D0%B5%D1%80%D0%B0%D1%86%D0%B8%D1%8F&descAlignY=60&descSize=20" width="100%" alt="CasinoBot"/>

<a href="https://github.com/JamikKhidirov/CasinoBot">
<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=900&color=F7B32B&center=true&vCenter=true&width=830&height=45&lines=Telegram+bot+on+aiogram+3.x;Dice+%7C+Bowling+%7C+Darts+%7C+Basketball+%7C+Football;PVP+%7C+Solo+%7C+Blackjack+%7C+Rock-Paper-Scissors;Balance+%7C+Bets+%7C+Promo+codes+%7C+Top+players" alt="Typing SVG"/>
</a>

<!-- ─────────────── Бейджи ─────────────── -->

<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/aiogram-3.x-2C9AB7?style=for-the-badge&logo=telegram&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-aiosqlite-003B57?style=for-the-badge&logo=sqlite&logoColor=white"/>
<img src="https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
<img src="https://img.shields.io/badge/Amvera-deploy-6A5ACD?style=for-the-badge&logo=icloud&logoColor=white"/>

<img src="https://img.shields.io/github/stars/JamikKhidirov/CasinoBot?style=for-the-badge&logo=github&color=f7b32b"/>
<img src="https://img.shields.io/github/last-commit/JamikKhidirov/CasinoBot?style=for-the-badge&color=2ea043"/>
<img src="https://img.shields.io/github/repo-size/JamikKhidirov/CasinoBot?style=for-the-badge&color=ff6b6b"/>
<img src="https://komarev.com/ghpvc/?username=JamikKhidirov&style=for-the-badge&color=f7b32b&label=VIEWS"/>

<br/><br/>

<b>🎰 Казино «под ключ» + 💬 анонимный чат в одном Telegram-боте</b><br/>
<sub>Версия <b>8.0.0</b> · Python 3.12 · aiogram 3.x · SQLite</sub>

</div>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:f7b32b,100:302b63&height=4&width=1000" width="100%"/>

## 🧭 Навигация

<div align="center">

| &#x1F3AE; [Быстрый старт](#-быстрый-старт) | 🐳 [Docker](#-docker) | ️ [Конфигурация](#-конфигурация) |
|:---:|:---:|:---:|
| &#x1F3AE; [Игры](#-игры-и-ставки) | 📋 [Команды](#-команды) | 🏗️ [Структура](#-структура-проекта) |

</div>


## ✨ Что умеет бот

<div align="center">

| 🎰 Казино | 💬 Анонимный чат | 🛡 Модерация |
|:---:|:---:|:---:|
| 🎲 Кости · 🎳 Боулинг<br/>🎯 Дротики · 🏀 Баскетбол<br/>⚽ Футбол · 🃏 Блэкджек · ✂️ КНБ | 🔎 Поиск собеседника<br/>✉️ Переписка 1-на-1<br/>🚪 Выход из диалога | 🚫 Баны · 🔇 Муты<br/>⚠️ Варны · 📨 Жалобы<br/>📝 Апелляции |

</div>

### 🎯 Ключевые фишки

- 🎲 **8 игр**: 5 «эмодзи-кубиков» (PVP), КНБ, блэкджек до 6 игроков и режим «против бота».
- ⏱ **Таймер 30 секунд** на каждом столе — виден обратный отсчёт, игра не «висит».
- 🧾 **Ставки и комиссия**: 10% комиссия казино, у бота-соперника свой баланс.
- 💰 **Баланс и переводы**: пополнение через админа, вывод, ежедневный бонус, промокоды.
- 🏆 **Топ игроков** (PVP и Solo) + профиль со статистикой.
- 🔓 `/unlock` — снять зависшие игры и вернуть ставки.
- 🔁 **Возврат ставок** за игры, потерянные при перезапуске бота.
- 🧩 **Эмодзи вместо кнопок**: отправь 🎲 🏀 ⚽ 🎳 🎯 прямо в чат — бот поймёт.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:302b63,100:f7b32b&height=4&width=1000" width="100%"/>

## 🚀 Быстрый старт

### 1️⃣ Клонируем и ставим зависимости

```bash
git clone https://github.com/JamikKhidirov/CasinoBot.git
cd CasinoBot

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
```

### 2️⃣ Настраиваем окружение

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # Linux / macOS
```

Минимально нужно заполнить:

```env
BOT_TOKEN=123456789:AA-ваш-токен-из-@BotFather
OWNER_ID=1819756249
OWNER_TG=jamik_khidirov
```

> 💡 Переменные окружения имеют приоритет, но в `config.py` есть дефолты — бот запустится даже без `.env`.

### 3️⃣ Запускаем

```bash
python main.py
```

- ✅ Бот работает на **long polling** — вебхуки и открытые порты не нужны.
- 📄 Логи пишутся в консоль и в файл `bot_errors.log`.
- ❗ Если Telegram API недоступен (`ConnectTimeout`) — включите VPN или задайте `PROXY_URL`.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:f7b32b,100:302b63&height=4&width=1000" width="100%"/>

## 🐳 Docker

### 🏗 Сборка и запуск вручную

```bash
docker build -t casinobot:latest .

docker run -d ^
  --name casinobot ^
  --restart unless-stopped ^
  -e BOT_TOKEN="123456789:AA-ваш-токен" ^
  -e OWNER_ID="1819756249" ^
  -e OWNER_TG="jamik_khidirov" ^
  -v casinobot_data:/data ^
  casinobot:latest
```

> &#x1F427; На Linux/macOS замените `^` на `\`.

### 🧩 Docker Compose (рекомендуется)

```bash
copy .env.example .env      # 1. заполнить BOT_TOKEN и OWNER_ID
docker compose up -d --build    # 2. собрать и запустить
docker compose logs -f          # 3. смотреть логи
docker compose down             # остановить
```

### 📦 Что внутри образа

| Параметр | Значение |
|:---|:---|
| Базовый образ | `python:3.12-slim` |
| Рабочая папка | `/app` |
| Пользователь | `bot` (не root) |
| Данные | `/data` → том `casinobot_data` |
| Точка входа | `python main.py` |

- 💾 БД `chat.db` и `casino.db` код создаёт в `/data`, поэтому том монтируется **именно в `/data`** — иначе данные пропадут при пересборке.
- 🌐 Порты не нужны: бот работает через long polling (`EXPOSE 8080` оставлен для платформ, требующих порт).
- 🔐 Секреты передаются переменными окружения — токен в образ не «запекается».
- &#x1F6AB; `.dockerignore` исключает `.venv`, `.git`, `*.db`, `*.session`, `.env` — образ остаётся лёгким.

### ☁️ Деплой на Amvera

В репозитории есть `amvera.yml` (persistenceMount `/data`, script `main.py`):

```bash
git push amvera master
```

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:302b63,100:f7b32b&height=4&width=1000" width="100%"/>

## 🎮 Игры и ставки

<div align="center">

| Игра | Эмодзи | Команда | Режим |
|:---:|:---:|:---|:---:|
| Кости | &#x1F3B2; | `/dice` · `/куб` | PVP / Solo |
| Боулинг | &#x1F3B3; | `/bowling` · `/боулинг` | PVP / Solo |
| Дротики | &#x1F3AF; | `/darts` · `/дротики` | PVP / Solo |
| Баскетбол | &#x1F3C0; | `/basket` · `/баскетбол` | PVP / Solo |
| Футбол | ⚽ | `/football` · `/футбол` | PVP / Solo |
| КНБ | ✂️ | меню казино | PVP (группа) |
| Блэкджек | &#x1F0CF; | `/blackjack` · `/блекджек` | до 6 игроков |

</div>

### 📜 Правила

| Правило | Значение |
|:---|:---|
| Таймер хода / набора игроков | **30 секунд** |
| Комиссия казино | **10%** от банка |
| Стартовый баланс игрока | **1000** монет |
| Баланс бота-соперника | **500** монет |
| Футбол / баскетбол | бросок **> 3** = гол, **≤ 3** = промах |
| КНБ | выбор в ЛС, победитель забирает банк |

### 💸 Бонусы, пополнение и вывод

- &#x1F381; **Ежедневный бонус**: игроку — 500 монет, боту — 200 монет.
- &#x1F3AB; **Промокоды**: админ создаёт (`/createpromo`), игрок активирует (`/promo`).
- 📥 **Пополнение**: админ выдаёт реквизиты → оплата → `/одобрить` → монеты на балансе.
- 📤 **Вывод**: запросы обрабатывает админ через `/выводы`.
- 🏦 **Счёт бота** пополняется командой `/addbotcoins`.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:f7b32b,100:302b63&height=4&width=1000" width="100%"/>

## 📋 Команды

<details open>
<summary><b>&#x1F3AE; Игроку</b></summary>

| Команда | Что делает |
|:---|:---|
| `/start` | 🏠 Главное меню (чат + казино) |
| `/help` | ❓ Справка по всем командам |
| `/profile` · `/профиль` | &#x1F464; Профиль игрока |
| `/top` · `/топ` | &#x1F3C6; Топ игроков казино |
| `/games` · `/игры` | &#x1F3AE; Список игр |
| `/dice [ставка]` · `/куб [ставка]` | &#x1F3B2; Кости |
| `/bowling [ставка]` · `/боулинг [ставка]` | &#x1F3B3; Боулинг |
| `/darts [ставка]` · `/дротики [ставка]` | &#x1F3AF; Дротики |
| `/basket [ставка]` · `/баскетбол [ставка]` | &#x1F3C0; Баскетбол |
| `/football [ставка]` · `/футбол [ставка]` | ⚽ Футбол |
| `/blackjack [ставка]` · `/блекджек [ставка]` | &#x1F0CF; Блэкджек |
| `/solo` · `/сботом` | &#x1F916; Игра против бота (в ЛС) |
| `/solotop` | ⭐ Топ игроков с ботом |
| `/active` · `/активные` | &#x1F579; Активные игры |
| `/unlock` · `/разблокировать` | &#x1F513; Отменить свои игры |
| `/promo` | &#x1F3AB; Активировать промокод |

</details>

<details>
<summary><b>&#x1F451; Админам</b></summary>

| Команда | Что делает |
|:---|:---|
| `/stats` | &#x1F4CA; Статистика бота |
| `/admin` | &#x1F451; Админ-панель казино |
| `/players` · `/игроки` | &#x1F465; Список игроков казино |
| `/mod` | 🛡 Панель модерации |
| `/ban` · `/unban` | &#x1F6AB; / ✅ Бан и разбан |
| `/mute` · `/unmute` | 🔇 / 🔊 Мут и размут |
| `/warn` · `/warns` | ⚠️ Варн и список варнов |
| `/check` | 📋 Проверить пользователя |
| `/chatlog` | 💬 Переписка пользователя |
| `/пополнить` | 💰 Пополнить баланс |
| `/одобрить` | ✅ Подтвердить депозит |
| `/выводы` | 📤 Запросы на вывод |
| `/addbotcoins` | &#x1F916; Пополнить счёт бота |
| `/createpromo` · `/deletepromo` · `/promo_list` | &#x1F3AB; Управление промокодами |

</details>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:302b63,100:f7b32b&height=4&width=1000" width="100%"/>

## 🏗️ Структура проекта

```mermaid
flowchart TD
    TG([Telegram]) --> DP["aiogram Dispatcher"]
    DP --> CHAT["Чат-роутеры: user, callbacks, text_handler"]
    DP --> CASINO["Роутер казино"]
    DP --> MODS["admin, moderation, developer"]
    CASINO --> PVP["games_pvp, games_rps, blackjack"]
    CASINO --> SOLO["games_solo, menu, profile"]
    PVP --> BASE["base.py: GameRoom, BlackjackRoom, БД"]
    SOLO --> BASE
    BASE --> DB1[("chat.db")]
    BASE --> DB2[("casino.db")]
```

```
CasinoBot/
├── main.py                     # Точка входа: Bot + Dispatcher + polling
├── config.py                   # Настройки (ENV + дефолты)
├── db.py                       # SQLite: users, messages, bans, reports, appeals, moderation
├── requirements.txt            # Зависимости
├── Dockerfile                  # Образ для хостинга
├── docker-compose.yml          # Запуск одной командой
├── amvera.yml                  # Деплой на Amvera
├── .env.example                # Шаблон переменных окружения
├── handlers/
│   ├── user.py                 # /start, поиск собеседника
│   ├── callbacks.py            # Инлайн-кнопки чата и казино
│   ├── text_handler.py         # Диспетчер текстовых сообщений
│   ├── admin.py                # /stats
│   ├── moderation.py           # Баны, муты, варны, /mod
│   ├── developer.py            # Выдача прав, рассылка
│   ├── casino/
│       ├── base.py             # GameRoom, BlackjackRoom, БД, утилиты
│       ├── menu.py             # Меню, /games, /top, /active
│       ├── profile.py          # Профиль, пополнение, вывод, промокоды
│       ├── games_pvp.py        # Кости, боулинг, дротики, баскетбол, футбол
│       ├── games_solo.py       # Игры против бота
│       ├── games_rps.py        # Камень-ножницы-бумага
│       ├── blackjack.py        # Блэкджек до 6 игроков
│       ├── admin.py            # Админ-панель казино
│       └── keyboards.py        # Клавиатуры казино
└── utils/
    ├── keyboards.py            # Главное меню, клавиатуры чата
    └── helpers.py              # is_admin, is_banned, save_message
```

## ⚙️ Конфигурация

| Переменная | Обязательна | Описание |
|:---|:---:|:---|
| `BOT_TOKEN` | ✅ | Токен от [@BotFather](https://t.me/BotFather) |
| `OWNER_ID` | ✅ | Telegram ID владельца |
| `OWNER_TG` | — | Username владельца без `@` |
| `ADMINS` | — | Доп. админы через запятую: `111,222` |
| `VERSION` | — | Версия бота (по умолчанию `8.0.0`) |
| `PROJECT_NAME` | — | Название проекта |
| `PROXY_URL` | — | Прокси для Telegram API: `http://user:pass@host:8080` или `socks5://host:1080`. Требует пакет `aiohttp-socks` (уже в `requirements.txt`) |
| `DB_NAME` | — | Имя файла БД чата (по умолчанию `chat.db`) |

### 🧠 Тонкости, которые стоит знать

- 🐍 **Python 3.10+**: в `db.py` используется синтаксис `sqlite3.Connection | None`.
- 🗄 **Базы данных**: `chat.db` (чат) и `casino.db` (казино). Если существует папка `/data` — файлы пишутся туда (Amvera, Docker), иначе в корень проекта.
- 🚫 **Импорт БД**: используйте `import db` и `db.cur`, а не `from db import cur` — иначе получите `None`.
- 📄 **Логи**: `bot_errors.log` + stdout, поэтому `docker compose logs -f` показывает всё.
- ✂️ Сообщения длиннее 4096 символов обрезаются до `[:3997] + "..."`.
- 🔁 Ставки за игры, потерянные при перезапуске, возвращаются (`refund_orphaned_games`).
- 📡 При сетевых ошибках (`TelegramNetworkError`) polling повторяется до 10 раз с растущей паузой.
- 🔐 Токен по умолчанию прописан в `config.py` — в публичном репозитории передавайте свой через `BOT_TOKEN`.

## 🤝 Как помочь проекту

1. Форкните репозиторий и создайте ветку от `develop`.
2. Держитесь стиля проекта: aiogram 3.x, HTML-разметка, русские тексты сообщений.
3. Проверьте запуск локально: `python main.py`.
4. Откройте Pull Request с описанием изменений.

## 📄 Лицензия

Проект распространяется по лицензии **MIT**. © [JamikKhidirov](https://github.com/JamikKhidirov)

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:f7b32b,50:302b63,100:0f0c29&height=140&section=footer&text=%D0%A3%D0%B4%D0%B0%D1%87%D0%BD%D0%BE%D0%B9+%D0%B8%D0%B3%D1%80%D1%8B%21&fontSize=34&fontColor=ffffff&animation=twinkling" width="100%"/>

