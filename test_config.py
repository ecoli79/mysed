# Создайте файл test_config.py в корне проекта
#!/usr/bin/env python3

import os
import sys
sys.path.append(os.path.dirname(__file__))

from config.settings import config

print("=== Диагностика конфигурации LDAP ===")
print(f"Рабочая директория: {os.getcwd()}")
print(f"Путь к .env файлу: {os.path.join(os.getcwd(), '.env')}")
print(f".env файл существует: {os.path.exists('.env')}")
print()

print("=== Настройки LDAP ===")
print(f"LDAP_SERVER: '{config.ldap_server}'")
print(f"LDAP_USER: '{config.ldap_user}'")
print(f"LDAP_PASSWORD: {'*' * len(config.ldap_password) if config.ldap_password else 'НЕ УСТАНОВЛЕН'}")
print(f"LDAP_BASE_DN: '{config.ldap_base_dn}'")
print()

print("=== Переменные окружения ===")
print(f"LDAP_SERVER env: '{os.getenv('LDAP_SERVER', 'НЕ НАЙДЕНА')}'")
print(f"LDAP_USER env: '{os.getenv('LDAP_USER', 'НЕ НАЙДЕНА')}'")
print(f"LDAP_PASSWORD env: {'УСТАНОВЛЕНА' if os.getenv('LDAP_PASSWORD') else 'НЕ НАЙДЕНА'}")
print(f"LDAP_BASE_DN env: '{os.getenv('LDAP_BASE_DN', 'НЕ НАЙДЕНА')}'")
print()

try:
    from auth.ldap_auth import LDAPAuthenticator
    print("✅ LDAPAuthenticator инициализирован успешно")
except Exception as e:
    print(f"❌ Ошибка инициализации LDAPAuthenticator: {e}")

print()
print("=== Тест подключения к LDAP ===")
if config.ldap_server and config.ldap_user and config.ldap_password:
    try:
        from ldap3 import Server, Connection
        server = Server(config.ldap_server)
        conn = Connection(server, user=config.ldap_user, password=config.ldap_password, auto_bind=True)
        print("✅ Подключение к LDAP успешно")
        conn.unbind()
    except Exception as e:
        print(f"❌ Ошибка подключения к LDAP: {e}")
else:
    print("❌ Настройки LDAP не полные - пропускаем тест подключения")