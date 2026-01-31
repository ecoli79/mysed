# services/sync_directory.py
import sys
import os
import asyncio
from pathlib import Path

# Добавляем путь к проекту
project_path = Path(__file__).parent.parent
sys.path.insert(0, str(project_path))

import logging
from typing import Optional, Set
import argparse
import signal

from services.directory_processor import DirectoryProcessor
from services.directory_watcher import DirectoryWatcher
from services.mayan_connector import MayanClient
from config.settings import config
from app_logging.logger import setup_logging, get_logger

# Настраиваем логирование
setup_logging()
logger = get_logger(__name__)


class DirectorySyncService:
    """Сервис для синхронизации файлов из директории с Mayan EDMS"""
    
    def __init__(self, watch_directory: Path, scan_existing: bool = False):
        """
        Инициализация сервиса
        
        Args:
            watch_directory: Директория для мониторинга
            scan_existing: Сканировать ли существующие файлы при запуске
        """
        self.watch_directory = Path(watch_directory)
        self.scan_existing = scan_existing
        self.mayan_client: Optional[MayanClient] = None
        self.directory_processor: Optional[DirectoryProcessor] = None
        self.watcher: Optional[DirectoryWatcher] = None
        self.running = False
        self._file_queue: asyncio.Queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        
        # Статистика
        self.stats = {
            'processed': 0,
            'skipped': 0,
            'errors': 0
        }
    
    async def _initialize(self):
        """Инициализирует компоненты"""
        logger.info("Инициализация компонентов...")
        
        # Mayan клиент
        self.mayan_client = await MayanClient.create_with_user_credentials()
        
        # Обработчик файлов
        self.directory_processor = DirectoryProcessor(self.mayan_client)
        
        logger.info("Компоненты инициализированы успешно")
    
    async def _process_file(self, file_path: Path):
        """
        Обрабатывает файл
        
        Args:
            file_path: Путь к файлу
        """
        try:
            logger.info(f"Обработка файла: {file_path}")
            
            result = await self.directory_processor.process_file(
                file_path,
                check_duplicates=True
            )
            
            if result['success']:
                self.stats['processed'] += 1
                logger.info(
                    f"✓ Файл '{file_path.name}' успешно обработан. "
                    f"Документ ID: {result['document_id']}"
                )
                if result.get('registered_number'):
                    logger.info(f"  Присвоен номер: {result['registered_number']}")
            else:
                if result.get('error') == 'Дубликат: документ уже существует':
                    self.stats['skipped'] += 1
                    logger.info(f"⊘ Файл '{file_path.name}' пропущен (дубликат)")
                else:
                    self.stats['errors'] += 1
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"✗ Ошибка обработки файла '{file_path.name}': {error_msg}")
        
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Критическая ошибка при обработке файла {file_path}: {e}", exc_info=True)
    
    def _file_callback(self, file_path: Path):
        """
        Callback для обработки новых файлов (вызывается из синхронного контекста watchdog)
        
        Args:
            file_path: Путь к файлу
        """
        # Добавляем файл в очередь для асинхронной обработки
        try:
            self._file_queue.put_nowait(file_path)
        except asyncio.QueueFull:
            logger.warning(f"Очередь файлов переполнена, файл {file_path} будет обработан позже")
    
    async def _process_file_queue(self):
        """Обрабатывает файлы из очереди"""
        while self.running:
            try:
                # Ждем файл из очереди с таймаутом
                file_path = await asyncio.wait_for(self._file_queue.get(), timeout=1.0)
                await self._process_file(file_path)
            except asyncio.TimeoutError:
                # Таймаут - продолжаем цикл
                continue
            except Exception as e:
                logger.error(f"Ошибка при обработке очереди файлов: {e}", exc_info=True)
    
    async def start_watching(self, recursive: bool = False, file_extensions: Optional[Set[str]] = None):
        """
        Запускает мониторинг директории
        
        Args:
            recursive: Мониторить ли поддиректории рекурсивно
            file_extensions: Множество расширений файлов для фильтрации
        """
        if not self.mayan_client or not self.directory_processor:
            await self._initialize()
        
        # Создаем наблюдатель
        self.watcher = DirectoryWatcher(
            watch_directory=self.watch_directory,
            callback=self._file_callback,
            recursive=recursive
        )
        
        # Запускаем задачу обработки очереди файлов
        self.running = True
        self._processing_task = asyncio.create_task(self._process_file_queue())
        
        # Сканируем существующие файлы, если нужно
        if self.scan_existing:
            self.watcher.scan_existing_files(file_extensions)
        
        # Запускаем мониторинг
        self.watcher.start()
        
        logger.info(
            f"Мониторинг директории запущен: {self.watch_directory} "
            f"(рекурсивно: {recursive})"
        )
    
    def stop_watching(self):
        """Останавливает мониторинг"""
        self.running = False
        if self.watcher:
            self.watcher.stop()
        if self._processing_task:
            self._processing_task.cancel()
        logger.info("Мониторинг остановлен")
    
    async def close(self):
        """Закрывает соединения"""
        self.stop_watching()
        if self.mayan_client:
            await self.mayan_client.close()
    
    def print_stats(self):
        """Выводит статистику"""
        logger.info("=" * 60)
        logger.info("Статистика обработки:")
        logger.info(f"  Обработано файлов: {self.stats['processed']}")
        logger.info(f"  Пропущено (дубликаты): {self.stats['skipped']}")
        logger.info(f"  Ошибок: {self.stats['errors']}")
        logger.info("=" * 60)


