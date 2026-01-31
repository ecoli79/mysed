# Сервис мониторинга директории и синхронизации с Mayan EDMS

## Описание

Сервис автоматически отслеживает указанную директорию на предмет новых файлов и загружает их в Mayan EDMS как документы. Сервис использует мониторинг в реальном времени (watchdog) и проверяет дубликаты по SHA256 хешу файлов перед загрузкой.

## Основные возможности

- ✅ Мониторинг директории в реальном времени (watchdog)
- ✅ Однократное сканирование существующих файлов
- ✅ Рекурсивный мониторинг поддиректорий
- ✅ Фильтрация по расширениям файлов
- ✅ Проверка дубликатов по хешу SHA256
- ✅ Автоматическая загрузка в Mayan EDMS
- ✅ Логирование всех операций
- ✅ Обработка ошибок и повторные попытки

## Требования

- Python 3.11+
- Доступ к Mayan EDMS API
- Настроенные типы документов и кабинеты в Mayan EDMS
- Библиотека `watchdog` (устанавливается автоматически)

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

# Тип документа для файлов из директории (должен существовать в Mayan)
MAYAN_DIRECTORY_DOCUMENT_TYPE=Входящие

# Кабинет для файлов из директории (должен существовать в Mayan)
MAYAN_DIRECTORY_CABINET=Файлы из директории

# Настройки мониторинга директории (опционально, можно указать в командной строке)
DIRECTORY_WATCH_PATH=/path/to/watch/directory
DIRECTORY_WATCH_RECURSIVE=false
DIRECTORY_WATCH_EXTENSIONS=.pdf,.docx,.doc
DIRECTORY_SCAN_EXISTING=true
```

### 2. Настройка Mayan EDMS

Убедитесь, что в Mayan EDMS созданы:

1. **Тип документа** с названием, указанным в `MAYAN_DIRECTORY_DOCUMENT_TYPE` (по умолчанию "Входящие")
2. **Кабинет** с названием, указанным в `MAYAN_DIRECTORY_CABINET` (по умолчанию "Файлы из директории")

## Использование

### Базовый запуск

```bash
# Однократное сканирование директории
python -m services.sync_directory /path/to/directory --scan-existing

# Постоянный мониторинг директории
python -m services.sync_directory /path/to/directory --watch --scan-existing

# Мониторинг без сканирования существующих файлов
python -m services.sync_directory /path/to/directory --watch
```

### Параметры командной строки

| Параметр | Описание |
|----------|----------|
| `directory` | Путь к директории для мониторинга (обязательный) |
| `--watch` | Запустить постоянный мониторинг (иначе однократное сканирование) |
| `--scan-existing` | Сканировать существующие файлы при запуске |
| `--recursive` | Мониторить поддиректории рекурсивно |
| `--extensions EXT` | Фильтр расширений файлов (через запятую, например: `.pdf,.docx,.doc`) |
| `--dry-run` | Тестовый режим: только проверка подключений, файлы не обрабатываются |

### Примеры использования

#### Однократное сканирование

```bash
# Сканировать все файлы в директории
python -m services.sync_directory /var/incoming --scan-existing

# Сканировать только PDF и DOCX файлы
python -m services.sync_directory /var/incoming --scan-existing --extensions ".pdf,.docx"
```

#### Постоянный мониторинг

```bash
# Мониторинг с автоматической обработкой новых файлов
python -m services.sync_directory /var/incoming --watch --scan-existing

# Мониторинг только PDF файлов
python -m services.sync_directory /var/incoming --watch --extensions ".pdf"

# Рекурсивный мониторинг всех поддиректорий
python -m services.sync_directory /var/incoming --watch --recursive
```

#### Тестовый режим

```bash
# Проверка подключений без обработки файлов
python -m services.sync_directory /var/incoming --dry-run
```

## Автоматический запуск (Systemd)

Для постоянного мониторинга рекомендуется использовать systemd service:

```ini
# /etc/systemd/system/directory-sync.service
[Unit]
Description=Directory Sync Service for Mayan EDMS
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/project
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python -m services.sync_directory /var/incoming --watch --scan-existing
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация сервиса:

```bash
sudo systemctl enable directory-sync.service
sudo systemctl start directory-sync.service
sudo systemctl status directory-sync.service
```

## Как это работает

1. **Инициализация** - сервис подключается к Mayan EDMS и инициализирует кеш хешей
2. **Сканирование существующих** (если `--scan-existing`) - обрабатывает все файлы в директории
3. **Мониторинг** (если `--watch`) - отслеживает изменения в директории в реальном времени
4. **Обработка файлов** - для каждого нового файла:
   - Вычисляет SHA256 хеш файла
   - Проверяет дубликаты в локальном SQLite кеше
   - Если дубликат не найден, проверяет в Mayan EDMS
   - Если файл уникален, создает документ в Mayan EDMS
   - Сохраняет хеш в кеш для будущих проверок
