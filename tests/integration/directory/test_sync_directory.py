"""
Интеграционные тесты синхронизации директории
"""
import pytest
import asyncio
from pathlib import Path
from services.sync_directory import sync_directory, process_file_async, FileProcessingStats
from services.directory_processor import DirectoryProcessor
from services.directory_watcher import DirectoryWatcher
from services.mayan_connector import MayanClient
from tests.integration.directory.fixtures import (
    temp_directory,
    sample_file,
    sample_files,
    mock_mayan_client_with_types
)


@pytest.mark.integration
@pytest.mark.directory
class TestSyncDirectory:
    """Тесты синхронизации директории"""
    
    @pytest.mark.asyncio
    async def test_directory_processor_initialization(self, mock_mayan_client_with_types):
        """Тест инициализации процессора директории"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        assert processor.mayan_client == mock_mayan_client_with_types
        assert processor.hash_cache is not None
        assert processor.document_type_id is None  # Инициализируется при первом использовании
    
    @pytest.mark.asyncio
    async def test_process_file(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки файла"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test PDF content')
        
        # Обрабатываем файл
        result = await processor.process_file(test_file, check_duplicates=True)
        
        # Проверяем результат
        assert result['success'] is True
        assert result['document_id'] is not None
        assert result['filename'] == 'test.pdf'
        assert result['error'] is None
    
    @pytest.mark.asyncio
    async def test_process_duplicate(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки дубликата"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test PDF content')
        
        # Обрабатываем файл первый раз
        result1 = await processor.process_file(test_file, check_duplicates=True)
        assert result1['success'] is True
        
        # Обрабатываем тот же файл второй раз (должен быть пропущен)
        result2 = await processor.process_file(test_file, check_duplicates=True)
        assert result2['success'] is False
        assert 'дубликат' in result2['error'].lower()
    
    @pytest.mark.asyncio
    async def test_sync_directory_scan_existing(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types,
        monkeypatch
    ):
        """Тест синхронизации с сканированием существующих файлов"""
        # Создаем несколько файлов
        for i in range(3):
            test_file = temp_directory / f'test_{i}.pdf'
            test_file.write_bytes(f'Test content {i}'.encode())
        
        # Подменяем создание клиента
        async def mock_create_client():
            return mock_mayan_client_with_types
        
        monkeypatch.setattr(
            'services.sync_directory.MayanClient.create_with_user_credentials',
            mock_create_client
        )
        
        # Запускаем синхронизацию
        result = await sync_directory(
            watch_directory=str(temp_directory),
            dry_run=False,
            scan_existing=True,
            recursive=False,
            file_extensions=None,
            watch_mode=False
        )
        
        # Проверяем результат
        assert result['success'] is True
        assert result['processed'] == 3
        assert result['skipped'] == 0
    
    @pytest.mark.asyncio
    async def test_sync_directory_without_scan(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types,
        monkeypatch
    ):
        """Тест синхронизации без сканирования существующих файлов"""
        # Создаем файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test content')
        
        # Подменяем создание клиента
        async def mock_create_client():
            return mock_mayan_client_with_types
        
        monkeypatch.setattr(
            'services.sync_directory.MayanClient.create_with_user_credentials',
            mock_create_client
        )
        
        # Запускаем синхронизацию без сканирования
        result = await sync_directory(
            watch_directory=str(temp_directory),
            dry_run=False,
            scan_existing=False,
            recursive=False,
            file_extensions=None,
            watch_mode=False
        )
        
        # Проверяем, что существующий файл не был обработан
        assert result['processed'] == 0
    
    @pytest.mark.asyncio
    async def test_file_extension_filter(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types,
        monkeypatch
    ):
        """Тест фильтрации по расширениям файлов"""
        # Создаем файлы с разными расширениями
        (temp_directory / 'test.pdf').write_bytes(b'PDF content')
        (temp_directory / 'test.docx').write_bytes(b'DOCX content')
        (temp_directory / 'test.txt').write_text('TXT content')
        
        # Подменяем создание клиента
        async def mock_create_client():
            return mock_mayan_client_with_types
        
        monkeypatch.setattr(
            'services.sync_directory.MayanClient.create_with_user_credentials',
            mock_create_client
        )
        
        # Запускаем синхронизацию с фильтром
        result = await sync_directory(
            watch_directory=str(temp_directory),
            dry_run=False,
            scan_existing=True,
            recursive=False,
            file_extensions={'.pdf', '.docx'},
            watch_mode=False
        )
        
        # Проверяем, что обработаны только PDF и DOCX
        assert result['processed'] == 2
    
    @pytest.mark.asyncio
    async def test_process_file_async_stats(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки файла со статистикой"""
        processor = DirectoryProcessor(mock_mayan_client_with_types)
        stats = FileProcessingStats()
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test content')
        
        # Обрабатываем файл
        await process_file_async(test_file, processor, stats)
        
        # Проверяем статистику
        assert stats.processed == 1
        assert stats.errors == 0
        assert stats.skipped == 0
    
    @pytest.mark.asyncio
    async def test_dry_run_mode(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types,
        monkeypatch
    ):
        """Тест тестового режима (dry run)"""
        # Подменяем создание клиента
        async def mock_create_client():
            return mock_mayan_client_with_types
        
        monkeypatch.setattr(
            'services.sync_directory.MayanClient.create_with_user_credentials',
            mock_create_client
        )
        
        # Запускаем в тестовом режиме
        result = await sync_directory(
            watch_directory=str(temp_directory),
            dry_run=True,
            scan_existing=False,
            recursive=False,
            file_extensions=None,
            watch_mode=False
        )
        
        # В dry run режиме документы не создаются
        assert result['success'] is True
        assert result['processed'] == 0