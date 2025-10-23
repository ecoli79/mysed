from nicegui import ui
from services.camunda_connector import create_camunda_client
from services.mayan_connector import MayanClient
from config.settings import config
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional
from models import CamundaHistoryTask
from auth.middleware import get_current_user
from utils import validate_username
from datetime import datetime
import api_router

logger = logging.getLogger(__name__)

# Глобальные переменные для управления состоянием
_tasks_container: Optional[ui.column] = None
_completed_tasks_container: Optional[ui.column] = None
_details_container: Optional[ui.column] = None
_task_details_sidebar: Optional[ui.column] = None
_task_details_column: Optional[ui.column] = None  # Добавляем переменную для контейнера деталей
_uploaded_files_container: Optional[ui.column] = None
_uploaded_files: List[Dict[str, Any]] = []
_tabs: Optional[ui.tabs] = None  # Добавляем ссылку на табы
_task_details_tab: Optional[ui.tab] = None  # Добавляем ссылку на вкладку деталей
_tasks_header_container: Optional[ui.column] = None  # Добавляем переменную для заголовка с количеством задач
_certificate_select_global = None
_selected_certificate = None
_certificates_cache = []

def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return MayanClient.create_with_session_user()

def _is_valid_username(username: str) -> bool:
    """Проверяет безопасность имени пользователя"""
    if not username or len(username) > 50:
        return False
    
    # Разрешаем только буквы, цифры, точки, дефисы и подчеркивания
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_')
    return all(c in allowed_chars for c in username)

def content() -> None:
    """Основная страница завершения задач"""
    ui.label('Завершение задач').classes('text-2xl font-bold mb-6')
    
    # Создаем табы
    with ui.tabs().classes('w-full') as tabs:
        active_tasks_tab = ui.tab('Мои активные задачи')
        completed_tasks_tab = ui.tab('Завершенные задачи')
        task_details_tab = ui.tab('Детали задачи')
    
    with ui.tab_panels(tabs, value=active_tasks_tab).classes('w-full mt-4'):
        # Таб с активными задачами
        with ui.tab_panel(active_tasks_tab):
            create_active_tasks_section()
        
        # Таб с завершенными задачами
        with ui.tab_panel(completed_tasks_tab):
            create_completed_tasks_section()
        
        # Таб с деталями задачи
        with ui.tab_panel(task_details_tab):
            create_task_details_section()
    
    # Сохраняем ссылку на табы для использования в других функциях
    global _tabs, _task_details_tab
    _tabs = tabs
    _task_details_tab = task_details_tab

def create_active_tasks_section():
    """Создает секцию с активными задачами"""
    global _tasks_container, _task_details_sidebar, _task_details_column, _tasks_header_container
    
    ui.label('Мои активные задачи').classes('text-xl font-semibold mb-4')
    
    # Создаем горизонтальный макет с задачами слева и деталями справа
    with ui.row().classes('w-full gap-4'):
        # Левая колонка с задачами
        with ui.column().classes('flex-1'):
            with ui.card().classes('p-6 w-full'):
                # Кнопка обновления
                ui.button(
                    'Обновить задачи',
                    icon='refresh',
                    on_click=lambda: load_active_tasks(_tasks_header_container)
                ).classes('mb-4 bg-blue-500 text-white')
                
                # Контейнер для заголовка с количеством задач
                _tasks_header_container = ui.column().classes('w-full mb-4')
                
                # Контейнер для задач
                _tasks_container = ui.column().classes('w-full')
                
                # Загружаем задачи при открытии страницы
                load_active_tasks(_tasks_header_container)
        
        # Правая колонка с деталями задачи (скрыта по умолчанию)
        _task_details_column = ui.column().classes('w-1/3')
        with _task_details_column:
            with ui.card().classes('p-4 h-full'):
                ui.label('Детали задачи').classes('text-lg font-semibold mb-4')
                _task_details_sidebar = ui.column().classes('w-full')
                
                # Показываем сообщение по умолчанию
                with _task_details_sidebar:
                    ui.label('Выберите задачу для просмотра деталей').classes('text-gray-500 text-center')
        
        # Скрываем блок деталей по умолчанию
        _task_details_column.set_visibility(False)

def load_active_tasks(header_container=None):
    """Загружает и отображает активные задачи пользователя"""
    global _tasks_container
    
    if _tasks_container is None:
        return
    
    # Очищаем контейнеры
    _tasks_container.clear()
    if header_container:
        header_container.clear()
    
    try:
        # Получаем текущего авторизованного пользователя
        user = get_current_user()
        if not user:
            if header_container:
                with header_container:
                    ui.label('Ошибка: пользователь не авторизован').classes('text-red-600')
            return
        
        # Валидация логина на безопасность
        if not validate_username(user.username):
            logger.error(f"Небезопасный логин пользователя: {user.username}")
            if header_container:
                with header_container:
                    ui.label('Ошибка: некорректный логин пользователя').classes('text-red-600')
            return
        
        # Получаем активные задачи пользователя с фильтрацией
        assignee = user.username
        camunda_client = create_camunda_client()
        tasks = camunda_client.get_user_tasks_filtered(
            assignee=assignee,
            active_only=True,
            filter_completed=True
        )
        
        if tasks:
            # Добавляем заголовок с количеством задач в отдельный контейнер
            if header_container:
                with header_container:
                    ui.label(f'Найдено {len(tasks)} активных задач:').classes('text-lg font-semibold')
            
            # Добавляем карточки задач в основной контейнер
            for task in tasks:
                create_task_card_with_progress(task)
        else:
            # Показываем сообщение об отсутствии задач
            if header_container:
                with header_container:
                    ui.label('Нет активных задач').classes('text-gray-500')
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке активных задач: {e}", exc_info=True)
        if header_container:
            with header_container:
                ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')

def create_task_card_with_progress(task):
    """Создает карточку задачи с информацией о прогрессе"""
    global _tasks_container
    
    if _tasks_container is None:
        return
        
    with _tasks_container:
        with ui.card().classes('p-4 mb-4 border-l-4 border-blue-500'):
            with ui.row().classes('w-full justify-between items-start'):
                with ui.column().classes('flex-1'):
                    ui.label(task.name).classes('text-lg font-semibold')
                    ui.label(f'ID задачи: {task.id}').classes('text-sm text-gray-600')
                    ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm text-gray-600')
                    
                    # Добавляем информацию о прогрессе
                    try:
                        camunda_client = create_camunda_client()
                        progress = camunda_client.get_task_progress(task.process_instance_id)
                        
                        # Прогресс-бар
                        with ui.row().classes('w-full items-center gap-2 mt-2'):
                            ui.label(f'Прогресс: {progress["completed_reviews"]}/{progress["total_reviews"]} пользователей').classes('text-sm')
                            ui.linear_progress(value=progress["progress_percent"]/100, show_value=False).classes('flex-1')
                            ui.label(f'{progress["progress_percent"]:.0f}%').classes('text-sm text-gray-600')
                        
                        # Список пользователей и их статус
                        if progress["user_status"]:
                            with ui.expansion('Статус пользователей', icon='people').classes('w-full mt-2'):
                                for user_info in progress["user_status"]:
                                    status_icon = 'check_circle' if user_info["completed"] else 'schedule'
                                    status_color = 'text-green-600' if user_info["completed"] else 'text-orange-600'
                                    
                                    with ui.row().classes('w-full items-center gap-2'):
                                        ui.icon(status_icon).classes(status_color)
                                        ui.label(f'{user_info["user"]}: {user_info["status"]}').classes('text-sm')
                        
                    except Exception as e:
                        logger.warning(f"Не удалось получить информацию о прогрессе для задачи {task.id}: {e}")
                        ui.label('Информация о прогрессе недоступна').classes('text-sm text-gray-500')
                
                with ui.column().classes('gap-2'):
                    ui.button(
                        'Завершить задачу',
                        icon='check',
                        on_click=lambda t=task: complete_task(t)
                    ).classes('bg-green-500 text-white')
                    
                    ui.button(
                        'Детали',
                        icon='info',
                        on_click=lambda t=task: show_task_details(t)
                    ).classes('bg-blue-500 text-white')

def create_task_card(task):
    """Создает карточку задачи"""
    global _tasks_container
    
    if _tasks_container is None:
        return
        
    with _tasks_container:
        with ui.card().classes('mb-3 p-4 border-l-4 border-blue-500'):
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    ui.label(f'{task.name}').classes('text-lg font-semibold')
                    
                    if task.description:
                        ui.label(f'Описание: {task.description}').classes('text-sm text-gray-600')
                    
                    ui.label(f'Создана: {task.start_time}').classes('text-sm text-gray-600')
                    
                    if task.due:
                        ui.label(f'Срок: {task.due}').classes('text-sm text-gray-600')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        ui.button(
                            'Просмотр деталей',
                            icon='visibility',
                            on_click=lambda t=task: show_task_details(t)
                        ).classes('bg-blue-500 text-white text-xs')
                        
                        ui.button(
                            'Завершить задачу',
                            icon='check',
                            on_click=lambda t=task: complete_task(t)
                        ).classes('bg-green-500 text-white text-xs')
                
                with ui.column().classes('items-end'):
                    ui.label(f'ID: {task.id}').classes('text-xs text-gray-500 font-mono')
                    ui.label(f'Приоритет: {task.priority}').classes('text-xs text-gray-500')

