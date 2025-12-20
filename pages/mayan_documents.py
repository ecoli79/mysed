from nicegui import ui
from services.mayan_connector import MayanClient, MayanDocument, MayanTokenExpiredError
from services.access_types import AccessTypeManager, AccessType
from services.document_access_manager import document_access_manager
from auth.middleware import get_current_user
from config.settings import config
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Protocol
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager
from collections import defaultdict
import io
import mimetypes
import requests
import json
import tempfile
import os
import base64
import atexit
from components.loading_indicator import LoadingIndicator, with_loading
import asyncio
from auth.ldap_auth import LDAPAuthenticator
from auth.session_manager import session_manager
from auth.token_storage import token_storage
from components.document_viewer import show_document_viewer
from services.signature_manager import SignatureManager
import traceback
import re
import html
from app_logging.logger import get_logger

logger = get_logger(__name__)

# Класс для управления состоянием модуля (замена глобальных переменных)
@dataclass
class MayanDocumentsState:
    """Состояние модуля работы с документами Mayan EDMS"""
    recent_documents_container: Optional[ui.column] = None
    search_results_container: Optional[ui.column] = None
    upload_form_container: Optional[ui.column] = None
    favorites_container: Optional[ui.column] = None
    mayan_client: Optional[MayanClient] = None
    mayan_client_cache: Optional[MayanClient] = None
    token_checked: bool = False
    connection_status: bool = False
    auth_error: Optional[str] = None
    current_user: Optional[Any] = None
    _token_check_lock: Optional[asyncio.Lock] = None
    _page_timers: Optional[List[Any]] = None
    
    def __post_init__(self):
        """Инициализация блокировки после создания объекта"""
        if self._token_check_lock is None:
            self._token_check_lock = asyncio.Lock()
        if self._page_timers is None:
            self._page_timers = []
    
    @property
    def token_check_lock(self) -> asyncio.Lock:
        """Получает блокировку для проверки токена"""
        return self._token_check_lock
    
    @property
    def page_timers(self) -> List[Any]:
        """Получает список таймеров страницы"""
        if self._page_timers is None:
            self._page_timers = []
        return self._page_timers
    
    def reset_cache(self):
        """Сбрасывает кэш клиента"""
        self.mayan_client_cache = None
        self.token_checked = False
    
    def cleanup_timers(self):
        """Очищает все таймеры страницы"""
        if self._page_timers:
            for timer in self._page_timers:
                try:
                    if hasattr(timer, 'deactivate'):
                        timer.deactivate()
                    elif hasattr(timer, 'cancel'):
                        timer.cancel()
                except Exception as e:
                    logger.debug(f'Ошибка при отмене таймера страницы: {e}')
            self._page_timers.clear()
    
    def reset_all(self):
        """Сбрасывает все состояние"""
        self.cleanup_timers()
        self.recent_documents_container = None
        self.search_results_container = None
        self.upload_form_container = None
        self.favorites_container = None
        self.mayan_client = None
        self.reset_cache()
        self.connection_status = False
        self.auth_error = None
        self.current_user = None

# Глобальный экземпляр состояния
_state = MayanDocumentsState()

# Обратная совместимость: функции для доступа к состоянию
# В будущем рекомендуется использовать _state напрямую
def get_state() -> MayanDocumentsState:
    """Получает глобальный экземпляр состояния"""
    return _state

# Глобальная переменная для обратной совместимости с theme.py
# Используется в theme.py для сброса при logout
_current_user = None  # Используется через _state.current_user

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

# Утилиты для безопасной работы с файлами
import threading
_temp_files: set[str] = set()
_temp_files_lock = asyncio.Lock()
_temp_files_sync_lock = threading.Lock()  # Для синхронного доступа из таймеров

