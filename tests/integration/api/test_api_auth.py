"""
Тесты аутентификации API
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
class TestAPIAuth:
    """Тесты аутентификации API"""
    
    def test_cryptopro_event_endpoint_exists(self, test_client):
        """Тест существования endpoint для событий КриптоПро"""
        # Отправляем пустой запрос для проверки существования endpoint
        response = test_client.post('/api/cryptopro-event', json={})
        
        # Endpoint должен существовать (может вернуть ошибку, но не 404)
        assert response.status_code != 404
    
    def test_cryptopro_event_requires_json(self, test_client):
        """Тест, что endpoint требует JSON"""
        response = test_client.post('/api/cryptopro-event')
        
        # Endpoint может обработать пустой запрос и вернуть 200 с ошибкой в теле
        # или вернуть 422/400. Проверяем, что это не 200 с успешным ответом
        if response.status_code == 200:
            data = response.json()
            # Если статус 200, то в теле должна быть ошибка
            assert data.get('status') != 'success'
        else:
            # Или статус должен быть ошибкой
            assert response.status_code in [400, 422, 500]