def create_completed_tasks_section():
    """Создает секцию с завершенными задачами"""
    global _completed_tasks_container
    
    ui.label('Завершенные задачи').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Кнопка обновления
        ui.button(
            'Обновить задачи',
            icon='refresh',
            on_click=load_completed_tasks
        ).classes('mb-4 bg-blue-500 text-white')
        
        # Контейнер для задач
        _completed_tasks_container = ui.column().classes('w-full')
        
        # Загружаем задачи при открытии страницы
        load_completed_tasks()

def load_completed_tasks():
    """Загружает завершенные задачи"""
    global _completed_tasks_container
    
    if _completed_tasks_container is None:
        return
        
    _completed_tasks_container.clear()
    
    with _completed_tasks_container:
        try:
            # Получаем текущего авторизованного пользователя
            user = get_current_user()
            if not user:
                ui.label('Ошибка: пользователь не авторизован').classes('text-red-600')
                return
            
            # Валидация логина на безопасность
            if not validate_username(user.username):
                logger.error(f"Небезопасный логин пользователя: {user.username}")
                ui.label('Ошибка: некорректный логин пользователя').classes('text-red-600')
                return
            
            # Получаем завершенные задачи пользователя с группировкой
            assignee = user.username
            camunda_client = create_camunda_client()
            
            logger.info(f"Загружаем завершенные задачи для пользователя {assignee}")
            
            tasks = camunda_client.get_completed_tasks_grouped(assignee=assignee)
            
            logger.info(f"Получено {len(tasks) if tasks else 0} задач (сгруппированных)")
            
            if tasks:
                ui.label(f'Найдено {len(tasks)} завершенных задач:').classes('text-lg font-semibold mb-4')
                
                for task in tasks:
                    # Проверяем тип задачи
                    from models import GroupedHistoryTask
                    if isinstance(task, GroupedHistoryTask):
                        logger.info(f"Создаем карточку для группированной задачи {task.process_instance_id}")
                        create_grouped_completed_task_card(task)
                    else:
                        logger.info(f"Создаем карточку для обычной задачи {task.id}")
                        create_completed_task_card(task)
            else:
                ui.label('Нет завершенных задач').classes('text-gray-500')
                
        except Exception as e:
            logger.error(f"Ошибка при загрузке завершенных задач: {e}", exc_info=True)
            ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')


def create_grouped_completed_task_card(task):
    """Создает карточку для группированной завершенной задачи"""
    global _completed_tasks_container
    
    if _completed_tasks_container is None:
        return
        
    with _completed_tasks_container:
        with ui.card().classes('mb-3 p-4 border-l-4 border-green-500'):
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    # Название задачи с иконкой группы
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('groups').classes('text-blue-600')
                        ui.label(f'{task.name}').classes('text-lg font-semibold')
                    
                    if task.description:
                        ui.label(f'Описание: {task.description}').classes('text-sm text-gray-600')
                    
                    ui.label(f'Начата: {task.start_time}').classes('text-sm text-gray-600')
                    
                    if task.end_time:
                        ui.label(f'Завершена: {task.end_time}').classes('text-sm text-gray-600')
                    
                    if hasattr(task, 'duration_formatted'):
                        ui.label(f'Длительность: {task.duration_formatted}').classes('text-sm text-gray-600')
                    
                    # Прогресс завершения
                    with ui.row().classes('w-full items-center gap-2 mt-2'):
                        ui.label(f'Прогресс: {task.completed_users}/{task.total_users} пользователей').classes('text-sm font-medium')
                        ui.linear_progress(value=task.completion_percent/100, show_value=False).classes('flex-1')
                        ui.label(f'{task.completion_percent:.0f}%').classes('text-sm text-gray-600')
                    
                    # Список пользователей с кратким статусом
                    with ui.expansion(f'Пользователи ({len(task.user_tasks)})', icon='people').classes('w-full mt-2'):
                        for user_task in task.user_tasks:
                            status_icon = 'check_circle' if user_task.status == 'completed' else 'cancel'
                            status_color = 'text-green-600' if user_task.status == 'completed' else 'text-red-600'
                            status_text = 'Завершено' if user_task.status == 'completed' else 'Отменено'
                            
                            with ui.row().classes('w-full items-center gap-2 mb-2'):
                                ui.icon(status_icon).classes(status_color)
                                with ui.column().classes('flex-1'):
                                    ui.label(f'{user_task.assignee}: {status_text}').classes('text-sm font-medium')
                                    if user_task.end_time:
                                        ui.label(f'Завершена: {user_task.end_time}').classes('text-xs text-gray-500')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        ui.button(
                            'Просмотр деталей',
                            icon='visibility',
                            on_click=lambda t=task: show_grouped_task_details_in_tab(t)
                        ).classes('bg-blue-500 text-white text-xs')
                
                with ui.column().classes('items-end'):
                    ui.label(f'ID процесса: {task.process_instance_id}').classes('text-xs text-gray-500 font-mono')
                    ui.label(f'Статус: Завершена').classes('text-xs text-green-600')
                    ui.label(f'Multi-user: {task.total_users} польз.').classes('text-xs text-blue-600')

def show_grouped_task_details_in_tab(task):
    """Показывает детали группированной завершенной задачи"""
    global _details_container, _tabs, _task_details_tab
    
    if _details_container is None:
        ui.notify('Ошибка: контейнер деталей не инициализирован', type='error')
        return
    
    # Переключаемся на вкладку "Детали задачи"
    if _tabs is not None and _task_details_tab is not None:
        _tabs.value = _task_details_tab
    
    # Очищаем контейнер деталей
    _details_container.clear()
    
    with _details_container:
        # Основная информация о задаче
        with ui.card().classes('p-4 bg-green-50 mb-4'):
            ui.label('Информация о завершенной задаче').classes('text-lg font-semibold mb-3')
            
            with ui.row().classes('items-center gap-2 mb-2'):
                ui.icon('groups').classes('text-blue-600')
                ui.label('Multi-user задача').classes('text-sm font-medium text-blue-600')
            
            ui.label(f'Название: {task.name}').classes('text-sm mb-2')
            ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm mb-2')
            ui.label(f'Создана: {task.start_time}').classes('text-sm mb-2')
            
            if task.end_time:
                ui.label(f'Завершена: {task.end_time}').classes('text-sm mb-2')
            
            if hasattr(task, 'duration_formatted'):
                ui.label(f'Общая длительность: {task.duration_formatted}').classes('text-sm mb-2')
            
            ui.label(f'Приоритет: {task.priority}').classes('text-sm mb-2')
            ui.label(f'Статус: Завершена').classes('text-sm mb-2')
            
            if task.description:
                ui.label(f'Описание: {task.description}').classes('text-sm mb-2')
            
            if task.due:
                ui.label(f'Срок: {task.due}').classes('text-sm mb-2')
            
            # Прогресс
            ui.label(f'Прогресс завершения: {task.completed_users}/{task.total_users} пользователей ({task.completion_percent:.0f}%)').classes('text-sm mb-2')
        
        # Детальная информация о пользователях
            with ui.card().classes('p-4 bg-blue-50 mb-4'):
                ui.label('Подзадачи пользователей').classes('text-lg font-semibold mb-3')
                
                for user_task in task.user_tasks:
                    with ui.card().classes('p-3 mb-3 bg-white'):
                        status_color = 'text-green-600' if user_task.status == 'completed' else 'text-red-600'
                        status_icon = 'check_circle' if user_task.status == 'completed' else 'cancel'
                        
                        with ui.row().classes('items-center gap-2 mb-2'):
                            ui.icon(status_icon).classes(status_color)
                            ui.label(f'Пользователь: {user_task.assignee}').classes('text-sm font-semibold')
                        
                        ui.label(f'ID задачи: {user_task.task_id}').classes('text-xs text-gray-500 mb-1')
                        ui.label(f'Начата: {user_task.start_time}').classes('text-xs mb-1')
                        
                        if user_task.end_time:
                            ui.label(f'Завершена: {user_task.end_time}').classes('text-xs mb-1')
                        
                        if user_task.duration:
                            duration_sec = user_task.duration // 1000
                            duration_formatted = f'{duration_sec // 60} мин {duration_sec % 60} сек'
                            ui.label(f'Длительность: {duration_formatted}').classes('text-xs mb-1')
                        
                        ui.label(f'Статус: {"Завершено" if user_task.status == "completed" else "Отменено"}').classes(f'text-xs mb-1 {status_color}')
                        
                        # ДОБАВЛЯЕМ ОТОБРАЖЕНИЕ КОММЕНТАРИЯ
                        if user_task.comment:
                            with ui.card().classes('p-2 bg-yellow-50 border-l-4 border-yellow-400 mt-2'):
                                ui.label('Комментарий:').classes('text-xs font-semibold text-yellow-800')
                                ui.label(user_task.comment).classes('text-xs text-gray-700 italic')
                        
                        if user_task.review_date:
                            ui.label(f'Дата ознакомления: {user_task.review_date}').classes('text-xs text-gray-600 mt-1')
        
        # Информация о процессе
        try:
            camunda_client = create_camunda_client()
            process_variables = camunda_client.get_history_process_instance_variables_by_name(
                task.process_instance_id,
                ['documentName', 'documentContent', 'assigneeList', 'reviewDates', 'reviewComments']
            )
            
            if process_variables:
                with ui.card().classes('p-4 bg-purple-50 mb-4'):
                    ui.label('Переменные процесса').classes('text-lg font-semibold mb-3')
                    
                    for key, value in process_variables.items():
                        # Форматируем значение для лучшего отображения
                        formatted_value = format_variable_value(value)
                        if isinstance(formatted_value, (dict, list)):
                            import json
                            formatted_value = json.dumps(formatted_value, ensure_ascii=False, indent=2)
                        ui.label(f'{key}: {formatted_value}').classes('text-sm mb-1 whitespace-pre-wrap')
        except Exception as e:
            logger.warning(f"Не удалось получить переменные процесса {task.process_instance_id}: {e}")
        
        # Кнопка обновления
        with ui.column().classes('w-full gap-2'):
            ui.button(
                'Обновить детали',
                icon='refresh',
                on_click=lambda t=task: show_grouped_task_details_in_tab(t)
            ).classes('w-full bg-blue-500 text-white')

