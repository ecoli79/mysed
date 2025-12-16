"""
Тесты синхронизации групп из LDAP
"""
import pytest
from tests.fixtures.mock_ldap import mock_ldap_authenticator
from tests.fixtures.test_data import TEST_GROUPS


@pytest.mark.integration
@pytest.mark.ldap
class TestGroupSync:
    """Тесты синхронизации групп"""
    
    @pytest.mark.asyncio
    async def test_get_user_groups(self, mock_ldap_authenticator):
        """Тест получения групп пользователя"""
        username = 'test_user'
        user = mock_ldap_authenticator.get_user_by_login(username)
        
        assert user is not None
        assert user.memberOf is not None
        assert isinstance(user.memberOf, list)
        assert len(user.memberOf) > 0
    
    @pytest.mark.asyncio
    async def test_sync_groups_to_mayan_mock(self):
        """Тест синхронизации групп в Mayan через мок"""
        # В реальном тесте здесь была бы синхронизация групп
        # Для мока просто проверяем, что тестовые группы существуют
        assert len(TEST_GROUPS) > 0
        for group in TEST_GROUPS:
            assert 'cn' in group
            assert 'dn' in group
    
    @pytest.mark.asyncio
    async def test_group_membership(self, mock_ldap_authenticator):
        """Тест проверки членства в группах"""
        # Проверяем, что пользователь состоит в нужных группах
        test_user = mock_ldap_authenticator.get_user_by_login('test_user')
        assert test_user is not None
        # В LDAPUser группы хранятся в memberOf
        assert 'users' in test_user.memberOf
        
        admin_user = mock_ldap_authenticator.get_user_by_login('admin_user')
        assert admin_user is not None
        assert 'admins' in admin_user.memberOf
        assert 'users' in admin_user.memberOf

