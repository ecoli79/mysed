"""
Интеграционные тесты API подписания документов
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
from tests.fixtures.test_data import TEST_DOCUMENTS


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
class TestDocumentSigningAPI:
    """Тесты API подписания документов"""
    
    def test_cryptopro_event_certificates_loaded(self, test_client: TestClient):
        """Тест обработки события загрузки сертификатов"""
        event_data = {
            'event': 'certificates_loaded',
            'data': {
                'certificates': [
                    {
                        'subject': 'CN=Test User',
                        'validTo': '2025-12-31',
                        'issuer': 'Test CA',
                        'thumbprint': 'test_thumbprint'
                    }
                ],
                'count': 1,
                'show_all': False
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
    
    def test_cryptopro_event_certificate_selected(self, test_client: TestClient):
        """Тест обработки события выбора сертификата"""
        # Сначала загружаем сертификаты
        load_event = {
            'event': 'certificates_loaded',
            'data': {
                'certificates': [
                    {
                        'subject': 'CN=Test User',
                        'validTo': '2025-12-31',
                        'issuer': 'Test CA',
                        'thumbprint': 'test_thumbprint'
                    }
                ],
                'count': 1,
                'show_all': True  # Показываем все для теста
            }
        }
        test_client.post('/api/cryptopro-event', json=load_event)
        
        # Затем выбираем сертификат (формат из test_cryptopro_events.py)
        select_event = {
            'event': 'certificate_selected',
            'data': {
                'value': '0',
                'text': 'CN=Test User',
                'certificate': {
                    'subject': 'CN=Test User',
                    'validTo': '2025-12-31',
                    'issuer': 'Test CA'
                },
                'task_id': 'test_task_123'
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=select_event)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['action'] == 'certificate_selected'
    
    def test_cryptopro_event_signature_completed(self, test_client: TestClient):
        """Тест обработки события завершения подписания"""
        event_data = {
            'event': 'signature_completed',
            'data': {
                'signature': 'MOCK_SIGNATURE_BASE64_DATA',
                'certificateInfo': {
                    'subject': 'CN=Test User',
                    'issuer': 'Test CA',
                },
                'originalData': 'original_data_hash',
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['action'] == 'signature_completed'
        assert 'message' in data
    
    def test_cryptopro_event_signature_error(self, test_client: TestClient):
        """Тест обработки события ошибки подписания"""
        event_data = {
            'event': 'signature_error',
            'data': {
                'error': 'Ошибка подписания документа',
                'task_id': 'test_task_123'
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
    
    def test_cryptopro_event_signature_verified(self, test_client: TestClient):
        """Тест обработки события проверки подписи"""
        # Сначала отправляем событие завершения подписания
        complete_event = {
            'event': 'signature_completed',
            'data': {
                'signature': 'MOCK_SIGNATURE_BASE64_DATA',
                'certificateInfo': {
                    'subject': 'CN=Test User',
                    'issuer': 'Test CA',
                },
                'originalData': 'original_data_hash',
            }
        }
        test_client.post('/api/cryptopro-event', json=complete_event)
        
        # Затем проверяем подпись
        event_data = {
            'event': 'signature_verified',
            'data': {
                'isValid': True,  # API ожидает camelCase
                'certificateInfo': {
                    'subject': 'CN=Test User',
                    'issuer': 'Test CA',
                },
                'timestamp': '2025-12-16T20:29:16'
            }
        }
        
        response = test_client.post('/api/cryptopro-event', json=event_data)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['action'] == 'signature_verified'
        assert 'message' in data
    
    def test_check_signature_result(self, test_client: TestClient):
        """Тест проверки результата подписания"""
        # Сначала отправляем событие завершения подписания
        event_data = {
            'event': 'signature_completed',
            'data': {
                'signature': 'MOCK_SIGNATURE_BASE64_DATA',
                'certificateInfo': {
                    'subject': 'CN=Test User',
                    'issuer': 'Test CA',
                },
                'originalData': 'original_data_hash',
            }
        }
        test_client.post('/api/cryptopro-event', json=event_data)
        
        # Затем проверяем наличие результата через событие
        check_event = {
            'event': 'check_signature_result',
            'data': {}
        }
        response = test_client.post('/api/cryptopro-event', json=check_event)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] in ['success', 'pending']
        assert 'has_result' in data
        assert 'message' in data

