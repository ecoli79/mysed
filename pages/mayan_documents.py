from nicegui import ui
from services.mayan_connector import MayanClient, MayanDocument, MayanTokenExpiredError
from services.access_types import AccessTypeManager, AccessType
from services.document_access_manager import document_access_manager
from auth.middleware import get_current_user
from config.settings import config
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Protocol
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from contextlib import contextmanager
import io
import mimetypes
import requests
import json
import tempfile
import os
import base64
from components.loading_indicator import LoadingIndicator, with_loading
import logging
import asyncio
from auth.ldap_auth import LDAPAuthenticator
from auth.session_manager import session_manager
from auth.token_storage import token_storage
from components.document_viewer import show_document_viewer
from services.signature_manager import SignatureManager
import traceback
import re

logger = logging.getLogger(__name__)

# Глобальные переменные для управления состоянием
_recent_documents_container: Optional[ui.column] = None
_search_results_container: Optional[ui.column] = None
_upload_form_container: Optional[ui.column] = None
_mayan_client: Optional[MayanClient] = None
_connection_status: bool = False
_auth_error: Optional[str] = None
_current_user: Optional[Any] = None

# После строки 39, добавить:
_mayan_client_cache: Optional[MayanClient] = None
_token_checked: bool = False
_token_check_lock = asyncio.Lock()  # Блокировка для предотвращения race conditions

# После строки 36 (после _upload_form_container), добавить:
_favorites_container: Optional[ui.column] = None

# Исключения
class UploadError(Exception):
    """Базовое исключение для ошибок загрузки"""
    pass

class ValidationError(UploadError):
    """Ошибка валидации данных"""
    pass

class FileProcessingError(UploadError):
    """Ошибка обработки файла"""
    pass

class DocumentCreationError(UploadError):
    """Ошибка создания документа"""
    pass

# Константы
class FileSize(Enum):
    """Размеры файлов в байтах"""
    MAX_SIZE = 50 * 1024 * 1024  # 50MB
    WARNING_SIZE = 10 * 1024 * 1024  # 10MB

# Типы данных
@dataclass(frozen=True)
class UploadParams:
    """Параметры загрузки документа"""
    label: str
    description: str
    document_type_name: Optional[str] = None
    cabinet_name: Optional[str] = None
    cabinet_id: Optional[int] = None  # Добавляем поле для прямого указания ID
    language_name: Optional[str] = None
    tag_names: Optional[List[str]] = None

@dataclass(frozen=True)
class FileInfo:
    """Информация о файле"""
    name: str
    content: bytes
    mimetype: str
    size: int

@dataclass(frozen=True)
class DocumentMetadata:
    """Метаданные документа"""
    document_type_id: int
    cabinet_id: Optional[int] = None
    language_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None

# Протоколы
class FormDataExtractor(Protocol):
    """Протокол для извлечения данных из формы"""
    async def extract_metadata(self, container: ui.column, params: UploadParams) -> DocumentMetadata: ...

