#!/usr/bin/env python3
"""
Скрипт для очистки данных из базы данных Camunda.

Этот скрипт позволяет очистить различные типы данных из базы данных Camunda:
- ACT_HI_* - исторические данные (завершенные процессы)
- ACT_RU_* - runtime данные (активные процессы и задачи)
- ACT_RE_* - repository данные (определения процессов)
- ACT_ID_* - identity данные (пользователи и группы)
- ACT_GE_* - general данные (общие данные и байт-массивы)

ВНИМАНИЕ: Операция необратима! Убедитесь, что у вас есть резервная копия перед выполнением.

Использование:
    # 1. Создайте файл конфигурации:
    cd scripts
    cp .env.example .env
    # Отредактируйте .env и укажите реальные значения
    
    # 2. Запустите скрипт:
    # Очистка только исторических данных (по умолчанию):
    python scripts/cleanup_camunda_history.py
    
    # Очистка истории и активных процессов:
    python scripts/cleanup_camunda_history.py --history --runtime
    
    # Полная очистка всех данных (кроме identity):
    python scripts/cleanup_camunda_history.py --all
    
    # С переменными окружения (переопределяют .env):
    POSTGRES_HOST=localhost CAMUNDA_DATABASE_PASSWORD=password \
    python scripts/cleanup_camunda_history.py --history --runtime
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2 import sql
import argparse
from datetime import datetime

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from config.settings import config
except ImportError:
    config = None


def load_env_file(envPath: Path) -> Dict[str, str]:
    """
    Загружает переменные окружения из .env файла.
    
    Args:
        envPath: Путь к .env файлу
        
    Returns:
        Словарь с переменными окружения
    """
    envVars = {}
    
    if not envPath.exists():
        return envVars
    
    try:
        with open(envPath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                
                # Парсим строку KEY=VALUE или KEY="VALUE"
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip()
                    
                    # Убираем кавычки если есть
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    envVars[key] = value
    except Exception as e:
        print(f"⚠️  Предупреждение: Не удалось загрузить .env файл {envPath}: {e}")
    
    return envVars


def find_env_file() -> Optional[Path]:
    """
    Ищет .env файл в возможных местах.
    Приоритет поиска:
    1. scripts/.env (там же где скрипт)
    2. Docker-compose/.env
    3. Корень проекта .env
    
    Returns:
        Путь к найденному .env файлу или None
    """
    # Приоритет 1: scripts/.env (там же где скрипт)
    scriptDir = Path(__file__).parent
    scriptEnv = scriptDir / '.env'
    if scriptEnv.exists():
        return scriptEnv
    
    # Приоритет 2: Docker-compose/.env
    dockerComposeEnv = project_root / 'Docker-compose' / '.env'
    if dockerComposeEnv.exists():
        return dockerComposeEnv
    
    # Приоритет 3: Корень проекта .env
    rootEnv = project_root / '.env'
    if rootEnv.exists():
        return rootEnv
    
    return None


def get_db_config(verbose: bool = False) -> Dict[str, Any]:
    """
    Получает конфигурацию базы данных из переменных окружения или .env файла.
    
    Args:
        verbose: Если True, выводит информацию о загруженных настройках
        
    Returns:
        Словарь с параметрами подключения к БД
    """
    # Сначала загружаем .env файл
    envFile = find_env_file()
    envVars = {}
    
    if envFile:
        if verbose:
            print(f"📄 Загрузка переменных из: {envFile}")
        envVars = load_env_file(envFile)
    else:
        if verbose:
            print("⚠️  .env файл не найден, используются переменные окружения")
    
    # Параметры подключения к PostgreSQL
    # Приоритет: переменные окружения > .env файл > значения по умолчанию
    # Используем os.getenv для проверки явно установленных переменных окружения,
    # но если их нет, берем из envVars (загруженного .env файла)
    dbHost = os.getenv('POSTGRES_HOST') or envVars.get('POSTGRES_HOST', 'localhost')
    dbPort = int(os.getenv('POSTGRES_PORT') or envVars.get('POSTGRES_PORT', '5432'))
    dbName = os.getenv('CAMUNDA_DATABASE_NAME') or envVars.get('CAMUNDA_DATABASE_NAME', 'camunda')
    dbUser = os.getenv('CAMUNDA_DATABASE_USER') or envVars.get('CAMUNDA_DATABASE_USER', 'camunda')
    dbPassword = os.getenv('CAMUNDA_DATABASE_PASSWORD') or envVars.get('CAMUNDA_DATABASE_PASSWORD', '')
    
    # Если хост указан как имя Docker сервиса, но мы запускаемся локально, используем localhost
    if dbHost in ['postgresql', 'postgres'] and not os.path.exists('/.dockerenv'):
        if verbose:
            print(f"   ⚠️  Хост '{dbHost}' похож на имя Docker сервиса, но скрипт запущен локально")
            print(f"   Используется 'localhost' вместо '{dbHost}'")
        dbHost = 'localhost'
    
    # Если есть доступ к config, используем его значения как fallback
    # НО только если значения НЕ были установлены из .env файла
    # Приоритет: .env файл > config > значения по умолчанию
    userFromEnv = envVars.get('CAMUNDA_DATABASE_USER') or os.getenv('CAMUNDA_DATABASE_USER')
    passwordFromEnv = envVars.get('CAMUNDA_DATABASE_PASSWORD') or os.getenv('CAMUNDA_DATABASE_PASSWORD')
    
    if config and hasattr(config, 'camunda_username'):
        configUser = getattr(config, 'camunda_username', None)
        configPassword = getattr(config, 'camunda_password', None)
        
        if verbose and configUser:
            print(f"   Config camunda_username: {configUser}")
        
        # Используем значения из config ТОЛЬКО если они не были установлены из .env
        if not userFromEnv:
            if not dbUser or dbUser == 'camunda':
                oldUser = dbUser
                dbUser = configUser or dbUser
                if verbose and oldUser != dbUser and configUser:
                    print(f"   ⚠️  Пользователь изменен с '{oldUser}' на '{dbUser}' из config")
        
        if not passwordFromEnv and not dbPassword and configPassword:
            dbPassword = configPassword
            if verbose:
                print(f"   ⚠️  Пароль загружен из config")
    
    if not dbPassword:
        scriptEnv = Path(__file__).parent / '.env'
        envFileHint = ""
        if envFile:
            envFileHint = f"\nПроверьте файл: {envFile}"
        else:
            envFileHint = f"\nСоздайте файл: {scriptEnv} (можно скопировать из .env.example)"
        raise ValueError(
            f'CAMUNDA_DATABASE_PASSWORD не установлен.{envFileHint}\n'
            'Установите переменную окружения CAMUNDA_DATABASE_PASSWORD '
            'или добавьте её в .env файл в директории scripts/'
        )
    
    if verbose:
        print(f"   Хост: {dbHost}")
        print(f"   Порт: {dbPort}")
        print(f"   База данных: {dbName}")
        print(f"   Пользователь: {dbUser}")
        print(f"   Пароль: {'*' * len(dbPassword) if dbPassword else 'НЕ УСТАНОВЛЕН'}")
        if envFile:
            print(f"   Источник: {envFile}")
        else:
            print(f"   Источник: переменные окружения")
        
        # Отладочная информация
        if verbose:
            print(f"\n   Отладка загрузки переменных:")
            print(f"   POSTGRES_HOST из env: {os.getenv('POSTGRES_HOST', 'НЕТ')}")
            print(f"   POSTGRES_HOST из .env файла: {envVars.get('POSTGRES_HOST', 'НЕТ')}")
            print(f"   CAMUNDA_DATABASE_USER из env: {os.getenv('CAMUNDA_DATABASE_USER', 'НЕТ')}")
            print(f"   CAMUNDA_DATABASE_USER из .env файла: {envVars.get('CAMUNDA_DATABASE_USER', 'НЕТ')}")
            print(f"   CAMUNDA_DATABASE_PASSWORD из env: {'ЕСТЬ' if os.getenv('CAMUNDA_DATABASE_PASSWORD') else 'НЕТ'}")
            print(f"   CAMUNDA_DATABASE_PASSWORD из .env файла: {'ЕСТЬ' if envVars.get('CAMUNDA_DATABASE_PASSWORD') else 'НЕТ'}")
    
    return {
        'host': dbHost,
        'port': dbPort,
        'database': dbName,
        'user': dbUser,
        'password': dbPassword
    }


def get_camunda_tables(conn, tablePrefix: str = None, schema: str = 'public') -> List[str]:
    """
    Получает список таблиц Camunda по префиксу.
    
    Args:
        conn: Соединение с базой данных
        tablePrefix: Префикс таблиц (например, 'ACT_HI_', 'ACT_RU_', 'ACT_RE_')
                     Если None, возвращает все таблицы Camunda
        schema: Схема базы данных (по умолчанию 'public')
        
    Returns:
        Список имен таблиц
    """
    try:
        with conn.cursor() as cur:
            if tablePrefix:
                # Используем ILIKE для case-insensitive поиска (PostgreSQL)
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s
                    AND table_name ILIKE %s
                    ORDER BY table_name;
                """, (schema, f'{tablePrefix}%'))
            else:
                # Используем ILIKE для case-insensitive поиска (PostgreSQL)
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s
                    AND table_name ILIKE 'act_%'
                    ORDER BY table_name;
                """, (schema,))
            tables = [row[0] for row in cur.fetchall()]
        return tables
    except Exception as e:
        # Если ошибка доступа к схеме, возвращаем пустой список
        return []


def get_all_schemas(conn) -> List[str]:
    """
    Получает список всех схем в базе данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен схем
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name;
        """)
        schemas = [row[0] for row in cur.fetchall()]
    return schemas


def find_camunda_tables_in_all_schemas(conn, tablePrefix: str = None) -> Dict[str, List[str]]:
    """
    Ищет таблицы Camunda во всех схемах базы данных.
    
    Args:
        conn: Соединение с базой данных
        tablePrefix: Префикс таблиц (например, 'ACT_HI_', 'ACT_RU_')
        
    Returns:
        Словарь {schema_name: [table_names]}
    """
    try:
        schemas = get_all_schemas(conn)
        result = {}
        
        for schema in schemas:
            try:
                tables = get_camunda_tables(conn, tablePrefix, schema)
                if tables:
                    result[schema] = tables
            except Exception as e:
                # Пропускаем схемы, к которым нет доступа
                continue
        
        return result
    except Exception as e:
        # Если не удалось получить схемы, возвращаем пустой словарь
        return {}


def get_history_tables(conn) -> List[str]:
    """
    Получает список всех таблиц истории (ACT_HI_*) из базы данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен таблиц истории
    """
    return get_camunda_tables(conn, 'ACT_HI_')


def get_runtime_tables(conn) -> List[str]:
    """
    Получает список всех runtime таблиц (ACT_RU_*) из базы данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен runtime таблиц
    """
    return get_camunda_tables(conn, 'ACT_RU_')


def get_repository_tables(conn) -> List[str]:
    """
    Получает список всех repository таблиц (ACT_RE_*) из базы данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен repository таблиц
    """
    return get_camunda_tables(conn, 'ACT_RE_')


def get_identity_tables(conn) -> List[str]:
    """
    Получает список всех identity таблиц (ACT_ID_*) из базы данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен identity таблиц
    """
    return get_camunda_tables(conn, 'ACT_ID_')


def get_general_tables(conn) -> List[str]:
    """
    Получает список всех general таблиц (ACT_GE_*) из базы данных.
    
    Args:
        conn: Соединение с базой данных
        
    Returns:
        Список имен general таблиц
    """
    return get_camunda_tables(conn, 'ACT_GE_')


def get_table_row_count(conn, tableName: str) -> int:
    """
    Получает количество строк в таблице.
    
    Args:
        conn: Соединение с базой данных
        tableName: Имя таблицы
        
    Returns:
        Количество строк
    """
    with conn.cursor() as cur:
        cur.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(
            sql.Identifier(tableName)
        ))
        return cur.fetchone()[0]


def truncate_table(conn, tableName: str) -> int:
    """
    Очищает таблицу (TRUNCATE).
    
    Args:
        conn: Соединение с базой данных
        tableName: Имя таблицы
        
    Returns:
        Количество удаленных строк (0 для TRUNCATE, но возвращаем для совместимости)
    """
    with conn.cursor() as cur:
        # Используем TRUNCATE для быстрой очистки
        cur.execute(sql.SQL('TRUNCATE TABLE {} CASCADE').format(
            sql.Identifier(tableName)
        ))
        conn.commit()
    return 0


def cleanup_camunda_tables(
    dbConfig: Dict[str, Any],
    tablePrefixes: List[str] = None,
    dryRun: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Очищает данные из указанных таблиц Camunda.
    
    Args:
        dbConfig: Конфигурация подключения к БД
        tablePrefixes: Список префиксов таблиц для очистки 
                      (например, ['ACT_HI_', 'ACT_RU_'])
                      Если None, очищает только исторические данные (ACT_HI_*)
        dryRun: Если True, только показывает что будет удалено, не удаляет
        verbose: Если True, выводит подробную информацию
        
    Returns:
        Словарь с результатами операции
    """
    if tablePrefixes is None:
        tablePrefixes = ['ACT_HI_']
    results = {
        'tables_found': [],
        'tables_cleaned': [],
        'total_rows_before': 0,
        'total_rows_after': 0,
        'errors': []
    }
    
    try:
        # Подключаемся к базе данных
        if verbose:
            print(f"Подключение к базе данных {dbConfig['database']} на {dbConfig['host']}:{dbConfig['port']}...")
        
        # Отладочный вывод параметров подключения (без пароля)
        if verbose:
            debugConfig = {k: ('*' * len(v) if k == 'password' else v) for k, v in dbConfig.items()}
            print(f"\n   Параметры подключения к БД: {debugConfig}")
        
        conn = psycopg2.connect(**dbConfig)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        try:
            # Получаем список таблиц для очистки
            allTables = []
            tableInfo = {}
            
            for prefix in tablePrefixes:
                tables = get_camunda_tables(conn, prefix)
                allTables.extend(tables)
                tableInfo[prefix] = tables
            
            if not allTables:
                print(f"⚠️  Таблицы с префиксами {', '.join(tablePrefixes)} не найдены в схеме 'public'.")
                
                # Диагностика: ищем таблицы во всех схемах
                print("\n🔍 Диагностика: поиск таблиц Camunda во всех схемах...")
                allSchemasTables = find_camunda_tables_in_all_schemas(conn)
                
                if allSchemasTables:
                    print("   Найдены таблицы Camunda в следующих схемах:")
                    for schema, tables in allSchemasTables.items():
                        print(f"   - Схема '{schema}': {len(tables)} таблиц")
                        if len(tables) <= 10:
                            for table in tables:
                                print(f"     * {table}")
                        else:
                            print(f"     (первые 10): {', '.join(tables[:10])}...")
                else:
                    # Проверяем, есть ли вообще таблицы в базе
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(*) 
                            FROM information_schema.tables 
                            WHERE table_schema = 'public'
                        """)
                        totalTables = cur.fetchone()[0]
                        print(f"   Всего таблиц в схеме 'public': {totalTables}")
                        
                        if totalTables > 0:
                            cur.execute("""
                                SELECT table_name 
                                FROM information_schema.tables 
                                WHERE table_schema = 'public'
                                ORDER BY table_name
                                LIMIT 20
                            """)
                            sampleTables = [row[0] for row in cur.fetchall()]
                            print(f"   Примеры таблиц: {', '.join(sampleTables)}")
                        else:
                            print("   ⚠️  База данных пуста или Camunda еще не была развернута")
                            print("   💡 Убедитесь, что:")
                            print("      - Camunda сервер был запущен хотя бы один раз")
                            print("      - Вы подключены к правильной базе данных")
                            print("      - База данных не пустая")
                
                return results
            
            results['tables_found'] = allTables
            
            if verbose:
                print(f"\nНайдено таблиц для очистки: {len(allTables)}")
                for prefix, tables in tableInfo.items():
                    if tables:
                        print(f"  {prefix}*: {len(tables)} таблиц")
                print("=" * 60)
            
            # Собираем статистику до очистки
            for tableName in allTables:
                try:
                    rowCount = get_table_row_count(conn, tableName)
                    results['total_rows_before'] += rowCount
                    
                    if verbose:
                        print(f"  {tableName}: {rowCount:,} строк")
                except Exception as e:
                    errorMsg = f"Ошибка при подсчете строк в {tableName}: {e}"
                    results['errors'].append(errorMsg)
                    if verbose:
                        print(f"  ⚠️  {errorMsg}")
            
            if dryRun:
                print("\n" + "=" * 60)
                print("🔍 РЕЖИМ ПРОВЕРКИ (dry-run) - данные НЕ будут удалены")
                print("=" * 60)
                print(f"Всего строк для удаления: {results['total_rows_before']:,}")
                print(f"Таблиц для очистки: {len(allTables)}")
                return results
            
            # Подтверждение
            print("\n" + "=" * 60)
            prefixesStr = ', '.join(tablePrefixes)
            print(f"⚠️  ВНИМАНИЕ: Вы собираетесь удалить данные из таблиц: {prefixesStr}")
            print("=" * 60)
            print(f"Таблиц для очистки: {len(allTables)}")
            print(f"Всего строк для удаления: {results['total_rows_before']:,}")
            print("\nОперация НЕОБРАТИМА!")
            
            confirm = input("\nПродолжить? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y', 'да', 'д']:
                print("❌ Операция отменена.")
                return results
            
            # Очищаем таблицы
            print("\nНачинаем очистку...")
            print("=" * 60)
            
            for tableName in allTables:
                try:
                    if verbose:
                        print(f"Очистка {tableName}...", end=' ')
                    
                    truncate_table(conn, tableName)
                    results['tables_cleaned'].append(tableName)
                    
                    if verbose:
                        print("✓")
                    else:
                        print(f"✓ {tableName}")
                        
                except Exception as e:
                    errorMsg = f"Ошибка при очистке {tableName}: {e}"
                    results['errors'].append(errorMsg)
                    print(f"❌ {errorMsg}")
            
            # Проверяем результат
            print("\n" + "=" * 60)
            print("Проверка результатов...")
            print("=" * 60)
            
            for tableName in allTables:
                try:
                    rowCount = get_table_row_count(conn, tableName)
                    results['total_rows_after'] += rowCount
                    
                    if verbose and rowCount > 0:
                        print(f"  ⚠️  {tableName}: осталось {rowCount} строк")
                except Exception as e:
                    if verbose:
                        print(f"  ⚠️  Ошибка при проверке {tableName}: {e}")
            
            # Итоги
            print("\n" + "=" * 60)
            print("✅ ОЧИСТКА ЗАВЕРШЕНА")
            print("=" * 60)
            print(f"Таблиц обработано: {len(results['tables_cleaned'])}")
            print(f"Строк удалено: {results['total_rows_before']:,}")
            print(f"Строк осталось: {results['total_rows_after']:,}")
            
            if results['errors']:
                print(f"\n⚠️  Ошибок: {len(results['errors'])}")
                for error in results['errors']:
                    print(f"  - {error}")
            
        finally:
            conn.close()
            
    except psycopg2.Error as e:
        errorMsg = f"Ошибка подключения к базе данных: {e}"
        results['errors'].append(errorMsg)
        print(f"❌ {errorMsg}")
        raise
    except Exception as e:
        errorMsg = f"Неожиданная ошибка: {e}"
        results['errors'].append(errorMsg)
        print(f"❌ {errorMsg}")
        raise
    
    return results


def main():
    """Главная функция скрипта"""
    parser = argparse.ArgumentParser(
        description='Очистка данных из базы данных Camunda',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Очистка только исторических данных (по умолчанию):
  python scripts/cleanup_camunda_history.py --dry-run

  # Очистка истории и активных процессов:
  python scripts/cleanup_camunda_history.py --history --runtime

  # Полная очистка всех данных (кроме identity):
  python scripts/cleanup_camunda_history.py --all

  # Очистка только определений процессов:
  python scripts/cleanup_camunda_history.py --repository

Типы данных:
  --history, -hi    Исторические данные (ACT_HI_*) - завершенные процессы
  --runtime, -ru    Runtime данные (ACT_RU_*) - активные процессы и задачи
  --repository, -re Repository данные (ACT_RE_*) - определения процессов
  --identity, -id   Identity данные (ACT_ID_*) - пользователи и группы
  --general, -ge    General данные (ACT_GE_*) - общие данные и байт-массивы
  --all             Все данные кроме identity (history + runtime + repository + general)

Переменные окружения:
  POSTGRES_HOST          - хост PostgreSQL (по умолчанию: localhost)
  POSTGRES_PORT          - порт PostgreSQL (по умолчанию: 5432)
  CAMUNDA_DATABASE_NAME  - имя базы данных (по умолчанию: camunda)
  CAMUNDA_DATABASE_USER  - пользователь БД (по умолчанию: camunda)
  CAMUNDA_DATABASE_PASSWORD - пароль БД (обязательно)
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Режим проверки: показывает что будет удалено, но не удаляет данные'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Подробный вывод информации'
    )
    
    # Опции выбора типов данных
    parser.add_argument(
        '--history', '-hi',
        action='store_true',
        help='Очистить исторические данные (ACT_HI_*)'
    )
    
    parser.add_argument(
        '--runtime', '-ru',
        action='store_true',
        help='Очистить runtime данные (ACT_RU_*) - активные процессы'
    )
    
    parser.add_argument(
        '--repository', '-re',
        action='store_true',
        help='Очистить repository данные (ACT_RE_*) - определения процессов'
    )
    
    parser.add_argument(
        '--identity', '-id',
        action='store_true',
        help='Очистить identity данные (ACT_ID_*) - пользователи и группы'
    )
    
    parser.add_argument(
        '--general', '-ge',
        action='store_true',
        help='Очистить general данные (ACT_GE_*) - общие данные'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Очистить все данные кроме identity (history + runtime + repository + general)'
    )
    
    args = parser.parse_args()
    
    # Определяем какие типы данных очищать
    tablePrefixes = []
    
    if args.all:
        # Очищаем все кроме identity
        tablePrefixes = ['ACT_HI_', 'ACT_RU_', 'ACT_RE_', 'ACT_GE_']
    else:
        # Если ничего не указано, по умолчанию только история
        if not any([args.history, args.runtime, args.repository, args.identity, args.general]):
            tablePrefixes = ['ACT_HI_']
        else:
            if args.history:
                tablePrefixes.append('ACT_HI_')
            if args.runtime:
                tablePrefixes.append('ACT_RU_')
            if args.repository:
                tablePrefixes.append('ACT_RE_')
            if args.identity:
                tablePrefixes.append('ACT_ID_')
            if args.general:
                tablePrefixes.append('ACT_GE_')
    
    print("=" * 60)
    print("Очистка данных Camunda")
    print("=" * 60)
    print(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Типы данных для очистки: {', '.join(tablePrefixes) if tablePrefixes else 'не указано'}")
    
    if args.dry_run:
        print("\n🔍 РЕЖИМ ПРОВЕРКИ - данные не будут удалены")
    
    if 'ACT_RU_' in tablePrefixes:
        print("\n⚠️  ВНИМАНИЕ: Будет удалена информация об АКТИВНЫХ процессах и задачах!")
    
    if 'ACT_RE_' in tablePrefixes:
        print("\n⚠️  ВНИМАНИЕ: Будет удалена информация об ОПРЕДЕЛЕНИЯХ процессов!")
        print("   После этого нужно будет заново развернуть процессы.")
    
    if 'ACT_ID_' in tablePrefixes:
        print("\n⚠️  ВНИМАНИЕ: Будет удалена информация о ПОЛЬЗОВАТЕЛЯХ и ГРУППАХ!")
    
    try:
        # Получаем конфигурацию БД
        if args.verbose:
            print(f"\nПараметры подключения:")
        dbConfig = get_db_config(verbose=args.verbose)
        
        # Выполняем очистку
        results = cleanup_camunda_tables(
            dbConfig,
            tablePrefixes=tablePrefixes,
            dryRun=args.dry_run,
            verbose=args.verbose
        )
        
        # Код выхода
        if results['errors']:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n❌ Операция прервана пользователем.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

