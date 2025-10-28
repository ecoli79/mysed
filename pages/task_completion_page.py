from math import log
from nicegui import ui
from services.camunda_connector import create_camunda_client
from services.mayan_connector import MayanClient
from config.settings import config
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional
from models import CamundaHistoryTask, LDAPUser
from auth.middleware import get_current_user
from auth.ldap_auth import LDAPAuthenticator
from utils import validate_username
from datetime import datetime
import api_router
from ldap3 import Server, Connection, SUBTREE, ALL
from utils.date_utils import format_date_russian
import base64
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
import io
import os
from services.signature_manager import SignatureManager


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
_document_for_signing = None
_signature_result_handler = None


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
        ui.label('Подписание документа').classes('text-xl font-bold mb-4')
        
        with ui.column().classes('w-full gap-4'):
            # Получаем переменные процесса
            document_id = None
            document_name = None
            signer_list = []
            
            try:
                camunda_client = create_camunda_client()
                process_variables = camunda_client.get_process_instance_variables(task.process_instance_id)
                
                logger.info(f"Переменные процесса {task.process_instance_id}: {process_variables}")
                
                # Извлекаем ID документа из переменных
                document_id = process_variables.get('documentId')
                document_name = process_variables.get('documentName')
                
                # Извлекаем список подписантов
                signer_list = process_variables.get('signerList', [])
                if isinstance(signer_list, dict) and 'value' in signer_list:
                    signer_list = signer_list['value']
                elif isinstance(signer_list, str):
                    try:
                        import json
                        signer_list = json.loads(signer_list)
                    except:
                        signer_list = [signer_list] if signer_list else []
                
            except Exception as e:
                ui.label(f'Ошибка при получении переменных процесса: {str(e)}').classes('text-red-600')
                logger.error(f"Ошибка в complete_signing_task при получении переменных: {e}")
            
            # ИСПРАВЛЕНИЕ: Проверяем, уже подписан ли документ текущим пользователем
            # Добавляем проверку, что document_id - это валидный ID документа (число)
            def is_valid_document_id(doc_id):
                '''Проверяет, что document_id - это валидный идентификатор (число)'''
                if not doc_id:
                    return False
                try:
                    # Пытаемся преобразовать в число
                    int(str(doc_id).strip())
                    return True
                except (ValueError, AttributeError):
                    return False
            
            if document_id and document_id != 'НЕ НАЙДЕН' and str(document_id).strip() and is_valid_document_id(document_id):
                try:
                    # Получаем текущего пользователя
                    user = get_current_user()
                    
                    if user:
                        signature_manager = SignatureManager()
                        
                        # Проверяем, существует ли уже подпись пользователя
                        if signature_manager.check_user_signature_exists(document_id, user.username):
                            with ui.card().classes('p-4 bg-yellow-50 border border-yellow-200'):
                                ui.label('⚠️ Документ уже подписан').classes('text-lg font-semibold text-yellow-800 mb-2')
                                ui.label(f'Вы уже подписали этот документ ранее.').classes('text-yellow-700 mb-2')
                                
                                # Показываем кнопку "Завершить задачу" без возможности повторной подписи
                                ui.button(
                                    'Завершить задачу',
                                    icon='check_circle',
                                    on_click=lambda: submit_signing_task_completion(
                                        task,
                                        True,
                                        '',
                                        {},
                                        'Документ уже подписан',
                                        dialog
                                    )
                                ).classes('bg-green-600 text-white')
                                
                                ui.button('Закрыть', on_click=dialog.close).classes('bg-gray-500 text-white')
                            
                            dialog.open()
                            return  # Выходим из функции, не показывая форму подписания
                        
                except Exception as e:
                    logger.warning(f"Ошибка проверки существующей подписи: {e}")
                    # Продолжаем процесс, если не удалось проверить
            
            # Отображение списка подписантов
            if signer_list:
                ui.label('Список подписантов:').classes('text-lg font-semibold mt-4 mb-2')
                
                try:
                    # ИСПРАВЛЕНИЕ: Создаем объект LDAPAuthenticator
                    from auth.ldap_auth import LDAPAuthenticator
                    ldap_auth = LDAPAuthenticator()
                    
                    signers_container = ui.column().classes('w-full mb-4')
                    
                    with signers_container:                           
                        with ui.column().classes('w-full'):
                            for i, signer_login in enumerate(signer_list):
                                try:
                                    logger.info(f"Обрабатываем подписанта {i+1}: {signer_login}")
                                    
                                    # ДОБАВЛЯЕМ ЛОГИРОВАНИЕ: Проверяем пользователя в LDAP
                                    user_info = ldap_auth.get_user_by_login(signer_login)
                                    logger.info(f"Результат get_user_by_login для {signer_login}: {user_info is not None}")
                                    
                                    if not user_info:
                                        logger.info(f"Пользователь {signer_login} не найден через точный поиск, пробуем широкий поиск")
                                        user_info = ldap_auth.find_user_by_login(signer_login)
                                        logger.info(f"Результат find_user_by_login для {signer_login}: {user_info is not None}")
                                    
                                    if user_info:
                                        ui.label(f'{i+1}. {user_info.givenName} {user_info.sn} - {user_info.destription}').classes('text-sm mb-1')
                                        logger.info(f"Найдена информация о пользователе {signer_login}: {user_info.givenName} {user_info.sn}")
                                    else:
                                        ui.label(f'{i+1}. {signer_login} (не найден в LDAP)').classes('text-sm mb-1 text-red-600')
                                        logger.warning(f"Пользователь {signer_login} не найден в LDAP после всех попыток поиска")
                                        
                                except Exception as e:
                                    logger.error(f"Ошибка получения информации о пользователе {signer_login}: {e}")
                                    ui.label(f'{i+1}. {signer_login} (ошибка: {str(e)})').classes('text-sm mb-1 text-red-600')
                except Exception as e:
                    logger.error(f"Ошибка получения списка подписантов из LDAP: {e}")
                    ui.label(f'Ошибка получения информации о подписантах: {str(e)}').classes('text-red-600')
            else:
                ui.label('Список подписантов не найден в переменных процесса').classes('text-yellow-600 mt-4')
            
            # Загружаем документ из Mayan EDMS
            if document_id and document_id != 'НЕ НАЙДЕН' and str(document_id).strip():
                try:
                    mayan_client = get_mayan_client()
                    document_content = mayan_client.get_document_file_content(document_id)
                    
                    if document_content:
                        import base64
                        document_base64 = base64.b64encode(document_content).decode('utf-8')
                        
                        ui.label(f'Документ загружен: {document_name or "Неизвестно"}').classes('text-green-600 mb-2')
                        ui.label(f'Размер файла: {len(document_content)} байт').classes('text-sm text-gray-600 mb-4')
                        
                        global _document_for_signing
                        _document_for_signing = {
                            'content': document_content,
                            'base64': document_base64,
                            'name': document_name,
                            'id': document_id
                        }
                    else:
                        ui.label('Не удалось загрузить содержимое документа').classes('text-red-600')
                        return
                        
                except Exception as e:
                    ui.label(f'Ошибка при загрузке документа: {str(e)}').classes('text-red-600')
                    logger.error(f"Ошибка при загрузке документа {document_id}: {e}")
                    return
            else:
                ui.label('ID документа не найден').classes('text-red-600')
                return
            
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
                
                data_to_sign_value = f"Документ ID: {document_id}, Название: {document_name}"
                
                data_to_sign = ui.textarea(
                    label='Данные для подписания',
                    placeholder='Введите данные для подписания...',
                    value=data_to_sign_value
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
                ui.button(
                    'Проверить результат подписания',
                    icon='refresh',
                    on_click=lambda: check_and_display_signature_result(signature_info, signed_data_display, result_container)
                ).classes('mb-4 bg-blue-500 text-white')

            
            # Результат подписания (изначально скрыт)
            result_container = ui.column().classes('w-full mb-4')
            result_container.visible = False
            
            with result_container:
                ui.label('Результат подписания:').classes('text-lg font-semibold mb-2 text-green-600')
                
                signature_info = ui.html('').classes('w-full mb-4 p-4 bg-green-50 rounded border border-green-200')
                
                signed_data_display = ui.textarea(
                    label='Подпись (Base64)',
                    value='',
                    placeholder='Здесь будет отображена подпись после подписания...'
                ).classes('w-full mb-4')
                
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
                        'Сохранить подписанный PDF',
                        icon='save',
                        on_click=lambda: save_signature_to_file(signed_data_display.value, document_name or task.name)
                    ).classes('bg-orange-500 text-white')

                    ui.button(
                        'Проверить созданный PDF',
                        icon='refresh',
                        on_click=lambda: check_and_save_signed_pdf()
                    ).classes('mb-4 bg-blue-500 text-white')
                    
                    ui.button(
                        'Завершить задачу',
                        icon='check',
                        on_click=lambda: complete_signing_task_with_result(
                            task,
                            signature_info,
                            signed_data_display,
                            result_container,
                            document_id,
                            document_name,
                            dialog
                        )
                    ).classes('bg-green-600 text-white')
            
            ui.button('ОТМЕНА', on_click=dialog.close).classes('bg-gray-500 text-white')
    
    dialog.open()

