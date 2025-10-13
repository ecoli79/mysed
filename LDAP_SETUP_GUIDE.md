# Руководство по настройке структуры департаментов в OpenLDAP

## Обзор

Данное руководство описывает, как организовать структуру департаментов в OpenLDAP, сохраняя простоту иерархии и обеспечивая удобство работы для различных приложений.

## Рекомендуемая структура

```
dc=permgp7,dc=ru
├── ou=People                    # Все пользователи
│   ├── ou=HR                   # Отдел кадров
│   ├── ou=IT                   # IT отдел
│   ├── ou=Finance              # Финансовый отдел
│   └── ou=Management           # Руководство
├── ou=Groups                   # Все группы
│   ├── cn=users               # Существующая группа
│   ├── cn=admins              # Существующая группа
│   ├── cn=HR_Staff           # Сотрудники отдела кадров
│   └── cn=IT_Staff           # Сотрудники IT отдела
└── ou=Roles                   # Ролевые группы
    ├── cn=Managers
    ├── cn=Employees
    └── cn=DepartmentHeads     # Начальники отделов
```

## Шаги настройки

### 1. Создание структуры

Используйте файл `ldap_structure_setup.ldif` для создания структуры:

```bash
# Добавление структуры в LDAP
ldapadd -x -D "cn=admin,dc=permgp7,dc=ru" -W -f ldap_structure_setup.ldif
```

### 2. Настройка memberOf overlay (рекомендуется)

Для автоматического поддержания обратных ссылок на группы:

```bash
# Добавление overlay в конфигурацию OpenLDAP
ldapmodify -Y EXTERNAL -H ldapi:/// <<EOF
dn: olcDatabase={1}mdb,cn=config
changetype: modify
add: olcOverlay
olcOverlay: memberof

add: olcMemberOfGroupOC
olcMemberOfGroupOC: groupOfNames

add: olcMemberOfMemberAD
olcMemberOfMemberAD: member

add: olcMemberOfMemberOfAD
olcMemberOfMemberOfAD: memberOf

add: olcMemberOfRefInt
olcMemberOfRefInt: TRUE
EOF
```

### 3. Проверка структуры

```bash
# Просмотр созданной структуры
ldapsearch -x -D "cn=admin,dc=permgp7,dc=ru" -W -b "dc=permgp7,dc=ru" -s sub "(objectClass=organizationalUnit)"
```

## Типы групп

### 1. Статические группы (groupOfNames)
- Содержат явный список участников
- Участники добавляются/удаляются вручную
- Пример: `cn=DepartmentHeads`

### 2. Динамические группы (groupOfURLs)
- Участники определяются поисковым запросом
- Автоматически обновляются при изменении данных
- Пример: `cn=All_HR_Users`

## Примеры использования

### Python API

```python
from ldap_users import (
    get_departments,
    get_users_by_department,
    get_users_by_group,
    get_department_heads
)

# Получить все департаменты
departments = get_departments()

# Получить пользователей отдела кадров
hr_users = get_users_by_department('HR')

# Получить всех начальников отделов
heads = get_department_heads()

# Получить пользователей из группы
managers = get_users_by_group('Managers', 'Roles')
```

### LDAP запросы

```bash
# Получить всех пользователей отдела кадров
ldapsearch -x -D "cn=admin,dc=permgp7,dc=ru" -W \
  -b "ou=HR,ou=People,dc=permgp7,dc=ru" \
  "(objectClass=inetOrgPerson)"

# Получить всех участников группы
ldapsearch -x -D "cn=admin,dc=permgp7,dc=ru" -W \
  -b "cn=DepartmentHeads,ou=Roles,dc=permgp7,dc=ru" \
  "(objectClass=groupOfNames)"

# Получить всех пользователей через динамическую группу
ldapsearch -x -D "cn=admin,dc=permgp7,dc=ru" -W \
  -b "ou=HR,ou=People,dc=permgp7,dc=ru" \
  "(objectClass=inetOrgPerson)"
```

## Преимущества данного подхода

1. **Простота иерархии**: Не более 2-3 уровней вложенности
2. **Гибкость**: Легко добавлять новые департаменты и группы
3. **Производительность**: Быстрые запросы благодаря простой структуре
4. **Совместимость**: Работает с любыми LDAP клиентами
5. **Масштабируемость**: Легко расширяется при росте организации

## Рекомендации

1. **Используйте OU для логического разделения** по департаментам
2. **Используйте группы для ролей и функций**
3. **Настройте memberOf overlay** для упрощения запросов
4. **Документируйте назначение каждой группы**
5. **Регулярно проверяйте актуальность членства в группах**

## Миграция существующих данных

Если у вас уже есть пользователи в корне базы:

```bash
# Перемещение пользователя в департамент
ldapmodify -x -D "cn=admin,dc=permgp7,dc=ru" -W <<EOF
dn: uid=existing_user,dc=permgp7,dc=ru
changetype: modrdn
newrdn: uid=existing_user
deleteoldrdn: 1
newsuperior: ou=HR,ou=People,dc=permgp7,dc=ru
EOF
```

## Мониторинг и обслуживание

1. **Регулярно проверяйте целостность данных**
2. **Мониторьте производительность запросов**
3. **Ведите журнал изменений структуры**
4. **Создавайте резервные копии перед изменениями**
