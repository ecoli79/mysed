from ldap3 import Server, Connection, SUBTREE, ALL
from models import User


LDAP_SERVER = '172.19.228.72'
BASE_DN = 'dc=permgp7,dc=ru'
#SEARCH_FILTER = '(uid={})'
SERVER = Server(LDAP_SERVER, get_info=ALL)
CONN = Connection(SERVER, user='cn=admin,dc=permgp7,dc=ru', password='Gkb6CodCod', auto_bind=True)


async def get_users():
    users = []
    search_filter = '(uid={})'
    CONN.search(BASE_DN, search_filter.format('*'), attributes=['uid', 'givenName', 'sn', 'mail'])
    try:
        for entry in CONN.entries:
            try:
                user = User(
                    login = entry.uid.value,
                    first_name = entry.givenName.value,
                    last_name = entry.sn.value,
                    email = entry.mail.value
                )

                users.append(user)
            except Exception as e:
                print(f"Error while get user from ldap_server {entry}: {e}")
        
        return users
    
    except Exception as e:
        print(f"Error connecting to LDAP server: {e}")
        return users


async def browse_ldap():
    """Рекурсивно обходит LDAP-дерево и выводит структуру"""
    search_filter='(objectClass=*)'
    attrs = ['objectClass', 'cn', 'ou', 'uid', 'mail', 'sn', 'givenName']
    try:
        CONN.search(
            BASE_DN,
            search_filter,
            search_scope = SUBTREE,
            attributes = attrs
        )
        print(f"\n🔍 Найдено записей в '{BASE_DN}': {len(CONN.entries)}\n")
        
        print(f"\n🌳 Структура начиная с: {BASE_DN}")
        print("─" * 60)

        for entry in CONN.entries:
            print(f"📍 DN: {entry.entry_dn}")

            # Перебираем только те атрибуты, которые есть у записи
            for attr_name in attrs:
                if attr_name in entry:  # ← Правильная проверка
                    values = entry[attr_name].values
                    print(f"   {attr_name}: {values}")

            print("   " + "─" * 40)
            
    except Exception as e:
        print(f"Ошибка при обходе: {e}") 


def get_groups():
    search_filter='(objectClass=posixGroup)'
    attrs = ['cn', 'memberUid', 'description']
    groups = []
 
    try:
        CONN.search(
            search_base = BASE_DN,
            search_filter = search_filter,
            search_scope = SUBTREE,
            attributes = attrs
        )

        for entry in CONN.entries:
            group = {
                'cn': entry.cn.value,
                'memberUid': entry.memberUid.values,
                'description': entry.description.value
            }
            groups.append(group)
        
        return groups

    except Exception as e:
        print(f"Ошибка при получении групп: {e}")
    


def load_ldap_users_by_group():
    try:
        users = get_users()
        # Создаём словарь: группа → список пользователей
        groups_dict = {}

        for user in users:
            user_data = user.model_dump()  # или просто user, если это словарь
            user_groups = user_data.get('groups', []) or []

            # Если у пользователя нет групп — отнесём в "No Group"
            if not user_groups:
                user_groups = ['No Group']

            for group in user_groups:
                if group not in groups_dict:
                    groups_dict[group] = []
                groups_dict[group].append(user_data)

        # Сортируем группы по имени
        sorted_groups = dict(sorted(groups_dict.items()))
    except Exception as e:
        print(f"Ошибка при загрузке пользователей из LDAP: {e}")

async def users_filter(users, query: str = ''):
    query = query.lower().strip()
    def user_to_dict(u):
        if isinstance(u, dict):
            return u
        return u.__dict__
    if query == '':
        return [user_to_dict(u) for u in users]
    return [
        user_to_dict(u) for u in users
        if any(query in str(val).lower() for val in user_to_dict(u).values())
    ]