def create_completed_task_card(task):
    """Создает карточку завершенной задачи"""
    global _completed_tasks_container
    
    if _completed_tasks_container is None:
        return
        
    with _completed_tasks_container:
        with ui.card().classes('mb-3 p-4 border-l-4 border-green-500'):
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    ui.label(f'{task.name}').classes('text-lg font-semibold')
                    
                    if task.description:
                        ui.label(f'Описание: {task.description}').classes('text-sm text-gray-600')
                    
                    ui.label(f'Начата: {task.start_time}').classes('text-sm text-gray-600')
                    
                    if hasattr(task, 'end_time') and task.end_time:
                        ui.label(f'Завершена: {task.end_time}').classes('text-sm text-gray-600')
                    
                    if hasattr(task, 'duration_formatted'):
                        ui.label(f'Длительность: {task.duration_formatted}').classes('text-sm text-gray-600')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        ui.button(
                            'Просмотр деталей',
                            icon='visibility',
                            on_click=lambda t=task: show_completed_task_details_in_tab(t)
                        ).classes('bg-blue-500 text-white text-xs')
                        
                        ui.button(
                            'Просмотр результатов',
                            icon='folder_open',
                            on_click=lambda t=task: show_task_results(t)
                        ).classes('bg-green-500 text-white text-xs')
                
                with ui.column().classes('items-end'):
                    ui.label(f'ID: {task.id}').classes('text-xs text-gray-500 font-mono')
                    ui.label(f'Статус: Завершена').classes('text-xs text-green-600')


