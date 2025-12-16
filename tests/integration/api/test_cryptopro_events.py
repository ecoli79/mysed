"""
Тесты обработки событий КриптоПро
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from api_router import api_router
from tests.fixtures.test_data import TEST_CERTIFICATES


@pytest.fixture
def test_app():
    """Создает тестовое FastAPI приложение"""
    app = FastAPI()
    app.include_router(api_router)
    return app


@pytest.fixture
def test_client(test_app):
    """Создает тестовый клиент для FastAPI"""
    return TestClient(test_app)


@pytest.mark.integration
@pytest.mark.api
class TestCryptoproEvents:
    """Тесты обработки событий КриптоПро"""
    
    def test_certificates_loaded_event(self, test_client):
        """Тест обработки события загрузки сертификатов"""
        event_data = {
            'event': 'certificates_loaded',
            'data': {
                'certificates': TEST_CERTIFICATES,
                'count': len(TEST_CERTIFICATES),
                'show_all': False,
                'task_id': 'task_123',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'options' in data
        assert 'certificates' in data
        assert data['filtered_count'] <= data['total_count']
    
    def test_certificate_selected_event(self, test_client):
        """Тест обработки события выбора сертификата"""
        # Сначала загружаем сертификаты
        load_event = {
            'event': 'certificates_loaded',
            'data': {
                'certificates': TEST_CERTIFICATES,
                'count': len(TEST_CERTIFICATES),
                'show_all': True,
            }
        }
        test_client.post('/api/cryptopro-event', json=load_event)
        
        # Затем выбираем сертификат
        select_event = {
            'event': 'certificate_selected',
            'data': {
                'value': '0',
                'text': 'CN=Тестовый Пользователь',
                'certificate': TEST_CERTIFICATES[0],
                'task_id': 'task_123',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=select_event)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['action'] == 'certificate_selected'
    
    def test_signature_completed_event(self, test_client):
        """Тест обработки события завершения подписания"""
        event_data = {
            'event': 'signature_completed',
            'data': {
                'signature': 'base64_encoded_signature_data',
                'certificateInfo': {
                    'subject': 'CN=Тестовый Пользователь',
                    'issuer': 'CN=Test CA',
                },
                'originalData': 'original_data_hash',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['action'] == 'signature_completed'
    
    def test_signature_error_event(self, test_client):
        """Тест обработки события ошибки подписания"""
        event_data = {
            'event': 'signature_error',
            'data': {
                'error': 'Ошибка подписания документа',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'error'
        assert data['action'] == 'signature_error'
        assert 'error' in data['message'].lower() or 'ошибка' in data['message'].lower()
    
    def test_certificates_error_event(self, test_client):
        """Тест обработки события ошибки загрузки сертификатов"""
        event_data = {
            'event': 'certificates_error',
            'data': {
                'error': 'Плагин КриптоПро не установлен',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'error'
        assert data['action'] == 'show_error'
    
    def test_no_certificates_event(self, test_client):
        """Тест обработки события отсутствия сертификатов"""
        event_data = {
            'event': 'no_certificates',
            'data': {
                'message': 'Сертификаты не найдены',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'warning'
        assert data['action'] == 'show_warning'

