# Code Review: mayan_documents.py

## Критичность: 🔴 Высокая | 🟡 Средняя | 🟢 Низкая

---

## 🔴 КРИТИЧЕСКИЕ УЯЗВИМОСТИ БЕЗОПАСНОСТИ

### 1. XSS (Cross-Site Scripting) через JavaScript Injection
**Строки: 635-648, 1769-1780, 1472-1493**

**Проблема:**
```python
# Строка 635-648
html_content = f'''
    <div id="preview_clickable_{document.document_id}" 
         ...
         title="Нажмите для просмотра всех страниц документа">
        <img src="{data_uri}" 
             alt="Превью документа {document.document_id}" 
             ...
    </div>
'''

# Строка 1769-1780
ui.run_javascript(f'''
    const element = document.querySelector('[data-id="{expansion.id}"]');
    if (element) {{
        const header = element.querySelector('.q-expansion-item__header');
        if (header) {{
            const label = header.querySelector('.q-expansion-item__header-content');
            if (label) {{
                label.textContent = "{new_title}";
            }}
        }}
    }}
''')
```

**Риск:** Если `document.label`, `document.document_id` или `new_title` содержат пользовательский ввод, возможна инъекция JavaScript.

**Решение:**
```python
import html
import json

# Экранирование HTML
safe_label = html.escape(document.label)
safe_id = str(document.document_id)  # ID должен быть числом

# Для JavaScript используйте json.dumps
ui.run_javascript(f'''
    const element = document.querySelector('[data-id={json.dumps(str(expansion.id))}]');
    if (element) {{
        const label = element.querySelector('.q-expansion-item__header-content');
        if (label) {{
            label.textContent = {json.dumps(new_title)};
        }}
    }}
''')
```

### 2. Path Traversal в именах файлов
**Строки: 1361, 1392, 2045**

**Проблема:**
```python
filename = document.file_latest_filename or f"document_{document.document_id}"
# Нет валидации на ../, абсолютные пути и т.д.
```

**Риск:** Если `file_latest_filename` содержит `../../../etc/passwd`, возможен доступ к файлам вне рабочей директории.

**Решение:**
```python
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от опасных символов"""
    # Убираем путь, оставляем только имя файла
    safe_name = Path(filename).name
    # Убираем опасные символы
    safe_name = re.sub(r'[<>:"|?*\x00-\x1f]', '', safe_name)
    # Ограничиваем длину
    return safe_name[:255] if len(safe_name) > 255 else safe_name

filename = sanitize_filename(document.file_latest_filename) if document.file_latest_filename else f"document_{document.document_id}"
```

### 3. Утечка чувствительных данных в логи
**Строки: 277-285, 1163-1177**

**Проблема:**
```python
logger.info(f"SimpleFormDataExtractor: params.cabinet_id={params.cabinet_id}, params.cabinet_name={params.cabinet_name}")
logger.info(f"Подготовка формы: cabinet_id_map = {local_cabinet_id_map}")
```

**Риск:** В логах могут попасть токены, пароли, внутренние структуры данных.

**Решение:**
```python
# Не логируйте чувствительные данные
logger.info(f"SimpleFormDataExtractor: cabinet_id получен, cabinet_name={'указан' if params.cabinet_name else 'не указан'}")
# Или используйте маскирование
logger.debug(f"cabinet_id_map содержит {len(local_cabinet_id_map)} записей")
```

### 4. Race Condition в глобальном кэше клиента
**Строки: 347-478**

**Проблема:**
```python
# Строка 363-373: Проверка вне блокировки
if _mayan_client_cache:
    cached_token = None
    if 'Authorization' in _mayan_client_cache.client.headers:
        # ... проверка токена
        if cached_token == current_user.mayan_api_token and _token_checked:
            return _mayan_client_cache  # ⚠️ Может вернуть устаревший клиент

# Строка 383: Блокировка только для проверки токена
async with _token_check_lock:
    # ...
```

**Риск:** Между проверкой токена (строка 372) и получением блокировки (строка 383) другой поток может изменить `_mayan_client_cache`.

