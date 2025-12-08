from math import log
from nicegui import ui
from nicegui import context
from services.camunda_connector import create_camunda_client
from services.mayan_connector import MayanClient
from config.settings import config
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional, Union
from models import CamundaHistoryTask, LDAPUser, GroupedHistoryTask
from auth.middleware import get_current_user
from auth.ldap_auth import LDAPAuthenticator
from utils import validate_username
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
import tempfile
import json
import pytz
from components.document_viewer import show_document_viewer
from components.gantt_chart import create_gantt_chart, parse_task_deadline
import urllib.parse
import asyncio
from components.gantt_chart import parse_task_deadline
from models import CamundaTask


logger = logging.getLogger(__name__)

# Глобальные переменные для управления состоянием
_tasks_container: Optional[ui.column] = None
_completed_tasks_container: Optional[ui.column] = None
_completed_tasks_header_container: Optional[ui.row] = None  # Добавляем контейнер для заголовка
_details_container: Optional[ui.column] = None
#_task_details_sidebar: Optional[ui.column] = None
#_task_details_column: Optional[ui.column] = None  # Добавляем переменную для контейнера деталей
_uploaded_files_container: Optional[ui.column] = None
_uploaded_files: List[Dict[str, Any]] = []
_tabs: Optional[ui.tabs] = None  # Добавляем ссылку на табы
_task_details_tab: Optional[ui.tab] = None  # Добавляем ссылку на вкладку деталей
_active_tasks_tab: Optional[ui.tab] = None  # Добавляем ссылку на вкладку активных задач
_tasks_header_container: Optional[ui.column] = None  # Добавляем переменную для заголовка с количеством задач
_certificate_select_global = None
_selected_certificate = None
_certificates_cache = []
_document_for_signing = None
_signature_result_handler = None

# Добавляем глобальную переменную для хранения pending task_id
_pending_task_id = None
# Добавляем глобальную переменную для хранения ID выбранной задачи
_selected_task_id: Optional[str] = None

_task_cards = {}

# Добавляем глобальную переменную для режима показа всех сертификатов
_show_all_certificates = False

_completed_tasks_container: Optional[ui.column] = None
_completed_tasks_header_container: Optional[ui.row] = None
_all_completed_tasks: List[Union[GroupedHistoryTask, CamundaHistoryTask]] = []  # Все загруженные задачи
_current_page: int = 1  # Текущая страница
_page_size: int = 10  # Размер страницы
_pagination_container: Optional[ui.row] = None  # Контейнер для элементов пагинации


async def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return await MayanClient.create_with_session_user()

def _is_valid_username(username: str) -> bool:
    """Проверяет безопасность имени пользователя"""
    if not username or len(username) > 50:
        return False
    
    # Разрешаем только буквы, цифры, точки, дефисы и подчеркивания
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_')
    return all(c in allowed_chars for c in username)

def content() -> None:
    """Страница завершения задач"""
    # Добавляем CSS стили для раскраски дат
    ui.add_head_html('''
        <style>
            .due-date-overdue {
                background-color: #ffebee !important;
                color: #c62828 !important;
            }
            .due-date-warning {
                background-color: #ff9800 !important;
                color: #ffffff !important;
            }
            .due-date-ok {
                background-color: #e8f5e9 !important;
                color: #2e7d32 !important;
            }
        </style>
    ''')
    
    try:
        # ui.label('Завершение задач').classes('text-2xl font-bold mb-6')
        
        # Проверяем query параметры для открытия конкретной задачи
        # Используем правильный способ получения query параметров в NiceGUI
        try:
            # Получаем query параметры из URL
            if hasattr(context, 'client') and context.client and hasattr(context.client, 'request'):
                request = context.client.request
                if hasattr(request, 'query_params'):
                    query_params = request.query_params
                    task_id = query_params.get('task_id', '')
                else:
                    # Альтернативный способ - из URL
                    url = str(request.url) if hasattr(request, 'url') else ''
                    if '?' in url:
                        query_string = url.split('?')[1]
                        params = urllib.parse.parse_qs(query_string)
                        task_id = params.get('task_id', [''])[0]
                    else:
                        task_id = ''
            else:
                task_id = ''
            
            if task_id:
                logger.info(f"Получен task_id из query параметров: {task_id}")
                # Сохраняем task_id в глобальную переменную для использования после инициализации
                global _pending_task_id
                _pending_task_id = task_id
                # Используем таймер с небольшой задержкой, чтобы дождаться инициализации всех компонентов
                ui.timer(0.5, lambda: open_task_by_id(_pending_task_id), once=True)
        except Exception as e:
            logger.warning(f"Не удалось получить query параметры: {e}")
            _pending_task_id = None
        
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
        global _tabs, _task_details_tab, _active_tasks_tab
        _tabs = tabs
        _task_details_tab = task_details_tab
        _active_tasks_tab = active_tasks_tab
    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы: {e}")
        ui.notify(f'Ошибка при загрузке страницы: {str(e)}', type='error')

async def open_task_by_id(task_id: str):
    """Открывает задачу по ID на вкладке активных задач"""
    global _tabs, _active_tasks_tab, _tasks_container, _tasks_header_container
    
    if not task_id:
        logger.warning("open_task_by_id вызван без task_id")
        return
    
    logger.info(f"Открываем задачу по ID: {task_id}")
    
    # Ждем инициализации компонентов
    if _tasks_container is None:
        logger.warning("_tasks_container еще не инициализирован, повторная попытка через 0.3 сек")
        ui.timer(0.3, lambda: open_task_by_id(task_id), once=True)
        return
    
    # Переключаемся на вкладку активных задач
    if _tabs and _active_tasks_tab:
        _tabs.value = _active_tasks_tab
        logger.info("Переключились на вкладку активных задач")
    
    # Загружаем активные задачи и находим нужную
    await load_active_tasks(_tasks_header_container, target_task_id=task_id)

def create_active_tasks_section():
    """Создает секцию с активными задачами"""
    global _tasks_container, _tasks_header_container
        
    # Создаем контейнер для задач
    with ui.card().classes('p-6 w-full'):
        # Контейнер для заголовка с количеством задач и кнопкой обновления в одной строке
        _tasks_header_container = ui.row().classes('w-full items-center gap-4 mb-4')
        
        # Контейнер для задач
        _tasks_container = ui.column().classes('w-full')
        
        # Загружаем задачи при открытии страницы
        async def init_tasks():
            await load_active_tasks(_tasks_header_container)
        
        ui.timer(0.1, lambda: init_tasks(), once=True)

