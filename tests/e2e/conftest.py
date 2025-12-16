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
def test_app_url() -> str:
    """URL тестового приложения"""
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
def test_user_credentials():
    """Учетные данные тестового пользователя"""
    return {
        'username': os.getenv('TEST_USERNAME', 'test_user'),
        'password': os.getenv('TEST_PASSWORD', 'test_password'),
    }


@pytest.fixture
async def authenticated_page(page: Page, test_app_url: str, test_user_credentials: dict):
    """Создает аутентифицированную страницу"""
    # Переходим на страницу входа
    await page.goto(f'{test_app_url}/login')
    
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
    
    # Ждем редиректа на главную страницу
    await page.wait_for_url(f'{test_app_url}/**', timeout=10000)
    
    # Ждем загрузки главной страницы
    await page.wait_for_load_state('networkidle', timeout=10000)
    
    return page

