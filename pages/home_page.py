from nicegui import ui
from datetime import datetime, timezone, timedelta
from typing import Any, Union
from services.camunda_connector import CamundaClient, create_camunda_client
from auth.middleware import get_current_user
from config.settings import config
from utils import validate_username, create_task_detail_data
import asyncio
from components.gantt_chart import create_gantt_chart, parse_task_deadline
from models import GroupedHistoryTask, CamundaTask, CamundaHistoryTask
from utils.date_utils import format_date_russian
from utils.aggrid_locale import AGGGRID_RUSSIAN_LOCALE, apply_aggrid_pagination_localization
from app_logging.logger import get_logger


logger = get_logger(__name__)


def _extract_camunda_variable(variables: dict, key: str) -> str | None:
    """Извлекает значение переменной из формата Camunda API."""
    value = variables.get(key)
    if not value:
        return None
    if isinstance(value, dict) and 'value' in value:
        result = value['value']
    elif isinstance(value, str):
        result = value
    else:
        result = str(value) if value else None
    return result.strip() if result and isinstance(result, str) else result


async def _get_task_process_variables(
    camunda_client: CamundaClient,
    task: Union[CamundaTask, CamundaHistoryTask, GroupedHistoryTask, Any],
    show_finished: bool
) -> dict[str, str | None]:
    """Получает переменные процесса для задачи и возвращает извлечённые данные."""
    result = {
        'due_date': None,
        'task_name': None,
        'task_description': None,
        'document_name': None,
        'document_id': None,
    }
    
    if not hasattr(task, 'process_instance_id') or not task.process_instance_id:
        return result
    
    try:
        var_names = ['dueDate', 'taskName', 'documentName', 'taskDescription', 'documentId', 'mayanDocumentId']
        if show_finished:
            process_variables = await camunda_client.get_history_process_instance_variables_by_name(
                task.process_instance_id, var_names
            )
        else:
            process_variables = await camunda_client.get_process_instance_variables_by_name(
                task.process_instance_id, var_names
            )
        
        result['due_date'] = _extract_camunda_variable(process_variables, 'dueDate')
        result['task_name'] = (
            _extract_camunda_variable(process_variables, 'taskName') or
            _extract_camunda_variable(process_variables, 'documentName')
        )
        result['task_description'] = _extract_camunda_variable(process_variables, 'taskDescription')
        result['document_name'] = _extract_camunda_variable(process_variables, 'documentName')
        result['document_id'] = (
            _extract_camunda_variable(process_variables, 'documentId') or
            _extract_camunda_variable(process_variables, 'mayanDocumentId')
        )
    except Exception as e:
        logger.warning(f'Не удалось получить переменные процесса {task.process_instance_id}: {e}')
    
    return result


def content() -> None:
    """Главная страница с задачами пользователя"""
    # Добавляем CSS стили и вспомогательную функцию JavaScript
    ui.add_head_html('''
        <style>
            .ag-cell.due-date-overdue, .due-date-overdue {
                background-color: #ffebee !important;
                color: #c62828 !important;
            }
            .ag-cell.due-date-warning, .due-date-warning {
                background-color: #ff9800 !important;
                color: #ffffff !important;
            }
            .ag-cell.due-date-ok, .due-date-ok {
                background-color: #e8f5e9 !important;
                color: #2e7d32 !important;
            }
        </style>
        <script>
            // Функция для безопасного экранирования HTML (защита от XSS)
            window.escapeHtml = function(str) {
                if (str == null || str === undefined) {
                    return '';
                }
                const div = document.createElement('div');
                div.textContent = String(str);
                return div.innerHTML;
            };
        </script>
    ''')
    
    # Получаем текущего авторизованного пользователя
    user = get_current_user()
    if not user:
        ui.notify('Ошибка: пользователь не авторизован', type='error')
        ui.navigate.to('/login')
        return
    
    # Применяем глобальную локализацию пагинации ag-grid при загрузке страницы
    apply_aggrid_pagination_localization()
    
    ui.timer(0.1, lambda: create_tasks_page(user.username), once=True)

