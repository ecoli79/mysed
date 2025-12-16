"""
E2E тесты получения списка документов
"""
import pytest
from tests.e2e.pages.mayan_documents_page import MayanDocumentsPage
from tests.e2e.pages.login_page import LoginPage


@pytest.mark.e2e
class TestDocumentsList:
    """Тесты получения списка документов"""
    
    @pytest.mark.asyncio
    async def test_navigate_to_documents_page(self, authenticated_page, test_app_url):
        """Тест перехода на страницу документов"""
        documents_page = MayanDocumentsPage(authenticated_page)
        
        # Переходим на страницу документов
        await documents_page.navigate_to(test_app_url)
        
        # Проверяем, что мы на странице документов
        assert await documents_page.is_on_documents_page()
    
    @pytest.mark.asyncio
    async def test_documents_page_loads(self, authenticated_page, test_app_url):
        """Тест загрузки страницы документов"""
        documents_page = MayanDocumentsPage(authenticated_page)
        
        # Переходим на страницу документов
        await documents_page.navigate_to(test_app_url)
        
        # Ждем загрузки документов
        await documents_page.wait_for_documents_loaded()
        
        # Проверяем, что страница загрузилась
        assert await documents_page.is_documents_list_visible()
    
    @pytest.mark.asyncio
    async def test_documents_list_displayed(self, authenticated_page, test_app_url):
        """Тест отображения списка документов"""
        documents_page = MayanDocumentsPage(authenticated_page)
        
        # Переходим на страницу документов
        await documents_page.navigate_to(test_app_url)
        
        # Ждем загрузки
        await documents_page.wait_for_documents_loaded()
        await documents_page.wait_for_loading_complete()
        
        # Проверяем, что список документов отображается
        assert await documents_page.is_documents_list_visible()
        
        # Получаем количество документов
        documents_count = await documents_page.get_documents_count()
        
        # Документы могут быть или не быть (зависит от тестовых данных)
        # Главное - что страница загрузилась и список отображается
        assert documents_count >= 0
    
    @pytest.mark.asyncio
    async def test_documents_list_after_login(self, page, test_app_url, test_user_credentials):
        """Тест получения списка документов после входа"""
        # Сначала входим в систему
        login_page = LoginPage(page)
        await login_page.navigate_to(test_app_url)
        await login_page.login(
            username=test_user_credentials['username'],
            password=test_user_credentials['password']
        )
        await login_page.wait_for_redirect(test_app_url)
        
        # Переходим на страницу документов
        documents_page = MayanDocumentsPage(page)
        await documents_page.navigate_to(test_app_url)
        
        # Ждем загрузки
        await documents_page.wait_for_documents_loaded()
        await documents_page.wait_for_loading_complete()
        
        # Проверяем, что страница загрузилась
        assert await documents_page.is_on_documents_page()
        assert await documents_page.is_documents_list_visible()
    
    @pytest.mark.asyncio
    async def test_documents_page_title(self, authenticated_page, test_app_url):
        """Тест заголовка страницы документов"""
        documents_page = MayanDocumentsPage(authenticated_page)
        
        # Переходим на страницу документов
        await documents_page.navigate_to(test_app_url)
        
        # Ждем загрузки
        await documents_page.wait_for_documents_loaded()
        
        # Проверяем заголовок страницы
        title = await documents_page.get_page_title()
        assert title is not None
        assert len(title) > 0

