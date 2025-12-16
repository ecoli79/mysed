"""
Конфигурация и фикстуры для E2E тестов
"""
import pytest
import asyncio
import subprocess
import time
import os
import sys
from pathlib import Path
from typing import Generator, AsyncGenerator

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


# Используем function scope вместо session для избежания проблем с event loop
@pytest.fixture
async def playwright() -> AsyncGenerator[Playwright, None]:
    """Запускает Playwright"""
    print('[E2E] Инициализация Playwright...')
    try:
        async with async_playwright() as p:
            print('[E2E] Playwright инициализирован')
            yield p
            print('[E2E] Playwright закрыт')
    except Exception as e:
        print(f'[E2E] Ошибка инициализации Playwright: {e}')
        raise


@pytest.fixture
async def browser(playwright: Playwright) -> AsyncGenerator[Browser, None]:
    """Создает браузер для тестов"""
    print('[E2E] Запуск браузера Chromium...')
    try:
        browser = await asyncio.wait_for(
            playwright.chromium.launch(headless=True),
            timeout=30.0
        )
        print('[E2E] Браузер запущен')
        yield browser
        print('[E2E] Закрытие браузера...')
        await browser.close()
        print('[E2E] Браузер закрыт')
    except asyncio.TimeoutError:
        print('[E2E] Таймаут запуска браузера')
        raise Exception('Таймаут запуска браузера. Проверьте установку Playwright: uv run playwright install chromium')
    except Exception as e:
        print(f'[E2E] Ошибка запуска браузера: {e}')
        raise


@pytest.fixture
async def browser_context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """Создает контекст браузера для каждого теста"""
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        locale='ru-RU',
    )
    yield context
    await context.close()


@pytest.fixture
async def page(browser_context: BrowserContext) -> AsyncGenerator[Page, None]:
    """Создает страницу для каждого теста"""
    page = await browser_context.new_page()
    # Устанавливаем таймауты
    page.set_default_timeout(10000)  # 10 секунд
    page.set_default_navigation_timeout(10000)
    yield page
    await page.close()


@pytest.fixture(scope='session')
def test_app_url(request) -> str:
    """URL тестового приложения"""
    # Сначала проверяем параметры командной строки
    url = request.config.getoption('--TEST_APP_URL', default=None)
    
    # Если не указан в командной строке, берем из переменных окружения
    if url is None:
        url = os.getenv('TEST_APP_URL', 'http://localhost:8080')
    skip_if_unavailable = os.getenv('E2E_SKIP_IF_UNAVAILABLE', 'true').lower() == 'true'
    
    # Проверяем доступность приложения синхронно с коротким таймаутом
    import socket
    from urllib.parse import urlparse
    
    print(f'\n[E2E] Проверка доступности приложения: {url}')
    
    # Парсим URL
    parsed = urlparse(url)
    host = parsed.hostname or 'localhost'
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    
    # Быстрая проверка доступности порта
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)  # Короткий таймаут
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            # Порт недоступен
            if skip_if_unavailable:
                pytest.skip(f'Приложение недоступно: {url} (порт {port} закрыт).\n'
                           f'Запустите приложение: python main.py')
            else:
                pytest.fail(f'Приложение недоступно: {url} (порт {port} закрыт)')
        
        print(f'[E2E] Порт {port} доступен, проверяем HTTP ответ...')
        
        # Проверяем HTTP ответ
        import httpx
        try:
            with httpx.Client(timeout=2.0, follow_redirects=True) as client:
                response = client.get(url)
                print(f'[E2E] Приложение доступно, статус: {response.status_code}')
                if response.status_code >= 500:
                    if skip_if_unavailable:
                        pytest.skip(f'Приложение недоступно: {url} (статус {response.status_code})')
                    else:
                        pytest.fail(f'Приложение недоступно: {url} (статус {response.status_code})')
        except httpx.TimeoutException:
            if skip_if_unavailable:
                pytest.skip(f'Таймаут подключения к {url}. Убедитесь, что приложение запущено.')
            else:
                pytest.fail(f'Таймаут подключения к {url}')
        except Exception as e:
            if skip_if_unavailable:
                pytest.skip(f'Ошибка HTTP подключения: {e}')
            else:
                pytest.fail(f'Ошибка HTTP подключения: {e}')
                
    except socket.timeout:
        if skip_if_unavailable:
            pytest.skip(f'Таймаут проверки порта {port}. Убедитесь, что приложение запущено на {url}')
        else:
            pytest.fail(f'Таймаут проверки порта {port}')
    except Exception as e:
        if skip_if_unavailable:
            pytest.skip(f'Ошибка проверки доступности: {e}')
        else:
            pytest.fail(f'Ошибка проверки доступности: {e}')
    
    return url


