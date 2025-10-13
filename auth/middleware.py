from nicegui import ui
from typing import Optional
from auth.session_manager import session_manager
from auth.token_storage import token_storage, get_last_token
from models import UserSession
import functools

def require_auth(func):
    """Декоратор для проверки аутентификации"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Получаем IP-адрес клиента
        try:
            client_ip = ui.context.client.request.client.host
        except:
            client_ip = "unknown"
        
        # Получаем токен из хранилища
        token = token_storage.get_token(client_ip)
        
        # Если токен не найден по IP, пробуем последний токен
        if not token:
            token = get_last_token()
        
        if not token:
            # Перенаправляем на страницу входа
            ui.navigate.to('/login')
            return
        
        # Проверяем сессию
        user = session_manager.get_user_by_token(token)
        if not user:
            ui.navigate.to('/login')
            return
        
        # Вызываем оригинальную функцию без изменений
        return func(*args, **kwargs)
    
    return wrapper

def require_group(group: str):
    """Декоратор для проверки принадлежности к группе"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                client_ip = ui.context.client.request.client.host
            except:
                client_ip = "unknown"
            
            token = token_storage.get_token(client_ip)
            
            if not token:
                ui.navigate.to('/login')
                return
            
            user = session_manager.get_user_by_token(token)
            if not user:
                ui.navigate.to('/login')
                return
            
            if not session_manager.is_user_in_group(token, group):
                ui.notify('Недостаточно прав доступа', type='error')
                ui.navigate.to('/')
                return
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

def get_current_user() -> Optional[UserSession]:
    """Получает текущего пользователя"""
    try:
        client_ip = ui.context.client.request.client.host
        token = token_storage.get_token(client_ip)
        if token:
            return session_manager.get_user_by_token(token)
    except:
        pass
    return None