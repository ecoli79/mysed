#!/usr/bin/env python3
"""
Скрипт синхронизации пользователей и групп из LDAP в Mayan EDMS
Автоматически проверяет новых пользователей и группы в LDAP и добавляет их в Mayan EDMS
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ldap3 import Server, Connection, SUBTREE, ALL
from services.mayan_connector import MayanClient
from config.settings import config
from models import LDAPUser, UserGroup
from app_logging.logger import setup_logging, get_logger

# Настройка логирования
setup_logging()
logger = get_logger(__name__)

class LDAPGroupSyncManager:
    """Менеджер синхронизации групп между LDAP и Mayan EDMS"""
    
    def __init__(self, mayan_client: MayanClient):
        self.mayan_client = mayan_client
        self.sync_state_file = Path("logs/group_sync_state.json")
        self.synced_groups = set()
        self.remove_old_members = False  # Флаг для удаления старых участников
        self._load_sync_state()
    
    def _load_sync_state(self):
        """Загружает состояние синхронизации групп из файла"""
        try:
            if self.sync_state_file.exists():
                with open(self.sync_state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.synced_groups = set(state.get('synced_groups', []))
                    logger.info(f"Состояние синхронизации групп загружено: {len(self.synced_groups)} групп")
            else:
                logger.info("Файл состояния синхронизации групп не найден, начинаем с чистого листа")
        except Exception as e:
            logger.warning(f"Ошибка загрузки состояния синхронизации групп: {e}")
    
    def _save_sync_state(self):
        """Сохраняет состояние синхронизации групп в файл"""
        try:
            state = {
                'last_sync_time': datetime.now().isoformat(),
                'synced_groups': list(self.synced_groups)
            }
            
            # Создаем директорию logs если её нет
            self.sync_state_file.parent.mkdir(exist_ok=True)
            
            with open(self.sync_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Состояние синхронизации групп сохранено: {len(self.synced_groups)} групп")
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния синхронизации групп: {e}")
    
    def get_ldap_groups(self, ldap_server: Server) -> List[UserGroup]:
        """Получает все группы из LDAP"""
        groups = []
        
        try:
            # Подключение к LDAP
            conn = Connection(
                ldap_server, 
                user=config.ldap_user, 
                password=config.ldap_password, 
                auto_bind=True
            )
            
            # Поиск всех групп
            search_filter = '(objectClass=posixGroup)'
            base_dn = 'dc=permgp7,dc=ru'
            
            conn.search(
                base_dn,
                search_filter,
                SUBTREE,
                attributes=['cn', 'memberUid', 'description', 'objectClass']
            )
            
            logger.info(f"Найдено {len(conn.entries)} групп в LDAP")
            
            for entry in conn.entries:
                try:
                    # Получаем список участников группы
                    members = []
                    if hasattr(entry, 'memberUid') and entry.memberUid:
                        members = list(entry.memberUid.values)
                    
                    # Определяем тип группы (статическая или динамическая)
                    is_dynamic = False
                    if hasattr(entry, 'objectClass') and entry.objectClass:
                        object_classes = [str(oc).lower() for oc in entry.objectClass.values]
                        is_dynamic = 'dynamicgroup' in object_classes or 'groupofnames' in object_classes
                    
                    group = UserGroup(
                        cn=entry.cn.value,
                        description=entry.description.value if hasattr(entry, 'description') else None,
                        memberUid=members,
                        is_dynamic=is_dynamic,
                        group_type="dynamic" if is_dynamic else "static"
                    )
                    groups.append(group)
                    
                except Exception as e:
                    logger.warning(f"Ошибка обработки группы {entry}: {e}")
                    continue
            
            conn.unbind()
            logger.info(f"Получено {len(groups)} групп из LDAP")
            
        except Exception as e:
            logger.error(f"Ошибка получения групп из LDAP: {e}")
        
        return groups
    
    def get_mayan_groups(self) -> List[Dict[str, Any]]:
        """Получает все группы из Mayan EDMS"""
        try:
            # Используем новый метод MayanClient
            groups = self.mayan_client.get_groups()
            logger.info(f"Получено {len(groups)} групп из Mayan EDMS")
            return groups
                
        except Exception as e:
            logger.error(f"Ошибка получения групп из Mayan EDMS: {e}")
            return []
    
    def _get_group_members(self, group_id: str) -> List[str]:
        """Получает список участников группы"""
        try:
            # Используем новый метод MayanClient
            users = self.mayan_client.get_group_users(group_id)
            members = [user.get('username') for user in users if user.get('username')]
            logger.debug(f"Получено {len(members)} участников группы {group_id}")
            return members
            
        except Exception as e:
            logger.error(f"Ошибка получения участников группы {group_id}: {e}")
            return []
    
    def _add_group_members(self, group_name: str, member_usernames: List[str]) -> int:
        """Добавляет участников в группу Mayan EDMS"""
        try:
            logger.info(f"Добавляем участников в группу {group_name}")
            
            # Получаем ID группы
            groups = self.get_mayan_groups()
            group_id = None
            for group in groups:
                if group['name'] == group_name:
                    group_id = group['id']
                    break
            
            if not group_id:
                logger.error(f"Не удалось найти ID группы {group_name}")
                return 0
            
            members_added = 0
            
            # Добавляем участников в группу используя новый метод
            for username in member_usernames:
                try:
                    success = self.mayan_client.add_user_to_group(group_id, username)
                    if success:
                        logger.info(f"Пользователь {username} добавлен в группу {group_name}")
                        members_added += 1
                    else:
                        logger.warning(f"Не удалось добавить пользователя {username} в группу {group_name}")
                        
                except Exception as e:
                    logger.warning(f"Ошибка добавления пользователя {username} в группу {group_name}: {e}")
            
            logger.info(f"В группу {group_name} добавлено {members_added} участников из {len(member_usernames)}")
            return members_added
            
        except Exception as e:
            logger.error(f"Ошибка добавления участников в группу {group_name}: {e}")
            return 0

    def _update_group_membership(self, group_name: str, member_usernames: List[str]) -> int:
        """Обновляет членство в группе Mayan EDMS"""
        try:
            logger.info(f"Обновляем членство в группе {group_name}")
            
            # Получаем ID группы
            groups = self.get_mayan_groups()
            group_id = None
            for group in groups:
                if group['name'] == group_name:
                    group_id = group['id']
                    break
            
            if not group_id:
                logger.error(f"Не удалось найти ID группы {group_name}")
                return 0
            
            # Получаем текущих участников группы
            current_members = self._get_group_members(group_id)
            logger.info(f"Текущие участники группы {group_name}: {current_members}")
            
            members_added = 0
            
            # Добавляем новых участников используя новый метод
            for username in member_usernames:
                if username not in current_members:
                    try:
                        success = self.mayan_client.add_user_to_group(group_id, username)
                        if success:
                            logger.info(f"Пользователь {username} добавлен в группу {group_name}")
                            members_added += 1
                        else:
                            logger.warning(f"Не удалось добавить пользователя {username} в группу {group_name}")
                            
                    except Exception as e:
                        logger.warning(f"Ошибка добавления пользователя {username} в группу {group_name}: {e}")
                else:
                    logger.debug(f"Пользователь {username} уже в группе {group_name}")
            
            # Удаляем участников, которых нет в LDAP (если включено)
            if self.remove_old_members:
                removed_count = self._remove_old_members(group_id, current_members, member_usernames)
                logger.info(f"Удалено {removed_count} старых участников из группы {group_name}")
            
            logger.info(f"В группу {group_name} добавлено {members_added} новых участников")
            return members_added
            
        except Exception as e:
            logger.error(f"Ошибка обновления членства в группе {group_name}: {e}")
            return 0

    def _remove_old_members(self, group_id: str, current_members: List[str], ldap_members: List[str]) -> int:
        """Удаляет участников, которых нет в LDAP группе"""
        try:
            members_to_remove = set(current_members) - set(ldap_members)
            removed_count = 0
            
            for username in members_to_remove:
                try:
                    # Используем новый метод MayanClient
                    success = self.mayan_client.remove_user_from_group(group_id, username)
                    if success:
                        logger.info(f"Пользователь {username} удален из группы")
                        removed_count += 1
                    else:
                        logger.warning(f"Не удалось удалить пользователя {username} из группы")
                        
                except Exception as e:
                    logger.warning(f"Ошибка удаления пользователя {username} из группы: {e}")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Ошибка удаления старых участников: {e}")
            return 0
    
    def create_group_in_mayan(self, ldap_group: UserGroup) -> bool:
        """Создает группу в Mayan EDMS"""
        try:
            logger.info(f"Создаем группу {ldap_group.cn} в Mayan EDMS")
            
            # Подготавливаем данные группы
            group_data = {
                'name': ldap_group.cn,
                'description': ldap_group.description or f"Группа {ldap_group.cn} из LDAP"
            }
            
            # Создаем группу используя новый метод MayanClient
            success = self.mayan_client.create_group(group_data)
            
            if success:
                logger.info(f"Группа {ldap_group.cn} успешно создана в Mayan EDMS")
                
                # Добавляем группу в отслеживаемые
                self.synced_groups.add(ldap_group.cn)
                
                # Добавляем участников группы
                if ldap_group.memberUid:
                    logger.info(f"Добавляем {len(ldap_group.memberUid)} участников в группу {ldap_group.cn}")
                    members_added = self._add_group_members(ldap_group.cn, ldap_group.memberUid)
                    logger.info(f"Добавлено {members_added} участников в группу {ldap_group.cn}")
                
                return True
            else:
                logger.error(f"Не удалось создать группу {ldap_group.cn} в Mayan EDMS")
                return False
                
        except Exception as e:
            logger.error(f"Исключение при создании группы {ldap_group.cn}: {e}")
            return False
    
    def sync_groups(self, ldap_server: Server, force_sync: bool = False) -> Dict[str, Any]:
        """Основной метод синхронизации групп с полным обновлением членства"""
        logger.info("Начинаем синхронизацию групп")
        
        sync_stats = {
            'total_ldap_groups': 0,
            'total_mayan_groups': 0,
            'new_groups_created': 0,
            'groups_updated': 0,
            'groups_skipped': 0,
            'groups_already_exist': 0,
            'members_added': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Получаем группы из LDAP
            ldap_groups = self.get_ldap_groups(ldap_server)
            sync_stats['total_ldap_groups'] = len(ldap_groups)
            
            # Получаем группы из Mayan EDMS
            mayan_groups = self.get_mayan_groups()
            sync_stats['total_mayan_groups'] = len(mayan_groups)
            
            # Создаем словарь существующих групп в Mayan для быстрого поиска
            existing_mayan_groups = {group['name']: group for group in mayan_groups}
            
            # Обрабатываем каждую группу из LDAP
            for ldap_group in ldap_groups:
                try:
                    logger.info(f"Обрабатываем группу: {ldap_group.cn}")
                    
                    # Проверяем, существует ли группа в Mayan EDMS
                    if ldap_group.cn in existing_mayan_groups:
                        logger.info(f"Группа {ldap_group.cn} уже существует в Mayan EDMS, обновляем членство")
                        
                        # Обновляем членство в существующей группе
                        members_added = self._update_group_membership(ldap_group.cn, ldap_group.memberUid)
                        sync_stats['members_added'] += members_added
                        sync_stats['groups_updated'] += 1
                        
                        # Добавляем группу в отслеживаемые
                        self.synced_groups.add(ldap_group.cn)
                        
                    else:
                        # Группа не существует, создаем её
                        logger.info(f"Создаем новую группу: {ldap_group.cn}")
                        
                        result = self.create_group_in_mayan(ldap_group)
                        if result:
                            sync_stats['new_groups_created'] += 1
                            logger.info(f"Группа {ldap_group.cn} успешно создана")
                            
                            # Участники уже добавлены в create_group_in_mayan
                            sync_stats['members_added'] += len(ldap_group.memberUid)
                        else:
                            # Проверяем, была ли это ошибка дублирования
                            if ldap_group.cn in self.synced_groups:
                                sync_stats['groups_already_exist'] += 1
                                logger.info(f"Группа {ldap_group.cn} уже существовала в Mayan EDMS")
                            else:
                                sync_stats['errors'] += 1
                                logger.error(f"Ошибка синхронизации группы {ldap_group.cn}")
                
                except Exception as e:
                    sync_stats['errors'] += 1
                    logger.error(f"Ошибка обработки группы {ldap_group.cn}: {e}")
            
            # Сохраняем состояние синхронизации
            self._save_sync_state()
            
            sync_stats['end_time'] = datetime.now().isoformat()
            sync_stats['success'] = sync_stats['errors'] == 0
            
            logger.info(f"Синхронизация групп завершена:")
            logger.info(f"   Всего групп в LDAP: {sync_stats['total_ldap_groups']}")
            logger.info(f"   Всего групп в Mayan: {sync_stats['total_mayan_groups']}")
            logger.info(f"   Новых групп создано: {sync_stats['new_groups_created']}")
            logger.info(f"   Групп обновлено: {sync_stats['groups_updated']}")
            logger.info(f"   Групп уже существовало: {sync_stats['groups_already_exist']}")
            logger.info(f"   Участников добавлено: {sync_stats['members_added']}")
            logger.info(f"   Ошибок: {sync_stats['errors']}")
            
            return sync_stats
            
        except Exception as e:
            logger.error(f"Критическая ошибка синхронизации групп: {e}")
            sync_stats['errors'] += 1
            sync_stats['success'] = False
            return sync_stats

class UserSyncManager:
    """Менеджер синхронизации пользователей между LDAP и Mayan EDMS"""
    
    def __init__(self):
        self.ldap_server = None
        self.mayan_client = None
        self.sync_state_file = Path("logs/user_sync_state.json")
        self.last_sync_time = None
        self.synced_users = set()
        self.group_sync_manager = None
        
        # Инициализация подключений
        self._init_ldap_connection()
        self._init_mayan_connection()
        self._load_sync_state()
        
        # Инициализация менеджера синхронизации групп
        self.group_sync_manager = LDAPGroupSyncManager(self.mayan_client)
    
    def _init_ldap_connection(self):
        """Инициализация подключения к LDAP"""
        try:
            if not config.ldap_server:
                raise ValueError("LDAP сервер не настроен")
            
            self.ldap_server = Server(config.ldap_server, get_info=ALL)
            logger.info(f"LDAP сервер инициализирован: {config.ldap_server}")
        except Exception as e:
            logger.error(f"Ошибка инициализации LDAP: {e}")
            raise
    
    def _init_mayan_connection(self):
        """Инициализация подключения к Mayan EDMS"""
        try:
            self.mayan_client = MayanClient.create_default()
            logger.info("Mayan EDMS клиент инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации Mayan EDMS: {e}")
            raise
    
    def _load_sync_state(self):
        """Загружает состояние синхронизации из файла"""
        try:
            if self.sync_state_file.exists():
                with open(self.sync_state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.last_sync_time = state.get('last_sync_time')
                    self.synced_users = set(state.get('synced_users', []))
                    logger.info(f"Состояние синхронизации загружено: {len(self.synced_users)} пользователей")
            else:
                logger.info("Файл состояния синхронизации не найден, начинаем с чистого листа")
        except Exception as e:
            logger.warning(f"Ошибка загрузки состояния синхронизации: {e}")
    
    def _save_sync_state(self):
        """Сохраняет состояние синхронизации в файл"""
        try:
            state = {
                'last_sync_time': datetime.now().isoformat(),
                'synced_users': list(self.synced_users)
            }
            
            # Создаем директорию logs если её нет
            self.sync_state_file.parent.mkdir(exist_ok=True)
            
            with open(self.sync_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Состояние синхронизации сохранено: {len(self.synced_users)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния синхронизации: {e}")
    
    def get_ldap_users(self) -> List[LDAPUser]:
        """Получает всех пользователей из LDAP"""
        users = []
        
        try:
            # Подключение к LDAP
            conn = Connection(
                self.ldap_server, 
                user=config.ldap_user, 
                password=config.ldap_password, 
                auto_bind=True
            )
            
            # Поиск всех пользователей
            search_filter = '(uid=*)'
            base_dn = 'dc=permgp7,dc=ru'
            
            conn.search(
                base_dn,
                search_filter,
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail', 'memberOf', 'userPassword']
            )
            
            logger.info(f"Найдено {len(conn.entries)} пользователей в LDAP")
            
            for entry in conn.entries:
                try:
                    # Получаем группы пользователя
                    groups = []
                    if hasattr(entry, 'memberOf') and entry.memberOf:
                        for group_dn in entry.memberOf:
                            group_name = str(group_dn).split(',')[0].split('=')[1]
                            groups.append(group_name)
                    
                    user = LDAPUser(
                        dn=str(entry.entry_dn),
                        uid=entry.uid.value,
                        cn=entry.cn.value,
                        givenName=entry.givenName.value,
                        sn=entry.sn.value,
                        mail=entry.mail.value if hasattr(entry, 'mail') else None,
                        memberOf=groups
                    )
                    users.append(user)
                    
                except Exception as e:
                    logger.warning(f"Ошибка обработки пользователя {entry}: {e}")
                    continue
            
            conn.unbind()
            logger.info(f"Получено {len(users)} пользователей из LDAP")
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей из LDAP: {e}")
        
        return users
    
    def get_mayan_users(self) -> List[Dict[str, Any]]:
        """Получает всех пользователей из Mayan EDMS"""
        try:
            # Используем новый метод MayanClient
            users = self.mayan_client.get_users()
            logger.info(f"Получено {len(users)} пользователей из Mayan EDMS")
            return users
        except Exception as e:
            logger.error(f"Ошибка получения пользователей из Mayan EDMS: {e}")
            return []
    
    def create_user_in_mayan(self, ldap_user: LDAPUser, default_password: str = "TempPassword123!") -> bool:
        """Создает пользователя в Mayan EDMS"""
        try:
            logger.info(f"Создаем пользователя {ldap_user.uid} в Mayan EDMS")
            
            # Подготавливаем данные пользователя
            user_data = {
                'username': ldap_user.uid,
                'first_name': ldap_user.givenName,
                'last_name': ldap_user.sn,
                'email': ldap_user.mail or f"{ldap_user.uid}@permgp7.ru",
                'password': default_password,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            }
            
            # Создаем пользователя используя новый метод MayanClient
            success = self.mayan_client.create_user(user_data)
            
            if success:
                logger.info(f"Пользователь {ldap_user.uid} успешно создан в Mayan EDMS")
                
                # Добавляем пользователя в отслеживаемые
                self.synced_users.add(ldap_user.uid)
                
                # Создаем API токен для пользователя
                try:
                    api_token = self.mayan_client.create_user_api_token(ldap_user.uid, default_password)
                    if api_token:
                        logger.info(f"API токен создан для пользователя {ldap_user.uid}")
                    else:
                        logger.warning(f"Не удалось создать API токен для пользователя {ldap_user.uid}")
                except Exception as e:
                    logger.warning(f"Ошибка создания API токена для {ldap_user.uid}: {e}")
                
                return True
            else:
                logger.error(f"Не удалось создать пользователя {ldap_user.uid} в Mayan EDMS")
                return False
                
        except Exception as e:
            logger.error(f"Исключение при создании пользователя {ldap_user.uid}: {e}")
            return False
    
    def sync_users(self, force_sync: bool = False) -> Dict[str, Any]:
        """Основной метод синхронизации пользователей"""
        logger.info("Начинаем синхронизацию пользователей")
        
        sync_stats = {
            'total_ldap_users': 0,
            'total_mayan_users': 0,
            'new_users_created': 0,
            'users_skipped': 0,
            'users_already_exist': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Получаем пользователей из LDAP
            ldap_users = self.get_ldap_users()
            sync_stats['total_ldap_users'] = len(ldap_users)
            
            # Получаем пользователей из Mayan EDMS
            mayan_users = self.get_mayan_users()
            sync_stats['total_mayan_users'] = len(mayan_users)
            
            # Создаем множество существующих пользователей в Mayan
            existing_mayan_users = {user['username'] for user in mayan_users}
            
            # Обрабатываем каждого пользователя из LDAP
            for ldap_user in ldap_users:
                try:
                    # Пропускаем если пользователь уже существует в Mayan
                    if ldap_user.uid in existing_mayan_users:
                        logger.debug(f"Пользователь {ldap_user.uid} уже существует в Mayan EDMS")
                        sync_stats['users_skipped'] += 1
                        continue
                    
                    # Пропускаем если пользователь уже был синхронизирован в этой сессии
                    if ldap_user.uid in self.synced_users and not force_sync:
                        logger.debug(f"Пользователь {ldap_user.uid} уже синхронизирован")
                        sync_stats['users_skipped'] += 1
                        continue
                    
                    # Создаем пользователя в Mayan EDMS
                    result = self.create_user_in_mayan(ldap_user)
                    if result:
                        sync_stats['new_users_created'] += 1
                        logger.info(f"Пользователь {ldap_user.uid} успешно синхронизирован")
                    else:
                        # Проверяем, была ли это ошибка дублирования
                        if ldap_user.uid in self.synced_users:
                            sync_stats['users_already_exist'] += 1
                            logger.info(f"Пользователь {ldap_user.uid} уже существовал в Mayan EDMS")
                        else:
                            sync_stats['errors'] += 1
                            logger.error(f"Ошибка синхронизации пользователя {ldap_user.uid}")
                
                except Exception as e:
                    sync_stats['errors'] += 1
                    logger.error(f"Ошибка обработки пользователя {ldap_user.uid}: {e}")
            
            # Сохраняем состояние синхронизации
            self._save_sync_state()
            
            sync_stats['end_time'] = datetime.now().isoformat()
            sync_stats['success'] = sync_stats['errors'] == 0
            
            logger.info(f"Синхронизация пользователей завершена:")
            logger.info(f"   Всего пользователей в LDAP: {sync_stats['total_ldap_users']}")
            logger.info(f"   Всего пользователей в Mayan: {sync_stats['total_mayan_users']}")
            logger.info(f"   Новых пользователей создано: {sync_stats['new_users_created']}")
            logger.info(f"   Пользователей уже существовало: {sync_stats['users_already_exist']}")
            logger.info(f"   Пользователей пропущено: {sync_stats['users_skipped']}")
            logger.info(f"   Ошибок: {sync_stats['errors']}")
            
            return sync_stats
            
        except Exception as e:
            logger.error(f"Критическая ошибка синхронизации пользователей: {e}")
            sync_stats['errors'] += 1
            sync_stats['success'] = False
            return sync_stats
    
    def sync_groups(self, force_sync: bool = False) -> Dict[str, Any]:
        """Синхронизация групп"""
        if not self.group_sync_manager:
            logger.error("Менеджер синхронизации групп не инициализирован")
            return {'success': False, 'errors': 1}
        
        return self.group_sync_manager.sync_groups(self.ldap_server, force_sync)
    
    def full_sync(self, force_sync: bool = False) -> Dict[str, Any]:
        """Полная синхронизация пользователей и групп"""
        logger.info("Начинаем полную синхронизацию пользователей и групп")
        
        full_stats = {
            'users': {},
            'groups': {},
            'overall_success': True,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Сначала синхронизируем пользователей
            logger.info("=== СИНХРОНИЗАЦИЯ ПОЛЬЗОВАТЕЛЕЙ ===")
            user_stats = self.sync_users(force_sync)
            full_stats['users'] = user_stats
            
            # Затем синхронизируем группы
            logger.info("=== СИНХРОНИЗАЦИЯ ГРУПП ===")
            group_stats = self.sync_groups(force_sync)
            full_stats['groups'] = group_stats
            
            # Определяем общий успех
            full_stats['overall_success'] = user_stats.get('success', False) and group_stats.get('success', False)
            full_stats['end_time'] = datetime.now().isoformat()
            
            logger.info("=== ИТОГИ ПОЛНОЙ СИНХРОНИЗАЦИИ ===")
            logger.info(f"Пользователи: создано {user_stats.get('new_users_created', 0)}, ошибок {user_stats.get('errors', 0)}")
            logger.info(f"Группы: создано {group_stats.get('new_groups_created', 0)}, обновлено {group_stats.get('groups_updated', 0)}, ошибок {group_stats.get('errors', 0)}")
            logger.info(f"Общий результат: {'УСПЕШНО' if full_stats['overall_success'] else 'С ОШИБКАМИ'}")
            
            return full_stats
            
        except Exception as e:
            logger.error(f"Критическая ошибка полной синхронизации: {e}")
            full_stats['overall_success'] = False
            return full_stats
    
    def cleanup_inactive_users(self, days_inactive: int = 90) -> Dict[str, Any]:
        """Удаляет неактивных пользователей из Mayan EDMS (опционально)"""
        logger.info(f"Проверяем неактивных пользователей (старше {days_inactive} дней)")
        
        cleanup_stats = {
            'checked_users': 0,
            'inactive_users': 0,
            'users_deactivated': 0,
            'errors': 0
        }
        
        try:
            mayan_users = self.get_mayan_users()
            cleanup_stats['checked_users'] = len(mayan_users)
            
            cutoff_date = datetime.now() - timedelta(days=days_inactive)
            
            for user in mayan_users:
                try:
                    # Проверяем дату последнего входа
                    last_login = user.get('last_login')
                    if last_login:
                        last_login_date = datetime.fromisoformat(last_login.replace('Z', '+00:00'))
                        if last_login_date < cutoff_date:
                            cleanup_stats['inactive_users'] += 1
                            logger.info(f"Неактивный пользователь: {user['username']} (последний вход: {last_login})")
                            
                            # Здесь можно добавить логику деактивации пользователя
                            # Пока только логируем
                            
                except Exception as e:
                    cleanup_stats['errors'] += 1
                    logger.error(f"Ошибка проверки пользователя {user.get('username', 'Unknown')}: {e}")
            
            logger.info(f"Проверка неактивных пользователей завершена:")
            logger.info(f"   Проверено пользователей: {cleanup_stats['checked_users']}")
            logger.info(f"   Неактивных пользователей: {cleanup_stats['inactive_users']}")
            logger.info(f"   Ошибок: {cleanup_stats['errors']}")
            
        except Exception as e:
            logger.error(f"Ошибка проверки неактивных пользователей: {e}")
            cleanup_stats['errors'] += 1
        
        return cleanup_stats

def main():
    """Основная функция скрипта"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Синхронизация пользователей и групп LDAP с Mayan EDMS')
    parser.add_argument('--force', action='store_true', help='Принудительная синхронизация всех пользователей и групп')
    parser.add_argument('--cleanup', action='store_true', help='Проверить и деактивировать неактивных пользователей')
    parser.add_argument('--days', type=int, default=90, help='Количество дней неактивности для cleanup (по умолчанию: 90)')
    parser.add_argument('--users-only', action='store_true', help='Синхронизировать только пользователей')
    parser.add_argument('--groups-only', action='store_true', help='Синхронизировать только группы')
    parser.add_argument('--remove-old-members', action='store_true', help='Удалять участников групп, которых нет в LDAP')
    
    args = parser.parse_args()
    
    try:
        # Создаем менеджер синхронизации
        sync_manager = UserSyncManager()
        
        # Передаем параметр удаления старых участников
        if hasattr(sync_manager.group_sync_manager, 'remove_old_members'):
            sync_manager.group_sync_manager.remove_old_members = args.remove_old_members
        
        # Определяем тип синхронизации
        if args.users_only:
            logger.info("Выполняем синхронизацию только пользователей")
            sync_result = sync_manager.sync_users(force_sync=args.force)
        elif args.groups_only:
            logger.info("Выполняем синхронизацию только групп")
            sync_result = sync_manager.sync_groups(force_sync=args.force)
        else:
            logger.info("Выполняем полную синхронизацию пользователей и групп")
            sync_result = sync_manager.full_sync(force_sync=args.force)
        
        # Выполняем cleanup если запрошено
        if args.cleanup:
            cleanup_result = sync_manager.cleanup_inactive_users(args.days)
            sync_result['cleanup'] = cleanup_result
        
        # Выводим итоговый результат
        if sync_result.get('success', sync_result.get('overall_success', False)):
            logger.info("Синхронизация завершена успешно!")
            sys.exit(0)
        else:
            logger.error("Синхронизация завершена с ошибками!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()