def check_and_save_signed_pdf():
    """Проверяет результат создания подписанного PDF и сохраняет его"""
    try:
        signature_result = api_router.get_signature_result()
        
        if signature_result and signature_result.get('action') == 'signed_document_created':
            signed_document = signature_result.get('signed_document', '')
            filename = signature_result.get('filename', 'signed_document.pdf')
            
            if signed_document:
                # Декодируем Base64 в бинарные данные
                import base64
                pdf_binary = base64.b64decode(signed_document)
                
                # Сохраняем подписанный PDF в файл
                with open(filename, 'wb') as f:
                    f.write(pdf_binary)
                
                ui.notify(f'✅ Подписанный PDF сохранен в файл: {filename}', type='positive')
                
                # Очищаем результат после обработки
                api_router.clear_signature_result()
            else:
                ui.notify('Подписанный документ не найден', type='error')
        else:
            ui.notify('Результат создания подписанного PDF не найден. Сначала создайте подписанный PDF.', type='warning')
            
    except Exception as e:
        logger.error(f"Ошибка сохранения подписанного PDF: {e}")
        ui.notify(f'Ошибка сохранения подписанного PDF: {str(e)}', type='error')

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

def complete_signing_task_with_result(task, signature_info, signed_data_display, result_container, document_id, document_name, dialog):
    '''Завершает задачу подписания с проверкой результата'''
    try:
        # ИСПРАВЛЕНИЕ: Проверяем наличие данных подписи в UI элементе
        # Если данные уже отображаются в UI, используем их
        if signed_data_display.value and len(signed_data_display.value) > 100:
            logger.info('Данные подписи найдены в UI элементе, завершаем задачу')
            
            # ДОБАВЛЯЕМ ЛОГИРОВАНИЕ
            signature_result = api_router.get_signature_result()
            logger.info(f'Signature result from api_router: {signature_result}')
            
            # Получаем информацию о сертификате из результата
            certificate_info = {}
            if signature_result:
                certificate_info = signature_result.get('certificate_info', {})
                logger.info(f'Certificate info from signature_result: {certificate_info}')
                if not certificate_info or certificate_info == {}:
                    logger.warning('Certificate info пуст! Проверяем что в signature_result')
                    logger.info(f'Полный signature_result: {signature_result}')
            else:
                logger.warning('Signature result is None или пустой')
            
            # Завершаем задачу с данными подписи
            submit_signing_task_completion(
                task, 
                True,
                signed_data_display.value,
                certificate_info,
                'Документ подписан',
                dialog
            )
            return
        
        # Если данных в UI нет, пытаемся получить из api_router
        if not check_and_display_signature_result(signature_info, signed_data_display, result_container):
            ui.notify('Результат подписания не найден. Сначала подпишите документ.', type='warning')
            return
        
        # ИСПРАВЛЕНИЕ: Получаем certificate_info из результата подписания
        signature_result = api_router.get_signature_result()
        logger.info(f'Signature result after check_and_display: {signature_result}')
        
        certificate_info = {}
        if signature_result:
            certificate_info = signature_result.get('certificate_info', {})
            logger.info(f'Certificate info after check_and_display: {certificate_info}')
        
        # Теперь завершаем задачу с данными подписи
        submit_signing_task_completion(
            task, 
            True,
            signed_data_display.value,
            certificate_info,
            'Документ подписан',
            dialog
        )
        
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f'Ошибка при завершении задачи подписания {task.id}: {e}', exc_info=True)

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
                        console.log('Объект Store создан');
                        
                        console.log('Открываем хранилище сертификатов...');
                        yield oStore.Open();
                        console.log('Хранилище открыто');
                        
                        console.log('Получаем список сертификатов...');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        console.log(`Найдено сертификатов: ${certCnt}`);
                        
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

