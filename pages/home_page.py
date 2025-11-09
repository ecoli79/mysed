from message import message
from nicegui import ui
from models import Task
from datetime import datetime, timezone
from services.camunda_connector import CamundaClient
from auth.middleware import get_current_user
from config.settings import config
from utils import validate_username, format_due_date, create_task_detail_data
import theme
import logging

logger = logging.getLogger(__name__)

def content() -> None:
    """Главная страница с задачами пользователя"""
    # Получаем текущего авторизованного пользователя
    user = get_current_user()
    if not user:
        ui.notify('Ошибка: пользователь не авторизован', type='error')
        ui.navigate.to('/login')
        return
    
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
                from datetime import timedelta
                # Используем выбранный период или 7 дней по умолчанию
                days = period_select.value if period_select and period_select.value else 7
                # Вычисляем дату N дней назад
                days_ago = datetime.now(timezone.utc) - timedelta(days=days)
                # Форматируем в ISO формат для Camunda API
                finished_after = days_ago.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0000'
                logger.info(f"Ограничение завершенных задач: после {finished_after}, максимум {max_results} задач")
            
            # Получаем задачи
            user_tasks = camunda_client.get_user_tasks(
                current_login, 
                active_only=active_only,
                finished_after=finished_after if show_finished else None,
                max_results=max_results if show_finished else None
            )
            logger.info(f"Получено {len(user_tasks)} задач от Camunda API")
            
            for task in user_tasks:
                # Логируем каждую задачу для отладки
                logger.debug(f"Обрабатываем задачу: {task.id} - {task.name}")
                
                # Форматируем дату окончания
                due_date = getattr(task, 'due', '')
                if due_date:
                    try:
                        due_date = format_due_date(due_date)
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Не удалось отформатировать дату {due_date}: {e}")
                        # Оставляем исходное значение если не удалось распарсить
                
                task_data = {
                    'name': getattr(task, 'name', ''),
                    'description': getattr(task, 'description', ''),
                    'start_time': getattr(task, 'start_time', ''),
                    'due_date': due_date,
                    'end_time': getattr(task, 'end_time', ''),
                    'duration_formatted': getattr(task, 'duration_formatted', ''),
                    'delete_reason': getattr(task, 'delete_reason', ''),
                }
                tasks.append(task_data)
                logger.debug(f"Добавлена задача в список: {task_data['name']}")

            logger.info(f"Обработано {len(tasks)} задач для отображения")
            
            # Обновляем данные в таблице
            if tasks_grid:
                logger.info(f"Обновляем таблицу с {len(tasks)} задачами")
                tasks_grid.options['rowData'] = tasks
                tasks_grid.update()
                logger.info("Таблица задач обновлена")
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

        
        # Основная таблица задач
        tasks_grid = ui.aggrid({
            'columnDefs': [
                {'headerName': 'Процесс', 'field': 'name', 'sortable': True, 'filter': True},
                {'headerName': 'Описание', 'field': 'description', 'sortable': True, 'filter': True},
                {'headerName': 'Начало', 'field': 'start_time', 'sortable': True, 'filter': True},
                {'headerName': 'Срок выполнения', 'field': 'due_date', 'sortable': True, 'filter': True},
                {'headerName': 'Завершение', 'field': 'end_time', 'sortable': True, 'filter': True},
                {'headerName': 'Длительность', 'field': 'duration_formatted', 'sortable': True, 'filter': True},
                {'headerName': 'Статус', 'field': 'delete_reason', 'sortable': True, 'filter': True},
            ],
            'rowData': [],
            'rowSelection': 'single',
            'pagination': True,
            'paginationPageSize': 10,
        }).classes('w-full h-96').on('cellDoubleClicked', on_task_dblclick)
        
        # Таблица детальной информации о задаче
        with ui.card().classes('w-full mt-4') as tasks_details_card:
            with ui.row().classes('w-full items-center justify-between mb-2'):
                ui.label('Детали задачи').classes('text-h6 font-bold')
                tasks_details_toggle = ui.button('Скрыть', icon='expand_less').classes('text-sm')
            
            tasks_details_grid = ui.aggrid({
                'columnDefs': [
                    {'headerName': 'Поле', 'field': 'field'},
                    {'headerName': 'Значение', 'field': 'value'},
                ],
                'rowData': [],
                'rowSelection': 'none',
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
            ui.button('Принять задачу', icon='check', on_click=lambda: ui.notify('Функция в разработке'))
            ui.button('Отклонить задачу', icon='close', on_click=lambda: ui.notify('Функция в разработке'))
            ui.button('Завершить задачу', icon='done', on_click=lambda: ui.notify('Функция в разработке'))
    
    # Загружаем задачи при инициализации
    ui.timer(0.1, lambda: refresh_tasks(False), once=True)
