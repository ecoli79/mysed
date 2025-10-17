#!/usr/bin/env python3
"""
Скрипт для тестирования и настройки синхронизации пользователей
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ldap3 import Server, Connection, SUBTREE, ALL
from services.mayan_connector import MayanClient
from config.settings import config

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SyncTester:
    """Класс для тестирования компонентов синхронизации"""
    
    def test_ldap_connection(self):
        """Тестирует подключение к LDAP"""
        logger.info("Тестируем подключение к LDAP...")
        
        try:
            server = Server(config.ldap_server, get_info=ALL)
            conn = Connection(
                server, 
                user=config.ldap_user, 
                password=config.ldap_password, 
                auto_bind=True
            )
            
            # Простой поиск
            conn.search('dc=permgp7,dc=ru', '(uid=*)', SUBTREE, attributes=['uid'])
            
            logger.info(f"LDAP подключение успешно! Найдено {len(conn.entries)} пользователей")
            conn.unbind()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения к LDAP: {e}")
            return False
    
    def test_mayan_connection(self):
        """Тестирует подключение к Mayan EDMS"""
        logger.info("Тестируем подключение к Mayan EDMS...")
        
        try:
            client = MayanClient.create_default()
            
            # Тестируем подключение
            if client.test_connection():
                logger.info("Mayan EDMS подключение успешно!")
                
                # Получаем список пользователей
                users = client.get_users(page=1, page_size=5)
                logger.info(f"Найдено {len(users)} пользователей в Mayan EDMS")
                
                return True
            else:
                logger.error("Не удалось подключиться к Mayan EDMS")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка подключения к Mayan EDMS: {e}")
            return False
    
    def test_user_creation(self, test_username: str = "test_sync_user"):
        """Тестирует создание пользователя в Mayan EDMS"""
        logger.info(f"Тестируем создание пользователя {test_username}...")
        
        try:
            client = MayanClient.create_default()
            
            # Проверяем, существует ли пользователь
            users = client.get_users(page=1, page_size=1000)
            existing_users = {user['username'] for user in users}
            
            if test_username in existing_users:
                logger.info(f"Пользователь {test_username} уже существует")
                return True
            
            # Создаем тестового пользователя
            user_data = {
                'username': test_username,
                'first_name': 'Test',
                'last_name': 'User',
                'email': f'{test_username}@permgp7.ru',
                'password': 'TestPassword123!',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            }
            
            response = client._make_request('POST', 'users/', json=user_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Тестовый пользователь {test_username} создан успешно!")
                
                # Создаем API токен
                api_token = client.create_user_api_token(test_username, 'TestPassword123!')
                if api_token:
                    logger.info(f"API токен для тестового пользователя создан")
                
                return True
            else:
                logger.error(f"Ошибка создания тестового пользователя: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка тестирования создания пользователя: {e}")
            return False
    
    def show_ldap_users_sample(self, limit: int = 5):
        """Показывает пример пользователей из LDAP"""
        logger.info(f"Получаем пример {limit} пользователей из LDAP...")
        
        try:
            server = Server(config.ldap_server, get_info=ALL)
            conn = Connection(
                server, 
                user=config.ldap_user, 
                password=config.ldap_password, 
                auto_bind=True
            )
            
            conn.search(
                'dc=permgp7,dc=ru',
                '(uid=*)',
                SUBTREE,
                attributes=['uid', 'cn', 'givenName', 'sn', 'mail']
            )
            
            logger.info(f"Найдено {len(conn.entries)} пользователей в LDAP")
            logger.info("Пример пользователей:")
            
            for i, entry in enumerate(conn.entries[:limit]):
                try:
                    logger.info(f"   {i+1}. {entry.givenName.value} {entry.sn.value} ({entry.uid.value})")
                    if hasattr(entry, 'mail') and entry.mail:
                        logger.info(f"      Email: {entry.mail.value}")
                except Exception as e:
                    logger.warning(f"   {i+1}. Ошибка обработки пользователя: {e}")
            
            conn.unbind()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей из LDAP: {e}")
            return False
    
    def show_mayan_users_sample(self, limit: int = 5):
        """Показывает пример пользователей из Mayan EDMS"""
        logger.info(f"Получаем пример {limit} пользователей из Mayan EDMS...")
        
        try:
            client = MayanClient.create_default()
            users = client.get_users(page=1, page_size=limit)
            
            logger.info(f"Найдено {len(users)} пользователей в Mayan EDMS")
            logger.info("Пример пользователей:")
            
            for i, user in enumerate(users):
                logger.info(f"   {i+1}. {user.get('first_name', 'N/A')} {user.get('last_name', 'N/A')} ({user.get('username', 'N/A')})")
                logger.info(f"      Email: {user.get('email', 'N/A')}")
                logger.info(f"      Active: {user.get('is_active', 'N/A')}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей из Mayan EDMS: {e}")
            return False

def main():
    """Основная функция тестирования"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Тестирование компонентов синхронизации')
    parser.add_argument('--test-ldap', action='store_true', help='Тестировать подключение к LDAP')
    parser.add_argument('--test-mayan', action='store_true', help='Тестировать подключение к Mayan EDMS')
    parser.add_argument('--test-create', action='store_true', help='Тестировать создание пользователя')
    parser.add_argument('--show-ldap', action='store_true', help='Показать пример пользователей из LDAP')
    parser.add_argument('--show-mayan', action='store_true', help='Показать пример пользователей из Mayan EDMS')
    parser.add_argument('--all', action='store_true', help='Выполнить все тесты')
    
    args = parser.parse_args()
    
    tester = SyncTester()
    all_tests_passed = True
    
    if args.all or args.test_ldap:
        if not tester.test_ldap_connection():
            all_tests_passed = False
    
    if args.all or args.test_mayan:
        if not tester.test_mayan_connection():
            all_tests_passed = False
    
    if args.all or args.test_create:
        if not tester.test_user_creation():
            all_tests_passed = False
    
    if args.show_ldap:
        tester.show_ldap_users_sample()
    
    if args.show_mayan:
        tester.show_mayan_users_sample()
    
    if not args.test_ldap and not args.test_mayan and not args.test_create and not args.show_ldap and not args.show_mayan and not args.all:
        # Если никаких аргументов не передано, выполняем базовые тесты
        logger.info("Выполняем базовые тесты...")
        
        if not tester.test_ldap_connection():
            all_tests_passed = False
        
        if not tester.test_mayan_connection():
            all_tests_passed = False
        
        tester.show_ldap_users_sample(3)
        tester.show_mayan_users_sample(3)
    
    if all_tests_passed:
        logger.info("Все тесты прошли успешно!")
        sys.exit(0)
    else:
        logger.error("Некоторые тесты не прошли!")
        sys.exit(1)

if __name__ == "__main__":
    main()