"""
Компонент для отображения диаграммы Ганта задач
"""
from nicegui import ui
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def parse_task_deadline(due_date: Any) -> Optional[datetime]:
    """
    Парсит дедлайн задачи из различных форматов в datetime объект
    
    Args:
        due_date: Дедлайн в виде строки, datetime объекта или другого формата
        
    Returns:
        datetime объект или None, если не удалось распарсить
    """
    if due_date is None:
        return None
    
    # Если уже datetime объект
    if isinstance(due_date, datetime):
        return due_date
    
    try:
        due_str = str(due_date).strip()
        
        # ISO формат с T
        if 'T' in due_str:
            # ISO формат с Z
            if due_str.endswith('Z'):
                return datetime.fromisoformat(due_str.replace('Z', '+00:00'))
            else:
                # Убираем timezone если есть
                if '+' in due_str or (len(due_str) > 19 and due_str[-5] in '+-'):
                    # Убираем offset - берем только базовую часть
                    if '+' in due_str:
                        base_part = due_str.split('+')[0]
                    elif '-' in due_str[10:]:  # Проверяем offset (не дефис в дате)
                        # Находим позицию начала offset
                        t_pos = due_str.find('T')
                        if t_pos > 0:
                            time_part = due_str[t_pos+1:]
                            if len(time_part) > 8:
                                base_part = due_str[:t_pos+9]  # YYYY-MM-DDTHH:MM:SS
                            else:
                                base_part = due_str
                        else:
                            base_part = due_str
                    else:
                        base_part = due_str
                    
                    if 'T' in base_part:
                        return datetime.strptime(base_part[:19], '%Y-%m-%dT%H:%M:%S')
                    else:
                        return datetime.strptime(base_part[:10], '%Y-%m-%d')
                else:
                    return datetime.strptime(due_str[:19], '%Y-%m-%dT%H:%M:%S')
        else:
            # Простой формат даты YYYY-MM-DD
            try:
                return datetime.strptime(due_str[:10], '%Y-%m-%d')
            except ValueError:
                # Пробуем формат DD.MM.YYYY
                try:
                    return datetime.strptime(due_str[:10], '%d.%m.%Y')
                except ValueError:
                    # Пробуем формат DD.MM.YYYY HH:MM
                    try:
                        return datetime.strptime(due_str[:16], '%d.%m.%Y %H:%M')
                    except ValueError:
                        logger.warning(f"Не удалось распарсить дату: {due_date}")
                        return None
    except Exception as e:
        logger.warning(f"Ошибка при парсинге дедлайна {due_date}: {e}")
        return None


def prepare_tasks_for_gantt(tasks: List[Any], name_field: str = 'name', due_field: str = 'due', 
                            id_field: str = 'id', process_instance_id_field: str = 'process_instance_id',
                            description_field: str = 'description') -> List[Dict[str, Any]]:
    """
    Подготавливает список задач для отображения на диаграмме Ганта
    
    Args:
        tasks: Список задач (объекты с атрибутами или словари)
        name_field: Название поля/атрибута с именем задачи
        due_field: Название поля/атрибута с дедлайном
        id_field: Название поля/атрибута с ID задачи
        process_instance_id_field: Название поля/атрибута с ID процесса
        description_field: Название поля/атрибута с описанием задачи
        
    Returns:
        Список словарей с ключами 'name', 'description', 'deadline', 'task_id', 'process_instance_id'
    """
    parsed_tasks = []
    
    for task in tasks:
        # Получаем имя задачи
        if isinstance(task, dict):
            task_name = task.get(name_field, '')
            due_date = task.get(due_field)
            task_id = task.get(id_field, '')
            process_instance_id = task.get(process_instance_id_field, '')
            task_description = task.get(description_field, '')
        else:
            task_name = getattr(task, name_field, '')
            due_date = getattr(task, due_field, None)
            task_id = getattr(task, id_field, '')
            process_instance_id = getattr(task, process_instance_id_field, '')
            task_description = getattr(task, description_field, '')
        
        if not task_name:
            continue
        
        # Парсим дедлайн
        deadline = parse_task_deadline(due_date)
        
        if deadline:
            parsed_tasks.append({
                'name': task_name,
                'description': task_description,
                'deadline': deadline,
                'task_id': task_id,
                'process_instance_id': process_instance_id
            })
    
    return parsed_tasks


