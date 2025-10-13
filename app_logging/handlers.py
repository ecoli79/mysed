# logging/handlers.py
import json
import logging
import logging.handlers
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
import threading
from queue import Queue, Empty
import time
import os

from .database import DatabaseAdapterFactory
from config.settings import DatabaseType


class ContextFilter(logging.Filter):
    """Фильтр для добавления контекстной информации в логи"""
    
    def filter(self, record):
        # Добавляем информацию о потоке
        record.thread_name = threading.current_thread().name
        
        # Добавляем информацию о процессе
        record.process_id = os.getpid()
        
        # Добавляем временную метку
        record.timestamp = datetime.utcnow().isoformat()
        
        return True


class JSONFormatter(logging.Formatter):
    """Форматтер для JSON логов"""
    
    def format(self, record):
        log_entry = {
            'timestamp': getattr(record, 'timestamp', datetime.utcnow().isoformat()),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
            'thread': getattr(record, 'thread_name', threading.current_thread().name),
            'process_id': getattr(record, 'process_id', os.getpid()),
        }
        
        # Добавляем исключения если есть
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Добавляем дополнительные поля
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
            
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class DatabaseLogHandler(logging.Handler):
    """Обработчик для записи логов в базу данных"""
    
    def __init__(self, db_config, table_name='application_logs', batch_size=100, flush_interval=5):
        super().__init__()
        
        self.db_config = db_config
        self.table_name = table_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue = Queue()
        self.batch = []
        self.last_flush = time.time()
        self.lock = threading.Lock()
        
        # Создаем адаптер базы данных
        try:
            self.db_adapter = DatabaseAdapterFactory.create_adapter(
                db_config.db_type,
                db_config.dict(),
                table_name
            )
        except Exception as e:
            print(f"Ошибка создания адаптера БД: {e}")
            self.db_adapter = None
        
        # Запускаем фоновый поток для записи в БД
        if self.db_adapter:
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()
    
    def emit(self, record):
        """Добавляет запись в очередь для записи в БД"""
        if not self.db_adapter:
            return
            
        try:
            log_data = {
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelname,
                'logger': record.name,
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'message': record.getMessage(),
                'thread_name': getattr(record, 'thread_name', threading.current_thread().name),
                'process_id': getattr(record, 'process_id', os.getpid()),
                'exception': record.exc_text if record.exc_info else None,
                'extra_data': getattr(record, 'extra_fields', None)
            }
            
            self.log_queue.put(log_data, block=False)
        except Exception:
            self.handleError(record)
    
    def _worker(self):
        """Фоновый поток для записи логов в БД"""
        while True:
            try:
                # Собираем записи в батч
                while len(self.batch) < self.batch_size:
                    try:
                        log_data = self.log_queue.get(timeout=1)
                        self.batch.append(log_data)
                    except Empty:
                        break
                
                # Записываем батч если он заполнен или прошло достаточно времени
                current_time = time.time()
                if self.batch and (len(self.batch) >= self.batch_size or 
                                 current_time - self.last_flush >= self.flush_interval):
                    self._flush_batch()
                    
            except Exception as e:
                print(f"Ошибка в worker потоке логов: {e}")
                time.sleep(1)
    
    def _flush_batch(self):
        """Записывает батч логов в базу данных"""
        if not self.batch or not self.db_adapter:
            return
            
        try:
            success = self.db_adapter.insert_logs(self.batch)
            if success:
                with self.lock:
                    self.batch.clear()
                    self.last_flush = time.time()
            else:
                print("Ошибка записи логов в БД")
                # В случае ошибки очищаем батч чтобы не накапливать память
                with self.lock:
                    self.batch.clear()
                
        except Exception as e:
            print(f"Ошибка записи логов в БД: {e}")
            with self.lock:
                self.batch.clear()


class StructuredLogHandler(logging.Handler):
    """Обработчик для структурированных логов с дополнительными полями"""
    
    def __init__(self, target_handler, extra_fields: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.target_handler = target_handler
        self.extra_fields = extra_fields or {}
    
    def emit(self, record):
        # Добавляем дополнительные поля
        if self.extra_fields:
            record.extra_fields = getattr(record, 'extra_fields', {})
            record.extra_fields.update(self.extra_fields)
        
        self.target_handler.emit(record)