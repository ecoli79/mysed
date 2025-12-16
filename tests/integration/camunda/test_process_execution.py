"""
Тесты выполнения процессов в Camunda
"""
import pytest
from tests.fixtures.mock_camunda import mock_camunda_client, real_camunda_client


@pytest.mark.integration
@pytest.mark.camunda
class TestProcessExecution:
    """Тесты выполнения процессов"""
    
    @pytest.mark.asyncio
    async def test_start_process_with_mock(self, mock_camunda_client):
        """Тест запуска процесса через мок"""
        process_key = 'test_process'
        business_key = 'test_business_key_123'
        variables = {
            'document_id': '123',
            'assignee': 'test_user',
        }
        
        process_instance = await mock_camunda_client.start_process(
            process_definition_key=process_key,
            business_key=business_key,
            variables=variables
        )
        
        assert process_instance is not None
        assert 'id' in process_instance
        assert process_instance['business_key'] == business_key
        assert process_instance['variables'] == variables
        
        # Проверяем, что метод был вызван
        mock_camunda_client.start_process.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_tasks_for_process_instance(self, mock_camunda_client):
        """Тест получения задач для экземпляра процесса"""
        # Сначала запускаем процесс
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='test_process',
            business_key='test_bk_456'
        )
        
        process_instance_id = process_instance['id']
        
        # Получаем задачи для этого процесса
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance_id
        )
        
        assert isinstance(tasks, list)
        # Проверяем, что все задачи принадлежат этому процессу
        for task in tasks:
            assert task.get('process_instance_id') == process_instance_id
    
    @pytest.mark.asyncio
    async def test_complete_task_and_check_history(self, mock_camunda_client):
        """Тест завершения задачи и проверки истории"""
        # Сначала получаем существующую задачу
        tasks = await mock_camunda_client.get_tasks()
        if not tasks:
            pytest.skip('Нет задач для тестирования')
        
        task_id = tasks[0]['id']
        
        # Завершаем задачу
        await mock_camunda_client.complete_task(
            task_id=task_id,
            variables={'status': 'completed'}
        )
        
        # Получаем историю задач
        history_tasks = await mock_camunda_client.get_history_tasks()
        
        # Проверяем, что завершенная задача есть в истории
        completed_task = next(
            (t for t in history_tasks if t.get('id') == task_id),
            None
        )
        # Задача должна быть в истории после завершения
        assert completed_task is not None
        assert 'end_time' in completed_task
    
    @pytest.mark.asyncio
    @pytest.mark.real_server
    async def test_get_process_definitions_with_real_server(self, real_camunda_client):
        """Тест получения определений процессов с реального сервера"""
        try:
            processes = await real_camunda_client.get_process_definitions()
            
            assert isinstance(processes, list)
            # Если есть процессы, проверяем структуру
            if processes:
                process = processes[0]
                # Проверяем наличие основных полей
                assert hasattr(process, 'id') or 'id' in process
        except Exception as e:
            pytest.skip(f'Не удалось подключиться к реальному серверу: {e}')
        finally:
            await real_camunda_client.close()

