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
            
            # Создаем ACL для документа с пользователем
            acl = client.create_acl_with_user('documents.document', document_id, user_id)
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
            success = client.add_permissions_to_acl(acl['id'], [permission_id])
            
            if success:
                logger.info(f"Доступ к документу {document_id} предоставлен пользователю {username}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при предоставлении доступа пользователю: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _get_permission_id(self, client: MayanClient, permission_name: str) -> Optional[int]:
        """
        Получает ID разрешения по названию
        """
        try:
            permissions = client.get_permissions()
            logger.info(f"Получено {len(permissions)} разрешений")
            
            # Маппинг разрешений
            permission_map = {
                'read': 'documents.view_document',
                'write': 'documents.change_document',
                'download': 'documents.download_document'
            }
            
            mayan_permission = permission_map.get(permission_name)
            if not mayan_permission:
                logger.error(f"Неизвестное разрешение: {permission_name}")
                return None
            
            logger.info(f"Ищем разрешение: {mayan_permission}")
            
            # Ищем разрешение
            for permission in permissions:
                logger.info(f"Проверяем разрешение: {permission.get('name')}")
                if permission['name'] == mayan_permission:
                    logger.info(f"Найдено разрешение {mayan_permission} с ID: {permission['id']}")
                    return permission['id']
            
            logger.error(f"Разрешение {mayan_permission} не найдено")
            logger.error(f"Доступные разрешения: {[p['name'] for p in permissions]}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске разрешения: {e}")
            return None

# Глобальный экземпляр менеджера
document_access_manager = DocumentAccessManager()