def create_gantt_chart(
    tasks: List[Any],
    title: str = 'Список по времени задач',
    name_field: str = 'name',
    due_field: str = 'due',
    id_field: str = 'id',
    process_instance_id_field: str = 'process_instance_id',
    description_field: str = 'description',
    now: Optional[datetime] = None,
    px_per_day: int = 30
) -> None:
    """
    Создает диаграмму Ганта для задач с дедлайнами
    
    Args:
        tasks: Список задач (объекты с атрибутами или словари)
        title: Заголовок диаграммы
        name_field: Название поля/атрибута с именем задачи
        due_field: Название поля/атрибута с дедлайном
        id_field: Название поля/атрибута с ID задачи
        process_instance_id_field: Название поля/атрибута с ID процесса
        description_field: Название поля/атрибута с описанием задачи
        now: Текущая дата для расчета (по умолчанию datetime.now())
        px_per_day: Пикселей на день для масштабирования
    """
    # Подготавливаем задачи
    parsed_tasks = prepare_tasks_for_gantt(tasks, name_field, due_field, id_field, process_instance_id_field, description_field)
    
    if not parsed_tasks:
        ui.label('Нет задач с указанными дедлайнами для отображения на диаграмме').classes('text-gray-500 text-center mt-4 mb-4')
        return
    
    # Используем переданную дату или текущую
    if now is None:
        now = datetime.now()
    
    # Вычисляем параметры для диаграммы
    future_days = max((t['deadline'] - now).days for t in parsed_tasks if t['deadline'] >= now) if any(t['deadline'] >= now for t in parsed_tasks) else 0
    past_days = max((now - t['deadline']).days for t in parsed_tasks if t['deadline'] < now) if any(t['deadline'] < now for t in parsed_tasks) else 0
    
    timeline_width = (future_days + past_days) * px_per_day + 120
    center_offset = future_days * px_per_day
    
    # Создаем диаграмму
    with ui.card().classes('p-4 mb-4 w-full max-w-full').style('width: 100%; max-width: 100%;'):
        ui.label(title).classes('text-xl font-bold mb-2')
        
        # Контейнер для задач - простая структура как в примере
        # Используем items-stretch вместо items-center, чтобы строки занимали всю ширину
        with ui.column().classes('gap-1 w-full items-stretch').style('width: 100%;'):
            for task_data in parsed_tasks:
                full_name = task_data['name']
                task_description = task_data.get('description', '')
                deadline = task_data['deadline']
                task_id = task_data.get('task_id', '')
                process_instance_id = task_data.get('process_instance_id', '')
                date_str = deadline.strftime('%d.%m.%Y')
                
                # Вычисляем количество дней до дедлайна
                delta_days = (deadline - now).days
                if delta_days > 0:
                    days_text = f'через {delta_days} дн.'
                elif delta_days < 0:
                    days_text = f'{abs(delta_days)} дн. назад'
                else:
                    days_text = 'сегодня'
                
                # Формируем tooltip с описанием, если оно есть
                tooltip_text = f'{full_name}\nДедлайн: {date_str}\n{days_text}'
                if task_description:
                    # Обрезаем описание, если оно слишком длинное
                    desc_display = task_description[:100] + '...' if len(task_description) > 100 else task_description
                    tooltip_text = f'{full_name}\nОписание: {desc_display}\nДедлайн: {date_str}\n{days_text}'
                safe_tooltip = tooltip_text.replace('"', '&quot;').replace('\n', '&#10;')
                
                # Контейнер для строки задачи - как в примере
                # Увеличиваем высоту контейнера, чтобы вместить увеличенный блок задачи
                # Ширина строки занимает всю ширину материнского блока
                with ui.element('div').style(f'position: relative; height: 70px; width: 100%; background: #fafafa; border: 1px solid #eee; overflow: hidden;'):
                    # Линия "СЕГОДНЯ" - строго по центру строки
                    ui.html(f'''
                        <div style="
                            position: absolute;
                            left: calc(50% - 1px);
                            top: 0;
                            width: 2px;
                            height: 100%;
                            background: red;
                            z-index: 15;
                        "></div>
                    ''')
                    
                    # Вычисляем количество дней до deadline (положительное = в будущем, отрицательное = в прошлом)
                    delta = (deadline - now).days
                    
                    # Смещение относительно красной линии "Сегодня" (в пикселях)
                    # Слева от красной линии (отрицательное смещение) - задачи с deadline в будущем (delta > 0)
                    # Справа от красной линии (положительное смещение) - задачи с deadline в прошлом (delta < 0)
                    # Чем больше дней до deadline, тем дальше от красной линии влево
                    offset_px = -delta * px_per_day
                    
                    # Позиция блока: для будущих задач позиционируем правый край блока,
                    # для просроченных - левый край, чтобы блок не заходил на красную линию
                    # Ширина блока 190px, поэтому нужно учесть половину ширины
                    block_half_width = 95  # половина ширины блока (190px / 2)
                    
                    # Определяем цвет блока в зависимости от количества дней до deadline
                    if delta < 0:
                        # Дедлайн прошел - красный
                        x_pos_offset = offset_px + block_half_width
                        bg, border, text_color = '#ffebee', '#c62828', '#c62828'
                    elif delta <= 2:
                        # Осталось 2 дня или меньше - оранжевый
                        x_pos_offset = offset_px - block_half_width
                        bg, border, text_color = '#ff9800', '#e65100', '#ffffff'
                    else:
                        # Осталось больше 2 дней - зеленый
                        x_pos_offset = offset_px - block_half_width
                        bg, border, text_color = '#e8f5e9', '#2e7d32', '#2e7d32'
                    
                    # Позиция блока = центр строки (50%) + смещение
                    x_pos_percent = 50
                    
                    # Обрезаем имя как в примере, но немного длиннее для трех строк
                    # Увеличиваем длину имени пропорционально увеличению блока
                    display_name = (full_name[:32] + '…') if len(full_name) > 32 else full_name
                    task_identifier = task_id if task_id else process_instance_id
                    
                    # Создаем кликабельный блок задачи - исправляем отображение текста
                    if task_identifier:
                        # Используем onclick для навигации - правильный способ для NiceGUI
                        click_handler = f"window.location.href='/task_completion?task_id={task_identifier}'"
                        ui.html(f'''
                            <div
                                title="{safe_tooltip}"
                                onclick="{click_handler}"
                                style="
                                    position: absolute;
                                    left: calc({x_pos_percent}% + {x_pos_offset}px);
                                    top: 50%;
                                    transform: translate(-50%, -50%);
                                    width: 190px;
                                    min-height: 65px;
                                    max-width: calc(100% - 10px);
                                    background: {bg};
                                    border: 2px solid {border};
                                    border-radius: 8px;
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: flex-start;
                                    align-items: center;
                                    text-align: center;
                                    padding: 6px 5px;
                                    box-sizing: border-box;
                                    cursor: pointer;
                                    z-index: 10;
                                "
                                onmouseover="this.style.opacity='0.9';"
                                onmouseout="this.style.opacity='1';"
                            >
                                <div style="font-weight: bold; font-size: 13px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; width: 100%; white-space: nowrap; margin-bottom: 4px; padding-top: 2px; color: {text_color};">{display_name}</div>
                                <div style="font-size: 11px; color: {text_color}; line-height: 1.3; margin-bottom: 3px; white-space: nowrap; opacity: 0.9;">{date_str}</div>
                                <div style="font-size: 11px; color: {text_color}; font-weight: 600; line-height: 1.3; white-space: nowrap; opacity: 0.9;">{days_text}</div>
                            </div>
                        ''')
                    else:
                        ui.html(f'''
                            <div
                                title="{safe_tooltip}"
                                style="
                                    position: absolute;
                                    left: calc({x_pos_percent}% + {x_pos_offset}px);
                                    top: 50%;
                                    transform: translate(-50%, -50%);
                                    width: 190px;
                                    min-height: 65px;
                                    max-width: calc(100% - 10px);
                                    background: {bg};
                                    border: 2px solid {border};
                                    border-radius: 8px;
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: flex-start;
                                    align-items: center;
                                    text-align: center;
                                    padding: 6px 5px;
                                    box-sizing: border-box;
                                    z-index: 10;
                                "
                            >
                                <div style="font-weight: bold; font-size: 13px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; width: 100%; white-space: nowrap; margin-bottom: 4px; padding-top: 2px; color: {text_color};">{display_name}</div>
                                <div style="font-size: 11px; color: {text_color}; line-height: 1.3; margin-bottom: 3px; white-space: nowrap; opacity: 0.9;">{date_str}</div>
                                <div style="font-size: 11px; color: {text_color}; font-weight: 600; line-height: 1.3; white-space: nowrap; opacity: 0.9;">{days_text}</div>
                            </div>
                        ''')
        
        # УБРАНО: блок с подписями "Будущее" и "Прошлое"

