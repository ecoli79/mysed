from nicegui import ui
from services.mayan_connector import MayanClient, MayanDocument
from services.access_types import AccessTypeManager, AccessType
from services.document_access_manager import document_access_manager
from auth.middleware import get_current_user
from config.settings import config
from datetime import datetime
import logging
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

logger = logging.getLogger(__name__)

# Глобальные переменные для управления состоянием
_recent_documents_container: Optional[ui.column] = None
_search_results_container: Optional[ui.column] = None
_upload_form_container: Optional[ui.column] = None
_mayan_client: Optional[MayanClient] = None
_connection_status: bool = False
_auth_error: Optional[str] = None

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
    def extract_metadata(self, container: ui.column, params: UploadParams) -> DocumentMetadata: ...

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
    
    def upload_document(
        self, 
        upload_event, 
        params: UploadParams, 
        container: ui.column
    ) -> None:
        """Загружает документ"""
        try:
            # Валидация входных данных
            self._validate_params(params)
            
            # Извлечение метаданных
            metadata = self.extractor.extract_metadata(container, params)
            
            # Обработка файла
            file_info = self._process_file(upload_event)
            
            # Создание документа с файлом в одном запросе используя новый метод из MayanClient
            result = self.client.create_document_with_file(
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
            
            # Обновление списка документов
            load_recent_documents()
            
        except ValidationError as e:
            self._notify_error(f"Ошибка валидации: {e}")
        except FileProcessingError as e:
            self._notify_error(f"Ошибка обработки файла: {e}")
        except DocumentCreationError as e:
            self._notify_error(f"Ошибка создания документа: {e}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке документа: {e}")
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
        ui.notify(f'Документ "{label}" успешно загружен!', type='positive')
        logger.info(f"Документ {label} успешно загружен с ID: {document_id}")
    
    def _notify_error(self, message: str) -> None:
        """Уведомляет об ошибке"""
        ui.notify(message, type='error')
        logger.error(message)

class SimpleFormDataExtractor:
    """Упрощенный извлекатель данных из формы"""
    
    def extract_metadata(self, container: ui.column, params: UploadParams) -> DocumentMetadata:
        """Извлекает метаданные из параметров напрямую"""
        # Получаем клиент для получения ID по названиям
        client = get_mayan_client()
        
        # Получаем ID типа документа
        document_type_id = self._get_document_type_id_by_name(client, params.document_type_name)
        
        # Получаем ID кабинета
        cabinet_id = self._get_cabinet_id_by_name(client, params.cabinet_name)
        
        # Получаем ID языка
        # language_id = self._get_language_id_by_name(client, params.language_name)
        
        # Получаем ID тегов
        tag_ids = self._get_tag_ids_by_names(client, params.tag_names)
        
        return DocumentMetadata(
            document_type_id=document_type_id,
            cabinet_id=cabinet_id,
            language_id='rus', #language_id,
            tag_ids=tag_ids
        )
    
    def _get_document_type_id_by_name(self, client: MayanClient, type_name: Optional[str]) -> int:
        """Получает ID типа документа по названию"""
        if not type_name:
            raise ValidationError("Тип документа не выбран")
        
        document_types = client.get_document_types()
        for dt in document_types:
            if dt['label'] == type_name:
                return dt['id']
        
        raise ValidationError(f"Не удалось найти тип документа: {type_name}")
    
    def _get_cabinet_id_by_name(self, client: MayanClient, cabinet_name: Optional[str]) -> Optional[int]:
        """Получает ID кабинета по названию"""
        if not cabinet_name:
            return None
        
        cabinets = client.get_cabinets()
        for cabinet in cabinets:
            if cabinet['label'] == cabinet_name:
                return cabinet['id']
        
        logger.warning(f"Не удалось найти кабинет: {cabinet_name}")
        return None

    def _get_tag_ids_by_names(self, client: MayanClient, tag_names: Optional[List[str]]) -> Optional[List[int]]:
        """Получает ID тегов по названиям"""
        if not tag_names:
            return None
        
        try:
            tags = client.get_tags()
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

def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return MayanClient.create_with_session_user()

def check_connection() -> bool:
    """Проверяет подключение к Mayan EDMS"""
    global _connection_status, _auth_error
    
    try:
        client = get_mayan_client()
        _connection_status = client.test_connection()
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

def update_file_size(document: MayanDocument, size_label: ui.label):
    """Асинхронно обновляет количество страниц в карточке документа"""
    try:
        client = get_mayan_client()
        
        # Получаем количество страниц документа
        page_count = client.get_document_page_count(document.document_id)
        
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

def create_document_card(document: MayanDocument) -> ui.card:
    """Создает карточку документа с возможностью предоставления доступа"""
    
    # Временное логирование для отладки
    logger.info(f"Создаем карточку для документа {document.document_id}:")
    logger.info(f"  - Название: {document.label}")
    logger.info(f"  - Файл: {document.file_latest_filename}")
    logger.info(f"  - Размер файла: {document.file_latest_size}")
    logger.info(f"  - MIME-тип: {document.file_latest_mimetype}")
    
    # ИСПРАВЛЕНИЕ: Проверяем наличие подписей у документа
    has_signatures = False
    try:
        from services.signature_manager import SignatureManager
        signature_manager = SignatureManager()
        has_signatures = signature_manager.document_has_signatures(document.document_id)
        logger.info(f"  - Есть подписи: {has_signatures}")
    except Exception as e:
        logger.warning(f"Ошибка проверки подписей для документа {document.document_id}: {e}")
    
    with ui.card().classes('w-full mb-4') as card:
        with ui.row().classes('w-full items-start'):
            # Основная информация
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
            
            # Кнопки действий - исправляем структуру и выравнивание
            with ui.column().classes('items-end gap-2 min-w-fit flex-shrink-0'):
                if document.file_latest_id:
                    # Кнопка скачивания
                    ui.button('Скачать', icon='download').classes('text-xs').on_click(
                        lambda doc=document: download_document_file(doc)
                    )
                    
                    # Кнопка предварительного просмотра
                    ui.button('Просмотр', icon='visibility').classes('text-xs').on_click(
                        lambda doc=document: preview_document_file(doc)
                    )
                    
                    # ИСПРАВЛЕНИЕ: Кнопка "Скачать с подписями" показывается только если есть подписи
                    if has_signatures:
                        ui.button('Скачать с подписями', icon='verified', color='green').classes('text-xs').on_click(
                            lambda doc=document: download_signed_document(doc)
                        )
                
                # Кнопка просмотра содержимого
                ui.button('Содержимое', icon='text_fields').classes('text-xs').on_click(
                    lambda doc=document: show_document_content(doc)
                )
                
                # Кнопка просмотра доступа
                ui.button('Доступ', icon='security').classes('text-xs').on_click(
                    lambda doc=document: show_document_access_info(doc)
                )
                
                # Кнопка предоставления доступа
                current_user = get_current_user()
                if current_user:
                    ui.button('Предоставить доступ', icon='share', color='blue').classes('text-xs').on_click(
                        lambda doc=document: show_grant_access_dialog(doc)
                    )
    
    return card


def show_grant_access_dialog(document: MayanDocument):
    """
    Показывает диалог для предоставления доступа к документу
    """
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-md'):
        ui.label(f'Предоставить доступ к документу: {document.label}').classes('text-lg font-semibold mb-4')
        
        # Форма предоставления доступа
        with ui.column().classes('w-full gap-4'):
            
            # Получаем список ролей для выпадающего списка
            try:
                roles = document_access_manager.get_available_roles()
                
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
            
            #Получаем список разрешений для документов
            # try:
            #     permissions = document_access_manager.get_available_permissions_for_documents()
                
            #     if permissions:
            #         # Создаем список названий разрешений
            #         permission_options = [perm['label'] for perm in permissions if perm.get('label')]
            #         logger.info(f"Доступные разрешения для документов: {permission_options}")
                    
            #         if permission_options:
            #             # Множественный выбор разрешений
            #             permission_select = ui.select(
            #                 options=permission_options,
            #                 label='Выберите разрешения (можно несколько)',
            #                 multiple=True,
            #                 value=[]  # Начинаем с пустого списка
            #             ).classes('w-full')
                        
            #             # Добавляем подсказку
            #             ui.label('💡 Совет: Выберите несколько разрешений для более гибкого управления доступом').classes('text-xs text-blue-600')
            #         else:
            #             ui.label('Разрешения найдены, но без названий').classes('text-orange-500')
            #             permission_select = None
            #     else:
            #         ui.label('Разрешения для документов не найдены').classes('text-orange-500')
            #         permission_select = None
                    
            # except Exception as e:
            #     logger.error(f"Ошибка при получении разрешений: {e}")
            #     ui.label(f'Ошибка при загрузке разрешений: {str(e)}').classes('text-red-500')
            #     permission_select = None

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




            def handle_grant_access():
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
                    permissions = document_access_manager.get_available_permissions_for_documents()
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
                    success = document_access_manager.grant_document_access_to_role_by_pks(
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
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    ui.notify(f'Ошибка: {str(e)}', type='error')
            
            # # Кнопки
            with ui.row().classes('w-full gap-2'):
                ui.button('Отмена').on('click', dialog.close)
                ui.button('Предоставить доступ', icon='add', color='primary').classes('flex-1').on('click', handle_grant_access)
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
                ui.button('Скачать файл', icon='download', on_click=lambda: download_document_file(document)).classes('mt-4')
            
            # Кнопки управления
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Закрыть').on('click', dialog.close)
        
        dialog.open()
        
    except Exception as e:
        logger.error(f"Ошибка при получении содержимого документа: {e}")
        ui.notify(f'Ошибка при получении содержимого: {str(e)}', type='error')


def load_recent_documents():
    """Загружает последние 10 документов"""
    global _recent_documents_container
    
    if _recent_documents_container:
        _recent_documents_container.clear()
    
    # Проверяем подключение
    if not check_connection():
        with _recent_documents_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        logger.info("Загружаем последние документы...")
        # Получаем последние 10 документов
        documents = get_mayan_client().get_documents(page=1, page_size=10)
        logger.info(f"Получено документов: {len(documents)}")
        
        if not documents:
            with _recent_documents_container:
                ui.label('Документы не найдены').classes('text-gray-500 text-center py-8')
            return
        
        with _recent_documents_container:
            for document in documents:
                create_document_card(document)
                
    except Exception as e:
        logger.error(f"Ошибка при загрузке документов: {e}")
        with _recent_documents_container:
            ui.label(f'Ошибка при загрузке документов: {str(e)}').classes('text-red-500 text-center py-8')

def search_documents(query: str):
    """Выполняет поиск документов"""
    global _search_results_container
    
    if _search_results_container:
        _search_results_container.clear()
    
    if not query.strip():
        with _search_results_container:
            ui.label('Введите поисковый запрос').classes('text-gray-500 text-center py-8')
        return
    
    # Проверяем подключение
    if not check_connection():
        with _search_results_container:
            ui.label('Нет подключения к серверу Mayan EDMS').classes('text-red-500 text-center py-8')
            if _auth_error:
                ui.label(f'Ошибка: {_auth_error}').classes('text-sm text-gray-500 text-center')
            ui.label(f'Проверьте настройки подключения к серверу: {config.mayan_url}').classes('text-sm text-gray-500 text-center')
        return
    
    try:
        logger.info(f"Выполняем поиск по запросу: {query}")
        # Выполняем поиск
        documents = get_mayan_client().search_documents(query, page=1, page_size=20)
        logger.info(f"Найдено документов: {len(documents)}")
        
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
        with _search_results_container:
            ui.label(f'Ошибка при поиске: {str(e)}').classes('text-red-500 text-center py-8')

def upload_document():
    """Загружает документ на сервер"""
    global _upload_form_container
    
    if _upload_form_container:
        _upload_form_container.clear()
    
    with _upload_form_container:
        ui.label('Загрузка документа').classes('text-lg font-semibold mb-4')
        
        # Проверяем подключение
        if not check_connection():
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
                client = get_mayan_client()
                
                # Получаем типы документов
                document_types = client.get_document_types()
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
                    ui.label('Не удалось загрузить типы документов').classes('text-red-500')
                            
                # Получаем кабинеты
                cabinets = client.get_cabinets()
                cabinet_select = None
                if cabinets:
                    # ИСПРАВЛЕНИЕ: Используем простой список названий для отображения
                    cabinet_options = []
                    cabinet_id_map = {}  # Словарь для соответствия названий и ID
                    for cabinet in cabinets:
                        display_name = cabinet['label']  # Название кабинета
                        cabinet_options.append(display_name)  # Простой список названий
                        cabinet_id_map[display_name] = cabinet['id']  # Сохраняем соответствие
                    
                    default_cabinet_value = cabinet_options[0] if cabinet_options else None  # Название первого элемента
                    cabinet_select = ui.select(
                        options=cabinet_options,
                        label='Кабинет',
                        value=default_cabinet_value
                    ).classes('w-full')
                    
                    # Сохраняем соответствие для использования в handle_file_upload
                    cabinet_select.cabinet_id_map = cabinet_id_map
                else:
                    ui.label('Кабинеты не найдены').classes('text-gray-500')
                
                # Убираем языки и теги - оставляем только тип документа и кабинет
                                    
            except Exception as e:
                logger.error(f"Ошибка при получении данных с сервера: {e}")
                ui.label(f'Ошибка при загрузке данных: {str(e)}').classes('text-red-500')
                document_type_select = None
                cabinet_select = None
            
            # Загрузка файла
            upload_area = ui.upload(
                on_upload=lambda e: handle_file_upload(
                    e, 
                    description_input.value,
                    document_type_select.value if document_type_select else None,
                    cabinet_select.value if cabinet_select else None
                ),
                auto_upload=False
            ).classes('w-full')
            
            ui.label('Выберите файл для загрузки').classes('text-sm text-gray-600')

def handle_file_upload(
    upload_event, 
    description: str, 
    document_type_name: Optional[str] = None, 
    cabinet_name: Optional[str] = None
) -> None:
    """Обрабатывает загрузку файла с улучшенной архитектурой"""
    global _upload_form_container
    
    if not _upload_form_container:
        ui.notify('Форма загрузки не инициализирована', type='error')
        return
    
    try:
        # Получаем имя файла без расширения для названия документа
        filename = upload_event.name
        # Убираем расширение файла для названия документа
        document_label = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        logger.info(f"Имя файла: {filename}")
        logger.info(f"Название документа (без расширения): {document_label}")
        
        # Создаем параметры загрузки
        params = UploadParams(
            label=document_label,  # Используем имя файла без расширения
            description=description,
            document_type_name=document_type_name,
            cabinet_name=cabinet_name,
            language_name=None,  # Убираем языки
            tag_names=None  # Убираем теги
        )
        
        # Получаем клиент
        client = get_mayan_client()
        
        # Создаем загрузчик с упрощенным извлекателем
        uploader = DocumentUploader(client, SimpleFormDataExtractor())
        uploader.upload_document(upload_event, params, _upload_form_container)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке документа: {e}")
        ui.notify(f'Критическая ошибка: {str(e)}', type='error')


def download_document_file(document: MayanDocument):
    """Скачивает файл документа через прокси"""
    try:
        client = get_mayan_client()
        
        # Получаем содержимое файла
        file_content = client.get_document_file_content(document.document_id)
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

def preview_document_file(document: MayanDocument):
    """Показывает превью документа в диалоге"""
    try:
        client = get_mayan_client()
        
        # Получаем содержимое файла
        file_content = client.get_document_file_content(document.document_id)
        if not file_content:
            ui.notify('Не удалось получить содержимое файла для просмотра', type='error')
            return
        
        # Определяем тип файла по расширению, если MIME-тип не определен или неправильный
        filename = document.file_latest_filename or f"document_{document.document_id}"
        mimetype = document.file_latest_mimetype or 'application/octet-stream'
        
        # Если MIME-тип не определен или неправильный, определяем по расширению
        if mimetype == 'application/octet-stream' or not mimetype:
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
                
                # Конвертируем в base64 для отображения в iframe
                with open(temp_path, 'rb') as f:
                    pdf_data = base64.b64encode(f.read()).decode()
                
                # Создаем iframe для отображения PDF с увеличенной высотой
                pdf_url = f"data:{mimetype};base64,{pdf_data}"
                ui.html(f'''
                    <iframe src="{pdf_url}" 
                            width="100%" 
                            height="75vh" 
                            style="border: none; min-height: 600px;">
                        <p>Ваш браузер не поддерживает отображение PDF файлов. 
                        <a href="{pdf_url}" target="_blank">Открыть в новой вкладке</a></p>
                    </iframe>
                ''').classes('w-full')
                
                # Удаляем временный файл
                ui.timer(10.0, lambda: os.unlink(temp_path), once=True)
            
            elif mimetype in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                # Для документов Word показываем информацию
                ui.label('Документ Microsoft Word').classes('text-lg font-semibold mb-2')
                ui.label(f'Файл: {filename}').classes('text-sm text-gray-600 mb-2')
                ui.label(f'Размер: {format_file_size(len(file_content))}').classes('text-sm text-gray-600 mb-4')
                ui.label('Для просмотра документа Word скачайте файл и откройте в соответствующем приложении.').classes('text-gray-500')
                
                # Кнопка для скачивания
                ui.button('Скачать файл', icon='download', on_click=lambda: download_document_file(document)).classes('mt-4')
            
            elif mimetype in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                # Для Excel файлов показываем информацию
                ui.label('Таблица Microsoft Excel').classes('text-lg font-semibold mb-2')
                ui.label(f'Файл: {filename}').classes('text-sm text-gray-600 mb-2')
                ui.label(f'Размер: {format_file_size(len(file_content))}').classes('text-sm text-gray-600 mb-4')
                ui.label('Для просмотра таблицы Excel скачайте файл и откройте в соответствующем приложении.').classes('text-gray-500')
                
                # Кнопка для скачивания
                ui.button('Скачать файл', icon='download', on_click=lambda: download_document_file(document)).classes('mt-4')
            
            else:
                # Для других типов файлов показываем информацию
                ui.label(f'Файл типа {mimetype}').classes('text-lg font-semibold mb-2')
                ui.label(f'Файл: {filename}').classes('text-sm text-gray-600 mb-2')
                ui.label(f'Размер: {format_file_size(len(file_content))}').classes('text-sm text-gray-600 mb-4')
                ui.label('Этот тип файла не может быть отображен в превью.').classes('text-gray-500')
                
                # Кнопка для скачивания
                ui.button('Скачать файл', icon='download', on_click=lambda: download_document_file(document)).classes('mt-4')
            
            # Кнопки управления
            with ui.row().classes('mt-4 gap-2'):
                ui.button('Закрыть', on_click=dialog.close).classes('flex-1')
                ui.button('Открыть в новой вкладке', icon='open_in_new', on_click=lambda: ui.open(f"data:{mimetype};base64,{base64.b64encode(file_content).decode()}")).classes('flex-1')
        
        dialog.open()
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре файла: {e}")
        ui.notify(f'Ошибка при просмотре: {str(e)}', type='error')

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
    """Основная страница работы с документами Mayan EDMS"""
    global _recent_documents_container, _search_results_container, _upload_form_container
    
    logger.info("Открыта страница работы с документами Mayan EDMS")
    
    # # Заголовок страницы
    # ui.label('Документы Mayan EDMS').classes('text-2xl font-bold mb-6')
    
    # # Статус подключения
    # connection_status_label = ui.label('Проверка подключения...').classes('text-sm mb-4')
    
    # # Проверяем подключение при загрузке страницы
    # if check_connection():
    #     connection_status_label.text = 'Подключение к серверу установлено'
    #     connection_status_label.classes('text-green-600')
    # else:
    #     connection_status_label.text = f'Нет подключения к серверу {config.mayan_url}'
    #     connection_status_label.classes('text-red-600')
    #     if _auth_error:
    #         ui.label(f'Ошибка авторизации: {_auth_error}').classes('text-sm text-red-500 mb-2')
    
    # Создаем табы
    with ui.tabs().classes('w-full') as tabs:
        recent_tab = ui.tab('Последние документы')
        search_tab = ui.tab('Поиск документов')
        upload_tab = ui.tab('Загрузка документов')
    
    with ui.tab_panels(tabs, value=recent_tab).classes('w-full'):
        # Таб с последними документами
        with ui.tab_panel(recent_tab):
            with ui.row().classes('w-full mb-4'):
                ui.label('Последние 10 документов').classes('text-lg font-semibold')
                ui.button('Обновить', icon='refresh', on_click=load_recent_documents).classes('ml-auto')
            
            _recent_documents_container = ui.column().classes('w-full')
            # Загружаем документы только после создания контейнера
            ui.timer(0.1, load_recent_documents, once=True)
        
        # Таб поиска документов
        with ui.tab_panel(search_tab):
            ui.label('Поиск документов').classes('text-lg font-semibold mb-4')
            
            with ui.row().classes('w-full mb-4'):
                search_input = ui.input('Поисковый запрос', placeholder='Введите название документа для поиска').classes('flex-1')
                ui.button('Поиск', icon='search', on_click=lambda: search_documents(search_input.value)).classes('ml-2')
            
            _search_results_container = ui.column().classes('w-full')
            with _search_results_container:
                ui.label('Введите поисковый запрос для начала поиска').classes('text-gray-500 text-center py-8')
        
        # Таб загрузки документов
        with ui.tab_panel(upload_tab):
            _upload_form_container = ui.column().classes('w-full')
            upload_document()

def download_signed_document(document: MayanDocument):
    '''Скачивает документ с информацией о подписях'''
    try:
        from services.signature_manager import SignatureManager
        import tempfile
        
        ui.notify('Создание итогового документа с подписями...', type='info')
        
        signature_manager = SignatureManager()
        signed_pdf = signature_manager.create_signed_document_pdf(document.document_id)
        
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
            
            ui.notify(f'✅ Файл "{filename}" подготовлен для скачивания', type='success')
            logger.info(f'Итоговый документ {document.document_id} подготовлен для скачивания как {filename}')
        else:
            ui.notify('⚠️ Не удалось создать документ с подписями', type='warning')
            
    except Exception as e:
        logger.error(f'Ошибка скачивания документа с подписями: {e}', exc_info=True)
        ui.notify(f'Ошибка: {str(e)}', type='error')