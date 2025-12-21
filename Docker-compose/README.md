# Docker Compose Configuration

Этот каталог содержит конфигурацию Docker Compose для запуска всех необходимых сервисов проекта.

## Структура сервисов

### Основные сервисы:
- **app** (NiceGUI) - основное веб-приложение
- **PostgreSQL** - база данных для Mayan EDMS и Camunda BPM
- **OpenLDAP** - сервер каталогов для аутентификации
- **phpLDAPadmin** - веб-интерфейс для управления LDAP
- **RabbitMQ** - брокер сообщений для Mayan EDMS
- **Redis** - кэш и блокировки для Mayan EDMS
- **Mayan EDMS** - система управления документами
- **Camunda BPM** - платформа управления бизнес-процессами
- **Elasticsearch** (опционально) - поисковый движок для Mayan

## Быстрый старт

### 1. Создайте файл .env

Создайте файл `.env` в директории `Docker-compose` со следующим содержимым:

```env
# Основное приложение
APP_NAME=NiceGUI Example
APP_PORT=8080
DEBUG=false
ENVIRONMENT=production

# PostgreSQL
POSTGRES_PASSWORD=yourpsqlpass
POSTGRES_PORT=5432
# Пароли для пользователей баз данных (используются в скрипте инициализации)
MAYAN_DATABASE_PASSWORD=yourmayandbpass
CAMUNDA_DATABASE_PASSWORD=yourcamundapass

# RabbitMQ
MAYAN_RABBITMQ_USER=mayan
MAYAN_RABBITMQ_PASSWORD=mayanrabbitpass
MAYAN_RABBITMQ_VHOST=mayan
MAYAN_RABBITMQ_ADMIN_PORT=15672

# Redis
MAYAN_REDIS_PASSWORD=mayanredispassword

# Mayan EDMS
MAYAN_DATABASE_USER=mayan
MAYAN_DATABASE_PASSWORD=mayandbpass
MAYAN_FRONTEND_HTTP_PORT=80
MAYAN_USERNAME=admin
MAYAN_PASSWORD=your_mayan_password
MAYAN_API_TOKEN=your_mayan_api_token

# Camunda
CAMUNDA_USERNAME=your_camunda_username
CAMUNDA_PASSWORD=your_camunda_password
CAMUNDA_VERIFY_SSL=false
# Пароли для базы данных Camunda (используются в production.yml)
CAMUNDA_DATABASE_USER=camunda
CAMUNDA_DATABASE_PASSWORD=yourcamundapass
# SSL настройки для Camunda (опционально)
CAMUNDA_SSL_KEYSTORE_PASSWORD=camunda
CAMUNDA_SSL_KEY_PASSWORD=camunda
# LDAP настройки для Camunda (опционально, если отличается от основных LDAP настроек)
CAMUNDA_LDAP_SERVER_URL=ldap://openldap:389/

# LDAP
LDAP_USER=cn=yourldaplogin
LDAP_PASSWORD=yourldappass
LDAP_BASE_DN=dc=permgp7,dc=ru

# Elasticsearch (опционально)
MAYAN_ELASTICSEARCH_PASSWORD=mayanespassword
```

### 2. Запустите сервисы

```bash
cd Docker-compose
docker compose up -d
```

**Примечание:** При первом запуске Docker соберет образ для основного приложения (это может занять несколько минут).

Это запустит все сервисы, включая:
- **Основное приложение (NiceGUI)** на порту 8080
- PostgreSQL, OpenLDAP, RabbitMQ, Redis
- Mayan EDMS и Camunda BPM

### Пересборка образа приложения

Если вы изменили код приложения и нужно пересобрать образ:

```bash
docker compose build app
docker compose up -d app
```

Или пересобрать все сервисы:

```bash
docker compose up -d --build
```

### 3. Проверьте статус

```bash
docker compose ps
```

### 4. Доступ к приложению

После запуска основное приложение будет доступно по адресу:
- **Основное приложение**: http://localhost:8080
- **Mayan EDMS**: http://localhost:80
- **Camunda BPM**: http://localhost:8081 (HTTP) или https://localhost:8443 (HTTPS)
- **phpLDAPadmin**: https://localhost:6443
- **RabbitMQ Management**: http://localhost:15672