def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от опасных символов и предотвращает path traversal"""
    if not filename:
        return 'file'
    
    # Убираем путь, оставляем только имя файла
    safe_name = Path(filename).name
    
    # Убираем опасные символы
    safe_name = re.sub(r'[<>:"|?*\x00-\x1f]', '', safe_name)
    
    # Убираем ведущие точки и пробелы
    safe_name = safe_name.lstrip('. ')
    
    # Если имя пустое после очистки, используем дефолтное
    if not safe_name:
        safe_name = 'file'
    
    # Ограничиваем длину (максимум 255 символов для большинства файловых систем)
    if len(safe_name) > 255:
        # Сохраняем расширение если есть
        name_part, ext = os.path.splitext(safe_name)
        max_name_len = 255 - len(ext)
        safe_name = name_part[:max_name_len] + ext
    
    return safe_name

def cleanup_temp_files():
    """Очищает все отслеживаемые временные файлы при выходе из приложения"""
    with _temp_files_sync_lock:
        files_to_clean = list(_temp_files)
    for temp_path in files_to_clean:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.debug(f"Удален временный файл при выходе: {temp_path}")
        except OSError as e:
            logger.warning(f"Не удалось удалить временный файл при выходе {temp_path}: {e}")
    with _temp_files_sync_lock:
        _temp_files.clear()

# Регистрируем функцию очистки при выходе
atexit.register(cleanup_temp_files)

# Rate Limiting механизм
_rate_limits: Dict[str, List[datetime]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()

def create_page_timer(delay: float, callback, once: bool = True):
    """
    Создает таймер на уровне страницы с отслеживанием.
    Поддерживает как синхронные, так и асинхронные callback'и.
    
    Args:
        delay: Задержка в секундах
        callback: Функция обратного вызова (может быть async или возвращать корутину)
        once: Если True, таймер выполнится один раз
    
    Returns:
        Объект таймера
    """
    state = get_state()
    
    def safe_callback():
        """Безопасный callback с обработкой ошибок и поддержкой async функций"""
        try:
            # Вызываем callback и проверяем результат
            result = callback()
            
            # Если результат - корутина (async функция или lambda, возвращающая корутину), создаем задачу
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
            # Если callback сам является async функцией (но не был вызван), создаем задачу
            elif asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback())
        except Exception as e:
            # Логируем ошибки выполнения callback, но не блокируем выполнение
            # Это может быть нормально, если клиент отключился во время выполнения
            logger.debug(f'Ошибка при выполнении callback таймера: {e}')
    
    timer = ui.timer(delay, safe_callback, once=once)
    state.page_timers.append(timer)
    return timer

async def check_rate_limit(user_id: str, action: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    """
    Проверяет rate limit для действия пользователя
    
    Args:
        user_id: Идентификатор пользователя
        action: Тип действия ('search', 'load', 'upload', 'delete', etc.)
        max_requests: Максимальное количество запросов в окне времени
        window_seconds: Размер окна времени в секундах
    
    Returns:
        True если запрос разрешен, False если превышен лимит
    """
    async with _rate_limit_lock:
        now = datetime.now()
        key = f"{user_id}:{action}"
        
        # Удаляем старые записи (старше window_seconds)
        _rate_limits[key] = [
            timestamp for timestamp in _rate_limits[key]
            if now - timestamp < timedelta(seconds=window_seconds)
        ]
        
        # Проверяем лимит
        if len(_rate_limits[key]) >= max_requests:
            logger.warning(f'Rate limit превышен для пользователя {user_id}, действие {action}: {len(_rate_limits[key])}/{max_requests} запросов за {window_seconds} секунд')
            return False
        
        # Добавляем текущий запрос
        _rate_limits[key].append(now)
        logger.debug(f'Rate limit проверка для {user_id}:{action}: {len(_rate_limits[key])}/{max_requests} запросов')
        return True

def get_rate_limit_status(user_id: str, action: str, window_seconds: int = 60) -> Dict[str, Any]:
    """
    Получает текущий статус rate limit для пользователя и действия
    
    Returns:
        Словарь с информацией о текущем статусе лимита
    """
    key = f"{user_id}:{action}"
    now = datetime.now()
    
    # Очищаем старые записи
    recent_requests = [
        timestamp for timestamp in _rate_limits.get(key, [])
        if now - timestamp < timedelta(seconds=window_seconds)
    ]
    
    return {
        'current_requests': len(recent_requests),
        'window_seconds': window_seconds,
        'oldest_request': recent_requests[0] if recent_requests else None,
        'newest_request': recent_requests[-1] if recent_requests else None
    }

# Кэширование метаданных
_metadata_cache: Dict[str, tuple[Any, datetime]] = {}
_metadata_cache_lock = asyncio.Lock()
_metadata_cache_ttl = timedelta(minutes=5)  # TTL для кэша метаданных

async def get_cached_document_types(client: MayanClient) -> List[Dict[str, Any]]:
    """
    Получает типы документов с кэшированием
    
    Args:
        client: Клиент Mayan EDMS
    
    Returns:
        Список типов документов
    """
    cache_key = 'document_types'
    now = datetime.now()
    
    async with _metadata_cache_lock:
        # Проверяем кэш
        if cache_key in _metadata_cache:
            data, timestamp = _metadata_cache[cache_key]
            if now - timestamp < _metadata_cache_ttl:
                logger.debug(f'Использован кэш для типов документов (возраст: {(now - timestamp).total_seconds():.1f}с)')
                return data
        
        # Загружаем данные
        logger.debug('Загрузка типов документов из API (кэш пуст или истек)')
        data = await client.get_document_types()
        _metadata_cache[cache_key] = (data, now)
        return data

async def get_cached_cabinets(client: MayanClient) -> List[Dict[str, Any]]:
    """
    Получает кабинеты с кэшированием
    
    Args:
        client: Клиент Mayan EDMS
    
    Returns:
        Список кабинетов
    """
    cache_key = 'cabinets'
    now = datetime.now()
    
    async with _metadata_cache_lock:
        # Проверяем кэш
        if cache_key in _metadata_cache:
            data, timestamp = _metadata_cache[cache_key]
            if now - timestamp < _metadata_cache_ttl:
                logger.debug(f'Использован кэш для кабинетов (возраст: {(now - timestamp).total_seconds():.1f}с)')
                return data
        
        # Загружаем данные
        logger.debug('Загрузка кабинетов из API (кэш пуст или истек)')
        data = await client.get_cabinets()
        _metadata_cache[cache_key] = (data, now)
        return data

async def get_cached_tags(client: MayanClient) -> List[Dict[str, Any]]:
    """
    Получает теги с кэшированием
    
    Args:
        client: Клиент Mayan EDMS
    
    Returns:
        Список тегов
    """
    cache_key = 'tags'
    now = datetime.now()
    
    async with _metadata_cache_lock:
        # Проверяем кэш
        if cache_key in _metadata_cache:
            data, timestamp = _metadata_cache[cache_key]
            if now - timestamp < _metadata_cache_ttl:
                logger.debug(f'Использован кэш для тегов (возраст: {(now - timestamp).total_seconds():.1f}с)')
                return data
        
        # Загружаем данные
        logger.debug('Загрузка тегов из API (кэш пуст или истек)')
        data = await client.get_tags()
        _metadata_cache[cache_key] = (data, now)
        return data

async def load_previews_batch(document_ids: List[int], client: Optional[MayanClient] = None) -> Dict[int, bytes]:
    """
    Загружает превью для нескольких документов параллельно (оптимизация N+1 проблемы)
    
    Args:
        document_ids: Список ID документов для загрузки превью
        client: Опциональный клиент Mayan (если не передан, будет создан новый)
    
    Returns:
        Словарь {document_id: image_data} с загруженными превью
    """
    if not document_ids:
        return {}
    
    if client is None:
        client = await get_mayan_client()
    
    previews: Dict[int, bytes] = {}
    
    # Создаем задачи для параллельной загрузки всех превью
    async def load_single_preview(doc_id: int) -> tuple[int, Optional[bytes]]:
        """Загружает превью для одного документа"""
        try:
            image_data = await client.get_document_preview_image(doc_id)
            return (doc_id, image_data)
        except MayanTokenExpiredError:
            # Токен истек, обновляем клиент и повторяем
            logger.warning(f'Токен истек при загрузке превью для документа {doc_id}, обновляем...')
            state = get_state()
            state.reset_cache()
            client = await get_mayan_client()
            try:
                image_data = await client.get_document_preview_image(doc_id)
                return (doc_id, image_data)
            except Exception as e:
                logger.warning(f"Ошибка загрузки превью для {doc_id} после обновления токена: {e}")
                return (doc_id, None)
        except Exception as e:
            logger.warning(f"Ошибка загрузки превью для {doc_id}: {e}")
            return (doc_id, None)
    
    # Загружаем все превью параллельно
    logger.info(f'Начинаем батч-загрузку превью для {len(document_ids)} документов')
    tasks = [load_single_preview(doc_id) for doc_id in document_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Обрабатываем результаты
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Исключение при загрузке превью: {result}")
        elif isinstance(result, tuple) and len(result) == 2:
            doc_id, image_data = result
            if image_data:
                previews[doc_id] = image_data
    
    logger.info(f'Батч-загрузка превью завершена: загружено {len(previews)}/{len(document_ids)} превью')
    return previews

async def safe_download_file(content: bytes, filename: str, delay_seconds: float = 5.0):
    """Безопасно создает временный файл для скачивания с гарантированным удалением"""
    safe_filename = sanitize_filename(filename)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{safe_filename}") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Регистрируем файл для отслеживания
        async with _temp_files_lock:
            _temp_files.add(temp_path)
        
        # Открываем файл для скачивания
        ui.download(temp_path, safe_filename)
        
        # Удаляем временный файл через заданное время
        def cleanup():
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    with _temp_files_sync_lock:
                        _temp_files.discard(temp_path)
                except OSError as e:
                    logger.warning(f"Не удалось удалить временный файл {temp_path}: {e}")
        
        ui.timer(delay_seconds, cleanup, once=True)
        
        return temp_path
    except Exception as e:
        # В случае ошибки пытаемся удалить файл
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                async with _temp_files_lock:
                    _temp_files.discard(temp_path)
            except OSError:
                pass
        raise

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
        except TimeoutError as e:
            logger.error(f"Таймаут при загрузке документа: {e}", exc_info=True)
            self._notify_error("Превышено время ожидания при загрузке документа. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке документа: {e}", exc_info=True)
            # Не показываем детали ошибки пользователю для безопасности
            self._notify_error("Произошла ошибка при загрузке документа. Обратитесь к администратору.")
    
    def _validate_params(self, params: UploadParams) -> None:
        """Валидирует параметры"""
        if not params.label.strip():
            raise ValidationError("Название документа не может быть пустым")
        
        if len(params.label) > 255:
            raise ValidationError("Название документа слишком длинное")
    
    def _process_file(self, upload_event) -> FileInfo:
        """Обрабатывает загруженный файл с проверкой размера при чтении"""
        try:
            filename = upload_event.name
            mimetype = upload_event.type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            
            # Читаем файл порциями с проверкой размера для предотвращения DoS
            file_content = b''
            max_size = FileSize.MAX_SIZE.value
            chunk_size = 1024 * 1024  # 1MB порции для эффективности
            
            while True:
                chunk = upload_event.content.read(chunk_size)
                if not chunk:
                    break
                
                # Проверяем размер перед добавлением, чтобы избежать переполнения памяти
                if len(file_content) + len(chunk) > max_size:
                    raise ValidationError(f"Файл превышает максимальный размер: {max_size} байт ({FileSize.MAX_SIZE.value / (1024 * 1024):.0f}MB)")
                
                file_content += chunk
            
            file_info = FileInfo(
                name=filename,
                content=file_content,
                mimetype=mimetype,
                size=len(file_content)
            )
            
            # Дополнительная валидация через FileValidator
            FileValidator.validate_file(file_info)
            return file_info
            
        except ValidationError:
            # Пробрасываем ValidationError как есть
            raise
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
        # Безопасное логирование без чувствительных данных
        logger.debug(f"SimpleFormDataExtractor: cabinet_id {'указан' if cabinet_id else 'не указан'}, cabinet_name {'указан' if params.cabinet_name else 'не указан'}")
        if not cabinet_id and params.cabinet_name:
            logger.debug(f"SimpleFormDataExtractor: Ищем кабинет по имени")
            cabinet_id = await self._get_cabinet_id_by_name(client, params.cabinet_name)
            logger.debug(f"SimpleFormDataExtractor: Кабинет {'найден' if cabinet_id else 'не найден'}")
        elif not cabinet_id:
            logger.warning(f"SimpleFormDataExtractor: cabinet_id не найден и cabinet_name не указан")
        
        logger.debug(f"SimpleFormDataExtractor: Итоговый cabinet_id {'получен' if cabinet_id else 'не получен'}")
        
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
        
        document_types = await get_cached_document_types(client)
        for dt in document_types:
            if dt['label'] == type_name:
                return dt['id']
        
        raise ValidationError(f"Не удалось найти тип документа: {type_name}")
    
    async def _get_cabinet_id_by_name(self, client: MayanClient, cabinet_name: Optional[str]) -> Optional[int]:
        """Получает ID кабинета по названию"""
        if not cabinet_name:
            return None
        
        cabinets = await get_cached_cabinets(client)
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
            tags = await get_cached_tags(client)
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

def _extract_token_from_client(client: MayanClient) -> Optional[str]:
    """Извлекает API токен из заголовков клиента"""
    if not client or not hasattr(client, 'client'):
        return None
    
    if 'Authorization' in client.client.headers:
        auth_header = client.client.headers['Authorization']
        if auth_header.startswith('Token '):
            return auth_header[6:]
    
    return None

async def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя
    
    Использует блокировку для предотвращения race conditions при параллельных вызовах.
    Вся логика проверки кэша и создания клиента выполняется внутри блокировки.
    """
    state = get_state()
    
    # Получаем текущего пользователя из контекста
    current_user = state.current_user if state.current_user else get_current_user()
    
    if not current_user:
        raise ValueError('Пользователь не авторизован')
    
    # Проверяем наличие токена (до блокировки, чтобы не блокировать на простых проверках)
    if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
        raise MayanTokenExpiredError(f'У пользователя {current_user.username} нет API токена для доступа к Mayan EDMS')
    
    try:
        # ВСЯ логика проверки кэша и создания клиента выполняется внутри блокировки
        # для предотвращения race conditions при параллельных вызовах
        async with state.token_check_lock:
            try:
                # Проверяем кэш внутри блокировки (double-checked locking pattern)
                if state.mayan_client_cache and state.token_checked:
                    cached_token = _extract_token_from_client(state.mayan_client_cache)
                    
                    # Если токен совпадает, возвращаем кэшированный клиент
                    if cached_token == current_user.mayan_api_token:
                        return state.mayan_client_cache
                
                # Создаем новый клиент
                client = MayanClient(
                    base_url=config.mayan_url,
                    api_token=current_user.mayan_api_token
                )
                
                # Проверяем действительность токена только если еще не проверяли
                if not state.token_checked:
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
                    
                    state.token_checked = True
                
                # Кэшируем клиент внутри блокировки
                state.mayan_client_cache = client
                return client
                
            except MayanTokenExpiredError:
                # Сбрасываем кэш при ошибке токена
                state.reset_cache()
                
                logger.warning('Обнаружен истекший токен, запрашиваем повторную авторизацию')
                
                # Показываем диалог повторной авторизации
                new_token = await show_mayan_reauth_dialog()
                
                if new_token:
                    # Обновляем токен пользователя
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
                    state.mayan_client_cache = client
                    state.token_checked = True
                    logger.info('Клиент Mayan EDMS обновлен с новым токеном')
                    return client
                else:
                    raise ValueError('Повторная авторизация не удалась или была отменена')
            except Exception as e:
                logger.error(f'Ошибка при создании клиента Mayan EDMS: {e}', exc_info=True)
                # Сбрасываем кэш при ошибке (внутри блокировки)
                state.reset_cache()
                raise
    
    # Обработка MayanTokenExpiredError, выброшенного до входа в блокировку (строка 376)
    # Используем блокировку для безопасного обновления кэша
    except MayanTokenExpiredError:
        state = get_state()
        async with state.token_check_lock:
            # Сбрасываем кэш при ошибке токена (внутри блокировки)
            state.reset_cache()
            
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
                state.mayan_client_cache = client
                state.token_checked = True
                logger.info('Клиент Mayan EDMS обновлен с новым токеном')
                return client
            else:
                raise ValueError('Повторная авторизация не удалась или была отменена')

