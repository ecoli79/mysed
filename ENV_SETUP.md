# Настройка переменных окружения

Для работы приложения необходимо создать файл `.env` в корневой директории проекта со следующими переменными:

## Создание файла .env

Создайте файл `.env` в корневой директории проекта:

```bash
touch .env
```

## Содержимое файла .env

```env
# Настройки приложения
APP_NAME="NiceGUI Example"
DEBUG=false
ENVIRONMENT=development

# Настройки Camunda
CAMUNDA_URL=https://172.19.228.72:8443
CAMUNDA_USERNAME=dvimpolitov
CAMUNDA_PASSWORD=your_camunda_password_here

# Настройки LDAP
LDAP_SERVER=172.19.228.72
LDAP_USER=cn=admin,dc=permgp7,dc=ru
LDAP_PASSWORD=your_ldap_password_here

# Настройки Mayan
MAYAN_URL=http://172.19.228.72:8000
MAYAN_USERNAME=admin
MAYAN_PASSWORD=your_mayan_password_here
MAYAN_API_TOKEN=your_mayan_api_token_here
```

## Важные замечания

1. **Замените пароли** на реальные значения
2. **Не коммитьте** файл `.env` в git - он уже добавлен в `.gitignore`
3. **Скопируйте** этот файл как `.env` и заполните реальными значениями
4. **Убедитесь**, что файл `.env` находится в корневой директории проекта

## Проверка настроек

После создания файла `.env` приложение автоматически загрузит настройки из него.
