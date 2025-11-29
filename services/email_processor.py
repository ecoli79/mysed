# services/email_processor.py
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import logging
from services.mayan_connector import MayanClient
from models import IncomingEmail
from config.settings import config

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
    
    async def process_email(self, email: IncomingEmail) -> Dict[str, Any]:
        """
        Обрабатывает письмо и сохраняет вложения в Mayan EDMS
        
        Args:
            email: Объект входящего письма
        
        Returns:
            Словарь с результатами обработки:
            {
                'success': bool,
                'processed_attachments': List[Dict],  # Список обработанных вложений
                'registered_numbers': List[str],      # Список присвоенных номеров
                'errors': List[str]                   # Список ошибок
            }
        """
        result = {
            'success': False,
            'processed_attachments': [],
            'registered_numbers': [],
            'errors': []
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
            
            logger.info(f"Обрабатываем письмо {email.message_id} с {len(email.attachments)} вложением(ями)")
            
            # Обрабатываем каждое вложение как отдельный документ
            for idx, attachment in enumerate(email.attachments):
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
                        }
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
            
            # Успех если хотя бы одно вложение обработано
            result['success'] = len(result['processed_attachments']) > 0
            
            if result['success']:
                logger.info(
                    f"Успешно обработано {len(result['processed_attachments'])} вложений из письма {email.message_id}. "
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
    
    async def _process_attachment(
        self, 
        attachment: Dict[str, Any], 
        email_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Обрабатывает одно вложение и создает документ в Mayan EDMS
        
        Args:
            attachment: Словарь с данными вложения:
                {
                    'filename': str,
                    'content': bytes,
                    'mimetype': str,
                    'size': int
                }
            email_metadata: Метаданные письма для сохранения в description
        
        Returns:
            Словарь с результатом:
            {
                'success': bool,
                'document_id': Optional[str],
                'registered_number': Optional[str],
                'filename': str,
                'error': Optional[str]
            }
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
            
            if not file_content:
                result['error'] = 'Вложение не содержит данных'
                return result
            
            # Проверяем дубликаты перед созданием документа
            message_id = email_metadata.get('message_id', '')
            if await self._check_duplicate(message_id, filename):
                logger.warning(
                    f"Дубликат обнаружен: вложение '{filename}' из письма {message_id} уже обработано. Пропускаем."
                )
                result['error'] = 'Дубликат: документ уже существует'
                return result
            
            # Формируем label для документа (Mayan автоматически присвоит номер)
            # Можно использовать имя файла или тему письма
            label = filename
            
            # Формируем description с метаданными письма
            description = self._format_email_metadata(email_metadata, filename)
            
            # Создаем документ в Mayan EDMS
            # Mayan автоматически присвоит входящий номер согласно настройкам типа документа
            # Документ будет иметь тип "Входящие" и попадет в кабинет "Входящие письма"
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
                # (Mayan может изменить label при автоматической нумерации)
                registered_number = await self._extract_registered_number(document_id, label)
                
                result['success'] = True
                result['document_id'] = str(document_id)
                result['registered_number'] = registered_number
                
                logger.info(
                    f"Вложение '{filename}' успешно сохранено как документ {document_id} "
                    f"с номером {registered_number}"
                )
            else:
                result['error'] = 'Не удалось создать документ в Mayan EDMS'
                logger.error(f"Не удалось создать документ для вложения '{filename}'")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Ошибка при обработке вложения '{filename}': {e}", exc_info=True)
        
        return result
    
    def _format_email_metadata(self, email_metadata: Dict[str, Any], filename: str) -> str:
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
    
    async def _check_duplicate(self, message_id: str, filename: str) -> bool:
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