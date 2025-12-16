"""
Моки для Email операций
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Any, Optional
from datetime import datetime
from tests.fixtures.test_data import TEST_EMAILS


class MockEmailClient:
    """Мок клиента Email для тестирования"""
    
    def __init__(self, server: str = 'localhost', port: int = 993,
                 username: str = None, password: str = None,
                 use_ssl: bool = True, protocol: str = 'imap'):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.protocol = protocol
        self.connection = None
        
        # Хранилище для моков данных
        self._emails: List[Dict[str, Any]] = TEST_EMAILS.copy()
        self._unread_emails: List[Dict[str, Any]] = TEST_EMAILS.copy()
        self._connected = False
        
        # Настраиваем моки методов
        self._setup_mocks()
    
    def _setup_mocks(self):
        """Настраивает моки для всех методов"""
        # Подключение
        self.connect = AsyncMock(side_effect=self._connect_impl)
        self.disconnect = AsyncMock(side_effect=self._disconnect_impl)
        self.test_connection = AsyncMock(side_effect=self._test_connection_impl)
        
        # Получение писем
        self.fetch_emails = AsyncMock(side_effect=self._fetch_emails_impl)
        self.fetch_unread_emails = AsyncMock(side_effect=self._fetch_unread_emails_impl)
        
        # Пометка как прочитанное
        self.mark_as_read = AsyncMock(side_effect=self._mark_as_read_impl)
        
        # Контекстный менеджер
        self.__aenter__ = AsyncMock(return_value=self)
        self.__aexit__ = AsyncMock(return_value=None)
    
    async def _connect_impl(self):
        """Имитация подключения к почтовому серверу"""
        if self.username and self.password:
            self._connected = True
            return True
        return False
    
    async def _disconnect_impl(self):
        """Имитация отключения от почтового сервера"""
        self._connected = False
    
    async def _test_connection_impl(self):
        """Имитация проверки подключения"""
        return self._connected
    
    async def _fetch_emails_impl(self, max_count: int = 10, unread_only: bool = False):
        """Имитация получения писем"""
        from models import IncomingEmail
        from datetime import datetime
        
        emails_to_return = self._unread_emails if unread_only else self._emails
        emails_to_return = emails_to_return[:max_count]
        
        result = []
        for email_data in emails_to_return:
            # Парсим дату из строки
            received_date = datetime.fromisoformat(email_data['received_date'].replace('Z', '+00:00'))
            
            email = IncomingEmail(
                message_id=email_data['message_id'],
                from_address=email_data['from_address'],
                subject=email_data['subject'],
                body=email_data['body'],
                received_date=received_date,
                attachments=email_data.get('attachments', [])
            )
            result.append(email)
        
        return result
    
    async def _fetch_unread_emails_impl(self, max_count: int = 10):
        """Имитация получения непрочитанных писем"""
        return await self._fetch_emails_impl(max_count=max_count, unread_only=True)
    
    async def _mark_as_read_impl(self, message_id: str):
        """Имитация пометки письма как прочитанного"""
        # Удаляем из списка непрочитанных
        self._unread_emails = [e for e in self._unread_emails if e['message_id'] != message_id]
        return True


@pytest.fixture
def mock_email_client():
    """Фикстура для создания мок клиента Email"""
    return MockEmailClient(
        server='localhost',
        port=993,
        username='test@example.com',
        password='test_password',
        use_ssl=True,
        protocol='imap'
    )


@pytest.fixture
def real_email_client(test_config, use_real_servers):
    """Фикстура для создания реального клиента Email (если разрешено)"""
    if not use_real_servers:
        pytest.skip('Требуется реальный Email сервер (установите TEST_USE_REAL_SERVERS=true)')
    
    from services.email_client import EmailClient
    
    return EmailClient.create_default()

