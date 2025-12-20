# Система логирования для проекта NiceGUI Example

## 📋 Содержание
1. [Обзор](#обзор)
2. [Установка и настройка](#установка-и-настройка)
3. [Базовое использование](#базовое-использование)
4. [Конфигурация](#конфигурация)
5. [Продвинутые возможности](#продвинутые-возможности)
6. [Примеры интеграции](#примеры-интеграции)
7. [Устранение неполадок](#устранение-неполадок)

## 🔍 Обзор

Система логирования предоставляет:
- **Гибкую конфигурацию** через .env файл
- **Множественные обработчики**: консоль, файл, база данных
- **Поддержку разных БД**: SQLite и PostgreSQL
- **Структурированное логирование** с JSON форматом
- **Автоматическое логирование функций** через декораторы
- **Контекстную информацию** (поток, процесс, модуль)

## ⚙️ Установка и настройка

### 1. Установка зависимостей

```bash
# Минимальный набор (только SQLite)
uv add python-dotenv

# С поддержкой PostgreSQL
uv add python-dotenv psycopg2-binary
```

### 2. Структура файлов

```
project/
├── config/
│   ├── __init__.py
│   └── settings.py
├── logging/
│   ├── __init__.py
│   ├── logger.py
│   ├── handlers.py
│   └── database/
│       ├── __init__.py
│       ├── base.py
│       ├── postgresql_adapter.py
│       ├── sqlite_adapter.py
│       └── factory.py
├── .env
└── main.py
```

### 3. Инициализация в main.py

```python
# main.py
from logging.logger import setup_logging
from config.settings import config

# Настраиваем логирование при старте приложения
setup_logging()

# Остальной код приложения
```

## 🚀 Базовое использование

### Простое логирование

```python
from logging.logger import get_logger

# Создаем логгер
logger = get_logger(__name__)

# Используем разные уровни
logger.debug("Отладочная информация")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.critical("Критическая ошибка")
```

### Логирование с исключениями

```python
try:
    # ваш код
    risky_operation()
except Exception as e:
    logger.error("Произошла ошибка", exc_info=True)
```

### Структурированное логирование

```python
# Логгер с дополнительными полями
logger = get_logger(__name__, extra_fields={
    'component': 'user_service',
    'version': '1.0.0'
})

# Логирование с контекстом
logger.info("Пользователь выполнил действие", extra={
    'user_id': '12345',
    'action': 'login',
    'ip_address': '192.168.1.1'
})
```

## ⚙️ Конфигурация

### .env файл

```bash
# Основные настройки приложения
APP_NAME=NiceGUI Example
DEBUG=false
ENVIRONMENT=development

# Настройки логирования
LOG_LEVEL=INFO
LOG_HANDLERS=console,file,database
LOG_DIR=logs
LOG_FILE=app.log
LOG_MAX_FILE_SIZE=10485760
LOG_BACKUP_COUNT=5
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s
LOG_DATE_FORMAT=%Y-%m-%d %H:%M:%S
LOG_JSON_FORMAT=false
LOG_CONTEXT=true

# Настройки базы данных для логов
DB_TYPE=sqlite
SQLITE_PATH=logs/app_logs.db
LOG_TABLE_NAME=application_logs

# PostgreSQL настройки (если используется)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=logs
DB_USER=postgres
DB_PASSWORD=your_password

# Настройки Camunda
CAMUNDA_URL=https://172.19.228.72:8443
CAMUNDA_USERNAME=dvimpolitov
CAMUNDA_PASSWORD=gkb6codcod

# Настройки LDAP
LDAP_SERVER=your_ldap_server
LDAP_USER=your_ldap_user
LDAP_PASSWORD=your_ldap_password
```

### Параметры конфигурации

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `LOG_LEVEL` | Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL) | INFO |
| `LOG_HANDLERS` | Обработчики (console, file, database, rotating_file) | console,file |
| `DB_TYPE` | Тип БД (sqlite, postgresql) | sqlite |
| `LOG_JSON_FORMAT` | JSON формат логов | false |
| `LOG_CONTEXT` | Добавлять контекстную информацию | true |

## 🔧 Продвинутые возможности

### Автоматическое логирование функций

```python
from logging.logger import log_function_call

@log_function_call(log_args=True, log_result=True)
def process_data(data: dict) -> dict:
    # ваша логика
    return processed_data
```

### Переключение между базами данных

```bash
# SQLite (по умолчанию)
DB_TYPE=sqlite
SQLITE_PATH=logs/app_logs.db

# PostgreSQL
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=logs
DB_USER=postgres
DB_PASSWORD=password
```

### Настройка ротации файлов

```bash
LOG_HANDLERS=console,rotating_file
LOG_MAX_FILE_SIZE=10485760  # 10MB
LOG_BACKUP_COUNT=5
```

### JSON логирование

```bash
LOG_JSON_FORMAT=true
```

Результат:
```json
{
  "timestamp": "2024-01-15T10:30:00.123456",
  "level": "INFO",
  "logger": "my_module",
  "module": "my_module",
  "function": "my_function",
  "line": 42,
  "message": "Информационное сообщение",
  "thread": "MainThread",
  "process_id": 12345
}
```

## 📝 Примеры интеграции

### В CamundaClient

```python
# services/camunda_connector.py
from logging.logger import get_logger, log_function_call

class CamundaClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.logger = get_logger(__name__, extra_fields={
            'component': 'camunda_client',
            'base_url': base_url
        })
        self.logger.info("CamundaClient инициализирован")
    
    @log_function_call()
    def start_process(self, process_key: str, assign_list: list):
        self.logger.info(f"Запуск процесса {process_key} с назначенными пользователями: {assign_list}")
        
        try:
            # ваша логика запуска процесса
            process_id = self._execute_start_process(process_key, assign_list)
            self.logger.info(f"Процесс {process_key} успешно запущен, ID: {process_id}")
            return process_id
        except Exception as e:
            self.logger.error(f"Ошибка при запуске процесса {process_key}: {e}", exc_info=True)
            return None
    
    def _execute_start_process(self, process_key: str, assign_list: list):
        # ваша логика
        pass
```

### В LDAP модуле

```python
# auth/ldap_auth.py
from app_logging.logger import get_logger

logger = get_logger(__name__)

class LDAPAuthenticator:
    async def get_users(self):
        logger.info("Получение списка пользователей из LDAP")
    try:
        # ваша логика
        users = await _fetch_users_from_ldap()
        logger.info(f"Получено {len(users)} пользователей")
        return users
    except Exception as e:
        logger.error(f"Ошибка получения пользователей: {e}", exc_info=True)
        return []
```

### В NiceGUI страницах

```python
# pages/home_page.py
from logging.logger import get_logger

logger = get_logger(__name__, extra_fields={'component': 'ui'})

def content():
    logger.info("Загрузка главной страницы")
    try:
        # ваша логика
        logger.info("Главная страница загружена успешно")
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы: {e}", exc_info=True)
```

## 🔍 Просмотр логов

### Консоль
Логи выводятся в stdout с цветовой подсветкой уровней.

### Файлы
- **Обычный файл**: `logs/app.log`
- **Ротация файлов**: `logs/app.log.1`, `logs/app.log.2`, и т.д.

### База данных

#### SQLite
```bash
sqlite3 logs/app_logs.db
.tables
SELECT * FROM application_logs ORDER BY timestamp DESC LIMIT 10;
```

#### PostgreSQL
```sql
SELECT * FROM application_logs 
ORDER BY timestamp DESC 
LIMIT 10;
```

## 🛠️ Устранение неполадок

### Проблема: Логи не записываются в БД

**Решение:**
1. Проверьте настройки БД в .env
2. Убедитесь, что `LOG_HANDLERS` содержит `database`
3. Проверьте доступность БД

```python
# Проверка соединения
from logging.database import DatabaseAdapterFactory
from config.settings import config, DatabaseType

adapter = DatabaseAdapterFactory.create_adapter(
    config.logging.database.db_type,
    config.logging.database.database.dict()
)
print(f"Соединение с БД: {adapter.test_connection()}")
```

### Проблема: Ошибка импорта psycopg2

**Решение:**
```bash
# Установите psycopg2-binary вместо psycopg2
uv add psycopg2-binary
```

### Проблема: Логи не создаются

**Решение:**
1. Проверьте права на запись в директорию `logs/`
2. Убедитесь, что `setup_logging()` вызван в main.py
3. Проверьте уровень логирования в .env

### Проблема: Слишком много логов

**Решение:**
1. Увеличьте уровень логирования: `LOG_LEVEL=WARNING`
2. Настройте ротацию файлов
3. Используйте фильтры по компонентам

```python
# Логирование только для определенного компонента
logger = get_logger(__name__, extra_fields={'component': 'critical_module'})
```

## 📊 Мониторинг и аналитика

### Анализ логов в SQLite

```sql
-- Топ ошибок
SELECT level, message, COUNT(*) as count 
FROM application_logs 
WHERE level = 'ERROR' 
GROUP BY message 
ORDER BY count DESC;

-- Логи по времени
SELECT DATE(timestamp) as date, COUNT(*) as logs_count
FROM application_logs 
GROUP BY DATE(timestamp) 
ORDER BY date DESC;
```

### Анализ логов в PostgreSQL

```sql
-- Статистика по уровням
SELECT level, COUNT(*) as count 
FROM application_logs 
GROUP BY level 
ORDER BY count DESC;

-- Логи по компонентам
SELECT extra_data->>'component' as component, COUNT(*) as count
FROM application_logs 
WHERE extra_data IS NOT NULL
GROUP BY extra_data->>'component'
ORDER BY count DESC;
```

---

## 🎯 Заключение

Система логирования готова к использованию! Она автоматически создаст необходимые таблицы и директории при первом запуске. Просто настройте .env файл под ваши нужды и начинайте использовать логирование в своих модулях.