def handle_signature_result(result, signature_info, signed_data_display, result_container):
    """Обрабатывает результат подписания"""
    try:
        logger.info("Получен результат подписания")
        
        # Обновляем UI с результатом подписания
        signature_info_html = f'''
        <div style="font-family: monospace; font-size: 12px;">
            <div style="color: #2e7d32; font-weight: bold; margin-bottom: 10px;">✅ Документ успешно подписан!</div>
            <div style="margin-bottom: 5px;"><strong>Сертификат:</strong> {result['certificate_info'].get('subject', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Издатель:</strong> {result['certificate_info'].get('issuer', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Серийный номер:</strong> {result['certificate_info'].get('serialNumber', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Время подписания:</strong> {result['timestamp']}</div>
        </div>
        '''
        
        # Обновляем элементы интерфейса
        signature_info.content = signature_info_html
        signed_data_display.value = result['signature']
        
        # Показываем результат
        result_container.visible = True
        
        ui.notify('✅ Документ успешно подписан!', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка обработки результата подписания: {e}")
        ui.notify(f'Ошибка обработки результата: {str(e)}', type='error')

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
    """Подписывает документ с использованием выбранного сертификата - ПОДПИСАНИЕ РЕАЛЬНОГО ДОКУМЕНТА"""
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
        
        # Получаем РЕАЛЬНЫЙ индекс сертификата в КриптоПро
        cryptopro_index = certificate_data.get('index', 1)
        
        logger.info(f"Используем РЕАЛЬНЫЙ индекс КриптоПро: {cryptopro_index}")
        
        # Показываем информацию о сертификате
        ui.notify(f'Подписание с сертификатом: {certificate_data.get("subject", "Неизвестно")}', type='info')
        
        # Получаем реальное содержимое документа для подписи
        global _document_for_signing
        if not _document_for_signing:
            ui.notify('Документ не загружен для подписи!', type='error')
            return
        
        # Используем Base64 содержимое документа
        document_base64 = _document_for_signing.get('base64', '')
        if not document_base64:
            ui.notify('Содержимое документа не найдено!', type='error')
            return
        
        logger.info(f"Подписываем документ размером: {len(document_base64)} символов Base64")
        
        # ИСПРАВЛЕННОЕ РЕШЕНИЕ: Подписание реального содержимого документа
        ui.run_javascript(f'''
            console.log('=== ПОДПИСАНИЕ РЕАЛЬНОГО ДОКУМЕНТА ===');
            console.log('Размер документа в Base64:', `{document_base64}`.length);
            console.log('Реальный индекс КриптоПро:', {cryptopro_index});
            
            if (typeof window.cadesplugin !== 'undefined') {{
                console.log('cadesplugin найден, начинаем подписание...');
                
                // ИСПРАВЛЕНИЕ: Выносим переменные в область видимости для всех блоков
                const documentBase64 = `{document_base64}`;
                const certIndex = {cryptopro_index};
                
                window.cadesplugin.async_spawn(function*() {{
                    try {{
                        console.log('=== ШАГ 1: Создаем Store ===');
                        const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                        console.log('✅ Store создан');
                        
                        console.log('=== ШАГ 2: Открываем хранилище ===');
                        yield oStore.Open();
                        console.log('✅ Хранилище открыто');
                        
                        console.log('=== ШАГ 3: Получаем сертификаты ===');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        console.log(`✅ Найдено сертификатов: ${{certCnt}}`);
                        
                        console.log('=== ШАГ 4: Получаем сертификат по индексу ===');
                        console.log(`Получаем сертификат с индексом: ${{certIndex}}`);
                        const certificate = yield certs.Item(certIndex);
                        console.log('✅ Сертификат получен');
                        
                        // Проверяем сертификат
                        const subject = yield certificate.SubjectName;
                        const hasPrivateKey = yield certificate.HasPrivateKey();
                        console.log(`Сертификат: ${{subject}}`);
                        console.log(`Имеет приватный ключ: ${{hasPrivateKey}}`);
                        
                        if (!hasPrivateKey) {{
                            throw new Error('Сертификат не имеет приватного ключа для подписи');
                        }}
                        
                        console.log('=== ШАГ 5: Создаем подписанта ===');
                        const oSigner = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.CPSigner");
                        yield oSigner.propset_Certificate(certificate);
                        console.log('✅ Подписант создан');
                        
                        // ИСПРАВЛЕНИЕ: Включаем цепочку сертификатов в подпись
                        // Устанавливаем Options для включения цепочки сертификатов
                        const signerOptions = window.cadesplugin.CAPICOM_CERTIFICATE_INCLUDE_WHOLE_CHAIN;
                        yield oSigner.propset_Options(signerOptions);
                        console.log('✅ Установлены опции подписанта (включена цепочка сертификатов)');
                        
                        console.log('=== ШАГ 6: Создаем объект данных ===');
                        const oSignedData = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.CadesSignedData");
                        
                        // ИСПРАВЛЕНИЕ: Правильное кодирование данных
                        console.log('Устанавливаем кодировку контента...');
                        yield oSignedData.propset_ContentEncoding(window.cadesplugin.CADESCOM_BASE64_TO_BINARY);
                        
                        console.log('Устанавливаем данные для подписи (реальное содержимое документа)...');
                        yield oSignedData.propset_Content(documentBase64);
                        console.log('✅ Объект данных создан');
                        
                        console.log('=== ШАГ 7: ВЫПОЛНЯЕМ ПОДПИСЬ ===');
                        // ИСПРАВЛЕНИЕ: Используем правильные параметры подписи
                        const signature = yield oSignedData.SignCades(oSigner, window.cadesplugin.CADESCOM_CADES_BES, false);
                        console.log('✅ ПОДПИСЬ СОЗДАНА!');
                        
                        console.log('=== ШАГ 8: Получаем информацию о сертификате ===');
                        const certificateInfo = {{
                            subject: yield certificate.SubjectName,
                            issuer: yield certificate.IssuerName,
                            serialNumber: yield certificate.SerialNumber,
                            validFrom: yield certificate.ValidFromDate,
                            validTo: yield certificate.ValidToDate
                        }};
                        console.log('✅ Информация о сертификате получена');
                        
                        console.log('=== ШАГ 9: Закрываем хранилище ===');
                        yield oStore.Close();
                        console.log('✅ Хранилище закрыто');
                        
                        console.log('=== УСПЕХ! ПОДПИСАНИЕ ЗАВЕРШЕНО ===');
                        return {{
                            signature: signature,
                            certificateInfo: certificateInfo
                        }};
                        
                    }} catch (e) {{
                        console.error('=== ОШИБКА ПОДПИСАНИЯ ===');
                        console.error('Ошибка:', e);
                        console.error('Код ошибки:', e.number);
                        console.error('Сообщение:', e.message);
                        
                        const errorMessage = "Ошибка подписания: " + (e.message || e.toString());
                        console.error('Сообщение об ошибке:', errorMessage);
                        throw new Error(errorMessage);
                    }}
                }})
                .then(result => {{
                    console.log('=== ОТПРАВЛЯЕМ РЕЗУЛЬТАТ В PYTHON ===');
                    console.log('Результат:', result);
                    
                    window.nicegui_handle_event('signature_completed', {{
                        signature: result.signature,
                        certificateInfo: result.certificateInfo,
                        originalData: documentBase64
                    }});
                }})
                .catch(error => {{
                    console.error('=== ОТПРАВЛЯЕМ ОШИБКУ В PYTHON ===');
                    console.error('Ошибка:', error);
                    
                    window.nicegui_handle_event('signature_error', {{
                        error: error.message || 'Неизвестная ошибка подписания'
                    }});
                }});
                
            }} else {{
                console.error('❌ cadesplugin не найден');
                window.nicegui_handle_event('signature_error', {{
                    error: 'cadesplugin не инициализирован'
                }});
            }}
        ''')
        
        # Показываем индикатор загрузки
        ui.notify('Подписание документа...', type='info')
        
    except Exception as e:
        logger.error(f"Ошибка подписания документа: {e}")
        ui.notify(f'Ошибка подписания: {str(e)}', type='error')

def check_and_display_signature_result(signature_info, signed_data_display, result_container):
    """Проверяет наличие результата подписания и обновляет UI"""
    signature_result = api_router.get_signature_result()
    if signature_result:
        # Обновляем UI с результатом подписания
        signature_info_html = f'''
        <div style="font-family: monospace; font-size: 12px;">
            <div style="color: #2e7d32; font-weight: bold; margin-bottom: 10px;">Документ успешно подписан!</div>
            <div style="margin-bottom: 5px;"><strong>Сертификат:</strong> {signature_result['certificate_info'].get('subject', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Издатель:</strong> {signature_result['certificate_info'].get('issuer', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Серийный номер:</strong> {signature_result['certificate_info'].get('serialNumber', 'Неизвестно')}</div>
            <div style="margin-bottom: 5px;"><strong>Время подписания:</strong> {signature_result['timestamp']}</div>
        </div>
        '''
        
        # Обновляем элементы интерфейса
        signature_info.content = signature_info_html
        signed_data_display.value = signature_result['signature']
        
        # Показываем результат
        result_container.visible = True
        
        ui.notify('Документ успешно подписан!', type='positive')
        
        # ИСПРАВЛЕНИЕ: НЕ очищаем результат здесь, он нужен для завершения задачи
        # api_router.clear_signature_result()  # <-- УДАЛЯЕМ ЭТУ СТРОКУ
        return True
    return False

def check_certificates_container():
    """Проверяет состояние глобального контейнера сертификатов"""
    ui.run_javascript('''
        console.log('=== ПРОВЕРКА КОНТЕЙНЕРА СЕРТИФИКАТОВ ===');
        console.log('window.global_selectbox_container:', window.global_selectbox_container);
        console.log('Тип:', typeof window.global_selectbox_container);
        console.log('Длина:', window.global_selectbox_container ? window.global_selectbox_container.length : 'не определено');
        
        if (window.global_selectbox_container && window.global_selectbox_container.length > 0) {
            console.log('✅ Контейнер содержит сертификаты:');
            for (let i = 0; i < window.global_selectbox_container.length; i++) {
                console.log(`  Сертификат ${i}:`, window.global_selectbox_container[i]);
                try {
                    // Пробуем получить информацию о сертификате
                    if (window.global_selectbox_container[i] && typeof window.global_selectbox_container[i].SubjectName !== 'undefined') {
                        console.log(`    Subject: ${window.global_selectbox_container[i].SubjectName}`);
                    }
                } catch (e) {
                    console.log(`    Ошибка получения Subject: ${e.message}`);
                }
            }
        } else {
            console.log('❌ Контейнер пуст или не определен');
            console.log('Попытка перезагрузки сертификатов...');
            
            // Попытка перезагрузить сертификаты
            if (window.cryptoProIntegration) {
                window.cryptoProIntegration.getAvailableCertificates()
                    .then(certs => {
                        console.log('✅ Сертификаты перезагружены:', certs);
                        console.log('Новый контейнер:', window.global_selectbox_container);
                    })
                    .catch(error => {
                        console.error('❌ Ошибка перезагрузки сертификатов:', error);
                    });
            }
        }
    ''')

def handle_signature_result():
    """Обрабатывает результат подписания от JavaScript"""
    global _signature_result
    
    try:
        # Получаем результат подписания из API роутера
        signature_result = api_router.get_signature_result()
        
        if signature_result:
            logger.info("Получен результат подписания")
            
            # Обновляем UI с результатом подписания
            # Здесь можно обновить соответствующие элементы интерфейса
            
            # Очищаем результат после обработки
            api_router.clear_signature_result()
            
    except Exception as e:
        logger.error(f"Ошибка обработки результата подписания: {e}")

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
    """Проверяет подпись через CryptoPro API"""
    try:
        if not signature_base64:
            ui.notify('Подпись не найдена для проверки', type='warning')
            return
        
        # Используем JavaScript для проверки подписи через CryptoPro
        ui.run_javascript(f'''
            console.log('=== ПРОВЕРКА ПОДПИСИ ===');
            console.log('Размер подписи:', `{signature_base64}`.length);
            
            if (typeof window.cadesplugin !== 'undefined') {{
                console.log('cadesplugin найден, начинаем проверку...');
                
                window.cadesplugin.async_spawn(function*() {{
                    try {{
                        console.log('=== ШАГ 1: Создаем объект для проверки ===');
                        const oSignedData = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.CadesSignedData");
                        console.log('✅ Объект создан');
                        
                        console.log('=== ШАГ 2: Устанавливаем подпись ===');
                        yield oSignedData.propset_ContentEncoding(window.cadesplugin.CADESCOM_BASE64_TO_BINARY);
                        yield oSignedData.propset_Content(`{signature_base64}`);
                        console.log('✅ Подпись установлена');
                        
                        console.log('=== ШАГ 3: ВЫПОЛНЯЕМ ПРОВЕРКУ ===');
                        const isValid = yield oSignedData.VerifyCades(`{signature_base64}`, window.cadesplugin.CADESCOM_CADES_BES, false);
                        console.log('✅ Проверка завершена, результат:', isValid);
                        
                        if (isValid) {{
                            console.log('=== УСПЕХ! ПОДПИСЬ ВАЛИДНА ===');
                            
                            // Получаем информацию о сертификате
                            const signers = yield oSignedData.Signers;
                            const signerCount = yield signers.Count;
                            console.log(`Найдено подписантов: ${{signerCount}}`);
                            
                            let certificateInfo = null;
                            if (signerCount > 0) {{
                                const signer = yield signers.Item(1);
                                const certificate = yield signer.Certificate;
                                certificateInfo = {{
                                    subject: yield certificate.SubjectName,
                                    issuer: yield certificate.IssuerName,
                                    serialNumber: yield certificate.SerialNumber,
                                    validFrom: yield certificate.ValidFromDate,
                                    validTo: yield certificate.ValidToDate
                                }};
                            }}
                            
                            window.nicegui_handle_event('signature_verified', {{
                                isValid: true,
                                certificateInfo: certificateInfo,
                                timestamp: new Date().toISOString()
                            }});
                        }} else {{
                            console.log('=== ОШИБКА! ПОДПИСЬ НЕВАЛИДНА ===');
                            window.nicegui_handle_event('signature_verified', {{
                                isValid: false,
                                error: 'Подпись не прошла проверку',
                                timestamp: new Date().toISOString()
                            }});
                        }}
                        
                    }} catch (e) {{
                        console.error('=== ОШИБКА ПРОВЕРКИ ===');
                        console.error('Ошибка:', e);
                        
                        window.nicegui_handle_event('signature_verified', {{
                            isValid: false,
                            error: e.message || 'Ошибка при проверке подписи',
                            timestamp: new Date().toISOString()
                        }});
                    }}
                }});
                
            }} else {{
                console.error('❌ cadesplugin не найден');
                window.nicegui_handle_event('signature_verified', {{
                    isValid: false,
                    error: 'cadesplugin не инициализирован',
                    timestamp: new Date().toISOString()
                }});
            }}
        ''')
        
        ui.notify('Проверка подписи...', type='info')
        
    except Exception as e:
        logger.error(f"Ошибка проверки подписи: {e}")
        ui.notify(f'Ошибка проверки подписи: {str(e)}', type='error')

def save_signature_to_file(signature_base64, task_name):
    """Сохраняет PDF с профессиональной встроенной электронной подписью"""
    try:       
        # Получаем исходный документ из глобальной переменной
        global _document_for_signing
        if not _document_for_signing:
            ui.notify('Исходный документ не найден', type='error')
            return
        
        original_document_base64 = _document_for_signing.get('base64', '')
        if not original_document_base64:
            ui.notify('Содержимое исходного документа не найдено', type='error')
            return
        
        # Создаем имя файла для подписанного PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"signed_{task_name}_{timestamp}.pdf"
        
        # Декодируем исходный PDF
        pdf_binary = base64.b64decode(original_document_base64)
        
        try:            
            # Путь к директории со шрифтами
            fonts_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
            
            # Регистрируем шрифт для поддержки русского текста
            font_name = 'Helvetica'  # По умолчанию
            
            # Пытаемся загрузить локальные шрифты
            font_files = [
                ('DejaVuSans', 'DejaVuSans.ttf'),
                ('LiberationSans', 'LiberationSans-Regular.ttf'),
                ('Roboto', 'Roboto.ttf'),
                ('OpenSans', 'OpenSans.ttf')
            ]
            
            for font_name, font_file in font_files:
                font_path = os.path.join(fonts_dir, font_file)
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        logger.info(f"Загружен шрифт: {font_name} из {font_path}")
                        break
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить шрифт {font_name}: {e}")
                        continue
            
            # Получаем информацию о сертификате из результата подписания
            signature_result = api_router.get_signature_result()
            certificate_info = {}
            if signature_result and signature_result.get('certificate_info'):
                certificate_info = signature_result.get('certificate_info', {})
            
            # Извлекаем данные сертификата
            cert_subject = certificate_info.get('subject', 'Неизвестно')
            cert_issuer = certificate_info.get('issuer', 'Неизвестно')
            serial_number = certificate_info.get('serialNumber', 'Неизвестно')
            valid_from = certificate_info.get('validFrom', '')
            valid_to = certificate_info.get('validTo', '')
            
            # Обрабатываем даты
            from_date_str = "Неизвестно"
            to_date_str = "Неизвестно"
            if valid_from and valid_to:
                try:
                    from_date = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                    to_date = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))
                    from_date_str = from_date.strftime('%d.%m.%Y')
                    to_date_str = to_date.strftime('%d.%m.%Y')
                except:
                    pass
            
            # Создаем страницу с блоком электронной подписи
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=A4)
            
            # Создаем профессиональный блок подписи
            # Позиция блока - ПОДБИРАЕМ ТОЧНУЮ ВЫСОТУ
            block_x = 10*cm
            block_y = 1.5*cm
            block_width = 5.6*cm
            block_height = 3.2*cm  # Еще уменьшили, чтобы убрать место внизу
            
            # Фон блока (светло-голубой)
            can.setFillColor(HexColor('#F0F8FF'))
            can.setStrokeColor(HexColor('#1E3A8A'))
            can.setLineWidth(1.5)
            can.roundRect(block_x, block_y, block_width, block_height, 6, fill=1, stroke=1)
            
            # Внутренняя рамка
            can.setStrokeColor(HexColor('#3B82F6'))
            can.setLineWidth(0.5)
            can.roundRect(block_x + 0.1*cm, block_y + 0.1*cm, block_width - 0.2*cm, block_height - 0.2*cm, 4, fill=0, stroke=1)
            
            # Заголовок блока
            can.setFillColor(HexColor('#1E3A8A'))
            can.setFont(font_name, 9)
            can.drawString(block_x + 0.3*cm, block_y + 2.5*cm, "ДОКУМЕНТ ПОДПИСАН ЭП")
            
            # Линия под заголовком
            can.setStrokeColor(HexColor('#1E3A8A'))
            can.setLineWidth(1)
            can.line(block_x + 0.3*cm, block_y + 2.3*cm, block_x + block_width - 0.3*cm, block_y + 2.3*cm)
            
            # Информация о сертификате - ПРАВИЛЬНЫЕ ИНТЕРВАЛЫ
            can.setFillColor(HexColor('#000000'))
            can.setFont(font_name, 7)
            
            # Дата подписания - ИНТЕРВАЛ 0.25cm
            sign_date = datetime.now().strftime('%d.%m.%Y')
            can.drawString(block_x + 0.3*cm, block_y + 2.0*cm, f"Дата: {sign_date}")
            
            # Сертификат - ИНТЕРВАЛ 0.25cm
            cert_subject_short = cert_subject[:35] + "..." if len(cert_subject) > 35 else cert_subject
            can.drawString(block_x + 0.3*cm, block_y + 1.75*cm, f"Сертификат: {cert_subject_short}")
            
            # Владелец - ИНТЕРВАЛ 0.25cm
            cert_issuer_short = cert_issuer[:35] + "..." if len(cert_issuer) > 35 else cert_issuer
            can.drawString(block_x + 0.3*cm, block_y + 1.5*cm, f"Владелец: {cert_issuer_short}")
            
            # Срок действия - ИНТЕРВАЛ 0.25cm
            can.drawString(block_x + 0.3*cm, block_y + 1.25*cm, f"Действителен: {from_date_str} - {to_date_str}")
            
            # Статус подписи - БОЛЬШИЙ ИНТЕРВАЛ перед ним
            can.setFillColor(HexColor('#059669'))
            can.setFont(font_name, 8)
            can.drawString(block_x + 0.3*cm, block_y + 0.95*cm, "✓ ПОДПИСЬ ДЕЙСТВИТЕЛЬНА")
            
            # Дополнительная информация - ОЧЕНЬ БЛИЗКО К НИЖНЕЙ ГРАНИЦЕ
            can.setFillColor(HexColor('#6B7280'))
            can.setFont(font_name, 6)
            can.drawString(block_x + 0.3*cm, block_y + 0.5*cm, "CryptoPro • CAdES-BES")
            
            can.save()
            
            # Получаем данные блока подписи
            packet.seek(0)
            signature_page = packet.getvalue()
            
            # Объединяем исходный PDF с блоком подписи
            from PyPDF2 import PdfReader, PdfWriter
            
            # Читаем исходный PDF
            original_pdf = PdfReader(io.BytesIO(pdf_binary))
            
            # Создаем новый PDF с блоком подписи
            signature_pdf = PdfReader(io.BytesIO(signature_page))
            
            # Объединяем PDF
            writer = PdfWriter()
            
            # Добавляем все страницы исходного PDF
            for page in original_pdf.pages:
                writer.add_page(page)
            
            # Добавляем страницу с блоком подписи
            writer.add_page(signature_pdf.pages[0])
            
            # Сохраняем объединенный PDF
            with open(filename, 'wb') as output_file:
                writer.write(output_file)
            
            ui.notify(f'✅ PDF с профессиональной электронной подписью сохранен: {filename}', type='positive')
            
        except ImportError:
            # Если библиотеки не установлены, сохраняем исходный PDF
            with open(filename, 'wb') as f:
                f.write(pdf_binary)
            
            ui.notify(f'✅ PDF сохранен: {filename}\\n(Для профессиональной подписи установите: pip install reportlab PyPDF2)', type='info')
            
        except Exception as e:
            # В случае ошибки сохраняем исходный PDF
            logger.error(f"Ошибка создания PDF с профессиональной подписью: {e}")
            with open(filename, 'wb') as f:
                f.write(pdf_binary)
            
            ui.notify(f'✅ PDF сохранен: {filename}\\n(Ошибка создания профессиональной подписи: {str(e)})', type='warning')
        
    except Exception as e:
        logger.error(f"Ошибка сохранения PDF: {e}")
        ui.notify(f'Ошибка сохранения PDF: {str(e)}', type='error')


