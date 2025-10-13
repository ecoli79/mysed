import requests.auth
import pycamunda.task
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


url = 'https://172.19.228.72:8443/engine-rest'

# Создаём сессию с отключённой проверкой SSL
session = requests.Session()
session.verify = False
session.auth = requests.auth.HTTPBasicAuth('dvimpolitov', 'gkb6codcod')


get_tasks = pycamunda.task.GetList(url)
get_tasks.session = session
task = pycamunda.task.Get(url, id_='73713250-895c-11f0-8302-02420ac80202')
print(task)
# pycamunda.task.SetAssignee(url, id_='73713250-895c-11f0-8302-02420ac80202', user_id='namassold')
# tasks = get_tasks()

# for task in tasks:
#     print(task)