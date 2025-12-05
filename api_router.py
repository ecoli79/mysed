import theme
from datetime import datetime
from message import message
from nicegui import ui
from fastapi import APIRouter, Request
import json
import logging
import re
from auth.middleware import get_current_user
from auth.ldap_auth import LDAPAuthenticator
from typing import Optional
from auth.session_manager import session_manager, UserSession
from auth.token_storage import token_storage, get_last_token

# Создаем FastAPI роутер для API endpoints
api_router = APIRouter(prefix='/api')

logger = logging.getLogger(__name__)

# Глобальные переменные для КриптоПро
_certificates_cache = []
_selected_certificate = None
_signature_result = None
_last_user_username = None  # Добавляем переменную для отслеживания смены пользователя

# Добавляем глобальную переменную для режима показа всех сертификатов
_show_all_certificates = False

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

def extract_cn_from_subject(subject: str) -> str:
    """
    Извлекает CN (Common Name) из subject сертификата
    
    Args:
        subject: Строка subject сертификата, например "CN=Имполитов Денис Владимирович, O=Организация, ..."
        
    Returns:
        CN значение или пустая строка
    """
    if not subject:
        return ''
    
    # Ищем CN= в строке
    cn_match = re.search(r'CN=([^,]+)', subject, re.IGNORECASE)
    if cn_match:
        return cn_match.group(1).strip()
    
    return ''

def normalize_fio(fio: str) -> str:
    """
    Нормализует ФИО для сравнения: убирает лишние пробелы, приводит к нижнему регистру
    
    Args:
        fio: ФИО в любом формате
        
    Returns:
        Нормализованная строка ФИО
    """
    if not fio:
        return ''
    
    # Убираем лишние пробелы и приводим к нижнему регистру
    normalized = ' '.join(fio.split()).lower()
    return normalized

def remove_middle_name(fio: str) -> str:
    """
    Убирает отчество из ФИО, оставляя только имя и фамилию
    
    Args:
        fio: Полное ФИО, например "Имполитов Денис Владимирович"
        
    Returns:
        ФИО без отчества, например "Имполитов Денис"
    """
    if not fio:
        return ''
    
    parts = fio.split()
    if len(parts) >= 2:
        # Берем первые два слова (фамилия и имя)
        return ' '.join(parts[:2])
    return fio

def get_user_from_request(request: Request) -> Optional[UserSession]:
    """
    Получает пользователя из FastAPI Request
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        UserSession или None
    """
    try:
        # Получаем IP адрес клиента из запроса
        client_ip = request.client.host if request.client else None
        
        if not client_ip:
            # Пробуем получить из заголовков
            forwarded_for = request.headers.get('X-Forwarded-For')
            if forwarded_for:
                client_ip = forwarded_for.split(',')[0].strip()
            else:
                client_ip = "unknown"
        
        logger.debug(f"Получен IP адрес клиента: {client_ip}")
        
        # Получаем токен из хранилища по IP
        token = token_storage.get_token(client_ip)
        
        # Если токен не найден по IP, пробуем последний токен
        if not token:
            token = get_last_token()
            logger.debug(f"Используем последний токен: {token[:8] if token else None}...")
        
        if token:
            user = session_manager.get_user_by_token(token)
            if user:
                logger.debug(f"Пользователь найден по токену: {user.username}")
                return user
            else:
                logger.warning(f"Пользователь не найден для токена: {token[:8] if token else None}...")
        else:
            logger.warning(f"Токен не найден для IP: {client_ip}")
            
    except Exception as e:
        logger.error(f"Ошибка получения пользователя из Request: {e}", exc_info=True)
    
    return None

