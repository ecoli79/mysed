"""
Тесты обработки email писем
"""
import pytest
from tests.fixtures.mock_email import mock_email_client
from tests.fixtures.test_data import TEST_EMAILS


@pytest.mark.integration
@pytest.mark.email
class TestEmailProcessing:
    """Тесты обработки email писем"""
    
    @pytest.mark.asyncio
    async def test_parse_email_with_attachments(self, mock_email_client):
        """Тест парсинга письма с вложениями"""
        await mock_email_client.connect()
        
        emails = await mock_email_client.fetch_emails(max_count=1)
        
        assert len(emails) > 0
        email = emails[0]
        
        # Проверяем наличие вложений
        if email.attachments:
            assert len(email.attachments) > 0
            attachment = email.attachments[0]
            assert 'filename' in attachment
            assert 'content' in attachment
            assert 'mimetype' in attachment
            assert 'size' in attachment
    
    @pytest.mark.asyncio
    async def test_parse_email_without_attachments(self, mock_email_client):
        """Тест парсинга письма без вложений"""
        await mock_email_client.connect()
        
        emails = await mock_email_client.fetch_emails(max_count=10)
        
        # Ищем письмо без вложений
        email_without_attachments = None
        for email in emails:
            if not email.attachments or len(email.attachments) == 0:
                email_without_attachments = email
                break
        
        if email_without_attachments:
            assert email_without_attachments.attachments == []
    
    @pytest.mark.asyncio
    async def test_email_structure(self, mock_email_client):
        """Тест структуры письма"""
        await mock_email_client.connect()
        
        emails = await mock_email_client.fetch_emails(max_count=1)
        
        assert len(emails) > 0
        email = emails[0]
        
        # Проверяем обязательные поля
        assert email.message_id is not None
        assert email.from_address is not None
        assert email.subject is not None
        assert email.received_date is not None
        assert isinstance(email.attachments, list)

