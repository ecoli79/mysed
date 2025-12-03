from message import message
from nicegui import ui
from models import Task
from datetime import datetime, timezone, timedelta
from services.camunda_connector import CamundaClient
from auth.middleware import get_current_user
from config.settings import config
from utils import validate_username, format_due_date, create_task_detail_data
import theme
import logging
import asyncio
from components.gantt_chart import create_gantt_chart
from models import GroupedHistoryTask, CamundaHistoryTask
from utils.date_utils import format_date_russian
from utils.aggrid_locale import AGGGRID_RUSSIAN_LOCALE, apply_aggrid_pagination_localization


logger = logging.getLogger(__name__)

def content() -> None:
    """Главная страница с задачами пользователя"""
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
    tasks_grid = None
    tasks_details_grid = None
    period_select = None  # Объявляем заранее
    
    async def refresh_tasks(show_finished: bool = False):
        """Обновляет список задач в зависимости от состояния checkbox"""
        # Показываем/скрываем выбор периода
        if period_select:
            period_select.set_visibility(show_finished)
        
        # Показываем/скрываем диаграмму Ганта (только для активных задач)
        if gantt_container:
            gantt_container.set_visibility(not show_finished)
        
        try:
            logger.info(f"Начинаем обновление задач для пользователя {current_login}, show_finished={show_finished}")
            
            # Создаем клиент Camunda с конфигурацией из настроек
            if not config.camunda_url:
                raise ValueError("Camunda URL не настроен. Установите переменную CAMUNDA_URL в файле .env")
            if not config.camunda_username:
                raise ValueError("Camunda пользователь не настроен. Установите переменную CAMUNDA_USERNAME в файле .env")
            if not config.camunda_password:
                raise ValueError("Camunda пароль не настроен. Установите переменную CAMUNDA_PASSWORD в файле .env")
            
            camunda_client = CamundaClient(
                base_url=config.camunda_url,
                username=config.camunda_username,
                password=config.camunda_password,
                verify_ssl=False  # Для разработки отключаем проверку SSL
            )
            tasks = []

            # Показываем активные задачи по умолчанию, завершенные только если checkbox отмечен
            active_only = not show_finished
            logger.info(f"Получаем задачи для пользователя {current_login}: active_only={active_only}")
            
            # Для завершенных задач добавляем ограничение по дате (последние 7 дней)
            finished_after = None
            max_results = 500  # Ограничение по количеству
            
            if show_finished:
                # Используем выбранный период или 7 дней по умолчанию
                days = period_select.value if period_select and period_select.value else 7
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
                                except:
                                    # Если не удалось распарсить, включаем задачу
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
            
            for task in user_tasks:
                # Логируем каждую задачу для отладки
                task_id = getattr(task, 'id', 'unknown')
                task_name = getattr(task, 'name', 'unknown')
                logger.debug(f"Обрабатываем задачу: {task_id} - {task_name}")
                
                # Проверяем тип задачи для правильной обработки
                
                
                # Форматируем дату окончания
                due_date = getattr(task, 'due', '')
                
                # Получаем название, описание и dueDate из переменных процесса (как в диаграмме Ганта)
                task_description = getattr(task, 'description', '')
                if hasattr(task, 'process_instance_id') and task.process_instance_id:
                    try:
                        # Для завершенных задач используем исторические переменные
                        if show_finished:
                            process_variables = await camunda_client.get_history_process_instance_variables_by_name(
                                task.process_instance_id,
                                ['dueDate', 'taskName', 'documentName', 'taskDescription']
                            )
                        else:
                            process_variables = await camunda_client.get_process_instance_variables_by_name(
                                task.process_instance_id,
                                ['dueDate', 'taskName', 'documentName', 'taskDescription']
                            )
                        
                        # Получаем dueDate
                        if not due_date:
                            due_date_raw = process_variables.get('dueDate')
                            if due_date_raw:
                                if isinstance(due_date_raw, dict) and 'value' in due_date_raw:
                                    due_date = due_date_raw['value']
                                elif isinstance(due_date_raw, str):
                                    due_date = due_date_raw
                                else:
                                    due_date = str(due_date_raw) if due_date_raw else ''
                        
                        # Получаем название из переменных процесса (приоритет: taskName, documentName)
                        # Используем ту же логику, что и для диаграммы Ганта
                        # Всегда пытаемся получить название из переменных процесса, если оно доступно
                        task_name_from_vars = (
                            process_variables.get('taskName') or 
                            process_variables.get('documentName') or 
                            None
                        )
                        # Обрабатываем формат переменных Camunda
                        if task_name_from_vars:
                            if isinstance(task_name_from_vars, dict) and 'value' in task_name_from_vars:
                                task_name_from_vars = task_name_from_vars['value']
                            elif not isinstance(task_name_from_vars, str):
                                task_name_from_vars = str(task_name_from_vars) if task_name_from_vars else None
                            
                            # Используем название из переменных процесса, если оно есть
                            if task_name_from_vars and task_name_from_vars.strip():
                                task_name = task_name_from_vars.strip()
                        # Если название задачи стандартное, но не нашли в переменных, оставляем исходное
                        elif not task_name or task_name in ['Подписать документ', 'Ознакомиться с документом']:
                            # Оставляем исходное название, если не нашли в переменных
                            pass
                        
                        # Получаем описание из переменных процесса (taskDescription)
                        task_description_from_vars = process_variables.get('taskDescription')
                        if task_description_from_vars:
                            # Обрабатываем формат переменных Camunda
                            if isinstance(task_description_from_vars, dict) and 'value' in task_description_from_vars:
                                task_description_from_vars = task_description_from_vars['value']
                            elif not isinstance(task_description_from_vars, str):
                                task_description_from_vars = str(task_description_from_vars) if task_description_from_vars else None
                            
                            # Используем описание из переменных процесса, если оно есть
                            if task_description_from_vars and task_description_from_vars.strip():
                                task_description = task_description_from_vars.strip()
                    except Exception as e:
                        logger.warning(f"Не удалось получить переменные процесса {task.process_instance_id}: {e}")
                
                if due_date:
                    try:
                        due_date = format_date_russian(due_date)
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Не удалось отформатировать дату {due_date}: {e}")
                        # Оставляем исходное значение если не удалось распарсить
                
                # Получаем поля задачи - используем прямые атрибуты как на странице завершения задач
                start_time = getattr(task, 'start_time', '')
                end_time = getattr(task, 'end_time', '')
                
                # Форматируем даты для отображения (если они уже не отформатированы)
                if start_time:
                    try:
                        # Проверяем, не отформатирована ли уже дата
                        if 'T' in str(start_time) or len(str(start_time)) > 20:
                            start_time = format_date_russian(start_time)
                    except:
                        pass
                
                if end_time:
                    try:
                        # Проверяем, не отформатирована ли уже дата
                        if 'T' in str(end_time) or len(str(end_time)) > 20:
                            end_time = format_date_russian(end_time)
                    except:
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
                    'end_time': end_time,
                    'duration_formatted': duration_formatted,
                    'delete_reason': delete_reason,
                }
                tasks.append(task_data)
                logger.debug(f"Добавлена задача в список: {task_data['name']}")

            logger.info(f"Обработано {len(tasks)} задач для отображения")
            
            # ДОБАВИТЬ: Обновляем диаграмму Ганта для активных задач
            if not show_finished and user_tasks and gantt_container:
                gantt_container.clear()
                tasks_for_gantt = []
                
                # Получаем dueDate, название и описание из переменных процесса для задач
                for task in user_tasks:
                    due_date = getattr(task, 'due', None)
                    task_name = getattr(task, 'name', '')  # Название задачи по умолчанию
                    task_description = ''  # Описание задачи
                    
                    # Получаем данные из переменных процесса для единообразия
                    if hasattr(task, 'process_instance_id') and task.process_instance_id:
                        try:
                            # Получаем dueDate, название и описание из переменных процесса
                            process_variables = await camunda_client.get_process_instance_variables_by_name(
                                task.process_instance_id,
                                ['dueDate', 'taskName', 'documentName', 'taskDescription']
                            )
                            
                            # Получаем dueDate
                            if not due_date:
                                due_date_raw = process_variables.get('dueDate')
                                if due_date_raw:
                                    if isinstance(due_date_raw, dict) and 'value' in due_date_raw:
                                        due_date = due_date_raw['value']
                                    elif isinstance(due_date_raw, str):
                                        due_date = due_date_raw
                                    else:
                                        due_date = str(due_date_raw) if due_date_raw else None
                            
                            # Получаем название из переменных процесса (приоритет: taskName, documentName)
                            task_name_from_vars = (
                                process_variables.get('taskName') or 
                                process_variables.get('documentName') or 
                                None
                            )
                            # Обрабатываем формат переменных Camunda
                            if task_name_from_vars:
                                if isinstance(task_name_from_vars, dict) and 'value' in task_name_from_vars:
                                    task_name_from_vars = task_name_from_vars['value']
                                elif not isinstance(task_name_from_vars, str):
                                    task_name_from_vars = str(task_name_from_vars) if task_name_from_vars else None
                                
                                # Используем название из переменных процесса, если оно есть
                                if task_name_from_vars and task_name_from_vars.strip():
                                    task_name = task_name_from_vars.strip()
                            
                            # Получаем описание из переменных процесса (taskDescription)
                            task_description_from_vars = process_variables.get('taskDescription')
                            if task_description_from_vars:
                                # Обрабатываем формат переменных Camunda
                                if isinstance(task_description_from_vars, dict) and 'value' in task_description_from_vars:
                                    task_description_from_vars = task_description_from_vars['value']
                                elif not isinstance(task_description_from_vars, str):
                                    task_description_from_vars = str(task_description_from_vars) if task_description_from_vars else None
                                
                                # Используем описание из переменных процесса, если оно есть
                                if task_description_from_vars and task_description_from_vars.strip():
                                    task_description = task_description_from_vars.strip()
                                    
                        except Exception as e:
                            logger.warning(f"Не удалось получить переменные процесса {task.process_instance_id}: {e}")
                    
                    if due_date:
                        tasks_for_gantt.append({
                            'name': task_name,  # Используем название из переменных процесса
                            'description': task_description,  # Добавляем описание из переменных процесса
                            'due': due_date,
                            'id': getattr(task, 'id', ''),
                            'process_instance_id': getattr(task, 'process_instance_id', '')
                        })
                
                with gantt_container:
                    create_gantt_chart(
                        tasks_for_gantt if tasks_for_gantt else [],
                        title='Активные задачи со сроками',
                        name_field='name',
                        due_field='due',
                        id_field='id',
                        process_instance_id_field='process_instance_id',
                        description_field='description'  # Добавляем поле описания
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
                if tasks_details_grid and detail_data:
                    tasks_details_grid.options['rowData'] = detail_data
                    tasks_details_grid.update()
                    tasks_details_grid.visible = True
                    
                    # Обновляем кнопку переключения
                    if 'tasks_details_toggle' in locals():
                        tasks_details_toggle.text = 'Скрыть'
                        tasks_details_toggle.icon = 'expand_less'
                    
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
        # Заголовок и элементы управления
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('Мои задачи').classes('text-h5 font-bold')
            
        # Счетчик задач
        with ui.row().classes('w-full items-center justify-between'):
            tasks_count_label = ui.label('Загружаем задачи...').classes('text-lg mb-2')
            finished_checkbox = ui.checkbox(
                'Показать завершенные задачи', 
                value=False,
                on_change=lambda e: refresh_tasks(e.value)  # ВАЖНО: добавляем обработчик!
            ).classes('mr-4')

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
                on_change=lambda: refresh_tasks(finished_checkbox.value)  # Обновляем при изменении периода
            ).classes('mr-4')
            period_select.set_visibility(False)

        # ДОБАВИТЬ: Контейнер для диаграммы Ганта (только для активных задач)
        gantt_container = ui.column().classes('w-full mb-4')
        gantt_container.set_visibility(False)  # Скрываем по умолчанию

        # Основная таблица задач
        tasks_grid = ui.aggrid({
            'columnDefs': [
                {'headerName': 'Процесс', 'field': 'name', 'sortable': True, 'filter': True},
                {'headerName': 'Описание', 'field': 'description', 'sortable': True, 'filter': True},
                {'headerName': 'Начало', 'field': 'start_time', 'sortable': True, 'filter': True},
                {'headerName': 'Срок исполнения', 'field': 'due_date', 'sortable': True, 'filter': True},
                {'headerName': 'Завершение', 'field': 'end_time', 'sortable': True, 'filter': True},
                {'headerName': 'Длительность', 'field': 'duration_formatted', 'sortable': True, 'filter': True},
                {'headerName': 'Статус', 'field': 'delete_reason', 'sortable': True, 'filter': True},
            ],
            'rowData': [],
            'rowSelection': 'single',
            'pagination': True,
            'paginationPageSize': 10,
            'localeText': AGGGRID_RUSSIAN_LOCALE,
        }).classes('w-full h-96').on('cellDoubleClicked', on_task_dblclick)
        
        # Применяем JavaScript локализацию для пагинации (fallback для элементов, которые не локализуются через localeText)
        # Запускаем локализацию после создания таблицы с несколькими попытками
        ui.timer(0.3, apply_aggrid_pagination_localization, once=True)
        ui.timer(0.8, apply_aggrid_pagination_localization, once=True)
        ui.timer(1.5, apply_aggrid_pagination_localization, once=True)
        
        # Таблица детальной информации о задаче
        with ui.card().classes('w-full mt-4') as tasks_details_card:
            with ui.row().classes('w-full items-center justify-between mb-2'):
                ui.label('Детали задачи').classes('text-h6 font-bold')
                tasks_details_toggle = ui.button('Скрыть', icon='expand_less').classes('text-xs px-2 py-1 h-7')
            
            tasks_details_grid = ui.aggrid({
                'columnDefs': [
                    {'headerName': 'Поле', 'field': 'field'},
                    {'headerName': 'Значение', 'field': 'value'},
                ],
                'rowData': [],
                'rowSelection': 'none',
                'localeText': AGGGRID_RUSSIAN_LOCALE,
            }).classes('w-full h-48')
            tasks_details_grid.visible = False
            
            # Обработчик для кнопки скрытия/показа
            def toggle_details():
                if tasks_details_grid.visible:
                    tasks_details_grid.visible = False
                    tasks_details_toggle.text = 'Показать'
                    tasks_details_toggle.icon = 'expand_more'
                else:
                    tasks_details_grid.visible = True
                    tasks_details_toggle.text = 'Скрыть'
                    tasks_details_toggle.icon = 'expand_less'
            
            tasks_details_toggle.on_click(toggle_details)
        
        # Кнопки действий
        with ui.row().classes('w-full mt-4 justify-center'):
            ui.button('Принять задачу', icon='check', on_click=lambda: ui.notify('Функция в разработке')).classes('text-xs px-2 py-1 h-7')
            ui.button('Отклонить задачу', icon='close', on_click=lambda: ui.notify('Функция в разработке')).classes('text-xs px-2 py-1 h-7')
            ui.button('Завершить задачу', icon='done', on_click=lambda: ui.notify('Функция в разработке')).classes('text-xs px-2 py-1 h-7')
    
    # Загружаем задачи при инициализации
    ui.timer(0.1, lambda: refresh_tasks(False), once=True)
