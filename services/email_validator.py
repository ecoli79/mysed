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
            # Формат в .env: значения разделяются запятыми
            # Пример: EMAIL_ALLOWED_SENDERS=*@*.permkrai.ru,user@example.com,@domain.com
            if config.email_allowed_senders:
                # Разбиваем строку по запятой и убираем пробелы
                allowed_senders = [s.strip() for s in config.email_allowed_senders.split(',') if s.strip()]
            else:
                allowed_senders = []
        
        self.allowed_senders = allowed_senders
        # Нормализуем адреса (приводим к нижнему регистру, но только для точных адресов, не для масок)
        # Маски должны оставаться как есть (с *), поэтому проверяем наличие *
        normalized = []
        for addr in self.allowed_senders:
            addr = addr.strip()
            # Если это не маска (не содержит *), приводим к нижнему регистру
            if '*' not in addr:
                addr = addr.lower()
            normalized.append(addr)
        self.allowed_senders = normalized
        
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
        
        # Сначала пытаемся извлечь адрес из угловых скобок <email@example.com>
        # Обрабатываем как полные скобки <email@example.com>, так и неполные <email@example.com
        bracket_match = re.search(r'<([^>@]+@[^>]+)', email_string)
        if bracket_match:
            email = bracket_match.group(1).strip()
            # Убираем возможные завершающие символы, которые не являются частью email
            email = email.rstrip('>').strip()
            # Проверяем, что это валидный email
            if self.EMAIL_PATTERN.match(email):
                return email.lower()
        
        # Если не нашли в скобках, ищем email в строке
        # Убираем угловые скобки и другие символы, которые могут быть в начале/конце
        cleaned = email_string.strip()
        # Убираем ведущие < если есть
        if cleaned.startswith('<'):
            cleaned = cleaned[1:]
        # Убираем завершающие > если есть
        if cleaned.endswith('>'):
            cleaned = cleaned[:-1]
        cleaned = cleaned.strip()
        
        # Ищем email в очищенной строке
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', cleaned)
        if email_match:
            email = email_match.group(0)
            # Проверяем, что это валидный email
            if self.EMAIL_PATTERN.match(email):
                return email.lower()
        
        return None
    
    def _match_pattern(self, email: str, pattern: str) -> bool:
        """
        Проверяет соответствие email паттерну с поддержкой масок
        
        Args:
            email: Email адрес для проверки
            pattern: Паттерн с масками (*@*.permkrai.ru, user@domain.com, @domain.com)
        
        Returns:
            True если соответствует, False иначе
        """
        pattern = pattern.strip().lower()
        email = email.lower()
        
        # Точное совпадение
        if pattern == email:
            return True
        
        # Если паттерн начинается с @ - проверяем домен
        if pattern.startswith('@'):
            email_domain = email.split('@')[1] if '@' in email else None
            pattern_domain = pattern[1:]  # Убираем @
            if email_domain == pattern_domain:
                return True
        
        # Если паттерн содержит маски (*)
        if '*' in pattern:
            # Преобразуем паттерн в регулярное выражение
            # * заменяем на .* (любые символы)
            # Экранируем специальные символы regex
            import re
            
            # Специальная обработка для паттернов типа *@*.domain.com
            # Если паттерн *@*.domain.com, также проверяем *@domain.com (без поддомена)
            if pattern.startswith('*@*.'):
                base_domain = pattern[4:]  # Убираем '*@*.'
                # Проверяем основной паттерн
                regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
                regex_pattern = f'^{regex_pattern}$'
                
                try:
                    if re.match(regex_pattern, email):
                        return True
                except re.error:
                    logger.warning(f"Некорректный паттерн regex: {regex_pattern}")
                
                # Также проверяем вариант без поддомена: *@domain.com
                alt_pattern = f'*@{base_domain}'
                alt_regex = alt_pattern.replace('.', r'\.').replace('*', '.*')
                alt_regex = f'^{alt_regex}$'
                
                try:
                    if re.match(alt_regex, email):
                        return True
                except re.error:
                    pass
            
            # Обычная обработка для других паттернов
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            regex_pattern = f'^{regex_pattern}$'
            
            try:
                if re.match(regex_pattern, email):
                    return True
            except re.error:
                logger.warning(f"Некорректный паттерн regex: {regex_pattern}")
        
        return False
    
    def is_allowed(self, email_address: str) -> bool:
        """
        Проверяет, разрешен ли отправитель
        
        Поддерживает:
        - Точные адреса: user@domain.com
        - Домены: @domain.com или domain.com
        - Маски: *@*.permkrai.ru, user@*.domain.com
        
        Args:
            email_address: Адрес отправителя
        
        Returns:
            True если отправитель разрешен, False иначе
        """
        # Если whitelist пуст, блокируем всех (безопаснее по умолчанию)
        if not self.allowed_senders:
            logger.warning("Whitelist пуст! Все отправители будут заблокированы. Укажите EMAIL_ALLOWED_SENDERS в .env")
            return False
        
        # Извлекаем чистый email
        clean_email = self.extract_email_address(email_address)
        if not clean_email:
            logger.warning(f"Не удалось извлечь email из '{email_address}'")
            return False
        
        # Проверяем каждый паттерн в whitelist
        for pattern in self.allowed_senders:
            if self._match_pattern(clean_email, pattern):
                logger.debug(f"Отправитель {clean_email} соответствует паттерну {pattern}")
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