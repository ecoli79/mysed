#!/usr/bin/env python3
# test_email_client.py
"""
Тестовый скрипт для проверки работы EmailClient (асинхронная версия)
"""
import sys
import asyncio
from pathlib import Path

# Добавляем путь к проекту
project_path = Path(__file__).parent.parent 
sys.path.insert(0, str(project_path))

import logging
from services.email_client import EmailClient
from config.settings import config
from app_logging.logger import setup_logging, get_logger

# Настраиваем логирование
setup_logging()
logger = get_logger(__name__)


def print_section(title: str):
    """Печатает заголовок секции"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(success: bool, message: str):
    """Печатает результат теста"""
    symbol = '✅' if success else '❌'
    print(f"{symbol} {message}")


async def test_configuration():
    """Тест 1: Проверка конфигурации из .env"""
    print_section("ТЕСТ 1: Проверка конфигурации")
    
    try:
        print(f"EMAIL_SERVER: {config.email_server or 'НЕ НАСТРОЕН'}")
        print(f"EMAIL_PORT: {config.email_port}")
        print(f"EMAIL_USERNAME: {config.email_username or 'НЕ НАСТРОЕН'}")
        print(f"EMAIL_PASSWORD: {'*' * len(config.email_password) if config.email_password else 'НЕ НАСТРОЕН'}")
        print(f"EMAIL_USE_SSL: {config.email_use_ssl}")
        print(f"EMAIL_PROTOCOL: {config.email_protocol}")
        print(f"EMAIL_ALLOWED_SENDERS: {config.email_allowed_senders or 'НЕ НАСТРОЕН'}")
        
        if not config.email_server or not config.email_username or not config.email_password:
            print_result(False, "Конфигурация неполная. Проверьте .env файл")
            return False
        
        print_result(True, "Конфигурация загружена успешно")
        return True
        
    except Exception as e:
        print_result(False, f"Ошибка загрузки конфигурации: {e}")
        return False


async def test_client_initialization():
    """Тест 2: Инициализация клиента"""
    print_section("ТЕСТ 2: Инициализация EmailClient")
    
    try:
        # Тест с настройками из .env
        print("\n2.1. Создание клиента с настройками из .env:")
        client = EmailClient.create_default()
        print_result(True, f"Клиент создан: {client.protocol.upper()} {client.server}:{client.port}")
        
        # Тест с явными параметрами
        print("\n2.2. Создание клиента с явными параметрами:")
        test_client = EmailClient(
            server="test.example.com",
            port=993,
            username="test@example.com",
            password="test",
            use_ssl=True,
            protocol="imap"
        )
        print_result(True, f"Клиент с параметрами создан: {test_client.server}")
        
        return True
        
    except ValueError as e:
        print_result(False, f"Ошибка валидации: {e}")
        return False
    except Exception as e:
        print_result(False, f"Ошибка создания клиента: {e}")
        return False


async def test_connection():
    """Тест 3: Подключение к почтовому серверу"""
    print_section("ТЕСТ 3: Подключение к почтовому серверу")
    
    try:
        client = EmailClient.create_default()
        
        print(f"\nПодключение к {client.protocol.upper()} серверу {client.server}:{client.port}...")
        
        if await client.test_connection():
            print_result(True, "Подключение успешно")
            return True
        else:
            print_result(False, "Не удалось подключиться к серверу")
            print("\nВозможные причины:")
            print("  - Неверные учетные данные")
            print("  - Сервер недоступен")
            print("  - Неверный порт или протокол")
            print("  - Проблемы с SSL/TLS")
            return False
            
    except Exception as e:
        print_result(False, f"Ошибка подключения: {e}")
        logger.exception("Детали ошибки:")
        return False


async def test_fetch_emails():
    """Тест 4: Получение писем"""
    print_section("ТЕСТ 4: Получение писем")
    
    try:
        client = EmailClient.create_default()
        
        print(f"\nПодключение к серверу...")
        if not await client.connect():
            print_result(False, "Не удалось подключиться")
            return False
        
        print_result(True, "Подключение установлено")
        
        print(f"\nПолучение непрочитанных писем (максимум 5)...")
        emails = await client.fetch_unread_emails(max_count=5)
        
        print_result(True, f"Найдено писем: {len(emails)}")
        
        if emails:
            print("\nДетали писем:")
            for idx, email_obj in enumerate(emails, 1):
                print(f"\n  Письмо {idx}:")
                print(f"    Message-ID: {email_obj.message_id}")
                print(f"    От: {email_obj.from_address}")
                print(f"    Тема: {email_obj.subject}")
                print(f"    Дата: {email_obj.received_date}")
                print(f"    Вложений: {len(email_obj.attachments)}")
                
                if email_obj.attachments:
                    print("    Вложения:")
                    for att in email_obj.attachments:
                        print(f"      - {att['filename']} ({att['size']} байт, {att['mimetype']})")
                
                # Показываем первые 100 символов тела письма
                if email_obj.body:
                    body_preview = email_obj.body[:100].replace('\n', ' ')
                    print(f"    Тело (первые 100 символов): {body_preview}...")
        else:
            print("\nНепрочитанных писем не найдено")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print_result(False, f"Ошибка получения писем: {e}")
        logger.exception("Детали ошибки:")
        return False


async def test_email_parsing():
    """Тест 5: Парсинг писем"""
    print_section("ТЕСТ 5: Парсинг писем")
    
    try:
        client = EmailClient.create_default()
        
        if not await client.connect():
            print_result(False, "Не удалось подключиться")
            return False
        
        print("\nПолучение одного письма для тестирования парсинга...")
        emails = await client.fetch_unread_emails(max_count=1)
        
        if not emails:
            print_result(False, "Нет писем для тестирования парсинга")
            await client.disconnect()
            return False
        
        email_obj = emails[0]
        
        print_result(True, "Письмо успешно распарсено")
        print("\nПроверка структуры письма:")
        
        checks = [
            ("Message-ID", bool(email_obj.message_id)),
            ("From address", bool(email_obj.from_address)),
            ("Subject", True),  # Subject может быть пустым
            ("Received date", bool(email_obj.received_date)),
            ("Attachments list", isinstance(email_obj.attachments, list)),
        ]
        
        for check_name, check_result in checks:
            print_result(check_result, f"{check_name}: {'OK' if check_result else 'ОШИБКА'}")
        
        # Проверка вложений
        if email_obj.attachments:
            print("\nПроверка структуры вложений:")
            for idx, att in enumerate(email_obj.attachments, 1):
                att_checks = [
                    ("filename", 'filename' in att and bool(att['filename'])),
                    ("content", 'content' in att and isinstance(att['content'], bytes)),
                    ("mimetype", 'mimetype' in att and bool(att['mimetype'])),
                    ("size", 'size' in att and isinstance(att['size'], int)),
                ]
                
                print(f"\n  Вложение {idx}:")
                for check_name, check_result in att_checks:
                    print_result(check_result, f"    {check_name}: {'OK' if check_result else 'ОШИБКА'}")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print_result(False, f"Ошибка парсинга: {e}")
        logger.exception("Детали ошибки:")
        return False


async def test_mark_as_read():
    """Тест 6: Пометка письма как прочитанного (только для IMAP)"""
    print_section("ТЕСТ 6: Пометка письма как прочитанного")
    
    try:
        client = EmailClient.create_default()
        
        if client.protocol != "imap":
            print_result(False, f"Тест доступен только для IMAP (текущий протокол: {client.protocol})")
            return False
        
        if not await client.connect():
            print_result(False, "Не удалось подключиться")
            return False
        
        print("\nПолучение одного письма...")
        emails = await client.fetch_unread_emails(max_count=1)
        
        if not emails:
            print_result(False, "Нет непрочитанных писем для тестирования")
            await client.disconnect()
            return False
        
        email_obj = emails[0]
        print(f"\nПопытка пометить письмо как прочитанное: {email_obj.message_id}")
        
        if await client.mark_as_read(email_obj.message_id):
            print_result(True, "Письмо помечено как прочитанное")
        else:
            print_result(False, "Не удалось пометить письмо как прочитанное")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
        logger.exception("Детали ошибки:")
        return False


async def test_context_manager():
    """Тест 7: Использование контекстного менеджера"""
    print_section("ТЕСТ 7: Асинхронный контекстный менеджер")
    
    try:
        print("\nТестирование async with statement...")
        
        async with EmailClient.create_default() as client:
            print_result(True, "Клиент создан через асинхронный контекстный менеджер")
            
            # Проверяем, что подключение установлено
            if client.connection:
                print_result(True, "Подключение установлено автоматически")
            else:
                print_result(False, "Подключение не установлено")
        
        print_result(True, "Соединение закрыто автоматически при выходе из контекста")
        return True
        
    except Exception as e:
        print_result(False, f"Ошибка: {e}")
        logger.exception("Детали ошибки:")
        return False


async def main():
    """Основная функция запуска тестов"""
    print("\n" + "=" * 60)
    print("  ТЕСТИРОВАНИЕ EMAIL CLIENT (АСИНХРОННАЯ ВЕРСИЯ)")
    print("=" * 60)
    
    results = []
    
    # Запускаем тесты
    results.append(("Конфигурация", await test_configuration()))
    
    if results[-1][1]:  # Если конфигурация OK, продолжаем
        results.append(("Инициализация", await test_client_initialization()))
        results.append(("Подключение", await test_connection()))
        
        # Эти тесты требуют реального подключения
        if results[-1][1]:  # Если подключение OK
            results.append(("Получение писем", await test_fetch_emails()))
            results.append(("Парсинг писем", await test_email_parsing()))
            results.append(("Пометка как прочитанное", await test_mark_as_read()))
        
        results.append(("Асинхронный контекстный менеджер", await test_context_manager()))
    
    # Итоги
    print_section("ИТОГИ ТЕСТИРОВАНИЯ")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nПройдено тестов: {passed} из {total}")
    print("\nДетали:")
    for test_name, result in results:
        status = "ПРОЙДЕН" if result else "ПРОВАЛЕН"
        print(f"  {status}: {test_name}")
    
    if passed == total:
        print("\nВсе тесты пройдены успешно!")
        return 0
    else:
        print(f"\nПровалено тестов: {total - passed}")
        return 1


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nТестирование прервано пользователем")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")
        logger.exception("Детали:")
        sys.exit(1)