from contextlib import contextmanager
from nicegui import ui
from auth.middleware import get_current_user
from config.settings import config
from auth.session_manager import session_manager
from auth.token_storage import token_storage, clear_last_token
from menu import menu
from pages.mayan_documents import _current_user

def logout():
    try:
        clientIp = ui.context.client.request.client.host
    except:
        clientIp = 'unknown'

    token = token_storage.get_token(clientIp)
    if token:
        session_manager.remove_session(token)
        token_storage.remove_token(clientIp)
    clear_last_token()
    
    # Сбрасываем кэшированного пользователя в mayan_documents
    try:
        global _current_user
        _current_user = None
    except:
        pass
    
    ui.navigate.to('/login')

def create_user_info():
    user = get_current_user()
    if user:
        with ui.row().classes('items-center gap-4'):
            with ui.column().classes('items-end gap-1'):
                ui.label(f'{user.first_name} {user.last_name}').classes('text-white')
                with ui.row().classes('items-center gap-1'):
                    ui.icon('settings', size='xs').classes('text-white')
                    ui.link('Профиль', '/profile').classes('text-white text-xs no-underline hover:underline')
            ui.button('Выйти', on_click=logout).classes('text-white')

@contextmanager
def frame(navigation_title: str):
    ui.colors(primary='#6E93D6', secondary='#53B689', accent='#111B1E', positive='#53B689')
    ui.page_title(config.app_name)

    ui.add_head_html('''
        <!-- КриптоПро ЭЦП Browser Plug-in -->
        <script type="text/javascript">
            // Увеличиваем таймаут загрузки плагина до 60 секунд
            // Это даст время пользователю нажать "Разрешить" в диалоге расширения
            window.cadesplugin_load_timeout = 60000;
        </script>
        <script type="text/javascript" src="/static/js/cadesplugin_api.js"></script>
        <script type="text/javascript" src="/static/js/Code.js"></script>
        <script type="text/javascript" src="/static/js/async_code.js"></script>
        <script type="text/javascript" src="/static/js/cryptopro-integration.js"></script>

        <script type="text/javascript">
            document.addEventListener('DOMContentLoaded', function() {
                setTimeout(function() {
                    if (typeof CryptoProIntegration !== 'undefined') {
                        window.cryptoProIntegration = new CryptoProIntegration();
                        console.log('CryptoPro интеграция инициализирована');
                    } else {
                        console.warn('CryptoProIntegration класс не найден');
                    }
                }, 1000);
                
                // Обработчик сообщений от расширения КриптоПро
                window.addEventListener('message', function(event) {
                    if (event.data && typeof event.data === 'string') {
                        if (event.data.includes('cadesplugin_loaded')) {
                            console.log('✅ Расширение КриптоПро загружено и готово к работе');
                        } else if (event.data.includes('cadesplugin_load_error')) {
                            console.error('❌ Ошибка загрузки расширения КриптоПро');
                        }
                    }
                });
            });
        </script>
    ''')

    user = get_current_user()

    # Если пользователь авторизован — показываем левый дровер с меню
    if user:
        drawer = ui.left_drawer(value=True, fixed=True).props('show-if-above').classes(
            'bg-primary text-white w-60 px-3 py-3'
        )
        with drawer:
            ui.label(config.app_name).classes('font-bold text-white text-base mb-3')
            menu(user)
    else:
        drawer = None  # для единообразия ниже

    # Шапка: кнопка-стрелка только для авторизованных
    with ui.header().classes('items-center'):
        if user and drawer is not None:
            toggle_btn = ui.button(icon='chevron_right', on_click=drawer.toggle).props(
                'flat round dense color=white'
            )
            def set_icon(name: str):
                toggle_btn.props(f'icon={name}')
                toggle_btn.update()
            toggle_btn.on('mouseenter', lambda e: set_icon('chevron_left'))
            toggle_btn.on('mouseleave', lambda e: set_icon('chevron_right'))

        ui.label(navigation_title).classes('text-white')
        ui.space()
        if user:
            from components.theme import create_user_info as _create_user_info
            _create_user_info()

    # Контент
    with ui.column().classes('w-full items-center p-4'):
        yield

