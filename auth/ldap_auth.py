from turtle import position
from ldap3 import Server, Connection, SUBTREE, ALL
from models import UserSession, AuthResponse, LDAPUser
from config.settings import config
from datetime import datetime
import secrets
from typing import Optional
from app_logging.logger import get_logger


logger = get_logger(__name__)

class LDAPAuthenticator:
    def __init__(self):
        # Проверяем наличие всех необходимых настроек
        if not config.ldap_server:
            raise ValueError("LDAP сервер не настроен. Установите переменную LDAP_SERVER в файле .env")
        if not config.ldap_user:
            raise ValueError("LDAP пользователь не настроен. Установите переменную LDAP_USER в файле .env")
        if not config.ldap_password:
            raise ValueError("LDAP пароль не настроен. Установите переменную LDAP_PASSWORD в файле .env")
        
        self.ldap_server = config.ldap_server
        self.base_dn = 'dc=permgp7,dc=ru'
        self.admin_dn = config.ldap_user
        self.admin_password = config.ldap_password
        
        self.server = Server(self.ldap_server, get_info=ALL)
        
    async def authenticate_user(self, username: str, password: str) -> AuthResponse:
        """Аутентификация пользователя через LDAP"""
        try:
            # Создаем соединение с LDAP сервером
            conn = Connection(self.server, user=self.admin_dn, password=self.admin_password, auto_bind=True)
            
            # Поиск пользователя
            search_filter = f'(uid={username})'
            conn.search(
                self.base_dn, 
                search_filter, 
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail', 'memberOf', 'userPassword']
            )
            
            if not conn.entries:
                return AuthResponse(
                    success=False,
                    message='Пользователь не найден'
                )
            
            user_entry = conn.entries[0]
            
            # Проверяем группы пользователя
            # В OpenLDAP с posixGroup нужно искать группы, где memberUid содержит username
            groups = []
            
            # Извлекаем группу из DN, если пользователь находится внутри группы
            # Например, из "cn=Денис Имполитов,cn=admins,dc=permgp7,dc=ru" извлекаем "admins"
            user_dn = str(user_entry.entry_dn)
            dn_parts = user_dn.split(',')
            for part in dn_parts:
                if part.startswith('cn=') and part != f'cn={user_entry.cn.value}':
                    # Это не имя пользователя, а группа
                    group_name = part.split('=')[1]
                    if group_name not in groups:
                        groups.append(group_name)
                        logger.debug(f'Извлечена группа из DN для пользователя {username}: {group_name}')
            
            # Сначала пробуем получить группы через memberOf (для groupOfNames)
            if hasattr(user_entry, 'memberOf') and user_entry.memberOf:
                for group_dn in user_entry.memberOf:
                    group_name = str(group_dn).split(',')[0].split('=')[1]
                    if group_name not in groups:
                        groups.append(group_name)
            
            # Дополнительно ищем группы posixGroup, где memberUid содержит username
            try:
                group_search_filter = f'(&(objectClass=posixGroup)(memberUid={username}))'
                conn.search(
                    self.base_dn,
                    group_search_filter,
                    SUBTREE,
                    attributes=['cn']
                )
                
                for group_entry in conn.entries:
                    if hasattr(group_entry, 'cn') and group_entry.cn:
                        group_name = group_entry.cn.value
                        if group_name not in groups:
                            groups.append(group_name)
                            logger.debug(f'Найдена группа posixGroup для пользователя {username}: {group_name}')
            except Exception as e:
                logger.warning(f'Ошибка при поиске групп posixGroup для пользователя {username}: {e}')
            
            logger.info(f'Пользователь {username} состоит в группах: {groups}')

            # Попытка аутентификации пользователя
            # Используем DN пользователя из результата поиска
            user_dn = str(user_entry.entry_dn)
            logger.info(f"Попытка аутентификации пользователя {username} с DN: {user_dn}")
            try:
                user_conn = Connection(self.server, user=user_dn, password=password, auto_bind=True)
                user_conn.unbind()
                
                # Создаем сессию пользователя
                user_session = UserSession(
                    user_id=user_entry.uid.value,
                    username=user_entry.uid.value,
                    first_name=user_entry.givenName.value,
                    last_name=user_entry.sn.value,
                    email=user_entry.mail.value if hasattr(user_entry, 'mail') else None,
                    groups=groups,
                    login_time=datetime.now().isoformat(),
                    last_activity=datetime.now().isoformat(),
                    is_active=True,
                    mayan_api_token=None  # Будет установлен ниже
                )

                # Создаем API токен для пользователя в Mayan EDMS
                try:
                    from services.mayan_connector import MayanClient
                    from config.settings import config
                    
                    if config.mayan_url:
                        logger.info(f'LDAP: Создаем API токен Mayan EDMS для пользователя {username}')
                        
                        # Создаем временный клиент с системными учетными данными
                        temp_mayan_client = MayanClient(
                            base_url=config.mayan_url,
                            username=config.mayan_username,
                            password=config.mayan_password,
                            api_token=config.mayan_api_token,
                            verify_ssl=False
                        )
                        
                        # Создаем API токен для пользователя
                        mayan_token = await temp_mayan_client.create_user_api_token(username, password)
                        if mayan_token:
                            user_session.mayan_api_token = mayan_token
                            logger.info(f'LDAP: API токен Mayan EDMS успешно создан для пользователя {username}')
                            logger.info(f'LDAP: Токен сохранен в сессии: {mayan_token[:10]}...{mayan_token[-5:] if len(mayan_token) > 15 else "***"}')
                        else:
                            logger.warning(f'LDAP: Не удалось создать API токен Mayan EDMS для пользователя {username}')
                    else:
                        logger.warning("🔑 LDAP: Mayan EDMS не настроен, пропускаем создание API токена")
                        
                except Exception as e:
                    logger.error(f'LDAP: Ошибка при создании API токена Mayan EDMS для пользователя {username}: {e}')
                    # Продолжаем без токена - пользователь сможет работать с системными учетными данными
                
                # Генерируем токен сессии
                token = self._generate_session_token(user_session)
                
                return AuthResponse(
                    success=True,
                    message='Успешная аутентификация',
                    user=user_session,
                    token=token
                )
                
            except Exception as e:
                logger.warning(f'Ошибка аутентификации пользователя {username}: {e}')
                return AuthResponse(
                    success=False,
                    message='Неверный пароль'
                )
                
        except Exception as e:
            logger.error(f'Ошибка подключения к LDAP серверу: {e}')
            return AuthResponse(
                success=False,
                message='Ошибка подключения к серверу аутентификации'
            )
    
    def _generate_session_token(self, user: UserSession) -> str:
        """Генерирует токен сессии для пользователя"""
        # Используем криптографически стойкий генератор случайных чисел
        token_data = f"{user.username}:{secrets.token_urlsafe(32)}"
        return token_data
    
    async def get_user_groups(self, username: str) -> list:
        """Получает группы пользователя из LDAP"""
        try:
            conn = Connection(self.server, user=self.admin_dn, password=self.admin_password, auto_bind=True)
            
            search_filter = f'(uid={username})'
            conn.search(
                self.base_dn, 
                search_filter, 
                SUBTREE,
                attributes=['memberOf']
            )
            
            if not conn.entries:
                return []
            
            user_entry = conn.entries[0]
            groups = []
            
            if hasattr(user_entry, 'memberOf') and user_entry.memberOf:
                for group_dn in user_entry.memberOf:
                    group_name = str(group_dn).split(',')[0].split('=')[1]
                    groups.append(group_name)
            
            return groups
            
        except Exception as e:
            logger.error(f"Ошибка получения групп пользователя {username}: {e}")
            return []
    
    async def search_users(self, search_term: str = None) -> list:
        """Поиск пользователей в LDAP"""
        try:
            conn = Connection(self.server, user=self.admin_dn, password=self.admin_password, auto_bind=True)
            
            if search_term:
                search_filter = f'(|(uid=*{search_term}*)(cn=*{search_term}*)(givenName=*{search_term}*)(sn=*{search_term}*))'
            else:
                search_filter = '(uid=*)'
            
            conn.search(
                self.base_dn, 
                search_filter, 
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail']
            )
            
            users = []
            for entry in conn.entries:
                try:
                    user = LDAPUser(
                        dn=str(entry.entry_dn),
                        uid=entry.uid.value,
                        cn=entry.cn.value,
                        givenName=entry.givenName.value,
                        sn=entry.sn.value,
                        email=entry.mail.value if hasattr(entry, 'mail') else None,
                        memberOf=[]
                    )
                    users.append(user)
                except Exception as e:
                    logger.warning(f"Ошибка обработки пользователя {entry}: {e}")
                    continue
            
            return users
            
        except Exception as e:
            logger.error(f"Ошибка поиска пользователей: {e}")
            return []

    def get_user_by_login(self, username: str) -> Optional[LDAPUser]:
        """Получает информацию о пользователе по логину (синхронно)"""
        try:
            conn = Connection(self.server, user=self.admin_dn, password=self.admin_password, auto_bind=True)
            
            search_filter = f'(uid={username})'
            conn.search(
                self.base_dn, 
                search_filter, 
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail', 'description']
            )
            
            if not conn.entries:
                return None
            
            entry = conn.entries[0]
            
            # ИСПРАВЛЕНИЕ: Правильно обрабатываем поля, которые могут отсутствовать или быть None
            email = entry.mail.value if hasattr(entry, 'mail') and entry.mail.value else None
            description = entry.description.value if hasattr(entry, 'description') and entry.description.value else ''
            
            user = LDAPUser(
                dn=str(entry.entry_dn),
                uid=entry.uid.value,
                cn=entry.cn.value,
                givenName=entry.givenName.value,
                sn=entry.sn.value,
                email=email,
                destription=description,
                memberOf=[]
            )
            
            conn.unbind()
            return user
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {username}: {e}")
            return None

    def find_user_by_login(self, username: str) -> Optional[LDAPUser]:
        """Находит пользователя по логину с использованием широкого поиска"""
        try:
            logger.info(f"Широкий поиск пользователя в LDAP: {username}")
            conn = Connection(self.server, user=self.admin_dn, password=self.admin_password, auto_bind=True)
            
            # Используем широкий поиск, как в search_users
            search_filter = f'(uid=*{username}*)'
            logger.info(f"LDAP широкий фильтр поиска: {search_filter}")
            
            conn.search(
                self.base_dn, 
                search_filter, 
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail', 'description']
            )
            
            logger.info(f"LDAP широкий поиск найден записей: {len(conn.entries)}")
            
            # Ищем точное совпадение по uid
            for entry in conn.entries:
                if entry.uid.value == username:
                    logger.info(f"LDAP точное совпадение найдено: {entry.entry_dn}")
                    
                    # ИСПРАВЛЕНИЕ: Правильно обрабатываем поля, которые могут отсутствовать или быть None
                    email = entry.mail.value if hasattr(entry, 'mail') and entry.mail.value else None
                    description = entry.description.value if hasattr(entry, 'description') and entry.description.value else ''
                    
                    user = LDAPUser(
                        dn=str(entry.entry_dn),
                        uid=entry.uid.value,
                        cn=entry.cn.value,
                        givenName=entry.givenName.value,
                        sn=entry.sn.value,
                        email=email,
                        destription=description,
                        memberOf=[]
                    )
                    conn.unbind()
                    return user
            
            logger.warning(f"Пользователь {username} не найден при широком поиске")
            conn.unbind()
            return None
            
        except Exception as e:
            logger.error(f"Ошибка широкого поиска пользователя {username}: {e}")
            return None