def get_user_fio_for_certificate_matching(request: Request = None) -> str:
    """
    Получает ФИО текущего пользователя для сравнения с сертификатами
    
    Args:
        request: Опциональный FastAPI Request объект для получения пользователя
        
    Returns:
        Строка с именем и фамилией пользователя в формате "Фамилия Имя"
    """
    global _last_user_username
    
    try:
        # Пробуем получить пользователя из Request, если он передан
        user = None
        if request:
            user = get_user_from_request(request)
        
        # Если не получили из Request, пробуем через get_current_user (для NiceGUI контекста)
        if not user:
            try:
                user = get_current_user()
            except Exception as e:
                logger.debug(f"get_current_user() не доступен в этом контексте: {e}")
        
        if not user:
            logger.warning("Не удалось получить пользователя ни из Request, ни из ui.context")
            # Очищаем кэш при отсутствии пользователя
            _last_user_username = None
            return ''
        
        current_username = getattr(user, 'username', '').strip()
        
        # Если пользователь изменился, очищаем кэш сертификатов
        if _last_user_username and _last_user_username != current_username:
            logger.info(f"Обнаружена смена пользователя: {_last_user_username} -> {current_username}, очищаем кэш сертификатов")
            global _certificates_cache, _selected_certificate
            _certificates_cache = []
            _selected_certificate = None
        
        _last_user_username = current_username
        
        logger.info(f"Получен пользователь: username={current_username}, first_name={getattr(user, 'first_name', 'N/A')}, last_name={getattr(user, 'last_name', 'N/A')}")
        
        # Пробуем получить из сессии пользователя
        if hasattr(user, 'first_name') and hasattr(user, 'last_name'):
            first_name = getattr(user, 'first_name', '').strip()
            last_name = getattr(user, 'last_name', '').strip()
            
            if first_name and last_name:
                # Формат: "Фамилия Имя"
                fio = f"{last_name} {first_name}"
                logger.info(f"ФИО из сессии: {fio}")
                return fio
        
        # Если нет в сессии, пробуем получить из LDAP
        if current_username:
            try:
                ldap_auth = LDAPAuthenticator()
                ldap_user = ldap_auth.get_user_by_login(current_username)
                if ldap_user:
                    sn = getattr(ldap_user, 'sn', '').strip()
                    given_name = getattr(ldap_user, 'givenName', '').strip()
                    
                    if sn and given_name:
                        # Формат: "Фамилия Имя"
                        fio = f"{sn} {given_name}"
                        logger.info(f"ФИО из LDAP: {fio}")
                        return fio
                    else:
                        logger.warning(f"LDAP пользователь найден, но sn или givenName пустые: sn={sn}, givenName={given_name}")
                else:
                    logger.warning(f"LDAP пользователь не найден для username={current_username}")
            except Exception as ldap_error:
                logger.error(f"Ошибка при получении пользователя из LDAP: {ldap_error}", exc_info=True)
        
        logger.warning("Не удалось получить ФИО пользователя ни из сессии, ни из LDAP")
    except Exception as e:
        logger.error(f"Ошибка получения ФИО пользователя: {e}", exc_info=True)
    
    return ''

def extract_name_parts(fio: str) -> tuple:
    """
    Извлекает части ФИО (фамилию и имя) из строки
    
    Args:
        fio: ФИО в любом формате, например "Имполитов Денис Владимирович" или "Имполитов Денис"
        
    Returns:
        Кортеж (фамилия, имя) в нижнем регистре, или (None, None) если не удалось извлечь
    """
    if not fio:
        return (None, None)
    
    # Нормализуем: убираем лишние пробелы, кавычки, приводим к нижнему регистру
    normalized = ' '.join(fio.split()).lower()
    # Убираем кавычки
    normalized = normalized.strip('"\'')
    
    parts = normalized.split()
    
    if len(parts) >= 2:
        # Берем первые два слова как фамилию и имя
        return (parts[0], parts[1])
    elif len(parts) == 1:
        # Если только одно слово, считаем его фамилией
        return (parts[0], None)
    
    return (None, None)