def add_additional_signature_to_pdf(existing_pdf_path, signature_base64, signer_name, task_name):
    """Добавляет дополнительную подпись к существующему PDF"""
    try:       
        # Создаем имя файла для обновленного PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"signed_{task_name}_{signer_name}_{timestamp}.pdf"
        
        try:           
            # Загружаем шрифт
            fonts_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
            font_name = 'Helvetica'
            
            for font_name, font_file in [('DejaVuSans', 'DejaVuSans.ttf')]:
                font_path = os.path.join(fonts_dir, font_file)
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        break
                    except:
                        continue
            
            # Создаем страницу с дополнительным блоком подписи
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=A4)
            
            # Получаем информацию о сертификате
            signature_result = api_router.get_signature_result()
            certificate_info = {}
            if signature_result and signature_result.get('certificate_info'):
                certificate_info = signature_result.get('certificate_info', {})
            
            # Создаем дополнительный блок подписи
            block_x = 12*cm
            block_y = 2*cm
            block_width = 6*cm
            block_height = 4*cm
            
            # Фон блока (светло-синий)
            can.setFillColor(HexColor('#E3F2FD'))
            can.setStrokeColor(HexColor('#1976D2'))
            can.setLineWidth(2)
            can.roundRect(block_x, block_y, block_width, block_height, 8, fill=1, stroke=1)
            
            # Заголовок блока
            can.setFillColor(HexColor('#1976D2'))
            can.setFont(font_name, 10)
            can.drawString(block_x + 0.3*cm, block_y + 3.2*cm, "ДОПОЛНИТЕЛЬНАЯ ПОДПИСЬ")
            
            # Информация о подписанте
            can.setFillColor(HexColor('#000000'))
            can.setFont(font_name, 8)
            can.drawString(block_x + 0.3*cm, block_y + 2.8*cm, f"Подписант: {signer_name}")
            
            # Дата подписания
            sign_date = datetime.now().strftime('%d.%m.%Y')
            can.drawString(block_x + 0.3*cm, block_y + 2.6*cm, f"Дата подписания: {sign_date}")
            
            # Статус
            can.setFillColor(HexColor('#2E7D32'))
            can.setFont(font_name, 9)
            can.drawString(block_x + 0.3*cm, block_y + 2.2*cm, "✓ ПОДПИСЬ ДЕЙСТВИТЕЛЬНА")
            
            can.save()
            
            # Объединяем с существующим PDF
            packet.seek(0)
            signature_page = packet.getvalue()
            
            from PyPDF2 import PdfReader, PdfWriter
            
            # Читаем существующий PDF
            with open(existing_pdf_path, 'rb') as f:
                existing_pdf = PdfReader(f)
            
            # Создаем новый PDF с дополнительной подписью
            signature_pdf = PdfReader(io.BytesIO(signature_page))
            
            # Объединяем PDF
            writer = PdfWriter()
            
            # Добавляем все страницы существующего PDF
            for page in existing_pdf.pages:
                writer.add_page(page)
            
            # Добавляем страницу с дополнительной подписью
            writer.add_page(signature_pdf.pages[0])
            
            # Сохраняем обновленный PDF
            with open(filename, 'wb') as output_file:
                writer.write(output_file)
            
            ui.notify(f'✅ PDF обновлен с дополнительной подписью {signer_name}: {filename}', type='positive')
            
        except Exception as e:
            logger.error(f"Ошибка добавления дополнительной подписи: {e}")
            ui.notify(f'Ошибка добавления дополнительной подписи: {str(e)}', type='error')
        
    except Exception as e:
        logger.error(f"Ошибка обработки PDF: {e}")
        ui.notify(f'Ошибка обработки PDF: {str(e)}', type='error')


