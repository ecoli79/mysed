from contextlib import contextmanager
from nicegui import ui
from auth.middleware import get_current_user
from auth.session_manager import session_manager
from auth.token_storage import token_storage, clear_last_token
from config.settings import config

def logout():
    """Функция выхода из системы"""
    try:
        client_ip = ui.context.client.request.client.host
    except:
        client_ip = "unknown"
    
    # Получаем токен
    token = token_storage.get_token(client_ip)
    
    # Удаляем сессию и токен
    if token:
        session_manager.remove_session(token)
        token_storage.remove_token(client_ip)
    
    # Очищаем последний токен
    clear_last_token()
    
    # Перенаправляем на страницу входа
    ui.navigate.to('/login')

def create_user_info():
    """Создает информацию о пользователе и кнопку выхода"""
    user = get_current_user()
    if user:
        with ui.row().classes('items-center gap-4'):
            ui.label(f'{user.first_name} {user.last_name}').classes('text-white')
            ui.button('Выйти', on_click=logout).classes('text-white')

@contextmanager
def frame(navigation_title: str):
    """Custom page frame to share the same styling and behavior across all pages"""
    ui.colors(primary='#6E93D6', secondary='#53B689', accent='#111B1E', positive='#53B689')
    
    # Проверяем авторизацию
    user = get_current_user()
    
    with ui.header():
        ui.label(config.app_name).classes('font-bold')
        ui.space()
        ui.label(navigation_title)
        ui.space()
        
        # Показываем меню и информацию о пользователе только если авторизован
        if user:
            with ui.row():
                from menu import menu
                menu()
            ui.space()
            create_user_info()
    
    # Изменяем контейнер для поддержки полной ширины
    with ui.column().classes('w-full items-center'):
        yield