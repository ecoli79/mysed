# services/base_document_processor.py
"""Базовый класс для обработки документов (email, directory, etc.)"""

from typing import Optional, Dict, Any
from datetime import datetime
import json
import hashlib
import asyncio
from pathlib import Path

from services.mayan_connector import MayanClient
from services.document_hash_cache import DocumentHashCache
from config.settings import config
from services.logger import get_logger

logger = get_logger(__name__)


class BaseDocumentProcessor:
    """Базовый класс для обработчиков документов"""
    
    def __init__(
        self, 
        mayan_client: MayanClient, 
        document_type_config_key: str,
        cabinet_config_key: str,
        cache_db_path: Optional[str] = None
    ):
        """
        Инициализация процессора
        
        Args:
            mayan_client: Клиент Mayan EDMS
            document_type_config_key: Ключ конфигурации для типа документа
            cabinet_config_key: Ключ конфигурации для кабинета
            cache_db_path: Путь к БД кеша
        """
        self.mayan_client = mayan_client
        self.document_type_config_key = document_type_config_key
        self.cabinet_config_key = cabinet_config_key
        
        self.document_type_id: Optional[int] = None
        self.cabinet_id: Optional[int] = None
        
        # Инициализируем кеш хешей документов
        self.hash_cache = DocumentHashCache(cache_db_path=cache_db_path)
        
        # Блокировка для предотвращения race condition
        self._processing_lock = asyncio.Lock()
        
        # Флаг инициализации кеша
        self._cache_initialized = False
    
    async def _init_document_type_and_cabinet(self):
        """Инициализирует тип документа и кабинет"""
        if self.document_type_id is not None and self.cabinet_id is not None:
            if not self._cache_initialized:
                await self._sync_hash_cache()
            return
        
        try:
            # Получаем список типов документов
            document_types = await self.mayan_client.get_document_types()
            type_name = getattr(config, self.document_type_config_key)
            
            for doc_type in document_types:
                if doc_type.get('label') == type_name:
                    self.document_type_id = doc_type['id']
                    logger.info(f"Найден тип документа: {type_name} (ID: {self.document_type_id})")
                    break
            
            if self.document_type_id is None and document_types:
                self.document_type_id = document_types[0]['id']
                logger.warning(f"Тип '{type_name}' не найден, используем '{document_types[0]['label']}'")
            
            # Получаем список кабинетов
            cabinets = await self.mayan_client.get_cabinets()
            cabinet_name = getattr(config, self.cabinet_config_key)
            
            for cabinet in cabinets:
                if cabinet.get('label') == cabinet_name:
                    self.cabinet_id = cabinet['id']
                    logger.info(f"Найден кабинет: {cabinet_name} (ID: {self.cabinet_id})")
                    break
            
            if self.cabinet_id is None:
                logger.warning(f"Кабинет '{cabinet_name}' не найден. Документы будут созданы без кабинета.")
            
            # Синхронизируем кеш после инициализации
            if self.cabinet_id is not None:
                await self._sync_hash_cache()
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации типа документа и кабинета: {e}")
    
    async def _sync_hash_cache(self):
        """Синхронизирует кеш хешей с документами из Mayan"""
        if self._cache_initialized:
            return
        
        try:
            cache_count = self.hash_cache.get_count(cabinet_id=self.cabinet_id)
            logger.info(f"Текущий размер кеша: {cache_count} записей")
            
            if cache_count == 0:
                logger.info("Кеш пуст, начинаем полную синхронизацию из Mayan...")
                await self.hash_cache.sync_from_mayan(
                    self.mayan_client,
                    cabinet_id=self.cabinet_id,
                    max_pages=100
                )
            else:
                logger.info(f"Кеш уже содержит {cache_count} записей, пропускаем синхронизацию")
            
            self._cache_initialized = True
        except Exception as e:
            logger.error(f"Ошибка синхронизации кеша: {e}", exc_info=True)
            self._cache_initialized = True
    
    @staticmethod
    def calculate_file_hash(file_content: bytes) -> str:
        """Вычисляет SHA256 хеш файла"""
        return hashlib.sha256(file_content).hexdigest()
    
    def format_metadata(
        self, 
        source: str,
        filename: str,
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Форматирует метаданные для сохранения в description документа
        
        Args:
            source: Источник документа (email, directory, etc.)
            filename: Имя файла
            file_hash: SHA256 хеш файла
            file_size: Размер файла в байтах
            extra_metadata: Дополнительные метаданные (message_id, from, subject и т.д.)
        
        Returns:
            JSON-строка с метаданными
        """
        metadata_dict = {
            'source': source,
            'attachment_filename': filename,
            'processed_date': datetime.now().isoformat()
        }
        
        if file_hash:
            metadata_dict['attachment_hash'] = file_hash
        if file_size:
            metadata_dict['attachment_size'] = file_size
        
        # Добавляем дополнительные метаданные
        if extra_metadata:
            metadata_dict.update(extra_metadata)
        
        try:
            return json.dumps(metadata_dict, ensure_ascii=False, indent=2)
        except Exception:
            # Fallback на простой текст
            return (
                f"Источник: {source}\n"
                f"Файл: {filename}\n"
                f"Обработано: {datetime.now().isoformat()}"
            )
    
    async def _check_duplicate_by_hash(
        self, 
        file_hash: str,
        filename: str,
        exclude_document_id: Optional[str] = None
    ) -> bool:
        """
        Проверяет дубликаты по хешу файла
        
        Args:
            file_hash: SHA256 хеш файла
            filename: Имя файла (для логирования)
            exclude_document_id: ID документа для исключения из проверки
        
        Returns:
            True если дубликат найден
        """
        if not file_hash:
            logger.warning(f"Проверка дубликатов без хеша для файла {filename} - менее надежно!")
            return False
        
        # ПЕРВЫЙ ПРИОРИТЕТ: Проверка в локальном кеше
        if self.hash_cache.hash_exists(file_hash, cabinet_id=self.cabinet_id):
            cached_doc = self.hash_cache.get_document_by_hash(file_hash, cabinet_id=self.cabinet_id)
            if cached_doc and str(cached_doc['document_id']) != str(exclude_document_id):
                logger.warning(
                    f"ДУБЛИКАТ НАЙДЕН в кеше: документ {cached_doc['document_id']}, "
                    f"hash={file_hash[:32]}..., filename='{filename}'"
                )
                return True
        
        # ВТОРОЙ ПРИОРИТЕТ: Проверка в Mayan
        try:
            logger.info(f"Проверка дубликатов в Mayan для файла '{filename}'...")
            
            max_pages = 20
            checked_documents = 0
            
            for page in range(1, max_pages + 1):
                try:
                    documents, total = await self.mayan_client.get_documents(
                        page=page,
                        page_size=100,
                        cabinet_id=self.cabinet_id
                    )
                except Exception as e:
                    logger.error(f"Ошибка при получении страницы {page}: {e}", exc_info=True)
                    break
                
                if not documents:
                    break
                
                checked_documents += len(documents)
                
                for doc in documents:
                    if exclude_document_id and str(doc.document_id) == str(exclude_document_id):
                        continue
                    
                    try:
                        if not doc.description:
                            continue
                        
                        try:
                            metadata = json.loads(doc.description)
                        except json.JSONDecodeError:
                            continue
                        
                        # Проверка по хешу
                        doc_hash = metadata.get('attachment_hash') or metadata.get('file_hash')
                        if doc_hash == file_hash:
                            logger.warning(
                                f"ДУБЛИКАТ НАЙДЕН в Mayan: документ {doc.document_id}, "
                                f"hash={file_hash[:32]}..., filename='{filename}'"
                            )
                            # Добавляем в кеш
                            self.hash_cache.add_hash(
                                file_hash=file_hash,
                                document_id=str(doc.document_id),
                                filename=metadata.get('attachment_filename'),
                                message_id=metadata.get('message_id'),
                                cabinet_id=self.cabinet_id,
                                metadata=metadata
                            )
                            return True
                    
                    except Exception as e:
                        logger.debug(f"Ошибка обработки документа {doc.document_id}: {e}")
                        continue
            
            logger.info(f"Дубликатов не найдено. Проверено {checked_documents} документов")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке дубликатов в Mayan: {e}", exc_info=True)
            return False
    
    async def create_document(
        self,
        label: str,
        filename: str,
        file_content: bytes,
        mimetype: str,
        metadata_dict: Dict[str, Any],
        language: str = 'rus'
    ) -> Dict[str, Any]:
        """
        Создает документ в Mayan EDMS
        
        Args:
            label: Метка документа
            filename: Имя файла
            file_content: Содержимое файла
            mimetype: MIME-тип
            metadata_dict: Словарь с метаданными
            language: Язык документа
        
        Returns:
            Результат создания документа
        """
        description = json.dumps(metadata_dict, ensure_ascii=False, indent=2)
        
        return await self.mayan_client.create_document_with_file(
            label=label,
            description=description,
            filename=filename,
            file_content=file_content,
            mimetype=mimetype,
            document_type_id=self.document_type_id,
            cabinet_id=self.cabinet_id,
            language=language
        )
    
    async def extract_registered_number(self, document_id: str, original_label: str) -> Optional[str]:
        """Извлекает входящий номер из документа Mayan EDMS"""
        try:
            document = await self.mayan_client.get_document(document_id)
            if document:
                label = document.label
                
                import re
                patterns = [
                    r'(IN-\d{4}-\d+)',
                    r'(ВХ-\d{4}-\d+)',
                    r'(\d{4}-\d+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, label)
                    if match:
                        return match.group(1)
                
                return label
                
        except Exception as e:
            logger.warning(f"Не удалось извлечь номер из документа {document_id}: {e}")
        
        return None