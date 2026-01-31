"""
Фикстуры для тестов мониторинга директории
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

from services.directory_processor import DirectoryProcessor
from tests.fixtures.mock_mayan import MockMayanClient


@pytest.fixture
def temp_directory() -> Generator[Path, None, None]:
    """Создает временную директорию для тестов"""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # Очистка после теста
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_file(temp_directory: Path) -> Path:
    """Создает тестовый файл"""
    test_file = temp_directory / 'test_document.pdf'
    test_file.write_bytes(b'Test PDF content for testing')
    return test_file


@pytest.fixture
def sample_files(temp_directory: Path) -> list[Path]:
    """Создает несколько тестовых файлов"""
    files = []
    for i in range(3):
        test_file = temp_directory / f'test_document_{i}.pdf'
        test_file.write_bytes(f'Test PDF content {i}'.encode())
        files.append(test_file)
    return files


@pytest.fixture
def mock_directory_processor(mock_mayan_client_with_types):
    """Создает DirectoryProcessor с мок клиентом Mayan"""
    processor = DirectoryProcessor(mock_mayan_client_with_types)
    return processor


@pytest.fixture
def mock_mayan_client_with_types():
    """Создает мок клиента Mayan с типами документов и кабинетами для директории"""
    # Создаем новый экземпляр MockMayanClient напрямую
    client = MockMayanClient()
    
    # Добавляем типы документов и кабинеты для директории
    client._document_types.append({
        'id': 3,
        'label': 'Файлы из директории'
    })
    client._cabinets.append({
        'id': 3,
        'label': 'Файлы из директории'
    })
    
    # Мокируем create_document_with_file
    async def create_document_with_file_impl(**kwargs):
        document_id = str(len(client._uploaded_documents) + 300)
        file_content = kwargs.get('file_content', b'')
        filename = kwargs.get('filename', 'unknown')
        
        document = {
            'document_id': document_id,
            'label': kwargs.get('label', filename),
            'filename': filename,
            'file_latest_filename': filename,
            'file_size': len(file_content) if isinstance(file_content, bytes) else 0,
        }
        client._uploaded_documents.append(document)
        client._documents.append(document)
        
        # Возвращаем в формате, который ожидает DirectoryProcessor
        return {
            'document_id': int(document_id),  # ID должен быть int
            'label': kwargs.get('label', filename),
            'filename': filename,
            'mimetype': kwargs.get('mimetype', 'application/octet-stream'),
            'size': len(file_content) if isinstance(file_content, bytes) else 0,
        }
    
    client.create_document_with_file = AsyncMock(side_effect=create_document_with_file_impl)
    
    return client

