"""
Тесты полного workflow ознакомления с документом
"""
import pytest
from tests.fixtures.mock_camunda import mock_camunda_client
from tests.fixtures.mock_mayan import mock_mayan_client


@pytest.mark.integration
@pytest.mark.workflow
class TestDocumentReviewFlow:
    """Тесты workflow ознакомления с документом"""
    
    @pytest.mark.asyncio
    async def test_complete_document_review_workflow(self, mock_camunda_client, mock_mayan_client, test_user_data):
        """Тест полного цикла ознакомления с документом"""
        # 1. Получаем документ из Mayan
        documents = await mock_mayan_client.get_documents(page=1, page_size=1)
        assert len(documents) > 0
        document = documents[0]
        document_id = document['document_id']
        
        # 2. Запускаем процесс ознакомления в Camunda
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='document_review',
            business_key=f'review_{document_id}',
            variables={
                'document_id': document_id,
                'assignee': test_user_data['username'],
            }
        )
        assert process_instance is not None
        
        # 3. Создаем задачу вручную для теста (мок не создает задачи автоматически)
        # В реальном сценарии задача создается процессом
        from tests.fixtures.test_data import TEST_TASKS
        test_task = TEST_TASKS[0].copy()
        test_task['process_instance_id'] = process_instance['id']
        mock_camunda_client._tasks.append(test_task)
        
        # 4. Получаем задачу ознакомления
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(tasks) > 0
        task = tasks[0]
        
        # 5. Завершаем задачу ознакомления
        result = await mock_camunda_client.complete_task(
            task_id=task['id'],
            variables={
                'reviewed': True,
                'review_comment': 'Ознакомлен',
            }
        )
        assert result is True
        
        # 6. Проверяем, что задача завершена
        completed_task = await mock_camunda_client.get_task(task['id'])
        assert completed_task is None  # Задача должна быть удалена после завершения
    
    @pytest.mark.asyncio
    async def test_document_review_with_multiple_users(self, mock_camunda_client, mock_mayan_client):
        """Тест ознакомления с документом несколькими пользователями"""
        # Получаем документ
        documents = await mock_mayan_client.get_documents(page=1, page_size=1)
        assert len(documents) > 0
        document_id = documents[0]['document_id']
        
        # Запускаем процесс для нескольких пользователей
        users = ['test_user', 'reviewer_user', 'admin_user']
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='document_review',
            business_key=f'multi_review_{document_id}',
            variables={
                'document_id': document_id,
                'reviewers': users,
            }
        )
        
        # Создаем задачи для всех пользователей вручную (мок не создает задачи автоматически)
        from tests.fixtures.test_data import TEST_TASKS
        for i, username in enumerate(users):
            test_task = TEST_TASKS[0].copy()
            test_task['id'] = f'task_multi_{i}'
            test_task['process_instance_id'] = process_instance['id']
            test_task['assignee'] = username
            test_task['name'] = 'Ознакомиться с документом'
            mock_camunda_client._tasks.append(test_task)
        
        # Получаем задачи для всех пользователей
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(tasks) == len(users)
        
        # Завершаем задачи для каждого пользователя
        for task in tasks:
            await mock_camunda_client.complete_task(
                task_id=task['id'],
                variables={'reviewed': True}
            )
        
        # Проверяем, что все задачи завершены
        remaining_tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(remaining_tasks) == 0