async def check_connection() -> bool:
    """Проверяет подключение к Mayan EDMS"""
    state = get_state()
    
    try:
        client = await get_mayan_client()
        connection_status = await client.test_connection()
        state.connection_status = connection_status
        state.auth_error = None
        return connection_status
    except Exception as e:
        logger.error(f"Ошибка при проверке подключения: {e}")
        state.connection_status = False
        state.auth_error = str(e)
        return False

async def with_timeout(coro, timeout: float = 30.0, operation_name: str = "операция"):
    """Выполняет асинхронную операцию с таймаутом
    
    Args:
        coro: Асинхронная корутина для выполнения
        timeout: Таймаут в секундах (по умолчанию 30)
        operation_name: Название операции для сообщений об ошибках
    
    Returns:
        Результат выполнения корутины
    
    Raises:
        TimeoutError: Если операция превысила таймаут
        Exception: Другие исключения из корутины
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Таймаут при выполнении {operation_name} (>{timeout}с)")
        raise TimeoutError(f"{operation_name.capitalize()} превысила лимит времени ({timeout}с)")

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

def update_preview_in_card(preview_html: ui.html, preview_data_uri: dict, image_data: bytes):
    """
    Обновляет превью в карточке документа с уже загруженными данными
    
    Args:
        preview_html: HTML элемент для отображения превью
        preview_data_uri: Словарь для хранения data_uri
        image_data: Байты изображения
    """
    try:
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
        
        # Безопасное создание HTML с экранированием
        safe_document_id = html.escape(str(preview_html.id if hasattr(preview_html, 'id') else ''))
        safe_alt_text = html.escape(f"Превью документа")
        if not data_uri.startswith('data:'):
            logger.warning(f'Небезопасный data URI для превью')
            data_uri = ''
        
        html_content = f'''
            <div id="preview_clickable_{safe_document_id}"
                 style="cursor: pointer; transition: opacity 0.2s;"
                 onmouseover="this.style.opacity='0.8'"
                 onmouseout="this.style.opacity='1'"
                 title="Нажмите для просмотра всех страниц документа">
                <img src="{data_uri}"
                     class="w-32 h-32 object-contain bg-gray-100 rounded border"
                     alt="{safe_alt_text}"
                     style="display: block; pointer-events: none;" />
            </div>
        '''
        
        preview_html.content = html_content
        preview_html.update()
    except Exception as e:
        logger.error(f'Ошибка обновления превью: {e}', exc_info=True)
        preview_html.content = '<div class="w-32 h-32 flex items-center justify-center text-xs text-red-400 bg-gray-100 rounded border">Ошибка загрузки</div>'
        preview_html.update()

def create_document_card(document: MayanDocument, update_cabinet_title_func=None, current_count=None, documents_count_label=None, is_favorites_page: bool = False, favorites_count_label: Optional[ui.label] = None, preview_image_data: Optional[bytes] = None) -> ui.card:
    """
    Создает карточку документа с возможностью предоставления доступа
    
    Args:
        document: Документ для отображения
        update_cabinet_title_func: Функция для обновления заголовка кабинета
        current_count: Текущий счетчик документов
        documents_count_label: Label для отображения счетчика
        is_favorites_page: Флаг, что это страница избранного
        favorites_count_label: Label для счетчика избранного
        preview_image_data: Опциональные данные превью (если уже загружены батчем)
    """
    
    # Временное логирование для отладки
    logger.info(f"Создаем карточку для документа {document.document_id}:")
    logger.info(f"- Название: {document.label}")
    logger.info(f"- Файл: {document.file_latest_filename}")
    logger.info(f"- Размер файла: {document.file_latest_size}")
    logger.info(f"- MIME-тип: {document.file_latest_mimetype}")
    
    with ui.card().classes('w-full mb-4') as card:
        # Инициализируем список таймеров для предотвращения утечки памяти
        card.timers: List[Any] = []
        
        def add_timer(delay: float, callback, once: bool = True):
            """Создает таймер и сохраняет ссылку на него в карточке"""
            timer = ui.timer(delay, callback, once=once)
            card.timers.append(timer)
            return timer
        
        def cleanup_timers():
            """Отменяет все таймеры карточки для предотвращения утечки памяти"""
            for timer in card.timers:
                try:
                    if hasattr(timer, 'deactivate'):
                        timer.deactivate()
                    elif hasattr(timer, 'cancel'):
                        timer.cancel()
                except Exception as e:
                    logger.debug(f'Ошибка при отмене таймера: {e}')
            card.timers.clear()
        
        # Сохраняем функцию cleanup в карточке для вызова при удалении
        card.cleanup = cleanup_timers
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
                                preview_state = get_state()
                                preview_state.reset_cache()
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
                                
                                # Безопасное экранирование данных для HTML
                                safe_document_id = html.escape(str(document.document_id))
                                safe_alt_text = html.escape(f"Превью документа {document.document_id}")
                                # data_uri уже безопасен (base64), но для надежности проверяем, что это data URI
                                if not data_uri.startswith('data:'):
                                    logger.warning(f'Небезопасный data URI для документа {document.document_id}')
                                    data_uri = ''
                                
                                # Создаем кликабельное превью с курсором pointer
                                html_content = f'''
                                    <div id="preview_clickable_{safe_document_id}" 
                                         style="cursor: pointer; transition: opacity 0.2s;" 
                                         onmouseover="this.style.opacity='0.8'" 
                                         onmouseout="this.style.opacity='1'"
                                         title="Нажмите для просмотра всех страниц документа">
                                        <img src="{data_uri}" 
                                             class="w-32 h-32 object-contain bg-gray-100 rounded border" 
                                             alt="{safe_alt_text}" 
                                             style="display: block; pointer-events: none;" />
                                    </div>
                                '''
                                
                                preview_html.content = html_content
                                preview_html.update()
                                
                                # Добавляем обработчик клика через NiceGUI
                                # NiceGUI поддерживает async функции напрямую в обработчиках
                                # Регистрируем обработчик клика через NiceGUI
                                # Используем add_timer для регистрации обработчика после обновления DOM (с сохранением ссылки)
                                add_timer(0.1, lambda: preview_html.on('click', show_full_preview), once=True)
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
                
                # Если превью уже загружено батчем, используем его сразу
                if preview_image_data:
                    update_preview_in_card(preview_html, preview_data_uri, preview_image_data)
                    # Добавляем обработчик клика (с сохранением ссылки на таймер)
                    add_timer(0.1, lambda: preview_html.on('click', show_full_preview), once=True)
                # Иначе загружаем превью асинхронно (старый механизм для обратной совместимости)
                elif document.file_latest_id:
                    add_timer(0.1, load_preview, once=True)
            
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
                            add_timer(0.1, lambda: update_file_size(document, pages_label), once=True)
                
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
                
                # Кнопки быстрого запуска процессов
                current_user = get_current_user()
                if current_user:
                    ui.button('Запустить процесс ознакомления', icon='verified', color='blue').classes('text-xs px-2 py-1 h-7').on_click(
                        lambda doc=document: ui.navigate.to(f'/task-assignment?document_id={doc.document_id}&process_type=signing')
                    )
                    
                    ui.button('Подписание', icon='edit', color='green').classes('text-xs px-2 py-1 h-7').on_click(
                        lambda doc=document: ui.navigate.to(f'/task-assignment?document_id={doc.document_id}&process_type=signing')
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
                        
                        # Запускаем проверку статуса (с сохранением ссылки на таймер)
                        add_timer(0.1, check_and_show_favorite_button, once=True)
                                        
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
        
        # Запускаем проверку подписей асинхронно (с сохранением ссылки на таймер)
        if document.file_latest_id:
            add_timer(0.1, check_and_add_signature_button, once=True)
    
    return card


async def search_documents(query: str):
    """Выполняет поиск документов"""
    state = get_state()
    
    # Проверяем rate limit для поиска
    current_user = get_current_user()
    if current_user:
        user_id = current_user.username
    else:
        user_id = 'anonymous'
    
    if not await check_rate_limit(user_id, 'search', max_requests=15, window_seconds=60):
        if state.search_results_container:
            state.search_results_container.clear()
            with state.search_results_container:
                ui.label('Превышен лимит запросов поиска. Пожалуйста, подождите немного и попробуйте снова.').classes('text-orange-500 text-center py-8')
                status = get_rate_limit_status(user_id, 'search', window_seconds=60)
                if status['current_requests'] > 0:
                    ui.label(f'Использовано запросов: {status["current_requests"]}/15 за последнюю минуту').classes('text-sm text-gray-500 text-center')
        return
    
    if not query.strip():
        if state.search_results_container:
            state.search_results_container.clear()
            with state.search_results_container:
                ui.label('Введите поисковый запрос').classes('text-gray-500 text-center py-8')
        return
    
    # Проверяем подключение
    if not await check_connection():
        if state.search_results_container:
            state.search_results_container.clear()
            with state.search_results_container:
                ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
                if state.auth_error:
                    ui.label(f'Ошибка: {state.auth_error}').classes('text-sm text-gray-500 text-center')
                ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    # Очищаем контейнер и показываем индикатор сразу
    if state.search_results_container:
        state.search_results_container.clear()
        loading = LoadingIndicator(state.search_results_container, 'Поиск документов...')
        loading.show()
        
        async def perform_search():
            try:
                logger.info(f"Выполняем поиск по запросу: {query}")
                # Выполняем поиск с таймаутом
                client = await get_mayan_client()
                documents = await with_timeout(
                    client.search_documents(query, page=1, page_size=20),
                    timeout=30.0,
                    operation_name="поиск документов"
                )
                logger.info(f"Найдено документов: {len(documents)}")
                
                # Скрываем индикатор и очищаем контейнер перед показом результатов
                loading.hide()
                state.search_results_container.clear()
                
                if not documents:
                    with state.search_results_container:
                        ui.label(f'По запросу "{query}" ничего не найдено').classes('text-gray-500 text-center py-8')
                    return
                
                # Оптимизация N+1: загружаем все превью батчем перед созданием карточек
                document_ids = [doc.document_id for doc in documents if doc.file_latest_id]
                previews = {}
                if document_ids:
                    try:
                        previews = await load_previews_batch(document_ids, client)
                    except Exception as e:
                        logger.error(f"Ошибка при батч-загрузке превью: {e}", exc_info=True)
                        # Продолжаем работу без превью
                
                # Создаем карточки с уже загруженными превью
                with state.search_results_container:
                    ui.label(f'Найдено документов: {len(documents)}').classes('text-lg font-semibold mb-4')
                    for document in documents:
                        preview_data = previews.get(document.document_id)
                        create_document_card(document, preview_image_data=preview_data)
                        
            except TimeoutError as e:
                logger.error(f"Таймаут при поиске документов: {e}")
                loading.hide()
                state.search_results_container.clear()
                with state.search_results_container:
                    ui.label(f'Превышено время ожидания при поиске. Попробуйте позже.').classes('text-red-500 text-center py-8')
            except Exception as e:
                logger.error(f"Ошибка при поиске документов: {e}")
                loading.hide()
                state.search_results_container.clear()
                with state.search_results_container:
                    ui.label(f'Ошибка при поиске: {str(e)}').classes('text-red-500 text-center py-8')
        
        # Выполняем поиск с небольшой задержкой, чтобы UI успел обновиться и показать индикатор
        create_page_timer(0.05, lambda: perform_search(), once=True)

async def upload_document():
    """Загружает документ на сервер"""
    state = get_state()
    
    # Проверяем rate limit для загрузки
    current_user = get_current_user()
    if current_user:
        user_id = current_user.username
    else:
        user_id = 'anonymous'
    
    if not await check_rate_limit(user_id, 'upload', max_requests=10, window_seconds=60):
        if state.upload_form_container:
            state.upload_form_container.clear()
            with state.upload_form_container:
                ui.label('Превышен лимит загрузок. Пожалуйста, подождите немного и попробуйте снова.').classes('text-orange-500 text-center py-8')
                status = get_rate_limit_status(user_id, 'upload', window_seconds=60)
                if status['current_requests'] > 0:
                    ui.label(f'Использовано загрузок: {status["current_requests"]}/10 за последнюю минуту').classes('text-sm text-gray-500 text-center')
        return
    
    if state.upload_form_container:
        state.upload_form_container.clear()
    
    with state.upload_form_container:
        ui.label('Загрузка документа').classes('text-lg font-semibold mb-4')
        
        # Проверяем подключение
        if not await check_connection():
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if state.auth_error:
                ui.label(f'Ошибка: {state.auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
            return
        
        # Форма загрузки
        with ui.column().classes('w-full gap-4'):
            # Убираем поля названия документа и описания - будем брать из имени файла
            description_input = ui.textarea('Описание (опционально)', placeholder='Введите описание документа').classes('w-full')
            
            try:
                client = await get_mayan_client()
                
                # Получаем типы документов с кэшированием
                document_types = await with_timeout(
                    get_cached_document_types(client),
                    timeout=15.0,
                    operation_name="загрузка типов документов"
                )
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
                            
                # Получаем кабинеты с кэшированием
                cabinets = await with_timeout(
                    get_cached_cabinets(client),
                    timeout=15.0,
                    operation_name="загрузка кабинетов"
                )
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
                # Безопасное логирование - только количество, без содержимого
                logger.debug(f"Подготовка формы: cabinet_id_map содержит {len(local_cabinet_id_map)} кабинетов")
            
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
    state = get_state()
    
    if not state.upload_form_container:
        # Не можем использовать ui.notify в асинхронной задаче, логируем ошибку
        logger.error('Форма загрузки не инициализирована')
        return
    
    try:
        # Валидация выбора типа документа
        if not document_type_name:
            if state.upload_form_container:
                with state.upload_form_container:
                    error_label = ui.label('Пожалуйста, выберите тип документа').classes('text-red-500 p-4 bg-red-50 rounded')
            logger.warning("Попытка загрузки без выбранного типа документа")
            return
        
        # Валидация выбора кабинета
        if not cabinet_name or cabinet_name == 'Выберите кабинет':
            if state.upload_form_container:
                with state.upload_form_container:
                    error_label = ui.label('Пожалуйста, выберите кабинет для сохранения документа').classes('text-red-500 p-4 bg-red-50 rounded')
            logger.warning("Попытка загрузки без выбранного кабинета")
            return
        
        # Получаем имя файла без расширения для названия документа
        filename = upload_event.name
        # Убираем расширение файла для названия документа
        document_label = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        logger.debug(f"Имя файла: {filename}")
        logger.debug(f"Название документа (без расширения): {document_label}")
        # Безопасное логирование - не логируем чувствительные структуры данных
        logger.debug(f"Получены параметры: document_type_name={'указан' if document_type_name else 'не указан'}, cabinet_name={'указан' if cabinet_name else 'не указан'}, cabinet_id_map={'передан' if cabinet_id_map else 'не передан'}")
        
        # Получаем ID кабинета из карты, если она передана
        cabinet_id = None
        if cabinet_name and cabinet_id_map:
            logger.debug(f"Попытка найти кабинет в карте")
            logger.debug(f"Карта содержит {len(cabinet_id_map)} записей")
            cabinet_id = cabinet_id_map.get(cabinet_name)
            if cabinet_id:
                logger.debug(f"Кабинет найден в карте")
            else:
                logger.warning(f"Кабинет не найден в карте")
        else:
            if not cabinet_name:
                logger.warning("cabinet_name не передан или пустой")
            if not cabinet_id_map:
                logger.warning("cabinet_id_map не передан или пустой")
        
        logger.debug(f"Итоговый cabinet_id {'получен' if cabinet_id else 'не получен'}")
        
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
        
        logger.debug(f"Создан UploadParams с cabinet_id {'указан' if params.cabinet_id else 'не указан'}")
        
        # Получаем клиент
        client = await get_mayan_client()
        
        # Создаем загрузчик с упрощенным извлекателем
        uploader = DocumentUploader(client, SimpleFormDataExtractor())
        await uploader.upload_document(upload_event, params, state.upload_form_container)
        
    except TimeoutError as e:
        logger.error(f"Таймаут при загрузке документа: {e}", exc_info=True)
        try:
            if state.upload_form_container:
                with state.upload_form_container:
                    error_label = ui.label('Превышено время ожидания при загрузке. Попробуйте позже.').classes('text-red-500 p-4 bg-red-50 rounded')
        except Exception as ui_error:
            logger.error(f'Не удалось отобразить ошибку в UI: {ui_error}')
    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке документа: {e}", exc_info=True)
        # Используем контейнер для отображения ошибки вместо ui.notify
        try:
            if state.upload_form_container:
                with state.upload_form_container:
                    error_label = ui.label('Произошла ошибка при загрузке документа. Обратитесь к администратору.').classes('text-red-500 p-4 bg-red-50 rounded')
        except Exception as ui_error:
            # Если даже это не работает, просто логируем
            logger.error(f'Не удалось отобразить ошибку в UI: {ui_error}')


async def download_document_file(document: MayanDocument):
    """Скачивает файл документа через прокси"""
    # Проверяем rate limit для скачивания
    current_user = get_current_user()
    if current_user:
        user_id = current_user.username
    else:
        user_id = 'anonymous'
    
    if not await check_rate_limit(user_id, 'download', max_requests=30, window_seconds=60):
        ui.notify('Превышен лимит скачиваний. Пожалуйста, подождите немного и попробуйте снова.', type='warning')
        return
    
    try:
        client = await get_mayan_client()
        
        # Получаем содержимое файла с таймаутом
        try:
            file_content = await with_timeout(
                client.get_document_file_content(document.document_id),
                timeout=60.0,  # Больший таймаут для больших файлов
                operation_name=f"скачивание файла документа {document.document_id}"
            )
        except TimeoutError as e:
            ui.notify(f'Превышено время ожидания при скачивании файла: {str(e)}', type='error')
            return
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            ui.notify('Не удалось получить содержимое файла', type='error')
            return
        
        if not file_content:
            ui.notify('Не удалось получить содержимое файла', type='error')
            return
        
        # Создаем временный файл для скачивания
        filename = document.file_latest_filename or f"document_{document.document_id}"
        
        # Безопасное создание и скачивание файла с гарантированным удалением
        await safe_download_file(file_content, filename, delay_seconds=5.0)
        
        ui.notify(f'Файл "{filename}" подготовлен для скачивания', type='positive')
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        ui.notify(f'Ошибка при скачивании: {str(e)}', type='error')

def content() -> None:
    """Основная страница работы с документами Mayan EDMS - кабинеты с документами"""
    state = get_state()
    
    # Сохраняем пользователя в состоянии для использования в асинхронных функциях
    # Это важно, так как таймеры могут выполняться без UI контекста
    current_user = get_current_user()
    if current_user:
        state.current_user = current_user
    
    # Очищаем старые таймеры при открытии страницы
    state.cleanup_timers()
    
    logger.info("Открыта страница работы с документами Mayan EDMS")
    
    # Секция с документами
    with ui.row().classes('w-full mb-4'):
        ui.label('Документы по кабинетам').classes('text-lg font-semibold')
        ui.button('Обновить', icon='refresh', on_click=load_documents_by_cabinets).classes('ml-auto text-xs px-2 py-1 h-7')
    
    state.recent_documents_container = ui.column().classes('w-full')
    # Загружаем документы только после создания контейнера
    create_page_timer(0.1, load_documents_by_cabinets, once=True)

async def load_documents_by_cabinets():
    """Загружает документы, сгруппированные по кабинетам"""
    state = get_state()
    
    if state.recent_documents_container:
        state.recent_documents_container.clear()
    
    # Проверяем подключение
    if not await check_connection():
        with state.recent_documents_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if state.auth_error:
                ui.label(f'Ошибка: {state.auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        client = await get_mayan_client()
        
        # Получаем список кабинетов с таймаутом
        logger.info("Загружаем список кабинетов...")
        cabinets = await with_timeout(
            get_cached_cabinets(client),
            timeout=30.0,
            operation_name="загрузка кабинетов"
        )
        logger.info(f"Получено кабинетов: {len(cabinets)}")
        
        if not cabinets:
            with state.recent_documents_container:
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
                        # Безопасное обновление заголовка expansion через props
                        # NiceGUI обычно экранирует значения в props, но для надежности используем json.dumps
                        safe_title = json.dumps(new_title)
                        expansion.props(f'label={safe_title}')
                        expansion.update()
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении заголовка кабинета {cabinet_id}: {e}")
                        # Альтернативный способ - через JavaScript с безопасной вставкой данных
                        try:
                            # Безопасная вставка данных через json.dumps для предотвращения XSS
                            safe_expansion_id = json.dumps(str(expansion.id))
                            safe_new_title = json.dumps(new_title)
                            
                            ui.run_javascript(f'''
                                (function() {{
                                    const element = document.querySelector('[data-id=' + {safe_expansion_id} + ']');
                                    if (element) {{
                                        const header = element.querySelector('.q-expansion-item__header');
                                        if (header) {{
                                            const label = header.querySelector('.q-expansion-item__header-content');
                                            if (label) {{
                                                label.textContent = {safe_new_title};
                                            }}
                                        }}
                                    }}
                                }})();
                            ''')
                        except Exception as js_error:
                            logger.warning(f"Ошибка при выполнении JavaScript для обновления заголовка: {js_error}")
                            pass
                
                # Асинхронно загружаем количество документов
                async def load_documents_count():
                    """Загружает количество документов в кабинете"""
                    try:
                        count = await with_timeout(
                            client.get_cabinet_documents_count(cabinet_id),
                            timeout=15.0,
                            operation_name=f"подсчет документов кабинета {cabinet_id}"
                        )
                        update_cabinet_title(count)
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке количества документов кабинета {cabinet_id}: {e}")
                        # В случае ошибки показываем заголовок без количества
                        update_cabinet_title(0)
                
                # Загружаем количество документов с небольшой задержкой, чтобы не блокировать UI
                create_page_timer(0.1, load_documents_count, once=True)
                
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
                                
                                # Получаем документы кабинета с таймаутом
                                logger.info(f"Загружаем документы кабинета {cabinet_id} ({cabinet_label}): страница {page}, размер {size}...")
                                documents, total_count = await with_timeout(
                                    client.get_cabinet_documents(cabinet_id, page=page, page_size=size),
                                    timeout=30.0,
                                    operation_name=f"загрузка документов кабинета {cabinet_id}"
                                )
                                logger.info(f"Получено документов для кабинета {cabinet_id}: {len(documents)} из {total_count}")
                                
                                current_page = page
                                page_size = size
                                
                                # Обновляем контейнер документов
                                if documents_container:
                                    documents_container.clear()
                                    
                                    if documents:
                                        # Оптимизация N+1: загружаем все превью батчем перед созданием карточек
                                        document_ids = [doc.document_id for doc in documents if doc.file_latest_id]
                                        previews = {}
                                        if document_ids:
                                            try:
                                                previews = await load_previews_batch(document_ids, client)
                                            except Exception as e:
                                                logger.error(f"Ошибка при батч-загрузке превью: {e}", exc_info=True)
                                                # Продолжаем работу без превью
                                        
                                        with documents_container:
                                            # Создаем label для счетчика документов
                                            documents_count_label = ui.label(
                                                f'Найдено документов: {total_count} (показано {len(documents)} из {total_count})'
                                            ).classes('text-sm text-gray-600 mb-2')
                                            
                                            for document in documents:
                                                # Передаем функцию обновления заголовка, текущий счетчик и label счетчика
                                                preview_data = previews.get(document.document_id)
                                                create_document_card(
                                                    document, 
                                                    update_cabinet_title, 
                                                    total_count,
                                                    documents_count_label,
                                                    preview_image_data=preview_data
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
                            create_page_timer(0.01, load_cabinet_content, once=True)
                    except Exception as ex:
                        logger.error(f"Ошибка при обработке события expansion: {ex}")
                        # В случае ошибки пробуем загрузить
                        create_page_timer(0.01, load_cabinet_content, once=True)
                
                expansion.on('update:model-value', on_expansion_change)
        
        # Создаем дерево кабинетов
        with state.recent_documents_container:
            if root_cabinets:
                for root_cabinet in root_cabinets:
                    create_cabinet_tree(root_cabinet)
            else:
                # Если нет корневых кабинетов, показываем все кабинеты
                for cabinet in cabinets:
                    create_cabinet_tree(cabinet)
                
    except TimeoutError as e:
        logger.error(f"Таймаут при загрузке кабинетов: {e}", exc_info=True)
        with state.recent_documents_container:
            ui.label('Превышено время ожидания при загрузке кабинетов. Попробуйте позже.').classes('text-red-500 text-center py-8')
    except Exception as e:
        logger.error(f"Ошибка при загрузке кабинетов: {e}", exc_info=True)
        with state.recent_documents_container:
            ui.label('Произошла ошибка при загрузке кабинетов. Обратитесь к администратору.').classes('text-red-500 text-center py-8')

def search_content() -> None:
    """Страница поиска документов"""
    state = get_state()
    
    # Сохраняем пользователя в состоянии для использования в асинхронных функциях
    current_user = get_current_user()
    if current_user:
        state.current_user = current_user
    
    logger.info("Открыта страница поиска документов")
    
    ui.label('Поиск документов').classes('text-lg font-semibold mb-4')
    
    with ui.row().classes('w-full mb-4'):
        search_input = ui.input('Поисковый запрос', placeholder='Введите название документа для поиска').classes('flex-1')
        ui.button('Поиск', icon='search', on_click=lambda: search_documents(search_input.value)).classes('ml-2 text-xs px-2 py-1 h-7')
    
    state.search_results_container = ui.column().classes('w-full')
    with state.search_results_container:
        ui.label('Введите поисковый запрос для начала поиска').classes('text-gray-500 text-center py-8')

async def upload_content(container: Optional[ui.column] = None, user: Optional[Any] = None) -> None:
    """Страница загрузки документов"""
    state = get_state()
    
    logger.info("Открыта страница загрузки документов")
    
    # Используем переданный контейнер или создаем новый (если вызывается напрямую)
    if container is not None:
        state.upload_form_container = container
    else:
        state.upload_form_container = ui.column().classes('w-full')
    
    # Сохраняем пользователя в состоянии для использования в асинхронных функциях
    if user is not None:
        state.current_user = user
    
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
            
            # Безопасное создание и скачивание файла с гарантированным удалением
            await safe_download_file(signed_pdf, filename, delay_seconds=5.0)
            
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
            # Получаем пароль из поля ввода
            password = password_input.value.strip()
            
            if not password:
                status_label.text = 'Пожалуйста, введите пароль'
                status_label.classes('text-red-500')
                return
            
            status_label.text = 'Проверка учетных данных...'
            status_label.classes('text-blue-500')
            
            # Используем try-finally для гарантированной очистки поля пароля
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
                # Пароль используется только здесь, в минимальной области видимости
                new_token = await temp_mayan_client.create_user_api_token(current_user.username, password)
                
                # После использования пароля, очищаем переменную (хотя в Python строки immutable,
                # это минимизирует время жизни ссылки)
                password = None
                
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
                # Безопасное логирование: не используем exc_info=True, чтобы избежать попадания
                # локальных переменных (включая password) в traceback
                # Логируем только тип исключения и сообщение, без полного traceback
                error_type = type(e).__name__
                error_message = str(e)
                # Убираем возможные упоминания пароля из сообщения об ошибке
                safe_error_message = error_message.replace('password', '***').replace('Password', '***')
                logger.error(f'Ошибка при повторной авторизации для пользователя {current_user.username}: [{error_type}] {safe_error_message}')
                
                # Показываем пользователю общее сообщение об ошибке без деталей
                status_label.text = 'Ошибка авторизации. Проверьте правильность пароля.'
                status_label.classes('text-red-500')
            finally:
                # Гарантированная очистка поля ввода пароля после использования
                # Это минимизирует время хранения пароля в UI компоненте
                try:
                    password_input.value = ''
                except Exception:
                    # Игнорируем ошибки при очистке (например, если компонент уже удален)
                    pass
                # Очищаем локальную переменную
                password = None
        
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
                # Проверяем rate limit для удаления (очень строгий лимит)
                current_user = get_current_user()
                if current_user:
                    user_id = current_user.username
                else:
                    user_id = 'anonymous'
                
                if not await check_rate_limit(user_id, 'delete', max_requests=5, window_seconds=60):
                    ui.notify('Превышен лимит удалений. Пожалуйста, подождите немного и попробуйте снова.', type='warning')
                    dialog.close()
                    return
                
                try:
                    client = await get_mayan_client()
                    success = await with_timeout(
                        client.delete_document(document.document_id),
                        timeout=30.0,
                        operation_name=f"удаление документа {document.document_id}"
                    )
                    
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
                                
                                # Отменяем все таймеры карточки перед удалением для предотвращения утечки памяти
                                if hasattr(card, 'cleanup'):
                                    try:
                                        card.cleanup()
                                        logger.debug(f'Таймеры карточки документа {document.document_id} отменены')
                                    except Exception as e:
                                        logger.warning(f'Ошибка при отмене таймеров карточки: {e}')
                                
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
                    # Отменяем все таймеры карточки перед удалением для предотвращения утечки памяти
                    if hasattr(card, 'cleanup'):
                        try:
                            card.cleanup()
                            logger.debug(f'Таймеры карточки документа {document.document_id} отменены')
                        except Exception as e:
                            logger.warning(f'Ошибка при отмене таймеров карточки: {e}')
                    
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
    state = get_state()
    
    if not state.favorites_container:
        return
    
    # Проверяем подключение
    if not await check_connection():
        with state.favorites_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if state.auth_error:
                ui.label(f'Ошибка: {state.auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        logger.info("Загружаем избранные документы...")
        client = await get_mayan_client()
        documents, total_count = await with_timeout(
            client.get_favorite_documents(page=1, page_size=100),
            timeout=30.0,
            operation_name="загрузка избранных документов"
        )
        logger.info(f"Получено избранных документов: {len(documents)} из {total_count}")
        
        state.favorites_container.clear()
        
        if not documents:
            with state.favorites_container:
                ui.label('У вас нет избранных документов').classes('text-gray-500 text-center py-8')
            return
        
        # Оптимизация N+1: загружаем все превью батчем перед созданием карточек
        document_ids = [doc.document_id for doc in documents if doc.file_latest_id]
        previews = {}
        if document_ids:
            try:
                previews = await load_previews_batch(document_ids, client)
            except Exception as e:
                logger.error(f"Ошибка при батч-загрузке превью: {e}", exc_info=True)
                # Продолжаем работу без превью
        
        with state.favorites_container:
            # Создаем label для счетчика документов
            count_label = ui.label(f'Избранные документы ({total_count})').classes('text-lg font-semibold mb-4')
            
            for document in documents:
                # Передаем флаг, что это страница избранных, и счетчик
                preview_data = previews.get(document.document_id)
                create_document_card(document, is_favorites_page=True, favorites_count_label=count_label, preview_image_data=preview_data)
    except TimeoutError as e:
        logger.error(f"Таймаут при загрузке избранных документов: {e}", exc_info=True)
        state.favorites_container.clear()
        with state.favorites_container:
            ui.label('Превышено время ожидания при загрузке избранных документов. Попробуйте позже.').classes('text-red-500 text-center py-8')
    except Exception as e:
        logger.error(f"Ошибка при загрузке избранных документов: {e}", exc_info=True)
        state.favorites_container.clear()
        with state.favorites_container:
            ui.label('Произошла ошибка при загрузке избранных документов. Обратитесь к администратору.').classes('text-red-500 text-center py-8')

# Добавить функцию favorites_content (после функции upload_content, после строки 1880):

def favorites_content() -> None:
    """Страница избранных документов"""
    state = get_state()
    
    # Сохраняем пользователя в состоянии для использования в асинхронных функциях
    current_user = get_current_user()
    if current_user:
        state.current_user = current_user
    
    # Очищаем старые таймеры при открытии страницы
    state.cleanup_timers()
    
    logger.info("Открыта страница избранных документов")
    
    # Секция с избранными документами
    with ui.row().classes('w-full mb-4'):
        ui.label('Избранные документы').classes('text-lg font-semibold')
        ui.button('Обновить', icon='refresh', on_click=load_favorite_documents).classes('ml-auto text-xs px-2 py-1 h-7')
    
    state.favorites_container = ui.column().classes('w-full')
    # Загружаем избранные документы только после создания контейнера
    create_page_timer(0.1, load_favorite_documents, once=True)