#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Создание пользователя для Mayan
    CREATE USER mayan WITH PASSWORD 'mayandbpass';
    CREATE DATABASE mayan OWNER mayan;
    GRANT ALL PRIVILEGES ON DATABASE mayan TO mayan;

    -- Создание пользователя для Camunda
    CREATE USER camunda WITH PASSWORD 'Gkb6CodCod';
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


