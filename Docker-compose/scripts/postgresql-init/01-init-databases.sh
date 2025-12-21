#!/bin/bash
set -e

# Получаем пароли из переменных окружения или используем значения по умолчанию
MAYAN_DB_PASSWORD="${MAYAN_DATABASE_PASSWORD}"
CAMUNDA_DB_PASSWORD="${CAMUNDA_DATABASE_PASSWORD}"

# Проверяем, что пароли установлены
if [ -z "$MAYAN_DB_PASSWORD" ]; then
    echo "ERROR: MAYAN_DATABASE_PASSWORD не установлен" >&2
    exit 1
fi

if [ -z "$CAMUNDA_DB_PASSWORD" ]; then
    echo "ERROR: CAMUNDA_DATABASE_PASSWORD не установлен" >&2
    exit 1
fi

# Экранируем одинарные кавычки в паролях для безопасного использования в SQL
# Заменяем каждую одинарную кавычку на две одинарные кавычки (стандарт SQL)
MAYAN_DB_PASSWORD_ESCAPED=$(echo "$MAYAN_DB_PASSWORD" | sed "s/'/''/g")
CAMUNDA_DB_PASSWORD_ESCAPED=$(echo "$CAMUNDA_DB_PASSWORD" | sed "s/'/''/g")

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Создание пользователя для Mayan
    CREATE USER mayan WITH PASSWORD '${MAYAN_DB_PASSWORD_ESCAPED}';
    CREATE DATABASE mayan OWNER mayan;
    GRANT ALL PRIVILEGES ON DATABASE mayan TO mayan;

    -- Создание пользователя для Camunda
    CREATE USER camunda WITH PASSWORD '${CAMUNDA_DB_PASSWORD_ESCAPED}';
    CREATE DATABASE camunda OWNER camunda;
    GRANT ALL PRIVILEGES ON DATABASE camunda TO camunda;

    -- Выдача прав на создание схем
    \c mayan
    GRANT ALL ON SCHEMA public TO mayan;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO mayan;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO mayan;

    \c camunda
    GRANT ALL ON SCHEMA public TO camunda;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO camunda;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO camunda;
EOSQL

echo "Databases initialized successfully"


