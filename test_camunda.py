import services.camunda_connector

camunda_client = services.camunda_connector.CamundaClient(
    base_url='https://172.19.228.72:8443',
    username='dvimpolitov',
    password='gkb6codcod'
)

process_instance_id = 'a9db872b-a066-11f0-9a93-02420ac80202'

print("=== ТЕСТ ПОЛУЧЕНИЯ ПЕРЕМЕННЫХ ЗАВЕРШЕННОГО ПРОЦЕССА ===")

# Тест 1: Получение всех переменных процесса
print("\n1. Получение всех переменных процесса:")
try:
    endpoint = 'history/variable-instance'
    params = {
        'processInstanceId': process_instance_id,
        'deserializeValues': 'true'
    }
    response = camunda_client._make_request('GET', endpoint, params=params)
    print(f"Статус ответа: {response.status_code}")
    
    if response.status_code == 200:
        variables_data = response.json()
        print(f"✅ Найдено {len(variables_data)} переменных:")
        for var in variables_data:
            print(f"   - {var.get('name')}: {var.get('value')} (тип: {var.get('type')})")
    else:
        print(f"❌ Ошибка: {response.text}")
        
except Exception as e:
    print(f"❌ Исключение: {e}")

# Тест 2: Получение конкретных переменных
print("\n2. Получение конкретных переменных:")
try:
    endpoint = 'history/variable-instance'
    params = {
        'processInstanceId': process_instance_id,
        'deserializeValues': 'true',
        'variableNames': 'assigneeList,documentName,documentContent'
    }
    response = camunda_client._make_request('GET', endpoint, params=params)
    print(f"Статус ответа: {response.status_code}")
    
    if response.status_code == 200:
        variables_data = response.json()
        print(f"✅ Найдено {len(variables_data)} переменных:")
        for var in variables_data:
            print(f"   - {var.get('name')}: {var.get('value')}")
    else:
        print(f"❌ Ошибка: {response.text}")
        
except Exception as e:
    print(f"❌ Исключение: {e}")

print("\n=== ЗАКЛЮЧЕНИЕ ===")
print("Если переменные получены - можно использовать исторический endpoint")
print("Если ошибка 404/500 - переменные могли быть удалены или недоступны")