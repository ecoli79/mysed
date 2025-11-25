# from nicegui import ui


# def menu() -> None:
#     ui.link('Мои задачи', '/').classes(replace='text-white')
#     ui.link('Завершение задач', '/task_completion').classes(replace='text-white')
#     #ui.link('Ознакомление с документами', '/document_review').classes(replace='text-white')
#     ui.link('Документы Mayan EDMS', '/mayan_documents').classes(replace='text-white')
#     ui.link('Запущенные мной процессы', '/my_processes').classes(replace='text-white')
#     ui.link('Управление шаблонами процессов', '/process_templates').classes(replace='text-white')
#     ui.link('Назначение задач', '/task-assignment').classes(replace='text-white')
#     ui.link('Подписание документов', '/document_signing').classes('text-white hover:text-blue-200')

from typing import List, Tuple
import logging
from nicegui import ui
from models import UserSession

logger = logging.getLogger(__name__)

def menu(user: UserSession) -> None:
    # Проверяем, является ли пользователь администратором
    # Нормализуем группы: убираем пробелы и приводим к нижнему регистру
    user_groups_normalized = [group.strip().lower() for group in user.groups]
    is_admin = 'admins' in user_groups_normalized
    
    # Отладочный вывод (можно убрать после проверки)
    logger.debug(f'Пользователь {user.username}: группы = {user.groups}, is_admin = {is_admin}')
    
    # Структура: (текст, url, is_submenu, admin_only)
    links: List[Tuple[str, str, bool, bool]] = [
        ('Мои задачи', '/', False, False),
        ('Запустить новый процесс', '/task-assignment', False, False),
        ('Завершение задач', '/task_completion', False, False),
        ('Документы Mayan EDMS', '/mayan_documents', False, False),
        ('Поиск документов', '/mayan_documents_search', True, False),  # True = подраздел
        ('Загрузка документов', '/mayan_documents_upload', True, False),  # True = подраздел
        ('Запущенные мной процессы', '/my_processes', False, False),
        ('Подписание документов', '/document_signing', False, False),
        ('Управление шаблонами процессов', '/process_templates', False, True),  # Только для админов
    ]
    with ui.column().classes('gap-1'):
        for text, url, is_submenu, admin_only in links:
            # Пропускаем ссылки, доступные только админам, если пользователь не админ
            if admin_only and not is_admin:
                continue
                
            if is_submenu:
                # Подраздел с отступом
                ui.link(text, url).classes(
                    'block w-full px-3 py-2 rounded hover:bg-white/10 text-white no-underline hover:no-underline pl-8'
                )
            else:
                # Обычный пункт меню
                ui.link(text, url).classes(
                    'block w-full px-3 py-2 rounded hover:bg-white/10 text-white no-underline hover:no-underline'
                )

