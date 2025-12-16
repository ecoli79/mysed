"""
Моки для Mayan EDMS REST API
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Any, Optional
from tests.fixtures.test_data import TEST_DOCUMENTS


class MockMayanClient:
    """Мок клиента Mayan EDMS для тестирования"""
    
    def __init__(self, base_url: str = 'http://localhost:8000',
                 username: str = None, password: str = None,
                 api_token: str = None):
        self.base_url = base_url
        self.api_url = f'{base_url}/api/v4/'
        self.username = username
        self.password = password
        self.api_token = api_token
        
        # Хранилище для моков данных
        self._documents: List[Dict[str, Any]] = TEST_DOCUMENTS.copy()
        self._document_types: List[Dict[str, Any]] = [
            {'id': 1, 'label': 'Входящие'},
            {'id': 2, 'label': 'Исходящие'},
        ]
        self._cabinets: List[Dict[str, Any]] = [
            {'id': 1, 'label': 'Входящие письма'},
            {'id': 2, 'label': 'Архив'},
        ]
        self._uploaded_documents: List[Dict[str, Any]] = []
        
        # Настраиваем моки методов
        self._setup_mocks()
    
    def _setup_mocks(self):
        """Настраивает моки для всех методов"""
        # Документы
        self.get_documents = AsyncMock(side_effect=self._get_documents_impl)
        self.get_document = AsyncMock(side_effect=self._get_document_impl)
        self.upload_document = AsyncMock(side_effect=self._upload_document_impl)
        self.delete_document = AsyncMock(side_effect=self._delete_document_impl)
        
        # Поиск документов
        self.search_documents = AsyncMock(side_effect=self._search_documents_impl)
        
        # Типы документов
        self.get_document_types = AsyncMock(side_effect=self._get_document_types_impl)
        self.get_cabinets = AsyncMock(side_effect=self._get_cabinets_impl)
        
        # Доступ к документам
        self.grant_document_access = AsyncMock(side_effect=self._grant_document_access_impl)
        self.revoke_document_access = AsyncMock(side_effect=self._revoke_document_access_impl)
        
        # Файлы документов
        self.get_document_file = AsyncMock(side_effect=self._get_document_file_impl)
        
        # Закрытие клиента
        self.close = AsyncMock()
        self.__aenter__ = AsyncMock(return_value=self)
        self.__aexit__ = AsyncMock(return_value=None)
    
    async def _get_documents_impl(self, page: int = 1, page_size: int = 100, **kwargs):
        """Имитация получения списка документов"""
        start = (page - 1) * page_size
        end = start + page_size
        return self._documents[start:end]
    
    async def _get_document_impl(self, document_id: str):
        """Имитация получения документа по ID"""
        from services.mayan_connector import MayanDocument
        
        doc = next((d for d in self._documents if d['document_id'] == document_id), None)
        if doc:
            return MayanDocument(
                document_id=doc['document_id'],
                label=doc['label'],
                file_latest_filename=doc['file_latest_filename'],
            )
        return None
    
    async def _upload_document_impl(self, file_content: bytes, filename: str,
                                   document_type_id: int = None, cabinet_id: int = None,
                                   label: str = None):
        """Имитация загрузки документа"""
        document_id = str(len(self._uploaded_documents) + 200)  # Начинаем с 200
        file_size = len(file_content) if isinstance(file_content, bytes) else file_content.__len__() if hasattr(file_content, '__len__') else 0
        document = {
            'document_id': document_id,
            'label': label or filename,
            'filename': filename,
            'file_latest_filename': filename,
            'document_type': 'Входящие',
            'cabinet': 'Входящие письма',
            'file_size': file_size,
        }
        self._uploaded_documents.append(document)
        self._documents.append(document)
        return document
    
    async def _delete_document_impl(self, document_id: str):
        """Имитация удаления документа"""
        self._documents = [d for d in self._documents if d['document_id'] != document_id]
        self._uploaded_documents = [d for d in self._uploaded_documents if d['document_id'] != document_id]
        return True
    
    async def _search_documents_impl(self, query: str, **kwargs):
        """Имитация поиска документов"""
        results = []
        query_lower = query.lower()
        for doc in self._documents:
            if query_lower in doc['label'].lower() or query_lower in doc.get('filename', '').lower():
                results.append(doc)
        return results
    
    async def _get_document_types_impl(self):
        """Имитация получения типов документов"""
        return self._document_types
    
    async def _get_cabinets_impl(self):
        """Имитация получения кабинетов"""
        return self._cabinets
    
    async def _grant_document_access_impl(self, document_id: str, user_id: str, permission: str):
        """Имитация предоставления доступа к документу"""
        return True
    
    async def _revoke_document_access_impl(self, document_id: str, user_id: str, permission: str):
        """Имитация отзыва доступа к документу"""
        return True
    
    async def _get_document_file_impl(self, document_id: str, file_id: str = None):
        """Имитация получения файла документа"""
        doc = next((d for d in self._documents if d['document_id'] == document_id), None)
        if doc:
            return b'Mock PDF content for document ' + document_id.encode()
        return None


@pytest.fixture
def mock_mayan_client():
    """Фикстура для создания мок клиента Mayan"""
    return MockMayanClient()


@pytest.fixture
def real_mayan_client(test_config, use_real_servers):
    """Фикстура для создания реального клиента Mayan (если разрешено)"""
    if not use_real_servers:
        pytest.skip('Требуется реальный сервер Mayan (установите TEST_USE_REAL_SERVERS=true)')
    
    from services.mayan_connector import MayanClient
    
    return MayanClient(
        base_url=test_config.mayan_url,
        username=test_config.mayan_username or None,
        password=test_config.mayan_password or None,
        api_token=test_config.mayan_api_token or None,
        verify_ssl=False
    )

