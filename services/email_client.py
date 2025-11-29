# services/email_client.py
import asyncio
import aioimaplib
import poplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging
import ssl
import socket

from models import IncomingEmail
from config.settings import config

logger = logging.getLogger(__name__)

# Таймаут для подключения (в секундах)
CONNECTION_TIMEOUT = 30


class EmailClient:
    """Асинхронный клиент для работы с почтовым сервером (IMAP/POP3)"""
    
    def __init__(
        self,
        server: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        protocol: Optional[str] = None,
        timeout: int = CONNECTION_TIMEOUT
    ):
        """
        Инициализация клиента почтового сервера
        
        Args:
            server: Адрес почтового сервера (если None, берется из config)
            port: Порт сервера (если None, берется из config)
            username: Имя пользователя (если None, берется из config)
            password: Пароль (если None, берется из config)
            use_ssl: Использовать SSL/TLS (если None, берется из config)
            protocol: Протокол "imap" или "pop3" (если None, берется из config)
            timeout: Таймаут подключения в секундах (по умолчанию 30)
        """
        # Используем переданные параметры или берем из конфигурации
        self.server = server or config.email_server
        self.port = port or config.email_port
        self.username = username or config.email_username
        self.password = password or config.email_password
        self.use_ssl = use_ssl if use_ssl is not None else config.email_use_ssl
        self.protocol = (protocol or config.email_protocol).lower()
        self.timeout = timeout
        
        self.connection = None
        self.mailbox = "INBOX"  # По умолчанию используем входящие
        
        # Валидация
        if not self.server:
            raise ValueError("EMAIL_SERVER не настроен. Укажите в .env или передайте в конструктор")
        if not self.username:
            raise ValueError("EMAIL_USERNAME не настроен. Укажите в .env или передайте в конструктор")
        if not self.password:
            raise ValueError("EMAIL_PASSWORD не настроен. Укажите в .env или передайте в конструктор")
        
        if self.protocol not in ["imap", "pop3"]:
            raise ValueError(f"Неподдерживаемый протокол: {self.protocol}. Используйте 'imap' или 'pop3'")
        
        logger.info(f"Инициализирован EmailClient: {self.protocol.upper()} {self.server}:{self.port}")
    
    @classmethod
    def create_default(cls) -> 'EmailClient':
        """
        Создает клиент с настройками из конфигурации (.env)
        
        Returns:
            Настроенный экземпляр EmailClient
        """
        try:
            logger.info("Создаем EmailClient с настройками из конфигурации")
            return cls()
        except Exception as e:
            logger.error(f"Ошибка создания EmailClient: {e}")
            raise
    
    async def _connect_imap(self) -> bool:
        """Подключается к IMAP серверу с таймаутом"""
        try:
            logger.info(f"Подключение к IMAP серверу {self.server}:{self.port} (таймаут: {self.timeout}с)...")
            
            if self.use_ssl:
                # Создаем SSL контекст
                context = ssl.create_default_context()
                self.connection = aioimaplib.IMAP4_SSL(
                    host=self.server,
                    port=self.port,
                    ssl_context=context,
                    timeout=self.timeout
                )
            else:
                self.connection = aioimaplib.IMAP4(
                    host=self.server,
                    port=self.port,
                    timeout=self.timeout
                )
            
            # Ждем подключения
            await self.connection.wait_hello_from_server()
            
            # Если не используем SSL, но нужен STARTTLS
            if not self.use_ssl:
                await self.connection.starttls()
            
            # Аутентификация
            logger.debug("Выполняем аутентификацию...")
            await self.connection.login(self.username, self.password)
            
            # Выбираем почтовый ящик
            logger.debug(f"Выбираем почтовый ящик: {self.mailbox}")
            await self.connection.select(self.mailbox)
            
            logger.info(f"✅ Успешное подключение к IMAP серверу {self.server}:{self.port}")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Таймаут подключения к IMAP серверу {self.server}:{self.port}")
            return False
        except aioimaplib.IMAP4.error as e:
            logger.error(f"Ошибка IMAP: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка подключения к IMAP серверу: {e}", exc_info=True)
            return False
    
    async def _connect_pop3(self) -> bool:
        """Подключается к POP3 серверу с таймаутом (через asyncio.to_thread)"""
        try:
            logger.info(f"Подключение к POP3 серверу {self.server}:{self.port} (таймаут: {self.timeout}с)...")
            
            def _sync_connect():
                """Синхронная функция подключения к POP3"""
                if self.use_ssl:
                    conn = poplib.POP3_SSL(self.server, self.port, timeout=self.timeout)
                else:
                    conn = poplib.POP3(self.server, self.port, timeout=self.timeout)
                
                # Аутентификация
                conn.user(self.username)
                conn.pass_(self.password)
                
                return conn
            
            # Выполняем синхронное подключение в отдельном потоке
            self.connection = await asyncio.to_thread(_sync_connect)
            
            logger.info(f"✅ Успешное подключение к POP3 серверу {self.server}:{self.port}")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Таймаут подключения к POP3 серверу {self.server}:{self.port}")
            return False
        except poplib.error_proto as e:
            logger.error(f"Ошибка POP3: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка подключения к POP3 серверу: {e}", exc_info=True)
            return False
    
    async def connect(self) -> bool:
        """Подключается к почтовому серверу"""
        if self.protocol == "imap":
            return await self._connect_imap()
        else:
            return await self._connect_pop3()
    
    async def disconnect(self):
        """Отключается от почтового сервера"""
        try:
            if self.connection:
                if self.protocol == "imap":
                    await self.connection.close()
                    await self.connection.logout()
                else:
                    # Для POP3 используем asyncio.to_thread
                    def _sync_disconnect():
                        self.connection.quit()
                    
                    await asyncio.to_thread(_sync_disconnect)
                
                self.connection = None
                logger.info("Отключение от почтового сервера")
        except Exception as e:
            logger.warning(f"Ошибка при отключении: {e}")
    
    async def test_connection(self) -> bool:
        """Тестирует подключение к почтовому серверу"""
        try:
            if await self.connect():
                await self.disconnect()
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка тестирования подключения: {e}")
            return False
    
    def _decode_header(self, header_value: str) -> str:
        """Декодирует заголовок письма"""
        if not header_value:
            return ""
        
        try:
            decoded_parts = decode_header(header_value)
            decoded_string = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding)
                    else:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += part
            return decoded_string
        except Exception as e:
            logger.warning(f"Ошибка декодирования заголовка '{header_value}': {e}")
            return str(header_value)
    
    async def _parse_email_imap(self, msg_num: str) -> Optional[IncomingEmail]:
        """Парсит письмо из IMAP"""
        try:
            # Получаем письмо - используем BODY.PEEK[] чтобы не помечать как прочитанное
            result, data = await self.connection.fetch(msg_num, '(BODY.PEEK[])')
            if result != 'OK':
                logger.warning(f"Не удалось получить письмо {msg_num}: результат {result}")
                return None
            
            # Парсим email - структура данных от aioimaplib может быть разной
            # data может быть списком: [b'1 FETCH...', b'...', b'...', b'...'] где последние элементы - само письмо
            if not data or len(data) == 0:
                logger.warning(f"Пустой ответ для письма {msg_num}")
                return None
            
            raw_email = None
            
            # Ищем самый большой bytes или bytearray объект в data (это должно быть само письмо)
            # Пропускаем первый элемент, так как там обычно заголовок
            for item in data[1:]:
                if isinstance(item, (bytes, bytearray)) and len(item) > 1000:  # Минимальный размер письма
                    # Преобразуем bytearray в bytes
                    raw_email = bytes(item) if isinstance(item, bytearray) else item
                    break
            
            # Если не нашли в последующих элементах, проверяем первый элемент
            if raw_email is None:
                first_item = data[0]
                
                if isinstance(first_item, tuple) and len(first_item) >= 2:
                    # Структура: (b'1', (b'RFC822', b'...')) или (b'1', b'...')
                    second_item = first_item[1]
                    if isinstance(second_item, tuple) and len(second_item) >= 2:
                        # Вложенный кортеж: (b'RFC822', b'...')
                        raw_email = second_item[1]
                    elif isinstance(second_item, (bytes, bytearray)) and len(second_item) > 1000:
                        # Прямой bytes/bytearray: (b'1', b'...')
                        raw_email = bytes(second_item) if isinstance(second_item, bytearray) else second_item
                elif isinstance(first_item, list) and len(first_item) > 1:
                    for item in first_item[1:]:
                        if isinstance(item, (bytes, bytearray)) and len(item) > 1000:
                            raw_email = bytes(item) if isinstance(item, bytearray) else item
                            break
                elif isinstance(first_item, (bytes, bytearray)) and len(first_item) > 1000:
                    # Прямой bytes/bytearray (но обычно это заголовок)
                    raw_email = bytes(first_item) if isinstance(first_item, bytearray) else first_item
            
            # Если все еще не нашли, ищем рекурсивно
            if raw_email is None:
                def find_bytes(obj, depth=0):
                    """Рекурсивно ищем bytes или bytearray в структуре"""
                    if depth > 3:  # Ограничиваем глубину
                        return None
                    if isinstance(obj, (bytes, bytearray)) and len(obj) > 1000:  # Минимальный размер письма
                        return bytes(obj) if isinstance(obj, bytearray) else obj
                    if isinstance(obj, (tuple, list)):
                        for item in obj:
                            result = find_bytes(item, depth + 1)
                            if result:
                                return result
                    return None
                
                for item in data:
                    raw_email = find_bytes(item)
                    if raw_email:
                        break
            
            # Если все еще не bytes, логируем ошибку
            if not isinstance(raw_email, bytes):
                logger.error(f"Не удалось извлечь письмо {msg_num} из ответа сервера")
                logger.debug(f"Структура данных: длина data: {len(data)}")
                return None
            
            email_message = email.message_from_bytes(raw_email)
            
            # Извлекаем данные
            message_id = email_message.get('Message-ID', f'<{msg_num}@unknown>')
            from_address = self._decode_header(email_message.get('From', ''))
            subject = self._decode_header(email_message.get('Subject', ''))
            
            # Если нет адреса отправителя, используем значение по умолчанию
            if not from_address:
                from_address = email_message.get('From', 'unknown@unknown')
                logger.warning(f"Письмо {msg_num} не имеет адреса отправителя, используем: {from_address}")
            
            # Парсим дату
            date_str = email_message.get('Date', '')
            try:
                received_date = parsedate_to_datetime(date_str)
            except Exception:
                received_date = datetime.now()
            
            # Извлекаем тело письма
            body = self._extract_body(email_message)
            
            # Извлекаем вложения
            attachments = self._extract_attachments(email_message)
            
            try:
                email_obj = IncomingEmail(
                    message_id=message_id,
                    from_address=from_address,
                    subject=subject,
                    body=body,
                    received_date=received_date,
                    attachments=attachments
                )
                logger.debug(f"Успешно распарсено письмо {msg_num}: {message_id}")
                return email_obj
            except Exception as validation_error:
                logger.error(f"Ошибка валидации Pydantic для письма {msg_num}: {validation_error}")
                logger.debug(f"Данные письма: message_id={message_id}, from={from_address}, subject={subject[:50]}")
                return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга письма {msg_num}: {e}", exc_info=True)
            return None
    
    async def _parse_email_pop3(self, msg_num: int) -> Optional[IncomingEmail]:
        """Парсит письмо из POP3"""
        try:
            # Получаем письмо через asyncio.to_thread
            def _sync_retr():
                lines = self.connection.retr(msg_num)[1]
                return b'\n'.join(lines)
            
            raw_email = await asyncio.to_thread(_sync_retr)
            
            # Парсим email
            email_message = email.message_from_bytes(raw_email)
            
            # Извлекаем данные
            message_id = email_message.get('Message-ID', f'<{msg_num}@unknown>')
            from_address = self._decode_header(email_message.get('From', ''))
            subject = self._decode_header(email_message.get('Subject', ''))
            
            # Парсим дату
            date_str = email_message.get('Date', '')
            try:
                received_date = parsedate_to_datetime(date_str)
            except Exception:
                received_date = datetime.now()
            
            # Извлекаем тело письма
            body = self._extract_body(email_message)
            
            # Извлекаем вложения
            attachments = self._extract_attachments(email_message)
            
            return IncomingEmail(
                message_id=message_id,
                from_address=from_address,
                subject=subject,
                body=body,
                received_date=received_date,
                attachments=attachments
            )
            
        except Exception as e:
            logger.error(f"Ошибка парсинга письма {msg_num}: {e}", exc_info=True)
            return None
    
    def _extract_body(self, email_message: email.message.Message) -> str:
        """Извлекает тело письма"""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Пропускаем вложения
                if "attachment" in content_disposition:
                    continue
                
                # Извлекаем текст
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body += payload.decode(charset, errors='ignore')
                    except Exception as e:
                        logger.warning(f"Ошибка извлечения текста: {e}")
        else:
            # Простое письмо
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    charset = email_message.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
            except Exception as e:
                logger.warning(f"Ошибка извлечения текста: {e}")
        
        return body
    
    def _extract_attachments(self, email_message: email.message.Message) -> List[Dict[str, Any]]:
        """Извлекает вложения из письма"""
        attachments = []
        
        if not email_message.is_multipart():
            return attachments
        
        for part in email_message.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Проверяем, является ли часть вложением
            if "attachment" in content_disposition or part.get_filename():
                try:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                    
                    # Получаем содержимое вложения
                    payload = part.get_payload(decode=True)
                    if payload:
                        content_type = part.get_content_type()
                        
                        attachments.append({
                            'filename': filename or f'attachment_{len(attachments) + 1}',
                            'content': payload,
                            'mimetype': content_type,
                            'size': len(payload)
                        })
                        
                        logger.debug(f"Извлечено вложение: {filename} ({len(payload)} байт)")
                        
                except Exception as e:
                    logger.warning(f"Ошибка извлечения вложения: {e}")
        
        return attachments
    
    async def fetch_unread_emails(self, max_count: Optional[int] = None) -> List[IncomingEmail]:
        """
        Получает список непрочитанных писем
        
        Args:
            max_count: Максимальное количество писем для получения
        
        Returns:
            Список объектов IncomingEmail
        """
        emails = []
        
        try:
            if not self.connection:
                if not await self.connect():
                    return emails
            
            if self.protocol == "imap":
                # Ищем непрочитанные письма
                result, messages = await self.connection.search(None, 'UNSEEN')
                if result != 'OK':
                    logger.warning("Не удалось найти непрочитанные письма")
                    return emails
                
                # Декодируем bytes в строки
                if isinstance(messages[0], bytes):
                    message_ids = [msg_id.decode('utf-8') for msg_id in messages[0].split()]
                else:
                    message_ids = messages[0].split()
                
                # Ограничиваем количество
                if max_count:
                    message_ids = message_ids[:max_count]
                
                logger.info(f"Найдено {len(message_ids)} непрочитанных писем")
                
                # Парсим каждое письмо
                for msg_num in message_ids:
                    email_obj = await self._parse_email_imap(msg_num)
                    if email_obj:
                        emails.append(email_obj)
                    else:
                        logger.warning(f"Не удалось распарсить письмо {msg_num}")
            
            else:  # POP3
                # Получаем количество писем через asyncio.to_thread
                def _sync_list():
                    return len(self.connection.list()[1])
                
                num_messages = await asyncio.to_thread(_sync_list)
                
                # Ограничиваем количество
                if max_count:
                    num_messages = min(num_messages, max_count)
                
                logger.info(f"Найдено {num_messages} писем в почтовом ящике")
                
                # POP3 не различает прочитанные/непрочитанные, получаем все
                # В реальности нужно отслеживать уже обработанные письма
                for msg_num in range(1, num_messages + 1):
                    email_obj = await self._parse_email_pop3(msg_num)
                    if email_obj:
                        emails.append(email_obj)
            
            logger.info(f"Успешно получено {len(emails)} писем")
            
        except Exception as e:
            logger.error(f"Ошибка получения писем: {e}", exc_info=True)
        finally:
            # Не отключаемся, так как может понадобиться пометить письма как прочитанные
            pass
        
        return emails
    
    async def fetch_emails(self, max_count: Optional[int] = None, unread_only: bool = False) -> List[IncomingEmail]:
        """
        Получает список писем (все или только непрочитанные)
        
        Args:
            max_count: Максимальное количество писем для получения
            unread_only: Если True, получает только непрочитанные письма. 
                        Если False, получает все письма (включая прочитанные)
        
        Returns:
            Список объектов IncomingEmail
        """
        emails = []
        
        try:
            if not self.connection:
                if not await self.connect():
                    return emails
            
            if self.protocol == "imap":
                if unread_only:
                    # Ищем только непрочитанные письма
                    search_criteria = 'UNSEEN'
                    log_msg = "непрочитанных"
                else:
                    # Ищем все письма
                    search_criteria = 'ALL'
                    log_msg = "всех"
                
                result, messages = await self.connection.search(None, search_criteria)
                if result != 'OK':
                    logger.warning(f"Не удалось найти {log_msg} письма")
                    return emails
                
                # Декодируем bytes в строки
                if isinstance(messages[0], bytes):
                    message_ids = [msg_id.decode('utf-8') for msg_id in messages[0].split()]
                else:
                    message_ids = messages[0].split()
                
                # Если пустой результат (например, нет писем)
                if not message_ids or (isinstance(message_ids[0], bytes) and not message_ids[0]):
                    logger.info(f"Найдено 0 {log_msg} писем")
                    return emails
                
                # Преобразуем все message_ids в строки (на случай если они int)
                message_ids = [str(msg_id) if not isinstance(msg_id, str) else msg_id for msg_id in message_ids]
                
                # Ограничиваем количество
                if max_count:
                    message_ids = message_ids[:max_count]
                
                logger.info(f"Найдено {len(message_ids)} {log_msg} писем")
                
                # Парсим каждое письмо
                for msg_num in message_ids:
                    email_obj = await self._parse_email_imap(str(msg_num))
                    if email_obj:
                        emails.append(email_obj)
                    else:
                        logger.warning(f"Не удалось распарсить письмо {msg_num}")
            
            else:  # POP3
                # Получаем количество писем через asyncio.to_thread
                def _sync_list():
                    return len(self.connection.list()[1])
                
                num_messages = await asyncio.to_thread(_sync_list)
                
                # Ограничиваем количество
                if max_count:
                    num_messages = min(num_messages, max_count)
                
                logger.info(f"Найдено {num_messages} писем в почтовом ящике")
                
                # POP3 не различает прочитанные/непрочитанные, получаем все
                for msg_num in range(1, num_messages + 1):
                    email_obj = await self._parse_email_pop3(msg_num)
                    if email_obj:
                        emails.append(email_obj)
            
            logger.info(f"Успешно получено {len(emails)} писем")
            
        except Exception as e:
            logger.error(f"Ошибка получения писем: {e}", exc_info=True)
        finally:
            # Не отключаемся, так как может понадобиться пометить письма как прочитанные
            pass
        
        return emails
    
    async def mark_as_read(self, message_id: str) -> bool:
        """
        Помечает письмо как прочитанное (только для IMAP)
        
        Args:
            message_id: ID письма
        
        Returns:
            True если успешно, False иначе
        """
        if self.protocol != "imap":
            logger.warning("mark_as_read поддерживается только для IMAP")
            return False
        
        try:
            if not self.connection:
                if not await self.connect():
                    return False
            
            # Ищем письмо по Message-ID
            result, messages = await self.connection.search(None, f'HEADER Message-ID "{message_id}"')
            if result != 'OK' or not messages[0]:
                logger.warning(f"Письмо {message_id} не найдено")
                return False
            
            # Декодируем bytes в строки, если необходимо
            if isinstance(messages[0], bytes):
                msg_nums = [msg_num.decode('utf-8') for msg_num in messages[0].split()]
            else:
                msg_nums = messages[0].split()
            
            # Помечаем как прочитанное
            for msg_num in msg_nums:
                await self.connection.store(msg_num, '+FLAGS', '\\Seen')
            
            logger.info(f"Письмо {message_id} помечено как прочитанное")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка пометки письма как прочитанного: {e}")
            return False
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер: вход"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер: выход"""
        await self.disconnect()
    
    # Оставляем синхронные методы для обратной совместимости (deprecated)
    def __enter__(self):
        """Синхронный контекстный менеджер (deprecated)"""
        import warnings
        warnings.warn(
            "Использование синхронного контекстного менеджера устарело. Используйте 'async with'",
            DeprecationWarning,
            stacklevel=2
        )
        # Запускаем асинхронный код в новом event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.connect())
            return self
        finally:
            loop.close()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Синхронный контекстный менеджер (deprecated)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.disconnect())
        finally:
            loop.close()