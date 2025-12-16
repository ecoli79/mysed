"""
Фикстуры для тестов Mayan EDMS
"""
import pytest
from tests.fixtures.mock_mayan import MockMayanClient


@pytest.fixture
def mayan_client_factory():
    """Фабрика для создания клиентов Mayan"""
    def _create_client(use_mock: bool = True, **kwargs):
        if use_mock:
            return MockMayanClient(**kwargs)
        else:
            from services.mayan_connector import MayanClient
            return MayanClient(**kwargs)
    return _create_client

