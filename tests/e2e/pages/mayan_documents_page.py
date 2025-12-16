"""
Page Object для страницы документов Mayan EDMS
"""
from playwright.async_api import Page
from typing import List, Optional


class MayanDocumentsPage:
    """Page Object для страницы документов Mayan EDMS"""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def navigate_to(self, base_url: str):
        """Переходит на страницу документов"""
        await self.page.goto(f'{base_url}/mayan_documents')
        await self.page.wait_for_load_state('networkidle')
    
    async def wait_for_documents_loaded(self, timeout: int = 30000):
        """Ждет загрузки списка документов"""
        # Ждем появления элементов документов или сообщения об отсутствии
        try:
            # Может быть таблица, список или сообщение "Нет документов"
            await self.page.wait_for_selector(
                'table, .document-item, .document-card, text="Нет документов", text="Документы не найдены"',
                timeout=timeout,
                state='visible'
            )
        except:
            # Если не найдено, возможно страница еще загружается
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
    
    async def get_documents_count(self) -> int:
        """Получает количество отображаемых документов"""
        try:
            # Ищем элементы документов (могут быть в таблице, списке или карточках)
            document_items = self.page.locator(
                'table tbody tr, .document-item, .document-card, [data-document-id]'
            )
            count = await document_items.count()
            return count
        except:
            return 0
    
    async def get_document_titles(self) -> List[str]:
        """Получает список названий документов"""
        try:
            # Ищем заголовки документов
            titles = []
            title_elements = self.page.locator(
                'table tbody tr td:first-child, .document-title, .document-label, [data-document-label]'
            )
            count = await title_elements.count()
            for i in range(count):
                text = await title_elements.nth(i).text_content()
                if text:
                    titles.append(text.strip())
            return titles
        except:
            return []
    
    async def is_documents_list_visible(self) -> bool:
        """Проверяет, виден ли список документов"""
        try:
            # Проверяем наличие элементов документов или сообщения об отсутствии
            has_documents = await self.page.locator('table, .document-item, .document-card').count() > 0
            has_no_documents_message = await self.page.locator('text=/Нет документов|Документы не найдены/').count() > 0
            return has_documents or has_no_documents_message
        except:
            return False
    
    async def wait_for_loading_complete(self, timeout: int = 30000):
        """Ждет завершения загрузки (исчезновения индикатора загрузки)"""
        try:
            # Ждем исчезновения индикатора загрузки
            loading_indicator = self.page.locator('.loading, .spinner, [data-loading="true"]')
            await loading_indicator.wait_for(state='hidden', timeout=timeout)
        except:
            # Если индикатора нет, просто ждем завершения сетевых запросов
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
    
    async def get_page_title(self) -> Optional[str]:
        """Получает заголовок страницы"""
        try:
            title = await self.page.title()
            return title
        except:
            return None
    
    async def is_on_documents_page(self) -> bool:
        """Проверяет, находимся ли мы на странице документов"""
        current_url = self.page.url
        return '/mayan_documents' in current_url

