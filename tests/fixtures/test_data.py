"""
Тестовые данные для использования в тестах
"""
from typing import Dict, List, Any


# Тестовые пользователи
TEST_USERS: List[Dict[str, Any]] = [
    {
        'username': 'test_user',
        'first_name': 'Тестовый',
        'last_name': 'Пользователь',
        'email': 'test@example.com',
        'groups': ['users'],
        'dn': 'uid=test_user,ou=People,dc=permgp7,dc=ru',
    },
    {
        'username': 'admin_user',
        'first_name': 'Администратор',
        'last_name': 'Системы',
        'email': 'admin@example.com',
        'groups': ['admins', 'users'],
        'dn': 'uid=admin_user,ou=People,dc=permgp7,dc=ru',
    },
    {
        'username': 'reviewer_user',
        'first_name': 'Рецензент',
        'last_name': 'Документов',
        'email': 'reviewer@example.com',
        'groups': ['users'],
        'dn': 'uid=reviewer_user,ou=People,dc=permgp7,dc=ru',
    },
]

# Тестовые группы LDAP
TEST_GROUPS: List[Dict[str, Any]] = [
    {
        'cn': 'users',
        'dn': 'cn=users,ou=Groups,dc=permgp7,dc=ru',
        'members': ['uid=test_user,ou=People,dc=permgp7,dc=ru'],
    },
    {
        'cn': 'admins',
        'dn': 'cn=admins,ou=Groups,dc=permgp7,dc=ru',
        'members': ['uid=admin_user,ou=People,dc=permgp7,dc=ru'],
    },
]

# Тестовые документы
TEST_DOCUMENTS: List[Dict[str, Any]] = [
    {
        'document_id': '123',
        'label': 'Тестовый документ 1',
        'filename': 'test_document_1.pdf',
        'file_latest_filename': 'test_document_1.pdf',
        'document_type': 'Входящие',
        'cabinet': 'Входящие письма',
        'file_size': 1024,
    },
    {
        'document_id': '124',
        'label': 'Тестовый документ 2',
        'filename': 'test_document_2.pdf',
        'file_latest_filename': 'test_document_2.pdf',
        'document_type': 'Входящие',
        'cabinet': 'Входящие письма',
        'file_size': 2048,
    },
]

# Тестовые процессы Camunda
TEST_PROCESS_DEFINITIONS: List[Dict[str, Any]] = [
    {
        'id': 'test_process:1:123',
        'key': 'test_process',
        'name': 'Тестовый процесс',
        'version': 1,
        'deployment_id': 'deployment_123',
    },
    {
        'id': 'document_review:1:456',
        'key': 'document_review',
        'name': 'Ознакомление с документом',
        'version': 1,
        'deployment_id': 'deployment_456',
    },
]

# Тестовые задачи Camunda
TEST_TASKS: List[Dict[str, Any]] = [
    {
        'id': 'task_123',
        'name': 'Тестовая задача',
        'assignee': 'test_user',
        'process_instance_id': 'proc_inst_123',
        'process_definition_id': 'test_process:1:123',
        'task_definition_key': 'userTask1',
        'created': '2024-01-15T10:00:00.000+0000',
    },
    {
        'id': 'task_124',
        'name': 'Задача ознакомления',
        'assignee': 'reviewer_user',
        'process_instance_id': 'proc_inst_124',
        'process_definition_id': 'document_review:1:456',
        'task_definition_key': 'reviewTask',
        'created': '2024-01-15T11:00:00.000+0000',
    },
]

# Тестовые сертификаты КриптоПро
TEST_CERTIFICATES: List[Dict[str, Any]] = [
    {
        'index': 0,
        'subject': 'CN=Тестовый Пользователь, O=Организация, C=RU',
        'issuer': 'CN=Test CA, O=Test Org, C=RU',
        'validFrom': '2024-01-01',
        'validTo': '2025-01-01',
        'isValid': True,
    },
    {
        'index': 1,
        'subject': 'CN=Администратор Системы, O=Организация, C=RU',
        'issuer': 'CN=Test CA, O=Test Org, C=RU',
        'validFrom': '2024-01-01',
        'validTo': '2025-01-01',
        'isValid': True,
    },
]

# Тестовые email сообщения
TEST_EMAILS: List[Dict[str, Any]] = [
    {
        'message_id': '<test_email_1@example.com>',
        'from_address': 'sender@example.com',
        'subject': 'Тестовое письмо 1',
        'body': 'Содержимое тестового письма 1',
        'received_date': '2024-01-15T10:00:00',
        'attachments': [
            {
                'filename': 'attachment_1.pdf',
                'content': b'PDF content here',
                'mimetype': 'application/pdf',
                'size': 1024,
            },
        ],
    },
    {
        'message_id': '<test_email_2@example.com>',
        'from_address': 'sender@example.com',
        'subject': 'Тестовое письмо 2',
        'body': 'Содержимое тестового письма 2',
        'received_date': '2024-01-15T11:00:00',
        'attachments': [],
    },
]

# Тестовые BPMN процессы
TEST_BPMN_PROCESSES: Dict[str, str] = {
    'simple_process': '''<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" 
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn" 
             id="Definitions_1" 
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="SimpleProcess" name="Простой процесс" isExecutable="true">
    <startEvent id="StartEvent_1" name="Начало" />
    <userTask id="userTask1" name="Пользовательская задача" />
    <endEvent id="EndEvent_1" name="Конец" />
    <sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="userTask1" />
    <sequenceFlow id="Flow_2" sourceRef="userTask1" targetRef="EndEvent_1" />
  </process>
</definitions>''',
}

