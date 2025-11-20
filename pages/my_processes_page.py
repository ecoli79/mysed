from nicegui import ui
from services.camunda_connector import CamundaClient, create_camunda_client
from auth.middleware import get_current_user, require_auth
from config.settings import config
import logging
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

# Глобальная переменная для контейнера деталей процесса
_details_container = None

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
            
            ui.button('Обновить', icon='refresh', on_click=lambda: load_my_processes(processes_container, details_container, current_user.username)).classes('bg-blue-500 text-white')
        
        # Создаем разделенную структуру: слева процессы, справа детали
        with ui.row().classes('w-full gap-4'):
            # Левая колонка - список процессов
            with ui.column().classes('flex-1'):
                processes_container = ui.column().classes('w-full')
            
            # Правая колонка - детали процесса
            with ui.column().classes('w-1/3 min-w-[400px]'):
                details_container = ui.column().classes('w-full')
                _details_container = details_container
                
        
        # Загружаем процессы
        ui.timer(0.1, lambda: load_my_processes(processes_container, details_container, current_user.username), once=True)

async def load_my_processes(processes_container, details_container, creator_username):
    """Загружает процессы созданные пользователем"""
    try:
        # ОЧИЩАЕМ КОНТЕЙНЕРЫ ПЕРЕД ЗАГРУЗКОЙ
        processes_container.clear()
        details_container.clear()  # Очищаем блок с деталями процесса
        
        camunda_client = await create_camunda_client()
        
        # Получаем активные процессы
        active_processes = await camunda_client.get_processes_by_creator(creator_username, active_only=True)
        
        # Получаем завершенные процессы
        completed_processes = await camunda_client.get_processes_by_creator(creator_username, active_only=False)
        
        # ИСКЛЮЧАЕМ АКТИВНЫЕ ПРОЦЕССЫ ИЗ ЗАВЕРШЕННЫХ (если они там есть)
        active_process_ids = {p['id'] for p in active_processes}
        completed_processes = [p for p in completed_processes if p.get('id') not in active_process_ids]
        
        with processes_container:
            # Активные процессы
            if active_processes:
                ui.label('Активные процессы').classes('text-lg font-semibold mt-4 mb-2')
                for process in active_processes:
                    create_process_card(process, is_active=True, details_container=details_container)
            
            # Завершенные процессы
            if completed_processes:
                ui.label('Завершенные процессы').classes('text-lg font-semibold mt-4 mb-2')
                for process in completed_processes:
                    create_process_card(process, is_active=False, details_container=details_container)
            
            if not active_processes and not completed_processes:
                ui.label('У вас нет созданных процессов').classes('text-gray-500 text-center mt-8')
    except Exception as e:
        processes_container.clear()
        details_container.clear()  # Также очищаем при ошибке
        with processes_container:
            ui.label(f'Ошибка при загрузке процессов: {str(e)}').classes('text-red-600')
        logger.error(f"Ошибка при загрузке процессов: {e}", exc_info=True)


def create_process_card(process, is_active=True, details_container=None):
    """Создает карточку процесса с расширенной информацией"""
    from utils.date_utils import format_date_russian
    
    status_color = 'border-green-500' if is_active else 'border-gray-500'
    status_text = 'Активен' if is_active else 'Завершен'
    
    # Извлекаем переменные процесса
    variables = process.get('variables', {})
    process_id = process.get('id', 'Неизвестно')
    
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
    due_date = variables.get('dueDate', '')
    if due_date:
        due_date = format_date_russian(due_date)
    
    # Обрезаем длинный ID процесса для отображения
    display_process_id = process_id
    if len(display_process_id) > 40:
        display_process_id = display_process_id[:40] + '...'
    
    with ui.card().classes(f'mb-3 p-4 border-l-4 {status_color} w-full max-w-full'):
        with ui.row().classes('items-start justify-between w-full gap-4'):
            with ui.column().classes('flex-1 min-w-0'):
                # Название процесса - с переносом текста
                ui.label(f'Процесс: {process_name}').classes('text-lg font-semibold break-words mb-2')
                
                # ID процесса - с переносом и обрезкой
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.label('ID:').classes('text-sm font-medium text-gray-500 whitespace-nowrap')
                    ui.label(display_process_id).classes('text-sm font-mono text-gray-600 break-all')
                
                # Статус
                ui.label(f'Статус: {status_text}').classes('text-sm font-medium mb-1')
                
                # Дата создания
                start_time = process.get('startTime', 'Неизвестно')
                if start_time and start_time != 'Неизвестно':
                    formatted_time = format_date_russian(start_time)
                    ui.label(f'Создан: {formatted_time}').classes('text-sm text-gray-600 mb-1')
                
                # Кому назначен процесс
                if assignee_list:
                    assignees_text = ', '.join(assignee_list) if isinstance(assignee_list, list) else str(assignee_list)
                    if len(assignees_text) > 60:
                        assignees_text = assignees_text[:60] + '...'
                    ui.label(f'Назначено: {assignees_text}').classes('text-sm text-gray-700 break-words mb-1')
                
                # Стадия выполнения (прогресс)
                if is_active and progress_info:
                    completed = progress_info.get('nr_of_completed_instances', 0)
                    total = progress_info.get('nr_of_instances', len(assignee_list) if assignee_list else 0)
                    if total > 0:
                        progress_percent = round((completed / total) * 100)
                        
                        # Прогресс-бар с текстом в одной строке
                        with ui.row().classes('w-full items-center gap-2 my-2 mb-2'):
                            ui.linear_progress(value=progress_percent / 100, show_value=False).classes('flex-1 h-4 min-w-0')
                            ui.label(f'{completed}/{total} ({progress_percent}%)').classes('text-xs text-gray-600 whitespace-nowrap')
                
                # Описание задачи (если есть)
                if task_description:
                    ui.label(f'Описание: {task_description}').classes('text-sm text-gray-600 italic break-words mb-1')
                
                # Дедлайн (если есть) - теперь отформатирован
                if due_date:
                    ui.label(f'Срок исполнения: {due_date}').classes('text-sm text-orange-600 mb-1')
                
                # Бизнес-ключ
                if process.get('businessKey'):
                    business_key = str(process.get('businessKey'))
                    if len(business_key) > 50:
                        business_key = business_key[:50] + '...'
                    ui.label(f'Бизнес-ключ: {business_key}').classes('text-xs text-gray-500 break-all')
            
            with ui.column().classes('items-end flex-shrink-0'):
                if is_active:
                    ui.button('Просмотр', icon='visibility', on_click=lambda pid=process_id, det_container=details_container: show_process_details(pid, det_container)).classes('bg-blue-500 text-white whitespace-nowrap')
                else:
                    ui.button('История', icon='history', on_click=lambda pid=process_id, det_container=details_container: show_process_history(pid, det_container)).classes('bg-gray-500 text-white whitespace-nowrap')

