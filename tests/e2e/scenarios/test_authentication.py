"""
E2E тесты авторизации в приложении
"""
import pytest
import asyncio
from tests.e2e.pages.login_page import LoginPage


@pytest.mark.e2e
class TestAuthentication:
    """Тесты авторизации в приложении"""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # Максимальное время выполнения теста (30 секунд)
    async def test_successful_login(self, page, test_app_url, test_user_credentials):
        """Тест успешного входа в систему"""
        login_page = LoginPage(page)
        
        print(f'\n[E2E] Начало теста входа. URL: {test_app_url}')
        print(f'[E2E] Текущий URL до перехода: {page.url}')
        
        try:
            # Переходим на страницу входа
            print('[E2E] Переход на страницу входа...')
            try:
                await asyncio.wait_for(
                    login_page.navigate_to(test_app_url),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                pytest.fail(f'Таймаут перехода на страницу входа: {test_app_url}/login')
            print(f'[E2E] Текущий URL после перехода: {page.url}')
            
            # Выполняем вход
            print('[E2E] Заполнение формы входа...')
            await login_page.login(
                username=test_user_credentials['username'],
                password=test_user_credentials['password']
            )
            print('[E2E] Форма заполнена, ожидание обработки...')
            
            # Ждем немного для обработки
            await page.wait_for_timeout(3000)
            print(f'[E2E] Текущий URL после входа: {page.url}')
            
            # Проверяем редирект (может быть не сразу)
            try:
                print('[E2E] Ожидание редиректа...')
                await login_page.wait_for_redirect(test_app_url, timeout=15000)
                print(f'[E2E] Редирект произошел. Текущий URL: {page.url}')
            except Exception as redirect_error:
                # Если редирект не произошел, проверяем текущий URL
                current_url = page.url
                print(f'[E2E] Редирект не произошел. Текущий URL: {current_url}')
                if '/login' in current_url:
                    # Проверяем сообщение об ошибке
                    status_message = await login_page.get_status_message()
                    if status_message:
                        pytest.fail(f'Вход не удался: {status_message}. URL: {current_url}')
                    else:
                        # Делаем скриншот для отладки
                        await page.screenshot(path='test_successful_login_error.png')
                        pytest.fail(f'Вход не удался, остались на странице входа: {current_url}')
                else:
                    # Возможно, редирект уже произошел, но мы его не поймали
                    print(f'[E2E] Редирект возможно уже произошел: {current_url}')
            
            # Проверяем, что вход успешен
            is_successful = await login_page.is_login_successful(test_app_url)
            assert is_successful, f'Вход не успешен, текущий URL: {page.url}'
            
            # Проверяем, что мы не на странице входа
            assert '/login' not in page.url, f'Остались на странице входа: {page.url}'
            print('[E2E] Тест входа успешно завершен')
        except Exception as e:
            # Делаем скриншот для отладки
            screenshot_path = 'test_successful_login_error.png'
            await page.screenshot(path=screenshot_path)
            print(f'[E2E] Ошибка в тесте. Скриншот сохранен: {screenshot_path}')
            print(f'[E2E] Текущий URL: {page.url}')
            try:
                content = await page.content()
                print(f'[E2E] Текст страницы (первые 500 символов): {content[:500]}')
            except:
                pass
            raise
    
    @pytest.mark.asyncio
    async def test_login_with_invalid_credentials(self, page, test_app_url):
        """Тест входа с неверными учетными данными"""
        login_page = LoginPage(page)
        
        # Переходим на страницу входа
        await login_page.navigate_to(test_app_url)
        
        # Пытаемся войти с неверными данными
        await login_page.login(
            username='invalid_user',
            password='invalid_password'
        )
        
        # Ждем сообщения об ошибке
        await page.wait_for_timeout(2000)  # Даем время на обработку
        
        # Проверяем, что мы все еще на странице входа
        assert '/login' in page.url or 'login' in page.url.lower()
        
        # Проверяем наличие сообщения об ошибке
        status_message = await login_page.get_status_message()
        assert status_message is not None
        assert any(keyword in status_message.lower() for keyword in ['ошибка', 'неверный', 'не найден', 'error'])
    
    @pytest.mark.asyncio
    async def test_login_with_empty_fields(self, page, test_app_url):
        """Тест входа с пустыми полями"""
        login_page = LoginPage(page)
        
        # Переходим на страницу входа
        await login_page.navigate_to(test_app_url)
        
        # Пытаемся войти без заполнения полей
        await login_page.click_login_button()
        
        # Ждем сообщения об ошибке
        await page.wait_for_timeout(1000)
        
        # Проверяем наличие сообщения о необходимости заполнить поля
        status_message = await login_page.get_status_message()
        assert status_message is not None
        assert any(keyword in status_message.lower() for keyword in ['заполните', 'поле', 'fill', 'required'])
    
    @pytest.mark.asyncio
    async def test_login_page_elements(self, page, test_app_url):
        """Тест наличия элементов на странице входа"""
        login_page = LoginPage(page)
        
        # Переходим на страницу входа
        await login_page.navigate_to(test_app_url)
        
        # Проверяем наличие полей ввода
        username_input = page.locator('input[placeholder*="пользователя"], input[placeholder*="Пользователя"]').first
        password_input = page.locator('input[type="password"]').first
        login_button = page.locator('button:has-text("Войти"), button:has-text("Вход")').first
        
        assert await username_input.is_visible()
        assert await password_input.is_visible()
        assert await login_button.is_visible()

