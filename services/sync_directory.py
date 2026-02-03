# services/sync_directory.py
"""Упрощенный сервис синхронизации файлов"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Set
import argparse
import signal

from services.directory_processor import DirectoryProcessor
from services.directory_watcher import DirectoryWatcher
from services.mayan_connector import MayanClient
from config.settings import config
from services.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


class FileProcessingStats:
    """Простой класс для статистики обработки"""
    
    def __init__(self):
        self.processed = 0
        self.skipped = 0
        self.errors = 0
    
    def increment_processed(self):
        self.processed += 1
    
    def increment_skipped(self):
        self.skipped += 1
    
    def increment_errors(self):
        self.errors += 1
    
    def print_summary(self):
        logger.info('=' * 60)
        logger.info('Статистика обработки:')
        logger.info(f'  Обработано файлов: {self.processed}')
        logger.info(f'  Пропущено (дубликаты): {self.skipped}')
        logger.info(f'  Ошибок: {self.errors}')
        logger.info('=' * 60)


async def process_file_async(
    file_path: Path, 
    processor: DirectoryProcessor, 
    stats: FileProcessingStats
):
    """
    Асинхронно обрабатывает один файл
    
    Args:
        file_path: Путь к файлу
        processor: Процессор директории
        stats: Объект статистики
    """
    try:
        logger.info(f'Обработка файла: {file_path}')
        
        result = await processor.process_file(file_path, check_duplicates=True)
        
        if result['success']:
            stats.increment_processed()
            logger.info(
                f"✓ Файл '{file_path.name}' успешно обработан. "
                f"Документ ID: {result['document_id']}"
            )
            if result.get('registered_number'):
                logger.info(f"  Присвоен номер: {result['registered_number']}")
        else:
            if result.get('error') == 'Дубликат: документ уже существует':
                stats.increment_skipped()
                logger.info(f"⊘ Файл '{file_path.name}' пропущен (дубликат)")
            else:
                stats.increment_errors()
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"✗ Ошибка обработки файла '{file_path.name}': {error_msg}")
    
    except Exception as e:
        stats.increment_errors()
        logger.error(f'Критическая ошибка при обработке файла {file_path}: {e}', exc_info=True)


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
        dry_run: Если True, только проверяет подключение
        scan_existing: Сканировать ли существующие файлы
        recursive: Мониторить ли поддиректории рекурсивно
        file_extensions: Множество расширений файлов для фильтрации
        watch_mode: Если True, запускает постоянный мониторинг
    
    Returns:
        Словарь с результатами синхронизации
    """
    watch_path = Path(watch_directory)
    stats = FileProcessingStats()
    
    # Валидация
    if not config.mayan_url:
        raise ValueError('MAYAN_URL не настроен в .env')
    if not config.mayan_username and not config.mayan_api_token:
        raise ValueError('MAYAN_USERNAME или MAYAN_API_TOKEN не настроен в .env')
    if not watch_path.exists() or not watch_path.is_dir():
        raise ValueError(f'Директория не существует или не является директорией: {watch_path}')
    
    # Логируем параметры запуска
    logger.info('=' * 60)
    logger.info('Начало синхронизации файлов из директории')
    logger.info(f'Директория: {watch_path}')
    logger.info(f"Режим: {'DRY RUN (тестовый)' if dry_run else 'PRODUCTION'}")
    logger.info(f"Мониторинг: {'ВКЛЮЧЕН' if watch_mode else 'ВЫКЛЮЧЕН (однократное сканирование)'}")
    logger.info(f"Сканирование существующих: {'ДА' if scan_existing else 'НЕТ'}")
    logger.info(f"Рекурсивный поиск: {'ДА' if recursive else 'НЕТ'}")
    logger.info('=' * 60)
    
    # Инициализация компонентов
    mayan_client = await MayanClient.create_with_user_credentials()
    
    try:
        # Режим тестирования
        if dry_run:
            logger.info('Тестовый режим: проверка подключений...')
            if await mayan_client.test_connection():
                logger.info('✓ Подключение к Mayan EDMS успешно')
                return {'success': True, 'processed': 0, 'skipped': 0, 'errors': []}
            else:
                logger.error('✗ Не удалось подключиться к Mayan EDMS')
                return {'success': False, 'processed': 0, 'skipped': 0, 'errors': ['Ошибка подключения']}
        
        # Создаем процессор
        processor = DirectoryProcessor(mayan_client)
        
        # Создаем очередь для асинхронной обработки
        file_queue = asyncio.Queue()
        processing_active = True
        
        # Callback для watchdog (синхронный контекст)
        def file_callback(file_path: Path):
            try:
                file_queue.put_nowait(file_path)
            except asyncio.QueueFull:
                logger.warning(f'Очередь переполнена, файл {file_path} отложен')
        
        # Задача обработки очереди
        async def process_queue():
            while processing_active or not file_queue.empty():
                try:
                    file_path = await asyncio.wait_for(file_queue.get(), timeout=1.0)
                    await process_file_async(file_path, processor, stats)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f'Ошибка в обработчике очереди: {e}', exc_info=True)
        
        # Запускаем обработчик очереди
        queue_task = asyncio.create_task(process_queue())
        
        # Создаем watcher
        watcher = DirectoryWatcher(
            watch_directory=watch_path,
            callback=file_callback,
            recursive=recursive
        )
        
        # Сканируем существующие файлы
        if scan_existing:
            watcher.scan_existing_files(file_extensions)
        
        # Запускаем watcher
        watcher.start()
        logger.info(f'Мониторинг запущен: {watch_path} (рекурсивно: {recursive})')
        
        try:
            if watch_mode:
                # Постоянный мониторинг
                def signal_handler(signum, frame):
                    logger.info('Получен сигнал остановки...')
                    nonlocal processing_active
                    processing_active = False
                
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)
                
                # Ждем прерывания
                while processing_active:
                    await asyncio.sleep(1)
            else:
                # Однократное сканирование - ждем опустошения очереди
                logger.info('Ожидание завершения обработки файлов...')
                max_wait = 300  # 5 минут
                waited = 0
                
                while waited < max_wait and not file_queue.empty():
                    await asyncio.sleep(0.5)
                    waited += 0.5
                
                if file_queue.empty():
                    logger.info('Все файлы обработаны')
                else:
                    logger.warning(f'Таймаут {max_wait} сек, в очереди еще {file_queue.qsize()} файлов')
                
                processing_active = False
        
        finally:
            # Останавливаем watcher
            watcher.stop()
            
            # Ждем завершения обработки очереди
            await asyncio.sleep(1)
            await queue_task
            
            # Выводим статистику
            stats.print_summary()
        
        logger.info('=' * 60)
        logger.info('Синхронизация завершена')
        logger.info('=' * 60)
        
        return {
            'success': stats.processed > 0 or stats.skipped > 0,
            'processed': stats.processed,
            'skipped': stats.skipped,
            'errors': []
        }
    
    except Exception as e:
        error_msg = f'Критическая ошибка синхронизации: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {'success': False, 'processed': 0, 'skipped': 0, 'errors': [error_msg]}
    
    finally:
        await mayan_client.close()