async def create_tasks_page(login: str):
    """Создает страницу задач для указанного пользователя"""
    if not login or not isinstance(login, str):
        logger.error(f"Некорректный логин пользователя: {login}")
        ui.notify('Ошибка: некорректный логин пользователя', type='error')
        return
    
    # Валидация логина на безопасность
    if not validate_username(login):
        logger.error(f"Небезопасный логин пользователя: {login}")
        ui.notify('Ошибка: небезопасный логин пользователя', type='error')
        return
    
    # Переменные для хранения состояния
    current_login = login
    period_select = None  # Объявляем заранее
    
    async def refresh_tasks(show_finished: bool = False):
        """Обновляет список задач в зависимости от состояния checkbox"""
        nonlocal tasks_grid  # Добавляем nonlocal для доступа к tasks_grid
        
        # Показываем/скрываем выбор периода
        if period_select:
            period_select.set_visibility(show_finished)
        
        # Показываем/скрываем диаграмму Ганта (только для активных задач)
        if gantt_container:
            gantt_container.set_visibility(not show_finished)
        
        try:
            logger.info(f"Начинаем обновление задач для пользователя {current_login}, show_finished={show_finished}")
            
            # Создаем клиент Camunda (автоматически использует учетные данные пользователя, если доступны)
            camunda_client = await create_camunda_client()
            tasks = []

            # Показываем активные задачи по умолчанию, завершенные только если checkbox отмечен
            logger.info(f"Получаем задачи для пользователя {current_login}: active_only={not show_finished}")
            
            # Для завершенных задач добавляем ограничение по дате (последние 7 дней)
            finished_after = None
            max_results = 500  # Ограничение по количеству
            
            if show_finished:
                # Используем выбранный период или 7 дней по умолчанию
                days = period_select.value if (period_select is not None and period_select.value is not None) else 7
                # Вычисляем дату N дней назад
                days_ago = datetime.now(timezone.utc) - timedelta(days=days)
                # Форматируем в ISO формат для Camunda API
                finished_after = days_ago.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0000'
                logger.info(f"Ограничение завершенных задач: после {finished_after}, максимум {max_results} задач")
            
            # Получаем задачи
            if show_finished:
                # Для завершенных задач используем отдельный метод
                user_tasks = await camunda_client.get_completed_tasks_grouped(assignee=current_login)
                # Фильтруем по дате вручную, если нужно
                if finished_after:
                    try:
                        finished_date = datetime.fromisoformat(finished_after.replace('+0000', '+00:00'))
                        # Исправляем: используем end_time вместо endTime
                        filtered_tasks = []
                        for task in user_tasks:
                            end_time = getattr(task, 'end_time', None)
                            if end_time:
                                try:
                                    # Парсим дату завершения задачи
                                    task_end_date = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                                    if task_end_date >= finished_date:
                                        filtered_tasks.append(task)
                                except (ValueError, TypeError) as e:
                                    # Если не удалось распарсить, включаем задачу
                                    logger.debug(f'Не удалось распарсить дату завершения задачи {getattr(task, "id", "unknown")}: {e}')
                                    filtered_tasks.append(task)
                            else:
                                # Если нет end_time, включаем задачу
                                filtered_tasks.append(task)
                        user_tasks = filtered_tasks
                    except Exception as e:
                        logger.warning(f'Ошибка фильтрации по дате: {e}')
                # Ограничиваем количество результатов
                if max_results and len(user_tasks) > max_results:
                    user_tasks = user_tasks[:max_results]
            else:
                # Для активных задач используем обычный метод
                user_tasks = await camunda_client.get_user_tasks(
                    current_login, 
                    active_only=True
                )
            logger.info(f'Получено {len(user_tasks)} задач от Camunda API')
            
            # Оптимизация: загружаем переменные процесса параллельно для всех задач
            logger.info(f'Загружаем переменные процесса для {len(user_tasks)} задач параллельно...')
            process_vars_coroutines = [
                _get_task_process_variables(camunda_client, task, show_finished)
                for task in user_tasks
            ]
            process_vars_results = await asyncio.gather(*process_vars_coroutines, return_exceptions=True)
            
            # Создаем словарь кэша: task_id -> process_variables
            process_vars_cache = {}
            for task, result in zip(user_tasks, process_vars_results):
                task_id = getattr(task, 'id', 'unknown')
                if isinstance(result, Exception):
                    logger.warning(f'Ошибка при загрузке переменных процесса для задачи {task_id}: {result}')
                    process_vars_cache[task_id] = {
                        'due_date': None,
                        'task_name': None,
                        'task_description': None,
                        'document_name': None,
                        'document_id': None,
                    }
                else:
                    process_vars_cache[task_id] = result
            
            logger.info(f'Переменные процесса загружены для {len(process_vars_cache)} задач')
            
            for task in user_tasks:
                # Логируем каждую задачу для отладки
                task_id = getattr(task, 'id', 'unknown')
                task_name = getattr(task, 'name', 'unknown')
                logger.debug(f'Обрабатываем задачу: {task_id} - {task_name}')
                
                # Форматируем дату окончания
                due_date = getattr(task, 'due', '')
                due_date_raw = due_date if due_date else None
                
                # Получаем название, описание и dueDate из переменных процесса
                task_description = getattr(task, 'description', '')
                document_id = None
                document_name = None
                
                # Получаем переменные процесса из кэша
                proc_vars = process_vars_cache.get(task_id, {
                    'due_date': None,
                    'task_name': None,
                    'task_description': None,
                    'document_name': None,
                    'document_id': None,
                })
                
                # Применяем значения из переменных процесса
                if not due_date and proc_vars['due_date']:
                    due_date = proc_vars['due_date']
                    due_date_raw = proc_vars['due_date']
                
                if proc_vars['task_name']:
                    task_name = proc_vars['task_name']
                
                if proc_vars['task_description']:
                    task_description = proc_vars['task_description']
                
                document_name = proc_vars['document_name']
                document_id = proc_vars['document_id']

                # Форматируем дату для отображения (due_date_raw уже сохранен выше)
                if due_date:
                    try:
                        due_date = format_date_russian(due_date)
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Не удалось отформатировать дату {due_date}: {e}")
                        # Если не удалось отформатировать, оставляем исходное значение
                        if not due_date_raw:
                            due_date_raw = due_date
                else:
                    due_date_raw = None

                # Получаем поля задачи - используем прямые атрибуты как на странице завершения задач
                start_time = getattr(task, 'start_time', '')
                end_time = getattr(task, 'end_time', '')
                
                # Форматируем даты для отображения (если они уже не отформатированы)
                if start_time:
                    try:
                        # Проверяем, не отформатирована ли уже дата
                        if 'T' in str(start_time) or len(str(start_time)) > 20:
                            start_time = format_date_russian(start_time)
                    except (ValueError, TypeError, OSError):
                        # Если не удалось отформатировать, оставляем исходное значение
                        pass
                
                if end_time:
                    try:
                        # Проверяем, не отформатирована ли уже дата
                        if 'T' in str(end_time) or len(str(end_time)) > 20:
                            end_time = format_date_russian(end_time)
                    except (ValueError, TypeError, OSError):
                        # Если не удалось отформатировать, оставляем исходное значение
                        pass
                
                # Получаем длительность
                duration_formatted = getattr(task, 'duration_formatted', '')
                if not duration_formatted and hasattr(task, 'duration') and task.duration:
                    # Форматируем длительность из миллисекунд
                    duration_sec = task.duration / 1000
                    if duration_sec < 60:
                        duration_formatted = f'{duration_sec:.1f} сек'
                    elif duration_sec < 3600:
                        duration_formatted = f'{duration_sec/60:.1f} мин'
                    else:
                        duration_formatted = f'{duration_sec/3600:.1f} ч'
                
                # Получаем delete_reason для завершенных задач
                delete_reason = getattr(task, 'delete_reason', '')
                if not delete_reason and hasattr(task, 'deleteReason'):
                    delete_reason = task.deleteReason
                
                # Форматируем статус
                if delete_reason == 'completed':
                    delete_reason = 'Завершена'
                elif delete_reason == 'cancelled':
                    delete_reason = 'Отменена'
                elif isinstance(task, GroupedHistoryTask):
                    # Для группированных задач проверяем статус
                    if task.completed_users >= task.total_users:
                        delete_reason = 'Завершена'
                    else:
                        delete_reason = f'В процессе ({task.completed_users}/{task.total_users})'
                elif not delete_reason:
                    delete_reason = 'Активна' if not show_finished else 'Завершена'
                
                task_data = {
                    'name': task_name,  # Используем название из переменных процесса (как в диаграмме Ганта)
                    'description': task_description,  # Используем описание из переменных процесса (taskDescription)
                    'start_time': start_time,
                    'due_date': due_date,
                    'due_date_raw': due_date_raw,  # Добавляем исходную дату для сравнения
                    'end_time': end_time,
                    'duration_formatted': duration_formatted,
                    'delete_reason': delete_reason,
                    'document_id': document_id,  # Добавляем ID документа для открытия
                    'document_name': document_name,  # Добавляем название документа для отображения
                }
                
                # Логируем для отладки
                logger.debug(f"Данные задачи {task_id}: document_id={document_id}, name={task_name}")

                # Вычисляем разницу в днях для использования в cellClassRules
                if due_date_raw:
                    try:
                        deadline = parse_task_deadline(due_date_raw)
                        if deadline:
                            now = datetime.now()
                            now = now.replace(hour=0, minute=0, second=0, microsecond=0)
                            deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
                            diff_days = (deadline - now).days
                            task_data['due_date_diff_days'] = diff_days
                        else:
                            task_data['due_date_diff_days'] = None
                    except Exception as e:
                        logger.warning(f"Не удалось вычислить разницу дней для {task_name}: {e}")
                        task_data['due_date_diff_days'] = None
                else:
                    task_data['due_date_diff_days'] = None
                
                tasks.append(task_data)
                logger.debug(f"Добавлена задача в список: {task_data['name']}")

            logger.info(f"Обработано {len(tasks)} задач для отображения")
            
            # Обновляем диаграмму Ганта для активных задач (используем кэш переменных процесса)
            if not show_finished and user_tasks and gantt_container:
                gantt_container.clear()
                tasks_for_gantt = []
                
                for task in user_tasks:
                    task_id = getattr(task, 'id', 'unknown')
                    due_date = getattr(task, 'due', None)
                    task_name = getattr(task, 'name', '')
                    task_description = ''
                    
                    # Используем кэш переменных процесса вместо повторных запросов
                    proc_vars = process_vars_cache.get(task_id, {
                        'due_date': None,
                        'task_name': None,
                        'task_description': None,
                        'document_name': None,
                        'document_id': None,
                    })
                    
                    if not due_date and proc_vars['due_date']:
                        due_date = proc_vars['due_date']
                    if proc_vars['task_name']:
                        task_name = proc_vars['task_name']
                    if proc_vars['task_description']:
                        task_description = proc_vars['task_description']
                    
                    if due_date:
                        tasks_for_gantt.append({
                            'name': task_name,
                            'description': task_description,
                            'due': due_date,
                            'id': getattr(task, 'id', ''),
                            'process_instance_id': getattr(task, 'process_instance_id', '')
                        })
                
                with gantt_container:
                    create_gantt_chart(
                        tasks_for_gantt,
                        title='Активные задачи со сроками',
                        name_field='name',
                        due_field='due',
                        id_field='id',
                        process_instance_id_field='process_instance_id',
                        description_field='description'
                    )
            
            # Обновляем данные в таблице
            if tasks_grid:
                logger.info(f"Обновляем таблицу с {len(tasks)} задачами")
                try:
                    tasks_grid.options['rowData'] = tasks
                    tasks_grid.update()
                    logger.info("Таблица задач обновлена")
                except KeyError as e:
                    # Игнорируем ошибку удаления уже удаленного клиента (race condition в NiceGUI)
                    logger.warning(f"Ошибка обновления таблицы (игнорируем): {e}")
                    # Пробуем обновить еще раз
                    try:
                        tasks_grid.options['rowData'] = tasks
                        tasks_grid.update()
                    except Exception as e2:
                        logger.error(f"Повторная ошибка обновления таблицы: {e2}")
            else:
                logger.warning("tasks_grid не инициализирована!")
            
            # Обновляем счетчик задач
            tasks_count_label.text = f'Найдено задач: {len(tasks)}'
            
            ui.notify(f'Загружено {len(tasks)} задач', type='positive')
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке задач для пользователя {current_login}: {e}", exc_info=True)
            ui.notify(f'Ошибка при загрузке задач: {str(e)}', type='negative')
    
    async def on_task_dblclick(event):
        """Обработчик двойного клика по задаче"""
        try:
            logger.debug(f"Обработка двойного клика: {event.args}")
            
            # Проверяем, что event.args содержит данные задачи
            if isinstance(event.args, dict) and 'data' in event.args:
                row_data = event.args['data']
                
                ui.notify(f'Выбрана задача: {row_data.get("name", "Без названия")}')
                
                # Преобразуем данные задачи в формат для детальной таблицы
                detail_data = create_task_detail_data(row_data)
                
                # Показываем детальную информацию
                if detail_data:
                    ui.notify(f'Показано {len(detail_data)} полей задачи', type='positive')
                else:
                    ui.notify('Нет данных для отображения', type='warning')
            else:
                logger.warning(f"Неожиданная структура event.args: {event.args}")
                ui.notify('Не удалось получить данные задачи', type='warning')
        except Exception as e:
            logger.error(f"Ошибка при обработке двойного клика: {e}", exc_info=True)
            ui.notify(f'Ошибка при обработке задачи: {str(e)}', type='negative')
    
    # Создаем UI элементы
    with ui.column().classes('w-full'):
        # Заголовок
        with ui.row().classes('w-full items-center justify-between mb-1'):
            tasks_count_label = ui.label('Загружаем задачи...').classes('text-sm mb-1')

        # Раскрываемый блок для диаграммы Ганта (только для активных задач)
        with ui.expansion('Графика', icon='timeline', value=False).classes('w-full mb-4'):
            gantt_container = ui.column().classes('w-full')
            gantt_container.set_visibility(False)  # Скрываем по умолчанию

        # Элементы управления (после диаграммы Ганта, перед таблицей)
        with ui.row().classes('w-full items-center justify-end mb-2'):
            finished_checkbox = ui.checkbox(
                'Показать завершенные задачи', 
                value=False,
                on_change=lambda e: ui.timer(0.1, lambda: refresh_tasks(e.value), once=True)  # Исправляем вызов
            ).classes('text-xs mr-4')

            # Добавляем выбор периода для завершенных задач (скрыт по умолчанию)
            period_select = ui.select(
                {
                    7: 'Последние 7 дней',
                    30: 'Последние 30 дней',
                    90: 'Последние 90 дней',
                    180: 'Последние 180 дней'
                },
                value=7,
                label='Период',
                on_change=lambda: ui.timer(0.1, lambda: refresh_tasks(finished_checkbox.value), once=True)  # Исправляем вызов
            ).classes('text-xs mr-4')
            period_select.set_visibility(False)

        # Функция для открытия предварительного просмотра документа
        async def open_document_preview(document_id: str):
            """Открывает предварительный просмотр документа"""
            try:
                from services.mayan_connector import MayanClient
                from components.document_viewer import show_document_viewer
                
                document_id = str(document_id).strip()
                
                if not document_id or document_id in ['null', 'None', '']:
                    logger.warning(f"Некорректный document_id: {document_id}")
                    return
                
                logger.info(f"Открываем предварительный просмотр документа с ID: {document_id}")
                
                mayan_client = await MayanClient.create_with_session_user()
                await show_document_viewer(document_id, mayan_client=mayan_client)
            except Exception as e:
                logger.error(f"Ошибка при открытии просмотра документа {document_id}: {e}", exc_info=True)
                ui.notify(f'Ошибка при открытии просмотра: {str(e)}', type='error')

        # Основная таблица задач
        tasks_grid = ui.aggrid({
            'columnDefs': [
                {'headerName': 'Процесс', 'field': 'name', 'sortable': True, 'filter': True},
                {'headerName': 'Описание', 'field': 'description', 'sortable': True, 'filter': True},
                {'headerName': 'Начало', 'field': 'start_time', 'sortable': True, 'filter': True},
                {
                    'headerName': 'Срок исполнения', 
                    'field': 'due_date', 
                    'sortable': True, 
                    'filter': True,
                    'cellClassRules': {
                        'due-date-overdue': 'data.due_date_diff_days < 0',
                        'due-date-warning': 'data.due_date_diff_days >= 0 && data.due_date_diff_days <= 2',
                        'due-date-ok': 'data.due_date_diff_days > 2'
                    }
                },
                {'headerName': 'Завершение', 'field': 'end_time', 'sortable': True, 'filter': True},
                {'headerName': 'Статус', 'field': 'delete_reason', 'sortable': True, 'filter': True},
                {
                    'headerName': 'Документ',
                    'field': 'document_name',  # Изменяем поле на document_name
                    'sortable': False,
                    'filter': False,
                    'cellRenderer': '''
                        function(params) {
                            // Проверяем наличие document_name и document_id
                            const docName = params.data && params.data.document_name ? params.data.document_name : null;
                            const docId = params.data && params.data.document_id ? params.data.document_id : null;
                            
                            if (!docName || docName === 'null' || docName === '' || docName === null || docName === undefined || docName === 'None') {
                                return '';
                            }
                            
                            // Обрезаем длинное название документа
                            let displayName = String(docName).trim();
                            if (displayName.length > 50) {
                                displayName = displayName.substring(0, 50) + '...';
                            }
                            
                            // Используем глобальную функцию escapeHtml для защиты от XSS
                            const escapedDocName = window.escapeHtml(docName);
                            const escapedDisplayName = window.escapeHtml(displayName);
                            
                            // Возвращаем название документа как ссылку с экранированным HTML
                            return '<span style="color: #1976d2; cursor: pointer; text-decoration: underline;" title="' + escapedDocName + '">' + escapedDisplayName + '</span>';
                        }
                    ''',
                    'width': 250
                },
            ],
            'rowData': [],
            'rowSelection': 'single',
            'pagination': True,
            'paginationPageSize': 10,
            'paginationPageSizeSelector': [10, 25, 50, 100],
            'localeText': AGGGRID_RUSSIAN_LOCALE,
        }).classes('w-full h-96').on('cellDoubleClicked', on_task_dblclick).on('cellClicked', lambda event: handle_document_cell_click(event, open_document_preview))
        
        # Обработчик клика по ячейке документа
        async def handle_document_cell_click(event, preview_func):
            """Обрабатывает клик по ячейке документа"""
            try:
                # Проверяем, что клик был по колонке "Документ"
                if event.args and 'colDef' in event.args:
                    col_def = event.args['colDef']
                    if col_def.get('headerName') == 'Документ':
                        # Получаем document_id из данных строки
                        if 'data' in event.args:
                            row_data = event.args['data']
                            document_id = row_data.get('document_id')
                            
                            if document_id and document_id not in ['null', 'None', '']:
                                await preview_func(str(document_id))
                            else:
                                ui.notify('Документ не найден для этой задачи', type='warning')
            except Exception as e:
                logger.error(f"Ошибка при обработке клика по ячейке документа: {e}", exc_info=True)
                ui.notify(f'Ошибка при открытии документа: {str(e)}', type='error')

        # Загружаем задачи при инициализации страницы
        async def init_tasks():
            await refresh_tasks(False)
        
        ui.timer(0.1, lambda: init_tasks(), once=True)
