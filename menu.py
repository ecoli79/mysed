from nicegui import ui


def menu() -> None:
    ui.link('Мои задачи', '/').classes(replace='text-white')
    ui.link('Завершение задач', '/task_completion').classes(replace='text-white')
    #ui.link('Ознакомление с документами', '/document_review').classes(replace='text-white')
    ui.link('Документы Mayan EDMS', '/mayan_documents').classes(replace='text-white')
    ui.link('Запущенные мной процессы', '/my_processes').classes(replace='text-white')
    ui.link('Управление шаблонами процессов', '/process_templates').classes(replace='text-white')
    ui.link('Назначение задач', '/task-assignment').classes(replace='text-white')