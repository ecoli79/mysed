from nicegui import ui
from services.camunda_connector import CamundaClient
from auth.middleware import get_current_user, require_auth
from config.settings import config
import logging
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

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

@require_auth
def content():
    """Создает страницу для отслеживания созданных пользователем процессов"""
    current_user = get_current_user()
    if not current_user:
        ui.navigate.to('/login')
        return
    
    ui.page_title('Мои процессы')
    
    with ui.column().classes('w-full p-4'):
        ui.label(f'Процессы, созданные пользователем: {current_user.username}').classes('text-xl font-bold mb-4')
        
        # Контейнер для процессов
        processes_container = ui.column().classes('w-full')
        
        # Загружаем процессы
        load_my_processes(processes_container, current_user.username)

def load_my_processes(container, creator_username):
    """Загружает процессы созданные пользователем"""
    try:
        camunda_client = get_camunda_client()
        
        # Получаем активные процессы
        active_processes = camunda_client.get_processes_by_creator(creator_username, active_only=True)
        
        # Получаем завершенные процессы
        completed_processes = camunda_client.get_processes_by_creator(creator_username, active_only=False)
        
        with container:
            # Активные процессы
            if active_processes:
                ui.label('Активные процессы').classes('text-lg font-semibold mt-4 mb-2')
                for process in active_processes:
                    create_process_card(process, is_active=True)
            
            # Завершенные процессы
            if completed_processes:
                ui.label('Завершенные процессы').classes('text-lg font-semibold mt-4 mb-2')
                for process in completed_processes:
                    create_process_card(process, is_active=False)
            
            if not active_processes and not completed_processes:
                ui.label('У вас нет созданных процессов').classes('text-gray-500 text-center mt-8')
    except Exception as e:
        ui.label(f'Ошибка при загрузке процессов: {str(e)}').classes('text-red-600')
        logger.error(f"Ошибка при загрузке процессов: {e}", exc_info=True)


def create_process_card(process, is_active=True):
    """Создает карточку процесса"""
    status_color = 'border-green-500' if is_active else 'border-gray-500'
    status_text = 'Активен' if is_active else 'Завершен'
    
    with ui.card().classes(f'mb-3 p-4 border-l-4 {status_color}'):
        with ui.row().classes('items-start justify-between w-full'):
            with ui.column().classes('flex-1'):
                ui.label(f'Процесс: {process.get("processDefinitionKey", "Неизвестно")}').classes('text-lg font-semibold')
                ui.label(f'ID: {process["id"]}').classes('text-sm font-mono')
                ui.label(f'Статус: {status_text}').classes('text-sm')
                ui.label(f'Создан: {process.get("startTime", "Неизвестно")}').classes('text-sm text-gray-600')
                
                if process.get('businessKey'):
                    ui.label(f'Бизнес-ключ: {process["businessKey"]}').classes('text-sm text-gray-600')
            
            with ui.column().classes('items-end'):
                if is_active:
                    ui.button('Просмотр', icon='visibility', on_click=lambda: show_process_details(process['id'])).classes('bg-blue-500 text-white')
                else:
                    ui.button('История', icon='history', on_click=lambda: show_process_history(process['id'])).classes('bg-gray-500 text-white')

def show_process_details(process_id):
    """Показывает детали активного процесса"""
    try:
        camunda_client = get_camunda_client()
        progress_info = camunda_client.get_multi_instance_task_progress(process_id)
        
        with ui.dialog() as dialog:
            with ui.card().classes('p-6 w-full max-w-4xl'):
                ui.label('Детали процесса').classes('text-xl font-bold mb-4')
                
                # Основная информация
                ui.label(f'ID процесса: {process_id}').classes('text-sm mb-2')
                ui.label(f'Прогресс: {progress_info["completed_reviews"]}/{progress_info["total_reviews"]} ({progress_info["progress_percent"]:.1f}%)').classes('text-sm mb-2')
                
                # Статус пользователей
                ui.label('Статус пользователей:').classes('text-sm font-semibold mb-2')
                for user_status in progress_info['user_status']:
                    status_color = 'text-green-600' if user_status['completed'] else 'text-orange-600'
                    ui.label(f'• {user_status["user"]}: {user_status["status"]}').classes(f'text-sm {status_color}')
                
                ui.button('Закрыть', on_click=dialog.close).classes('bg-gray-500 text-white mt-4')
        
        dialog.open()
        
    except Exception as e:
        ui.notify(f'Ошибка при получении деталей процесса: {str(e)}', type='error')

