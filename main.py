import asyncio
import api_router
import class_example
import function_example
from pages import home_page, deploy_work, task_completion_page, document_review_page, login_page, my_processes_page, mayan_documents, document_signing_page
from auth.middleware import require_auth, get_current_user
import theme
import os

from nicegui import app, ui

from app_logging.logger import setup_logging, get_logger
from config.settings import config

import logging
logging.basicConfig(level=logging.DEBUG)

# Настраиваем логирование при старте приложения
logger = get_logger(__name__)

# Настройка статических файлов
app.add_static_files('/static', os.path.join(os.path.dirname(__file__), 'static'))

# Страница входа (без авторизации)
@ui.page('/login')
def login_page_handler():
    with theme.frame(''):
        login_page.create_login_page()

# Главная страница с проверкой аутентификации
@ui.page('/')
@require_auth
def home_page_handler() -> None:
    with theme.frame('Мои задачи'):
        ui.timer(0.1, lambda: home_page.content(), once=True)

@ui.page('/my_processes')        
@require_auth
def my_processes_page_handler() -> None:
    with theme.frame('Запущенные мной процессы'):
        my_processes_page.content()

# Страница управления шаблонами процессов с авторизацией
@ui.page('/process_templates')
@require_auth
def deploy_work_page() -> None:
    user = get_current_user()
    logger.info('Открыли страницу управления шаблонами процессов', extra={
        'component': 'process_templates',
        'version': '1.0.0',
        'user': user.username
    })
    deploy_work.process_templates_page()

# Страница завершения задач с авторизацией
@ui.page('/task_completion')
@require_auth
def task_completion_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу завершения задач', extra={
        'component': 'task_completion',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Завершение задач'):
        task_completion_page.content()

# Страница ознакомления с документами с авторизацией
@ui.page('/document_review')
@require_auth
def document_review_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу ознакомления с документами', extra={
        'component': 'document_review',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Ознакомление с документами'):
        document_review_page.content()

# Страница работы с документами Mayan EDMS с авторизацией
@ui.page('/mayan_documents')
@require_auth
def mayan_documents_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу работы с документами Mayan EDMS', extra={
        'component': 'mayan_documents',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Документы Mayan EDMS'):
        mayan_documents.content()

# Страница поиска документов Mayan EDMS
@ui.page('/mayan_documents_search')
@require_auth
def mayan_documents_search_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу поиска документов Mayan EDMS', extra={
        'component': 'mayan_documents_search',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Поиск документов'):
        mayan_documents.search_content()

# Страница загрузки документов Mayan EDMS
@ui.page('/mayan_documents_upload')
@require_auth
def mayan_documents_upload_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу загрузки документов Mayan EDMS', extra={
        'component': 'mayan_documents_upload',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Загрузка документов'):
        # Создаем контейнер в синхронном контексте
        container = ui.column().classes('w-full')
        
        async def load_upload_content():
            try:
                # Передаем контейнер и пользователя в функцию
                await mayan_documents.upload_content(container, user)
            except Exception as e:
                logger.error(f'Ошибка загрузки страницы загрузки документов: {e}', exc_info=True)
                with container:
                    ui.label(f'Ошибка загрузки страницы: {str(e)}').classes('text-red-500')
        
        ui.timer(0.1, lambda: asyncio.create_task(load_upload_content()), once=True)

# Страница избранных документов Mayan EDMS
@ui.page('/mayan_documents_favorites')
@require_auth
def mayan_documents_favorites_page_handler() -> None:
    """Обработчик страницы избранных документов Mayan EDMS"""
    user = get_current_user()
    logger.info('Открыли страницу избранных документов Mayan EDMS', extra={
        'component': 'mayan_documents_favorites',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Избранные документы'):
        mayan_documents.favorites_content()

# Страница только для администраторов
@ui.page('/admin')
@require_auth
#@require_group('Administrators')
def admin_page() -> None:
    user = get_current_user()
    with theme.frame('Администрирование'):
        ui.label('Панель администратора')
        ui.label(f'Пользователь: {user.first_name} {user.last_name}')
        ui.label(f'Группы: {", ".join(user.groups)}')

@ui.page('/document_signing')
@require_auth
def document_signing_page_handler() -> None:
    user = get_current_user()
    logger.info('Открыли страницу подписания документов', extra={
        'component': 'document_signing',
        'version': '1.0.0',
        'user': user.username
    })
    with theme.frame('Подписание документов'):
        document_signing_page.content()
        
# Тестовая страница (тоже с авторизацией)
@ui.page('/d')
@require_auth
def c_page() -> None:
    user = get_current_user()
    with theme.frame('Homepage'):
        ui.label('This page is just a placeholder. The actual content is created using an APIRouter.')
        ui.label(f'Пользователь: {user.first_name} {user.last_name}')

# Тестовая страница
@ui.page('/test')
@require_auth
def test_page():
    user = get_current_user()
    with theme.frame('Тестовая страница'):
        ui.label('Авторизация работает!')
        ui.label(f'Пользователь: {user.first_name} {user.last_name}')
        ui.label(f'Логин: {user.username}')
        ui.label(f'Email: {user.email or "Не указан"}')
        ui.label(f'Группы: {", ".join(user.groups) if user.groups else "Нет групп"}')
        ui.button('Вернуться на главную', on_click=lambda: ui.navigate.to('/'))

# Example 2: use a function to move the whole page creation into a separate file
#function_example.create()

# Example 3: use a class to move the whole page creation into a separate file
from class_example import ClassExample

# Инициализируем класс с назначением задач
task_assignment = ClassExample()

# Example 4: use APIRouter as described in https://nicegui.io/documentation/page#modularize_with_apirouter
# Подключаем API роутер для обработки событий КриптоПро
app.include_router(api_router.router)

ui.run(title=config.app_name)