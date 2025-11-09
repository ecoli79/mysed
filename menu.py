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
from nicegui import ui
from models import UserSession

def menu(user: UserSession) -> None:
    links: List[Tuple[str, str, bool]] = [
        ('Мои задачи', '/', False),
        ('Запустить новый процесс', '/task-assignment', False),
        ('Завершение задач', '/task_completion', False),
        ('Документы Mayan EDMS', '/mayan_documents', False),
        ('Поиск документов', '/mayan_documents_search', True),  # True = подраздел
        ('Загрузка документов', '/mayan_documents_upload', True),  # True = подраздел
        ('Запущенные мной процессы', '/my_processes', False),
        ('Управление шаблонами процессов', '/process_templates', False),
        ('Подписание документов', '/document_signing', False),
    ]
    with ui.column().classes('gap-1'):
        for text, url, is_submenu in links:
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

