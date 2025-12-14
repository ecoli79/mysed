# config/settings.py
from enum import Enum
from pathlib import Path
from typing import Optional, List
from pydantic import Field, ConfigDict, field_validator
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


class DatabaseConfig(BaseSettings):
    """Конфигурация базы данных для логов"""
    
    db_type: DatabaseType = Field(default=DatabaseType.SQLITE, env="LOG_DB_TYPE")
    host: str = Field(default='localhost', env="LOG_DB_HOST")
    port: int = Field(default=5432, env="LOG_DB_PORT")
    database: str = Field(default='logs', env="LOG_DB_NAME")
    username: str = Field(default='postgres', env="LOG_DB_USERNAME")
    password: str = Field(default='', env="LOG_DB_PASSWORD")
    sqlite_path: str = Field(default='logs/app_logs.db', env="LOG_SQLITE_PATH")
    table_name: str = Field(default='application_logs', env="LOG_TABLE_NAME")
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


class LoggingConfig(BaseSettings):
    """Конфигурация системы логирования"""
    
    # Основные настройки
    level: LogLevel = Field(default=LogLevel.INFO, env="LOG_LEVEL")
    handlers: List[LogHandler] = Field(
        default=[LogHandler.CONSOLE, LogHandler.FILE],
        env="LOG_HANDLERS"
    )
    
    # Настройки файлового логирования
    log_dir: Path = Field(default=Path("logs"), env="LOG_DIR")
    log_file: str = Field(default='app.log', env="LOG_FILE")
    max_file_size: int = Field(default=10 * 1024 * 1024, env="LOG_MAX_FILE_SIZE")  # 10MB
    backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    # Настройки форматирования
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        env="LOG_FORMAT"
    )
    date_format: str = Field(default="%Y-%m-%d %H:%M:%S", env="LOG_DATE_FORMAT")
    
    # Настройки базы данных
    database: Optional[DatabaseConfig] = None
    
    # Дополнительные настройки
    enable_json_logging: bool = Field(default=False, env="LOG_JSON_FORMAT")
    enable_context_logging: bool = Field(default=True, env="LOG_CONTEXT")
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @field_validator('handlers', mode='before')
    @classmethod
    def parse_handlers(cls, v):
        """Парсит строку handlers из .env в список"""
        if isinstance(v, str):
            # Разделяем по запятой и очищаем пробелы
            handlers = [h.strip() for h in v.split(',')]
            return [LogHandler(h) for h in handlers if h]
        return v
    
    @field_validator('log_dir', mode='before')
    @classmethod
    def parse_log_dir(cls, v):
        """Преобразует строку в Path"""
        if isinstance(v, str):
            return Path(v)
        return v
    
    def __init__(self, **data):
        super().__init__(**data)
        # Инициализируем database config если handlers содержит DATABASE
        if LogHandler.DATABASE in self.handlers and self.database is None:
            self.database = DatabaseConfig()


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
    mayan_incoming_document_type: str = Field(default="Входящие", env="MAYAN_INCOMING_DOCUMENT_TYPE")
    mayan_incoming_cabinet: str = Field(default="Входящие письма", env="MAYAN_INCOMING_CABINET")

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
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Глобальный экземпляр конфигурации
config = AppConfig()