**Решение:**
```python
async def get_mayan_client() -> MayanClient:
    global _mayan_client_cache, _token_checked, _token_check_lock
    
    async with _token_check_lock:  # Блокировка с самого начала
        current_user = _current_user if _current_user else get_current_user()
        
        if not current_user:
            raise ValueError('Пользователь не авторизован')
        
        if not hasattr(current_user, 'mayan_api_token') or not current_user.mayan_api_token:
            raise MayanTokenExpiredError(f'У пользователя {current_user.username} нет API токена')
        
        # Проверяем кэш внутри блокировки
        if _mayan_client_cache and _token_checked:
            cached_token = _extract_token_from_client(_mayan_client_cache)
            if cached_token == current_user.mayan_api_token:
                return _mayan_client_cache
        
        # Создаем новый клиент
        client = MayanClient(
            base_url=config.mayan_url,
            api_token=current_user.mayan_api_token
        )
        
        # Проверяем токен
        if not _token_checked:
            is_valid = await client.check_token_validity()
            # ... обработка истекшего токена
        
        _mayan_client_cache = client
        _token_checked = True
        return client
```

---

## 🟡 ПРОБЛЕМЫ БЕЗОПАСНОСТИ И НАДЕЖНОСТИ

### 5. Небезопасное удаление временных файлов
**Строки: 1364-1372, 2048-2056**

**Проблема:**
```python
with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
    temp_file.write(file_content)
    temp_path = temp_file.name

ui.download(temp_path, filename)
ui.timer(5.0, lambda: os.unlink(temp_path), once=True)  # ⚠️ Может не выполниться при ошибке
```

**Риски:**
- Файл может не удалиться при исключении
- Нет проверки существования файла перед удалением
- Возможна утечка дискового пространства

**Решение:**
```python
from contextlib import asynccontextmanager
import atexit

_temp_files = set()

@asynccontextmanager
async def temp_file_for_download(content: bytes, filename: str):
    """Контекстный менеджер для безопасной работы с временными файлами"""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{sanitize_filename(filename)}") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
            _temp_files.add(temp_path)
        
        yield temp_path
        
        # Удаляем сразу после использования
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                _temp_files.discard(temp_path)
            except OSError as e:
                logger.warning(f"Не удалось удалить временный файл {temp_path}: {e}")
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                _temp_files.discard(temp_path)
            except OSError:
                pass
        raise

# Очистка при выходе
def cleanup_temp_files():
    for temp_path in list(_temp_files):
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass
    _temp_files.clear()

atexit.register(cleanup_temp_files)
```

### 6. Отсутствие валидации размера файла при чтении
**Строка: 222**

**Проблема:**
```python
file_content = upload_event.content.read()  # ⚠️ Читает весь файл в память
```

**Риск:** При большом файле (близком к лимиту 50MB) может произойти переполнение памяти или DoS.

**Решение:**
```python
def _process_file(self, upload_event) -> FileInfo:
    """Обрабатывает загруженный файл с проверкой размера"""
    try:
        filename = upload_event.name
        mimetype = upload_event.type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        # Читаем файл порциями с проверкой размера
        file_content = b''
        max_size = FileSize.MAX_SIZE.value
        chunk_size = 1024 * 1024  # 1MB
        
        while True:
            chunk = upload_event.content.read(chunk_size)
            if not chunk:
                break
            
            if len(file_content) + len(chunk) > max_size:
                raise ValidationError(f"Файл превышает максимальный размер: {max_size} байт")
            
            file_content += chunk
        
        file_info = FileInfo(
            name=filename,
            content=file_content,
            mimetype=mimetype,
            size=len(file_content)
        )
        
        FileValidator.validate_file(file_info)
        return file_info
        
    except Exception as e:
        raise FileProcessingError(f"Ошибка обработки файла: {e}")
```

### 7. Небезопасная работа с паролями
**Строка: 2092**

**Проблема:**
```python
password = password_input.value.strip()  # Пароль хранится в строке
```

**Риск:** Пароль остается в памяти после использования, может попасть в логи.

**Решение:**
```python
# Используйте специальные типы для паролей (если доступны)
# Или очищайте строку после использования
def clear_password(password: str) -> None:
    """Пытается очистить строку из памяти (ограниченная эффективность в Python)"""
    # В Python строки immutable, но можно попытаться минимизировать время жизни
    pass

try:
    password = password_input.value.strip()
    # ... использование пароля
finally:
    password_input.value = ''  # Очищаем поле
    # Примечание: полная очистка из памяти в Python невозможна
```

### 8. Отсутствие rate limiting
**Строки: 1072-1130, 1132-1347**

**Проблема:** Нет ограничений на частоту запросов поиска и загрузки.

**Риск:** Возможен DoS через множественные запросы.

