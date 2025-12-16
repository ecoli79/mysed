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

2. **Установите переменные окружения** (ОБЯЗАТЕЛЬНО для тестов авторизации):
```bash
# Учетные данные для входа (используйте реальные учетные данные, под которыми вы авторизовывались)
export TEST_USERNAME='ваш_логин'
export TEST_PASSWORD='ваш_пароль'

# URL приложения (опционально, по умолчанию http://localhost:8080)
export TEST_APP_URL=http://localhost:8080

# По умолчанию тесты пропускаются, если приложение недоступно
# Для принудительного запуска (с ошибкой вместо пропуска):
export E2E_SKIP_IF_UNAVAILABLE=false
```

**Альтернативный способ:** Передача через параметры командной строки:
```bash
uv run pytest tests/e2e/ -v --TEST_USERNAME=ваш_логин --TEST_PASSWORD=ваш_пароль
```

**Проверка переменных окружения:**
```bash
python3 check_test_env.py
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
│   ├── mayan_documents_page.py  # Страница документов
│   └── document_signing_page.py  # Страница завершения задач (task_completion) - где происходит подписание
└── scenarios/               # E2E сценарии
    ├── test_authentication.py  # Тесты авторизации
    ├── test_documents_list.py  # Тесты списка документов
    └── test_document_signing.py  # Тесты подписания документов
```

## Page Object Model

Каждая страница имеет свой Page Object класс с методами для взаимодействия:
- `navigate_to()` - переход на страницу
- Методы для заполнения форм
- Методы для проверки состояния

## Тестирование подписания документов (CAdES)

**Важно**: Подписание документов происходит на странице `/task_completion` (завершение задач), а не на отдельной странице подписания.

Тестирование подписания документов с помощью CryptoPro CAdES плагина имеет особенности:

### Подходы к тестированию

1. **Интеграционные тесты API** (`tests/integration/api/test_document_signing_api.py`):
   - Тестируют обработку событий от CryptoPro плагина на сервере
   - Не требуют установки плагина
   - Используют мокированные данные подписи
   - Запуск: `uv run pytest tests/integration/api/test_document_signing_api.py -v`

2. **E2E тесты с мокированием** (`tests/e2e/scenarios/test_document_signing.py`):
   - Мокируют CryptoPro плагин через JavaScript
   - Тестируют UI взаимодействие без реального плагина
   - Работают в headless режиме
   - Запуск: `uv run pytest tests/e2e/scenarios/test_document_signing.py -v`

3. **E2E тесты с реальным плагином** (требует настройки):
   - Требуют установки CryptoPro ЭЦП Browser Plug-in
   - Требуют установки сертификата
   - Работают только в не-headless режиме
   - Запуск: 
     ```bash
     SKIP_REAL_PLUGIN_TESTS=false HEADLESS=false uv run pytest tests/e2e/scenarios/test_document_signing.py -v -m real_plugin
     ```

### Мокирование CryptoPro плагина

Для тестирования без реального плагина используется мокирование JavaScript API:

```python
# В тесте
signing_page = DocumentSigningPage(page)
await signing_page.mock_plugin_available()
await signing_page.simulate_certificate_selection(0)
await signing_page.simulate_signature_complete("MOCK_SIGNATURE")
```

### Ограничения

- **Headless режим**: CryptoPro плагин не работает в headless браузере
- **Требования к окружению**: Реальные тесты требуют Windows и установленного плагина
- **Сертификаты**: Для реальных тестов нужны тестовые сертификаты

## Примечания

- E2E тесты требуют запущенного приложения
- Используйте тестовые учетные данные
- Тесты могут быть медленнее интеграционных
- Используйте моки для внешних сервисов в E2E окружении
- Тесты подписания по умолчанию используют моки (помечены `@pytest.mark.skip`)

