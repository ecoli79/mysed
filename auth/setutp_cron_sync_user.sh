#!/bin/bash
# Скрипт для настройки автоматической синхронизации пользователей

# Путь к проекту
PROJECT_PATH="/home/medic/djangoproject/nicegui_example"

# Путь к скрипту синхронизации
SYNC_SCRIPT="$PROJECT_PATH/user_sync.py"

# Путь к логам
LOG_PATH="$PROJECT_PATH/logs"

# Создаем директорию для логов если её нет
mkdir -p "$LOG_PATH"

# Функция для добавления cron задачи
add_cron_job() {
    local schedule="$1"
    local description="$2"
    
    # Создаем временный файл с cron задачей
    temp_cron=$(mktemp)
    
    # Получаем существующие cron задачи
    crontab -l 2>/dev/null > "$temp_cron"
    
    # Добавляем новую задачу
    echo "# $description" >> "$temp_cron"
    echo "$schedule cd $PROJECT_PATH && python3 $SYNC_SCRIPT >> $LOG_PATH/cron_sync.log 2>&1" >> "$temp_cron"
    
    # Устанавливаем новые cron задачи
    crontab "$temp_cron"
    
    # Удаляем временный файл
    rm "$temp_cron"
    
    echo "Cron задача добавлена: $description"
    echo "   Расписание: $schedule"
}

# Функция для удаления cron задач синхронизации
remove_cron_jobs() {
    # Получаем существующие cron задачи
    temp_cron=$(mktemp)
    crontab -l 2>/dev/null > "$temp_cron"
    
    # Удаляем строки содержащие user_sync.py
    sed -i '/user_sync.py/d' "$temp_cron"
    
    # Устанавливаем обновленные cron задачи
    crontab "$temp_cron"
    
    # Удаляем временный файл
    rm "$temp_cron"
    
    echo "Cron задачи синхронизации удалены"
}

# Функция для показа текущих cron задач
show_cron_jobs() {
    echo "Текущие cron задачи:"
    crontab -l 2>/dev/null | grep -E "(user_sync|Синхронизация)" || echo "   Нет задач синхронизации"
}

# Функция для тестирования скрипта
test_sync_script() {
    echo "Тестируем скрипт синхронизации..."
    
    if [ ! -f "$SYNC_SCRIPT" ]; then
        echo "Скрипт синхронизации не найден: $SYNC_SCRIPT"
        return 1
    fi
    
    # Переходим в директорию проекта
    cd "$PROJECT_PATH"
    
    # Тестируем скрипт
    python3 "$SYNC_SCRIPT" --help
    if [ $? -eq 0 ]; then
        echo "Скрипт синхронизации работает корректно"
        return 0
    else
        echo "Ошибка в скрипте синхронизации"
        return 1
    fi
}

# Основное меню
case "$1" in
    "add")
        case "$2" in
            "hourly")
                add_cron_job "0 * * * *" "Синхронизация пользователей каждый час"
                ;;
            "daily")
                add_cron_job "0 9 * * *" "Синхронизация пользователей каждый день в 9:00"
                ;;
            "weekly")
                add_cron_job "0 9 * * 1" "Синхронизация пользователей каждую неделю в понедельник в 9:00"
                ;;
            "custom")
                if [ -z "$3" ]; then
                    echo "Укажите расписание для custom режима"
                    echo "Пример: $0 add custom '0 */6 * * *'"
                    exit 1
                fi
                add_cron_job "$3" "Синхронизация пользователей (пользовательское расписание)"
                ;;
            *)
                echo "Неизвестный режим: $2"
                echo "Доступные режимы: hourly, daily, weekly, custom"
                exit 1
                ;;
        esac
        ;;
    "remove")
        remove_cron_jobs
        ;;
    "show")
        show_cron_jobs
        ;;
    "test")
        test_sync_script
        ;;
    "run")
        echo "Запускаем синхронизацию пользователей..."
        cd "$PROJECT_PATH"
        python3 "$SYNC_SCRIPT"
        ;;
    "run-force")
        echo "Запускаем принудительную синхронизацию пользователей..."
        cd "$PROJECT_PATH"
        python3 "$SYNC_SCRIPT" --force
        ;;
    *)
        echo "Использование: $0 {add|remove|show|test|run|run-force}"
        echo ""
        echo "Команды:"
        echo "  add hourly     - Добавить синхронизацию каждый час"
        echo "  add daily      - Добавить синхронизацию каждый день в 9:00"
        echo "  add weekly     - Добавить синхронизацию каждую неделю в понедельник в 9:00"
        echo "  add custom     - Добавить синхронизацию с пользовательским расписанием"
        echo "  remove         - Удалить все задачи синхронизации"
        echo "  show           - Показать текущие задачи синхронизации"
        echo "  test           - Протестировать скрипт синхронизации"
        echo "  run            - Запустить синхронизацию один раз"
        echo "  run-force      - Запустить принудительную синхронизацию"
        echo ""
        echo "Примеры:"
        echo "  $0 add daily"
        echo "  $0 add custom '0 */6 * * *'  # Каждые 6 часов"
        echo "  $0 test"
        echo "  $0 run"
        exit 1
        ;;
esac