@pytest.fixture(scope='session')
def test_user_credentials(request):
    """Учетные данные тестового пользователя"""
    # Сначала проверяем параметры командной строки
    username = request.config.getoption('--TEST_USERNAME', default=None)
    password = request.config.getoption('--TEST_PASSWORD', default=None)
    
    # Если не указаны в командной строке, берем из переменных окружения
    if username is None:
        username = os.getenv('TEST_USERNAME')
    if password is None:
        password = os.getenv('TEST_PASSWORD')
    
    # Если все еще не указаны, используем значения по умолчанию
    if username is None:
        username = 'test_user'
    if password is None:
        password = 'test_password'
    
    credentials = {
        'username': username,
        'password': password,
    }
    
    # Логируем (без пароля для безопасности)
    print(f'\n[E2E] Используются учетные данные: username={username}, password={"*" * len(password) if password else "не указан"}')
    
    return credentials


@pytest.fixture
async def authenticated_page(page: Page, test_app_url: str, test_user_credentials: dict):
    """Создает аутентифицированную страницу"""
    import asyncio
    import time
    
    print('[E2E] Начало аутентификации...')
    
    # Переходим на страницу входа
    await page.goto(f'{test_app_url}/login', wait_until='domcontentloaded')
    
    # Ждем загрузки формы входа
    await page.wait_for_selector('input[placeholder*="пользователя"], input[placeholder*="Пользователя"]', timeout=10000)
    
    # Заполняем форму
    username_input = page.locator('input[placeholder*="пользователя"], input[placeholder*="Пользователя"]').first
    password_input = page.locator('input[type="password"]').first
    
    await username_input.fill(test_user_credentials['username'])
    await password_input.fill(test_user_credentials['password'])
    
    # Нажимаем кнопку входа
    login_button = page.locator('button:has-text("Войти"), button:has-text("Вход")').first
    await login_button.click()
    
    # Ждем обработки (может появиться сообщение о статусе)
    await page.wait_for_timeout(2000)
    
    # Проверяем сообщение о статусе
    try:
        status_message = page.locator('text=/Пожалуйста|Проверка|Успешный|не найден|Неверный|ошибка|Ошибка/').first
        await status_message.wait_for(state='visible', timeout=3000)
        message_text = await status_message.text_content()
        print(f'[E2E] Сообщение о статусе: {message_text}')
        
        if message_text and any(keyword in message_text.lower() for keyword in ['ошибка', 'неверный', 'не найден', 'error']):
            await page.screenshot(path='authenticated_page_login_error.png')
            raise Exception(f'Ошибка входа: {message_text}')
    except:
        pass  # Сообщение может не появиться, это нормально
    
    # Ждем редиректа (уход со страницы /login)
    # Редирект происходит через 1 секунду после успешного входа
    print('[E2E] Ожидание редиректа после входа...')
    start_time = time.time()
    timeout_seconds = 10.0
    
    while True:
        current_url = page.url
        if '/login' not in current_url:
            # Редирект произошел
            print(f'[E2E] Редирект произошел. Текущий URL: {current_url}')
            await page.wait_for_load_state('domcontentloaded', timeout=5000)
            break
        
        # Проверяем таймаут
        if time.time() - start_time > timeout_seconds:
            # Делаем скриншот для отладки
            await page.screenshot(path='authenticated_page_error.png')
            raise Exception(f'Таймаут ожидания редиректа после входа. Текущий URL: {current_url}')
        
        await asyncio.sleep(0.2)
    
    # Дополнительная задержка для сохранения токена на сервере
    print('[E2E] Ожидание сохранения токена на сервере...')
    await page.wait_for_timeout(1000)
    
    # Дополнительная проверка: пытаемся перейти на защищенную страницу
    # чтобы убедиться, что аутентификация работает
    print('[E2E] Проверка аутентификации через попытку доступа к защищенной странице...')
    try:
        await page.goto(f'{test_app_url}/mayan_documents', wait_until='domcontentloaded', timeout=10000)
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        
        # Проверяем, не произошел ли редирект на /login
        final_url = page.url
        if '/login' in final_url:
            await page.screenshot(path='authenticated_page_auth_check_failed.png')
            # Получаем содержимое страницы для отладки
            try:
                content = await page.content()
                print(f'[E2E] Содержимое страницы (первые 500 символов): {content[:500]}')
            except:
                pass
            raise Exception(f'Аутентификация не работает: произошел редирект на /login при попытке доступа к защищенной странице. URL: {final_url}')
        
        print('[E2E] Аутентификация успешна!')
    except Exception as e:
        if '/login' in page.url:
            await page.screenshot(path='authenticated_page_auth_check_failed.png')
            raise Exception(f'Ошибка при проверке аутентификации: {e}. Текущий URL: {page.url}')
        raise
    
    return page