5. **Логирование** - все операции логируются

## Структура метаданных

Каждый документ в Mayan EDMS содержит метаданные в поле `description`:

```json
{
  "source": "directory",
  "file_path": "/var/incoming/document.pdf",
  "file_name": "document.pdf",
  "file_directory": "/var/incoming",
  "file_hash": "sha256_hash_here",
  "file_size": 12345,
  "processed_date": "2024-01-15T10:35:00"
}
```

## Проверка дубликатов

Сервис использует двухуровневую проверку дубликатов:

1. **Локальный кеш (SQLite)** - быстрая проверка по хешу SHA256
2. **Mayan EDMS** - полная проверка по хешу и метаданным

Кеш хранится в `logs/document_hash_cache.db` и автоматически синхронизируется с Mayan EDMS при первом запуске.

## Фильтрация файлов

### По расширениям

```bash
# Только PDF и DOCX
python -m services.sync_directory /var/incoming --watch --extensions ".pdf,.docx"

# Только изображения
python -m services.sync_directory /var/incoming --watch --extensions ".jpg,.png,.gif"
```

### Рекурсивный поиск

```bash
# Мониторинг всех поддиректорий
python -m services.sync_directory /var/incoming --watch --recursive
```

## Логирование

Логи сохраняются в:
- Консоль (по умолчанию)
- Файл `logs/app.log` (если настроено)

Уровень логирования настраивается через переменную `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR, CRITICAL).

## Устранение неполадок

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
- Существует ли тип документа MAYAN_DIRECTORY_DOCUMENT_TYPE
- Существует ли кабинет MAYAN_DIRECTORY_CABINET
- Достаточно ли прав у пользователя для создания документов
- Логи для деталей об ошибках
```

### Файлы не обрабатываются

```
Проверьте:
- Права доступа к директории (чтение)
- Фильтр расширений (если указан)
- Логи для деталей
```

### Дубликаты не обнаруживаются

```
Проверьте:
- Кеш хешей: logs/document_hash_cache.db
- Попробуйте очистить кеш и перезапустить синхронизацию
```

### Ошибка "Директория не существует"

```
Проверьте:
- Правильность пути к директории
- Существование директории
- Права доступа
```

## Примеры использования

### Мониторинг папки входящих документов

```bash
# Постоянный мониторинг с обработкой существующих файлов
python -m services.sync_directory /var/incoming/documents --watch --scan-existing
```

### Обработка только PDF файлов

```bash
python -m services.sync_directory /var/incoming --watch --extensions ".pdf"
```

### Однократная обработка всех файлов

```bash
python -m services.sync_directory /var/incoming --scan-existing --recursive
```

### Мониторинг с фильтрацией и рекурсией

```bash
python -m services.sync_directory /var/incoming \
  --watch \
  --recursive \
  --extensions ".pdf,.docx,.xlsx" \
  --scan-existing
```

## API

Сервис можно использовать программно:

```python
from services.sync_directory import sync_directory

# Синхронизация директории
result = await sync_directory(
    watch_directory="/var/incoming",
    dry_run=False,
    scan_existing=True,
    recursive=False,
    file_extensions={'.pdf', '.docx'},
    watch_mode=True
)

print(f"Обработано: {result['processed']} файлов")
print(f"Пропущено: {result['skipped']} дубликатов")
```

## Производительность

- **Кеш хешей**: Проверка дубликатов через SQLite кеш выполняется мгновенно
- **Мониторинг**: Watchdog отслеживает изменения в реальном времени с минимальной задержкой
- **Обработка**: Файлы обрабатываются асинхронно через очередь задач

## Безопасность

- Проверка прав доступа к директории
- Валидация типов файлов
- Защита от race conditions при параллельной обработке
- Безопасное хранение хешей в SQLite

## Дополнительная информация

- Кеш хешей: `logs/document_hash_cache.db`
- Логи: `logs/app.log`
- Модуль обработки: `services/directory_processor.py`
- Модуль мониторинга: `services/directory_watcher.py`
- Модуль синхронизации: `services/sync_directory.py`

## Сравнение с Email сервисом

| Функция | Email Sync | Directory Sync |
|---------|------------|----------------|
| Источник данных | Почтовый сервер | Файловая система |
| Протокол | IMAP/POP3 | Watchdog |
| Фильтрация | По отправителям | По расширениям |
| Режим работы | Периодический | Постоянный/однократный |
| Проверка дубликатов | ✅ | ✅ |
| Кеш хешей | ✅ | ✅ |

Оба сервиса используют одинаковый механизм проверки дубликатов и кеширования хешей.