## Внешние зависимости

### MinIO/S3 хранилище

Mayan EDMS настроен на использование внешнего MinIO/S3 хранилища по адресу `url_minio:9000`.

**Важно:** Убедитесь, что:
1. MinIO сервер доступен по указанному адресу
2. Создан bucket с именем `mayan`
3. Учетные данные доступа корректны (login/password)

Если нужно использовать локальный MinIO, добавьте сервис в `docker-compose.yml`:

```yaml
minio:
  image: minio/minio:latest
  container_name: minio
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: minio_login
    MINIO_ROOT_PASSWORD: minio_password
  ports:
    - "9000:9000"
    - "9001:9001"
  volumes:
    - ./data/minio:/data
  networks:
    - services_network
```

И обновите `MAYAN_DOCUMENTS_FILE_STORAGE_BACKEND_ARGUMENTS` в `docker-compose.yml`:
```yaml
endpoint_url: "http://minio:9000"
```

## Порты сервисов

- **Основное приложение (NiceGUI)**: 8080 (по умолчанию)
- **PostgreSQL**: 5432
- **OpenLDAP**: 389 (LDAP), 636 (LDAPS)
- **phpLDAPadmin**: 6443
- **RabbitMQ**: 5672 (AMQP), 15672 (Management UI)
- **Redis**: 6379
- **Mayan EDMS**: 80 (по умолчанию)
- **Camunda BPM**: 8081 (HTTP), 8443 (HTTPS)
- **Elasticsearch**: 9200 (если включен)

## Резервное копирование

### Автоматическое резервное копирование PostgreSQL

```bash
docker compose --profile backup run --rm postgresql-backup
```

### Полное резервное копирование всех сервисов

```bash
./scripts/run-backups.sh
```

## Инициализация баз данных

Базы данных `mayan` и `camunda` создаются автоматически при первом запуске PostgreSQL через скрипт `scripts/postgresql-init/01-init-databases.sh`.

## Healthchecks

Все сервисы имеют настроенные healthchecks для обеспечения корректного порядка запуска:
- PostgreSQL проверяет готовность через `pg_isready`
- OpenLDAP проверяет доступность через `ldapsearch`
- RabbitMQ проверяет через `rabbitmq-diagnostics ping`
- Redis проверяет через `redis-cli ping`

## Troubleshooting

### Проблемы с подключением к LDAP

Если Camunda или Mayan не могут подключиться к LDAP:
1. Убедитесь, что OpenLDAP запущен: `docker compose ps openldap`
2. Проверьте логи: `docker compose logs openldap`
3. Убедитесь, что в конфигурации указан `openldap` (имя сервиса), а не IP-адрес

### Проблемы с Mayan EDMS

Если Mayan не запускается:
1. Проверьте, что PostgreSQL готов: `docker compose ps postgresql`
2. Проверьте логи: `docker compose logs mayan-app`
3. Убедитесь, что RabbitMQ и Redis запущены

### Проблемы с Camunda

Если Camunda не запускается:
1. Проверьте подключение к PostgreSQL
2. Проверьте конфигурацию в `camunda/production.yml`
3. Проверьте логи: `docker compose logs camunda`

### Проблемы с основным приложением

Если основное приложение не запускается:
1. Проверьте, что все зависимости запущены: `docker compose ps`
2. Проверьте логи: `docker compose logs app`
3. Убедитесь, что переменные окружения настроены правильно
4. Проверьте, что приложение может подключиться к другим сервисам:
   - LDAP: `openldap:389`
   - Camunda: `camunda:8443`
   - Mayan: `mayan-app:8000`

## Остановка и очистка

### Остановка сервисов

```bash
docker compose down
```

### Остановка с удалением volumes (⚠️ удалит все данные!)

```bash
docker compose down -v
```

## Дополнительная информация

- [ENV_SETUP.md](./ENV_SETUP.md) - настройка переменных окружения для основного приложения
- [DEPLOY_WORK_GUIDE.md](./DEPLOY_WORK_GUIDE.md) - руководство по развертыванию процессов

