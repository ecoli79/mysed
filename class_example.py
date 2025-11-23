import theme
from message import message
from nicegui import ui, events
from ldap_users import get_users, get_groups, users_filter
from services.camunda_connector import CamundaClient
from auth.middleware import get_current_user
from services.document_access_manager import document_access_manager
from services.mayan_connector import MayanClient
from config.settings import config
from datetime import datetime, timezone
import time
import logging

logger = logging.getLogger(__name__)

class ClassExample:

    def __init__(self) -> None:
        """The page is created as soon as the class is instantiated.

        This can obviously also be done in a method, if you want to decouple the instantiation of the object from the page creation.
        """
        @ui.page('/task-assignment')
        async def page_task_assignment():
            with theme.frame('Назначение задач пользователям'):
                #message('Выбор пользователей и назначение им задач')
                # Список для хранения выбранных пользователей
                selected_users = []
                all_users = await get_users()
                
                # Инициализация Camunda клиента с использованием конфигурации
                try:
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
                        verify_ssl=False
                    )
                    print("Camunda клиент успешно инициализирован")
                except Exception as e:
                    print(f"Ошибка при инициализации Camunda клиента: {e}")
                    ui.notify(f'Ошибка подключения к Camunda: {str(e)}', type='negative')
                    camunda_client = None
               
                async def on_row_dblclick(event):
                    row_data = event.args.get('data') if isinstance(event.args, dict) else None
                    if row_data:
                        add_user_to_selection(row_data)
                    else:
                        ui.notify("Could not get row data")
                
                # Создаем текстовое поле для фильтрации
                with ui.row().classes('w-full mb-4'):
                    ui.label('Поиск пользователей:').classes('text-lg font-bold mb-2')
                    search_input = ui.input(
                        placeholder='Введите логин, имя, фамилию или email...',
                        on_change=lambda e: filter_users(e.value, all_users, all_users_grid)
                    ).classes('w-80 h-50')
                    
                    # Кнопка для очистки фильтра
                    ui.button('Очистить', on_click=lambda: clear_filter(all_users, all_users_grid, search_input)).classes('ml-2')
                
                # Контейнер с двумя таблицами рядом
                with ui.row().classes('w-full gap-4'):
                    # Левая колонка - таблица всех пользователей
                    with ui.column().classes('flex-1'):
                        ui.label('Все пользователи:').classes('text-lg font-bold mb-2')
                        
                        all_users_grid = ui.aggrid({
                            'columnDefs': [
                                {'headerName': 'Логин', 'field': 'login'},
                                {'headerName': 'Имя', 'field': 'first_name'},
                                {'headerName': 'Фамилия', 'field': 'last_name'},
                                {'headerName': 'Email', 'field': 'email'},
                            ],
                            'rowData': [ user.__dict__ for user in all_users],
                            'rowSelection': 'multiple',
                            # Простая HTML заглушка
                            'overlayNoRowsTemplate': '''
                                <div style="padding: 40px; text-align: center; color: #666; font-size: 16px;">
                                    <i class="material-icons" style="font-size: 48px; color: #ccc; margin-bottom: 10px;">people</i>
                                    <br/>
                                    <strong>Нет пользователей для отображения</strong>
                                    <br/>
                                    <span style="font-size: 14px; color: #999;">Попробуйте изменить фильтр поиска</span>
                                </div>
                            ''',
                            'suppressNoRowsOverlay': False,  # Показывать заглушку когда нет данных
                        }).classes('w-full').on('cellDoubleClicked', on_row_dblclick)
                       
                        user_count_label = ui.label(f'Найдено пользователей: {len(all_users)}').classes('text-sm text-gray-600 mt-2')
                    
                    # Правая колонка - таблица выбранных пользователей
                    with ui.column().classes('flex-1'):
                        ui.label('Выбранные пользователи:').classes('text-lg font-bold mb-2')
                        
                        # Таблица выбранных пользователей
                        selected_users_grid = ui.aggrid({
                            'columnDefs': [
                                {'headerName': 'Логин', 'field': 'login'},
                                {'headerName': 'Имя', 'field': 'first_name'},
                                {'headerName': 'Фамилия', 'field': 'last_name'},
                                {'headerName': 'Email', 'field': 'email'},
                            ],
                            'rowData': [],
                            'rowSelection': 'multiple',
                              # Простая HTML заглушка
                            'overlayNoRowsTemplate': '''
                                <div style="padding: 40px; text-align: center; color: #666; font-size: 16px;">
                                    <i class="material-icons" style="font-size: 48px; color: #ccc; margin-bottom: 10px;">people</i>
                                    <br/>
                                    <strong>Не выбраны пользователи</strong>
                                    <br/>
                                    <span style="font-size: 14px; color: #999;">Выберите пользователей из верхнего списка чтобы назначить им задачу</span>
                                </div>
                            ''',
                        }).classes('w-full')
                        
                        # Счетчик выбранных пользователей
                        selected_count_label = ui.label('Выбрано пользователей: 0').classes('text-sm text-gray-600 mt-2')
                                        
                # Кнопки для работы с выбранными пользователями
                with ui.row().classes('w-full mt-2'):
                    ui.space()
                    ui.button('Очистить выбор', on_click=lambda: clear_selection()).classes('mr-2')
                    ui.button('Удалить выбранного', on_click=lambda: show_selected_rows_selected_users()).classes('mr-2')
                
                # # Контейнер для выбора типа процесса
                # with ui.column().classes('w-full mt-4'):
                #     process_type_container = ui.column().classes('w-full mt-4')
                #     process_type_container.visible = False
                    
                #     with process_type_container:
                #         ui.label('Выберите тип процесса:').classes('text-lg font-bold mb-2')
                        
                #         # Радио-кнопки для выбора типа процесса
                #         process_type_radio = ui.radio(
                #             ['Обычный процесс (отдельный для каждого пользователя)', 'Multi-Instance процесс (один процесс для всех)'],
                #             value='Multi-Instance процесс (один процесс для всех)'
                #         ).classes('w-full mb-4')
                        
                        # Контейнер для выбора шаблона процесса
                    process_template_container = ui.column().classes('w-full mt-4')
                    
                    with process_template_container:
                        ui.label('Выберите шаблон процесса:').classes('text-lg font-bold mb-2')
                        
                        with ui.row().classes('w-full items-end'):
                            process_template_select = ui.select(
                                options={},
                                label='Шаблон процесса',
                                with_input=True,
                                clearable=True
                            ).classes('w-80').props('id="process_template_select"')
                            
                        # Кнопка для открытия формы запуска процесса
                        ui.button(
                            'Запустить процесс для выбранных пользователей',
                            on_click=lambda: open_process_form(),
                            icon='play_arrow'
                        ).classes('mt-2')
                    
                
                # Функция для добавления пользователя в выбор
                def add_user_to_selection(user_data):
                    # Проверяем, не выбран ли уже этот пользователь
                    if not any(user['login'] == user_data['login'] for user in selected_users):
                        selected_users.append(user_data)
                        update_selected_users_table()
                        update_selected_count()
                        # Показываем уведомление
                        ui.notify(f'Пользователь {user_data["login"]} добавлен в выбор', type='positive')
                    else:
                        ui.notify(f'Пользователь {user_data["login"]} уже выбран', type='warning')
                
                async def show_selected_rows_selected_users():
                    selected = await selected_users_grid.get_selected_rows()
                    if selected:
                        for row in selected:
                            ui.notify(f'Удаляем пользователя: {row["login"]}')
                            remove_user_from_selection(row['login'])
                    else:
                            ui.notify('Нет выбранных строк', type='warning')
                
                # Функция для удаления пользователя из выбора
                def remove_user_from_selection(login):
                    selected_users[:] = [user for user in selected_users if user['login'] != login]
                    update_selected_users_table()
                    update_selected_count()
                    
                    ui.notify(f'Пользователь {login} удален из выбора', type='info')
                
                # Функция для обновления таблицы выбранных пользователей
                def update_selected_users_table():
                    print(f"Обновление таблицы. Выбранных пользователей: {len(selected_users)}")
                    selected_users_grid.options['rowData'] = selected_users
                    selected_users_grid.update()
                
                # Функция для обновления счетчика выбранных пользователей
                def update_selected_count():
                    selected_count_label.text = f'Выбрано пользователей: {len(selected_users)}'
                    # Показываем/скрываем контейнер выбора типа процесса
                    # process_type_container.visible = len(selected_users) > 0
                
                # Функция для очистки выбора
                def clear_selection():
                    selected_users.clear()
                    update_selected_users_table()
                    update_selected_count()
                    ui.notify('Выбор очищен', type='info')

                async def filter_users(query: str, users: list, grid_component, count_label=user_count_label):
                    if query:
                        filtered_users = await users_filter(users, query)
                        grid_component.options['rowData'] = filtered_users
                        grid_component.update()
                        count_label.text = f'Найдено пользователей: {len(filtered_users)}'
                    else:
                        # Если поиск пустой, показываем всех пользователей
                        grid_component.options['rowData'] = [user.__dict__ for user in users]
                        grid_component.update()
                        count_label.text = f'Найдено пользователей: {len(users)}'
                
                def clear_filter(users: list, grid_component, search_input_component, count_label=user_count_label):
                    search_input_component.value = ''
                    grid_component.options['rowData'] = [user.__dict__ for user in users]
                    grid_component.update()
                    count_label.text = f'Найдено пользователей: {len(users)}'
                
                # Функция для загрузки активных шаблонов процессов
                async def load_process_templates():
                    if not camunda_client:
                        ui.notify('Camunda клиент не инициализирован', type='negative')
                        return
                        
                    print("Начинаем загрузку шаблонов процессов...")
                    try:
                        process_definitions = await camunda_client.get_active_process_definitions()
                        print(f"Получено определений процессов: {len(process_definitions)}")
                        
                        # Создаем словарь для select: {key: name}
                        template_options = {}
                        for process_def in process_definitions:
                            if process_def.startable_in_tasklist:
                                template_options[process_def.key] = f"{process_def.name} (v{process_def.version})"
                        
                        process_template_select.options = template_options
                        print(f"Устанавливаем опции: {template_options}")
                        process_template_select.update()
                        print("Вызван update() для process_template_select")
                        
                    except Exception as e:
                        ui.notify(f'Ошибка при загрузке шаблонов процессов: {str(e)}', type='negative')
                        logger.error(f"Ошибка при загрузке шаблонов процессов: {e}", exc_info=True)
                                                       
                # Функция для открытия формы запуска процесса
                async def open_process_form():
                    if not selected_users:
                        ui.notify('Не выбраны пользователи', type='warning')
                        return
                    
                    if not process_template_select.value:
                        ui.notify('Не выбран шаблон процесса', type='warning')
                        return
                    
                    # Создаем модальное окно с формой
                    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
                        ui.label('Настройка запуска процесса').classes('text-h6 font-bold mb-4')
                        
                        # Информация о процессе
                        with ui.row().classes('w-full mb-4'):
                            ui.label('Процесс:').classes('font-bold')
                            ui.label(process_template_select.value).classes('ml-2')
                        
                        # # Информация о типе процесса
                        # with ui.row().classes('w-full mb-4'):
                        #     ui.label('Тип процесса:').classes('font-bold')
                        #     ui.label(process_type_radio.value).classes('ml-2')
                        
                        # Информация о пользователях
                        with ui.column().classes('w-full mb-4'):
                            ui.label('Пользователи:').classes('font-bold mb-2')
                            ui.label(f'Выбрано пользователей: {len(selected_users)}').classes('text-sm text-gray-600 mb-2')
                            
                            # Список выбранных пользователей
                            with ui.column().classes('w-full max-h-32 overflow-y-auto border rounded p-2'):
                                for user in selected_users:
                                    ui.label(f"• {user['login']} - {user['first_name']} {user['last_name']}").classes('text-sm')
                        
                        # Переменные процесса
                        ui.label('Переменные процесса:').classes('text-lg font-bold mb-2')
                        
                        # Инициализируем переменные для процессов с документами ДО использования в лямбде
                        # Это нужно, чтобы лямбда на кнопке "Запустить процесс" могла безопасно обращаться к этим переменным
                        document_id_input = None
                        document_name_input = None
                        roles_select = None  # Инициализируем как None, будет переопределено в блоке if для DocumentSigningProcess
                        
                        # Основные переменные
                        with ui.column().classes('w-full mb-4'):
                            ui.label('Основные параметры:').classes('font-bold mb-2')
                            
                            # Название задачи
                            task_name_input = ui.input(
                                label='Название задачи',
                                placeholder='Введите название задачи',
                                value='Новая задача'
                            ).classes('w-full mb-2')
                            
                            # Описание задачи
                            task_description_input = ui.textarea(
                                label='Описание задачи',
                                placeholder='Введите описание задачи',
                                value=''
                            ).classes('w-full mb-2')
                            
                            # Приоритет
                            priority_select = ui.select(
                                options={'1': 'Низкий', '2': 'Средний', '3': 'Высокий', '4': 'Критический'},
                                label='Приоритет',
                                value='2'
                            ).classes('w-full mb-2')
                            
                            # Срок выполнения
                            due_date_input = ui.input(
                                label='Срок выполнения',
                                placeholder='YYYY-MM-DD',
                                value=''
                            ).classes('w-full mb-2').props('type="date"')

                            if process_template_select.value and 'DocumentSigningProcess' in process_template_select.value:
                                # Поля для подписания документов
                                # Теперь document_id_input, document_name_input, roles_select уже инициализированы как None
                                # и будут переопределены в этом блоке реальными виджетами
                                ui.label('Параметры подписания:').classes('font-bold mb-2')
                                
                                # Секция выбора документа из Mayan EDMS
                                selected_doc_label = ui.label('Документ не выбран').classes('text-sm text-gray-500 mb-2')
                                
                                with ui.column().classes('w-full mb-4 p-3 bg-blue-50 rounded border'):
                                    ui.label('Выбор документа из Mayan EDMS:').classes('font-semibold mb-2')
                                    
                                    # Поиск документа
                                    document_search_input = ui.input(
                                        label='Поиск документа',
                                        placeholder='Введите название документа для поиска...',
                                        value=''
                                    ).classes('w-full mb-2')
                                    
                                    # Добавляем обработчик Enter для поиска
                                    def on_search_enter(e):
                                        if e.args and e.args.get('key') == 'Enter':
                                            search_and_display_documents_for_task(document_search_input.value)
                                    
                                    # Кнопки поиска
                                    with ui.row().classes('w-full mb-2 gap-2'):
                                        search_btn = ui.button(
                                            'Поиск документов',
                                            icon='search',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-blue-500 text-white')
                                        
                                        refresh_btn = ui.button(
                                            'Показать последние',
                                            icon='refresh',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-gray-500 text-white')
                                        
                                        reset_btn = ui.button(
                                            'Сбросить поиск',
                                            icon='clear',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-orange-500 text-white')
                                    
                                    # Контейнер для результатов поиска
                                    document_results_container = ui.column().classes('w-full max-h-64 overflow-y-auto border rounded p-2 bg-white')
                                
                                # Объявляем поля для document_id и document_name до функций
                                document_id_input = ui.input(
                                    label='ID документа в Mayan EDMS',
                                    placeholder='Заполнится автоматически при выборе документа',
                                    value=''
                                ).classes('w-full mb-2')
                                
                                document_name_input = ui.input(
                                    label='Название документа',
                                    placeholder='Заполнится автоматически при выборе документа',
                                    value=''
                                ).classes('w-full mb-2')
                                
                                # Добавляем выбор ролей для предоставления доступа к документу
                                ui.label('Роли для предоставления доступа к документу:').classes('font-bold mb-2')
                                
                                # Получаем доступные роли из Mayan EDMS

                                
                                try:
                                    # Используем системный клиент для получения ролей
                                    system_client = await MayanClient.create_default()
                                    roles = await system_client.get_roles(page=1, page_size=1000)
                                    
                                    # Создаем словарь role_label -> role_label для выбора
                                    role_options = {}
                                    for role in roles:
                                        role_label = role.get('label')
                                        if role_label:
                                            role_options[role_label] = role_label
                                    
                                    roles_select = ui.select(
                                        options=role_options,
                                        label='Выберите роли (можно выбрать несколько)',
                                        multiple=True,
                                        value=[],
                                        with_input=True
                                    ).classes('w-full mb-2')
                                    
                                    if not role_options:
                                        ui.label('Роли не найдены в системе').classes('text-sm text-orange-500 mb-2')
                                        roles_select = None
                                    
                                except Exception as e:
                                    logger.error(f'Ошибка при загрузке ролей: {e}', exc_info=True)
                                    ui.label(f'Ошибка загрузки ролей: {str(e)}').classes('text-sm text-red-500 mb-2')
                                    roles_select = None
                                
                                # Информационное сообщение
                                ui.label('Выберите роли, которым будет предоставлен доступ к документу для подписания').classes('text-xs text-gray-600 mb-2')
                                
                                # Определяем функции после объявления всех переменных
                                async def search_and_display_documents_for_task(query: str = ''):
                                    """Ищет и отображает документы из Mayan EDMS для выбора"""
                                    try:
                                        # Если query не передан, берем из поля ввода
                                        if not query and hasattr(document_search_input, 'value'):
                                            query = document_search_input.value or ''
                                        
                                        document_results_container.clear()
                                        
                                        # Показываем индикатор загрузки
                                        with document_results_container:
                                            ui.label('Поиск документов...').classes('text-sm text-gray-600 text-center py-4')
                                                                                
                                        # Получаем клиент Mayan EDMS
                                        mayan_client = await MayanClient.create_with_session_user()
                                        
                                        # Выполняем поиск
                                        query = query.strip() if query else ''
                                        
                                        if query:
                                            logger.info(f"Выполняем поиск документов по запросу: '{query}'")
                                            documents = await mayan_client.search_documents(query, page=1, page_size=20)
                                            logger.info(f"Найдено документов: {len(documents)}")
                                        else:
                                            # Если запрос пустой, показываем последние документы
                                            logger.info("Запрос пустой, показываем последние документы")
                                            documents = await mayan_client.get_documents(page=1, page_size=20)
                                        
                                        # Очищаем контейнер перед показом результатов
                                        document_results_container.clear()
                                        
                                        if not documents:
                                            with document_results_container:
                                                ui.label('Документы не найдены').classes('text-sm text-gray-500 text-center py-4')
                                            return
                                        
                                        # Отображаем найденные документы
                                        with document_results_container:
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
                                                        
                                                        # Кнопка выбора документа
                                                        ui.button(
                                                            'Выбрать',
                                                            icon='check',
                                                            on_click=lambda d=doc: select_document_for_task(d)
                                                        ).classes('bg-green-500 text-white')
                                        
                                    except Exception as e:
                                        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
                                        document_results_container.clear()
                                        with document_results_container:
                                            ui.label(f'Ошибка при поиске: {str(e)}').classes('text-sm text-red-600 text-center py-4')
                                
                                # Добавляем обработчик Enter для поля поиска (после определения функции)
                                document_search_input.on('keydown.enter', lambda: search_and_display_documents_for_task(document_search_input.value))
                                
                                def select_document_for_task(doc):
                                    """Выбирает документ и автоматически заполняет поля формы"""
                                    try:
                                        # Заполняем поля формы автоматически
                                        document_id_input.value = str(doc.document_id)
                                        document_name_input.value = doc.label
                                        
                                        # Обновляем метку выбранного документа
                                        selected_doc_label.text = f'✓ Выбран: {doc.label} (ID: {doc.document_id})'
                                        selected_doc_label.classes('text-sm text-green-600 font-semibold mb-2')
                                        
                                        # Показываем уведомление
                                        ui.notify(f'Выбран документ: {doc.label} (ID: {doc.document_id})', type='positive')
                                        
                                        # Сворачиваем результаты поиска и показываем подтверждение
                                        document_results_container.clear()
                                        with document_results_container:
                                            with ui.card().classes('p-3 bg-green-50 border-l-4 border-green-500'):
                                                with ui.row().classes('items-center'):
                                                    ui.icon('check_circle').classes('text-green-500 mr-2 text-xl')
                                                    with ui.column().classes('flex-1'):
                                                        ui.label(f'Выбран документ: {doc.label}').classes('text-sm font-semibold')
                                                        ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-600')
                                                        if hasattr(doc, 'file_latest_filename') and doc.file_latest_filename:
                                                            ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                                                
                                                # Кнопка для изменения выбора
                                                ui.button(
                                                    'Выбрать другой документ',
                                                    icon='refresh',
                                                    on_click=lambda: search_and_display_documents_for_task(document_search_input.value)
                                                ).classes('mt-2 bg-blue-500 text-white')
                                    
                                    except Exception as e:
                                        logger.error(f"Ошибка при выборе документа: {e}", exc_info=True)
                                        ui.notify(f'Ошибка при выборе документа: {str(e)}', type='negative')
                                
                                def reset_search():
                                    """Сбрасывает поиск и очищает все поля"""
                                    try:
                                        # Очищаем поле поиска
                                        document_search_input.value = ''
                                        
                                        # Очищаем контейнер результатов
                                        document_results_container.clear()
                                        
                                        # Сбрасываем выбранный документ
                                        selected_doc_label.text = 'Документ не выбран'
                                        selected_doc_label.classes('text-sm text-gray-500 mb-2')
                                        
                                        # Очищаем поля документа
                                        document_id_input.value = ''
                                        document_name_input.value = ''
                                        
                                        ui.notify('Поиск сброшен', type='info')
                                    
                                    except Exception as e:
                                        logger.error(f"Ошибка при сбросе поиска: {e}", exc_info=True)
                                        ui.notify(f'Ошибка при сбросе: {str(e)}', type='negative')
                                
                                # Обновляем обработчики кнопок
                                search_btn.on_click(lambda: search_and_display_documents_for_task(document_search_input.value))
                                
                                # Для кнопки "Показать последние" передаем пустой запрос явно
                                refresh_btn.on_click(lambda: search_and_display_documents_for_task(''))
                                
                                reset_btn.on_click(lambda: reset_search())
                            else:
                                # Если это не процесс подписания, создаем пустые значения
                                document_id_input = None
                                document_name_input = None
                                roles_select = None
                        
                        # Дополнительные переменные
                        with ui.column().classes('w-full mb-4'):
                            ui.label('Дополнительные параметры:').classes('font-bold mb-2')
                            
                            # Категория
                            category_input = ui.input(
                                label='Категория',
                                placeholder='Введите категорию задачи',
                                value=''
                            ).classes('w-full mb-2')
                            
                            # Теги
                            tags_input = ui.input(
                                label='Теги (через запятую)',
                                placeholder='Введите теги через запятую',
                                value=''
                            ).classes('w-full mb-2')
                        
                        # Кнопки
                        with ui.row().classes('w-full justify-end mt-4'):
                            start_button = ui.button(
                                'Запустить процесс',
                                on_click=lambda: start_process_with_form(
                                    dialog,
                                    task_name_input.value,
                                    task_description_input.value,
                                    priority_select.value,
                                    due_date_input.value,
                                    category_input.value,
                                    tags_input.value,
                                    start_button,
                                    document_id_input.value if document_id_input else '',
                                    document_name_input.value if document_name_input else '',
                                    roles_select.value if roles_select else []
                                ),
                                icon='play_arrow'
                            ).classes('bg-green-500 text-white')
                            ui.button('Отмена', on_click=dialog.close).classes('mr-2')
                    
                    dialog.open()
                
                # Функция для запуска процесса с параметрами из формы
                async def start_process_with_form(dialog, task_name, task_description, priority, due_date, category, tags, start_button, document_id='', document_name='', selected_roles=None):
                    try:
                        if not camunda_client:
                            ui.notify('Camunda клиент не инициализирован', type='negative')
                            return
                            
                        # Валидация формы
                        if not task_name.strip():
                            ui.notify('Название задачи обязательно для заполнения', type='warning')
                            return
                        
                        if not task_description.strip():
                            ui.notify('Описание задачи обязательно для заполнения', type='warning')
                            return
                        
                        # Валидация даты
                        if not due_date:
                            ui.notify('Срок выполнения обязателен для заполнения', type='warning')
                            return
                        
                        try:
                            due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                            # Проверяем, что дата не в прошлом
                            if due_date_obj.date() < datetime.now().date():
                                ui.notify('Срок выполнения не может быть в прошлом', type='warning')
                                return
                            
                            # Конвертируем в формат даты для Camunda
                            due_date_utc = due_date_obj.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)
                            due_date_str = due_date_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0000'
                            
                        except ValueError:
                            ui.notify('Неверный формат даты. Используйте YYYY-MM-DD', type='warning')
                            return
                        
                        # Показываем индикатор загрузки
                        start_button.props('loading')
                        start_button.text = 'Запуск процесса...'
                        
                        process_key = process_template_select.value
                        assignee_list = [user['login'] for user in selected_users]
                        
                        # Подготавливаем переменные процесса
                        process_variables = {
                            'taskName': {
                                'value': task_name.strip(),
                                'type': 'String'
                            },
                            'taskDescription': {
                                'value': task_description.strip(),
                                'type': 'String'
                            },
                            'priority': {
                                'value': int(priority),
                                'type': 'Integer'
                            },
                            'dueDate': {
                                'value': due_date_str,
                                'type': 'Date'
                            }
                        }
                        
                        # Добавляем дополнительные переменные если они заполнены
                        if category.strip():
                            process_variables['category'] = {
                                'value': category.strip(),
                                'type': 'String'
                            }
                        
                        if tags.strip():
                            process_variables['tags'] = {
                                'value': tags.strip(),
                                'type': 'String'
                            }
                        
                        # Получаем текущего пользователя один раз в начале функции
                        current_user = get_current_user()
                        creator_username = current_user.username if current_user else None
                        
                        # Выбираем метод запуска в зависимости от типа процесса
                        process_id = None
                        if process_key == 'DocumentReviewProcessMultiInstance':
                            # Получаем текущего пользователя для передачи creator_username
                            current_user = get_current_user()
                            creator_username = current_user.username if current_user else None
                            
                            process_id = await camunda_client.start_document_review_process_multi_instance(
                                document_name=task_name.strip(),
                                document_content=task_description.strip(),
                                assignee_list=assignee_list,
                                business_key=f"batch_{int(time.time())}",
                                creator_username=creator_username,
                                due_date=due_date_str  # ДОБАВИТЬ ЭТУ СТРОКУ
                            )
                        elif process_key == 'DocumentSigningProcess':
                            # Специальная обработка для процесса подписания документов
                            # Используем специальные поля для подписания документов
                            if not document_id.strip():
                                ui.notify('ID документа обязателен для процесса подписания!', type='error')
                                return
                            
                            if not document_name.strip():
                                ui.notify('Название документа обязательно для процесса подписания!', type='error')
                                return
                            
                            # Проверяем, что document_id является числовым
                            if not document_id.isdigit():
                                ui.notify('ID документа должен быть числовым значением!', type='error')
                                return
                            
                            # Валидация ролей (может быть пустым списком, но должно быть списком)
                            if selected_roles is None:
                                selected_roles = []
                            
                            # Преобразуем в список, если это не список
                            if isinstance(selected_roles, str):
                                selected_roles = [selected_roles] if selected_roles else []
                            
                            process_id = await camunda_client.start_document_signing_process(
                                document_id=document_id.strip(),
                                document_name=document_name.strip(),
                                signer_list=assignee_list,
                                role_names=selected_roles,  # Передаем выбранные роли
                                business_key=f"signing_{int(time.time())}",
                                creator_username=creator_username,  # Добавить эту строку
                                due_date=due_date_str  # Добавляем due_date в переменные процесса
                            )
                        else:
                            # Для других процессов используем универсальный метод
                            # Получаем текущего пользователя для передачи creator_username
                            
                            current_user = get_current_user()
                            creator_username = current_user.username if current_user else None
                            
                            process_id = await camunda_client.start_process(
                                process_definition_key=process_key,
                                assignee_list=assignee_list,
                                additional_variables=process_variables,
                                business_key=f"batch_{int(time.time())}",
                                creator_username=creator_username  # Добавить эту строку
                            )
                        
                        print(f"Результат запуска процесса: {process_id}")
                        
                        if process_id:
                            ui.notify(f'Процесс {process_key} успешно запущен (ID: {process_id}) для {len(assignee_list)} пользователей', type='positive')
                            
                            # Закрываем диалог и очищаем выбор
                            dialog.close()
                            clear_selection()
                            process_template_select.value = None
                        else:
                            ui.notify('Ошибка при запуске процесса', type='negative')
                        
                    except Exception as e:
                        ui.notify(f'Ошибка при запуске процесса: {str(e)}', type='negative')
                        logger.error(f"Ошибка при запуске процесса: {e}", exc_info=True)
                    finally:
                        # Убираем индикатор загрузки
                        start_button.props(remove='loading')
                        start_button.text = 'Запустить процесс'
                
                # Загружаем шаблоны процессов при инициализации страницы с задержкой
                ui.timer(2.0, lambda: load_process_templates(), once=True)
                