#!/usr/bin/env python3
"""
Скрипт для тестирования синхронизации пользователей между Mayan EDMS и OpenLDAP
"""

import sys
import os
import logging
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mayan_connector import MayanClient
from services.user_sync_manager import UserSyncManager
from config.settings import config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/user_sync.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def test_mayan_connection():
    """Тестирует подключение к Mayan EDMS"""
    logger.info("🔍 Тестируем подключение к Mayan EDMS")
    
    try:
        # Создаем клиент с системными учетными данными
        mayan_client = MayanClient(
            base_url=config.mayan_url,
            username=config.mayan_username,
            password=config.mayan_password,
            api_token=config.mayan_api_token,
            verify_ssl=False
        )
        
        # Тестируем получение групп
        logger.info("📋 Получаем группы из Mayan EDMS")
        groups = mayan_client.get_groups()
        logger.info(f"📋 Найдено {len(groups)} групп")
        
        for group in groups[:5]:  # Показываем первые 5 групп
            logger.info(f"   - {group.get('name')} (ID: {group.get('id')})")
        
        # Тестируем получение пользователей
        logger.info("👤 Получаем пользователей из Mayan EDMS")
        users = mayan_client.get_users()
        logger.info(f"👤 Найдено {len(users)} пользователей")
        
        for user in users[:5]:  # Показываем первых 5 пользователей
            logger.info(f"   - {user.get('username')} ({user.get('first_name')} {user.get('last_name')})")
        
        return mayan_client
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Mayan EDMS: {e}")
        return None

def test_user_group_operations(mayan_client):
    """Тестирует операции с пользователями и группами"""
    logger.info("🔍 Тестируем операции с пользователями и группами")
    
    try:
        # Получаем первую группу для тестирования
        groups = mayan_client.get_groups()
        if not groups:
            logger.warning("⚠️ Нет групп для тестирования")
            return
        
        test_group = groups[0]
        group_id = test_group.get('id')
        group_name = test_group.get('name')
        
        logger.info(f"🧪 Тестируем с группой: {group_name} (ID: {group_id})")
        
        # Получаем пользователей группы
        logger.info(f"📋 Получаем пользователей группы {group_name}")
        group_users = mayan_client.get_group_users(group_id)
        logger.info(f"📋 В группе {group_name} найдено {len(group_users)} пользователей")
        
        for user in group_users[:3]:  # Показываем первых 3 пользователей
            logger.info(f"   - {user.get('username')}")
        
        # Тестируем добавление пользователя в группу (если есть пользователи)
        users = mayan_client.get_users()
        if users:
            test_user = users[0]
            username = test_user.get('username')
            
            logger.info(f"➕ Тестируем добавление пользователя {username} в группу {group_name}")
            success = mayan_client.add_user_to_group(group_id, username)
            
            if success:
                logger.info(f"✅ Пользователь {username} успешно добавлен в группу {group_name}")
            else:
                logger.error(f"❌ Не удалось добавить пользователя {username} в группу {group_name}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования операций: {e}")

def main():
    """Основная функция"""
    logger.info("🚀 Запуск тестирования синхронизации пользователей")
    logger.info(f"⏰ Время запуска: {datetime.now().isoformat()}")
    
    # Тестируем подключение к Mayan EDMS
    mayan_client = test_mayan_connection()
    
    if mayan_client:
        # Тестируем операции с пользователями и группами
        test_user_group_operations(mayan_client)
        
        logger.info("✅ Тестирование завершено успешно")
    else:
        logger.error("❌ Тестирование завершено с ошибками")
        sys.exit(1)

if __name__ == "__main__":
    main()
