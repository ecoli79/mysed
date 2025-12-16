"""
Тесты полного workflow создания документа
"""
import pytest
from tests.fixtures.mock_camunda import mock_camunda_client
from tests.fixtures.mock_mayan import mock_mayan_client


@pytest.mark.integration
@pytest.mark.workflow
class TestDocumentCreationFlow:
    """Тесты workflow создания документа"""
    
    @pytest.mark.asyncio
    async def test_complete_document_creation_workflow(self, mock_camunda_client, mock_mayan_client):
        """Тест полного цикла создания документа"""
        # 1. Запускаем процесс создания документа в Camunda
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='task_create_document',
            business_key='create_doc_123',
            variables={
                'document_name': 'Новый документ',
                'assignee': 'test_user',
            }
        )
        assert process_instance is not None
        
        # 2. Создаем задачу вручную для теста (мок не создает задачи автоматически)
        from tests.fixtures.test_data import TEST_TASKS
        test_task = TEST_TASKS[0].copy()
        test_task['process_instance_id'] = process_instance['id']
        test_task['name'] = 'Подготовить документ'
        mock_camunda_client._tasks.append(test_task)
        
        # 3. Получаем задачу создания документа
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(tasks) > 0
        task = tasks[0]
        
        # 4. Создаем документ в Mayan (имитация загрузки файла)
        test_content = b'Test document content'
        document = await mock_mayan_client.upload_document(
            file_content=test_content,
            filename='new_document.pdf',
            document_type_id=1,
            cabinet_id=1,
            label='Новый документ'
        )
        assert document is not None
        document_id = document['document_id']
        
        # 5. Завершаем задачу с ID созданного документа
        result = await mock_camunda_client.complete_task(
            task_id=task['id'],
            variables={
                'document_id': document_id,
                'document_label': document['label'],
            }
        )
        assert result is True
        
        # 6. Проверяем, что документ создан в Mayan
        created_document = await mock_mayan_client.get_document(document_id)
        assert created_document is not None
        assert created_document.document_id == document_id

