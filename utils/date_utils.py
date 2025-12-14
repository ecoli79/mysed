from datetime import datetime, timezone
from app_logging.logger import get_logger

logger = get_logger(__name__)

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

def format_date_russian(due_date) -> str:
    """Форматирует дату в российском формате DD.MM.YYYY HH:MM"""
    if isinstance(due_date, (int, float)):
        # Timestamp в миллисекундах
        due_obj = datetime.fromtimestamp(due_date / 1000, tz=timezone.utc)
        return due_obj.strftime('%d.%m.%Y %H:%M')
    
    if not due_date:
        return ''
    
    due_str = str(due_date).strip()
    
    try:
        # Нормализуем строку для fromisoformat
        # Заменяем Z на +00:00
        if due_str.endswith('Z'):
            due_str = due_str.replace('Z', '+00:00')
        # Исправляем offset без двоеточия: +0000 -> +00:00
        elif '+' in due_str[-5:] or (len(due_str) > 19 and due_str[-5] in '+-'):
            import re
            # Находим offset в конце строки без двоеточия
            offset_pattern = r'([+-])(\d{2})(\d{2})$'
            if re.search(offset_pattern, due_str):
                due_str = re.sub(offset_pattern, r'\1\2:\3', due_str)
        
        # Используем fromisoformat для парсинга
        due_obj = datetime.fromisoformat(due_str)
        return due_obj.strftime('%d.%m.%Y %H:%M')
        
    except (ValueError, AttributeError) as e:
        # Если fromisoformat не сработал, пробуем упрощенный парсинг
        try:
            # Удаляем миллисекунды и timezone, оставляем только базовую часть
            # Формат: 2025-11-07T23:59:59.000+0000 -> 2025-11-07T23:59:59
            base_part = due_str.split('.')[0]  # Убираем миллисекунды
            if '+' in base_part:
                base_part = base_part.split('+')[0]
            elif '-' in base_part[10:]:  # Проверяем offset (не дефис в дате)
                # Находим позицию начала offset
                t_pos = base_part.find('T')
                if t_pos > 0:
                    time_part = base_part[t_pos+1:]
                    if len(time_part) > 8:
                        base_part = base_part[:t_pos+9]  # Берем только YYYY-MM-DDTHH:MM:SS
            
            if 'T' in base_part:
                due_obj = datetime.strptime(base_part, '%Y-%m-%dT%H:%M:%S')
                return due_obj.strftime('%d.%m.%Y %H:%M')
            else:
                due_obj = datetime.strptime(base_part, '%Y-%m-%d')
                return due_obj.strftime('%d.%m.%Y')
        except ValueError:
            logger.warning(f"Не удалось распарсить дату: {due_date}, ошибка: {e}")
            return str(due_date)