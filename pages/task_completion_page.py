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
    """Отправляет завершение задачи"""
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