"""
Фикстуры для тестов Email
"""
import pytest


@pytest.fixture
def email_client_factory():
    """Фабрика для создания клиентов Email"""
    def _create_client(use_mock: bool = True, **kwargs):
        if use_mock:
            from tests.fixtures.mock_email import MockEmailClient
            return MockEmailClient(**kwargs)
        else:
            from services.email_client import EmailClient
            return EmailClient(**kwargs)
    return _create_client

