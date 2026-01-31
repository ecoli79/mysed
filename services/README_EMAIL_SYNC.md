# Сервис синхронизации Email с Mayan EDMS

## Описание

Сервис автоматически подключается к почтовому серверу (IMAP/POP3), получает входящие письма от разрешенных отправителей и сохраняет вложения в Mayan EDMS как документы. Сервис проверяет дубликаты по SHA256 хешу файлов, используя локальный SQLite кеш для быстрой проверки.

## Основные возможности

- ✅ Поддержка IMAP и POP3 протоколов
- ✅ Фильтрация писем по отправителям (whitelist)
- ✅ Автоматическое сохранение вложений в Mayan EDMS
- ✅ Проверка дубликатов по хешу SHA256
- ✅ Обработка только непрочитанных писем (опционально)
- ✅ Логирование всех операций
- ✅ Обработка ошибок и повторные попытки

## Требования

- Python 3.11+
- Доступ к почтовому серверу (IMAP/POP3)
- Доступ к Mayan EDMS API
- Настроенные типы документов и кабинеты в Mayan EDMS

## Настройка

### 1. Переменные окружения

Добавьте следующие переменные в файл `.env`:

```bash
# Настройки Mayan EDMS
MAYAN_URL=http://localhost:8000
MAYAN_USERNAME=admin
MAYAN_PASSWORD=admin
# ИЛИ используйте API токен
MAYAN_API_TOKEN=your_api_token_here

# Тип документа для входящих писем (должен существовать в Mayan)
MAYAN_INCOMING_DOCUMENT_TYPE=Входящие

# Кабинет для входящих писем (должен существовать в Mayan)
MAYAN_INCOMING_CABINET=Входящие письма

# Настройки почтового сервера
EMAIL_SERVER=imap.example.com
EMAIL_PORT=993
EMAIL_USERNAME=your_email@example.com
EMAIL_PASSWORD=your_password
EMAIL_USE_SSL=true
EMAIL_PROTOCOL=imap  # или pop3

# Список разрешенных отправителей (через запятую)
# Если пусто, обрабатываются письма от всех отправителей
EMAIL_ALLOWED_SENDERS=sender1@example.com,sender2@example.com

# Интервал проверки почты в секундах (для cron/планировщика)
EMAIL_CHECK_INTERVAL=300
```

### 2. Настройка Mayan EDMS

Убедитесь, что в Mayan EDMS созданы:

1. **Тип документа** с названием, указанным в `MAYAN_INCOMING_DOCUMENT_TYPE` (по умолчанию "Входящие")
2. **Кабинет** с названием, указанным в `MAYAN_INCOMING_CABINET` (по умолчанию "Входящие письма")

## Использование

### Базовый запуск

```bash
# Обработка непрочитанных писем
python -m services.sync_email

# Обработка всех писем (включая прочитанные)
python -m services.sync_email --include-read

# Обработка максимум 10 писем за раз
python -m services.sync_email --max-emails 10
```

### Тестовый режим

Проверка подключений без обработки писем:

```bash
python -m services.sync_email --dry-run
```

### Параметры командной строки

| Параметр | Описание |
|----------|----------|
| `--dry-run` | Тестовый режим: только проверка подключений, письма не обрабатываются |
| `--max-emails N` | Максимальное количество писем для обработки за один запуск |
| `--include-read` | Обрабатывать все письма, включая прочитанные. При этом проверяет, какие вложения уже обработаны и пропускает их |

## Автоматический запуск (Cron)

Для автоматической проверки почты можно настроить cron:

```bash
# Проверка каждые 5 минут
*/5 * * * * cd /path/to/project && /path/to/python -m services.sync_email >> /var/log/email_sync.log 2>&1

# Проверка каждый час
0 * * * * cd /path/to/project && /path/to/python -m services.sync_email --max-emails 50 >> /var/log/email_sync.log 2>&1
```

## Как это работает

