from components import theme
from components.message import message
from nicegui import ui, events
from auth.ldap_auth import LDAPAuthenticator
from services.camunda_connector import CamundaClient
from auth.middleware import get_current_user
from services.document_access_manager import document_access_manager
from services.mayan_connector import MayanClient
from config.settings import config
from datetime import datetime, timezone
import time
import asyncio
from utils.aggrid_locale import AGGGRID_RUSSIAN_LOCALE
from app_logging.logger import get_logger

logger = get_logger(__name__)

class TaskAssignmentPage:

    def __init__(self) -> None:
        """The page is created as soon as the class is instantiated.

        This can obviously also be done in a method, if you want to decouple the instantiation of the object from the page creation.
        """
        @ui.page('/task-assignment')
        async def page_task_assignment():
            with theme.frame('Назначение задач пользователям'):
                #message('Выбор пользователей и назначение им задач')
                # Сохраняем текущего пользователя в замыкании для использования в асинхронных функциях
                current_user = get_current_user()
                if not current_user:
                    ui.notify('Ошибка: пользователь не авторизован', type='error')
                    ui.navigate.to('/login')
                    return
                
                # Получаем query параметры из URL
                document_id_from_url = None
                process_type_from_url = None
                
                try:
                    from nicegui import context
                    import urllib.parse
                    
                    if hasattr(context, 'client') and context.client and hasattr(context.client, 'request'):
                        request = context.client.request
                        if hasattr(request, 'query_params'):
                            query_params = request.query_params
                            document_id_from_url = query_params.get('document_id', '')
                            process_type_from_url = query_params.get('process_type', '')
                        else:
                            url = str(request.url) if hasattr(request, 'url') else ''
                            if '?' in url:
                                query_string = url.split('?')[1]
                                params = urllib.parse.parse_qs(query_string)
                                document_id_from_url = params.get('document_id', [''])[0]
                                process_type_from_url = params.get('process_type', [''])[0]
                except Exception as e:
                    logger.warning(f"Не удалось получить query параметры: {e}")
                
                # Сохраняем для использования после инициализации компонентов
                pending_document_id = document_id_from_url if document_id_from_url else None
                pending_process_type = process_type_from_url if process_type_from_url else None
                
                # ===== ДОБАВИТЬ: Переменная для хранения названия документа =====
                pending_document_name = None
                # ===== КОНЕЦ ДОБАВЛЕНИЯ =====
                
                # Словарь для хранения ссылок на элементы формы документа
                document_form_elements = {
                    'document_id_input': None,
                    'document_name_input': None,
                    'selected_doc_label': None,
                    'selected_doc_label_review': None
                }
                
                # Список для хранения выбранных пользователей
                selected_users = []
                # Список для хранения выбранных ролей (при выборе пользователей по роли)
                selected_roles_from_selection = []
                
                # Инициализация LDAP клиента
                ldap_authenticator = None
                try:
                    ldap_authenticator = LDAPAuthenticator()
                except Exception as e:
                    logger.error(f"Ошибка при инициализации LDAP клиента: {e}")
                    ui.notify('Ошибка: не удалось подключиться к LDAP серверу', type='error')
                
                all_users = await ldap_authenticator.get_users() if ldap_authenticator else []
                
                # Инициализация Camunda клиента с использованием конфигурации
                camunda_client = None
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
                
                # Кеш для ролей пользователей (username -> [роли])
                user_roles_cache = {}
                
                async def load_user_roles():
                    """Загружает роли для всех пользователей через группы ролей"""
                    try:
                        logger.info('Начинаем загрузку ролей пользователей...')
                        system_client = await MayanClient.create_default()
                        
                        # Получаем все роли
                        roles = await system_client.get_roles(page=1, page_size=1000)
                        logger.info(f'Получено {len(roles)} ролей')
                        
                        # Для каждой роли получаем группы, затем пользователей групп
                        for role in roles:
                            role_id = role.get('id')
                            role_label = role.get('label')
                            
                            if not role_id or not role_label:
                                continue
                            
                            try:
                                # Получаем группы роли
                                role_groups = await system_client.get_role_groups(role_id)
                                
                                # Для каждой группы получаем пользователей
                                for group in role_groups:
                                    group_id = group.get('id')
                                    if not group_id:
                                        continue
                                    
                                    try:
                                        # Получаем пользователей группы
                                        group_users = await system_client.get_group_users(str(group_id))
                                        
                                        # Добавляем роль к каждому пользователю
                                        for group_user in group_users:
                                            username = group_user.get('username')
                                            if username:
                                                if username not in user_roles_cache:
                                                    user_roles_cache[username] = []
                                                if role_label not in user_roles_cache[username]:
                                                    user_roles_cache[username].append(role_label)
                                        
                                    except Exception as e:
                                        logger.warning(f'Ошибка при получении пользователей группы {group_id}: {e}')
                                        continue
                                
                            except Exception as e:
                                logger.warning(f'Ошибка при получении групп роли {role_label}: {e}')
                                continue
                        
                        logger.info(f'Загружены роли для {len(user_roles_cache)} пользователей')
                        
                        # Обновляем данные в таблицах
                        update_users_table_with_roles()
                        update_selected_users_table()
                        
                    except Exception as e:
                        logger.error(f'Ошибка при загрузке ролей пользователей: {e}', exc_info=True)
                
                def update_users_table_with_roles():
                    """Обновляет таблицу всех пользователей с ролями"""
                    try:
                        users_data = []
                        for user in all_users:
                            user_dict = user.__dict__ if hasattr(user, '__dict__') else {
                                'login': getattr(user, 'login', None) or getattr(user, 'username', None),
                                'first_name': getattr(user, 'first_name', ''),
                                'last_name': getattr(user, 'last_name', ''),
                                'email': getattr(user, 'email', '')
                            }
                            
                            # Добавляем роли пользователя
                            user_login = user_dict.get('login')
                            if user_login and user_login in user_roles_cache:
                                user_dict['roles'] = ', '.join(user_roles_cache[user_login])
                            else:
                                user_dict['roles'] = ''
                            
                            users_data.append(user_dict)
                        
                        all_users_grid.options['rowData'] = users_data
                        all_users_grid.update()
                    except Exception as e:
                        logger.error(f'Ошибка при обновлении таблицы пользователей: {e}', exc_info=True)
               
                async def on_row_dblclick(event):
                    row_data = event.args.get('data') if isinstance(event.args, dict) else None
                    if row_data:
                        add_user_to_selection(row_data)
                    else:
                        ui.notify("Could not get row data")
                
                # Контейнер с двумя таблицами рядом
                with ui.row().classes('w-full gap-4 items-stretch'):
                    # Левая колонка - таблица всех пользователей
                    with ui.column().classes('flex-1 flex flex-col'):
                        # Заголовок и поле поиска в одной строке
                        with ui.row().classes('w-full items-center gap-2 mb-2'):
                            ui.label('Все пользователи:').classes('text-lg font-bold')
                            search_input = ui.input(
                                placeholder='Введите логин, имя, фамилию или email...',
                                on_change=lambda e: ui.timer(0.1, lambda: filter_users(e.value, all_users, all_users_grid), once=True)
                            ).classes('w-80')
                        
                        # Таблица всех пользователей - увеличенная высота, чтобы начиналась там же где select в правой колонке
                        all_users_grid = ui.aggrid({
                            'columnDefs': [
                                {'headerName': 'Логин', 'field': 'login'},
                                {'headerName': 'Имя', 'field': 'first_name'},
                                {'headerName': 'Фамилия', 'field': 'last_name'},
                                {'headerName': 'Email', 'field': 'email'},
                                {'headerName': 'Роли', 'field': 'roles', 'sortable': True, 'filter': True, 'width': 200},
                            ],
                            'rowData': [ user.__dict__ for user in all_users],
                            'rowSelection': 'multiple',
                            'localeText': AGGGRID_RUSSIAN_LOCALE,
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
                        }).classes('w-full').style('height: 356px;').on('cellDoubleClicked', on_row_dblclick)
                       
                        user_count_label = ui.label(f'Найдено пользователей: {len(all_users)}').classes('text-xs text-gray-600 mt-2')
                    
                    # Правая колонка - таблица выбранных пользователей
                    with ui.column().classes('flex-1 flex flex-col'):
                        # Заголовок и скрытое поле для выравнивания с левой колонкой
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Выбранные пользователи:').classes('text-lg font-bold')
                            # Скрытое поле для выравнивания с полем поиска слева (такая же высота)
                            ui.input().classes('w-80').style('visibility: hidden;')
                        
                        # Добавляем select для выбора роли
                        role_select_container = ui.column().classes('w-full mb-2')
                        role_select = None
                        
                        async def load_roles_for_selection():
                            """Загружает роли для выбора"""
                            nonlocal role_select
                            try:
                                system_client = await MayanClient.create_default()
                                roles = await system_client.get_roles(page=1, page_size=1000)
                                
                                role_options = {}
                                for role in roles:
                                    role_label = role.get('label')
                                    if role_label:
                                        role_options[role_label] = role_label
                                
                                if role_options:
                                    with role_select_container:
                                        role_select = ui.select(
                                            options=role_options,
                                            label='Выбрать пользователей по роли',
                                            value=None,
                                            clearable=True,
                                            with_input=True,
                                            on_change=lambda: ui.timer(0.1, lambda: handle_role_selection(), once=True)
                                        ).classes('w-full')
                                
                            except Exception as e:
                                logger.error(f'Ошибка при загрузке ролей: {e}', exc_info=True)
                        
                        async def handle_role_selection():
                            """Обрабатывает выбор роли и добавляет пользователей в выбор через группы"""
                            nonlocal selected_roles_from_selection
                            
                            if not role_select or not role_select.value:
                                # Если роль очищена, очищаем список выбранных ролей
                                selected_roles_from_selection = []
                                # Пересоздаем форму, если она видна, чтобы обновить отображение ролей
                                if process_form_container.visible:
                                    ui.timer(0.1, lambda: create_process_form(), once=True)
                                return
                            
                            try:
                                selected_role_label = role_select.value
                                ui.notify(f'Загрузка пользователей роли: {selected_role_label}', type='info')
                                
                                # Сохраняем выбранную роль
                                if selected_role_label not in selected_roles_from_selection:
                                    selected_roles_from_selection.append(selected_role_label)
                                
                                # Получаем роль по label и находим её ID
                                system_client = await MayanClient.create_default()
                                roles = await system_client.get_roles(page=1, page_size=1000)
                                
                                role_id = None
                                for role in roles:
                                    if role.get('label') == selected_role_label:
                                        role_id = role.get('id')
                                        break
                                
                                if not role_id:
                                    ui.notify(f'Роль {selected_role_label} не найдена', type='error')
                                    return
                                
                                # Получаем группы, состоящие в выбранной роли
                                role_groups = await system_client.get_role_groups(role_id)
                                
                                if not role_groups:
                                    ui.notify(f'В роли {selected_role_label} нет групп', type='warning')
                                    return
                                
                                # Собираем всех пользователей из всех групп роли
                                all_role_usernames = set()
                                
                                for group in role_groups:
                                    group_id = group.get('id')
                                    if not group_id:
                                        continue
                                    
                                    try:
                                        # Получаем пользователей группы
                                        group_users = await system_client.get_group_users(str(group_id))
                                        
                                        # Добавляем username в множество
                                        for group_user in group_users:
                                            username = group_user.get('username')
                                            if username:
                                                all_role_usernames.add(username)
                                        
                                        logger.info(f'Группа {group.get("name", group_id)} содержит {len(group_users)} пользователей')
                                    except Exception as e:
                                        logger.warning(f'Ошибка при получении пользователей группы {group_id}: {e}')
                                        continue
                                
                                if not all_role_usernames:
                                    ui.notify(f'В группах роли {selected_role_label} не найдено пользователей', type='warning')
                                    return
                                
                                # Находим соответствующих пользователей в all_users по username
                                added_count = 0
                                for user in all_users:
                                    user_login = getattr(user, 'login', None) or getattr(user, 'username', None)
                                    if user_login and user_login in all_role_usernames:
                                        # Проверяем, не выбран ли уже этот пользователь
                                        if not any(selected_user['login'] == user_login for selected_user in selected_users):
                                            user_dict = user.__dict__ if hasattr(user, '__dict__') else {
                                                'login': user_login,
                                                'first_name': getattr(user, 'first_name', ''),
                                                'last_name': getattr(user, 'last_name', ''),
                                                'email': getattr(user, 'email', '')
                                            }
                                            selected_users.append(user_dict)
                                            added_count += 1
                                
                                # Обновляем таблицу
                                update_selected_users_table()
                                ui.timer(0.1, lambda: update_selected_count(), once=True)
                                
                                if added_count > 0:
                                    ui.notify(f'Добавлено {added_count} пользователей из {len(role_groups)} групп роли {selected_role_label}', type='positive')
                                else:
                                    ui.notify('Все пользователи этой роли уже выбраны', type='info')
                                
                                # Пересоздаем форму, если она видна, чтобы обновить отображение ролей
                                if process_form_container.visible:
                                    ui.timer(0.1, lambda: create_process_form(), once=True)
                                
                            except Exception as e:
                                logger.error(f'Ошибка при выборе роли: {e}', exc_info=True)
                                ui.notify(f'Ошибка при загрузке пользователей роли: {str(e)}', type='error')
                        
                        # Загружаем роли при инициализации
                        ui.timer(0.1, lambda: load_roles_for_selection(), once=True)
                        
                        # Загружаем роли пользователей в фоне
                        ui.timer(0.5, lambda: load_user_roles(), once=True)
                        
                        # Таблица выбранных пользователей - высота вычисляется автоматически через calc()
                        selected_users_grid = ui.aggrid({
                            'columnDefs': [
                                {'headerName': 'Логин', 'field': 'login'},
                                {'headerName': 'Имя', 'field': 'first_name'},
                                {'headerName': 'Фамилия', 'field': 'last_name'},
                                {'headerName': 'Email', 'field': 'email'},
                                {'headerName': 'Роли', 'field': 'roles', 'sortable': True, 'filter': True, 'width': 200},
                            ],
                            'rowData': [],
                            'rowSelection': 'multiple',
                            'localeText': AGGGRID_RUSSIAN_LOCALE,
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
                        }).classes('w-full').style('height: calc(356px - 72px); margin-bottom: 0;')
                        
                        # Счетчик выбранных пользователей и кнопки в одной строке
                        with ui.row().classes('w-full items-center justify-between').style('margin-top: 4px;'):
                            selected_count_label = ui.label('Выбрано пользователей: 0').classes('text-xs text-gray-600')
                            
                            # Кнопки для работы с выбранными пользователями
                            with ui.row().classes('gap-2'):
                                ui.button('Очистить выбор', on_click=lambda: clear_selection()).classes('text-xs px-2 py-1 h-7')
                                ui.button('Удалить выбранного', on_click=lambda: show_selected_rows_selected_users()).classes('text-xs px-2 py-1 h-7')
                
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
                        
                        # Контейнер для выбора шаблона процесса (по центру страницы)
                    process_template_container = ui.column().classes('w-full items-center justify-center').style('margin-top: 0;')
                    
                    with process_template_container:
                        # ui.label('Выберите шаблон процесса:').classes('text-lg font-bold mb-4 text-center')
                        
                        # Обработчик изменения шаблона (определяем до создания select)
                        async def handle_template_change():
                            if process_template_select.value and selected_users:
                                # При изменении шаблона пересоздаем форму (могут быть разные поля)
                                await create_process_form()
                            else:
                                process_form_container.set_visibility(False)
                                process_form_container.clear()
                        
                        # Контейнер для строки с select и полями наименования/описания
                        with ui.column().classes('w-full items-center gap-2'):
                            # Строка с select шаблона и полями наименования/описания - всегда видна
                            process_name_row = ui.row().classes('w-full gap-2 items-end justify-center')
                            
                            with process_name_row:
                                # Select шаблона
                                process_template_select = ui.select(
                                    options={},
                                    label='Шаблон процесса',
                                    with_input=True,
                                    clearable=True,
                                    on_change=lambda: ui.timer(0.1, lambda: handle_template_change(), once=True)
                                ).classes('flex-[1]').props('id="process_template_select"')
                                
                                # Наименование процесса
                                task_name_input = ui.input(
                                    label='Название задачи',
                                    placeholder='Введите название задачи',
                                    value='Новая задача'
                                ).classes('flex-[2]')
                                
                                # Описание процесса
                                task_description_input = ui.textarea(
                                    label='Описание задачи',
                                    placeholder='Введите описание задачи',
                                    value=''
                                ).classes('flex-[2]').props('rows=2').style('resize: vertical;')
                            
                            # Инициализируем переменные для формы (будут созданы внутри контейнера)
                            priority_select = None
                            due_date_input = None
                            category_input = None
                            tags_input = None
                            document_id_input = None
                            document_name_input = None
                            roles_select = None
                            start_button = None
                            
                        # Контейнер для формы запуска процесса (изначально скрыт)
                        process_form_container = ui.column().classes('w-full mt-4')
                        process_form_container.set_visibility(False)
                
                
                # Функция для добавления пользователя в выбор
                def add_user_to_selection(user_data):
                    # Проверяем, не выбран ли уже этот пользователь
                    if not any(user['login'] == user_data['login'] for user in selected_users):
                        selected_users.append(user_data)
                        update_selected_users_table()
                        ui.timer(0.1, lambda: update_selected_count(), once=True)
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
                    ui.timer(0.1, lambda: update_selected_count(), once=True)
                    
                    ui.notify(f'Пользователь {login} удален из выбора', type='info')
                
                # Функция для обновления таблицы выбранных пользователей
                def update_selected_users_table():
                    print(f"Обновление таблицы. Выбранных пользователей: {len(selected_users)}")
                    # Добавляем роли к выбранным пользователям
                    for user in selected_users:
                        user_login = user.get('login')
                        if user_login and user_login in user_roles_cache:
                            user['roles'] = ', '.join(user_roles_cache[user_login])
                        elif 'roles' not in user:
                            user['roles'] = ''
                    
                    selected_users_grid.options['rowData'] = selected_users
                    selected_users_grid.update()
                
                # Функция для обновления счетчика выбранных пользователей
                async def update_selected_count():
                    selected_count_label.text = f'Выбрано пользователей: {len(selected_users)}'
                    # Сбрасываем форму только если пользователей стало 0
                    if len(selected_users) == 0:
                        process_form_container.set_visibility(False)
                        process_form_container.clear()
                    # Если пользователей больше 0 и шаблон выбран, но форма не видна - создаем её
                    elif process_template_select.value and len(selected_users) > 0:
                        if not process_form_container.visible:
                            logger.info(f"Создание формы: шаблон={process_template_select.value}, пользователей={len(selected_users)}")
                            await create_process_form()
                        # Если форма уже видна - не трогаем, данные сохраняются
                
                # Функция для очистки выбора
                def clear_selection():
                    selected_users.clear()
                    selected_roles_from_selection.clear()
                    update_selected_users_table()
                    ui.timer(0.1, lambda: update_selected_count(), once=True)
                    ui.notify('Выбор очищен', type='info')

                async def filter_users(query: str, users: list, grid_component, count_label=user_count_label):
                    if query:
                        if not ldap_authenticator:
                            ui.notify('LDAP клиент не инициализирован', type='error')
                            return
                        filtered_users = await ldap_authenticator.users_filter(users, query)
                        # users_filter уже возвращает словари, добавляем роли
                        users_data = []
                        for user_dict in filtered_users:
                            # Добавляем роли пользователя
                            user_login = user_dict.get('login')
                            if user_login and user_login in user_roles_cache:
                                user_dict['roles'] = ', '.join(user_roles_cache[user_login])
                            else:
                                user_dict['roles'] = ''
                            
                            users_data.append(user_dict)
                        
                        grid_component.options['rowData'] = users_data
                        grid_component.update()
                        count_label.text = f'Найдено пользователей: {len(filtered_users)}'
                    else:
                        # Если поиск пустой, показываем всех пользователей
                        update_users_table_with_roles()
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
                        
                        # ===== ДОБАВИТЬ ЭТОТ КОД =====
                        # Автоматически заполняем документ и выбираем шаблон, если передан document_id
                        if pending_document_id:
                            # Используем таймер с небольшой задержкой, чтобы дождаться полной инициализации
                            ui.timer(0.5, lambda: auto_fill_document_from_url(), once=True)
                        # ===== КОНЕЦ ДОБАВЛЕНИЯ =====
                        
                    except Exception as e:
                        ui.notify(f'Ошибка при загрузке шаблонов процессов: {str(e)}', type='negative')
                        logger.error(f"Ошибка при загрузке шаблонов процессов: {e}", exc_info=True)
                                                       
                # Функция для создания формы запуска процесса на странице
                async def create_process_form():
                    """Создает форму запуска процесса внутри контейнера process_form_container"""
                    if not selected_users:
                        process_form_container.set_visibility(False)
                        process_form_container.clear()
                        return
                    
                    if not process_template_select.value:
                        process_form_container.set_visibility(False)
                        process_form_container.clear()
                        return
                    
                    # Сохраняем значения document_id и document_name из старых полей (если они были заполнены)
                    saved_document_id = None
                    saved_document_name = None
                    
                    if document_form_elements['document_id_input']:
                        try:
                            saved_document_id = document_form_elements['document_id_input'].value
                        except:
                            pass
                    
                    if document_form_elements['document_name_input']:
                        try:
                            saved_document_name = document_form_elements['document_name_input'].value
                        except:
                            pass
                    
                    # Если значения не были сохранены из полей, но есть pending_document_id, используем его
                    if not saved_document_id and pending_document_id:
                        saved_document_id = pending_document_id
                    # ===== КОНЕЦ СОХРАНЕНИЯ =====
                    
                    # Очищаем контейнер перед созданием новой формы
                    process_form_container.clear()
                    
                    # Показываем контейнер
                    process_form_container.set_visibility(True)
                    
                    logger.info(f"Создание формы для процесса: {process_template_select.value}, пользователей: {len(selected_users)}")
                    
                    # Создаем форму внутри контейнера
                    with process_form_container:
                       
                        # Инициализируем переменные для процессов с документами ДО использования в лямбде
                        document_id_input = None
                        document_name_input = None
                        roles_select = None
                        
                        # Основные переменные
                        with ui.column().classes('w-full mb-4'):
                            # Наименование и описание теперь в строке с select, убираем их отсюда
                            
                            # Приоритет, Срок исполнения и Роли на одной строке
                            with ui.row().classes('w-full gap-2 mb-2'):
                                
                                # Срок исполнения (1 часть - в 4 раза меньше других)
                                due_date_input = ui.input(
                                    label='Срок исполнения',
                                    placeholder='YYYY-MM-DD',
                                    value=''
                                ).classes('flex-[1]').props('type="date"')
                                # Приоритет (4 части)
                                priority_select = ui.select(
                                    options={'1': 'Низкий', '2': 'Средний', '3': 'Высокий', '4': 'Критический'},
                                    label='Приоритет',
                                    value='2'
                                ).classes('flex-[2]')
                                
                                # Роли для доступа (4 части, показываем только для процессов с документами)
                                roles_select_container = ui.column().classes('flex-[4]')
                                roles_select = None
                                
                                # Проверяем, есть ли уже выбранные роли при выборе пользователей
                                # Если роли выбраны вверху, не показываем select для ролей в форме
                                if selected_roles_from_selection:
                                    # Роли уже выбраны вверху, показываем информацию о выбранных ролях
                                    with roles_select_container:
                                        ui.label(f'Роли для доступа (выбраны при выборе пользователей):').classes('text-sm font-semibold mb-1')
                                        roles_text = ', '.join(selected_roles_from_selection)
                                        ui.label(roles_text).classes('text-sm text-gray-600 mb-2')
                                    # Используем выбранные роли
                                    roles_select = None
                                    logger.info(f'Используются роли, выбранные при выборе пользователей: {selected_roles_from_selection}')
                                # Загружаем роли, если это процесс с документами и роли не выбраны вверху
                                elif process_template_select.value and ('DocumentSigningProcess' in process_template_select.value or 'DocumentReviewProcess' in process_template_select.value or 'Ознаком' in process_template_select.value):
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
                                        
                                        with roles_select_container:
                                            roles_select = ui.select(
                                                options=role_options,
                                                label='Роли для доступа',
                                                multiple=True,
                                                value=[],
                                                with_input=True
                                            ).classes('w-full')
                                        
                                        if not role_options:
                                            roles_select = None
                                            
                                    except Exception as e:
                                        logger.error(f'Ошибка при загрузке ролей: {e}', exc_info=True)
                                        roles_select = None
                                else:
                                    roles_select_container.set_visibility(False)

                            if process_template_select.value and 'DocumentSigningProcess' in process_template_select.value:
                                # Поля для подписания документов
                                # Теперь document_id_input, document_name_input, roles_select уже инициализированы как None
                                # и будут переопределены в этом блоке реальными виджетами
                                # ui.label('Параметры подписания:').classes('font-bold mb-2')
                                
                                # Секция выбора документа из Mayan EDMS
                                selected_document_container = ui.column().classes('w-full mb-4')
                                document_form_elements['selected_doc_label'] = selected_document_container  # Сохраняем контейнер вместо label
                                
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
                                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                                        
                                        refresh_btn = ui.button(
                                            'Показать последние',
                                            icon='refresh',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                                        
                                        reset_btn = ui.button(
                                            'Сбросить поиск',
                                            icon='clear',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-orange-500 text-white text-xs px-2 py-1 h-7')
                                    
                                    # Контейнер для результатов поиска
                                    document_results_container = ui.column().classes('w-full max-h-64 overflow-y-auto border rounded p-2 bg-white')
                                
                                # Скрытые переменные для document_id и document_name (не показываем пользователю)
                                document_id_input = ui.input(value='').classes('hidden')
                                document_name_input = ui.input(value='').classes('hidden')
                                # Сохраняем ссылки
                                document_form_elements['document_id_input'] = document_id_input
                                document_form_elements['document_name_input'] = document_name_input
                                
                                # ===== ВОССТАНАВЛИВАЕМ ЗНАЧЕНИЯ =====
                                if saved_document_id:
                                    document_id_input.value = saved_document_id
                                    document_id_input.update()
                                if saved_document_name:
                                    document_name_input.value = saved_document_name
                                    document_name_input.update()
                                # ===== КОНЕЦ ВОССТАНОВЛЕНИЯ =====
                                
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
                                                                                
                                        # Получаем клиент Mayan EDMS используя сохраненного пользователя
                                        try:
                                            # Проверяем наличие API токена у пользователя
                                            if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
                                                raise ValueError(f'У пользователя {current_user.username} нет API токена для доступа к Mayan EDMS')
                                            
                                            # Создаем клиент напрямую с токеном пользователя
                                            mayan_client = MayanClient(
                                                base_url=config.mayan_url,
                                                api_token=current_user.mayan_api_token
                                            )
                                        except ValueError as auth_error:
                                            logger.error(f"Ошибка авторизации при создании клиента Mayan: {auth_error}")
                                            document_results_container.clear()
                                            with document_results_container:
                                                ui.label('Ошибка авторизации').classes('text-sm text-red-600 text-center py-2')
                                                ui.label(f'Детали: {str(auth_error)}').classes('text-xs text-gray-500 text-center mt-1')
                                                ui.label('Пожалуйста, обновите страницу и войдите снова').classes('text-xs text-gray-400 text-center mt-2')
                                            return
                                        except Exception as client_error:
                                            logger.error(f"Ошибка при создании клиента Mayan: {client_error}", exc_info=True)
                                            document_results_container.clear()
                                            with document_results_container:
                                                ui.label('Ошибка подключения').classes('text-sm text-red-600 text-center py-2')
                                                ui.label(f'Детали: {str(client_error)}').classes('text-xs text-gray-500 text-center mt-1')
                                            return
                                        
                                        # Выполняем поиск
                                        query = query.strip() if query else ''
                                        
                                        if query:
                                            logger.info(f"Выполняем поиск документов по запросу: '{query}'")
                                            documents = await mayan_client.search_documents(query, page=1, page_size=20)
                                            logger.info(f"Найдено документов: {len(documents)}")
                                        else:
                                            # Если запрос пустой, показываем последние документы
                                            logger.info("Запрос пустой, показываем последние документы")
                                            try:
                                                documents, total_count = await mayan_client.get_documents(page=1, page_size=20)
                                                logger.info(f"Получено документов: {len(documents)}, всего: {total_count}")
                                            except Exception as get_docs_error:
                                                logger.error(f"Ошибка при получении последних документов: {get_docs_error}", exc_info=True)
                                                documents = []
                                        
                                        # Очищаем контейнер перед показом результатов
                                        document_results_container.clear()
                                        
                                        if not documents:
                                            with document_results_container:
                                                ui.label('Документы не найдены').classes('text-sm text-gray-500 text-center py-4')
                                                ui.label('У вас нет доступа к документам или документы отсутствуют').classes('text-xs text-gray-400 text-center mt-2')
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
                                                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                                        
                                    except Exception as e:
                                        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
                                        document_results_container.clear()
                                        with document_results_container:
                                            ui.label('Ошибка при поиске документов').classes('text-sm text-red-600 text-center py-2')
                                            ui.label(f'Детали: {str(e)}').classes('text-xs text-gray-500 text-center mt-1')
                                            ui.label('Проверьте подключение к Mayan EDMS и права доступа').classes('text-xs text-gray-400 text-center mt-2')
                                
                                # Добавляем обработчик Enter для поля поиска (после определения функции)
                                document_search_input.on('keydown.enter', lambda: search_and_display_documents_for_task(document_search_input.value))
                                
                                def select_document_for_task(doc):
                                    """Выбирает документ и автоматически заполняет поля формы"""
                                    try:
                                        # Заполняем поля формы автоматически
                                        document_id_input.value = str(doc.document_id)
                                        document_name_input.value = doc.label
                                        
                                        # Обновляем метку выбранного документа
                                        selected_document_container.clear()
                                        with selected_document_container:
                                            with ui.card().classes('p-3 bg-green-50 border-l-4 border-green-500'):
                                                with ui.row().classes('items-start gap-4 w-full'):
                                                    ui.icon('check_circle').classes('text-green-500 mr-2 text-xl')
                                                    with ui.column().classes('flex-1'):
                                                        ui.label(f'Выбран документ: {doc.label}').classes('text-sm font-semibold')
                                                        ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-600')
                                                        if hasattr(doc, 'file_latest_filename') and doc.file_latest_filename:
                                                            ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                                                
                                                # Кнопка для изменения выбора
                                                # Используем прямой вызов через ui.timer для сохранения контекста NiceGUI
                                                def on_select_another_click():
                                                    """Обработчик для кнопки выбора другого документа"""
                                                    # Сохраняем значение запроса в переменную
                                                    search_query = document_search_input.value
                                                    # Используем ui.timer для вызова асинхронной функции в правильном контексте
                                                    # NiceGUI автоматически обработает асинхронную функцию
                                                    async def timer_callback():
                                                        await search_and_display_documents_for_task(search_query)
                                                    ui.timer(0.1, timer_callback, once=True)
                                                
                                                ui.button(
                                                    'Выбрать другой документ',
                                                    icon='refresh',
                                                    on_click=on_select_another_click
                                                ).classes('mt-2 bg-blue-500 text-white text-xs px-2 py-1 h-7')
                                    
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
                                        selected_document_container.clear()
                                        selected_document_container.update()
                                        
                                        ui.notify('Поиск сброшен', type='info')
                                    
                                    except Exception as e:
                                        logger.error(f"Ошибка при сбросе поиска: {e}", exc_info=True)
                                        ui.notify(f'Ошибка при сбросе: {str(e)}', type='negative')
                                
                                # Обновляем обработчики кнопок
                                search_btn.on_click(lambda: search_and_display_documents_for_task(document_search_input.value))
                                
                                # Для кнопки "Показать последние" передаем пустой запрос явно
                                refresh_btn.on_click(lambda: search_and_display_documents_for_task(''))
                                
                                reset_btn.on_click(lambda: reset_search())
                            
                            elif process_template_select.value and ('DocumentReviewProcess' in process_template_select.value or 'Ознаком' in process_template_select.value):
                                # Поля для ознакомления с документом
                                ui.label('Параметры ознакомления с документом:').classes('font-bold mb-2')
                                
                                # Секция выбора документа из Mayan EDMS
                                selected_doc_label_review = ui.label('Документ не выбран').classes('text-sm text-gray-500 mb-2')
                                # Сохраняем ссылку
                                document_form_elements['selected_doc_label_review'] = selected_doc_label_review
                                
                                with ui.column().classes('w-full mb-4 p-3 bg-blue-50 rounded border'):
                                    ui.label('Выбор документа из Mayan EDMS:').classes('font-semibold mb-2')
                                    
                                    # Поиск документа
                                    document_search_input_review = ui.input(
                                        label='Поиск документа',
                                        placeholder='Введите название документа для поиска...',
                                        value=''
                                    ).classes('w-full mb-2')
                                    
                                    # Кнопки поиска
                                    with ui.row().classes('w-full mb-2 gap-2'):
                                        search_btn_review = ui.button(
                                            'Поиск документов',
                                            icon='search',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
                                        
                                        refresh_btn_review = ui.button(
                                            'Показать последние',
                                            icon='refresh',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                                        
                                        reset_btn_review = ui.button(
                                            'Сбросить поиск',
                                            icon='clear',
                                            on_click=lambda: None  # Будет обновлено ниже
                                        ).classes('bg-orange-500 text-white text-xs px-2 py-1 h-7')
                                    
                                    # Контейнер для результатов поиска
                                    document_results_container_review = ui.column().classes('w-full max-h-64 overflow-y-auto border rounded p-2 bg-white')
                                
                                # Скрытые переменные для document_id и document_name (не показываем пользователю)
                                document_id_input = ui.input(value='').classes('hidden')
                                document_name_input = ui.input(value='').classes('hidden')
                                # Сохраняем ссылки
                                document_form_elements['document_id_input'] = document_id_input
                                document_form_elements['document_name_input'] = document_name_input
                                
                                # ===== ВОССТАНАВЛИВАЕМ ЗНАЧЕНИЯ =====
                                if saved_document_id:
                                    document_id_input.value = saved_document_id
                                    document_id_input.update()
                                if saved_document_name:
                                    document_name_input.value = saved_document_name
                                    document_name_input.update()
                                # ===== КОНЕЦ ВОССТАНОВЛЕНИЯ =====
                                
                                # Определяем функции после объявления всех переменных
                                async def search_and_display_documents_for_review(query: str = ''):
                                    """Ищет и отображает документы из Mayan EDMS для выбора"""
                                    try:
                                        # Если query не передан, берем из поля ввода
                                        if not query and hasattr(document_search_input_review, 'value'):
                                            query = document_search_input_review.value or ''
                                        
                                        document_results_container_review.clear()
                                        
                                        # Показываем индикатор загрузки
                                        with document_results_container_review:
                                            ui.label('Поиск документов...').classes('text-sm text-gray-600 text-center py-4')
                                                                                
                                        # Получаем клиент Mayan EDMS используя сохраненного пользователя
                                        try:
                                            # Проверяем наличие API токена у пользователя
                                            if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
                                                raise ValueError(f'У пользователя {current_user.username} нет API токена для доступа к Mayan EDMS')
                                            
                                            # Создаем клиент напрямую с токеном пользователя
                                            mayan_client = MayanClient(
                                                base_url=config.mayan_url,
                                                api_token=current_user.mayan_api_token
                                            )
                                        except ValueError as auth_error:
                                            logger.error(f"Ошибка авторизации при создании клиента Mayan: {auth_error}")
                                            document_results_container_review.clear()
                                            with document_results_container_review:
                                                ui.label('Ошибка авторизации').classes('text-sm text-red-600 text-center py-2')
                                                ui.label(f'Детали: {str(auth_error)}').classes('text-xs text-gray-500 text-center mt-1')
                                                ui.label('Пожалуйста, обновите страницу и войдите снова').classes('text-xs text-gray-400 text-center mt-2')
                                            return
                                        except Exception as client_error:
                                            logger.error(f"Ошибка при создании клиента Mayan: {client_error}", exc_info=True)
                                            document_results_container_review.clear()
                                            with document_results_container_review:
                                                ui.label('Ошибка подключения').classes('text-sm text-red-600 text-center py-2')
                                                ui.label(f'Детали: {str(client_error)}').classes('text-xs text-gray-500 text-center mt-1')
                                            return
                                        
                                        # Выполняем поиск
                                        query = query.strip() if query else ''
                                        
                                        if query:
                                            logger.info(f"Выполняем поиск документов по запросу: '{query}'")
                                            documents = await mayan_client.search_documents(query, page=1, page_size=20)
                                            logger.info(f"Найдено документов: {len(documents)}")
                                        else:
                                            # Если запрос пустой, показываем последние документы
                                            logger.info("Запрос пустой, показываем последние документы")
                                            try:
                                                documents, total_count = await mayan_client.get_documents(page=1, page_size=20)
                                                logger.info(f"Получено документов: {len(documents)}, всего: {total_count}")
                                            except Exception as get_docs_error:
                                                logger.error(f"Ошибка при получении последних документов: {get_docs_error}", exc_info=True)
                                                documents = []
                                        
                                        # Очищаем контейнер перед показом результатов
                                        document_results_container_review.clear()
                                        
                                        if not documents:
                                            with document_results_container_review:
                                                ui.label('Документы не найдены').classes('text-sm text-gray-500 text-center py-4')
                                                ui.label('У вас нет доступа к документам или документы отсутствуют').classes('text-xs text-gray-400 text-center mt-2')
                                            return
                                        
                                        # Отображаем найденные документы
                                        with document_results_container_review:
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
                                                            on_click=lambda d=doc: select_document_for_review(d)
                                                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                                        
                                    except Exception as e:
                                        logger.error(f"Ошибка при поиске документов: {e}", exc_info=True)
                                        document_results_container_review.clear()
                                        with document_results_container_review:
                                            ui.label('Ошибка при поиске документов').classes('text-sm text-red-600 text-center py-2')
                                            ui.label(f'Детали: {str(e)}').classes('text-xs text-gray-500 text-center mt-1')
                                            ui.label('Проверьте подключение к Mayan EDMS и права доступа').classes('text-xs text-gray-400 text-center mt-2')
                                
                                # Добавляем обработчик Enter для поля поиска (после определения функции)
                                document_search_input_review.on('keydown.enter', lambda: search_and_display_documents_for_review(document_search_input_review.value))
                                
                                def select_document_for_review(doc):
                                    """Выбирает документ и автоматически заполняет поля формы"""
                                    try:
                                        # Заполняем поля формы автоматически
                                        document_id_input.value = str(doc.document_id)
                                        document_name_input.value = doc.label
                                        
                                        # Обновляем метку выбранного документа
                                        selected_doc_label_review.text = f'✓ Выбран: {doc.label} (ID: {doc.document_id})'
                                        selected_doc_label_review.classes('text-sm text-green-600 font-semibold mb-2')
                                        
                                        # Показываем уведомление
                                        ui.notify(f'Выбран документ: {doc.label} (ID: {doc.document_id})', type='positive')
                                        
                                        # Сворачиваем результаты поиска и показываем подтверждение
                                        document_results_container_review.clear()
                                        with document_results_container_review:
                                            with ui.card().classes('p-3 bg-green-50 border-l-4 border-green-500'):
                                                with ui.row().classes('items-center'):
                                                    ui.icon('check_circle').classes('text-green-500 mr-2 text-xl')
                                                    with ui.column().classes('flex-1'):
                                                        ui.label(f'Выбран документ: {doc.label}').classes('text-sm font-semibold')
                                                        ui.label(f'ID: {doc.document_id}').classes('text-xs text-gray-600')
                                                        if hasattr(doc, 'file_latest_filename') and doc.file_latest_filename:
                                                            ui.label(f'Файл: {doc.file_latest_filename}').classes('text-xs text-gray-600')
                                                
                                                # Кнопка для изменения выбора
                                                # Используем прямой вызов через ui.timer для сохранения контекста NiceGUI
                                                def on_select_another_review_click():
                                                    """Обработчик для кнопки выбора другого документа"""
                                                    # Сохраняем значение запроса в переменную
                                                    search_query = document_search_input_review.value
                                                    # Используем ui.timer для вызова асинхронной функции в правильном контексте
                                                    # NiceGUI автоматически обработает асинхронную функцию
                                                    async def timer_callback():
                                                        await search_and_display_documents_for_review(search_query)
                                                    ui.timer(0.1, timer_callback, once=True)
                                                
                                                ui.button(
                                                    'Выбрать другой документ',
                                                    icon='refresh',
                                                    on_click=on_select_another_review_click
                                                ).classes('mt-2 bg-blue-500 text-white text-xs px-2 py-1 h-7')
                                    
                                    except Exception as e:
                                        logger.error(f"Ошибка при выборе документа: {e}", exc_info=True)
                                        ui.notify(f'Ошибка при выборе документа: {str(e)}', type='negative')
                                
                                def reset_search_review():
                                    """Сбрасывает поиск и очищает все поля"""
                                    try:
                                        # Очищаем поле поиска
                                        document_search_input_review.value = ''
                                        
                                        # Очищаем контейнер результатов
                                        document_results_container_review.clear()
                                        
                                        # Сбрасываем выбранный документ
                                        selected_doc_label_review.text = 'Документ не выбран'
                                        selected_doc_label_review.classes('text-sm text-gray-500 mb-2')
                                        
                                        # Очищаем поля документа
                                        document_id_input.value = ''
                                        document_name_input.value = ''
                                        
                                        ui.notify('Поиск сброшен', type='info')
                                    
                                    except Exception as e:
                                        logger.error(f"Ошибка при сбросе поиска: {e}", exc_info=True)
                                        ui.notify(f'Ошибка при сбросе: {str(e)}', type='negative')
                                
                                # Обновляем обработчики кнопок
                                search_btn_review.on_click(lambda: search_and_display_documents_for_review(document_search_input_review.value))
                                
                                # Для кнопки "Показать последние" передаем пустой запрос явно
                                refresh_btn_review.on_click(lambda: search_and_display_documents_for_review(''))
                                
                                reset_btn_review.on_click(lambda: reset_search_review())
                            
                            else:
                                # Если это не процесс подписания или ознакомления, создаем пустые значения
                                document_id_input = None
                                document_name_input = None
                                roles_select = None
                        
                        # Инициализируем category_input и tags_input как None (поля закомментированы)
                        category_input = None
                        tags_input = None
                        
                        # Кнопка запуска процесса
                        with ui.row().classes('w-full justify-center mt-4'):
                            start_button = ui.button(
                                'Запустить процесс',
                                on_click=lambda: start_process_with_form(
                                    task_name_input.value,
                                    task_description_input.value,
                                    priority_select.value,
                                    due_date_input.value,
                                    category_input.value if category_input else '',
                                    tags_input.value if tags_input else '',
                                    start_button,
                                    document_form_elements['document_id_input'].value if document_form_elements['document_id_input'] else '',
                                    document_form_elements['document_name_input'].value if document_form_elements['document_name_input'] else '',
                                    # Используем роли из выбранных вверху, если они есть, иначе из select
                                    selected_roles_from_selection if selected_roles_from_selection else (roles_select.value if roles_select else [])
                                ),
                                icon='play_arrow'
                            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                
                # Функция для запуска процесса с параметрами из формы
                async def start_process_with_form(task_name, task_description, priority, due_date, category, tags, start_button, document_id='', document_name='', selected_roles=None):
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
                            ui.notify('Срок исполнения обязателен для заполнения', type='warning')
                            return
                        
                        try:
                            due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                            # Проверяем, что дата не в прошлом
                            if due_date_obj.date() < datetime.now().date():
                                ui.notify('Срок исполнения не может быть в прошлом', type='warning')
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
                        if process_key == 'DocumentReviewProcessMultiInstance' or (process_key and 'DocumentReviewProcess' in process_key):
                            # Проверяем наличие document_id
                            if not document_id or not document_id.strip():
                                ui.notify('ID документа обязателен для процесса ознакомления!', type='error')
                                return
                            
                            # Получаем информацию о документе из Mayan EDMS
                            try:
                                mayan_client = await MayanClient.create_with_session_user()
                                document_info = await mayan_client.get_document_info_for_review(document_id.strip())
                                
                                if not document_info:
                                    ui.notify('Ошибка при получении информации о документе', type='error')
                                    return
                                
                                document_name_for_review = document_info.get("label", document_name.strip() if document_name else task_name.strip())
                                document_content = document_info.get("content", task_description.strip() if task_description else "Содержимое недоступно")
                                
                            except Exception as e:
                                logger.error(f"Ошибка при получении информации о документе: {e}", exc_info=True)
                                ui.notify(f'Ошибка при получении информации о документе: {str(e)}', type='error')
                                return
                            
                            # Валидация ролей (может быть пустым списком, но должно быть списком)
                            if selected_roles is None:
                                selected_roles = []
                            
                            # Преобразуем в список, если это не список
                            if isinstance(selected_roles, str):
                                selected_roles = [selected_roles] if selected_roles else []
                            
                            process_id = await camunda_client.start_document_review_process_multi_instance(
                                document_id=document_id.strip(),
                                document_name=document_name_for_review,
                                document_content=document_content,
                                assignee_list=assignee_list,
                                business_key=f"batch_{int(time.time())}",
                                creator_username=creator_username,
                                due_date=due_date_str,
                                role_names=selected_roles,
                                process_definition_key=process_key  # Передаем реальный ключ процесса из выбранного шаблона
                            )
                        elif process_key == 'DocumentSigningProcess' or (process_key and 'DocumentSigningProcess' in process_key):
                            # Специальная обработка для процесса подписания документов
                            # Используем специальные поля для подписания документов
                            if not document_id or not document_id.strip():
                                ui.notify('ID документа обязателен для процесса подписания!', type='error')
                                return
                            
                            # ===== ИСПРАВЛЕНИЕ: Получаем document_name из Mayan, если он не указан =====
                            final_document_name = document_name.strip() if document_name and document_name.strip() else None
                            
                            # Если document_name не указан, получаем его из Mayan по document_id
                            if not final_document_name and document_id.strip():
                                try:
                                    mayan_client = await MayanClient.create_with_session_user()
                                    document_info = await mayan_client.get_document_info_for_review(document_id.strip())
                                    if document_info:
                                        final_document_name = document_info.get('label', '')
                                        # Обновляем также поле в форме для будущего использования
                                        if document_form_elements['document_name_input']:
                                            document_form_elements['document_name_input'].value = final_document_name
                                            document_form_elements['document_name_input'].update()
                                except Exception as e:
                                    logger.warning(f"Не удалось получить название документа {document_id}: {e}")
                            
                            if not final_document_name or not final_document_name.strip():
                                ui.notify('Название документа обязательно для процесса подписания!', type='error')
                                return
                            # ===== КОНЕЦ ИСПРАВЛЕНИЯ =====
                            
                            # Проверяем, что document_id является числовым
                            if not document_id.strip().isdigit():
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
                                document_name=final_document_name.strip(),  # Используем final_document_name
                                signer_list=assignee_list,
                                role_names=selected_roles,
                                business_key=f"signing_{int(time.time())}",
                                creator_username=creator_username,
                                due_date=due_date_str,
                                task_name=task_name.strip(),
                                task_description=task_description.strip()
                            )
                        else:
                            # Для других процессов используем универсальный метод
                            # Получаем текущего пользователя для передачи creator_username
                            
                            current_user = get_current_user()
                            creator_username = current_user.username if current_user else None
                            
                            # Преобразуем process_variables в правильный формат для start_process
                            variables_dict = {}
                            for key, var_data in process_variables.items():
                                if isinstance(var_data, dict) and 'value' in var_data:
                                    variables_dict[key] = var_data['value']
                                else:
                                    variables_dict[key] = var_data
                            
                            process_id = await camunda_client.start_process(
                                process_definition_key=process_key,
                                variables=variables_dict,
                                business_key=f"batch_{int(time.time())}"
                            )
                        
                        print(f"Результат запуска процесса: {process_id}")
                        
                        if process_id:
                            ui.notify(f'Процесс {process_key} успешно запущен (ID: {process_id}) для {len(assignee_list)} пользователей', type='positive')
                            
                            # Очищаем выбор и форму
                            clear_selection()
                            process_template_select.value = None
                            # Очищаем поля названия и описания задачи
                            task_name_input.value = 'Новая задача'
                            task_description_input.value = ''
                            process_form_container.set_visibility(False)
                            process_form_container.clear()
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

                # Добавляем CSS переменную для высоты таблиц
                ui.add_head_html('''
                    <style>
                        :root {
                            --left-table-height: 356px;
                            --role-select-height: 56px;
                            --right-table-height: calc(var(--left-table-height) - var(--role-select-height));
                        }
                    </style>
                ''')

                # Добавляем функцию автоматического заполнения
                async def auto_fill_document_from_url():
                    """Автоматически заполняет документ из URL параметров"""
                    if not pending_document_id:
                        return
                    
                    try:
                        mayan_client = await MayanClient.create_with_session_user()
                        document_info = await mayan_client.get_document_info_for_review(pending_document_id)
                        
                        if not document_info:
                            ui.notify('Документ не найден', type='warning')
                            return
                        
                        # ===== ДОБАВИТЬ: Сохраняем document_name для использования при пересоздании формы =====
                        # Используем nonlocal или глобальную переменную для сохранения
                        # Но лучше использовать pending_document_name, который будет использоваться при сохранении
                        document_name_from_info = document_info.get('label', '')
                        # ===== КОНЕЦ ДОБАВЛЕНИЯ =====
                        
                        # Сохраняем для использования при пересоздании формы
                        pending_document_name = document_name_from_info
                        
                        # Сначала выбираем шаблон процесса, чтобы создать форму
                        if pending_process_type == 'review':
                            # Ищем шаблон для ознакомления
                            found_template = False
                            for key, name in process_template_select.options.items():
                                if 'DocumentReviewProcess' in key or 'Ознаком' in name:
                                    process_template_select.value = key
                                    process_template_select.update()
                                    found_template = True
                                    # Вызываем обработчик изменения шаблона, чтобы создать форму
                                    await handle_template_change()
                                    # Ждем, чтобы форма успела создаться
                                    await asyncio.sleep(0.5)
                                    break
                            
                            if not found_template:
                                ui.notify('Шаблон процесса ознакомления не найден', type='warning')
                                return
                                
                        elif pending_process_type == 'signing':
                            # Ищем шаблон для подписания
                            found_template = False
                            for key, name in process_template_select.options.items():
                                if 'DocumentSigningProcess' in key or 'Подписан' in name:
                                    process_template_select.value = key
                                    process_template_select.update()
                                    found_template = True
                                    # Вызываем обработчик изменения шаблона, чтобы создать форму
                                    await handle_template_change()
                                    # Ждем, чтобы форма успела создаться
                                    await asyncio.sleep(0.5)
                                    break
                            
                            if not found_template:
                                ui.notify('Шаблон процесса подписания не найден', type='warning')
                                return
                        
                        # Теперь заполняем поля документа (форма уже должна быть создана)
                        if document_form_elements['document_id_input']:
                            document_form_elements['document_id_input'].value = pending_document_id
                            document_form_elements['document_id_input'].update()
                        
                        if document_form_elements['document_name_input']:
                            document_form_elements['document_name_input'].value = document_name_from_info
                            document_form_elements['document_name_input'].update()
                        
                        # Обновляем label выбранного документа
                        if pending_process_type == 'review' and document_form_elements['selected_doc_label_review']:
                            document_form_elements['selected_doc_label_review'].text = f'✓ Выбран: {document_info.get("label")} (ID: {pending_document_id})'
                            document_form_elements['selected_doc_label_review'].classes('text-sm text-green-600 font-semibold mb-2')
                            document_form_elements['selected_doc_label_review'].update()
                        elif pending_process_type == 'signing' and document_form_elements['selected_doc_label']:
                            document_form_elements['selected_doc_label'].text = f'✓ Выбран: {document_info.get("label")} (ID: {pending_document_id})'
                            document_form_elements['selected_doc_label'].classes('text-sm text-green-600 font-semibold mb-2')
                            document_form_elements['selected_doc_label'].update()
                        
                        ui.notify(f'Документ "{document_info.get("label")}" выбран автоматически', type='success')
                        
                    except Exception as e:
                        logger.error(f"Ошибка при автоматическом заполнении: {e}", exc_info=True)
                        ui.notify(f'Ошибка при автоматическом заполнении: {str(e)}', type='error')

