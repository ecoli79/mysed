# logging/database/sqlite_adapter.py
from typing import List, Dict, Any, Optional
import sqlite3
import json
from pathlib import Path
from .base import DatabaseAdapter


class SQLiteAdapter(DatabaseAdapter):
    """Адаптер для работы с SQLite"""
    
    def __init__(self, config: Dict[str, Any], table_name: str = 'application_logs'):
        # Создаем директорию для SQLite файла если не существует
        sqlite_path = Path(config['sqlite_path'])
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        
        super().__init__(config, table_name)
    
    def _create_table(self) -> None:
        """Создает таблицу для логов если она не существует"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        level VARCHAR(20) NOT NULL,
                        logger VARCHAR(255) NOT NULL,
                        module VARCHAR(255),
                        function VARCHAR(255),
                        line INTEGER,
                        message TEXT NOT NULL,
                        thread_name VARCHAR(255),
                        process_id INTEGER,
                        exception TEXT,
                        extra_data TEXT
                    );
                """)
                
                # Создаем индексы
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp ON {self.table_name} (timestamp);")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_level ON {self.table_name} (level);")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_logger ON {self.table_name} (logger);")
                
                conn.commit()
        except Exception as e:
            print(f"Ошибка создания таблицы логов SQLite: {e}")
    
    def get_connection(self):
        """Получает соединение с SQLite"""
        return sqlite3.connect(self.config['sqlite_path'])
    
    def close_connection(self, connection) -> None:
        """Закрывает соединение с SQLite"""
        if connection:
            connection.close()
    
    def insert_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """Вставляет логи в SQLite"""
        if not logs:
            return True
            
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                # Подготавливаем данные для SQLite
                prepared_logs = []
                for log in logs:
                    prepared_log = log.copy()
                    # Конвертируем JSONB в строку для SQLite
                    if 'extra_data' in prepared_log and prepared_log['extra_data']:
                        prepared_log['extra_data'] = json.dumps(prepared_log['extra_data'])
                    prepared_logs.append(prepared_log)
                
                cur.executemany(f"""
                    INSERT INTO {self.table_name} 
                    (timestamp, level, logger, module, function, line, message, 
                     thread_name, process_id, exception, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (
                        log['timestamp'],
                        log['level'],
                        log['logger'],
                        log['module'],
                        log['function'],
                        log['line'],
                        log['message'],
                        log['thread_name'],
                        log['process_id'],
                        log['exception'],
                        log['extra_data']
                    ) for log in prepared_logs
                ])
                conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка записи логов в SQLite: {e}")
            return False