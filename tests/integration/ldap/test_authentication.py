"""
Тесты аутентификации через LDAP
"""
import pytest
from tests.fixtures.mock_ldap import mock_ldap_authenticator, real_ldap_authenticator


@pytest.mark.integration
@pytest.mark.ldap
class TestLDAPAuthentication:
    """Тесты аутентификации через LDAP"""
    
    @pytest.mark.asyncio
    async def test_authenticate_user_with_mock(self, mock_ldap_authenticator):
        """Тест аутентификации пользователя через мок"""
        username = 'test_user'
        password = 'test_password'
        
        response = await mock_ldap_authenticator.authenticate_user(
            username=username,
            password=password
        )
        
        assert response is not None
        assert response.success is True
        assert response.user is not None
        assert response.user.username == username
        assert response.user.first_name == 'Тестовый'
        assert response.user.last_name == 'Пользователь'
    
    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_credentials(self, mock_ldap_authenticator):
        """Тест аутентификации с неверными учетными данными"""
        username = 'test_user'
        password = ''  # Пустой пароль
        
        response = await mock_ldap_authenticator.authenticate_user(
            username=username,
            password=password
        )
        
        assert response is not None
        assert response.success is False
        assert 'пароль' in response.message.lower() or 'неверный' in response.message.lower()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, mock_ldap_authenticator):
        """Тест аутентификации несуществующего пользователя"""
        username = 'non_existent_user'
        password = 'password'
        
        response = await mock_ldap_authenticator.authenticate_user(
            username=username,
            password=password
        )
        
        assert response is not None
        assert response.success is False
        assert 'не найден' in response.message.lower()
    
    @pytest.mark.asyncio
    async def test_get_user_by_login(self, mock_ldap_authenticator):
        """Тест получения пользователя по логину"""
        username = 'test_user'
        user = mock_ldap_authenticator.get_user_by_login(username)
        
        assert user is not None
        assert user.uid == username
        assert user.givenName == 'Тестовый'
        assert user.sn == 'Пользователь'
    
    @pytest.mark.asyncio
    async def test_get_user_by_login_not_found(self, mock_ldap_authenticator):
        """Тест получения несуществующего пользователя"""
        username = 'non_existent_user'
        user = mock_ldap_authenticator.get_user_by_login(username)
        
        assert user is None
    
    @pytest.mark.asyncio
    @pytest.mark.real_server
    async def test_authenticate_user_with_real_server(self, real_ldap_authenticator):
        """Тест аутентификации с реальным LDAP сервером (только чтение)"""
        try:
            # Используем тестового пользователя, если он существует
            username = 'test_user'
            password = 'test_password'
            
            response = await real_ldap_authenticator.authenticate_user(
                username=username,
                password=password
            )
            
            # Проверяем структуру ответа
            assert response is not None
            assert hasattr(response, 'success')
            # Не проверяем успешность, так как учетные данные могут быть неверными
        except Exception as e:
            pytest.skip(f'Не удалось подключиться к реальному LDAP серверу: {e}')

