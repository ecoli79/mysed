"""
Тесты полного workflow подписания документа
"""
import pytest
from tests.fixtures.mock_camunda import mock_camunda_client
from tests.fixtures.mock_mayan import mock_mayan_client
from tests.fixtures.test_data import TEST_CERTIFICATES


@pytest.mark.integration
@pytest.mark.workflow
class TestDocumentSigningFlow:
    """Тесты workflow подписания документа"""
    
    @pytest.mark.asyncio
    async def test_complete_document_signing_workflow(self, mock_camunda_client, mock_mayan_client):
        """Тест полного цикла подписания документа"""
        # 1. Получаем документ из Mayan
        documents = await mock_mayan_client.get_documents(page=1, page_size=1)
        assert len(documents) > 0
        document = documents[0]
        document_id = document['document_id']
        
        # 2. Запускаем процесс подписания в Camunda
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='DocumentSigningProcess',
            business_key=f'sign_{document_id}',
            variables={
                'document_id': document_id,
                'signerList': ['test_user', 'reviewer_user'],
            }
        )
        assert process_instance is not None
        
        # 3. Создаем задачу вручную для теста (мок не создает задачи автоматически)
        from tests.fixtures.test_data import TEST_TASKS
        test_task = TEST_TASKS[0].copy()
        test_task['process_instance_id'] = process_instance['id']
        test_task['name'] = 'Подписать документ'
        mock_camunda_client._tasks.append(test_task)
        
        # 4. Получаем задачи подписания
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(tasks) > 0
        
        # 5. Завершаем задачи подписания (имитация подписания)
        for task in tasks:
            await mock_camunda_client.complete_task(
                task_id=task['id'],
                variables={
                    'signed': True,
                    'signatureData': 'base64_signature_data',
                    'certificateInfo': TEST_CERTIFICATES[0],
                }
            )
        
        # 6. Проверяем, что все задачи завершены
        remaining_tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(remaining_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_document_signing_with_certificate(self, mock_camunda_client, mock_mayan_client):
        """Тест подписания документа с сертификатом"""
        # Получаем документ
        documents = await mock_mayan_client.get_documents(page=1, page_size=1)
        assert len(documents) > 0
        document_id = documents[0]['document_id']
        
        # Запускаем процесс подписания
        process_instance = await mock_camunda_client.start_process(
            process_definition_key='DocumentSigningProcess',
            business_key=f'sign_cert_{document_id}',
            variables={
                'document_id': document_id,
                'certificate': TEST_CERTIFICATES[0],
            }
        )
        
        # Создаем задачу вручную для теста
        from tests.fixtures.test_data import TEST_TASKS
        test_task = TEST_TASKS[0].copy()
        test_task['process_instance_id'] = process_instance['id']
        test_task['name'] = 'Подписать документ'
        mock_camunda_client._tasks.append(test_task)
        
        # Создаем задачу вручную для теста
        from tests.fixtures.test_data import TEST_TASKS
        test_task = TEST_TASKS[0].copy()
        test_task['process_instance_id'] = process_instance['id']
        test_task['name'] = 'Подписать документ'
        mock_camunda_client._tasks.append(test_task)
        
        # Получаем задачу подписания
        tasks = await mock_camunda_client.get_tasks(
            process_instance_id=process_instance['id']
        )
        assert len(tasks) > 0
        
        # Завершаем задачу с данными подписи
        task = tasks[0]
        result = await mock_camunda_client.complete_task(
            task_id=task['id'],
            variables={
                'signed': True,
                'signatureData': 'signature_data',
                'certificateInfo': TEST_CERTIFICATES[0],
            }
        )
        assert result is True

