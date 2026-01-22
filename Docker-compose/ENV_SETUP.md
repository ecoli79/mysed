# Настройка переменных окружения

Для работы приложения необходимо создать файл `.env` в директории `Docker-compose` со следующими переменными:

## Создание файла .env

Создайте файл `.env` в директории `Docker-compose`:

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
CAMUNDA_URL=https://camunda_url:8443
CAMUNDA_USERNAME=your_camunda_login
CAMUNDA_PASSWORD=your_camunda_password
CAMUNDA_VERIFY_SSL=false  # Проверка SSL сертификатов (true для production, false для разработки с self-signed сертификатами)

# Настройки LDAP
LDAP_SERVER=openldap
LDAP_USER=cn=your_ldap_admin_login_here
LDAP_PASSWORD=your_ldap_password_here
LDAP_BASE_DN=dc=permgp7,dc=ru

# Настройки Mayan
MAYAN_URL=http://mayan_url:8000
MAYAN_USERNAME=admin
MAYAN_PASSWORD=your_mayan_password_here
MAYAN_API_TOKEN=your_mayan_api_token_here
```

## Важные замечания

1. **Замените пароли** на реальные значения
2. **Не коммитьте** файл `.env` в git - он уже добавлен в `.gitignore`
3. **Скопируйте** этот файл как `.env` и заполните реальными значениями
4. **Убедитесь**, что файл `.env` находится в директории `Docker-compose`
5. **LDAP_SERVER** должен указывать на контейнер openldap: `ldap://openldap:389` (для Docker Compose) или внешний адрес LDAP сервера
6. **LDAP_BASE_DN** должен соответствовать вашему LDAP домену, например: `dc=permgp7,dc=ru`

## Проверка настроек

После создания файла `.env` приложение автоматически загрузит настройки из него.