def match_user_fio_with_certificate(user_fio: str, certificate_cn: str) -> bool:
    """
    Сравнивает ФИО пользователя с CN сертификата
    
    Сравнивает только фамилию и имя, игнорируя отчество и порядок слов.
    Например:
    - "Имполитов Денис" совпадет с "Имполитов Денис Владимирович"
    - "Денис Имполитов" совпадет с "Имполитов Денис Владимирович"
    
    Args:
        user_fio: ФИО пользователя (может быть "Фамилия Имя" или "Имя Фамилия")
        certificate_cn: CN из сертификата (может содержать отчество)
        
    Returns:
        True если фамилия и имя совпадают (без учета отчества и порядка)
    """
    if not user_fio or not certificate_cn:
        return False
    
    # Извлекаем части ФИО
    user_surname, user_name = extract_name_parts(user_fio)
    cert_surname, cert_name = extract_name_parts(certificate_cn)
    
    if not user_surname or not user_name:
        logger.debug(f"Не удалось извлечь фамилию и имя из user_fio: {user_fio}")
        return False
    
    if not cert_surname or not cert_name:
        logger.debug(f"Не удалось извлечь фамилию и имя из certificate_cn: {certificate_cn}")
        return False
    
    # Сравниваем: фамилия и имя должны совпадать (в любом порядке)
    # Вариант 1: user_fio = "Фамилия Имя", cert_cn = "Фамилия Имя ..."
    match1 = (user_surname == cert_surname) and (user_name == cert_name)
    
    # Вариант 2: user_fio = "Имя Фамилия", cert_cn = "Фамилия Имя ..." (обратный порядок)
    match2 = (user_surname == cert_name) and (user_name == cert_surname)
    
    result = match1 or match2
    
    if result:
        logger.info(f"Совпадение найдено: user_fio='{user_fio}' ({user_surname} {user_name}) <-> cert_cn='{certificate_cn}' ({cert_surname} {cert_name})")
    else:
        logger.debug(f"Совпадение не найдено: user_fio='{user_fio}' ({user_surname} {user_name}) <-> cert_cn='{certificate_cn}' ({cert_surname} {cert_name})")
    
    return result

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
    global _certificates_cache, _selected_certificate, _signature_result, _last_user_username
    
    try:
        data = await request.json()
        event_name = data.get('event')
        event_data = data.get('data', {})
        
        logger.info(f"Получено событие КриптоПро: {event_name}")
        
        # Обрабатываем различные события
        if event_name == 'certificates_loaded':
            certificates = event_data.get('certificates', [])
            count = event_data.get('count', 0)
            show_all = event_data.get('show_all', False)
            task_id = event_data.get('task_id')
            cert_select_id = event_data.get('cert_select_id')
            
            logger.info(f"Загружено сертификатов: {count}, show_all: {show_all}, task_id: {task_id}")
            
            # Получаем текущего пользователя из Request
            user = get_user_from_request(request)
            current_username = getattr(user, 'username', '').strip() if user else None
            
            logger.info(f"Пользователь из Request: username={current_username}, user={user is not None}")
            
            # Если пользователь изменился, очищаем кэш
            if _last_user_username and _last_user_username != current_username:
                logger.info(f"Обнаружена смена пользователя при загрузке сертификатов: {_last_user_username} -> {current_username}")
                _certificates_cache = []
                _selected_certificate = None
                _last_user_username = current_username
            
            # Получаем ФИО пользователя для фильтрации (передаем request)
            user_fio = get_user_fio_for_certificate_matching(request)
            logger.info(f"ФИО пользователя для фильтрации: '{user_fio}' (username: {current_username})")
            
            # Фильтруем сертификаты, если не включен режим показа всех
            filtered_certificates = []
            matched_certificates = []
            
            if show_all:
                # Показываем все сертификаты
                filtered_certificates = certificates
                logger.info("Режим показа всех сертификатов включен")
            else:
                # НЕ показываем все сертификаты автоматически, даже если ФИО пустое
                if not user_fio:
                    logger.warning(f"ФИО пользователя пустое (username: {current_username}), показываем пустой список")
                    filtered_certificates = []
                else:
                    # Фильтруем по ФИО пользователя
                    for cert in certificates:
                        subject = cert.get('subject', '')
                        cn = extract_cn_from_subject(subject)
                        
                        if cn:
                            if match_user_fio_with_certificate(user_fio, cn):
                                matched_certificates.append(cert)
                                logger.info(f"Найден соответствующий сертификат: {cn}")
                            else:
                                logger.debug(f"Сертификат не соответствует: CN={cn}, User FIO={user_fio}")
                        else:
                            logger.warning(f"Не удалось извлечь CN из subject: {subject}")
                    
                    filtered_certificates = matched_certificates
                    
                    if not filtered_certificates:
                        logger.warning(f"Не найдено сертификатов, соответствующих ФИО пользователя '{user_fio}' (username: {current_username}). Всего сертификатов: {count}")
            
            # Создаем словарь опций для NiceGUI select
            options = {}
            for i, cert in enumerate(filtered_certificates):
                # Используем индекс как ключ, а subject как отображаемое значение
                options[str(i)] = f"{cert['subject']} (действителен до: {cert['validTo']})"
            
            # Обновляем глобальную переменную с отфильтрованными сертификатами
            _certificates_cache = filtered_certificates
            
            # ОБНОВЛЯЕМ SELECT ЧЕРЕЗ PYTHON, если есть task_id
            if task_id:
                try:
                    # Импортируем глобальную переменную из task_completion_page
                    import sys
                    task_completion_module = sys.modules.get('pages.task_completion_page')
                    if task_completion_module and hasattr(task_completion_module, '_task_certificates_containers'):
                        containers = getattr(task_completion_module, '_task_certificates_containers', {}).get(task_id)
                        if containers:
                            certificate_select = containers.get('certificate_select')
                            certificates_container = containers.get('certificates_container')
                            
                            if certificate_select:
                                if options:
                                    # Обновляем опции select
                                    certificate_select.options = options
                                    certificate_select.update()
                                    logger.info(f"✅ Обновлен select для задачи {task_id} с {len(options)} опциями")
                                else:
                                    # Если опций нет, показываем сообщение
                                    logger.warning(f"Нет опций для обновления select для задачи {task_id}")
                            else:
                                logger.warning(f"certificate_select не найден для задачи {task_id}")
                        else:
                            logger.warning(f"Контейнеры не найдены для задачи {task_id}")
                except Exception as e:
                    logger.error(f"Ошибка обновления select через Python: {e}", exc_info=True)
            
            # Формируем ответ
            response = {
                "status": "success", 
                "action": "update_certificates_select",
                "options": options,
                "certificates": filtered_certificates,
                "total_count": count,
                "filtered_count": len(filtered_certificates),
                "show_all": show_all
            }
            
            # Добавляем task_id и cert_select_id из события, если они есть
            if task_id:
                response['task_id'] = task_id
            if cert_select_id:
                response['cert_select_id'] = cert_select_id
            
            # Если сертификаты не найдены и не включен режим показа всех, добавляем предупреждение
            if not show_all and not filtered_certificates and certificates:
                response["warning"] = "Сертификат пользователя не найден. Используйте параметр show_all=true для показа всех сертификатов."
                response["message"] = f"Не найдено сертификатов, соответствующих ФИО пользователя ({user_fio}). Всего доступно сертификатов: {count}."
            
            return response
            
        elif event_name == 'certificate_selected':
            value = event_data.get('value', '')
            text = event_data.get('text', '')
            certificate = event_data.get('certificate', {})
            task_id = event_data.get('task_id')
            logger.info(f"Выбран сертификат: {value} -> {text}")
            
            # ИСПРАВЛЕНИЕ: value - это индекс в массиве certificates (0, 1, 2...)
            array_index = int(value) if value.isdigit() else 0
            
            # Получаем сертификат из кэша по индексу массива
            selected_cert_from_cache = None
            if array_index < len(_certificates_cache):
                selected_cert_from_cache = _certificates_cache[array_index]
            elif certificate:
                # Если сертификат пришел напрямую, используем его
                selected_cert_from_cache = certificate
            
            # Используем сертификат из кэша или переданный напрямую
            final_certificate = selected_cert_from_cache or certificate or None
            
            if not final_certificate:
                logger.error(f"Не удалось найти сертификат по индексу {array_index}")
                return {
                    "status": "error",
                    "message": f"Сертификат не найден по индексу {array_index}"
                }
            
            # Реальный индекс КриптоПро берем из самого сертификата
            cryptopro_index = final_certificate.get('index', array_index + 1)
            
            # Обновляем глобальную переменную с выбранным сертификатом
            _selected_certificate = {
                'value': value,
                'text': text,
                'certificate': final_certificate,
                'js_index': cryptopro_index
            }
            
            logger.info(f"DEBUG: Обновлен _selected_certificate. Индекс массива: {array_index}, Индекс КриптоПро: {cryptopro_index}")
            logger.info(f"DEBUG: Сертификат: {final_certificate.get('subject', 'Неизвестно')}")
            logger.info(f"DEBUG: Действителен: {final_certificate.get('isValid', 'Неизвестно')}")
            
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
            
        elif event_name == 'crypto_status_update':
            # Обработка обновления статуса КриптоПро
            status_html = event_data.get('status_html', '')
            task_id = event_data.get('task_id')
            
            return {
                "status": "success",
                "action": "update_status",
                "status_html": status_html,
                "task_id": task_id
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