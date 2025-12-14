from nicegui import ui
from services.camunda_connector import CamundaClient, create_camunda_client
from auth.middleware import get_current_user, require_auth
from config.settings import config
from typing import Optional, List, Dict, Any
import json
from components.gantt_chart import create_gantt_chart, parse_task_deadline, prepare_tasks_for_gantt
from datetime import datetime
from app_logging.logger import get_logger

logger = get_logger(__name__)

# Глобальная переменная для контейнера деталей процесса
_details_container = None
# Глобальная переменная для хранения ID выбранного процесса
_selected_process_id: Optional[str] = None
# Словарь для хранения ссылок на карточки процессов (process_id -> card_info)
_process_cards: Dict[str, Dict[str, Any]] = {}

def get_camunda_client() -> CamundaClient:
    """Получает клиент Camunda с проверкой конфигурации"""
    if not config.camunda_url:
        raise ValueError("Camunda URL не настроен. Установите переменную CAMUNDA_URL в файле .env")
    if not config.camunda_username:
        raise ValueError("Camunda пользователь не настроен. Установите переменную CAMUNDA_USERNAME в файле .env")
    if not config.camunda_password:
        raise ValueError("Camunda пароль не настроен. Установите переменную CAMUNDA_PASSWORD в файле .env")
    
    return CamundaClient(
        base_url=config.camunda_url,
        username=config.camunda_username,
        password=config.camunda_password,
        verify_ssl=False  # Для разработки отключаем проверку SSL
    )

def get_user_display_name(username: str) -> str:
    """
    Получает отформатированное имя пользователя из логина
    
    Args:
        username: Логин пользователя
        
    Returns:
        Строка с именем, фамилией и должностью или логин, если не найдено
    """
    try:
        from auth.ldap_auth import LDAPAuthenticator
        
        ldap_auth = LDAPAuthenticator()
        user_info = ldap_auth.get_user_by_login(username)
        
        if user_info:
            display_parts = [user_info.givenName, user_info.sn]
            if user_info.destription:
                display_parts.append(user_info.destription)
            return ' '.join(filter(None, display_parts[:2])) + (f' - {user_info.destription}' if user_info.destription else '')
        else:
            return username
    except Exception as e:
        logger.warning(f"Не удалось получить данные пользователя {username} из LDAP: {e}")
        return username

