#!/bin/bash
# Скрипт для установки переменных окружения для тестов

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Установка переменных окружения для тестов"
echo "=========================================="
echo ""

# Функция для запроса значения
ask_value() {
    local var_name=$1
    local current_value=$2
    local prompt=$3
    local is_password=$4
    
    if [ -n "$current_value" ]; then
        echo -e "${YELLOW}Текущее значение ${var_name}: ${current_value}${NC}"
        read -p "Изменить? (y/n): " change
        if [ "$change" != "y" ] && [ "$change" != "Y" ]; then
            echo "$current_value"
            return
        fi
    fi
    
    if [ "$is_password" = "true" ]; then
        read -sp "$prompt: " value
        echo ""
    else
        read -p "$prompt: " value
    fi
    
    echo "$value"
}

# Получаем текущие значения
CURRENT_USERNAME=${TEST_USERNAME:-""}
CURRENT_PASSWORD=${TEST_PASSWORD:-""}
CURRENT_APP_URL=${TEST_APP_URL:-"http://localhost:8080"}

# Запрашиваем новые значения
echo "Введите учетные данные для тестов:"
echo ""

NEW_USERNAME=$(ask_value "TEST_USERNAME" "$CURRENT_USERNAME" "Имя пользователя (TEST_USERNAME)" false)
NEW_PASSWORD=$(ask_value "TEST_PASSWORD" "$CURRENT_PASSWORD" "Пароль (TEST_PASSWORD)" true)
NEW_APP_URL=$(ask_value "TEST_APP_URL" "$CURRENT_APP_URL" "URL приложения (TEST_APP_URL)" false)

# Устанавливаем переменные окружения
export TEST_USERNAME="$NEW_USERNAME"
export TEST_PASSWORD="$NEW_PASSWORD"
export TEST_APP_URL="$NEW_APP_URL"

echo ""
echo -e "${GREEN}✓ Переменные окружения установлены:${NC}"
echo "  TEST_USERNAME=$TEST_USERNAME"
echo "  TEST_PASSWORD=${TEST_PASSWORD:+*****}"
echo "  TEST_APP_URL=$TEST_APP_URL"
echo ""

# Предлагаем сохранить в файл
read -p "Сохранить в файл .env.test? (y/n): " save
if [ "$save" = "y" ] || [ "$save" = "Y" ]; then
    cat > .env.test << EOF
# Переменные окружения для тестов
# Сгенерировано автоматически $(date)

TEST_USERNAME=$TEST_USERNAME
TEST_PASSWORD=$TEST_PASSWORD
TEST_APP_URL=$TEST_APP_URL
EOF
    echo -e "${GREEN}✓ Сохранено в .env.test${NC}"
    echo ""
    echo "Для использования в тестах загрузите файл:"
    echo "  source .env.test"
    echo "  # или"
    echo "  export \$(cat .env.test | xargs)"
fi

echo ""
echo "Для запуска тестов используйте:"
echo "  uv run pytest tests/e2e/ -v"
echo ""
echo "Или с параметрами командной строки:"
echo "  uv run pytest tests/e2e/ -v --TEST_USERNAME=$TEST_USERNAME --TEST_PASSWORD=*****"
echo ""

