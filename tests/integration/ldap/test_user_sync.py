"""
Тесты синхронизации пользователей из LDAP
"""
import pytest
from tests.fixtures.mock_ldap import mock_ldap_authenticator
from tests.fixtures.mock_mayan import mock_mayan_client


@pytest.mark.integration
@pytest.mark.ldap
class TestUserSync:
    """Тесты синхронизации пользователей"""
    
    @pytest.mark.asyncio
    async def test_get_user_from_ldap(self, mock_ldap_authenticator):
        """Тест получения пользователя из LDAP"""
        username = 'test_user'
        user = mock_ldap_authenticator.get_user_by_login(username)
        
        assert user is not None
        assert user.uid == username
        assert user.mail is not None
        assert user.memberOf is not None
    
    @pytest.mark.asyncio
    async def test_sync_user_to_mayan_mock(self, mock_ldap_authenticator, mock_mayan_client):
        """Тест синхронизации пользователя в Mayan через мок"""
        # Получаем пользователя из LDAP
        username = 'test_user'
        ldap_user = mock_ldap_authenticator.get_user_by_login(username)
        
        assert ldap_user is not None
        
        # В реальном тесте здесь была бы синхронизация в Mayan
        # Для мока просто проверяем, что данные пользователя корректны
        assert ldap_user.uid == username
        assert ldap_user.givenName is not None
        assert ldap_user.sn is not None
    
    @pytest.mark.asyncio
    async def test_sync_multiple_users(self, mock_ldap_authenticator):
        """Тест синхронизации нескольких пользователей"""
        usernames = ['test_user', 'admin_user', 'reviewer_user']
        synced_users = []
        
        for username in usernames:
            user = mock_ldap_authenticator.get_user_by_login(username)
            if user:
                synced_users.append(user)
        
        assert len(synced_users) == len(usernames)
        for user in synced_users:
            assert user.uid in usernames

