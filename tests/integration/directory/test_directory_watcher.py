"""
Тесты мониторинга директории
"""
import pytest
import time
from pathlib import Path
from services.directory_watcher import DirectoryWatcher
from tests.integration.directory.fixtures import temp_directory


@pytest.mark.integration
@pytest.mark.directory
class TestDirectoryWatcher:
    """Тесты DirectoryWatcher"""
    
    def test_watcher_initialization(self, temp_directory: Path):
        """Тест инициализации наблюдателя"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        assert watcher.watch_directory == temp_directory
        assert watcher.recursive is False
        assert watcher.observer is None
    
    def test_watcher_initialization_nonexistent_directory(self):
        """Тест инициализации с несуществующей директорией"""
        non_existent = Path('/nonexistent/directory/path')
        
        def callback(file_path: Path):
            pass
        
        with pytest.raises(ValueError, match='не существует'):
            DirectoryWatcher(
                watch_directory=non_existent,
                callback=callback,
                recursive=False
            )
    
    def test_watcher_initialization_file_not_directory(self, temp_directory: Path):
        """Тест инициализации с файлом вместо директории"""
        test_file = temp_directory / 'test.txt'
        test_file.write_text('test')
        
        def callback(file_path: Path):
            pass
        
        with pytest.raises(ValueError, match='не является директорией'):
            DirectoryWatcher(
                watch_directory=test_file,
                callback=callback,
                recursive=False
            )
    
    def test_watcher_start_stop(self, temp_directory: Path):
        """Тест запуска и остановки наблюдателя"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        # Запускаем наблюдатель
        watcher.start()
        assert watcher.observer is not None
        assert watcher.observer.is_alive() is True
        
        # Останавливаем наблюдатель
        watcher.stop()
        # Даем время на остановку
        time.sleep(0.5)
        assert watcher.observer.is_alive() is False
    
    def test_watcher_scan_existing_files(self, temp_directory: Path):
        """Тест сканирования существующих файлов"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        # Создаем несколько файлов
        files = []
        for i in range(3):
            test_file = temp_directory / f'test_{i}.pdf'
            test_file.write_bytes(b'Test content')
            files.append(test_file)
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        # Сканируем существующие файлы
        watcher.scan_existing_files()
        
        # Проверяем, что callback был вызван для всех файлов
        assert len(callback_called) == 3
        for file_path in files:
            assert file_path in callback_called
    
    def test_watcher_scan_existing_files_with_filter(self, temp_directory: Path):
        """Тест сканирования с фильтром по расширениям"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        # Создаем файлы с разными расширениями
        pdf_file = temp_directory / 'test.pdf'
        pdf_file.write_bytes(b'PDF content')
        
        docx_file = temp_directory / 'test.docx'
        docx_file.write_bytes(b'DOCX content')
        
        txt_file = temp_directory / 'test.txt'
        txt_file.write_text('TXT content')
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        # Сканируем только PDF и DOCX файлы
        watcher.scan_existing_files(file_extension_filter={'.pdf', '.docx'})
        
        # Проверяем, что callback был вызван только для PDF и DOCX
        assert len(callback_called) == 2
        assert pdf_file in callback_called
        assert docx_file in callback_called
        assert txt_file not in callback_called
    
    def test_watcher_recursive_scan(self, temp_directory: Path):
        """Тест рекурсивного сканирования"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        # Создаем файлы в корне и поддиректории
        root_file = temp_directory / 'root_file.pdf'
        root_file.write_bytes(b'Root content')
        
        subdir = temp_directory / 'subdir'
        subdir.mkdir()
        subdir_file = subdir / 'subdir_file.pdf'
        subdir_file.write_bytes(b'Subdir content')
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=True
        )
        
        # Сканируем рекурсивно
        watcher.scan_existing_files()
        
        # Проверяем, что оба файла найдены
        assert len(callback_called) == 2
        assert root_file in callback_called
        assert subdir_file in callback_called
    
    def test_watcher_non_recursive_scan(self, temp_directory: Path):
        """Тест нерекурсивного сканирования"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        # Создаем файлы в корне и поддиректории
        root_file = temp_directory / 'root_file.pdf'
        root_file.write_bytes(b'Root content')
        
        subdir = temp_directory / 'subdir'
        subdir.mkdir()
        subdir_file = subdir / 'subdir_file.pdf'
        subdir_file.write_bytes(b'Subdir content')
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        # Сканируем только корневую директорию
        watcher.scan_existing_files()
        
        # Проверяем, что найден только файл из корня
        assert len(callback_called) == 1
        assert root_file in callback_called
        assert subdir_file not in callback_called
    
    def test_watcher_duplicate_prevention(self, temp_directory: Path):
        """Тест предотвращения повторной обработки файлов"""
        callback_called = []
        
        def callback(file_path: Path):
            callback_called.append(file_path)
        
        # Создаем файл
        test_file = temp_directory / 'test.pdf'
        test_file.write_bytes(b'Test content')
        
        watcher = DirectoryWatcher(
            watch_directory=temp_directory,
            callback=callback,
            recursive=False
        )
        
        # Сканируем первый раз
        watcher.scan_existing_files()
        assert len(callback_called) == 1
        
        # Сканируем второй раз (файл не должен быть обработан повторно)
        watcher.scan_existing_files()
        assert len(callback_called) == 1  # Не изменилось

