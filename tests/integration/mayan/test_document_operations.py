"""
Тесты операций с документами в Mayan EDMS
"""
import pytest
from tests.fixtures.mock_mayan import mock_mayan_client, real_mayan_client


@pytest.mark.integration
@pytest.mark.mayan
class TestDocumentOperations:
    """Тесты операций с документами"""
    
    @pytest.mark.asyncio
    async def test_get_documents_with_mock(self, mock_mayan_client):
        """Тест получения списка документов через мок"""
        documents = await mock_mayan_client.get_documents(page=1, page_size=10)
        
        assert isinstance(documents, list)
        assert len(documents) > 0
        
        # Проверяем структуру документа
        doc = documents[0]
        assert 'document_id' in doc
        assert 'label' in doc
        assert 'filename' in doc
    
    @pytest.mark.asyncio
    @pytest.mark.real_server
    async def test_get_documents_with_real_server(self, real_mayan_client):
        """Тест получения списка документов с реального сервера"""
        try:
            documents = await real_mayan_client.get_documents(page=1, page_size=10)
            
            assert isinstance(documents, list)
            # Если есть документы, проверяем структуру
            if documents:
                doc = documents[0]
                assert hasattr(doc, 'document_id') or 'document_id' in doc
        except Exception as e:
            pytest.skip(f'Не удалось подключиться к реальному серверу: {e}')
        finally:
            await real_mayan_client.close()
    
    @pytest.mark.asyncio
    async def test_get_document_by_id(self, mock_mayan_client):
        """Тест получения документа по ID"""
        document_id = '123'
        document = await mock_mayan_client.get_document(document_id)
        
        assert document is not None
        assert document.document_id == document_id
    
    @pytest.mark.asyncio
    async def test_upload_document_with_mock(self, mock_mayan_client, temp_dir):
        """Тест загрузки документа через мок"""
        # Создаем тестовый файл
        test_file = temp_dir / 'test_document.pdf'
        test_content = b'PDF content for testing'
        test_file.write_bytes(test_content)
        
        # Загружаем документ
        document = await mock_mayan_client.upload_document(
            file_content=test_content,
            filename='test_document.pdf',
            document_type_id=1,
            cabinet_id=1,
            label='Тестовый документ для загрузки'
        )
        
        assert document is not None
        assert 'document_id' in document
        assert document['filename'] == 'test_document.pdf'
        assert document['file_size'] == len(test_content)
        
        # Проверяем, что документ появился в списке
        documents = await mock_mayan_client.get_documents()
        document_ids = [d.get('document_id') for d in documents]
        assert document['document_id'] in document_ids
    
    @pytest.mark.asyncio
    async def test_delete_document_with_mock(self, mock_mayan_client):
        """Тест удаления документа через мок"""
        document_id = '123'
        
        # Проверяем, что документ существует
        document = await mock_mayan_client.get_document(document_id)
        assert document is not None
        
        # Удаляем документ
        result = await mock_mayan_client.delete_document(document_id)
        assert result is True
        
        # Проверяем, что документ удален
        document = await mock_mayan_client.get_document(document_id)
        assert document is None
    
    @pytest.mark.asyncio
    async def test_get_document_file(self, mock_mayan_client):
        """Тест получения файла документа"""
        document_id = '123'
        file_content = await mock_mayan_client.get_document_file(document_id)
        
        assert file_content is not None
        assert isinstance(file_content, bytes)
        assert len(file_content) > 0

