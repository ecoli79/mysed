from nicegui import ui
from auth.ldap_auth import LDAPAuthenticator
from auth.session_manager import session_manager
from auth.token_storage import token_storage, set_last_token
from models import LoginRequest
import asyncio
from auth.middleware import get_current_user
from app_logging.logger import get_logger

logger = get_logger(__name__)

def create_login_page():
    """Создает страницу входа в систему"""
    
    with ui.column().classes('w-full max-w-md mx-auto mt-8'):
        ui.html('<h1 class="text-2xl font-bold text-center mb-6">Вход в систему</h1>')
        
        with ui.card().classes('w-full'):
            username_input = ui.input('Имя пользователя', placeholder='Введите имя пользователя').classes('w-full mb-4')
            password_input = ui.input('Пароль', password=True, placeholder='Введите пароль').classes('w-full mb-4')
            
            login_button = ui.button('Войти', color='primary').classes('w-full')
            
            status_label = ui.label('').classes('text-center mt-4')
    
    async def handle_login():
        """Обработчик входа"""
        username = username_input.value.strip()
        password = password_input.value.strip()
        
        if not username or not password:
            status_label.text = 'Пожалуйста, заполните все поля'
            status_label.classes('text-red-500')
            return
        
        status_label.text = 'Проверка учетных данных...'
        status_label.classes('text-blue-500')
        
        # Аутентификация через LDAP
        authenticator = LDAPAuthenticator()
        auth_response = await authenticator.authenticate_user(username, password)
        
        if auth_response.success:
            # Создаем сессию
            session_manager.create_session(auth_response.user, auth_response.token)
            
            # Сохраняем токен в хранилище
            try:
                client_ip = ui.context.client.request.client.host
            except:
                client_ip = "unknown"
            
            token_storage.set_token(client_ip, auth_response.token)
            set_last_token(auth_response.token)
            
            status_label.text = 'Успешный вход!'
            status_label.classes('text-green-500')
            
            # Перенаправляем на главную страницу
            ui.timer(1.0, lambda: ui.navigate.to('/'), once=True)
        else:
            status_label.text = auth_response.message
            status_label.classes('text-red-500')
    
    login_button.on_click(handle_login)
    
    # Обработка нажатия Enter
    username_input.on('keydown.enter', handle_login)
    password_input.on('keydown.enter', handle_login)

def create_logout_button():
    """Создает кнопку выхода"""
    def logout():
        # Получаем текущего пользователя перед выходом для очистки кеша
        try:
            from pages.mayan_documents import clear_metadata_cache, get_state
            from auth.middleware import get_current_user
            
            current_user = get_current_user()
            if current_user:
                # Очищаем кеш метаданных для текущего пользователя
                clear_metadata_cache(current_user.username)
            
            # Также очищаем состояние страницы документов
            state = get_state()
            state.reset_all()
        except Exception as e:
            logger.debug(f'Ошибка при очистке кеша при выходе: {e}')
        
        # Удаляем токен из хранилища
        client_id = ui.context.client.id
        token_storage.remove_token(client_id)
        ui.navigate.to('/login')
    
    return ui.button('Выйти', on_click=logout, color='red')