**Решение:**
```python
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio

_rate_limits = defaultdict(list)
_rate_limit_lock = asyncio.Lock()

async def check_rate_limit(user_id: str, action: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    """Проверяет rate limit для действия пользователя"""
    async with _rate_limit_lock:
        now = datetime.now()
        key = f"{user_id}:{action}"
        
        # Удаляем старые записи
        _rate_limits[key] = [
            timestamp for timestamp in _rate_limits[key]
            if now - timestamp < timedelta(seconds=window_seconds)
        ]
        
        # Проверяем лимит
        if len(_rate_limits[key]) >= max_requests:
            return False
        
        _rate_limits[key].append(now)
        return True

# Использование:
async def search_documents(query: str):
    current_user = get_current_user()
    if not await check_rate_limit(current_user.username, 'search'):
        ui.notify('Превышен лимит запросов. Попробуйте позже.', type='warning')
        return
    # ... остальной код
```

---

## 🟡 ПРОБЛЕМЫ АРХИТЕКТУРЫ И КАЧЕСТВА КОДА

### 9. Избыточное использование глобальных переменных
**Строки: 33-48**

**Проблема:**
```python
_recent_documents_container: Optional[ui.column] = None
_search_results_container: Optional[ui.column] = None
_upload_form_container: Optional[ui.column] = None
_mayan_client: Optional[MayanClient] = None
_connection_status: bool = False
_auth_error: Optional[str] = None
_current_user: Optional[Any] = None
_mayan_client_cache: Optional[MayanClient] = None
_token_checked: bool = False
_favorites_container: Optional[ui.column] = None
```

**Проблемы:**
- Сложно тестировать
- Race conditions в многопоточности
- Сложно отслеживать состояние

**Решение:**
```python
from dataclasses import dataclass, field
from typing import Dict, Optional
import threading

@dataclass
class MayanDocumentsState:
    """Состояние модуля работы с документами"""
    recent_documents_container: Optional[ui.column] = None
    search_results_container: Optional[ui.column] = None
    upload_form_container: Optional[ui.column] = None
    favorites_container: Optional[ui.column] = None
    mayan_client_cache: Optional[MayanClient] = None
    token_checked: bool = False
    connection_status: bool = False
    auth_error: Optional[str] = None
    current_user: Optional[Any] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def reset_cache(self):
        """Сбрасывает кэш клиента"""
        with self._lock:
            self.mayan_client_cache = None
            self.token_checked = False

# Используйте экземпляр состояния
_state = MayanDocumentsState()
```

### 10. Отсутствие обработки таймаутов
**Строки: 1047, 1105, 1717, 1854**

**Проблема:**
```python
documents, total_count = await client.get_documents(page=1, page_size=10)
# Нет таймаута - запрос может висеть бесконечно
```

**Решение:**
```python
import asyncio

async def get_documents_with_timeout(client, page=1, page_size=10, timeout=30):
    """Получает документы с таймаутом"""
    try:
        return await asyncio.wait_for(
            client.get_documents(page=page, page_size=page_size),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Таймаут при получении документов (>{timeout}с)")
        raise TimeoutError(f"Запрос превысил лимит времени ({timeout}с)")

# Использование:
try:
    documents, total_count = await get_documents_with_timeout(client)
except TimeoutError as e:
    ui.notify(f'Превышено время ожидания: {str(e)}', type='error')
    return
```

### 11. Неэффективная обработка больших списков
**Строки: 1854-1878**

**Проблема:**
```python
for document in documents:
    create_document_card(document, ...)  # Создает все карточки синхронно
```

**Риск:** При большом количестве документов UI блокируется.

**Решение:**
```python
async def create_documents_cards_batch(documents: List[MayanDocument], container: ui.column, batch_size: int = 10):
    """Создает карточки документов батчами для избежания блокировки UI"""
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        for document in batch:
            create_document_card(document, ...)
        
        # Даем UI время на обновление
        if i + batch_size < len(documents):
            await asyncio.sleep(0.1)  # Небольшая задержка между батчами
```

### 12. Отсутствие валидации входных данных
**Строки: 1072, 1291, 2045**

**Проблема:**
```python
async def search_documents(query: str):
    if not query.strip():  # Только проверка на пустоту
        return
    # Нет проверки на SQL injection, XSS в запросе
```

**Решение:**
```python
def validate_search_query(query: str, max_length: int = 200) -> str:
    """Валидирует поисковый запрос"""
    if not query:
        raise ValueError("Поисковый запрос не может быть пустым")
    
    query = query.strip()
    
    if len(query) > max_length:
        raise ValueError(f"Поисковый запрос слишком длинный (максимум {max_length} символов)")
    
    # Убираем опасные символы
    query = re.sub(r'[<>"\']', '', query)
    
    return query

# Использование:
try:
    safe_query = validate_search_query(query)
    documents = await client.search_documents(safe_query)
except ValueError as e:
    ui.notify(str(e), type='warning')
    return
```

