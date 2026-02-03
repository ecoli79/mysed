# services/directory_processor.py
"""Обработчик файлов из директории"""

from typing import Optional, Dict, Any
from pathlib import Path
import mimetypes
from datetime import datetime

from services.base_document_processor import BaseDocumentProcessor
from services.mayan_connector import MayanClient
from services.logger import get_logger

logger = get_logger(__name__)


class DirectoryProcessor(BaseDocumentProcessor):
    """Обработчик файлов из директории - сохраняет документы в Mayan EDMS"""
    
    def __init__(self, mayan_client: MayanClient, cache_db_path: Optional[str] = None):
        super().__init__(
            mayan_client=mayan_client,
            document_type_config_key='mayan_directory_document_type',
            cabinet_config_key='mayan_directory_cabinet',
            cache_db_path=cache_db_path
        )
    
    async def process_file(
        self, 
        file_path: Path,
        check_duplicates: bool = True
    ) -> Dict[str, Any]:
        """
        Обрабатывает файл и создает документ в Mayan EDMS
        """
        result = {
            'success': False,
            'document_id': None,
            'registered_number': None,
            'filename': file_path.name,
            'error': None
        }
        
        # Инициализируем тип документа и кабинет при первом использовании
        if self.document_type_id is None or self.cabinet_id is None:
            await self._init_document_type_and_cabinet()
        
        # Используем блокировку для предотвращения параллельного создания дубликатов
        async with self._processing_lock:
            try:
                # Проверяем существование файла
                if not file_path.exists() or not file_path.is_file():
                    result['error'] = f'Файл не существует или не является файлом: {file_path}'
                    return result
                
                # Читаем содержимое файла
                try:
                    file_content = file_path.read_bytes()
                except Exception as e:
                    result['error'] = f'Ошибка чтения файла: {str(e)}'
                    return result
                
                if not file_content:
                    result['error'] = 'Файл пуст'
                    return result
                
                file_size = len(file_content)
                
                # Определяем MIME тип
                mimetype, _ = mimetypes.guess_type(str(file_path))
                if not mimetype:
                    mimetype = 'application/octet-stream'
                
                # Вычисляем хеш файла
                file_hash = self.calculate_file_hash(file_content)
                
                logger.info(
                    f"Обработка файла: '{file_path.name}', hash={file_hash[:32]}..., "
                    f"size={file_size}, path={file_path}"
                )
                
                # Проверяем дубликаты перед созданием документа
                if check_duplicates:
                    logger.info(f"Проверка дубликатов для файла '{file_path.name}'...")
                    is_duplicate = await self._check_duplicate_by_hash(
                        file_hash=file_hash,
                        filename=file_path.name
                    )
                    
                    if is_duplicate:
                        logger.warning(
                            f"ДУБЛИКАТ ОБНАРУЖЕН! Файл '{file_path.name}' с хешем {file_hash[:32]}... "
                            f"уже существует. Пропускаем создание."
                        )
                        result['error'] = 'Дубликат: документ уже существует'
                        return result
                
                # Используем format_metadata из базового класса
                description = self.format_metadata(
                    source='directory',
                    filename=file_path.name,
                    file_hash=file_hash,
                    file_size=file_size,
                    extra_metadata=None
                )
                
                # Создаем документ в Mayan EDMS
                logger.info(f"Создание документа в Mayan EDMS для файла '{file_path.name}'...")
                try:
                    document_result = await self.mayan_client.create_document_with_file(
                        label=file_path.name,
                        description=description,
                        filename=file_path.name,
                        file_content=file_content,
                        mimetype=mimetype,
                        document_type_id=self.document_type_id,
                        cabinet_id=self.cabinet_id,
                        language='rus'
                    )
                except Exception as e:
                    logger.error(f"Исключение при создании документа для '{file_path.name}': {e}", exc_info=True)
                    result['error'] = f'Ошибка при создании документа: {str(e)}'
                    return result
                
                # ИЗМЕНЕНО: Проверяем полный успех создания документа
                if document_result and document_result.get('document_id'):
                    document_id = document_result['document_id']
                    
                    # ИЗМЕНЕНО: Проверяем что document_result содержит success=True
                    # или cabinet_added=True (если кабинет был назначен)
                    is_fully_successful = document_result.get('success', False)
                    cabinet_assigned = document_result.get('cabinet_added', False) if self.cabinet_id else True
                    
                    if not is_fully_successful:
                        logger.warning(
                            f"Документ {document_id} создан, но есть проблемы: "
                            f"success={is_fully_successful}, cabinet_assigned={cabinet_assigned}"
                        )
                        result['error'] = 'Документ создан не полностью (возможно, не добавлен в кабинет)'
                        result['document_id'] = str(document_id)
                        # НЕ добавляем в кеш!
                        return result
                    
                    # Парсим description обратно в dict для кеша
                    import json
                    try:
                        metadata_dict = json.loads(description)
                    except:
                        metadata_dict = {
                            'source': 'directory',
                            'attachment_filename': file_path.name,
                            'attachment_hash': file_hash,
                            'attachment_size': file_size
                        }
                    
                    # ИЗМЕНЕНО: Добавляем хеш в кеш ТОЛЬКО после полного успеха
                    try:
                        self.hash_cache.add_hash(
                            file_hash=file_hash,
                            document_id=str(document_id),
                            filename=file_path.name,
                            message_id=None,
                            cabinet_id=self.cabinet_id,
                            metadata=metadata_dict
                        )
                        logger.info(
                            f"✓ Документ {document_id} полностью создан, хеш {file_hash[:32]}... добавлен в кеш"
                        )
                    except Exception as cache_error:
                        logger.error(f"Ошибка при добавлении хеша в кеш: {cache_error}", exc_info=True)
                        # Документ создан, но кеш не обновлен - не критично
                        logger.warning("Документ создан успешно, но хеш не добавлен в кеш (будет проверяться через Mayan)")
                    
                    # Извлекаем входящий номер
                    registered_number = await self.extract_registered_number(document_id, file_path.name)
                    
                    result['success'] = True
                    result['document_id'] = str(document_id)
                    result['registered_number'] = registered_number
                    
                    logger.info(
                        f"✓ Файл '{file_path.name}' полностью сохранен как документ {document_id} "
                        f"(hash: {file_hash[:32]}...)"
                    )
                else:
                    result['error'] = 'Не удалось создать документ в Mayan EDMS'
                    logger.error(f"Не удалось создать документ для файла '{file_path.name}'")
                
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Ошибка при обработке файла '{file_path.name}': {e}", exc_info=True)
        
        return result