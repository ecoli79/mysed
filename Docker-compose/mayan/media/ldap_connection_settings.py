
from __future__ import absolute_import

from mayan.settings.production import *
import ldap
import os
from django_auth_ldap.config import LDAPSearch, GroupOfNamesType, LDAPSearchUnion, NestedActiveDirectoryGroupType, PosixGroupType

#from .base import *
from django.conf import settings
from django.contrib.auth import get_user_model

SECRET_KEY = '<your secret key>'

# makes sure this works in Active Directory
ldap.set_option(ldap.OPT_REFERRALS, 0)

# This is the default, but I like to be explicit.
AUTH_LDAP_ALWAYS_UPDATE_USER = True


# Получаем LDAP учетные данные из переменных окружения
# Переменные должны быть установлены в docker-compose.yml
LDAP_USER_AUTO_CREATION = os.environ.get('LDAP_USER_AUTO_CREATION')
LDAP_URL = os.environ.get('LDAP_USER_AUTO_CREATION')
LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN')
LDAP_ADDITIONAL_USER_DN = os.environ.get('LDAP_ADDITIONAL_USER_DN')
LDAP_ADMIN_DN = os.environ.get('LDAP_USER')
LDAP_PASSWORD = os.environ.get('LDAP_PASSWORD')

# Проверяем, что пароль установлен
if not LDAP_PASSWORD:
    raise ValueError(
        'LDAP_PASSWORD не установлен. '
        'Установите переменную окружения LDAP_PASSWORD в docker-compose.yml'
    )

AUTH_LDAP_SERVER_URI = LDAP_URL
AUTH_LDAP_BIND_DN = LDAP_ADMIN_DN
AUTH_LDAP_BIND_PASSWORD = LDAP_PASSWORD


AUTH_LDAP_USER_SEARCH = LDAPSearch(
    LDAP_BASE_DN,
    ldap.SCOPE_SUBTREE,
    "(uid=%(user)s)"
)
AUTH_LDAP_USER_ATTR_MAP = {
                        "first_name": "sn",
                        "last_name": "givenName",
			            "email": "mail"
                          }


AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    LDAP_BASE_DN,
    ldap.SCOPE_SUBTREE,
    '(objectClass=posixGroup)'
)

AUTH_LDAP_GROUP_TYPE = PosixGroupType()

AUTH_LDAP_USER_FLAGS_BY_GROUP = {
    'is_superuser': 'cn=admins,dc=permgp7,dc=ru',
}

# Создавать группы в Django, если их нет
AUTH_LDAP_MIRROR_GROUPS = True

# Опционально: синхронизировать группы при каждом входе
AUTH_LDAP_FIND_GROUP_PERMS = True


AUTHENTICATION_BACKENDS = (
'django_auth_ldap.backend.LDAPBackend',
#'mayan.settings.settings_local.EmailOrUsernameModelBackend',
'django.contrib.auth.backends.ModelBackend',
)

class EmailOrUsernameModelBackend(object):
    """
    This is a ModelBacked that allows authentication with either a username or an email address.

    """
    def authenticate(self, username=None, password=None):
        if '@' in username:
            kwargs = {'email': username}
        else:
            kwargs = {'username': username}
        try:
            user = get_user_model().objects.get(**kwargs)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None

    def get_user(self, username):
        try:
            return get_user_model().objects.get(pk=username)
        except get_user_model().DoesNotExist:
            return None