### 13. Неправильная обработка исключений
**Строки: 201-209, 236-237**

**Проблема:**
```python
except Exception as e:
    logger.error(f"Неожиданная ошибка при загрузке документа: {e}", exc_info=True)
    self._notify_error(f"Неожиданная ошибка: {e}")  # ⚠️ Показывает пользователю детали ошибки
```

**Риск:** Утечка внутренней информации пользователю.

**Решение:**
```python
except Exception as e:
    logger.error(f"Неожиданная ошибка при загрузке документа: {e}", exc_info=True)
    # Не показываем детали пользователю
    self._notify_error("Произошла ошибка при загрузке документа. Обратитесь к администратору.")
```

### 14. Memory Leak в таймерах
**Строки: 655, 675, 695, 779, 1130**

**Проблема:**
```python
ui.timer(0.1, lambda: preview_html.on('click', show_full_preview), once=True)
ui.timer(0.1, load_preview, once=True)
ui.timer(0.1, lambda: update_file_size(document, pages_label), once=True)
```

**Риск:** Таймеры могут накапливаться, если создается много карточек.

**Решение:**
```python
# Сохраняйте ссылки на таймеры и отменяйте их при необходимости
class DocumentCard:
    def __init__(self, document: MayanDocument):
        self.document = document
        self.timers = []
    
    def add_timer(self, delay: float, callback, once: bool = True):
        timer = ui.timer(delay, callback, once=once)
        self.timers.append(timer)
        return timer
    
    def cleanup(self):
        """Отменяет все таймеры"""
        for timer in self.timers:
            try:
                timer.deactivate()
            except:
                pass
        self.timers.clear()
```

---

## 🟢 УЛУЧШЕНИЯ И BEST PRACTICES

### 15. Использование современных типов Python 3.12+
**Строки: 8, 74-99**

**Рекомендация:**
```python
# Вместо Optional[List[str]]
from typing import Optional, List

# Используйте:
from typing import Optional
from collections.abc import Sequence

tag_names: Optional[Sequence[str]] = None  # Более гибко

# Или используйте Union types (Python 3.10+)
tag_names: Sequence[str] | None = None
```

### 16. Использование dataclass для конфигурации
**Улучшение:**
```python
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass(frozen=True, slots=True)  # slots=True для Python 3.10+
class FileSize:
    """Размеры файлов в байтах"""
    MAX_SIZE: ClassVar[int] = 50 * 1024 * 1024
    WARNING_SIZE: ClassVar[int] = 10 * 1024 * 1024
```

### 17. Использование contextvars для контекста пользователя
**Вместо глобальной переменной `_current_user`:**
```python
from contextvars import ContextVar

current_user_context: ContextVar[Optional[Any]] = ContextVar('current_user', default=None)

def get_current_user_safe() -> Optional[Any]:
    """Безопасно получает текущего пользователя из контекста"""
    return current_user_context.get() or get_current_user()
```

### 18. Улучшение логирования
**Проблема:** Слишком много логирования на уровне INFO.

**Решение:**
```python
# Используйте уровни логирования правильно
logger.debug(f"Детали загрузки превью для документа {document.document_id}")  # Вместо info
logger.info(f"Документ {document.document_id} успешно загружен")  # Важные события
logger.warning(f"Необычный MIME-тип: {mimetype}")  # Предупреждения
logger.error(f"Ошибка при загрузке: {e}", exc_info=True)  # Ошибки
```

### 19. Добавление type hints везде
**Проблема:** Не все функции имеют type hints.

**Решение:**
```python
from typing import Awaitable, Callable

async def load_preview() -> None:  # Явный возвращаемый тип
    """Загружает превью документа"""
    ...

def create_document_card(
    document: MayanDocument,
    update_cabinet_title_func: Optional[Callable[[int], None]] = None,
    current_count: Optional[int] = None,
    documents_count_label: Optional[ui.label] = None,
    is_favorites_page: bool = False,
    favorites_count_label: Optional[ui.label] = None
) -> ui.card:
    ...
```

### 20. Использование структурных паттернов
**Рекомендация:** Разделить большой файл на модули:
- `mayan_documents/upload.py` - загрузка
- `mayan_documents/search.py` - поиск
- `mayan_documents/cards.py` - карточки документов
- `mayan_documents/access.py` - управление доступом
- `mayan_documents/state.py` - управление состоянием

