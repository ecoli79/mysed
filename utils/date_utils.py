from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def format_due_date(due_date) -> str:
    """Форматирует дату окончания задачи"""
    if isinstance(due_date, (int, float)):
        # Timestamp в миллисекундах
        due_obj = datetime.fromtimestamp(due_date / 1000, tz=timezone.utc)
        return due_obj.strftime('%Y-%m-%d %H:%M')
    elif 'T' in str(due_date):
        # ISO формат с временем
        due_str = str(due_date)
        if due_str.endswith('Z'):
            due_obj = datetime.fromisoformat(due_str.replace('Z', '+00:00'))
        else:
            # Формат без timezone
            due_obj = datetime.strptime(due_str, '%Y-%m-%dT%H:%M:%S')
        return due_obj.strftime('%Y-%m-%d %H:%M')
    elif '.' in str(due_date) and len(str(due_date).split('.')) == 3:
        # Уже отформатированная дата в формате DD.MM.YYYY HH:MM:SS
        # Просто возвращаем как есть
        return str(due_date)
    else:
        # Простой формат даты
        try:
            due_obj = datetime.strptime(str(due_date), '%Y-%m-%d')
            return due_obj.strftime('%Y-%m-%d')
        except ValueError:
            # Если не удалось распарсить, возвращаем как есть
            logger.warning(f"Не удалось распарсить дату: {due_date}")
            return str(due_date)