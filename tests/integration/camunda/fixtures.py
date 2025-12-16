"""
Фикстуры для тестов Camunda
"""
import pytest
from tests.fixtures.mock_camunda import MockCamundaClient


@pytest.fixture
def camunda_client_factory():
    """Фабрика для создания клиентов Camunda"""
    def _create_client(use_mock: bool = True, **kwargs):
        if use_mock:
            return MockCamundaClient(**kwargs)
        else:
            from services.camunda_connector import CamundaClient
            return CamundaClient(**kwargs)
    return _create_client

