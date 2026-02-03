# services/directory_watcher.py
"""Наблюдатель за файловой системой для мониторинга директории"""

from pathlib import Path
from typing import Optional, Callable, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from services.logger import get_logger

logger = get_logger(__name__)


class DirectoryWatcherHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы"""
    
    def __init__(self, callback: Callable[[Path], None], processed_files: Set[Path]):
        self.callback = callback
        self.processed_files = processed_files
    
    def on_created(self, event: FileSystemEvent):
        """Вызывается при создании файла"""
        if not event.is_directory:
            self._handle_file(Path(event.src_path))
    
    def on_moved(self, event: FileSystemEvent):
        """Вызывается при перемещении файла"""
        if not event.is_directory:
            file_path = Path(getattr(event, 'dest_path', event.src_path))
            self._handle_file(file_path)
    
    def _handle_file(self, file_path: Path):
        """Обрабатывает файл"""
        try:
            if file_path in self.processed_files or not file_path.exists():
                return
            
            self.processed_files.add(file_path)
            logger.info(f"Обнаружен новый файл: {file_path}")
            self.callback(file_path)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке события для файла {file_path}: {e}", exc_info=True)


class DirectoryWatcher:
    """Класс для мониторинга директории на предмет новых файлов"""
    
    def __init__(
        self, 
        watch_directory: Path,
        callback: Callable[[Path], None],
        recursive: bool = False
    ):
        self.watch_directory = Path(watch_directory)
        self.callback = callback
        self.recursive = recursive
        self.observer: Optional[Observer] = None
        self.processed_files: Set[Path] = set()
        
        if not self.watch_directory.is_dir():
            raise ValueError(f"Путь не является директорией: {self.watch_directory}")
    
    def start(self):
        """Запускает мониторинг директории"""
        if self.observer and self.observer.is_alive():
            logger.warning("Наблюдатель уже запущен")
            return
        
        event_handler = DirectoryWatcherHandler(self.callback, self.processed_files)
        self.observer = Observer()
        self.observer.schedule(
            event_handler,
            str(self.watch_directory),
            recursive=self.recursive
        )
        self.observer.start()
        logger.info(f"Мониторинг запущен: {self.watch_directory} (рекурсивно: {self.recursive})")
    
    def stop(self):
        """Останавливает мониторинг"""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)
            logger.info("Мониторинг остановлен")
    
    def scan_existing_files(self, file_extension_filter: Optional[Set[str]] = None):
        """Сканирует существующие файлы в директории"""
        logger.info(f"Сканирование существующих файлов в {self.watch_directory}")
        
        try:
            files = list(
                self.watch_directory.rglob('*') if self.recursive 
                else self.watch_directory.glob('*')
            )
            
            # Фильтруем только файлы
            files = [f for f in files if f.is_file()]
            
            # Применяем фильтр по расширению
            if file_extension_filter:
                files = [f for f in files if f.suffix.lower() in file_extension_filter]
            
            logger.info(f"Найдено {len(files)} файлов для обработки")
            
            for file_path in files:
                if file_path not in self.processed_files:
                    self.processed_files.add(file_path)
                    self.callback(file_path)
            
            logger.info(f"Сканирование завершено, обработано {len(files)} файлов")
            
        except Exception as e:
            logger.error(f"Ошибка при сканировании директории: {e}", exc_info=True)