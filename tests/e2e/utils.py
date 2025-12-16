"""
Утилиты для E2E тестов
"""
import httpx
from typing import Optional


async def check_app_availability(url: str, timeout: float = 5.0) -> bool:
    """Проверяет доступность приложения"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            return response.status_code < 500
    except:
        return False


def get_app_url() -> str:
    """Получает URL приложения из переменных окружения"""
    import os
    return os.getenv('TEST_APP_URL', 'http://localhost:8080')

