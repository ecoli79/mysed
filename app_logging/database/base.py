# logging/database/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime


class DatabaseAdapter(ABC):
    """Абстрактный базовый класс для адаптеров баз данных"""
    
    def __init__(self, config: Dict[str, Any], table_name: str = 'application_logs'):
        self.config = config
        self.table_name = table_name
        self._create_table()
    
    @abstractmethod
    def _create_table(self) -> None:
        """Создает таблицу для логов если она не существует"""
        pass
    
    @abstractmethod
    def insert_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """Вставляет логи в базу данных"""
        pass
    
    @abstractmethod
    def get_connection(self):
        """Получает соединение с базой данных"""
        pass
    
    @abstractmethod
    def close_connection(self, connection) -> None:
        """Закрывает соединение с базой данных"""
        pass
    
    def test_connection(self) -> bool:
        """Тестирует соединение с базой данных"""
        try:
            conn = self.get_connection()
            self.close_connection(conn)
            return True
        except Exception:
            return False
    
    def get_logs(self, limit: int = 100, offset: int = 0, 
                 level: Optional[str] = None, logger: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает логи из базы данных
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            level: Фильтр по уровню логирования
            logger: Фильтр по имени логгера
            
        Returns:
            Список логов
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = f"SELECT * FROM {self.table_name}"
            params = []
            conditions = []
            
            if level:
                conditions.append("level = ?")
                params.append(level)
            
            if logger:
                conditions.append("logger = ?")
                params.append(logger)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            logs = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            self.close_connection(conn)
            return logs
            
        except Exception as e:
            print(f"Ошибка получения логов: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30) -> bool:
        """
        Удаляет старые логи
        
        Args:
            days: Количество дней для хранения логов
            
        Returns:
            True если очистка прошла успешно
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # SQL зависит от типа БД, переопределяется в наследниках
            cursor.execute(f"""
                DELETE FROM {self.table_name} 
                WHERE timestamp < datetime('now', '-{days} days')
            """)
            
            deleted_count = cursor.rowcount
            conn.commit()
            self.close_connection(conn)
            
            print(f"Удалено {deleted_count} старых записей логов")
            return True
            
        except Exception as e:
            print(f"Ошибка очистки старых логов: {e}")
            return False