async def sync_directory(
    watch_directory: str,
    dry_run: bool = False,
    scan_existing: bool = False,
    recursive: bool = False,
    file_extensions: Optional[Set[str]] = None,
    watch_mode: bool = False
) -> dict:
    """
    Синхронизирует файлы из директории с Mayan EDMS
    
    Args:
        watch_directory: Директория для мониторинга
        dry_run: Если True, только проверяет подключение, не обрабатывает файлы
        scan_existing: Сканировать ли существующие файлы при запуске
        recursive: Мониторить ли поддиректории рекурсивно
        file_extensions: Множество расширений файлов для фильтрации
        watch_mode: Если True, запускает постоянный мониторинг, иначе однократное сканирование
    
    Returns:
        Словарь с результатами синхронизации
    """
    result = {
        'success': False,
        'processed': 0,
        'skipped': 0,
        'errors': []
    }
    
    watch_path = Path(watch_directory)
    
    try:
        logger.info("=" * 60)
        logger.info("Начало синхронизации файлов из директории")
        logger.info(f"Директория: {watch_path}")
        logger.info(f"Режим: {'DRY RUN (тестовый)' if dry_run else 'PRODUCTION'}")
        logger.info(f"Мониторинг: {'ВКЛЮЧЕН (постоянный)' if watch_mode else 'ВЫКЛЮЧЕН (однократное сканирование)'}")
        logger.info(f"Сканирование существующих: {'ДА' if scan_existing else 'НЕТ'}")
        logger.info(f"Рекурсивный поиск: {'ДА' if recursive else 'НЕТ'}")
        logger.info("=" * 60)
        
        # Проверяем конфигурацию
        if not config.mayan_url:
            raise ValueError("MAYAN_URL не настроен в .env")
        if not config.mayan_username and not config.mayan_api_token:
            raise ValueError("MAYAN_USERNAME или MAYAN_API_TOKEN не настроен в .env")
        
        # Проверяем существование директории
        if not watch_path.exists():
            raise ValueError(f"Директория не существует: {watch_path}")
        
        if not watch_path.is_dir():
            raise ValueError(f"Путь не является директорией: {watch_path}")
        
        # Инициализируем сервис
        service = DirectorySyncService(watch_path, scan_existing=scan_existing)
        
        if dry_run:
            # Тестовый режим - только проверка подключения
            logger.info("Тестовый режим: проверка подключений...")
            
            await service._initialize()
            
            # Проверяем подключение к Mayan EDMS
            if await service.mayan_client.test_connection():
                logger.info("✓ Подключение к Mayan EDMS успешно")
            else:
                logger.error("✗ Не удалось подключиться к Mayan EDMS")
                result['errors'].append("Ошибка подключения к Mayan EDMS")
                await service.close()
                return result
            
            logger.info("Все подключения работают корректно")
            result['success'] = True
            await service.close()
            return result
        
        # Запускаем мониторинг или однократное сканирование
        if watch_mode:
            # Режим постоянного мониторинга
            await service.start_watching(recursive=recursive, file_extensions=file_extensions)
            
            # Ожидаем сигнала остановки
            def signal_handler(signum, frame):
                logger.info("Получен сигнал остановки...")
                service.stop_watching()
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            try:
                # Бесконечный цикл ожидания
                while service.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Получен сигнал прерывания...")
                service.stop_watching()
            
            # Обновляем результат из статистики
            result['processed'] = service.stats['processed']
            result['skipped'] = service.stats['skipped']
            result['success'] = service.stats['processed'] > 0 or service.stats['skipped'] > 0
            
            service.print_stats()
            await service.close()
        else:
            # Однократное сканирование
            await service.start_watching(recursive=recursive, file_extensions=file_extensions)
            
            # Ждем немного, чтобы обработались все файлы
            await asyncio.sleep(2)
            
            service.stop_watching()
            
            # Обновляем результат из статистики
            result['processed'] = service.stats['processed']
            result['skipped'] = service.stats['skipped']
            result['success'] = service.stats['processed'] > 0 or service.stats['skipped'] > 0
            
            service.print_stats()
            await service.close()
        
        logger.info("=" * 60)
        logger.info("Синхронизация завершена")
        logger.info(f"Обработано файлов: {result['processed']}")
        logger.info(f"Пропущено (дубликаты): {result['skipped']}")
        if result['errors']:
            logger.warning(f"Ошибок: {len(result['errors'])}")
            for error in result['errors']:
                logger.warning(f"  - {error}")
        logger.info("=" * 60)
        
    except Exception as e:
        error_msg = f"Критическая ошибка синхронизации: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result['errors'].append(error_msg)
        result['success'] = False
    
    return result


