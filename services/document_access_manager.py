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

# Глобальный экземпляр менеджера
document_access_manager = DocumentAccessManager()