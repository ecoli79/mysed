import theme
from message import message
from nicegui import ui
from fastapi import APIRouter, Request
import json
import logging

# Создаем FastAPI роутер для API endpoints
api_router = APIRouter(prefix='/api')

logger = logging.getLogger(__name__)

# Глобальные переменные для КриптоПро
_certificates_cache = []
_selected_certificate = None

# Функции для работы с состоянием
def get_selected_certificate():
    """Возвращает выбранный сертификат"""
    return _selected_certificate

def set_selected_certificate(certificate):
    """Устанавливает выбранный сертификат"""
    global _selected_certificate
    _selected_certificate = certificate

def get_certificates_cache():
    """Возвращает кэш сертификатов"""
    return _certificates_cache

def set_certificates_cache(certificates):
    """Устанавливает кэш сертификатов"""
    global _certificates_cache
    _certificates_cache = certificates

# NiceGUI страницы (без роутера)
@ui.page('/c')
def page_example():
    with theme.frame('- Page C -'):
        message('Page C')
        ui.label('This page and its subpages are created using an APIRouter.')
        ui.link('Item 1', '/c/items/1').classes('text-xl text-grey-8')
        ui.link('Item 2', '/c/items/2').classes('text-xl text-grey-8')
        ui.link('Item 3', '/c/items/3').classes('text-xl text-grey-8')
        ui.link('Item 4', '/c/items/4').classes('text-xl text-grey-8')

@ui.page('/c/items/{item_id}', dark=True)
def item(item_id: str):
    with theme.frame(f'- Page C{item_id} -'):
        message(f'Item  #{item_id}')
        ui.link('go back', '/c').classes('text-xl text-grey-8')

# API endpoints для обработки событий КриптоПро
@api_router.post("/cryptopro-event")
async def handle_cryptopro_event(request: Request):
    """Обрабатывает события от КриптоПро плагина"""
    global _certificates_cache, _selected_certificate
    
    try:
        data = await request.json()
        event_name = data.get('event')
        event_data = data.get('data', {})
        
        logger.info(f"Получено событие КриптоПро: {event_name}")
        
        # Обрабатываем различные события
        if event_name == 'certificates_loaded':
            certificates = event_data.get('certificates', [])
            count = event_data.get('count', 0)
            logger.info(f"Загружено сертификатов: {count}")
            
            # Создаем словарь опций для NiceGUI select
            options = {}
            for i, cert in enumerate(certificates):
                # Используем индекс как ключ, а subject как отображаемое значение
                options[str(i)] = f"{cert['subject']} (действителен до: {cert['validTo']})"
            
            # Обновляем глобальную переменную с сертификатами
            _certificates_cache = certificates
            
            return {
                "status": "success", 
                "action": "update_select",
                "options": options,
                "certificates": certificates
            }
            
        elif event_name == 'certificate_selected':
            value = event_data.get('value', '')
            text = event_data.get('text', '')
            logger.info(f"Выбран сертификат: {value} -> {text}")
            
            # Обновляем глобальную переменную с выбранным сертификатом
            _selected_certificate = {
                'value': value,
                'text': text,
                'certificate': _certificates_cache[int(value)] if value.isdigit() and int(value) < len(_certificates_cache) else None
            }
            
            logger.info(f"DEBUG: Обновлен _selected_certificate = {_selected_certificate}")
            
            return {
                "status": "success",
                "action": "certificate_selected",
                "selected": _selected_certificate
            }
            
        elif event_name == 'certificates_error':
            error = event_data.get('error', 'Неизвестная ошибка')
            logger.error(f"Ошибка загрузки сертификатов: {error}")
            return {
                "status": "error", 
                "message": error,
                "action": "show_error"
            }
            
        elif event_name == 'no_certificates':
            message = event_data.get('message', 'Сертификаты не найдены')
            logger.warning(message)
            return {
                "status": "warning", 
                "message": message,
                "action": "show_warning"
            }
            
        elif event_name == 'plugin_not_available':
            message = event_data.get('message', 'Плагин недоступен')
            logger.warning(message)
            return {
                "status": "warning", 
                "message": message,
                "action": "show_warning"
            }
            
        elif event_name == 'integration_not_available':
            message = event_data.get('message', 'Интеграция недоступна')
            logger.warning(message)
            return {
                "status": "warning", 
                "message": message,
                "action": "show_warning"
            }
            
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Ошибка обработки события КриптоПро: {e}")
        return {"status": "error", "message": str(e)}

router = api_router