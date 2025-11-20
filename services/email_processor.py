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
        self._init_document_type()
    
    def _init_document_type(self):
        """Инициализирует или создает тип документа для входящих вложений"""
        try:
            # Получаем список типов документов
            document_types = self.mayan_client.get_document_types()
            
            # Ищем тип "Входящее вложение" или "Входящий документ"
            incoming_type_name = getattr(config, 'mayan_incoming_document_type', 'Входящее вложение')
            
            for doc_type in document_types:
                if doc_type.get('label') == incoming_type_name:
                    self.incoming_document_type_id = doc_type['id']
                    logger.info(f"Найден тип документа для входящих: {incoming_type_name} (ID: {self.incoming_document_type_id})")
                    return
            
            # Если тип не найден, используем первый доступный или создаем новый
            if document_types:
                self.incoming_document_type_id = document_types[0]['id']
                logger.warning(f"Тип '{incoming_type_name}' не найден, используем '{document_types[0]['label']}' (ID: {self.incoming_document_type_id})")
            else:
                logger.error("Не найдено ни одного типа документа в Mayan EDMS")
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации типа документа: {e}")
    
    def process_email(self, email: IncomingEmail) -> Dict[str, Any]:
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
                    attachment_result = self._process_attachment(
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
    
    def _process_attachment(
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
            
            # Формируем label для документа (Mayan автоматически присвоит номер)
            # Можно использовать имя файла или тему письма
            label = filename
            
            # Формируем description с метаданными письма
            description = self._format_email_metadata(email_metadata, filename)
            
            # Создаем документ в Mayan EDMS
            # Mayan автоматически присвоит входящий номер согласно настройкам типа документа
            document_result = self.mayan_client.create_document_with_file(
                label=label,
                description=description,
                filename=filename,
                file_content=file_content,
                mimetype=mimetype,
                document_type_id=self.incoming_document_type_id,
                language='rus'
            )
            
            if document_result and document_result.get('document_id'):
                document_id = document_result['document_id']
                
                # Извлекаем входящий номер из label документа
                # (Mayan может изменить label при автоматической нумерации)
                registered_number = self._extract_registered_number(document_id, label)
                
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
    
    def _extract_registered_number(self, document_id: str, original_label: str) -> Optional[str]:
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
            document = self.mayan_client.get_document(document_id)
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