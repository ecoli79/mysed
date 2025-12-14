from nicegui import ui
from services.camunda_connector import CamundaClient
from services.mayan_connector import MayanClient, MayanDocument
from config.settings import config
from datetime import datetime
from typing import Optional, List, Dict, Any
from app_logging.logger import get_logger

logger = get_logger(__name__)

# Глобальные переменные для управления состоянием
_tasks_container: Optional[ui.column] = None
_documents_container: Optional[ui.column] = None
_search_results_container: Optional[ui.column] = None
_uploaded_files_container: Optional[ui.column] = None
_progress_container: Optional[ui.column] = None  # Новый контейнер для прогресса
_uploaded_files: List[Dict[str, Any]] = []

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

def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return MayanClient.create_with_session_user()

def content() -> None:
    """Основная страница ознакомления с документами"""
    ui.label('Ознакомление с документами').classes('text-2xl font-bold mb-6')
    
    # Создаем табы
    with ui.tabs().classes('w-full') as tabs:
        review_tab = ui.tab('Мои задачи ознакомления')
        documents_tab = ui.tab('Документы из Mayan EDMS')
        start_review_tab = ui.tab('Запустить ознакомление')
        progress_tab = ui.tab('Прогресс процессов')  # Новый таб
    
    with ui.tab_panels(tabs, value=review_tab).classes('w-full mt-4'):
        # Таб с задачами ознакомления
        with ui.tab_panel(review_tab):
            create_review_tasks_section()
        
        # Таб с документами из Mayan EDMS
        with ui.tab_panel(documents_tab):
            create_documents_section()
        
        # Таб для запуска ознакомления
        with ui.tab_panel(start_review_tab):
            create_start_review_section()
        
        # Таб для отслеживания прогресса Multi-Instance процессов
        with ui.tab_panel(progress_tab):
            create_progress_tracking_section()

