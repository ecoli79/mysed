"""
Моки для LDAP операций
"""
import pytest
from unittest.mock import MagicMock, Mock
from typing import Dict, List, Any, Optional
from tests.fixtures.test_data import TEST_USERS, TEST_GROUPS


class MockLDAPConnection:
    """Мок LDAP соединения"""
    
    def __init__(self, server, user=None, password=None, auto_bind=False):
        self.server = server
        self.user = user
        self.password = password
        self.auto_bind = auto_bind
        self.entries = []
        self.bound = auto_bind
        
        # Инициализируем тестовые данные
        self._setup_test_data()
    
    def _setup_test_data(self):
        """Настраивает тестовые данные LDAP"""
        # Создаем мок entries для пользователей
        self._users = {user['username']: user for user in TEST_USERS}
        self._groups = {group['cn']: group for group in TEST_GROUPS}
    
    def bind(self):
        """Имитация привязки к LDAP"""
        if self.user and self.password:
            self.bound = True
            return True
        return False
    
    def search(self, search_base: str, search_filter: str, search_scope, attributes: List[str] = None):
        """Имитация поиска в LDAP"""
        self.entries = []
        
        # Простой парсинг фильтра
        if 'uid=' in search_filter:
            # Поиск пользователя
            username = search_filter.split('uid=')[1].split(')')[0]
            if username in self._users:
                user = self._users[username]
                entry = MockLDAPEntry(user)
                self.entries.append(entry)
        elif 'cn=' in search_filter and 'posixGroup' in search_filter:
            # Поиск групп
            # Упрощенная логика для тестов
            pass
    
    def unbind(self):
        """Имитация отключения от LDAP"""
        self.bound = False


class MockLDAPEntry:
    """Мок LDAP записи"""
    
    def __init__(self, user_data: Dict[str, Any]):
        self.entry_dn = user_data.get('dn', f"uid={user_data['username']},ou=People,dc=permgp7,dc=ru")
        self._user_data = user_data
        
        # Создаем атрибуты
        self.uid = MockAttribute(user_data.get('username'))
        self.cn = MockAttribute(f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip())
        self.givenName = MockAttribute(user_data.get('first_name', ''))
        self.sn = MockAttribute(user_data.get('last_name', ''))
        self.mail = MockAttribute(user_data.get('email', ''))
        self.memberOf = []
        
        # Добавляем группы
        for group_name in user_data.get('groups', []):
            self.memberOf.append(f"cn={group_name},ou=Groups,dc=permgp7,dc=ru")


class MockAttribute:
    """Мок LDAP атрибута"""
    
    def __init__(self, value):
        self.value = value
    
    def __str__(self):
        return str(self.value)


class MockLDAPServer:
    """Мок LDAP сервера"""
    
    def __init__(self, host, get_info=None):
        self.host = host
        self.get_info = get_info


class MockLDAPAuthenticator:
    """Мок LDAP аутентификатора"""
    
    def __init__(self):
        self.ldap_server = 'localhost'
        self.base_dn = 'dc=permgp7,dc=ru'
        self.admin_dn = 'cn=admin,dc=permgp7,dc=ru'
        self.admin_password = 'admin'
        self.server = MockLDAPServer(self.ldap_server)
        self._users = {user['username']: user for user in TEST_USERS}
    
    async def authenticate_user(self, username: str, password: str):
        """Имитация аутентификации пользователя"""
        from models import AuthResponse, UserSession
        
        if username not in self._users:
            return AuthResponse(
                success=False,
                message='Пользователь не найден',
                user=None
            )
        
        user_data = self._users[username]
        
        # В реальном тесте здесь должна быть проверка пароля
        # Для мока просто проверяем, что пароль не пустой
        if not password:
            return AuthResponse(
                success=False,
                message='Неверный пароль',
                user=None
            )
        
        from datetime import datetime
        return AuthResponse(
            success=True,
            message='Аутентификация успешна',
            user=UserSession(
                user_id=user_data['username'],
                username=user_data['username'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                email=user_data.get('email'),
                description=user_data.get('description'),
                groups=user_data.get('groups', []),
                login_time=datetime.now().isoformat(),
                last_activity=datetime.now().isoformat(),
                is_active=True,
            )
        )
    
    def get_user_by_login(self, username: str):
        """Имитация получения пользователя по логину"""
        if username in self._users:
            user_data = self._users[username]
            from models import LDAPUser
            return LDAPUser(
                dn=user_data.get('dn', f"uid={username},ou=People,dc=permgp7,dc=ru"),
                uid=user_data['username'],
                cn=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                givenName=user_data.get('first_name', ''),
                sn=user_data.get('last_name', ''),
                destription='',  # Опечатка в модели
                mail=user_data.get('email', ''),
                memberOf=user_data.get('groups', []),
                userPassword=None,
            )
        return None


@pytest.fixture
def mock_ldap_authenticator():
    """Фикстура для создания мок LDAP аутентификатора"""
    return MockLDAPAuthenticator()


@pytest.fixture
def real_ldap_authenticator(test_config, use_real_servers):
    """Фикстура для создания реального LDAP аутентификатора (если разрешено)"""
    if not use_real_servers:
        pytest.skip('Требуется реальный LDAP сервер (установите TEST_USE_REAL_SERVERS=true)')
    
    from auth.ldap_auth import LDAPAuthenticator
    return LDAPAuthenticator()

