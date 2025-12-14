from typing import Dict, Optional
from models import UserSession
from datetime import datetime, timedelta
import json
from app_logging.logger import get_logger

# Создаем logger для этого модуля
logger = get_logger(__name__)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}
        self.session_timeout = timedelta(hours=8)  # 8 часов бездействия
        logger.info("SessionManager инициализирован")
    
    def create_session(self, user: UserSession, token: str) -> None:
        """Создает новую сессию пользователя"""
        self.sessions[token] = user
        logger.info(f"Создана сессия для пользователя {user.username} с токеном {token[:8]}...")
    
    def get_session(self, token: str) -> Optional[UserSession]:
        """Получает сессию по токену"""
        if token not in self.sessions:
            logger.debug(f"Сессия с токеном {token[:8]}... не найдена")
            return None
        
        session = self.sessions[token]
        
        # Проверяем, не истекла ли сессия
        try:
            # Пробуем сначала ISO формат
            try:
                last_activity = datetime.fromisoformat(session.last_activity)
            except ValueError:
                # Если не ISO формат, пробуем парсить как отформатированную дату
                last_activity = datetime.strptime(session.last_activity, '%d.%m.%Y %H:%M:%S')
            
            if datetime.now() - last_activity > self.session_timeout:
                logger.info(f"Сессия пользователя {session.username} истекла, удаляем")
                self.remove_session(token)
                return None
        except (ValueError, TypeError) as e:
            # Если не можем распарсить дату, считаем сессию недействительной
            logger.warning(f"Не удалось распарсить дату последней активности для пользователя {session.username}: {e}")
            self.remove_session(token)
            return None
        
        # Обновляем время последней активности
        session.last_activity = datetime.now().isoformat()
        logger.debug(f"Обновлена активность для пользователя {session.username}")
        return session
    
    def remove_session(self, token: str) -> None:
        """Удаляет сессию и отзывает API токен Mayan EDMS"""
        if token in self.sessions:
            session = self.sessions[token]
            logger.info(f"Удаляем сессию пользователя {session.username}")
            
            # Отзываем API токен Mayan EDMS если есть
            if hasattr(session, 'mayan_api_token') and session.mayan_api_token:
                try:
                    from services.mayan_connector import MayanClient
                    from config.settings import config
                    
                    # Создаем клиент с системными учетными данными для отзыва токена
                    mayan_client = MayanClient(
                        base_url=config.mayan_url,
                        username=config.mayan_username,
                        password=config.mayan_password,
                        api_token=config.mayan_api_token,
                        verify_ssl=False
                    )
                    
                    # Отзываем токен
                    mayan_client.revoke_user_api_token(session.mayan_api_token)
                    logger.info(f"API токен Mayan EDMS отозван для пользователя {session.username}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отзыве API токена Mayan EDMS: {e}")
            else:
                logger.debug(f"API токен Mayan EDMS не найден для пользователя {session.username}")
            
            del self.sessions[token]
        else:
            logger.warning(f"Попытка удалить несуществующую сессию с токеном {token[:8]}...")
    
    def update_session_activity(self, token: str) -> bool:
        """Обновляет время последней активности"""
        session = self.get_session(token)
        if session:
            session.last_activity = datetime.now().isoformat()
            logger.debug(f"Обновлена активность для пользователя {session.username}")
            return True
        else:
            logger.warning(f"Не удалось обновить активность для токена {token[:8]}...")
            return False
    
    def get_user_by_token(self, token: str) -> Optional[UserSession]:
        """Получает пользователя по токену"""
        session = self.get_session(token)
        if session:
            logger.debug(f"Получен пользователь {session.username} по токену")
        else:
            logger.debug(f"Пользователь не найден по токену {token[:8]}...")
        return session
    
    def is_user_in_group(self, token: str, group: str) -> bool:
        """Проверяет, состоит ли пользователь в группе"""
        session = self.get_session(token)
        if not session:
            logger.warning(f"Сессия не найдена для проверки группы {group}")
            return False
        
        is_in_group = group in session.groups
        logger.debug(f"Пользователь {session.username} {'состоит' if is_in_group else 'не состоит'} в группе {group}")
        return is_in_group
    
    def cleanup_expired_sessions(self) -> None:
        """Очищает истекшие сессии"""
        current_time = datetime.now()
        expired_tokens = []
        
        logger.info("Начинаем очистку истекших сессий")
        
        for token, session in self.sessions.items():
            try:
                last_activity = datetime.fromisoformat(session.last_activity)
                if current_time - last_activity > self.session_timeout:
                    expired_tokens.append(token)
                    logger.info(f"Сессия пользователя {session.username} истекла")
            except (ValueError, TypeError) as e:
                # Если не можем распарсить дату, считаем сессию недействительной
                expired_tokens.append(token)
                logger.warning(f"Не удалось распарсить дату для пользователя {session.username}: {e}")
        
        for token in expired_tokens:
            del self.sessions[token]
        
        logger.info(f"Очищено {len(expired_tokens)} истекших сессий")

# Глобальный менеджер сессий
session_manager = SessionManager()