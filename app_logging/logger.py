# logging/logger.py
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any
import os
import sys
import threading

from .handlers import DatabaseLogHandler, JSONFormatter, ContextFilter, StructuredLogHandler
from config.settings import config, LogLevel, LogHandler


class NoiseFilter(logging.Filter):
    """Фильтр для подавления шумных логов"""
    
    def __init__(self):
        super().__init__()
        # Список логгеров, которые нужно подавить
        self.noisy_loggers = [
            'watchfiles',
            'watchfiles.main',
            'uvicorn.access',
            'uvicorn.error',
        ]
    
    def filter(self, record):
        # Подавляем логи от шумных логгеров
        if any(record.name.startswith(logger) for logger in self.noisy_loggers):
            return False
        
        # Подавляем сообщения о детекции изменений файлов
        if 'change detected' in record.getMessage():
            return False
            
        return True


class LoggerManager:
    """Менеджер для настройки и управления логгерами"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._loggers = {}
            self._setup_logging()
    
    def _setup_logging(self):
        """Настраивает систему логирования"""
        log_config = config.logging
        
        # Создаем директорию для логов
        log_dir = Path(log_config.log_dir)
        log_dir.mkdir(exist_ok=True)
        
        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_config.level.value))
        
        # Очищаем существующие обработчики
        root_logger.handlers.clear()
        
        # Добавляем фильтр шума
        noise_filter = NoiseFilter()
        
        # Добавляем обработчики в зависимости от конфигурации
        for handler_type in log_config.handlers:
            handler = self._create_handler(handler_type, log_config)
            if handler:
                handler.addFilter(noise_filter)  # Добавляем фильтр
                root_logger.addHandler(handler)
    
    def _create_handler(self, handler_type: LogHandler, log_config) -> Optional[logging.Handler]:
        """Создает обработчик логов по типу"""
        
        if handler_type == LogHandler.CONSOLE:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(getattr(logging, log_config.level.value))
            
        elif handler_type == LogHandler.FILE:
            log_file = log_config.log_dir / log_config.log_file
            handler = logging.FileHandler(log_file, encoding='utf-8')
            handler.setLevel(getattr(logging, log_config.level.value))
            
        elif handler_type == LogHandler.ROTATING_FILE:
            log_file = log_config.log_dir / log_config.log_file
            handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=log_config.max_file_size,
                backupCount=log_config.backup_count,
                encoding='utf-8'
            )
            handler.setLevel(getattr(logging, log_config.level.value))
            
        elif handler_type == LogHandler.DATABASE:
            if log_config.database:
                handler = DatabaseLogHandler(log_config.database)
                handler.setLevel(getattr(logging, log_config.level.value))
            else:
                print("Предупреждение: Конфигурация БД не найдена, пропускаем DatabaseLogHandler")
                return None
        else:
            print(f"Неизвестный тип обработчика: {handler_type}")
            return None
        
        # Настраиваем форматирование
        if log_config.enable_json_logging:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                log_config.log_format,
                datefmt=log_config.date_format
            )
        
        handler.setFormatter(formatter)
        
        # Добавляем контекстный фильтр
        if log_config.enable_context_logging:
            handler.addFilter(ContextFilter())
        
        return handler
    
    def get_logger(self, name: str, extra_fields: Optional[Dict[str, Any]] = None) -> logging.Logger:
        """Получает логгер с дополнительными полями"""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            
            # Добавляем структурированный обработчик если нужны дополнительные поля
            if extra_fields:
                for handler in logging.getLogger().handlers:
                    structured_handler = StructuredLogHandler(handler, extra_fields)
                    logger.addHandler(structured_handler)
            
            self._loggers[name] = logger
        
        return self._loggers[name]

# Глобальный экземпляр менеджера
_logger_manager = LoggerManager()


def get_logger(name: str, extra_fields: Optional[Dict[str, Any]] = None) -> logging.Logger:
    """
    Получает настроенный логгер
    
    Args:
        name: Имя логгера (обычно __name__)
        extra_fields: Дополнительные поля для структурированного логирования
        
    Returns:
        Настроенный логгер
    """
    return _logger_manager.get_logger(name, extra_fields)


def setup_logging():
    """Настраивает систему логирования (вызывается при старте приложения)"""
    _logger_manager._setup_logging()


# Декоратор для логирования функций
def log_function_call(logger_name: str = None, log_args: bool = True, log_result: bool = True):
    """Декоратор для автоматического логирования вызовов функций"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            
            # Логируем входные параметры
            if log_args:
                logger.debug(f"Вызов {func.__name__} с args={args}, kwargs={kwargs}")
            
            try:
                result = func(*args, **kwargs)
                
                # Логируем результат
                if log_result:
                    logger.debug(f"Функция {func.__name__} завершена успешно, результат: {result}")
                
                return result
                
            except Exception as e:
                logger.error(f"Ошибка в функции {func.__name__}: {e}", exc_info=True)
                raise
        
        return wrapper
    return decorator