async def show_process_details(process_id, details_container):
    """Показывает детали активного процесса справа"""
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
        
        with details_container:
            with ui.card().classes('p-6 w-full max-w-full'):
                ui.label('Детали процесса').classes('text-xl font-bold mb-4')
                
                # Основная информация
                ui.label(f'ID процесса: {process_id}').classes('text-sm font-mono text-gray-600 mb-2 break-all')
                
                # Название процесса - с обрезкой и переносом
                process_name = variables.get('taskName') or variables.get('documentName') or 'Неизвестно'
                if len(process_name) > 100:
                    process_name = process_name[:100] + '...'
                ui.label(f'Название: {process_name}').classes('text-lg font-semibold mb-3 break-words')
                
                # Описание
                task_description = variables.get('taskDescription', '')
                if task_description:
                    ui.label('Описание:').classes('text-sm font-semibold mb-1')
                    ui.label(task_description).classes('text-sm mb-3 text-gray-600 break-words')
                
                # Статус процесса
                ui.label('Статус: Активен').classes('text-sm font-medium text-green-600 mb-3')
                
                # Прогресс выполнения
                if progress_info:
                    completed = progress_info.get('nr_of_completed_instances', 0)
                    total = progress_info.get('nr_of_instances', 0)
                    
                    # Пересчитываем процент для точного отображения
                    if total > 0:
                        progress_percent = round((completed / total) * 100)
                    else:
                        progress_percent = round(progress_info.get('progress_percent', 0))
                    
                    ui.label('Прогресс выполнения:').classes('text-sm font-semibold mb-2')
                    
                    # Прогресс-бар с текстом в одной строке
                    with ui.row().classes('w-full items-center gap-2 my-2 mb-4'):
                        ui.linear_progress(value=progress_percent / 100, show_value=False).classes('flex-1 h-4')
                        ui.label(f'{completed}/{total} ({progress_percent}%)').classes('text-xs text-gray-600 whitespace-nowrap')
                    
                    # Статус пользователей
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
                due_date = variables.get('dueDate', '')
                if due_date:
                    from utils.date_utils import format_date_russian
                    formatted_due = format_date_russian(due_date)
                    ui.label(f'Срок исполнения: {formatted_due}').classes('text-sm text-orange-600')
                
                # Бизнес-ключ
                if process_info.get('businessKey'):
                    business_key = str(process_info.get('businessKey'))
                    if len(business_key) > 50:
                        business_key = business_key[:50] + '...'
                    ui.label(f'Бизнес-ключ: {business_key}').classes('text-xs text-gray-500 mt-2 break-all')
        
    except Exception as e:
        ui.notify(f'Ошибка при получении деталей процесса: {str(e)}', type='error')
        logger.error(f"Ошибка в show_process_details: {e}", exc_info=True)

async def show_process_history(process_id, details_container):
    """Показывает историю завершенного процесса справа"""
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
        
        with details_container:
            with ui.card().classes('p-6 w-full max-w-full'):
                ui.label('История процесса').classes('text-xl font-bold mb-4')
                
                # Основная информация о процессе
                ui.label('Информация о процессе').classes('text-lg font-semibold mb-2')
                ui.label(f'ID процесса: {process_id}').classes('text-sm font-mono text-gray-600 mb-1 break-all')
                
                process_key = history_process.get('processDefinitionKey', 'Неизвестно')
                ui.label(f'Ключ процесса: {process_key}').classes('text-sm mb-1 break-words')
                
                # Название процесса - с обрезкой и переносом
                process_name = variables.get('taskName') or variables.get('documentName') or process_key
                if len(process_name) > 100:
                    process_name = process_name[:100] + '...'
                ui.label(f'Название: {process_name}').classes('text-lg font-semibold mb-3 break-words')
                
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
                    ui.label(f'Бизнес-ключ: {history_process["businessKey"]}').classes('text-xs text-gray-500 mt-3 break-all')
        
    except Exception as e:
        ui.notify(f'Ошибка при получении истории процесса: {str(e)}', type='error')
        logger.error(f"Ошибка при получении истории процесса {process_id}: {e}", exc_info=True)

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