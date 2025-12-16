"""
Моки для Camunda REST API
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Any, Optional
from tests.fixtures.test_data import (
    TEST_PROCESS_DEFINITIONS,
    TEST_TASKS,
)


class MockCamundaClient:
    """Мок клиента Camunda для тестирования"""
    
    def __init__(self, base_url: str = 'http://localhost:8080', 
                 username: str = None, password: str = None):
        self.base_url = base_url
        self.engine_rest_url = f'{base_url}/engine-rest/'
        self.username = username
        self.password = password
        
        # Хранилище для моков данных
        self._deployments: Dict[str, Any] = {}
        self._process_definitions: List[Dict[str, Any]] = TEST_PROCESS_DEFINITIONS.copy()
        self._process_instances: Dict[str, Any] = {}
        self._tasks: List[Dict[str, Any]] = TEST_TASKS.copy()
        self._history_tasks: List[Dict[str, Any]] = []
        
        # Настраиваем моки методов
        self._setup_mocks()
    
    def _setup_mocks(self):
        """Настраивает моки для всех методов"""
        # Развертывание процессов
        self.deploy_process = AsyncMock(side_effect=self._deploy_process_impl)
        
        # Получение процессов
        self.get_process_definitions = AsyncMock(side_effect=self._get_process_definitions_impl)
        self.get_process_definition = AsyncMock(side_effect=self._get_process_definition_impl)
        
        # Запуск процессов
        self.start_process = AsyncMock(side_effect=self._start_process_impl)
        
        # Задачи
        self.get_tasks = AsyncMock(side_effect=self._get_tasks_impl)
        self.get_task = AsyncMock(side_effect=self._get_task_impl)
        self.complete_task = AsyncMock(side_effect=self._complete_task_impl)
        self.assign_task = AsyncMock(side_effect=self._assign_task_impl)
        self.claim_task = AsyncMock(side_effect=self._claim_task_impl)
        
        # История
        self.get_history_tasks = AsyncMock(side_effect=self._get_history_tasks_impl)
        
        # Закрытие клиента
        self.close = AsyncMock()
        self.__aenter__ = AsyncMock(return_value=self)
        self.__aexit__ = AsyncMock(return_value=None)
    
    async def _deploy_process_impl(self, deployment_name: str, bpmn_file_path: str, **kwargs):
        """Имитация развертывания процесса"""
        deployment_id = f'deployment_{len(self._deployments) + 1}'
        deployment = {
            'id': deployment_id,
            'name': deployment_name,
            'deployment_time': '2024-01-15T10:00:00.000+0000',
            'source': 'test',
        }
        self._deployments[deployment_id] = deployment
        return deployment
    
    async def _get_process_definitions_impl(self, **kwargs):
        """Имитация получения списка процессов"""
        return self._process_definitions
    
    async def _get_process_definition_impl(self, process_definition_id: str):
        """Имитация получения процесса по ID"""
        for proc in self._process_definitions:
            if proc['id'] == process_definition_id:
                return proc
        return None
    
    async def _start_process_impl(self, process_definition_key: str, 
                                 business_key: str = None, variables: Dict = None):
        """Имитация запуска процесса"""
        process_instance_id = f'proc_inst_{len(self._process_instances) + 1}'
        process_instance = {
            'id': process_instance_id,
            'definition_id': f'{process_definition_key}:1:123',
            'business_key': business_key,
            'variables': variables or {},
        }
        self._process_instances[process_instance_id] = process_instance
        return process_instance
    
    async def _get_tasks_impl(self, assignee: str = None, process_instance_id: str = None, **kwargs):
        """Имитация получения задач"""
        tasks = self._tasks.copy()
        
        if assignee:
            tasks = [t for t in tasks if t.get('assignee') == assignee]
        
        if process_instance_id:
            tasks = [t for t in tasks if t.get('process_instance_id') == process_instance_id]
        
        return tasks
    
    async def _get_task_impl(self, task_id: str):
        """Имитация получения задачи по ID"""
        for task in self._tasks:
            if task['id'] == task_id:
                return task
        return None
    
    async def _complete_task_impl(self, task_id: str, variables: Dict = None):
        """Имитация завершения задачи"""
        # Находим задачу перед удалением
        task = next((t for t in self._tasks if t['id'] == task_id), None)
        
        # Удаляем задачу из списка активных
        self._tasks = [t for t in self._tasks if t['id'] != task_id]
        
        # Добавляем в историю
        if task:
            history_task = task.copy()
            history_task['end_time'] = '2024-01-15T12:00:00.000+0000'
            self._history_tasks.append(history_task)
        
        return True
    
    async def _assign_task_impl(self, task_id: str, user_id: str):
        """Имитация назначения задачи"""
        for task in self._tasks:
            if task['id'] == task_id:
                task['assignee'] = user_id
                return True
        return False
    
    async def _claim_task_impl(self, task_id: str, user_id: str):
        """Имитация взятия задачи в работу"""
        return await self._assign_task_impl(task_id, user_id)
    
    async def _get_history_tasks_impl(self, **kwargs):
        """Имитация получения истории задач"""
        return self._history_tasks


@pytest.fixture
def mock_camunda_client():
    """Фикстура для создания мок клиента Camunda"""
    return MockCamundaClient()


@pytest.fixture
def real_camunda_client(test_config, use_real_servers):
    """Фикстура для создания реального клиента Camunda (если разрешено)"""
    if not use_real_servers:
        pytest.skip('Требуется реальный сервер Camunda (установите TEST_USE_REAL_SERVERS=true)')
    
    from services.camunda_connector import CamundaClient
    
    return CamundaClient(
        base_url=test_config.camunda_url,
        username=test_config.camunda_username or None,
        password=test_config.camunda_password or None,
        verify_ssl=False
    )

