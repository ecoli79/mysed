import theme
from datetime import datetime
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
_signature_result = None

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
    global _certificates_cache, _selected_certificate, _signature_result
    
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
            
            # ИСПРАВЛЕНИЕ: Используем правильный индекс для JavaScript
            cert_index = int(value) if value.isdigit() else 0
            
            # Обновляем глобальную переменную с выбранным сертификатом
            _selected_certificate = {
                'value': value,
                'text': text,
                'certificate': _certificates_cache[cert_index] if cert_index < len(_certificates_cache) else None,
                'js_index': cert_index  # JavaScript индекс (соответствует позиции в global_selectbox_container)
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
        
        elif event_name == 'signature_completed':
            signature = event_data.get('signature', '')
            certificate_info = event_data.get('certificateInfo', {})
            original_data = event_data.get('originalData', '')
            
            logger.info(f"ПОДПИСАНИЕ ЗАВЕРШЕНО УСПЕШНО!")
            logger.info(f"Размер подписи: {len(signature)} символов")
            
            # ДОБАВЛЯЕМ ЛОГИРОВАНИЕ
            logger.info(f"Certificate info получен из JavaScript: {certificate_info}")
            logger.info(f"Certificate info keys: {certificate_info.keys() if certificate_info else 'None'}")
            
            # Сохраняем результат подписания в глобальной переменной
            _signature_result = {
                'signature': signature,
                'certificate_info': certificate_info,
                'original_data': original_data,
                'timestamp': datetime.now().isoformat()
            }
            
            
            return {
                "status": "success",
                "action": "signature_completed",
                "message": "Документ успешно подписан"
            }
            
        elif event_name == 'signature_error':
            error = event_data.get('error', 'Неизвестная ошибка')
            logger.error(f"❌ ОШИБКА ПОДПИСАНИЯ: {error}")
            
            return {
                "status": "error",
                "action": "signature_error",
                "message": f"Ошибка подписания: {error}"
            }

        elif event_name == 'signature_verified':
            is_valid = event_data.get('isValid', False)
            certificate_info = event_data.get('certificateInfo', {})
            error = event_data.get('error', '')
            timestamp = event_data.get('timestamp', '')
            
            if is_valid:
                logger.info(f"ПОДПИСЬ ПРОВЕРЕНА И ВАЛИДНА!")
                logger.info(f"Сертификат: {certificate_info.get('subject', 'Неизвестно')}")
                
                return {
                    "status": "success",
                    "action": "signature_verified",
                    "message": "Подпись проверена и валидна",
                    "certificateInfo": certificate_info,
                    "timestamp": timestamp
                }
            else:
                logger.error(f"ПОДПИСЬ НЕВАЛИДНА: {error}")
                
                return {
                    "status": "error",
                    "action": "signature_verified",
                    "message": f"Подпись невалидна: {error}"
                }

        elif event_name == 'signed_document_created':
            signed_document = event_data.get('signedDocument', '')
            filename = event_data.get('filename', 'signed_document.pdf')
            timestamp = event_data.get('timestamp', '')
            
            logger.info(f"ПОДПИСАННЫЙ PDF СОЗДАН!")
            logger.info(f"Размер подписанного документа: {len(signed_document)} символов")
            
            _signature_result = {
                'signed_document': signed_document,
                'filename': filename,
                'timestamp': timestamp,
                'action': 'signed_document_created'
            }
            
            return {
                "status": "success",
                "action": "signed_document_created",
                "message": "Подписанный PDF создан успешно"
            }
            
        elif event_name == 'signed_document_error':
            error = event_data.get('error', 'Неизвестная ошибка')
            logger.error(f"ОШИБКА СОЗДАНИЯ ПОДПИСАННОГО PDF: {error}")
            
            return {
                "status": "error",
                "action": "signed_document_error",
                "message": f"Ошибка создания подписанного PDF: {error}"
            }
        
        elif event_name == 'check_signature_result':
            # Проверяем наличие результата подписания
            if _signature_result:
                return {
                    "status": "success",
                    "action": "check_signature_result",
                    "has_result": True,
                    "message": "Результат подписания найден"
                }
            else:
                return {
                    "status": "pending",
                    "action": "check_signature_result",
                    "has_result": False,
                    "message": "Результат подписания еще не готов"
                }
            
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Ошибка обработки события КриптоПро: {e}")
        return {"status": "error", "message": str(e)}

def get_signature_result():
    """Возвращает результат последнего подписания"""
    global _signature_result
    return _signature_result

def clear_signature_result():
    """Очищает результат подписания"""
    global _signature_result
    _signature_result = None


router = api_router