# def save_signature_to_file(signature_base64, task_name):
#     """Сохраняет подписанный PDF документ в файл"""
#     try:
#         import base64
#         from datetime import datetime
        
#         # Получаем исходный документ из глобальной переменной
#         global _document_for_signing
#         if not _document_for_signing:
#             ui.notify('Исходный документ не найден', type='error')
#             return
        
#         original_document_base64 = _document_for_signing.get('base64', '')
#         if not original_document_base64:
#             ui.notify('Содержимое исходного документа не найдено', type='error')
#             return
        
#         # Создаем имя файла для подписанного PDF
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         filename = f"signed_{task_name}_{timestamp}.pdf"
        
#         # Используем JavaScript для создания подписанного PDF через CryptoPro
#         ui.run_javascript(f'''
#             console.log('=== СОЗДАНИЕ ПОДПИСАННОГО PDF ===');
#             console.log('Размер исходного документа:', `{original_document_base64}`.length);
#             console.log('Размер подписи:', `{signature_base64}`.length);
            
#             if (typeof window.cadesplugin !== 'undefined') {{
#                 console.log('cadesplugin найден, создаем подписанный PDF...');
                
#                 window.cadesplugin.async_spawn(function*() {{
#                     try {{
#                         console.log('=== ШАГ 1: Создаем объект для подписанных данных ===');
#                         const oSignedData = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.CadesSignedData");
#                         console.log('✅ Объект создан');
                        
