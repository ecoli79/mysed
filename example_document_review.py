#!/usr/bin/env python3
"""
Пример использования процесса ознакомления с документом
Демонстрирует, как сохраняются и извлекаются переменные с датами ознакомления
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.camunda_connector import CamundaClient
from datetime import datetime
import json

def main():
    # Конфигурация Camunda
    CAMUNDA_URL = 'https://172.19.228.72:8443'
    CAMUNDA_USERNAME = 'dvimpolitov'
    CAMUNDA_PASSWORD = 'gkb6codcod'
    
    # Создание клиента
    camunda = CamundaClient(CAMUNDA_URL, CAMUNDA_USERNAME, CAMUNDA_PASSWORD)
    
    print('=== Пример процесса ознакомления с документом ===\n')
    
    # 1. Запуск процесса ознакомления
    print('1. Запуск процесса ознакомления...')
    
    document_name = 'Политика информационной безопасности'
    document_content = 'Данный документ содержит правила работы с информационными системами...'
    assignee_list = ['user1', 'user2', 'user3']
    
    process_id = camunda.start_document_review_process(
        document_name=document_name,
        document_content=document_content,
        assignee_list=assignee_list,
        business_key=f'doc_review_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    )
    
    if process_id:
        print(f'Процесс запущен! ID: {process_id}')
    else:
        print('Ошибка при запуске процесса')
        return
    
    print(f'Документ: {document_name}')
    print(f'Пользователи: {', '.join(assignee_list)}')
    print()
    
    # 2. Получение задач для каждого пользователя
    print('2. Получение задач для пользователей...')
    
    for user in assignee_list:
        tasks = camunda.get_user_tasks(user, active_only=True)
        review_tasks = [task for task in tasks if task.task_definition_key == 'reviewTask']
        
        if review_tasks:
            task = review_tasks[0]
            print(f'📋 Пользователь {user}: задача {task.id}')
            
            # 3. Завершение задачи с сохранением даты ознакомления
            print(f'3. Завершение ознакомления для пользователя {user}...')
            
            # Симулируем разные даты ознакомления для каждого пользователя
            review_dates = {
                'user1': '2024-01-15',
                'user2': '2024-01-16', 
                'user3': '2024-01-17'
            }
            
            review_comments = {
                'user1': 'Ознакомился с документом',
                'user2': 'Все понятно, готов к работе',
                'user3': 'Требуются дополнительные разъяснения'
            }
            
            success = camunda.complete_document_review_with_storage(
                task_id=task.id,
                review_date=review_dates[user],
                review_comment=review_comments[user]
            )
            
            if success:
                print(f'Пользователь {user} ознакомился {review_dates[user]}')
            else:
                print(f'Ошибка при завершении ознакомления для {user}')
        else:
            print(f'Пользователь {user}: нет активных задач')
    
    print()
    
    # 4. Проверка статуса ознакомления
    print('4. Проверка статуса ознакомления...')
    
    status = camunda.get_document_review_status(process_id)
    
    if status:
        print(f'Статус процесса:')
        document_name = status.get('document_name', 'Не указан')
        completed = status.get('completed_reviews', 0)
        total = status.get('total_reviews', 0)
        is_completed = status.get('is_completed', False)
        
        print(f'   Документ: {document_name}')
        print(f'   Завершено: {completed} из {total}')
        print(f'   Статус: {"Завершен" if is_completed else " В процессе"}')
        print()
        
        # Детали по каждому пользователю
        review_dates = status.get('review_dates', {})
        review_comments = status.get('review_comments', {})
        review_status = status.get('review_status', {})
        
        print('Детали ознакомления:')
        for user in assignee_list:
            if review_status.get(user, False):
                review_date = review_dates.get(user, 'Не указана')
                review_comment = review_comments.get(user, '')
                print(f' {user}: {review_date}')
                if review_comment:
                    print(f'  {review_comment}')
            else:
                print(f'   ⏳ {user}: Ожидает ознакомления')
        
        print()
        
        # 5. Демонстрация переменных процесса
        print('5. Переменные процесса:')
        process_vars = camunda.get_process_instance_variables(process_id)
        
        review_dates_json = json.dumps(process_vars.get('reviewDates', {}), ensure_ascii=False, indent=2)
        review_comments_json = json.dumps(process_vars.get('reviewComments', {}), ensure_ascii=False, indent=2)
        review_status_json = json.dumps(process_vars.get('reviewStatus', {}), ensure_ascii=False, indent=2)
        completed_reviews = process_vars.get('completedReviews', 0)
        total_reviews = process_vars.get('totalReviews', 0)
        
        print(f'   reviewDates: {review_dates_json}')
        print(f'   reviewComments: {review_comments_json}')
        print(f'   reviewStatus: {review_status_json}')
        print(f'   completedReviews: {completed_reviews}')
        print(f'   totalReviews: {total_reviews}')
    
    print('\n=== Пример завершен ===')

if __name__ == '__main__':
    main()