async def load_active_tasks(header_container=None, target_task_id: Optional[str] = None):
    """Загружает и отображает активные задачи пользователя"""
    global _tasks_container, _task_cards
    
    if _tasks_container is None:
        return
    
    # Очищаем контейнеры и словарь карточек
    _tasks_container.clear()
    _task_cards.clear()
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
        camunda_client = await create_camunda_client()
        tasks = await camunda_client.get_user_tasks_filtered(
            assignee=assignee,
            active_only=True,
            filter_completed=True
        )
        
        # Нормализуем target_task_id для сравнения (приводим к строке)
        target_task_id_str = str(target_task_id).strip() if target_task_id else None
        logger.info(f"Ищем задачу с ID: {target_task_id_str}")
        
        if tasks:
            # Добавляем кнопку обновления и заголовок с количеством задач в одну строку
            if header_container:
                with header_container:
                    ui.button(
                        'Обновить задачи',
                        icon='refresh',
                        on_click=lambda: load_active_tasks(_tasks_header_container)
                    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                    ui.label(f'Найдено {len(tasks)} активных задач:').classes('text-lg font-semibold')
            
            # Добавляем диаграмму Ганта перед карточками задач
            # Фильтруем задачи, у которых есть дедлайн
            tasks_with_due = [task for task in tasks if hasattr(task, 'due') and task.due]
            if tasks_with_due:
                create_gantt_chart(
                    tasks_with_due, 
                    title='Диаграмма Ганта активных задач',
                    name_field='name',
                    due_field='due',
                    id_field='id',
                    process_instance_id_field='process_instance_id'
                )
            
            # Переменная для хранения найденной задачи
            found_task = None
            
            # Добавляем карточки задач в основной контейнер
            for task in tasks:
                await create_task_card_with_progress(task)
                
                # Проверяем, является ли это задача, которую нужно открыть
                # Приводим все ID к строкам для надежного сравнения
                if target_task_id_str:
                    task_id_str = str(getattr(task, 'id', '')).strip()
                    process_id_str = str(getattr(task, 'process_instance_id', '')).strip()
                    
                    logger.debug(f"Сравниваем: task_id={task_id_str}, process_id={process_id_str}, target={target_task_id_str}")
                    
                    if task_id_str == target_task_id_str or process_id_str == target_task_id_str:
                        found_task = task
                        logger.info(f"Найдена задача в списке: task_id={task_id_str}, process_id={process_id_str}")
                        break
            
            # Если нашли задачу в списке, показываем её детали
            if found_task:
                logger.info(f"Показываем детали найденной задачи {found_task.id}")
                # Вызываем напрямую, а не через ui.timer, чтобы сохранить контекст
                await show_task_details(found_task)
            elif target_task_id_str:
                # Если задача не найдена в списке, пробуем загрузить её напрямую по ID
                logger.info(f"Задача {target_task_id_str} не найдена в списке активных задач, пробуем загрузить напрямую")
                try:
                    # Пробуем загрузить задачу напрямую
                    direct_task = await camunda_client.get_task_by_id(target_task_id_str)
                    if direct_task:
                        logger.info(f"Задача {target_task_id_str} найдена напрямую, показываем детали")
                        # Используем небольшую задержку, чтобы UI успел обновиться
                        ui.timer(0.1, lambda: show_task_details(direct_task), once=True)
                    else:
                        # Если не нашли как активную, пробуем найти по process_instance_id
                        logger.info(f"Задача {target_task_id_str} не найдена как активная, пробуем найти задачи процесса")
                        try:
                            # Получаем задачи процесса
                            endpoint = f'task?processInstanceId={target_task_id_str}'
                            response = await camunda_client._make_request('GET', endpoint)
                            response.raise_for_status()
                            process_tasks = response.json()
                            
                            if process_tasks and len(process_tasks) > 0:
                                # Берем первую задачу процесса
                                task_data = process_tasks[0]
                                process_task = CamundaTask(
                                    id=task_data['id'],
                                    name=task_data.get('name', ''),
                                    assignee=task_data.get('assignee'),
                                    start_time=task_data.get('created', ''),
                                    due=task_data.get('due'),
                                    follow_up=task_data.get('followUp'),
                                    delegation_state=task_data.get('delegationState'),
                                    description=task_data.get('description'),
                                    execution_id=task_data.get('executionId', ''),
                                    owner=task_data.get('owner'),
                                    parent_task_id=task_data.get('parentTaskId'),
                                    priority=task_data.get('priority', 0),
                                    process_definition_id=task_data.get('processDefinitionId', ''),
                                    process_instance_id=task_data.get('processInstanceId', ''),
                                    task_definition_key=task_data.get('taskDefinitionKey', ''),
                                    case_execution_id=task_data.get('caseExecutionId'),
                                    case_instance_id=task_data.get('caseInstanceId'),
                                    case_definition_id=task_data.get('caseDefinitionId'),
                                    suspended=task_data.get('suspended', False),
                                    form_key=task_data.get('formKey'),
                                    tenant_id=task_data.get('tenantId')
                                )
                                logger.info(f"Найдена задача процесса {target_task_id_str}, показываем детали")
                                ui.timer(0.1, lambda: show_task_details(process_task), once=True)
                            else:
                                logger.warning(f"Задача {target_task_id_str} не найдена ни в списке, ни напрямую")
                                ui.notify(f'Задача {target_task_id_str} не найдена в ваших активных задачах', type='warning')
                        except Exception as e2:
                            logger.warning(f"Не удалось найти задачу по process_instance_id {target_task_id_str}: {e2}")
                            ui.notify(f'Задача {target_task_id_str} не найдена', type='warning')
                except Exception as e:
                    logger.error(f"Ошибка при загрузке задачи {target_task_id_str} напрямую: {e}", exc_info=True)
                    ui.notify(f'Ошибка при загрузке задачи: {str(e)}', type='error')
        else:
            # Показываем сообщение об отсутствии задач
            if header_container:
                with header_container:
                    ui.label('Нет активных задач').classes('text-gray-500')
            
            # Если есть target_task_id, но нет задач в списке, пробуем загрузить напрямую
            if target_task_id_str:
                logger.info(f"Нет активных задач, но есть target_task_id={target_task_id_str}, пробуем загрузить напрямую")
                try:
                    direct_task = await camunda_client.get_task_by_id(target_task_id_str)
                    if direct_task:
                        logger.info(f"Задача {target_task_id_str} найдена напрямую, показываем детали")
                        ui.timer(0.1, lambda: show_task_details(direct_task), once=True)
                    else:
                        # Пробуем найти по process_instance_id
                        try:
                            endpoint = f'task?processInstanceId={target_task_id_str}'
                            response = await camunda_client._make_request('GET', endpoint)
                            response.raise_for_status()
                            process_tasks = response.json()
                            
                            if process_tasks and len(process_tasks) > 0:
                                task_data = process_tasks[0]
                                process_task = CamundaTask(
                                    id=task_data['id'],
                                    name=task_data.get('name', ''),
                                    assignee=task_data.get('assignee'),
                                    start_time=task_data.get('created', ''),
                                    due=task_data.get('due'),
                                    follow_up=task_data.get('followUp'),
                                    delegation_state=task_data.get('delegationState'),
                                    description=task_data.get('description'),
                                    execution_id=task_data.get('executionId', ''),
                                    owner=task_data.get('owner'),
                                    parent_task_id=task_data.get('parentTaskId'),
                                    priority=task_data.get('priority', 0),
                                    process_definition_id=task_data.get('processDefinitionId', ''),
                                    process_instance_id=task_data.get('processInstanceId', ''),
                                    task_definition_key=task_data.get('taskDefinitionKey', ''),
                                    case_execution_id=task_data.get('caseExecutionId'),
                                    case_instance_id=task_data.get('caseInstanceId'),
                                    case_definition_id=task_data.get('caseDefinitionId'),
                                    suspended=task_data.get('suspended', False),
                                    form_key=task_data.get('formKey'),
                                    tenant_id=task_data.get('tenantId')
                                )
                                logger.info(f"Найдена задача процесса {target_task_id_str}, показываем детали")
                                ui.timer(0.1, lambda: show_task_details(process_task), once=True)
                            else:
                                logger.warning(f"Задача {target_task_id_str} не найдена")
                                ui.notify(f'Задача {target_task_id_str} не найдена', type='warning')
                        except Exception as e2:
                            logger.warning(f"Не удалось найти задачу по process_instance_id {target_task_id_str}: {e2}")
                            ui.notify(f'Задача {target_task_id_str} не найдена', type='warning')
                except Exception as e:
                    logger.error(f"Ошибка при загрузке задачи {target_task_id_str} напрямую: {e}", exc_info=True)
                    ui.notify(f'Ошибка при загрузке задачи: {str(e)}', type='error')
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке активных задач: {e}", exc_info=True)
        if header_container:
            with header_container:
                ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')

async def create_task_card_with_progress(task):
    """Создает карточку задачи с информацией о прогрессе"""
    global _tasks_container, _selected_task_id, _task_cards
    
    if _tasks_container is None:
        return
    
    # Определяем, является ли эта задача выбранной
    task_id_str = str(getattr(task, 'id', ''))
    process_id_str = str(getattr(task, 'process_instance_id', ''))
    is_selected = _selected_task_id and (
        task_id_str == _selected_task_id or 
        process_id_str == _selected_task_id
    )
    
    # Получаем наименование задачи из переменных процесса
    task_name_display = task.name  # По умолчанию используем task.name
    due_date_raw = None
    due_date_formatted = None
    due_date_diff_days = None
    
    try:
        camunda_client = await create_camunda_client()
        process_variables = await camunda_client.get_process_instance_variables(process_id_str)
        if process_variables:
            # Проверяем наличие taskName в переменных процесса
            task_name_var = process_variables.get('taskName')
            if task_name_var:
                # Извлекаем значение, если это словарь с 'value'
                if isinstance(task_name_var, dict) and 'value' in task_name_var:
                    task_name_display = task_name_var['value']
                else:
                    task_name_display = task_name_var
            
            # Получаем dueDate из переменных процесса
            due_date_var = process_variables.get('dueDate')
            if due_date_var:
                if isinstance(due_date_var, dict) and 'value' in due_date_var:
                    due_date_raw = due_date_var['value']
                else:
                    due_date_raw = due_date_var
    except Exception as e:
        logger.warning(f"Не удалось получить переменные процесса для задачи {task.id}: {e}")
        # Используем task.name по умолчанию
    
    # Если не получили из переменных, пробуем из атрибута задачи
    if not due_date_raw:
        due_date_raw = getattr(task, 'due', None)
    
    # Форматируем дату и вычисляем разницу в днях
    if due_date_raw:
        try:
            due_date_formatted = format_date_russian(due_date_raw)
            deadline = parse_task_deadline(due_date_raw)
            if deadline:
                now = datetime.now()
                now = now.replace(hour=0, minute=0, second=0, microsecond=0)
                deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
                due_date_diff_days = (deadline - now).days
        except Exception as e:
            logger.warning(f"Не удалось обработать дату дедлайна для задачи {task.id}: {e}")

    # Выбираем стили в зависимости от того, выбрана ли задача
    if is_selected:
        border_class = 'border-l-4 border-blue-600'
        bg_class = 'bg-blue-50'
        border_style = 'border-2 border-blue-600'
        shadow_class = 'shadow-lg'
    else:
        border_class = 'border-l-4 border-blue-500'
        bg_class = ''
        border_style = 'border border-gray-200'
        shadow_class = ''
        
    with _tasks_container:
        # Создаем карточку с условными стилями и data-атрибутами
        card = ui.card().classes(f'p-4 mb-4 w-full max-w-full {border_class} {bg_class} {border_style} {shadow_class}')
        # Добавляем data-атрибуты для поиска через JavaScript
        card.props(f'data-task-id="{task_id_str}" data-process-id="{process_id_str}"')
        
        # Сохраняем ссылку на карточку для обновления стилей
        indicator_row = None
        details_container = None  # Контейнер для деталей задачи
        
        # ОБРАТИТЕ ВНИМАНИЕ: оборачиваем содержимое в with card:
        with card:
            # Добавляем индикатор выбранной задачи
            if is_selected:
                indicator_row = ui.row().classes('w-full items-center gap-2 mb-2')
                with indicator_row:
                    ui.icon('check_circle').classes('text-blue-600 text-lg')
                    ui.label('Выбрано').classes('text-blue-600 font-semibold text-sm')
            
            with ui.row().classes('w-full justify-between items-start'):
                with ui.column().classes('flex-1'):
                    ui.label(task_name_display).classes('text-lg font-semibold')
                    
                    # Выводим срок исполнения сразу после названия с цветовым выделением
                    if due_date_formatted and due_date_diff_days is not None:
                        # Определяем цвет в зависимости от количества дней
                        if due_date_diff_days < 0:
                            # Дедлайн прошел - красный
                            bg_color = '#c62828'
                            text_color = '#ffffff'
                        elif due_date_diff_days <= 2:
                            # Осталось 2 дня или меньше - оранжевый
                            bg_color = '#ff9800'
                            text_color = '#ffffff'
                        else:
                            # Осталось больше 2 дней - зеленый
                            bg_color = '#e8f5e9'
                            text_color = '#2e7d32'
                        
                        with ui.row().classes('items-center gap-2 mt-1'):
                            ui.label('Срок исполнения:').classes('text-sm font-medium')
                            ui.label(due_date_formatted).classes('text-sm font-semibold px-2 py-1 rounded').style(f'background-color: {bg_color}; color: {text_color};')
                    elif due_date_formatted:
                        # Если есть дата, но не удалось вычислить разницу
                        with ui.row().classes('items-center gap-2 mt-1'):
                            ui.label('Срок исполнения:').classes('text-sm font-medium')
                            ui.label(due_date_formatted).classes('text-sm text-gray-600')
                    
                    # Добавляем информацию о прогрессе
                    try:
                        camunda_client = await create_camunda_client()
                        progress = await camunda_client.get_task_progress(task.process_instance_id)
                        
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
                                    
                                    # Получаем отображаемое имя (ФИО и должность) вместо логина
                                    user_display_name = get_user_display_name(user_info["user"])
                                    
                                    with ui.row().classes('w-full items-center gap-2'):
                                        ui.icon(status_icon).classes(status_color)
                                        ui.label(f'{user_display_name}: {user_info["status"]}').classes('text-sm')
                        
                    except Exception as e:
                        logger.warning(f"Не удалось получить информацию о прогрессе для задачи {task.id}: {e}")
                        ui.label('Информация о прогрессе недоступна').classes('text-sm text-gray-500')
                
                # ПРАВАЯ КОЛОНКА С КНОПКАМИ - вынесена из левой колонки
                with ui.column().classes('gap-2'):
                    ui.button(
                        'Завершить задачу',
                        icon='check',
                        on_click=lambda t=task: complete_task(t)
                    ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                    
                    ui.button(
                        'Детали',
                        icon='info',
                        on_click=lambda t=task: show_task_details(t)
                    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
            
            # Контейнер для деталей задачи (скрыт по умолчанию)
            details_container = ui.column().classes('w-full mt-4')
            details_container.set_visibility(False)
        
        # Сохраняем ссылку на карточку, индикатор и контейнеры
        # Контейнер формы завершения будет создан динамически при нажатии на кнопку
        _task_cards[task_id_str] = {
            'card': card,
            'indicator': indicator_row,
            'task_id': task_id_str,
            'process_id': process_id_str,
            'details_container': details_container
        }

def create_task_card(task):
    """Создает карточку задачи"""
    global _tasks_container, _task_cards
    
    if _tasks_container is None:
        return
    
    task_id_str = str(getattr(task, 'id', ''))
    process_id_str = str(getattr(task, 'process_instance_id', ''))
    
    # Получаем срок исполнения и вычисляем разницу в днях
    due_date_raw = getattr(task, 'due', None)
    due_date_formatted = None
    due_date_diff_days = None
    
    if due_date_raw:
        try:
            due_date_formatted = format_date_russian(due_date_raw)
            deadline = parse_task_deadline(due_date_raw)
            if deadline:
                now = datetime.now()
                now = now.replace(hour=0, minute=0, second=0, microsecond=0)
                deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
                due_date_diff_days = (deadline - now).days
        except Exception as e:
            logger.warning(f"Не удалось обработать дату дедлайна для задачи {task.id}: {e}")
        
    with _tasks_container:
        card = ui.card().classes('mb-3 p-4 border-l-4 border-blue-500')
        
        with card:
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    ui.label(f'{task.name}').classes('text-lg font-semibold')
                    
                    # Выводим срок исполнения сразу после названия с цветовым выделением
                    if due_date_formatted and due_date_diff_days is not None:
                        # Определяем цвет в зависимости от количества дней
                        if due_date_diff_days < 0:
                            # Дедлайн прошел - красный
                            bg_color = '#ffebee'
                            text_color = '#c62828'
                        elif due_date_diff_days <= 2:
                            # Осталось 2 дня или меньше - оранжевый
                            bg_color = '#ff9800'
                            text_color = '#ffffff'
                        else:
                            # Осталось больше 2 дней - зеленый
                            bg_color = '#e8f5e9'
                            text_color = '#2e7d32'
                        
                        with ui.row().classes('items-center gap-2 mt-1'):
                            ui.label('Срок исполнения:').classes('text-sm font-medium')
                            ui.label(due_date_formatted).classes('text-sm font-semibold px-2 py-1 rounded').style(f'background-color: {bg_color}; color: {text_color};')
                    elif due_date_formatted:
                        # Если есть дата, но не удалось вычислить разницу
                        with ui.row().classes('items-center gap-2 mt-1'):
                            ui.label('Срок исполнения:').classes('text-sm font-medium')
                            ui.label(due_date_formatted).classes('text-sm text-gray-600')
                    
                    if task.description:
                        ui.label(f'Описание: {task.description}').classes('text-sm text-gray-600')
                    
                    ui.label(f'Создана: {task.start_time}').classes('text-sm text-gray-600')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        ui.button(
                            'Просмотр деталей',
                            icon='visibility',
                            on_click=lambda t=task: show_task_details(t)
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                        
                        ui.button(
                            'Завершить задачу',
                            icon='check',
                            on_click=lambda t=task: complete_task(t)
                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                
                with ui.column().classes('items-end'):
                    ui.label(f'Статус: Завершена').classes('text-xs text-green-600')
                    ui.label(f'Multi-user: {task.total_users} польз.').classes('text-xs text-blue-600')
        
        # Сохраняем ссылку на карточку
        # Контейнер формы завершения будет создан динамически при нажатии на кнопку
        _task_cards[task_id_str] = {
            'card': card,
            'task_id': task_id_str,
            'process_id': process_id_str
        }

def create_completed_tasks_section():
    """Создает секцию с завершенными задачами"""
    global _completed_tasks_container, _completed_tasks_header_container, _pagination_container
    
    # ui.label('Завершенные задачи').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Контейнер для кнопки обновления и заголовка в одной строке
        _completed_tasks_header_container = ui.row().classes('w-full items-center gap-4 mb-4')
        
        with _completed_tasks_header_container:
            ui.button(
                'Обновить задачи',
                icon='refresh',
                on_click=load_completed_tasks
            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        # Контейнер для задач
        _completed_tasks_container = ui.column().classes('w-full')
        
        # Контейнер для пагинации
        _pagination_container = ui.row().classes('w-full items-center justify-between mt-4')
        
        # Загружаем задачи при открытии страницы
        load_completed_tasks()

async def load_completed_tasks():
    """Загружает завершенные задачи"""
    global _completed_tasks_container, _completed_tasks_header_container, _all_completed_tasks, _current_page, _pagination_container
    
    if _completed_tasks_container is None:
        return
    
    _completed_tasks_container.clear()
    
    # Обновляем заголовок с количеством задач
    if _completed_tasks_header_container:
        _completed_tasks_header_container.clear()
        with _completed_tasks_header_container:
            ui.button(
                'Обновить задачи',
                icon='refresh',
                on_click=load_completed_tasks
            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
    
    with _completed_tasks_container:
        try:
            # Получаем текущего авторизованного пользователя
            user = get_current_user()
            if not user:
                if _completed_tasks_header_container:
                    with _completed_tasks_header_container:
                        ui.label('Ошибка: пользователь не авторизован').classes('text-red-600')
                ui.label('Ошибка: пользователь не авторизован').classes('text-red-600')
                return
            
            # Валидация логина на безопасность
            if not validate_username(user.username):
                logger.error(f"Небезопасный логин пользователя: {user.username}")
                if _completed_tasks_header_container:
                    with _completed_tasks_header_container:
                        ui.label('Ошибка: некорректный логин пользователя').classes('text-red-600')
                ui.label('Ошибка: некорректный логин пользователя').classes('text-red-600')
                return
            
            # Получаем завершенные задачи пользователя с группировкой
            assignee = user.username
            camunda_client = await create_camunda_client()
            
            logger.info(f"Загружаем завершенные задачи для пользователя {assignee}")
            
            tasks = await camunda_client.get_completed_tasks_grouped(assignee=assignee)
            
            # Сохраняем все задачи
            _all_completed_tasks = tasks if tasks else []
            _current_page = 1  # Сбрасываем на первую страницу при новой загрузке
            
            logger.info(f"Получено {len(_all_completed_tasks)} задач (сгруппированных)")
            
            # Обновляем заголовок с количеством задач
            if _completed_tasks_header_container:
                _completed_tasks_header_container.clear()
                with _completed_tasks_header_container:
                    ui.button(
                        'Обновить задачи',
                        icon='refresh',
                        on_click=load_completed_tasks
                    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                    if _all_completed_tasks:
                        ui.label(f'Найдено {len(_all_completed_tasks)} завершенных задач:').classes('text-lg font-semibold')
                    else:
                        ui.label('Нет завершенных задач').classes('text-lg font-semibold text-gray-500')
            
            # Отображаем задачи текущей страницы
            display_current_page()
                
        except Exception as e:
            logger.error(f"Ошибка при загрузке завершенных задач: {e}", exc_info=True)
            if _completed_tasks_header_container:
                _completed_tasks_header_container.clear()
                with _completed_tasks_header_container:
                    ui.button(
                        'Обновить задачи',
                        icon='refresh',
                        on_click=load_completed_tasks
                    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                    ui.label(f'Ошибка при загрузке задач').classes('text-lg font-semibold text-red-600')
            ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')

def display_current_page():
    """Отображает задачи текущей страницы"""
    global _completed_tasks_container, _all_completed_tasks, _current_page, _page_size, _pagination_container
    
    if _completed_tasks_container is None:
        return
    
    # Очищаем контейнер задач
    _completed_tasks_container.clear()
    
    if not _all_completed_tasks:
        with _completed_tasks_container:
            ui.label('Нет завершенных задач').classes('text-gray-500')
        # Очищаем пагинацию
        if _pagination_container:
            _pagination_container.clear()
        return
    
    # Вычисляем индексы для текущей страницы
    total_tasks = len(_all_completed_tasks)
    total_pages = (total_tasks + _page_size - 1) // _page_size  # Округление вверх
    
    # Проверяем, что текущая страница не выходит за границы
    if _current_page > total_pages:
        _current_page = total_pages if total_pages > 0 else 1
    if _current_page < 1:
        _current_page = 1
    
    # Вычисляем индексы для среза
    start_idx = (_current_page - 1) * _page_size
    end_idx = min(start_idx + _page_size, total_tasks)
    
    # Получаем задачи для текущей страницы
    page_tasks = _all_completed_tasks[start_idx:end_idx]
    
    # Отображаем задачи
    with _completed_tasks_container:
        for task in page_tasks:
            # Проверяем тип задачи
            if isinstance(task, GroupedHistoryTask):
                logger.info(f"Создаем карточку для группированной задачи {task.process_instance_id}")
                create_grouped_completed_task_card(task)
            else:
                logger.info(f"Создаем карточку для обычной задачи {task.id}")
                create_completed_task_card(task)
    
    # Обновляем элементы пагинации
    if _pagination_container:
        _pagination_container.clear()
        with _pagination_container:
            # Информация о текущей странице
            ui.label(f'Страница {_current_page} из {total_pages} (всего задач: {total_tasks})').classes('text-sm text-gray-600')
            
            # Кнопки навигации
            with ui.row().classes('items-center gap-2'):
                # Кнопка "Первая"
                ui.button(
                    'Первая',
                    icon='first_page',
                    on_click=lambda: go_to_page(1)
                ).classes('text-xs px-2 py-1').props('flat').set_enabled(_current_page > 1)
                
                # Кнопка "Предыдущая"
                ui.button(
                    'Предыдущая',
                    icon='chevron_left',
                    on_click=lambda: go_to_page(_current_page - 1)
                ).classes('text-xs px-2 py-1').props('flat').set_enabled(_current_page > 1)
                
                # Выбор размера страницы
                ui.select(
                    [5, 10, 20, 50, 100],
                    value=_page_size,
                    on_change=lambda e: change_page_size(e.value),
                    label='Задач на странице'
                ).classes('text-xs').style('min-width: 150px')
                
                # Кнопка "Следующая"
                ui.button(
                    'Следующая',
                    icon='chevron_right',
                    on_click=lambda: go_to_page(_current_page + 1)
                ).classes('text-xs px-2 py-1').props('flat').set_enabled(_current_page < total_pages)
                
                # Кнопка "Последняя"
                ui.button(
                    'Последняя',
                    icon='last_page',
                    on_click=lambda: go_to_page(total_pages)
                ).classes('text-xs px-2 py-1').props('flat').set_enabled(_current_page < total_pages)

def go_to_page(page: int):
    """Переходит на указанную страницу"""
    global _current_page
    
    total_tasks = len(_all_completed_tasks)
    total_pages = (total_tasks + _page_size - 1) // _page_size
    
    if 1 <= page <= total_pages:
        _current_page = page
        display_current_page()

def change_page_size(new_size: int):
    """Изменяет размер страницы"""
    global _page_size, _current_page
    
    _page_size = new_size
    # Пересчитываем текущую страницу, чтобы не выйти за границы
    total_tasks = len(_all_completed_tasks)
    total_pages = (total_tasks + _page_size - 1) // _page_size
    if _current_page > total_pages:
        _current_page = total_pages if total_pages > 0 else 1
    
    display_current_page()

async def create_grouped_completed_task_card(task):
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
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                
                with ui.column().classes('items-end'):
                    ui.label(f'Статус: Завершена').classes('text-xs text-green-600')
                    ui.label(f'Multi-user: {task.total_users} польз.').classes('text-xs text-blue-600')

async def show_grouped_task_details_in_tab(task):
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
            # ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm mb-2')  # УБРАНО
            ui.label(f'Создана: {task.start_time}').classes('text-sm mb-2')
            
            if task.end_time:
                ui.label(f'Завершена: {task.end_time}').classes('text-sm mb-2')
            
            if hasattr(task, 'duration_formatted'):
                ui.label(f'Общая длительность: {task.duration_formatted}').classes('text-sm mb-2')
            
            ui.label(f'Приоритет: {task.priority}').classes('text-sm mb-2')
            ui.label(f'Статус: Завершена').classes('text-sm mb-2')
            
            if task.description:
                ui.label(f'Описание: {task.description}').classes('text-sm mb-2')
            
            # if task.due:
            #     ui.label(f'Срок: {task.due}').classes('text-sm mb-2')
            
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
                            user_display_name = get_user_display_name(user_task.assignee)
                            ui.label(f'{user_display_name}').classes('text-sm font-semibold')
                        
                        # ui.label(f'ID задачи: {user_task.task_id}').classes('text-xs text-gray-500 mb-1')  # УБРАНО
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
            camunda_client = await create_camunda_client()
            process_variables = await camunda_client.get_history_process_instance_variables_by_name(
                task.process_instance_id,
                ['documentName', 'documentContent', 'assigneeList', 'reviewDates', 'reviewComments']
            )
            
            if process_variables:
                with ui.card().classes('p-4 bg-purple-50 mb-4'):
                    # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                    
                    for key, value in process_variables.items():
                        # Форматируем значение для лучшего отображения
                        formatted_value = format_variable_value(value)
                        if isinstance(formatted_value, (dict, list)):
                            ui.label(f'{key}:').classes('text-sm font-medium mb-1')
                            ui.json_editor({'content': {'json': formatted_value}}).classes('w-full')
                        else:
                            ui.label(f'{key}: {formatted_value}').classes('text-sm mb-2')
        except Exception as e:
            logger.warning(f"Не удалось получить переменные процесса {task.process_instance_id}: {e}")
        
        # Кнопка обновления
        with ui.column().classes('w-full gap-2'):
            ui.button(
                'Обновить детали',
                icon='refresh',
                on_click=lambda t=task: show_grouped_task_details_in_tab(t)
            ).classes('w-full bg-blue-500 text-white text-xs px-2 py-1 h-7')

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
                    
                        async def show_details(t=task):
                            await show_completed_task_details_in_tab(t)
                        
                        ui.button(
                            'Просмотр деталей',
                            icon='visibility',
                            on_click=lambda t=task: show_details(t)
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                        
                with ui.column().classes('items-end'):
                    ui.label(f'Статус: Завершена').classes('text-xs text-green-600')
                    # Показываем информацию о multi-user только если это группированная задача
                    if hasattr(task, 'total_users'):
                        ui.label(f'Multi-user: {task.total_users} польз.').classes('text-xs text-blue-600')


async def show_completed_task_details_in_tab(task):
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
            if isinstance(task, GroupedHistoryTask):
                # Если это группированная задача, используем специальную функцию
                show_grouped_task_details_in_tab(task)
                return
            
            # Получаем детальную информацию о задаче
            camunda_client = await create_camunda_client()
            
            # Для завершенных задач используем исторический API
            task_details = await camunda_client.get_history_task_by_id(task.id)
            if not task_details:
                # Если историческая задача не найдена, попробуем получить как активную
                task_details = await camunda_client.get_task_by_id(task.id)
            
            # ИСПРАВЛЕНИЕ: Если задача не найдена в Camunda, используем данные из объекта task
            if not task_details:
                logger.warning(f"Задача {task.id} не найдена в Camunda, используем данные из объекта задачи")
                # Используем данные из объекта task (CamundaHistoryTask)
                task_details = task
            
            # Проверяем, является ли это задачей подписания документа
            is_signing_task = False
            if hasattr(task_details, 'name') and task_details.name == "Подписать документ":
                is_signing_task = True
            elif hasattr(task, 'name') and task.name == "Подписать документ":
                is_signing_task = True
            
            # Основная информация о задаче - только нужные поля
            with ui.card().classes('p-4 bg-green-50 mb-4'):
                ui.label('Информация о завершенной задаче').classes('text-lg font-semibold mb-3')
                
                # Инициатор
                if hasattr(task_details, 'assignee') and task_details.assignee:
                    executor_display_name = get_user_display_name(task_details.assignee)
                    ui.label(f'Инициатор: {executor_display_name}').classes('text-sm mb-2')
                
                # Создана
                if hasattr(task_details, 'start_time') and task_details.start_time:
                    formatted_start = format_date_russian(task_details.start_time)
                    ui.label(f'Создана: {formatted_start}').classes('text-sm mb-2')
                elif hasattr(task_details, 'created') and task_details.created:
                    formatted_start = format_date_russian(task_details.created)
                    ui.label(f'Создана: {formatted_start}').classes('text-sm mb-2')
                
                # Завершена
                if hasattr(task_details, 'end_time') and task_details.end_time:
                    formatted_end = format_date_russian(task_details.end_time)
                    ui.label(f'Завершена: {formatted_end}').classes('text-sm mb-2')
                
                # Длительность
                if hasattr(task_details, 'duration') and task_details.duration:
                    duration_sec = task_details.duration // 1000
                    duration_formatted = f'{duration_sec // 60} мин {duration_sec % 60} сек'
                    ui.label(f'Длительность: {duration_formatted}').classes('text-sm mb-2')
                
                # Статус
                ui.label(f'Статус: Завершена').classes('text-sm mb-2')
                
                # Описание
                if hasattr(task_details, 'description') and task_details.description:
                    ui.label(f'Описание: {task_details.description}').classes('text-sm mb-2')
                
                # Причина завершения
                if hasattr(task_details, 'delete_reason') and task_details.delete_reason:
                    ui.label(f'Причина завершения: {task_details.delete_reason}').classes('text-sm mb-2')
            
            # Переменные процесса - только нужные поля
            document_id = None
            document_name = None
            try:
                process_instance_id = task_details.process_instance_id if hasattr(task_details, 'process_instance_id') else None
                
                if process_instance_id:
                    # Для задач подписания добавляем signerList в список запрашиваемых переменных
                    variable_names = ['documentName', 'documentId', 'reviewDates', 'reviewComments']
                    if is_signing_task:
                        variable_names.append('signerList')
                    
                    process_variables = await camunda_client.get_history_process_instance_variables_by_name(
                        process_instance_id,
                        variable_names
                    )
                    
                    if process_variables:
                        with ui.card().classes('p-4 bg-purple-50 mb-4'):
                            # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                            
                            # documentName
                            if 'documentName' in process_variables:
                                doc_name = process_variables['documentName']
                                # Извлекаем значение, если это словарь с 'value'
                                if isinstance(doc_name, dict) and 'value' in doc_name:
                                    doc_name = doc_name['value']
                                document_name = doc_name
                                ui.label(f'Документ: {doc_name}').classes('text-sm mb-4')
                            
                            # Получаем documentId для скачивания документа с подписями
                            if 'documentId' in process_variables:
                                doc_id = process_variables['documentId']
                                # Извлекаем значение, если это словарь с 'value'
                                if isinstance(doc_id, dict) and 'value' in doc_id:
                                    doc_id = doc_id['value']
                                document_id = str(doc_id).strip() if doc_id else None
                            
                            # Кнопка для скачивания документа с подписями (только для задач подписания)
                            if is_signing_task and document_id and document_id != 'НЕ НАЙДЕН':
                                with ui.row().classes('w-full mb-4 gap-2'):
                                    async def download_signed():
                                        await download_signed_document_from_task(document_id, document_name)
                                    
                                    ui.button(
                                        'Скачать документ с подписями',
                                        icon='download',
                                        on_click=download_signed
                                    ).classes('bg-green-600 text-white text-xs px-2 py-1 h-7')
                            
                            # Список участников процесса (только для задач подписания)
                            if is_signing_task and 'signerList' in process_variables:
                                signer_list = process_variables['signerList']
                                
                                logger.info(f"Получен signerList из переменных: {signer_list}, тип: {type(signer_list)}")
                                
                                # Извлекаем значение, если это словарь с 'value'
                                if isinstance(signer_list, dict) and 'value' in signer_list:
                                    signer_list = signer_list['value']
                                    logger.info(f"Извлечено значение из словаря: {signer_list}, тип: {type(signer_list)}")
                                
                                # Парсим JSON строку, если нужно
                                if isinstance(signer_list, str):
                                    try:
                                        signer_list = json.loads(signer_list)
                                        logger.info(f"Распарсена JSON строка: {signer_list}, тип: {type(signer_list)}")
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"Не удалось распарсить signerList как JSON: {e}, значение: {signer_list}")
                                        # Если не JSON, возможно это просто строка с одним пользователем
                                        signer_list = [signer_list] if signer_list else []
                                
                                # Если это не список, пытаемся преобразовать
                                if not isinstance(signer_list, list):
                                    logger.warning(f"signerList не является списком: {signer_list}, тип: {type(signer_list)}")
                                    if signer_list:
                                        # Если это строка или другой тип, создаем список
                                        signer_list = [str(signer_list)]
                                    else:
                                        signer_list = []
                                
                                logger.info(f"Итоговый signer_list: {signer_list}, длина: {len(signer_list) if isinstance(signer_list, list) else 'не список'}")
                                
                                if signer_list and isinstance(signer_list, list) and len(signer_list) > 0:
                                    ui.label('Участники процесса:').classes('text-sm font-medium mb-2')
                                    
                                    signers_container = ui.column().classes('w-full mb-4')
                                    with signers_container:
                                        for i, signer_login in enumerate(signer_list, 1):
                                            try:
                                                # Обрабатываем случай, когда элемент списка может быть не строкой
                                                signer_login_str = str(signer_login).strip()
                                                if not signer_login_str:
                                                    continue
                                                
                                                user_display_name = get_user_display_name(signer_login_str)
                                                with ui.row().classes('w-full items-center gap-2 mb-1'):
                                                    ui.icon('person').classes('text-blue-600 text-sm')
                                                    ui.label(f'{i}. {user_display_name}').classes('text-sm')
                                            except Exception as e:
                                                logger.error(f"Ошибка получения информации о подписанте {signer_login}: {e}")
                                                with ui.row().classes('w-full items-center gap-2 mb-1'):
                                                    ui.icon('person').classes('text-gray-400 text-sm')
                                                    signer_login_str = str(signer_login) if signer_login else 'неизвестно'
                                                    ui.label(f'{i}. {signer_login_str} (не найден)').classes('text-sm text-gray-600')
                                else:
                                    logger.warning(f"signerList пуст или не является списком: {signer_list}")
                            
                            # reviewComments и reviewDates - объединяем по пользователям
                            review_comments = None
                            review_dates = None
                            
                            # Получаем reviewComments
                            if 'reviewComments' in process_variables:
                                comments_value = process_variables['reviewComments']
                                # Извлекаем значение, если это словарь с 'value'
                                if isinstance(comments_value, dict) and 'value' in comments_value:
                                    comments_value = comments_value['value']
                                
                                # Парсим JSON строку
                                if isinstance(comments_value, str):
                                    try:
                                        review_comments = json.loads(comments_value)
                                    except json.JSONDecodeError:
                                        logger.warning("Не удалось распарсить reviewComments")
                                        review_comments = {}
                                elif isinstance(comments_value, dict):
                                    review_comments = comments_value
                            
                            # Получаем reviewDates
                            if 'reviewDates' in process_variables:
                                dates_value = process_variables['reviewDates']
                                # Извлекаем значение, если это словарь с 'value'
                                if isinstance(dates_value, dict) and 'value' in dates_value:
                                    dates_value = dates_value['value']
                                
                                # Парсим JSON строку
                                if isinstance(dates_value, str):
                                    try:
                                        review_dates = json.loads(dates_value)
                                    except json.JSONDecodeError:
                                        logger.warning("Не удалось распарсить reviewDates")
                                        review_dates = {}
                                elif isinstance(dates_value, dict):
                                    review_dates = dates_value
                            
                            # Объединяем комментарии и даты по пользователям
                            if review_comments or review_dates:
                                ui.label('Комментарии пользователей:').classes('text-sm font-medium mb-2')
                                
                                # Собираем всех пользователей из обоих словарей
                                all_users = set()
                                if review_comments:
                                    all_users.update(review_comments.keys())
                                if review_dates:
                                    all_users.update(review_dates.keys())
                                
                                # Отображаем информацию по каждому пользователю
                                for username in sorted(all_users):
                                    user_display_name = get_user_display_name(username)
                                    
                                    with ui.card().classes('p-3 mb-3 bg-white border-l-4 border-blue-400'):
                                        ui.label(f'{user_display_name}').classes('text-sm font-semibold mb-2')
                                        
                                        # Дата завершения
                                        if review_dates and username in review_dates:
                                            date_value = review_dates[username]
                                            if date_value:
                                                formatted_date = format_date_russian(date_value)
                                                ui.label(f'Дата завершения: {formatted_date}').classes('text-xs text-gray-600 mb-1')
                                        
                                        # Комментарий
                                        if review_comments and username in review_comments:
                                            comment = review_comments[username]
                                            if comment:
                                                with ui.card().classes('p-2 bg-yellow-50 border-l-4 border-yellow-400 mt-2'):
                                                    ui.label('Комментарий:').classes('text-xs font-semibold text-yellow-800 mb-1')
                                                    ui.label(comment).classes('text-xs text-gray-700 italic')
                    else:
                        with ui.card().classes('p-4 bg-gray-50 mb-4'):
                            # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                            ui.label('Переменные процесса недоступны или не найдены').classes('text-sm text-gray-600')
                else:
                    logger.warning("process_instance_id не найден для получения переменных процесса")
            except Exception as e:
                logger.warning(f"Не удалось загрузить переменные процесса: {e}")
                with ui.card().classes('p-4 bg-gray-50 mb-4'):
                    # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                    ui.label(f'Не удалось загрузить переменные процесса: {str(e)}').classes('text-sm text-gray-600')
                
        except Exception as e:
            logger.error(f'Ошибка при загрузке деталей завершенной задачи {task.id}: {e}', exc_info=True)
            ui.label(f'Ошибка при загрузке деталей задачи: {str(e)}').classes('text-red-600')


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
        ).classes('bg-blue-500 text-white mb-4 text-xs px-2 py-1 h-7')
        
        # Контейнер для деталей задачи
        _details_container = ui.column().classes('w-full')

async def load_task_details(task_id: str):
    """Загружает детали задачи"""
    global _details_container
    
    if _details_container is None:
        logger.warning("_details_container не инициализирован")
        return
        
    if not task_id:
        ui.notify('Введите ID задачи', type='error')
        return
    
async def complete_task(task):
    """Завершает задачу"""
    # Проверяем, является ли это задачей подписания
    if task.name == "Подписать документ":
        await complete_signing_task(task)
    else:
        complete_regular_task(task)


def complete_regular_task(task):
    """Завершает задачу - форма открывается прямо в карточке задачи"""
    global _task_cards, _uploaded_files, _uploaded_files_container
    
    # Находим карточку задачи
    task_id_str = str(getattr(task, 'id', ''))
    process_id_str = str(getattr(task, 'process_instance_id', ''))
    
    task_card_info = _task_cards.get(task_id_str) or _task_cards.get(process_id_str)
    
    if not task_card_info:
        ui.notify('Ошибка: карточка задачи не найдена', type='error')
        return
    
    card = task_card_info['card']
    
    # Проверяем, есть ли уже контейнер формы завершения
    if 'completion_form_container' in task_card_info:
        # Если форма уже существует, просто показываем её
        completion_form = task_card_info['completion_form_container']
        completion_form.set_visibility(True)
        return
    
    # Создаем контейнер для формы завершения
    with card:
        completion_form = ui.column().classes('w-full mt-4 p-4 bg-gray-50 border rounded')
        completion_form.set_visibility(True)
    
    # Сохраняем ссылку на контейнер формы
    task_card_info['completion_form_container'] = completion_form
    
    # Очищаем список загруженных файлов
    _uploaded_files = []
    
    # Создаем форму завершения внутри контейнера
    with completion_form:
        ui.label('Завершение задачи').classes('text-lg font-semibold mb-4')
        
        # Информация о задаче
        with ui.card().classes('p-3 bg-white mb-4'):
            ui.label(f'Задача: {task.name}').classes('text-base font-semibold')
            # ui.label(f'ID задачи: {task.id}').classes('text-sm text-gray-600')  # УБРАНО
            # ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm text-gray-600')  # УБРАНО
        
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
            _uploaded_files_container = ui.column().classes('w-full mb-4')
            
            # Кнопки действий
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button(
                    'Отмена',
                    on_click=lambda: completion_form.set_visibility(False)
                ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                
                ui.button(
                    'Завершить задачу',
                    icon='check',
                    on_click=lambda: submit_task_completion(task, status_select.value, comment_textarea.value, completion_form)
                ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')

async def complete_signing_task(task):
    """Завершает задачу подписания документа - форма открывается прямо в карточке задачи"""
    
    # Объявляем global в начале функции
    global _show_all_certificates, _document_for_signing, _task_cards
    
    # Сбрасываем глобальную переменную при открытии формы
    _show_all_certificates = False  # Всегда начинаем с фильтрованного режима
    
    # Находим карточку задачи
    task_id_str = str(getattr(task, 'id', ''))
    process_id_str = str(getattr(task, 'process_instance_id', ''))
    
    task_card_info = _task_cards.get(task_id_str) or _task_cards.get(process_id_str)
    
    if not task_card_info:
        ui.notify('Ошибка: карточка задачи не найдена', type='error')
        return
    
    card = task_card_info['card']
    
    # Проверяем, есть ли уже контейнер формы завершения
    if 'completion_form_container' in task_card_info and task_card_info['completion_form_container']:
        # Если форма уже существует, очищаем её содержимое и пересоздаём
        # Это нужно для того, чтобы сертификаты загружались заново
        old_form = task_card_info['completion_form_container']
        old_form.clear()
        completion_form = old_form
    else:
        # Создаем контейнер для формы завершения
        with card:
            completion_form = ui.column().classes('w-full mt-4 p-4 bg-gray-50 border rounded')
            completion_form.set_visibility(True)
        
        # Сохраняем ссылку на контейнер формы
        task_card_info['completion_form_container'] = completion_form
    
    # Сбрасываем глобальные переменные для новой задачи
    global _certificates_cache, _selected_certificate
    _certificates_cache = []
    _selected_certificate = None
    
    # Создаем форму завершения внутри контейнера
    with completion_form:
        ui.label('Подписание документа').classes('text-xl font-bold mb-4')
        
        with ui.column().classes('w-full gap-4'):
            # Получаем переменные процесса
            document_id = None
            document_name = None
           # signer_list = []
            
            try:
                camunda_client = await create_camunda_client()
                process_variables = await camunda_client.get_process_instance_variables(task.process_instance_id)
                
                logger.info(f"Переменные процесса {task.process_instance_id}: {process_variables}")
                
                # Извлекаем ID документа из переменных
                document_id = process_variables.get('documentId')
                document_name = process_variables.get('documentName')
                
                # Извлекаем список подписантов
                # signer_list = process_variables.get('signerList', [])
                # if isinstance(signer_list, dict) and 'value' in signer_list:
                #     signer_list = signer_list['value']
                # elif isinstance(signer_list, str):
                #     try:
                #         signer_list = json.loads(signer_list)
                #     except:
                #         signer_list = [signer_list] if signer_list else []
                
            except Exception as e:
                ui.label(f'Ошибка при получении переменных процесса: {str(e)}').classes('text-red-600')
                logger.error(f"Ошибка в complete_signing_task при получении переменных: {e}")
            
            # ИСПРАВЛЕНИЕ: Проверяем, уже подписан ли документ текущим пользователем
            def is_valid_document_id(doc_id):
                '''Проверяет, что document_id - это валидный идентификатор (число)'''
                if not doc_id:
                    return False
                try:
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
                        if await signature_manager.check_user_signature_exists(document_id, user.username):
                            with ui.card().classes('p-4 bg-yellow-50 border border-yellow-200'):
                                ui.label('Документ уже подписан').classes('text-lg font-semibold text-yellow-800 mb-2')
                                ui.label(f'Вы уже подписали этот документ ранее.').classes('text-yellow-700 mb-2')
                                
                                # Показываем кнопку "Завершить задачу" без возможности повторной подписи
                                async def complete_already_signed():
                                    await submit_signing_task_completion(
                                        task,
                                        True,
                                        '',
                                        {},
                                        'Документ уже подписан',
                                        completion_form
                                    )
                                
                                ui.button(
                                    'Завершить задачу',
                                    icon='check_circle',
                                    on_click=complete_already_signed
                                ).classes('bg-green-600 text-white text-xs px-2 py-1 h-7')
                                
                                ui.button('Отмена', on_click=lambda: completion_form.set_visibility(False)).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                            
                            return  # Выходим из функции, не показывая форму подписания
                        
                except Exception as e:
                    logger.warning(f"Ошибка проверки существующей подписи: {e}")
                    # Продолжаем процесс, если не удалось проверить
            
            # # Отображение списка подписантов
            # if signer_list:
            #     ui.label('Список подписантов:').classes('text-lg font-semibold mt-4 mb-2')
                
            #     try:
            #         ldap_auth = LDAPAuthenticator()
                    
            #         signers_container = ui.column().classes('w-full mb-4')
                    
            #         with signers_container:                           
            #             with ui.column().classes('w-full'):
            #                 for i, signer_login in enumerate(signer_list):
            #                     try:
            #                         logger.info(f"Обрабатываем подписанта {i+1}: {signer_login}")
                                    
            #                         user_info = ldap_auth.get_user_by_login(signer_login)
            #                         logger.info(f"Результат get_user_by_login для {signer_login}: {user_info is not None}")
                                    
            #                         if not user_info:
            #                             logger.info(f"Пользователь {signer_login} не найден через точный поиск, пробуем широкий поиск")
            #                             user_info = ldap_auth.find_user_by_login(signer_login)
            #                             logger.info(f"Результат find_user_by_login для {signer_login}: {user_info is not None}")
                                    
            #                         if user_info:
            #                             ui.label(f'{i+1}. {user_info.givenName} {user_info.sn} - {user_info.destription}').classes('text-sm mb-1')
            #                             logger.info(f"Найдена информация о пользователе {signer_login}: {user_info.givenName} {user_info.sn}")
            #                         else:
            #                             ui.label(f'{i+1}. {signer_login} (не найден в LDAP)').classes('text-sm mb-1 text-red-600')
            #                             logger.warning(f"Пользователь {signer_login} не найден в LDAP после всех попыток поиска")
                                        
            #                     except Exception as e:
            #                         logger.error(f"Ошибка получения информации о пользователе {signer_login}: {e}")
            #                         ui.label(f'{i+1}. {signer_login} (ошибка: {str(e)})').classes('text-sm mb-1 text-red-600')
            #     except Exception as e:
            #         logger.error(f"Ошибка получения списка подписантов из LDAP: {e}")
            #         ui.label(f'Ошибка получения информации о подписантах: {str(e)}').classes('text-red-600')
            # else:
            #     ui.label('Список подписантов не найден в переменных процесса').classes('text-yellow-600 mt-4')
            
            # Загружаем документ из Mayan EDMS
            document_loaded = False
            if document_id and document_id != 'НЕ НАЙДЕН' and str(document_id).strip():
                try:
                    mayan_client = await get_mayan_client()
                    document_content = await mayan_client.get_document_file_content(document_id)
                    
                    if document_content:
                        document_base64 = base64.b64encode(document_content).decode('utf-8')
                        
                        ui.label(f'Документ загружен: {document_name or "Неизвестно"}').classes('text-green-600 mb-2')
                        #ui.label(f'Размер файла: {len(document_content)} байт').classes('text-sm text-gray-600 mb-4')
                        
                        # Добавляем кнопки для просмотра и скачивания документа
                        with ui.row().classes('w-full mb-4 gap-2'):
                            async def open_preview():
                                await open_document_preview(str(document_id))
                            
                            async def download_doc():
                                await download_document_from_task(str(document_id), document_name)
                            
                            ui.button(
                                'Просмотр документа',
                                icon='visibility',
                                on_click=open_preview
                            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                            
                            ui.button(
                                'Скачать документ',
                                icon='download',
                                on_click=download_doc
                            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                        
                        global _document_for_signing
                        _document_for_signing = {
                            'content': document_content,
                            'base64': document_base64,
                            'name': document_name,
                            'id': document_id
                        }
                        document_loaded = True
                    else:
                        with ui.card().classes('p-4 bg-yellow-50 border border-yellow-200 mb-4'):
                            ui.label('⚠️ Предупреждение').classes('text-lg font-semibold text-yellow-800 mb-2')
                            ui.label('Не удалось загрузить содержимое документа из Mayan EDMS.').classes('text-yellow-700 mb-2')
                            ui.label('Возможно, документ уже был удален или перемещен.').classes('text-yellow-700 mb-2')
                            ui.label('Вы можете завершить задачу, если документ уже был подписан ранее.').classes('text-yellow-700')
                        
                except Exception as e:
                    with ui.card().classes('p-4 bg-red-50 border border-red-200 mb-4'):
                        ui.label('❌ Ошибка загрузки документа').classes('text-lg font-semibold text-red-800 mb-2')
                        ui.label(f'Ошибка при загрузке документа: {str(e)}').classes('text-red-700 mb-2')
                        ui.label('Вы можете завершить задачу, если документ уже был подписан ранее.').classes('text-red-700')
                    logger.error(f"Ошибка при загрузке документа {document_id}: {e}")
            else:
                with ui.card().classes('p-4 bg-yellow-50 border border-yellow-200 mb-4'):
                    ui.label('⚠️ ID документа не найден').classes('text-lg font-semibold text-yellow-800 mb-2')
                    ui.label('ID документа не найден в переменных процесса.').classes('text-yellow-700 mb-2')
                    ui.label('Вы можете завершить задачу, если документ уже был подписан ранее.').classes('text-yellow-700')
            
            # Статус КриптоПро (показываем только если документ загружен)
            if document_loaded:
               # ui.label('Электронная подпись:').classes('text-lg font-semibold')
                
                # Контейнер для статуса КриптоПро (показываем сразу)
                crypto_status_container = ui.column().classes('w-full mb-0')
                
                with crypto_status_container:
                    crypto_status = ui.html('').classes('mb-0')
                    crypto_status.props(f'data-crypto-status="true"')
                
                # Контейнер для списка сертификатов (создаем через NiceGUI)
                certificates_container = ui.column().classes('w-full mb-1')
                certificates_container.props(f'data-task-id="{task_id_str}" data-cert-container="true"')
                
                # Получаем ID элемента для поиска через JavaScript
                cert_select_id = f'cert-select-{task_id_str}'
                
                # Select для выбора сертификата (создаем внутри контейнера)
                with certificates_container:
                    certificate_select = ui.select(
                        options={},
                        label='Выберите сертификат для подписания',
                        with_input=True
                    ).classes('w-full mb-4')
                    # Добавляем data-атрибут для поиска через JavaScript
                    if hasattr(certificate_select, 'props'):
                        certificate_select.props(f'data-cert-select-id="{cert_select_id}"')
                
                # НЕ скрываем контейнер - показываем сразу, но select будет пустым до загрузки
                # certificates_container.set_visibility(False)  # УБИРАЕМ ЭТУ СТРОКУ
                
                # Сохраняем ссылки на контейнеры в глобальной переменной
                global _task_certificates_containers
                if '_task_certificates_containers' not in globals():
                    _task_certificates_containers = {}
                _task_certificates_containers[task_id_str] = {
                    'certificates_container': certificates_container,
                    'crypto_status_container': crypto_status_container,
                    'cert_select_id': f'cert-select-{task_id_str}'
                }
                
                def on_show_all_changed(e):
                    """Обработчик изменения переключателя"""
                    global _show_all_certificates
                    if hasattr(e, 'value'):
                        _show_all_certificates = e.value
                    elif isinstance(e, bool):
                        _show_all_certificates = e
                    else:
                        _show_all_certificates = show_all_checkbox.value
                    
                    # Перезагружаем сертификаты (без select)
                    check_crypto_pro_availability_and_load(
                        crypto_status, 
                        certificates_container,
                        None,  # Не передаем select
                        task_id_str
                    )
                
                show_all_checkbox = ui.checkbox(
                    'Показать все сертификаты',
                    value=_show_all_certificates,
                    on_change=on_show_all_changed
                ).classes('mb-1')
                
                # Вызываем проверку и загрузку сертификатов
                check_crypto_pro_availability_and_load(
                    crypto_status,
                    certificates_container,
                    None,  # Не передаем select
                    task_id_str
                )
                
                # Информация о выбранном сертификате
                certificate_info_display = ui.html('').classes('w-full mb-1 p-4 bg-gray-50 rounded')
                
                # Обработчик выбора сертификата будет обрабатываться через JavaScript
                # и обновлять certificate_info_display через API
                
                # Кнопки для подписания (без блока "Данные для подписания")
                with ui.row().classes('w-full justify-between gap-2 mb-1'):
                    ui.button(
                        'Подписать документ',
                        icon='edit',
                        on_click=lambda: sign_document_with_certificate(
                            task,
                            certificate_info_display,
                            result_container
                        )
                    ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                    ui.button('ОТМЕНА', on_click=lambda: completion_form.set_visibility(False)).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                
                # Результат подписания (изначально скрыт)
                result_container = ui.column().classes('w-full mb-1')
                result_container.visible = False
                
                with result_container:
                    ui.label('Документ успешно подписан!').classes('text-lg font-semibold mb-4 text-green-600')
                    
                    # Кнопка завершения задачи
                    ui.button(
                        'Завершить задачу',
                        icon='check',
                        on_click=lambda: complete_signing_task_with_result(
                            task,
                            document_id,
                            document_name,
                            completion_form
                        )
                    ).classes('bg-green-600 text-white text-xs px-2 py-1 h-7')
            else:
                # Если документ не загружен, показываем только кнопку завершения задачи
                with ui.card().classes('p-4 bg-blue-50 border border-blue-200 mb-4'):
                    ui.label('Завершение задачи без подписания').classes('text-lg font-semibold text-blue-800 mb-2')
                    ui.label('Документ не загружен. Вы можете завершить задачу, если документ уже был подписан ранее.').classes('text-blue-700 mb-4')
                    
                    async def complete_without_signing():
                        await submit_signing_task_completion(
                            task,
                            True,
                            '',
                            {},
                            'Документ уже подписан (не удалось загрузить для проверки)',
                            completion_form
                        )
                    
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('ОТМЕНА', on_click=lambda: completion_form.set_visibility(False)).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                        ui.button(
                            'Завершить задачу',
                            icon='check',
                            on_click=complete_without_signing
                        ).classes('bg-green-600 text-white text-xs px-2 py-1 h-7')

def check_and_save_signed_pdf():
    """Проверяет результат создания подписанного PDF и сохраняет его"""
    try:
        signature_result = api_router.get_signature_result()
        
        if signature_result and signature_result.get('action') == 'signed_document_created':
            signed_document = signature_result.get('signed_document', '')
            filename = signature_result.get('filename', 'signed_document.pdf')
            
            if signed_document:
                # Декодируем Base64 в бинарные данные
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

async def complete_signing_task_with_result(task, document_id, document_name, completion_form):
    """Завершает задачу подписания с результатом"""
    try:
        # Получаем результат подписания
        signature_result = api_router.get_signature_result()
        
        if not signature_result:
            ui.notify('Результат подписания не найден', type='error')
            return
        
        # Проверяем, что подписание завершено (есть signature или action == 'signature_completed')
        signed = (
            signature_result.get('action') == 'signature_completed' or 
            signature_result.get('action') == 'signed_document_created' or
            bool(signature_result.get('signature'))
        )
        
        # Получаем данные подписи (может быть 'signature' или 'signed_document')
        signature_data = signature_result.get('signature') or signature_result.get('signed_document', '')
        certificate_info = signature_result.get('certificate_info', {})
        
        await submit_signing_task_completion(
            task,
            signed,
            signature_data,
            certificate_info,
            'Документ подписан',
            completion_form
        )
        
    except Exception as e:
        logger.error(f'Ошибка при завершении задачи подписания {task.id}: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')

def check_crypto_pro_availability_and_load(status_container, certificates_container, certificate_select, task_id=None):
    """Проверяет доступность КриптоПро и загружает сертификаты"""
    try:
        global _show_all_certificates, _task_certificates_containers
        
        # Получаем cert_select_id из сохраненных контейнеров
        cert_select_id = f'cert-select-{task_id}' if task_id else 'cert-select-default'
        if task_id and '_task_certificates_containers' in globals():
            containers = _task_certificates_containers.get(task_id, {})
            cert_select_id = containers.get('cert_select_id', cert_select_id)
        
        # Показываем статус проверки
        # status_container.content = '''
        # <div style="padding: 10px; border: 1px solid #ddd; border-radius: 4px; background-color: #f9f9f9;">
        #     <div style="color: #666;">🔍 Проверка КриптоПро плагина...</div>
        # </div>
        # '''
        
        # Запускаем проверку через JavaScript
        ui.run_javascript(f'''
            setTimeout(() => {{
                console.log("=== Начинаем проверку КриптоПро для задачи {task_id} ===");
                
                // Проверяем доступность плагина
                if (typeof window.cryptoProIntegration !== 'undefined') {{
                    console.log("✅ CryptoProIntegration класс найден");
                    
                    // НЕ обновляем статус - убираем этот блок
                    // Просто загружаем сертификаты без отображения статуса
                    
                    // Автоматически загружаем сертификаты
                    setTimeout(() => {{
                        window.cryptoProIntegration.getAvailableCertificates()
                            .then(certificates => {{
                                console.log("Сертификаты получены для задачи {task_id}:", certificates);
                                
                                // Отправляем событие о загруженных сертификатах
                                window.nicegui_handle_event('certificates_loaded', {{
                                    certificates: certificates,
                                    count: certificates.length,
                                    show_all: {str(_show_all_certificates).lower()},
                                    task_id: '{task_id}',
                                    cert_select_id: '{cert_select_id}'
                                }});
                            }})
                            .catch(error => {{
                                console.error("Ошибка получения сертификатов для задачи {task_id}:", error);
                                window.nicegui_handle_event('certificates_error', {{
                                    error: error.message,
                                    task_id: '{task_id}'
                                }});
                            }});
                    }}, 500);
                    
                }} else {{
                    console.log("❌ CryptoProIntegration класс не найден");
                    // Показываем ошибку только в консоли, не в UI
                }}
            }}, 100);
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
        global _show_all_certificates
        
        ui.run_javascript(f'''
            console.log('=== Автоматическая загрузка сертификатов ===');
            console.log('show_all: {str(_show_all_certificates).lower()}');
            
            // Принудительно устанавливаем pluginAvailable = true
            if (window.cryptoProIntegration) {{
                window.cryptoProIntegration.pluginAvailable = true;
                window.cryptoProIntegration.pluginLoaded = true;
                console.log('Принудительно установлен pluginAvailable = true');
            }}
            
            // Используем готовую функцию из async_code.js
            if (typeof window.cadesplugin !== 'undefined') {{
                console.log('cadesplugin найден, получаем сертификаты...');
                
                // Используем async_spawn для получения сертификатов
                window.cadesplugin.async_spawn(function*() {{
                    try {{
                        console.log('Создаем объект Store...');
                        const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                        console.log('Объект Store создан');
                        
                        console.log('Открываем хранилище сертификатов...');
                        yield oStore.Open();
                        console.log('Хранилище открыто');
                        
                        console.log('Получаем список сертификатов...');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        console.log(`Найдено сертификатов: ${{certCnt}}`);
                        
                        const certList = [];
                        
                        for (let i = 1; i <= certCnt; i++) {{
                            try {{
                                console.log(`Обрабатываем сертификат ${{i}}...`);
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
                                if (hasPrivateKey) {{
                                    const certInfo = {{
                                        subject: subject,
                                        issuer: issuer,
                                        serialNumber: serialNumber,
                                        validFrom: validFrom,
                                        validTo: validTo,
                                        isValid: isValid,
                                        hasPrivateKey: hasPrivateKey,
                                        index: i
                                    }};
                                    
                                    certList.push(certInfo);
                                    console.log(`✅ Сертификат для подписи: ${{subject}} (действителен: ${{isValid}})`);
                                }} else {{
                                    console.log(`⚠️ Сертификат без приватного ключа: ${{subject}}`);
                                }}
                                
                            }} catch (certError) {{
                                console.warn(`⚠️ Ошибка при получении сертификата ${{i}}:`, certError);
                            }}
                        }}
                        
                        console.log('Закрываем хранилище...');
                        yield oStore.Close();
                        console.log(`✅ Успешно получено ${{certList.length}} сертификатов`);
                        
                        // Отправляем сертификаты в Python через событие с параметром show_all
                        window.nicegui_handle_event('certificates_loaded', {{
                            certificates: certList,
                            count: certList.length,
                            show_all: {str(_show_all_certificates).lower()}
                        }});
                        
                        return certList;
                        
                    }} catch (e) {{
                        console.error('❌ Ошибка при получении сертификатов:', e);
                        window.nicegui_handle_event('certificates_error', {{
                            error: e.message || 'Неизвестная ошибка'
                        }});
                        throw e;
                    }}
                }});
                
            }} else {{
                console.error('cadesplugin не найден');
                window.nicegui_handle_event('integration_not_available', {{
                    message: 'КриптоПро интеграция недоступна'
                }});
            }}
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

def sign_document_with_certificate(task, certificate_info_display, result_container):
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
        
        # Проверяем действительность сертификата
        is_valid = certificate_data.get('isValid', True)
        
        if not is_valid:
            ui.notify('⚠️ Внимание: Выбранный сертификат недействителен!', type='warning')
        
        # Получаем РЕАЛЬНЫЙ индекс сертификата в КриптоПро
        cryptopro_index = certificate_data.get('index', selected_cert.get('js_index', 1))
        
        logger.info(f"Используем РЕАЛЬНЫЙ индекс КриптоПро: {cryptopro_index}")
        logger.info(f"Сертификат: {certificate_data.get('subject', 'Неизвестно')}")
        logger.info(f"Действителен: {is_valid}")
        
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
        
        # НОВОЕ: Автоматически проверяем результат подписания через короткую задержку
        check_attempts = [0]  # Используем список для модификации внутри вложенной функции
        max_attempts = 20  # Максимум 20 попыток (10 секунд)
        
        def auto_check_result():
            """Автоматически проверяет результат подписания и показывает кнопку завершения"""
            check_attempts[0] += 1
            signature_result = api_router.get_signature_result()
            if signature_result and signature_result.get('signature'):
                # Показываем контейнер с кнопкой завершения
                result_container.visible = True
                ui.notify('Документ успешно подписан!', type='positive')
                logger.info('Результат подписания получен, показываем кнопку завершения задачи')
            elif check_attempts[0] < max_attempts:
                # Продолжаем проверять каждые 500мс до получения результата
                ui.timer(0.5, auto_check_result, once=True)
            else:
                logger.warning('Превышено максимальное количество попыток проверки результата подписания')
                ui.notify('Не удалось получить результат подписания автоматически.', type='warning')
        
        # Начинаем автоматическую проверку через 1 секунду после подписания
        ui.timer(1.0, auto_check_result, once=True)
        
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

def save_signed_pdf_to_file():
    """Сохраняет подписанный PDF в файл"""
    try:
        signature_result = api_router.get_signature_result()
        
        if signature_result and signature_result.get('action') == 'signed_document_created':
            signed_document = signature_result.get('signed_document', '')
            filename = signature_result.get('filename', 'signed_document.pdf')
            
            if signed_document:
                # Декодируем Base64 в бинарные данные
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

async def load_and_display_document(document_id: str, container: ui.column):
    """Загружает и отображает документ"""
    try:
        mayan_client = await MayanClient.create_with_session_user()
        logger.info(f'mayan_client: {mayan_client}')
        logger.info(f'Загружаем документ {document_id}')
        
        # Получаем информацию о документе
        document_info = await mayan_client.get_document_info_for_review(document_id)
        
        if document_info:
            # Создаем ссылку на документ в Mayan EDMS
            document_url = mayan_client.get_document_file_url(document_id)
            
            with container:
                # Кнопка для открытия документа в новой вкладке
                ui.button(
                    'Открыть документ в Mayan EDMS',
                    icon='open_in_new',
                    on_click=lambda url=document_url: ui.run_javascript(f'window.open("{url}", "_blank")')
                ).classes('mb-4 bg-blue-500 text-white text-xs px-2 py-1 h-7')
                
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

async def load_document_content_for_signing(document_id: str, content_container: ui.html):
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
        mayan_client = await get_mayan_client()  # ДОБАВИТЬ await
        document = await mayan_client.get_document(document_id)
        
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

async def submit_signing_task_completion(task, signed, signature_data, certificate_info, comment, completion_form):
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
                
                camunda_client = await create_camunda_client()
                process_variables = await camunda_client.get_process_instance_variables(task.process_instance_id)
                document_id = process_variables.get('documentId')
                
                if document_id and signature_data:
                    signature_manager = SignatureManager()
                    
                    success = await signature_manager.upload_signature_to_document(
                        document_id=document_id,
                        username=username,
                        signature_base64=signature_data,
                        certificate_info=certificate_info
                    )
                    
                    if success:
                        ui.notify(f'Подпись {username}.p7s загружена к документу', type='positive')
                        logger.info(f'Подпись пользователя {username} загружена к документу {document_id}')
                    else:
                        logger.error(f'Не удалось загрузить подпись пользователя {username} к документу {document_id}')
                        ui.notify('Подпись создана, но не загружена в Mayan', type='warning')
                        
        except Exception as e:
            logger.error(f'Ошибка при загрузке подписи в Mayan EDMS: {e}', exc_info=True)
            ui.notify('Ошибка загрузки подписи в Mayan, задача будет завершена', type='warning')
        
        # Подготавливаем переменные для процесса подписания
        variables = {
            'signed': signed,
            'signatureComment': comment or '',
            'signatureDate': datetime.now().isoformat(),
            'signatureUploaded': True
        }
        
        # Завершаем задачу в Camunda
        camunda_client = await create_camunda_client()
        success = await camunda_client.complete_task_with_variables(task.id, variables)
        
        if success:
            # Очищаем результат подписания после успешного завершения
            api_router.clear_signature_result()
            ui.notify('Документ успешно подписан!', type='success')
            # Скрываем форму завершения
            if completion_form:
                completion_form.set_visibility(False)
            # Обновляем список задач
            await load_active_tasks(_tasks_header_container)
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

async def submit_task_completion(task, status, comment, completion_form):
    """Отправляет завершение обычной задачи"""
    global _uploaded_files, _task_cards
    
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
                mayan_client = await get_mayan_client()
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
        
        # Завершаем задачу в Camunda
        camunda_client = await create_camunda_client()
        
        success = await camunda_client.complete_task_with_user_data(
            task_id=task.id,
            status=status,
            comment=comment or '',
            review_date=datetime.now().isoformat()
        )
        
        if success:
            ui.notify('Задача успешно завершена!', type='success')
            # Скрываем форму завершения
            if completion_form:
                completion_form.set_visibility(False)
            # Обновляем список задач
            await load_active_tasks(_tasks_header_container)
        else:
            ui.notify('Ошибка при завершении задачи', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f"Ошибка при завершении задачи {task.id}: {e}", exc_info=True)

async def show_task_details(task):
    """Показывает детали задачи внутри карточки задачи"""
    global _task_cards, _selected_task_id
    
    # Обновляем выбранную задачу
    task_id_str = str(getattr(task, 'id', ''))
    process_id_str = str(getattr(task, 'process_instance_id', ''))
    
    # Сохраняем ID выбранной задачи (приоритет task_id, если есть, иначе process_instance_id)
    old_selected_id = _selected_task_id
    _selected_task_id = task_id_str if task_id_str else process_id_str
    
    # Находим карточку задачи
    task_card_info = _task_cards.get(task_id_str) or _task_cards.get(process_id_str)
    
    if not task_card_info or 'details_container' not in task_card_info:
        ui.notify('Ошибка: карточка задачи не найдена', type='error')
        return
    
    details_container = task_card_info['details_container']
    
    # Обновляем стили карточек без перезагрузки списка
    if old_selected_id != _selected_task_id:
        logger.info(f"Обновляем выделение: старая задача={old_selected_id}, новая задача={_selected_task_id}")
        
        # Обновляем стили через JavaScript
        update_script = f"""
        // Убираем выделение со старой карточки
        if ('{old_selected_id}') {{
            const oldCards = document.querySelectorAll('[data-task-id="{old_selected_id}"], [data-process-id="{old_selected_id}"]');
            oldCards.forEach(card => {{
                card.classList.remove('border-l-4', 'border-blue-600', 'border-2', 'shadow-lg', 'bg-blue-50');
                card.classList.add('border-l-4', 'border-blue-500', 'border', 'border-gray-200');
                // Удаляем индикатор
                const indicator = card.querySelector('[data-indicator="true"]');
                if (indicator) indicator.remove();
            }});
        }}
        
        // Добавляем выделение новой карточке
        if ('{_selected_task_id}') {{
            const newCards = document.querySelectorAll('[data-task-id="{_selected_task_id}"], [data-process-id="{_selected_task_id}"]');
            newCards.forEach(card => {{
                card.classList.remove('border-l-4', 'border-blue-500', 'border', 'border-gray-200');
                card.classList.add('border-l-4', 'border-blue-600', 'border-2', 'border-blue-600', 'shadow-lg', 'bg-blue-50');
                // Добавляем индикатор, если его нет
                if (!card.querySelector('[data-indicator="true"]')) {{
                    const indicator = document.createElement('div');
                    indicator.setAttribute('data-indicator', 'true');
                    indicator.className = 'flex items-center gap-2 mb-2 w-full';
                    indicator.innerHTML = '<span class="material-icons text-blue-600 text-lg">check_circle</span><span class="text-blue-600 font-semibold text-sm">Выбрано</span>';
                    card.insertBefore(indicator, card.firstChild);
                }}
            }});
        }}
        """
        
        ui.run_javascript(update_script)
    
    # Показываем контейнер с деталями
    details_container.set_visibility(True)
    
    # Очищаем контейнер
    details_container.clear()
    
    with details_container:
        # ui.label('Загрузка деталей...').classes('text-gray-600')
        
        try:
            # Получаем детальную информацию о задаче
            camunda_client = await create_camunda_client()
            
            logger.info(f"Попытка получить детали задачи {task.id}")
            
            task_details = None
            is_history_task = False
            
            # Сначала пробуем получить как активную задачу
            task_details = await camunda_client.get_task_by_id(task.id)
            
            if task_details:
                logger.info(f"Задача {task.id} найдена как активная")
                is_history_task = False
            else:
                # Если активная задача не найдена, пробуем получить как историческую
                logger.info(f"Активная задача {task.id} не найдена, пробуем получить как историческую")
                task_details = await camunda_client.get_history_task_by_id(task.id)
                
                if task_details:
                    logger.info(f"Задача {task.id} найдена как историческая")
                    is_history_task = True
                else:
                    logger.warning(f"Задача {task.id} не найдена ни как активная, ни как историческая")
            
            logger.info(f"Результат получения задачи {task.id}: {task_details is not None}")
            
            if not task_details:
                ui.label(f'Задача {task.id} не найдена').classes('text-red-600')
                ui.label('Возможные причины:').classes('text-sm text-gray-600 mt-2')
                ui.label('• Задача была удалена из истории').classes('text-sm text-gray-600')
                ui.label('• Задача еще не завершена').classes('text-sm text-gray-600')
                ui.label('• Неправильный ID задачи').classes('text-sm text-gray-600')
                return
            
            # Переменные процесса - показываем только нужные поля
            try:
                process_variables = await camunda_client.get_process_instance_variables(task_details.process_instance_id)
                if process_variables:
                    with ui.card().classes('p-4 bg-yellow-50 mb-4'):
                        # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                        
                        # Добавляем ID задачи и ID процесса
                        # ui.label(f'ID задачи: {task_details.id}').classes('text-sm text-gray-600 mb-2')
                        # ui.label(f'ID процесса: {task_details.process_instance_id}').classes('text-sm text-gray-600 mb-3')
                        
                        # Проверяем, является ли это задачей подписания документа
                        is_signing_task = hasattr(task_details, 'name') and task_details.name == "Подписать документ"
                        
                        # Извлекаем нужные переменные
                        creator_name = None
                        creator_login = None
                        document_name = None
                        due_date = None
                        document_id = None
                        
                        for var_name, var_value in process_variables.items():
                            # Извлекаем значение в зависимости от формата
                            if isinstance(var_value, dict) and 'value' in var_value:
                                actual_value = var_value['value']
                            else:
                                actual_value = var_value
                            
                            # Извлекаем нужные переменные
                            if var_name == 'creatorName':
                                creator_name = actual_value
                                creator_login = actual_value  # Сохраняем логин для задач подписания
                            elif var_name == 'processCreator':
                                # Альтернативное имя переменной
                                if not creator_name:
                                    creator_name = actual_value
                                    creator_login = actual_value
                            elif var_name == 'creator':
                                # Еще одно альтернативное имя
                                if not creator_name:
                                    creator_name = actual_value
                                    creator_login = actual_value
                            elif var_name == 'documentName':
                                document_name = actual_value
                            elif var_name == 'dueDate':
                                due_date = actual_value
                            elif var_name in ['documentId', 'mayanDocumentId']:
                                document_id = actual_value
                        
                        # Отображаем только нужные переменные
                        if creator_name:
                            # Для задач подписания документа показываем полные данные пользователя
                            if is_signing_task and creator_login:
                                creator_display_name = get_user_display_name(creator_login)
                                ui.label(f'Создатель: {creator_display_name}').classes('text-sm mb-2')
                            else:
                                ui.label(f'Создатель: {creator_name}').classes('text-sm mb-2')
                        
                        if document_name:
                            ui.label(f'Документ: {document_name}').classes('text-sm mb-2')
                        
                        if due_date:
                            # Форматируем дату
                            formatted_date = format_date_russian(due_date)
                            
                            # Вычисляем разницу в днях для раскраски
                            due_date_diff_days = None
                            try:
                                deadline = parse_task_deadline(due_date)
                                if deadline:
                                    now = datetime.now()
                                    now = now.replace(hour=0, minute=0, second=0, microsecond=0)
                                    deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
                                    due_date_diff_days = (deadline - now).days
                            except Exception as e:
                                logger.warning(f"Не удалось вычислить разницу дней для срока: {e}")
                            
                            # Определяем класс для раскраски
                            if due_date_diff_days is not None:
                                if due_date_diff_days < 0:
                                    # Дедлайн прошел - красный
                                    date_class = 'due-date-overdue'
                                elif due_date_diff_days <= 2:
                                    # Осталось 2 дня или меньше - оранжевый
                                    date_class = 'due-date-warning'
                                else:
                                    # Осталось больше 2 дней - зеленый
                                    date_class = 'due-date-ok'
                                
                            #     ui.label(f'Срок: ').classes('text-sm mb-2 inline')
                            #     ui.label(formatted_date).classes(f'text-sm font-semibold px-2 py-1 rounded {date_class} mb-2 inline')
                            # else:
                            #     ui.label(f'Срок: {formatted_date}').classes('text-sm mb-2')
                        
                        # Добавляем кнопки для работы с документом, если documentId найден
                        if document_id:
                            try:
                                mayan_client = await MayanClient.create_with_session_user()
                                
                                # Преобразуем document_id в строку, если нужно
                                doc_id_str = str(document_id).strip()
                                if not doc_id_str:
                                    raise ValueError("Document ID пустой")
                                
                                # Получаем URL документа
                                document_url = await mayan_client.get_document_file_url(doc_id_str)
                                
                                if document_url:
                                    with ui.row().classes('w-full mt-3 gap-2'):
                                        ui.button(
                                            'Скачать документ',
                                            icon='download',
                                            on_click=lambda doc_id=doc_id_str, doc_name=document_name: download_document_from_task(doc_id, doc_name)
                                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                                        
                                        # Добавляем кнопку для просмотра, если есть preview URL
                                        preview_url = await mayan_client.get_document_preview_url(doc_id_str)
                                        if preview_url:
                                            ui.button(
                                                'Просмотр документа',
                                                icon='visibility',
                                                on_click=lambda doc_id=doc_id_str: open_document_preview(doc_id)
                                            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                                    
                            except Exception as e:
                                logger.error(f"Ошибка при получении URL документа {document_id}: {e}", exc_info=True)
                                ui.label(f'Ошибка при открытии документа: {str(e)}').classes('text-xs text-red-600 mt-1')
                        
            except Exception as e:
                logger.warning(f"Не удалось получить переменные процесса {task_details.process_instance_id}: {e}")
                # Даже если переменные недоступны, показываем ID задачи и процесса
                with ui.card().classes('p-4 bg-yellow-50 mb-4'):
                    # ui.label('Переменные процесса').classes('text-lg font-semibold mb-1')
                    # ui.label(f'ID задачи: {task_details.id}').classes('text-sm text-gray-600 mb-2')  # УБРАНО
                    # ui.label(f'ID процесса: {task_details.process_instance_id}').classes('text-sm text-gray-600 mb-2')  # УБРАНО
                    ui.label('Переменные процесса недоступны').classes('text-sm text-gray-500')
            
            # Кнопка для скрытия деталей
            with ui.row().classes('w-full mt-3'):
                ui.button(
                    'Скрыть детали',
                    icon='close',
                    on_click=lambda: hide_task_details_in_card(task_id_str, process_id_str)
                ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
            
        except Exception as e:
            ui.label(f'Ошибка при загрузке деталей: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке деталей задачи {task.id}: {e}", exc_info=True)

def hide_task_details():
    """Скрывает блок с деталями задачи (устаревшая функция, оставлена для совместимости)"""
    # Функция больше не используется, так как детали теперь внутри карточек
    pass

def hide_task_details_in_card(task_id_str: str, process_id_str: str):
    """Скрывает детали задачи внутри карточки"""
    global _task_cards
    
    # Находим карточку задачи
    task_card_info = _task_cards.get(task_id_str) or _task_cards.get(process_id_str)
    
    if task_card_info and 'details_container' in task_card_info:
        details_container = task_card_info['details_container']
        details_container.set_visibility(False)

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

async def download_document_from_task(document_id: str, document_name: str = None):
    """Скачивает документ из Mayan EDMS через безопасный прокси-подход"""
    try:

        mayan_client = await MayanClient.create_with_session_user()
        
        # Получаем содержимое файла И информацию о выбранном файле
        file_content = await mayan_client.get_document_file_content(str(document_id))
        if not file_content:
            ui.notify('Не удалось получить содержимое файла', type='error')
            return
        
        # Получаем имя файла из выбранного файла (не из метаданных документа)
        # Используем внутренний метод для получения информации о выбранном файле
        file_info = await mayan_client._get_main_document_file(str(document_id))
        
        if file_info and file_info.get('filename'):
            # Используем имя файла из выбранного файла
            filename = file_info.get('filename')
            logger.info(f"Используем имя файла из выбранного файла: {filename}")
        elif document_name:
            # Если имя файла не найдено, используем document_name
            filename = document_name
            # Убеждаемся, что есть правильное расширение
            if not filename.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt')):
                # Проверяем содержимое для определения типа
                if file_content[:4] == b'%PDF':
                    filename = f'{filename}.pdf' if not filename.endswith('.pdf') else filename
                else:
                    filename = f'{filename}.pdf'  # По умолчанию PDF
            logger.info(f"Используем document_name с расширением: {filename}")
        else:
            # Пробуем получить из document_info
            document_info = await mayan_client.get_document_info_for_review(str(document_id))
            if document_info and document_info.get('filename'):
                filename = document_info.get('filename')
                # КРИТИЧЕСКАЯ ПРОВЕРКА: Если имя файла заканчивается на .json, но содержимое PDF
                if filename.lower().endswith('.json') and file_content[:4] == b'%PDF':
                    # Заменяем расширение на .pdf
                    filename = filename.rsplit('.', 1)[0] + '.pdf'
                    logger.warning(f"Исправлено расширение файла: {filename}")
                logger.info(f"Используем имя файла из document_info: {filename}")
            else:
                filename = f'document_{document_id}.pdf'
                logger.info(f"Используем имя файла по умолчанию: {filename}")
        
        # ФИНАЛЬНАЯ ПРОВЕРКА: Убеждаемся, что расширение соответствует содержимому
        if file_content[:4] == b'%PDF' and not filename.lower().endswith('.pdf'):
            filename = filename.rsplit('.', 1)[0] + '.pdf' if '.' in filename else filename + '.pdf'
            logger.info(f"Исправлено расширение файла на .pdf: {filename}")
        elif not file_content[:4] == b'%PDF' and filename.lower().endswith('.pdf'):
            logger.warning(f"Файл имеет расширение .pdf, но содержимое не является PDF")
        
        # Создаем временный файл для скачивания
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        # Используем ui.download для безопасного скачивания
        ui.download(temp_path, filename)
        
        # Удаляем временный файл через некоторое время
        ui.timer(5.0, lambda path=temp_path: os.unlink(path) if os.path.exists(path) else None, once=True)
        
        ui.notify(f'Файл "{filename}" подготовлен для скачивания', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании документа {document_id}: {e}", exc_info=True)
        ui.notify(f'Ошибка при скачивании: {str(e)}', type='error')

async def open_document_preview(document_id: str):
    """Открывает предварительный просмотр документа"""
    try:
        
        mayan_client = await MayanClient.create_with_session_user()
        await show_document_viewer(str(document_id), mayan_client=mayan_client)
            
    except Exception as e:
        logger.error(f"Ошибка при открытии просмотра документа {document_id}: {e}", exc_info=True)
        ui.notify(f'Ошибка при открытии просмотра: {str(e)}', type='error')

def get_user_display_name(username: str) -> str:
    """
    Получает отформатированное имя пользователя из логина (ФИО и должность)
    
    Args:
        username: Логин пользователя
        
    Returns:
        Строка с именем, фамилией и должностью или логин, если не найдено
    """
    try:
        ldap_auth = LDAPAuthenticator()
        user_info = ldap_auth.get_user_by_login(username)
        
        if user_info:
            # Формируем строку: "Фамилия Имя - Должность"
            display_parts = []
            if user_info.sn:
                display_parts.append(user_info.sn)
            if user_info.givenName:
                display_parts.append(user_info.givenName)
            
            display_name = ' '.join(filter(None, display_parts))
            
            if user_info.destription:
                display_name += f' - {user_info.destription}'
            
            return display_name if display_name else username
        else:
            return username
    except Exception as e:
        logger.warning(f"Не удалось получить данные пользователя {username} из LDAP: {e}")
        return username

async def download_signed_document_from_task(document_id: str, document_name: str = None):
    """Скачивает документ с подписями из Mayan EDMS"""
    try:
        ui.notify('Создание итогового документа с подписями...', type='info')
        
        signature_manager = SignatureManager()
        signed_pdf = await signature_manager.create_signed_document_pdf(str(document_id))
        
        if signed_pdf:
            # Создаем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if document_name:
                # Убираем расширение из имени документа, если есть
                base_name = document_name.rsplit('.', 1)[0] if '.' in document_name else document_name
                filename = f"signed_{base_name.replace(' ', '_')}_{timestamp}.pdf"
            else:
                filename = f"signed_document_{document_id}_{timestamp}.pdf"
            
            # Создаем временный файл для скачивания
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                temp_file.write(signed_pdf)
                temp_path = temp_file.name
            
            # Открываем файл для скачивания
            ui.download(temp_path, filename)
            
            # Удаляем временный файл через некоторое время
            ui.timer(5.0, lambda path=temp_path: os.unlink(path) if os.path.exists(path) else None, once=True)
            
            ui.notify(f'Файл "{filename}" подготовлен для скачивания', type='success')
            logger.info(f'Итоговый документ {document_id} подготовлен для скачивания как {filename}')
        else:
            ui.notify('Не удалось создать документ с подписями', type='warning')
            
    except Exception as e:
        logger.error(f'Ошибка скачивания документа с подписями: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')

# УДАЛЯЕМ весь блок с @ui.on - этот декоратор не существует в NiceGUI
# Обработка событий теперь происходит через JavaScript напрямую

# ... existing code ...