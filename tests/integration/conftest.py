"""
Конфигурация и фикстуры для интеграционных тестов
"""
import os
import pytest
from typing import Optional
from pathlib import Path

from config.settings import AppConfig


@pytest.fixture(scope='session')
def test_config() -> AppConfig:
    """Создает тестовую конфигурацию приложения"""
    # Переопределяем настройки для тестов
    test_env = {
        'ENVIRONMENT': 'test',
        'TEST_USE_REAL_SERVERS': os.getenv('TEST_USE_REAL_SERVERS', 'false'),
    }
    
    # Устанавливаем переменные окружения
    for key, value in test_env.items():
        os.environ[key] = value
    
    # Создаем конфигурацию
    config = AppConfig()
    
    # Переопределяем URL для тестов, если указаны
    if os.getenv('TEST_CAMUNDA_URL'):
        config.camunda_url = os.getenv('TEST_CAMUNDA_URL')
    if os.getenv('TEST_MAYAN_URL'):
        config.mayan_url = os.getenv('TEST_MAYAN_URL')
    if os.getenv('TEST_LDAP_SERVER'):
        config.ldap_server = os.getenv('TEST_LDAP_SERVER')
    if os.getenv('TEST_EMAIL_SERVER'):
        config.email_server = os.getenv('TEST_EMAIL_SERVER')
    
    return config


@pytest.fixture
def use_real_servers() -> bool:
    """Проверяет, нужно ли использовать реальные серверы"""
    return os.getenv('TEST_USE_REAL_SERVERS', 'false').lower() == 'true'


@pytest.fixture
def test_user_data():
    """Возвращает тестовые данные пользователя"""
    return {
        'username': 'test_user',
        'first_name': 'Тестовый',
        'last_name': 'Пользователь',
        'email': 'test@example.com',
        'groups': ['users'],
    }


@pytest.fixture
def test_document_data():
    """Возвращает тестовые данные документа"""
    return {
        'document_id': '123',
        'label': 'Тестовый документ',
        'filename': 'test_document.pdf',
        'file_latest_filename': 'test_document.pdf',
        'document_type': 'Входящие',
    }


@pytest.fixture
def test_process_data():
    """Возвращает тестовые данные процесса"""
    return {
        'process_definition_id': 'test_process:1:123',
        'process_instance_id': 'proc_inst_123',
        'business_key': 'test_business_key',
    }


@pytest.fixture
def test_task_data():
    """Возвращает тестовые данные задачи"""
    return {
        'task_id': 'task_123',
        'name': 'Тестовая задача',
        'assignee': 'test_user',
        'process_instance_id': 'proc_inst_123',
        'process_definition_id': 'test_process:1:123',
    }

