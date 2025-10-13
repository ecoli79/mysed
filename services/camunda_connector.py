import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import json
from typing import List, Optional, Dict, Any, Union
from urllib.parse import urljoin
import os

# for SSL warnings disable
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    """Клиент для работы с Camunda Community Edition 7.22 REST API"""
    
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
        self.session = requests.Session()
        self.session.verify = verify_ssl
        
        # Настраиваем аутентификацию
        if token:
            # Используем токен
            self.session.headers.update({
                'Authorization': f'{token_type} {token}'
            })
            self.auth_type = 'token'
        elif username and password:
            # Используем Basic Auth
            self.auth = HTTPBasicAuth(username, password)
            self.session.auth = self.auth
            self.auth_type = 'basic'
        else:
            raise ValueError("Необходимо указать либо username/password, либо token")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Выполняет HTTP запрос к Camunda API"""
        url = urljoin(self.engine_rest_url, endpoint.lstrip('/'))
        
        # Устанавливаем Content-Type только если передаем JSON
        if 'json' in kwargs:
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        
        response = self.session.request(method, url, **kwargs, verify=False)
        return response
    
    def deploy_process(self, deployment_name: str, bpmn_file_path: str, 
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
            
            # Выполняем запрос напрямую через session
            url = urljoin(self.engine_rest_url, endpoint.lstrip('/'))
            response = self.session.post(url, data=data, files=files, verify=False)
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
        except requests.RequestException as e:
            logger.error(f"Ошибка при развертывании процесса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус ответа: {e.response.status_code}")
                logger.error(f"Текст ответа: {e.response.text}")
            return None
    
    def get_active_process_definitions(self) -> List[CamundaProcessDefinition]:
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
            response = self._make_request('GET', endpoint, params=params)
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
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении определений процессов: {e}")
            return []
    
    def get_task_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными задачи
        """
        endpoint = f'task/{task_id}/variables'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            variables_data = response.json()
            variables = {}
            
            for var_name, var_data in variables_data.items():
                if 'value' in var_data:
                    variables[var_name] = var_data['value']
            
            return variables
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении переменных задачи {task_id}: {e}")
            return {}
    
    def get_process_instance_variables(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает переменные экземпляра процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с переменными процесса
        """
        endpoint = f'process-instance/{process_instance_id}/variables'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            variables_data = response.json()
            variables = {}
            
            for var_name, var_data in variables_data.items():
                if 'value' in var_data:
                    variables[var_name] = var_data['value']
            return variables
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении переменных процесса {process_instance_id}: {e}")
            return {}
    
    def get_process_instance_variables_by_name(self, process_instance_id: str, variable_names: List[str]) -> Dict[str, Any]:
        """
        Получает конкретные переменные экземпляра процесса по именам
        
        Args:
            process_instance_id: ID экземпляра процесса
            variable_names: Список имен переменных для получения
            
        Returns:
            Словарь с переменными процесса
        """
        endpoint = f'process-instance/{process_instance_id}/variables'
        params = {'deserializeValues': 'true'}
        
        # Добавляем фильтр по именам переменных
        if variable_names:
            params['variableNames'] = ','.join(variable_names)
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            variables_data = response.json()
            
            variables = {}
            
            for var_name, var_data in variables_data.items():
                if 'value' in var_data:
                    variables[var_name] = var_data['value']
            return variables
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении переменных процесса {process_instance_id}: {e}")
            return {}
    
    def assign_task(self, task_id: str, assignee: str) -> bool:
        """
        Назначает задачу пользователю
        
        Args:
            task_id: ID задачи
            assignee: Имя пользователя для назначения
            
        Returns:
            True если назначение прошло успешно, False иначе
        """
        endpoint = f'task/{task_id}/assignee'
        
        payload = {'assignee': assignee}
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при назначении задачи {task_id} пользователю {assignee}: {e}")
            return False
    
    def get_user_tasks(self, assignee: str, active_only: bool = True, fetch_variables: bool = True) -> List[Union[CamundaTask, CamundaHistoryTask]]:
        """
        Получает список задач назначенных пользователю
        
        Args:
            assignee: Имя пользователя
            active_only: Получать только активные задачи
            fetch_variables: Получать переменные задач и процессов для description и dueDate
            
        Returns:
            Список задач пользователя
        """
        if active_only:
            endpoint = 'task'
            params = {
                'assignee': assignee,
                'active': 'true',
                'sortBy': 'created',
                'sortOrder': 'desc'
            }
        else:
            endpoint = 'history/task'
            params = {
                'assignee': assignee,
                'sortBy': 'startTime',
                'sortOrder': 'desc'
            }
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            tasks_data = response.json()
            
            if active_only:
                tasks = []
                for task_data in tasks_data:
                    # Логируем полный ответ API для отладки
                    logger.debug(f"Полный ответ API для задачи {task_data['id']}: {task_data}")
                    
                    # Инициализируем значения по умолчанию
                    due_date = task_data.get('due')
                    description = task_data.get('description')
                    
                    # Получаем переменные только если это необходимо
                    if fetch_variables:
                        try:
                            # Получаем переменные задачи
                            task_variables = self.get_task_variables(task_data['id'])                        
                            # Также пытаемся получить переменные процесса
                            process_variables = self.get_process_instance_variables_by_name(
                                task_data['processInstanceId'], 
                                ['dueDate', 'taskName', 'taskDescription', 'priority', 'category', 'tags']
                            )
                                                    
                            if 'dueDate' in process_variables:
                                due_date = process_variables['dueDate']
                            elif 'dueDate' in task_variables:
                                due_date = task_variables['dueDate']
                            
                            if 'taskDescription' in process_variables:
                                description = process_variables['taskDescription']
                                logger.debug(f"Используем taskDescription из переменных процесса: '{description}' (тип: {type(description)})")
                            elif 'description' in task_variables:
                                description = task_variables['description']
                        except Exception as e:
                            # Логируем ошибку, но продолжаем обработку задачи
                            logger.warning(f"Не удалось получить переменные для задачи {task_data['id']}: {e}")
                            # Используем значения по умолчанию из task_data
                            pass
                       
                    
                    # Создаем объект задачи
                    task = CamundaTask(
                        id=task_data['id'],
                        name=task_data['name'],
                        assignee=task_data.get('assignee'),
                        start_time=task_data['created'],
                        due=due_date,
                        follow_up=task_data.get('followUp'),
                        delegation_state=task_data.get('delegationState'),
                        description=description,
                        execution_id=task_data['executionId'],
                        owner=task_data.get('owner'),
                        parent_task_id=task_data.get('parentTaskId'),
                        priority=task_data['priority'],
                        process_definition_id=task_data['processDefinitionId'],
                        process_instance_id=task_data['processInstanceId'],
                        task_definition_key=task_data['taskDefinitionKey'],
                        case_execution_id=task_data.get('caseExecutionId'),
                        case_instance_id=task_data.get('caseInstanceId'),
                        case_definition_id=task_data.get('caseDefinitionId'),
                        suspended=task_data['suspended'],
                        form_key=task_data.get('formKey'),
                        tenant_id=task_data.get('tenantId')
                    )
                    tasks.append(task)
                
                return tasks
            else:
                history_tasks = []
                for task_data in tasks_data:
                    # Инициализируем значения по умолчанию
                    due_date = task_data.get('due')
                    description = task_data.get('description')
                    
                    # Для завершенных задач переменные могут быть недоступны
                    # Пытаемся получить их, но не критично если не получится
                    if fetch_variables:
                        try:
                            # Получаем переменные задачи
                            task_variables = self.get_task_variables(task_data['id'])

                            # Также пытаемся получить переменные процесса
                            process_variables = self.get_process_instance_variables_by_name(
                                task_data['processInstanceId'], 
                                ['dueDate', 'taskName', 'taskDescription', 'priority', 'category', 'tags']
                            )
                          
                            if 'dueDate' in process_variables:
                                due_date = process_variables['dueDate']
                            elif 'dueDate' in task_variables:
                                due_date = task_variables['dueDate']
                        
                            if 'taskDescription' in process_variables:
                                description = process_variables['taskDescription']
                            elif 'description' in task_variables:
                                description = task_variables['description']
                        except Exception as e:
                            # Логируем ошибку, но продолжаем обработку задачи
                            logger.warning(f"Не удалось получить переменные для завершенной задачи {task_data['id']}: {e}")
                            # Используем значения по умолчанию из task_data
                            pass
                    
                    history_task = CamundaHistoryTask(
                        id=task_data['id'],
                        process_definition_key=task_data['processDefinitionKey'],
                        process_definition_id=task_data['processDefinitionId'],
                        process_instance_id=task_data['processInstanceId'],
                        execution_id=task_data['executionId'],
                        case_definition_key=task_data.get('caseDefinitionKey'),
                        case_definition_id=task_data.get('caseDefinitionId'),
                        case_instance_id=task_data.get('caseInstanceId'),
                        case_execution_id=task_data.get('caseExecutionId'),
                        activity_instance_id=task_data['activityInstanceId'],
                        name=task_data['name'],
                        description=description,
                        delete_reason=task_data.get('deleteReason'),
                        owner=task_data.get('owner'),
                        assignee=task_data.get('assignee'),
                        start_time=task_data['startTime'],
                        end_time=task_data.get('endTime'),
                        duration=task_data.get('duration'),
                        task_definition_key=task_data['taskDefinitionKey'],
                        priority=task_data['priority'],
                        due=due_date,
                        parent_task_id=task_data.get('parentTaskId'),
                        follow_up=task_data.get('followUp'),
                        tenant_id=task_data.get('tenantId'),
                        removal_time=task_data.get('removalTime'),
                        root_process_instance_id=task_data.get('rootProcessInstanceId')
                    )
                    history_tasks.append(history_task)
                
                return history_tasks
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении задач пользователя {assignee}: {e}")
            return []
    
    def get_task(self, task: Union[CamundaTask, CamundaHistoryTask]) -> Optional[CamundaTask]:
        """
        Получает информацию о конкретной активной задаче по её ID.
        
        Args:
            task_id: ID задачи
            
        Returns:
            Объект CamundaTask или None, если задача не найдена или произошла ошибка
        """
        if isinstance(task,CamundaTask):
            endpoint = f'task/{task.id}'
        elif isinstance(task,CamundaHistoryTask):
            endpoint = f'task/{task.id}'

        try:
            response = self._make_request('GET', endpoint)
            if response.status_code == 404:
                logger.warning(f"Задача с ID {task.id} не найдена.")
                return None
            response.raise_for_status()
            
            task_data = response.json()
            
            return CamundaTask(
                id=task_data['id'],
                name=task_data['name'],
                assignee=task_data.get('assignee'),
                start_time=task_data['created'],
                due=task_data.get('due'),
                follow_up=task_data.get('followUp'),
                delegation_state=task_data.get('delegationState'),
                description=task_data.get('description'),
                execution_id=task_data['executionId'],
                owner=task_data.get('owner'),
                parent_task_id=task_data.get('parentTaskId'),
                priority=task_data['priority'],
                process_definition_id=task_data['processDefinitionId'],
                process_instance_id=task_data['processInstanceId'],
                task_definition_key=task_data['taskDefinitionKey'],
                case_execution_id=task_data.get('caseExecutionId'),
                case_instance_id=task_data.get('caseInstanceId'),
                case_definition_id=task_data.get('caseDefinitionId'),
                suspended=task_data['suspended'],
                form_key=task_data.get('formKey'),
                tenant_id=task_data.get('tenantId')
            )
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении задачи {task.id}: {e}")
            return None

    def complete_task(self, task_id: str, variables: Optional[Dict[str, Any]] = None) -> bool:
        """
        Завершает задачу
        
        Args:
            task_id: ID задачи
            variables: Переменные для передачи в процесс
            
        Returns:
            True если задача завершена успешно, False иначе
        """
        endpoint = f'task/{task_id}/complete'
        
        payload = {}
        if variables:
            payload['variables'] = variables
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False
    
    def start_process(self, process_definition_key: str, 
                assignee_list: List[str],
                due_date: Optional[str] = None,
                process_notes: Optional[str] = None,
                additional_variables: Optional[Dict[str, Any]] = None,
                business_key: Optional[str] = None,
                creator_username: Optional[str] = None) -> Optional[str]:
        """
        Универсальный метод для запуска любых процессов
        
        Args:
            process_definition_key: Ключ определения процесса (каждый процесс свой BPMN)
            assignee_list: Список пользователей (может быть один)
            due_date: Дата до которой должна быть завершена задача (ISO format)
            process_notes: Заметки связанные с процессом/документом
            additional_variables: Дополнительные переменные специфичные для процесса
            business_key: Бизнес-ключ процесса
            
        Returns:
            ID экземпляра процесса или None в случае ошибки
        """
        endpoint = f'process-definition/key/{process_definition_key}/start'
        
        # Только базовые переменные, которые нужны всем процессам
        process_variables = {
            # Список пользователей
            'assigneeList': {
                'value': json.dumps(assignee_list),
                'type': 'Object',
                'valueInfo': {
                    'serializationDataFormat': 'application/json',
                    'objectTypeName': 'java.util.ArrayList'
                }
            },
            
            # Общее количество пользователей
            'totalUsers': {
                'value': len(assignee_list),
                'type': 'Integer'
            },
            
            # Счетчик завершенных задач
            'completedTasks': {
                'value': 0,
                'type': 'Integer'
            },
            
            # Дата дедлайна
            'dueDate': {
                'value': due_date or '',
                'type': 'String'
            },
            
            # Общие заметки по процессу
            'processNotes': {
                'value': process_notes or '',
                'type': 'String'
            },
            
            # Словари для хранения данных по пользователям
            'userCompletionDates': {
                'value': '{}',
                'type': 'String'
            },
            
            'userComments': {
                'value': '{}',
                'type': 'String'
            },
            
            'userStatus': {
                'value': '{}',
                'type': 'String'
            },
            
            'userCompleted': {
                'value': '{}',
                'type': 'String'
            },
            
            # Время создания процесса
            'processStartTime': {
                'value': datetime.now().isoformat(),
                'type': 'String'
            },
            
            # Статус процесса
            'processStatus': {
                'value': 'active',
                'type': 'String'
            },
                    # Информация о создателе процесса
            'processCreator': {
                'value': creator_username or 'system',
                'type': 'String'
            },
            
            'creatorName': {
                'value': creator_username or 'Система',
                'type': 'String'
            },
        }
        
        # Добавляем дополнительные переменные если они есть
        if additional_variables:
            for key, value in additional_variables.items():
                process_variables[key] = self._format_variable(value)
        
        # Подготавливаем payload
        payload = {
            'variables': process_variables
        }
        
        if business_key:
            payload['businessKey'] = business_key
        
        try:
            logger.info(f"Запуск процесса {process_definition_key}")
            logger.info(f"Пользователи: {assignee_list}")
            logger.info(f"Дедлайн: {due_date}")
            logger.info(f"Заметки: {process_notes}")
            logger.info(f"Дополнительные переменные: {list(additional_variables.keys()) if additional_variables else 'нет'}")
            
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            
            result = response.json()
            process_instance_id = result.get('id')
            
            if process_instance_id:
                logger.info(f"Процесс {process_definition_key} успешно запущен. ID: {process_instance_id}")
                
            return process_instance_id
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при запуске процесса {process_definition_key}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_details = e.response.json()
                    logger.error(f"Детали ошибки: {json.dumps(error_details, indent=2)}")
                except:
                    logger.error(f"Текст ответа: {e.response.text}")
            return None

    def _format_variable(self, value: Any) -> Dict[str, Any]:
        """Форматирует переменную в формат Camunda API"""
        if isinstance(value, dict) and 'value' in value and 'type' in value:
            return value
        elif isinstance(value, str):
            return {'value': value, 'type': 'String'}
        elif isinstance(value, bool):
            return {'value': value, 'type': 'Boolean'}
        elif isinstance(value, int):
            return {'value': value, 'type': 'Integer'}
        elif isinstance(value, float):
            return {'value': value, 'type': 'Double'}
        elif isinstance(value, (list, dict)):
            return {'value': json.dumps(value), 'type': 'String'}
        else:
            return {'value': str(value), 'type': 'String'}


    def set_process_variable(self, process_instance_id: str, variable_name: str, 
                           variable_value: Any, variable_type: str = "String") -> bool:
        """
        Устанавливает переменную процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            variable_name: Имя переменной
            variable_value: Значение переменной
            variable_type: Тип переменной (String, Number, Boolean, Object, Date)
            
        Returns:
            True если переменная установлена успешно, False иначе
        """
        endpoint = f'process-instance/{process_instance_id}/variables/{variable_name}'
        
        # Подготавливаем переменную в формате Camunda API
        if variable_type == "Date" and isinstance(variable_value, str):
            # Для дат используем ISO формат
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
            response = self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при установке переменной {variable_name}: {e}")
            return False

    def set_multiple_process_variables(self, process_instance_id: str, 
                                     variables: Dict[str, Any]) -> bool:
        """
        Устанавливает несколько переменных процесса одновременно
        
        Args:
            process_instance_id: ID экземпляра процесса
            variables: Словарь переменных {имя: значение}
            
        Returns:
            True если все переменные установлены успешно, False иначе
        """
        endpoint = f'process-instance/{process_instance_id}/variables'
        
        # Подготавливаем переменные в формате Camunda API
        process_variables = {}
        
        for var_name, var_value in variables.items():
            if isinstance(var_value, str):
                process_variables[var_name] = {
                    'value': var_value,
                    'type': 'String'
                }
            elif isinstance(var_value, bool):
                process_variables[var_name] = {
                    'value': var_value,
                    'type': 'Boolean'
                }
            elif isinstance(var_value, (int, float)):
                process_variables[var_name] = {
                    'value': var_value,
                    'type': 'Number'
                }
            elif isinstance(var_value, dict) and 'value' in var_value and 'type' in var_value:
                # Уже в формате Camunda API
                process_variables[var_name] = var_value
            else:
                # Для сложных объектов используем JSON сериализацию
                process_variables[var_name] = {
                    'value': json.dumps(var_value),
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': type(var_value).__name__
                    }
                }
        
        payload = {'modifications': process_variables}
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при установке переменных процесса: {e}")
            return False


    def complete_task_with_user_data(self, task_id: str, 
                                status: str = "completed",
                                comment: Optional[str] = None,
                                review_date: Optional[str] = None) -> bool:
        """
        Завершает задачу и обновляет переменные пользователя напрямую в Python коде
        """
        # Получаем информацию о задаче
        task_info = self.get_task_by_id(task_id)
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
        process_variables_raw = self.get_process_instance_variables(process_instance_id)
        
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
            }
        }
        
        # Обновляем переменные процесса
        if not self.set_multiple_process_variables(process_instance_id, updated_variables):
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
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            
            logger.info(f"Задача {task_id} успешно завершена пользователем {assignee}")
            logger.info(f"Обновлены переменные: userCompleted={process_vars.user_completed.to_dict()}, completedTasks={process_vars.completed_tasks}")
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False

    def complete_task_with_variables(self, task_id: str, 
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
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при завершении задачи {task_id}: {e}")
            return False

    def get_process_instance_history(self, process_instance_id: str) -> List[Dict[str, Any]]:
        """
        Получает историю выполнения экземпляра процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Список событий истории процесса
        """
        endpoint = f'history/process-instance/{process_instance_id}'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении истории процесса {process_instance_id}: {e}")
            return []

     # ===== УНИВЕРСАЛЬНЫЕ ФУНКЦИИ =====
    def start_process_for_multiple_users(self, process_definition_key: str, 
                                       user_list: List[str],
                                       variables: Optional[Dict[str, Any]] = None,
                                       business_key: Optional[str] = None) -> List[str]:
        """
        Универсальная функция для запуска процесса для нескольких пользователей
        
        Args:
            process_definition_key: Ключ определения процесса
            user_list: Список пользователей
            variables: Базовые переменные для всех процессов
            business_key: Базовый бизнес-ключ (будет дополнен именем пользователя)
            
        Returns:
            Список ID экземпляров процессов
        """
        process_ids = []
        
        for user in user_list:
            # Создаем копию переменных для каждого пользователя
            user_variables = variables.copy() if variables else {}
            
            # Добавляем информацию о пользователе
            user_variables['assignee'] = {
                'value': user,
                'type': 'String'
            }
            
            # Для DocumentReviewProcess инициализируем счетчики
            if process_definition_key == 'DocumentReviewProcess':
                user_variables['completedReviews'] = {
                    'value': 0,
                    'type': 'Integer'
                }
                user_variables['totalReviews'] = {
                    'value': len(user_list),
                    'type': 'Integer'
                }
            
            # Создаем уникальный business key для каждого процесса
            user_business_key = f"{business_key}_{user}" if business_key else f"{process_definition_key}_{user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            process_id = self.start_process(
                process_definition_key=process_definition_key,
                variables=user_variables,
                business_key=user_business_key
            )
            
            if process_id:
                process_ids.append(process_id)
                logger.info(f"Запущен процесс {process_definition_key} для пользователя {user}, ID: {process_id}")
            else:
                logger.error(f"Ошибка при запуске процесса {process_definition_key} для пользователя {user}")
        
        return process_ids

    def get_user_tasks_by_process_key(self, username: str, process_definition_key: str, 
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
        all_tasks = self.get_user_tasks(username, active_only=active_only)
        
        # Фильтруем задачи по ключу процесса
        filtered_tasks = []
        for task in all_tasks:
            if hasattr(task, 'process_definition_id'):
                # Получаем информацию о процессе
                try:
                    process_info = self._make_request('GET', f'process-definition/{task.process_definition_id}').json()
                    if process_info.get('key') == process_definition_key:
                        filtered_tasks.append(task)
                except Exception as e:
                    logger.warning(f"Ошибка при получении информации о процессе {task.process_definition_id}: {e}")
        
        return filtered_tasks

    def get_process_variables_by_names(self, process_instance_id: str, 
                                     variable_names: List[str]) -> Dict[str, Any]:
        """
        Универсальная функция для получения конкретных переменных процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            variable_names: Список имен переменных
            
        Returns:
            Словарь с переменными
        """
        return self.get_process_instance_variables_by_name(process_instance_id, variable_names)

    def set_process_variables(self, process_instance_id: str, 
                            variables: Dict[str, Any]) -> bool:
        """
        Универсальная функция для установки переменных процесса
        
        Args:
            process_instance_id: ID экземпляра процесса
            variables: Словарь переменных {имя: значение}
            
        Returns:
            True если переменные установлены успешно, False иначе
        """
        return self.set_multiple_process_variables(process_instance_id, variables)

    def get_process_status(self, process_instance_id: str, 
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
            variables = self.get_process_variables_by_names(process_instance_id, status_variables)
        else:
            variables = self.get_process_instance_variables(process_instance_id)
        
        return {
            'process_instance_id': process_instance_id,
            'variables': variables,
            'is_active': self.is_process_active(process_instance_id)
        }

    def is_process_active(self, process_instance_id: str) -> bool:
        """
        Проверяет, активен ли процесс
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            True если процесс активен, False иначе
        """
        try:
            response = self._make_request('GET', f'process-instance/{process_instance_id}')
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_process_definition_by_key(self, process_definition_key: str) -> Optional[Dict[str, Any]]:
        """
        Получает определение процесса по ключу
        
        Args:
            process_definition_key: Ключ определения процесса
            
        Returns:
            Словарь с информацией о процессе или None
        """
        try:
            response = self._make_request('GET', f'process-definition/key/{process_definition_key}')
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении определения процесса {process_definition_key}: {e}")
            return None

    def get_process_instances_by_definition_key(self, process_definition_key: str, 
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
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении экземпляров процесса {process_definition_key}: {e}")
            return []

    def delete_process_instance(self, process_instance_id: str, 
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
            response = self._make_request('DELETE', endpoint, params=params)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении процесса {process_instance_id}: {e}")
            return False

    def suspend_process_instance(self, process_instance_id: str) -> bool:
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
            response = self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при приостановке процесса {process_instance_id}: {e}")
            return False

    def activate_process_instance(self, process_instance_id: str) -> bool:
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
            response = self._make_request('PUT', endpoint, json=payload)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при активации процесса {process_instance_id}: {e}")
            return False
           
    def get_task_completion_form_data(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает данные формы завершения задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с данными формы или None
        """
        endpoint = f'task/{task_id}/form'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении данных формы задачи {task_id}: {e}")
            return None

    def get_task_completion_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные для завершения задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными
        """
        # Получаем переменные задачи
        task_variables = self.get_task_variables(task_id)
        
        # Получаем информацию о задаче
        task_info = self.get_task_by_id(task_id)
        if not task_info:
            return task_variables
        
        # Получаем переменные процесса
        process_variables = self.get_process_instance_variables(task_info.process_instance_id)
        
        # Объединяем переменные
        all_variables = {**process_variables, **task_variables}
        
        return all_variables

    def get_task_by_id(self, task_id: str) -> Optional[CamundaTask]:
        """
        Получает задачу по ID
        
        Args:
            task_id: ID задачи
            
        Returns:
            Объект задачи или None
        """
        endpoint = f'task/{task_id}'
        
        try:
            logger.info(f"Запрашиваем активную задачу {task_id} по URL: {urljoin(self.engine_rest_url, endpoint.lstrip('/'))}")
            response = self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для активной задачи {task_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Активная задача {task_id} не найдена (404)")
                return None
            
            response.raise_for_status()
            
            task_data = response.json()
            logger.info(f"Получены данные активной задачи {task_id}: {task_data}")
            
            # Инициализируем значения по умолчанию
            due_date = task_data.get('due')
            description = task_data.get('description')
            
            # Получаем переменные процесса для дополнительной информации
            try:
                process_variables = self.get_process_instance_variables_by_name(
                    task_data['processInstanceId'], 
                    ['dueDate', 'taskName', 'taskDescription', 'priority', 'category', 'tags']
                )
                
                if 'dueDate' in process_variables:
                    due_date = process_variables['dueDate']
                
                if 'taskDescription' in process_variables:
                    description = process_variables['taskDescription']
            except Exception as e:
                logger.warning(f"Не удалось получить переменные процесса для задачи {task_id}: {e}")
            
            task = CamundaTask(
                id=task_data['id'],
                name=task_data['name'],
                assignee=task_data.get('assignee'),
                start_time=task_data['created'],
                due=task_data.get('due'),
                follow_up=task_data.get('followUp'),
                delegation_state=task_data.get('delegationState'),
                description=description,
                execution_id=task_data['executionId'],
                owner=task_data.get('owner'),
                parent_task_id=task_data.get('parentTaskId'),
                priority=task_data['priority'],
                process_definition_id=task_data['processDefinitionId'],
                process_instance_id=task_data['processInstanceId'],
                task_definition_key=task_data['taskDefinitionKey'],
                case_execution_id=task_data.get('caseExecutionId'),
                case_instance_id=task_data.get('caseInstanceId'),
                case_definition_id=task_data.get('caseDefinitionId'),
                suspended=task_data['suspended'],
                form_key=task_data.get('formKey'),
                tenant_id=task_data.get('tenantId')
            )
            
            logger.info(f"Создан объект активной задачи {task_id}: {task.name}")
            return task
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении активной задачи {task_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None

    def get_history_task_by_id(self, task_id: str) -> Optional[CamundaHistoryTask]:
        """
        Получает историческую задачу по ID (исправленная версия)
        
        Args:
            task_id: ID задачи
            
        Returns:
            Объект исторической задачи или None
        """
        try:
            # Используем альтернативный способ через поиск по taskId
            endpoint = f'history/task?taskId={task_id}'
            logger.info(f"Запрашиваем историческую задачу {task_id} через альтернативный endpoint")
            response = self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для исторической задачи {task_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Историческая задача {task_id} не найдена (404)")
                return None
            
            response.raise_for_status()
            
            tasks = response.json()
            
            if not tasks:
                logger.warning(f"Историческая задача {task_id} не найдена в результатах поиска")
                return None
            
            # Берем первую найденную задачу (должна быть одна)
            task_data = tasks[0]
            logger.info(f"Получены данные исторической задачи {task_id}: {task_data}")
            
            # Инициализируем значения по умолчанию
            due_date = task_data.get('due')
            description = task_data.get('description')
            
            # Получаем переменные процесса для дополнительной информации
            try:
                process_variables = self.get_process_instance_variables_by_name(
                    task_data['processInstanceId'], 
                    ['dueDate', 'taskName', 'taskDescription', 'priority', 'category', 'tags']
                )
                
                if 'dueDate' in process_variables:
                    due_date = process_variables['dueDate']
                
                if 'taskDescription' in process_variables:
                    description = process_variables['taskDescription']
            except Exception as e:
                logger.warning(f"Не удалось получить переменные процесса для задачи {task_id}: {e}")
            
            history_task = CamundaHistoryTask(
                id=task_data['id'],
                process_definition_key=task_data['processDefinitionKey'],
                process_definition_id=task_data['processDefinitionId'],
                process_instance_id=task_data['processInstanceId'],
                execution_id=task_data.get('executionId'),
                activity_instance_id=task_data.get('activityInstanceId'),
                name=task_data.get('name'),
                description=description,
                delete_reason=task_data.get('deleteReason'),
                owner=task_data.get('owner'),
                assignee=task_data.get('assignee'),
                start_time=task_data.get('startTime'),
                end_time=task_data.get('endTime'),
                duration=task_data.get('duration'),
                task_definition_key=task_data.get('taskDefinitionKey'),
                priority=task_data.get('priority'),
                due_date=due_date,
                parent_task_id=task_data.get('parentTaskId'),
                follow_up_date=task_data.get('followUp'),
                tenant_id=task_data.get('tenantId'),
                removal_time=task_data.get('removalTime'),
                root_process_instance_id=task_data.get('rootProcessInstanceId')
            )
            
            return history_task
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении исторической задачи {task_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None
    def get_history_process_instance_variables_by_name(self, process_instance_id: str, variable_names: List[str] = None) -> Dict[str, Any]:
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
            response = self._make_request('GET', endpoint, params=params)
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
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении исторических переменных процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return {}


    def get_user_tasks_filtered(self, assignee: str, active_only: bool = True, 
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
        all_tasks = self.get_user_tasks(assignee, active_only, fetch_variables=True)
        
        if not filter_completed:
            return all_tasks
        
        filtered_tasks = []
        
        for task in all_tasks:
            # Получаем переменные процесса для проверки статуса пользователя
            try:
                process_variables = self.get_process_instance_variables(task.process_instance_id)
                
                # Проверяем, завершил ли пользователь эту задачу
                user_completed = process_variables.get('userCompleted', {})
                if isinstance(user_completed, dict):
                    if user_completed.get(assignee, False):
                        # Пользователь уже завершил эту задачу, пропускаем
                        continue
                
                # Если пользователь не завершил задачу, добавляем её в результат
                filtered_tasks.append(task)
                
            except Exception as e:
                logger.warning(f"Не удалось проверить статус пользователя {assignee} для задачи {task.id}: {e}")
                # В случае ошибки добавляем задачу (лучше показать лишнюю, чем скрыть нужную)
                filtered_tasks.append(task)
        
        return filtered_tasks

    def get_task_progress(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает информацию о прогрессе выполнения Multi-Instance задачи
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о прогрессе
        """
        try:
            # Получаем переменные процесса
            process_variables = self.get_process_instance_variables(process_instance_id)
            
            # Получаем переменные Multi-Instance из активных задач
            multi_instance_variables = self._get_multi_instance_variables(process_instance_id)
            
            # Объединяем переменные
            all_variables = {**process_variables, **multi_instance_variables}
            
            # Для Multi-Instance процессов используем nrOfInstances и nrOfCompletedInstances
            nr_of_instances = all_variables.get('nrOfInstances', 0)
            nr_of_completed_instances = all_variables.get('nrOfCompletedInstances', 0)
            
            # Отладочная информация
            logger.info(f"Переменные процесса {process_instance_id}:")
            logger.info(f"  nrOfInstances: {nr_of_instances}")
            logger.info(f"  nrOfCompletedInstances: {nr_of_completed_instances}")
            logger.info(f"  nrOfActiveInstances: {all_variables.get('nrOfActiveInstances', 0)}")
            
            # Получаем список всех пользователей
            assignee_list = all_variables.get('assigneeList', [])
            if isinstance(assignee_list, str):
                try:
                    assignee_list = json.loads(assignee_list)
                except:
                    assignee_list = []
            
            logger.info(f"  assigneeList: {assignee_list}")
            
            # Получаем статус пользователей из переменных процесса
            user_completed = all_variables.get('userCompleted', {})
            if isinstance(user_completed, str):
                try:
                    user_completed = json.loads(user_completed)
                except:
                    user_completed = {}
            
            logger.info(f"  userCompleted: {user_completed}")
            
            # Если переменная userCompleted пуста или неполная, проверяем историю задач
            if not user_completed or len(user_completed) < len(assignee_list):
                logger.info(f"Переменная userCompleted неполная для процесса {process_instance_id}, проверяем историю задач")
                user_completed = self._get_user_completion_status_from_history(process_instance_id, assignee_list)
            
            # Создаем детальную информацию о пользователях
            user_status = []
            for user in assignee_list:
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

    def _get_multi_instance_variables(self, process_instance_id: str) -> Dict[str, Any]:
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
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            tasks = response.json()
            logger.info(f"Найдено {len(tasks)} активных задач для процесса {process_instance_id}")
            
            # Ищем переменные Multi-Instance в первой задаче (они одинаковые для всех экземпляров)
            if tasks:
                task_id = tasks[0]['id']
                task_variables = self.get_task_variables(task_id)
                
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

    def _get_user_completion_status_from_history(self, process_instance_id: str, assignee_list: List[str]) -> Dict[str, bool]:
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
            response = self._make_request('GET', endpoint)
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


    def start_document_review_process_multi_instance(self, 
                                               document_name: str,
                                               document_content: str,
                                               assignee_list: List[str],
                                               business_key: Optional[str] = None,
                                               creator_username: Optional[str] = None) -> Optional[str]:
        """
        Запускает процесс ознакомления с документом для нескольких пользователей
        с использованием Multi-Instance (один процесс, несколько параллельных задач)
        
        Args:
            document_name: Название документа
            document_content: Содержимое документа
            assignee_list: Список пользователей для ознакомления
            business_key: Бизнес-ключ процесса
            
        Returns:
            ID экземпляра процесса или None при ошибке
        """
        try:
            # Подготавливаем переменные для процесса
            process_variables = {
                'taskName': f'Ознакомиться с документом: {document_name}',
                'taskDescription': f'Необходимо ознакомиться с документом: {document_name}\n\nСодержимое:\n{document_content}',
                'priority': 2,
                'dueDate': '2025-09-29T23:59:59.000+0000',
                'documentName': document_name,
                'documentContent': document_content,
                
                # Multi-Instance переменные
                'assigneeList': {
                    'value': json.dumps(assignee_list),
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.ArrayList'
                    }
                },
                
                # Инициализируем счетчик завершенных ознакомлений
                'completedReviews': {
                    'value': 0,
                    'type': 'Integer'
                },
                
                # Инициализируем словари для хранения данных пользователей
                'reviewDates': {
                    'value': {},
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'reviewComments': {
                    'value': {},
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'reviewStatus': {
                    'value': {},
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
                },
                'userCompleted': {
                    'value': {},
                    'type': 'Object',
                    'valueInfo': {
                        'serializationDataFormat': 'application/json',
                        'objectTypeName': 'java.util.HashMap'
                    }
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
            
            # Запускаем процесс с Multi-Instance
            process_id = self.start_process(
                process_definition_key='DocumentReviewProcessMultiInstance',
                variables=process_variables,
                business_key=business_key,
                creator_username=creator_username
            )
            
            if process_id:
                logger.info(f"Запущен Multi-Instance процесс ознакомления с документом '{document_name}' для {len(assignee_list)} пользователей, ID: {process_id}")
                logger.info(f"Пользователи: {', '.join(assignee_list)}")
            else:
                logger.error(f"Ошибка при запуске Multi-Instance процесса ознакомления с документом '{document_name}'")
            
            return process_id
            
        except Exception as e:
            logger.error(f"Ошибка при запуске Multi-Instance процесса ознакомления: {e}", exc_info=True)
            return None

    def get_multi_instance_task_progress(self, process_instance_id: str) -> Dict[str, Any]:
        """
        Получает информацию о прогрессе выполнения Multi-Instance задачи
        
        Args:
            process_instance_id: ID экземпляра процесса
            
        Returns:
            Словарь с информацией о прогрессе
        """
        try:
            process_variables = self.get_process_instance_variables(process_instance_id)
            
            # Получаем информацию о Multi-Instance
            nr_of_instances = process_variables.get('nrOfInstances', 0)
            nr_of_completed_instances = process_variables.get('nrOfCompletedInstances', 0)
            
            # Получаем список пользователей
            assignee_list = process_variables.get('assigneeList', [])
            if isinstance(assignee_list, str):
                try:
                    assignee_list = json.loads(assignee_list)
                except:
                    assignee_list = []
            
            # Получаем статус пользователей
            user_completed = process_variables.get('userCompleted', {})
            if isinstance(user_completed, str):
                try:
                    user_completed = json.loads(user_completed)
                except:
                    user_completed = {}
            
            # Создаем детальную информацию о пользователях
            user_status = []
            for user in assignee_list:
                completed = user_completed.get(user, False) if isinstance(user_completed, dict) else False
                user_status.append({
                    'user': user,
                    'completed': completed,
                    'status': 'Завершено' if completed else 'В процессе'
                })
            
            return {
                'nr_of_instances': nr_of_instances,
                'nr_of_completed_instances': nr_of_completed_instances,
                'progress_percent': (nr_of_completed_instances / nr_of_instances) * 100 if nr_of_instances > 0 else 0,
                'user_status': user_status,
                'is_complete': nr_of_completed_instances >= nr_of_instances,
                'assignee_list': assignee_list
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении прогресса Multi-Instance задачи {process_instance_id}: {e}")
            return {
                'nr_of_instances': 0,
                'nr_of_completed_instances': 0,
                'progress_percent': 0,
                'user_status': [],
                'is_complete': False,
                'assignee_list': []
            }

    def get_process_instance_by_id(self, process_instance_id: str) -> Optional[Dict[str, Any]]:
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
            response = self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для процесса {process_instance_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Процесс {process_instance_id} не найден (404)")
                return None
            
            response.raise_for_status()
            process_data = response.json()
            logger.info(f"Получены данные процесса {process_instance_id}: {process_data}")
            return process_data
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None

    def get_history_process_instance_by_id(self, process_instance_id: str) -> Optional[Dict[str, Any]]:
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
            response = self._make_request('GET', endpoint)
            
            logger.info(f"Ответ сервера для исторического процесса {process_instance_id}: {response.status_code}")
            
            if response.status_code == 404:
                logger.warning(f"Исторический процесс {process_instance_id} не найден (404)")
                return None
            
            response.raise_for_status()
            process_data = response.json()
            logger.info(f"Получены данные исторического процесса {process_instance_id}: {process_data}")
            return process_data
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении исторического процесса {process_instance_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Детали ошибки: {e.response.text}")
            return None
    
    def diagnose_history_issue(self, task_id: str) -> Dict[str, Any]:
        """
        Диагностирует проблему с историей задач
        
        Args:
            task_id: ID задачи для диагностики
            
        Returns:
            Словарь с результатами диагностики
        """
        diagnosis = {
            'task_id': task_id,
            'active_task_found': False,
            'history_task_found': False,
            'process_instance_id': None,
            'process_history_found': False,
            'all_history_tasks': [],
            'errors': []
        }
        
        try:
            # 1. Проверяем активную задачу
            try:
                active_task = self.get_task_by_id(task_id)
                if active_task:
                    diagnosis['active_task_found'] = True
                    diagnosis['process_instance_id'] = active_task.process_instance_id
                    logger.info(f"Активная задача {task_id} найдена, процесс: {active_task.process_instance_id}")
            except Exception as e:
                diagnosis['errors'].append(f"Ошибка при получении активной задачи: {e}")
            
            # 2. Проверяем историческую задачу
            try:
                history_task = self.get_history_task_by_id(task_id)
                if history_task:
                    diagnosis['history_task_found'] = True
                    diagnosis['process_instance_id'] = history_task.process_instance_id
                    logger.info(f"Историческая задача {task_id} найдена, процесс: {history_task.process_instance_id}")
            except Exception as e:
                diagnosis['errors'].append(f"Ошибка при получении исторической задачи: {e}")
            
            # 3. Если есть process_instance_id, проверяем историю процесса
            if diagnosis['process_instance_id']:
                try:
                    process_history = self.get_history_process_instance_by_id(diagnosis['process_instance_id'])
                    if process_history:
                        diagnosis['process_history_found'] = True
                        logger.info(f"История процесса {diagnosis['process_instance_id']} найдена")
                    else:
                        logger.warning(f"История процесса {diagnosis['process_instance_id']} не найдена")
                except Exception as e:
                    diagnosis['errors'].append(f"Ошибка при получении истории процесса: {e}")
                
                # 4. Получаем все исторические задачи для процесса
                try:
                    endpoint = f'history/task?processInstanceId={diagnosis["process_instance_id"]}'
                    response = self._make_request('GET', endpoint)
                    response.raise_for_status()
                    diagnosis['all_history_tasks'] = response.json()
                    logger.info(f"Найдено {len(diagnosis['all_history_tasks'])} исторических задач для процесса {diagnosis['process_instance_id']}")
                except Exception as e:
                    diagnosis['errors'].append(f"Ошибка при получении всех исторических задач: {e}")
            
            # 5. Проверяем общую историю задач
            try:
                endpoint = 'history/task'
                response = self._make_request('GET', endpoint)
                response.raise_for_status()
                all_tasks = response.json()
                logger.info(f"Всего исторических задач в системе: {len(all_tasks)}")
                
                # Ищем нашу задачу среди всех
                for task in all_tasks:
                    if task.get('id') == task_id:
                        diagnosis['history_task_found'] = True
                        diagnosis['process_instance_id'] = task.get('processInstanceId')
                        logger.info(f"Задача {task_id} найдена в общей истории")
                        break
            except Exception as e:
                diagnosis['errors'].append(f"Ошибка при получении общей истории задач: {e}")
            
            return diagnosis
            
        except Exception as e:
            diagnosis['errors'].append(f"Общая ошибка диагностики: {e}")
            return diagnosis

    def get_completed_tasks_grouped(self, assignee: str = None) -> List[Union[CamundaHistoryTask, 'GroupedHistoryTask']]:
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
            
            response = self._make_request('GET', endpoint, params=params)
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
                        process_variables = self.get_history_process_instance_variables_by_name(
                            process_id, 
                            ['taskDescription', 'dueDate', 'assigneeList', 'userComments', 'userCompletionDates', 'userStatus', 'userCompleted']
                        )
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
                            comment = user_info['comment']
                            review_date = user_info['completion_date'] or end_time
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

    def get_history_task_variables(self, task_id: str) -> Dict[str, Any]:
        """
        Получает переменные исторической задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Словарь с переменными
        """
        try:
            endpoint = f'history/variable-instance?taskIdIn={task_id}'
            response = self._make_request('GET', endpoint)
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
    
    def get_processes_by_creator(self, creator_username: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Получает процессы, созданные конкретным пользователем
        
        Args:
            creator_username: Имя пользователя-создателя
            active_only: Получать только активные процессы
            
        Returns:
            Список процессов
        """
        try:
            # Получаем все процессы
            endpoint = 'process-instance' if active_only else 'history/process-instance'
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            all_processes = response.json()
            
            # Фильтруем по создателю
            creator_processes = []
            for process in all_processes:
                process_id = process['id']
                
                # Получаем переменные процесса
                try:
                    variables = self.get_process_instance_variables(process_id)
                    process_creator = variables.get('processCreator', '')
                    
                    if process_creator == creator_username:
                        creator_processes.append(process)
                except Exception as e:
                    logger.warning(f"Не удалось получить переменные для процесса {process_id}: {e}")
            
            return creator_processes
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении процессов создателя {creator_username}: {e}")
            return []


def create_camunda_client() -> CamundaClient:
    """
    Создает клиент Camunda с настройками из конфигурации
    
    Returns:
        Настроенный экземпляр CamundaClient
        
    Raises:
        ValueError: Если не настроены обязательные параметры
    """
    # Импортируем здесь, чтобы избежать циклических импортов
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
        verify_ssl=False  # Для разработки отключаем проверку SSL
    )