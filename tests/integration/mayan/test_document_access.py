"""
Тесты управления доступом к документам в Mayan EDMS
"""
import pytest
from tests.fixtures.mock_mayan import mock_mayan_client, real_mayan_client


@pytest.mark.integration
@pytest.mark.mayan
class TestDocumentAccess:
    """Тесты управления доступом к документам"""
    
    @pytest.mark.asyncio
    async def test_grant_document_access_with_mock(self, mock_mayan_client):
        """Тест предоставления доступа к документу через мок"""
        document_id = '123'
        user_id = 'test_user'
        permission = 'view'
        
        result = await mock_mayan_client.grant_document_access(
            document_id=document_id,
            user_id=user_id,
            permission=permission
        )
        
        assert result is True
        # Проверяем, что метод был вызван
        mock_mayan_client.grant_document_access.assert_called_once_with(
            document_id=document_id,
            user_id=user_id,
            permission=permission
        )
    
    @pytest.mark.asyncio
    async def test_revoke_document_access_with_mock(self, mock_mayan_client):
        """Тест отзыва доступа к документу через мок"""
        document_id = '123'
        user_id = 'test_user'
        permission = 'view'
        
        result = await mock_mayan_client.revoke_document_access(
            document_id=document_id,
            user_id=user_id,
            permission=permission
        )
        
        assert result is True
        # Проверяем, что метод был вызван
        mock_mayan_client.revoke_document_access.assert_called_once_with(
            document_id=document_id,
            user_id=user_id,
            permission=permission
        )
    
    @pytest.mark.asyncio
    async def test_get_document_types(self, mock_mayan_client):
        """Тест получения типов документов"""
        document_types = await mock_mayan_client.get_document_types()
        
        assert isinstance(document_types, list)
        assert len(document_types) > 0
        
        # Проверяем структуру типа документа
        doc_type = document_types[0]
        assert 'id' in doc_type
        assert 'label' in doc_type
    
    @pytest.mark.asyncio
    async def test_get_cabinets(self, mock_mayan_client):
        """Тест получения кабинетов"""
        cabinets = await mock_mayan_client.get_cabinets()
        
        assert isinstance(cabinets, list)
        assert len(cabinets) > 0
        
        # Проверяем структуру кабинета
        cabinet = cabinets[0]
        assert 'id' in cabinet
        assert 'label' in cabinet

