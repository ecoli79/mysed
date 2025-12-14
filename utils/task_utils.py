from typing import Dict, List
from app_logging.logger import get_logger

logger = get_logger(__name__)

def create_task_detail_data(row_data: Dict) -> List[Dict]:
    """Создает данные для детальной таблицы задачи"""
    field_translations = {
        'name': 'Название процесса',
        'description': 'Описание',
        'start_time': 'Время начала',
        'due_date': 'Срок выполнения',
        'end_time': 'Время завершения',
        'duration_formatted': 'Длительность',
        'delete_reason': 'Причина удаления/Статус'
    }
    
    detail_data = []
    for key, value in row_data.items():
        # Пропускаем пустые значения
        if value and str(value).strip():
            field_name = field_translations.get(key, key.replace('_', ' ').title())
            detail_data.append({
                'field': field_name,
                'value': str(value)
            })
    
    return detail_data


