# syntax=docker/dockerfile:1

# ============================================================
#  CasinoBot — Telegram-бот (aiogram 3.x)
#  БД (chat.db / casino.db) автоматически пишутся в /data,
#  поэтому том нужно монтировать именно туда.
# ============================================================
FROM python:3.12-slim

LABEL org.opencontainers.image.title="CasinoBot" \
      org.opencontainers.image.description="Telegram-бот: казино + анонимный чат" \
      org.opencontainers.image.source="https://github.com/JamikKhidirov/CasinoBot"

# --- Поведение Python в контейнере ---
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# --- Зависимости отдельным слоем (кешируется между сборками) ---
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Код проекта ---
COPY . .

# --- Работаем не от root + создаём папку для БД ---
RUN mkdir -p /data \
    && useradd --create-home --uid 1000 bot \
    && chown -R bot:bot /app /data
USER bot

# Персистентный том: сюда попадут chat.db и casino.db
VOLUME ["/data"]

# Бот работает через long polling, входящий порт не обязателен.
# EXPOSE оставлен для платформ, требующих открытый порт.
EXPOSE 8080

CMD ["python", "main.py"]
