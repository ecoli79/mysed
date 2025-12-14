# services/document_hash_cache.py
"""
Модуль для постоянного кеширования хешей документов из Mayan EDMS.
Использует SQLite для быстрого поиска дубликатов по хешу файла.
"""
import sqlite3
from pathlib import Path
from typing import Optional, Set, List, Dict, Any
from datetime import datetime
import json
import asyncio
from app_logging.logger import get_logger

logger = get_logger(__name__)


class DocumentHashCache:
    """
    Кеш хешей документов для быстрой проверки дубликатов.
    Использует SQLite с индексом по хешу для быстрого поиска.
    """
    
    def __init__(self, cache_db_path: Optional[Path] = None):
        """
        Инициализация кеша
        
        Args:
            cache_db_path: Путь к файлу SQLite базы данных. 
                          Если None, используется logs/document_hash_cache.db
        """
        if cache_db_path is None:
            # Используем директорию logs в корне проекта
            cache_db_path = Path(__file__).parent.parent / 'logs' / 'document_hash_cache.db'
        
        self.cache_db_path = Path(cache_db_path)
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Блокировка для потокобезопасности
        self._lock = asyncio.Lock()
        
        # Инициализируем базу данных
        self._init_database()
    
    def _init_database(self):
        """Инициализирует базу данных и создает таблицу если не существует"""
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # Создаем таблицу для хранения хешей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS document_hashes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hash TEXT NOT NULL UNIQUE,
                        document_id TEXT NOT NULL,
                        filename TEXT,
                        message_id TEXT,
                        cabinet_id INTEGER,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        metadata TEXT
                    )
                """)
                
                # Создаем уникальный индекс по хешу для быстрого поиска
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_hash_unique 
                    ON document_hashes(hash)
                """)
                
                # Создаем индекс по document_id для быстрого поиска по ID документа
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_document_id 
                    ON document_hashes(document_id)
                """)
                
                # Создаем индекс по message_id для быстрого поиска по message_id
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_id 
                    ON document_hashes(message_id)
                """)
                
                # Создаем индекс по cabinet_id для фильтрации по кабинету
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cabinet_id 
                    ON document_hashes(cabinet_id)
                """)
                
                conn.commit()
                
                logger.info(f"База данных кеша хешей инициализирована: {self.cache_db_path}")
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных кеша хешей: {e}", exc_info=True)
            raise
    
    def hash_exists(self, file_hash: str, cabinet_id: Optional[int] = None) -> bool:
        """
        Проверяет, существует ли хеш в кеше
        
        Args:
            file_hash: SHA256 хеш файла
            cabinet_id: ID кабинета для фильтрации (опционально)
        
        Returns:
            True если хеш найден, False иначе
        """
        if not file_hash:
            return False
        
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                cursor = conn.cursor()
                
                if cabinet_id is not None:
                    cursor.execute("""
                        SELECT 1 FROM document_hashes 
                        WHERE hash = ? AND cabinet_id = ?
                        LIMIT 1
                    """, (file_hash, cabinet_id))
                else:
                    cursor.execute("""
                        SELECT 1 FROM document_hashes 
                        WHERE hash = ?
                        LIMIT 1
                    """, (file_hash,))
                
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка проверки хеша в кеше: {e}", exc_info=True)
            return False
    
    def get_document_by_hash(
        self, 
        file_hash: str, 
        cabinet_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о документе по хешу
        
        Args:
            file_hash: SHA256 хеш файла
            cabinet_id: ID кабинета для фильтрации (опционально)
        
        Returns:
            Словарь с информацией о документе или None
        """
        if not file_hash:
            return None
        
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if cabinet_id is not None:
                    cursor.execute("""
                        SELECT * FROM document_hashes 
                        WHERE hash = ? AND cabinet_id = ?
                        LIMIT 1
                    """, (file_hash, cabinet_id))
                else:
                    cursor.execute("""
                        SELECT * FROM document_hashes 
                        WHERE hash = ?
                        LIMIT 1
                    """, (file_hash,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row['id'],
                        'hash': row['hash'],
                        'document_id': row['document_id'],
                        'filename': row['filename'],
                        'message_id': row['message_id'],
                        'cabinet_id': row['cabinet_id'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                        'metadata': json.loads(row['metadata']) if row['metadata'] else None
                    }
                return None
        except Exception as e:
            logger.error(f"Ошибка получения документа по хешу: {e}", exc_info=True)
            return None
    
    def add_hash(
        self,
        file_hash: str,
        document_id: str,
        filename: Optional[str] = None,
        message_id: Optional[str] = None,
        cabinet_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавляет хеш в кеш
        
        Args:
            file_hash: SHA256 хеш файла
            document_id: ID документа в Mayan EDMS
            filename: Имя файла
            message_id: Message-ID письма
            cabinet_id: ID кабинета
            metadata: Дополнительные метаданные
        
        Returns:
            True если успешно добавлено, False иначе
        """
        if not file_hash or not document_id:
            return False
        
        try:
            now = datetime.now().isoformat()
            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
            
            with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                cursor = conn.cursor()
                
                # Используем INSERT OR REPLACE для обновления существующих записей
                cursor.execute("""
                    INSERT OR REPLACE INTO document_hashes 
                    (hash, document_id, filename, message_id, cabinet_id, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM document_hashes WHERE hash = ?), ?),
                        ?, ?)
                """, (
                    file_hash, document_id, filename, message_id, cabinet_id,
                    file_hash, now,  # created_at (сохраняем оригинальную дату если запись существует)
                    now,  # updated_at
                    metadata_json
                ))
                
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Хеш уже существует, обновляем информацию
            try:
                now = datetime.now().isoformat()
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
                
                with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE document_hashes 
                        SET document_id = ?, filename = ?, message_id = ?, cabinet_id = ?,
                            updated_at = ?, metadata = ?
                        WHERE hash = ?
                    """, (document_id, filename, message_id, cabinet_id, now, metadata_json, file_hash))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка обновления хеша в кеше: {e}", exc_info=True)
                return False
        except Exception as e:
            logger.error(f"Ошибка добавления хеша в кеш: {e}", exc_info=True)
            return False
    
    def remove_hash(self, file_hash: str) -> bool:
        """
        Удаляет хеш из кеша
        
        Args:
            file_hash: SHA256 хеш файла
        
        Returns:
            True если успешно удалено, False иначе
        """
        if not file_hash:
            return False
        
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM document_hashes WHERE hash = ?", (file_hash,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка удаления хеша из кеша: {e}", exc_info=True)
            return False
    
    def get_all_hashes(self, cabinet_id: Optional[int] = None) -> Set[str]:
        """
        Получает все хеши из кеша
        
        Args:
            cabinet_id: ID кабинета для фильтрации (опционально)
        
        Returns:
            Множество всех хешей
        """
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                
                if cabinet_id is not None:
                    cursor.execute("SELECT hash FROM document_hashes WHERE cabinet_id = ?", (cabinet_id,))
                else:
                    cursor.execute("SELECT hash FROM document_hashes")
                
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Ошибка получения всех хешей из кеша: {e}", exc_info=True)
            return set()
    
    def get_count(self, cabinet_id: Optional[int] = None) -> int:
        """
        Получает количество хешей в кеше
        
        Args:
            cabinet_id: ID кабинета для фильтрации (опционально)
        
        Returns:
            Количество хешей
        """
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=10.0) as conn:
                cursor = conn.cursor()
                
                if cabinet_id is not None:
                    cursor.execute("SELECT COUNT(*) FROM document_hashes WHERE cabinet_id = ?", (cabinet_id,))
                else:
                    cursor.execute("SELECT COUNT(*) FROM document_hashes")
                
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка получения количества хешей: {e}", exc_info=True)
            return 0
    
    async def sync_from_mayan(
        self,
        mayan_client,
        cabinet_id: Optional[int] = None,
        max_pages: int = 100
    ) -> int:
        """
        Синхронизирует кеш с документами из Mayan EDMS
        
        Args:
            mayan_client: Клиент Mayan EDMS
            cabinet_id: ID кабинета для синхронизации
            max_pages: Максимальное количество страниц для проверки
        
        Returns:
            Количество добавленных/обновленных записей
        """
        async with self._lock:
            logger.info(f"Начинаем синхронизацию кеша хешей из Mayan (кабинет: {cabinet_id})...")
            
            synced_count = 0
            checked_documents = 0
            
            try:
                for page in range(1, max_pages + 1):
                    documents = await mayan_client.get_documents(
                        page=page,
                        page_size=100,
                        cabinet_id=cabinet_id
                    )
                    
                    if not documents:
                        break
                    
                    for doc in documents:
                        checked_documents += 1
                        
                        try:
                            if not doc.description:
                                continue
                            
                            # Парсим метаданные
                            try:
                                metadata = json.loads(doc.description)
                            except json.JSONDecodeError:
                                # Если не JSON, пробуем найти хеш в тексте
                                if 'attachment_hash' in doc.description:
                                    # Извлекаем хеш из текста (простой поиск)
                                    import re
                                    hash_match = re.search(r'"attachment_hash"\s*:\s*"([a-f0-9]{64})"', doc.description)
                                    if hash_match:
                                        file_hash = hash_match.group(1)
                                        if self.add_hash(
                                            file_hash=file_hash,
                                            document_id=str(doc.id),
                                            filename=metadata.get('attachment_filename') if 'attachment_filename' in doc.description else None,
                                            message_id=metadata.get('email_message_id') if 'email_message_id' in doc.description else None,
                                            cabinet_id=cabinet_id,
                                            metadata={'source': 'text_parsing'}
                                        ):
                                            synced_count += 1
                                continue
                            
                            # Извлекаем хеш из метаданных
                            file_hash = metadata.get('attachment_hash')
                            if not file_hash:
                                continue
                            
                            # Добавляем в кеш
                            if self.add_hash(
                                file_hash=file_hash,
                                document_id=str(doc.id),
                                filename=metadata.get('attachment_filename'),
                                message_id=metadata.get('email_message_id'),
                                cabinet_id=cabinet_id,
                                metadata=metadata
                            ):
                                synced_count += 1
                        
                        except Exception as e:
                            logger.debug(f"Ошибка обработки документа {doc.id}: {e}")
                            continue
                
                logger.info(
                    f"Синхронизация завершена: проверено {checked_documents} документов, "
                    f"добавлено/обновлено {synced_count} записей в кеш"
                )
                return synced_count
                
            except Exception as e:
                logger.error(f"Ошибка синхронизации кеша из Mayan: {e}", exc_info=True)
                return synced_count
    
    def clear_cache(self, cabinet_id: Optional[int] = None) -> bool:
        """
        Очищает кеш
        
        Args:
            cabinet_id: ID кабинета для очистки (если None, очищает весь кеш)
        
        Returns:
            True если успешно очищено, False иначе
        """
        try:
            with sqlite3.connect(str(self.cache_db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                
                if cabinet_id is not None:
                    cursor.execute("DELETE FROM document_hashes WHERE cabinet_id = ?", (cabinet_id,))
                else:
                    cursor.execute("DELETE FROM document_hashes")
                
                conn.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Кеш очищен: удалено {deleted_count} записей")
                return True
        except Exception as e:
            logger.error(f"Ошибка очистки кеша: {e}", exc_info=True)
            return False
