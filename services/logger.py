# services/logger.py
"""
Простой модуль логирования для services скриптов.

Используется для скриптов, которые запускаются вне Docker контейнера
и не имеют доступа к общей директории логов приложения.
"""
import logging
import sys
from pathlib import Path
from typing import Optional
import os


class ServicesLogger:
    """Простой менеджер логирования для services скриптов"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loggers = {}
        return cls._instance
    
    def __init__(self):
        if not ServicesLogger._initialized:
            ServicesLogger._initialized = True
            self._setup_logging()
    
    def _setup_logging(self):
        """Настраивает простое логирование для services"""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Очищаем существующие обработчики
        root_logger.handlers.clear()
        
        # Всегда добавляем консольный handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Опционально добавляем файловый handler в домашнюю директорию пользователя
        # или временную директорию, если доступна запись
        log_file_path = self._get_log_file_path()
        if log_file_path:
            try:
                log_file_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
            except (PermissionError, OSError):
                # Если не удалось создать файловый handler, просто продолжаем без него
                pass
    
    def _get_log_file_path(self) -> Optional[Path]:
        """
        Определяет путь к файлу лога.
        
        Пытается использовать:
        1. ~/.mysed/services.log (в домашней директории пользователя)
        2. /tmp/mysed-services.log (временная директория)
        
        Returns:
            Path к файлу лога или None, если нет доступных вариантов
        """
        # Пробуем домашнюю директорию пользователя
        home_dir = Path.home()
        if home_dir.exists() and os.access(home_dir, os.W_OK):
            log_dir = home_dir / '.mysed'
            return log_dir / 'services.log'
        
        # Пробуем временную директорию
        temp_dir = Path('/tmp')
        if temp_dir.exists() and os.access(temp_dir, os.W_OK):
            return temp_dir / 'mysed-services.log'
        
        return None
    
    def get_logger(self, name: str) -> logging.Logger:
        """Получает логгер с указанным именем"""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            self._loggers[name] = logger
        return self._loggers[name]


# Глобальный экземпляр
_logger_manager = ServicesLogger()


def get_logger(name: str) -> logging.Logger:
    """
    Получает настроенный логгер для services скриптов
    
    Args:
        name: Имя логгера (обычно __name__)
    
    Returns:
        Настроенный логгер
    """
    return _logger_manager.get_logger(name)


def setup_logging():
    """
    Настраивает систему логирования для services.
    
    Вызывается при старте скрипта для явной инициализации.
    """
    _logger_manager._setup_logging()