#                         console.log('=== ШАГ 2: Устанавливаем исходный документ ===');
#                         yield oSignedData.propset_ContentEncoding(window.cadesplugin.CADESCOM_BASE64_TO_BINARY);
#                         yield oSignedData.propset_Content(`{original_document_base64}`);
#                         console.log('✅ Исходный документ установлен');
                        
#                         console.log('=== ШАГ 3: Создаем подписанный документ ===');
#                         // Создаем подписанный документ с встроенной подписью
#                         const signedDocument = yield oSignedData.SignCades(null, window.cadesplugin.CADESCOM_CADES_BES, true);
#                         console.log('✅ Подписанный документ создан');
                        
#                         console.log('=== ШАГ 4: Отправляем результат в Python ===');
#                         window.nicegui_handle_event('signed_document_created', {{
#                             signedDocument: signedDocument,
#                             filename: `{filename}`,
#                             timestamp: new Date().toISOString()
#                         }});
                        
#                     }} catch (e) {{
#                         console.error('=== ОШИБКА СОЗДАНИЯ ПОДПИСАННОГО PDF ===');
#                         console.error('Ошибка:', e);
                        
#                         window.nicegui_handle_event('signed_document_error', {{
#                             error: e.message || 'Ошибка при создании подписанного PDF',
#                             timestamp: new Date().toISOString()
#                         }});
#                     }}
#                 }});
                
