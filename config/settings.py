# config/settings.py
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
import os


class LogLevel(str, Enum):
    """Уровни логирования"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogHandler(str, Enum):
    """Типы обработчиков логов"""
    FILE = "file"
    DATABASE = "database"
    CONSOLE = "console"
    ROTATING_FILE = "rotating_file"


class DatabaseType(str, Enum):
    """Типы поддерживаемых баз данных"""
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class DatabaseConfig:
    """Конфигурация базы данных для логов"""
    def __init__(self, **data):
        self.db_type = data.get('db_type', DatabaseType.SQLITE)
        self.host = data.get('host', 'localhost')
        self.port = data.get('port', 5432)
        self.database = data.get('database', 'logs')
        self.username = data.get('username', 'postgres')
        self.password = data.get('password', '')
        self.sqlite_path = data.get('sqlite_path', 'logs/app_logs.db')
        self.table_name = data.get('table_name', 'application_logs')


class LoggingConfig:
    """Конфигурация системы логирования"""
    
    def __init__(self, **data):
        # Основные настройки
        self.level = data.get('level', LogLevel.INFO)
        self.handlers = data.get('handlers', [LogHandler.CONSOLE, LogHandler.FILE])
        
        # Настройки файлового логирования
        self.log_dir = data.get('log_dir', Path("logs"))
        self.log_file = data.get('log_file', 'app.log')
        self.max_file_size = data.get('max_file_size', 10 * 1024 * 1024)  # 10MB
        self.backup_count = data.get('backup_count', 5)
        
        # Настройки форматирования
        self.log_format = data.get('log_format', 
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s")
        self.date_format = data.get('date_format', "%Y-%m-%d %H:%M:%S")
        
        # Настройки базы данных
        self.database = data.get('database', None)
        
        # Дополнительные настройки
        self.enable_json_logging = data.get('enable_json_logging', False)
        self.enable_context_logging = data.get('enable_context_logging', True)


class AppConfig(BaseSettings):
    """Основная конфигурация приложения"""
    
    # Настройки приложения
    app_name: str = Field(default="NiceGUI Example", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Настройки Camunda
    camunda_url: str = Field(default="https://localhost:8080", env="CAMUNDA_URL")
    camunda_username: str = Field(default="", env="CAMUNDA_USERNAME")
    camunda_password: str = Field(default="", env="CAMUNDA_PASSWORD")
    
    # Настройки LDAP
    ldap_server: str = Field(default="", env="LDAP_SERVER")
    ldap_user: str = Field(default="", env="LDAP_USER")
    ldap_password: str = Field(default="", env="LDAP_PASSWORD")
    
    # Настройки Mayan
    mayan_url: str = Field(default="http://localhost:8000", env="MAYAN_URL")
    mayan_username: str = Field(default="", env="MAYAN_USERNAME")
    mayan_password: str = Field(default="", env="MAYAN_PASSWORD")
    mayan_api_token: str = Field(default="", env="MAYAN_API_TOKEN")

    # Настройки почтового сервера
    email_server: str = Field(default="", env="EMAIL_SERVER")
    email_port: int = Field(default=993, env="EMAIL_PORT")
    email_username: str = Field(default="", env="EMAIL_USERNAME")
    email_password: str = Field(default="", env="EMAIL_PASSWORD")
    email_use_ssl: bool = Field(default=True, env="EMAIL_USE_SSL")
    email_protocol: str = Field(default="imap", env="EMAIL_PROTOCOL")  # imap или pop3
    email_allowed_senders: str = Field(default="", env="EMAIL_ALLOWED_SENDERS")  # Через запятую
    email_check_interval: int = Field(default=300, env="EMAIL_CHECK_INTERVAL")  # Интервал проверки в секундах
    
    
    # Логирование
    logging: LoggingConfig = Field(default_factory=lambda: LoggingConfig())
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Глобальный экземпляр конфигурации
config = AppConfig()