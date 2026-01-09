#!/bin/bash
# Обертка для запуска скрипта очистки исторических данных Camunda через Docker

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Получаем директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_COMPOSE_DIR="$PROJECT_ROOT/Docker-compose"

# Проверяем наличие docker-compose.yml
if [ ! -f "$DOCKER_COMPOSE_DIR/docker-compose.yml" ]; then
    echo -e "${RED}Ошибка: docker-compose.yml не найден в $DOCKER_COMPOSE_DIR${NC}" >&2
    exit 1
fi

# Функция для вывода справки
show_help() {
    cat << EOF
Использование: $0 [OPTIONS]

Очистка исторических данных из базы данных Camunda через Docker Compose.

Опции:
  --dry-run          Режим проверки (не удаляет данные)
  --verbose, -v      Подробный вывод информации
  --help, -h         Показать эту справку

Примеры:
  # Проверка (без удаления)
  $0 --dry-run

  # Очистка с подробным выводом
  $0 --verbose

  # Очистка (требует подтверждения)
  $0

Переменные окружения берутся из .env файла в Docker-compose/
EOF
}

# Парсинг аргументов
DRY_RUN=""
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Неизвестная опция: $1${NC}" >&2
            show_help
            exit 1
            ;;
    esac
done

# Проверяем, что контейнер app запущен
if ! docker compose -f "$DOCKER_COMPOSE_DIR/docker-compose.yml" ps app | grep -q "Up"; then
    echo -e "${YELLOW}Предупреждение: Контейнер 'app' не запущен.${NC}"
    echo "Попытка запуска через docker compose exec может не сработать."
    echo ""
    read -p "Продолжить? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Формируем команду
CMD="python scripts/cleanup_camunda_history.py"

if [ -n "$DRY_RUN" ]; then
    CMD="$CMD $DRY_RUN"
fi

if [ -n "$VERBOSE" ]; then
    CMD="$CMD $VERBOSE"
fi

echo -e "${GREEN}Запуск очистки исторических данных Camunda...${NC}"
echo ""

# Запускаем команду в контейнере app
cd "$DOCKER_COMPOSE_DIR"
docker compose exec -T app $CMD

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Команда выполнена успешно${NC}"
else
    echo ""
    echo -e "${RED}❌ Команда завершилась с ошибкой (код: $exit_code)${NC}"
fi

exit $exit_code

