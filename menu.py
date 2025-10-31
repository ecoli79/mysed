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
    links: List[Tuple[str, str]] = [
        ('Мои задачи', '/'),
        ('Завершение задач', '/task_completion'),
        ('Документы Mayan EDMS', '/mayan_documents'),
        ('Запущенные мной процессы', '/my_processes'),
        ('Управление шаблонами процессов', '/process_templates'),
        ('Назначение задач', '/task-assignment'),
        ('Подписание документов', '/document_signing'),
    ]
    with ui.column().classes('gap-1'):
        for text, url in links:
             ui.link(text, url).classes(
            'block w-full px-3 py-2 rounded hover:bg-white/10 text-white no-underline hover:no-underline'
        )

