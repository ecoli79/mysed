# services/email_validator.py
import re
from typing import List, Optional
import logging
from config.settings import config

logger = logging.getLogger(__name__)


class EmailValidator:
    """Валидатор адресов электронной почты"""
    
    # Регулярное выражение для проверки email
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    def __init__(self, allowed_senders: Optional[List[str]] = None):
        """
        Инициализация валидатора
        
        Args:
            allowed_senders: Список разрешенных адресов отправителей (whitelist)
                           Если None, берется из config.email_allowed_senders
        """
        if allowed_senders is None:
            # Берем из конфигурации
            if config.email_allowed_senders:
                allowed_senders = [s.strip() for s in config.email_allowed_senders.split(',')]
            else:
                allowed_senders = []
        
        self.allowed_senders = allowed_senders
        # Нормализуем адреса (приводим к нижнему регистру)
        self.allowed_senders = [addr.lower().strip() for addr in self.allowed_senders]
        
        logger.info(f"Инициализирован EmailValidator с {len(self.allowed_senders)} разрешенными отправителями")
    
    @classmethod
    def create_default(cls) -> 'EmailValidator':
        """
        Создает валидатор с настройками из конфигурации (.env)
        
        Returns:
            Настроенный экземпляр EmailValidator
        """
        return cls()
    
    def is_valid_email(self, email_address: str) -> bool:
        """
        Проверяет валидность email адреса
        
        Args:
            email_address: Адрес электронной почты
        
        Returns:
            True если адрес валиден, False иначе
        """
        if not email_address:
            return False
        
        # Извлекаем email из строки вида "Имя <email@example.com>"
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_address)
        if email_match:
            email_address = email_match.group(0)
        
        return bool(self.EMAIL_PATTERN.match(email_address))
    
    def extract_email_address(self, email_string: str) -> Optional[str]:
        """
        Извлекает чистый email адрес из строки
        
        Args:
            email_string: Строка с email (может содержать имя: "Имя <email@example.com>")
        
        Returns:
            Чистый email адрес или None
        """
        if not email_string:
            return None
        
        # Ищем email в строке
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_string)
        if email_match:
            return email_match.group(0).lower()
        
        return None
    
    def is_allowed(self, email_address: str) -> bool:
        """
        Проверяет, разрешен ли отправитель
        
        Args:
            email_address: Адрес отправителя
        
        Returns:
            True если отправитель разрешен, False иначе
        """
        # Если whitelist пуст, разрешаем всех
        if not self.allowed_senders:
            logger.debug("Whitelist пуст, разрешаем всех отправителей")
            return True
        
        # Извлекаем чистый email
        clean_email = self.extract_email_address(email_address)
        if not clean_email:
            logger.warning(f"Не удалось извлечь email из '{email_address}'")
            return False
        
        # Проверяем точное совпадение
        if clean_email in self.allowed_senders:
            logger.debug(f"Отправитель {clean_email} найден в whitelist")
            return True
        
        # Проверяем домен (если в whitelist указан домен)
        email_domain = clean_email.split('@')[1] if '@' in clean_email else None
        if email_domain:
            for allowed in self.allowed_senders:
                # Если в whitelist указан домен (начинается с @)
                if allowed.startswith('@') and email_domain == allowed[1:]:
                    logger.debug(f"Домен {email_domain} найден в whitelist")
                    return True
                # Если в whitelist указан домен без @
                if '@' not in allowed and email_domain == allowed:
                    logger.debug(f"Домен {email_domain} найден в whitelist")
                    return True
        
        logger.warning(f"Отправитель {clean_email} не найден в whitelist")
        return False
    
    def add_allowed_sender(self, email_address: str) -> bool:
        """
        Добавляет адрес в whitelist
        
        Args:
            email_address: Адрес для добавления
        
        Returns:
            True если успешно добавлен, False иначе
        """
        clean_email = self.extract_email_address(email_address)
        if not clean_email:
            return False
        
        if clean_email not in self.allowed_senders:
            self.allowed_senders.append(clean_email)
            logger.info(f"Добавлен разрешенный отправитель: {clean_email}")
            return True
        
        return False
    
    def remove_allowed_sender(self, email_address: str) -> bool:
        """
        Удаляет адрес из whitelist
        
        Args:
            email_address: Адрес для удаления
        
        Returns:
            True если успешно удален, False иначе
        """
        clean_email = self.extract_email_address(email_address)
        if not clean_email:
            return False
        
        if clean_email in self.allowed_senders:
            self.allowed_senders.remove(clean_email)
            logger.info(f"Удален разрешенный отправитель: {clean_email}")
            return True
        
        return False