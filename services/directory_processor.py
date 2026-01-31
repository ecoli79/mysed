# services/directory_processor.py
from typing import Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path
import hashlib
import asyncio
import mimetypes
from services.mayan_connector import MayanClient
from services.document_hash_cache import DocumentHashCache
from config.settings import config
from app_logging.logger import get_logger

logger = get_logger(__name__)


class DirectoryProcessor:
    """Обработчик файлов из директории - сохраняет документы в Mayan EDMS"""
    
    def __init__(self, mayan_client: MayanClient, cache_db_path: Optional[str] = None):
        self.mayan_client = mayan_client
        self.directory_document_type_id: Optional[int] = None
        self.directory_cabinet_id: Optional[int] = None
        
        # Инициализируем кеш хешей документов
        self.hash_cache = DocumentHashCache(cache_db_path=cache_db_path)
        
        # Блокировка для предотвращения race condition
        self._processing_lock = asyncio.Lock()
        
        # Флаг инициализации кеша
        self._cache_initialized = False
    
    async def _init_document_type_and_cabinet(self):
        """Инициализирует тип документа и кабинет для файлов из директории"""
        if self.directory_document_type_id is not None and self.directory_cabinet_id is not None:
            # Если уже инициализировано, синхронизируем кеш если нужно
            if not self._cache_initialized:
                await self._sync_hash_cache()
            return  # Уже инициализировано
        
        try:
            # Получаем список типов документов
            document_types = await self.mayan_client.get_document_types()
            
            # Ищем тип документа из конфигурации (по умолчанию "Входящие")
            directory_type_name = config.mayan_directory_document_type
            
            for doc_type in document_types:
                if doc_type.get('label') == directory_type_name:
                    self.directory_document_type_id = doc_type['id']
                    logger.info(f"Найден тип документа для директории: {directory_type_name} (ID: {self.directory_document_type_id})")
                    break
            
            # Если тип не найден, используем первый доступный
            if self.directory_document_type_id is None:
                if document_types:
                    self.directory_document_type_id = document_types[0]['id']
                    logger.warning(f"Тип '{directory_type_name}' не найден, используем '{document_types[0]['label']}' (ID: {self.directory_document_type_id})")
                else:
                    logger.error("Не найдено ни одного типа документа в Mayan EDMS")
            
            # Получаем список кабинетов
            cabinets = await self.mayan_client.get_cabinets()
            
            # Ищем кабинет из конфигурации (по умолчанию "Файлы из директории")
            directory_cabinet_name = config.mayan_directory_cabinet
            
            for cabinet in cabinets:
                if cabinet.get('label') == directory_cabinet_name:
                    self.directory_cabinet_id = cabinet['id']
                    logger.info(f"Найден кабинет для директории: {directory_cabinet_name} (ID: {self.directory_cabinet_id})")
                    break
            
            # Если кабинет не найден, логируем предупреждение
            if self.directory_cabinet_id is None:
                logger.warning(f"Кабинет '{directory_cabinet_name}' не найден. Документы будут созданы без кабинета.")
                logger.info(f"Доступные кабинеты: {[c.get('label') for c in cabinets]}")
                
            # После инициализации синхронизируем кеш
            if self.directory_cabinet_id is not None:
                await self._sync_hash_cache()
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации типа документа и кабинета: {e}")
    
    async def _sync_hash_cache(self):
        """Синхронизирует кеш хешей с документами из Mayan"""
        if self._cache_initialized:
            return
        
        try:
            cache_count = self.hash_cache.get_count(cabinet_id=self.directory_cabinet_id)
            logger.info(f"Текущий размер кеша: {cache_count} записей")
            
            if cache_count == 0:
                logger.info("Кеш пуст, начинаем полную синхронизацию из Mayan...")
                await self.hash_cache.sync_from_mayan(
                    self.mayan_client,
                    cabinet_id=self.directory_cabinet_id,
                    max_pages=100
                )
            else:
                logger.info(f"Кеш уже содержит {cache_count} записей, пропускаем синхронизацию")
            
            self._cache_initialized = True
        except Exception as e:
            logger.error(f"Ошибка синхронизации кеша: {e}", exc_info=True)
            self._cache_initialized = True  # Помечаем как инициализированный, чтобы не повторять
    
    def _calculate_file_hash(self, file_content: bytes) -> str:
        """
        Вычисляет SHA256 хеш файла
        
        Args:
            file_content: Содержимое файла в байтах
        
        Returns:
            SHA256 хеш в виде hex-строки
        """
        return hashlib.sha256(file_content).hexdigest()
    
    def _format_file_metadata(
        self, 
        file_path: Path, 
        file_hash: Optional[str] = None, 
        file_size: Optional[int] = None
    ) -> str:
        """
        Форматирует метаданные файла для сохранения в description документа
        
        Args:
            file_path: Путь к файлу
            file_hash: SHA256 хеш файла (опционально)
            file_size: Размер файла в байтах (опционально)
        
        Returns:
            Отформатированная строка с метаданными
        """
        metadata_dict = {
            'source': 'directory',
            'file_path': str(file_path),
            'file_name': file_path.name,
            'file_directory': str(file_path.parent),
            'processed_date': datetime.now().isoformat()
        }
        
        # ВСЕГДА добавляем хеш и размер файла для надежной проверки дубликатов
        if file_hash:
            metadata_dict['file_hash'] = file_hash
        if file_size:
            metadata_dict['file_size'] = file_size
        
        # Форматируем как JSON для структурированного хранения
        try:
            return json.dumps(metadata_dict, ensure_ascii=False, indent=2)
        except Exception:
            # Fallback на простой текст
            return (
                f"Файл из директории\n"
                f"Путь: {file_path}\n"
                f"Имя: {file_path.name}\n"
                f"Обработано: {datetime.now().isoformat()}"
            )
    
    async def _check_duplicate(
        self, 
        file_path: Path,
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        exclude_document_id: Optional[str] = None
    ) -> bool:
        """
        Проверяет, существует ли уже документ с таким же хешем файла
        
        Args:
            file_path: Путь к файлу
            file_hash: SHA256 хеш файла
            file_size: Размер файла в байтах (опционально)
            exclude_document_id: ID документа, который нужно исключить из проверки
        
        Returns:
            True если дубликат найден, False иначе
        """
        if not file_hash:
            logger.warning(f"Проверка дубликатов без хеша для файла {file_path} - менее надежно!")
            return False
        
        # ПЕРВЫЙ ПРИОРИТЕТ: Проверка в локальном кеше (быстро!)
        if self.hash_cache.hash_exists(file_hash, cabinet_id=self.directory_cabinet_id):
            cached_doc = self.hash_cache.get_document_by_hash(file_hash, cabinet_id=self.directory_cabinet_id)
            if cached_doc and str(cached_doc['document_id']) != str(exclude_document_id):
                logger.warning(
                    f"ДУБЛИКАТ НАЙДЕН в кеше: документ {cached_doc['document_id']}, "
                    f"hash={file_hash[:32]}..., filename='{file_path.name}'"
                )
                return True
        
        # ВТОРОЙ ПРИОРИТЕТ: Проверка в Mayan (медленнее, но более полная)
        try:
            logger.debug(f"Проверка дубликатов в Mayan для файла '{file_path.name}'...")
            
            max_pages = 20  # Ограничиваем проверку в Mayan (кеш уже проверили)
            checked_documents = 0
            
            for page in range(1, max_pages + 1):
                try:
                    documents = await self.mayan_client.get_documents(
                        page=page,
                        page_size=100,
                        cabinet_id=self.directory_cabinet_id
                    )
                except Exception as e:
                    logger.error(f"Ошибка при получении страницы {page}: {e}")
                    break
                
                if not documents:
                    break
                
                checked_documents += len(documents)
                
                for doc in documents:
                    if exclude_document_id and str(doc.id) == str(exclude_document_id):
                        continue
                    
                    try:
                        if not doc.description:
                            continue
                        
                        try:
                            metadata = json.loads(doc.description)
                        except json.JSONDecodeError:
                            continue
                        
                        # Проверка по хешу
                        if metadata.get('file_hash') == file_hash:
                            logger.warning(
                                f"ДУБЛИКАТ НАЙДЕН в Mayan: документ {doc.id}, "
                                f"hash={file_hash[:32]}..., filename='{file_path.name}'"
                            )
                            # Добавляем в кеш для будущих проверок
                            self.hash_cache.add_hash(
                                file_hash=file_hash,
                                document_id=str(doc.id),
                                filename=metadata.get('file_name'),
                                message_id=None,
                                cabinet_id=self.directory_cabinet_id,
                                metadata=metadata
                            )
                            return True
                    
                    except Exception as e:
                        logger.debug(f"Ошибка обработки документа {doc.id}: {e}")
                        continue
            
            logger.debug(f"Дубликатов не найдено. Проверено {checked_documents} документов в Mayan")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке дубликатов в Mayan: {e}", exc_info=True)
            return False
    
    async def process_file(
        self, 
        file_path: Path,
        check_duplicates: bool = True
    ) -> Dict[str, Any]:
        """
        Обрабатывает файл и создает документ в Mayan EDMS
        
        Args:
            file_path: Путь к файлу для обработки
            check_duplicates: Проверять ли дубликаты перед созданием
        
        Returns:
            Словарь с результатом обработки
        """
        result = {
            'success': False,
            'document_id': None,
            'registered_number': None,
            'filename': file_path.name,
            'error': None
        }
        
        # Инициализируем тип документа и кабинет при первом использовании
        if self.directory_document_type_id is None or self.directory_cabinet_id is None:
            await self._init_document_type_and_cabinet()
        
        # Используем блокировку для предотвращения параллельного создания дубликатов
        async with self._processing_lock:
            try:
                # Проверяем существование файла
                if not file_path.exists():
                    result['error'] = f'Файл не существует: {file_path}'
                    return result
                
                if not file_path.is_file():
                    result['error'] = f'Путь не является файлом: {file_path}'
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
                file_hash = self._calculate_file_hash(file_content)
                
                logger.info(
                    f"Обработка файла: '{file_path.name}', hash={file_hash[:32]}..., "
                    f"size={file_size}, path={file_path}"
                )
                
                # Проверяем дубликаты перед созданием документа
                if check_duplicates:
                    if await self._check_duplicate(file_path, file_hash, file_size):
                        logger.warning(
                            f"ДУБЛИКАТ ОБНАРУЖЕН! Файл '{file_path.name}' с хешем {file_hash[:32]}... "
                            f"уже существует. Пропускаем создание."
                        )
                        result['error'] = 'Дубликат: документ уже существует'
                        return result
                
                # Формируем description с метаданными
                description = self._format_file_metadata(file_path, file_hash, file_size)
                
                # Создаем документ в Mayan EDMS
                document_result = await self.mayan_client.create_document_with_file(
                    label=file_path.name,
                    description=description,
                    filename=file_path.name,
                    file_content=file_content,
                    mimetype=mimetype,
                    document_type_id=self.directory_document_type_id,
                    cabinet_id=self.directory_cabinet_id,
                    language='rus'
                )
                
                if document_result and document_result.get('document_id'):
                    document_id = document_result['document_id']
                    
                    # КРИТИЧЕСКИ ВАЖНО: Добавляем хеш в кеш СРАЗУ после создания
                    self.hash_cache.add_hash(
                        file_hash=file_hash,
                        document_id=str(document_id),
                        filename=file_path.name,
                        message_id=None,
                        cabinet_id=self.directory_cabinet_id,
                        metadata=json.loads(description)
                    )
                    logger.info(
                        f"Документ {document_id} создан, хеш {file_hash[:32]}... добавлен в кеш"
                    )
                    
                    # Проверяем дубликаты после создания (исключая только что созданный)
                    duplicate_found = await self._check_duplicate(
                        file_path, file_hash, file_size, 
                        exclude_document_id=str(document_id)
                    )
                    
                    if duplicate_found:
                        logger.error(
                            f"КРИТИЧЕСКАЯ ОШИБКА: После создания документа {document_id} обнаружен дубликат!"
                        )
                    
                    # Извлекаем входящий номер
                    registered_number = await self._extract_registered_number(document_id, file_path.name)
                    
                    result['success'] = True
                    result['document_id'] = str(document_id)
                    result['registered_number'] = registered_number
                    
                    logger.info(
                        f"✓ Файл '{file_path.name}' сохранен как документ {document_id} "
                        f"(hash: {file_hash[:32]}...)"
                    )
                else:
                    result['error'] = 'Не удалось создать документ в Mayan EDMS'
                    logger.error(f"Не удалось создать документ для файла '{file_path.name}'")
                
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Ошибка при обработке файла '{file_path.name}': {e}", exc_info=True)
        
        return result
    
    async def _extract_registered_number(self, document_id: str, original_label: str) -> Optional[str]:
        """
        Извлекает входящий номер из документа Mayan EDMS
        
        Args:
            document_id: ID документа
            original_label: Исходный label
        
        Returns:
            Входящий номер или None
        """
        try:
            # Получаем актуальную информацию о документе
            document = await self.mayan_client.get_document(document_id)
            if document:
                # Mayan может изменить label при автоматической нумерации
                # Номер может быть в формате: "IN-2024-0001 - filename.pdf"
                label = document.label
                
                # Пытаемся извлечь номер из label
                # Формат может быть разным в зависимости от настроек Mayan
                import re
                
                # Ищем паттерны типа IN-2024-0001, ВХ-2024-001 и т.д.
                patterns = [
                    r'(IN-\d{4}-\d+)',      # IN-2024-0001
                    r'(ВХ-\d{4}-\d+)',      # ВХ-2024-001
                    r'(\d{4}-\d+)',         # 2024-0001
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, label)
                    if match:
                        return match.group(1)
                
                # Если паттерн не найден, возвращаем весь label
                return label
                
        except Exception as e:
            logger.warning(f"Не удалось извлечь номер из документа {document_id}: {e}")
        
        return None

