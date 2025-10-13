import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import json
from typing import List, Optional, Dict, Any, Union
from urllib.parse import urljoin
import os
import base64

# for SSL warnings disable
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import logging

logger = logging.getLogger(__name__)


class MayanDocument:
    """Модель документа Mayan EDMS"""
    def __init__(self, document_id: str, label: str, description: str = "", 
                 file_latest_id: str = "", file_latest_filename: str = "",
                 file_latest_mimetype: str = "", file_latest_size: int = 0,
                 datetime_created: str = "", datetime_modified: str = ""):
        self.document_id = document_id
        self.label = label
        self.description = description
        self.file_latest_id = file_latest_id
        self.file_latest_filename = file_latest_filename
        self.file_latest_mimetype = file_latest_mimetype
        self.file_latest_size = file_latest_size
        self.datetime_created = datetime_created
        self.datetime_modified = datetime_modified
    
    def __str__(self):
        return f"MayanDocument(id={self.document_id}, label='{self.label}', filename='{self.file_latest_filename}')"


class MayanClient:
    """Клиент для работы с Mayan EDMS REST API"""
    
    def __init__(self, base_url: str, username: str = "", password: str = "", 
                 api_token: str = "", verify_ssl: bool = False):
        """
        Инициализация клиента Mayan EDMS
        
        Args:
            base_url: Базовый URL Mayan EDMS сервера (например: http://172.19.228.72)
            username: Имя пользователя для аутентификации (если не используется токен)
            password: Пароль для аутентификации (если не используется токен)
            api_token: API токен для аутентификации (приоритет над username/password)
            verify_ssl: Проверять ли SSL сертификаты
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = urljoin(self.base_url, '/api/v4/')
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.verify = verify_ssl
                
        logger.info(f"Инициализация MayanClient для {self.base_url}")
        
        # Настройка аутентификации
        if api_token:
            self.session.headers.update({
                'Authorization': f'Token {api_token}'
            })
            logger.info(f"🔐 MayanClient: Используется API токен для аутентификации")
            logger.info(f"🔐 MayanClient: Токен: {api_token[:10]}...{api_token[-5:] if len(api_token) > 15 else '***'}")
        elif username and password:
            self.session.auth = HTTPBasicAuth(username, password)
            logger.info(f"🔐 MayanClient: Используется username/password для аутентификации")
            logger.info(f"🔐 MayanClient: Пользователь: {username}")
            logger.info(f"🔐 MayanClient: Пароль: {'*' * len(password) if password else 'НЕ УКАЗАН'}")
        else:
            raise ValueError("Необходимо указать либо API токен, либо username/password")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Выполняет HTTP запрос к Mayan EDMS API"""
        url = urljoin(self.api_url, endpoint.lstrip('/'))
        
        logger.debug(f"🌐 MayanClient: Выполняем {method} запрос к {url}")
        
        # Логируем способ аутентификации для каждого запроса
        if hasattr(self.session, 'auth') and self.session.auth:
            logger.debug(f"🌐 MayanClient: Аутентификация через Basic Auth (username/password)")
        elif 'Authorization' in self.session.headers:
            auth_header = self.session.headers['Authorization']
            if auth_header.startswith('Token '):
                token = auth_header[6:]  # Убираем "Token "
                logger.debug(f"🌐 MayanClient: Аутентификация через API токен: {token[:10]}...{token[-5:] if len(token) > 15 else '***'}")
            else:
                logger.debug(f"🌐 MayanClient: Аутентификация через заголовок Authorization")
        else:
            logger.warning(f"🌐 MayanClient: Запрос без аутентификации!")
        
        # Устанавливаем Content-Type только если передаем JSON и НЕ передаем файлы
        if 'json' in kwargs and 'files' not in kwargs:
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        
        # Добавляем логирование для загрузки файлов
        if 'files' in kwargs:
            logger.info(f"🌐 MayanClient: Загружаем файлы: {list(kwargs['files'].keys())}")
            logger.info(f"🌐 MayanClient: Данные: {kwargs.get('data', {})}")
        
        try:
            response = self.session.request(method, url, **kwargs, verify=False)
            logger.debug(f"🌐 MayanClient: Ответ получен: {response.status_code}")
            
            # Проверяем на ошибки аутентификации
            if response.status_code == 401:
                logger.error("🌐 MayanClient: Ошибка аутентификации: токен или учетные данные недействительны")
                raise requests.RequestException("Ошибка аутентификации. Проверьте токен или учетные данные.")
            elif response.status_code == 403:
                logger.error("🌐 MayanClient: Ошибка авторизации: недостаточно прав доступа")
                raise requests.RequestException("Ошибка авторизации. Недостаточно прав доступа.")
            elif response.status_code >= 400:
                logger.warning(f"🌐 MayanClient: HTTP ошибка {response.status_code}: {response.text}")
            
            return response
        except requests.RequestException as e:
            logger.error(f"🌐 MayanClient: Ошибка при выполнении запроса {method} {url}: {e}")
            raise

    def create_user_api_token(self, username: str, password: str) -> Optional[str]:
        """
        Создает API токен для пользователя в Mayan EDMS используя endpoint /auth/token/obtain/
        
        Args:
            username: Имя пользователя
            password: Пароль пользователя
        
        Returns:
            API токен или None в случае ошибки
        """
        logger.info(f"🔑 MayanClient: Создаем API токен для пользователя {username}")
        
        try:
            # Используем найденный правильный endpoint
            endpoint = 'auth/token/obtain/'
            payload = {
                'username': username,
                'password': password
            }
            
            logger.info(f"🔑 MayanClient: Отправляем запрос на создание токена для {username}")
            logger.info(f"🔑 MayanClient: URL: {urljoin(self.api_url, endpoint)}")
            logger.info(f"🔑 MayanClient: Payload: {payload}")
            
            # Создаем запрос БЕЗ Basic Auth, так как endpoint сам аутентифицирует пользователя
            url = urljoin(self.api_url, endpoint)
            
            # Подготавливаем заголовки
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Выполняем запрос БЕЗ аутентификации
            import requests
            response = requests.post(
                url, 
                json=payload, 
                headers=headers,
                verify=False  # БЕЗ auth=temp_client.session.auth
            )
            
            logger.info(f"🔑 MayanClient: Статус ответа: {response.status_code}")
            logger.info(f"🔑 MayanClient: Заголовки ответа: {dict(response.headers)}")
            logger.info(f"🔑 MayanClient: Content-Type: {response.headers.get('Content-Type', 'Не указан')}")
            logger.info(f"🔑 MayanClient: Текст ответа (первые 1000 символов): {response.text[:1000]}")
            
            if response.status_code == 200:
                # Проверяем Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                
                if 'application/json' in content_type:
                    try:
                        token_data = response.json()
                        logger.info(f"🔑 MayanClient: JSON ответ получен: {token_data}")
                        
                        # Извлекаем токен из поля 'token' согласно схеме AuthToken
                        api_token = token_data.get('token')
                        
                        if api_token:
                            logger.info(f"🔑 MayanClient: API токен успешно создан для пользователя {username}")
                            logger.info(f"🔑 MayanClient: Токен: {api_token[:10]}...{api_token[-5:] if len(api_token) > 15 else '***'}")
                            return api_token
                        else:
                            logger.error(f"🔑 MayanClient: Поле 'token' не найдено в ответе")
                            logger.error(f"🔑 MayanClient: Доступные ключи: {list(token_data.keys())}")
                            logger.error(f"🔑 MayanClient: Полный ответ: {token_data}")
                            return None
                    except json.JSONDecodeError as e:
                        logger.error(f"🔑 MayanClient: Ошибка парсинга JSON: {e}")
                        logger.error(f"🔑 MayanClient: Ответ: {response.text[:500]}...")
                        return None
                else:
                    logger.error(f"🔑 MayanClient: Получен не JSON ответ, Content-Type: {content_type}")
                    logger.error(f"🔑 MayanClient: Возможно, неправильный endpoint или нужны другие параметры")
                    return None
            elif response.status_code == 401:
                logger.error(f"🔑 MayanClient: Ошибка аутентификации для пользователя {username} (401)")
                logger.error(f"🔑 MayanClient: Неверные учетные данные")
                return None
            elif response.status_code == 403:
                logger.error(f"🔑 MayanClient: Ошибка авторизации для пользователя {username} (403)")
                logger.error(f"🔑 MayanClient: Недостаточно прав для создания токена")
                return None
            else:
                logger.error(f"🔑 MayanClient: Ошибка создания API токена для пользователя {username}: {response.status_code}")
                logger.error(f"🔑 MayanClient: Текст ответа: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"🔑 MayanClient: Исключение при создании токена: {e}")
            import traceback
            logger.error(f"🔑 MayanClient: Traceback: {traceback.format_exc()}")
            return None

    def revoke_user_api_token(self, api_token: str) -> bool:
        """
        Отзывает API токен пользователя
        
        Args:
            api_token: API токен для отзыва
            
        Returns:
            True если токен успешно отозван, False иначе
        """
        logger.info("Отзываем API токен пользователя")
        
        try:
            endpoint = 'auth/token/revoke/'
            payload = {
                'token': api_token
            }
            
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.status_code == 200:
                logger.info("API токен успешно отозван")
                return True
            else:
                logger.error(f"Ошибка отзыва API токена: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Исключение при отзыве API токена: {e}")
            return False
    
    def get_documents(self, page: int = 1, page_size: int = 20, 
                     search: str = "", label: str = "") -> List[MayanDocument]:
        """
        Получает список документов из Mayan EDMS
        
        Args:
            page: Номер страницы
            page_size: Размер страницы
            search: Поисковый запрос
            label: Фильтр по метке документа
            
        Returns:
            Список документов
        """
        endpoint = 'documents/'
        params = {
            'page': page,
            'page_size': page_size
        }
        
        if search:
            params['label__icontains'] = search
        if label:
            params['label__icontains'] = label
        
        logger.info(f"Получаем документы: страница {page}, размер {page_size}, поиск: '{search}'")
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            documents = []
            
            logger.info(f"Получено {len(data.get('results', []))} документов")
            
            for doc_data in data.get('results', []):
                document = MayanDocument(
                    document_id=doc_data['id'],
                    label=doc_data['label'],
                    description=doc_data.get('description', ''),
                    file_latest_id=doc_data.get('file_latest', {}).get('id', ''),
                    file_latest_filename=doc_data.get('file_latest', {}).get('filename', ''),
                    file_latest_mimetype=doc_data.get('file_latest', {}).get('mimetype', ''),
                    file_latest_size=doc_data.get('file_latest', {}).get('size', 0),
                    datetime_created=doc_data.get('datetime_created', ''),
                    datetime_modified=doc_data.get('datetime_modified', '')
                )
                documents.append(document)
            
            return documents
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении документов: {e}")
            return []
    
    def get_document(self, document_id: str) -> Optional[MayanDocument]:
        """
        Получает конкретный документ по ID
        
        Args:
            document_id: ID документа
            
        Returns:
            Объект документа или None
        """
        endpoint = f'documents/{document_id}/'
        
        logger.info(f"Получаем документ с ID: {document_id}")
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            doc_data = response.json()
            logger.info(f"Документ получен: {doc_data.get('label', 'Без названия')}")
            
            return MayanDocument(
                document_id=doc_data['id'],
                label=doc_data['label'],
                description=doc_data.get('description', ''),
                file_latest_id=doc_data.get('file_latest', {}).get('id', ''),
                file_latest_filename=doc_data.get('file_latest', {}).get('filename', ''),
                file_latest_mimetype=doc_data.get('file_latest', {}).get('mimetype', ''),
                file_latest_size=doc_data.get('file_latest', {}).get('size', 0),
                datetime_created=doc_data.get('datetime_created', ''),
                datetime_modified=doc_data.get('datetime_modified', '')
            )
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении документа {document_id}: {e}")
            return None
    
    def get_document_file_content_as_text(self, document_id: str) -> Optional[str]:
        """
        Получает содержимое файла документа как текст
        
        Args:
            document_id: ID документа
            
        Returns:
            Содержимое файла как строка или None
        """
        logger.info(f"Получаем текстовое содержимое документа {document_id}")
        
        document_content = self.get_document_file_content(document_id)
        if not document_content:
            return None
        
        try:
            # Пытаемся декодировать как текст
            content = document_content.decode('utf-8')
            logger.info(f"Содержимое декодировано как UTF-8, размер: {len(content)} символов")
            return content
        except UnicodeDecodeError:
            try:
                # Пытаемся декодировать как Windows-1251
                content = document_content.decode('windows-1251')
                logger.info(f"Содержимое декодировано как Windows-1251, размер: {len(content)} символов")
                return content
            except UnicodeDecodeError:
                # Если не удается декодировать как текст, возвращаем информацию о файле
                logger.warning(f"Не удалось декодировать содержимое документа {document_id} как текст")
                document = self.get_document(document_id)
                if document:
                    return f"Файл: {document.file_latest_filename}\nТип: {document.file_latest_mimetype}\nРазмер: {document.file_latest_size} байт\n\nДля просмотра содержимого скачайте файл по ссылке."
                return None

    def get_document_info_for_review(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о документе для процесса ознакомления
        
        Args:
            document_id: ID документа
            
        Returns:
            Словарь с информацией о документе или None
        """
        logger.info(f"Получаем информацию о документе для ознакомления: {document_id}")
        
        document = self.get_document(document_id)
        if not document:
            return None
        
        return {
            'document_id': document.document_id,
            'label': document.label,
            'description': document.description,
            'filename': document.file_latest_filename,
            'mimetype': document.file_latest_mimetype,
            'size': document.file_latest_size,
            'download_url': self.get_document_file_url(document_id),
            'preview_url': self.get_document_preview_url(document_id),
            'content': self.get_document_file_content_as_text(document_id)
        }
    
    def get_document_files(self, document_id: str, page: int = 1, page_size: int = 20) -> Optional[Dict[str, Any]]:
        """
        Получает список файлов документа используя правильный endpoint /documents/{document_id}/files/
        
        Args:
            document_id: ID документа (обязательный)
            page: Номер страницы (обязательный)
            page_size: Размер страницы (обязательный)
            
        Returns:
            Словарь с данными о файлах или None
        """
        logger.info(f"Получаем файлы документа {document_id}, страница {page}, размер {page_size}")
        
        endpoint = f'documents/{document_id}/files/'
        params = {
            'page': page,
            'page_size': page_size
        }
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Получено {len(data.get('results', []))} файлов для документа {document_id}")
            
            return data
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении файлов документа {document_id}: {e}")
            return None

    def get_document_file_content(self, document_id: str) -> Optional[bytes]:
        """
        Получает содержимое файла документа используя правильный endpoint
        
        Args:
            document_id: ID документа
            
        Returns:
            Содержимое файла в байтах или None
        """
        logger.info(f"Получаем содержимое файла документа {document_id}")
        
        # Получаем список файлов документа используя правильный endpoint
        files_data = self.get_document_files(document_id, page=1, page_size=1)
        if not files_data or not files_data.get('results'):
            logger.warning(f"Документ {document_id} не найден или не имеет файлов")
            return None
        
        # Берем первый файл (обычно это последний загруженный файл)
        file_info = files_data['results'][0]
        file_id = file_info['id']  # ID файла
        
        logger.info(f"Найден файл с file_id: {file_id}, имя: {file_info.get('filename', 'Неизвестно')}")
        
        # Используем правильный endpoint для скачивания файла
        endpoint = f'documents/{document_id}/files/{file_id}/download/'
        
        try:
            logger.info(f"Скачиваем файл через endpoint: {endpoint}")
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            # Проверяем, что получили содержимое файла, а не HTML страницу
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                logger.warning(f"Endpoint {endpoint} вернул HTML вместо файла")
                return None
            
            logger.info(f"Файл успешно скачан, размер: {len(response.content)} байт")
            return response.content
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла через {endpoint}: {e}")
            return None

    def get_document_file_url(self, document_id: str) -> Optional[str]:
        """
        Получает URL для скачивания файла документа
        
        Args:
            document_id: ID документа
            
        Returns:
            URL для скачивания или None
        """
        # Получаем информацию о файлах документа
        files_data = self.get_document_files(document_id, page=1, page_size=1)
        if not files_data or not files_data.get('results'):
            return None
        
        file_info = files_data['results'][0]
        file_id = file_info['id']
        
        # Строим URL для скачивания используя правильный endpoint
        url = f"{self.api_url}documents/{document_id}/files/{file_id}/download/"
        logger.debug(f"URL для скачивания документа {document_id}: {url}")
        return url

    def search_documents(self, query: str, page: int = 1, page_size: int = 20) -> List[MayanDocument]:
        """
        Выполняет поиск документов
        
        Args:
            query: Поисковый запрос
            page: Номер страницы
            page_size: Размер страницы
            
        Returns:
            Список найденных документов
        """
        logger.info(f"Выполняем поиск документов по запросу: '{query}'")
        return self.get_documents(page=page, page_size=page_size, search=query)
    
    def get_document_preview_url(self, document_id: str) -> Optional[str]:
        """
        Получает URL для предварительного просмотра документа
        
        Args:
            document_id: ID документа
            
        Returns:
            URL для предварительного просмотра или None
        """
        # Получаем информацию о файлах документа
        files_data = self.get_document_files(document_id, page=1, page_size=1)
        if not files_data or not files_data.get('results'):
            return None
        
        file_info = files_data['results'][0]
        
        # Используем готовый image_url из ответа API для превью
        if 'pages_first' in file_info and 'image_url' in file_info['pages_first']:
            preview_url = file_info['pages_first']['image_url']
            logger.debug(f"URL для предварительного просмотра документа {document_id}: {preview_url}")
            return preview_url
        
        return None

    def get_all_document_files(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Получает все файлы документа
        
        Args:
            document_id: ID документа
            
        Returns:
            Список всех файлов документа
        """
        logger.info(f"Получаем все файлы документа {document_id}")
        
        all_files = []
        page = 1
        page_size = 100  # Большой размер страницы для получения всех файлов
        
        while True:
            files_data = self.get_document_files(document_id, page=page, page_size=page_size)
            if not files_data or not files_data.get('results'):
                break
            
            files = files_data['results']
            all_files.extend(files)
            
            # Проверяем, есть ли следующая страница
            if not files_data.get('next'):
                break
            
            page += 1
        
        logger.info(f"Получено {len(all_files)} файлов для документа {document_id}")
        return all_files

    def download_document_file(self, document_id: str, file_id: str) -> Optional[bytes]:
        """
        Скачивает конкретный файл документа по file_id
        
        Args:
            document_id: ID документа
            file_id: ID файла
            
        Returns:
            Содержимое файла в байтах или None
        """
        logger.info(f"Скачиваем файл {file_id} документа {document_id}")
        
        endpoint = f'documents/{document_id}/files/{file_id}/download/'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            # Проверяем, что получили содержимое файла, а не HTML страницу
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                logger.warning(f"Endpoint {endpoint} вернул HTML вместо файла")
                return None
            
            logger.info(f"Файл {file_id} скачан, размер: {len(response.content)} байт")
            return response.content
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла {file_id}: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Тестирует подключение к Mayan EDMS
        
        Returns:
            True если подключение успешно, False иначе
        """
        logger.info("Тестируем подключение к Mayan EDMS")
        
        try:
            response = self._make_request('GET', 'documents/')
            response.raise_for_status()
            logger.info("Подключение к Mayan EDMS успешно")
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка подключения к Mayan EDMS: {e}")
            return False

    def upload_document_result(self, task_id: str, process_instance_id: str, 
                             filename: str, file_content: bytes, 
                             mimetype: str, description: str = "") -> Optional[Dict[str, Any]]:
        """
        Загружает результат выполнения задачи в Mayan EDMS
        
        Args:
            task_id: ID задачи
            process_instance_id: ID экземпляра процесса
            filename: Имя файла
            file_content: Содержимое файла
            mimetype: MIME-тип файла
            description: Описание файла
            
        Returns:
            Словарь с информацией о загруженном документе или None
        """
        logger.info(f"Загружаем результат задачи {task_id} в Mayan EDMS")
        
        try:
            # Создаем документ в Mayan EDMS
            document_data = {
                'label': f'Результат задачи {task_id}',
                'description': f'Результат выполнения задачи {task_id} процесса {process_instance_id}\n{description}',
                'document_type': 'result',  # Предполагаем, что есть тип документа "result"
                'language': 'rus'
            }
            
            # Создаем документ
            create_response = self._make_request('POST', 'documents/', json=document_data)
            create_response.raise_for_status()
            document_info = create_response.json()
            document_id = document_info['id']
            
            logger.info(f"Документ создан с ID: {document_id}")
            
            # Загружаем файл
            upload_data = {
                'action_name': 'upload',  # Добавляем обязательное поле
                'description': description
            }

            files = {
                'file_new': (filename, file_content, mimetype)  # file_new вместо file
            }
            
            upload_response = self._make_request('POST', f'documents/{document_id}/files/', 
                                               data=upload_data, files=files)
            upload_response.raise_for_status()
            
            file_info = upload_response.json()
            logger.info(f"Файл загружен с ID: {file_info['id']}")
            
            # Активируем версию файла
            self._activate_file_version(document_id, file_info['id'])
            
            return {
                'document_id': document_id,
                'file_id': file_info['id'],
                'filename': filename,
                'mimetype': mimetype,
                'size': len(file_content),
                'download_url': self.get_document_file_url(document_id),
                'preview_url': self.get_document_preview_url(document_id)
            }
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при загрузке результата задачи {task_id}: {e}")
            return None

    def get_document_types(self) -> List[Dict[str, Any]]:
        """
        Получает список типов документов
        
        Returns:
            Список типов документов
        """
        endpoint = 'document_types/'
        
        logger.info("Получаем список типов документов")
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            data = response.json()
            document_types = data.get('results', [])
            
            logger.info(f"Получено {len(document_types)} типов документов")
            
            # Отладочная информация
            if document_types:
                logger.info(f"Пример типа документа: {json.dumps(document_types[0], indent=2, ensure_ascii=False)}")
            
            return document_types
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении типов документов: {e}")
            return []


    def get_cabinets(self) -> List[Dict[str, Any]]:
        """
        Получает список кабинетов документов
        
        Returns:
            Список кабинетов
        """
        endpoint = 'cabinets/'
        
        logger.info("Получаем список кабинетов")
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            data = response.json()
            cabinets = data.get('results', [])
            
            logger.info(f"Получено {len(cabinets)} кабинетов")
            
            # Отладочная информация
            if cabinets:
                logger.info(f"Пример кабинета: {json.dumps(cabinets[0], indent=2, ensure_ascii=False)}")
            
            return cabinets
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении кабинетов: {e}")
            return []

    def get_tags(self) -> List[Dict[str, Any]]:
        """
        Получает список тегов
        
        Returns:
            Список тегов
        """
        endpoint = 'tags/'
        
        logger.info("Получаем список тегов")
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            data = response.json()
            tags = data.get('results', [])
            
            logger.info(f"Получено {len(tags)} тегов")
            
            # Отладочная информация
            if tags:
                logger.info(f"Пример тега: {json.dumps(tags[0], indent=2, ensure_ascii=False)}")
            
            return tags
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении тегов: {e}")
            return []

    def get_languages(self) -> List[Dict[str, Any]]:
        """
        Получает список языков
        
        Returns:
            Список языков
        """
        endpoint = 'languages/'
        
        logger.info("Получаем список языков")
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            
            data = response.json()
            languages = data.get('results', [])
            
            logger.info(f"Получено {len(languages)} языков")
            
            # Отладочная информация
            if languages:
                logger.info(f"Пример языка: {json.dumps(languages[0], indent=2, ensure_ascii=False)}")
            
            return languages
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении языков: {e}")
            return []

    def _activate_file_version(self, document_id: int, file_id: int) -> bool:
        """
        Активирует версию файла в документе
        
        Args:
            document_id: ID документа
            file_id: ID файла
            
        Returns:
            True если активация успешна, False иначе
        """
        try:
            logger.info(f"Активируем версию файла {file_id} для документа {document_id}")
            
            # ИСПРАВЛЕНИЕ: Используем правильный endpoint для получения версий документа
            versions_response = self._make_request(
                'GET', 
                f'documents/{document_id}/versions/'
            )
            versions_response.raise_for_status()
            
            versions_data = versions_response.json()
            versions = versions_data.get('results', [])
            
            logger.info(f"Найдено версий документа: {len(versions)}")
            logger.info(f"Данные версий: {versions_data}")
            
            if not versions:
                logger.warning(f"Не найдено версий для документа {document_id}")
                return False
            
            # Берем последнюю версию (обычно это загруженная версия)
            latest_version = versions[-1]
            version_id = latest_version['id']
            
            logger.info(f"Найдена версия документа: {version_id}")
            logger.info(f"Информация о версии: {latest_version}")
            
            # Проверяем, активна ли уже эта версия
            if latest_version.get('active', False):
                logger.info(f"Версия {version_id} уже активна")
                return True
            
            # ИСПРАВЛЕНИЕ: Используем правильный endpoint для активации версии документа
            try:
                logger.info(f"Пробуем активировать версию {version_id} через document versions endpoint")
                activate_response = self._make_request(
                    'POST', 
                    f'documents/{document_id}/versions/{version_id}/activate/'
                )
                activate_response.raise_for_status()
                logger.info(f"Версия {version_id} успешно активирована")
                return True
            except Exception as e:
                logger.warning(f"Не удалось активировать версию через activate endpoint: {e}")
                
                # Альтернативный способ - через modify endpoint
                try:
                    logger.info(f"Пробуем активировать версию {version_id} через modify endpoint")
                    activate_data = {'action': 'activate'}
                    activate_response = self._make_request(
                        'POST', 
                        f'documents/{document_id}/versions/{version_id}/modify/', 
                        data=activate_data
                    )
                    activate_response.raise_for_status()
                    logger.info(f"Версия {version_id} успешно активирована через modify endpoint")
                    return True
                except Exception as e2:
                    logger.warning(f"Не удалось активировать версию через modify endpoint: {e2}")
                    return False
        
        except Exception as e:
            logger.warning(f"Не удалось активировать версию файла: {e}")
            return False

    def upload_file_to_document(self, document_id: int, filename: str, file_content: bytes, 
                            mimetype: str, description: str = "") -> Optional[Dict[str, Any]]:
        """
        Загружает файл к документу и активирует его версию
        """
        try:
            logger.info(f"Загружаем файл {filename} к документу {document_id}")
            
            # Загружаем файл
            upload_data = {
                'action_name': 'upload',
                'description': description
            }

            files = {
                'file_new': (filename, file_content, mimetype)
            }
            
            logger.info(f"Данные загрузки: {upload_data}")
            logger.info(f"Файл: {filename}, размер: {len(file_content)} байт, тип: {mimetype}")
            
            upload_response = self._make_request('POST', f'documents/{document_id}/files/', 
                                            data=upload_data, files=files)
            
            # Добавляем детальное логирование ответа
            logger.info(f"Статус ответа загрузки файла: {upload_response.status_code}")
            logger.info(f"Заголовки ответа: {dict(upload_response.headers)}")
            logger.info(f"Текст ответа: {upload_response.text[:500]}...")
            
            # ИСПРАВЛЕНИЕ: Обрабатываем статус 202 как успешный
            if upload_response.status_code in [200, 201, 202]:
                logger.info(f"Файл успешно загружен (статус {upload_response.status_code})")
                
                # Если ответ пустой (статус 202), получаем информацию о файле из списка файлов документа
                if upload_response.status_code == 202 and not upload_response.text.strip():
                    logger.info("Получен статус 202 с пустым ответом, получаем информацию о файле из списка файлов документа")
                    
                    # Получаем список файлов документа
                    files_response = self._make_request('GET', f'documents/{document_id}/files/')
                    files_response.raise_for_status()
                    
                    files_data = files_response.json()
                    files_list = files_data.get('results', [])
                    
                    logger.info(f"Найдено файлов в документе: {len(files_list)}")
                    
                    if files_list:
                        # Берем последний файл (обычно это загруженный файл)
                        latest_file = files_list[-1]
                        file_id = latest_file['id']
                        
                        logger.info(f"Найден файл с ID: {file_id}")
                        logger.info(f"Информация о файле: {latest_file}")
                        
                        # ДОБАВЛЯЕМ ЛОГИРОВАНИЕ: Активируем версию файла
                        logger.info(f"Начинаем активацию версии файла {file_id}")
                        activation_result = self._activate_file_version(document_id, file_id)
                        logger.info(f"Результат активации версии: {activation_result}")
                        
                        return {
                            'file_id': file_id,
                            'filename': filename,
                            'mimetype': mimetype,
                            'size': len(file_content),
                            'description': description
                        }
                    else:
                        logger.error("Не найдено файлов в документе")
                        return None
                else:
                    # Обычный случай - есть JSON ответ
                    file_info = upload_response.json()
                    file_id = file_info['id']
                    
                    logger.info(f"Файл загружен с ID: {file_id}")
                    
                    # ДОБАВЛЯЕМ ЛОГИРОВАНИЕ: Активируем версию файла
                    logger.info(f"Начинаем активацию версии файла {file_id}")
                    activation_result = self._activate_file_version(document_id, file_id)
                    logger.info(f"Результат активации версии: {activation_result}")
                    
                    return {
                        'file_id': file_id,
                        'filename': filename,
                        'mimetype': mimetype,
                        'size': len(file_content),
                        'description': description
                    }
            else:
                upload_response.raise_for_status()
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при загрузке файла к документу {document_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON ответа: {e}")
            logger.error(f"Ответ сервера: {upload_response.text if 'upload_response' in locals() else 'Неизвестно'}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке файла к документу {document_id}: {e}")
            return None

    def create_document_with_file(self, label: str, description: str, filename: str, 
                                file_content: bytes, mimetype: str, 
                                document_type_id: int = None, cabinet_id: int = None,
                                language: str = "rus") -> Optional[Dict[str, Any]]:
        """
        Создает документ с файлом используя правильный endpoint /documents/upload/
        согласно спецификации Mayan EDMS REST API
        """
        logger.info(f"Создаем документ с файлом через /documents/upload/: {label}")
        
        try:
            # Подготавливаем данные согласно спецификации
            upload_data = {
                "label": label,
                "description": description,
                "language": language,
                "file_latest": {
                    "comment": description,
                    "filename": filename
                },
                "version_active": {
                    "active": True,
                    "comment": description
                }
            }
            
            # Добавляем document_type если указан
            if document_type_id:
                upload_data["document_type_id"] = document_type_id
            
            logger.info(f"Данные для загрузки: {upload_data}")
            
            # Подготавливаем файл для загрузки
            files = {
                'file': (filename, file_content, mimetype)
            }
            
            # Выполняем запрос к правильному endpoint
            response = self._make_request(
                'POST', 
                'documents/upload/', 
                data=upload_data, 
                files=files
            )
            
            logger.info(f"Статус ответа: {response.status_code}")
            logger.info(f"Заголовки ответа: {dict(response.headers)}")
            logger.info(f"Текст ответа: {response.text[:500]}...")
            
            if response.status_code in [200, 201, 202]:
                try:
                    result = response.json()
                    document_id = result.get('id')
                    
                    logger.info(f"Документ успешно создан с ID: {document_id}")
                    
                    # Добавляем в кабинет если указан
                    if cabinet_id:
                        logger.info(f"Добавляем документ {document_id} в кабинет {cabinet_id}")
                        cabinet_result = self._add_document_to_cabinet(document_id, cabinet_id)
                        logger.info(f"Результат добавления в кабинет: {cabinet_result}")
                    
                    return {
                        'document_id': document_id,
                        'label': label,
                        'filename': filename,
                        'mimetype': mimetype,
                        'size': len(file_content),
                        'download_url': self.get_document_file_url(document_id),
                        'preview_url': self.get_document_preview_url(document_id)
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON ответа: {e}")
                    logger.error(f"Ответ сервера: {response.text}")
                    return None
            else:
                logger.error(f"Ошибка создания документа: {response.status_code}")
                logger.error(f"Ответ сервера: {response.text}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании документа с файлом: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при создании документа с файлом: {e}")
            return None

    def _add_document_to_cabinet(self, document_id: int, cabinet_id: int) -> bool:
        """
        Добавляет документ в кабинет
        
        Args:
            document_id: ID документа
            cabinet_id: ID кабинета
            
        Returns:
            True если добавление успешно, False иначе
        """
        try:
            logger.info(f"Добавляем документ {document_id} в кабинет {cabinet_id}")
            
            # ИСПРАВЛЕНИЕ: Используем правильный endpoint для добавления документа в кабинет
            # В Mayan EDMS нужно использовать PATCH метод для обновления кабинета
            try:
                logger.info(f"Пробуем добавить документ через PATCH метод")
                cabinet_data = {'documents': [document_id]}
                response = self._make_request(
                    'PATCH', 
                    f'cabinets/{cabinet_id}/', 
                    json=cabinet_data
                )
                response.raise_for_status()
                logger.info(f"Документ {document_id} успешно добавлен в кабинет {cabinet_id}")
                return True
            except Exception as e:
                logger.warning(f"PATCH метод не сработал: {e}")
                
                # Альтернативный способ - через документ
                try:
                    logger.info(f"Пробуем добавить документ через обновление документа")
                    document_data = {'cabinets': [cabinet_id]}
                    response = self._make_request(
                        'PATCH', 
                        f'documents/{document_id}/', 
                        json=document_data
                    )
                    response.raise_for_status()
                    logger.info(f"Документ {document_id} успешно добавлен в кабинет {cabinet_id}")
                    return True
                except Exception as e2:
                    logger.warning(f"Обновление документа не сработало: {e2}")
                    return False
        
        except Exception as e:
            logger.warning(f"Не удалось добавить документ в кабинет: {e}")
            return False


    @staticmethod
    def create_with_session_user() -> 'MayanClient':
        """
        Создает клиент Mayan EDMS с API токеном текущего пользователя из сессии
        
        Returns:
            Настроенный экземпляр MayanClient
        """
        try:
            # Импортируем здесь, чтобы избежать циклических импортов
            from auth.middleware import get_current_user
            from config.settings import config
            
            # Получаем текущего пользователя из сессии
            current_user = get_current_user()
            
            logger.info(f"🔧 MayanClient.create_with_session_user: current_user={current_user.username if current_user else 'None'}")
            
            if not current_user:
                logger.error("❌ MayanClient.create_with_session_user: current_user is None")
                raise ValueError("Пользователь не авторизован")
            
            # Проверяем наличие API токена у пользователя
            if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
                logger.error(f"❌ MayanClient.create_with_session_user: у пользователя {current_user.username} нет API токена")
                raise ValueError(f"У пользователя {current_user.username} нет API токена для доступа к Mayan EDMS")
            
            logger.info(f"✅ MayanClient.create_with_session_user: создаем клиент для пользователя {current_user.username}")
            
            # Создаем клиент с API токеном пользователя
            client = MayanClient(
                base_url=config.mayan_url,
                api_token=current_user.mayan_api_token
            )
            
            logger.info(f"✅ MayanClient.create_with_session_user: клиент создан успешно")
            return client
            
        except Exception as e:
            logger.error(f"❌ MayanClient.create_with_session_user: ошибка создания клиента: {e}")
            raise

    @staticmethod
    def create_with_user_credentials() -> 'MayanClient':
        """
        Создает клиент Mayan EDMS с учетными данными пользователя из конфигурации
        
        Returns:
            Настроенный экземпляр MayanClient
        """
        try:
            from config.settings import config
            
            if not config.mayan_username or not config.mayan_password:
                raise ValueError("Необходимо настроить MAYAN_USERNAME и MAYAN_PASSWORD")
            
            logger.info(f"🔧 MayanClient.create_with_user_credentials: создаем клиент с пользователем {config.mayan_username}")
            
            client = MayanClient(
                base_url=config.mayan_url,
                username=config.mayan_username,
                password=config.mayan_password
            )
            
            logger.info(f"✅ MayanClient.create_with_user_credentials: клиент создан успешно")
            return client
            
        except Exception as e:
            logger.error(f"❌ MayanClient.create_with_user_credentials: ошибка создания клиента: {e}")
            raise

    @staticmethod
    def create_with_api_token() -> 'MayanClient':
        """
        Создает клиент Mayan EDMS с API токеном из конфигурации
        
        Returns:
            Настроенный экземпляр MayanClient
        """
        try:
            from config.settings import config
            
            if not config.mayan_api_token:
                raise ValueError("Необходимо настроить MAYAN_API_TOKEN")
            
            logger.info(f"🔧 MayanClient.create_with_api_token: создаем клиент с API токеном")
            
            client = MayanClient(
                base_url=config.mayan_url,
                api_token=config.mayan_api_token
            )
            
            logger.info(f"✅ MayanClient.create_with_api_token: клиент создан успешно")
            return client
            
        except Exception as e:
            logger.error(f"❌ MayanClient.create_with_api_token: ошибка создания клиента: {e}")
            raise

    @staticmethod
    def create_default() -> 'MayanClient':
        """
        Создает клиент Mayan EDMS с системными учетными данными из конфигурации
        
        Returns:
            Настроенный экземпляр MayanClient
        """
        try:
            from config.settings import config
            
            # Приоритет: API токен > пользователь/пароль
            if config.mayan_api_token:
                return MayanClient.create_with_api_token()
            elif config.mayan_username and config.mayan_password:
                return MayanClient.create_with_user_credentials()
            else:
                raise ValueError("Необходимо настроить либо MAYAN_API_TOKEN, либо MAYAN_USERNAME и MAYAN_PASSWORD")
            
        except Exception as e:
            logger.error(f"❌ MayanClient.create_default: ошибка создания клиента: {e}")
            raise


def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return MayanClient.create_with_session_user()