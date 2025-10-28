import theme
from message import message
from nicegui import ui, events
from ldap_users import get_users, get_groups, users_filter
from services.camunda_connector import CamundaClient
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
                message('Выбор пользователей и назначение им задач')
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
                }).classes('w-4/5').on('cellDoubleClicked', on_row_dblclick)
               
                user_count_label = ui.label(f'Найдено пользователей: {len(all_users)}')
               
                # Создаем контейнер для выбранных пользователей
                with ui.column().classes('w-full mt-4'):
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
                }).classes('w-4/5')
                
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
                def load_process_templates():
                    if not camunda_client:
                        ui.notify('Camunda клиент не инициализирован', type='negative')
                        return
                        
                    print("Начинаем загрузку шаблонов процессов...")
                    try:
                        process_definitions = camunda_client.get_active_process_definitions()
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
                def open_process_form():
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
                                ui.label('Параметры подписания:').classes('font-bold mb-2')
                                
                                document_id_input = ui.input(
                                    label='ID документа в Mayan EDMS',
                                    placeholder='Введите ID документа',
                                    value=''
                                ).classes('w-full mb-2')
                                
                                document_name_input = ui.input(
                                    label='Название документа',
                                    placeholder='Введите название документа',
                                    value=''
                                ).classes('w-full mb-2')
                                
                                # Обновляем значения при изменении
                                # task_name_input.on('change', lambda e: document_id_input.set_value(e.args))
                                # task_description_input.on('change', lambda e: document_name_input.set_value(e.args))
                            else:
                                # Если это не процесс подписания, создаем пустые значения
                                document_id_input = None
                                document_name_input = None
                        
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
                            ui.button('Отмена', on_click=dialog.close).classes('mr-2')
                            
                        # Кнопка запуска с индикатором загрузки
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
                                document_name_input.value if document_name_input else ''
                            ),
                            icon='play_arrow'
                        ).classes('bg-green-500 text-white')
                    
                    dialog.open()
                
                # Функция для запуска процесса с параметрами из формы
                async def start_process_with_form(dialog, task_name, task_description, priority, due_date, category, tags, start_button, document_id='', document_name=''):
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
                        
                        # Выбираем метод запуска в зависимости от типа процесса
                        process_id = None
                        if process_key == 'DocumentReviewProcessMultiInstance':
                            process_id = camunda_client.start_document_review_process_multi_instance(
                                document_name=task_name.strip(),
                                document_content=task_description.strip(),
                                assignee_list=assignee_list,
                                business_key=f"batch_{int(time.time())}"
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
                            
                            process_id = camunda_client.start_document_signing_process(
                                document_id=document_id.strip(),  # Используем специальное поле для ID документа
                                document_name=document_name.strip(),  # Используем специальное поле для названия документа
                                signer_list=assignee_list,
                                business_key=f"signing_{int(time.time())}"
                            )
                        else:
                            # Для других процессов используем универсальный метод
                            process_id = camunda_client.start_process(
                                process_definition_key=process_key,
                                assignee_list=assignee_list,
                                additional_variables=process_variables,
                                business_key=f"batch_{int(time.time())}"
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