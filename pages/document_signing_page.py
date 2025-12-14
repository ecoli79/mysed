from nicegui import ui
from services.signature_manager import SignatureManager
from services.mayan_connector import MayanClient
from auth.middleware import get_current_user
from datetime import datetime
import json
from app_logging.logger import get_logger

logger = get_logger(__name__)

def get_mayan_client() -> MayanClient:
    return MayanClient.create_with_session_user()

def content() -> None:
    """Основная страница подписания документов"""
    ui.label('Подписание документов').classes('text-2xl font-bold mb-6')
    
    ui.label('Для инициации процесса подписания документов используйте модуль назначения задач.').classes('text-lg mb-4')
    
    # Кнопка для перехода к назначению задач
    ui.button(
        'Перейти к назначению задач',
        icon='assignment',
        on_click=lambda: ui.navigate.to('/task-assignment')
    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
    
    ui.label('Инструкция:').classes('text-lg font-semibold mt-6 mb-2')
    ui.label('1. Выберите пользователей, которые должны подписать документ').classes('text-sm mb-1')
    ui.label('2. Выберите шаблон "Подписание документа"').classes('text-sm mb-1')
    ui.label('3. Заполните ID документа и название документа').classes('text-sm mb-1')
    ui.label('4. Запустите процесс').classes('text-sm mb-1')

def create_signing_tasks_section():
    """Создает секцию с задачами подписания"""
    ui.label('Мои задачи подписания').classes('text-lg font-semibold mb-4')
    
    # Контейнер для задач
    tasks_container = ui.column().classes('w-full')
    
    # Загружаем задачи
    load_signing_tasks(tasks_container)

def load_signing_tasks(container: ui.column):
    """Загружает задачи подписания для текущего пользователя"""
    try:
        user = get_current_user()
        signature_manager = SignatureManager()
        
        # Очищаем контейнер
        container.clear()
        
        # Получаем задачи подписания
        signing_tasks = signature_manager.get_signing_tasks_for_user(user.username)
        
        if not signing_tasks:
            ui.label('У вас нет активных задач подписания').classes('text-gray-600')
            return
        
        # Отображаем задачи
        for task in signing_tasks:
            with ui.card().classes('w-full mb-4 p-4'):
                ui.label(f'Документ: {task["document_name"]}').classes('text-lg font-semibold')
                ui.label(f'ID задачи: {task["task_id"]}').classes('text-sm text-gray-600')
                ui.label(f'Дата создания: {task["created"]}').classes('text-sm text-gray-600')
                
                # Кнопка для подписания
                ui.button(
                    'Подписать документ',
                    icon='edit',
                    on_click=lambda t=task: open_signing_dialog(t)
                ).classes('bg-blue-500 text-white mt-2 text-xs px-2 py-1 h-7')
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке задач подписания: {e}")
        ui.label(f'Ошибка при загрузке задач: {str(e)}').classes('text-red-600')

def open_signing_dialog(task):
    """Открывает диалог подписания документа"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
        ui.label('Подписание документа').classes('text-xl font-semibold mb-4')
        
        # Информация о задаче
        with ui.card().classes('p-4 bg-gray-50 mb-4'):
            ui.label(f'Документ: {task["document_name"]}').classes('text-lg font-semibold')
            ui.label(f'ID задачи: {task["task_id"]}').classes('text-sm text-gray-600')
        
        # Область для отображения документа
        ui.label('Содержимое документа:').classes('text-sm font-medium mb-2')
        document_content = ui.html('').classes('w-full h-96 border rounded p-4 bg-white')
        
        # Загружаем содержимое документа
        load_document_content(task["document_id"], document_content)
        
        # Область для подписи
        ui.label('Электронная подпись:').classes('text-sm font-medium mb-2 mt-4')
        
        # Информация о сертификате
        certificate_info = ui.html('').classes('w-full border rounded p-4 bg-gray-50 mb-4')
        
        # Кнопки действий
        with ui.row().classes('w-full justify-between mt-4'):
            ui.button(
                'Отмена',
                on_click=dialog.close
            ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
            
            ui.button(
                'Подписать документ',
                icon='edit',
                on_click=lambda: sign_document(task, dialog)
            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
    
    dialog.open()

def load_document_content(document_id: str, content_container: ui.html):
    """Загружает содержимое документа"""
    try:
        mayan_client = get_mayan_client()
        document_info = mayan_client.get_document_info_for_review(document_id)
        
        if document_info and 'content' in document_info:
            # Отображаем содержимое документа
            content_html = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h3>{document_info['label']}</h3>
                <div style="white-space: pre-wrap; background: white; padding: 20px; border: 1px solid #ddd; border-radius: 4px;">
                    {document_info['content']}
                </div>
            </div>
            """
            content_container.set_content(content_html)
        else:
            content_container.set_content('<p>Содержимое документа недоступно</p>')
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке содержимого документа {document_id}: {e}")
        content_container.set_content(f'<p>Ошибка при загрузке документа: {str(e)}</p>')

def sign_document(task, dialog):
    """Выполняет подписание документа"""
    try:
        # Получаем информацию о задаче из Camunda
        from services.camunda_connector import get_camunda_client
        camunda_client = get_camunda_client()
        
        # Получаем переменные процесса для получения document_id
        process_variables = camunda_client.get_process_instance_variables(task["process_instance_id"])
        document_id = process_variables.get('documentId') or task.get("document_id")
        
        if not document_id:
            ui.notify('Не удалось получить ID документа', type='error')
            return
        
        # Используем существующую логику из task_completion_page
        # Или реализуем упрощенную версию подписания
        from pages.task_completion_page import complete_signing_task
        
        # Создаем объект задачи для передачи
        from models import CamundaTask
        camunda_task = CamundaTask(
            id=task["task_id"],
            name=task.get("name", "Подписать документ"),
            assignee=get_current_user().username,
            process_instance_id=task.get("process_instance_id"),
            # ... другие поля
        )
        
        complete_signing_task(camunda_task)
        dialog.close()
        
    except Exception as e:
        logger.error(f"Ошибка при подписании документа: {e}")
        ui.notify(f'Ошибка: {str(e)}', type='error')

def sign_document_with_certificate(task, certificate_index, dialog):
    """Выполняет подписание документа с выбранным сертификатом"""
    try:
        # Получаем данные документа для подписания
        mayan_client = get_mayan_client()
        document_info = mayan_client.get_document_info_for_review(task["document_id"])
        
        if not document_info or 'content' not in document_info:
            ui.notify('Содержимое документа недоступно', type='error')
            return
        
        # Конвертируем содержимое в base64
        import base64
        document_content = document_info['content']
        if isinstance(document_content, str):
            document_content = document_content.encode('utf-8')
        
        data_to_sign = base64.b64encode(document_content).decode('utf-8')
        
        # JavaScript для подписания документа
        sign_script = f"""
        async function signDocument() {{
            try {{
                console.log('Начинаем подписание документа...');
                
                const dataToSign = '{data_to_sign}';
                const certificateIndex = {certificate_index};
                
                const result = await window.cryptoProIntegration.signData(dataToSign, certificateIndex);
                
                console.log('Подписание завершено:', result);
                
                // Отправляем результат на сервер
                window.nicegui_handle_event('signature_completed', {{
                    task_id: '{task["task_id"]}',
                    signature_data: result.signature,
                    certificate_info: result.certificateInfo
                }});
                
            }} catch (error) {{
                console.error('Ошибка при подписании:', error);
                window.nicegui_handle_event('signature_error', {{
                    error: error.message
                }});
            }}
        }}
        
        signDocument();
        """
        
        # Выполняем подписание
        ui.run_javascript(sign_script)
        
    except Exception as e:
        logger.error(f"Ошибка при подписании документа: {e}")
        ui.notify(f'Ошибка: {str(e)}', type='error')

def show_certificate_selection_dialog(task, parent_dialog):
    """Показывает диалог выбора сертификата"""
    with ui.dialog() as cert_dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label('Выбор сертификата для подписания').classes('text-xl font-semibold mb-4')
        
        # Контейнер для сертификатов
        cert_container = ui.column().classes('w-full')
        
        # Кнопка загрузки сертификатов
        ui.button(
            'Загрузить доступные сертификаты',
            icon='refresh',
            on_click=lambda: load_certificates(cert_container, task, cert_dialog, parent_dialog)
        ).classes('bg-blue-500 text-white mb-4 text-xs px-2 py-1 h-7')
        
        # Кнопка отмены
        ui.button(
            'Отмена',
            on_click=cert_dialog.close
        ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
    
    cert_dialog.open()

# Обновленная функция в pages/document_signing_page.py
def load_certificates(container, task, cert_dialog, parent_dialog):
    """Загружает и отображает доступные сертификаты"""
    try:
        # Очищаем контейнер
        container.clear()
        
        # Показываем индикатор загрузки
        loading_spinner = ui.spinner('Загрузка сертификатов...').classes('mx-auto')
        
        # JavaScript для загрузки сертификатов (адаптированный из рабочего примера)
        load_certs_script = """
        async function loadCertificates() {
            try {
                console.log('Начинаем загрузку сертификатов...');
                
                // Проверяем наличие cadesplugin
                if (typeof window.cadesplugin === 'undefined' || !window.cadesplugin) {
                    window.nicegui_handle_event('certificates_error', {
                        error: 'КриптоПро плагин не найден. Убедитесь, что скрипт cadesplugin_api.js загружен.'
                    });
                    return;
                }
                
                // Проверяем, что cryptoProIntegration инициализирован
                if (!window.cryptoProIntegration) {
                    window.nicegui_handle_event('certificates_error', {
                        error: 'КриптоПро интеграция не инициализирована. Перезагрузите страницу.'
                    });
                    return;
                }
                
                // Пробуем загрузить сертификаты
                // getAvailableCertificates сама проверит доступность плагина
                const certificates = await window.cryptoProIntegration.getAvailableCertificates();
                console.log('Получены сертификаты:', certificates);
                
                if (certificates.length === 0) {
                    window.nicegui_handle_event('no_certificates', {
                        message: 'Не найдено доступных сертификатов для подписи'
                    });
                    return;
                }
                
                // Отправляем сертификаты в NiceGUI
                window.nicegui_handle_event('certificates_loaded', {
                    certificates: certificates
                });
                
            } catch (error) {
                console.error('Ошибка при загрузке сертификатов:', error);
                window.nicegui_handle_event('certificates_error', {
                    error: error.message || String(error)
                });
            }
        }
        
        loadCertificates();
        """
        
        # Выполняем загрузку сертификатов
        ui.run_javascript(load_certs_script)
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке сертификатов: {e}")
        ui.notify(f'Ошибка при загрузке сертификатов: {str(e)}', type='error')

# Обработчики событий JavaScript
def handle_certificates_loaded(certificates):
    """Обрабатывает загруженные сертификаты"""
    try:
        logger.info(f"Получено сертификатов: {len(certificates)}")
        
        # Здесь нужно получить ссылку на контейнер и диалоги
        # Это требует рефакторинга для передачи контекста
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сертификатов: {e}")

def handle_certificates_error(error):
    """Обрабатывает ошибки загрузки сертификатов"""
    logger.error(f"Ошибка загрузки сертификатов: {error}")
    ui.notify(f'Ошибка загрузки сертификатов: {error}', type='error')

def handle_no_certificates(message):
    """Обрабатывает отсутствие сертификатов"""
    logger.warning(message)
    ui.notify(message, type='warning')

def handle_plugin_not_available(message):
    """Обрабатывает недоступность плагина"""
    logger.warning(message)
    ui.notify(message, type='warning')

def create_initiate_signing_section():
    """Создает секцию для инициации подписания"""
    ui.label('Инициировать подписание документа').classes('text-lg font-semibold mb-4')
    
    # Выбор документа
    ui.label('Выберите документ для подписания:').classes('text-sm font-medium mb-2')
    document_select = ui.select(
        options={},
        label='Документ'
    ).classes('w-full mb-4')
    
    # Список подписантов
    ui.label('Пользователи для подписания (через запятую):').classes('text-sm font-medium mb-2')
    signers_input = ui.input(
        label='Список пользователей',
        placeholder='user1, user2, user3'
    ).classes('w-full mb-4')
    
    # Комментарий
    comment_input = ui.textarea(
        label='Комментарий к процессу подписания',
        placeholder='Введите комментарий...'
    ).classes('w-full mb-4')
    
    # Кнопка запуска
    ui.button(
        'Запустить процесс подписания',
        icon='play_arrow',
        on_click=lambda: start_signing_process(document_select.value, signers_input.value, comment_input.value)
    ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
    
    # Загружаем доступные документы
    load_available_documents(document_select)

def load_available_documents(select_widget: ui.select):
    """Загружает доступные документы"""
    try:
        mayan_client = get_mayan_client()
        documents = mayan_client.get_documents(page=1, page_size=100)
        
        options = {}
        for doc in documents:
            options[doc.document_id] = doc.label
        
        select_widget.options = options
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке документов: {e}")
        ui.notify(f'Ошибка при загрузке документов: {str(e)}', type='error')

def start_signing_process(document_id: str, signers: str, comment: str):
    """Запускает процесс подписания"""
    if not document_id:
        ui.notify('Выберите документ', type='error')
        return
    
    if not signers:
        ui.notify('Введите список пользователей для подписания', type='error')
        return
    
    try:
        # Получаем текущего пользователя для передачи creator_username
        user = get_current_user()
        creator_username = user.username if user else None
        
        # Получаем информацию о документе
        mayan_client = get_mayan_client()
        document_info = mayan_client.get_document_info_for_review(document_id)
        if not document_info:
            ui.notify('Ошибка при получении информации о документе', type='error')
            return
        
        # Парсим список пользователей
        signer_list = [user.strip() for user in signers.split(',') if user.strip()]
        
        # Запускаем процесс подписания
        from services.camunda_connector import get_camunda_client
        camunda_client = get_camunda_client()
        
        process_id = camunda_client.start_document_signing_process(
            document_id=document_id,
            document_name=document_info["label"],
            signer_list=signer_list,
            business_key=None,
            role_names=None,
            creator_username=creator_username
        )
        
        if process_id:
            ui.notify(f'Процесс подписания запущен! ID процесса: {process_id}', type='success')
        else:
            ui.notify('Ошибка при запуске процесса подписания', type='error')
    
    except Exception as e:
        logger.error(f"Ошибка при запуске процесса подписания: {e}")
        ui.notify(f'Ошибка: {str(e)}', type='error')

def create_signing_progress_section():
    """Создает секцию для отслеживания прогресса подписания"""
    ui.label('Прогресс процессов подписания').classes('text-lg font-semibold mb-4')
    
    # Здесь можно добавить отслеживание активных процессов подписания
    ui.label('Функция отслеживания прогресса будет реализована в следующих версиях').classes('text-gray-600')