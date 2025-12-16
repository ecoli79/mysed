"""
Глобальная конфигурация pytest для всех тестов
"""
import os
import sys
import logging
from pathlib import Path
from typing import Generator

import pytest

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настройка логирования для тестов
logging.basicConfig(
    level=logging.WARNING,  # Уменьшаем уровень логирования в тестах
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Отключаем логирование для внешних библиотек
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('ldap3').setLevel(logging.WARNING)


@pytest.fixture(scope='session')
def test_env_file() -> Path:
    """Возвращает путь к файлу .env.test"""
    return project_root / '.env.test'


@pytest.fixture(scope='session', autouse=True)
def setup_test_environment(test_env_file: Path):
    """Настройка тестового окружения перед запуском всех тестов"""
    # Устанавливаем переменные окружения для тестов
    os.environ.setdefault('TEST_USE_REAL_SERVERS', 'false')
    os.environ.setdefault('ENVIRONMENT', 'test')
    
    # Если файл .env.test существует, pydantic-settings автоматически его загрузит
    # через переменную окружения ENV_FILE или через явную настройку
    
    yield
    
    # Очистка после тестов (если нужна)
    pass


@pytest.fixture
def use_real_servers() -> bool:
    """Фикстура для проверки, использовать ли реальные серверы"""
    return os.getenv('TEST_USE_REAL_SERVERS', 'false').lower() == 'true'


@pytest.fixture
def test_data_dir() -> Path:
    """Возвращает путь к директории с тестовыми данными"""
    return project_root / 'tests' / 'fixtures' / 'data'


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Возвращает временную директорию для тестов"""
    return tmp_path


def pytest_addoption(parser):
    """Добавляет опции командной строки для pytest"""
    parser.addoption(
        '--TEST_APP_URL',
        action='store',
        default=None,
        help='URL тестового приложения для E2E тестов'
    )
    parser.addoption(
        '--TEST_USERNAME',
        action='store',
        default=None,
        help='Имя пользователя для E2E тестов'
    )
    parser.addoption(
        '--TEST_PASSWORD',
        action='store',
        default=None,
        help='Пароль для E2E тестов'
    )