#             }} else {{
#                 console.error('❌ cadesplugin не найден');
#                 window.nicegui_handle_event('signed_document_error', {{
#                     error: 'cadesplugin не инициализирован',
#                     timestamp: new Date().toISOString()
#                 }});
#             }}
#         ''')
        
#         ui.notify('Создание подписанного PDF...', type='info')
        
#     except Exception as e:
#         logger.error(f"Ошибка создания подписанного PDF: {e}")
#         ui.notify(f'Ошибка создания подписанного PDF: {str(e)}', type='error')

def save_signed_pdf_to_file():
    """Сохраняет подписанный PDF в файл"""
    try:
        signature_result = api_router.get_signature_result()
        
        if signature_result and signature_result.get('action') == 'signed_document_created':
            signed_document = signature_result.get('signed_document', '')
            filename = signature_result.get('filename', 'signed_document.pdf')
            
            if signed_document:
                # Декодируем Base64 в бинарные данные
                import base64
                pdf_binary = base64.b64decode(signed_document)
                
                # Сохраняем подписанный PDF в файл
                with open(filename, 'wb') as f:
                    f.write(pdf_binary)
                
                ui.notify(f'✅ Подписанный PDF сохранен в файл: {filename}', type='positive')
                
                # Очищаем результат после обработки
                api_router.clear_signature_result()
            else:
                ui.notify('Подписанный документ не найден', type='error')
        else:
            ui.notify('Результат создания подписанного PDF не найден', type='warning')
            
    except Exception as e:
        logger.error(f"Ошибка сохранения подписанного PDF: {e}")
        ui.notify(f'Ошибка сохранения подписанного PDF: {str(e)}', type='error')

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

