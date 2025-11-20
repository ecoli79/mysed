#!/bin/bash
# Скрипт для запуска резервного копирования всех сервисов

BACKUP_BASE_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Starting backup process at $(date)"

# Резервное копирование PostgreSQL
echo "Backing up PostgreSQL..."
docker-compose run --rm postgresql-backup

# Резервное копирование OpenLDAP
echo "Backing up OpenLDAP..."
docker exec openldap slapcat -n 0 > "${BACKUP_BASE_DIR}/openldap/ldap_config_${TIMESTAMP}.ldif"
docker exec openldap slapcat -n 1 > "${BACKUP_BASE_DIR}/openldap/ldap_data_${TIMESTAMP}.ldif"

# Резервное копирование данных Mayan
echo "Backing up Mayan data..."
tar -czf "${BACKUP_BASE_DIR}/mayan/mayan_app_${TIMESTAMP}.tar.gz" -C ./data/mayan/app .

# Резервное копирование данных Camunda
echo "Backing up Camunda data..."
if [ -d "./data/camunda" ]; then
    tar -czf "${BACKUP_BASE_DIR}/camunda/camunda_data_${TIMESTAMP}.tar.gz" -C ./data/camunda .
fi

# Резервное копирование RabbitMQ
echo "Backing up RabbitMQ..."
if [ -d "./data/rabbitmq" ]; then
    tar -czf "${BACKUP_BASE_DIR}/rabbitmq/rabbitmq_${TIMESTAMP}.tar.gz" -C ./data/rabbitmq .
fi

# Резервное копирование Redis
echo "Backing up Redis..."
if [ -d "./data/redis" ]; then
    tar -czf "${BACKUP_BASE_DIR}/redis/redis_${TIMESTAMP}.tar.gz" -C ./data/redis .
fi

echo "Backup process completed at $(date)"

