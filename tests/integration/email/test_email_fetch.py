"""
Тесты получения email писем
"""
import pytest
from tests.fixtures.mock_email import mock_email_client, real_email_client


@pytest.mark.integration
@pytest.mark.email
class TestEmailFetch:
    """Тесты получения email писем"""
    
    @pytest.mark.asyncio
    async def test_connect_to_email_server(self, mock_email_client):
        """Тест подключения к почтовому серверу"""
        result = await mock_email_client.connect()
        
        assert result is True
        assert mock_email_client._connected is True
    
    @pytest.mark.asyncio
    async def test_fetch_emails_with_mock(self, mock_email_client):
        """Тест получения писем через мок"""
        await mock_email_client.connect()
        
        emails = await mock_email_client.fetch_emails(max_count=5)
        
        assert isinstance(emails, list)
        assert len(emails) > 0
        
        # Проверяем структуру письма
        email = emails[0]
        assert hasattr(email, 'message_id')
        assert hasattr(email, 'from_address')
        assert hasattr(email, 'subject')
        assert hasattr(email, 'body')
    
    @pytest.mark.asyncio
    async def test_fetch_unread_emails(self, mock_email_client):
        """Тест получения непрочитанных писем"""
        await mock_email_client.connect()
        
        unread_emails = await mock_email_client.fetch_unread_emails(max_count=5)
        
        assert isinstance(unread_emails, list)
        # Проверяем, что все письма из списка непрочитанных
        assert len(unread_emails) <= len(mock_email_client._unread_emails)
    
    @pytest.mark.asyncio
    async def test_mark_as_read(self, mock_email_client):
        """Тест пометки письма как прочитанного"""
        await mock_email_client.connect()
        
        # Получаем непрочитанные письма
        unread_before = await mock_email_client.fetch_unread_emails()
        assert len(unread_before) > 0
        
        # Помечаем первое письмо как прочитанное
        message_id = unread_before[0].message_id
        result = await mock_email_client.mark_as_read(message_id)
        
        assert result is True
        
        # Проверяем, что письмо больше не в списке непрочитанных
        unread_after = await mock_email_client.fetch_unread_emails()
        unread_ids = [e.message_id for e in unread_after]
        assert message_id not in unread_ids
    
    @pytest.mark.asyncio
    async def test_disconnect_from_email_server(self, mock_email_client):
        """Тест отключения от почтового сервера"""
        await mock_email_client.connect()
        assert mock_email_client._connected is True
        
        await mock_email_client.disconnect()
        assert mock_email_client._connected is False

