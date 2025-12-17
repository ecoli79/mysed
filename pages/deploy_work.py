from message import message
from nicegui import ui
from models import Task
from services.camunda_connector import create_camunda_client
from models import CamundaDeployment, CamundaProcessDefinition
import theme
import tempfile
import os
from nicegui import app, ui
from datetime import datetime
from urllib.parse import urljoin
import re
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


async def test_camunda_connection():
    """Тестирует подключение к Camunda"""
    try:
        camunda_client = await create_camunda_client()
        async with camunda_client:
            response = await camunda_client._make_request('GET', 'version')
            
            if response.status_code == 200:
                version_info = response.json()
                ui.notify(f'Подключение успешно! Версия Camunda: {version_info.get("version", "неизвестна")}', type='success')
            else:
                ui.notify(f'Ошибка подключения: {response.status_code}', type='error')
            
    except Exception as e:
        ui.notify(f'Ошибка подключения: {str(e)}', type='error')
        logger.error(f'Ошибка при тестировании подключения к Camunda: {e}', exc_info=True)


async def update_connection_status():
    """Обновляет статус подключения"""
    await test_camunda_connection()


async def deploy_click(uploaded_file, deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container):
    """Обработчик кнопки развертывания"""
    if not uploaded_file['file']:
        ui.notify('Выберите BPMN файл', type='error')
        return
    
    await deploy_process_from_upload(
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
            
            # Контейнер для результатов (создаем до upload_area)
            results_container = ui.column().classes('w-full')
            
            # Загрузка файла
            ui.upload(
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

    content = e.content.read()
    
    try:
        content_str = content.decode('utf-8')
        content = content_str.encode('utf-8')
    except UnicodeDecodeError:
        try:
            content_str = content.decode('windows-1251')
            content = content_str.encode('utf-8')
            ui.notify('Файл перекодирован из Windows-1251 в UTF-8', type='info')
        except UnicodeDecodeError:
            ui.notify('Не удалось определить кодировку файла', type='error')
            return
    
    if not is_valid_bpmn(content):
        ui.notify('Файл не является валидным BPMN файлом', type='error')
        return
    
    uploaded_file['file'] = {
        'name': e.name,
        'content': content
    }

    results_container.clear()
    with results_container:
        ui.label(f'Файл {e.name} загружен успешно!').classes('text-green-600')
        ui.label(f'Размер: {len(content)} байт').classes('text-sm text-gray-600')
        
        process_name = extract_process_name(content)
        if process_name:
            ui.label(f'Название процесса: {process_name}').classes('text-sm text-blue-600')


def is_valid_bpmn(content: bytes) -> bool:
    """Проверяет, является ли содержимое валидным BPMN файлом"""
    try:
        content_str = content.decode('utf-8')
        return '<definitions' in content_str and '<process' in content_str
    except UnicodeDecodeError:
        return False


def extract_process_name(content: bytes) -> str | None:
    """Извлекает название процесса из BPMN файла"""
    try:
        content_str = content.decode('utf-8')
        match = re.search(r'<process[^>]*name="([^"]*)"', content_str)
        return match.group(1) if match else None
    except (UnicodeDecodeError, AttributeError):
        return None


async def deploy_process_from_upload(deployment_name, enable_duplicate_filtering, deploy_changed_only, tenant_id, results_container, uploaded_file):
    """Развертывает процесс из загруженного файла"""
    if not deployment_name.value:
        ui.notify('Введите имя развертывания', type='error')
        return
    
    if not uploaded_file['file']:
        ui.notify('Нет загруженного файла', type='error')
        return

    results_container.clear()
    with results_container:
        progress = ui.linear_progress().classes('w-full mb-2')
        progress.value = 0.1

        tmpFilePath = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bpmn') as tmpFile:
                tmpFile.write(uploaded_file['file']['content'])
                tmpFilePath = tmpFile.name

            progress.value = 0.3
            
            deployment = await deploy_process_improved(
                deployment_name=deployment_name.value,
                bpmn_file_path=tmpFilePath,
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
                
                if deployment.process_definitions:
                    ui.label('Развернутые процессы:').classes('text-sm font-medium mt-2')
                    for process in deployment.process_definitions:
                        ui.label(f'  • {process.name} (ID: {process.id})').classes('text-sm text-blue-600')
                        ui.label(f'    Ключ: {process.key}, Версия: {process.version}').classes('text-xs text-gray-600')
                else:
                    ui.label('Процесс успешно развернут!').classes('text-sm text-blue-600 mt-2')
            else:
                ui.label('Ошибка развертывания').classes('text-red-600 font-semibold')
                
        except Exception as e:
            ui.label(f'Ошибка: {str(e)}').classes('text-red-600')
            logger.error(f'Ошибка при развертывании процесса: {e}', exc_info=True)
        finally:
            if tmpFilePath:
                try:
                    os.unlink(tmpFilePath)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    logger.error(f'Ошибка при удалении временного файла {tmpFilePath}: {e}')


async def deploy_process_improved(
    deployment_name: str,
    bpmn_file_path: str,
    enable_duplicate_filtering: bool = False,
    deploy_changed_only: bool = False,
    tenant_id: str | None = None
) -> CamundaDeployment | None:
    """
    Улучшенная функция развертывания процесса с правильным форматом multipart/form-data
    """
    endpoint = 'deployment/create'
    
    try:
        with open(bpmn_file_path, 'rb') as f:
            fileContent = f.read()
        
        try:
            contentStr = fileContent.decode('utf-8')
            logger.info(f'Размер файла: {len(fileContent)} байт')
            logger.info(f'Первые 200 символов файла: {contentStr[:200]}')
            
            if not ('<definitions' in contentStr and '<process' in contentStr):
                logger.error('Файл не содержит валидный BPMN процесс')
                logger.error(f'Содержимое файла: {contentStr[:500]}')
                return None
                        
            doctypeFound = re.search(r'<!DOCTYPE[^>]*>', contentStr, re.IGNORECASE | re.DOTALL)
            if doctypeFound:
                logger.warning(f'Найдена DOCTYPE декларация: {doctypeFound.group()}')
            else:
                logger.info('DOCTYPE декларация не найдена в файле')
            
            fileContent = contentStr.encode('utf-8')
            
        except UnicodeDecodeError as e:
            logger.error(f'Ошибка декодирования файла: {e}')
            return None
        
        # Подготавливаем данные для multipart/form-data
        data = {
            'deployment-name': deployment_name,
            'enable-duplicate-filtering': str(enable_duplicate_filtering).lower(),
            'deploy-changed-only': str(deploy_changed_only).lower(),
        }
        
        if tenant_id:
            data['tenant-id'] = tenant_id
        
        files = {
            'data': (os.path.basename(bpmn_file_path), fileContent, 'application/xml')
        }
        
        camundaClient = await create_camunda_client()
        async with camundaClient:
            url = urljoin(camundaClient.engine_rest_url, endpoint.lstrip('/'))
            
            logger.info(f'Отправляем запрос на развертывание на URL: {url}')
            logger.info(f'Параметры: deployment-name={deployment_name}, enable-duplicate-filtering={enable_duplicate_filtering}')
            
            response = await camundaClient.client.post(
                url,
                data=data,
                files=files,
                timeout=110.0
            )
            
            logger.info(f'Ответ сервера: {response.status_code}')
            logger.info(f'Заголовки ответа: {dict(response.headers)}')
            
            if response.status_code == 200:
                deploymentData = response.json()
                logger.info(f'Данные развертывания: {deploymentData}')
                
                processDefinitions = []
                if 'deployedProcessDefinitions' in deploymentData and deploymentData['deployedProcessDefinitions']:
                    for processData in deploymentData['deployedProcessDefinitions'].values():
                        processDefinitions.append(CamundaProcessDefinition(
                            id=processData['id'],
                            key=processData['key'],
                            category=processData.get('category'),
                            description=processData.get('description'),
                            name=processData['name'],
                            version=processData['version'],
                            resource=processData['resource'],
                            deployment_id=processData['deploymentId'],
                            diagram=processData.get('diagram'),
                            suspended=processData['suspended'],
                            tenant_id=processData.get('tenantId'),
                            version_tag=processData.get('versionTag'),
                            history_time_to_live=processData.get('historyTimeToLive'),
                            startable_in_tasklist=processData['startableInTasklist']
                        ))
                
                deployment = CamundaDeployment(
                    id=deploymentData['id'],
                    name=deploymentData['name'],
                    deployment_time=deploymentData['deploymentTime'],
                    source=deploymentData.get('source'),
                    tenant_id=deploymentData.get('tenantId'),
                    process_definitions=processDefinitions
                )
                
                return deployment
            else:
                logger.error(f'Ошибка развертывания: {response.status_code}')
                logger.error(f'Ответ сервера: {response.text}')
                return None
            
    except Exception as e:
        logger.error(f'Ошибка при развертывании процесса: {e}', exc_info=True)
        return None


async def load_process_definitions(processes_container):
    """Загружает список определений процессов"""
    processes_container.clear()
    
    with processes_container:
        loadingLabel = ui.label('Загрузка процессов...').classes('text-gray-600')
        
        try:
            camundaClient = await create_camunda_client()
            async with camundaClient:
                processes = await camundaClient.get_active_process_definitions()
            
            loadingLabel.delete()
            
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
            loadingLabel.delete()
            ui.label(f'Ошибка загрузки: {str(e)}').classes('text-red-600')
            logger.error(f'Ошибка при загрузке процессов: {e}', exc_info=True)


def create_manage_section():
    """Создает секцию управления процессами"""
    ui.label('Управление процессами').classes('text-xl font-semibold mb-4')
    
    with ui.card().classes('p-6 w-full'):
        with ui.column().classes('w-full'):
            ui.label('Список развернутых процессов').classes('text-sm font-medium mb-2')
            
            # Контейнер для процессов
            processesContainer = ui.column().classes('w-full')
            
            # Кнопка обновления
            ui.button(
                'Обновить список',
                icon='refresh',
                on_click=lambda: load_process_definitions(processesContainer)
            ).classes('mb-4 bg-blue-500 text-white text-xs px-2 py-1 h-7')
            
            # Загружаем процессы при открытии
            ui.timer(0.1, lambda: load_process_definitions(processesContainer), once=True)


async def refresh_templates():
    """Обновляет список шаблонов"""
    ui.notify('Функция в разработке', type='info')

    # try:
    #     camundaClient = await create_camunda_client()
    #     async with camundaClient:
    #         await camundaClient.get_active_process_definitions()
        
    #     templates = [
    #         {
    #             'name': 'Простой процесс одобрения',
    #             'description': 'Базовый процесс с одной задачей на одобрение',
    #             'file': 'simple_approval.bpmn',
    #             'icon': 'check_circle'
    #         },
    #         {
    #             'name': 'Процесс с несколькими участниками',
    #             'description': 'Процесс с последовательными задачами для разных пользователей',
    #             'file': 'multi_user_process.bpmn',
    #             'icon': 'group'
    #         },
    #         {
    #             'name': 'Процесс ознакомления с документом',
    #             'description': 'Процесс для ознакомления нескольких пользователей с документом',
    #             'file': 'document_review.bpmn',
    #             'icon': 'description'
    #         }
    #     ]
        
    #     ui.label(f'Доступно {len(templates)} шаблонов:').classes('text-lg font-semibold mb-4')
        
    #     for template in templates:
    #         with ui.card().classes('mb-3 p-4 border-l-4 border-green-500'):
    #             with ui.row().classes('items-start justify-between w-full'):
    #                 with ui.column().classes('flex-1'):
    #                     ui.label(f'{template["name"]}').classes('text-lg font-semibold')
    #                     ui.label(f'{template["description"]}').classes('text-sm text-gray-600')
    #                     ui.label(f'Файл: {template["file"]}').classes('text-sm text-gray-600')
                    
    #                 with ui.column().classes('items-end gap-2'):
    #                     ui.button(
    #                         'Скачать',
    #                         icon='download',
    #                         on_click=lambda t=template: download_template(t)
    #                     ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')
                        
    #                     ui.button(
    #                         'Создать',
    #                         icon='add',
    #                         on_click=lambda t=template: create_new_template(t['name'])
    #                     ).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
    # except Exception as e:
    #     ui.label(f'Ошибка загрузки шаблонов: {str(e)}').classes('text-red-600')
    #     logger.error(f'Ошибка при загрузке шаблонов: {e}', exc_info=True)


def download_template(template):
    """Скачивает шаблон"""
    ui.notify(f'Скачивание шаблона: {template["name"]}', type='info')


def create_new_template(name):
    """Создает новый шаблон"""
    if not name:
        ui.notify('Введите название шаблона', type='error')
        return
    
    ui.notify(f'Создание шаблона: {name}', type='info')


def create_templates_section():
    """Создает секцию шаблонов"""
    ui.label('Шаблоны процессов').classes('text-lg font-semibold mb-4')
    
    with ui.card().classes('p-4 bg-blue-50'):
        with ui.column().classes('w-full'):
            ui.label('Доступные шаблоны процессов').classes('text-sm font-medium mb-2')
            
            ui.button(
                'Обновить шаблоны',
                icon='refresh',
                on_click=refresh_templates
            ).classes('bg-green-500 text-white text-xs px-2 py-1 h-7')