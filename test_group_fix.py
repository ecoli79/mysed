#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправления добавления пользователей в группы
"""

import sys
import os
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mayan_connector import MayanClient
from config.settings import config
from app_logging.logger import setup_logging, get_logger

# Настройка логирования
setup_logging()
logger = get_logger(__name__)

def test_group_operations():
    """Тестирует операции с группами"""
    logger.info("🧪 Тестируем исправление операций с группами")
    
    try:
        # Создаем клиент с системными учетными данными
        mayan_client = MayanClient(
            base_url=config.mayan_url,
            username=config.mayan_username,
            password=config.mayan_password,
            api_token=config.mayan_api_token,
            verify_ssl=False
        )
        
        # Получаем группы
        logger.info("📋 Получаем список групп")
        groups = mayan_client.get_groups()
        logger.info(f"📋 Найдено {len(groups)} групп")
        
        if not groups:
            logger.warning("⚠️ Нет групп для тестирования")
            return
        
        # Получаем пользователей
        logger.info("👤 Получаем список пользователей")
        users = mayan_client.get_users()
        logger.info(f"👤 Найдено {len(users)} пользователей")
        
        if not users:
            logger.warning("⚠️ Нет пользователей для тестирования")
            return
        
        # Выбираем первую группу и первого пользователя для тестирования
        test_group = groups[0]
        test_user = users[0]
        
        group_id = test_group.get('id')
        group_name = test_group.get('name')
        username = test_user.get('username')
        
        logger.info(f"🧪 Тестируем с группой: {group_name} (ID: {group_id})")
        logger.info(f"🧪 Тестируем с пользователем: {username}")
        
        # Получаем текущих участников группы
        logger.info(f"📋 Получаем текущих участников группы {group_name}")
        current_members = mayan_client.get_group_users(group_id)
        current_usernames = [user.get('username') for user in current_members]
        logger.info(f"📋 Текущие участники: {current_usernames}")
        
        # Тестируем добавление пользователя в группу
        if username not in current_usernames:
            logger.info(f"➕ Тестируем добавление пользователя {username} в группу {group_name}")
            success = mayan_client.add_user_to_group(group_id, username)
            
            if success:
                logger.info(f"✅ Пользователь {username} успешно добавлен в группу {group_name}")
                
                # Проверяем, что пользователь действительно добавлен
                updated_members = mayan_client.get_group_users(group_id)
                updated_usernames = [user.get('username') for user in updated_members]
                
                if username in updated_usernames:
                    logger.info(f"✅ Подтверждено: пользователь {username} теперь в группе {group_name}")
                    
                    # Тестируем удаление пользователя из группы
                    logger.info(f"➖ Тестируем удаление пользователя {username} из группы {group_name}")
                    remove_success = mayan_client.remove_user_from_group(group_id, username)
                    
                    if remove_success:
                        logger.info(f"✅ Пользователь {username} успешно удален из группы {group_name}")
                        
                        # Проверяем, что пользователь действительно удален
                        final_members = mayan_client.get_group_users(group_id)
                        final_usernames = [user.get('username') for user in final_members]
                        
                        if username not in final_usernames:
                            logger.info(f"✅ Подтверждено: пользователь {username} больше не в группе {group_name}")
                        else:
                            logger.error(f"❌ Ошибка: пользователь {username} все еще в группе {group_name}")
                    else:
                        logger.error(f"❌ Не удалось удалить пользователя {username} из группы {group_name}")
                else:
                    logger.error(f"❌ Ошибка: пользователь {username} не найден в группе {group_name} после добавления")
            else:
                logger.error(f"❌ Не удалось добавить пользователя {username} в группу {group_name}")
        else:
            logger.info(f"ℹ️ Пользователь {username} уже в группе {group_name}, тестируем удаление")
            
            # Тестируем удаление пользователя из группы
            logger.info(f"➖ Тестируем удаление пользователя {username} из группы {group_name}")
            remove_success = mayan_client.remove_user_from_group(group_id, username)
            
            if remove_success:
                logger.info(f"✅ Пользователь {username} успешно удален из группы {group_name}")
                
                # Проверяем, что пользователь действительно удален
                updated_members = mayan_client.get_group_users(group_id)
                updated_usernames = [user.get('username') for user in updated_members]
                
                if username not in updated_usernames:
                    logger.info(f"✅ Подтверждено: пользователь {username} больше не в группе {group_name}")
                    
                    # Возвращаем пользователя в группу
                    logger.info(f"➕ Возвращаем пользователя {username} в группу {group_name}")
                    add_success = mayan_client.add_user_to_group(group_id, username)
                    
                    if add_success:
                        logger.info(f"✅ Пользователь {username} успешно возвращен в группу {group_name}")
                    else:
                        logger.error(f"❌ Не удалось вернуть пользователя {username} в группу {group_name}")
                else:
                    logger.error(f"❌ Ошибка: пользователь {username} все еще в группе {group_name}")
            else:
                logger.error(f"❌ Не удалось удалить пользователя {username} из группы {group_name}")
        
        logger.info("✅ Тестирование завершено успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")

def main():
    """Основная функция"""
    logger.info("🚀 Запуск тестирования исправления операций с группами")
    logger.info(f"⏰ Время запуска: {datetime.now().isoformat()}")
    
    test_group_operations()

if __name__ == "__main__":
    main()
