"""
Менеджер синхронизации пользователей между Mayan EDMS и OpenLDAP
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from app_logging.logger import get_logger

logger = get_logger(__name__)

class UserSyncManager:
    """Менеджер синхронизации пользователей между Mayan EDMS и OpenLDAP"""
    
    def __init__(self, mayan_client, ldap_client):
        """
        Инициализация менеджера синхронизации
        
        Args:
            mayan_client: Клиент Mayan EDMS
            ldap_client: Клиент OpenLDAP
        """
        self.mayan_client = mayan_client
        self.ldap_client = ldap_client
        logger.info("UserSyncManager инициализирован")
    
    def sync_users_from_ldap_to_mayan(self) -> Dict[str, Any]:
        """
        Синхронизирует пользователей из OpenLDAP в Mayan EDMS
        
        Returns:
            Словарь с результатами синхронизации
        """
        logger.info("🔄 Начинаем синхронизацию пользователей из OpenLDAP в Mayan EDMS")
        
        results = {
            'created_users': [],
            'updated_users': [],
            'errors': [],
            'total_processed': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Получаем пользователей из OpenLDAP
            logger.info("📋 Получаем пользователей из OpenLDAP")
            ldap_users = self.ldap_client.get_all_users()
            logger.info(f"📋 Найдено {len(ldap_users)} пользователей в OpenLDAP")
            
            # Получаем существующих пользователей из Mayan EDMS
            logger.info("📋 Получаем существующих пользователей из Mayan EDMS")
            mayan_users = self.mayan_client.get_users()
            mayan_usernames = {user.get('username') for user in mayan_users}
            logger.info(f"📋 Найдено {len(mayan_users)} пользователей в Mayan EDMS")
            
            # Обрабатываем каждого пользователя из OpenLDAP
            for ldap_user in ldap_users:
                results['total_processed'] += 1
                username = ldap_user.get('uid')
                
                if not username:
                    error_msg = f"Пользователь без username: {ldap_user}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    continue
                
                logger.info(f"👤 Обрабатываем пользователя: {username}")
                
                try:
                    if username in mayan_usernames:
                        # Пользователь существует, обновляем
                        logger.info(f"🔄 Обновляем существующего пользователя: {username}")
                        self._update_user_in_mayan(username, ldap_user)
                        results['updated_users'].append(username)
                    else:
                        # Пользователь не существует, создаем
                        logger.info(f"➕ Создаем нового пользователя: {username}")
                        self._create_user_in_mayan(username, ldap_user)
                        results['created_users'].append(username)
                        
                except Exception as e:
                    error_msg = f"Ошибка обработки пользователя {username}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            results['end_time'] = datetime.now().isoformat()
            results['success'] = len(results['errors']) == 0
            
            logger.info(f"✅ Синхронизация завершена:")
            logger.info(f"   - Создано пользователей: {len(results['created_users'])}")
            logger.info(f"   - Обновлено пользователей: {len(results['updated_users'])}")
            logger.info(f"   - Ошибок: {len(results['errors'])}")
            
            return results
            
        except Exception as e:
            error_msg = f"Критическая ошибка синхронизации: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            results['end_time'] = datetime.now().isoformat()
            results['success'] = False
            return results
    
    def sync_groups_from_ldap_to_mayan(self) -> Dict[str, Any]:
        """
        Синхронизирует группы из OpenLDAP в Mayan EDMS
        
        Returns:
            Словарь с результатами синхронизации
        """
        logger.info("🔄 Начинаем синхронизацию групп из OpenLDAP в Mayan EDMS")
        
        results = {
            'created_groups': [],
            'updated_groups': [],
            'errors': [],
            'total_processed': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Получаем группы из OpenLDAP
            logger.info("📋 Получаем группы из OpenLDAP")
            ldap_groups = self.ldap_client.get_all_groups()
            logger.info(f"📋 Найдено {len(ldap_groups)} групп в OpenLDAP")
            
            # Получаем существующие группы из Mayan EDMS
            logger.info("📋 Получаем существующие группы из Mayan EDMS")
            mayan_groups = self.mayan_client.get_groups()
            mayan_group_names = {group.get('name') for group in mayan_groups}
            logger.info(f"📋 Найдено {len(mayan_groups)} групп в Mayan EDMS")
            
            # Обрабатываем каждую группу из OpenLDAP
            for ldap_group in ldap_groups:
                results['total_processed'] += 1
                group_name = ldap_group.get('cn')
                
                if not group_name:
                    error_msg = f"Группа без имени: {ldap_group}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    continue
                
                logger.info(f"👥 Обрабатываем группу: {group_name}")
                
                try:
                    if group_name in mayan_group_names:
                        # Группа существует, обновляем
                        logger.info(f"🔄 Обновляем существующую группу: {group_name}")
                        self._update_group_in_mayan(group_name, ldap_group)
                        results['updated_groups'].append(group_name)
                    else:
                        # Группа не существует, создаем
                        logger.info(f"➕ Создаем новую группу: {group_name}")
                        self._create_group_in_mayan(group_name, ldap_group)
                        results['created_groups'].append(group_name)
                        
                except Exception as e:
                    error_msg = f"Ошибка обработки группы {group_name}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            results['end_time'] = datetime.now().isoformat()
            results['success'] = len(results['errors']) == 0
            
            logger.info(f"✅ Синхронизация групп завершена:")
            logger.info(f"   - Создано групп: {len(results['created_groups'])}")
            logger.info(f"   - Обновлено групп: {len(results['updated_groups'])}")
            logger.info(f"   - Ошибок: {len(results['errors'])}")
            
            return results
            
        except Exception as e:
            error_msg = f"Критическая ошибка синхронизации групп: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            results['end_time'] = datetime.now().isoformat()
            results['success'] = False
            return results
    
    def sync_user_group_memberships(self) -> Dict[str, Any]:
        """
        Синхронизирует членство пользователей в группах
        
        Returns:
            Словарь с результатами синхронизации
        """
        logger.info("🔄 Начинаем синхронизацию членства в группах")
        
        results = {
            'added_memberships': [],
            'removed_memberships': [],
            'errors': [],
            'total_processed': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Получаем группы из Mayan EDMS
            mayan_groups = self.mayan_client.get_groups()
            
            for group in mayan_groups:
                group_id = group.get('id')
                group_name = group.get('name')
                
                if not group_id or not group_name:
                    continue
                
                logger.info(f"👥 Обрабатываем группу: {group_name} (ID: {group_id})")
                
                try:
                    # Получаем пользователей группы из Mayan EDMS
                    mayan_group_users = self.mayan_client.get_group_users(group_id)
                    mayan_usernames = {user.get('username') for user in mayan_group_users}
                    
                    # Получаем пользователей группы из OpenLDAP
                    ldap_group_users = self.ldap_client.get_group_members(group_name)
                    ldap_usernames = {user.get('uid') for user in ldap_group_users}
                    
                    # Добавляем пользователей, которые есть в LDAP, но нет в Mayan
                    for username in ldap_usernames:
                        if username not in mayan_usernames:
                            logger.info(f"➕ Добавляем пользователя {username} в группу {group_name}")
                            success = self.mayan_client.add_user_to_group(group_id, username)
                            if success:
                                results['added_memberships'].append(f"{username} -> {group_name}")
                            else:
                                results['errors'].append(f"Не удалось добавить {username} в {group_name}")
                    
                    # Удаляем пользователей, которых нет в LDAP, но есть в Mayan
                    for username in mayan_usernames:
                        if username not in ldap_usernames:
                            logger.info(f"➖ Удаляем пользователя {username} из группы {group_name}")
                            success = self.mayan_client.remove_user_from_group(group_id, username)
                            if success:
                                results['removed_memberships'].append(f"{username} <- {group_name}")
                            else:
                                results['errors'].append(f"Не удалось удалить {username} из {group_name}")
                    
                    results['total_processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Ошибка обработки группы {group_name}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            results['end_time'] = datetime.now().isoformat()
            results['success'] = len(results['errors']) == 0
            
            logger.info(f"✅ Синхронизация членства завершена:")
            logger.info(f"   - Добавлено членств: {len(results['added_memberships'])}")
            logger.info(f"   - Удалено членств: {len(results['removed_memberships'])}")
            logger.info(f"   - Ошибок: {len(results['errors'])}")
            
            return results
            
        except Exception as e:
            error_msg = f"Критическая ошибка синхронизации членства: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            results['end_time'] = datetime.now().isoformat()
            results['success'] = False
            return results
    
    def _create_user_in_mayan(self, username: str, ldap_user: Dict[str, Any]) -> bool:
        """
        Создает пользователя в Mayan EDMS
        
        Args:
            username: Имя пользователя
            ldap_user: Данные пользователя из LDAP
            
        Returns:
            True если пользователь создан успешно
        """
        try:
            # Подготавливаем данные для создания пользователя
            user_data = {
                'username': username,
                'first_name': ldap_user.get('givenName', ''),
                'last_name': ldap_user.get('sn', ''),
                'email': ldap_user.get('mail', ''),
                'is_active': True
            }
            
            logger.info(f"Создаем пользователя {username} с данными: {user_data}")
            
            # Создаем пользователя
            success = self.mayan_client.create_user(user_data)
            
            if success:
                logger.info(f"✅ Пользователь {username} успешно создан в Mayan EDMS")
            else:
                logger.error(f"❌ Не удалось создать пользователя {username} в Mayan EDMS")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {username}: {e}")
            return False
    
    def _update_user_in_mayan(self, username: str, ldap_user: Dict[str, Any]) -> bool:
        """
        Обновляет пользователя в Mayan EDMS
        
        Args:
            username: Имя пользователя
            ldap_user: Данные пользователя из LDAP
            
        Returns:
            True если пользователь обновлен успешно
        """
        try:
            # Здесь можно добавить логику обновления пользователя
            # Пока что просто логируем
            logger.info(f"🔄 Обновление пользователя {username} (пока не реализовано)")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления пользователя {username}: {e}")
            return False
    
    def _create_group_in_mayan(self, group_name: str, ldap_group: Dict[str, Any]) -> bool:
        """
        Создает группу в Mayan EDMS
        
        Args:
            group_name: Имя группы
            ldap_group: Данные группы из LDAP
            
        Returns:
            True если группа создана успешно
        """
        try:
            # Подготавливаем данные для создания группы
            group_data = {
                'name': group_name,
                'description': ldap_group.get('description', '')
            }
            
            logger.info(f"Создаем группу {group_name} с данными: {group_data}")
            
            # Создаем группу
            success = self.mayan_client.create_group(group_data)
            
            if success:
                logger.info(f"✅ Группа {group_name} успешно создана в Mayan EDMS")
            else:
                logger.error(f"❌ Не удалось создать группу {group_name} в Mayan EDMS")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка создания группы {group_name}: {e}")
            return False
    
    def _update_group_in_mayan(self, group_name: str, ldap_group: Dict[str, Any]) -> bool:
        """
        Обновляет группу в Mayan EDMS
        
        Args:
            group_name: Имя группы
            ldap_group: Данные группы из LDAP
            
        Returns:
            True если группа обновлена успешно
        """
        try:
            # Здесь можно добавить логику обновления группы
            # Пока что просто логируем
            logger.info(f"🔄 Обновление группы {group_name} (пока не реализовано)")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления группы {group_name}: {e}")
            return False
