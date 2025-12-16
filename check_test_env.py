#!/usr/bin/env python3
"""Скрипт для проверки переменных окружения для E2E тестов"""
import os

print("=" * 60)
print("Проверка переменных окружения для E2E тестов")
print("=" * 60)

test_username = os.getenv('TEST_USERNAME')
test_password = os.getenv('TEST_PASSWORD')
test_app_url = os.getenv('TEST_APP_URL', 'http://localhost:8080')

print(f"\nTEST_APP_URL: {test_app_url}")
print(f"TEST_USERNAME: {test_username if test_username else '❌ НЕ УСТАНОВЛЕНО (будет использовано: test_user)'}")
if test_password:
    print(f"TEST_PASSWORD: {'*' * len(test_password)} (установлен)")
else:
    print(f"TEST_PASSWORD: ❌ НЕ УСТАНОВЛЕНО (будет использовано: test_password)")

if not test_username or not test_password:
    print("\n⚠️  ВНИМАНИЕ: Переменные окружения не установлены!")
    print("\nДля установки переменных окружения выполните:")
    print("  export TEST_USERNAME='ваш_логин'")
    print("  export TEST_PASSWORD='ваш_пароль'")
    print("  export TEST_APP_URL='http://localhost:8080'  # опционально")
    print("\nИли передайте их через командную строку:")
    print("  uv run pytest tests/e2e/ -v --TEST_USERNAME=ваш_логин --TEST_PASSWORD=ваш_пароль")
    print("\n⚠️  БЕЗ ПРАВИЛЬНЫХ УЧЕТНЫХ ДАННЫХ ТЕСТЫ АВТОРИЗАЦИИ НЕ ПРОЙДУТ!")
else:
    print("\n✅ Все переменные окружения установлены!")
    print("   Тесты должны работать корректно.")

print("=" * 60)