---

## 📊 CORNER CASES

### 21. Обработка None значений
**Строки: 503, 516, 1361**

**Проблема:**
```python
def format_file_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None or size_bytes == 0:  # ✅ Хорошо
        return "размер неизвестен"
```

**Но в других местах:**
```python
filename = document.file_latest_filename or f"document_{document.document_id}"
# ⚠️ Если file_latest_filename = "", вернется пустая строка, а не fallback
```

**Решение:**
```python
filename = document.file_latest_filename if document.file_latest_filename else f"document_{document.document_id}"
# Или
filename = document.file_latest_filename or (f"document_{document.document_id}" if document.document_id else "unknown")
```

### 22. Деление на ноль
**Строка: 1908**

**Проблема:**
```python
total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
# ✅ Хорошо, но можно улучшить
```

**Улучшение:**
```python
total_pages = max(1, (total_count + page_size - 1) // page_size) if page_size > 0 else 1
```

### 23. Обработка пустых списков
**Строки: 1724, 1854**

**Хорошо обработано:**
```python
if not cabinets:
    with _recent_documents_container:
        ui.label('Кабинеты не найдены').classes('text-gray-500 text-center py-8')
    return
```

---

## ⚡ BOTTLENECKS (Узкие места производительности)

### 24. N+1 Problem при загрузке превью
**Строки: 591-671**

**Проблема:** Для каждого документа делается отдельный запрос превью.

**Решение:**
```python
async def load_previews_batch(document_ids: List[int], client: MayanClient) -> Dict[int, bytes]:
    """Загружает превью для нескольких документов параллельно"""
    tasks = [client.get_document_preview_image(doc_id) for doc_id in document_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    previews = {}
    for doc_id, result in zip(document_ids, results):
        if isinstance(result, Exception):
            logger.warning(f"Ошибка загрузки превью для {doc_id}: {result}")
        else:
            previews[doc_id] = result
    
    return previews
```

### 25. Синхронные операции в async функциях
**Строки: 222, 1364**

**Проблема:**
```python
file_content = upload_event.content.read()  # Синхронное чтение
```

**Решение:**
```python
# Если возможно, используйте async чтение
if hasattr(upload_event.content, 'read_async'):
    file_content = await upload_event.content.read_async()
else:
    # Используйте executor для блокирующих операций
    loop = asyncio.get_event_loop()
    file_content = await loop.run_in_executor(None, upload_event.content.read)
```

### 26. Отсутствие кэширования метаданных
**Строки: 1159, 1194**

**Проблема:** Типы документов и кабинеты загружаются каждый раз при открытии формы.

**Решение:**
```python
from functools import lru_cache
from datetime import datetime, timedelta

_metadata_cache = {}
_cache_ttl = timedelta(minutes=5)

async def get_cached_document_types(client: MayanClient) -> List[Dict]:
    """Получает типы документов с кэшированием"""
    cache_key = 'document_types'
    now = datetime.now()
    
    if cache_key in _metadata_cache:
        data, timestamp = _metadata_cache[cache_key]
        if now - timestamp < _cache_ttl:
            return data
    
    data = await client.get_document_types()
    _metadata_cache[cache_key] = (data, now)
    return data
```

---

## 📝 ИТОГОВЫЕ РЕКОМЕНДАЦИИ

### Приоритет 1 (Критично - исправить немедленно):
1. ✅ XSS через JavaScript injection (строки 635-648, 1769-1780)
2. ✅ Path traversal в именах файлов (строки 1361, 1392, 2045)
3. ✅ Race condition в get_mayan_client (строки 347-478)
4. ✅ Небезопасное удаление временных файлов (строки 1364-1372)

### Приоритет 2 (Важно - исправить в ближайшее время):
5. ✅ Валидация размера файла при чтении (строка 222)
6. ✅ Добавление таймаутов для запросов (строки 1047, 1105)
7. ✅ Улучшение обработки исключений (строки 201-209)
8. ✅ Рефакторинг глобальных переменных (строки 33-48)

### Приоритет 3 (Желательно - улучшения):
9. ✅ Rate limiting (строки 1072, 1132)
10. ✅ Оптимизация N+1 проблем (строки 591-671)
11. ✅ Кэширование метаданных (строки 1159, 1194)
12. ✅ Разделение на модули

---

**Дата review:** 2024
**Reviewer:** Senior Python Developer
**Версия Python:** 3.12+


