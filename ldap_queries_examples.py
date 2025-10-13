#!/usr/bin/env python3
"""
Примеры запросов к OpenLDAP для работы с департаментами и группами
"""

from ldap_users import (
    get_departments, 
    get_users_by_department, 
    get_users_by_group,
    get_department_heads,
    get_hr_staff,
    get_it_staff,
    get_all_groups,
    get_users_from_dn
)

def example_queries():
    """Примеры различных запросов к LDAP"""
    
    print("=== ПРИМЕРЫ ЗАПРОСОВ К OPENLDAP ===\n")
    
    # 1. Получение всех департаментов
    print("1. Получение всех департаментов:")
    departments = get_departments()
    for dept in departments:
        print(f"   - {dept['name']}: {dept['description']}")
    print()
    
    # 2. Получение пользователей из конкретного департамента
    print("2. Получение пользователей из отдела кадров:")
    hr_users = get_users_by_department('HR')
    for user in hr_users:
        print(f"   - {user.first_name} {user.last_name} ({user.login}) - {user.email}")
    print()
    
    # 3. Получение пользователей из IT отдела
    print("3. Получение пользователей из IT отдела:")
    it_users = get_users_by_department('IT')
    for user in it_users:
        print(f"   - {user.first_name} {user.last_name} ({user.login}) - {user.email}")
    print()
    
    # 4. Получение всех начальников отделов
    print("4. Получение всех начальников отделов:")
    heads = get_department_heads()
    for head in heads:
        print(f"   - {head.first_name} {head.last_name} ({head.login}) - {head.email}")
    print()
    
    # 5. Получение сотрудников отдела кадров через группу
    print("5. Получение сотрудников отдела кадров через группу:")
    hr_staff = get_hr_staff()
    for staff in hr_staff:
        print(f"   - {staff.first_name} {staff.last_name} ({staff.login}) - {staff.email}")
    print()
    
    # 6. Получение IT сотрудников через группу
    print("6. Получение IT сотрудников через группу:")
    it_staff = get_it_staff()
    for staff in it_staff:
        print(f"   - {staff.first_name} {staff.last_name} ({staff.login}) - {staff.email}")
    print()
    
    # 7. Получение всех групп
    print("7. Получение всех групп:")
    all_groups = get_all_groups()
    for group in all_groups:
        group_type = "динамическая" if group['is_dynamic'] else "статическая"
        print(f"   - {group['cn']} ({group['type']}, {group_type}): {group['description']}")
    print()
    
    # 8. Получение пользователей из конкретной группы
    print("8. Получение пользователей из группы 'Managers':")
    managers = get_users_by_group('Managers', 'Roles')
    for manager in managers:
        print(f"   - {manager.first_name} {manager.last_name} ({manager.login}) - {manager.email}")
    print()
    
    # 9. Получение пользователей из динамической группы
    print("9. Получение пользователей из динамической группы 'All_HR_Users':")
    all_hr = get_users_by_group('All_HR_Users', 'Groups')
    for user in all_hr:
        print(f"   - {user.first_name} {user.last_name} ({user.login}) - {user.email}")
    print()


def advanced_queries():
    """Примеры более сложных запросов"""
    
    print("=== РАСШИРЕННЫЕ ЗАПРОСЫ ===\n")
    
    # 1. Получение всех пользователей из всех департаментов
    print("1. Все пользователи по департаментам:")
    departments = get_departments()
    for dept in departments:
        users = get_users_by_department(dept['name'])
        print(f"   {dept['name']} ({len(users)} пользователей):")
        for user in users:
            print(f"     - {user.first_name} {user.last_name}")
        print()
    
    # 2. Статистика по группам
    print("2. Статистика по группам:")
    all_groups = get_all_groups()
    for group in all_groups:
        users = get_users_by_group(group['cn'], group['type'])
        print(f"   {group['cn']}: {len(users)} пользователей")
    print()


def query_by_criteria():
    """Примеры запросов по различным критериям"""
    
    print("=== ЗАПРОСЫ ПО КРИТЕРИЯМ ===\n")
    
    # 1. Найти всех пользователей с определенным доменом email
    print("1. Пользователи с email доменом '@permgp7.ru':")
    departments = get_departments()
    for dept in departments:
        users = get_users_by_department(dept['name'])
        for user in users:
            if user.email and '@permgp7.ru' in user.email:
                print(f"   - {user.first_name} {user.last_name} ({user.email})")
    print()
    
    # 2. Найти пользователей по части имени
    print("2. Поиск пользователей по части имени 'Иван':")
    departments = get_departments()
    for dept in departments:
        users = get_users_by_department(dept['name'])
        for user in users:
            if 'Иван' in user.first_name or 'Иван' in user.last_name:
                print(f"   - {user.first_name} {user.last_name} из {dept['name']}")
    print()


if __name__ == "__main__":
    try:
        example_queries()
        advanced_queries()
        query_by_criteria()
    except Exception as e:
        print(f"Ошибка при выполнении запросов: {e}")
