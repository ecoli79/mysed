# services/email_processor.py
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import logging
from services.mayan_connector import MayanClient
from models import IncomingEmail
from config.settings import config
import hashlib

logger = logging.getLogger(__name__)


class EmailProcessor:
    """Обработчик входящих писем - сохраняет только вложения в Mayan EDMS"""
    
    def __init__(self, mayan_client: MayanClient):
        self.mayan_client = mayan_client
        self.incoming_document_type_id: Optional[int] = None
        self.incoming_cabinet_id: Optional[int] = None
        # Инициализация типа документа и кабинета будет выполнена асинхронно при первом использовании
    
    async def _init_document_type_and_cabinet(self):
        """Инициализирует тип документа 'Входящие' и кабинет 'Входящие письма'"""
        if self.incoming_document_type_id is not None and self.incoming_cabinet_id is not None:
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
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации типа документа и кабинета: {e}")
    

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
        file_size: Optional[int] = None
    ) -> bool:
        """
        Проверяет, существует ли уже документ с таким же message_id и filename,
        или с таким же хешем файла (для более надежной проверки)
        
        Args:
            message_id: Message-ID письма
            filename: Имя файла вложения
            file_hash: SHA256 хеш файла (опционально, для более надежной проверки)
            file_size: Размер файла в байтах (опционально, для дополнительной проверки)
        
        Returns:
            True если дубликат найден, False иначе
        """
        if not message_id or not filename:
            return False
        
        try:
            # Ищем документы в кабинете "Входящие письма" за последние 90 дней
            from datetime import timedelta
            date_from = (datetime.now() - timedelta(days=90)).isoformat()
            
            # Проверяем несколько страниц документов
            for page in range(1, 11):  # До 10 страниц (1000 документов)
                documents = await self.mayan_client.get_documents(
                    page=page,
                    page_size=100,
                    cabinet_id=self.incoming_cabinet_id,
                    datetime_created__gte=date_from
                )
                
                if not documents:
                    break
                
                # Проверяем каждый документ
                for doc in documents:
                    try:
                        # Парсим description (JSON)
                        if doc.description:
                            import json
                            metadata = json.loads(doc.description)
                            
                            # Проверка 1: Совпадение message_id и filename (основная проверка)
                            if (metadata.get('email_message_id') == message_id and 
                                metadata.get('attachment_filename') == filename):
                                logger.info(
                                    f"Найден дубликат по message_id+filename: документ {doc.id} "
                                    f"(message_id: {message_id}, filename: {filename})"
                                )
                                return True
                            
                            # Проверка 2: Совпадение хеша файла (если хеш передан)
                            if file_hash and metadata.get('attachment_hash') == file_hash:
                                logger.info(
                                    f"Найден дубликат по хешу файла: документ {doc.id} "
                                    f"(hash: {file_hash[:16]}..., filename: {filename})"
                                )
                                return True
                            
                            # Проверка 3: Совпадение размера и имени файла (дополнительная проверка)
                            if (file_size and 
                                metadata.get('attachment_size') == file_size and
                                metadata.get('attachment_filename') == filename):
                                logger.info(
                                    f"Найден возможный дубликат по размеру+имени: документ {doc.id} "
                                    f"(size: {file_size}, filename: {filename})"
                                )
                                # Для этой проверки возвращаем True только если нет хеша
                                # (если есть хеш, он более надежен)
                                if not file_hash:
                                    return True
                            
                    except (json.JSONDecodeError, KeyError, AttributeError) as e:
                        # Если не удалось распарсить, пропускаем
                        logger.debug(f"Ошибка парсинга метаданных документа {doc.id}: {e}")
                        continue
            
            return False
            
        except Exception as e:
            logger.warning(f"Ошибка при проверке дубликатов: {e}")
            # В случае ошибки не блокируем создание документа
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
        
        # Добавляем хеш и размер файла, если они переданы
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
        
        try:
            filename = attachment.get('filename', f'attachment_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            file_content = attachment.get('content', b'')
            mimetype = attachment.get('mimetype', 'application/octet-stream')
            file_size = attachment.get('size', len(file_content))
            
            if not file_content:
                result['error'] = 'Вложение не содержит данных'
                return result
            
            # Вычисляем хеш файла для проверки дубликатов
            file_hash = self._calculate_file_hash(file_content)
            logger.debug(f"Хеш файла '{filename}': {file_hash[:16]}... (размер: {file_size} байт)")
            
            # Проверяем дубликаты перед созданием документа
            if check_duplicate:
                message_id = email_metadata.get('message_id', '')
                if await self._check_duplicate(message_id, filename, file_hash, file_size):
                    logger.warning(
                        f"Дубликат обнаружен: вложение '{filename}' из письма {message_id} уже обработано. Пропускаем."
                    )
                    result['error'] = 'Дубликат: документ уже существует'
                    return result
            
            # Формируем label для документа (Mayan автоматически присвоит номер)
            label = filename
            
            # Формируем description с метаданными письма (включая хеш и размер)
            description = self._format_email_metadata(email_metadata, filename, file_hash, file_size)
            
            # Создаем документ в Mayan EDMS
            document_result = await self.mayan_client.create_document_with_file(
                label=label,
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
                
                # Извлекаем входящий номер из label документа
                registered_number = await self._extract_registered_number(document_id, label)
                
                result['success'] = True
                result['document_id'] = str(document_id)
                result['registered_number'] = registered_number
                
                logger.info(
                    f"Вложение '{filename}' успешно сохранено как документ {document_id} "
                    f"с номером {registered_number} (hash: {file_hash[:16]}...)"
                )
            else:
                result['error'] = 'Не удалось создать документ в Mayan EDMS'
                logger.error(f"Не удалось создать документ для вложения '{filename}'")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Ошибка при обработке вложения '{filename}': {e}", exc_info=True)
        
        return result
    
    def _format_email_metadata(
            self, 
            email_metadata: Dict[str, Any], 
            filename: str, 
            file_hash: Optional[str] = None, 
            file_size: Optional[int] = None
        ) -> str:
        """
        Форматирует метаданные письма для сохранения в description документа
        
        Args:
            email_metadata: Метаданные письма
            filename: Имя файла вложения
        
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
    
    async def _check_duplicate(
            self, 
            message_id: str, 
            filename: str, 
            file_hash: Optional[str] = None,
            file_size: Optional[int] = None
        ) -> bool:
        """
        Проверяет, существует ли уже документ с таким же message_id и filename
        
        Args:
            message_id: Message-ID письма
            filename: Имя файла вложения
        
        Returns:
            True если дубликат найден, False иначе
        """
        if not message_id or not filename:
            return False
        
        try:
            # Ищем документы в кабинете "Входящие письма" за последние 90 дней
            # (чтобы не проверять все документы)
            from datetime import timedelta
            date_from = (datetime.now() - timedelta(days=90)).isoformat()
            
            # Получаем документы из кабинета
            documents = await self.mayan_client.get_documents(
                page=1,
                page_size=100,
                cabinet_id=self.incoming_cabinet_id,
                datetime_created__gte=date_from
            )
            
            # Проверяем каждый документ
            for doc in documents:
                try:
                    # Парсим description (JSON)
                    if doc.description:
                        import json
                        metadata = json.loads(doc.description)
                        
                        # Проверяем совпадение message_id и filename
                        if (metadata.get('email_message_id') == message_id and 
                            metadata.get('attachment_filename') == filename):
                            logger.debug(
                                f"Найден дубликат: документ {doc.id} "
                                f"(message_id: {message_id}, filename: {filename})"
                            )
                            return True
                except (json.JSONDecodeError, KeyError, AttributeError):
                    # Если не удалось распарсить, пропускаем
                    continue
            
            # Если не нашли в первой странице, проверяем следующие страницы
            # (но ограничиваемся разумным количеством)
            for page in range(2, 6):  # Проверяем до 5 страниц (500 документов)
                documents = await self.mayan_client.get_documents(
                    page=page,
                    page_size=100,
                    cabinet_id=self.incoming_cabinet_id,
                    datetime_created__gte=date_from
                )
                
                if not documents:
                    break
                
                for doc in documents:
                    try:
                        if doc.description:
                            import json
                            metadata = json.loads(doc.description)
                            if (metadata.get('email_message_id') == message_id and 
                                metadata.get('attachment_filename') == filename):
                                logger.debug(
                                    f"Найден дубликат: документ {doc.id} "
                                    f"(message_id: {message_id}, filename: {filename})"
                                )
                                return True
                    except (json.JSONDecodeError, KeyError, AttributeError):
                        continue
            
            return False
            
        except Exception as e:
            logger.warning(f"Ошибка при проверке дубликатов: {e}")
            # В случае ошибки не блокируем создание документа
            return False


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
            from datetime import timedelta
            date_from = (datetime.now() - timedelta(days=90)).isoformat()
            
            # Ищем все документы с таким message_id
            processed_filenames = set()
            
            # Проверяем несколько страниц документов
            for page in range(1, 11):  # До 10 страниц (1000 документов)
                documents = await self.mayan_client.get_documents(
                    page=page,
                    page_size=100,
                    cabinet_id=self.incoming_cabinet_id,
                    datetime_created__gte=date_from
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