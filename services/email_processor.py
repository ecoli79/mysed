# services/email_processor.py
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
import json
from services.mayan_connector import MayanClient
from services.document_hash_cache import DocumentHashCache
from models import IncomingEmail
from config.settings import config
import hashlib
import asyncio
from app_logging.logger import get_logger

logger = get_logger(__name__)


class EmailProcessor:
    """Обработчик входящих писем - сохраняет только вложения в Mayan EDMS"""
    
    def __init__(self, mayan_client: MayanClient, cache_db_path: Optional[str] = None):
        self.mayan_client = mayan_client
        self.incoming_document_type_id: Optional[int] = None
        self.incoming_cabinet_id: Optional[int] = None
        
        # Инициализируем кеш хешей документов
        self.hash_cache = DocumentHashCache(cache_db_path=cache_db_path)
        
        # Блокировка для предотвращения race condition
        self._processing_lock = asyncio.Lock()
        
        # Флаг инициализации кеша
        self._cache_initialized = False
        
        # Инициализация типа документа и кабинета будет выполнена асинхронно при первом использовании
    
    async def _init_document_type_and_cabinet(self):
        """Инициализирует тип документа 'Входящие' и кабинет 'Входящие письма'"""
        if self.incoming_document_type_id is not None and self.incoming_cabinet_id is not None:
            # Если уже инициализировано, синхронизируем кеш если нужно
            if not self._cache_initialized:
                await self._sync_hash_cache()
            return  # Уже инициализировано
        
        try:
            # Получаем список типов документов
            document_types = await self.mayan_client.get_document_types()
            
            # Ищем тип документа из конфигурации (по умолчанию "Входящие")
            incoming_type_name = config.mayan_incoming_document_type
            
            for doc_type in document_types:
                if doc_type.get('label') == incoming_type_name:
                    self.incoming_document_type_id = doc_type['id']
                    logger.info(f"Найден тип документа для входящих: {incoming_type_name} (ID: {self.incoming_document_type_id})")
                    break
            
            # Если тип не найден, используем первый доступный
            if self.incoming_document_type_id is None:
                if document_types:
                    self.incoming_document_type_id = document_types[0]['id']
                    logger.warning(f"Тип '{incoming_type_name}' не найден, используем '{document_types[0]['label']}' (ID: {self.incoming_document_type_id})")
                else:
                    logger.error("Не найдено ни одного типа документа в Mayan EDMS")
            
            # Получаем список кабинетов
            cabinets = await self.mayan_client.get_cabinets()
            
            # Ищем кабинет из конфигурации (по умолчанию "Входящие письма")
            incoming_cabinet_name = config.mayan_incoming_cabinet
            
            for cabinet in cabinets:
                if cabinet.get('label') == incoming_cabinet_name:
                    self.incoming_cabinet_id = cabinet['id']
                    logger.info(f"Найден кабинет для входящих: {incoming_cabinet_name} (ID: {self.incoming_cabinet_id})")
                    break
            
            # Если кабинет не найден, логируем предупреждение
            if self.incoming_cabinet_id is None:
                logger.warning(f"Кабинет '{incoming_cabinet_name}' не найден. Документы будут созданы без кабинета.")
                logger.info(f"Доступные кабинеты: {[c.get('label') for c in cabinets]}")
                
            # После инициализации синхронизируем кеш
            if self.incoming_cabinet_id is not None:
                await self._sync_hash_cache()
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации типа документа и кабинета: {e}")
    
    async def _sync_hash_cache(self):
        """Синхронизирует кеш хешей с документами из Mayan"""
        if self._cache_initialized:
            return
        
        try:
            cache_count = self.hash_cache.get_count(cabinet_id=self.incoming_cabinet_id)
            logger.info(f"Текущий размер кеша: {cache_count} записей")
            
            if cache_count == 0:
                logger.info("Кеш пуст, начинаем полную синхронизацию из Mayan...")
                await self.hash_cache.sync_from_mayan(
                    self.mayan_client,
                    cabinet_id=self.incoming_cabinet_id,
                    max_pages=100
                )
            else:
                logger.info(f"Кеш уже содержит {cache_count} записей, пропускаем синхронизацию")
            
            self._cache_initialized = True
        except Exception as e:
            logger.error(f"Ошибка синхронизации кеша: {e}", exc_info=True)
            self._cache_initialized = True  # Помечаем как инициализированный, чтобы не повторять

    async def process_email(
        self, 
        email: IncomingEmail, 
        check_duplicates: bool = True,
        processed_filenames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает письмо и сохраняет вложения в Mayan EDMS
        
        Args:
            email: Объект входящего письма
            check_duplicates: Проверять ли дубликаты (по умолчанию True)
            processed_filenames: Список уже обработанных имен файлов (для пропуска)
        
        Returns:
            Словарь с результатами обработки
        """
        result = {
            'success': False,
            'processed_attachments': [],
            'registered_numbers': [],
            'errors': [],
            'skipped': 0  # Количество пропущенных вложений
        }
        
        # Инициализируем тип документа и кабинет при первом использовании
        if self.incoming_document_type_id is None or self.incoming_cabinet_id is None:
            await self._init_document_type_and_cabinet()
        
        try:
            # Проверяем наличие вложений
            if not email.attachments or len(email.attachments) == 0:
                logger.info(f"Письмо {email.message_id} не содержит вложений, пропускаем")
                result['errors'].append('Письмо не содержит вложений')
                return result
            
            # Если передан список обработанных файлов, фильтруем вложения
            attachments_to_process = email.attachments
            if processed_filenames:
                attachments_to_process = await self.get_unprocessed_attachments(
                    email, 
                    processed_filenames
                )
                result['skipped'] = len(email.attachments) - len(attachments_to_process)
                
                if not attachments_to_process:
                    logger.info(
                        f"Все вложения из письма {email.message_id} уже обработаны. "
                        f"Пропущено: {result['skipped']}"
                    )
                    result['success'] = True  # Считаем успехом, если все уже обработаны
                    return result
            
            logger.info(
                f"Обрабатываем письмо {email.message_id} с {len(attachments_to_process)} "
                f"необработанным(и) вложением(ями) из {len(email.attachments)}"
            )
            
            # Обрабатываем каждое вложение
            for idx, attachment in enumerate(attachments_to_process):
                try:
                    attachment_result = await self._process_attachment(
                        attachment=attachment,
                        email_metadata={
                            'from': email.from_address,
                            'subject': email.subject,
                            'received_date': email.received_date.isoformat(),
                            'message_id': email.message_id,
                            'attachment_index': idx + 1,
                            'total_attachments': len(email.attachments)
                        },
                        check_duplicate=check_duplicates
                    )
                    
                    if attachment_result['success']:
                        result['processed_attachments'].append(attachment_result)
                        if attachment_result.get('registered_number'):
                            result['registered_numbers'].append(attachment_result['registered_number'])
                    else:
                        result['errors'].append(
                            f"Ошибка обработки вложения {attachment.get('filename', 'unknown')}: "
                            f"{attachment_result.get('error', 'Unknown error')}"
                        )
                        
                except Exception as e:
                    error_msg = f"Ошибка при обработке вложения {idx + 1}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    result['errors'].append(error_msg)
            
            # Успех если хотя бы одно вложение обработано или все уже были обработаны
            result['success'] = len(result['processed_attachments']) > 0 or result['skipped'] > 0
            
            if result['success']:
                logger.info(
                    f"Успешно обработано {len(result['processed_attachments'])} вложений из письма {email.message_id}. "
                    f"Пропущено (уже обработано): {result['skipped']}. "
                    f"Присвоены номера: {', '.join(result['registered_numbers'])}"
                )
            else:
                logger.warning(f"Не удалось обработать ни одного вложения из письма {email.message_id}")
            
            return result
            
        except Exception as e:
            error_msg = f"Критическая ошибка при обработке письма {email.message_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result['errors'].append(error_msg)
            return result

    def _calculate_file_hash(self, file_content: bytes) -> str:
        """
        Вычисляет SHA256 хеш файла
        
        Args:
            file_content: Содержимое файла в байтах
        
        Returns:
            SHA256 хеш в виде hex-строки
        """
        return hashlib.sha256(file_content).hexdigest()

    
    async def _check_duplicate(
        self, 
        message_id: str, 
        filename: str, 
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        exclude_document_id: Optional[str] = None
    ) -> bool:
        """
        Проверяет, существует ли уже документ с таким же message_id и filename,
        или с таким же хешем файла (для более надежной проверки)
        
        Args:
            message_id: Message-ID письма
            filename: Имя файла вложения
            file_hash: SHA256 хеш файла (опционально, для более надежной проверки)
            file_size: Размер файла в байтах (опционально, для дополнительной проверки)
            exclude_document_id: ID документа, который нужно исключить из проверки
        
        Returns:
            True если дубликат найден, False иначе
        """
        if not message_id or not filename:
            return False
        
        if not file_hash:
            logger.warning(f"Проверка дубликатов без хеша для файла {filename} - менее надежно!")
        
        # ПЕРВЫЙ ПРИОРИТЕТ: Проверка в локальном кеше (быстро!)
        if file_hash:
            if self.hash_cache.hash_exists(file_hash, cabinet_id=self.incoming_cabinet_id):
                cached_doc = self.hash_cache.get_document_by_hash(file_hash, cabinet_id=self.incoming_cabinet_id)
                if cached_doc and str(cached_doc['document_id']) != str(exclude_document_id):
                    logger.error(
                        f"ДУБЛИКАТ НАЙДЕН в кеше: документ {cached_doc['document_id']}, "
                        f"hash={file_hash[:32]}..., filename='{filename}'"
                    )
                    return True
        
        # ВТОРОЙ ПРИОРИТЕТ: Проверка в Mayan (медленнее, но более полная)
        try:
            logger.debug(f"Проверка дубликатов в Mayan для файла '{filename}'...")
            
            max_pages = 20  # Ограничиваем проверку в Mayan (кеш уже проверили)
            checked_documents = 0
            
            for page in range(1, max_pages + 1):
                try:
                    documents = await self.mayan_client.get_documents(
                        page=page,
                        page_size=100,
                        cabinet_id=self.incoming_cabinet_id
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
                        if file_hash and metadata.get('attachment_hash') == file_hash:
                            logger.error(
                                f"ДУБЛИКАТ НАЙДЕН в Mayan: документ {doc.id}, "
                                f"hash={file_hash[:32]}..., filename='{filename}'"
                            )
                            # Добавляем в кеш для будущих проверок
                            self.hash_cache.add_hash(
                                file_hash=file_hash,
                                document_id=str(doc.id),
                                filename=metadata.get('attachment_filename'),
                                message_id=metadata.get('email_message_id'),
                                cabinet_id=self.incoming_cabinet_id,
                                metadata=metadata
                            )
                            return True
                        
                        # Проверка по message_id + filename
                        if (metadata.get('email_message_id') == message_id and 
                            metadata.get('attachment_filename') == filename):
                            logger.error(
                                f"ДУБЛИКАТ НАЙДЕН по message_id+filename: документ {doc.id}"
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
    
    def _format_email_metadata(self, email_metadata: Dict[str, Any], filename: str, file_hash: Optional[str] = None, file_size: Optional[int] = None) -> str:
        """
        Форматирует метаданные письма для сохранения в description документа
        
        Args:
            email_metadata: Метаданные письма
            filename: Имя файла вложения
            file_hash: SHA256 хеш файла (опционально)
            file_size: Размер файла в байтах (опционально)
        
        Returns:
            Отформатированная строка с метаданными
        """
        metadata_dict = {
            'incoming_from_email': email_metadata.get('from', ''),
            'email_subject': email_metadata.get('subject', ''),
            'email_received_date': email_metadata.get('received_date', ''),
            'email_message_id': email_metadata.get('message_id', ''),
            'attachment_filename': filename,
            'attachment_number': email_metadata.get('attachment_index', 1),
            'total_attachments': email_metadata.get('total_attachments', 1),
            'processed_date': datetime.now().isoformat()
        }
        
        # ВСЕГДА добавляем хеш и размер файла для надежной проверки дубликатов
        if file_hash:
            metadata_dict['attachment_hash'] = file_hash
        if file_size:
            metadata_dict['attachment_size'] = file_size
        
        # Форматируем как JSON для структурированного хранения
        try:
            return json.dumps(metadata_dict, ensure_ascii=False, indent=2)
        except Exception:
            # Fallback на простой текст
            return (
                f"Входящее письмо\n"
                f"От: {email_metadata.get('from', 'Неизвестно')}\n"
                f"Тема: {email_metadata.get('subject', 'Без темы')}\n"
                f"Дата получения: {email_metadata.get('received_date', 'Неизвестно')}\n"
                f"Вложение: {filename}\n"
                f"Обработано: {datetime.now().isoformat()}"
            )
    
    async def _process_attachment(
        self, 
        attachment: Dict[str, Any], 
        email_metadata: Dict[str, Any],
        check_duplicate: bool = True
    ) -> Dict[str, Any]:
        """
        Обрабатывает одно вложение и создает документ в Mayan EDMS
        
        Args:
            attachment: Словарь с данными вложения
            email_metadata: Метаданные письма для сохранения в description
            check_duplicate: Проверять ли дубликаты перед созданием
        
        Returns:
            Словарь с результатом
        """
        result = {
            'success': False,
            'document_id': None,
            'registered_number': None,
            'filename': attachment.get('filename', 'unknown'),
            'error': None
        }
        
        # Используем блокировку для предотвращения параллельного создания дубликатов
        async with self._processing_lock:
            try:
                filename = attachment.get('filename', f'attachment_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
                file_content = attachment.get('content', b'')
                mimetype = attachment.get('mimetype', 'application/octet-stream')
                file_size = attachment.get('size', len(file_content))
                
                if not file_content:
                    result['error'] = 'Вложение не содержит данных'
                    return result
                
                # Вычисляем хеш файла
                file_hash = self._calculate_file_hash(file_content)
                message_id = email_metadata.get('message_id', '')
                
                logger.info(
                    f"Обработка вложения: '{filename}', hash={file_hash[:32]}..., "
                    f"size={file_size}, message_id={message_id}"
                )
                
                # Проверяем дубликаты перед созданием документа
                if check_duplicate:
                    if await self._check_duplicate(message_id, filename, file_hash, file_size):
                        logger.error(
                            f"ДУБЛИКАТ ОБНАРУЖЕН! Файл '{filename}' с хешем {file_hash[:32]}... "
                            f"уже существует. Пропускаем создание."
                        )
                        result['error'] = 'Дубликат: документ уже существует'
                        return result
                
                # Формируем description с метаданными
                description = self._format_email_metadata(email_metadata, filename, file_hash, file_size)
                
                # Создаем документ в Mayan EDMS
                document_result = await self.mayan_client.create_document_with_file(
                    label=filename,
                    description=description,
                    filename=filename,
                    file_content=file_content,
                    mimetype=mimetype,
                    document_type_id=self.incoming_document_type_id,
                    cabinet_id=self.incoming_cabinet_id,
                    language='rus'
                )
                
                if document_result and document_result.get('document_id'):
                    document_id = document_result['document_id']
                    
                    # КРИТИЧЕСКИ ВАЖНО: Добавляем хеш в кеш СРАЗУ после создания
                    self.hash_cache.add_hash(
                        file_hash=file_hash,
                        document_id=str(document_id),
                        filename=filename,
                        message_id=message_id,
                        cabinet_id=self.incoming_cabinet_id,
                        metadata=json.loads(description)
                    )
                    logger.info(
                        f"Документ {document_id} создан, хеш {file_hash[:32]}... добавлен в кеш"
                    )
                    
                    # Проверяем дубликаты после создания (исключая только что созданный)
                    duplicate_found = await self._check_duplicate(
                        message_id, filename, file_hash, file_size, 
                        exclude_document_id=str(document_id)
                    )
                    
                    if duplicate_found:
                        logger.error(
                            f"КРИТИЧЕСКАЯ ОШИБКА: После создания документа {document_id} обнаружен дубликат!"
                        )
                    
                    # Извлекаем входящий номер
                    registered_number = await self._extract_registered_number(document_id, filename)
                    
                    result['success'] = True
                    result['document_id'] = str(document_id)
                    result['registered_number'] = registered_number
                    
                    logger.info(
                        f"✓ Вложение '{filename}' сохранено как документ {document_id} "
                        f"(hash: {file_hash[:32]}...)"
                    )
                else:
                    result['error'] = 'Не удалось создать документ в Mayan EDMS'
                    logger.error(f"Не удалось создать документ для вложения '{filename}'")
                
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Ошибка при обработке вложения '{filename}': {e}", exc_info=True)
        
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


    async def check_email_processed(self, message_id: str) -> Dict[str, Any]:
        """
        Проверяет, было ли письмо уже обработано и какие вложения сохранены
        
        Args:
            message_id: Message-ID письма
            
        Returns:
            Словарь с информацией:
            {
                'is_processed': bool,              # Все ли вложения обработаны
                'processed_attachments': List[str], # Список обработанных имен файлов
                'total_found': int                 # Всего найдено документов для этого письма
            }
        """
        result = {
            'is_processed': False,
            'processed_attachments': [],
            'total_found': 0
        }
        
        if not message_id:
            return result
        
        try:
            # УБРАНО ограничение по дате - проверяем ВСЕ документы
            # Ищем все документы с таким message_id
            processed_filenames = set()
            
            # Проверяем больше страниц для надежности
            for page in range(1, 101):  # До 100 страниц (10000 документов)
                documents = await self.mayan_client.get_documents(
                    page=page,
                    page_size=100,
                    cabinet_id=self.incoming_cabinet_id
                    # УБРАНО datetime_created__gte - проверяем все документы
                )
                
                if not documents:
                    break
                
                for doc in documents:
                    try:
                        if doc.description:
                            import json
                            metadata = json.loads(doc.description)
                            
                            if metadata.get('email_message_id') == message_id:
                                result['total_found'] += 1
                                filename = metadata.get('attachment_filename')
                                if filename:
                                    processed_filenames.add(filename)
                    except (json.JSONDecodeError, KeyError, AttributeError):
                        continue
            
            result['processed_attachments'] = list(processed_filenames)
            # Считаем письмо обработанным, если найдены документы
            # (полную проверку делаем в process_email, сравнивая с количеством вложений)
            result['is_processed'] = len(processed_filenames) > 0
            
        except Exception as e:
            logger.warning(f"Ошибка при проверке статуса письма {message_id}: {e}")
        
        return result

    async def get_unprocessed_attachments(
        self, 
        email: IncomingEmail, 
        processed_filenames: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Возвращает список вложений, которые еще не были обработаны
        
        Args:
            email: Объект письма
            processed_filenames: Список уже обработанных имен файлов
            
        Returns:
            Список необработанных вложений
        """
        processed_set = set(processed_filenames)
        unprocessed = []
        
        for attachment in email.attachments:
            filename = attachment.get('filename', '')
            if filename not in processed_set:
                unprocessed.append(attachment)
            else:
                logger.info(
                    f"Вложение '{filename}' из письма {email.message_id} уже обработано, пропускаем"
                )
        
        return unprocessed