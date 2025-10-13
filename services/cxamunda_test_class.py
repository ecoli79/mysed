# camunda_client.py
import requests
from typing import Dict, List, Any, Optional

class CamundaClient:
    def __init__(self, base_url: str = "https://172.19.228.72:8443/engine-rest"):
        self.base_url = base_url  # убираем лишний слэш
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def start_process_instance(self, process_key: str, variables: Optional[Dict] = None) -> Dict:
        """
        Запускает процесс по ключу.
        """
        url = f"{self.base_url}/process-definition/key/{process_key}/start"
        payload = {"variables": variables} if variables else {}
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_process_instances(self, process_definition_key: Optional[str] = None) -> List[Dict]:
        """
        Получает список запущенных экземпляров процессов.
        """
        url = f"{self.base_url}/process-instance"
        params = {}
        if process_definition_key:
            params["processDefinitionKey"] = process_definition_key

        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_tasks(self, assignee: Optional[str] = None) -> List[Dict]:
        """
        Получает список задач (User Tasks).
        """
        url = f"{self.base_url}/task"
        params = {}
        if assignee:
            params["assignee"] = assignee

        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def complete_task(self, task_id: str, variables: Optional[Dict] = None) -> Dict:
        """
        Завершает задачу (например, user task).
        """
        url = f"{self.base_url}/task/{task_id}/complete"
        payload = {"variables": variables} if variables else {}
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_variables(self, process_instance_id: str, var_names: Optional[List[str]] = None) -> Dict:
        """
        Получает переменные процесса.
        """
        url = f"{self.base_url}/process-instance/{process_instance_id}/variables"
        if var_names:
            url += "?" + "&".join([f"variableName={name}" for name in var_names])

        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def close(self):
        self.session.close()

    

if __name__ == "__main__":
    camunda_client = CamundaClient()
    for process_instance in camunda_client.get_process_instances():
        print(process_instance)

    tasks = camunda_client.get_tasks('namassold')
    for task in tasks:
        print(task)