def main():
    """Точка входа скрипта"""
    parser = argparse.ArgumentParser(description='Синхронизация файлов из директории с Mayan EDMS')
    parser.add_argument(
        'directory',
        type=str,
        help='Директория для мониторинга'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Тестовый режим: только проверка подключений'
    )
    parser.add_argument(
        '--scan-existing',
        action='store_true',
        help='Сканировать существующие файлы при запуске'
    )
    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Мониторить поддиректории рекурсивно'
    )
    parser.add_argument(
        '--extensions',
        type=str,
        default=None,
        help='Расширения файлов для фильтрации (через запятую, например: .pdf,.docx,.doc)'
    )
    parser.add_argument(
        '--watch',
        action='store_true',
        help='Запустить постоянный мониторинг (иначе однократное сканирование)'
    )
    
    args = parser.parse_args()
    
    # Парсим расширения файлов
    file_extensions = None
    if args.extensions:
        file_extensions = {ext.strip().lower() for ext in args.extensions.split(',') if ext.strip()}
        logger.info(f"Фильтр расширений: {file_extensions}")
    
    try:
        result = asyncio.run(sync_directory(
            watch_directory=args.directory,
            dry_run=args.dry_run,
            scan_existing=args.scan_existing,
            recursive=args.recursive,
            file_extensions=file_extensions,
            watch_mode=args.watch
        ))
        
        if result['success']:
            sys.exit(0)
        else:
            logger.error("Синхронизация завершилась с ошибками")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Синхронизация прервана пользователем")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