def create_review_tasks_section():
    """Создает секцию с задачами ознакомления"""
    global _tasks_container
    
    ui.label('Мои задачи ознакомления').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Кнопка обновления
        ui.button(
            'Обновить задачи',
            icon='refresh',
            on_click=load_review_tasks
        ).classes('mb-4 bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        # Контейнер для задач
        _tasks_container = ui.column().classes('w-full')
        
        # Загружаем задачи при открытии страницы
        load_review_tasks()

def load_review_tasks():
    """Загружает задачи ознакомления"""
    global _tasks_container
    
    if _tasks_container is None:
        return
        
    _tasks_container.clear()
    
    with _tasks_container:
        ui.label('Загрузка задач...').classes('text-gray-600')
        
        try:
            # Получаем задачи для процесса ознакомления с документами
            username = 'dvimpolitov'  # Это должно быть динамически
            camunda_client = get_camunda_client()
            tasks = camunda_client.get_user_tasks_by_process_key(
                username=username,
                process_definition_key='DocumentReviewProcess',
                active_only=True
            )
            
            if tasks:
                ui.label(f'Найдено {len(tasks)} задач ознакомления:').classes('text-lg font-semibold mb-4')
                
                for task in tasks:
                    create_task_card(task)
            else:
                ui.label('Нет активных задач ознакомления').classes('text-gray-500')
                
        except Exception as e:
            ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке задач ознакомления: {e}", exc_info=True)

def create_task_card(task):
    """Создает карточку задачи"""
    global _tasks_container
    
    if _tasks_container is None:
        return
        
    with _tasks_container:
        # Получаем дополнительную информацию о процессе
        camunda_client = get_camunda_client()
        process_vars = camunda_client.get_process_variables_by_names(
            task.process_instance_id,
            ['mayanDocumentId', 'documentDownloadUrl', 'documentFileInfo', 'taskName', 'taskDescription']
        )
        
        with ui.card().classes('mb-3 p-4 border-l-4 border-blue-500'):
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    ui.label(f'{task.name}').classes('text-lg font-semibold')
                    
                    # Используем переменные процесса для отображения информации
                    task_name = process_vars.get('taskName', task.name)
                    task_description = process_vars.get('taskDescription', task.description or '')
                    
                    ui.label(f'Задача: {task_name}').classes('text-sm text-gray-600')
                    if task_description:
                        ui.label(f'Описание: {task_description}').classes('text-sm text-gray-600')
                    ui.label(f'Создана: {task.start_time}').classes('text-sm text-gray-600')
                    
                    # Информация о файле из Mayan EDMS
                    file_info = process_vars.get('documentFileInfo', {})
                    if file_info:
                        ui.label(f'Файл: {file_info.get("filename", "Неизвестно")}').classes('text-sm text-gray-600')
                        ui.label(f'Тип: {file_info.get("mimetype", "Неизвестно")}').classes('text-sm text-gray-600')
                        ui.label(f'Размер: {file_info.get("size", 0)} байт').classes('text-sm text-gray-600')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        download_url = process_vars.get('documentDownloadUrl')
                        if download_url:
                            ui.button(
                                'Скачать документ',
                                icon='download',
                                on_click=lambda url=download_url: download_document(url)
                            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                        
                        ui.button(
                            'Завершить ознакомление',
                            icon='check',
                            on_click=lambda t=task: complete_review_task(t)
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                
                # Блок с ID удален полностью, так как больше не содержит содержимого
                # with ui.column().classes('items-end'):
                #     ui.label(f'ID задачи: {task.id}').classes('text-xs text-gray-500 font-mono')
                #     ui.label(f'ID процесса: {task.process_instance_id}').classes('text-xs text-gray-500 font-mono')

def create_documents_section():
    """Создает секцию с документами из Mayan EDMS"""
    global _documents_container
    
    ui.label('Документы из Mayan EDMS').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Поиск документов
        with ui.row().classes('w-full mb-4'):
            search_input = ui.input(
                'Поиск документов',
                placeholder='Введите название документа для поиска'
            ).classes('flex-1')
            
            ui.button(
                'Поиск',
                icon='search',
                on_click=lambda: search_documents(search_input.value)
            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        # Контейнер для документов
        _documents_container = ui.column().classes('w-full')
        
        # Загружаем документы при открытии страницы
        search_documents("")

def search_documents(query: str = ""):
    """Выполняет поиск документов"""
    global _documents_container
    
    if _documents_container is None:
        return
        
    _documents_container.clear()
    
    with _documents_container:
        ui.label('Поиск документов...').classes('text-gray-600')
        
        try:
            mayan_client = get_mayan_client()
            documents = mayan_client.search_documents(query, page_size=20)
            
            if documents:
                ui.label(f'Найдено {len(documents)} документов:').classes('text-lg font-semibold mb-4')
                
                for doc in documents:
                    create_document_card(doc)
            else:
                ui.label('Документы не найдены').classes('text-gray-500')
                
        except Exception as e:
            ui.label(f'Ошибка при поиске документов: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)

def create_document_card(doc: MayanDocument):
    """Создает карточку документа"""
    global _documents_container
    
    if _documents_container is None:
        return
        
    with _documents_container:
        with ui.card().classes('mb-3 p-4 border-l-4 border-green-500'):
            with ui.row().classes('items-start justify-between w-full'):
                with ui.column().classes('flex-1'):
                    ui.label(f'{doc.label}').classes('text-lg font-semibold')
                    if doc.description:
                        ui.label(f'Описание: {doc.description}').classes('text-sm text-gray-600')
                    ui.label(f'Файл: {doc.file_latest_filename}').classes('text-sm text-gray-600')
                    ui.label(f'Тип: {doc.file_latest_mimetype}').classes('text-sm text-gray-600')
                    ui.label(f'Размер: {doc.file_latest_size} байт').classes('text-sm text-gray-600')
                    ui.label(f'Создан: {doc.datetime_created}').classes('text-sm text-gray-600')
                    
                    # Кнопки действий
                    with ui.row().classes('gap-2 mt-2'):
                        ui.button(
                            'Просмотр',
                            icon='visibility',
                            on_click=lambda d=doc: view_document(d)
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                        
                        ui.button(
                            'Скачать',
                            icon='download',
                            on_click=lambda d=doc: download_document_from_mayan(d)
                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                
                with ui.column().classes('items-end'):
                    ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-500 font-mono')

def create_start_review_section():
    """Создает секцию для запуска ознакомления"""
    global _search_results_container
    
    ui.label('Запуск ознакомления с документом').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        with ui.column().classes('w-full'):
            ui.label('Выберите документ из Mayan EDMS для ознакомления').classes('text-sm font-medium mb-2')
            
            # Поиск документов для выбора
            with ui.row().classes('w-full mb-4'):
                doc_search_input = ui.input(
                    'Поиск документа',
                    placeholder='Введите название документа'
                ).classes('flex-1')
                
                search_btn = ui.button(
                    'Найти',
                    icon='search',
                ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                
                refresh_btn = ui.button(
                    'Показать последние',
                    icon='refresh',
                ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                
                reset_btn = ui.button(
                    'Сбросить',
                    icon='clear',
                ).classes('bg-red-500 text-white text-xs px-2 py-1 h-7')
            
            # Метка выбранного документа
            selected_doc_label = ui.label('Документ не выбран').classes('text-sm text-gray-500 mb-2')
            
            # Контейнер для результатов поиска
            _search_results_container = ui.column().classes('w-full mb-4')
            
            # Форма для запуска ознакомления
            with ui.card().classes('p-4 bg-gray-50'):
                ui.label('Настройки ознакомления').classes('text-lg font-semibold mb-4')
                
                # Хранилище выбранного документа
                selected_document = {'doc': None, 'document_id': None}
                
                # Поля для документа (скрытые, заполняются автоматически)
                document_id_input = ui.input(
                    'ID документа',
                    value=''
                ).classes('w-full mb-2').style('display: none')
                
                document_name_input = ui.input(
                    'Название документа',
                    value=''
                ).classes('w-full mb-2').style('display: none')
                
                # Список пользователей
                assignee_list = ui.input(
                    'Список пользователей (через запятую)',
                    placeholder='user1,user2,user3'
                ).classes('w-full mb-4')
                
                # Выбор ролей для доступа к документу
                ui.label('Назначение прав доступа к документу').classes('text-sm font-semibold mb-2')
                ui.label('Выберите роли, которым будет предоставлен доступ к документу для ознакомления').classes('text-xs text-gray-600 mb-2')
                
                roles_select = None
                try:
                    # Получаем доступные роли из Mayan EDMS
                    from services.mayan_connector import MayanClient
                    import asyncio
                    
                    async def load_roles():
                        try:
                            system_client = await MayanClient.create_default()
                            roles = await system_client.get_roles(page=1, page_size=1000)
                            
                            role_options = {}
                            for role in roles:
                                role_label = role.get('label')
                                if role_label:
                                    role_options[role_label] = role_label
                            
                            return role_options
                        except Exception as e:
                            logger.error(f'Ошибка при загрузке ролей: {e}', exc_info=True)
                            return {}
                    
                    # Загружаем роли синхронно
                    role_options = {}
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Если цикл уже запущен, используем create_task
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(asyncio.run, load_roles())
                                role_options = future.result()
                        else:
                            role_options = loop.run_until_complete(load_roles())
                    except:
                        # Fallback: пробуем через новый цикл
                        role_options = asyncio.run(load_roles())
                    
                    if role_options:
                        roles_select = ui.select(
                            options=role_options,
                            label='Выберите роли (можно выбрать несколько)',
                            multiple=True,
                            value=[],
                            with_input=True
                        ).classes('w-full mb-4')
                    else:
                        ui.label('Роли не найдены в системе').classes('text-sm text-orange-500 mb-2')
                        roles_select = None
                        
                except Exception as e:
                    logger.error(f'Ошибка при загрузке ролей: {e}', exc_info=True)
                    ui.label(f'Ошибка загрузки ролей: {str(e)}').classes('text-sm text-red-500 mb-2')
                    roles_select = None
                
                # Бизнес-ключ
                business_key = ui.input(
                    'Бизнес-ключ (опционально)',
                    placeholder='Оставьте пустым для автоматической генерации'
                ).classes('w-full mb-4')
                
                # Функция поиска и отображения документов
                async def search_and_display_documents_for_review(query: str = ''):
                    """Ищет и отображает документы из Mayan EDMS для выбора"""
                    try:
                        if not query and hasattr(doc_search_input, 'value'):
                            query = doc_search_input.value or ''
                        
                        _search_results_container.clear()
                        
                        with _search_results_container:
                            ui.label('Поиск документов...').classes('text-sm text-gray-600 text-center py-4')
                        
                        mayan_client = get_mayan_client()
                        query = query.strip() if query else ''
                        
                        if query:
                            documents = mayan_client.search_documents(query, page_size=20)
                        else:
                            documents = mayan_client.get_documents(page=1, page_size=20)
                        
                        _search_results_container.clear()
                        
                        if not documents:
                            with _search_results_container:
                                ui.label('Документы не найдены').classes('text-sm text-gray-500 text-center py-4')
                            return
                        
                        with _search_results_container:
                            ui.label(f'Найдено документов: {len(documents)}').classes('text-sm font-semibold mb-2')
                            
                            for doc in documents:
                                with ui.card().classes('mb-2 p-3 cursor-pointer hover:bg-blue-50 border-l-4 border-blue-200 transition-colors'):
                                    with ui.row().classes('items-center w-full'):
                                        ui.icon('description').classes('text-blue-500 mr-2 text-xl')
                                        
                                        with ui.column().classes('flex-1'):
                                            ui.label(doc.label).classes('text-sm font-semibold')
                                            if hasattr(doc, 'file_latest_filename') and doc.file_latest_filename:
                                                ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                                            if hasattr(doc, 'file_latest_size') and doc.file_latest_size:
                                                size_kb = doc.file_latest_size / 1024
                                                size_mb = size_kb / 1024
                                                if size_mb >= 1:
                                                    ui.label(f'Размер: {size_mb:.1f} МБ').classes('text-xs text-gray-600')
                                                else:
                                                    ui.label(f'Размер: {size_kb:.1f} КБ').classes('text-xs text-gray-600')
                                        
                                        ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-500 font-mono mr-2')
                                        
                                        ui.button(
                                            'Выбрать',
                                            icon='check',
                                            on_click=lambda d=doc: select_document_for_review(d)
                                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                        
                    except Exception as e:
                        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
                        _search_results_container.clear()
                        with _search_results_container:
                            ui.label(f'Ошибка при поиске: {str(e)}').classes('text-sm text-red-600 text-center py-4')
                
                def select_document_for_review(doc):
                    """Выбирает документ и автоматически заполняет поля формы"""
                    try:
                        selected_document['doc'] = doc
                        selected_document['document_id'] = doc.document_id
                        
                        document_id_input.value = str(doc.document_id)
                        document_name_input.value = doc.label
                        
                        selected_doc_label.text = f'✓ Выбран: {doc.label} (ID: {doc.document_id})'
                        selected_doc_label.classes('text-sm text-green-600 font-semibold mb-2')
                        
                        ui.notify(f'Выбран документ: {doc.label} (ID: {doc.document_id})', type='positive')
                        
                        _search_results_container.clear()
                        with _search_results_container:
                            with ui.card().classes('p-3 bg-green-50 border-l-4 border-green-500'):
                                with ui.row().classes('items-center'):
                                    ui.icon('check_circle').classes('text-green-500 mr-2 text-xl')
                                    with ui.column().classes('flex-1'):
                                        ui.label(f'Выбран документ: {doc.label}').classes('text-sm font-semibold')
                                        ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-600')
                                        if hasattr(doc, 'file_latest_filename') and doc.file_latest_filename:
                                            ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                                
                                ui.button(
                                    'Выбрать другой документ',
                                    icon='refresh',
                                    on_click=lambda: search_and_display_documents_for_review(doc_search_input.value)
                                ).classes('mt-2 bg-blue-500 text-white text-xs px-2 py-1 h-7')
                    
                    except Exception as e:
                        logger.error(f"Ошибка при выборе документа: {e}", exc_info=True)
                        ui.notify(f'Ошибка при выборе документа: {str(e)}', type='negative')
                
                def reset_search():
                    """Сбрасывает поиск и очищает все поля"""
                    try:
                        doc_search_input.value = ''
                        _search_results_container.clear()
                        selected_document['doc'] = None
                        selected_document['document_id'] = None
                        selected_doc_label.text = 'Документ не выбран'
                        selected_doc_label.classes('text-sm text-gray-500 mb-2')
                        document_id_input.value = ''
                        document_name_input.value = ''
                        ui.notify('Поиск сброшен', type='info')
                    except Exception as e:
                        logger.error(f"Ошибка при сбросе поиска: {e}", exc_info=True)
                        ui.notify(f'Ошибка при сбросе: {str(e)}', type='negative')
                
                # Обработчики кнопок
                search_btn.on_click(lambda: search_and_display_documents_for_review(doc_search_input.value))
                refresh_btn.on_click(lambda: search_and_display_documents_for_review(''))
                reset_btn.on_click(lambda: reset_search())
                
                # Обработчик Enter для поля поиска
                doc_search_input.on('keydown.enter', lambda: search_and_display_documents_for_review(doc_search_input.value))
                
                # Кнопка запуска
                ui.button(
                    'Запустить ознакомление',
                    icon='play_arrow',
                    on_click=lambda: start_document_review(
                        selected_document,
                        assignee_list.value,
                        business_key.value,
                        roles_select.value if roles_select else []
                    )
                ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')

def search_documents_for_review(query: str):
    """Поиск документов для выбора"""
    global _search_results_container
    
    if _search_results_container is None:
        return
        
    _search_results_container.clear()
    
    with _search_results_container:
        ui.label('Поиск документов...').classes('text-gray-600')
        
        try:
            mayan_client = get_mayan_client()
            documents = mayan_client.search_documents(query, page_size=10)
            
            if documents:
                ui.label(f'Найдено {len(documents)} документов:').classes('text-sm font-medium mb-2')
                
                for doc in documents:
                    create_document_selection_card(doc)
            else:
                ui.label('Документы не найдены').classes('text-gray-500')
                
        except Exception as e:
            ui.label(f'Ошибка при поиске: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)

def create_document_selection_card(doc: MayanDocument):
    """Создает карточку для выбора документа"""
    global _search_results_container
    
    if _search_results_container is None:
        return
        
    with _search_results_container:
        with ui.card().classes('mb-2 p-3 cursor-pointer hover:bg-blue-50'):
            with ui.row().classes('items-center w-full'):
                ui.radio(
                    'selected_doc',
                    value=doc,
                    on_change=lambda e: select_document(e.value)
                ).classes('mr-3')
                
                with ui.column().classes('flex-1'):
                    ui.label(f'{doc.label}').classes('text-sm font-semibold')
                    ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                    ui.label(f'Размер: {doc.file_latest_size} байт').classes('text-xs text-gray-600')
                
                ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-500 font-mono')

def select_document(doc):
    """Выбирает документ"""
    ui.notify(f'Выбран документ: {doc.label}', type='info')

def start_document_review(selected_document: Dict, assignee_list: str, business_key: str, role_names: List[str] = None):
    """Запускает процесс ознакомления с использованием Multi-Instance"""
    if not selected_document.get('doc') or not selected_document.get('document_id'):
        ui.notify('Выберите документ', type='error')
        return
    
    if not assignee_list:
        ui.notify('Введите список пользователей', type='error')
        return
    
    try:
        # Получаем текущего пользователя для передачи creator_username
        from auth.middleware import get_current_user
        current_user = get_current_user()
        creator_username = current_user.username if current_user else None
        
        # Получаем информацию о документе
        mayan_client = get_mayan_client()
        document_id = selected_document['document_id']
        document_info = mayan_client.get_document_info_for_review(document_id)
        if not document_info:
            ui.notify('Ошибка при получении информации о документе', type='error')
            return
        
        # Парсим список пользователей
        users = [user.strip() for user in assignee_list.split(',') if user.strip()]
        
        # Запускаем Multi-Instance процесс для всех пользователей
        camunda_client = get_camunda_client()
        process_id = camunda_client.start_document_review_process_multi_instance(
            document_id=document_id,
            document_name=document_info["label"],
            document_content=document_info.get("content", "Содержимое недоступно"),
            assignee_list=users,
            business_key=business_key if business_key else None,
            creator_username=creator_username,
            role_names=role_names if role_names else []
        )
        
        if process_id:
            ui.notify(f'Запущен Multi-Instance процесс ознакомления для {len(users)} пользователей!', type='success')
            
            # Показываем информацию о процессе
            with ui.card().classes('p-3 bg-green-50 mt-2'):
                ui.label(f'Документ: {selected_document["doc"].label}').classes('text-sm font-semibold')
                ui.label(f'Пользователи: {", ".join(users)}').classes('text-sm')
                if role_names:
                    ui.label(f'Роли с доступом: {", ".join(role_names)}').classes('text-sm')
                ui.label(f'ID процесса: {process_id}').classes('text-sm font-mono')
                ui.label('Тип: Multi-Instance (один процесс, несколько параллельных задач)').classes('text-xs text-gray-600')
        else:
            ui.notify('Ошибка при запуске процесса', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f"Ошибка при запуске процесса ознакомления: {e}", exc_info=True)

def download_document(url: str):
    """Скачивает документ по URL"""
    ui.open(url, new_tab=True)

def download_document_from_mayan(doc: MayanDocument):
    """Скачивает документ из Mayan EDMS"""
    mayan_client = get_mayan_client()
    download_url = mayan_client.get_document_file_url(doc.document_id)
    if download_url:
        ui.open(download_url, new_tab=True)
    else:
        ui.notify('Не удалось получить ссылку для скачивания', type='error')

def view_document(doc: MayanDocument):
    """Просматривает документ"""
    mayan_client = get_mayan_client()
    preview_url = mayan_client.get_document_preview_url(doc.document_id)
    if preview_url:
        ui.open(preview_url, new_tab=True)
    else:
        ui.notify('Предварительный просмотр недоступен', type='error')

def complete_review_task(task):
    """Завершает задачу ознакомления"""
    # Создаем модальное окно для завершения задачи
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label('Завершение ознакомления с документом').classes('text-xl font-semibold mb-4')
        
        # Информация о задаче
        with ui.card().classes('p-4 bg-gray-50 mb-4'):
            ui.label(f'Задача: {task.name}').classes('text-lg font-semibold')
            # ui.label(f'ID задачи: {task.id}').classes('text-sm text-gray-600')  # УБРАНО
            # ui.label(f'ID процесса: {task.process_instance_id}').classes('text-sm text-gray-600')  # УБРАНО
        
        # Форма завершения
        with ui.column().classes('w-full'):
            # Статус завершения
            status_select = ui.select(
                options={
                    'completed': 'Ознакомлен',
                    'rejected': 'Отклонено',
                    'cancelled': 'Отменено'
                },
                value='completed',
                label='Статус ознакомления'
            ).classes('w-full mb-4')
            
            # Комментарий
            comment_textarea = ui.textarea(
                label='Комментарий',
                placeholder='Введите комментарий к ознакомлению...'
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
                ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                
                ui.button(
                    'Завершить ознакомление',
                    icon='check',
                    on_click=lambda: submit_task_completion(task, status_select.value, comment_textarea.value, dialog)
                ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
    
    dialog.open()

def handle_file_upload(e):
    """Обрабатывает загрузку файлов"""
    global _uploaded_files_container, _uploaded_files
    
    if _uploaded_files_container is None:
        return
        
    for file in e.files:
        file_info = {
            'filename': file.name,
            'mimetype': file.type,
            'content': file.content,
            'size': len(file.content),
            'description': f'Файл результата для задачи'
        }
        _uploaded_files.append(file_info)
        
        with _uploaded_files_container:
            with ui.card().classes('p-2 mb-2 bg-green-50'):
                ui.label(f'{file.name} ({file.type})').classes('text-sm')
                ui.label(f'Размер: {len(file.content)} байт').classes('text-xs text-gray-600')

def submit_task_completion(task, status, comment, dialog):
    """Отправляет завершение задачи"""
    global _uploaded_files
    
    try:
        # Подготавливаем переменные для процесса
        variables = {
            'reviewed': status == 'completed',
            'reviewDate': datetime.now().isoformat(),
            'reviewComment': comment or '',
            'taskStatus': status
        }
        
        # Загружаем файлы в Mayan EDMS, если они есть
        result_files = []
        if _uploaded_files:
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
        
        # Завершаем задачу в Camunda
        camunda_client = get_camunda_client()
        success = camunda_client.complete_task_with_user_data(
            task_id=task.id,
            status=status,
            comment=comment,
            review_date=datetime.now().isoformat()
        )
        
        if success:
            ui.notify('Задача успешно завершена!', type='success')
            dialog.close()
            # Обновляем список задач
            load_review_tasks()
        else:
            ui.notify('Ошибка при завершении задачи', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка: {str(e)}', type='error')
        logger.error(f"Ошибка при завершении задачи {task.id}: {e}", exc_info=True)

def create_progress_tracking_section():
    """Создает секцию отслеживания прогресса Multi-Instance процессов"""
    global _progress_container
    
    ui.label('Отслеживание прогресса процессов согласования').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        # Кнопка обновления
        ui.button(
            'Обновить процессы',
            icon='refresh',
            on_click=load_multi_instance_processes
        ).classes('mb-4 bg-green-500 text-white text-xs px-2 py-1 h-7')
        
        # Контейнер для процессов
        _progress_container = ui.column().classes('w-full')
        
        # Загружаем процессы при открытии таба
        load_multi_instance_processes()

def load_multi_instance_processes():
    """Загружает и отображает Multi-Instance процессы"""
    global _progress_container
    
    if _progress_container is None:
        return
        
    _progress_container.clear()
    
    with _progress_container:
        ui.label('Загрузка процессов...').classes('text-gray-600')
        
        try:
            camunda_client = get_camunda_client()
            
            # Получаем все активные процессы DocumentReviewProcessMultiInstance
            processes = camunda_client.get_process_instances_by_definition_key('DocumentReviewProcessMultiInstance', active_only=True)
            
            if not processes:
                ui.label('Нет активных процессов согласования').classes('text-gray-500')
                return
            
            ui.label(f'Найдено {len(processes)} активных процессов:').classes('text-lg font-semibold mb-4')
            
            for process in processes:
                create_process_progress_card(process)
                
        except Exception as e:
            ui.label(f'Ошибка при загрузке процессов: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке Multi-Instance процессов: {e}", exc_info=True)

def create_process_progress_card(process):
    """Создает карточку процесса с информацией о прогрессе"""
    global _progress_container
    
    if _progress_container is None:
        return
        
    try:
        camunda_client = get_camunda_client()
        
        # Получаем прогресс процесса
        progress_info = camunda_client.get_multi_instance_task_progress(process.id)
        
        with _progress_container:
            with ui.card().classes('p-4 mb-4 w-full border-l-4 border-green-500'):
                with ui.row().classes('w-full items-center'):
                    with ui.column().classes('flex-1'):
                        ui.label(f'Процесс: {process.business_key or process.id}').classes('text-lg font-semibold')
                        ui.label(f'ID: {process.id}').classes('text-sm text-gray-600 font-mono')
                        ui.label(f'Запущен: {process.start_time}').classes('text-sm text-gray-600')
                        
                        # Прогресс-бар
                        progress_percent = progress_info['progress_percent']
                        ui.label(f'Прогресс: {progress_info["nr_of_completed_instances"]}/{progress_info["nr_of_instances"]} ({progress_percent:.1f}%)').classes('text-sm font-medium')
                        
                        with ui.linear_progress().classes('w-full h-2 mt-1'):
                            ui.linear_progress().value = progress_percent / 100
                    
                    with ui.column().classes('items-end'):
                        # Статус процесса
                        if progress_info['is_complete']:
                            ui.label('✅ Завершен').classes('text-green-600 font-semibold')
                        else:
                            ui.label('🔄 В процессе').classes('text-blue-600 font-semibold')
                        
                        # Кнопка деталей
                        ui.button('Детали', icon='info', on_click=lambda p=process: show_process_details(p)).classes('text-xs px-2 py-1 h-7')
                
                # Детальная информация о пользователях
                with ui.expansion('Статус пользователей', icon='people').classes('mt-2'):
                    for user_status in progress_info['user_status']:
                        status_icon = '✅' if user_status['completed'] else '⏳'
                        status_color = 'text-green-600' if user_status['completed'] else 'text-blue-600'
                        
                        with ui.row().classes('items-center p-2'):
                            ui.label(f'{status_icon} {user_status["user"]}').classes(f'text-sm {status_color}')
                            ui.label(f'({user_status["status"]})').classes('text-xs text-gray-500 ml-2')
                            
    except Exception as e:
        logger.error(f"Ошибка при создании карточки процесса {process.id}: {e}")
        with _progress_container:
            with ui.card().classes('p-4 mb-4 w-full bg-red-50'):
                ui.label(f'Ошибка при загрузке процесса {process.id}').classes('text-red-600')
                ui.label(f'Детали: {str(e)}').classes('text-xs text-red-500')

def show_process_details(process):
    """Показывает детальную информацию о процессе"""
    try:
        camunda_client = get_camunda_client()
        
        # Получаем детальную информацию
        progress_info = camunda_client.get_multi_instance_task_progress(process.id)
        process_variables = camunda_client.get_process_instance_variables(process.id)
        
        with ui.dialog() as dialog:
            with ui.card().classes('p-6 w-full max-w-4xl'):
                ui.label('Детали процесса согласования').classes('text-xl font-bold mb-4')
                
                # Основная информация
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Основная информация').classes('text-lg font-semibold mb-2')
                        ui.label(f'ID процесса: {process.id}').classes('text-sm')
                        ui.label(f'Бизнес-ключ: {process.business_key or "Не указан"}').classes('text-sm')
                        ui.label(f'Запущен: {process.start_time}').classes('text-sm')
                        ui.label(f'Статус: {"Завершен" if progress_info["is_complete"] else "В процессе"}').classes('text-sm')
                
                # Прогресс
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Прогресс выполнения').classes('text-lg font-semibold mb-2')
                        ui.label(f'Завершено: {progress_info["nr_of_completed_instances"]}/{progress_info["nr_of_instances"]} задач').classes('text-sm')
                        
                        with ui.linear_progress().classes('w-full h-3 mt-2'):
                            ui.linear_progress().value = progress_info['progress_percent'] / 100
                        
                        ui.label(f'{progress_info["progress_percent"]:.1f}%').classes('text-sm text-center')
                
                # Детали пользователей
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Детали пользователей').classes('text-lg font-semibold mb-2')
                        
                        for user_status in progress_info['user_status']:
                            status_icon = '✅' if user_status['completed'] else '⏳'
                            status_color = 'text-green-600' if user_status['completed'] else 'text-blue-600'
                            
                            with ui.row().classes('items-center p-2 border-b'):
                                ui.label(f'{status_icon} {user_status["user"]}').classes(f'text-sm {status_color} flex-1')
                                ui.label(f'({user_status["status"]})').classes('text-xs text-gray-500')
                
                # Переменные процесса
                with ui.row().classes('mb-4'):
                    with ui.column().classes('flex-1'):
                        ui.label('Переменные процесса').classes('text-lg font-semibold mb-2')
                        
                        # Показываем только важные переменные
                        important_vars = ['taskName', 'taskDescription', 'documentName', 'documentContent']
                        for var_name in important_vars:
                            if var_name in process_variables:
                                var_value = process_variables[var_name]
                                if isinstance(var_value, str) and len(var_value) > 100:
                                    var_value = var_value[:100] + '...'
                                
                                with ui.row().classes('p-2 border-b'):
                                    ui.label(f'{var_name}:').classes('text-sm font-medium w-32')
                                    ui.label(str(var_value)).classes('text-sm text-gray-600 flex-1')
                
                # Кнопки действий
                with ui.row().classes('mt-4'):
                    ui.button('Закрыть', on_click=dialog.close).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                    
                    if not progress_info['is_complete']:
                        ui.button('Обновить', icon='refresh', on_click=lambda: [
                            dialog.close(),
                            load_multi_instance_processes()
                        ]).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        dialog.open()
        
    except Exception as e:
        ui.notify(f'Ошибка при показе деталей процесса: {str(e)}', type='error')
        logger.error(f"Ошибка при показе деталей процесса {process.id}: {e}", exc_info=True)