FROM python:3.12-slim

WORKDIR /app

# Устанавливаем git для обновления datasources и шрифты для генерации карточек
RUN apt-get update && apt-get install -y git fonts-dejavu-core fonts-liberation && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Копируем mission_pool с изображениями миссий
COPY mission_pool ./mission_pool

# Инициализируем git в datasources если нужно
RUN cd /app/datasources && git init 2>/dev/null || true

# Запускаем бота
CMD ["python", "-m", "wh40k_bot.main"]
