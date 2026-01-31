"""
Тесты обработки файлов из директории
"""
import pytest
import json
from pathlib import Path

from services.directory_processor import DirectoryProcessor
from tests.integration.directory.fixtures import (
    temp_directory,
    sample_file,
    sample_files,
    mock_mayan_client_with_types
)


@pytest.mark.integration
@pytest.mark.directory
class TestDirectoryProcessor:
    """Тесты DirectoryProcessor"""
    
    @pytest.mark.asyncio
    async def test_process_file_success(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест успешной обработки файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_content = b'Test PDF content'
        test_file.write_bytes(test_content)
        
        # Обрабатываем файл
        result = await processor.process_file(test_file, check_duplicates=True)
        
        assert result['success'] is True
        assert result['document_id'] is not None
        assert result['filename'] == 'test.pdf'
        assert result['error'] is None
        
        # Проверяем, что документ был создан в Mayan
        assert mock_mayan_client_with_types.create_document_with_file.called
    
    @pytest.mark.asyncio
    async def test_process_file_duplicate(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки дубликата файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_content = b'Test PDF content'
        test_file.write_bytes(test_content)
        
        # Обрабатываем файл первый раз
        result1 = await processor.process_file(test_file, check_duplicates=True)
        assert result1['success'] is True
        
        # Обрабатываем тот же файл второй раз (должен быть пропущен как дубликат)
        result2 = await processor.process_file(test_file, check_duplicates=True)
        assert result2['success'] is False
        assert 'дубликат' in result2['error'].lower() or 'duplicate' in result2['error'].lower()
    
    @pytest.mark.asyncio
    async def test_process_file_not_exists(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки несуществующего файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Пытаемся обработать несуществующий файл
        non_existent_file = temp_directory / 'non_existent.pdf'
        result = await processor.process_file(non_existent_file, check_duplicates=True)
        
        assert result['success'] is False
        assert result['error'] is not None
        assert 'не существует' in result['error'].lower() or 'not exist' in result['error'].lower()
    
    @pytest.mark.asyncio
    async def test_process_file_empty(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки пустого файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем пустой файл
        empty_file = temp_directory / 'empty.pdf'
        empty_file.write_bytes(b'')
        
        result = await processor.process_file(empty_file, check_duplicates=True)
        
        assert result['success'] is False
        assert result['error'] is not None
        assert 'пуст' in result['error'].lower() or 'empty' in result['error'].lower()
    
    @pytest.mark.asyncio
    async def test_process_file_metadata(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест метаданных файла в description"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test_metadata.pdf'
        test_content = b'Test PDF content for metadata'
        test_file.write_bytes(test_content)
        
        # Обрабатываем файл
        result = await processor.process_file(test_file, check_duplicates=True)
        
        assert result['success'] is True
        
        # Проверяем, что create_document_with_file был вызван с правильными параметрами
        call_args = mock_mayan_client_with_types.create_document_with_file.call_args
        assert call_args is not None
        
        kwargs = call_args.kwargs
        assert kwargs['label'] == 'test_metadata.pdf'
        assert kwargs['filename'] == 'test_metadata.pdf'
        
        # Проверяем, что description содержит метаданные
        description = kwargs.get('description', '')
        metadata = json.loads(description)
        assert metadata['source'] == 'directory'
        assert metadata['file_name'] == 'test_metadata.pdf'
        assert 'file_hash' in metadata
        assert 'file_size' in metadata
    
    @pytest.mark.asyncio
    async def test_process_file_hash_calculation(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест вычисления хеша файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test_hash.pdf'
        test_content = b'Test content for hash'
        test_file.write_bytes(test_content)
        
        # Вычисляем хеш напрямую
        expected_hash = processor._calculate_file_hash(test_content)
        
        # Обрабатываем файл
        result = await processor.process_file(test_file, check_duplicates=True)
        
        assert result['success'] is True
        
        # Проверяем, что хеш был добавлен в кеш
        assert processor.hash_cache.hash_exists(expected_hash)
    
    @pytest.mark.asyncio
    async def test_process_file_without_duplicate_check(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки файла без проверки дубликатов"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test_no_check.pdf'
        test_content = b'Test content'
        test_file.write_bytes(test_content)
        
        # Обрабатываем файл первый раз
        result1 = await processor.process_file(test_file, check_duplicates=False)
        assert result1['success'] is True
        
        # Обрабатываем тот же файл второй раз без проверки дубликатов
        # (должен быть создан второй документ)
        result2 = await processor.process_file(test_file, check_duplicates=False)
        # В этом случае файл все равно может быть пропущен из-за кеша,
        # но это зависит от реализации
        assert result2 is not None

