# logging/database/postgresql_adapter.py
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from .base import DatabaseAdapter


class PostgreSQLAdapter(DatabaseAdapter):
    """Адаптер для работы с PostgreSQL"""
    
    def _create_table(self) -> None:
        """Создает таблицу для логов если она не существует"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                            level VARCHAR(20) NOT NULL,
                            logger VARCHAR(255) NOT NULL,
                            module VARCHAR(255),
                            function VARCHAR(255),
                            line INTEGER,
                            message TEXT NOT NULL,
                            thread_name VARCHAR(255),
                            process_id INTEGER,
                            exception TEXT,
                            extra_data JSONB
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp 
                        ON {self.table_name} (timestamp);
                        
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_level 
                        ON {self.table_name} (level);
                        
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_logger 
                        ON {self.table_name} (logger);
                    """)
                    conn.commit()
        except Exception as e:
            print(f"Ошибка создания таблицы логов PostgreSQL: {e}")
    
    def get_connection(self):
        """Получает соединение с PostgreSQL"""
        return psycopg2.connect(
            host=self.config['host'],
            port=self.config['port'],
            database=self.config['database'],
            user=self.config['username'],
            password=self.config['password']
        )
    
    def close_connection(self, connection) -> None:
        """Закрывает соединение с PostgreSQL"""
        if connection:
            connection.close()
    
    def insert_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """Вставляет логи в PostgreSQL"""
        if not logs:
            return True
            
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(f"""
                        INSERT INTO {self.table_name} 
                        (timestamp, level, logger, module, function, line, message, 
                         thread_name, process_id, exception, extra_data)
                        VALUES (%(timestamp)s, %(level)s, %(logger)s, %(module)s, 
                                %(function)s, %(line)s, %(message)s, %(thread_name)s, 
                                %(process_id)s, %(exception)s, %(extra_data)s)
                    """, logs)
                    conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка записи логов в PostgreSQL: {e}")
            return False
    
    def get_logs(self, limit: int = 100, offset: int = 0, 
                 level: Optional[str] = None, logger: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает логи из PostgreSQL"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = f"SELECT * FROM {self.table_name}"
                    params = []
                    conditions = []
                    
                    if level:
                        conditions.append("level = %s")
                        params.append(level)
                    
                    if logger:
                        conditions.append("logger = %s")
                        params.append(logger)
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                    
                    query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])
                    
                    cur.execute(query, params)
                    logs = [dict(row) for row in cur.fetchall()]
                    
                    return logs
                    
        except Exception as e:
            print(f"Ошибка получения логов из PostgreSQL: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30) -> bool:
        """Удаляет старые логи из PostgreSQL"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        DELETE FROM {self.table_name} 
                        WHERE timestamp < NOW() - INTERVAL '{days} days'
                    """)
                    
                    deleted_count = cur.rowcount
                    conn.commit()
                    
                    print(f"Удалено {deleted_count} старых записей логов из PostgreSQL")
                    return True
                    
        except Exception as e:
            print(f"Ошибка очистки старых логов из PostgreSQL: {e}")
            return False