1. **Подключение к почтовому серверу** - сервис подключается к указанному почтовому серверу
2. **Получение писем** - получает непрочитанные письма (или все, если указан `--include-read`)
3. **Фильтрация по отправителям** - проверяет, разрешен ли отправитель (если указан `EMAIL_ALLOWED_SENDERS`)
4. **Обработка вложений** - для каждого вложения:
   - Вычисляет SHA256 хеш файла
   - Проверяет дубликаты в локальном SQLite кеше
   - Если дубликат не найден, проверяет в Mayan EDMS
   - Если файл уникален, создает документ в Mayan EDMS
   - Сохраняет хеш в кеш для будущих проверок
5. **Маркировка писем** - помечает письма как прочитанные после успешной обработки

## Структура метаданных

Каждый документ в Mayan EDMS содержит метаданные в поле `description`:

```json
{
  "incoming_from_email": "sender@example.com",
  "email_subject": "Тема письма",
  "email_received_date": "2024-01-15T10:30:00",
  "email_message_id": "<message-id@example.com>",
  "attachment_filename": "document.pdf",
  "attachment_number": 1,
  "total_attachments": 2,
  "attachment_hash": "sha256_hash_here",
  "attachment_size": 12345,
  "processed_date": "2024-01-15T10:35:00"
}
```

## Проверка дубликатов

Сервис использует двухуровневую проверку дубликатов:

1. **Локальный кеш (SQLite)** - быстрая проверка по хешу SHA256
2. **Mayan EDMS** - полная проверка по хешу и метаданным

Кеш хранится в `logs/document_hash_cache.db` и автоматически синхронизируется с Mayan EDMS при первом запуске.

## Логирование

Логи сохраняются в:
- Консоль (по умолчанию)
- Файл `logs/app.log` (если настроено)

Уровень логирования настраивается через переменную `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR, CRITICAL).

## Устранение неполадок

### Ошибка подключения к почтовому серверу

```
Проверьте:
- EMAIL_SERVER, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD
- EMAIL_USE_SSL (true для порта 993, false для 143)
- Доступность почтового сервера из сети
```

### Ошибка подключения к Mayan EDMS

```
Проверьте:
- MAYAN_URL, MAYAN_USERNAME, MAYAN_PASSWORD (или MAYAN_API_TOKEN)
- Доступность Mayan EDMS из сети
- Правильность учетных данных
```

### Документы не создаются

```
Проверьте:
- Существует ли тип документа MAYAN_INCOMING_DOCUMENT_TYPE
- Существует ли кабинет MAYAN_INCOMING_CABINET
- Достаточно ли прав у пользователя для создания документов
```

### Все письма пропускаются

```
Проверьте:
- EMAIL_ALLOWED_SENDERS - возможно, список слишком ограничен
- Логи для деталей о том, почему письма пропускаются
```

### Дубликаты не обнаруживаются

```
Проверьте:
- Кеш хешей: logs/document_hash_cache.db
- Попробуйте очистить кеш и перезапустить синхронизацию
```

## Примеры использования

### Обработка писем от конкретного отправителя

```bash
# В .env
EMAIL_ALLOWED_SENDERS=important@example.com

# Запуск
python -m services.sync_email
```

### Обработка всех писем (включая старые)

```bash
python -m services.sync_email --include-read
```

### Ограничение количества писем за раз

```bash
python -m services.sync_email --max-emails 20
```

## API

Сервис можно использовать программно:

```python
from services.sync_email import sync_emails

# Синхронизация писем
result = await sync_emails(
    dry_run=False,
    max_emails=10,
    include_read=False
)

print(f"Обработано: {result['processed']} писем")
print(f"Сохранено: {result['attachments_saved']} вложений")
```

## Дополнительная информация

- Кеш хешей: `logs/document_hash_cache.db`
- Логи: `logs/app.log`
- Модуль обработки: `services/email_processor.py`
- Модуль клиента: `services/email_client.py`

