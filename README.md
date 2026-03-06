# WH40K Match Bot ⚔️🎲

Telegram-бот для организации матчей Warhammer 40,000. Собирает списки армий от участников и рассылает их всем перед игрой.

## Возможности

- ✅ Создание игр с 2-10 участниками
- ✅ Сбор списков армий (файл)
- ✅ Автоматическая рассылка списков всем участникам
- ✅ Дедлайны и напоминания
- ✅ Распределение по командам (A и B)
- ✅ Запись результатов матчей
- ✅ Уведомления участников

---

## Quickstart (Docker — 5 минут)

```bash
# 1. Клонируем репозиторий
git clone <repo-url> wh-match-bot
cd wh-match-bot

# 2. Настраиваем окружение
cp .env.example .env
# Откройте .env и заполните BOT_TOKEN и ADMIN_IDS

# 3. Запускаем
docker compose up -d --build

# 4. Проверяем логи
docker compose logs -f bot
```

Бот готов к работе. Напишите `/start` в Telegram.

---

## Установка

### Требования

| Инструмент | Версия | Назначение |
|------------|--------|------------|
| Python | ≥ 3.11 | Рантайм |
| PostgreSQL | ≥ 14 | База данных |
| Redis | ≥ 7 | FSM-хранилище, кэш |
| Docker + Compose | любая | Для Docker-деплоя |
| uv | любая | Для локальной разработки |

### 1. Получить токен бота

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot`
2. Следуйте инструкциям, сохраните токен вида `1234567890:AAF...`

### 2. Узнать свой Telegram ID

Напишите [@userinfobot](https://t.me/userinfobot) — он покажет ваш числовой ID.

### 3. Настроить `.env`

```bash
cp .env.example .env
```

Откройте `.env` и заполните:

```env
BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

DB_HOST=localhost
DB_PORT=5432
DB_NAME=wh40k_bot
DB_USER=postgres
DB_PASSWORD=your_password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

ADMIN_IDS=123456789,987654321
```

---

## Запуск

### Вариант A: Docker Compose (рекомендуется)

Запускает бота, PostgreSQL и Redis одной командой. Данные сохраняются в Docker volumes.

```bash
docker compose up -d --build
```

Полезные команды:

```bash
docker compose logs -f bot        # логи бота в реальном времени
docker compose ps                 # статус контейнеров
docker compose restart bot        # перезапуск бота
docker compose down               # остановить всё
docker compose down -v            # остановить и удалить volumes (осторожно!)
```

### Вариант B: Локально с uv

Подходит для разработки. PostgreSQL и Redis нужно запустить отдельно.

```bash
# Устанавливаем зависимости
uv sync

# Запускаем
uv run python -m wh40k_bot.main
```

Или через pip:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m wh40k_bot.main
```

---

## Деплой на сервер

### Подготовка сервера (Ubuntu/Debian)

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Проверяем
docker --version
docker compose version
```

### Деплой

```bash
# Копируем проект на сервер
scp -r . user@your-server:/opt/wh-match-bot

# Или клонируем на сервере
ssh user@your-server
git clone <repo-url> /opt/wh-match-bot
cd /opt/wh-match-bot

# Настраиваем окружение
cp .env.example .env
nano .env   # заполняем переменные

# Запускаем
docker compose up -d --build
```

### Автозапуск при перезагрузке

Docker Compose уже настроен с `restart: unless-stopped` — контейнеры перезапустятся автоматически после перезагрузки сервера.

### Обновление бота

```bash
cd /opt/wh-match-bot
git pull
docker compose up -d --build bot
```

### Бэкап базы данных

```bash
# Создать дамп
docker compose exec postgres pg_dump -U postgres wh40k_bot > backup_$(date +%Y%m%d).sql

# Восстановить из дампа
docker compose exec -T postgres psql -U postgres wh40k_bot < backup_20240101.sql
```

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен от BotFather | — |
| `ADMIN_IDS` | ID админов через запятую | — |
| `DB_HOST` | Хост PostgreSQL | `localhost` |
| `DB_PORT` | Порт PostgreSQL | `5432` |
| `DB_NAME` | Имя базы данных | `wh40k_bot` |
| `DB_USER` | Пользователь БД | `postgres` |
| `DB_PASSWORD` | Пароль БД | — |
| `REDIS_HOST` | Хост Redis | `localhost` |
| `REDIS_PORT` | Порт Redis | `6379` |
| `REDIS_DB` | Номер БД Redis | `0` |

---

## Команды бота

### Для всех пользователей

| Команда | Описание |
|---------|----------|
| `/start` | Начать работу с ботом |
| `/mygames` | Показать мои активные игры |
| `/submit` | Отправить список армии |
| `/help` | Справка |

### Для админов

| Команда | Описание |
|---------|----------|
| `/newgame @user1 @user2 ...` | Создать игру |
| `/games` | Все активные игры |
| `/game [id]` | Управление игрой |
| `/users` | Список пользователей |

### Примеры создания игры

```
/newgame @player1 @player2
/newgame @player1 @player2 @player3 "Битва за Терру"
/newgame @player1 @player2 "Турнир" 48
```

Последний аргумент — дедлайн в часах (по умолчанию 24).

---

## Как это работает

```
┌─────────────────────────────────────────────────────────────┐
│  1. Админ: /newgame @player1 @player2 "Матч" 24            │
├─────────────────────────────────────────────────────────────┤
│  2. Бот → каждому участнику: "Вас добавили в игру!"        │
├─────────────────────────────────────────────────────────────┤
│  3. Участники отправляют списки армий боту                  │
├─────────────────────────────────────────────────────────────┤
│  4. Когда все отправили → Бот рассылает ВСЕ списки ВСЕМ    │
├─────────────────────────────────────────────────────────────┤
│  5. Админ распределяет команды (A / B)                      │
├─────────────────────────────────────────────────────────────┤
│  6. После игры: админ записывает победителя                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Структура проекта

```
wh-match-bot/
├── Dockerfile
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── wh40k_bot/
    ├── bot/
    │   ├── handlers/
    │   │   ├── callbacks.py
    │   │   └── commands.py
    │   ├── keyboards.py
    │   ├── middlewares.py
    │   ├── states.py
    │   └── utils.py
    ├── config.py
    ├── db/
    │   ├── models.py
    │   └── repository.py
    ├── main.py
    ├── scheduler.py
    └── services/
        └── game_service.py
```

---

## Лицензия

MIT

---

*За Императора! Или за Хаос. Или за кого там ваша армия...* 🎲
