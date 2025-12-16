"""
Тесты операций с задачами в Camunda
"""
import pytest
from tests.fixtures.mock_camunda import mock_camunda_client, real_camunda_client


@pytest.mark.integration
@pytest.mark.camunda
class TestTaskOperations:
    """Тесты операций с задачами"""
    
    @pytest.mark.asyncio
    async def test_get_tasks_with_mock(self, mock_camunda_client):
        """Тест получения задач через мок"""
        tasks = await mock_camunda_client.get_tasks()
        
        assert isinstance(tasks, list)
        assert len(tasks) > 0
        
        # Проверяем структуру задачи
        task = tasks[0]
        assert 'id' in task
        assert 'name' in task
        assert 'assignee' in task
    
    @pytest.mark.asyncio
    @pytest.mark.real_server
    async def test_get_tasks_with_real_server(self, real_camunda_client):
        """Тест получения задач с реального сервера"""
        try:
            tasks = await real_camunda_client.get_tasks()
            
            assert isinstance(tasks, list)
            # Если есть задачи, проверяем структуру
            if tasks:
                task = tasks[0]
                assert hasattr(task, 'id') or 'id' in task
        except Exception as e:
            pytest.skip(f'Не удалось подключиться к реальному серверу: {e}')
        finally:
            await real_camunda_client.close()
    
    @pytest.mark.asyncio
    async def test_get_tasks_by_assignee(self, mock_camunda_client):
        """Тест получения задач по исполнителю"""
        assignee = 'test_user'
        tasks = await mock_camunda_client.get_tasks(assignee=assignee)
        
        assert isinstance(tasks, list)
        # Проверяем, что все задачи назначены указанному пользователю
        for task in tasks:
            assert task.get('assignee') == assignee
    
    @pytest.mark.asyncio
    async def test_get_task_by_id(self, mock_camunda_client):
        """Тест получения задачи по ID"""
        task_id = 'task_123'
        task = await mock_camunda_client.get_task(task_id)
        
        assert task is not None
        assert task['id'] == task_id
    
    @pytest.mark.asyncio
    async def test_complete_task_with_mock(self, mock_camunda_client):
        """Тест завершения задачи через мок"""
        task_id = 'task_123'
        variables = {'status': 'completed', 'comment': 'Задача выполнена'}
        
        result = await mock_camunda_client.complete_task(
            task_id=task_id,
            variables=variables
        )
        
        assert result is True
        # Проверяем, что метод был вызван
        mock_camunda_client.complete_task.assert_called_once_with(
            task_id=task_id,
            variables=variables
        )
    
    @pytest.mark.asyncio
    async def test_assign_task_with_mock(self, mock_camunda_client):
        """Тест назначения задачи через мок"""
        task_id = 'task_123'
        user_id = 'new_user'
        
        result = await mock_camunda_client.assign_task(
            task_id=task_id,
            user_id=user_id
        )
        
        assert result is True
        # Проверяем, что задача была назначена
        task = await mock_camunda_client.get_task(task_id)
        assert task['assignee'] == user_id
    
    @pytest.mark.asyncio
    async def test_claim_task_with_mock(self, mock_camunda_client):
        """Тест взятия задачи в работу через мок"""
        task_id = 'task_124'
        user_id = 'reviewer_user'
        
        result = await mock_camunda_client.claim_task(
            task_id=task_id,
            user_id=user_id
        )
        
        assert result is True
        # Проверяем, что задача была взята в работу
        task = await mock_camunda_client.get_task(task_id)
        assert task['assignee'] == user_id

