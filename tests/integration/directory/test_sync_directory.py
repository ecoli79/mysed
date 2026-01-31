"""
Интеграционные тесты синхронизации директории
"""
import pytest
import asyncio
from pathlib import Path
from services.sync_directory import DirectorySyncService
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
    async def test_service_initialization(self, temp_directory: Path):
        """Тест инициализации сервиса"""
        service = DirectorySyncService(temp_directory, scan_existing=False)
        
        assert service.watch_directory == temp_directory
        assert service.scan_existing is False
        assert service.running is False
        assert service.stats['processed'] == 0
        assert service.stats['skipped'] == 0
        assert service.stats['errors'] == 0
    
    @pytest.mark.asyncio
    async def test_service_process_file(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки файла через сервис"""
        service = DirectorySyncService(temp_directory, scan_existing=False)
        service.mayan_client = mock_mayan_client_with_types
        service.directory_processor = service.directory_processor or None
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test PDF content')
        
        # Обрабатываем файл
        await service._process_file(test_file)
        
        # Проверяем статистику
        assert service.stats['processed'] == 1
        assert service.stats['errors'] == 0
    
    @pytest.mark.asyncio
    async def test_service_process_duplicate(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест обработки дубликата через сервис"""
        service = DirectorySyncService(temp_directory, scan_existing=False)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Создаем тестовый файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test PDF content')
        
        # Обрабатываем файл первый раз
        await service._process_file(test_file)
        assert service.stats['processed'] == 1
        
        # Обрабатываем тот же файл второй раз (должен быть пропущен)
        await service._process_file(test_file)
        assert service.stats['processed'] == 1  # Не изменилось
        assert service.stats['skipped'] == 1  # Пропущен как дубликат
    
    @pytest.mark.asyncio
    async def test_service_start_watching_scan_existing(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест запуска мониторинга с сканированием существующих файлов"""
        # Создаем несколько файлов
        files = []
        for i in range(3):
            test_file = temp_directory / f'test_{i}.pdf'
            test_file.write_bytes(f'Test content {i}'.encode())
            files.append(test_file)
        
        service = DirectorySyncService(temp_directory, scan_existing=True)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Запускаем мониторинг с сканированием существующих файлов
        await service.start_watching(recursive=False, file_extensions=None)
        
        # Даем время на обработку
        await asyncio.sleep(1)
        
        # Останавливаем мониторинг
        service.stop_watching()
        
        # Проверяем статистику
        assert service.stats['processed'] == 3
        assert service.stats['errors'] == 0
        
        await service.close()
    
    @pytest.mark.asyncio
    async def test_service_start_watching_without_scan(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест запуска мониторинга без сканирования существующих файлов"""
        # Создаем файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test content')
        
        service = DirectorySyncService(temp_directory, scan_existing=False)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Запускаем мониторинг без сканирования
        await service.start_watching(recursive=False, file_extensions=None)
        
        # Даем время на инициализацию
        await asyncio.sleep(0.5)
        
        # Останавливаем мониторинг
        service.stop_watching()
        
        # Проверяем, что существующий файл не был обработан
        assert service.stats['processed'] == 0
        
        await service.close()
    
    @pytest.mark.asyncio
    async def test_service_file_extension_filter(
        self,
        temp_directory: Path,
        mock_mayan_client_with_types
    ):
        """Тест фильтрации по расширениям файлов"""
        # Создаем файлы с разными расширениями
        pdf_file = temp_directory / 'test.pdf'
        pdf_file.write_bytes(b'PDF content')
        
        docx_file = temp_directory / 'test.docx'
        docx_file.write_bytes(b'DOCX content')
        
        txt_file = temp_directory / 'test.txt'
        txt_file.write_text('TXT content')
        
        service = DirectorySyncService(temp_directory, scan_existing=True)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Запускаем мониторинг с фильтром только PDF и DOCX
        await service.start_watching(
            recursive=False,
            file_extensions={'.pdf', '.docx'}
        )
        
        # Даем время на обработку
        await asyncio.sleep(1)
        
        # Останавливаем мониторинг
        service.stop_watching()
        
        # Проверяем, что обработаны только PDF и DOCX
        assert service.stats['processed'] == 2
        assert service.stats['errors'] == 0
        
        await service.close()
    
    @pytest.mark.asyncio
    async def test_service_close(self, temp_directory: Path, mock_mayan_client_with_types):
        """Тест закрытия сервиса"""
        service = DirectorySyncService(temp_directory, scan_existing=False)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Запускаем мониторинг
        await service.start_watching(recursive=False)
        
        # Закрываем сервис
        await service.close()
        
        # Проверяем, что мониторинг остановлен
        assert service.running is False
        assert service.watcher is None or not service.watcher.observer.is_alive()
    
    @pytest.mark.asyncio
    async def test_service_print_stats(self, temp_directory: Path, mock_mayan_client_with_types):
        """Тест вывода статистики"""
        service = DirectorySyncService(temp_directory, scan_existing=False)
        service.mayan_client = mock_mayan_client_with_types
        
        # Инициализируем компоненты
        await service._initialize()
        
        # Создаем и обрабатываем файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test content')
        await service._process_file(test_file)
        
        # Выводим статистику (проверяем, что не падает)
        service.print_stats()
        
        assert service.stats['processed'] == 1

