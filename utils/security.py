import re
from typing import Optional
from app_logging.logger import get_logger

logger = get_logger(__name__)

def validate_username(username: str) -> bool:
    """Валидирует имя пользователя на безопасность"""
    if not username or not isinstance(username, str):
        return False
    
    # Проверяем длину
    if len(username) < 3 or len(username) > 50:
        return False
    
    # Разрешаем только безопасные символы
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        return False
    
    # Запрещаем опасные паттерны
    dangerous_patterns = [
        r'\.\.',  # Path traversal
        r'[<>"\']',  # HTML/JS injection
        r'[;&|`$]',  # Command injection
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, username):
            logger.warning(f"Обнаружен опасный паттерн в имени пользователя: {username}")
            return False
    
    return True

def sanitize_input(value: str, max_length: int = 1000) -> str:
    """Очищает пользовательский ввод"""
    if not isinstance(value, str):
        return str(value)
    
    # Обрезаем до максимальной длины
    value = value[:max_length]
    
    # Удаляем потенциально опасные символы
    value = re.sub(r'[<>"\']', '', value)
    
    return value.strip()

