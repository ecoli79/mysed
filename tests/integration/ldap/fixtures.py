"""
Фикстуры для тестов LDAP
"""
import pytest


@pytest.fixture
def ldap_authenticator_factory():
    """Фабрика для создания LDAP аутентификаторов"""
    def _create_authenticator(use_mock: bool = True, **kwargs):
        if use_mock:
            from tests.fixtures.mock_ldap import MockLDAPAuthenticator
            return MockLDAPAuthenticator(**kwargs)
        else:
            from auth.ldap_auth import LDAPAuthenticator
            return LDAPAuthenticator(**kwargs)
    return _create_authenticator

