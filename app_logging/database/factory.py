# logging/database/factory.py
from typing import Dict, Any
from .base import DatabaseAdapter
from .postgresql_adapter import PostgreSQLAdapter
from .sqlite_adapter import SQLiteAdapter
from config.settings import DatabaseType


class DatabaseAdapterFactory:
    """Фабрика для создания адаптеров баз данных"""
    
    @staticmethod
    def create_adapter(db_type: DatabaseType, config: Dict[str, Any], table_name: str = 'application_logs') -> DatabaseAdapter:
        """
        Создает адаптер базы данных по типу
        
        Args:
            db_type: Тип базы данных
            config: Конфигурация базы данных
            table_name: Имя таблицы для логов
            
        Returns:
            Адаптер базы данных
            
        Raises:
            ValueError: Если тип базы данных не поддерживается
        """
        if db_type == DatabaseType.POSTGRESQL:
            return PostgreSQLAdapter(config, table_name)
        elif db_type == DatabaseType.SQLITE:
            return SQLiteAdapter(config, table_name)
        else:
            raise ValueError(f"Неподдерживаемый тип базы данных: {db_type}")