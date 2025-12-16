# Интеграционные тесты

Этот каталог содержит интеграционные тесты для проверки взаимодействия между компонентами системы и внешними сервисами.

## Структура

```
tests/
├── integration/          # Интеграционные тесты
│   ├── api/             # Тесты FastAPI endpoints
│   ├── camunda/         # Тесты интеграции с Camunda
│   ├── mayan/           # Тесты интеграции с Mayan EDMS
│   ├── ldap/            # Тесты интеграции с LDAP
│   ├── email/           # Тесты обработки email
│   └── workflows/       # Тесты полных workflows
├── e2e/                 # E2E тесты (браузерные)
│   ├── pages/           # Page Object Model
│   └── scenarios/       # Полные пользовательские сценарии
├── fixtures/            # Моки и тестовые данные
└── conftest.py          # Глобальная конфигурация pytest
```

## Установка зависимостей

Проект использует `uv` для управления зависимостями. Тесты используют то же окружение, что и основной проект.

```bash
# Синхронизация зависимостей (включая тестовые) из pyproject.toml
uv sync --extra test

# Или если зависимости уже установлены, просто активируйте окружение
source .venv/bin/activate  # Linux/Mac
# или
.venv\Scripts\activate  # Windows
```

## Настройка

1. Скопируйте `.env.test.example` в `.env.test`:
```bash
cp .env.test.example .env.test
```

2. Отредактируйте `.env.test` и укажите настройки для вашего окружения:
```bash
# Использовать реальные серверы для чтения (true/false)
TEST_USE_REAL_SERVERS=false

# URL тестовых серверов (если TEST_USE_REAL_SERVERS=true)
TEST_CAMUNDA_URL=http://localhost:8080
TEST_MAYAN_URL=http://localhost:8000
TEST_LDAP_SERVER=localhost
TEST_EMAIL_SERVER=localhost
```

## Запуск тестов

### Все интеграционные тесты
```bash
# С активированным окружением
pytest tests/integration/

# Или через uv run (без активации окружения)
uv run pytest tests/integration/
```

### Тесты конкретного компонента
```bash
# Только Camunda
uv run pytest tests/integration/camunda/

# Только Mayan
uv run pytest tests/integration/mayan/

# Только LDAP
uv run pytest tests/integration/ldap/

# Только Email
uv run pytest tests/integration/email/

# Только API
uv run pytest tests/integration/api/

# Только workflows
uv run pytest tests/integration/workflows/
```

### Быстрые тесты (без медленных)
```bash
uv run pytest tests/integration/ -m "not slow"
```

### Тесты с реальными серверами
```bash
TEST_USE_REAL_SERVERS=true uv run pytest tests/integration/ -m real_server
```

### С покрытием кода
```bash
uv run pytest tests/integration/ --cov=services --cov=api_router --cov-report=html
```

### Параллельный запуск
```bash
uv run pytest tests/integration/ -n auto
```

### E2E тесты (браузерные)
```bash
# Установка Playwright браузеров (один раз)
uv run playwright install chromium

# Запуск E2E тестов (требует запущенного приложения)
TEST_APP_URL=http://localhost:8080 uv run pytest tests/e2e/ -v

# См. tests/e2e/README.md для подробностей
```

## Маркеры pytest

- `@pytest.mark.integration` - Интеграционные тесты
- `@pytest.mark.camunda` - Тесты Camunda
- `@pytest.mark.mayan` - Тесты Mayan EDMS
- `@pytest.mark.ldap` - Тесты LDAP
- `@pytest.mark.email` - Тесты Email
- `@pytest.mark.workflow` - Тесты полных workflows
- `@pytest.mark.slow` - Медленные тесты
- `@pytest.mark.real_server` - Требуют реального сервера

## Принципы тестирования

### Чтение с реальных серверов
- GET-запросы к Camunda, Mayan, LDAP выполняются с реальными серверами (если `TEST_USE_REAL_SERVERS=true`)
- Используется для проверки структуры данных и доступности сервисов

### Запись через моки
- POST/PUT/DELETE операции выполняются через моки для безопасности
- Предотвращает изменение данных на реальных серверах

### Изоляция тестов
- Каждый тест независим
- Используются фикстуры для setup/teardown
- Тестовые данные не влияют друг на друга

## Примеры

### Пример 1: Тест получения задач из Camunda
```python
@pytest.mark.integration
@pytest.mark.camunda
async def test_get_user_tasks(real_camunda_client):
    tasks = await real_camunda_client.get_tasks(assignee='test_user')
    assert isinstance(tasks, list)
```

### Пример 2: Тест завершения задачи через мок
```python
@pytest.mark.integration
@pytest.mark.camunda
async def test_complete_task(mock_camunda_client):
    result = await mock_camunda_client.complete_task(
        task_id='task_123',
        variables={'status': 'completed'}
    )
    assert result is True
```

### Пример 3: Тест полного workflow
```python
@pytest.mark.integration
@pytest.mark.workflow
async def test_document_review_workflow(
    mock_camunda_client,
    real_mayan_client,
    test_user
):
    # 1. Создаем процесс (мок)
    process_id = await mock_camunda_client.start_process(...)
    
    # 2. Получаем документ из Mayan (реальный)
    document = await real_mayan_client.get_document(document_id='123')
    
    # 3. Завершаем задачу (мок)
    await mock_camunda_client.complete_task(...)
```

## CI/CD

Тесты готовы к интеграции в CI/CD pipeline. Пример конфигурации для GitHub Actions:

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v1
        with:
          version: "latest"
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: uv sync --extra test
      - run: uv run pytest tests/integration/ -m "not slow" --cov=services --cov-report=xml
```

## Отчеты

После запуска тестов с покрытием, отчеты доступны в:
- HTML: `htmlcov/index.html`
- XML: `coverage.xml` (для CI/CD)

## Устранение неполадок

### Тесты не запускаются
- Убедитесь, что установлены все зависимости: `uv sync --extra test`
- Проверьте, что Python версии 3.11 или выше
- Убедитесь, что виртуальное окружение активировано: `source .venv/bin/activate`
- Или используйте `uv run` для запуска команд в окружении проекта: `uv run pytest tests/integration/`

### Ошибки подключения к серверам
- Проверьте настройки в `.env.test`
- Убедитесь, что серверы доступны (если `TEST_USE_REAL_SERVERS=true`)
- Используйте моки по умолчанию: `TEST_USE_REAL_SERVERS=false`

### Тесты падают с ошибками импорта
- Убедитесь, что вы запускаете тесты из корневой директории проекта
- Проверьте, что все пути в `sys.path` настроены правильно

