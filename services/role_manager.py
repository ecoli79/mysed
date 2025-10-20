import logging
from typing import List, Optional, Dict, Any
from services.mayan_connector import MayanClient
from models import Role, Permission, UserRole

logger = logging.getLogger(__name__)

class RoleManager:
    """Менеджер управления ролями и разрешениями"""
    
    def __init__(self):
        self.mayan_client = None
        
    def _get_mayan_client(self) -> MayanClient:
        """Получает клиент Mayan EDMS"""
        if not self.mayan_client:
            self.mayan_client = MayanClient.create_with_session_user()
        return self.mayan_client
    
    def get_all_roles(self) -> List[Dict[str, Any]]:
        """
        Получает все роли из Mayan EDMS
        """
        try:
            client = self._get_mayan_client()
            roles = client.get_roles(page=1, page_size=1000)
            logger.info(f"Получено {len(roles)} ролей")
            return roles
        except Exception as e:
            logger.error(f"Ошибка при получении ролей: {e}")
            return []
    
    def create_role(self, name: str, description: str = "") -> bool:
        """
        Создает новую роль в Mayan EDMS
        """
        try:
            client = self._get_mayan_client()
            
            role_data = {
                'label': name,
                'text': description
            }
            
            # Используем существующий метод создания роли в MayanClient
            # (нужно будет добавить этот метод в MayanClient)
            success = client.create_role(role_data)
            
            if success:
                logger.info(f"Роль {name} создана успешно")
            else:
                logger.error(f"Ошибка создания роли {name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при создании роли {name}: {e}")
            return False
    
    def add_user_to_role(self, role_name: str, username: str) -> bool:
        """
        Добавляет пользователя к роли
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем роль
            roles = client.get_roles()
            role_id = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена")
                return False
            
            # Получаем пользователя
            users = client.get_users()
            user_id = None
            for user in users:
                if user['username'] == username:
                    user_id = user['id']
                    break
            
            if not user_id:
                logger.error(f"Пользователь {username} не найден")
                return False
            
            # Добавляем пользователя к роли
            # (нужно будет добавить этот метод в MayanClient)
            success = client.add_user_to_role(role_id, user_id)
            
            if success:
                logger.info(f"Пользователь {username} добавлен к роли {role_name}")
            else:
                logger.error(f"Ошибка добавления пользователя {username} к роли {role_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя к роли: {e}")
            return False
    
    def get_role_users(self, role_name: str) -> List[Dict[str, Any]]:
        """
        Получает список пользователей в роли
        """
        try:
            client = self._get_mayan_client()
            
            # Получаем роль
            roles = client.get_roles()
            role_id = None
            for role in roles:
                if role['label'] == role_name:
                    role_id = role['id']
                    break
            
            if not role_id:
                logger.error(f"Роль {role_name} не найдена")
                return []
            
            # Получаем пользователей роли
            users = client.get_role_users(role_id)
            logger.info(f"В роли {role_name} найдено {len(users)} пользователей")
            
            return users
            
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей роли {role_name}: {e}")
            return []

# Глобальный экземпляр менеджера
role_manager = RoleManager()