# Классы
class FileValidator:
    """Валидатор файлов"""
    
    @staticmethod
    def validate_file(file_info: FileInfo) -> None:
        """Валидирует файл"""
        FileValidator._validate_size(file_info.size)
        FileValidator._validate_mimetype(file_info.mimetype, file_info.name)
    
    @staticmethod
    def _validate_size(size: int) -> None:
        """Проверяет размер файла"""
        if size > FileSize.MAX_SIZE.value:
            raise ValidationError(f"Файл слишком большой: {size} байт. Максимум: {FileSize.MAX_SIZE.value}")
        
        if size > FileSize.WARNING_SIZE.value:
            logger.warning(f"Большой файл: {size} байт")
    
    @staticmethod
    def _validate_mimetype(mimetype: str, filename: str) -> None:
        """Проверяет MIME-тип файла"""
        allowed_types = {
            'application/pdf',
            'text/plain',
            'text/csv',
            'application/json',
            'application/xml',
            'image/jpeg',
            'image/png',
            'image/gif',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        
        if mimetype not in allowed_types:
            logger.warning(f"Необычный MIME-тип: {mimetype} для файла {filename}")

class DocumentUploader:
    """Класс для загрузки документов"""
    
    def __init__(self, client: MayanClient, extractor: FormDataExtractor = None):
        self.client = client
        self.extractor = extractor
        self.container: Optional[ui.column] = None  # Добавить для хранения контейнера
    
    async def upload_document(
        self, 
        upload_event, 
        params: UploadParams, 
        container: ui.column
    ) -> None:
        """Загружает документ"""
        # Сохраняем контейнер для уведомлений
        self.container = container
        
        try:
            # Валидация входных данных
            self._validate_params(params)
            
            # Извлечение метаданных
            metadata = await self.extractor.extract_metadata(container, params)
            
            # Обработка файла
            file_info = self._process_file(upload_event)
            
            # Создание документа с файлом в одном запросе используя новый метод из MayanClient
            # Метод create_document_with_file автоматически добавляет документ в кабинет после создания
            result = await self.client.create_document_with_file(
                label=params.label,
                description=params.description,
                filename=file_info.name,
                file_content=file_info.content,
                mimetype=file_info.mimetype,
                document_type_id=metadata.document_type_id,
                cabinet_id=metadata.cabinet_id,
                language='rus' #metadata.language_id or "rus"
            )
            
            if not result:
                raise DocumentCreationError("Не удалось создать документ с файлом")
            
            document_id = result['document_id']
            
            # Уведомление об успехе
            self._notify_success(params.label, document_id)
            
            # Очистка формы
            upload_event.sender.clear()
            
            # Не обновляем список документов - это не нужно при загрузке нового документа
            # Пользователь может обновить список вручную, если нужно
            
        except ValidationError as e:
            self._notify_error(f"Ошибка валидации: {e}")
        except FileProcessingError as e:
            self._notify_error(f"Ошибка обработки файла: {e}")
        except DocumentCreationError as e:
            self._notify_error(f"Ошибка создания документа: {e}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке документа: {e}", exc_info=True)
            self._notify_error(f"Неожиданная ошибка: {e}")
    
    def _validate_params(self, params: UploadParams) -> None:
        """Валидирует параметры"""
        if not params.label.strip():
            raise ValidationError("Название документа не может быть пустым")
        
        if len(params.label) > 255:
            raise ValidationError("Название документа слишком длинное")
    
    def _process_file(self, upload_event) -> FileInfo:
        """Обрабатывает загруженный файл"""
        try:
            file_content = upload_event.content.read()
            filename = upload_event.name
            mimetype = upload_event.type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            
            file_info = FileInfo(
                name=filename,
                content=file_content,
                mimetype=mimetype,
                size=len(file_content)
            )
            
            FileValidator.validate_file(file_info)
            return file_info
            
        except Exception as e:
            raise FileProcessingError(f"Ошибка обработки файла: {e}")
    
    def _notify_success(self, label: str, document_id: int) -> None:
        """Уведомляет об успешной загрузке"""
        try:
            if self.container:
                with self.container:
                    success_label = ui.label(f'Документ "{label}" успешно загружен! (ID: {document_id})').classes('text-green-600 p-4 bg-green-50 rounded')
            else:
                logger.info(f'Документ "{label}" успешно загружен! (ID: {document_id})')
        except Exception as e:
            logger.info(f'Документ "{label}" успешно загружен! (ID: {document_id})')
            logger.warning(f'Не удалось отобразить уведомление об успехе: {e}')
        logger.info(f"Документ {label} успешно загружен с ID: {document_id}")
    
    def _notify_error(self, message: str) -> None:
        """Уведомляет об ошибке"""
        try:
            if self.container:
                with self.container:
                    error_label = ui.label(message).classes('text-red-500 p-4 bg-red-50 rounded')
            else:
                logger.error(message)
        except Exception as e:
            logger.error(message)
            logger.warning(f'Не удалось отобразить ошибку в UI: {e}')

class SimpleFormDataExtractor:
    """Упрощенный извлекатель данных из формы"""
    
    async def extract_metadata(self, container: ui.column, params: UploadParams) -> DocumentMetadata:
        """Извлекает метаданные из параметров напрямую"""
        # Получаем клиент для получения ID по названиям
        client = await get_mayan_client()
        
        # Получаем ID типа документа
        document_type_id = await self._get_document_type_id_by_name(client, params.document_type_name)
        
        # Получаем ID кабинета - используем переданный ID, если он есть, иначе ищем по имени
        cabinet_id = params.cabinet_id
        logger.info(f"SimpleFormDataExtractor: params.cabinet_id={params.cabinet_id}, params.cabinet_name={params.cabinet_name}")
        if not cabinet_id and params.cabinet_name:
            logger.info(f"SimpleFormDataExtractor: Ищем кабинет по имени '{params.cabinet_name}'")
            cabinet_id = await self._get_cabinet_id_by_name(client, params.cabinet_name)
            logger.info(f"SimpleFormDataExtractor: Найден cabinet_id={cabinet_id}")
        elif not cabinet_id:
            logger.warning(f"SimpleFormDataExtractor: cabinet_id не найден и cabinet_name не указан")
        
        logger.info(f"SimpleFormDataExtractor: Итоговый cabinet_id={cabinet_id} (тип: {type(cabinet_id)})")
        
        # Получаем ID языка
        # language_id = await self._get_language_id_by_name(client, params.language_name)
        
        # Получаем ID тегов
        tag_ids = await self._get_tag_ids_by_names(client, params.tag_names)
        
        return DocumentMetadata(
            document_type_id=document_type_id,
            cabinet_id=cabinet_id,
            language_id='rus', #language_id,
            tag_ids=tag_ids
        )
    
    async def _get_document_type_id_by_name(self, client: MayanClient, type_name: Optional[str]) -> int:
        """Получает ID типа документа по названию"""
        if not type_name:
            raise ValidationError("Тип документа не выбран")
        
        document_types = await client.get_document_types()
        for dt in document_types:
            if dt['label'] == type_name:
                return dt['id']
        
        raise ValidationError(f"Не удалось найти тип документа: {type_name}")
    
    async def _get_cabinet_id_by_name(self, client: MayanClient, cabinet_name: Optional[str]) -> Optional[int]:
        """Получает ID кабинета по названию"""
        if not cabinet_name:
            return None
        
        cabinets = await client.get_cabinets()
        for cabinet in cabinets:
            if cabinet['label'] == cabinet_name:
                return cabinet['id']
        
        logger.warning(f"Не удалось найти кабинет: {cabinet_name}")
        return None
    
    async def _get_tag_ids_by_names(self, client: MayanClient, tag_names: Optional[List[str]]) -> Optional[List[int]]:
        """Получает ID тегов по названиям"""
        if not tag_names:
            return None
        
        try:
            tags = await client.get_tags()
            tag_ids = []
            
            for tag_name in tag_names:
                for tag in tags:
                    if tag.get('label') == tag_name or tag.get('name') == tag_name:
                        tag_ids.append(tag['id'])
                        break
                else:
                    logger.warning(f"Не удалось найти тег: {tag_name}")
            
            return tag_ids if tag_ids else None
        except Exception as e:
            logger.warning(f"Ошибка при получении тегов: {e}")
            return None

async def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    global _mayan_client_cache, _token_checked, _token_check_lock
    
    try:
        # ВСЕГДА получаем текущего пользователя из контекста, чтобы использовать актуальный токен
        current_user = _current_user if _current_user else get_current_user()
        
        if not current_user:
            raise ValueError('Пользователь не авторизован')
        
        # Создаем клиент с API токеном пользователя напрямую
        if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
            raise MayanTokenExpiredError(f'У пользователя {current_user.username} нет API токена для доступа к Mayan EDMS')
        
        # Проверяем, есть ли кэшированный клиент с тем же токеном
        if _mayan_client_cache:
            # Получаем токен из заголовков клиента
            cached_token = None
            if 'Authorization' in _mayan_client_cache.client.headers:
                auth_header = _mayan_client_cache.client.headers['Authorization']
                if auth_header.startswith('Token '):
                    cached_token = auth_header[6:]
            
            # Если токен совпадает, возвращаем кэшированный клиент
            if cached_token == current_user.mayan_api_token and _token_checked:
                return _mayan_client_cache
        
        # Создаем новый клиент
        client = MayanClient(
            base_url=config.mayan_url,
            api_token=current_user.mayan_api_token
        )
        
        # Проверяем токен только один раз при первом создании клиента
        # Используем блокировку, чтобы избежать множественных проверок при параллельных вызовах
        async with _token_check_lock:
            # Двойная проверка после получения блокировки
            if _mayan_client_cache and _token_checked:
                cached_token = None
                if 'Authorization' in _mayan_client_cache.client.headers:
                    auth_header = _mayan_client_cache.client.headers['Authorization']
                    if auth_header.startswith('Token '):
                        cached_token = auth_header[6:]
                if cached_token == current_user.mayan_api_token:
                    return _mayan_client_cache
            
            # Проверяем действительность токена только если еще не проверяли
            if not _token_checked:
                is_valid = await client.check_token_validity()
                
                if not is_valid:
                    logger.warning('API токен Mayan EDMS истек, запрашиваем повторную авторизацию')
                    
                    # Показываем диалог повторной авторизации
                    new_token = await show_mayan_reauth_dialog()
                    
                    if new_token:
                        # Обновляем токен пользователя в сессии
                        current_user.mayan_api_token = new_token
                        # Обновляем сессию в session_manager
                        try:
                            from auth.token_storage import token_storage
                            client_ip = ui.context.client.request.client.host
                            token = token_storage.get_token(client_ip)
                            if token:
                                session = session_manager.get_user_by_token(token)
                                if session:
                                    session.mayan_api_token = new_token
                        except Exception as e:
                            logger.warning(f'Не удалось обновить токен в сессии: {e}')
                        
                        # Создаем новый клиент с обновленным токеном
                        client = MayanClient(
                            base_url=config.mayan_url,
                            api_token=new_token
                        )
                        logger.info('Клиент Mayan EDMS обновлен с новым токеном')
                    else:
                        raise ValueError('Повторная авторизация не удалась или была отменена')
                
                _token_checked = True
        
        # Кэшируем клиент
        _mayan_client_cache = client
        return client
        
    except MayanTokenExpiredError:
        # Сбрасываем кэш при ошибке токена
        _mayan_client_cache = None
        _token_checked = False
        
        logger.warning('Обнаружен истекший токен, запрашиваем повторную авторизацию')
        
        # Показываем диалог повторной авторизации
        new_token = await show_mayan_reauth_dialog()
        
        if new_token:
            # Получаем текущего пользователя для обновления токена
            current_user = get_current_user()
            
            if current_user:
                current_user.mayan_api_token = new_token
                # Обновляем сессию в session_manager
                try:
                    from auth.token_storage import token_storage
                    client_ip = ui.context.client.request.client.host
                    token = token_storage.get_token(client_ip)
                    if token:
                        session = session_manager.get_user_by_token(token)
                        if session:
                            session.mayan_api_token = new_token
                except Exception as e:
                    logger.warning(f'Не удалось обновить токен в сессии: {e}')
            
            # Создаем новый клиент с обновленным токеном
            client = MayanClient(
                base_url=config.mayan_url,
                api_token=new_token
            )
            _mayan_client_cache = client
            _token_checked = True
            logger.info('Клиент Mayan EDMS обновлен с новым токеном')
            return client
        else:
            raise ValueError('Повторная авторизация не удалась или была отменена')
    except Exception as e:
        logger.error(f'Ошибка при создании клиента Mayan EDMS: {e}', exc_info=True)
        # Сбрасываем кэш при ошибке
        _mayan_client_cache = None
        _token_checked = False
        raise

# Добавить функцию для сброса кэша (на случай смены пользователя)
def reset_mayan_client_cache():
    """Сбрасывает кэш клиента Mayan EDMS"""
    global _mayan_client_cache, _token_checked
    _mayan_client_cache = None
    _token_checked = False
    logger.info('Кэш клиента Mayan EDMS сброшен')

async def check_connection() -> bool:
    """Проверяет подключение к Mayan EDMS"""
    global _connection_status, _auth_error
    
    try:
        client = await get_mayan_client()
        _connection_status = await client.test_connection()
        _auth_error = None
        return _connection_status
    except Exception as e:
        logger.error(f"Ошибка при проверке подключения: {e}")
        _connection_status = False
        _auth_error = str(e)
        return False

def format_file_size(size_bytes: Optional[int]) -> str:
    """Форматирует размер файла в читаемый вид"""
    if size_bytes is None or size_bytes == 0:
        return "размер неизвестен"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def format_datetime(dt_str: str) -> str:
    """Форматирует дату и время"""
    if not dt_str:
        return "Не указано"
    
    try:
        # Парсим ISO формат даты
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return dt_str

async def update_file_size(document: MayanDocument, size_label: ui.label):
    """Асинхронно обновляет количество страниц в карточке документа"""
    try:
        client = await get_mayan_client()
        
        # Получаем количество страниц документа
        page_count = await client.get_document_page_count(document.document_id)
        
        if page_count and page_count > 0:
            if page_count == 1:
                size_label.text = "(1 страница)"
            elif page_count in [2, 3, 4]:
                size_label.text = f"({page_count} страницы)"
            else:
                size_label.text = f"({page_count} страниц)"
        else:
            size_label.text = "(количество страниц неизвестно)"
            
    except Exception as e:
        logger.error(f"Ошибка при получении количества страниц для документа {document.document_id}: {e}")
        size_label.text = "(ошибка получения страниц)"

def create_document_card(document: MayanDocument, update_cabinet_title_func=None, current_count=None, documents_count_label=None, is_favorites_page: bool = False, favorites_count_label: Optional[ui.label] = None) -> ui.card:
    """Создает карточку документа с возможностью предоставления доступа"""
    
    # Временное логирование для отладки
    logger.info(f"Создаем карточку для документа {document.document_id}:")
    logger.info(f"- Название: {document.label}")
    logger.info(f"- Файл: {document.file_latest_filename}")
    logger.info(f"- Размер файла: {document.file_latest_size}")
    logger.info(f"- MIME-тип: {document.file_latest_mimetype}")
    
    with ui.card().classes('w-full mb-4') as card:
        # Сохраняем функцию обновления, текущий счетчик и label счетчика в карточке
        card.update_cabinet_title_func = update_cabinet_title_func
        card.current_count = current_count
        card.documents_count_label = documents_count_label
        
        with ui.row().classes('w-full items-start gap-4'):
            # Превью документа (слева)
            preview_container = ui.column().classes('flex-shrink-0')
            with preview_container:
                # Контейнер для превью (будет обновляться)
                preview_html = ui.html('<div class="w-32 h-32 flex items-center justify-center text-xs text-gray-400 bg-gray-100 rounded border">Загрузка превью...</div>').classes('w-32 h-32')
                
                # Переменная для хранения data_uri для полноразмерного просмотра
                preview_data_uri = {'value': None}
                
                # Функция для открытия полноразмерного изображения с каруселью
                async def show_full_preview():
                    """Открывает полноразмерное изображение превью с каруселью всех страниц"""
                    try:
                        client = await get_mayan_client()
                        await show_document_viewer(document.document_id, document.label, mayan_client=client)
                    except Exception as e:
                        logger.error(f'Ошибка при открытии полноразмерного превью: {e}', exc_info=True)
                        try:
                            ui.notify(f'Ошибка при открытии превью: {str(e)}', type='error')
                        except RuntimeError:
                            # Если нет контекста UI, просто логируем ошибку
                            logger.error(f'Ошибка при открытии превью (без контекста UI): {str(e)}')
                
                # Асинхронно загружаем превью
                async def load_preview():
                    """Загружает превью документа"""
                    try:
                        logger.info(f'Начинаем загрузку превью для документа {document.document_id}')
                        client = await get_mayan_client()
                        
                        # Получаем URL превью
                        preview_url = await client.get_document_preview_url(document.document_id)
                        
                        if preview_url:
                            logger.info(f'URL превью для документа {document.document_id}: {preview_url}')
                            
                            # Загружаем изображение через клиент с аутентификацией
                            try:
                                image_data = await client.get_document_preview_image(document.document_id)
                            except MayanTokenExpiredError:
                                # Токен истек во время запроса, обновляем клиент и повторяем
                                logger.warning(f'Токен истек при загрузке превью для документа {document.document_id}, обновляем...')
                                global _mayan_client_cache, _token_checked
                                _mayan_client_cache = None
                                _token_checked = False
                                client = await get_mayan_client()
                                image_data = await client.get_document_preview_image(document.document_id)
                            
                            if image_data:
                                logger.info(f'Получено {len(image_data)} байт изображения для документа {document.document_id}')
                                
                                # Конвертируем в base64 для отображения
                                img_base64 = base64.b64encode(image_data).decode()
                                
                                # Определяем MIME-тип изображения
                                mimetype = 'image/jpeg'
                                if image_data[:4] == b'\x89PNG':
                                    mimetype = 'image/png'
                                elif image_data[:6] in [b'GIF87a', b'GIF89a']:
                                    mimetype = 'image/gif'
                                
                                # Устанавливаем превью через data URI в HTML
                                data_uri = f'data:{mimetype};base64,{img_base64}'
                                
                                # Сохраняем data_uri для полноразмерного просмотра
                                preview_data_uri['value'] = data_uri
                                
                                # Создаем кликабельное превью с курсором pointer
                                html_content = f'''
                                    <div id="preview_clickable_{document.document_id}" 
                                         style="cursor: pointer; transition: opacity 0.2s;" 
                                         onmouseover="this.style.opacity='0.8'" 
                                         onmouseout="this.style.opacity='1'"
                                         title="Нажмите для просмотра всех страниц документа">
                                        <img src="{data_uri}" 
                                             class="w-32 h-32 object-contain bg-gray-100 rounded border" 
                                             alt="Превью документа {document.document_id}" 
                                             style="display: block; pointer-events: none;" />
                                    </div>
                                '''
                                
                                preview_html.content = html_content
                                preview_html.update()
                                
                                # Добавляем обработчик клика через NiceGUI
                                # NiceGUI поддерживает async функции напрямую в обработчиках
                                # Регистрируем обработчик клика через NiceGUI
                                # Используем ui.timer для регистрации обработчика после обновления DOM
                                ui.timer(0.1, lambda: preview_html.on('click', show_full_preview), once=True)
                            else:
                                logger.warning(f'Не удалось загрузить изображение для документа {document.document_id}')
                                preview_html.content = '<div class="w-32 h-32 flex items-center justify-center text-xs text-gray-400 bg-gray-100 rounded border">Превью недоступно</div>'
                                preview_html.update()
                        else:
                            logger.warning(f'Превью недоступно для документа {document.document_id}')
                            preview_html.content = '<div class="w-32 h-32 flex items-center justify-center text-xs text-gray-400 bg-gray-100 rounded border">Превью недоступно</div>'
                            preview_html.update()
                    except MayanTokenExpiredError:
                        logger.warning(f'Токен истек при загрузке превью для документа {document.document_id}')
                        preview_html.content = '<div class="w-32 h-32 flex items-center justify-center text-xs text-red-400 bg-gray-100 rounded border">Требуется авторизация</div>'
                        preview_html.update()
                    except Exception as e:
                        logger.error(f'Ошибка загрузки превью для документа {document.document_id}: {e}', exc_info=True)
                        preview_html.content = '<div class="w-32 h-32 flex items-center justify-center text-xs text-red-400 bg-gray-100 rounded border">Ошибка загрузки</div>'
                        preview_html.update()
                
                # Запускаем загрузку превью
                if document.file_latest_id:
                    ui.timer(0.1, load_preview, once=True)
            
            # Основная информация (в центре)
            with ui.column().classes('flex-1'):
                ui.label(document.label).classes('text-lg font-semibold')
                
                if document.description:
                    ui.label(document.description).classes('text-sm text-gray-600 mb-2')
                
                # Информация о файле
                if document.file_latest_filename:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('description').classes('text-blue-500')
                        ui.label(document.file_latest_filename).classes('text-sm')
                        
                        # Создаем элемент для отображения количества страниц
                        pages_label = ui.label("").classes('text-xs text-gray-500')
                        
                        # Асинхронно получаем количество страниц
                        if document.file_latest_id:
                            ui.timer(0.1, lambda: update_file_size(document, pages_label), once=True)
                
                # Даты
                with ui.row().classes('text-xs text-gray-500 gap-4'):
                    ui.label(f"Создан: {format_datetime(document.datetime_created)}")
                    ui.label(f"Изменен: {format_datetime(document.datetime_modified)}")
            
            # Кнопки действий (справа)
            buttons_container = ui.column().classes('items-end gap-2 min-w-fit flex-shrink-0')
            with buttons_container:
                if document.file_latest_id:
                    # Кнопка скачивания
                    ui.button('Скачать', icon='download').classes('text-xs px-2 py-1 h-7').on_click(
                        lambda doc=document: download_document_file(doc)
                    )
                
                # Кнопка предоставления доступа
                current_user = get_current_user()
                if current_user:
                    ui.button('Предоставить доступ', icon='share', color='blue').classes('text-xs px-2 py-1 h-7').on_click(
                        lambda doc=document: show_grant_access_dialog(doc)
                    )
                    
                    # Кнопка избранного
                    if is_favorites_page:
                        # На странице избранных сразу показываем, что документ в избранном
                        favorite_button = ui.button('Удалить из избранного', icon='star', color='amber').classes('text-xs px-2 py-1 h-7')
                        
                        # Обработчик клика для страницы избранных
                        favorite_button.on_click(lambda doc=document, btn=favorite_button, card_ref=card, count_label_ref=favorites_count_label: toggle_favorite(doc, btn, card_ref, count_label_ref))
                    else:
                        # На других страницах проверяем статус асинхронно и показываем кнопку только если документ не в избранном
                        async def check_and_show_favorite_button():
                            """Проверяет статус и показывает кнопку только если документ не в избранном"""
                            try:
                                is_favorite = await check_favorite_status(document)
                                if not is_favorite:
                                    # Документ не в избранном - показываем кнопку
                                    favorite_button = ui.button('В избранное', icon='star_border', color='amber').classes('text-xs px-2 py-1 h-7')
                                    favorite_button.on_click(lambda doc=document, btn=favorite_button: toggle_favorite(doc, btn))
                            except Exception as e:
                                logger.warning(f'Ошибка при проверке статуса избранного: {e}')
                                # В случае ошибки не показываем кнопку
                        
                        # Запускаем проверку статуса
                        ui.timer(0.1, check_and_show_favorite_button, once=True)
                                        
                    # Кнопка удаления (только для admins и secretar)
                    user_groups_normalized = [group.strip().lower() for group in current_user.groups]
                    is_admin_or_secretar = 'admins' in user_groups_normalized or 'secretar' in user_groups_normalized
                    
                    if is_admin_or_secretar:
                        ui.button('Удалить', icon='delete', color='red').classes('text-xs px-2 py-1 h-7').on_click(
                            lambda doc=document, card_ref=card: delete_document(doc, card_ref)
                        )
        
        # Асинхронно проверяем наличие подписей и добавляем кнопку, если они есть
        async def check_and_add_signature_button():
            """Проверяет наличие подписей и добавляет кнопку"""
            try:
                signature_manager = SignatureManager()
                has_signatures = await signature_manager.document_has_signatures(document.document_id)
                logger.info(f"  - Есть подписи для документа {document.document_id}: {has_signatures}")
                
                if has_signatures:
                    with buttons_container:
                        async def download_handler(doc=document):
                            await download_signed_document(doc)
                        ui.button('Скачать с подписями', icon='verified', color='green').classes('text-xs px-2 py-1 h-7').on_click(
                            lambda doc=document: download_handler(doc)
                        )
            except Exception as e:
                logger.warning(f"Ошибка проверки подписей для документа {document.document_id}: {e}")
        
        # Запускаем проверку подписей асинхронно
        if document.file_latest_id:
            ui.timer(0.1, check_and_add_signature_button, once=True)
    
    return card


async def show_grant_access_dialog(document: MayanDocument):
    """
    Показывает диалог для предоставления доступа к документу
    """
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-md'):
        ui.label(f'Предоставить доступ к документу: {document.label}').classes('text-lg font-semibold mb-4')
        
        # Форма предоставления доступа
        with ui.column().classes('w-full gap-4'):
            
            # Получаем список ролей для выпадающего списка
            try:
                roles = await document_access_manager.get_available_roles()
                
                if roles:
                    # Создаем список названий ролей
                    role_options = [role['label'] for role in roles if role.get('label')]
                    logger.info(f"Доступные роли для выбора: {role_options}")
                    
                    if role_options:
                        # Выпадающий список ролей
                        role_select = ui.select(
                            options=role_options,
                            label='Выберите роль',
                            value=role_options[0]
                        ).classes('w-full')
                    else:
                        ui.label('Роли найдены, но без названий').classes('text-orange-500')
                        role_select = None
                else:
                    ui.label('Роли не найдены в системе')
                    ui.label('Возможные причины:').classes('text-sm text-gray-600')
                    ui.label('• API токен не имеет прав на просмотр ролей').classes('text-sm text-gray-600')
                    ui.label('• Роли не созданы в системе').classes('text-sm text-gray-600')
                    ui.label('• Неправильная конфигурация Mayan EDMS').classes('text-sm text-gray-600')
                    role_select = None
                    
            except Exception as e:
                logger.error(f"Ошибка при получении ролей: {e}")
                ui.label(f'Ошибка при загрузке ролей: {str(e)}').classes('text-red-500')
                role_select = None
            
            #Получаем типы доступа вместо отдельных разрешений
            try:
                access_types = AccessTypeManager.get_all_access_types()
                
                if access_types:
                    # Создаем список названий типов доступа
                    access_type_options = [access_type['label'] for access_type in access_types]
                    logger.info(f"Доступные типы доступа: {access_type_options}")
                    
                    if access_type_options:
                        # Одиночный выбор типа доступа
                        access_type_select = ui.select(
                            options=access_type_options,
                            label='Выберите тип доступа',
                            value=None  # Начинаем без выбора
                        ).classes('w-full')
                        
                        # Добавляем подсказку
                        ui.label('💡 Выберите тип доступа - система автоматически применит необходимые разрешения').classes('text-xs text-blue-600')
                    else:
                        ui.label('Типы доступа не найдены').classes('text-orange-500')
                        access_type_select = None
                else:
                    ui.label('Типы доступа не найдены').classes('text-orange-500')
                    access_type_select = None
                    
            except Exception as e:
                logger.error(f"Ошибка при получении типов доступа: {e}")
                ui.label(f'Ошибка при загрузке типов доступа: {str(e)}').classes('text-red-500')
                access_type_select = None

            async def handle_grant_access():
                try:
                    logger.info("=== НАЧАЛО ПРЕДОСТАВЛЕНИЯ ДОСТУПА ===")
                    
                    if not role_select or not role_select.value:
                        logger.warning("Роль не выбрана")
                        ui.notify('Выберите роль', type='error')
                        return
                        
                    if not access_type_select or not access_type_select.value:
                        logger.warning("Тип доступа не выбран")
                        ui.notify('Выберите тип доступа', type='error')
                        return
                        
                    role_name = role_select.value
                    access_type_label = access_type_select.value
                    
                    logger.info(f"Выбрана роль: {role_name}")
                    logger.info(f"Выбран тип доступа: {access_type_label}")
                        
                    # Находим выбранный тип доступа
                    selected_access_type = None
                    for access_type in AccessTypeManager.get_all_access_types():
                        if access_type['label'] == access_type_label:
                            selected_access_type = AccessType(access_type['value'])
                            break
                            
                    if not selected_access_type:
                        logger.error(f"Не удалось найти тип доступа для: {access_type_label}")
                        ui.notify('Ошибка: не удалось определить тип доступа', type='error')
                        return
                        
                    logger.info(f"Найден тип доступа: {selected_access_type}")
                        
                    # Получаем разрешения для выбранного типа доступа
                    permission_names = AccessTypeManager.get_access_type_permissions(selected_access_type)
                    logger.info(f"Разрешения для типа доступа: {permission_names}")
                    
                    # Получаем все доступные разрешения из Mayan EDMS
                    permissions = await document_access_manager.get_available_permissions_for_documents()
                    logger.info(f"Получено разрешений из Mayan EDMS: {len(permissions)}")
                    
                    # Находим pk разрешений по их названиям
                    permission_pks = []
                    for perm_name in permission_names:
                        logger.info(f"Ищем разрешение: {perm_name}")
                        found = False
                        for perm in permissions:
                            if perm['label'] == perm_name:
                                permission_pks.append(perm['pk'])
                                logger.info(f"Найдено разрешение {perm_name} с pk: {perm['pk']}")
                                found = True
                                break
                        if not found:
                            logger.warning(f"Разрешение {perm_name} не найдено в Mayan EDMS")
                    
                    logger.info(f"Найдено pk разрешений: {permission_pks}")
                    
                    if len(permission_pks) != len(permission_names):
                        logger.error(f"Не все разрешения найдены. Ожидалось: {len(permission_names)}, найдено: {len(permission_pks)}")
                        ui.notify('Не удалось найти ID для некоторых разрешений', type='error')
                        return
                        
                    logger.info(f"Предоставляем доступ к документу {document.document_id} роли {role_name}")
                    
                    # Предоставляем доступ роли
                    success = await document_access_manager.grant_document_access_to_role_by_pks(
                        document_id=document.document_id,
                        document_label=document.label,
                        role_name=role_name,
                        permission_pks=permission_pks
                    )
                    
                    logger.info(f"Результат предоставления доступа: {success}")
                    
                    if success:
                        permissions_text = ', '.join(permission_names)
                        logger.info(f"Доступ успешно предоставлен: {permissions_text}")
                        ui.notify(f'Доступ к документу "{document.label}" предоставлен роли {role_name} с типом доступа: {access_type_label} ({permissions_text})', type='positive')
                        dialog.close()
                    else:
                        logger.error("Ошибка при предоставлении доступа роли")
                        ui.notify('Ошибка при предоставлении доступа роли', type='error')
                            
                except Exception as e:
                    logger.error(f"Ошибка при предоставлении доступа: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    ui.notify(f'Ошибка: {str(e)}', type='error')
            
            # # Кнопки
            with ui.row().classes('w-full gap-2'):
                ui.button('Отмена').classes('text-xs px-2 py-1 h-7').on('click', dialog.close)
                ui.button('Предоставить доступ', icon='add', color='primary').classes('flex-1 text-xs px-2 py-1 h-7').on('click', handle_grant_access)
    dialog.open()

def grant_access_to_document(document: MayanDocument, username: str, 
                           permission: str, dialog):
    """Предоставляет доступ к документу"""
    try:
        if not username.strip():
            ui.notify('Введите имя пользователя', type='error')
            return
        
        # Показываем индикатор загрузки
        ui.notify('Предоставляем доступ...', type='info')
        
        # Предоставляем доступ через DocumentAccessManager
        success = document_access_manager.grant_document_access_to_user(
            document_id=document.document_id,
            document_label=document.label,
            username=username,
            permission=permission
        )
        
        if success:
            ui.notify(f'Доступ к документу "{document.label}" предоставлен пользователю {username}', type='positive')
            dialog.close()
        else:
            ui.notify('Ошибка при предоставлении доступа. Проверьте логи для подробностей.', type='error')
            
    except Exception as e:
        logger.error(f"Ошибка при предоставлении доступа: {e}")
        ui.notify(f'Ошибка: {str(e)}', type='error')

def show_document_content(document: MayanDocument):
    """
    Показывает содержимое документа в диалоге
    """
    try:
        client = get_mayan_client()
        
        # Получаем текстовое содержимое документа
        content = client.get_document_file_content_as_text(document.document_id)
        
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
            ui.label(f'Содержимое документа: {document.label}').classes('text-lg font-semibold mb-4')
            
            if content:
                # Показываем содержимое в текстовом поле
                ui.textarea(value=content).classes('w-full h-[70vh]').props('readonly')
                
                # Информация о файле
                with ui.row().classes('text-sm text-gray-600 mt-2'):
                    ui.label(f"Файл: {document.file_latest_filename}")
                    ui.label(f"Размер: {format_file_size(document.file_latest_size)}")
                    ui.label(f"Тип: {document.file_latest_mimetype}")
            else:
                ui.label('Не удалось получить содержимое документа').classes('text-red-500')
                ui.label('Возможные причины:').classes('font-bold mt-2')
                ui.label('• Файл не является текстовым').classes('ml-4')
                ui.label('• Файл поврежден').classes('ml-4')
                ui.label('• Нет прав на доступ к файлу').classes('ml-4')
                
                # Кнопка для скачивания файла
                ui.button('Скачать файл', icon='download', on_click=lambda: download_document_file(document)).classes('mt-4 text-xs px-2 py-1 h-7')
            
            # Кнопки управления
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Закрыть').classes('text-xs px-2 py-1 h-7').on('click', dialog.close)
        
        dialog.open()
        
    except Exception as e:
        logger.error(f"Ошибка при получении содержимого документа: {e}")
        ui.notify(f'Ошибка при получении содержимого: {str(e)}', type='error')


async def load_recent_documents():
    """Загружает последние 10 документов"""
    global _recent_documents_container
    
    if not _recent_documents_container:
        logger.warning("Контейнер для документов не инициализирован")
        return
    
    _recent_documents_container.clear()
    
    # Проверяем подключение
    if not await check_connection():
        with _recent_documents_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        logger.info("Загружаем последние документы...")
        # Получаем последние 10 документов
        client = await get_mayan_client()
        documents, total_count = await client.get_documents(page=1, page_size=10)
        logger.info(f"Получено документов: {len(documents)}")
        
        if not documents:
            with _recent_documents_container:
                ui.label('Документы не найдены').classes('text-gray-500 text-center py-8')
            return
        
        with _recent_documents_container:
            tasks = []
            for document in documents:
                card = create_document_card(document)  # Создаем карточку синхронно
                # Загрузка превью происходит автоматически внутри create_document_card через ui.timer
                #tasks.append(asyncio.create_task(load_preview_for_card(card, document)))
            
            # Ждем завершения всех задач (опционально)
            # await asyncio.gather(*tasks)
                
    except Exception as e:
        logger.error(f"Ошибка при загрузке документов: {e}", exc_info=True)
        if _recent_documents_container:
            with _recent_documents_container:
                ui.label(f'Ошибка при загрузке документов: {str(e)}').classes('text-red-500 text-center py-8')

async def search_documents(query: str):
    """Выполняет поиск документов"""
    global _search_results_container
    
    if not query.strip():
        if _search_results_container:
            _search_results_container.clear()
            with _search_results_container:
                ui.label('Введите поисковый запрос').classes('text-gray-500 text-center py-8')
        return
    
    # Проверяем подключение
    if not await check_connection():
        if _search_results_container:
            _search_results_container.clear()
            with _search_results_container:
                ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
                if _auth_error:
                    ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
                ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    # Очищаем контейнер и показываем индикатор сразу
    if _search_results_container:
        _search_results_container.clear()
        loading = LoadingIndicator(_search_results_container, 'Поиск документов...')
        loading.show()
        
        async def perform_search():
            try:
                logger.info(f"Выполняем поиск по запросу: {query}")
                # Выполняем поиск
                client = await get_mayan_client()
                documents = await client.search_documents(query, page=1, page_size=20)
                logger.info(f"Найдено документов: {len(documents)}")
                
                # Скрываем индикатор и очищаем контейнер перед показом результатов
                loading.hide()
                _search_results_container.clear()
                
                if not documents:
                    with _search_results_container:
                        ui.label(f'По запросу "{query}" ничего не найдено').classes('text-gray-500 text-center py-8')
                    return
                
                with _search_results_container:
                    ui.label(f'Найдено документов: {len(documents)}').classes('text-lg font-semibold mb-4')
                    for document in documents:
                        create_document_card(document)
                        
            except Exception as e:
                logger.error(f"Ошибка при поиске документов: {e}")
                loading.hide()
                _search_results_container.clear()
                with _search_results_container:
                    ui.label(f'Ошибка при поиске: {str(e)}').classes('text-red-500 text-center py-8')
        
        # Выполняем поиск с небольшой задержкой, чтобы UI успел обновиться и показать индикатор
        ui.timer(0.05, lambda: perform_search(), once=True)

async def upload_document():
    """Загружает документ на сервер"""
    global _upload_form_container
    
    if _upload_form_container:
        _upload_form_container.clear()
    
    with _upload_form_container:
        ui.label('Загрузка документа').classes('text-lg font-semibold mb-4')
        
        # Проверяем подключение
        if not await check_connection():
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
            return
        
        # Форма загрузки
        with ui.column().classes('w-full gap-4'):
            # Убираем поля названия документа и описания - будем брать из имени файла
            description_input = ui.textarea('Описание (опционально)', placeholder='Введите описание документа').classes('w-full')
            
            try:
                client = await get_mayan_client()
                
                # Получаем типы документов
                document_types = await client.get_document_types()
                document_type_select = None
                if document_types:
                    # ОТЛАДКА: Выводим информацию о том, что приходит от API
                    logger.info(f"Получено типов документов: {len(document_types)}")
                    for i, dt in enumerate(document_types):
                        logger.info(f"Тип {i}: {json.dumps(dt, indent=2, ensure_ascii=False)}")
                    
                    # ИСПРАВЛЕНИЕ: Используем простой список названий для отображения
                    type_options = []
                    type_id_map = {}  # Словарь для соответствия названий и ID
                    for dt in document_types:
                        display_name = dt['label']  # Название типа документа
                        type_options.append(display_name)  # Простой список названий
                        type_id_map[display_name] = dt['id']  # Сохраняем соответствие
                        logger.info(f"Добавляем опцию: '{display_name}' -> {dt['id']}")
                    
                    logger.info(f"Итоговые опции: {type_options}")
                    logger.info(f"Соответствие названий и ID: {type_id_map}")
                                       
                    default_value = type_options[0] if type_options else None  # Название первого элемента
                    document_type_select = ui.select(
                        options=type_options,
                        label='Тип документа',
                        value=default_value
                    ).classes('w-full')
                    
                    # Сохраняем соответствие для использования в handle_file_upload
                    document_type_select.type_id_map = type_id_map
                else:
                    # Изменяем сообщение - это не ошибка, а просто отсутствие типов документов
                    ui.label('Типы документов не найдены в системе').classes('text-orange-500')
                    logger.warning("Типы документов не найдены в системе")
                            
                # Получаем кабинеты
                cabinets = await client.get_cabinets()
                cabinet_select = None
                if cabinets:
                    # ИСПРАВЛЕНИЕ: Используем простой список названий для отображения
                    cabinet_options = []
                    cabinet_id_map = {}  # Словарь для соответствия названий и ID
                    
                    # Добавляем опцию по умолчанию "Выберите кабинет"
                    default_option = 'Выберите кабинет'
                    cabinet_options.append(default_option)
                    
                    for cabinet in cabinets:
                        display_name = cabinet['label']  # Название кабинета
                        cabinet_options.append(display_name)  # Простой список названий
                        cabinet_id_map[display_name] = cabinet['id']  # Сохраняем соответствие
                    
                    # Устанавливаем "Выберите кабинет" как значение по умолчанию
                    cabinet_select = ui.select(
                        options=cabinet_options,
                        label='Кабинет',
                        value=default_option
                    ).classes('w-full')
                    
                    # Сохраняем соответствие для использования в handle_file_upload
                    cabinet_select.cabinet_id_map = cabinet_id_map
                else:
                    ui.label('Кабинеты не найдены').classes('text-gray-500')
                
                # Убираем языки и теги - оставляем только тип документа и кабинет
                                    
            except Exception as e:
                logger.error(f"Ошибка при получении данных с сервера: {e}", exc_info=True)
                ui.label(f'Ошибка при загрузке данных: {str(e)}').classes('text-red-500')
                document_type_select = None
                cabinet_select = None
            
            # Загрузка файла
            # Сохраняем cabinet_id_map в локальную переменную для правильного захвата в lambda
            local_cabinet_id_map = None
            if cabinet_select and hasattr(cabinet_select, 'cabinet_id_map'):
                local_cabinet_id_map = cabinet_select.cabinet_id_map
                logger.info(f"Подготовка формы: cabinet_id_map содержит {len(local_cabinet_id_map)} кабинетов")
                logger.info(f"Подготовка формы: cabinet_id_map = {local_cabinet_id_map}")
            
            # Сохраняем type_id_map в локальную переменную для правильного захвата в lambda
            local_type_id_map = None
            if document_type_select and hasattr(document_type_select, 'type_id_map'):
                local_type_id_map = document_type_select.type_id_map
            
            upload_area = ui.upload(
                on_upload=lambda e: asyncio.create_task(handle_file_upload(
                    e, 
                    description_input.value,
                    document_type_select.value if document_type_select else None,
                    cabinet_select.value if cabinet_select else None,
                    local_cabinet_id_map,
                    local_type_id_map
                )),
                auto_upload=False
            ).classes('w-full')
            
            ui.label('Выберите файл для загрузки').classes('text-sm text-gray-600')

async def handle_file_upload(
    upload_event, 
    description: str, 
    document_type_name: Optional[str] = None, 
    cabinet_name: Optional[str] = None,
    cabinet_id_map: Optional[Dict[str, int]] = None,
    type_id_map: Optional[Dict[str, int]] = None
) -> None:
    """Обрабатывает загрузку файла с улучшенной архитектурой"""
    global _upload_form_container
    
    if not _upload_form_container:
        # Не можем использовать ui.notify в асинхронной задаче, логируем ошибку
        logger.error('Форма загрузки не инициализирована')
        return
    
    try:
        # Валидация выбора типа документа
        if not document_type_name:
            if _upload_form_container:
                with _upload_form_container:
                    error_label = ui.label('Пожалуйста, выберите тип документа').classes('text-red-500 p-4 bg-red-50 rounded')
            logger.warning("Попытка загрузки без выбранного типа документа")
            return
        
        # Валидация выбора кабинета
        if not cabinet_name or cabinet_name == 'Выберите кабинет':
            if _upload_form_container:
                with _upload_form_container:
                    error_label = ui.label('Пожалуйста, выберите кабинет для сохранения документа').classes('text-red-500 p-4 bg-red-50 rounded')
            logger.warning("Попытка загрузки без выбранного кабинета")
            return
        
        # Получаем имя файла без расширения для названия документа
        filename = upload_event.name
        # Убираем расширение файла для названия документа
        document_label = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        logger.info(f"Имя файла: {filename}")
        logger.info(f"Название документа (без расширения): {document_label}")
        logger.info(f"Полученные параметры: document_type_name={document_type_name}, cabinet_name={cabinet_name}, cabinet_id_map={cabinet_id_map}")
        
        # Получаем ID кабинета из карты, если она передана
        cabinet_id = None
        if cabinet_name and cabinet_id_map:
            logger.info(f"Попытка найти кабинет '{cabinet_name}' в карте")
            logger.info(f"Доступные ключи в карте: {list(cabinet_id_map.keys())}")
            cabinet_id = cabinet_id_map.get(cabinet_name)
            if cabinet_id:
                logger.info(f"Кабинет '{cabinet_name}' найден в карте, ID: {cabinet_id}")
            else:
                logger.warning(f"Кабинет '{cabinet_name}' не найден в карте")
        else:
            if not cabinet_name:
                logger.warning("cabinet_name не передан или пустой")
            if not cabinet_id_map:
                logger.warning("cabinet_id_map не передан или пустой")
        
        logger.info(f"Итоговый cabinet_id: {cabinet_id}")
        
        # Создаем параметры загрузки
        params = UploadParams(
            label=document_label,  # Используем имя файла без расширения
            description=description,
            document_type_name=document_type_name,
            cabinet_name=cabinet_name,
            cabinet_id=cabinet_id,  # Добавляем ID напрямую
            language_name=None,  # Убираем языки
            tag_names=None  # Убираем теги
        )
        
        logger.info(f"Создан UploadParams с cabinet_id={params.cabinet_id}")
        
        # Получаем клиент
        client = await get_mayan_client()
        
        # Создаем загрузчик с упрощенным извлекателем
        uploader = DocumentUploader(client, SimpleFormDataExtractor())
        await uploader.upload_document(upload_event, params, _upload_form_container)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке документа: {e}", exc_info=True)
        # Используем контейнер для отображения ошибки вместо ui.notify
        try:
            if _upload_form_container:
                with _upload_form_container:
                    error_label = ui.label(f'Ошибка загрузки: {str(e)}').classes('text-red-500 p-4 bg-red-50 rounded')
        except Exception as ui_error:
            # Если даже это не работает, просто логируем
            logger.error(f'Не удалось отобразить ошибку в UI: {ui_error}')


async def download_document_file(document: MayanDocument):
    """Скачивает файл документа через прокси"""
    try:
        client = await get_mayan_client()
        
        # Получаем содержимое файла
        file_content = await client.get_document_file_content(document.document_id)
        if not file_content:
            ui.notify('Не удалось получить содержимое файла', type='error')
            return
        
        # Создаем временный файл для скачивания
        filename = document.file_latest_filename or f"document_{document.document_id}"
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        # Открываем файл для скачивания
        ui.download(temp_path, filename)
        
        # Удаляем временный файл через некоторое время
        ui.timer(5.0, lambda: os.unlink(temp_path), once=True)
        
        ui.notify(f'Файл "{filename}" подготовлен для скачивания', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        ui.notify(f'Ошибка при скачивании: {str(e)}', type='error')

async def preview_document_file(document: MayanDocument):
    """Показывает превью документа в диалоге"""
    try:
        client = await get_mayan_client()
        
        # Получаем содержимое файла
        file_content = await client.get_document_file_content(document.document_id)
        if not file_content:
            ui.notify('Не удалось получить содержимое файла для просмотра', type='error')
            return
        
        # Определяем тип файла по расширению, если MIME-тип не определен или неправильный
        filename = document.file_latest_filename or f"document_{document.document_id}"
        mimetype = document.file_latest_mimetype or 'application/octet-stream'
        
        # ИСПРАВЛЕНИЕ: Проверяем магические байты для правильного определения типа файла
        if file_content:
            # Проверяем PDF по магическим байтам
            if file_content[:4] == b'%PDF':
                mimetype = 'application/pdf'
                logger.info(f"Определен MIME-тип по магическим байтам: {mimetype}")
            # Проверяем изображения
            elif file_content[:3] == b'\xff\xd8\xff':
                mimetype = 'image/jpeg'
                logger.info(f"Определен MIME-тип по магическим байтам: {mimetype}")
            elif file_content[:8] == b'\x89PNG\r\n\x1a\n':
                mimetype = 'image/png'
                logger.info(f"Определен MIME-тип по магическим байтам: {mimetype}")
            elif file_content[:6] in [b'GIF87a', b'GIF89a']:
                mimetype = 'image/gif'
                logger.info(f"Определен MIME-тип по магическим байтам: {mimetype}")
            # Если MIME-тип все еще не определен, пробуем по расширению
            elif mimetype == 'application/octet-stream' or not mimetype:
                detected_mimetype, _ = mimetypes.guess_type(filename)
                if detected_mimetype:
                    mimetype = detected_mimetype
                    logger.info(f"Определен MIME-тип по расширению: {mimetype}")
        
        # Увеличиваем размер диалога для лучшего просмотра
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-[95vw] max-h-[95vh]'):
            ui.label(f'Просмотр документа: {document.label}').classes('text-lg font-semibold mb-4')
            
            # Проверяем, можно ли отобразить файл как текст
            if mimetype.startswith('text/') or mimetype in ['application/json', 'application/xml']:
                try:
                    content_text = file_content.decode('utf-8')
                    ui.textarea(value=content_text).classes('w-full h-[70vh]').props('readonly')
                except UnicodeDecodeError:
                    ui.label('Файл содержит бинарные данные и не может быть отображен как текст').classes('text-gray-500')
            
            elif mimetype.startswith('image/'):
                # Для изображений создаем временный файл и отображаем
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                    temp_file.write(file_content)
                    temp_path = temp_file.name
                
                # Конвертируем в base64 для отображения
                with open(temp_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                    ui.image(f"data:{mimetype};base64,{img_data}").classes('max-w-full max-h-[70vh]')
                
                # Удаляем временный файл
                os.unlink(temp_path)
            
            elif mimetype == 'application/pdf':
                # Для PDF файлов создаем временный файл и отображаем через iframe
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                    temp_file.write(file_content)
                    temp_path = temp_file.name
                
                # Конвертируем в base64 для создания blob URL
                with open(temp_path, 'rb') as f:
                    pdf_data = base64.b64encode(f.read()).decode()
                
                # Создаем уникальный ID для контейнера PDF
                pdf_container_id = f"pdf-container-{document.document_id}"
                pdf_iframe_id = f"pdf-iframe-{document.document_id}"
                
                # Создаем HTML контейнер с iframe
                ui.html(f'''
                    <div id="{pdf_container_id}" style="width: 100%; height: 75vh; min-height: 600px;">
                        <iframe id="{pdf_iframe_id}" 
                                width="100%" 
                                height="100%" 
                                style="border: none;">
                            <p>Ваш браузер не поддерживает отображение PDF файлов.</p>
                        </iframe>
                    </div>
                ''').classes('w-full')
                
                # ИСПРАВЛЕНИЕ: Используем ui.add_body_html() для добавления скрипта
                # Создаем blob URL через JavaScript для избежания ограничений размера data URI
                script_content = f'''
                    (function() {{
                        const pdfData = {repr(pdf_data)};
                        const binaryString = atob(pdfData);
                        const bytes = new Uint8Array(binaryString.length);
                        for (let i = 0; i < binaryString.length; i++) {{
                            bytes[i] = binaryString.charCodeAt(i);
                        }}
                        const blob = new Blob([bytes], {{ type: 'application/pdf' }});
                        const blobUrl = URL.createObjectURL(blob);
                        const iframe = document.getElementById('{pdf_iframe_id}');
                        if (iframe) {{
                            iframe.src = blobUrl;
                        }}
                        
                        // Очищаем blob URL при закрытии диалога (через 5 минут или при размонтировании)
                        setTimeout(function() {{
                            URL.revokeObjectURL(blobUrl);
                        }}, 300000);
                    }})();
                '''
                ui.add_body_html(f'<script>{script_content}</script>')
                
                # Удаляем временный файл
                ui.timer(10.0, lambda: os.unlink(temp_path), once=True)
            
            elif mimetype in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                # Для документов Word показываем информацию
                ui.label('Документ Microsoft Word').classes('text-lg font-semibold mb-2')
                ui.label(f'Файл: {filename}').classes('text-sm text-gray-600 mb-2')
                ui.label(f'Размер: {format_file_size(len(file_content))}').classes('text-sm text-gray-600 mb-4')
                ui.label('Для просмотра документа Word скачайте файл и откройте в соответствующем приложении.').classes('text-gray-500')
            
            else:
                # Для неизвестных типов файлов показываем информацию
                ui.label('Файл не может быть отображен в браузере').classes('text-lg font-semibold mb-2')
                ui.label(f'Тип файла: {mimetype}').classes('text-sm text-gray-600 mb-2')
                ui.label(f'Размер: {format_file_size(len(file_content))}').classes('text-sm text-gray-600 mb-4')
                ui.label('Скачайте файл для просмотра в соответствующем приложении.').classes('text-gray-500')
            
            with ui.row().classes('mt-4'):
                ui.button('Закрыть', on_click=dialog.close).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                ui.button('Открыть в новой вкладке', icon='open_in_new', on_click=lambda: (
                    ui.download(temp_path if 'temp_path' in locals() else None, filename),
                    dialog.close()
                )).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        dialog.open()
        
    except Exception as e:
        logger.error(f'Ошибка при просмотре документа: {e}', exc_info=True)
        ui.notify(f'Ошибка при просмотре документа: {str(e)}', type='error')

# def grant_access_to_document_enhanced(document: MayanDocument, access_type: str,
#                                     username: str, role_name: str, 
#                                     permission: str, dialog):
#     """Предоставляет доступ к документу пользователю или роли"""
#     try:
#         if access_type == 'Пользователь':
#             if not username or not username.strip():
#                 ui.notify('Введите имя пользователя', type='error')
#                 return
            
#             success = document_access_manager.grant_document_access_to_user(
#                 document_id=document.document_id,
#                 document_label=document.label,
#                 username=username,
#                 permission=permission
#             )
            
#             if success:
#                 ui.notify(f'Доступ к документу "{document.label}" предоставлен пользователю {username}', type='positive')
#             else:
#                 ui.notify('Ошибка при предоставлении доступа пользователю', type='error')
        
#         else:  # Роль
#             if not role_name or not role_name.strip():
#                 ui.notify('Введите название роли', type='error')
#                 return
            
#             success = document_access_manager.grant_document_access_to_role(
#                 document_id=document.document_id,
#                 document_label=document.label,
#                 role_name=role_name,
#                 permission=permission
#             )
            
#             if success:
#                 ui.notify(f'Доступ к документу "{document.label}" предоставлен роли {role_name}', type='positive')
#             else:
#                 ui.notify('Ошибка при предоставлении доступа роли', type='error')
        
#         dialog.close()
            
#     except Exception as e:
#         logger.error(f"Ошибка при предоставлении доступа: {e}")
#         ui.notify(f'Ошибка: {str(e)}', type='error')

def grant_access_to_document_enhanced(document: MayanDocument, access_type: str,
                                    username: str, role_name: str, 
                                    permission: str, dialog):
    """
    Предоставляет доступ к документу с улучшенной обработкой ошибок
    """
    try:
        # Если permission содержит запятые, разделяем на отдельные разрешения
        if ',' in permission:
            permissions = [p.strip() for p in permission.split(',')]
        else:
            permissions = [permission]
        
        logger.info(f"Предоставляем доступ к документу {document.document_id}")
        logger.info(f"Тип доступа: {access_type}")
        logger.info(f"Роль: {role_name}")
        logger.info(f"Разрешения: {permissions}")
        
        # Предоставляем доступ для каждого разрешения
        for perm in permissions:
            result = document_access_manager.grant_access_to_document(
                document_id=document.document_id,
                username=username,
                role_name=role_name,
                permission_name=perm
            )
            
            if result.get('error'):
                logger.error(f"Ошибка при предоставлении разрешения {perm}: {result['error']}")
                ui.notify(f'Ошибка при предоставлении разрешения {perm}: {result["error"]}', type='error')
                return
        
        ui.notify(f'Доступ успешно предоставлен! Тип: {access_type}', type='positive')
        dialog.close()
        
    except Exception as e:
        logger.error(f"Ошибка при предоставлении доступа: {e}")
        ui.notify(f'Ошибка: {str(e)}', type='error')


def show_document_access_info(document: MayanDocument):
    """
    Показывает информацию о доступе к документу
    """
    ui.notify('Загружаем информацию о доступе...', type='info')
    
    access_info = document_access_manager.get_document_access_info(document.document_id)
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
        ui.label(f'Доступ к документу "{document.label}"').classes('text-lg font-semibold mb-4')
        
        if access_info.get('error'):
            ui.label(f'Ошибка: {access_info["error"]}').classes('text-red-500')
        else:
            # Показываем общую информацию
            ui.label(f'Найдено ACL записей: {len(access_info["acls"])}').classes('font-bold')
            ui.label(f'Метод получения: {access_info.get("access_method", "unknown")}').classes('text-sm text-gray-600 mb-4')
            
            # Показываем роли с доступом
            if access_info['roles_with_access']:
                ui.label('Роли с доступом:').classes('font-bold mt-4')
                for role in access_info['roles_with_access']:
                    ui.label(f"• {role.get('label', 'Неизвестная роль')}").classes('ml-4')
            
            # Показываем пользователей с доступом
            if access_info['users_with_access']:
                ui.label('Пользователи с доступом:').classes('font-bold mt-4')
                for user in access_info['users_with_access']:
                    ui.label(f"• {user.get('username', 'Неизвестный пользователь')}").classes('ml-4')
            
            # Показываем детальную информацию об ACL
            if access_info['acls']:
                ui.label('Детальная информация об ACL:').classes('font-bold mt-4')
                
                for i, acl in enumerate(access_info['acls']):
                    with ui.expansion(f'ACL {i+1} (ID: {acl.get("acl_id", "unknown")})').classes('w-full'):
                        # Показываем роль
                        if acl.get('role'):
                            ui.label(f"Роль: {acl['role'].get('label', 'Неизвестная роль')}")
                        
                        # Показываем пользователя
                        if acl.get('user'):
                            ui.label(f"Пользователь: {acl['user'].get('username', 'Неизвестный пользователь')}")
                        
                        # Показываем разрешения
                        if acl.get('permissions'):
                            ui.label('Разрешения:').classes('font-bold mt-2')
                            for perm in acl['permissions']:
                                ui.label(f"• {perm.get('name', 'Неизвестное разрешение')}").classes('ml-4')
                        
                        # Показываем детали ACL
                        if acl.get('details'):
                            ui.label('Детали ACL:').classes('font-bold mt-2')
                            ui.code(str(acl['details'])).classes('text-xs')
                        
                        # Показываем краткую информацию
                        if acl.get('summary'):
                            ui.label('Краткая информация:').classes('font-bold mt-2')
                            ui.code(str(acl['summary'])).classes('text-xs')
                        
                        # Показываем ошибки
                        if acl.get('error'):
                            ui.label(f'Ошибка: {acl["error"]}').classes('text-red-500')
            
            if not access_info['roles_with_access'] and not access_info['users_with_access']:
                ui.label('Нет настроенного доступа').classes('text-gray-500')
                ui.label('Это означает, что:').classes('font-bold mt-2')
                ui.label('• Документ доступен всем пользователям').classes('ml-4')
                ui.label('• Или ACL не настроены').classes('ml-4')
        
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Закрыть').on('click', dialog.close)
    
    dialog.open()

def content() -> None:
    """Основная страница работы с документами Mayan EDMS - кабинеты с документами"""
    global _recent_documents_container
    
    logger.info("Открыта страница работы с документами Mayan EDMS")
    
    # Секция с документами
    with ui.row().classes('w-full mb-4'):
        ui.label('Документы по кабинетам').classes('text-lg font-semibold')
        ui.button('Обновить', icon='refresh', on_click=load_documents_by_cabinets).classes('ml-auto text-xs px-2 py-1 h-7')
    
    _recent_documents_container = ui.column().classes('w-full')
    # Загружаем документы только после создания контейнера
    ui.timer(0.1, load_documents_by_cabinets, once=True)

async def load_documents_by_cabinets():
    """Загружает документы, сгруппированные по кабинетам"""
    global _recent_documents_container
    
    if _recent_documents_container:
        _recent_documents_container.clear()
    
    # Проверяем подключение
    if not await check_connection():
        with _recent_documents_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        client = await get_mayan_client()
        
        # Получаем список кабинетов
        logger.info("Загружаем список кабинетов...")
        cabinets = await client.get_cabinets()
        logger.info(f"Получено кабинетов: {len(cabinets)}")
        
        if not cabinets:
            with _recent_documents_container:
                ui.label('Кабинеты не найдены').classes('text-gray-500 text-center py-8')
            return
        
        # Создаем словарь кабинетов по ID для быстрого доступа
        cabinets_dict = {cab.get('id'): cab for cab in cabinets}
        
        # Находим корневые кабинеты (без parent_id)
        root_cabinets = [cab for cab in cabinets if not cab.get('parent_id')]
        
        def create_cabinet_tree(cabinet, level=0):
            """Рекурсивно создает дерево кабинетов"""
            cabinet_id = cabinet.get('id')
            cabinet_label = cabinet.get('label', f'Кабинет {cabinet_id}')
            cabinet_full_path = cabinet.get('full_path', cabinet_label)
            
            # Отступ для вложенных кабинетов
            indent_class = f'ml-{level * 4}' if level > 0 else ''
            
            # Создаем заголовок с плейсхолдером для количества
            cabinet_title = f"{cabinet_full_path} (…)"
            
            # Создаем разворачиваемую секцию для кабинета
            with ui.expansion(cabinet_title, icon='folder').classes(f'w-full mb-2 {indent_class} bg-blue-50 text-lg font-medium') as expansion:
                # Делаем иконку папки синей
                expansion.props('icon-color="primary"')
                # Если props не работает, используем CSS
                expansion.style('--q-primary: #1976D2; color: #1976D2;')
                
                # Создаем отдельный label для заголовка, который можно обновлять
                #title_label = ui.label(cabinet_title).classes('text-lg font-medium')
                
                # Функция для обновления заголовка с количеством документов
                def update_cabinet_title(count: int):
                    """Обновляет заголовок кабинета с количеством документов"""
                    try:
                        new_title = f"{cabinet_full_path} ({count})"
                        # Обновляем заголовок expansion через props
                        expansion.props(f'label="{new_title}"')
                        expansion.update()
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении заголовка кабинета {cabinet_id}: {e}")
                        # Альтернативный способ - через JavaScript
                        try:
                            ui.run_javascript(f'''
                                const element = document.querySelector('[data-id="{expansion.id}"]');
                                if (element) {{
                                    const header = element.querySelector('.q-expansion-item__header');
                                    if (header) {{
                                        const label = header.querySelector('.q-expansion-item__header-content');
                                        if (label) {{
                                            label.textContent = "{new_title}";
                                        }}
                                    }}
                                }}
                            ''')
                        except:
                            pass
                
                # Асинхронно загружаем количество документов
                async def load_documents_count():
                    """Загружает количество документов в кабинете"""
                    try:
                        count = await client.get_cabinet_documents_count(cabinet_id)
                        update_cabinet_title(count)
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке количества документов кабинета {cabinet_id}: {e}")
                        # В случае ошибки показываем заголовок без количества
                        update_cabinet_title(0)
                
                # Загружаем количество документов с небольшой задержкой, чтобы не блокировать UI
                ui.timer(0.1, load_documents_count, once=True)
                
                # Функция для обновления стилей при разворачивании
                def update_expansion_style(is_expanded):
                    """Обновляет стили заголовка при разворачивании"""
                    if is_expanded:
                        expansion.style('--q-primary: #1565C0; color: #1565C0; font-weight: 600;')
                    else:
                        expansion.style('--q-primary: #1976D2; color: #1976D2; font-weight: 500;')
                
                # Контейнер для документов и подкабинетов
                content_container = ui.column().classes('w-full mt-2')
                
                # Флаг для отслеживания, загружены ли уже документы
                documents_loaded = False
                
                # Загружаем документы асинхронно при разворачивании
                async def load_cabinet_content():
                    """Загружает документы и подкабинеты для конкретного кабинета"""
                    nonlocal documents_loaded
                    
                    # Если документы уже загружены, не загружаем повторно
                    if documents_loaded:
                        return
                    
                    documents_loaded = True
                    
                    # Обновляем стиль заголовка при разворачивании
                    update_expansion_style(True)
                    
                    try:
                        content_container.clear()
                        
                        # Показываем индикатор загрузки
                        with content_container:
                            loading_label = ui.label('Загрузка...').classes('text-sm text-gray-500')
                        
                        # Переменные для пагинации
                        current_page = 1
                        page_size = 10
                        total_count = 0
                        documents_container = None
                        pagination_container = None
                        
                        # Функция для загрузки документов с пагинацией
                        async def load_documents_page(page: int, size: int):
                            """Загружает страницу документов"""
                            nonlocal current_page, page_size, total_count
                            
                            try:
                                # Показываем индикатор загрузки
                                if documents_container:
                                    documents_container.clear()
                                    with documents_container:
                                        loading_label = ui.label('Загрузка...').classes('text-sm text-gray-500')
                                
                                # Получаем документы кабинета
                                logger.info(f"Загружаем документы кабинета {cabinet_id} ({cabinet_label}): страница {page}, размер {size}...")
                                documents, total_count = await client.get_cabinet_documents(cabinet_id, page=page, page_size=size)
                                logger.info(f"Получено документов для кабинета {cabinet_id}: {len(documents)} из {total_count}")
                                
                                current_page = page
                                page_size = size
                                
                                # Обновляем контейнер документов
                                if documents_container:
                                    documents_container.clear()
                                    
                                    if documents:
                                        with documents_container:
                                            # Создаем label для счетчика документов
                                            documents_count_label = ui.label(
                                                f'Найдено документов: {total_count} (показано {len(documents)} из {total_count})'
                                            ).classes('text-sm text-gray-600 mb-2')
                                            
                                            for document in documents:
                                                # Передаем функцию обновления заголовка, текущий счетчик и label счетчика
                                                create_document_card(
                                                    document, 
                                                    update_cabinet_title, 
                                                    total_count,
                                                    documents_count_label
                                                )
                                    else:
                                        with documents_container:
                                            ui.label('Документы не найдены').classes('text-sm text-gray-500 text-center py-4')
                                
                                # Обновляем пагинацию
                                if pagination_container:
                                    pagination_container.clear()
                                    update_pagination_ui()
                                    
                            except Exception as e:
                                logger.error(f"Ошибка при загрузке страницы документов кабинета {cabinet_id}: {e}", exc_info=True)
                                if documents_container:
                                    documents_container.clear()
                                    with documents_container:
                                        ui.label(f'Ошибка при загрузке: {str(e)}').classes('text-sm text-red-500')
                        
                        # Функция для обновления UI пагинации
                        def update_pagination_ui():
                            """Обновляет элементы управления пагинацией"""
                            if not pagination_container:
                                return
                            
                            with pagination_container:
                                with ui.row().classes('w-full items-center gap-2'):
                                    # Кнопка "Предыдущая"
                                    prev_button = ui.button('◄', on_click=lambda: load_documents_page(current_page - 1, page_size))
                                    prev_button.set_enabled(current_page > 1)
                                    
                                    # Информация о странице
                                    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
                                    page_info = ui.label(f'Страница {current_page} из {total_pages}').classes('text-sm')
                                    
                                    # Кнопка "Следующая"
                                    next_button = ui.button('►', on_click=lambda: load_documents_page(current_page + 1, page_size))
                                    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
                                    next_button.set_enabled(current_page < total_pages)
                                    
                                    # Выбор размера страницы
                                    ui.label('Размер страницы:').classes('text-sm ml-4')
                                    page_size_select = ui.select(
                                        [10, 20, 50, 100],
                                        value=page_size,
                                        on_change=lambda e: load_documents_page(1, int(e.value))
                                    ).classes('text-sm')
                        
                        # Находим подкабинеты
                        child_cabinets = [cab for cab in cabinets if cab.get('parent_id') == cabinet_id]
                        
                        content_container.clear()
                        
                        # Показываем подкабинеты
                        if child_cabinets:
                            with content_container:
                                ui.label('Подкабинеты:').classes('text-sm font-semibold mb-2')
                                for child_cab in child_cabinets:
                                    create_cabinet_tree(child_cab, level + 1)
                        
                        # Создаем контейнер для документов
                        with content_container:
                            if child_cabinets:
                                ui.label('Документы:').classes('text-sm font-semibold mb-2 mt-4')
                            
                            # Контейнер для списка документов
                            documents_container = ui.column().classes('w-full')
                            
                            # Контейнер для пагинации
                            pagination_container = ui.column().classes('w-full mt-4')
                        
                        # Загружаем первую страницу документов
                        await load_documents_page(1, 10)
                                
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке содержимого кабинета {cabinet_id}: {e}", exc_info=True)
                        content_container.clear()
                        with content_container:
                            ui.label(f'Ошибка при загрузке: {str(e)}').classes('text-sm text-red-500')

                # Используем правильный способ отслеживания разворачивания
                def on_expansion_change(e):
                    """Обработчик изменения состояния expansion"""
                    try:
                        is_expanded = False
                        # В NiceGUI событие может передавать значение напрямую
                        if hasattr(e, 'value'):
                            is_expanded = e.value
                        elif hasattr(e, 'args'):
                            # Если args - это bool
                            if isinstance(e.args, bool):
                                is_expanded = e.args
                            elif isinstance(e.args, (list, tuple)) and len(e.args) > 0:
                                is_expanded = e.args[0]
                        
                        # Обновляем стили при изменении состояния
                        update_expansion_style(is_expanded)
                        
                        # Загружаем содержимое при разворачивании (используем timer для async функции)
                        if is_expanded:
                            ui.timer(0.01, load_cabinet_content, once=True)
                    except Exception as ex:
                        logger.error(f"Ошибка при обработке события expansion: {ex}")
                        # В случае ошибки пробуем загрузить
                        ui.timer(0.01, load_cabinet_content, once=True)
                
                expansion.on('update:model-value', on_expansion_change)
        
        # Создаем дерево кабинетов
        with _recent_documents_container:
            if root_cabinets:
                for root_cabinet in root_cabinets:
                    create_cabinet_tree(root_cabinet)
            else:
                # Если нет корневых кабинетов, показываем все кабинеты
                for cabinet in cabinets:
                    create_cabinet_tree(cabinet)
                
    except Exception as e:
        logger.error(f"Ошибка при загрузке кабинетов: {e}", exc_info=True)
        with _recent_documents_container:
            ui.label(f'Ошибка при загрузке кабинетов: {str(e)}').classes('text-red-500 text-center py-8')

def search_content() -> None:
    """Страница поиска документов"""
    global _search_results_container
    
    logger.info("Открыта страница поиска документов")
    
    ui.label('Поиск документов').classes('text-lg font-semibold mb-4')
    
    with ui.row().classes('w-full mb-4'):
        search_input = ui.input('Поисковый запрос', placeholder='Введите название документа для поиска').classes('flex-1')
        ui.button('Поиск', icon='search', on_click=lambda: search_documents(search_input.value)).classes('ml-2 text-xs px-2 py-1 h-7')
    
    _search_results_container = ui.column().classes('w-full')
    with _search_results_container:
        ui.label('Введите поисковый запрос для начала поиска').classes('text-gray-500 text-center py-8')

async def upload_content(container: Optional[ui.column] = None, user: Optional[Any] = None) -> None:
    """Страница загрузки документов"""
    global _upload_form_container
    
    logger.info("Открыта страница загрузки документов")
    
    # Используем переданный контейнер или создаем новый (если вызывается напрямую)
    if container is not None:
        _upload_form_container = container
    else:
        _upload_form_container = ui.column().classes('w-full')
    
    # Сохраняем пользователя в глобальной переменной для использования в асинхронных функциях
    if user is not None:
        global _current_user
        _current_user = user
    
    await upload_document()

async def download_signed_document(document: MayanDocument):
    '''Скачивает документ с информацией о подписях'''
    try:       
        ui.notify('Создание итогового документа с подписями...', type='info')
        
        signature_manager = SignatureManager()
        signed_pdf = await signature_manager.create_signed_document_pdf(document.document_id)
        
        if signed_pdf:
            # Создаем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"signed_{document.label.replace(' ', '_')}_{timestamp}.pdf"
            
            # ИСПРАВЛЕНИЕ: Создаем временный файл для скачивания через браузер
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                temp_file.write(signed_pdf)
                temp_path = temp_file.name
            
            # Открываем файл для скачивания
            ui.download(temp_path, filename)
            
            # Удаляем временный файл через некоторое время
            ui.timer(5.0, lambda: os.unlink(temp_path), once=True)
            
            ui.notify(f'Файл "{filename}" подготовлен для скачивания', type='success')
            logger.info(f'Итоговый документ {document.document_id} подготовлен для скачивания как {filename}')
        else:
            ui.notify('Не удалось создать документ с подписями', type='warning')
            
    except Exception as e:
        logger.error(f'Ошибка скачивания документа с подписями: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')

async def show_mayan_reauth_dialog() -> Optional[str]:
    """
    Показывает диалог повторной авторизации для Mayan EDMS
    
    Returns:
        Новый API токен или None если авторизация не удалась
    """
    current_user = get_current_user()
    if not current_user:
        ui.notify('Пользователь не авторизован', type='error')
        return None
    
    dialog_result = {'token': None, 'cancelled': False}
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-md'):
        ui.label('Требуется повторная авторизация').classes('text-lg font-semibold mb-4')
        ui.label(f'API токен Mayan EDMS для пользователя {current_user.username} истек.').classes('text-sm text-gray-600 mb-4')
        ui.label('Пожалуйста, введите пароль для повторной авторизации:').classes('text-sm mb-2')
        
        password_input = ui.input('Пароль', password=True, placeholder='Введите пароль').classes('w-full mb-4')
        
        status_label = ui.label('').classes('text-sm text-center mb-4')
        
        async def handle_reauth():
            """Обрабатывает повторную авторизацию"""
            password = password_input.value.strip()
            
            if not password:
                status_label.text = 'Пожалуйста, введите пароль'
                status_label.classes('text-red-500')
                return
            
            status_label.text = 'Проверка учетных данных...'
            status_label.classes('text-blue-500')
            
            try:               
                # Создаем временный клиент с системными учетными данными
                temp_mayan_client = MayanClient(
                    base_url=config.mayan_url,
                    username=config.mayan_username,
                    password=config.mayan_password,
                    api_token=config.mayan_api_token,
                    verify_ssl=False
                )
                
                # Создаем новый API токен для пользователя
                new_token = await temp_mayan_client.create_user_api_token(current_user.username, password)
                
                if new_token:
                    # Обновляем токен в сессии
                    current_user.mayan_api_token = new_token
                    # Обновляем сессию в session_manager
                    try:
                        from auth.token_storage import token_storage
                        client_ip = ui.context.client.request.client.host
                        token = token_storage.get_token(client_ip)
                        if token:
                            session = session_manager.get_user_by_token(token)
                            if session:
                                session.mayan_api_token = new_token
                    except Exception as e:
                        logger.warning(f'Не удалось обновить токен в сессии: {e}')
                    
                    status_label.text = 'Авторизация успешна!'
                    status_label.classes('text-green-500')
                    
                    dialog_result['token'] = new_token
                    dialog.close()
                else:
                    status_label.text = 'Неверный пароль или ошибка создания токена'
                    status_label.classes('text-red-500')
                    
            except Exception as e:
                logger.error(f'Ошибка при повторной авторизации: {e}', exc_info=True)
                status_label.text = f'Ошибка авторизации: {str(e)}'
                status_label.classes('text-red-500')
        
        def handle_cancel():
            """Обрабатывает отмену"""
            dialog_result['cancelled'] = True
            dialog.close()
        
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Отмена', on_click=handle_cancel).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
            ui.button('Авторизоваться', on_click=handle_reauth).classes('bg-blue-500 text-white text-xs px-2 py-1 h-7')
        
        # Обработка нажатия Enter
        password_input.on('keydown.enter', handle_reauth)
    
    dialog.open()
    
    # Ждем закрытия диалога
    await dialog
    
    if dialog_result['cancelled']:
        return None
    
    return dialog_result['token']

async def delete_document(document: MayanDocument, card: ui.card = None):
    """Удаляет документ с подтверждением и удаляет карточку из UI"""
    try:
        # Показываем диалог подтверждения
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md'):
            ui.label(f'Удаление документа').classes('text-lg font-semibold mb-4')
            ui.label(f'Вы уверены, что хотите удалить документ "{document.label}"?').classes('text-sm mb-4')
            ui.label('Это действие нельзя отменить.').classes('text-xs text-red-500 mb-4')
            
            async def confirm_delete():
                try:
                    client = await get_mayan_client()
                    success = await client.delete_document(document.document_id)
                    
                    if success:
                        ui.notify(f'Документ "{document.label}" успешно удален', type='positive')
                        dialog.close()
                        
                        # Удаляем карточку из UI напрямую, если она передана
                        if card:
                            try:
                                # Читаем текущее значение счетчика из label "Найдено документов"
                                current_count = None
                                if hasattr(card, 'documents_count_label') and card.documents_count_label:
                                    try:
                                        # Парсим текущее значение из текста label
                                        label_text = card.documents_count_label.text
                                        import re
                                        match = re.search(r'Найдено документов:\s*(\d+)', label_text)
                                        if match:
                                            current_count = int(match.group(1))
                                            logger.info(f'Прочитано текущее значение счетчика из label: {current_count}')
                                    except Exception as e:
                                        logger.warning(f'Не удалось прочитать счетчик из label: {e}')
                                
                                # Если не удалось прочитать из label, используем сохраненное значение
                                if current_count is None and hasattr(card, 'current_count') and card.current_count is not None:
                                    current_count = card.current_count
                                    logger.info(f'Используем сохраненное значение счетчика: {current_count}')
                                
                                # Обновляем счетчики, если удалось определить текущее значение
                                if current_count is not None:
                                    new_count = max(0, current_count - 1)  # Уменьшаем на 1, но не меньше 0
                                    
                                    # Обновляем счетчик документов в заголовке кабинета
                                    if hasattr(card, 'update_cabinet_title_func') and card.update_cabinet_title_func:
                                        card.update_cabinet_title_func(new_count)
                                        logger.info(f'Обновлен счетчик документов в заголовке кабинета: {new_count}')
                                    
                                    # Обновляем label "Найдено документов"
                                    if hasattr(card, 'documents_count_label') and card.documents_count_label:
                                        card.documents_count_label.text = f'Найдено документов: {new_count}'
                                        logger.info(f'Обновлен label счетчика документов: {new_count}')
                                    
                                    # Обновляем счетчик во всех карточках, которые используют тот же label
                                    # Это нужно для того, чтобы при следующем удалении использовалось актуальное значение
                                    if hasattr(card, 'documents_count_label') and card.documents_count_label:
                                        # Находим все карточки с тем же label и обновляем их счетчик
                                        # Это делается через обновление самого label, так что другие карточки будут читать актуальное значение
                                        pass  # Label уже обновлен выше
                                else:
                                    logger.warning('Не удалось определить текущее значение счетчика')
                                
                                card.delete()
                                logger.info(f'Карточка документа {document.document_id} удалена из UI')
                            except Exception as e:
                                logger.warning(f'Не удалось удалить карточку из UI: {e}')
                                # Fallback: обновляем список, если не удалось удалить карточку
                                await load_documents_by_cabinets()
                        else:
                            # Если карточка не передана, обновляем весь список
                            logger.warning('Карточка не передана в delete_document, обновляем весь список')
                            await load_documents_by_cabinets()
                    else:
                        ui.notify('Ошибка при удалении документа', type='error')
                except Exception as e:
                    logger.error(f'Ошибка при удалении документа: {e}', exc_info=True)
                    ui.notify(f'Ошибка при удалении: {str(e)}', type='error')
            
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Отмена', on_click=dialog.close).classes('bg-gray-500 text-white text-xs px-2 py-1 h-7')
                ui.button('Удалить', icon='delete', color='red', on_click=confirm_delete).classes('bg-red-500 text-white text-xs px-2 py-1 h-7')
        
        dialog.open()
        
    except Exception as e:
        logger.error(f'Ошибка при открытии диалога удаления документа: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')

async def toggle_favorite(document: MayanDocument, button: ui.button, card: Optional[ui.card] = None, count_label: Optional[ui.label] = None):
    """Добавляет или удаляет документ из избранного"""
    try:
        client = await get_mayan_client()
        
        # Если карточка передана (на странице избранных), мы знаем, что документ в избранном
        # Не проверяем статус, сразу удаляем
        if card:
            # Удаляем из избранного
            success = await client.remove_document_from_favorites(document.document_id)
            if success:
                ui.notify(f'Документ "{document.label}" удален из избранного', type='info')
                
                # Обновляем счетчик документов, если он передан
                if count_label:
                    try:
                        # Парсим текущее значение из текста label
                        label_text = count_label.text
                        import re
                        match = re.search(r'Избранные документы\s*\((\d+)\)', label_text)
                        if match:
                            current_count = int(match.group(1))
                            new_count = max(0, current_count - 1)
                            count_label.text = f'Избранные документы ({new_count})'
                            logger.info(f'Обновлен счетчик избранных документов: {new_count}')
                    except Exception as e:
                        logger.warning(f'Не удалось обновить счетчик: {e}')
                
                # Удаляем карточку из UI
                try:
                    card.delete()
                    logger.info(f'Карточка документа {document.document_id} удалена из списка избранных')
                except Exception as e:
                    logger.warning(f'Не удалось удалить карточку из UI: {e}')
                    # Fallback: обновляем весь список
                    await load_favorite_documents()
            else:
                ui.notify('Ошибка при удалении из избранного', type='error')
        else:
            # На других страницах проверяем статус и переключаем
            is_favorite = await client.is_document_in_favorites(document.document_id)
            
            if is_favorite:
                # Удаляем из избранного
                success = await client.remove_document_from_favorites(document.document_id)
                if success:
                    ui.notify(f'Документ "{document.label}" удален из избранного', type='info')
                    # Обновляем кнопку
                    button.props('icon=star_border')
                    button.text = 'В избранное'
                else:
                    ui.notify('Ошибка при удалении из избранного', type='error')
            else:
                # Добавляем в избранное
                success = await client.add_document_to_favorites(document.document_id)
                if success:
                    ui.notify(f'Документ "{document.label}" добавлен в избранное', type='positive')
                    # Обновляем кнопку
                    button.props('icon=star')
                    button.text = 'В избранном'
                else:
                    ui.notify('Ошибка при добавлении в избранное', type='error')
    except Exception as e:
        logger.error(f'Ошибка при работе с избранным: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')

async def check_favorite_status(document: MayanDocument) -> bool:
    """Проверяет, находится ли документ в избранном"""
    try:
        client = await get_mayan_client()
        return await client.is_document_in_favorites(document.document_id)
    except Exception as e:
        logger.warning(f'Ошибка при проверке статуса избранного для документа {document.document_id}: {e}')
        return False


async def load_favorite_documents():
    """Загружает избранные документы"""
    global _favorites_container
    
    if not _favorites_container:
        return
    
    # Проверяем подключение
    if not await check_connection():
        with _favorites_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        logger.info("Загружаем избранные документы...")
        client = await get_mayan_client()
        documents, total_count = await client.get_favorite_documents(page=1, page_size=100)
        logger.info(f"Получено избранных документов: {len(documents)} из {total_count}")
        
        _favorites_container.clear()
        
        if not documents:
            with _favorites_container:
                ui.label('У вас нет избранных документов').classes('text-gray-500 text-center py-8')
            return
        
        with _favorites_container:
            # Создаем label для счетчика документов
            count_label = ui.label(f'Избранные документы ({total_count})').classes('text-lg font-semibold mb-4')
            
            for document in documents:
                # Передаем флаг, что это страница избранных, и счетчик
                create_document_card(document, is_favorites_page=True, favorites_count_label=count_label)
    except Exception as e:
        logger.error(f"Ошибка при загрузке избранных документов: {e}", exc_info=True)
        _favorites_container.clear()
        with _favorites_container:
            ui.label(f'Ошибка при загрузке избранных документов: {str(e)}').classes('text-red-500 text-center py-8')

# Добавить функцию favorites_content (после функции upload_content, после строки 1880):

def favorites_content() -> None:
    """Страница избранных документов"""
    global _favorites_container
    
    logger.info("Открыта страница избранных документов")
    
    # Секция с избранными документами
    with ui.row().classes('w-full mb-4'):
        ui.label('Избранные документы').classes('text-lg font-semibold')
        ui.button('Обновить', icon='refresh', on_click=load_favorite_documents).classes('ml-auto text-xs px-2 py-1 h-7')
    
    _favorites_container = ui.column().classes('w-full')
    # Загружаем избранные документы только после создания контейнера
    ui.timer(0.1, load_favorite_documents, once=True)