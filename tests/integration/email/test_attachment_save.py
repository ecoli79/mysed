"""
Тесты сохранения вложений email в Mayan EDMS
"""
import pytest
from tests.fixtures.mock_email import mock_email_client
from tests.fixtures.mock_mayan import mock_mayan_client


@pytest.mark.integration
@pytest.mark.email
class TestAttachmentSave:
    """Тесты сохранения вложений"""
    
    @pytest.mark.asyncio
    async def test_save_attachment_to_mayan(self, mock_email_client, mock_mayan_client):
        """Тест сохранения вложения в Mayan через мок"""
        await mock_email_client.connect()
        
        # Получаем письмо с вложением
        emails = await mock_email_client.fetch_emails(max_count=10)
        email_with_attachment = None
        
        for email in emails:
            if email.attachments and len(email.attachments) > 0:
                email_with_attachment = email
                break
        
        if not email_with_attachment:
            pytest.skip('Нет писем с вложениями для тестирования')
        
        # Сохраняем первое вложение в Mayan
        attachment = email_with_attachment.attachments[0]
        document = await mock_mayan_client.upload_document(
            file_content=attachment['content'],
            filename=attachment['filename'],
            document_type_id=1,
            cabinet_id=1,
            label=f'Вложение из письма: {email_with_attachment.subject}'
        )
        
        assert document is not None
        assert 'document_id' in document
        assert document['filename'] == attachment['filename']
        # Размер должен соответствовать реальному размеру контента
        actual_size = len(attachment['content']) if isinstance(attachment['content'], bytes) else attachment.get('size', 0)
        assert document['file_size'] == actual_size
    
    @pytest.mark.asyncio
    async def test_save_multiple_attachments(self, mock_email_client, mock_mayan_client):
        """Тест сохранения нескольких вложений"""
        await mock_email_client.connect()
        
        emails = await mock_email_client.fetch_emails(max_count=10)
        saved_documents = []
        
        for email in emails:
            if email.attachments:
                for attachment in email.attachments:
                    document = await mock_mayan_client.upload_document(
                        file_content=attachment['content'],
                        filename=attachment['filename'],
                        document_type_id=1,
                        cabinet_id=1,
                        label=f'Вложение: {attachment["filename"]}'
                    )
                    saved_documents.append(document)
        
        # Проверяем, что все вложения сохранены
        assert len(saved_documents) > 0
        for doc in saved_documents:
            assert 'document_id' in doc