def main():
    """Точка входа скрипта"""
    parser = argparse.ArgumentParser(description='Синхронизация файлов из директории с Mayan EDMS')
    parser.add_argument('directory', type=str, nargs='?', default=None,
                       help='Директория для мониторинга')
    parser.add_argument('--dry-run', action='store_true',
                       help='Тестовый режим: только проверка подключений')
    parser.add_argument('--scan-existing', action='store_true',
                       help='Сканировать существующие файлы')
    parser.add_argument('--recursive', action='store_true',
                       help='Мониторить поддиректории рекурсивно')
    parser.add_argument('--extensions', type=str, default=None,
                       help='Расширения файлов (через запятую, например: .pdf,.docx)')
    parser.add_argument('--watch', action='store_true',
                       help='Постоянный мониторинг (иначе однократное сканирование)')
    
    args = parser.parse_args()
    
    # Определяем директорию
    watch_directory = args.directory or config.directory_watch_path
    if not watch_directory or not watch_directory.strip():
        logger.error('Директория не указана. Укажите путь в командной строке или установите DIRECTORY_WATCH_PATH в .env')
        sys.exit(1)
    
    # Параметры из конфигурации или аргументов
    scan_existing = args.scan_existing or config.directory_scan_existing
    recursive = args.recursive or config.directory_watch_recursive
    
    # Парсим расширения
    file_extensions = None
    if args.extensions:
        file_extensions = {ext.strip().lower() for ext in args.extensions.split(',') if ext.strip()}
    elif config.directory_watch_extensions:
        file_extensions = {ext.strip().lower() for ext in config.directory_watch_extensions.split(',') if ext.strip()}
    
    try:
        result = asyncio.run(sync_directory(
            watch_directory=watch_directory,
            dry_run=args.dry_run,
            scan_existing=scan_existing,
            recursive=recursive,
            file_extensions=file_extensions,
            watch_mode=args.watch
        ))
        
        sys.exit(0 if result['success'] else 1)
    
    except KeyboardInterrupt:
        logger.info('Синхронизация прервана пользователем')
        sys.exit(130)
    except Exception as e:
        logger.error(f'Критическая ошибка: {e}', exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()