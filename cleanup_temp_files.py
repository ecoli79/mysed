#!/usr/bin/env python3
"""
Скрипт для поиска и удаления временных BPMN файлов
"""

import os
import glob
import tempfile
from datetime import datetime, timedelta
from app_logging.logger import setup_logging, get_logger

# Настройка логирования
setup_logging()
logger = get_logger(__name__)

def find_temp_bpmn_files():
    """Находит все временные BPMN файлы в системе"""
    temp_files = []
    
    # Стандартные временные директории
    temp_dirs = [
        '/tmp',
        tempfile.gettempdir(),
        os.path.expanduser('~/.cache'),
        '/var/tmp'
    ]
    
    # Добавляем текущую рабочую директорию
    temp_dirs.append(os.getcwd())
    
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            # Ищем файлы с паттерном tmp*.bpmn
            pattern = os.path.join(temp_dir, 'tmp*.bpmn')
            files = glob.glob(pattern)
            temp_files.extend(files)
            
            # Ищем файлы с паттерном tmp* (без расширения)
            pattern2 = os.path.join(temp_dir, 'tmp*')
            files2 = glob.glob(pattern2)
            # Фильтруем только файлы, которые выглядят как временные
            for f in files2:
                if os.path.isfile(f) and os.path.basename(f).startswith('tmp') and len(os.path.basename(f)) > 3:
                    temp_files.append(f)
    
    return list(set(temp_files))  # Убираем дубликаты

def analyze_temp_file(file_path):
    """Анализирует временный файл"""
    try:
        stat = os.stat(file_path)
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        
        # Читаем первые несколько строк для анализа содержимого
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(500)
        
        is_bpmn = '<definitions' in content and '<process' in content
        has_doctype = '<!DOCTYPE' in content.upper()
        
        return {
            'size': size,
            'mtime': mtime,
            'age': age,
            'is_bpmn': is_bpmn,
            'has_doctype': has_doctype,
            'content_preview': content[:200] + '...' if len(content) > 200 else content
        }
    except Exception as e:
        logger.error(f"Ошибка при анализе файла {file_path}: {e}")
        return None

def cleanup_temp_files(dry_run=True, max_age_hours=24):
    """Очищает временные файлы"""
    logger.info("Поиск временных BPMN файлов...")
    
    temp_files = find_temp_bpmn_files()
    
    if not temp_files:
        logger.info("Временные файлы не найдены")
        return
    
    logger.info(f"Найдено {len(temp_files)} потенциальных временных файлов:")
    
    files_to_delete = []
    
    for file_path in temp_files:
        analysis = analyze_temp_file(file_path)
        if analysis:
            logger.info(f"\nФайл: {file_path}")
            logger.info(f"  Размер: {analysis['size']} байт")
            logger.info(f"  Возраст: {analysis['age']}")
            logger.info(f"  BPMN: {'Да' if analysis['is_bpmn'] else 'Нет'}")
            logger.info(f"  DOCTYPE: {'Да' if analysis['has_doctype'] else 'Нет'}")
            logger.info(f"  Содержимое: {analysis['content_preview']}")
            
            # Решаем, удалять ли файл
            should_delete = False
            reason = ""
            
            if analysis['age'] > timedelta(hours=max_age_hours):
                should_delete = True
                reason = f"Файл старше {max_age_hours} часов"
            elif analysis['is_bpmn'] and analysis['has_doctype']:
                should_delete = True
                reason = "BPMN файл с DOCTYPE (проблемный)"
            elif analysis['is_bpmn'] and analysis['age'] > timedelta(hours=1):
                should_delete = True
                reason = "Старый BPMN файл"
            elif not analysis['is_bpmn'] and analysis['age'] > timedelta(minutes=30):
                should_delete = True
                reason = "Старый не-BPMN файл"
            
            if should_delete:
                files_to_delete.append((file_path, reason))
                logger.info(f"  -> БУДЕТ УДАЛЕН: {reason}")
            else:
                logger.info(f"  -> ОСТАВЛЕН")
    
    if not files_to_delete:
        logger.info("\nНет файлов для удаления")
        return
    
    logger.info(f"\nНайдено {len(files_to_delete)} файлов для удаления:")
    for file_path, reason in files_to_delete:
        logger.info(f"  {file_path} - {reason}")
    
    if dry_run:
        logger.info("\nРЕЖИМ ПРОСМОТРА: файлы НЕ будут удалены")
        logger.info("Для удаления запустите с параметром --delete")
    else:
        logger.info("\nУдаление файлов...")
        deleted_count = 0
        for file_path, reason in files_to_delete:
            try:
                os.unlink(file_path)
                logger.info(f"Удален: {file_path}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Ошибка при удалении {file_path}: {e}")
        
        logger.info(f"\nУдалено {deleted_count} из {len(files_to_delete)} файлов")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Очистка временных BPMN файлов')
    parser.add_argument('--delete', action='store_true', 
                       help='Реально удалить файлы (по умолчанию только просмотр)')
    parser.add_argument('--max-age', type=int, default=24,
                       help='Максимальный возраст файлов в часах (по умолчанию 24)')
    
    args = parser.parse_args()
    
    logger.info("=== Очистка временных BPMN файлов ===")
    logger.info(f"Режим: {'УДАЛЕНИЕ' if args.delete else 'ПРОСМОТР'}")
    logger.info(f"Максимальный возраст: {args.max_age} часов")
    
    cleanup_temp_files(dry_run=not args.delete, max_age_hours=args.max_age)

if __name__ == '__main__':
    main()