def show_process_history(process_id):
    """Показывает историю завершенного процесса"""
    try:
        camunda_client = get_camunda_client()
        
        # Получаем историческую информацию о процессе
        history_process = camunda_client.get_history_process_instance_by_id(process_id)
        if not history_process:
            ui.notify('История процесса не найдена', type='warning')
            return
        
        # Получаем исторические переменные процесса
        history_variables = camunda_client.get_history_process_instance_variables_by_name(
            process_id, 
            ['taskName', 'taskDescription', 'documentName', 'documentContent', 
             'assigneeList', 'userComments', 'userCompletionDates', 'userStatus', 
             'userCompleted', 'processCreator', 'creatorName']
        )
        
        # Получаем исторические задачи для этого процесса
        endpoint = f'history/task?processInstanceId={process_id}'
        response = camunda_client._make_request('GET', endpoint)
        response.raise_for_status()
        history_tasks = response.json()
        
        with ui.dialog() as dialog:
            with ui.card().classes('p-6 w-full max-w-5xl'):
                ui.label('История процесса').classes('text-xl font-bold mb-4')
                
                # Основная информация о процессе
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Информация о процессе').classes('text-lg font-semibold mb-2')
                        ui.label(f'ID процесса: {process_id}').classes('text-sm')
                        ui.label(f'Ключ процесса: {history_process.get("processDefinitionKey", "Неизвестно")}').classes('text-sm')
                        ui.label(f'Начало: {history_process.get("startTime", "Неизвестно")}').classes('text-sm')
                        ui.label(f'Завершение: {history_process.get("endTime", "Не завершен")}').classes('text-sm')
                        ui.label(f'Длительность: {history_process.get("durationInMillis", 0) / 1000:.1f} сек').classes('text-sm')
                        
                        # Информация о создателе
                        creator = history_variables.get('processCreator', 'Неизвестно')
                        creator_name = history_variables.get('creatorName', creator)
                        ui.label(f'Создатель: {creator_name}').classes('text-sm')
                
                # Информация о документе
                document_name = history_variables.get('documentName', 'Неизвестно')
                if document_name != 'Неизвестно':
                    with ui.row().classes('mb-4'):
                        with ui.column().classes('flex-1'):
                            ui.label('Информация о документе').classes('text-lg font-semibold mb-2')
                            ui.label(f'Название: {document_name}').classes('text-sm')
                            
                            # Показываем содержимое документа (обрезанное)
                            document_content = history_variables.get('documentContent', '')
                            if document_content and len(document_content) > 200:
                                document_content = document_content[:200] + '...'
                            if document_content:
                                ui.label(f'Содержимое: {document_content}').classes('text-sm text-gray-600')
                
                # Статистика выполнения
                assignee_list = history_variables.get('assigneeList', [])
                if isinstance(assignee_list, str):
                    try:
                        import json
                        assignee_list = json.loads(assignee_list)
                    except:
                        assignee_list = []
                
                user_completed = history_variables.get('userCompleted', {})
                if isinstance(user_completed, str):
                    try:
                        user_completed = json.loads(user_completed)
                    except:
                        user_completed = {}
                
                completed_count = sum(1 for user in assignee_list if user_completed.get(user, False))
                total_count = len(assignee_list)
                
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Статистика выполнения').classes('text-lg font-semibold mb-2')
                        ui.label(f'Всего пользователей: {total_count}').classes('text-sm')
                        ui.label(f'Завершили: {completed_count}').classes('text-sm')
                        ui.label(f'Не завершили: {total_count - completed_count}').classes('text-sm')
                        
                        # Прогресс-бар
                        if total_count > 0:
                            progress_percent = (completed_count / total_count) * 100
                            with ui.row().classes('items-center mt-2'):
                                ui.label('Прогресс:').classes('text-sm mr-2')
                                ui.linear_progress(progress_percent / 100).classes('flex-1')
                                ui.label(f'{progress_percent:.1f}%').classes('text-sm ml-2')
                
                # Детальная информация по пользователям
                if history_tasks:
                    with ui.row().classes('mb-4'):
                        with ui.column().classes('flex-1'):
                            ui.label('Детали выполнения').classes('text-lg font-semibold mb-2')
                            
                            # Создаем таблицу с результатами
                            with ui.table(
                                columns=[
                                    {'name': 'user', 'label': 'Пользователь', 'field': 'user'},
                                    {'name': 'status', 'label': 'Статус', 'field': 'status'},
                                    {'name': 'start_time', 'label': 'Начало', 'field': 'start_time'},
                                    {'name': 'end_time', 'label': 'Завершение', 'field': 'end_time'},
                                    {'name': 'duration', 'label': 'Длительность', 'field': 'duration'},
                                    {'name': 'comment', 'label': 'Комментарий', 'field': 'comment'}
                                ],
                                rows=[]
                            ).classes('w-full') as table:
                                
                                # Заполняем таблицу данными
                                table_rows = []
                                for task in history_tasks:
                                    assignee = task.get('assignee', 'Не назначен')
                                    start_time = task.get('startTime', '')
                                    end_time = task.get('endTime', '')
                                    duration = task.get('duration', 0)
                                    
                                    # Определяем статус
                                    delete_reason = task.get('deleteReason', '')
                                    if delete_reason == 'completed':
                                        status = 'Завершено'
                                        status_color = 'text-green-600'
                                    elif delete_reason == 'cancelled':
                                        status = 'Отменено'
                                        status_color = 'text-red-600'
                                    else:
                                        status = 'Не завершено'
                                        status_color = 'text-orange-600'
                                    
                                    # Получаем комментарий пользователя
                                    comment = ''
                                    try:
                                        user_comments = history_variables.get('userComments', {})
                                        if isinstance(user_comments, str):
                                            user_comments = json.loads(user_comments)
                                        comment = user_comments.get(assignee, '')
                                    except:
                                        pass
                                    
                                    # Форматируем длительность
                                    duration_text = ''
                                    if duration:
                                        duration_seconds = duration / 1000
                                        if duration_seconds < 60:
                                            duration_text = f'{duration_seconds:.1f} сек'
                                        elif duration_seconds < 3600:
                                            duration_text = f'{duration_seconds/60:.1f} мин'
                                        else:
                                            duration_text = f'{duration_seconds/3600:.1f} ч'
                                    
                                    table_rows.append({
                                        'user': assignee,
                                        'status': status,
                                        'start_time': start_time[:19] if start_time else '',
                                        'end_time': end_time[:19] if end_time else '',
                                        'duration': duration_text,
                                        'comment': comment[:50] + '...' if len(comment) > 50 else comment
                                    })
                                
                                table.rows = table_rows
                
                # Переменные процесса (для отладки)
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Переменные процесса').classes('text-lg font-semibold mb-2')
                        
                        # Показываем только важные переменные
                        important_vars = ['taskName', 'taskDescription', 'processCreator', 'creatorName']
                        for var_name in important_vars:
                            if var_name in history_variables:
                                var_value = history_variables[var_name]
                                if isinstance(var_value, str) and len(var_value) > 100:
                                    var_value = var_value[:100] + '...'
                                
                                with ui.row().classes('p-2 border-b'):
                                    ui.label(f'{var_name}:').classes('text-sm font-medium w-32')
                                    ui.label(str(var_value)).classes('text-sm text-gray-600 flex-1')
                
                # Кнопки действий
                with ui.row().classes('mt-4'):
                    ui.button('Закрыть', on_click=dialog.close).classes('bg-gray-500 text-white')
                    ui.button('Экспорт', icon='download', on_click=lambda: export_process_history(process_id, history_process, history_variables, history_tasks)).classes('bg-blue-500 text-white')
        
        dialog.open()
        
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