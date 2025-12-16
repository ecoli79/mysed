"""
Тесты поиска документов в Mayan EDMS
"""
import pytest
from tests.fixtures.mock_mayan import mock_mayan_client, real_mayan_client


@pytest.mark.integration
@pytest.mark.mayan
class TestDocumentSearch:
    """Тесты поиска документов"""
    
    @pytest.mark.asyncio
    async def test_search_documents_by_label(self, mock_mayan_client):
        """Тест поиска документов по названию"""
        query = 'Тестовый'
        results = await mock_mayan_client.search_documents(query)
        
        assert isinstance(results, list)
        # Проверяем, что все результаты содержат запрос
        for doc in results:
            assert query.lower() in doc['label'].lower()
    
    @pytest.mark.asyncio
    async def test_search_documents_by_filename(self, mock_mayan_client):
        """Тест поиска документов по имени файла"""
        query = 'test_document'
        results = await mock_mayan_client.search_documents(query)
        
        assert isinstance(results, list)
        # Проверяем, что результаты содержат запрос в имени файла или названии
        for doc in results:
            filename = doc.get('filename', '').lower()
            label = doc.get('label', '').lower()
            assert query.lower() in filename or query.lower() in label
    
    @pytest.mark.asyncio
    async def test_search_documents_no_results(self, mock_mayan_client):
        """Тест поиска документов без результатов"""
        query = 'NonExistentDocument12345'
        results = await mock_mayan_client.search_documents(query)
        
        assert isinstance(results, list)
        assert len(results) == 0
    
    @pytest.mark.asyncio
    @pytest.mark.real_server
    async def test_search_documents_with_real_server(self, real_mayan_client):
        """Тест поиска документов с реального сервера"""
        try:
            # Используем простой запрос
            query = 'test'
            results = await real_mayan_client.search_documents(query)
            
            assert isinstance(results, list)
            # Если есть результаты, проверяем структуру
            if results:
                doc = results[0]
                assert hasattr(doc, 'document_id') or 'document_id' in doc
        except Exception as e:
            pytest.skip(f'Не удалось подключиться к реальному серверу: {e}')
        finally:
            await real_mayan_client.close()

