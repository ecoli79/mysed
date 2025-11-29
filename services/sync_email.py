import sys
import os
import asyncio
from pathlib import Path

# Добавляем путь к проекту
project_path = Path(__file__).parent
sys.path.insert(0, str(project_path))

import logging
from datetime import datetime
from typing import List, Optional
import argparse

from services.email_client import EmailClient
from services.email_processor import EmailProcessor
from services.mayan_connector import MayanClient
from services.email_validator import EmailValidator
from config.settings import config
from app_logging.logger import setup_logging, get_logger

# Настраиваем логирование
setup_logging()
logger = get_logger(__name__)


async def sync_emails(dry_run: bool = False, max_emails: Optional[int] = None, include_read: bool = False) -> dict:
    """
    Синхронизирует входящие письма
    
    Args:
        dry_run: Если True, только проверяет подключение, не обрабатывает письма
        max_emails: Максимальное количество писем для обработки за один запуск
        include_read: Если True, обрабатывает все письма (включая прочитанные), 
                     иначе только непрочитанные
    
    Returns:
        Словарь с результатами синхронизации
    """
    result = {
        'success': False,
        'checked': 0,
        'processed': 0,
        'attachments_saved': 0,
        'errors': []
    }
    
    try:
        logger.info("=" * 60)
        logger.info("Начало синхронизации входящих писем")
        logger.info(f"Режим: {'DRY RUN (тестовый)' if dry_run else 'PRODUCTION'}")
        logger.info("=" * 60)
        
        # Проверяем конфигурацию
        if not config.email_server:
            raise ValueError("EMAIL_SERVER не настроен в .env")
        if not config.email_username:
            raise ValueError("EMAIL_USERNAME не настроен в .env")
        if not config.email_password:
            raise ValueError("EMAIL_PASSWORD не настроен в .env")
        
        # Инициализируем компоненты
        logger.info("Инициализация компонентов...")
        
        # Email клиент
        email_client = EmailClient.create_default()
        
        # Валидатор отправителей
        allowed_senders = []
        if config.email_allowed_senders:
            allowed_senders = [s.strip() for s in config.email_allowed_senders.split(',')]
        
        # Валидатор отправителей (берет настройки из .env)
        email_validator = EmailValidator.create_default()
        
        # Mayan клиент
        mayan_client = await MayanClient.create_with_user_credentials()
        
        # Обработчик писем
        email_processor = EmailProcessor(mayan_client)
        
        logger.info("Компоненты инициализированы успешно")
        
        if dry_run:
            # Тестовый режим - только проверка подключения
            logger.info("Тестовый режим: проверка подключений...")
            
            # Проверяем подключение к почтовому серверу
            if await email_client.test_connection():
                logger.info("✓ Подключение к почтовому серверу успешно")
            else:
                logger.error("✗ Не удалось подключиться к почтовому серверу")
                result['errors'].append("Ошибка подключения к почтовому серверу")
                return result
            
            # Проверяем подключение к Mayan EDMS
            if await mayan_client.test_connection():
                logger.info("✓ Подключение к Mayan EDMS успешно")
            else:
                logger.error("✗ Не удалось подключиться к Mayan EDMS")
                result['errors'].append("Ошибка подключения к Mayan EDMS")
                return result
            
            logger.info("Все подключения работают корректно")
            result['success'] = True
            return result
        
        # Получаем письма
        if include_read:
            logger.info(f"Получаем все письма (включая прочитанные, максимум {max_emails or 'все'})...")
            emails = await email_client.fetch_emails(max_count=max_emails, unread_only=False)
            logger.info(f"Найдено {len(emails)} писем (включая прочитанные)")
        else:
            logger.info("Получаем непрочитанные письма...")
            emails = await email_client.fetch_unread_emails(max_count=max_emails)
            logger.info(f"Найдено {len(emails)} непрочитанных писем")
        
        result['checked'] = len(emails)
        
        if not emails:
            logger.info("Писем не найдено")
            result['success'] = True
            return result
        
        # Показываем статистику по отправителям
        logger.info(f"Начинаем обработку {len(emails)} писем...")
        logger.info(f"Разрешенные отправители: {', '.join(email_validator.allowed_senders) if email_validator.allowed_senders else 'все'}")
        
        # Обрабатываем каждое письмо
        for email in emails:
            try:
                logger.info(f"Обрабатываем письмо: {email.message_id}")
                logger.info(f"  От: {email.from_address}")
                logger.info(f"  Тема: {email.subject}")
                
                # Проверяем отправителя
                # Извлекаем чистый email для логирования
                clean_email = email_validator.extract_email_address(email.from_address)
                logger.info(f"  Исходный адрес отправителя: '{email.from_address}'")
                logger.info(f"  Извлеченный email: '{clean_email}'")
                logger.info(f"  Разрешенные паттерны: {email_validator.allowed_senders}")
                
                is_allowed = email_validator.is_allowed(email.from_address)
                logger.info(f"  Результат проверки: {'РАЗРЕШЕН' if is_allowed else 'ЗАБЛОКИРОВАН'}")
                
                if not is_allowed:
                    logger.warning(
                        f"Письмо от неразрешенного отправителя: {email.from_address} "
                        f"(извлечен: {clean_email})"
                    )
                    # Помечаем как прочитанное, но не обрабатываем (только если это непрочитанное письмо)
                    if not include_read:
                        await email_client.mark_as_read(email.message_id)
                    continue
                
                logger.info(
                    f"✓ Отправитель разрешен: {email.from_address} "
                    f"(извлечен: {clean_email}), обрабатываем письмо..."
                )
                logger.info(f"  Вложений: {len(email.attachments)}")
                
                # Обрабатываем письмо (сохраняем вложения)
                process_result = await email_processor.process_email(email)
                
                if process_result['success']:
                    result['processed'] += 1
                    result['attachments_saved'] += len(process_result['processed_attachments'])
                    
                    logger.info(
                        f"✓ Письмо обработано успешно. "
                        f"Сохранено вложений: {len(process_result['processed_attachments'])}"
                    )
                    if process_result.get('registered_numbers'):
                        logger.info(f"  Присвоены номера: {', '.join(process_result['registered_numbers'])}")
                    
                    # Помечаем письмо как прочитанное (только если это непрочитанное письмо)
                    if not include_read:
                        await email_client.mark_as_read(email.message_id)
                else:
                    error_msg = f"Ошибка обработки письма: {', '.join(process_result['errors'])}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
                    
            except Exception as e:
                error_msg = f"Ошибка при обработке письма {email.message_id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result['errors'].append(error_msg)
        
        result['success'] = result['processed'] > 0 or result['checked'] == 0
        
        logger.info("=" * 60)
        logger.info("Синхронизация завершена")
        logger.info(f"Проверено писем: {result['checked']}")
        logger.info(f"Обработано писем: {result['processed']}")
        logger.info(f"Сохранено вложений: {result['attachments_saved']}")
        if result['errors']:
            logger.warning(f"Ошибок: {len(result['errors'])}")
        logger.info("=" * 60)
        
    except Exception as e:
        error_msg = f"Критическая ошибка синхронизации: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result['errors'].append(error_msg)
        result['success'] = False
    
    return result


def main():
    """Точка входа скрипта"""
    parser = argparse.ArgumentParser(description='Синхронизация входящих писем')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Тестовый режим: только проверка подключений'
    )
    parser.add_argument(
        '--max-emails',
        type=int,
        default=None,
        help='Максимальное количество писем для обработки'
    )
    parser.add_argument(
        '--include-read',
        action='store_true',
        help='Обрабатывать все письма, включая прочитанные'
    )
    
    args = parser.parse_args()
    
    try:
        result = asyncio.run(sync_emails(
            dry_run=args.dry_run, 
            max_emails=args.max_emails,
            include_read=args.include_read
        ))
        
        if result['success']:
            sys.exit(0)
        else:
            logger.error("Синхронизация завершилась с ошибками")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Синхронизация прервана пользователем")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()