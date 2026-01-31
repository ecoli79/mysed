# services/directory_watcher.py
from pathlib import Path
from typing import Optional, Callable, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from app_logging.logger import get_logger

logger = get_logger(__name__)


class DirectoryWatcherHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы для мониторинга директории"""
    
    def __init__(self, callback: Callable[[Path], None], processed_files: Set[Path]):
        """
        Инициализация обработчика
        
        Args:
            callback: Функция обратного вызова для обработки новых файлов
            processed_files: Множество уже обработанных файлов
        """
        self.callback = callback
        self.processed_files = processed_files
    
    def on_created(self, event: FileSystemEvent):
        """Вызывается при создании файла или директории"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        self._handle_file(file_path)
    
    def on_moved(self, event: FileSystemEvent):
        """Вызывается при перемещении файла"""
        if event.is_directory:
            return
        
        # При перемещении event.dest_path содержит новый путь
        if hasattr(event, 'dest_path') and event.dest_path:
            file_path = Path(event.dest_path)
        else:
            file_path = Path(event.src_path)
        
        self._handle_file(file_path)
    
    def _handle_file(self, file_path: Path):
        """Обрабатывает файл"""
        try:
            # Проверяем, что файл еще не обработан
            if file_path in self.processed_files:
                logger.debug(f"Файл {file_path} уже обработан, пропускаем")
                return
            
            # Проверяем, что файл существует и полностью записан
            if not file_path.exists():
                logger.debug(f"Файл {file_path} еще не существует, пропускаем")
                return
            
            # Добавляем в множество обработанных файлов
            self.processed_files.add(file_path)
            
            # Вызываем callback
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
        """
        Инициализация наблюдателя
        
        Args:
            watch_directory: Директория для мониторинга
            callback: Функция обратного вызова для обработки новых файлов
            recursive: Мониторить ли поддиректории рекурсивно
        """
        self.watch_directory = Path(watch_directory)
        self.callback = callback
        self.recursive = recursive
        self.observer: Optional[Observer] = None
        self.processed_files: Set[Path] = set()
        
        # Проверяем существование директории
        if not self.watch_directory.exists():
            raise ValueError(f"Директория не существует: {self.watch_directory}")
        
        if not self.watch_directory.is_dir():
            raise ValueError(f"Путь не является директорией: {self.watch_directory}")
    
    def start(self):
        """Запускает мониторинг директории"""
        if self.observer and self.observer.is_alive():
            logger.warning("Наблюдатель уже запущен")
            return
        
        try:
            event_handler = DirectoryWatcherHandler(self.callback, self.processed_files)
            self.observer = Observer()
            self.observer.schedule(
                event_handler,
                str(self.watch_directory),
                recursive=self.recursive
            )
            self.observer.start()
            logger.info(
                f"Мониторинг директории запущен: {self.watch_directory} "
                f"(рекурсивно: {self.recursive})"
            )
        except Exception as e:
            logger.error(f"Ошибка при запуске мониторинга: {e}", exc_info=True)
            raise
    
    def stop(self):
        """Останавливает мониторинг директории"""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)
            logger.info("Мониторинг директории остановлен")
    
    def scan_existing_files(self, file_extension_filter: Optional[Set[str]] = None):
        """
        Сканирует существующие файлы в директории
        
        Args:
            file_extension_filter: Множество расширений файлов для фильтрации (например, {'.pdf', '.docx'})
                                 Если None, обрабатываются все файлы
        """
        logger.info(f"Сканирование существующих файлов в {self.watch_directory}")
        
        try:
            if self.recursive:
                files = list(self.watch_directory.rglob('*'))
            else:
                files = list(self.watch_directory.glob('*'))
            
            # Фильтруем только файлы
            files = [f for f in files if f.is_file()]
            
            # Применяем фильтр по расширению, если указан
            if file_extension_filter:
                files = [
                    f for f in files 
                    if f.suffix.lower() in file_extension_filter
                ]
            
            logger.info(f"Найдено {len(files)} файлов для обработки")
            
            for file_path in files:
                if file_path not in self.processed_files:
                    self.processed_files.add(file_path)
                    logger.info(f"Обработка существующего файла: {file_path}")
                    self.callback(file_path)
            
            logger.info(f"Сканирование завершено, обработано {len(files)} файлов")
            
        except Exception as e:
            logger.error(f"Ошибка при сканировании директории: {e}", exc_info=True)

