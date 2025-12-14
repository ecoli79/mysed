from message import message
from nicegui import ui
from models import Task
from services.camunda_connector import create_camunda_client
import theme
import tempfile
import os
from nicegui import app, ui
from datetime import datetime
import requests
from urllib.parse import urljoin
import re
import xml.etree.ElementTree as ET
from app_logging.logger import get_logger

logger = get_logger(__name__)

from config.settings import config


def content() -> None:
    message('Мои задачи').classes('font-bold')
    process_templates_page()


def process_templates_page():
    """Страница работы с шаблонами процессов"""
    with theme.frame('- Шаблоны процессов -'):
        ui.label('Управление шаблонами процессов Camunda').classes('text-2xl font-bold mb-6')
        
        # Кнопка тестирования подключения
        with ui.row().classes('mb-4'):
            ui.button(
                'Тест подключения',
                icon='wifi',
                on_click=test_camunda_connection
            ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
            
            ui.button(
                'Обновить статус',
                icon='refresh',
                on_click=update_connection_status
            ).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
        
        # Создаем вкладки
        with ui.tabs().classes('w-full') as tabs:
            deploy_tab = ui.tab('Развертывание BPMN процессов', icon='cloud_upload')
            manage_tab = ui.tab('Управление процессами', icon='settings')
            templates_tab = ui.tab('Шаблоны процессов', icon='description')
        
        # Создаем панели вкладок
        with ui.tab_panels(tabs, value=deploy_tab).classes('w-full'):
            with ui.tab_panel(deploy_tab):
                create_deploy_section()
            
            with ui.tab_panel(manage_tab):
                create_manage_section()
            
            with ui.tab_panel(templates_tab):
                create_templates_section()

def test_camunda_connection():
    """Тестирует подключение к Camunda"""
    try:
        # Получаем клиент Camunda
        camunda_client = create_camunda_client()
        
        # Простой запрос для проверки подключения
        response = camunda_client._make_request('GET', 'version')
        
        if response.status_code == 200:
            version_info = response.json()
            ui.notify(f'Подключение успешно! Версия Camunda: {version_info.get("version", "неизвестна")}', type='success')
        else:
            ui.notify(f'Ошибка подключения: {response.status_code}', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка подключения: {str(e)}', type='error')
        logger.error(f"Ошибка при тестировании подключения к Camunda: {e}", exc_info=True)

def update_connection_status():
    """Обновляет статус подключения"""
    # Эта функция может быть расширена для отображения детального статуса
    test_camunda_connection()

def deploy_click(uploaded_file, deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container):
    """Обработчик кнопки развертывания"""
    # Проверяем, есть ли загруженный файл
    if not uploaded_file['file']:
        ui.notify('Выберите BPMN файл', type='error')
        return
    
    deploy_process_from_upload(
        deployment_name,
        enable_duplicate_filtering,
        deploy_changed_only,
        tenant_id,
        results_container,
        uploaded_file
    )

def create_deploy_section():
    """Создает секцию развертывания процессов"""
    ui.label('Развертывание BPMN процессов').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        with ui.column().classes('w-full'):
            # Поля для настройки развертывания
            deployment_name = ui.input(
                'Имя развертывания',
                placeholder='Введите имя развертывания'
            ).classes('w-full mb-2')
            
            enable_duplicate_filtering = ui.checkbox('Включить фильтрацию дубликатов').classes('mb-2')
            deploy_changed_only = ui.checkbox('Развертывать только измененные').classes('mb-2')
            
            tenant_id = ui.input(
                'ID арендатора (опционально)',
                placeholder='Оставьте пустым для развертывания без арендатора'
            ).classes('w-full mb-4')
            
            uploaded_file = {'file': None}
            
            # Загрузка файла
            upload_area = ui.upload(
                on_upload=lambda e: handle_bpmn_upload(
                    e,
                    deployment_name,
                    enable_duplicate_filtering,
                    deploy_changed_only,
                    tenant_id,
                    results_container,
                    uploaded_file
                ),
                on_rejected=lambda e: ui.notify(f'Файл отклонён: {e}', type='error'),
                auto_upload=False,
                multiple=False,
                max_file_size=10 * 1024 * 1024
            ).props('accept=".bpmn,.xml"').classes('w-full mb-4')
            
            # Контейнер для результатов
            results_container = ui.column().classes('w-full')
            
            # Кнопка развертывания
            ui.button(
                'Развернуть процесс',
                icon='cloud_upload',
                on_click=lambda: deploy_click(uploaded_file, deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container)
            ).props('type=button').classes('w-full bg-green-500 text-white text-xs px-2 py-1 h-7')

def handle_bpmn_upload(e, deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container, uploaded_file):
    """Обрабатывает загрузку BPMN файла"""
    if not deployment_name.value:
        ui.notify('Введите имя развертывания', type='error')
        return

    # Читаем содержимое СРАЗУ и сохраняем
    content = e.content.read()
    
    # Проверяем и исправляем кодировку файла
    try:
        # Пытаемся декодировать как UTF-8
        content_str = content.decode('utf-8')
        # Перекодируем обратно в UTF-8 для обеспечения правильной кодировки
        content = content_str.encode('utf-8')
    except UnicodeDecodeError:
        try:
            # Пытаемся декодировать как Windows-1251
            content_str = content.decode('windows-1251')
            content = content_str.encode('utf-8')
            ui.notify('Файл перекодирован из Windows-1251 в UTF-8', type='info')
        except UnicodeDecodeError:
            ui.notify('Не удалось определить кодировку файла', type='error')
            return
    
    # Проверяем, что это валидный BPMN файл
    if not is_valid_bpmn(content):
        ui.notify('Файл не является валидным BPMN файлом', type='error')
        return
    
    # Сохраняем имя и байты
    uploaded_file['file'] = {
        'name': e.name,
        'content': content
    }

    results_container.clear()
    with results_container:
        ui.label(f'Файл {e.name} загружен успешно!').classes('text-green-600')
        ui.label(f'Размер: {len(content)} байт').classes('text-sm text-gray-600')
        
        # Пытаемся извлечь название процесса
        process_name = extract_process_name(content)
        if process_name:
            ui.label(f'Название процесса: {process_name}').classes('text-sm text-blue-600')

def is_valid_bpmn(content):
    """Проверяет, является ли содержимое валидным BPMN файлом"""
    try:
        content_str = content.decode('utf-8')
        return '<definitions' in content_str and '<process' in content_str
    except UnicodeDecodeError:
        return False

def extract_process_name(content):
    """Извлекает название процесса из BPMN файла"""
    try:
        content_str = content.decode('utf-8')
        # Простое извлечение названия процесса
        import re
        match = re.search(r'<process[^>]*name="([^"]*)"', content_str)
        return match.group(1) if match else None
    except:
        return None

def deploy_process_from_upload(deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container, uploaded_file):
    """Развертывает процесс из загруженного файла"""
    if not deployment_name.value:
        ui.notify('Введите имя развертывания', type='error')
        return
    
    if not uploaded_file['file']:
        ui.notify('Нет загруженного файла', type='error')
        return

    # Показываем прогресс
    with results_container:
        progress = ui.linear_progress().classes('w-full mb-2')
        progress.value = 0.1

        tmp_file_path = None  # Инициализируем переменную
        try:
            # Создаём временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bpmn') as tmp_file:
                tmp_file.write(uploaded_file['file']['content'])
                tmp_file_path = tmp_file.name

            progress.value = 0.3
            
            # Развертываем с улучшенной обработкой ошибок
            deployment = deploy_process_improved(
                deployment_name=deployment_name.value,
                bpmn_file_path=tmp_file_path,
                enable_duplicate_filtering=enable_duplicate_filtering.value,
                deploy_changed_only=deploy_changed_only.value,
                tenant_id=tenant_id.value if tenant_id.value else None
            )
            
            progress.value = 0.8

            if deployment:
                progress.value = 1.0
                ui.label('✅ Развертывание успешно!').classes('text-green-600 font-semibold')
                ui.label(f'ID развертывания: {deployment.id}').classes('text-sm text-gray-600')
                ui.label(f'Время развертывания: {deployment.deployment_time}').classes('text-sm text-gray-600')
                
                # Показываем информацию о процессах
                if deployment.process_definitions:
                    ui.label('Развернутые процессы:').classes('text-sm font-medium mt-2')
                    for process in deployment.process_definitions:
                        ui.label(f'  • {process.name} (ID: {process.id})').classes('text-sm text-blue-600')
                        ui.label(f'    Ключ: {process.key}, Версия: {process.version}').classes('text-xs text-gray-600')
                else:
                    ui.label('Процесс успешно развернут!').classes('text-sm text-blue-600 mt-2')
            else:
                ui.label('❌ Ошибка развертывания').classes('text-red-600 font-semibold')
                
        except Exception as e:
            ui.label(f'❌ Ошибка: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при развертывании процесса: {e}", exc_info=True)
        finally:
            # Удаляем временный файл
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении временного файла {tmp_file_path}: {e}")

def deploy_process_improved(deployment_name, bpmn_file_path, enable_duplicate_filtering=False, deploy_changed_only=False, tenant_id=None):
    """
    Улучшенная функция развертывания процесса с правильным форматом multipart/form-data
    """
    endpoint = 'deployment/create'
    
    try:
        # Читаем файл полностью в память
        with open(bpmn_file_path, 'rb') as f:
            file_content = f.read()
        
        # Проверяем, что файл содержит валидный XML
        try:
            content_str = file_content.decode('utf-8')
            logger.info(f"Размер файла: {len(file_content)} байт")
            logger.info(f"Первые 200 символов файла: {content_str[:200]}")
            
            # Убеждаемся, что это валидный BPMN
            if not ('<definitions' in content_str and '<process' in content_str):
                logger.error("Файл не содержит валидный BPMN процесс")
                logger.error(f"Содержимое файла: {content_str[:500]}")
                return None
            
            # Радикальная очистка XML для Camunda 7.24
            import re
            import xml.etree.ElementTree as ET
            
            # Проверяем наличие DOCTYPE перед очисткой
            doctype_found = re.search(r'<!DOCTYPE[^>]*>', content_str, re.IGNORECASE | re.DOTALL)
            if doctype_found:
                logger.warning(f"Найдена DOCTYPE декларация: {doctype_found.group()}")
            else:
                logger.info("DOCTYPE декларация не найдена в файле")
            
            # # Удаляем DOCTYPE если он есть
            # content_str = re.sub(r'<!DOCTYPE[^>]*>', '', content_str, flags=re.IGNORECASE | re.DOTALL)
            
            # # Удаляем xsi:schemaLocation атрибут, который может вызывать проблемы
            # content_str = re.sub(r'\s+xsi:schemaLocation="[^"]*"', '', content_str)
            
            # Перекодируем обратно в байты
            file_content = content_str.encode('utf-8')
            
        except UnicodeDecodeError as e:
            logger.error(f"Ошибка декодирования файла: {e}")
            return None
        
        # Подготавливаем данные для multipart/form-data
        files = {
            'deployment-name': (None, deployment_name),
            'enable-duplicate-filtering': (None, str(enable_duplicate_filtering).lower()),
            'deploy-changed-only': (None, str(deploy_changed_only).lower()),
        }
        
        if tenant_id:
            files['tenant-id'] = (None, tenant_id)
        
        # Добавляем файл
        files['file'] = (os.path.basename(bpmn_file_path), file_content, 'application/xml')
        
        # Выполняем запрос напрямую через session
        camunda_client = create_camunda_client()
        url = urljoin(camunda_client.engine_rest_url, endpoint.lstrip('/'))
        
        logger.info(f"Отправляем запрос на развертывание на URL: {url}")
        logger.info(f"Параметры: deployment-name={deployment_name}, enable-duplicate-filtering={enable_duplicate_filtering}")
        
        response = camunda_client.session.post(url, files=files, verify=False)
        
        logger.info(f"Ответ сервера: {response.status_code}")
        logger.info(f"Заголовки ответа: {dict(response.headers)}")
        
        if response.status_code == 200:
            deployment_data = response.json()
            logger.info(f"Данные развертывания: {deployment_data}")
            
            # Создаем объект развертывания
            from models import CamundaDeployment, CamundaProcessDefinition
            
            # Извлекаем информацию о развернутых процессах
            process_definitions = []
            if 'deployedProcessDefinitions' in deployment_data and deployment_data['deployedProcessDefinitions']:
                for process_data in deployment_data['deployedProcessDefinitions'].values():
                    process_definitions.append(CamundaProcessDefinition(
                        id=process_data['id'],
                        key=process_data['key'],
                        category=process_data.get('category'),
                        description=process_data.get('description'),
                        name=process_data['name'],
                        version=process_data['version'],
                        resource=process_data['resource'],
                        deployment_id=process_data['deploymentId'],
                        diagram=process_data.get('diagram'),
                        suspended=process_data['suspended'],
                        tenant_id=process_data.get('tenantId'),
                        version_tag=process_data.get('versionTag'),
                        history_time_to_live=process_data.get('historyTimeToLive'),
                        startable_in_tasklist=process_data['startableInTasklist']
                    ))
            
            deployment = CamundaDeployment(
                id=deployment_data['id'],
                name=deployment_data['name'],
                deployment_time=deployment_data['deploymentTime'],
                source=deployment_data.get('source'),
                tenant_id=deployment_data.get('tenantId'),
                process_definitions=process_definitions
            )
            
            return deployment
        else:
            logger.error(f"Ошибка развертывания: {response.status_code}")
            logger.error(f"Ответ сервера: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при развертывании процесса: {e}", exc_info=True)
        return None

def load_process_definitions(processes_container):
    """Загружает список определений процессов"""
    processes_container.clear()
    
    with processes_container:
        ui.label('Загрузка процессов...').classes('text-gray-600')
        
        try:
            camunda_client = create_camunda_client()
            processes = camunda_client.get_active_process_definitions()
            
            if not processes:
                ui.label('Нет активных процессов').classes('text-gray-500')
                return
            
            ui.label(f'Найдено {len(processes)} процессов:').classes('text-lg font-semibold mb-4')
            
            for process in processes:
                with ui.card().classes('mb-3 p-4 border-l-4 border-blue-500'):
                    with ui.row().classes('items-start justify-between w-full'):
                        with ui.column().classes('flex-1'):
                            ui.label(f'{process.name}').classes('text-lg font-semibold')
                            ui.label(f'ID: {process.id}').classes('text-sm text-gray-600')
                            ui.label(f'Версия: {process.version}').classes('text-sm text-gray-600')
                            ui.label(f'Ключ: {process.key}').classes('text-sm text-gray-600')
                            
                            if process.description:
                                ui.label(f'Описание: {process.description}').classes('text-sm text-gray-600')
                        
                        with ui.column().classes('items-end'):
                            ui.label(f'Развертывание ID: {process.deployment_id}').classes('text-xs text-gray-500')
                            if process.tenant_id:
                                ui.label(f'Арендатор: {process.tenant_id}').classes('text-xs text-gray-500')
                            
        except Exception as e:
            ui.label(f'Ошибка загрузки: {str(e)}').classes('text-red-600')
            logger.error(f"Ошибка при загрузке процессов: {e}", exc_info=True)

def create_manage_section():
    """Создает секцию управления процессами"""
    ui.label('Управление процессами').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        with ui.column().classes('w-full'):
            ui.label('Список развернутых процессов').classes('text-sm font-medium mb-2')
            
            # Кнопка обновления
            ui.button(
                'Обновить список',
                icon='refresh',
                on_click=lambda: load_process_definitions(processes_container)
            ).classes('mb-4 bg-blue-500 text-white text-xs px-2 py-1 h-7')
            
            # Контейнер для процессов
            processes_container = ui.column().classes('w-full')
            
            # Загружаем процессы при открытии
            load_process_definitions(processes_container)

def refresh_templates():
    """Обновляет список шаблонов"""
    try:
        camunda_client = create_camunda_client()
        processes = camunda_client.get_active_process_definitions()
        
        # Список готовых шаблонов
        templates = [
            {
                'name': 'Простой процесс одобрения',
                'description': 'Базовый процесс с одной задачей на одобрение',
                'file': 'simple_approval.bpmn',
                'icon': 'check_circle'
            },
            {
                'name': 'Процесс с несколькими участниками',
                'description': 'Процесс с последовательными задачами для разных пользователей',
                'file': 'multi_user_process.bpmn',
                'icon': 'group'
            },
            {
                'name': 'Процесс ознакомления с документом',
                'description': 'Процесс для ознакомления нескольких пользователей с документом',
                'file': 'document_review.bpmn',
                'icon': 'description'
            }
        ]
        
        ui.label(f'Доступно {len(templates)} шаблонов:').classes('text-lg font-semibold mb-4')
        
        for template in templates:
            with ui.card().classes('mb-3 p-4 border-l-4 border-green-500'):
                with ui.row().classes('items-start justify-between w-full'):
                    with ui.column().classes('flex-1'):
                        ui.label(f'{template["name"]}').classes('text-lg font-semibold')
                        ui.label(f'{template["description"]}').classes('text-sm text-gray-600')
                        ui.label(f'Файл: {template["file"]}').classes('text-sm text-gray-600')
                    
                    with ui.column().classes('items-end gap-2'):
                        ui.button(
                            'Скачать',
                            icon='download',
                            on_click=lambda t=template: download_template(t)
                        ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                        
                        ui.button(
                            'Создать',
                            icon='add',
                            on_click=lambda t=template: create_new_template(t["name"])
                        ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
    except Exception as e:
        ui.label(f'Ошибка загрузки шаблонов: {str(e)}').classes('text-red-600')
        logger.error(f"Ошибка при загрузке шаблонов: {e}", exc_info=True)

def download_template(template):
    """Скачивает шаблон"""
    ui.notify(f'Скачивание шаблона: {template["name"]}', type='info')
    # Здесь можно добавить логику скачивания файла

def create_new_template(name):
    """Создает новый шаблон"""
    if not name:
        ui.notify('Введите название шаблона', type='error')
        return
    
    ui.notify(f'Создание шаблона: {name}', type='info')
    # Здесь можно добавить логику создания нового шаблона

def create_templates_section():
    """Создает секцию шаблонов"""
    ui.label('Шаблоны процессов').classes('text-lg font-semibold mb-4')
    
    with ui.card().classes('p-4 bg-blue-50'):
        with ui.column().classes('w-full'):
            ui.label('Доступные шаблоны процессов').classes('text-sm font-medium mb-2')
            
            # Кнопка обновления списка
            ui.button(
                'Обновить шаблоны',
                icon='refresh',
                on_click=refresh_templates
            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
        
        
       