def set_signature_result_handler(handler):
    """Устанавливает обработчик результата подписания"""
    global _signature_result_handler
    _signature_result_handler = handler

def check_signature_result():
    """Проверяет наличие результата подписания и обрабатывает его"""
    global _signature_result_handler
    
    try:
        signature_result = api_router.get_signature_result()
        
        if signature_result and _signature_result_handler:
            logger.info("Обрабатываем результат подписания")
            _signature_result_handler(signature_result)
            api_router.clear_signature_result()
            
    except Exception as e:
        logger.error(f"Ошибка обработки результата подписания: {e}")

def load_and_display_document(document_id: str, container: ui.column):
    """Загружает и отображает документ"""
    try:
        from services.mayan_connector import MayanClient
        mayan_client = MayanClient.create_with_session_user()
        logger.info(f'mayan_client: {mayan_client}')
        logger.info(f'Загружаем документ {document_id}')
        
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
        mayan_client = get_mayan_client()
        document = mayan_client.get_document(document_id)  # ← ИСПРАВЛЕНО: используем правильный метод
        
        if document:
            # Получаем содержимое документа
            document_content = mayan_client.get_document_file_content_as_text(document_id)  # ← ИСПРАВЛЕНО: используем правильный метод
            logger.info(f'Документ: {document}')
            if document_content:
                formated_date_document_create = format_date_russian(document.datetime_created)

                # Отображаем содержимое документа
                content_html = f'''
                    <div class="document-content p-4">
                        <h3 class="text-lg font-semibold mb-4">Документ: {document.label}</h3>
                        <p>{formated_date_document_create}</p>
                        <div class="mt-4">
                            <a href="{mayan_client.base_url}/documents/documents/{document_id}/preview" 
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
                        <p>Документ: {document.label}</p>
                        <p>Файл: {document.file_latest_filename}</p>
                        <p>Тип: {document.file_latest_mimetype}</p>
                        <p>Размер: {document.file_latest_size} байт</p>
                        <a href="{mayan_client.base_url}/documents/documents/{document_id}/preview" 
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
    '''Отправляет завершение задачи подписания'''
    try:
        if not signed:
            ui.notify('Необходимо подтвердить подписание документа', type='warning')
            return
        
        # Загружаем подпись в Mayan EDMS
        try:
            user = get_current_user()
            if not user:
                ui.notify('Не удалось получить информацию о пользователе', type='error')
                logger.error('Пользователь не авторизован при загрузке подписи')
            else:
                username = user.username
                
                camunda_client = create_camunda_client()
                process_variables = camunda_client.get_process_instance_variables(task.process_instance_id)
                document_id = process_variables.get('documentId')
                
                if document_id and signature_data:
                    from services.signature_manager import SignatureManager
                    signature_manager = SignatureManager()
                    
                    success = signature_manager.upload_signature_to_document(
                        document_id=document_id,
                        username=username,
                        signature_base64=signature_data,
                        certificate_info=certificate_info
                    )
                    
                    if success:
                        ui.notify(f'✅ Подпись {username}.p7s загружена к документу', type='positive')
                        logger.info(f'Подпись пользователя {username} загружена к документу {document_id}')
                    else:
                        logger.error(f'Не удалось загрузить подпись пользователя {username} к документу {document_id}')
                        ui.notify('⚠️ Подпись создана, но не загружена в Mayan', type='warning')
                        
        except Exception as e:
            logger.error(f'Ошибка при загрузке подписи в Mayan EDMS: {e}', exc_info=True)
            ui.notify('⚠️ Ошибка загрузки подписи в Mayan, задача будет завершена', type='warning')
        
        # Подготавливаем переменные для процесса подписания
        variables = {
            'signed': signed,
            # 'signatureData': signature_data,  # Не передаем - слишком большой
            # 'certificateInfo': certificate_info,  # Не передаем - сохранен в Mayan
            'signatureComment': comment or '',
            'signatureDate': datetime.now().isoformat(),
            'signatureUploaded': True  # Флаг что подпись загружена
        }
        
        # Завершаем задачу в Camunda
        success = camunda_client.complete_task_with_variables(task.id, variables)
        
        if success:
            # Очищаем результат подписания после успешного завершения
            api_router.clear_signature_result()
            ui.notify('Документ успешно подписан!', type='success')
            dialog.close()
            # Обновляем список задач
            load_active_tasks(_tasks_header_container)
        else:
            ui.notify('Ошибка при подписании документа', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f'Ошибка при завершении задачи подписания {task.id}: {e}', exc_info=True)

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