@require_auth
def content():
    """Создает страницу для отслеживания созданных пользователем процессов"""
    from auth.ldap_auth import LDAPAuthenticator
    
    current_user = get_current_user()
    if not current_user:
        ui.navigate.to('/login')
        return
    
    ui.page_title('Мои процессы')
    
    # Получаем данные пользователя из LDAP
    try:
        ldap_auth = LDAPAuthenticator()
        user_info = ldap_auth.get_user_by_login(current_user.username)
        
        # Формируем строку с информацией о пользователе
        if user_info:
            # Формат: "Имя Фамилия - Должность" или "Имя Фамилия" если должности нет
            user_display_parts = [user_info.givenName, user_info.sn]
            if user_info.destription:
                user_display_parts.append(user_info.destription)
            user_display = ' '.join(filter(None, user_display_parts[:2]))
            if user_info.destription:
                user_display += f' - {user_info.destription}'
        else:
            # Если не удалось получить данные из LDAP, используем логин
            user_display = current_user.username
    except Exception as e:
        logger.error(f"Ошибка при получении данных пользователя из LDAP: {e}")
        user_display = current_user.username
    
    # Глобальная переменная для контейнера деталей процесса
    global _details_container
    _details_container = None
    
    # Переменные для управления отображением завершенных процессов
    show_completed = False
    period_days = 7
    
    async def refresh_processes():
        """Обновляет список процессов с учетом фильтров"""
        nonlocal show_completed, period_days
        await load_my_processes(
            processes_container, 
            completed_processes_container,
            gantt_container,
            current_user.username,
            show_completed=show_completed,
            days=period_days
        )
    
    async def toggle_completed():
        """Переключает отображение завершенных процессов"""
        nonlocal show_completed
        show_completed = not show_completed
        
        # Сразу обновляем видимость контейнера завершенных процессов
        if show_completed:
            completed_processes_container.set_visibility(True)
        else:
            completed_processes_container.set_visibility(False)
            # Очищаем контейнер при скрытии
            completed_processes_container.clear()
        
        # Обновляем видимость фильтра периода
        if period_select:
            period_select.set_visibility(show_completed)
        
        # Обновляем текст кнопки
        if show_completed:
            show_completed_button.text = 'Скрыть завершенные'
            show_completed_button.icon = 'visibility_off'
        else:
            show_completed_button.text = 'Показать завершенные'
            show_completed_button.icon = 'visibility'
        
        # Вызываем асинхронную функцию обновления
        await refresh_processes()
    
    def on_period_change(e):
        """Обработчик изменения периода"""
        nonlocal period_days
        period_days = e.value
        if show_completed:
            refresh_processes()
    
    with ui.column().classes('w-full p-4'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            # Визуально разделяем статический текст и данные пользователя
            with ui.row().classes('items-baseline gap-2'):
                # Статический текст - серый, обычный вес
                ui.label('Процессы, созданные пользователем:').classes('text-lg text-gray-500 font-normal')
                
                # Данные пользователя - акцентный цвет, полужирный
                if user_info:
                    user_display = f'{user_info.givenName} {user_info.sn}'
                    if user_info.destription:
                        user_display += f' - {user_info.destription}'
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('badge').classes('text-blue-600 text-lg')
                        ui.label(user_display).classes('text-xl font-bold text-blue-700')
                else:
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('badge').classes('text-gray-600 text-lg')
                        ui.label(current_user.username).classes('text-xl font-bold text-gray-800')
            
            with ui.row().classes('items-center gap-2'):
                # Кнопка показа/скрытия завершенных процессов
                show_completed_button = ui.button(
                    'Показать завершенные',
                    icon='visibility',
                    on_click=toggle_completed
                ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                
                # Фильтр по дням (скрыт по умолчанию)
                period_select = ui.select(
                    {
                        7: 'Последние 7 дней',
                        30: 'Последние 30 дней',
                        90: 'Последние 90 дней',
                        180: 'Последние 180 дней'
                    },
                    value=7,
                    label='Период',
                    on_change=on_period_change
                ).classes('mr-4')
                period_select.set_visibility(False)
                
                ui.button(
                    'Обновить', 
                    icon='refresh', 
                    on_click=refresh_processes
                ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        # Создаем структуру: диаграмма Ганта сверху на всю ширину, под ней процессы
        # Контейнер для диаграммы Ганта (на всю ширину) - обернут в expansion для сворачивания
        with ui.expansion('Графика', icon='timeline', value=False).classes('w-full mb-4') as gantt_expansion:
            gantt_container = ui.column().classes('w-full')
            gantt_container.set_visibility(False)  # Скрываем по умолчанию
            
            # Обработчик открытия/закрытия expansion
            def on_gantt_expansion_change(e):
                if e.value:
                    gantt_container.set_visibility(True)
                else:
                    gantt_container.set_visibility(False)
            
            gantt_expansion.on('update:modelValue', on_gantt_expansion_change)

        # Контейнер для процессов (занимает всю ширину)
        with ui.column().classes('w-full'):
            processes_container = ui.column().classes('w-full')
            # Контейнер для завершенных процессов (скрыт по умолчанию)
            completed_processes_container = ui.column().classes('w-full')
            completed_processes_container.set_visibility(False)
        
        # Загружаем процессы
        ui.timer(0.1, lambda: refresh_processes(), once=True)

async def load_my_processes(processes_container, completed_processes_container, gantt_container, creator_username, show_completed: bool = False, days: int = 7):
    """Загружает процессы созданные пользователем"""
    global _process_cards
    
    from datetime import datetime, timezone, timedelta
    
    try:
        # ОЧИЩАЕМ КОНТЕЙНЕРЫ ПЕРЕД ЗАГРУЗКОЙ
        processes_container.clear()
        completed_processes_container.clear()
        gantt_container.clear()  # Очищаем контейнер диаграммы
        _process_cards.clear()  # Очищаем словарь карточек
        
        camunda_client = await create_camunda_client()
        
        # Получаем активные процессы
        active_processes = await camunda_client.get_processes_by_creator(creator_username, active_only=True)
        
        # Получаем завершенные процессы только если нужно их показать
        completed_processes = []
        if show_completed:
            completed_processes = await camunda_client.get_processes_by_creator(creator_username, active_only=False)
            
            # ИСКЛЮЧАЕМ АКТИВНЫЕ ПРОЦЕССЫ ИЗ ЗАВЕРШЕННЫХ (если они там есть)
            active_process_ids = {p['id'] for p in active_processes}
            completed_processes = [p for p in completed_processes if p.get('id') not in active_process_ids]
            
            # Фильтруем по дате завершения
            if days:
                try:
                    # Вычисляем дату N дней назад
                    days_ago = datetime.now(timezone.utc) - timedelta(days=days)
                    
                    filtered_completed = []
                    for process in completed_processes:
                        end_time = process.get('endTime', '')
                        if end_time:
                            try:
                                # Парсим дату завершения процесса
                                process_end_date = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                                if process_end_date >= days_ago:
                                    filtered_completed.append(process)
                            except Exception as e:
                                logger.warning(f'Ошибка парсинга даты завершения процесса {process.get("id", "unknown")}: {e}')
                                # Если не удалось распарсить, включаем процесс
                                filtered_completed.append(process)
                        else:
                            # Если нет endTime, включаем процесс
                            filtered_completed.append(process)
                    
                    completed_processes = filtered_completed
                    logger.info(f"Отфильтровано завершенных процессов за последние {days} дней: {len(completed_processes)}")
                except Exception as e:
                    logger.warning(f'Ошибка фильтрации завершенных процессов по дате: {e}')
        
        # Подготавливаем задачи для диаграммы Ганта из активных процессов
        tasks_for_gantt = []
        for process in active_processes:
            variables = process.get('variables', {})
            process_id = process.get('id', '')
            
            # Обрабатываем разные форматы переменных Camunda
            due_date_raw = variables.get('dueDate')
            due_date = ''
            
            if due_date_raw:
                # Если переменная - это словарь с полем 'value' (стандартный формат Camunda)
                if isinstance(due_date_raw, dict):
                    due_date = due_date_raw.get('value', '')
                # Если переменная - это строка
                elif isinstance(due_date_raw, str):
                    due_date = due_date_raw
                else:
                    due_date = str(due_date_raw)
            
            if due_date:
                process_name = (variables.get('taskName') or 
                               variables.get('documentName') or 
                               process.get('processDefinitionKey', 'Неизвестно'))
                
                # Получаем активную задачу для процесса, чтобы использовать её ID для ссылки
                task_id = ''
                try:
                    # Получаем активные задачи для процесса
                    endpoint = f'task?processInstanceId={process_id}'
                    response = await camunda_client._make_request('GET', endpoint)
                    response.raise_for_status()
                    tasks = response.json()
                    
                    # Берем первую активную задачу
                    if tasks and len(tasks) > 0:
                        task_id = tasks[0].get('id', '')
                        logger.debug(f"Найдена задача {task_id} для процесса {process_id}")
                except Exception as e:
                    logger.warning(f"Не удалось получить задачу для процесса {process_id}: {e}")
                    # Если не удалось получить задачу, используем process_instance_id как fallback
                    task_id = ''
                
                tasks_for_gantt.append({
                    'name': process_name,
                    'due': due_date,
                    'id': task_id if task_id else process_id,  # ИСПРАВЛЕНО: используем task_id если есть
                    'process_instance_id': process_id
                })
        
        # Добавляем диаграмму Ганта в отдельный контейнер (на всю ширину)
        with gantt_container:
            create_gantt_chart(
                tasks_for_gantt if tasks_for_gantt else [],
                title='Сроки по запущенным мной проектам:',
                name_field='name',
                due_field='due',
                id_field='id',
                process_instance_id_field='process_instance_id'
            )
            
            # Показываем контейнер после создания диаграммы
            gantt_container.set_visibility(True)
            
            # Добавляем отладочную информацию (можно убрать после проверки)
            if not tasks_for_gantt and active_processes:
                logger.info(f"Диаграмма Ганта: найдено {len(active_processes)} процессов, но ни у одного нет дедлайна")
                # Показываем информацию о переменных для отладки
                if active_processes:
                    sample_process = active_processes[0]
                    sample_variables = sample_process.get('variables', {})
                    logger.debug(f"Пример переменных процесса: {list(sample_variables.keys())}")
        
        # Активные процессы в processes_container
        with processes_container:
            if active_processes:
                ui.label('Активные процессы').classes('text-lg font-semibold mb-2')
                for process in active_processes:
                    create_process_card(process, is_active=True)
            
            if not active_processes and not show_completed:
                ui.label('У вас нет активных процессов').classes('text-gray-500 text-center mt-8')
        
        # Завершенные процессы отображаем в отдельном контейнере
        if show_completed:
            completed_processes_container.set_visibility(True)
            with completed_processes_container:
                if completed_processes:
                    ui.label('Завершенные процессы').classes('text-lg font-semibold mt-4 mb-2')
                    for process in completed_processes:
                        create_process_card(process, is_active=False)
                else:
                    ui.label('Нет завершенных процессов за выбранный период').classes('text-gray-500 text-center mt-4')
        else:
            # Скрываем и очищаем контейнер завершенных процессов
            completed_processes_container.set_visibility(False)
            completed_processes_container.clear()
            
    except Exception as e:
        processes_container.clear()
        completed_processes_container.clear()
        gantt_container.clear()  # Очищаем диаграмму при ошибке
        with processes_container:
            ui.label(f'Ошибка при загрузке процессов: {str(e)}').classes('text-red-600')
        logger.error(f"Ошибка при загрузке процессов: {e}", exc_info=True)


def create_process_card(process, is_active=True):
    """Создает карточку процесса с расширенной информацией"""
    from utils.date_utils import format_date_russian
    from components.gantt_chart import parse_task_deadline
    from datetime import datetime
    global _selected_process_id, _process_cards
    
    process_id = process.get('id', 'Неизвестно')
    
    # Определяем, является ли этот процесс выбранным
    is_selected = _selected_process_id and (process_id == _selected_process_id)
    
    # Выбираем стили в зависимости от того, выбран ли процесс
    if is_active:
        if is_selected:
            status_color = 'border-blue-600'
            bg_class = 'bg-blue-50'
            border_style = 'border-2 border-blue-600'
            shadow_class = 'shadow-lg'
        else:
            status_color = 'border-green-500'
            bg_class = ''
            border_style = 'border border-gray-200'
            shadow_class = ''
    else:
        if is_selected:
            status_color = 'border-blue-600'
            bg_class = 'bg-blue-50'
            border_style = 'border-2 border-blue-600'
            shadow_class = 'shadow-lg'
        else:
            status_color = 'border-gray-500'
            bg_class = ''
            border_style = 'border border-gray-200'
            shadow_class = ''
    
    status_text = 'Активен' if is_active else 'Завершен'
    
    # Извлекаем переменные процесса
    variables = process.get('variables', {})
    
    # Получаем название процесса
    process_name = (variables.get('taskName') or 
                   variables.get('documentName') or 
                   process.get('processDefinitionKey', 'Неизвестно'))
    
    # Обрезаем длинные названия процессов
    if len(process_name) > 80:
        process_name = process_name[:80] + '...'
    
    # Получаем список назначенных пользователей
    assignee_list = variables.get('assigneeList', [])
    if isinstance(assignee_list, str):
        try:
            import json
            assignee_list = json.loads(assignee_list)
        except:
            assignee_list = []
    
    # Получаем информацию о прогрессе (для активных процессов)
    progress_info = process.get('progress')
    
    # Получаем описание задачи
    task_description = variables.get('taskDescription', '')
    if task_description and len(task_description) > 100:
        task_description = task_description[:100] + '...'
    
    # Получаем дату дедлайна и форматируем её
    due_date_raw = variables.get('dueDate', '')
    due_date_formatted = None
    due_date_diff_days = None
    
    if due_date_raw:
        # Обрабатываем разные форматы переменных Camunda
        if isinstance(due_date_raw, dict):
            due_date_raw = due_date_raw.get('value', '')
        
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
                logger.warning(f"Не удалось обработать дату дедлайна для процесса {process_id}: {e}")

    # Извлекаем documentId из переменных процесса
    document_id = None
    document_id_raw = variables.get('documentId') or variables.get('mayanDocumentId')
    if document_id_raw:
        # Обрабатываем разные форматы переменных Camunda
        if isinstance(document_id_raw, dict) and 'value' in document_id_raw:
            document_id = str(document_id_raw['value']).strip() if document_id_raw['value'] else None
        elif isinstance(document_id_raw, str):
            document_id = document_id_raw.strip() if document_id_raw else None
        else:
            document_id = str(document_id_raw).strip() if document_id_raw else None
    
    # Определяем фон карточки в зависимости от дедлайна (только для активных процессов)
    card_bg_class = ''
    if is_active and due_date_diff_days is not None:
        if due_date_diff_days < 0:
            # Дедлайн прошел - красный фон для всей карточки
            card_bg_class = 'bg-red-50'
        elif due_date_diff_days <= 2:
            # Осталось 2 дня или меньше - оранжевый фон для всей карточки
            card_bg_class = 'bg-orange-50'
    
    # Создаем карточку с условными стилями и data-атрибутами
    # Добавляем card_bg_class к существующим классам, но только если процесс не выбран
    if is_selected:
        # Если процесс выбран, используем синий фон (приоритет выше)
        final_bg_class = bg_class
    else:
        # Если не выбран, применяем цвет фона в зависимости от дедлайна
        final_bg_class = card_bg_class if card_bg_class else bg_class
    
    card = ui.card().classes(f'mb-3 p-4 border-l-4 {status_color} w-full max-w-full {final_bg_class} {border_style} {shadow_class}')
    # Добавляем data-атрибуты для поиска через JavaScript
    card.props(f'data-process-id="{process_id}"')
    
    # Сохраняем ссылку на карточку
    indicator_row = None
    details_container = None  # Контейнер для деталей внутри карточки
    
    with card:
        # Добавляем индикатор выбранного процесса
        if is_selected:
            indicator_row = ui.row().classes('w-full items-center gap-2 mb-2')
            with indicator_row:
                ui.icon('check_circle').classes('text-blue-600 text-lg')
                ui.label('Выбрано').classes('text-blue-600 font-semibold text-sm')
        
        with ui.row().classes('items-start justify-between w-full gap-4'):
            with ui.column().classes('flex-1 min-w-0'):
                # Название процесса - с переносом текста
                ui.label(f'Процесс: {process_name}').classes('text-lg font-semibold break-words mb-2')
                
                # Статус
                ui.label(f'Статус: {status_text}').classes('text-sm font-medium mb-1')
                
                # Дата создания
                start_time = process.get('startTime', 'Неизвестно')
                if start_time and start_time != 'Неизвестно':
                    formatted_time = format_date_russian(start_time)
                    ui.label(f'Создан: {formatted_time}').classes('text-sm text-gray-600 mb-1')
                
                # Кому назначен процесс
                # if assignee_list:
                #     assignees_text = ', '.join(assignee_list) if isinstance(assignee_list, list) else str(assignee_list)
                #     if len(assignees_text) > 60:
                #         assignees_text = assignees_text[:60] + '...'
                #     ui.label(f'Назначено: {assignees_text}').classes('text-sm text-gray-700 break-words mb-1')
                
                # Стадия выполнения (прогресс)
                if is_active and progress_info:
                    # Используем правильные ключи из get_task_progress
                    completed = progress_info.get('completed_reviews', 0)
                    total = progress_info.get('total_reviews', 0)
                    
                    # Если total_reviews равен 0, пытаемся использовать assigneeList или signerList как fallback
                    if total == 0:
                        # Получаем список пользователей из переменных
                        variables = process.get('variables', {})
                        assignee_list = variables.get('assigneeList', [])
                        signer_list = variables.get('signerList', [])
                        
                        # Парсим списки если они строки
                        if isinstance(assignee_list, str):
                            try:
                                import json
                                assignee_list = json.loads(assignee_list)
                            except:
                                assignee_list = []
                        
                        if isinstance(signer_list, str):
                            try:
                                import json
                                signer_list = json.loads(signer_list)
                            except:
                                signer_list = []
                        
                        # Используем signerList для задач подписания, если assigneeList пуст
                        user_list = signer_list if signer_list and not assignee_list else assignee_list
                        total = len(user_list) if user_list else 0
                    
                    if total > 0:
                        progress_percent = round((completed / total) * 100)
                        
                        # Прогресс-бар с текстом в одной строке
                        with ui.row().classes('w-full items-center gap-2 my-2 mb-2'):
                            ui.linear_progress(value=progress_percent / 100, show_value=False).classes('flex-1 h-4 min-w-0')
                            ui.label(f'{completed}/{total} ({progress_percent}%)').classes('text-xs text-gray-600 whitespace-nowrap')
                    
                    # Список пользователей и их статус
                    if progress_info.get('user_status'):
                        with ui.expansion('Статус пользователей', icon='people').classes('w-full mt-2 mb-2'):
                            for user_status in progress_info.get('user_status', []):
                                status_color = 'text-green-600' if user_status['completed'] else 'text-orange-600'
                                status_icon = 'check_circle' if user_status['completed'] else 'schedule'
                                
                                # Получаем данные пользователя вместо логина
                                user_login = user_status['user']
                                user_display_name = get_user_display_name(user_login)
                                
                                with ui.row().classes('w-full items-center gap-2 mb-1'):
                                    ui.icon(status_icon).classes(f'{status_color} text-sm')
                                    ui.label(f'{user_display_name}').classes(f'text-sm {status_color} font-medium')
                                    ui.label(f'({user_status["status"]})').classes('text-xs text-gray-500')
                
                # Описание задачи (если есть)
                if task_description:
                    ui.label(f'Описание: {task_description}').classes('text-sm text-gray-600 italic break-words mb-1')
                
                # Дедлайн (если есть) - с раскраской в зависимости от количества дней
                if due_date_formatted:
                    # Определяем цвет в зависимости от количества дней до дедлайна
                    if due_date_diff_days is not None:
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
                        
                        with ui.row().classes('items-center gap-2 mb-1'):
                            ui.label('Срок исполнения:').classes('text-sm font-medium')
                            ui.label(due_date_formatted).classes('text-sm font-semibold px-2 py-1 rounded').style(f'background-color: {bg_color}; color: {text_color};')
                    else:
                        # Если не удалось вычислить разницу дней, показываем без раскраски
                        ui.label(f'Срок исполнения: {due_date_formatted}').classes('text-sm text-orange-600 mb-1')

                # Ссылка на документ (если есть)
                if document_id:
                    async def open_document():
                        try:
                            from services.mayan_connector import MayanClient
                            from components.document_viewer import show_document_viewer
                            
                            mayan_client = await MayanClient.create_with_session_user()
                            await show_document_viewer(str(document_id), mayan_client=mayan_client)
                        except Exception as e:
                            logger.error(f"Ошибка при открытии документа {document_id}: {e}", exc_info=True)
                            ui.notify(f'Ошибка при открытии документа: {str(e)}', type='error')
                    
                    ui.button(
                        'Открыть документ',
                        icon='description',
                        on_click=open_document
                    ).classes('bg-green-500 text-white whitespace-nowrap text-xs px-2 py-1 h-7 mt-1')
            
            with ui.column().classes('items-end flex-shrink-0'):
                if is_active:
                    ui.button('Просмотр', icon='visibility', on_click=lambda pid=process_id, card_container=card: show_process_details(pid, card_container)).classes('bg-blue-500 text-white whitespace-nowrap text-xs px-2 py-1 h-7')
                else:
                    ui.button('История', icon='history', on_click=lambda pid=process_id, card_container=card: show_process_history(pid, card_container)).classes('bg-gray-500 text-white whitespace-nowrap text-xs px-2 py-1 h-7')
        
        # Контейнер для деталей процесса (скрыт по умолчанию)
        details_container = ui.column().classes('w-full mt-4 hidden')
        details_container.set_visibility(False)
    
    # Сохраняем ссылку на карточку
    _process_cards[process_id] = {
        'card': card,
        'indicator': indicator_row,
        'details_container': details_container,
        'process_id': process_id,
        'is_active': is_active
    }

async def show_process_details(process_id, card_container):
    """Показывает детали активного процесса внизу карточки"""
    global _selected_process_id
    
    # Обновляем выбранный процесс
    old_selected_id = _selected_process_id
    _selected_process_id = process_id
    
    # Получаем контейнер деталей из словаря карточек
    card_info = _process_cards.get(process_id)
    if not card_info:
        return
    
    details_container = card_info.get('details_container')
    if not details_container:
        return
    
    # Переключаем видимость деталей
    is_visible = details_container.visible
    if is_visible:
        # Если детали уже открыты, закрываем их
        details_container.set_visibility(False)
        details_container.clear()
        _selected_process_id = None
        # Обновляем стили карточки
        update_card_selection(old_selected_id, None)
        return
    
    # Обновляем стили карточек без перезагрузки списка
    if old_selected_id != _selected_process_id:
        update_card_selection(old_selected_id, _selected_process_id)
    
    try:
        camunda_client = await create_camunda_client()
        
        # Получаем расширенную информацию о процессе
        process_info = await camunda_client.get_process_with_variables(process_id, is_active=True)
        if not process_info:
            ui.notify('Не удалось получить информацию о процессе', type='error')
            return
        
        variables = process_info.get('variables', {})
        progress_info = process_info.get('progress')
        
        # Очищаем контейнер деталей
        details_container.clear()
        details_container.set_visibility(True)
        
        with details_container:
            with ui.card().classes('p-4 w-full bg-gray-50 border border-gray-200'):
                ui.label('Детали процесса').classes('text-lg font-bold mb-4')
                
                # Основная информация
                ui.label(f'ID процесса: {process_id}').classes('text-sm font-mono text-gray-600 mb-2 break-all')
                
                # Название процесса - с обрезкой и переносом
                process_name = variables.get('taskName') or variables.get('documentName') or 'Неизвестно'
                if len(process_name) > 100:
                    process_name = process_name[:100] + '...'
                ui.label(f'Название: {process_name}').classes('text-base font-semibold mb-3 break-words')
                
                # Описание
                task_description = variables.get('taskDescription', '')
                if task_description:
                    ui.label('Описание:').classes('text-sm font-semibold mb-1')
                    ui.label(task_description).classes('text-sm mb-3 text-gray-600 break-words')
                
                # Статус процесса
                # ui.label('Статус: Активен').classes('text-sm font-medium text-green-600 mb-3')
                
                # Статус пользователей
                if progress_info:
                    ui.label('Статус пользователей:').classes('text-sm font-semibold mb-2')
                    
                    for user_status in progress_info.get('user_status', []):
                        status_color = 'text-green-600' if user_status['completed'] else 'text-orange-600'
                        status_icon = '✅' if user_status['completed'] else '⏳'
                        
                        # Получаем данные пользователя вместо логина
                        user_login = user_status['user']
                        user_display_name = get_user_display_name(user_login)
                        
                        with ui.row().classes('items-center mb-2'):
                            ui.label(f'{status_icon} {user_display_name}').classes(f'text-sm {status_color} font-medium')
                        with ui.row().classes('items-center mb-2'):    
                            ui.label(f'({user_status["status"]})').classes('text-xs text-gray-500 ml-2')
                
                # Дополнительная информация
                ui.label('Дополнительная информация:').classes('text-sm font-semibold mt-4 mb-2')
                
                # Дата создания
                start_time = process_info.get('startTime', '')
                if start_time:
                    from utils.date_utils import format_date_russian
                    formatted_start = format_date_russian(start_time)
                    ui.label(f'Создан: {formatted_start}').classes('text-sm text-gray-600')
                
                # Дедлайн
                # due_date = variables.get('dueDate', '')
                # if due_date:
                #     from utils.date_utils import format_date_russian
                #     formatted_due = format_date_russian(due_date)
                #     ui.label(f'Срок исполнения: {formatted_due}').classes('text-sm text-orange-600')
                
                # Бизнес-ключ
                if process_info.get('businessKey'):
                    business_key = str(process_info.get('businessKey'))
                    if len(business_key) > 50:
                        business_key = business_key[:50] + '...'
                    ui.label(f'Бизнес-ключ: {business_key}').classes('text-xs text-gray-500 mt-2 break-all')
        
    except Exception as e:
        ui.notify(f'Ошибка при получении деталей процесса: {str(e)}', type='error')
        logger.error(f"Ошибка в show_process_details: {e}", exc_info=True)

async def show_process_history(process_id, card_container):
    """Показывает историю завершенного процесса внизу карточки"""
    global _selected_process_id
    
    # Обновляем выбранный процесс
    old_selected_id = _selected_process_id
    _selected_process_id = process_id
    
    # Получаем контейнер деталей из словаря карточек
    card_info = _process_cards.get(process_id)
    if not card_info:
        return
    
    details_container = card_info.get('details_container')
    if not details_container:
        return
    
    # Переключаем видимость деталей
    is_visible = details_container.visible
    if is_visible:
        # Если детали уже открыты, закрываем их
        details_container.set_visibility(False)
        details_container.clear()
        _selected_process_id = None
        # Обновляем стили карточки
        update_card_selection(old_selected_id, None)
        return
    
    # Обновляем стили карточек без перезагрузки списка
    if old_selected_id != _selected_process_id:
        update_card_selection(old_selected_id, _selected_process_id)
    
    try:
        camunda_client = await create_camunda_client()
        
        # Получаем историческую информацию о процессе
        history_process = await camunda_client.get_history_process_instance_by_id(process_id)
        if not history_process:
            ui.notify('История процесса не найдена', type='warning')
            return
        
        # Получаем расширенную информацию
        process_info = await camunda_client.get_process_with_variables(process_id, is_active=False)
        variables = process_info.get('variables', {}) if process_info else {}
        
        # Очищаем контейнер деталей
        details_container.clear()
        details_container.set_visibility(True)
        
        with details_container:
            with ui.card().classes('p-4 w-full bg-gray-50 border border-gray-200'):
                ui.label('История процесса').classes('text-lg font-bold mb-4')
                
                # Основная информация о процессе
                ui.label('Информация о процессе').classes('text-base font-semibold mb-2')
                ui.label(f'ID процесса: {process_id}').classes('text-sm font-mono text-gray-600 mb-1 break-all')
                
                process_key = history_process.get('processDefinitionKey', 'Неизвестно')
                ui.label(f'Ключ процесса: {process_key}').classes('text-sm mb-1 break-words')
                
                # Название процесса - с обрезкой и переносом
                process_name = variables.get('taskName') or variables.get('documentName') or process_key
                if len(process_name) > 100:
                    process_name = process_name[:100] + '...'
                ui.label(f'Название: {process_name}').classes('text-base font-semibold mb-3 break-words')
                
                # Даты
                from utils.date_utils import format_date_russian
                
                start_time = history_process.get('startTime', '')
                if start_time:
                    formatted_start = format_date_russian(start_time)
                    ui.label(f'Начало: {formatted_start}').classes('text-sm text-gray-600 mb-1')
                
                end_time = history_process.get('endTime', '')
                if end_time:
                    formatted_end = format_date_russian(end_time)
                    ui.label(f'Завершение: {formatted_end}').classes('text-sm text-gray-600 mb-1')
                    ui.label('Статус: Завершен').classes('text-sm font-medium text-gray-600 mb-3')
                
                # Длительность
                duration_ms = history_process.get('durationInMillis', 0)
                if duration_ms:
                    duration_sec = duration_ms / 1000
                    if duration_sec < 60:
                        duration_text = f'{duration_sec:.1f} сек'
                    elif duration_sec < 3600:
                        duration_text = f'{duration_sec/60:.1f} мин'
                    else:
                        duration_text = f'{duration_sec/3600:.1f} ч'
                    ui.label(f'Длительность: {duration_text}').classes('text-sm text-gray-600 mb-3')
                
                # Информация о назначенных пользователях
                assignee_list = variables.get('assigneeList', [])
                if isinstance(assignee_list, str):
                    try:
                        import json
                        assignee_list = json.loads(assignee_list)
                    except:
                        assignee_list = []
                
                if assignee_list:
                    ui.label('Назначено пользователям:').classes('text-sm font-semibold mb-2')
                    for assignee in assignee_list:
                        # Получаем данные пользователя вместо логина
                        user_display_name = get_user_display_name(assignee)
                        
                        with ui.row().classes('items-center mb-1'):
                            ui.label(f'• {user_display_name}').classes('text-sm text-gray-600')
                            # Показываем логин в скобках меньшим шрифтом для справки
                            ui.label(f'[{assignee}]').classes('text-xs text-gray-400 ml-2')
                
                # Бизнес-ключ
                if history_process.get('businessKey'):
                    business_key = str(history_process.get('businessKey'))
                    if len(business_key) > 50:
                        business_key = business_key[:50] + '...'
                    ui.label(f'Бизнес-ключ: {business_key}').classes('text-xs text-gray-500 mt-3 break-all')
        
    except Exception as e:
        ui.notify(f'Ошибка при получении истории процесса: {str(e)}', type='error')
        logger.error(f"Ошибка при получении истории процесса {process_id}: {e}", exc_info=True)

def update_card_selection(old_selected_id, new_selected_id):
    """Обновляет стили карточек при выборе процесса"""
    logger.info(f"Обновляем выделение процесса: старая задача={old_selected_id}, новая задача={new_selected_id}")
    
    # Убираем выделение со старой карточки
    if old_selected_id:
        old_card_info = _process_cards.get(old_selected_id)
        if old_card_info:
            old_card = old_card_info.get('card')
            if old_card:
                # Восстанавливаем оригинальные стили
                is_active = old_card_info.get('is_active', True)
                if is_active:
                    old_card.classes(remove='border-l-4 border-blue-600 border-2 border-blue-600 shadow-lg bg-blue-50')
                    old_card.classes(add='border-l-4 border-green-500 border border-gray-200')
                else:
                    old_card.classes(remove='border-l-4 border-blue-600 border-2 border-blue-600 shadow-lg bg-blue-50')
                    old_card.classes(add='border-l-4 border-gray-500 border border-gray-200')
                
                # Удаляем индикатор
                indicator = old_card_info.get('indicator')
                if indicator:
                    indicator.set_visibility(False)
    
    # Добавляем выделение новой карточке
    if new_selected_id:
        new_card_info = _process_cards.get(new_selected_id)
        if new_card_info:
            new_card = new_card_info.get('card')
            if new_card:
                # Добавляем стили выделения
                new_card.classes(remove='border-l-4 border-green-500 border-gray-500 border border-gray-200')
                new_card.classes(add='border-l-4 border-blue-600 border-2 border-blue-600 shadow-lg bg-blue-50')
                
                # Добавляем индикатор
                indicator = new_card_info.get('indicator')
                if indicator:
                    indicator.set_visibility(True)
                else:
                    # Создаем новый индикатор если его нет
                    with new_card:
                        indicator_row = ui.row().classes('w-full items-center gap-2 mb-2')
                        with indicator_row:
                            ui.icon('check_circle').classes('text-blue-600 text-lg')
                            ui.label('Выбрано').classes('text-blue-600 font-semibold text-sm')
                        new_card_info['indicator'] = indicator_row

def export_process_history(process_id, history_process, history_variables, history_tasks):
    """Экспортирует историю процесса в CSV"""
    try:
        import csv
        import io
        from datetime import datetime
        
        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовки
        writer.writerow(['История процесса', process_id])
        writer.writerow(['Дата экспорта', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Информация о процессе
        writer.writerow(['Информация о процессе'])
        writer.writerow(['ID процесса', process_id])
        writer.writerow(['Ключ процесса', history_process.get('processDefinitionKey', 'Неизвестно')])
        writer.writerow(['Начало', history_process.get('startTime', 'Неизвестно')])
        writer.writerow(['Завершение', history_process.get('endTime', 'Не завершен')])
        writer.writerow(['Длительность (сек)', history_process.get('durationInMillis', 0) / 1000])
        writer.writerow(['Создатель', history_variables.get('creatorName', 'Неизвестно')])
        writer.writerow([])
        
        # Информация о документе
        document_name = history_variables.get('documentName', 'Неизвестно')
        if document_name != 'Неизвестно':
            writer.writerow(['Информация о документе'])
            writer.writerow(['Название документа', document_name])
            writer.writerow([])
        
        # Детали выполнения
        writer.writerow(['Детали выполнения'])
        writer.writerow(['Пользователь', 'Статус', 'Начало', 'Завершение', 'Длительность (сек)', 'Комментарий'])
        
        for task in history_tasks:
            assignee = task.get('assignee', 'Не назначен')
            start_time = task.get('startTime', '')
            end_time = task.get('endTime', '')
            duration = task.get('duration', 0)
            
            # Определяем статус
            delete_reason = task.get('deleteReason', '')
            if delete_reason == 'completed':
                status = 'Завершено'
            elif delete_reason == 'cancelled':
                status = 'Отменено'
            else:
                status = 'Не завершено'
            
            # Получаем комментарий
            comment = ''
            try:
                user_comments = history_variables.get('userComments', {})
                if isinstance(user_comments, str):
                    import json
                    user_comments = json.loads(user_comments)
                comment = user_comments.get(assignee, '')
            except:
                pass
            
            writer.writerow([
                assignee,
                status,
                start_time[:19] if start_time else '',
                end_time[:19] if end_time else '',
                duration / 1000 if duration else 0,
                comment
            ])
        
        # Получаем CSV данные
        csv_data = output.getvalue()
        output.close()
        
        # Создаем файл для скачивания
        filename = f'process_history_{process_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        # В NiceGUI можно использовать ui.download для скачивания файла
        ui.download(csv_data.encode('utf-8'), filename, 'text/csv')
        
        ui.notify(f'История процесса экспортирована в файл {filename}', type='success')
        
    except Exception as e:
        ui.notify(f'Ошибка при экспорте истории: {str(e)}', type='error')
        logger.error(f"Ошибка при экспорте истории процесса {process_id}: {e}", exc_info=True)