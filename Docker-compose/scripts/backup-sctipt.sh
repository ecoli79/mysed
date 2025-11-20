#!/bin/sh
set -e

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Создание резервных копий всех баз данных
for DB in mayan camunda; do
    echo "Backing up database: $DB"
    pg_dump -h "$PGHOST" -U "$PGUSER" -F c -b -v -f "$BACKUP_DIR/${DB}_${TIMESTAMP}.dump" "$DB"
    
    # Сжатие дампа
    gzip "$BACKUP_DIR/${DB}_${TIMESTAMP}.dump"
    
    echo "Backup completed: ${DB}_${TIMESTAMP}.dump.gz"
done

# Удаление резервных копий старше 30 дней
find "$BACKUP_DIR" -name "*.dump.gz" -mtime +30 -delete

echo "Backup process completed"

