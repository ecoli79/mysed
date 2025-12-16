# E2E (End-to-End) тесты

E2E тесты проверяют полные пользовательские сценарии через браузер.

## Установка зависимостей

```bash
# Установка Playwright
uv sync --extra test  # Обратите внимание: --extra test (не tests!)
uv run playwright install chromium
```

## Настройка

1. **Запустите приложение** (в отдельном терминале):
```bash
python main.py
# Или с указанием порта
PORT=8080 python main.py
```

2. **Установите переменные окружения** (опционально):
```bash
export TEST_APP_URL=http://localhost:8080
export TEST_USERNAME=test_user
export TEST_PASSWORD=test_password

# По умолчанию тесты пропускаются, если приложение недоступно
# Для принудительного запуска (с ошибкой вместо пропуска):
export E2E_SKIP_IF_UNAVAILABLE=false
```

**Важно**: E2E тесты автоматически проверяют доступность приложения перед запуском. Если приложение не запущено, тесты будут пропущены (skipped) с информативным сообщением.

## Запуск тестов

### Все E2E тесты
```bash
uv run pytest tests/e2e/ -v
```

### Конкретный тест
```bash
uv run pytest tests/e2e/scenarios/test_authentication.py -v
```

### С отображением браузера (не headless)
```bash
HEADLESS=false uv run pytest tests/e2e/ -v
```

## Структура

```
tests/e2e/
├── conftest.py              # Фикстуры для браузера и приложения
├── pages/                   # Page Object Model
│   ├── login_page.py       # Страница входа
│   └── mayan_documents_page.py  # Страница документов
└── scenarios/               # E2E сценарии
    ├── test_authentication.py  # Тесты авторизации
    └── test_documents_list.py  # Тесты списка документов
```

## Page Object Model

Каждая страница имеет свой Page Object класс с методами для взаимодействия:
- `navigate_to()` - переход на страницу
- Методы для заполнения форм
- Методы для проверки состояния

## Примечания

- E2E тесты требуют запущенного приложения
- Используйте тестовые учетные данные
- Тесты могут быть медленнее интеграционных
- Используйте моки для внешних сервисов в E2E окружении

