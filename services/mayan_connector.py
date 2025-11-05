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
        self.documentSearchModelPk = None
        self.documentSearchModelUrl = None
                
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
    
    def _get_search_models_root(self) -> str:
        return 'search_models/'
    
    def get_search_models(self) -> list:
        root = self._get_search_models_root()
        page = 1
        out = []
        while True:
            resp = self._make_request('GET', root, params={'page': page, 'page_size': 100})
            resp.raise_for_status()
            data = resp.json()
            results = data.get('results') if isinstance(data, dict) else data
            if not results:
                break
            out.extend(results)
            if isinstance(data, dict) and not data.get('next'):
                break
            page += 1
        return out
    
    def _ensure_document_search_model(self) -> bool:
        if self.documentSearchModelPk and self.documentSearchModelUrl:
            return True
        try:
            root = self._get_search_models_root()
            page = 1
            while True:
                r = self._make_request('GET', root, params={'page': page, 'page_size': 100})
                r.raise_for_status()
                data = r.json()
                results = data.get('results') if isinstance(data, dict) else data
                if not results:
                    break
                for m in results:
                    if m.get('app_label') == 'documents' and m.get('model_name') == 'documentsearchresult':
                        pk = m.get('pk') or m.get('id')
                        url = m.get('url')
                        if pk and url:
                            # нормализуем в относительный путь для _make_request
                            rel = url[len(self.api_url):].lstrip('/') if url.startswith(self.api_url) else f"{root.rstrip('/')}/{pk}/"
                            self.documentSearchModelPk = pk
                            self.documentSearchModelUrl = rel
                            return True
                if isinstance(data, dict) and not data.get('next'):
                    break
                page += 1
        except Exception:
            pass
        return False

    def _search_via_short_model(self, query: str, page: int, page_size: int) -> List[MayanDocument]:
        """
        Полнотекст через короткий путь модели:
        GET /api/v4/search/documents.documentsearchresult[/?] ? q=...
        """
        candidates = [
            'search/documents.documentsearchresult',
            'search/documents.documentsearchresult/',
        ]
        last_exc = None
        import re

        for ep in candidates:
            try:
                resp = self._make_request('GET', ep, params={'q': query, 'page': page, 'page_size': page_size})
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                items = data.get('results', data if isinstance(data, list) else [])

                doc_ids = []
                for it in items:
                    did = (
                        it.get('id')
                        or it.get('object_id')
                        or it.get('document_id')
                        or it.get('document__id')
                    )
                    if not did:
                        url = it.get('url') or it.get('object_url')
                        if url:
                            m = re.search(r'/documents/(\d+)/', url)
                            if m:
                                did = m.group(1)
                    if did:
                        doc_ids.append(str(did))

                docs: List[MayanDocument] = []
                for did in doc_ids:
                    d = self.get_document(did)
                    if d:
                        docs.append(d)
                return docs
            except Exception as e:
                last_exc = e
                continue

        if last_exc:
            raise last_exc
        return []
    
    def _search_via_document_search_model(self, query: str, page: int, page_size: int) -> list:
        if not self._ensure_document_search_model():
            # ВАЖНО: нет модели — пусть верхний уровень решает fallback
            raise RuntimeError('documentsearchresult model not available')
        base = self.documentSearchModelUrl.rstrip('/')
        try:
            resp = self._make_request('GET', f'{base}/results/', params={'q': query, 'page': page, 'page_size': page_size})
            if resp.status_code == 404:
                resp = self._make_request('GET', f'{base}/results/', params={'query': query, 'page': page, 'page_size': page_size})
            resp.raise_for_status()
            data = resp.json()
            items = data.get('results', data if isinstance(data, list) else [])
        except Exception as e:
            # Если сам endpoint падает — пробуем title выше
            raise e

        import re
        docIds = []
        for it in items:
            did = (
                it.get('document_id')
                or it.get('document__id')
                or it.get('object_id')
                or it.get('id')  # иногда id совпадает с id документа, но не всегда
                or it.get('pk')
            )
            if not did:
                url = it.get('url') or it.get('object_url')
                if url:
                    m = re.search(r'/documents/(\d+)/', url)
                    if m:
                        did = m.group(1)
            if did:
                docIds.append(str(did))

        out = []
        for did in docIds:
            d = self.get_document(did)
            if d:
                out.append(d)
        return out
    
    def _fetch_results_for_model(self, model_pk: str, query: str, page: int, page_size: int) -> list:
        rel = self._ensure_search_model_by_pk(model_pk)
        if not rel:
            return []
        base = rel.rstrip('/')
        for params in ({'q': query}, {'query': query}):
            try:
                r = self._make_request('GET', f'{base}/results/', params={**params, 'page': page, 'page_size': page_size})
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
                return data.get('results', data if isinstance(data, list) else [])
            except Exception:
                continue
        return []
            
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
            'page_size': page_size,
            'ordering': '-datetime_created'
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
            
            for i, doc_data in enumerate(data.get('results', [])):
                try:
                    # Получаем file_latest из API
                    file_latest_data = doc_data.get('file_latest', {})
                    file_latest_filename = file_latest_data.get('filename', '')
                    
                    # Проверяем, не является ли это файлом подписи или метаданных
                    is_signature_file = (file_latest_filename.endswith('.p7s') or 
                                       'signature_metadata_' in file_latest_filename)
                    
                    # Если это файл подписи/метаданных, получаем основной файл из всех файлов документа
                    if is_signature_file:
                        logger.debug(f"Документ {doc_data['id']}: file_latest является файлом подписи/метаданных, ищем основной файл")
                        
                        try:
                            # Получаем все файлы документа напрямую
                            files_response = self._make_request('GET', f'documents/{doc_data["id"]}/files/', params={'page': 1, 'page_size': 100})
                            files_response.raise_for_status()
                            files_data = files_response.json()
                            all_files = files_data.get('results', [])
                            
                            logger.debug(f"Получено {len(all_files)} файлов для документа {doc_data['id']}")
                            
                            # Фильтруем файлы: исключаем подписи и метаданные
                            main_files = []
                            for file_info in all_files:
                                filename = file_info.get('filename', '')
                                # Пропускаем файлы подписей и метаданных
                                if filename.endswith('.p7s') or 'signature_metadata_' in filename:
                                    logger.debug(f"Пропускаем файл подписи/метаданных: {filename}")
                                    continue
                                main_files.append(file_info)
                            
                            # Если нашли основные файлы, берем самый старый (первый созданный)
                            # или предпочитаем файлы с определенными типами MIME
                            if main_files:
                                # Сортируем по datetime_created (если есть) или по ID
                                # Старшие ID обычно означают более ранние файлы
                                def get_sort_key(file_info):
                                    # ИСПРАВЛЕНИЕ: Обрабатываем случай, когда mimetype может быть None
                                    mimetype = file_info.get('mimetype') or ''
                                    if mimetype:
                                        mimetype = str(mimetype).lower()
                                    else:
                                        mimetype = ''
                                    
                                    priority = 0
                                    if 'pdf' in mimetype:
                                        priority = 3
                                    elif 'image' in mimetype:
                                        priority = 2
                                    elif 'office' in mimetype or 'word' in mimetype or 'excel' in mimetype:
                                        priority = 2
                                    else:
                                        priority = 1
                                    
                                    # Сортируем по приоритету (убывание), затем по ID (возрастание - старые файлы первыми)
                                    file_id = file_info.get('id', 0)
                                    if isinstance(file_id, str):
                                        try:
                                            file_id = int(file_id)
                                        except:
                                            file_id = 0
                                    return (-priority, file_id)
                                
                                main_files_sorted = sorted(main_files, key=get_sort_key)
                                main_file = main_files_sorted[0]
                                
                                logger.debug(f"Выбран основной файл: {main_file.get('filename')} (MIME: {main_file.get('mimetype')})")
                                file_latest_id = str(main_file.get('id', ''))
                                file_latest_filename = main_file.get('filename', '')
                                file_latest_mimetype = main_file.get('mimetype', '')
                                file_latest_size = main_file.get('size', 0)
                            else:
                                # Если не нашли основные файлы, оставляем file_latest как есть
                                logger.warning(f"Не найден основной файл в документе {doc_data['id']}, только подписи/метаданные")
                                file_latest_id = file_latest_data.get('id', '')
                                file_latest_mimetype = file_latest_data.get('mimetype', '')
                                file_latest_size = file_latest_data.get('size', 0)
                        except Exception as e:
                            logger.warning(f"Ошибка при получении основных файлов документа {doc_data['id']}: {e}")
                            import traceback
                            logger.debug(f"Traceback: {traceback.format_exc()}")
                            # В случае ошибки используем file_latest как есть
                            file_latest_id = file_latest_data.get('id', '')
                            file_latest_filename = file_latest_data.get('filename', '')
                            file_latest_mimetype = file_latest_data.get('mimetype', '')
                            file_latest_size = file_latest_data.get('size', 0)
                    else:
                        # Если это не файл подписи/метаданных, используем file_latest как есть
                        file_latest_id = file_latest_data.get('id', '')
                        file_latest_mimetype = file_latest_data.get('mimetype', '')
                        file_latest_size = file_latest_data.get('size', 0)
                    
                    document = MayanDocument(
                        document_id=doc_data['id'],
                        label=doc_data['label'],
                        description=doc_data.get('description', ''),
                        file_latest_id=file_latest_id,
                        file_latest_filename=file_latest_filename,
                        file_latest_mimetype=file_latest_mimetype,
                        file_latest_size=file_latest_size,
                        datetime_created=doc_data.get('datetime_created', ''),
                        datetime_modified=doc_data.get('datetime_modified', '')
                    )
                    documents.append(document)
                    logger.debug(f"Документ {i+1} создан успешно: {document}")
                except Exception as e:
                    logger.error(f"Ошибка при создании документа {i+1}: {e}")
                    logger.error(f"Данные документа: {doc_data}")
                    # Пропускаем проблемный документ, но продолжаем обработку остальных
                    continue
            
            logger.info(f"Успешно создано {len(documents)} документов из {len(data.get('results', []))}")
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

    def _get_main_document_file(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает основной файл документа по активной версии
        
        Алгоритм:
        1. Получаем информацию о документе и извлекаем ID активной версии
        2. Пробуем получить файлы напрямую из активной версии через /documents/{id}/versions/{version_id}/files/
        3. Если не работает - используем fallback с фильтрацией
        
        Args:
            document_id: ID документа
            
        Returns:
            Информация о файле или None
        """
        try:
            # Шаг 1: Получаем информацию о документе и извлекаем ID активной версии
            logger.info(f"Получаем информацию о документе {document_id} для определения активной версии")
            document_response = self._make_request('GET', f'documents/{document_id}/')
            document_response.raise_for_status()
            document_data = document_response.json()
            
            # Извлекаем ID активной версии
            version_active = document_data.get('version_active', {})
            if not version_active:
                logger.warning(f"Документ {document_id} не имеет активной версии")
                return self._get_main_document_file_fallback(document_id)
            
            active_version_id = version_active.get('id')
            if not active_version_id:
                logger.warning(f"Активная версия документа {document_id} не имеет ID")
                return self._get_main_document_file_fallback(document_id)
            
            logger.info(f"ID активной версии документа {document_id}: {active_version_id}")
            
            # Шаг 2: Пробуем получить файлы напрямую из активной версии
            try:
                logger.info(f"Пробуем получить файлы напрямую из активной версии {active_version_id}")
                version_files_response = self._make_request('GET', f'documents/{document_id}/versions/{active_version_id}/files/')
                version_files_response.raise_for_status()
                version_files_data = version_files_response.json()
                
                version_files = version_files_data.get('results', [])
                if version_files:
                    logger.info(f"Найдено {len(version_files)} файлов в активной версии {active_version_id}")
                    
                    # Фильтруем файлы: исключаем метаданные и подписи
                    main_files = []
                    for file_info in version_files:
                        filename = file_info.get('filename', '').lower()
                        mimetype = (file_info.get('mimetype') or '').lower()
                        
                        # Пропускаем метаданные и подписи
                        if (filename.endswith('.p7s') or 
                            filename.endswith('.json') or
                            'signature' in filename or
                            'metadata' in filename or
                            'application/json' in mimetype):
                            logger.debug(f"Пропускаем файл метаданных/подписи: {file_info.get('filename')}")
                            continue
                        
                        main_files.append(file_info)
                    
                    if main_files:
                        # Приоритет: PDF > другие
                        pdf_files = [f for f in main_files if 'pdf' in (f.get('mimetype') or '').lower() or f.get('filename', '').lower().endswith('.pdf')]
                        if pdf_files:
                            selected_file = pdf_files[0]
                            logger.info(f"Выбран PDF файл из активной версии: {selected_file.get('filename')} (file_id: {selected_file.get('id')})")
                            return selected_file
                        else:
                            selected_file = main_files[0]
                            logger.info(f"Выбран основной файл из активной версии: {selected_file.get('filename')} (file_id: {selected_file.get('id')})")
                            return selected_file
                    else:
                        logger.warning(f"Все файлы активной версии {active_version_id} являются метаданными/подписями")
            except Exception as e:
                logger.warning(f"Не удалось получить файлы напрямую из версии {active_version_id}: {e}")
            
            # Шаг 3: Fallback - используем старый метод с фильтрацией
            logger.info(f"Используем fallback метод для поиска файла активной версии")
            return self._get_main_document_file_fallback(document_id)
            
        except Exception as e:
            logger.error(f"Ошибка при получении файла документа {document_id}: {e}", exc_info=True)
            return self._get_main_document_file_fallback(document_id)

    def get_document_file_content(self, document_id: str) -> Optional[bytes]:
        """
        Получает содержимое файла документа используя правильный endpoint
        Исключает файлы подписей (*.p7s) и метаданные (signature_metadata_*.json)
        
        Args:
            document_id: ID документа
            
        Returns:
            Содержимое файла в байтах или None
        """
        logger.info(f"Получаем содержимое файла документа {document_id}")
        
        file_info = self._get_main_document_file(document_id)
        if not file_info:
            logger.warning(f"Документ {document_id} не найден или не имеет основных файлов")
            return None
        
        file_id = file_info['id']
        filename = file_info.get('filename', 'Неизвестно')
        mimetype = file_info.get('mimetype', 'Неизвестно')
        logger.info(f"Выбран основной файл: file_id={file_id}, имя={filename}, MIME={mimetype}")
        
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
            
            content = response.content
            
            # КРИТИЧЕСКАЯ ПРОВЕРКА: Проверяем магические байты файла более тщательно
            if len(content) < 4:
                logger.warning(f"Скачанный файл слишком мал ({len(content)} байт)")
                return None
            
            # Проверяем магические байты PDF: PDF файлы начинаются с %PDF
            is_pdf = content[:4] == b'%PDF'
            logger.info(f"Проверка магических байтов: PDF={is_pdf}, первые 4 байта: {content[:4]}")
            
            # Дополнительная проверка: если файл начинается с %PDF, проверяем, что это действительно PDF
            if is_pdf:
                # Проверяем больше байтов - PDF должен содержать структуру PDF
                # Обычно после %PDF идет версия, например %PDF-1.4
                if len(content) > 8:
                    try:
                        # Пробуем декодировать первые 50 байт как текст для проверки
                        first_bytes_text = content[:50].decode('utf-8', errors='ignore')
                        logger.info(f"Первые 50 символов файла: {first_bytes_text[:50]}")
                        
                        # Проверяем, что это не JSON, маскирующийся под PDF
                        if first_bytes_text.strip().startswith('{') or first_bytes_text.strip().startswith('['):
                            logger.error(f"ОШИБКА: Файл начинается с %PDF, но содержит JSON! file_id={file_id}")
                            # Ищем альтернативный файл
                            return self._find_alternative_pdf_file(document_id, file_id, content)
                        
                        # Проверяем, что это действительно PDF структура
                        if '%PDF-' not in first_bytes_text and '%PDF' in first_bytes_text:
                            # Просто %PDF без версии - возможно, подозрительно
                            logger.warning(f"Файл начинается с %PDF, но не содержит версию PDF")
                    except Exception as e:
                        logger.debug(f"Ошибка при проверке первых байтов: {e}")
            else:
                # Файл не является PDF - проверяем, не JSON ли это
                logger.warning(f"Файл не является PDF (первые байты: {content[:20]})")
                
                # Пробуем декодировать как текст и проверить на JSON
                try:
                    import json
                    text_content = content.decode('utf-8')
                    
                    # Проверяем, является ли это валидным JSON
                    try:
                        json_data = json.loads(text_content)
                        logger.error(f"ОШИБКА: Скачанный файл является JSON! file_id={file_id}, filename={filename}")
                        logger.error(f"Размер JSON: {len(content)} байт")
                        logger.error(f"Первые 500 символов: {text_content[:500]}")
                        
                        # Ищем альтернативный PDF файл
                        return self._find_alternative_pdf_file(document_id, file_id, content)
                    except json.JSONDecodeError:
                        # Это не JSON
                        logger.warning(f"Файл не является ни PDF, ни JSON")
                except UnicodeDecodeError:
                    # Файл не является текстовым
                    logger.warning(f"Файл не является текстовым (не удалось декодировать как UTF-8)")
            
            # Файл прошел проверки - возвращаем
            logger.info(f"✓ Файл принят, размер: {len(content)} байт, Content-Type: {content_type}")
            return content
            
        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла через {endpoint}: {e}")
            return None

    def _find_alternative_pdf_file(self, document_id: str, excluded_file_id: int, original_content: bytes) -> Optional[bytes]:
        """
        Ищет альтернативный PDF файл среди всех файлов документа
        
        Args:
            document_id: ID документа
            excluded_file_id: ID файла, который нужно исключить из поиска
            original_content: Содержимое оригинального файла (для логирования)
            
        Returns:
            Содержимое альтернативного PDF файла или None
        """
        logger.info(f"Ищем альтернативный PDF файл среди всех файлов документа {document_id}...")
        files_data = self.get_document_files(document_id, page=1, page_size=100)
        if not files_data or not files_data.get('results'):
            logger.error(f"Не удалось получить список файлов для поиска альтернативного PDF")
            return None
        
        pdf_found = False
        for alt_file in files_data.get('results', []):
            alt_file_id = alt_file.get('id')
            alt_filename = alt_file.get('filename', '').lower()
            alt_mimetype = (alt_file.get('mimetype') or '').lower()
            
            # Пропускаем JSON и метаданные, а также исключаемый файл
            if (alt_filename.endswith('.json') or 
                'application/json' in alt_mimetype or
                'signature' in alt_filename or
                'metadata' in alt_filename or
                alt_filename.endswith('.p7s') or
                alt_file_id == excluded_file_id):
                continue
            
            # Если имя файла содержит .pdf - пробуем скачать его
            if alt_filename.endswith('.pdf'):
                logger.info(f"Найден потенциальный PDF файл: {alt_file.get('filename')} (file_id={alt_file_id})")
                
                # Скачиваем альтернативный файл
                alt_endpoint = f'documents/{document_id}/files/{alt_file_id}/download/'
                try:
                    alt_response = self._make_request('GET', alt_endpoint)
                    alt_response.raise_for_status()
                    alt_content = alt_response.content
                    
                    # Проверяем магические байты PDF
                    if len(alt_content) >= 4 and alt_content[:4] == b'%PDF':
                        # Проверяем, что это не JSON
                        try:
                            alt_text = alt_content.decode('utf-8', errors='ignore')
                            if not (alt_text.strip().startswith('{') or alt_text.strip().startswith('[')):
                                logger.info(f"✓ Альтернативный файл является PDF! {alt_file.get('filename')}, размер: {len(alt_content)} байт")
                                return alt_content
                            else:
                                # Это JSON, маскирующийся под PDF
                                logger.warning(f"✗ Альтернативный файл {alt_file.get('filename')} также является JSON")
                                continue
                        except:
                            # Не удалось декодировать как текст - вероятно, это бинарный PDF
                            logger.info(f"✓ Альтернативный файл является PDF! {alt_file.get('filename')}, размер: {len(alt_content)} байт")
                            return alt_content
                    else:
                        logger.warning(f"✗ Альтернативный файл {alt_file.get('filename')} не является PDF (первые байты: {alt_content[:20]})")
                except Exception as e:
                    logger.warning(f"Ошибка при скачивании альтернативного файла {alt_file_id}: {e}")
                    continue
        
        logger.error(f"Не удалось найти альтернативный PDF файл для документа {document_id}")
        return None

    def get_document_file_url(self, document_id: str) -> Optional[str]:
        """
        Получает URL для скачивания файла документа
        Исключает файлы подписей (*.p7s) и метаданные (signature_metadata_*.json)
        
        Args:
            document_id: ID документа
            
        Returns:
            URL для скачивания или None
        """
        file_info = self._get_main_document_file(document_id)
        if not file_info:
            return None
        file_id = file_info['id']
        
        # Строим URL для скачивания используя правильный endpoint
        return f'{self.api_url}documents/{document_id}/files/{file_id}/download/'

    def get_document_preview_url(self, document_id: str) -> Optional[str]:
        """
        Получает URL для предварительного просмотра документа
        Исключает файлы подписей (*.p7s) и метаданные (signature_metadata_*.json)
        
        Args:
            document_id: ID документа
            
        Returns:
            URL для предварительного просмотра или None
        """
        file_info = self._get_main_document_file(document_id)
        if not file_info:
            return None
        # Используем готовый image_url из ответа API для превью
        if 'pages_first' in file_info and 'image_url' in file_info['pages_first']:
            preview_url = file_info['pages_first']['image_url']
            logger.debug(f"URL превью из API: {preview_url}")
            return preview_url
        # Если нет image_url, строим URL вручную
        file_id = file_info.get('id')
        if file_id:
            return f'{self.api_url}documents/{document_id}/files/{file_id}/preview/'
        return None
            
    def search_documents(self, query: str, page: int = 1, page_size: int = 20) -> List[MayanDocument]:
        # 1) короткий путь search/documents.documentsearchresult?q=...
        try:
            docs = self._search_via_short_model(query, page, page_size)
            return docs  # пусто = честно "ничего не найдено"
        except Exception:
            pass

        # 2) прежний путь через search_models (если настроен)
        try:
            docs = self._search_via_document_search_model(query, page, page_size)
            return docs
        except Exception:
            pass

        # 3) fallback по названию
        return self.get_documents(page=page, page_size=page_size, search=query)

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
                            mimetype: str, description: str = "", skip_version_activation: bool = False) -> Optional[Dict[str, Any]]:
        """
        Загружает файл к документу и опционально активирует его версию
        
        Args:
            document_id: ID документа
            filename: Имя файла
            file_content: Содержимое файла
            mimetype: MIME-тип файла
            description: Описание файла
            skip_version_activation: Если True, не активирует версию после загрузки (для файлов подписи)
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
                        
                        # ИСПРАВЛЕНИЕ: Активируем версию только если не skip
                        if not skip_version_activation:
                            logger.info(f"Начинаем активацию версии файла {file_id}")
                            activation_result = self._activate_file_version(document_id, file_id)
                            logger.info(f"Результат активации версии: {activation_result}")
                        else:
                            logger.info(f"Пропускаем активацию версии для файла {file_id}")
                        
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
                    
                    # ИСПРАВЛЕНИЕ: Активируем версию только если не skip
                    if not skip_version_activation:
                        logger.info(f"Начинаем активацию версии файла {file_id}")
                        activation_result = self._activate_file_version(document_id, file_id)
                        logger.info(f"Результат активации версии: {activation_result}")
                    else:
                        logger.info(f"Пропускаем активацию версии для файла {file_id}")
                    
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

    def create_document_with_file(
        self, 
        label: str, 
        description: str, 
        filename: str, 
        file_content: bytes, 
        mimetype: str,
        document_type_id: Optional[int] = None,
        cabinet_id: Optional[int] = None,
        language: str = 'rus'
    ) -> Optional[Dict[str, Any]]:
        """
        Создает документ с файлом с улучшенной обработкой ошибок
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
            
            # ОБРАБОТКА ОШИБКИ 404: Тип документа не найден
            if response.status_code == 404:
                error_text = response.text
                if "No DocumentType matches the given query" in error_text:
                    logger.error(f"Тип документа с ID {document_type_id} больше не существует")
                    
                    # Получаем актуальный список типов документов
                    try:
                        current_types = self.get_document_types()
                        available_types = [dt['label'] for dt in current_types]
                        logger.info(f"Доступные типы документов: {available_types}")
                        
                        # Если есть доступные типы, предлагаем использовать первый
                        if current_types:
                            fallback_type_id = current_types[0]['id']
                            fallback_type_name = current_types[0]['label']
                            logger.info(f"Предлагаем использовать тип '{fallback_type_name}' (ID: {fallback_type_id})")
                            
                            # Обновляем данные и повторяем запрос
                            upload_data["document_type_id"] = fallback_type_id
                            logger.info(f"Повторяем загрузку с типом документа: {fallback_type_name}")
                            
                            # Повторный запрос
                            response = self._make_request(
                                'POST', 
                                'documents/upload/', 
                                data=upload_data, 
                                files=files
                            )
                            
                            logger.info(f"Статус повторного ответа: {response.status_code}")
                            
                            if response.status_code in [200, 201, 202]:
                                # Обрабатываем успешный ответ
                                return self._process_successful_upload_response(response, label, filename, file_content, mimetype, cabinet_id)
                            else:
                                logger.error(f"Повторная попытка также не удалась: {response.status_code}")
                                return None
                        else:
                            logger.error("Нет доступных типов документов в системе")
                            return None
                    except Exception as e:
                        logger.error(f"Ошибка при получении списка типов документов: {e}")
                        return None
                else:
                    logger.error(f"Неизвестная ошибка 404: {error_text}")
                    return None
            
            elif response.status_code in [200, 201, 202]:
                return self._process_successful_upload_response(response, label, filename, file_content, mimetype, cabinet_id)
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
    
    def _process_successful_upload_response(self, response: requests.Response, label: str, filename: str, file_content: bytes, 
                                                mimetype: str,
                                                cabinet_id: Optional[int]
                                            ) -> Optional[Dict[str, Any]]:
        """Обрабатывает успешный ответ от сервера"""
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
            
            # Используем правильный endpoint согласно спецификации Mayan EDMS API
            # POST /cabinets/{cabinet_id}/documents/add/ с параметром document (ID документа)
            try:
                logger.info(f"Добавляем документ через POST к cabinets/{cabinet_id}/documents/add/")
                # Согласно спецификации, передаем параметр document (ID документа)
                # Используем data (form-data) вместо json, так как это POST запрос с параметром
                response = self._make_request(
                    'POST', 
                    f'cabinets/{cabinet_id}/documents/add/', 
                    data={'document': document_id}
                )
                logger.info(f"Статус ответа: {response.status_code}")
                logger.info(f"Ответ сервера: {response.text[:500] if response.text else 'Пустой ответ'}")
                response.raise_for_status()
                logger.info(f"Документ {document_id} успешно добавлен в кабинет {cabinet_id}")
                return True
            except Exception as e:
                logger.error(f"Ошибка при добавлении документа в кабинет через POST к /documents/add/: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Статус ответа: {e.response.status_code}")
                    logger.error(f"Текст ответа: {e.response.text[:1000] if e.response.text else 'Пустой'}")
                return False
        
        except Exception as e:
            logger.error(f"Не удалось добавить документ в кабинет: {e}", exc_info=True)
            return False

    def get_acls_for_object(self, content_type: str, object_id: str) -> List[Dict[str, Any]]:
        """
        Получает список ACL для объекта
        Пытается использовать разные endpoints в зависимости от версии Mayan EDMS
        """
        # Пробуем разные варианты endpoints для получения ACL конкретного объекта
        endpoints_to_try = [
            # Стандартные endpoints для ACL
            f'acls/?content_type={content_type}&object_id={object_id}',
            f'access_control_lists/?content_type={content_type}&object_id={object_id}',
            
            # Возможные endpoints для конкретного документа
            f'documents/{object_id}/acls/',
            f'documents/{object_id}/access_control_lists/',
            f'documents/{object_id}/permissions/',
            
            # Альтернативные варианты
            f'object_permissions/?content_type={content_type}&object_id={object_id}',
            f'document_permissions/{object_id}/',
        ]
        
        for endpoint in endpoints_to_try:
            try:
                logger.info(f"Пробуем endpoint: {endpoint}")
                response = self._make_request('GET', endpoint)
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"ACL получены через endpoint {endpoint}")
                    
                    # Проверяем, что это действительно ACL, а не список разрешений
                    results = data.get('results', [])
                    if results:
                        first_item = results[0]
                        logger.info(f"Пример данных от endpoint {endpoint}: {first_item}")
                        logger.info(f"Ключи в данных: {list(first_item.keys())}")
                        
                        # Если это список разрешений (содержит 'pk' и 'label'), пропускаем
                        if 'pk' in first_item and 'label' in first_item and 'namespace' in first_item:
                            logger.warning(f"Endpoint {endpoint} возвращает список разрешений, а не ACL")
                            continue
                    
                    return results
                        
                elif response.status_code == 404:
                    logger.warning(f"Endpoint {endpoint} не найден (404)")
                    continue
                else:
                    logger.warning(f"Endpoint {endpoint} вернул статус {response.status_code}")
                    continue
                    
            except requests.RequestException as e:
                logger.warning(f"Ошибка при обращении к endpoint {endpoint}: {e}")
                continue
        
        # Если все endpoints не сработали, возвращаем пустой список
        logger.warning(f"Не удалось получить ACL для объекта {object_id} ни через один endpoint")
        logger.info("Возможно, для этого документа не настроены ACL")
        return []
    
    # def create_acl_with_user(self, content_type: str, object_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    #     """
    #     Создает ACL для объекта с пользователем
    #     Пытается использовать разные endpoints
    #     """
    #     # Пробуем разные варианты endpoints
    #     endpoints_to_try = [
    #         'acls/',
    #         'access_control_lists/',
    #         'permissions/'
    #     ]
        
    #     payload = {
    #         'content_type': content_type,
    #         'object_id': object_id,
    #         'user': user_id
    #     }
        
    #     for endpoint in endpoints_to_try:
    #         try:
    #             logger.info(f"Пробуем создать ACL через endpoint: {endpoint}")
    #             response = self._make_request('POST', endpoint, json=payload)
                
    #             if response.status_code in [200, 201]:
    #                 data = response.json()
    #                 logger.info(f"ACL создан через endpoint {endpoint}")
    #                 return data
    #             elif response.status_code == 404:
    #                 logger.warning(f"Endpoint {endpoint} не найден (404)")
    #                 continue
    #             else:
    #                 logger.warning(f"Endpoint {endpoint} вернул статус {response.status_code}: {response.text}")
    #                 continue
                    
    #         except requests.RequestException as e:
    #             logger.warning(f"Ошибка при создании ACL через endpoint {endpoint}: {e}")
    #             continue
        
    #     logger.error(f"Не удалось создать ACL для объекта {object_id} ни через один endpoint")
    #     return None
    
    # def add_permissions_to_acl(self, acl_id: int, permission_ids: List[int]) -> bool:
    #     """
    #     Добавляет разрешения к ACL
    #     Пытается использовать разные endpoints
    #     """
    #     # Пробуем разные варианты endpoints
    #     endpoints_to_try = [
    #         f'acls/{acl_id}/permissions/add/',
    #         f'access_control_lists/{acl_id}/permissions/add/',
    #         f'permissions/{acl_id}/add/'
    #     ]
        
    #     payload = {
    #         'permissions': permission_ids
    #     }
        
    #     for endpoint in endpoints_to_try:
    #         try:
    #             logger.info(f"Пробуем добавить разрешения через endpoint: {endpoint}")
    #             response = self._make_request('POST', endpoint, json=payload)
                
    #             if response.status_code in [200, 201]:
    #                 logger.info(f"Разрешения добавлены через endpoint {endpoint}")
    #                 return True
    #             elif response.status_code == 404:
    #                 logger.warning(f"Endpoint {endpoint} не найден (404)")
    #                 continue
    #             else:
    #                 logger.warning(f"Endpoint {endpoint} вернул статус {response.status_code}: {response.text}")
    #                 continue
                    
    #         except requests.RequestException as e:
    #             logger.warning(f"Ошибка при добавлении разрешений через endpoint {endpoint}: {e}")
    #             continue
        
    #     logger.error(f"Не удалось добавить разрешения к ACL {acl_id} ни через один endpoint")
    #     return False

    def remove_permissions_from_acl(self, acl_id: int, permission_ids: List[int]) -> bool:
        """
        Удаляет разрешения из ACL
        Endpoint: POST /api/v4/acls/{acl_id}/permissions/remove/
        """
        endpoint = f'acls/{acl_id}/permissions/remove/'
        payload = {
            'permissions': permission_ids
        }
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            logger.info(f"Разрешения {permission_ids} удалены из ACL {acl_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении разрешений из ACL: {e}")
            return False

    def delete_acl(self, acl_id: int) -> bool:
        """
        Удаляет ACL
        Endpoint: DELETE /api/v4/acls/{acl_id}/
        """
        endpoint = f'acls/{acl_id}/'
        
        try:
            response = self._make_request('DELETE', endpoint)
            response.raise_for_status()
            logger.info(f"ACL {acl_id} удален")
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении ACL: {e}")
            return False

    def get_roles(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        """
        Получает список ролей
        Endpoint: GET /api/v4/roles/
        """
        endpoint = 'roles/'
        #params = {'page': page, 'page_size': page_size}
        params = {}
        
        try:
            logger.info(f"Запрашиваем роли через endpoint: {endpoint}")
            logger.info(f"Параметры: {params}")
            
            response = self._make_request('GET', endpoint, params=params)
            logger.info(f"Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Получен ответ с count: {data.get('count', 'unknown')}")
                results = data.get('results', [])
                logger.info(f"Количество результатов: {len(results)}")
                
                # Выводим первые несколько ролей для отладки
                for i, role in enumerate(results[:5]):
                    logger.info(f"Роль {i+1}: {role}")
                
                return results
            else:
                logger.error(f"Ошибка HTTP {response.status_code}: {response.text}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении ролей: {e}")
            return []


    def get_role_users(self, role_id: int) -> List[Dict[str, Any]]:
        """
        Получает список пользователей в роли
        Endpoint: GET /api/v4/roles/{role_id}/users/
        """
        endpoint = f'roles/{role_id}/users/'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении пользователей роли {role_id}: {e}")
            return []

    def get_role_groups(self, role_id: int) -> List[Dict[str, Any]]:
        """
        Получает список групп в роли
        Endpoint: GET /api/v4/roles/{role_id}/groups/
        """
        endpoint = f'roles/{role_id}/groups/'
        
        try:
            response = self._make_request('GET', endpoint)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении групп роли {role_id}: {e}")
            return []

    def create_acl_with_user(self, content_type: str, object_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Создает ACL для объекта с пользователем
        Endpoint: POST /api/v4/acls/
        """
        endpoint = 'acls/'
        payload = {
            'content_type': content_type,
            'object_id': object_id,
            'user': user_id
        }
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(f"ACL создан для объекта {object_id} с пользователем {user_id}")
            return data
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании ACL с пользователем: {e}")
            return None

    def get_users(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        """
        Получает список пользователей
        Endpoint: GET /api/v4/users/
        """
        endpoint = 'users/'
        params = {'page': page, 'page_size': page_size}
        
        try:
            logger.info(f"Запрашиваем пользователей через endpoint: {endpoint}")
            logger.info(f"Параметры: {params}")
            
            response = self._make_request('GET', endpoint, params=params)
            logger.info(f"Статус ответа: {response.status_code}")
            
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Получен ответ с count: {data.get('count', 0)}")
            logger.info(f"Количество результатов: {len(data.get('results', []))}")
            
            # Отладочная информация о пользователях
            for i, user in enumerate(data.get('results', [])):
                logger.info(f"Пользователь {i+1}: {user.get('username')} (ID: {user.get('id')})")
            
            return data.get('results', [])
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении пользователей: {e}")
            logger.error(f"Ответ сервера: {response.text if 'response' in locals() else 'Нет ответа'}")
            return []

    def get_permissions(self, page: int = 1, page_size: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список всех разрешений
        Endpoint: GET /api/v4/permissions/
        """
        endpoint = 'permissions/'
        params = {'page': page, 'page_size': page_size}
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении разрешений: {e}")
            return []

    def add_permissions_to_acl(self, acl_id: int, permission_ids: List[int]) -> bool:
        """
        Добавляет разрешения к ACL
        Endpoint: POST /api/v4/acls/{acl_id}/permissions/add/
        """
        endpoint = f'acls/{acl_id}/permissions/add/'
        payload = {
            'permissions': permission_ids
        }
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            response.raise_for_status()
            logger.info(f"Разрешения {permission_ids} добавлены к ACL {acl_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при добавлении разрешений к ACL: {e}")
            return False

    def get_groups(self, page: int = 1, page_size: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список групп пользователей
        
        Args:
            page: Номер страницы
            page_size: Размер страницы
            
        Returns:
            Список групп
        """
        endpoint = 'groups/'
        params = {'page': page, 'page_size': page_size}
        
        logger.info("Получаем список групп пользователей")
        logger.info(f"Параметры пагинации: {params}")
        
        try:
            response = self._make_request('GET', endpoint, params=params)
            logger.info(f"Статус ответа получения групп: {response.status_code}")
            
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Ответ API: count={data.get('count', 0)}, next={data.get('next')}, previous={data.get('previous')}")
            
            groups = data.get('results', [])
            logger.info(f"Получено {len(groups)} групп со страницы {page}")
            
            # Проверяем, есть ли еще страницы
            if data.get('next'):
                logger.info(f"Есть следующая страница, загружаем следующие группы...")
                next_groups = self.get_groups(page=page + 1, page_size=page_size)
                groups.extend(next_groups)
                logger.info(f"Всего загружено групп: {len(groups)}")
            
            # Отладочная информация
            if groups:
                logger.info(f"Пример группы: {json.dumps(groups[0], indent=2, ensure_ascii=False)}")
            else:
                logger.warning(f"Группы не найдены. Структура ответа: {list(data.keys())}")
                if 'results' in data and not data['results']:
                    logger.warning(f"Поле 'results' существует, но пустое. Count: {data.get('count')}")
            
            return groups
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении групп: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Ответ сервера: {e.response.text[:500]}")
            return []

    def get_group_users(self, group_id: str) -> List[Dict[str, Any]]:
        """
        Получает список пользователей в группе
        
        Args:
            group_id: ID группы (строка)
            
        Returns:
            Список пользователей в группе
        """
        endpoint = f'groups/{group_id}/users/'
        
        logger.info(f"Получаем пользователей группы {group_id}")
        logger.info(f"URL: {urljoin(self.api_url, endpoint)}")
        
        try:
            response = self._make_request('GET', endpoint)
            
            logger.info(f"Статус ответа: {response.status_code}")
            logger.info(f"Ответ: {response.text[:500]}...")
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('results', [])
                
                logger.info(f"В группе {group_id} найдено {len(users)} пользователей")
                
                return users
            else:
                logger.error(f"Ошибка получения пользователей группы {group_id}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении пользователей группы {group_id}: {e}")
            return []

    def add_user_to_group(self, group_id: str, username: str) -> bool:
        """
        Добавляет пользователя в группу
        
        Args:
            group_id: ID группы (строка)
            username: Имя пользователя
            
        Returns:
            True если пользователь добавлен успешно, False иначе
        """
        try:
            # Получаем ID пользователя по имени
            user_id = self._get_user_id_by_username(username)
            
            if not user_id:
                logger.error(f"Пользователь {username} не найден в Mayan EDMS")
                return False
            
            logger.info(f"Найден пользователь {username} с ID {user_id}")
            
            endpoint = f'groups/{group_id}/users/add/'
            
            payload = {
                'user': user_id  # Используем ID пользователя, а не имя
            }
            
            logger.info(f"Добавляем пользователя {username} (ID: {user_id}) в группу {group_id}")
            logger.info(f"URL: {urljoin(self.api_url, endpoint)}")
            logger.info(f"Payload: {payload}")
            
            response = self._make_request('POST', endpoint, json=payload)
            
            logger.info(f"Статус ответа: {response.status_code}")
            logger.info(f"Ответ: {response.text[:500]}...")
            
            if response.status_code in [200, 201]:
                logger.info(f"Пользователь {username} успешно добавлен в группу {group_id}")
                return True
            else:
                logger.error(f"Ошибка добавления пользователя {username} в группу {group_id}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при добавлении пользователя {username} в группу {group_id}: {e}")
            return False

    def remove_user_from_group(self, group_id: str, username: str) -> bool:
        """
        Удаляет пользователя из группы
        
        Args:
            group_id: ID группы (строка)
            username: Имя пользователя
            
        Returns:
            True если пользователь удален успешно, False иначе
        """
        try:
            # Получаем ID пользователя по имени
            user_id = self._get_user_id_by_username(username)
            
            if not user_id:
                logger.error(f"Пользователь {username} не найден в Mayan EDMS")
                return False
            
            logger.info(f"Найден пользователь {username} с ID {user_id}")
            
            endpoint = f'groups/{group_id}/users/remove/'
            
            payload = {
                'user': user_id  # Используем ID пользователя, а не имя
            }
            
            logger.info(f"Удаляем пользователя {username} (ID: {user_id}) из группы {group_id}")
            logger.info(f"URL: {urljoin(self.api_url, endpoint)}")
            logger.info(f"Payload: {payload}")
            
            response = self._make_request('POST', endpoint, json=payload)
            
            logger.info(f"Статус ответа: {response.status_code}")
            logger.info(f"Ответ: {response.text[:500]}...")
            
            if response.status_code in [200, 201]:
                logger.info(f"Пользователь {username} успешно удален из группы {group_id}")
                return True
            else:
                logger.error(f"Ошибка удаления пользователя {username} из группы {group_id}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении пользователя {username} из группы {group_id}: {e}")
            return False

    def _get_user_id_by_username(self, username: str) -> Optional[int]:
        """
        Получает ID пользователя по имени пользователя
        
        Args:
            username: Имя пользователя
            
        Returns:
            ID пользователя или None если не найден
        """
        try:
            users = self.get_users()
            for user in users:
                if user.get('username') == username:
                    return user.get('id')
            return None
        except Exception as e:
            logger.error(f"Ошибка при поиске пользователя {username}: {e}")
            return None

    def create_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Создает нового пользователя
        
        Args:
            user_data: Данные пользователя
            
        Returns:
            True если пользователь создан успешно, False иначе
        """
        endpoint = 'users/'
        
        logger.info(f"Создаем пользователя {user_data.get('username')}")
        
        try:
            response = self._make_request('POST', endpoint, json=user_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Пользователь {user_data.get('username')} успешно создан")
                return True
            else:
                logger.error(f"Ошибка создания пользователя {user_data.get('username')}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании пользователя {user_data.get('username')}: {e}")
            return False

    def create_group(self, group_data: Dict[str, Any]) -> bool:
        """
        Создает новую группу
        
        Args:
            group_data: Данные группы
            
        Returns:
            True если группа создана успешно, False иначе
        """
        endpoint = 'groups/'
        
        logger.info(f"Создаем группу {group_data.get('name')}")
        
        try:
            response = self._make_request('POST', endpoint, json=group_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Группа {group_data.get('name')} успешно создана")
                return True
            else:
                logger.error(f"Ошибка создания группы {group_data.get('name')}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании группы {group_data.get('name')}: {e}")
            return False

    def create_role(self, role_data: Dict[str, Any]) -> bool:
        """
        Создает новую роль
        Endpoint: POST /api/v4/roles/
        """
        endpoint = 'roles/'
        
        try:
            response = self._make_request('POST', endpoint, json=role_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Роль {role_data.get('label')} создана успешно")
                return True
            else:
                logger.error(f"Ошибка создания роли: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании роли: {e}")
            return False
    
    def add_user_to_role(self, role_id: int, user_id: int) -> bool:
        """
        Добавляет пользователя к роли
        Endpoint: POST /api/v4/roles/{role_id}/users/add/
        """
        endpoint = f'roles/{role_id}/users/add/'
        payload = {'user': user_id}
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"Пользователь {user_id} добавлен к роли {role_id}")
                return True
            else:
                logger.error(f"Ошибка добавления пользователя к роли: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при добавлении пользователя к роли: {e}")
            return False
    
    def remove_user_from_role(self, role_id: int, user_id: int) -> bool:
        """
        Удаляет пользователя из роли
        Endpoint: POST /api/v4/roles/{role_id}/users/remove/
        """
        endpoint = f'roles/{role_id}/users/remove/'
        payload = {'user': user_id}
        
        try:
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"Пользователь {user_id} удален из роли {role_id}")
                return True
            else:
                logger.error(f"Ошибка удаления пользователя из роли: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении пользователя из роли: {e}")
            return False

    def get_object_acls_list(self, app_label: str, model_name: str, object_id: str) -> List[Dict[str, Any]]:
        """
        Получает список ACL для объекта
        Endpoint: GET /api/v4/objects/{app_label}/{model_name}/{object_id}/acls/
        
        Args:
            app_label: Метка приложения (например: 'documents')
            model_name: Имя модели (например: 'document')
            object_id: ID объекта
        """
        endpoint = f'objects/{app_label}/{model_name}/{object_id}/acls/'
        
        try:
            logger.info(f"Получаем список ACL для объекта {app_label}.{model_name}.{object_id}")
            logger.info(f"Endpoint: {endpoint}")
            
            response = self._make_request('GET', endpoint)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                logger.info(f"Получено {len(results)} ACL для объекта")
                
                if results:
                    logger.info(f"Пример ACL: {results[0]}")
                    logger.info(f"Ключи в ACL: {list(results[0].keys())}")
                
                return results
            elif response.status_code == 404:
                logger.warning(f"ACL для объекта {app_label}.{model_name}.{object_id} не найдены")
                return []
            else:
                logger.error(f"Ошибка получения списка ACL: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении списка ACL: {e}")
            return []

    def get_object_acl_details(self, app_label: str, model_name: str, object_id: str, acl_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает детали конкретного ACL объекта
        Endpoint: GET /api/v4/objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/
        
        Args:
            app_label: Метка приложения (например: 'documents')
            model_name: Имя модели (например: 'document')
            object_id: ID объекта
            acl_id: ID ACL
        """
        endpoint = f'objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/'
        
        try:
            logger.info(f"Получаем детали ACL {acl_id} для объекта {app_label}.{model_name}.{object_id}")
            logger.info(f"Endpoint: {endpoint}")
            
            response = self._make_request('GET', endpoint)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Получены детали ACL: {data}")
                logger.info(f"Ключи в ACL: {list(data.keys())}")
                return data
            elif response.status_code == 404:
                logger.warning(f"ACL {acl_id} для объекта {app_label}.{model_name}.{object_id} не найден")
                return None
            else:
                logger.error(f"Ошибка получения деталей ACL: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении деталей ACL: {e}")
            return None

    def create_acl_for_object(self, app_label: str, model_name: str, object_id: str, 
                        role_id: int = None, user_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Создает ACL для конкретного объекта
        Endpoint: POST /api/v4/objects/{app_label}/{model_name}/{object_id}/acls/
        """
        endpoint = f'objects/{app_label}/{model_name}/{object_id}/acls/'
        
        # Подготавливаем payload
        payload = {}
        if role_id:
            payload['role_id'] = role_id
        if user_id:
            payload['user_id'] = user_id
        
        try:
            logger.info(f"Создаем ACL для объекта {app_label}.{model_name}.{object_id}")
            logger.info(f"Endpoint: {endpoint}")
            logger.info(f"Payload: {payload}")
            
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.status_code in [200, 201]:
                acl_data = response.json()
                logger.info(f"ACL создан успешно: {acl_data}")
                return acl_data
            else:
                logger.error(f"Ошибка создания ACL: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                
                # Если ошибка 500, попробуем альтернативный подход
                if response.status_code == 500:
                    logger.info("Пробуем альтернативный метод создания ACL...")
                    return self._create_acl_alternative(app_label, model_name, object_id, role_id, user_id)
                
                return None
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании ACL: {e}")
            return None
    
    def _create_acl_alternative(self, app_label: str, model_name: str, object_id: str, 
                          role_id: int = None, user_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Альтернативный метод создания ACL через другой endpoint
        """
        try:
            # Пробуем создать ACL через общий endpoint ACL
            endpoint = 'acls/'
            payload = {
                'content_type': f'{app_label}.{model_name}',
                'object_id': object_id
            }
            
            if role_id:
                payload['role_id'] = role_id
            if user_id:
                payload['user_id'] = user_id
            
            logger.info(f"Альтернативный метод: {endpoint}")
            logger.info(f"Payload: {payload}")
            
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.status_code in [200, 201]:
                acl_data = response.json()
                logger.info(f"ACL создан через альтернативный метод: {acl_data}")
                return acl_data
            else:
                logger.error(f"Альтернативный метод тоже не сработал: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка в альтернативном методе: {e}")
            return None

    def add_permissions_to_object_acl(self, app_label: str, model_name: str, object_id: str, 
                                    acl_id: int, permission_ids: List) -> bool:
        """
        Добавляет разрешения к ACL объекта
        Endpoint: POST /api/v4/objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/permissions/add/
        """
        endpoint = f'objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/permissions/add/'
        
        # Добавляем разрешения по одному
        success_count = 0
        total_count = len(permission_ids)
        
        for permission_id in permission_ids:
            # Пробуем разные форматы payload для одного разрешения
            payloads_to_try = [
                {'permission': permission_id},  # Основной формат
                {'permission_id': permission_id},  # permission_id
                {'permission_pk': permission_id},   # permission_pk
                {'permission_codename': permission_id},  # permission_codename
            ]
            
            permission_added = False
            for payload in payloads_to_try:
                try:
                    logger.info(f"Добавляем разрешение {permission_id} к ACL {acl_id}")
                    logger.info(f"Endpoint: {endpoint}")
                    logger.info(f"Payload: {payload}")
                    
                    response = self._make_request('POST', endpoint, json=payload)
                    
                    if response.status_code in [200, 201]:
                        logger.info(f"Разрешение {permission_id} добавлено к ACL {acl_id}")
                        success_count += 1
                        permission_added = True
                        break
                    else:
                        logger.warning(f"Payload {payload} не сработал: {response.status_code}")
                        logger.warning(f"Ответ: {response.text}")
                        
                except requests.RequestException as e:
                    logger.warning(f"Ошибка с payload {payload}: {e}")
                    continue
            
            if not permission_added:
                logger.error(f"Не удалось добавить разрешение {permission_id} к ACL {acl_id}")
        
        # Если основной метод не сработал, пробуем альтернативный
        if success_count == 0:
            logger.info("Основной метод не сработал, пробуем альтернативный...")
            return self.add_permissions_to_object_acl_alternative(app_label, model_name, object_id, acl_id, permission_ids)
        
        # Возвращаем True, если хотя бы одно разрешение было добавлено
        if success_count > 0:
            logger.info(f"Успешно добавлено {success_count} из {total_count} разрешений к ACL {acl_id}")
            return True
        else:
            logger.error(f"Не удалось добавить ни одного разрешения к ACL {acl_id}")
            return False
    
    def add_permissions_to_object_acl_alternative(self, app_label: str, model_name: str, object_id: str, 
                                             acl_id: int, permission_ids: List) -> bool:
        """
        Альтернативный метод добавления разрешений к ACL объекта
        Пробует разные endpoints
        """
        # Пробуем разные endpoints
        endpoints_to_try = [
            f'objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/permissions/add/',
            f'acls/{acl_id}/permissions/add/',
            f'access_control_lists/{acl_id}/permissions/add/',
        ]
        
        for endpoint in endpoints_to_try:
            try:
                logger.info(f"Пробуем альтернативный endpoint: {endpoint}")
                
                # Добавляем разрешения по одному
                success_count = 0
                for permission_id in permission_ids:
                    payloads_to_try = [
                        {'permission': permission_id},
                        {'permissions': [permission_id]},
                        {'permission_id': permission_id},
                        {'permission_pk': permission_id},
                    ]
                    
                    permission_added = False
                    for payload in payloads_to_try:
                        try:
                            response = self._make_request('POST', endpoint, json=payload)
                            
                            if response.status_code in [200, 201]:
                                logger.info(f"Разрешение {permission_id} добавлено через {endpoint}")
                                success_count += 1
                                permission_added = True
                                break
                            else:
                                logger.warning(f"Payload {payload} не сработал через {endpoint}: {response.status_code}")
                                
                        except requests.RequestException as e:
                            logger.warning(f"Ошибка с payload {payload} через {endpoint}: {e}")
                            continue
                    
                    if not permission_added:
                        logger.warning(f"Не удалось добавить разрешение {permission_id} через {endpoint}")
                
                if success_count > 0:
                    logger.info(f"Успешно добавлено {success_count} разрешений через {endpoint}")
                    return True
                    
            except Exception as e:
                logger.warning(f"Ошибка при использовании endpoint {endpoint}: {e}")
                continue
        
        logger.error(f"Не удалось добавить разрешения через альтернативные endpoints")
        return False

    def delete_object_acl(self, app_label: str, model_name: str, object_id: str, acl_id: int) -> bool:
        """
        Удаляет ACL объекта
        Endpoint: DELETE /api/v4/objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/
        """
        endpoint = f'objects/{app_label}/{model_name}/{object_id}/acls/{acl_id}/'
        
        try:
            logger.info(f"Удаляем ACL {acl_id} объекта {app_label}.{model_name}.{object_id}")
            logger.info(f"Endpoint: {endpoint}")
            
            response = self._make_request('DELETE', endpoint)
            
            if response.status_code in [200, 204]:
                logger.info(f"ACL {acl_id} удален")
                return True
            else:
                logger.error(f"Ошибка удаления ACL: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении ACL: {e}")
            return False
    
    def get_permission_by_pk(self, permission_pk: str) -> Optional[Dict[str, Any]]:
        """
        Получает детальную информацию о разрешении по pk
        Endpoint: GET /api/v4/permissions/{pk}/
        """
        endpoint = f'permissions/{permission_pk}/'
        
        try:
            logger.info(f"Получаем детальную информацию о разрешении: {permission_pk}")
            response = self._make_request('GET', endpoint)
            
            if response.status_code == 200:
                permission_data = response.json()
                logger.info(f"Получена детальная информация о разрешении: {permission_data}")
                return permission_data
            else:
                logger.error(f"Ошибка получения разрешения {permission_pk}: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении разрешения {permission_pk}: {e}")
            return None

    def get_permission_id_by_pk(self, permission_pk: str) -> Optional[str]:
        """
        Получает ID разрешения по pk (возвращает строковый pk, если числовой ID не найден)
        """
        try:
            # Подход 1: Попробуем найти разрешение в общем списке
            try:
                permissions = self.get_permissions()
                for permission in permissions:
                    if permission and permission.get('pk') == permission_pk:
                        # Попробуем извлечь числовой ID из URL
                        url = permission.get('url', '')
                        if url:
                            import re
                            match = re.search(r'/permissions/(\d+)/', url)
                            if match:
                                numeric_id = int(match.group(1))
                                logger.info(f'Найден числовой ID для {permission_pk}: {numeric_id}')
                                return numeric_id
                        
                        # Если числовой ID не найден, возвращаем строковый pk
                        logger.info(f'Числовой ID не найден, используем строковый pk: {permission_pk}')
                        return permission_pk
            except Exception as e:
                logger.warning(f"Не удалось найти разрешение в списке: {e}")
            
            # Подход 2: Попробуем альтернативные endpoints
            alternative_endpoints = [
                f'permissions/?pk={permission_pk}',
                f'permissions/?codename={permission_pk}',
                f'permissions/?name={permission_pk}'
            ]
            
            for endpoint in alternative_endpoints:
                try:
                    logger.info(f"Пробуем альтернативный endpoint: {endpoint}")
                    response = self._make_request('GET', endpoint)
                    
                    if response.status_code == 200:
                        data = response.json()
                        results = data.get('results', [])
                        
                        # Ищем наше разрешение в результатах
                        for perm in results:
                            if perm.get('pk') == permission_pk:
                                # Попробуем извлечь числовой ID из URL
                                url = perm.get('url', '')
                                if url:
                                    import re
                                    match = re.search(r'/permissions/(\d+)/', url)
                                    if match:
                                        numeric_id = int(match.group(1))
                                        logger.info(f'Найден числовой ID через {endpoint}: {numeric_id}')
                                        return numeric_id
                                
                                # Если числовой ID не найден, возвращаем строковый pk
                                logger.info(f'Числовой ID не найден через {endpoint}, используем pk: {permission_pk}')
                                return permission_pk
                                
                except Exception as e:
                    logger.warning(f"Ошибка при обращении к {endpoint}: {e}")
                    continue
            
            # Если ничего не сработало, возвращаем строковый pk
            logger.warning(f"Не удалось найти разрешение {permission_pk}, используем pk как есть")
            return permission_pk
            
        except Exception as e:
            logger.error(f"Ошибка при получении ID разрешения {permission_pk}: {e}")
            return permission_pk  # Возвращаем pk как fallback

    def _get_page_count_from_pages_api(self, document_id: str) -> Optional[int]:
        """
        Получает количество страниц документа через API страниц
        Использует основной файл документа (исключая подписи и метаданные)
        
        Args:
            document_id: ID документа
            
        Returns:
            Количество страниц или None
        """
        try:
            # Получаем основной файл документа
            file_info = self._get_main_document_file(document_id)
            if not file_info:
                logger.warning(f"Документ {document_id} не найден или не имеет основных файлов")
                return None
            
            file_id = file_info.get('id')
            
            if not file_id:
                logger.warning(f"Не найден ID файла для документа {document_id}")
                return None
            
            # Используем правильный endpoint для получения страниц файла
            endpoint = f'documents/{document_id}/files/{file_id}/pages/'
            params = {'page': 1, 'page_size': 1}  # Нам нужен только count
            
            logger.info(f"Запрашиваем страницы файла через endpoint: {endpoint}")
            
            response = self._make_request('GET', endpoint, params=params)
            
            # Если получили 404, значит API страниц недоступен
            if response.status_code == 404:
                logger.debug(f"API страниц недоступен для файла {file_id} документа {document_id} (404)")
                return None
                
            response.raise_for_status()
            
            data = response.json()
            
            # ОТЛАДКА: Выводим ответ API
            logger.info(f"=== ОТЛАДКА: Ответ API страниц для документа {document_id} ===")
            logger.info(f"  count: {data.get('count')}")
            logger.info(f"  next: {data.get('next')}")
            logger.info(f"  previous: {data.get('previous')}")
            logger.info(f"  results count: {len(data.get('results', []))}")
            logger.info("=== КОНЕЦ ОТЛАДКИ ===")
            
            # Получаем общее количество страниц из поля count
            if 'count' in data:
                page_count = data['count']
                logger.info(f"Получено количество страниц через API страниц: {page_count}")
                return page_count
            
            logger.warning(f"Поле 'count' не найдено в ответе API страниц для документа {document_id}")
            return None
            
        except Exception as e:
            logger.debug(f"Не удалось получить количество страниц через API страниц: {e}")
            return None

    def get_document_page_count(self, document_id: str) -> Optional[int]:
        """
        Получает количество страниц документа
        Использует основной файл документа (исключая подписи и метаданные)
        
        Args:
            document_id: ID документа
            
        Returns:
            Количество страниц или None
        """
        logger.info(f"Получаем количество страниц документа {document_id}")
        
        try:
            # Получаем основной файл документа
            file_info = self._get_main_document_file(document_id)
            if not file_info:
                logger.warning(f"Документ {document_id} не найден или не имеет основных файлов")
                return None
            
            # ОТЛАДКА: Выводим все поля файла
            logger.info(f"=== ОТЛАДКА: Поля файла документа {document_id} ===")
            logger.info(f"  id: {file_info.get('id')}")
            logger.info(f"  filename: {file_info.get('filename')}")
            logger.info(f"  mimetype: {file_info.get('mimetype')}")
            logger.info(f"  size: {file_info.get('size')}")
            logger.info(f"  timestamp: {file_info.get('timestamp')}")
            logger.info(f"  url: {file_info.get('url')}")
            logger.info("=== КОНЕЦ ОТЛАДКИ ===")

            # ВСЕГДА обращаемся к API страниц для получения правильного количества
            # Поле count в ответе API страниц содержит точное количество страниц
            logger.info("Получаем количество страниц через API страниц...")
            page_count = self._get_page_count_from_pages_api(document_id)
            
            if page_count is not None:
                logger.info(f"Получено количество страниц через API страниц: {page_count}")
                return page_count
            else:
                logger.warning(f"Не удалось получить количество страниц через API страниц для документа {document_id}")
                return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении количества страниц документа {document_id}: {e}")
            return None

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

    def _get_main_document_file_fallback(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Fallback метод для получения основного файла документа (старый способ)
        Используется, если не удалось получить активную версию или найти файл по version_id
        
        Args:
            document_id: ID документа
            
        Returns:
            Информация о файле или None
        """
        # Получаем список всех файлов документа
        files_data = self.get_document_files(document_id, page=1, page_size=100)
        if not files_data or not files_data.get('results'):
            logger.warning(f"Fallback: не найдено файлов для документа {document_id}")
            return None
        
        # Исключаем файлы подписей и метаданные (более строгая фильтрация)
        exclude_patterns = ['.p7s', 'signature_metadata_']
        main_files = []
        
        logger.info(f"Fallback: фильтруем файлы документа {document_id}")
        
        for file_info in files_data.get('results', []):
            filename = file_info.get('filename', '')
            filename_lower = filename.lower()
            mimetype = (file_info.get('mimetype') or '').lower()
            file_size = file_info.get('size', 0)
            
            logger.debug(f"Проверяем файл: {filename} (MIME: {mimetype}, размер: {file_size})")
            
            # Пропускаем файлы подписей (.p7s)
            if filename_lower.endswith('.p7s'):
                logger.debug(f"Пропускаем файл подписи .p7s: {filename}")
                continue
            
            # Пропускаем все файлы, содержащие "signature" в имени
            if 'signature' in filename_lower:
                logger.debug(f"Пропускаем файл с 'signature' в имени: {filename}")
                continue
            
            # Пропускаем все JSON файлы
            if filename_lower.endswith('.json') or 'application/json' in mimetype:
                logger.debug(f"Пропускаем JSON файл (не может быть основным документом): {filename}")
                continue
            
            # Пропускаем файлы с "metadata" в имени
            if 'metadata' in filename_lower:
                logger.debug(f"Пропускаем файл с 'metadata' в имени: {filename}")
                continue
            
            main_files.append(file_info)
            logger.debug(f"Файл принят: {filename} (MIME: {mimetype})")
        
        logger.info(f"Fallback: после фильтрации осталось {len(main_files)} основных файлов")
        
        if not main_files:
            logger.warning(f"Документ {document_id} не содержит основных файлов (только подписи/метаданные)")
            return None
        
        # Сортируем файлы по приоритету
        def get_sort_key(file_info):
            mimetype = (file_info.get('mimetype') or '').lower()
            priority = 0
            if 'pdf' in mimetype:
                priority = 4
            elif 'image' in mimetype:
                priority = 3
            elif any(x in mimetype for x in ['word', 'excel', 'powerpoint', 'office', 'document']):
                priority = 3
            elif 'text' in mimetype:
                priority = 2
            else:
                priority = 1
            
            file_id = file_info.get('id', 0)
            if isinstance(file_id, str):
                try:
                    file_id = int(file_id)
                except:
                    file_id = 999999
            return (-priority, file_id)
        
        main_files_sorted = sorted(main_files, key=get_sort_key)
        main_file = main_files_sorted[0]
        
        logger.info(f"Выбран основной файл документа {document_id} (fallback): {main_file.get('filename')} (MIME: {main_file.get('mimetype')}, file_id: {main_file.get('id')})")
        return main_file

def get_mayan_client() -> MayanClient:
    """Получает клиент Mayan EDMS с учетными данными текущего пользователя"""
    return MayanClient.create_with_session_user()