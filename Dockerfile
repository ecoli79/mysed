# Dockerfile для основного NiceGUI приложения
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка uv для управления зависимостями
RUN pip install --no-cache-dir uv

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock ./

# Установка зависимостей
RUN uv sync --frozen --no-dev

# Копирование кода приложения
COPY . .

# Создание директории для логов
RUN mkdir -p /app/logs

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Порт для NiceGUI (по умолчанию 8080)
EXPOSE 8080

# Команда запуска приложения
CMD ["uv", "run", "python", "main.py"]

