import httpx
from httpx import BasicAuth
from datetime import datetime
from services.document_access_manager import document_access_manager
import json
from typing import List, Optional, Dict, Any, Union
from urllib.parse import urljoin
import os

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models import (
    CamundaDeployment, 
    CamundaProcessDefinition, 
    CamundaTask, 
    CamundaHistoryTask,
    CamundaDeploymentRequest,
    CamundaTaskAssignment,
    CamundaTaskCompletion,
    CamundaHistoryTask,
    GroupedHistoryTask,
    UserTaskInfo,
    ProcessVariables,
    JSONStringField,
)

import logging

logger = logging.getLogger(__name__)


class CamundaClient:
    """Асинхронный клиент для работы с Camunda Community Edition 7.22 REST API"""
    
    def __init__(self, base_url: str, username: str = None, password: str = None, 
                 token: str = None, token_type: str = 'Bearer', verify_ssl: bool = False):
        """
        Инициализация клиента Camunda
        
        Args:
            base_url: Базовый URL Camunda сервера (например: https://localhost:8080)
            username: Имя пользователя для аутентификации (если используется Basic Auth)
            password: Пароль для аутентификации (если используется Basic Auth)
            token: Токен для аутентификации (если используется Token Auth)
            token_type: Тип токена ('Bearer', 'JWT', etc.)
            verify_ssl: Проверять ли SSL сертификаты
        """
        self.base_url = base_url.rstrip('/')
        self.engine_rest_url = urljoin(self.base_url, '/engine-rest/')
        self.verify_ssl = verify_ssl
        
        # Настраиваем аутентификацию для httpx
        auth = None
        headers = {}
        
        if token:
            # Используем токен
            headers['Authorization'] = f'{token_type} {token}'
            self.auth_type = 'token'
        elif username and password:
            # Используем Basic Auth
            auth = BasicAuth(username, password)
            self.auth_type = 'basic'
        else:
            raise ValueError("Необходимо указать либо username/password, либо token")
    
        # Создаем httpx клиент
        self.client = httpx.AsyncClient(
            auth=auth,
            headers=headers,
            verify=verify_ssl,
            timeout=30.0
        )
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер: вход"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер: выход"""
        await self.close()
    
    async def close(self):
        """Закрывает HTTP клиент"""
        await self.client.aclose()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Выполняет HTTP запрос к Camunda API"""
        url = urljoin(self.engine_rest_url, endpoint.lstrip('/'))
        
        # Устанавливаем Content-Type только если передаем JSON и НЕ передаем файлы
        if 'json' in kwargs and 'files' not in kwargs:
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        
        response = await self.client.request(method, url, **kwargs)
        return response
    
    async def deploy_process(self, deployment_name: str, bpmn_file_path: str, 
                      enable_duplicate_filtering: bool = False,
                      deploy_changed_only: bool = False,
                      tenant_id: Optional[str] = None) -> Optional[CamundaDeployment]:
        """
        Развертывает BPMN процесс в Camunda
        
        Args:
            deployment_name: Имя развертывания
            bpmn_file_path: Путь к BPMN файлу
            enable_duplicate_filtering: Включить фильтрацию дубликатов
            deploy_changed_only: Развертывать только измененные файлы
            tenant_id: ID арендатора (опционально)
            
        Returns:
            CamundaDeployment объект или None в случае ошибки
        """
        endpoint = 'deployment/create'
        
        try:
            # Читаем файл полностью в память
            with open(bpmn_file_path, 'rb') as f:
                file_content = f.read()
            
            # Подготавливаем данные для multipart/form-data
            data = {
                'deployment-name': deployment_name,
                'enable-duplicate-filtering': str(enable_duplicate_filtering).lower(),
                'deploy-changed-only': str(deploy_changed_only).lower()
            }
            
            # Добавляем tenant_id если указан
            if tenant_id:
                data['tenant-id'] = tenant_id
            
            # Подготавливаем файлы для загрузки с правильным MIME-типом
            files = {
                'data': (os.path.basename(bpmn_file_path), file_content, 'text/xml')
            }
            
            # Выполняем запрос через httpx
            url = urljoin(self.engine_rest_url, endpoint.lstrip('/'))
            response = await self.client.post(url, data=data, files=files)
            response.raise_for_status()
            
            deployment_data = response.json()
            
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
            
            return CamundaDeployment(
                id=deployment_data['id'],
                name=deployment_data['name'],
                deployment_time=deployment_data['deploymentTime'],
                source=deployment_data.get('source'),
                tenant_id=deployment_data.get('tenantId'),
                process_definitions=process_definitions
            )
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при развертывании процесса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус ответа: {e.response.status_code}")
                logger.error(f"Текст ответа: {e.response.text}")
            return None
    
    async def get_active_process_definitions(self) -> List[CamundaProcessDefinition]:
        """
        Получает список активных определений процессов
        
        Returns:
            Список активных определений процессов
        """
        endpoint = 'process-definition'
        params = {
            'active': 'true',
            'sortBy': 'name',
            'sortOrder': 'asc'
        }
        
        try:
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            definitions_data = response.json()
            return [
                CamundaProcessDefinition(
                    id=def_data['id'],
                    key=def_data['key'],
                    category=def_data.get('category'),
                    description=def_data.get('description'),
                    name=def_data['name'],
                    version=def_data['version'],
                    resource=def_data['resource'],
                    deployment_id=def_data['deploymentId'],
                    diagram=def_data.get('diagram'),
                    suspended=def_data['suspended'],
                    tenant_id=def_data.get('tenantId'),
                    version_tag=def_data.get('versionTag'),
                    history_time_to_live=def_data.get('historyTimeToLive'),
                    startable_in_tasklist=def_data['startableInTasklist']
                )
                for def_data in definitions_data
            ]
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении определений процессов: {e}")
            return []
    
    async def get_task_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными задачи
        """
        endpoint = f'task/{task_id}/variables'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            variables_data = response.json()
            variables = {}
            
            for var_name, var_data in variables_data.items():
                if 'value' in var_data:
                    variables[var_name] = var_data['value']
            
            return variables
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении переменных задачи {task_id}: {e}")
            return {}
    
    async def get_process_instance_variables(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает переменные экземпляра процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с переменными процесса или пустой словарь при ошибке
        """
        endpoint = f'process-instance/{process_instance_id}/variables'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            
            variables_data = response.json()
            variables = {}
            
            if isinstance(variables_data, dict):
                for key, value_info in variables_data.items():
                    if isinstance(value_info, dict) and 'value' in value_info:
                        variables[key] = value_info['value']
                    else:
                        variables[key] = value_info
            
            return variables
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении переменных процесса {process_instance_id}: {e}")
            
            # Детальное логирование
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_text = e.response.text[:1000]
                    logger.error(f"Текст ошибки от Camunda: {error_text}")
                except:
                    pass
                    
                try:
                    error_json = e.response.json()
                    logger.error(f"JSON ошибки от Camunda: {error_json}")
                except:
                    pass
            
            return {}
    
    async def get_process_instance_variables_by_name(self, process_instance_id: str, variable_names: List[str]) -> Dict[str, Any]:
        """Получает конкретные переменные экземпляра процесса по именам"""
        endpoint = f'process-instance/{process_instance_id}/variables'
        params = {'deserializeValues': 'true'}
        
        if variable_names:
            params['variableNames'] = ','.join(variable_names)
        
        try:
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            variables_data = response.json()
            variables = {}
            
            if isinstance(variables_data, dict):
                for key, value_info in variables_data.items():
                    if isinstance(value_info, dict) and 'value' in value_info:
                        variables[key] = value_info['value']
                    else:
                        variables[key] = value_info
                            
            return variables
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении переменных процесса {process_instance_id}: {e}")
            return {}
    
    async def assign_task(self, task_id: str, assignee: str) -> bool:
        """Назначает задачу пользователю"""
        endpoint = f'task/{task_id}/assignee'
        payload = {'userId': assignee}
        
        try:
            response = await self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при назначении задачи {task_id}: {e}")
            return False
    
    async def get_user_tasks(self, assignee: str, active_only: bool = True, fetch_variables: bool = True,
                           process_definition_key: Optional[str] = None) -> List[CamundaTask]:
        """Получает задачи пользователя"""
        endpoint = 'task'
        params = {
            'assignee': assignee,
            'active': str(active_only).lower()
        }
        
        if process_definition_key:
            params['processDefinitionKey'] = process_definition_key
        
        try:
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            tasks_data = response.json()
            
            tasks = []
            for task_data in tasks_data:
                task = CamundaTask(
                    id=task_data['id'],
                    name=task_data.get('name', ''),
                    assignee=task_data.get('assignee'),
                    start_time=task_data.get('created', ''),  # Маппим 'created' на 'start_time'
                    due=task_data.get('due'),
                    follow_up=task_data.get('followUp'),
                    delegation_state=task_data.get('delegationState'),
                    description=task_data.get('description'),
                    execution_id=task_data.get('executionId', ''),
                    owner=task_data.get('owner'),
                    parent_task_id=task_data.get('parentTaskId'),
                    priority=task_data.get('priority', 0),
                    process_definition_id=task_data.get('processDefinitionId', ''),
                    process_instance_id=task_data.get('processInstanceId', ''),
                    task_definition_key=task_data.get('taskDefinitionKey', ''),
                    case_execution_id=task_data.get('caseExecutionId'),
                    case_instance_id=task_data.get('caseInstanceId'),
                    case_definition_id=task_data.get('caseDefinitionId'),
                    suspended=task_data.get('suspended', False),
                    form_key=task_data.get('formKey'),
                    tenant_id=task_data.get('tenantId')
                )
                
                if fetch_variables:
                    task.variables = await self.get_task_variables(task.id)
                
                tasks.append(task)
            
            return tasks
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении задач пользователя {assignee}: {e}")
            return []
    
    async def get_task(self, task: Union[CamundaTask, CamundaHistoryTask]) -> Optional[CamundaTask]:
        """Получает задачу по ID"""
        endpoint = f'task/{task.id}'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            task_data = response.json()
            
            return CamundaTask(
                id=task_data['id'],
                name=task_data.get('name', ''),
                assignee=task_data.get('assignee'),
                created=task_data.get('created'),
                due=task_data.get('due'),
                follow_up=task_data.get('followUp'),
                delegation_state=task_data.get('delegationState'),
                description=task_data.get('description'),
                execution_id=task_data.get('executionId'),
                owner=task_data.get('owner'),
                parent_task_id=task_data.get('parentTaskId'),
                priority=task_data.get('priority'),
                process_definition_id=task_data.get('processDefinitionId'),
                process_instance_id=task_data.get('processInstanceId'),
                task_definition_key=task_data.get('taskDefinitionKey'),
                case_execution_id=task_data.get('caseExecutionId'),
                case_instance_id=task_data.get('caseInstanceId'),
                case_definition_id=task_data.get('caseDefinitionId'),
                suspended=task_data.get('suspended'),
                form_key=task_data.get('formKey'),
                tenant_id=task_data.get('tenantId')
            )
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении задачи {task.id}: {e}")
            return None

    async def complete_task(self, task_id: str, variables: Optional[Dict[str, Any]] = None) -> bool:
        """Завершает задачу"""
        endpoint = f'task/{task_id}/complete'
        
        payload = {}
        if variables:
            payload['variables'] = self._prepare_variables(variables)
        
        try:
            response = await self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False
    
    async def start_process(self, process_definition_key: str, 
                          variables: Optional[Dict[str, Any]] = None,
                          business_key: Optional[str] = None,
                          validate: bool = True) -> Optional[str]:
        """
        Запускает процесс
        
        Args:
            process_definition_key: Ключ определения процесса
            variables: Переменные процесса
            business_key: Бизнес-ключ процесса
            validate: Проверять ли существование процесса перед запуском
            
        Returns:
            ID экземпляра процесса или None при ошибке
        """
        # Валидация существования процесса
        if validate:
            exists, error_msg = await self.validate_process_exists(process_definition_key)
            if not exists:
                logger.error(f"Не удалось запустить процесс: {error_msg}")
                return None
        
        endpoint = f'process-definition/key/{process_definition_key}/start'
        
        payload = {}
        if variables:
            prepared_vars = self._prepare_variables(variables)
            payload['variables'] = prepared_vars
            # Логируем переменные для отладки (без чувствительных данных)
            logger.debug(f"Переменные процесса {process_definition_key}: {list(prepared_vars.keys())}")
        if business_key:
            payload['businessKey'] = business_key
        
        try:
            # Логируем запрос для отладки
            logger.info(f"Запуск процесса {process_definition_key} с {len(payload.get('variables', {}))} переменными")
            
            response = await self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
            process_id = result.get('id')
            logger.info(f"Процесс {process_definition_key} успешно запущен, ID: {process_id}")
            return process_id
        except httpx.HTTPError as e:
            error_msg = f"Ошибка при запуске процесса {process_definition_key}"
            
            # Получаем детали ошибки от Camunda
            error_details = None
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                error_msg += f": HTTP {status_code}"
                
                # Пытаемся получить детали ошибки из ответа
                try:
                    if e.response.text:
                        error_details = e.response.text
                        logger.error(f"Детали ошибки от Camunda: {error_details}")
                except:
                    pass
                
                if status_code == 404:
                    error_msg += ": процесс не найден в Camunda"
                elif status_code == 400:
                    error_msg += ": некорректный запрос"
                    if error_details:
                        error_msg += f" - {error_details}"
            
            logger.error(f"{error_msg}: {e}")
            
            # Логируем payload для отладки (без чувствительных данных)
            if variables:
                logger.debug(f"Payload переменных (ключи): {list(variables.keys())}")
            
            return None

    def _format_variable(self, value: Any) -> Dict[str, Any]:
        """Форматирует переменную в формат Camunda API"""
        # Если переменная уже в правильном формате, возвращаем как есть
        if isinstance(value, dict) and 'value' in value and 'type' in value:
            return value
        elif isinstance(value, list):
            # Для списков используем тип Object с JSON-строкой для Multi-Instance коллекций
            return {
                'value': json.dumps(value),
                'type': 'Object',
                'valueInfo': {
                    'serializationDataFormat': 'application/json',
                    'objectTypeName': 'java.util.ArrayList'
                }
            }
        elif isinstance(value, str):
            return {'value': value, 'type': 'String'}
        elif isinstance(value, bool):
            return {'value': value, 'type': 'Boolean'}
        elif isinstance(value, int):
            return {'value': value, 'type': 'Integer'}
        elif isinstance(value, float):
            return {'value': value, 'type': 'Double'}
        elif isinstance(value, dict):
            # Для словарей используем тип Object с JSON-строкой
            return {
                'value': json.dumps(value),
                'type': 'Object',
                'valueInfo': {
                    'serializationDataFormat': 'application/json',
                    'objectTypeName': 'java.util.HashMap'
                }
            }
        else:
            return {'value': str(value), 'type': 'String'}

    def _prepare_variables(self, variables: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Подготавливает переменные для отправки в Camunda"""
        prepared = {}
        for key, value in variables.items():
            prepared[key] = self._format_variable(value)
        return prepared
    
    async def set_process_variable(self, process_instance_id: str, variable_name: str, 
                           variable_value: Any, variable_type: str = "String") -> bool:
        """Устанавливает переменную процесса"""
        endpoint = f'process-instance/{process_instance_id}/variables/{variable_name}'
        
        if variable_type == "Date" and isinstance(variable_value, str):
            payload = {
                'value': variable_value,
                'type': 'Date'
            }
        elif variable_type == "Object":
            payload = {
                'value': json.dumps(variable_value),
                'type': 'Object',
                'valueInfo': {
                    'serializationDataFormat': 'application/json',
                    'objectTypeName': type(variable_value).__name__
                }
            }
        else:
            payload = {
                'value': variable_value,
                'type': variable_type
            }
        
        try:
            response = await self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при установке переменной {variable_name}: {e}")
            return False

    async def set_multiple_process_variables(self, process_instance_id: str, 
                                     variables: Dict[str, Any]) -> bool:
        """Устанавливает несколько переменных процесса одновременно"""
        endpoint = f'process-instance/{process_instance_id}/variables'
        
        process_variables = {}
        for var_name, var_value in variables.items():
            process_variables[var_name] = self._format_variable(var_value)
        
        try:
            response = await self._make_request('POST', endpoint, json={'modifications': process_variables})
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при установке переменных процесса: {e}")
            return False
    
    async def get_task_by_id(self, task_id: str) -> Optional[CamundaTask]:
        """Получает задачу по ID"""
        endpoint = f'task/{task_id}'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            task_data = response.json()
            
            return CamundaTask(
                id=task_data['id'],
                name=task_data.get('name', ''),
                assignee=task_data.get('assignee'),
                start_time=task_data.get('created', ''), 
                due=task_data.get('due'),
                follow_up=task_data.get('followUp'),
                delegation_state=task_data.get('delegationState'),
                description=task_data.get('description'),
                execution_id=task_data.get('executionId', ''),
                owner=task_data.get('owner'),
                parent_task_id=task_data.get('parentTaskId'),
                priority=task_data.get('priority', 0),
                process_definition_id=task_data.get('processDefinitionId', ''),
                process_instance_id=task_data.get('processInstanceId', ''),
                task_definition_key=task_data.get('taskDefinitionKey', ''),
                case_execution_id=task_data.get('caseExecutionId'),
                case_instance_id=task_data.get('caseInstanceId'),
                case_definition_id=task_data.get('caseDefinitionId'),
                suspended=task_data.get('suspended', False),
                form_key=task_data.get('formKey'),
                tenant_id=task_data.get('tenantId')
            )
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении задачи {task_id}: {e}")
            return None
    
    async def get_history_task_by_id(self, task_id: str) -> Optional[CamundaHistoryTask]:
        """Получает историческую задачу по ID"""
        endpoint = f'history/task/{task_id}'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            task_data = response.json()
            
            return CamundaHistoryTask(
                id=task_data['id'],
                name=task_data.get('name', ''),
                assignee=task_data.get('assignee'),
                created=task_data.get('created'),
                due=task_data.get('due'),
                follow_up=task_data.get('followUp'),
                delegation_state=task_data.get('delegationState'),
                description=task_data.get('description'),
                execution_id=task_data.get('executionId'),
                owner=task_data.get('owner'),
                parent_task_id=task_data.get('parentTaskId'),
                priority=task_data.get('priority'),
                process_definition_id=task_data.get('processDefinitionId'),
                process_instance_id=task_data.get('processInstanceId'),
                task_definition_key=task_data.get('taskDefinitionKey'),
                case_execution_id=task_data.get('caseExecutionId'),
                case_instance_id=task_data.get('caseInstanceId'),
                case_definition_id=task_data.get('caseDefinitionId'),
                end_time=task_data.get('endTime'),
                duration=task_data.get('duration'),
                start_time=task_data.get('startTime'),
                delete_reason=task_data.get('deleteReason'),
                tenant_id=task_data.get('tenantId')
            )
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении исторической задачи {task_id}: {e}")
            return None
    
    async def get_history_process_instance_variables_by_name(self, process_instance_id: str, variable_names: List[str] = None) -> Dict[str, Any]:
        """
        Получает переменные завершенного экземпляра процесса по именам
        
        Args:
            process_instance_id: ID экземпляра процесса
            variable_names: Список имен переменных для получения (опционально)
            
        Returns:
            Словарь с переменными процесса
        """
        endpoint = 'history/variable-instance'
        params = {
            'processInstanceId': process_instance_id,
            'deserializeValues': 'true'
        }
        
        # Добавляем фильтр по именам переменных если указаны
        if variable_names:
            params['variableNames'] = ','.join(variable_names)
        
        try:
            logger.info(f"Запрашиваем исторические переменные процесса {process_instance_id}")
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            variables_data = response.json()
            logger.info(f"Получены исторические переменные: {len(variables_data)} переменных")
            
            # Преобразуем список переменных в словарь
            variables = {}
            for var in variables_data:
                var_name = var.get('name')
                var_value = var.get('value')
                variables[var_name] = var_value
            
            logger.info(f"Переменные процесса {process_instance_id}: {variables}")
            return variables
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении исторических переменных процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return {}
    
    async def get_process_instance_history(self, process_instance_id: str) -> List[Dict[str, Any]]:
        """
        Получает историю выполнения экземпляра процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Список событий истории процесса
        """
        endpoint = f'history/process-instance/{process_instance_id}'
        
        try:
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении истории процесса {process_instance_id}: {e}")
            return []
    
    async def get_user_tasks_filtered(self, assignee: str, active_only: bool = True, 
                            filter_completed: bool = True) -> List[Union[CamundaTask, CamundaHistoryTask]]:
        """
        Получает отфильтрованные задачи пользователя
        
        Args:
            assignee: Исполнитель задач
            active_only: Только активные задачи
            filter_completed: Фильтровать завершенные задачи
            
        Returns:
            Список отфильтрованных задач пользователя
        """
        # Получаем все задачи пользователя
        all_tasks = await self.get_user_tasks(assignee, active_only, fetch_variables=True)
        
        logger.info(f"Получено {len(all_tasks)} задач из get_user_tasks для пользователя {assignee}")
        
        if not filter_completed:
            # Дедупликация по ID задачи даже без фильтрации
            seen_task_ids = set()
            unique_tasks = []
            for task in all_tasks:
                if task.id not in seen_task_ids:
                    seen_task_ids.add(task.id)
                    unique_tasks.append(task)
                else:
                    logger.warning(f"Обнаружен дубликат задачи с ID {task.id} в get_user_tasks_filtered, пропускаем")
            logger.info(f"После дедупликации осталось {len(unique_tasks)} уникальных задач")
            return unique_tasks
        
        filtered_tasks = []
        seen_task_ids = set()  # Добавляем множество для отслеживания уже добавленных задач
        
        for task in all_tasks:
            # Проверяем, не добавлена ли уже задача с таким ID
            if task.id in seen_task_ids:
                logger.warning(f"Обнаружен дубликат задачи с ID {task.id} в get_user_tasks_filtered, пропускаем")
                continue
            
            # Получаем переменные процесса для проверки статуса пользователя
            try:
                process_variables = await self.get_process_instance_variables(task.process_instance_id)
                
                # Проверяем, завершил ли пользователь эту задачу
                user_completed = process_variables.get('userCompleted', {})
                if isinstance(user_completed, dict):
                    if user_completed.get(assignee, False):
                        # Пользователь уже завершил эту задачу, пропускаем
                        logger.debug(f"Пользователь {assignee} уже завершил задачу {task.id}, пропускаем")
                        continue
                
                # Если пользователь не завершил задачу, добавляем её в результат
                filtered_tasks.append(task)
                seen_task_ids.add(task.id)  # Отмечаем, что задача уже добавлена
                
            except Exception as e:
                logger.warning(f"Не удалось проверить статус пользователя {assignee} для задачи {task.id}: {e}")
                # В случае ошибки добавляем задачу только если она еще не была добавлена
                if task.id not in seen_task_ids:
                    filtered_tasks.append(task)
                    seen_task_ids.add(task.id)
        
        logger.info(f"После фильтрации осталось {len(filtered_tasks)} задач для пользователя {assignee}")
        return filtered_tasks
    
    async def get_task_progress(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает информацию о прогрессе выполнения Multi-Instance задачи
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о прогрессе
        """
        try:
            # Получаем переменные процесса
            process_variables = await self.get_process_instance_variables(process_instance_id)
            
            # Получаем переменные Multi-Instance из активных задач
            multi_instance_variables = await self._get_multi_instance_variables(process_instance_id)
            
            # Объединяем переменные
            all_variables = {**process_variables, **multi_instance_variables}
            
            # Для Multi-Instance процессов используем nrOfInstances и nrOfCompletedInstances
            nr_of_instances = all_variables.get('nrOfInstances', 0)
            nr_of_completed_instances = all_variables.get('nrOfCompletedInstances', 0)
            
            # ИСПРАВЛЕНИЕ: Поддерживаем как задачи ознакомления (assigneeList), так и задачи подписания (signerList)
            # Получаем список всех пользователей
            assignee_list = all_variables.get('assigneeList', [])
            signer_list = all_variables.get('signerList', [])
            
            # Используем signerList для задач подписания, если assigneeList пуст
            user_list = signer_list if signer_list and not assignee_list else assignee_list
            
            if isinstance(user_list, str):
                try:
                    user_list = json.loads(user_list)
                except:
                    user_list = []
            
            if isinstance(signer_list, dict) and 'value' in signer_list:
                signer_list = signer_list['value']
            elif isinstance(signer_list, str):
                try:
                    signer_list = json.loads(signer_list)
                except:
                    signer_list = []
            
            logger.info(f"Переменные процесса {process_instance_id}:")
            logger.info(f"  nrOfInstances: {nr_of_instances}")
            logger.info(f"  nrOfCompletedInstances: {nr_of_completed_instances}")
            logger.info(f"  nrOfActiveInstances: {all_variables.get('nrOfActiveInstances', 0)}")
            logger.info(f"  assigneeList: {assignee_list}")
            logger.info(f"  signerList: {signer_list}")
            logger.info(f"  Итоговый user_list: {user_list}")
            
            # Получаем статус пользователей из переменных процесса
            user_completed = all_variables.get('userCompleted', {})
            signatures = all_variables.get('signatures', {})
            
            # ИСПРАВЛЕНИЕ: Для задач подписания используем signatures для определения статуса
            if isinstance(signatures, str):
                try:
                    signatures = json.loads(signatures)
                except:
                    signatures = {}
            
            # Если есть данные о подписях, используем их
            if signatures and isinstance(signatures, dict):
                user_completed = {user: user in signatures for user in user_list}
                logger.info(f"  Используем signatures для определения статуса: {user_completed}")
            
            if isinstance(user_completed, str):
                try:
                    user_completed = json.loads(user_completed)
                except:
                    user_completed = {}
            
            logger.info(f"  userCompleted: {user_completed}")
            
            # Если переменная userCompleted пуста или неполная, проверяем историю задач
            if not user_completed or len(user_completed) < len(user_list):
                logger.info(f"Переменная userCompleted неполная для процесса {process_instance_id}, проверяем историю задач")
                user_completed = await self._get_user_completion_status_from_history(process_instance_id, user_list)
            
            # Создаем детальную информацию о пользователях
            user_status = []
            for user in user_list:
                completed = user_completed.get(user, False) if isinstance(user_completed, dict) else False
                user_status.append({
                    'user': user,
                    'completed': completed,
                    'status': 'Завершено' if completed else 'В процессе'
                })
            
            result = {
                'completed_reviews': nr_of_completed_instances,
                'total_reviews': nr_of_instances,
                'progress_percent': (nr_of_completed_instances / nr_of_instances) * 100 if nr_of_instances > 0 else 0,
                'user_status': user_status,
                'is_complete': nr_of_completed_instances >= nr_of_instances
            }
            
            logger.info(f"Результат get_task_progress: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении прогресса процесса {process_instance_id}: {e}")
            return {
                'completed_reviews': 0,
                'total_reviews': 1,
                'progress_percent': 0,
                'user_status': [],
                'is_complete': False
            }
    
    async def _get_multi_instance_variables(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает переменные Multi-Instance из активных задач
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с переменными Multi-Instance
        """
        try:
            # Получаем активные задачи для процесса
            endpoint = f'task?processInstanceId={process_instance_id}'
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            
            tasks = response.json()
            logger.info(f"Найдено {len(tasks)} активных задач для процесса {process_instance_id}")
            
            # Ищем переменные Multi-Instance в первой задаче (они одинаковые для всех экземпляров)
            if tasks:
                task_id = tasks[0]['id']
                task_variables = await self.get_task_variables(task_id)
                
                # Извлекаем переменные Multi-Instance
                multi_instance_vars = {}
                for var_name in ['nrOfInstances', 'nrOfCompletedInstances', 'nrOfActiveInstances']:
                    if var_name in task_variables:
                        multi_instance_vars[var_name] = task_variables[var_name]
                
                logger.info(f"Переменные Multi-Instance из задачи {task_id}: {multi_instance_vars}")
                return multi_instance_vars
            
            return {}
            
        except Exception as e:
            logger.error(f"Ошибка при получении переменных Multi-Instance для процесса {process_instance_id}: {e}")
            return {}
    
    async def _get_user_completion_status_from_history(self, process_instance_id: str, assignee_list: List[str]) -> Dict[str, bool]:
        """
        Получает статус завершения задач пользователей из истории Camunda
        
        Args:
            process_instance_id: ID экземпляра процесса
            assignee_list: Список пользователей
            
        Returns:
            Словарь с статусом завершения для каждого пользователя
        """
        user_completed = {}
        
        try:
            # Получаем исторические задачи для этого процесса
            endpoint = f'history/task?processInstanceId={process_instance_id}'
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            
            history_tasks = response.json()
            logger.info(f"Найдено {len(history_tasks)} исторических задач для процесса {process_instance_id}")
            
            # Инициализируем всех пользователей как незавершенных
            for user in assignee_list:
                user_completed[user] = False
            
            # Проверяем завершенные задачи
            for task in history_tasks:
                assignee = task.get('assignee')
                delete_reason = task.get('deleteReason')
                
                if assignee in assignee_list and delete_reason == 'completed':
                    user_completed[assignee] = True
                    logger.info(f"Пользователь {assignee} завершил задачу {task.get('id')}")
            
            logger.info(f"Статус завершения пользователей: {user_completed}")
            
        except Exception as e:
            logger.error(f"Ошибка при получении истории задач для процесса {process_instance_id}: {e}")
            # В случае ошибки возвращаем пустой словарь
            for user in assignee_list:
                user_completed[user] = False
        
        return user_completed
    
    async def complete_task_with_user_data(self, task_id: str, 
                                status: str = "completed",
                                comment: Optional[str] = None,
                                review_date: Optional[str] = None) -> bool:
        """
        Завершает задачу и обновляет переменные пользователя напрямую в Python коде
        """
        # Получаем информацию о задаче
        task_info = await self.get_task_by_id(task_id)
        if not task_info:
            logger.error(f"Не удалось получить информацию о задаче {task_id}")
            return False
            
        process_instance_id = task_info.process_instance_id
        assignee = task_info.assignee
        
        if not assignee:
            logger.error(f"Задача {task_id} не назначена пользователю")
            return False
        
        logger.info(f"Завершение задачи {task_id} пользователем {assignee}")
        
        # Получаем текущие переменные процесса
        process_variables_raw = await self.get_process_instance_variables(process_instance_id)
        
        # Создаем объект ProcessVariables для работы с переменными
        from models import ProcessVariables
        process_vars = ProcessVariables(**process_variables_raw)
        
        # Обновляем данные для текущего пользователя
        current_date = review_date or datetime.now().isoformat()
        
        if status == "completed":
            process_vars.update_user_info(
                username=assignee,
                comment=comment or "",
                completion_date=current_date,
                status="completed",
                completed=True
            )
            logger.info(f"Пользователь {assignee} завершил ознакомление с документом")
        else:
            process_vars.update_user_info(
                username=assignee,
                status="not_completed",
                completed=False
            )
            logger.info(f"Пользователь {assignee} не завершил ознакомление с документом")
        
        # Обновляем счетчик завершенных задач
        if status == "completed":
            process_vars.completed_tasks = (process_vars.completed_tasks or 0) + 1
        
        # Убеждаемся, что все JSON поля инициализированы
        from models import JSONStringField
        
        if not process_vars.user_completion_dates:
            process_vars.user_completion_dates = JSONStringField(value="{}")
        if not process_vars.user_comments:
            process_vars.user_comments = JSONStringField(value="{}")
        if not process_vars.user_status:
            process_vars.user_status = JSONStringField(value="{}")
        if not process_vars.user_completed:
            process_vars.user_completed = JSONStringField(value="{}")
        
        # ОБНОВЛЯЕМ СТАРЫЕ ПЕРЕМЕННЫЕ (reviewComments, reviewDates, reviewStatus) для обратной совместимости
        # Получаем текущие старые переменные
        review_dates = process_variables_raw.get('reviewDates', {})
        review_comments = process_variables_raw.get('reviewComments', {})
        review_status = process_variables_raw.get('reviewStatus', {})
        
        # Если это словари, работаем с ними, иначе парсим JSON строку
        if isinstance(review_dates, str):
            try:
                review_dates = json.loads(review_dates)
            except:
                review_dates = {}
        if isinstance(review_comments, str):
            try:
                review_comments = json.loads(review_comments)
            except:
                review_comments = {}
        if isinstance(review_status, str):
            try:
                review_status = json.loads(review_status)
            except:
                review_status = {}
        
        # Обновляем старые переменные данными текущего пользователя
        if status == "completed":
            review_dates[assignee] = current_date
            review_comments[assignee] = comment or ""
            review_status[assignee] = True
        else:
            review_status[assignee] = False
        
        # Подготавливаем переменные для обновления процесса в правильном формате Camunda API
        updated_variables = {
            'userCompletionDates': {
                'value': process_vars.user_completion_dates.value,
                'type': 'String'
            },
            'userComments': {
                'value': process_vars.user_comments.value,
                'type': 'String'
            },
            'userStatus': {
                'value': process_vars.user_status.value,
                'type': 'String'
            },
            'userCompleted': {
                'value': process_vars.user_completed.value,
                'type': 'String'
            },
            'completedTasks': {
                'value': process_vars.completed_tasks,
                'type': 'Integer'
            },
            # ДОБАВЛЯЕМ СТАРЫЕ ПЕРЕМЕННЫЕ для обратной совместимости
            'reviewDates': {
                'value': json.dumps(review_dates, ensure_ascii=False),
                'type': 'String'
            },
            'reviewComments': {
                'value': json.dumps(review_comments, ensure_ascii=False),
                'type': 'String'
            },
            'reviewStatus': {
                'value': json.dumps(review_status, ensure_ascii=False),
                'type': 'String'
            }
        }
        
        # Обновляем переменные процесса
        if not await self.set_multiple_process_variables(process_instance_id, updated_variables):
            logger.error(f"Не удалось обновить переменные процесса {process_instance_id}")
            return False
        
        # Подготавливаем переменные для завершения задачи
        task_variables = {
            'reviewed': {
                'value': status == 'completed',
                'type': 'Boolean'
            },
            'reviewDate': {
                'value': current_date,
                'type': 'String'
            }
        }
        
        if comment:
            task_variables['reviewComment'] = {
                'value': comment,
                'type': 'String'
            }
        
        # Завершаем задачу
        endpoint = f'task/{task_id}/complete'
        payload = {'variables': task_variables}
        
        try:
            response = await self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            
            logger.info(f"Задача {task_id} успешно завершена пользователем {assignee}")
            logger.info(f"Обновлены переменные: userCompleted={process_vars.user_completed.to_dict()}, completedTasks={process_vars.completed_tasks}")
            
            return True
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False

    async def complete_task_with_variables(self, task_id: str, 
                                   variables: Optional[Dict[str, Any]] = None,
                                   local_variables: Optional[Dict[str, Any]] = None) -> bool:
        """
        Завершает задачу с передачей переменных в процесс и локальных переменных
        
        Args:
            task_id: ID задачи
            variables: Переменные для передачи в процесс
            local_variables: Локальные переменные задачи
            
        Returns:
            True если задача завершена успешно, False иначе
        """
        endpoint = f'task/{task_id}/complete'
        
        payload = {}
        
        if variables:
            # Подготавливаем переменные процесса в формате Camunda API
            process_variables = {}
            for key, value in variables.items():
                if isinstance(value, dict) and 'value' in value and 'type' in value:
                    process_variables[key] = value
                elif isinstance(value, str):
                    process_variables[key] = {
                        'value': value,
                        'type': 'String'
                    }
                elif isinstance(value, bool):
                    process_variables[key] = {
                        'value': value,
                        'type': 'Boolean'
                    }
                elif isinstance(value, (int, float)):
                    process_variables[key] = {
                        'value': value,
                        'type': 'Number'
                    }
                else:
                    process_variables[key] = {
                        'value': json.dumps(value),
                        'type': 'Object',
                        'valueInfo': {
                            'serializationDataFormat': 'application/json',
                            'objectTypeName': type(value).__name__
                        }
                    }
            payload['variables'] = process_variables
        
        if local_variables:
            # Подготавливаем локальные переменные
            local_vars = {}
            for key, value in local_variables.items():
                if isinstance(value, dict) and 'value' in value and 'type' in value:
                    local_vars[key] = value
                elif isinstance(value, str):
                    local_vars[key] = {
                        'value': value,
                        'type': 'String'
                    }
                elif isinstance(value, bool):
                    local_vars[key] = {
                        'value': value,
                        'type': 'Boolean'
                    }
                elif isinstance(value, (int, float)):
                    local_vars[key] = {
                        'value': value,
                        'type': 'Number'
                    }
                else:
                    local_vars[key] = {
                        'value': json.dumps(value),
                        'type': 'Object',
                        'valueInfo': {
                            'serializationDataFormat': 'application/json',
                            'objectTypeName': type(value).__name__
                        }
                    }
            payload['localVariables'] = local_vars
        
        try:
            response = await self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False

    async def get_user_tasks_by_process_key(self, username: str, process_definition_key: str, 
                                    active_only: bool = True) -> List[Union[CamundaTask, CamundaHistoryTask]]:
        """
        Универсальная функция для получения задач пользователя по ключу процесса
        
        Args:
            username: Имя пользователя
            process_definition_key: Ключ определения процесса
            active_only: Получать только активные задачи
            
        Returns:
            Список задач пользователя
        """
        all_tasks = await self.get_user_tasks(username, active_only=active_only)
        
        # Фильтруем задачи по ключу процесса
        filtered_tasks = []
        for task in all_tasks:
            if hasattr(task, 'process_definition_id'):
                # Получаем информацию о процессе
                try:
                    response = await self._make_request('GET', f'process-definition/{task.process_definition_id}')
                    response.raise_for_status()
                    process_info = response.json()
                    if process_info.get('key') == process_definition_key:
                        filtered_tasks.append(task)
                except Exception as e:
                    logger.warning(f"Ошибка при получении информации о процессе {task.process_definition_id}: {e}")
        
        return filtered_tasks

    async def get_process_variables_by_names(self, process_instance_id: str, 
                                     variable_names: List[str]) -> Dict[str, Any]:
        """
        Универсальная функция для получения конкретных переменных процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            variable_names: Список имен переменных
            
        Returns:
            Словарь с переменными
        """
        return await self.get_process_instance_variables_by_name(process_instance_id, variable_names)

    async def get_process_status(self, process_instance_id: str, 
                         status_variables: List[str] = None) -> Dict[str, Any]:
        """
        Универсальная функция для получения статуса процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            status_variables: Список переменных для получения статуса
            
        Returns:
            Словарь со статусом процесса
        """
        if status_variables:
            variables = await self.get_process_variables_by_names(process_instance_id, status_variables)
        else:
            variables = await self.get_process_instance_variables(process_instance_id)
        
        return {
            'process_instance_id': process_instance_id,
            'variables': variables,
            'is_active': await self.is_process_active(process_instance_id)
        }

    async def is_process_active(self, process_instance_id: str) -> bool:
        """
        Проверяет, активен ли процесс
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            True если процесс активен, False иначе
        """
        try:
            response = await self._make_request('GET', f'process-instance/{process_instance_id}')
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_process_definition_by_key(self, process_definition_key: str) -> Optional[Dict[str, Any]]:
        """
        Получает определение процесса по ключу
        
        Args:
            process_definition_key: Ключ определения процесса
            
        Returns:
            Словарь с информацией о процессе или None
        """
        try:
            response = await self._make_request('GET', f'process-definition/key/{process_definition_key}')
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении определения процесса {process_definition_key}: {e}")
            return None

    async def get_process_instances_by_definition_key(self, process_definition_key: str, 
                                              active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Получает экземпляры процессов по ключу определения
        
        Args:
            process_definition_key: Ключ определения процесса
            active_only: Получать только активные процессы
            
        Returns:
            Список экземпляров процессов
        """
        endpoint = 'process-instance'
        params = {
            'processDefinitionKey': process_definition_key
        }
        
        if active_only:
            params['active'] = 'true'
        
        try:
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении экземпляров процесса {process_definition_key}: {e}")
            return []

    async def delete_process_instance(self, process_instance_id: str, 
                              reason: str = "Удален пользователем") -> bool:
        """
        Удаляет экземпляр процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            reason: Причина удаления
            
        Returns:
            True если процесс удален успешно, False иначе
        """
        endpoint = f'process-instance/{process_instance_id}'
        params = {'reason': reason}
        
        try:
            response = await self._make_request('DELETE', endpoint, params=params)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при удалении процесса {process_instance_id}: {e}")
            return False

    async def suspend_process_instance(self, process_instance_id: str) -> bool:
        """
        Приостанавливает экземпляр процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            True если процесс приостановлен успешно, False иначе
        """
        endpoint = f'process-instance/{process_instance_id}/suspended'
        payload = {'suspended': True}
        
        try:
            response = await self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при приостановке процесса {process_instance_id}: {e}")
            return False

    async def activate_process_instance(self, process_instance_id: str) -> bool:
        """
        Активирует экземпляр процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            True если процесс активирован успешно, False иначе
        """
        endpoint = f'process-instance/{process_instance_id}/suspended'
        payload = {'suspended': False}
        
        try:
            response = await self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при активации процесса {process_instance_id}: {e}")
            return False
           
    async def get_task_completion_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные для завершения задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными
        """
        # Получаем переменные задачи
        task_variables = await self.get_task_variables(task_id)
        
        # Получаем информацию о задаче
        task_info = await self.get_task_by_id(task_id)
        if not task_info:
            return task_variables
        
        # Получаем переменные процесса
        process_variables = await self.get_process_instance_variables(task_info.process_instance_id)
        
        # Объединяем переменные
        all_variables = {**process_variables, **task_variables}
        
        return all_variables

    async def get_process_instance_by_id(self, process_instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию об экземпляре процесса по ID
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о процессе или None
        """
        endpoint = f'process-instance/{process_instance_id}'
        
        try:
            logger.info(f"Запрашиваем процесс {process_instance_id} по URL: {urljoin(self.engine_rest_url, endpoint.lstrip('/'))}")
            response = await self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для процесса {process_instance_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Процесс {process_instance_id} не найден (404)")
                return None
            
            response.raise_for_status()
            process_data = response.json()
            logger.info(f"Получены данные процесса {process_instance_id}: {process_data}")
            return process_data
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None

    async def get_history_process_instance_by_id(self, process_instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию об историческом экземпляре процесса по ID
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о процессе или None
        """
        endpoint = f'history/process-instance/{process_instance_id}'
        
        try:
            logger.info(f"Запрашиваем исторический процесс {process_instance_id} по URL: {urljoin(self.engine_rest_url, endpoint.lstrip('/'))}")
            response = await self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для исторического процесса {process_instance_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Исторический процесс {process_instance_id} не найден (404)")
                return None
            
            response.raise_for_status()
            process_data = response.json()
            logger.info(f"Получены данные исторического процесса {process_instance_id}: {process_data}")
            return process_data
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении исторического процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None

    async def get_completed_tasks_grouped(self, assignee: str = None) -> List[Union[CamundaHistoryTask, 'GroupedHistoryTask']]:
        """
        Получает завершенные задачи с группировкой multi-instance задач
        
        Args:
            assignee: Фильтр по пользователю (опционально)
            
        Returns:
            Список завершенных задач (сгруппированные + обычные)
        """
        try:
            # Получаем все завершенные задачи
            endpoint = 'history/task'
            params = {
                'finished': 'true',
                'sortBy': 'endTime',
                'sortOrder': 'desc'
            }
            
            if assignee:
                params['taskAssignee'] = assignee
            
            response = await self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            tasks_data = response.json()
            
            # Группируем задачи по process_instance_id
            process_groups = {}
            
            for task_data in tasks_data:
                process_id = task_data.get('processInstanceId')
                
                if process_id not in process_groups:
                    process_groups[process_id] = []
                
                process_groups[process_id].append(task_data)
            
            # Создаем группированные и обычные задачи
            from models import GroupedHistoryTask, UserTaskInfo
            
            result_tasks = []
            
            for process_id, tasks in process_groups.items():
                # Если несколько задач с одинаковым именем и процессом - это multi-instance
                if len(tasks) > 1 and self._is_multi_instance_group(tasks):
                    # Создаем группированную задачу
                    first_task = tasks[0]
                    
                    # Получаем переменные процесса для дополнительной информации
                    try:
                        # Читаем ВСЕ переменные для обратной совместимости
                        process_variables_new = await self.get_history_process_instance_variables_by_name(
                            process_id, 
                            ['taskDescription', 'dueDate', 'assigneeList', 'userComments', 'userCompletionDates', 'userStatus', 'userCompleted']
                        )
                        
                        # Пытаемся прочитать старые переменные
                        process_variables_old = await self.get_history_process_instance_variables_by_name(
                            process_id,
                            ['reviewComments', 'reviewDates', 'reviewStatus']
                        )
                        
                        # Объединяем переменные
                        process_variables = {**process_variables_new, **process_variables_old}
                    except:
                        process_variables = {}
                    
                    # Создаем список подзадач для пользователей
                    user_tasks = []
                    completed_count = 0
                    
                    earliest_start = None
                    latest_end = None
                    total_duration = 0
                    
                    for task_data in tasks:
                        assignee = task_data.get('assignee', 'Не назначен')
                        end_time = task_data.get('endTime')
                        start_time = task_data.get('startTime')
                        duration = task_data.get('duration', 0)
                        
                        # Определяем статус
                        delete_reason = task_data.get('deleteReason')
                        status = 'completed' if delete_reason == 'completed' else 'cancelled'
                        
                        if status == 'completed':
                            completed_count += 1
                        
                        # Обновляем временные рамки
                        if start_time:
                            if not earliest_start or start_time < earliest_start:
                                earliest_start = start_time
                        
                        if end_time:
                            if not latest_end or end_time > latest_end:
                                latest_end = end_time
                        
                        total_duration += duration if duration else 0
                        
                        # Получаем комментарий пользователя из переменных
                        try:
                            # Используем новые модели для правильной обработки JSON
                            from models import ProcessVariables
                            process_vars = ProcessVariables(**process_variables)
                            user_info = process_vars.get_user_info(assignee)
                            comment = user_info['comment'] if user_info else None
                            review_date = user_info['completion_date'] if user_info else end_time
                            
                            # Если комментарий не найден, пробуем прочитать из старых переменных
                            if not comment and 'reviewComments' in process_variables:
                                try:
                                    import json
                                    review_comments_str = process_variables.get('reviewComments', '{}')
                                    if isinstance(review_comments_str, str):
                                        review_comments = json.loads(review_comments_str)
                                    else:
                                        review_comments = review_comments_str
                                    comment = review_comments.get(assignee)
                                except:
                                    pass
                                    
                        except Exception as e:
                            logger.warning(f"Не удалось получить комментарий для {assignee}: {e}")
                            comment = None
                            review_date = end_time
                        
                        user_tasks.append(UserTaskInfo(
                            task_id=task_data['id'],
                            assignee=assignee,
                            start_time=start_time or '',
                            end_time=end_time,
                            duration=duration,
                            status=status,
                            comment=comment,
                            review_date=review_date
                        ))
                    
                    # Создаем группированную задачу
                    grouped_task = GroupedHistoryTask(
                        process_instance_id=process_id,
                        name=first_task.get('name', ''),
                        description=process_variables.get('taskDescription') or first_task.get('description'),
                        process_definition_key=first_task.get('processDefinitionKey', ''),
                        process_definition_id=first_task.get('processDefinitionId', ''),
                        priority=first_task.get('priority', 50),
                        due=process_variables.get('dueDate') or first_task.get('due'),
                        start_time=earliest_start or '',
                        end_time=latest_end,
                        duration=total_duration,
                        total_users=len(tasks),
                        completed_users=completed_count,
                        user_tasks=user_tasks,
                        is_multi_instance=True
                    )
                    
                    result_tasks.append(grouped_task)
                else:
                    # Обычная задача - создаем CamundaHistoryTask
                    for task_data in tasks:
                        history_task = CamundaHistoryTask(
                            id=task_data['id'],
                            process_definition_key=task_data['processDefinitionKey'],
                            process_definition_id=task_data['processDefinitionId'],
                            process_instance_id=task_data['processInstanceId'],
                            execution_id=task_data.get('executionId', ''),
                            activity_instance_id=task_data.get('activityInstanceId', ''),
                            name=task_data.get('name', ''),
                            description=task_data.get('description'),
                            delete_reason=task_data.get('deleteReason'),
                            owner=task_data.get('owner'),
                            assignee=task_data.get('assignee'),
                            start_time=task_data.get('startTime', ''),
                            end_time=task_data.get('endTime'),
                            duration=task_data.get('duration'),
                            task_definition_key=task_data.get('taskDefinitionKey', ''),
                            priority=task_data.get('priority', 50),
                            due=task_data.get('due'),
                            parent_task_id=task_data.get('parentTaskId'),
                            follow_up=task_data.get('followUp'),
                            tenant_id=task_data.get('tenantId'),
                            removal_time=task_data.get('removalTime'),
                            root_process_instance_id=task_data.get('rootProcessInstanceId')
                        )
                        result_tasks.append(history_task)
            
            return result_tasks
            
        except Exception as e:
            logger.error(f"Ошибка при получении сгруппированных завершенных задач: {e}", exc_info=True)
            return []

    def _is_multi_instance_group(self, tasks: List[Dict]) -> bool:
        """
        Проверяет, являются ли задачи частью multi-instance процесса
        
        Args:
            tasks: Список задач для проверки
            
        Returns:
            True если это multi-instance группа
        """
        if len(tasks) < 2:
            return False
        
        # Проверяем, что все задачи имеют одинаковое имя и task_definition_key
        first_name = tasks[0].get('name')
        first_key = tasks[0].get('taskDefinitionKey')
        
        for task in tasks[1:]:
            if task.get('name') != first_name or task.get('taskDefinitionKey') != first_key:
                return False
        
        return True

    async def get_history_task_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные исторической задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными
        """
        try:
            endpoint = f'history/variable-instance?taskIdIn={task_id}'
            response = await self._make_request('GET', endpoint)
            response.raise_for_status()
            
            variables_data = response.json()
            variables = {}
            
            for var in variables_data:
                var_name = var.get('name')
                var_value = var.get('value')
                variables[var_name] = var_value
            
            return variables
            
        except Exception as e:
            logger.error(f"Ошибка при получении переменных исторической задачи {task_id}: {e}")
            return {}
    
    async def get_processes_by_creator(self, creator_username: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Получает процессы, созданные конкретным пользователем
        
        Использует оптимизированный подход с фильтрацией через Camunda REST API
        
        Args:
            creator_username: Имя пользователя-создателя
            active_only: Получать только активные процессы
            
        Returns:
            Список процессов
        """
        try:
            logger.info(f"Поиск процессов создателя: {creator_username}, active_only: {active_only}")
            
            if active_only:
                # Для активных процессов используем endpoint /process-instance
                endpoint = 'process-instance'
                
                # Получаем все активные процессы
                response = await self._make_request('GET', endpoint)
                response.raise_for_status()
                all_processes = response.json()
                
                logger.info(f"Найдено активных процессов всего: {len(all_processes)}")
                
                # Если процессов нет, возвращаем пустой список
                if not all_processes:
                    logger.info("Активных процессов не найдено")
                    return []
                
                # Фильтруем по создателю, получая переменные только для нужных процессов
                creator_processes = []
                
                # Оптимизация: проверяем переменные пакетами для уменьшения количества запросов
                for process in all_processes:
                    process_id = process['id']
                    
                    try:
                        # Получаем только переменную processCreator, если она есть
                        variables = await self.get_process_instance_variables_by_name(
                            process_id, 
                            ['processCreator']
                        )
                        process_creator = variables.get('processCreator', '')
                        
                        logger.debug(f"Процесс {process_id}: processCreator = '{process_creator}', ищем '{creator_username}'")
                        
                        if process_creator == creator_username:
                            logger.info(f"Найден процесс создателя: {process_id}")
                            # Получаем расширенную информацию о процессе
                            expanded_process = await self.get_process_with_variables(process_id, is_active=True)
                            if expanded_process:
                                creator_processes.append(expanded_process)
                            else:
                                # Если не удалось получить расширенную информацию, добавляем базовую
                                creator_processes.append(process)
                        elif process_creator:
                            logger.debug(f"Процесс {process_id} создан другим пользователем: '{process_creator}'")
                        else:
                            logger.debug(f"Процесс {process_id} не имеет переменной processCreator")
                            
                    except Exception as e:
                        logger.warning(f"Не удалось получить переменные для процесса {process_id}: {e}")
                
                logger.info(f"Найдено процессов создателя '{creator_username}': {len(creator_processes)}")
                return creator_processes
                
            else:
                # Для исторических процессов используем более эффективный endpoint
                # /history/variable-instance с фильтрацией по имени и значению переменной
                endpoint = 'history/variable-instance'
                params = {
                    'variableName': 'processCreator',
                    'variableValue': creator_username,
                    'deserializeValues': 'true'
                }
                
                try:
                    response = await self._make_request('GET', endpoint, params=params)
                    response.raise_for_status()
                    variable_instances = response.json()
                    
                    # Получаем уникальные ID процессов из переменных
                    process_ids = set()
                    for var_instance in variable_instances:
                        process_instance_id = var_instance.get('processInstanceId')
                        if process_instance_id:
                            process_ids.add(process_instance_id)
                    
                    if not process_ids:
                        logger.info("Завершенных процессов создателя не найдено")
                        return []
                    
                    # Получаем информацию о процессах по их ID и ПРОВЕРЯЕМ, ЧТО ОНИ ЗАВЕРШЕНЫ
                    creator_processes = []
                    for process_id in process_ids:
                        try:
                            # Получаем информацию о процессе из истории
                            history_endpoint = f'history/process-instance/{process_id}'
                            process_response = await self._make_request('GET', history_endpoint)
                            process_response.raise_for_status()
                            process_data = process_response.json()
                            
                            # ВАЖНО: Проверяем, что процесс действительно завершен (имеет endTime)
                            if process_data and process_data.get('endTime'):
                                # Получаем расширенную информацию о процессе
                                expanded_process = await self.get_process_with_variables(process_id, is_active=False)
                                if expanded_process:
                                    creator_processes.append(expanded_process)
                                else:
                                    creator_processes.append(process_data)
                            else:
                                # Процесс еще активен, пропускаем его (он будет в списке активных)
                                logger.debug(f"Процесс {process_id} еще активен (нет endTime), пропускаем в завершенных")
                        except Exception as e:
                            logger.warning(f"Не удалось получить информацию о процессе {process_id}: {e}")
                    
                    logger.info(f"Найдено завершенных процессов создателя '{creator_username}': {len(creator_processes)}")
                    return creator_processes
                    
                except httpx.HTTPError as e:
                    logger.error(f"Ошибка при получении исторических процессов создателя {creator_username}: {e}")
                    return []
            
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении процессов создателя {creator_username}: {e}")
            return []

    async def start_document_signing_process(self, document_id: str, document_name: str, 
                                    signer_list: List[str], business_key: str = None,
                                    role_names: List[str] = None,
                                    creator_username: Optional[str] = None,
                                    due_date: Optional[str] = None,
                                    task_name: Optional[str] = None,  # ДОБАВИТЬ
                                    task_description: Optional[str] = None) -> Optional[str]:  # ДОБАВИТЬ
        """Запускает процесс подписания документа
        
        Args:
            document_id: ID документа
            document_name: Название документа
            signer_list: Список пользователей-подписантов
            business_key: Бизнес-ключ процесса
            role_names: Список названий ролей для предоставления доступа (опционально)
            creator_username: Имя пользователя-создателя
            due_date: Срок исполнения в формате ISO (YYYY-MM-DDTHH:MM:SS.fff+0000)
            task_name: Название задачи  # ДОБАВИТЬ
            task_description: Описание задачи  # ДОБАВИТЬ
        """
        try:
            # Подготавливаем переменные в правильном формате для Camunda
            process_variables = {
                'documentId': {
                    'value': document_id,
                    'type': 'String'
                },
                'documentName': {
                    'value': document_name,
                    'type': 'String'
                },
                # ДОБАВИТЬ taskName и taskDescription
                **({'taskName': {
                    'value': task_name or document_name,
                    'type': 'String'
                }} if task_name else {}),
                **({'taskDescription': {
                    'value': task_description or '',
                    'type': 'String'
                }} if task_description else {}),
                # ДОБАВИТЬ dueDate если передан
                **({'dueDate': {
                    'value': due_date,
                    'type': 'Date'
                }} if due_date else {}),
                'signerList': {
                    'value': json.dumps(signer_list),
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.ArrayList'
                    }
                },
                'signedCount': {
                    'value': 0,
                    'type': 'Integer'
                },
                'signatures': {
                    'value': '{}',
                    'type': 'String'
                },
                # Информация о создателе
                'processCreator': {
                    'value': creator_username or 'system',
                    'type': 'String'
                },
                'creatorName': {
                    'value': creator_username or 'Система',
                    'type': 'String'
                },
            }
            
            data = {
                'variables': process_variables,
                'businessKey': business_key or f"signing_{document_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            }
            logger.info(f'Отправляем переменные процесса подписания: {process_variables}')
            logger.info(f'documentId: {document_id}, documentName: {document_name}')
            response = await self._make_request('POST', 'process-definition/key/DocumentSigningProcess/start', json=data)
            
            if response.status_code == 200:
                result = response.json()
                process_id = result['id']
                logger.info(f"Процесс подписания запущен: {process_id}")
                
                # Предоставляем доступ к документу выбранным ролям (если указаны)
                if role_names:
                    try:                    
                        logger.info(f'Предоставляем доступ к документу {document_id} ролям: {role_names}')
                        access_granted = await document_access_manager.grant_document_access_to_roles(
                            document_id=document_id,
                            document_label=document_name,
                            role_names=role_names
                        )
                        
                        if access_granted:
                            logger.info(f'Доступ к документу {document_id} успешно предоставлен ролям {role_names}')
                        else:
                            logger.warning(f'Не удалось предоставить доступ к документу {document_id} ролям')
                            
                    except Exception as e:
                        logger.error(f'Ошибка при предоставлении доступа к документу: {e}', exc_info=True)
                        # Не прерываем выполнение, т.к. процесс уже запущен
                else:
                    logger.warning(f'Роли не выбраны - доступ к документу {document_id} не будет предоставлен автоматически')
                
                return process_id
            else:
                logger.error(f"Ошибка запуска процесса подписания: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при запуске процесса подписания: {e}")
            return None

    async def complete_signing_task(self, task_id: str, signature_data: str, 
                            certificate_info: Dict[str, Any], comment: str = "") -> bool:
        """Завершает задачу подписания"""
        try:
            variables = {
                'signed': True,
                'signatureData': signature_data,
                'certificateInfo': json.dumps(certificate_info, ensure_ascii=False),
                'signatureComment': comment,
                'signatureDate': datetime.now().isoformat()
            }
            
            data = {
                'variables': self._prepare_variables(variables)
            }
            
            response = await self._make_request('POST', f'task/{task_id}/complete', json=data)
            
            if response.status_code == 204:
                logger.info(f"Задача подписания {task_id} завершена")
                return True
            else:
                logger.error(f"Ошибка завершения задачи подписания: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при завершении задачи подписания: {e}")
            return False

    async def start_document_review_process_multi_instance(self, 
                                               document_id: str,
                                               document_name: str,
                                               document_content: str,
                                               assignee_list: List[str],
                                               business_key: Optional[str] = None,
                                               creator_username: Optional[str] = None,
                                               due_date: Optional[str] = None,
                                               role_names: Optional[List[str]] = None,
                                               process_definition_key: Optional[str] = None) -> Optional[str]:
        """
        Запускает процесс ознакомления с документом для нескольких пользователей
        с использованием Multi-Instance (один процесс, несколько параллельных задач)
        
        Args:
            document_id: ID документа в Mayan EDMS
            document_name: Название документа
            document_content: Содержимое документа
            assignee_list: Список пользователей для ознакомления
            business_key: Бизнес-ключ процесса
            creator_username: Имя пользователя-создателя
            due_date: Срок исполнения в формате ISO (YYYY-MM-DDTHH:MM:SS.fff+0000)
            role_names: Список названий ролей для предоставления доступа (опционально)
            process_definition_key: Ключ определения процесса (если не указан, будет выполнен поиск)
            
        Returns:
            ID экземпляра процесса или None при ошибке
        """
        try:
            # Определяем ключ процесса
            process_key = process_definition_key
            
            # Если ключ не передан, пытаемся найти процесс по паттерну
            if not process_key:
                logger.info("Ключ процесса не указан, выполняем поиск по паттерну 'DocumentReview'")
                process_key = await self.find_process_by_name_pattern('DocumentReview')
                if not process_key:
                    # Пробуем альтернативные варианты
                    alternative_keys = ['DocumentReviewProcessMultiInstance', 'DocumentReviewProcess']
                    for alt_key in alternative_keys:
                        exists, _ = await self.validate_process_exists(alt_key)
                        if exists:
                            process_key = alt_key
                            logger.info(f"Найден процесс: {process_key}")
                            break
                    
                    if not process_key:
                        error_msg = "Не удалось найти процесс ознакомления с документом в Camunda"
                        logger.error(error_msg)
                        return None
            else:
                # Проверяем существование указанного процесса
                exists, error_msg = await self.validate_process_exists(process_key)
                if not exists:
                    logger.warning(f"Указанный процесс {process_key} не найден, пытаемся найти альтернативный")
                    # Пытаемся найти альтернативный процесс
                    process_key = await self.find_process_by_name_pattern('DocumentReview')
                    if not process_key:
                        logger.error(f"Не удалось найти процесс ознакомления: {error_msg}")
                        return None
            
            logger.info(f"Используется процесс: {process_key}")
            
            # Подготавливаем переменные для процесса
            process_variables = {
                'taskName': f'Ознакомиться с документом: {document_name}',
                'taskDescription': f'Необходимо ознакомиться с документом: {document_name}\n\nСодержимое:\n{document_content}',
                'priority': 2,
                'dueDate': due_date or '2025-09-29T23:59:59.000+0000',
                'documentName': document_name,
                'documentContent': document_content,
                'mayanDocumentId': document_id,  # Добавляем ID документа
                
                # Multi-Instance переменные - используем тот же формат, что и для signerList
                'assigneeList': {
                    'value': json.dumps(assignee_list),
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.ArrayList'
                    }
                },
                
                # Инициализируем счетчик завершенных ознакомлений
                'completedReviews': 0,
                
                # Инициализируем словари для хранения данных пользователей
                # Используем тип Object с JSON-строкой для HashMap
                'reviewDates': {
                    'value': '{}',
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'reviewComments': {
                    'value': '{}',
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'reviewStatus': {
                    'value': '{}',
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'userCompleted': {
                    'value': '{}',
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                
                # Информация о создателе
                'processCreator': creator_username or 'system',
                'creatorName': creator_username or 'Система',
            }
            
            # Запускаем процесс с Multi-Instance
            process_id = await self.start_process(
                process_definition_key=process_key,
                variables=process_variables,
                business_key=business_key,
                validate=True  # Включаем валидацию
            )
            
            if process_id:
                logger.info(f"Запущен Multi-Instance процесс ознакомления с документом '{document_name}' для {len(assignee_list)} пользователей, ID: {process_id}")
                logger.info(f"Пользователи: {', '.join(assignee_list)}")
                
                # Предоставляем доступ к документу выбранным ролям
                if role_names:
                    try:
                        from services.document_access_manager import document_access_manager
                        logger.info(f'Предоставляем доступ к документу {document_id} ролям: {role_names}')
                        access_granted = await document_access_manager.grant_document_access_to_roles(
                            document_id=document_id,
                            document_label=document_name,
                            role_names=role_names
                        )
                        
                        if access_granted:
                            logger.info(f'Доступ к документу {document_id} успешно предоставлен ролям {role_names}')
                        else:
                            logger.warning(f'Не удалось предоставить доступ к документу {document_id} ролям')
                            
                    except Exception as e:
                        logger.error(f'Ошибка при предоставлении доступа к документу: {e}', exc_info=True)
                        # Не прерываем выполнение, т.к. процесс уже запущен
                else:
                    logger.info(f'Роли не выбраны - доступ к документу {document_id} не будет предоставлен автоматически')
            
            return process_id
            
        except Exception as e:
            logger.error(f"Ошибка при запуске Multi-Instance процесса ознакомления: {e}", exc_info=True)
            return None
    
    async def get_multi_instance_task_progress(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает информацию о прогрессе выполнения Multi-Instance задачи
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о прогрессе
        """
        return await self.get_task_progress(process_instance_id)

    async def get_process_with_variables(self, process_id: str, is_active: bool = True) -> Dict[str, Any]:
        """
        Получает процесс вместе с его переменными для отображения
        
        Args:
            process_id: ID процесса
            is_active: Активен ли процесс
            
        Returns:
            Словарь с информацией о процессе и его переменными
        """
        try:
            # Получаем базовую информацию о процессе
            if is_active:
                endpoint = f'process-instance/{process_id}'
                response = await self._make_request('GET', endpoint)
                response.raise_for_status()
                process_data = response.json()
                
                # Получаем переменные процесса
                process_variables = await self.get_process_instance_variables_by_name(
                    process_id,
                    ['taskName', 'taskDescription', 'documentName', 'assigneeList', 
                     'totalUsers', 'completedTasks', 'processNotes', 'dueDate',
                     'processCreator', 'creatorName']
                )
            else:
                # Для исторических процессов
                endpoint = f'history/process-instance/{process_id}'
                response = await self._make_request('GET', endpoint)
                response.raise_for_status()
                process_data = response.json()
                
                # Получаем исторические переменные
                process_variables = await self.get_history_process_instance_variables_by_name(
                    process_id,
                    ['taskName', 'taskDescription', 'documentName', 'assigneeList',
                     'totalUsers', 'completedTasks', 'processNotes', 'dueDate',
                     'processCreator', 'creatorName']
                )
            
            # Добавляем переменные к данным процесса
            process_data['variables'] = process_variables
            
            # Для активных процессов получаем прогресс, если это Multi-Instance
            if is_active:
                try:
                    progress_info = await self.get_multi_instance_task_progress(process_id)
                    process_data['progress'] = progress_info
                except:
                    process_data['progress'] = None
            
            return process_data
            
        except Exception as e:
            logger.error(f"Ошибка при получении процесса {process_id} с переменными: {e}")
            return {}

    async def validate_process_exists(self, process_definition_key: str) -> tuple[bool, Optional[str]]:
        """
        Проверяет существование процесса в Camunda
        
        Args:
            process_definition_key: Ключ определения процесса
            
        Returns:
            Кортеж (существует ли процесс, сообщение об ошибке или None)
        """
        try:
            process_def = await self.get_process_definition_by_key(process_definition_key)
            if process_def:
                logger.info(f"Процесс {process_definition_key} найден в Camunda (версия {process_def.get('version', 'unknown')})")
                return True, None
            else:
                error_msg = f"Процесс {process_definition_key} не найден в Camunda"
                logger.warning(error_msg)
                return False, error_msg
        except Exception as e:
            error_msg = f"Ошибка при проверке существования процесса {process_definition_key}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def find_process_by_name_pattern(self, pattern: str) -> Optional[str]:
        """
        Ищет процесс по паттерну в названии
        
        Args:
            pattern: Паттерн для поиска (например, 'DocumentReview')
            
        Returns:
            Ключ процесса или None
        """
        try:
            process_definitions = await self.get_active_process_definitions()
            for process_def in process_definitions:
                if pattern.lower() in process_def.name.lower() or pattern.lower() in process_def.key.lower():
                    logger.info(f"Найден процесс по паттерну '{pattern}': {process_def.key} ({process_def.name})")
                    return process_def.key
            logger.warning(f"Процесс с паттерном '{pattern}' не найден")
            return None
        except Exception as e:
            logger.error(f"Ошибка при поиске процесса по паттерну '{pattern}': {e}")
            return None


async def create_camunda_client() -> CamundaClient:
    """
    Создает клиент Camunda с настройками из конфигурации
    
    Returns:
        Настроенный экземпляр CamundaClient
        
    Raises:
        ValueError: Если не настроены обязательные параметры
    """
    from config.settings import config
    
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
        verify_ssl=config.camunda_verify_ssl
    )