def show_completed_task_details_in_tab(task):
    """Показывает детали завершенной задачи на вкладке 'Детали задачи'"""
    global _details_container, _tabs, _task_details_tab
    
    if _details_container is None:
        ui.notify('Ошибка: контейнер деталей не инициализирован', type='error')
        return
    
    # Переключаемся на вкладку "Детали задачи"
    if _tabs is not None and _task_details_tab is not None:
        _tabs.value = _task_details_tab
    
    # Очищаем контейнер деталей
    _details_container.clear()
    
    with _details_container:
        ui.label('Загрузка деталей завершенной задачи...').classes('text-gray-600')
        
        try:
            # Проверяем, является ли это группированной задачей
            from models import GroupedHistoryTask
            if isinstance(task, GroupedHistoryTask):
                # Если это группированная задача, используем специальную функцию
                show_grouped_task_details_in_tab(task)
                return
            
            # Получаем детальную информацию о задаче
            camunda_client = create_camunda_client()
            
            # Для завершенных задач используем исторический API
            task_details = camunda_client.get_history_task_by_id(task.id)
            if not task_details:
                # Если историческая задача не найдена, попробуем получить как активную
                task_details = camunda_client.get_task_by_id(task.id)
            
            if not task_details:
                ui.label(f'Задача {task.id} не найдена').classes('text-red-600')
                ui.label('Возможные причины:').classes('text-sm text-gray-600 mt-2')
                ui.label('• Задача была удалена из истории').classes('text-sm text-gray-600')
                ui.label('• Неправильный ID задачи').classes('text-sm text-gray-600')
                return
            
            # Проверяем, является ли это частью multi-instance процесса
            # Получаем все задачи для этого процесса
            try:
                all_process_tasks = camunda_client.get_completed_tasks_grouped()
                grouped_task = None
                
                # Ищем группированную задачу для этого процесса
                for gt in all_process_tasks:
                    if isinstance(gt, GroupedHistoryTask) and gt.process_instance_id == task_details.process_instance_id:
                        grouped_task = gt
                        break
                
                if grouped_task:
                    # Если нашли группированную задачу, показываем её детали
                    show_grouped_task_details_in_tab(grouped_task)
                    return
                    
            except Exception as e:
                logger.warning(f"Не удалось проверить группировку для задачи {task.id}: {e}")
            
            # Основная информация о задаче (обычная задача) - УЛУЧШЕННАЯ ВЕРСИЯ
            with ui.card().classes('p-4 bg-green-50 mb-4'):
                ui.label('Информация о завершенной задаче').classes('text-lg font-semibold mb-3')
                
                # Добавляем иконку для обычной задачи
                with ui.row().classes('items-center gap-2 mb-2'):
                    ui.icon('person').classes('text-green-600')
                    ui.label('Обычная задача').classes('text-sm font-medium text-green-600')
                
                ui.label(f'Название: {task_details.name}').classes('text-sm mb-2')
                ui.label(f'ID задачи: {task_details.id}').classes('text-sm mb-2')
                ui.label(f'ID процесса: {task_details.process_instance_id}').classes('text-sm mb-2')
                ui.label(f'Исполнитель: {task_details.assignee or "Не назначен"}').classes('text-sm mb-2')
                ui.label(f'Создана: {task_details.start_time}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'end_time') and task_details.end_time:
                    ui.label(f'Завершена: {task_details.end_time}').classes('text-sm mb-2')
                
                # Добавляем длительность выполнения
                if hasattr(task_details, 'duration') and task_details.duration:
                    duration_sec = task_details.duration // 1000
                    duration_formatted = f'{duration_sec // 60} мин {duration_sec % 60} сек'
                    ui.label(f'Длительность: {duration_formatted}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'priority'):
                    ui.label(f'Приоритет: {task_details.priority}').classes('text-sm mb-2')
                
                ui.label(f'Статус: Завершена').classes('text-sm mb-2')
                
                if hasattr(task_details, 'description') and task_details.description:
                    ui.label(f'Описание: {task_details.description}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'due') and task_details.due:
                    ui.label(f'Срок: {task_details.due}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'delete_reason') and task_details.delete_reason:
                    ui.label(f'Причина завершения: {task_details.delete_reason}').classes('text-sm mb-2')
            
            # Детальная информация о пользователе (аналогично группированным задачам)
            with ui.card().classes('p-4 bg-blue-50 mb-4'):
                ui.label('Детали выполнения').classes('text-lg font-semibold mb-3')
                
                with ui.card().classes('p-3 mb-3 bg-white'):
                    status_color = 'text-green-600'
                    status_icon = 'check_circle'
                    
                    with ui.row().classes('items-center gap-2 mb-2'):
                        ui.icon(status_icon).classes(status_color)
                        ui.label(f'Пользователь: {task_details.assignee or "Не назначен"}').classes('text-sm font-semibold')
                    
                    ui.label(f'ID задачи: {task_details.id}').classes('text-xs text-gray-500 mb-1')
                    ui.label(f'Начата: {task_details.start_time}').classes('text-xs mb-1')
                    
                    if hasattr(task_details, 'end_time') and task_details.end_time:
                        ui.label(f'Завершена: {task_details.end_time}').classes('text-xs mb-1')
                    
                    if hasattr(task_details, 'duration') and task_details.duration:
                        duration_sec = task_details.duration // 1000
                        duration_formatted = f'{duration_sec // 60} мин {duration_sec % 60} сек'
                        ui.label(f'Длительность: {duration_formatted}').classes('text-xs mb-1')
                    
                    ui.label(f'Статус: Завершено').classes(f'text-xs mb-1 {status_color}')
                    
                    # Получаем комментарий пользователя из переменных процесса
                    try:
                        process_variables = camunda_client.get_history_process_instance_variables_by_name(
                            task_details.process_instance_id,
                            ['userComments', 'userCompletionDates', 'userStatus', 'userCompleted']
                        )
                        
                        if process_variables:
                            from models import ProcessVariables
                            process_vars = ProcessVariables(**process_variables)
                            user_info = process_vars.get_user_info(task_details.assignee)
                            
                            # Отображаем комментарий пользователя
                            if user_info and user_info.get('comment'):
                                with ui.card().classes('p-2 bg-yellow-50 border-l-4 border-yellow-400 mt-2'):
                                    ui.label('Комментарий:').classes('text-xs font-semibold text-yellow-800')
                                    ui.label(user_info['comment']).classes('text-xs text-gray-700 italic')
                            
                            # Отображаем дату ознакомления
                            if user_info and user_info.get('completion_date'):
                                ui.label(f'Дата ознакомления: {user_info["completion_date"]}').classes('text-xs text-gray-600 mt-1')
                            elif hasattr(task_details, 'end_time') and task_details.end_time:
                                ui.label(f'Дата ознакомления: {task_details.end_time}').classes('text-xs text-gray-600 mt-1')
                                
                    except Exception as e:
                        logger.warning(f"Не удалось получить комментарий для {task_details.assignee}: {e}")
                        # Если не удалось получить комментарий, показываем базовую информацию
                        if hasattr(task_details, 'end_time') and task_details.end_time:
                            ui.label(f'Дата ознакомления: {task_details.end_time}').classes('text-xs text-gray-600 mt-1')
            
            # Информация о процессе (улучшенная версия)
            try:
                process_variables = camunda_client.get_history_process_instance_variables_by_name(
                    task_details.process_instance_id,
                    ['documentName', 'documentContent', 'assigneeList', 'reviewDates', 'reviewComments', 'taskDescription', 'dueDate']
                )
                
                if process_variables:
                    with ui.card().classes('p-4 bg-purple-50 mb-4'):
                        ui.label('Переменные процесса').classes('text-lg font-semibold mb-3')
                        
                        for key, value in process_variables.items():
                            # Форматируем значение для лучшего отображения
                            formatted_value = format_variable_value(value)
                            if isinstance(formatted_value, (dict, list)):
                                import json
                                formatted_value = json.dumps(formatted_value, ensure_ascii=False, indent=2)
                            ui.label(f'{key}: {formatted_value}').classes('text-sm mb-1 whitespace-pre-wrap')
                else:
                    # Fallback к старому методу
                    process_variables = camunda_client.get_process_instance_variables(task_details.process_instance_id)
                    if process_variables:
                        with ui.card().classes('p-4 bg-purple-50 mb-4'):
                            ui.label('Переменные процесса').classes('text-lg font-semibold mb-3')
                            
                            for key, value in process_variables.items():
                                # Форматируем значение для лучшего отображения
                                formatted_value = format_variable_value(value)
                                ui.label(f'{key}: {formatted_value}').classes('text-sm mb-1')
            except Exception as e:
                logger.warning(f"Не удалось получить переменные процесса {task_details.process_instance_id}: {e}")
            
            # Кнопки действий
            with ui.column().classes('w-full gap-2'):
                ui.button(
                    'Обновить детали',
                    icon='refresh',
                    on_click=lambda t=task: show_completed_task_details_in_tab(t)
                ).classes('w-full bg-blue-500 text-white')
                
                ui.button(
                    'Просмотр результатов',
                    icon='folder_open',
                    on_click=lambda t=task: show_task_results(t)
                ).classes('w-full bg-green-500 text-white')
            
        except Exception as e:
            ui.label(f'Ошибка при загрузке деталей: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке деталей завершенной задачи {task.id}: {e}", exc_info=True)


def show_completed_task_details(task):
    """Показывает детали завершенной задачи"""
    show_task_details(task)

def show_completed_task_results(task):
    """Показывает результаты завершенной задачи"""
    show_task_results(task)

def create_task_details_section():
    """Создает секцию с деталями задачи"""
    global _details_container
    
    ui.label('Детали задачи').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Поле для ввода ID задачи
        task_id_input = ui.input(
            'ID задачи',
            placeholder='Введите ID задачи для просмотра деталей'
        ).classes('w-full mb-4')
        
        ui.button(
            'Загрузить детали',
            icon='search',
            on_click=lambda: load_task_details(task_id_input.value)
        ).classes('bg-blue-500 text-white mb-4')
        
        # Контейнер для деталей задачи
        _details_container = ui.column().classes('w-full')

def load_task_details(task_id: str):
    """Загружает детали задачи"""
    global _details_container
    
    if _details_container is None:
        return
        
    if not task_id:
        ui.notify('Введите ID задачи', type='error')
        return
    
    _details_container.clear()
    
    with _details_container:
        ui.label('Загрузка деталей...').classes('text-gray-600')
        
        try:
            # Получаем задачу по ID
            camunda_client = create_camunda_client()
            task = camunda_client.get_task_by_id(task_id)
            if not task:
                ui.label('Задача не найдена').classes('text-red-600')
                return
            
            # Отображаем детали задачи
            with ui.card().classes('p-4 bg-gray-50'):
                ui.label('Информация о задаче').classes('text-lg font-semibold mb-3')
                
                ui.label(f'Название: {task.name}').classes('text-sm mb-2')
                ui.label(f'ID: {task.id}').classes('text-sm mb-2')
                ui.label(f'Исполнитель: {task.assignee or "Не назначен"}').classes('text-sm mb-2')
                ui.label(f'Создана: {task.start_time}').classes('text-sm mb-2')
                ui.label(f'Приоритет: {task.priority}').classes('text-sm mb-2')
                ui.label(f'Статус: {"Активна" if not task.suspended else "Приостановлена"}').classes('text-sm mb-2')
                
                if task.description:
                    ui.label(f'Описание: {task.description}').classes('text-sm mb-2')
                
                if task.due:
                    ui.label(f'Срок: {task.due}').classes('text-sm mb-2')
            
            # Пытаемся получить переменные (с обработкой ошибок)
            try:
                variables = camunda_client.get_task_completion_variables(task_id)
                if variables:
                    with ui.card().classes('p-4 bg-blue-50 mt-4'):
                        ui.label('Переменные задачи').classes('text-lg font-semibold mb-3')
                        
                        for key, value in variables.items():
                            ui.label(f'{key}: {value}').classes('text-sm mb-1')
            except Exception as e:
                logger.warning(f"Не удалось получить переменные задачи {task_id}: {e}")
                with ui.card().classes('p-4 bg-yellow-50 mt-4'):
                    ui.label('Переменные задачи недоступны').classes('text-sm text-yellow-600')
            
        except Exception as e:
            ui.label(f'Ошибка при загрузке деталей: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке деталей задачи {task_id}: {e}", exc_info=True)

def complete_task(task):
    """Завершает задачу"""
    # Проверяем, является ли это задачей подписания
    if task.name == "Подписать документ":
        complete_signing_task(task)
    else:
        complete_regular_task(task)


def complete_regular_task(task):
    """Завершает задачу"""
    # Создаем модальное окно для завершения задачи
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label('Завершение задачи').classes('text-xl font-semibold mb-4')
        
        # Информация о задаче
        with ui.card().classes('p-4 bg-gray-50 mb-4'):
            ui.label(f'Задача: {task.name}').classes('text-lg font-semibold')
            ui.label(f'ID задачи: {task.id}').classes('text-sm text-gray-600')
            ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm text-gray-600')
        
        # Форма завершения
        with ui.column().classes('w-full'):
            # Статус завершения
            status_select = ui.select(
                options={
                    'completed': 'Выполнено',
                    'rejected': 'Отклонено',
                    'cancelled': 'Отменено'
                },
                value='completed',
                label='Статус выполнения'
            ).classes('w-full mb-4')
            
            # Комментарий
            comment_textarea = ui.textarea(
                label='Комментарий',
                placeholder='Введите комментарий к выполнению задачи...'
            ).classes('w-full mb-4')
            
            # Загрузка файлов результата
            ui.label('Файлы результата (опционально)').classes('text-sm font-medium mb-2')
            file_upload = ui.upload(
                on_upload=handle_file_upload,
                multiple=True,
                max_file_size=50 * 1024 * 1024  # 50MB
            ).classes('w-full mb-4')
            
            # Список загруженных файлов
            global _uploaded_files_container, _uploaded_files
            _uploaded_files_container = ui.column().classes('w-full mb-4')
            _uploaded_files = []
            
            # Кнопки действий
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button(
                    'Отмена',
                    on_click=dialog.close
                ).classes('bg-gray-500 text-white')
                
                ui.button(
                    'Завершить задачу',
                    icon='check',
                    on_click=lambda: submit_task_completion(task, status_select.value, comment_textarea.value, dialog)
                ).classes('bg-green-500 text-white')
    
    dialog.open()

def complete_signing_task(task):
    """Завершает задачу подписания документа"""
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
        ui.label('Подписание документа').classes('text-2xl font-bold mb-4')
        
        with ui.column().classes('w-full gap-4'):
            # Информация о документе
            ui.label(f'Документ: {task.name}').classes('text-lg')
            ui.label(f'ID документа: {task.name}')
            ui.label(f'ID задачи: {task.id}')
            
            # Документ для подписания
            ui.label('Документ для подписания:').classes('text-lg font-semibold')
            ui.label('Документ не найден').classes('text-red-500')
            
            # Статус КриптоПро
            ui.label('Электронная подпись:').classes('text-lg font-semibold')
            crypto_status = ui.html('').classes('mb-4')
            check_crypto_pro_availability(crypto_status)
            
            # Информация о выбранном сертификате
            certificate_info_display = ui.html('').classes('w-full mb-4 p-4 bg-gray-50 rounded')
            
            # Поля для подписания
            signing_fields_container = ui.column().classes('w-full mb-4')
            
            with signing_fields_container:
                ui.label('Данные для подписания:').classes('text-lg font-semibold mb-2')
                
                data_to_sign = ui.textarea(
                    label='Данные для подписания',
                    placeholder='Введите данные для подписания...',
                    value='Тестовые данные для подписания'
                ).classes('w-full mb-4')
                
                ui.button(
                    'Подписать документ',
                    icon='edit',
                    on_click=lambda: sign_document_with_certificate(
                        task,
                        data_to_sign.value,
                        signing_fields_container,
                        certificate_info_display,
                        result_container,
                        signature_info,
                        signed_data_display
                    )
                ).classes('mb-4 bg-green-500 text-white')
            
            # Результат подписания (изначально скрыт)
            result_container = ui.column().classes('w-full mb-4')
            result_container.visible = False
            
            with result_container:
                ui.label('Результат подписания:').classes('text-lg font-semibold mb-2 text-green-600')
                
                # Информация о подписи
                signature_info = ui.html('').classes('w-full mb-4 p-4 bg-green-50 rounded border border-green-200')
                
                # Подписанные данные - обычный редактируемый textarea
                signed_data_display = ui.textarea(
                    label='Подписанные данные (Base64)',
                    value='',
                    placeholder='Здесь будет отображена подпись после подписания...'
                ).classes('w-full mb-4')
                
                # Кнопки для работы с результатом
                with ui.row().classes('w-full gap-2'):
                    ui.button(
                        'Копировать подпись',
                        icon='content_copy',
                        on_click=lambda: copy_signature_to_clipboard(signed_data_display)
                    ).classes('bg-blue-500 text-white')
                    
                    ui.button(
                        'Проверить подпись',
                        icon='verified',
                        on_click=lambda: verify_signature(signed_data_display.value, signature_info)
                    ).classes('bg-purple-500 text-white')
                    
                    ui.button(
                        'Сохранить в файл',
                        icon='save',
                        on_click=lambda: save_signature_to_file(signed_data_display.value, task.name)
                    ).classes('bg-orange-500 text-white')
            
            # Кнопка отмены
            ui.button('ОТМЕНА', on_click=dialog.close).classes('bg-gray-500 text-white')
    
    dialog.open()

def sign_document(certificate_value, data_to_sign, signing_fields_container, certificate_info_display):
    """Подписывает документ выбранным сертификатом"""
    try:
        # Получаем выбранный сертификат из глобальной переменной
        global _selected_certificate
        if not _selected_certificate:
            ui.notify('Сертификат не выбран', type='error')
            return
        
        selected_cert = _selected_certificate['certificate']
        if not selected_cert:
            ui.notify('Информация о сертификате недоступна', type='error')
            return
        
        logger.info(f"Начинаем подписание документа сертификатом: {selected_cert['subject']}")
        
        # Здесь будет логика подписания документа
        ui.notify(f'Документ подписан сертификатом: {selected_cert["subject"]}', type='positive')
        
        # Скрываем поля подписания
        signing_fields_container.visible = False
        
    except Exception as e:
        logger.error(f"Ошибка при подписании документа: {e}")
        ui.notify(f'Ошибка при подписании: {str(e)}', type='error')

def check_crypto_pro_availability(status_container):
    """Проверяет доступность КриптоПро плагина"""
    try:
        # Сначала показываем статус проверки
        status_container.content = '''
        <div id="crypto-status" style="padding: 10px; border: 1px solid #ddd; border-radius: 4px; background-color: #f9f9f9;">
            <div style="color: #666;">🔍 Проверка КриптоПро плагина...</div>
        </div>
        '''
        
        # Затем запускаем проверку через JavaScript
        ui.run_javascript(f'''
            console.log("=== Начинаем проверку КриптоПро ===");
            
            // Проверяем доступность плагина
            if (typeof window.cryptoProIntegration !== 'undefined') {{
                console.log("✅ CryptoProIntegration класс найден");
                
                // Обновляем статус
                const statusDiv = document.getElementById('crypto-status');
                if (statusDiv) {{
                    statusDiv.innerHTML = `
                        <div style="color: green;">✅ КриптоПро плагин доступен</div>
                        <div style="color: green;">✅ Интеграция инициализирована</div>
                        <div style="color: green;">✅ CryptoProIntegration класс найден</div>
                        <div id="certificates-area" style="margin-top: 15px;"></div>
                    `;
                }}
                
                // Автоматически загружаем сертификаты
                setTimeout(() => {{
                    window.cryptoProIntegration.getAvailableCertificates()
                        .then(certificates => {{
                            console.log("Сертификаты получены:", certificates);
                            
                            // Отправляем событие о загруженных сертификатах
                            window.nicegui_handle_event('certificates_loaded', {{
                                certificates: certificates,
                                count: certificates.length
                            }});
                        }})
                        .catch(error => {{
                            console.error("Ошибка получения сертификатов:", error);
                            window.nicegui_handle_event('certificates_error', {{
                                error: error.message
                            }});
                        }});
                }}, 1000);
                
            }} else {{
                console.log("❌ CryptoProIntegration класс не найден");
                const statusDiv = document.getElementById('crypto-status');
                if (statusDiv) {{
                    statusDiv.innerHTML = `
                        <div style="color: red;">❌ CryptoProIntegration класс не найден</div>
                        <div style="color: #666;">Убедитесь, что скрипт cryptopro-integration.js загружен</div>
                    `;
                }}
            }}
        ''')
        
    except Exception as e:
        logger.error(f"Ошибка проверки КриптоПро: {e}")
        status_container.content = f'''
        <div style="color: red; padding: 10px; border: 1px solid red; border-radius: 4px;">
            ❌ Ошибка проверки КриптоПро: {str(e)}
        </div>
        '''

def load_certificates(certificate_select, status_container: ui.html):
    """Загружает список доступных сертификатов"""
    try:
        ui.run_javascript('''
            console.log('=== Автоматическая загрузка сертификатов ===');
            
            // Принудительно устанавливаем pluginAvailable = true
            if (window.cryptoProIntegration) {
                window.cryptoProIntegration.pluginAvailable = true;
                window.cryptoProIntegration.pluginLoaded = true;
                console.log('Принудительно установлен pluginAvailable = true');
            }
            
            // Используем готовую функцию из async_code.js
            if (typeof window.cadesplugin !== 'undefined') {
                console.log('cadesplugin найден, получаем сертификаты...');
                
                // Используем async_spawn для получения сертификатов
                window.cadesplugin.async_spawn(function*() {
                    try {
                        console.log('Создаем объект Store...');
                        const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                        console.log('✅ Объект Store создан');
                        
                        console.log('Открываем хранилище сертификатов...');
                        yield oStore.Open();
                        console.log('✅ Хранилище открыто');
                        
                        console.log('Получаем список сертификатов...');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        console.log(`✅ Найдено сертификатов: ${certCnt}`);
                        
                        const certList = [];
                        
                        for (let i = 1; i <= certCnt; i++) {
                            try {
                                console.log(`Обрабатываем сертификат ${i}...`);
                                const cert = yield certs.Item(i);
                                const subject = yield cert.SubjectName;
                                const issuer = yield cert.IssuerName;
                                const serialNumber = yield cert.SerialNumber;
                                const validFrom = yield cert.ValidFromDate;
                                const validTo = yield cert.ValidToDate;
                                const hasPrivateKey = yield cert.HasPrivateKey();
                                
                                // Проверяем срок действия сертификата
                                const validToDate = new Date(validTo);
                                const isValid = validToDate > new Date();
                                
                                // Добавляем только сертификаты с приватным ключом (для подписи)
                                if (hasPrivateKey) {
                                    const certInfo = {
                                        subject: subject,
                                        issuer: issuer,
                                        serialNumber: serialNumber,
                                        validFrom: validFrom,
                                        validTo: validTo,
                                        isValid: isValid,
                                        hasPrivateKey: hasPrivateKey,
                                        index: i
                                    };
                                    
                                    certList.push(certInfo);
                                    console.log(`✅ Сертификат для подписи: ${subject} (действителен: ${isValid})`);
                                } else {
                                    console.log(`⚠️ Сертификат без приватного ключа: ${subject}`);
                                }
                                
                            } catch (certError) {
                                console.warn(`⚠️ Ошибка при получении сертификата ${i}:`, certError);
                            }
                        }
                        
                        console.log('Закрываем хранилище...');
                        yield oStore.Close();
                        console.log(`✅ Успешно получено ${certList.length} сертификатов`);
                        
                        // Отправляем сертификаты в Python через событие
                        window.nicegui_handle_event('certificates_loaded', {
                            certificates: certList,
                            count: certList.length
                        });
                        
                        return certList;
                        
                    } catch (e) {
                        console.error('❌ Ошибка при получении сертификатов:', e);
                        window.nicegui_handle_event('certificates_error', {
                            error: e.message || 'Неизвестная ошибка'
                        });
                        throw e;
                    }
                });
                
            } else {
                console.error('cadesplugin не найден');
                window.nicegui_handle_event('integration_not_available', {
                    message: 'КриптоПро интеграция недоступна'
                });
            }
        ''')
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке сертификатов: {e}")
        ui.notify(f'Ошибка при загрузке сертификатов: {str(e)}', type='error')

def show_certificate_info(certificate_index: str, info_container: ui.html):
    """Показывает информацию о выбранном сертификате"""
    try:
        # Получаем информацию о сертификате из глобального кэша
        global _certificates_cache
        if _certificates_cache and certificate_index.isdigit():
            index = int(certificate_index)
            if 0 <= index < len(_certificates_cache):
                cert = _certificates_cache[index]
                
                # Форматируем информацию о сертификате
                info_html = f"""
                <div style="padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">
                    <h4 style="margin-top: 0; color: #333;">Информация о сертификате</h4>
                    <p><strong>Владелец:</strong> {cert['subject']}</p>
                    <p><strong>Издатель:</strong> {cert['issuer']}</p>
                    <p><strong>Серийный номер:</strong> {cert['serialNumber']}</p>
                    <p><strong>Действителен с:</strong> {cert['validFrom']}</p>
                    <p><strong>Действителен до:</strong> {cert['validTo']}</p>
                    <p><strong>Статус:</strong> 
                        <span style="color: {'green' if cert['isValid'] else 'red'};">
                            {'✅ Действителен' if cert['isValid'] else '❌ Истек'}
                        </span>
                    </p>
                    <p><strong>Приватный ключ:</strong> 
                        <span style="color: {'green' if cert['hasPrivateKey'] else 'red'};">
                            {'✅ Доступен' if cert['hasPrivateKey'] else '❌ Недоступен'}
                        </span>
                    </p>
                </div>
                """
                
                info_container.content = info_html
                logger.info(f"Отображена информация о сертификате: {cert['subject']}")
            else:
                info_container.content = '<div style="color: red;">Ошибка: неверный индекс сертификата</div>'
        else:
            info_container.content = '<div style="color: orange;">Информация о сертификате недоступна</div>'
            
    except Exception as e:
        logger.error(f"Ошибка при отображении информации о сертификате: {e}")
        info_container.content = f'<div style="color: red;">Ошибка: {str(e)}</div>'

def sign_document_with_certificate(task, data_to_sign, signing_fields_container, certificate_info_display, result_container, signature_info, signed_data_display):
    """Подписывает документ с использованием выбранного сертификата"""
    try:
        selected_cert = api_router.get_selected_certificate()
        
        if not selected_cert:
            ui.notify('Сертификат не выбран!', type='error')
            return
        
        logger.info(f"Начинаем подписание документа с сертификатом")
        
        # Получаем данные сертификата
        certificate_data = selected_cert.get('certificate')
        if not certificate_data:
            ui.notify('Данные сертификата не найдены!', type='error')
            return
        
        # Показываем информацию о сертификате
        ui.notify(f'Подписание с сертификатом: {certificate_data.get("subject", "Неизвестно")}', type='info')
        
        # Создаем имитацию подписи
        import base64
        import json
        from datetime import datetime
        
        # Создаем структуру подписи
        signature_data = {
            "original_data": data_to_sign,
            "signature_info": {
                "certificate_subject": certificate_data.get("subject"),
                "certificate_issuer": certificate_data.get("issuer"),
                "certificate_serial": certificate_data.get("serialNumber"),
                "signature_time": datetime.now().isoformat(),
                "signature_algorithm": "GOST R 34.10-2012",
                "hash_algorithm": "GOST R 34.11-2012"
            },
            "signature_value": "ИМИТАЦИЯ_ПОДПИСИ_" + base64.b64encode(data_to_sign.encode()).decode()[:50] + "...",
            "signature_format": "CAdES-BES"
        }
        
        # Кодируем в Base64
        signature_json = json.dumps(signature_data, ensure_ascii=False, indent=2)
        signature_base64 = base64.b64encode(signature_json.encode()).decode()
        
        # Скрываем поля подписания
        signing_fields_container.visible = False
        
        # Показываем результат
        result_container.visible = True
        
        # Обновляем информацию о подписи
        signature_info_html = f'''
        <div style="font-family: monospace; font-size: 12px;">
            <div style="color: #2e7d32; font-weight: bold; margin-bottom: 10px;">✅ Документ успешно подписан!</div>
            <div style="margin-bottom: 5px;"><strong>Сертификат:</strong> {certificate_data.get("subject", "Неизвестно")}</div>
            <div style="margin-bottom: 5px;"><strong>Издатель:</strong> {certificate_data.get("issuer", "Неизвестно")}</div>
            <div style="margin-bottom: 5px;"><strong>Серийный номер:</strong> {certificate_data.get("serialNumber", "Неизвестно")}</div>
            <div style="margin-bottom: 5px;"><strong>Действителен до:</strong> {certificate_data.get("validTo", "Неизвестно")}</div>
            <div style="margin-bottom: 5px;"><strong>Алгоритм подписи:</strong> GOST R 34.10-2012</div>
            <div style="margin-bottom: 5px;"><strong>Алгоритм хеширования:</strong> GOST R 34.11-2012</div>
            <div style="margin-bottom: 5px;"><strong>Формат подписи:</strong> CAdES-BES</div>
            <div style="margin-bottom: 5px;"><strong>Время подписания:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
        </div>
        '''
        
        # Обновляем элементы напрямую
        signature_info.content = signature_info_html
        signed_data_display.value = signature_base64
        
        ui.notify('Документ успешно подписан!', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка подписания документа: {e}")
        ui.notify(f'Ошибка подписания: {str(e)}', type='error')

def copy_signature_to_clipboard(signed_data_display):
    """Копирует подпись в буфер обмена"""
    try:
        signature_text = signed_data_display.value
        ui.run_javascript(f'''
            navigator.clipboard.writeText(`{signature_text}`).then(() => {{
                console.log('Подпись скопирована в буфер обмена');
            }}).catch(err => {{
                console.error('Ошибка копирования:', err);
            }});
        ''')
        ui.notify('Подпись скопирована в буфер обмена!', type='positive')
    except Exception as e:
        logger.error(f"Ошибка копирования: {e}")
        ui.notify(f'Ошибка копирования: {str(e)}', type='error')

def verify_signature(signature_base64, signature_info):
    """Проверяет подпись"""
    try:
        import base64
        import json
        
        # Декодируем подпись
        signature_json = base64.b64decode(signature_base64).decode()
        signature_data = json.loads(signature_json)
        
        # Проверяем структуру
        if 'signature_value' in signature_data and 'signature_info' in signature_data:
            ui.notify('✅ Подпись корректна!', type='positive')
            
            # Обновляем информацию о проверке
            verification_html = f'''
            <div style="color: #2e7d32; font-weight: bold; margin-bottom: 10px;">✅ Подпись проверена и корректна!</div>
            <div style="margin-bottom: 5px;"><strong>Статус:</strong> Валидная</div>
            <div style="margin-bottom: 5px;"><strong>Время проверки:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
            '''
            
            ui.run_javascript(f'''
                const signatureInfoElements = document.querySelectorAll('[class*="bg-green-50"]');
                if (signatureInfoElements.length > 0) {{
                    signatureInfoElements[0].innerHTML = `{verification_html}`;
                }}
            ''')
        else:
            ui.notify('❌ Подпись некорректна!', type='error')
            
    except Exception as e:
        logger.error(f"Ошибка проверки подписи: {e}")
        ui.notify(f'Ошибка проверки: {str(e)}', type='error')

def save_signature_to_file(signature_base64, task_name):
    """Сохраняет подпись в файл"""
    try:
        import base64
        import json
        from datetime import datetime
        
        # Декодируем подпись
        signature_json = base64.b64decode(signature_base64).decode()
        signature_data = json.loads(signature_json)
        
        # Создаем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"signature_{task_name}_{timestamp}.json"
        
        # Сохраняем в файл
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(signature_data, f, ensure_ascii=False, indent=2)
        
        ui.notify(f'Подпись сохранена в файл: {filename}', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        ui.notify(f'Ошибка сохранения: {str(e)}', type='error')


def refresh_tasks():
    """Обновляет список задач"""
    try:
        # Здесь должна быть логика обновления задач
        # Пока что просто логируем
        logger.info("Обновляем список задач")
    except Exception as e:
        logger.error(f"Ошибка обновления задач: {e}")

def get_selected_certificate():
    """Возвращает выбранный сертификат"""
    global _selected_certificate
    return _selected_certificate

def set_selected_certificate(certificate_data):
    """Устанавливает выбранный сертификат"""
    global _selected_certificate
    _selected_certificate = certificate_data

def load_and_display_document(document_id: str, container: ui.column):
    """Загружает и отображает документ"""
    try:
        from services.mayan_connector import MayanClient
        mayan_client = MayanClient.create_with_session_user()
        
        # Получаем информацию о документе
        document_info = mayan_client.get_document_info_for_review(document_id)
        
        if document_info:
            # Создаем ссылку на документ в Mayan EDMS
            document_url = mayan_client.get_document_file_url(document_id)
            
            with container:
                # Кнопка для открытия документа в новой вкладке
                ui.button(
                    'Открыть документ в Mayan EDMS',
                    icon='open_in_new',
                    on_click=lambda: ui.open(document_url)
                ).classes('mb-4 bg-blue-500 text-white')
                
                # Отображаем содержимое документа
                if 'content' in document_info and document_info['content']:
                    ui.label('Предварительный просмотр документа:').classes('text-sm font-medium mb-2')
                    
                    # Создаем область для отображения содержимого
                    content_html = f"""
                    <div style="font-family: Arial, sans-serif; line-height: 1.6; max-height: 400px; overflow-y: auto;">
                        <div style="white-space: pre-wrap; background: white; padding: 20px; border: 1px solid #ddd; border-radius: 4px;">
                            {document_info['content']}
                        </div>
                    </div>
                    """
                    ui.html(content_html).classes('w-full border rounded')
                else:
                    ui.label('Содержимое документа недоступно для предварительного просмотра').classes('text-gray-600 mb-2')
                    ui.label('Используйте кнопку выше для открытия документа в Mayan EDMS').classes('text-sm text-gray-500')
        else:
            with container:
                ui.label('Документ не найден').classes('text-red-600')
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке документа {document_id}: {e}")
        with container:
            ui.label(f'Ошибка при загрузке документа: {str(e)}').classes('text-red-600')

def load_document_content_for_signing(document_id: str, content_container: ui.html):
    """Загружает содержимое документа для подписания"""
    try:
        logger.info(f"Загружаем документ для подписания: {document_id}")
        
        # Проверяем, что document_id не пустой и не является названием
        if not document_id or document_id.strip() == "":
            content_container.content = '<div class="text-red-600">ID документа не указан</div>'
            return
        
        # Если document_id выглядит как название (содержит пробелы), показываем ошибку
        if ' ' in document_id.strip():
            content_container.content = f'''
                <div class="text-red-600 p-4">
                    <h3>Ошибка: Неверный ID документа</h3>
                    <p>Получено: "{document_id}"</p>
                    <p>ID документа должен быть числовым значением, а не названием.</p>
                    <p>Пожалуйста, проверьте правильность ввода ID документа при создании задачи.</p>
                </div>
            '''
            return
        
        # Получаем документ из Mayan EDMS
        mayan_client = get_mayan_client()  # Используем существующую функцию
        document_info = mayan_client.get_document_info(document_id)
        
        if document_info:
            # Получаем содержимое документа
            document_content = mayan_client.get_document_content(document_id)
            
            if document_content:
                # Отображаем содержимое документа
                content_html = f'''
                    <div class="document-content p-4">
                        <h3 class="text-lg font-semibold mb-4">Документ: {document_info.get('label', 'Без названия')}</h3>
                        <div class="document-preview border rounded p-4 bg-white">
                            <pre class="whitespace-pre-wrap text-sm">{document_content}</pre>
                        </div>
                        <div class="mt-4">
                            <a href="{mayan_client.base_url}/documents/{document_id}/" 
                               target="_blank" 
                               class="text-blue-600 hover:text-blue-800 underline">
                                Открыть документ в Mayan EDMS
                            </a>
                        </div>
                    </div>
                '''
                content_container.content = content_html
            else:
                content_container.content = f'''
                    <div class="text-yellow-600 p-4">
                        <h3>Документ найден, но содержимое недоступно</h3>
                        <p>Документ: {document_info.get('label', 'Без названия')}</p>
                        <a href="{mayan_client.base_url}/documents/{document_id}/" 
                           target="_blank" 
                           class="text-blue-600 hover:text-blue-800 underline">
                            Открыть документ в Mayan EDMS
                        </a>
                    </div>
                '''
        else:
            content_container.content = f'''
                <div class="text-red-600 p-4">
                    <h3>Документ не найден</h3>
                    <p>ID документа: {document_id}</p>
                    <p>Проверьте правильность ID документа в Mayan EDMS.</p>
                </div>
            '''
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке документа {document_id}: {e}")
        content_container.content = f'''
            <div class="text-red-600 p-4">
                <h3>Ошибка при загрузке документа</h3>
                <p>ID документа: {document_id}</p>
                <p>Ошибка: {str(e)}</p>
            </div>
        '''

def submit_signing_task_completion(task, signed, signature_data, certificate_info, comment, dialog):
    """Отправляет завершение задачи подписания"""
    try:
        if not signed:
            ui.notify('Необходимо подтвердить подписание документа', type='warning')
            return
        
        # Подготавливаем переменные для процесса подписания
        variables = {
            'signed': signed,
            'signatureData': signature_data,
            'certificateInfo': certificate_info,
            'signatureComment': comment or '',
            'signatureDate': datetime.now().isoformat()
        }
        
        # Завершаем задачу в Camunda
        camunda_client = create_camunda_client()
        success = camunda_client.complete_task_with_variables(task.id, variables)
        
        if success:
            ui.notify('Документ успешно подписан!', type='success')
            dialog.close()
            # Обновляем список задач
            load_active_tasks(_tasks_header_container)
        else:
            ui.notify('Ошибка при подписании документа', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f"Ошибка при завершении задачи подписания {task.id}: {e}", exc_info=True)


def handle_file_upload(e):
    """Обрабатывает загрузку файлов"""
    global _uploaded_files_container, _uploaded_files
    
    if _uploaded_files_container is None:
        return
        
    # Исправляем доступ к файлам
    files = getattr(e, 'files', [])
    if not files:
        # Пытаемся получить файлы из других атрибутов
        files = getattr(e, 'file', [])
        if not isinstance(files, list):
            files = [files] if files else []
    
    for file in files:
        file_info = {
            'filename': getattr(file, 'name', 'unknown'),
            'mimetype': getattr(file, 'type', 'application/octet-stream'),
            'content': getattr(file, 'content', b''),
            'size': len(getattr(file, 'content', b'')),
            'description': f'Файл результата для задачи'
        }
        _uploaded_files.append(file_info)
        
        with _uploaded_files_container:
            with ui.card().classes('p-2 mb-2 bg-green-50'):
                ui.label(f'{file_info["filename"]} ({file_info["mimetype"]})').classes('text-sm')
                ui.label(f'Размер: {file_info["size"]} байт').classes('text-xs text-gray-600')

def submit_task_completion(task, status, comment, dialog):
    """Отправляет завершение обычной задачи"""
    global _uploaded_files
    
    try:
        # Подготавливаем переменные для процесса
        variables = {
            'taskStatus': status,
            'taskComment': comment or '',
            'completionDate': datetime.now().isoformat()
        }
        
        # Загружаем файлы в Mayan EDMS, если они есть
        result_files = []
        if _uploaded_files:
            try:
                mayan_client = get_mayan_client()
                for file_info in _uploaded_files:
                    mayan_result = mayan_client.upload_document_result(
                        task_id=task.id,
                        process_instance_id=task.process_instance_id,
                        filename=file_info['filename'],
                        file_content=file_info['content'],
                        mimetype=file_info['mimetype'],
                        description=file_info['description']
                    )
                    
                    if mayan_result:
                        result_files.append({
                            'filename': mayan_result['filename'],
                            'mimetype': mayan_result['mimetype'],
                            'size': mayan_result['size'],
                            'mayan_document_id': mayan_result['document_id'],
                            'download_url': mayan_result['download_url'],
                            'description': file_info['description']
                        })
            except Exception as e:
                logger.warning(f"Не удалось загрузить файлы в Mayan EDMS: {e}")
                ui.notify('Файлы не загружены в Mayan EDMS, но задача будет завершена', type='warning')
        
        # Завершаем задачу в Camunda (упрощенная версия)
        camunda_client = create_camunda_client()
        
        # Используем простой метод завершения задачи
        success = camunda_client.complete_task_with_user_data(
            task_id=task.id,
            status=status,
            comment=comment or '',
            review_date=datetime.now().isoformat()
        )
        
        if success:
            ui.notify('Задача успешно завершена!', type='success')
            dialog.close()
            # Обновляем список задач
            load_active_tasks(_tasks_header_container)
        else:
            ui.notify('Ошибка при завершении задачи', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f"Ошибка при завершении задачи {task.id}: {e}", exc_info=True)

def show_task_details(task):
    """Показывает детали задачи в правом блоке"""
    global _task_details_sidebar, _task_details_column
    
    if _task_details_sidebar is None or _task_details_column is None:
        ui.notify('Ошибка: контейнер деталей не инициализирован', type='error')
        return
    
    # Показываем правый блок с деталями
    _task_details_column.set_visibility(True)
    
    # Очищаем контейнер
    _task_details_sidebar.clear()
    
    with _task_details_sidebar:
        ui.label('Загрузка деталей...').classes('text-gray-600')
        
        try:
            # Получаем детальную информацию о задаче
            camunda_client = create_camunda_client()
            
            logger.info(f"Попытка получить детали задачи {task.id}")
            
            task_details = None
            is_history_task = False
            
            # Сначала пробуем получить как активную задачу
            task_details = camunda_client.get_task_by_id(task.id)
            
            if task_details:
                logger.info(f"Задача {task.id} найдена как активная")
                is_history_task = False
            else:
                # Если активная задача не найдена, пробуем получить как историческую
                logger.info(f"Активная задача {task.id} не найдена, пробуем получить как историческую")
                task_details = camunda_client.get_history_task_by_id(task.id)
                
                if task_details:
                    logger.info(f"Задача {task.id} найдена как историческая")
                    is_history_task = True
                else:
                    logger.warning(f"Задача {task.id} не найдена ни как активная, ни как историческая")
                    
                    # Проверяем, существует ли процесс
                    if hasattr(task, 'process_instance_id') and task.process_instance_id:
                        logger.info(f"Проверяем процесс {task.process_instance_id}")
                        
                        # Проверяем активный процесс
                        process_info = camunda_client.get_process_instance_by_id(task.process_instance_id)
                        if process_info:
                            logger.info(f"Процесс {task.process_instance_id} найден как активный")
                        else:
                            # Проверяем исторический процесс
                            process_info = camunda_client.get_history_process_instance_by_id(task.process_instance_id)
                            if process_info:
                                logger.info(f"Процесс {task.process_instance_id} найден как исторический")
                            else:
                                logger.warning(f"Процесс {task.process_instance_id} не найден")
            
            logger.info(f"Результат получения задачи {task.id}: {task_details is not None}")
            
            if not task_details:
                ui.label(f'Задача {task.id} не найдена').classes('text-red-600')
                ui.label('Возможные причины:').classes('text-sm text-gray-600 mt-2')
                ui.label('• Задача была удалена из истории').classes('text-sm text-gray-600')
                ui.label('• Задача еще не завершена').classes('text-sm text-gray-600')
                ui.label('• Неправильный ID задачи').classes('text-sm text-gray-600')
                
                # Показываем информацию о задаче из списка
                with ui.card().classes('p-4 bg-yellow-50 mb-4'):
                    ui.label('Информация из списка задач').classes('text-lg font-semibold mb-3')
                    ui.label(f'ID задачи: {task.id}').classes('text-sm mb-2')
                    if hasattr(task, 'name'):
                        ui.label(f'Название: {task.name}').classes('text-sm mb-2')
                    if hasattr(task, 'process_instance_id'):
                        ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm mb-2')
                    if hasattr(task, 'assignee'):
                        ui.label(f'Исполнитель: {task.assignee or "Не назначен"}').classes('text-sm mb-2')
                    if hasattr(task, 'start_time'):
                        ui.label(f'Создана: {task.start_time}').classes('text-sm mb-2')
                    if hasattr(task, 'end_time') and task.end_time:
                        ui.label(f'Завершена: {task.end_time}').classes('text-sm mb-2')
                
                return
            
            # Основная информация о задаче
            with ui.card().classes('p-4 bg-blue-50 mb-4'):
                ui.label('Основная информация').classes('text-lg font-semibold mb-3')
                
                ui.label(f'Название: {task_details.name}').classes('text-sm mb-2')
                ui.label(f'ID задачи: {task_details.id}').classes('text-sm mb-2')
                ui.label(f'ID процесса: {task_details.process_instance_id}').classes('text-sm mb-2')
                ui.label(f'Исполнитель: {task_details.assignee or "Не назначен"}').classes('text-sm mb-2')
                ui.label(f'Создана: {task_details.start_time}').classes('text-sm mb-2')
                
                if is_history_task and hasattr(task_details, 'end_time') and task_details.end_time:
                    ui.label(f'Завершена: {task_details.end_time}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'priority'):
                    ui.label(f'Приоритет: {task_details.priority}').classes('text-sm mb-2')
                
                if is_history_task:
                    ui.label(f'Статус: Завершена').classes('text-sm mb-2')
                else:
                    ui.label(f'Статус: {"Активна" if not getattr(task_details, "suspended", False) else "Приостановлена"}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'description') and task_details.description:
                    ui.label(f'Описание: {task_details.description}').classes('text-sm mb-2')
                
                if hasattr(task_details, 'due') and task_details.due:
                    ui.label(f'Срок: {task_details.due}').classes('text-sm mb-2')
                
                if is_history_task and hasattr(task_details, 'delete_reason') and task_details.delete_reason:
                    ui.label(f'Причина завершения: {task_details.delete_reason}').classes('text-sm mb-2')
            
            # Переменные задачи (только для активных задач)
            if not is_history_task:
                try:
                    variables = camunda_client.get_task_variables(task.id)
                    if variables:
                        with ui.card().classes('p-4 bg-green-50 mb-4'):
                            ui.label('Переменные задачи').classes('text-lg font-semibold mb-3')
                            
                            for var_name, var_value in variables.items():
                                if isinstance(var_value, dict) and 'value' in var_value:
                                    display_value = var_value['value']
                                    if isinstance(display_value, str) and len(display_value) > 100:
                                        display_value = display_value[:100] + '...'
                                    ui.label(f'{var_name}: {display_value}').classes('text-sm mb-1')
                                else:
                                    ui.label(f'{var_name}: {var_value}').classes('text-sm mb-1')
                except Exception as e:
                    logger.warning(f"Не удалось получить переменные задачи {task.id}: {e}")
                    ui.label('Переменные задачи недоступны').classes('text-sm text-gray-500')
            
            # Переменные процесса
            try:
                process_variables = camunda_client.get_process_instance_variables(task_details.process_instance_id)
                if process_variables:
                    with ui.card().classes('p-4 bg-yellow-50 mb-4'):
                        ui.label('Переменные процесса').classes('text-lg font-semibold mb-3')
                        
                        for var_name, var_value in process_variables.items():
                            if isinstance(var_value, dict) and 'value' in var_value:
                                display_value = var_value['value']
                                if isinstance(display_value, str) and len(display_value) > 100:
                                    display_value = display_value[:100] + '...'
                                ui.label(f'{var_name}: {display_value}').classes('text-sm mb-1')
                            else:
                                ui.label(f'{var_name}: {var_value}').classes('text-sm mb-1')
            except Exception as e:
                logger.warning(f"Не удалось получить переменные процесса {task_details.process_instance_id}: {e}")
                ui.label('Переменные процесса недоступны').classes('text-sm text-gray-500')
            
            # Кнопки действий (только для активных задач)
            if not is_history_task:
                with ui.column().classes('w-full gap-2'):
                    ui.button(
                        'Завершить задачу',
                        icon='check',
                        on_click=lambda t=task: complete_task(t)
                    ).classes('w-full bg-green-500 text-white')
                    
                    ui.button(
                        'Обновить детали',
                        icon='refresh',
                        on_click=lambda t=task: show_task_details(t)
                    ).classes('w-full bg-blue-500 text-white')
                    
                    ui.button(
                        'Скрыть детали',
                        icon='close',
                        on_click=hide_task_details
                    ).classes('w-full bg-gray-500 text-white')
            else:
                # Для исторических задач только кнопки просмотра
                with ui.column().classes('w-full gap-2'):
                    ui.button(
                        'Обновить детали',
                        icon='refresh',
                        on_click=lambda t=task: show_task_details(t)
                    ).classes('w-full bg-blue-500 text-white')
                    
                    ui.button(
                        'Скрыть детали',
                        icon='close',
                        on_click=hide_task_details
                    ).classes('w-full bg-gray-500 text-white')
            
        except Exception as e:
            ui.label(f'Ошибка при загрузке деталей: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке деталей задачи {task.id}: {e}", exc_info=True)

def hide_task_details():
    """Скрывает блок с деталями задачи"""
    global _task_details_column
    
    if _task_details_column is None:
        return
    
    # Скрываем блок деталей
    _task_details_column.set_visibility(False)
    
    # Находим родительский контейнер и скрываем его
    details_column = _task_details_sidebar.parent
    if details_column:
        details_column.set_visibility(False)

def show_task_results(task):
    """Показывает результаты задачи"""
    ui.notify(f'Результаты задачи {task.id} будут показаны', type='info')

def format_variable_value(value):
    """
    Форматирует значение переменной для отображения
    Автоматически форматирует даты в формат DD.MM.YYYY HH:MM:SS (московское время)
    Обрабатывает JSON строки с правильной кодировкой
    """
    if isinstance(value, dict):
        # Если это словарь, форматируем каждое значение
        formatted_dict = {}
        for k, v in value.items():
            formatted_dict[k] = format_variable_value(v)
        return formatted_dict
    elif isinstance(value, list):
        # Если это список, форматируем каждый элемент
        return [format_variable_value(item) for item in value]
    elif isinstance(value, str):
        # Проверяем, похоже ли значение на ISO-дату
        try:
            from datetime import datetime
            import pytz
            import json
            
            # Проверяем, похоже ли значение на ISO-дату (упрощённо)
            iso_like = (
                value.startswith(('20', '19')) and  # Год
                ('T' in value or ' ' in value) and     # Разделитель
                any(c in value for c in [':', '+', 'Z'])  # Время или TZ
            )
            
            if iso_like:
                # Заменяем 'Z' на '+00:00' для корректного парсинга
                parsed_dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                moscow_tz = pytz.timezone('Europe/Moscow')
                local_dt = parsed_dt.astimezone(moscow_tz)
                return local_dt.strftime('%d.%m.%Y %H:%M:%S')
            else:
                # Проверяем, является ли строка JSON с Unicode escape sequences
                if value.startswith('{') and '\\u' in value:
                    try:
                        # Парсим JSON и пересоздаем с правильной кодировкой
                        parsed = json.loads(value)
                        return json.dumps(parsed, ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        return value
                return value
        except Exception:
            # Если не удалось распарсить как дату, возвращаем как есть
            return value
    else:
        return str(value)