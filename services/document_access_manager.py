# services/document_access_manager.py

import logging
from typing import List, Optional, Dict, Any
from services.mayan_connector import MayanClient, MayanDocument
from models import UserSession

logger = logging.getLogger(__name__)

class DocumentAccessManager:
    """Менеджер управления доступом к документам"""
    
    def __init__(self):
        self.mayan_client = None
        
    def _get_mayan_client(self) -> MayanClient:
        """Получает клиент Mayan EDMS"""
        if not self.mayan_client:
            self.mayan_client = MayanClient.create_with_session_user()
        return self.mayan_client
    
    def get_user_accessible_documents(self, user: UserSession) -> List[MayanDocument]:
        """
        Получает список документов, доступных пользователю
        Пока возвращаем все документы
        """
        try:
            client = self._get_mayan_client()
            all_documents = client.get_documents(page=1, page_size=1000)
            logger.info(f"Пользователь {user.username} видит {len(all_documents)} документов")
            return all_documents
            
        except Exception as e:
            logger.error(f"Ошибка при получении доступных документов: {e}")
            return []
    
    def grant_document_access_to_user(self, document_id: str, document_label: str,
                                 username: str, permission: str) -> bool:
        """
        Предоставляет доступ к документу конкретному пользователю
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем список пользователей
            users = client.get_users()
            logger.info(f"Получено {len(users)} пользователей из Mayan EDMS")
            
            if not users:
                logger.error("В Mayan EDMS не найдено пользователей")
                return False
            
            # Находим пользователя по имени
            user_id = None
            user_info = None
            for user in users:
                logger.info(f"Проверяем пользователя: {user.get('username')}")
                if user['username'] == username:
                    user_id = user['id']
                    user_info = user
                    break
            
            if not user_id:
                logger.error(f"Пользователь {username} не найден в Mayan EDMS")
                logger.error(f"Доступные пользователи: {[u['username'] for u in users]}")
                return False
            
            logger.info(f"Найден пользователь {username} с ID: {user_id}")
            logger.info(f"Информация о пользователе: {user_info}")
            
            # Создаем ACL для документа с пользователем через правильный endpoint
            acl = client.create_acl_for_object('documents', 'document', document_id, user_id=user_id)
            if not acl:
                logger.error("Не удалось создать ACL")
                return False
            
            logger.info(f"ACL создан: {acl}")
            
            # Получаем ID разрешения
            permission_id = self._get_permission_id(client, permission)
            if not permission_id:
                logger.error(f"Не удалось найти разрешение: {permission}")
                return False
            
            logger.info(f"Найдено разрешение {permission} с ID: {permission_id}")
            
            # Добавляем разрешение к ACL
            acl_id = acl.get('id') or acl.get('pk')
            if not acl_id:
                logger.error("Не удалось получить ID созданного ACL")
                return False
            
            success = client.add_permissions_to_object_acl('documents', 'document', document_id, acl_id, [permission_id])
            
            if success:
                logger.info(f"Доступ к документу {document_id} предоставлен пользователю {username}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при предоставлении доступа пользователю: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def grant_document_access_to_role_by_pks(self, document_id: str, document_label: str,
                                        role_name: str, permission_pks: List[str]) -> bool:
        """
        Предоставляет доступ к документу роли по списку pk разрешений
        """
        try:
            logger.info(f"=== НАЧАЛО ПРЕДОСТАВЛЕНИЯ ДОСТУПА ===")
            logger.info(f"Документ: {document_label} (ID: {document_id})")
            logger.info(f"Роль: {role_name}")
            logger.info(f"Разрешения PK: {permission_pks}")
            
            client = self._get_mayan_client()
            
            # Получаем список ролей
            roles = client.get_roles()
            logger.info(f"Получено {len(roles)} ролей из Mayan EDMS")
            
            # Находим роль по имени
            role_id = None
            role_info = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    role_info = role
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена в Mayan EDMS")
                logger.error(f"Доступные роли: {[r['label'] for r in roles]}")
                return False
            
            logger.info(f"Найдена роль {role_name} с ID: {role_id}")
            
            # Создаем ACL для документа с ролью
            logger.info(f"Создаем ACL для документа {document_id} с ролью {role_id}")
            acl = client.create_acl_for_object('documents', 'document', document_id, role_id=role_id)
            if not acl:
                logger.error("Не удалось создать ACL")
                return False
            
            logger.info(f"ACL создан: {acl}")
            
            # Получаем ID разрешений (могут быть строковыми)
            permission_ids = []
            for permission_pk in permission_pks:
                logger.info(f"Получаем ID для разрешения: {permission_pk}")
                permission_id = client.get_permission_id_by_pk(permission_pk)
                if not permission_id:
                    logger.error(f"Не удалось получить ID для разрешения: {permission_pk}")
                    return False
                permission_ids.append(permission_id)
                logger.info(f"Найдено разрешение {permission_pk} с ID: {permission_id}")
            
            # Добавляем разрешения к ACL
            acl_id = acl.get('id') or acl.get('pk')
            if not acl_id:
                logger.error("Не удалось получить ID созданного ACL")
                return False
            
            logger.info(f"Добавляем разрешения {permission_ids} к ACL {acl_id}")
            success = client.add_permissions_to_object_acl('documents', 'document', document_id, acl_id, permission_ids)
            
            if success:
                logger.info(f'Доступ к документу {document_id} предоставлен роли {role_name} с разрешениями: {permission_pks}')
            else:
                logger.error(f'Не удалось добавить разрешения к ACL')
            
            return success
        
        except Exception as e:
            logger.error(f'Ошибка при предоставлении доступа роли: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def grant_document_access_to_role_by_pk(self, document_id: str, document_label: str,
                                      role_name: str, permission_pk: str) -> bool:
        """
        Предоставляет доступ к документу роли по pk разрешения
        """
        try:
            logger.info(f"=== НАЧАЛО ПРЕДОСТАВЛЕНИЯ ДОСТУПА ===")
            logger.info(f"Документ: {document_label} (ID: {document_id})")
            logger.info(f"Роль: {role_name}")
            logger.info(f"Разрешение PK: {permission_pk}")
            
            client = self._get_mayan_client()
            
            # Получаем список ролей
            roles = client.get_roles()
            logger.info(f"Получено {len(roles)} ролей из Mayan EDMS")
            
            # Находим роль по имени
            role_id = None
            role_info = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    role_info = role
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена в Mayan EDMS")
                logger.error(f"Доступные роли: {[r['label'] for r in roles]}")
                return False
            
            logger.info(f"Найдена роль {role_name} с ID: {role_id}")
            
            # Создаем ACL для документа с ролью
            logger.info(f"Создаем ACL для документа {document_id} с ролью {role_id}")
            acl = client.create_acl_for_object('documents', 'document', document_id, role_id=role_id)
            if not acl:
                logger.error("Не удалось создать ACL")
                return False
            
            logger.info(f"ACL создан: {acl}")
            
            # Получаем ID разрешения (теперь может быть строковым)
            logger.info(f"Получаем ID для разрешения: {permission_pk}")
            permission_id = client.get_permission_id_by_pk(permission_pk)
            if not permission_id:
                logger.error(f"Не удалось получить ID для разрешения: {permission_pk}")
                return False
            
            logger.info(f"Найдено разрешение {permission_pk} с ID: {permission_id}")
            
            # Добавляем разрешение к ACL
            acl_id = acl.get('id') or acl.get('pk')
            if not acl_id:
                logger.error("Не удалось получить ID созданного ACL")
                return False
            
            logger.info(f"Добавляем разрешение {permission_id} к ACL {acl_id}")
            success = client.add_permissions_to_object_acl('documents', 'document', document_id, acl_id, [permission_id])
            
            if success:
                logger.info(f'Доступ к документу {document_id} предоставлен роли {role_name}')
            else:
                logger.error(f'Не удалось добавить разрешение к ACL')
            
            return success
            
        except Exception as e:
            logger.error(f'Ошибка при предоставлении доступа роли: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def grant_document_access_to_role(self, document_id: str, document_label: str,
                                    role_name: str, permission: str) -> bool:
        """
        Предоставляет доступ к документу роли
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем список ролей
            roles = client.get_roles()
            logger.info(f"Получено {len(roles)} ролей из Mayan EDMS")
            
            # Находим роль по имени
            role_id = None
            role_info = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    role_info = role
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена в Mayan EDMS")
                logger.error(f"Доступные роли: {[r['label'] for r in roles]}")
                return False
            
            logger.info(f"Найдена роль {role_name} с ID: {role_id}")
            
            # Создаем ACL для документа с ролью
            acl = client.create_acl_for_object('documents', 'document', document_id, role_id=role_id)
            if not acl:
                logger.error("Не удалось создать ACL")
                return False
            
            logger.info(f"ACL создан: {acl}")
            
            # Получаем ID разрешения
            permission_id = self._get_permission_id(client, permission)
            if not permission_id:
                logger.error(f"Не удалось найти разрешение: {permission}")
                return False
            
            logger.info(f"Найдено разрешение {permission} с ID: {permission_id}")
            
            # Добавляем разрешение к ACL
            acl_id = acl.get('id') or acl.get('pk')
            if not acl_id:
                logger.error("Не удалось получить ID созданного ACL")
                return False
            
            success = client.add_permissions_to_object_acl('documents', 'document', document_id, acl_id, [permission_id])
            
            if success:
                logger.info(f"Доступ к документу {document_id} предоставлен роли {role_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при предоставлении доступа роли: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def revoke_document_access_from_user(self, document_id: str, username: str) -> bool:
        """
        Отзывает доступ к документу у пользователя
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем ACL для документа
            acls = client.get_object_acls_list('documents', 'document', document_id)
            
            # Находим пользователя
            users = client.get_users()
            user_id = None
            for user in users:
                if user['username'] == username:
                    user_id = user['id']
                    break
            
            if not user_id:
                logger.error(f"Пользователь {username} не найден")
                return False
            
            # Находим ACL для этого пользователя
            for acl in acls:
                if acl.get('user') == user_id:
                    acl_id = acl.get('id') or acl.get('pk')
                    if acl_id:
                        # Удаляем ACL
                        success = client.delete_object_acl('documents', 'document', document_id, acl_id)
                        if success:
                            logger.info(f"Доступ к документу {document_id} отозван у пользователя {username}")
                        return success
                
                # Проверяем также детали ACL
                acl_details = client.get_object_acl_details('documents', 'document', document_id, str(acl.get('id', '')))
                if acl_details and acl_details.get('user') == user_id:
                    acl_id = acl_details.get('id')
                    if acl_id:
                        success = client.delete_object_acl('documents', 'document', document_id, acl_id)
                        if success:
                            logger.info(f"Доступ к документу {document_id} отозван у пользователя {username}")
                        return success
            
            logger.warning(f"ACL для пользователя {username} и документа {document_id} не найден")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при отзыве доступа у пользователя: {e}")
            return False

    def revoke_document_access_from_role(self, document_id: str, role_name: str) -> bool:
        """
        Отзывает доступ к документу у роли
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем ACL для документа
            acls = client.get_object_acls_list('documents', 'document', document_id)
            
            # Находим роль
            roles = client.get_roles()
            role_id = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена")
                return False
            
            # Находим ACL для этой роли
            for acl in acls:
                if acl.get('role') == role_id:
                    acl_id = acl.get('id') or acl.get('pk')
                    if acl_id:
                        # Удаляем ACL
                        success = client.delete_object_acl('documents', 'document', document_id, acl_id)
                        if success:
                            logger.info(f"Доступ к документу {document_id} отозван у роли {role_name}")
                        return success
                
                # Проверяем также детали ACL
                acl_details = client.get_object_acl_details('documents', 'document', document_id, str(acl.get('id', '')))
                if acl_details and acl_details.get('role') == role_id:
                    acl_id = acl_details.get('id')
                    if acl_id:
                        success = client.delete_object_acl('documents', 'document', document_id, acl_id)
                        if success:
                            logger.info(f"Доступ к документу {document_id} отозван у роли {role_name}")
                        return success
            
            logger.warning(f"ACL для роли {role_name} и документа {document_id} не найден")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при отзыве доступа у роли: {e}")
            return False
    
    def get_document_access_info(self, document_id: str) -> Dict[str, Any]:
        """
        Получает информацию о доступе к документу
        """
        try:
            client = self._get_mayan_client()
            
            access_info = {
                'document_id': document_id,
                'acls': [],
                'users_with_access': [],
                'roles_with_access': [],
                'error': None,
                'access_method': 'object_acls'
            }
            
            # Получаем список ACL для документа
            try:
                acls_list = client.get_object_acls_list('documents', 'document', document_id)
                logger.info(f"Получено {len(acls_list)} ACL для документа {document_id}")
                
                if acls_list:
                    # Получаем роли и пользователей для контекста
                    try:
                        roles = {role['id']: role for role in client.get_roles()}
                        users = {user['id']: user for user in client.get_users()}
                    except Exception as e:
                        logger.warning(f"Не удалось получить роли или пользователей: {e}")
                        roles = {}
                        users = {}
                    
                    # Для каждого ACL получаем детальную информацию
                    for acl_summary in acls_list:
                        acl_id = acl_summary.get('id') or acl_summary.get('pk')
                        if not acl_id:
                            logger.warning(f"ACL без ID: {acl_summary}")
                            continue
                        
                        # Получаем детали ACL
                        acl_details = client.get_object_acl_details('documents', 'document', document_id, str(acl_id))
                        
                        if acl_details:
                            acl_info = {
                                'acl_id': acl_id,
                                'details': acl_details,
                                'summary': acl_summary,
                                'permissions': [],
                                'role': None,
                                'user': None
                            }
                            
                            # ИСПРАВЛЕНИЕ: Правильно обрабатываем роль из ACL
                            if acl_details.get('role'):
                                # Роль может быть словарем или ID
                                role_data = acl_details['role']
                                if isinstance(role_data, dict):
                                    # Если роль - это словарь, используем его напрямую
                                    acl_info['role'] = role_data
                                    access_info['roles_with_access'].append(role_data)
                                elif isinstance(role_data, (int, str)):
                                    # Если роль - это ID, ищем в списке ролей
                                    role_info = roles.get(int(role_data))
                                    if role_info:
                                        acl_info['role'] = role_info
                                        access_info['roles_with_access'].append(role_info)
                            
                            # ИСПРАВЛЕНИЕ: Правильно обрабатываем пользователя из ACL
                            if acl_details.get('user'):
                                # Пользователь может быть словарем или ID
                                user_data = acl_details['user']
                                if isinstance(user_data, dict):
                                    # Если пользователь - это словарь, используем его напрямую
                                    acl_info['user'] = user_data
                                    access_info['users_with_access'].append(user_data)
                                elif isinstance(user_data, (int, str)):
                                    # Если пользователь - это ID, ищем в списке пользователей
                                    user_info = users.get(int(user_data))
                                    if user_info:
                                        acl_info['user'] = user_info
                                        access_info['users_with_access'].append(user_info)
                            
                            # Получаем разрешения ACL (если есть в деталях)
                            if 'permissions' in acl_details:
                                acl_info['permissions'] = acl_details['permissions']
                            
                            access_info['acls'].append(acl_info)
                        else:
                            logger.warning(f"Не удалось получить детали ACL {acl_id}")
                            # Добавляем хотя бы краткую информацию
                            acl_info = {
                                'acl_id': acl_id,
                                'summary': acl_summary,
                                'error': 'Не удалось получить детали'
                            }
                            access_info['acls'].append(acl_info)
                else:
                    logger.info(f"Для документа {document_id} не настроены ACL")
                        
            except Exception as e:
                logger.warning(f"Не удалось получить ACL для документа {document_id}: {e}")
                access_info['error'] = f"Не удалось получить информацию о доступе: {str(e)}"
                access_info['access_method'] = 'error'
            
            return access_info
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о доступе: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'document_id': document_id, 
                'error': f"Ошибка при получении информации о доступе: {str(e)}"
            }
    
    def get_available_roles(self) -> List[Dict[str, Any]]:
        """
        Получает список всех доступных ролей с сервера
        """
        try:
            client = self._get_mayan_client()
            
            logger.info("=== ПОЛУЧАЕМ РОЛИ ===")
            roles = client.get_roles()
            logger.info(f"Получено {len(roles)} ролей из Mayan EDMS")
            
            if not roles:
                logger.warning("Роли не найдены через основной endpoint. Пробуем альтернативные методы.")
                
                # Пробуем альтернативные endpoints
                alternative_endpoints = [
                    'authentication/roles/',
                    'permissions/roles/',
                    'access_control_lists/roles/',
                    'groups/',
                    'users/groups/'
                ]
                
                for alt_endpoint in alternative_endpoints:
                    try:
                        logger.info(f"Пробуем альтернативный endpoint: {alt_endpoint}")
                        response = client._make_request('GET', alt_endpoint)
                        
                        if response.status_code == 200:
                            data = response.json()
                            logger.info(f"Получены данные через {alt_endpoint}: {data}")
                            
                            # Пробуем извлечь роли из ответа
                            if 'results' in data:
                                roles = data['results']
                            elif isinstance(data, list):
                                roles = data
                            
                            if roles:
                                logger.info(f"Найдено {len(roles)} ролей через {alt_endpoint}")
                                break
                        else:
                            logger.warning(f"Endpoint {alt_endpoint} вернул статус {response.status_code}")
                            
                    except Exception as e:
                        logger.warning(f"Ошибка при обращении к {alt_endpoint}: {e}")
                        continue
            
            # Выводим все роли для отладки
            logger.info("=== ВСЕ РОЛИ ===")
            for i, role in enumerate(roles):
                logger.info(f"{i+1}. ID: {role.get('id', 'N/A')} | Label: {role.get('label', 'N/A')} | Name: {role.get('name', 'N/A')}")
            
            return roles
        
        except Exception as e:
            logger.error(f"Ошибка при получении ролей: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def get_available_permissions_for_documents(self) -> List[Dict[str, Any]]:
        """
        Получает список всех разрешений для документов из Mayan EDMS
        """
        try:
            client = self._get_mayan_client()
            permissions = client.get_permissions()
            
            logger.info(f"Получено {len(permissions)} разрешений")
            
            # Фильтруем только разрешения для документов
            document_permissions = []
            for permission in permissions:
                if permission:
                    namespace = permission.get('namespace', '')
                    label = permission.get('label', '')
                    pk = permission.get('pk', '')
                    
                    # Ищем разрешения, связанные с документами
                    if ('document' in namespace.lower() or 
                        'document' in label.lower() or 
                        'document' in pk.lower()):
                        document_permissions.append({
                            'pk': pk,
                            'label': label,
                            'namespace': namespace
                        })
            
            logger.info(f"Найдено {len(document_permissions)} разрешений для документов")
            
            # Сортируем по названию
            document_permissions.sort(key=lambda x: x['label'])
            
            return document_permissions
            
        except Exception as e:
            logger.error(f"Ошибка при получении разрешений для документов: {e}")
            return []

    def get_available_permissions(self) -> List[Dict[str, Any]]:
        """
        Получает список всех доступных разрешений с сервера
        """
        try:
            client = self._get_mayan_client()
            permissions = client.get_permissions()
            
            logger.info(f"=== ДОСТУПНЫЕ РАЗРЕШЕНИЯ ===")
            logger.info(f"Всего разрешений: {len(permissions)}")
            
            # Просто выводим все разрешения подряд
            logger.info("=== ВСЕ РАЗРЕШЕНИЯ ===")
            for i, permission in enumerate(permissions):
                if permission:
                    # ИСПРАВЛЕНИЕ: Проверяем реальную структуру данных
                    logger.info(f"Структура разрешения {i+1}: {permission}")
                    perm_id = permission.get('id', permission.get('pk', 'N/A'))
                    perm_name = permission.get('name', permission.get('codename', 'N/A'))
                    perm_label = permission.get('label', permission.get('title', 'N/A'))
                    logger.info(f"{i+1:3d}. ID: {perm_id} | Name: {perm_name} | Label: {perm_label}")
                else:
                    logger.warning(f"{i+1:3d}. None permission found!")
            
            # Ищем разрешения, связанные с документами
            logger.info("=== РАЗРЕШЕНИЯ ДЛЯ ДОКУМЕНТОВ ===")
            document_permissions = []
            for permission in permissions:
                if permission:
                    # Ищем по label, так как name пустое
                    label = permission.get('label', '')
                    if 'document' in label.lower():
                        document_permissions.append(permission)
                        perm_id = permission.get('id', permission.get('pk', 'N/A'))
                        perm_name = permission.get('name', permission.get('codename', 'N/A'))
                        logger.info(f"DOC: ID: {perm_id} | Name: {perm_name} | Label: {label}")
            
            logger.info(f"Найдено {len(document_permissions)} разрешений для документов")
            
            return permissions
            
        except Exception as e:
            logger.error(f"Ошибка при получении разрешений: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _get_permission_id(self, client: MayanClient, permission_name: str) -> Optional[int]:
        """
        Получает ID разрешения по названию
        """
        try:
            logger.info(f"=== ПОИСК РАЗРЕШЕНИЯ ===")
            logger.info(f"Ищем разрешение: {permission_name}")
            
            permissions = client.get_permissions()
            logger.info(f"Получено {len(permissions)} разрешений")
            
            # Маппинг разрешений - используем человекочитаемые названия
            permission_map = {
                'read': 'View documents',
                'write': 'Edit documents',
                'download': 'Download document files',
                'create': 'Create documents',
                'delete': 'Delete documents'
            }
            
            mayan_permission = permission_map.get(permission_name)
            if not mayan_permission:
                logger.error(f'Неизвестное разрешение: {permission_name}')
                logger.error(f'Доступные разрешения: {list(permission_map.keys())}')
                return None
            
            logger.info(f"Ищем разрешение по label: {mayan_permission}")
            
            # Ищем разрешение по label
            for permission in permissions:
                if permission:
                    label = permission.get('label', '')
                    if label == mayan_permission:
                        pk = permission.get('pk')
                        if pk:
                            logger.info(f'Найдено разрешение {mayan_permission} с pk: {pk}')
                            
                            # Получаем числовой ID через детальную информацию
                            numeric_id = client.get_permission_id_by_pk(pk)
                            if numeric_id:
                                logger.info(f'Получен числовой ID: {numeric_id}')
                                return numeric_id
                            else:
                                logger.warning(f"Не удалось получить числовой ID для {pk}")
                                # Попробуем использовать pk как есть (может сработать)
                                return pk
            
            logger.error(f'Разрешение {mayan_permission} не найдено')
            
            # Показываем все разрешения для отладки
            logger.error('=== ВСЕ РАЗРЕШЕНИЯ ДЛЯ ОТЛАДКИ ===')
            for permission in permissions[:10]:  # Показываем первые 10
                if permission:
                    perm_id = permission.get('id', 'N/A')
                    perm_pk = permission.get('pk', 'N/A')
                    perm_label = permission.get('label', 'N/A')
                    perm_url = permission.get('url', 'N/A')
                    logger.error(f"ID: {perm_id}, PK: {perm_pk}, Label: {perm_label}, URL: {perm_url}")
            
            return None
            
        except Exception as e:
            logger.error(f'Ошибка при поиске разрешения: {e}')
            import traceback
            logger.error(f'Traceback: {traceback.format_exc()}')
            return None


    def test_acl_reading(self, document_id: str) -> Dict[str, Any]:
        """
        Тестовый метод для проверки чтения ACL
        """
        try:
            client = self._get_mayan_client()
            
            logger.info(f"=== ТЕСТ ЧТЕНИЯ ACL ДЛЯ ДОКУМЕНТА {document_id} ===")
            
            # Шаг 1: Получаем список ACL
            logger.info('Шаг 1: Получаем список ACL')
            acls_list = client.get_object_acls_list('documents', 'document', document_id)
            logger.info(f"Получено ACL: {len(acls_list)}")
            
            result = {
                'document_id': document_id,
                'acls_count': len(acls_list),
                'acls_list': acls_list,
                'acl_details': []
            }
            
            # Шаг 2: Для каждого ACL получаем детали
            for i, acl_summary in enumerate(acls_list):
                logger.info(f"Шаг 2.{i+1}: Получаем детали ACL {acl_summary.get('id', 'unknown')}")
                
                acl_id = acl_summary.get('id') or acl_summary.get('pk')
                if acl_id:
                    acl_details = client.get_object_acl_details('documents', 'document', document_id, str(acl_id))
                    result['acl_details'].append({
                        'acl_id': acl_id,
                        'summary': acl_summary,
                        'details': acl_details
                    })
                else:
                    logger.warning(f"ACL без ID: {acl_summary}")
            
            logger.info(f"=== ТЕСТ ЗАВЕРШЕН ===")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка в тесте чтения ACL: {e}")
            return {
                'document_id': document_id,
                'error': str(e)
            }

    def get_user_roles(self, username: str) -> List[str]:
        """
        Получает список названий ролей пользователя
        Использует обратный подход: проверяет все роли и ищет пользователя по username
        
        Args:
            username: Имя пользователя
            
        Returns:
            Список названий ролей (label)
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем все роли (без пагинации, если возможно)
            logger.info(f'Получаем все роли для поиска пользователя {username}')
            all_roles = client.get_roles(page=1, page_size=1000)
            logger.info(f'Получено {len(all_roles)} ролей')
            
            # Находим роли, в которых состоит пользователь
            user_roles = []
            for role in all_roles:
                role_id = role.get('id')
                role_label = role.get('label')
                
                if not role_id or not role_label:
                    continue
                
                try:
                    role_users = client.get_role_users(role_id)
                    logger.debug(f'Роль {role_label} (ID: {role_id}) содержит {len(role_users)} пользователей')
                    
                    # Проверяем, есть ли пользователь в этой роли по username
                    for role_user in role_users:
                        role_username = role_user.get('username')
                        if role_username == username:
                            if role_label not in user_roles:
                                user_roles.append(role_label)
                                logger.info(f'Найден пользователь {username} в роли {role_label}')
                            break
                            
                except Exception as e:
                    logger.warning(f'Ошибка при получении пользователей роли {role_label} (ID: {role_id}): {e}')
                    continue
            
            logger.info(f'Пользователь {username} состоит в ролях: {user_roles}')
            return user_roles
            
        except Exception as e:
            logger.error(f'Ошибка при получении ролей пользователя {username}: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def grant_document_access_for_signing(self, document_id: str, document_label: str, 
                                         signer_usernames: List[str]) -> bool:
        """
        Предоставляет доступ к документу ролям подписантов для подписания
        Использует связь через группы: пользователь -> группа -> роль
        
        Args:
            document_id: ID документа
            document_label: Название документа
            signer_usernames: Список имен пользователей-подписантов
            
        Returns:
            True если доступ предоставлен хотя бы одной роли
        """
        try:
            from services.access_types import AccessType, AccessTypeManager
            from services.mayan_connector import MayanClient
            
            # Используем системный клиент для получения групп (административные права)
            # и пользовательский клиент для предоставления доступа
            system_client = MayanClient.create_default()
            user_client = self._get_mayan_client()
            
            logger.info(f'=== НАЧАЛО ПОИСКА РОЛЕЙ ЧЕРЕЗ ГРУППЫ ===')
            logger.info(f'Подписанты: {signer_usernames}')
            
            # Шаг 1: Получаем все группы через системный клиент
            logger.info('Шаг 1: Получаем все группы (используем системный клиент)')
            all_groups = system_client.get_groups()
            logger.info(f'Получено {len(all_groups)} групп')
            
            if not all_groups:
                logger.error('Не найдено ни одной группы в Mayan EDMS')
                return False
            
            logger.info(f'Найдены группы: {[g.get("name") for g in all_groups]}')
            
            # Шаг 2: Строим маппинг username -> set(group_ids)
            # Для каждой группы получаем пользователей и запоминаем, в каких группах они состоят
            logger.info('Шаг 2: Получаем пользователей групп и строим маппинг')
            username_to_groups = {}  # username -> set(group_ids)
            signer_usernames_set = set(signer_usernames)
            
            for group in all_groups:
                group_id = group.get('id')
                group_name = group.get('name')
                
                if not group_id:
                    continue
                
                try:
                    # Получаем пользователей группы через системный клиент
                    group_users = system_client.get_group_users(str(group_id))
                    logger.debug(f'Группа {group_name} (ID: {group_id}) содержит {len(group_users)} пользователей')
                    
                    # Для каждого пользователя группы запоминаем эту группу
                    for user in group_users:
                        username = user.get('username')
                        if username:
                            if username not in username_to_groups:
                                username_to_groups[username] = set()
                            username_to_groups[username].add(group_id)
                            logger.debug(f'Пользователь {username} состоит в группе {group_name} (ID: {group_id})')
                    
                except Exception as e:
                    logger.warning(f'Ошибка при получении пользователей группы {group_name} (ID: {group_id}): {e}')
                    continue
            
            # Шаг 3: Собираем группы подписантов
            logger.info('Шаг 3: Собираем группы подписантов')
            signer_groups = set()
            for username in signer_usernames:
                if username in username_to_groups:
                    groups = username_to_groups[username]
                    signer_groups.update(groups)
                    logger.info(f'Подписант {username} состоит в группах: {groups}')
                else:
                    logger.warning(f'Подписант {username} не найден ни в одной группе')
            
            if not signer_groups:
                logger.warning(f'Подписанты не состоят ни в одной группе')
                return False
            
            logger.info(f'Всего уникальных групп подписантов: {len(signer_groups)}')
            
            # Шаг 4: Получаем все роли и для каждой роли получаем группы
            # Используем системный клиент для получения ролей
            logger.info('Шаг 4: Получаем роли и их группы (используем системный клиент)')
            all_roles = system_client.get_roles(page=1, page_size=1000)
            logger.info(f'Получено {len(all_roles)} ролей')
            
            if not all_roles:
                logger.error('Не найдено ни одной роли в Mayan EDMS')
                return False
            
            # Шаг 5: Собираем роли, в которых есть группы подписантов
            unique_roles = set()
            
            for role in all_roles:
                role_id = role.get('id')
                role_label = role.get('label')
                
                if not role_id or not role_label:
                    continue
                
                try:
                    # Получаем группы роли через системный клиент
                    role_groups = system_client.get_role_groups(role_id)
                    logger.debug(f'Роль {role_label} (ID: {role_id}) содержит {len(role_groups)} групп')
                    
                    # Проверяем, есть ли пересечение между группами роли и группами подписантов
                    role_group_ids = {g.get('id') for g in role_groups if g.get('id')}
                    
                    # Находим пересечение
                    common_groups = signer_groups.intersection(role_group_ids)
                    
                    if common_groups:
                        unique_roles.add(role_label)
                        logger.info(f'✓ Найдена роль {role_label} для подписантов (общие группы: {common_groups})')
                        
                except Exception as e:
                    logger.warning(f'Ошибка при получении групп роли {role_label} (ID: {role_id}): {e}')
                    continue
            
            logger.info(f'=== РЕЗУЛЬТАТ ПОИСКА ===')
            logger.info(f'Найдено ролей: {unique_roles if unique_roles else "НЕТ"}')
            
            if not unique_roles:
                logger.warning(f'Не найдено ролей для подписантов: {signer_usernames}')
                return False
            
            logger.info(f'Предоставляем доступ к документу {document_id} ролям: {unique_roles}')
            
            # Шаг 6: Получаем разрешения для типа доступа SUBSCRIBE_DOCUMENT
            # Используем пользовательский клиент для получения разрешений и предоставления доступа
            permission_names = AccessTypeManager.get_access_type_permissions(AccessType.SUBSCRIBE_DOCUMENT)
            
            # Получаем все разрешения через пользовательский клиент
            all_permissions = user_client.get_permissions()
            
            # Составляем маппинг название -> pk
            permission_map = {}
            for perm in all_permissions:
                if perm:
                    label = perm.get('label', '')
                    pk = perm.get('pk')
                    if label in permission_names and pk:
                        permission_map[label] = pk
            
            # Получаем список pk разрешений
            permission_pks = list(permission_map.values())
            
            if not permission_pks:
                logger.error(f'Не найдено разрешений для типа доступа SUBSCRIBE_DOCUMENT')
                logger.error(f'Ожидаемые разрешения: {permission_names}')
                return False
            
            logger.info(f'Найдено {len(permission_pks)} разрешений для подписания')
            
            # Шаг 7: Предоставляем доступ каждой уникальной роли через пользовательский клиент
            success_count = 0
            for role_name in unique_roles:
                try:
                    result = self.grant_document_access_to_role_by_pks(
                        document_id=document_id,
                        document_label=document_label,
                        role_name=role_name,
                        permission_pks=permission_pks
                    )
                    if result:
                        success_count += 1
                        logger.info(f'✓ Доступ к документу {document_id} предоставлен роли {role_name}')
                    else:
                        logger.error(f'✗ Не удалось предоставить доступ роли {role_name}')
                except Exception as e:
                    logger.error(f'Ошибка при предоставлении доступа роли {role_name}: {e}')
                    import traceback
                    logger.error(f'Traceback: {traceback.format_exc()}')
            
            logger.info(f'=== ИТОГ ===')
            logger.info(f'Доступ предоставлен {success_count} из {len(unique_roles)} ролей')
            return success_count > 0
            
        except Exception as e:
            logger.error(f'Ошибка при предоставлении доступа для подписания: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def grant_document_access_to_roles(self, document_id: str, document_label: str, 
                                      role_names: List[str]) -> bool:
        """
        Предоставляет доступ к документу указанным ролям для подписания
        
        Args:
            document_id: ID документа
            document_label: Название документа
            role_names: Список названий ролей для предоставления доступа
            
        Returns:
            True если доступ предоставлен хотя бы одной роли
        """
        try:
            from services.access_types import AccessType, AccessTypeManager
            
            if not role_names:
                logger.warning('Список ролей пуст, доступ не предоставляется')
                return False
            
            logger.info(f'=== ПРЕДОСТАВЛЕНИЕ ДОСТУПА К ДОКУМЕНТУ РОЛЯМ ===')
            logger.info(f'Документ: {document_id} ({document_label})')
            logger.info(f'Роли: {role_names}')
            
            client = self._get_mayan_client()
            
            # Получаем разрешения для типа доступа SUBSCRIBE_DOCUMENT
            permission_names = AccessTypeManager.get_access_type_permissions(AccessType.SUBSCRIBE_DOCUMENT)
            
            # Получаем все разрешения
            all_permissions = client.get_permissions()
            
            # Составляем маппинг название -> pk
            permission_map = {}
            for perm in all_permissions:
                if perm:
                    label = perm.get('label', '')
                    pk = perm.get('pk')
                    if label in permission_names and pk:
                        permission_map[label] = pk
            
            # Получаем список pk разрешений
            permission_pks = list(permission_map.values())
            
            if not permission_pks:
                logger.error(f'Не найдено разрешений для типа доступа SUBSCRIBE_DOCUMENT')
                logger.error(f'Ожидаемые разрешения: {permission_names}')
                return False
            
            logger.info(f'Найдено {len(permission_pks)} разрешений для подписания')
            
            # Предоставляем доступ каждой роли
            success_count = 0
            for role_name in role_names:
                try:
                    result = self.grant_document_access_to_role_by_pks(
                        document_id=document_id,
                        document_label=document_label,
                        role_name=role_name,
                        permission_pks=permission_pks
                    )
                    if result:
                        success_count += 1
                        logger.info(f'✓ Доступ к документу {document_id} предоставлен роли {role_name}')
                    else:
                        logger.error(f'✗ Не удалось предоставить доступ роли {role_name}')
                except Exception as e:
                    logger.error(f'Ошибка при предоставлении доступа роли {role_name}: {e}')
                    import traceback
                    logger.error(f'Traceback: {traceback.format_exc()}')
            
            logger.info(f'=== ИТОГ ===')
            logger.info(f'Доступ предоставлен {success_count} из {len(role_names)} ролей')
            return success_count > 0
            
        except Exception as e:
            logger.error(f'Ошибка при предоставлении доступа ролям: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

# Глобальный экземпляр менеджера
document_access_manager = DocumentAccessManager()