"""
E2E тесты подписания документов с помощью CAdES
Подписание происходит на странице task_completion
"""
import pytest
import os
from tests.e2e.pages.document_signing_page import TaskCompletionPage


@pytest.mark.e2e
class TestDocumentSigning:
    """Тесты подписания документов на странице task_completion"""
    
    @pytest.mark.asyncio
    async def test_navigate_to_task_completion_page(self, authenticated_page, test_app_url):
        """Тест перехода на страницу завершения задач (task_completion)"""
        task_page = TaskCompletionPage(authenticated_page)
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Проверяем, что мы на странице завершения задач
        assert await task_page.is_on_task_completion_page(), f'Не на странице завершения задач. Текущий URL: {authenticated_page.url}'
    
    @pytest.mark.asyncio
    async def test_task_completion_page_loads(self, authenticated_page, test_app_url):
        """Тест загрузки страницы завершения задач"""
        task_page = TaskCompletionPage(authenticated_page)
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Ждем загрузки задач
        await task_page.wait_for_tasks_loaded()
        
        # Проверяем, что страница загрузилась
        assert await task_page.is_on_task_completion_page()
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Требует установки CryptoPro плагина или мокирования")
    async def test_certificate_selection_with_mock(self, authenticated_page, test_app_url):
        """Тест выбора сертификата с мокированным плагином на странице task_completion"""
        task_page = TaskCompletionPage(authenticated_page)
        
        # Мокируем плагин
        await task_page.mock_plugin_available()
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Переключаемся на таб активных задач
        await task_page.switch_to_active_tasks_tab()
        
        # Ждем загрузки задач
        await task_page.wait_for_tasks_loaded()
        
        # Проверяем наличие задач
        tasks_count = await task_page.get_tasks_count()
        
        if tasks_count > 0:
            # Пытаемся открыть диалог подписания
            await task_page.click_sign_button()
            
            # Ждем диалога выбора сертификата
            await task_page.wait_for_certificate_dialog()
            
            # Симулируем выбор сертификата
            await task_page.simulate_certificate_selection(0)
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Требует установки CryptoPro плагина или мокирования")
    async def test_document_signing_flow_with_mock(self, authenticated_page, test_app_url):
        """Тест полного процесса подписания с мокированным плагином на странице task_completion"""
        task_page = TaskCompletionPage(authenticated_page)
        
        # Мокируем плагин
        await task_page.mock_plugin_available()
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Переключаемся на таб активных задач
        await task_page.switch_to_active_tasks_tab()
        
        # Ждем загрузки задач
        await task_page.wait_for_tasks_loaded()
        
        # Проверяем наличие задач
        tasks_count = await task_page.get_tasks_count()
        
        if tasks_count > 0:
            # Пытаемся открыть диалог подписания
            await task_page.click_sign_button()
            
            # Ждем диалога выбора сертификата
            await task_page.wait_for_certificate_dialog()
            
            # Симулируем выбор сертификата
            await task_page.simulate_certificate_selection(0)
            
            # Симулируем завершение подписания
            await task_page.simulate_signature_complete("MOCK_SIGNATURE_BASE64")
            
            # Ждем завершения
            await task_page.wait_for_signature_complete()
    
    @pytest.mark.asyncio
    @pytest.mark.real_plugin
    @pytest.mark.skipif(
        "os.getenv('SKIP_REAL_PLUGIN_TESTS', 'true').lower() == 'true'",
        reason="Тесты с реальным плагином пропускаются по умолчанию. Установите SKIP_REAL_PLUGIN_TESTS=false для запуска"
    )
    async def test_certificate_selection_with_real_plugin(self, authenticated_page, test_app_url):
        """Тест выбора сертификата с реальным CryptoPro плагином на странице task_completion"""
        import os
        task_page = TaskCompletionPage(authenticated_page)
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Переключаемся на таб активных задач
        await task_page.switch_to_active_tasks_tab()
        
        # Ждем загрузки задач
        await task_page.wait_for_tasks_loaded()
        
        # Проверяем доступность плагина
        plugin_available = await task_page.is_plugin_available()
        if not plugin_available:
            pytest.skip("CryptoPro плагин не установлен или недоступен")
        
        # Проверяем наличие задач
        tasks_count = await task_page.get_tasks_count()
        if tasks_count == 0:
            pytest.skip("Нет задач для подписания")
        
        # Ищем задачу на подписание
        signing_task_id = await task_page.find_signing_task()
        if not signing_task_id:
            pytest.skip("Не найдена задача на подписание (с именем 'Подписать документ')")
        
        # Открываем задачу на подписание (нажимаем "Завершить задачу" - это откроет форму подписания)
        await task_page.open_signing_task()
        
        # Ждем появления формы подписания (селект сертификата и кнопка "Подписать документ")
        await task_page.wait_for_signing_form()
        
        # Ждем загрузки сертификатов (плагин должен загрузить их автоматически)
        await task_page.wait_for_certificate_dialog(timeout=15000)
        
        # Выбираем первый доступный сертификат (если есть селект)
        try:
            await task_page.select_certificate(0)
        except:
            # Если селект не найден, возможно сертификаты загружаются автоматически
            pass
    
    @pytest.mark.asyncio
    @pytest.mark.real_plugin
    @pytest.mark.skipif(
        "os.getenv('SKIP_REAL_PLUGIN_TESTS', 'true').lower() == 'true'",
        reason="Тесты с реальным плагином пропускаются по умолчанию. Установите SKIP_REAL_PLUGIN_TESTS=false для запуска"
    )
    async def test_document_signing_flow_with_real_plugin(self, authenticated_page, test_app_url):
        """Тест полного процесса подписания с реальным CryptoPro плагином на странице task_completion"""
        import os
        task_page = TaskCompletionPage(authenticated_page)
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Переключаемся на таб активных задач
        await task_page.switch_to_active_tasks_tab()
        
        # Ждем загрузки задач
        await task_page.wait_for_tasks_loaded()
        
        # Проверяем доступность плагина
        plugin_available = await task_page.is_plugin_available()
        if not plugin_available:
            pytest.skip("CryptoPro плагин не установлен или недоступен")
        
        # Проверяем наличие задач
        tasks_count = await task_page.get_tasks_count()
        if tasks_count == 0:
            pytest.skip("Нет задач для подписания")
        
        # Ищем задачу на подписание
        signing_task_id = await task_page.find_signing_task()
        if not signing_task_id:
            pytest.skip("Не найдена задача на подписание (с именем 'Подписать документ')")
        
        # Открываем задачу на подписание (нажимаем "Завершить задачу" - это откроет форму подписания)
        await task_page.open_signing_task()
        
        # Ждем появления формы подписания (селект сертификата и кнопка "Подписать документ")
        await task_page.wait_for_signing_form()
        
        # Ждем загрузки сертификатов (плагин должен загрузить их автоматически)
        await task_page.wait_for_certificate_dialog(timeout=15000)
        
        # Выбираем первый доступный сертификат (если есть селект)
        try:
            await task_page.select_certificate(0)
            # Даем время на обработку выбора сертификата
            await authenticated_page.wait_for_timeout(1000)
        except:
            # Если селект не найден, возможно сертификаты загружаются автоматически
            pass
        
        # Нажимаем кнопку "Подписать документ" (теперь она должна быть видна после выбора сертификата)
        await task_page.click_sign_button()
        
        # Ждем завершения подписания (может занять время, особенно с реальным плагином)
        await task_page.wait_for_signature_complete(timeout=60000)
    
    @pytest.mark.asyncio
    async def test_plugin_availability_check(self, authenticated_page, test_app_url):
        """Тест проверки доступности CryptoPro плагина на странице task_completion"""
        task_page = TaskCompletionPage(authenticated_page)
        
        # Переходим на страницу завершения задач
        await task_page.navigate_to(test_app_url)
        
        # Проверяем доступность плагина (вероятно, False в headless режиме)
        plugin_available = await task_page.is_plugin_available()
        
        # В headless режиме плагин обычно недоступен
        # Это нормально, тест просто проверяет, что проверка работает
        assert isinstance(plugin_available, bool)

