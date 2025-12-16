"""
Page Object для страницы входа
"""
from playwright.async_api import Page
from typing import Optional


class LoginPage:
    """Page Object для страницы входа в систему"""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def navigate_to(self, base_url: str):
        """Переходит на страницу входа"""
        try:
            await self.page.goto(f'{base_url}/login', timeout=10000, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
        except Exception as e:
            raise Exception(f'Не удалось перейти на страницу входа {base_url}/login: {e}')
    
    async def fill_username(self, username: str):
        """Заполняет поле имени пользователя"""
        try:
            username_input = self.page.locator('input[placeholder*="пользователя"], input[placeholder*="Пользователя"], input[type="text"]').first
            await username_input.wait_for(state='visible', timeout=5000)
            await username_input.fill(username)
        except Exception as e:
            # Пробуем альтернативные селекторы
            try:
                username_input = self.page.locator('input').first
                await username_input.wait_for(state='visible', timeout=5000)
                await username_input.fill(username)
            except:
                raise Exception(f'Не удалось найти поле имени пользователя: {e}')
    
    async def fill_password(self, password: str):
        """Заполняет поле пароля"""
        try:
            password_input = self.page.locator('input[type="password"]').first
            await password_input.wait_for(state='visible', timeout=5000)
            await password_input.fill(password)
        except Exception as e:
            raise Exception(f'Не удалось найти поле пароля: {e}')
    
    async def click_login_button(self):
        """Нажимает кнопку входа"""
        try:
            login_button = self.page.locator('button:has-text("Войти"), button:has-text("Вход"), button[type="submit"]').first
            await login_button.wait_for(state='visible', timeout=5000)
            await login_button.click()
        except Exception as e:
            raise Exception(f'Не удалось найти или нажать кнопку входа: {e}')
    
    async def login(self, username: str, password: str):
        """Выполняет полный процесс входа"""
        await self.fill_username(username)
        await self.fill_password(password)
        await self.click_login_button()
    
    async def get_status_message(self) -> Optional[str]:
        """Получает сообщение о статусе входа"""
        try:
            status_label = self.page.locator('text=/Пожалуйста|Проверка|Успешный|не найден|Неверный/').first
            await status_label.wait_for(state='visible', timeout=5000)
            return await status_label.text_content()
        except:
            return None
    
    async def is_login_successful(self, base_url: str) -> bool:
        """Проверяет, успешен ли вход (редирект на главную страницу)"""
        try:
            await self.page.wait_for_url(f'{base_url}/**', timeout=10000)
            # Проверяем, что мы не на странице входа
            current_url = self.page.url
            return '/login' not in current_url
        except:
            return False
    
    async def wait_for_redirect(self, base_url: str, timeout: int = 10000):
        """Ждет редиректа после входа"""
        try:
            await self.page.wait_for_url(f'{base_url}/**', timeout=timeout)
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
        except Exception as e:
            # Логируем текущий URL для отладки
            current_url = self.page.url
            raise Exception(f'Таймаут ожидания редиректа. Текущий URL: {current_url}, ошибка: {e}')

