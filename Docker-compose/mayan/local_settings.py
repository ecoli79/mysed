# S3/MinIO Storage Configuration
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# MinIO S3 Settings
AWS_ACCESS_KEY_ID = 'admin'
AWS_SECRET_ACCESS_KEY = 'gkb6codcod'
AWS_STORAGE_BUCKET_NAME = 'mayan'
AWS_S3_ENDPOINT_URL = 'http://172.19.228.50:9001'
AWS_S3_REGION_NAME = 'us-east-1'
AWS_S3_USE_SSL = False
AWS_S3_ADDRESSING_STYLE = 'path'

# Document Storage
DOCUMENTS_STORAGE_BACKEND = 'storages.backends.s3boto3.S3Boto3Storage'
DOCUMENTS_STORAGE_BACKEND_ARGUMENTS = {
    'bucket_name': 'mayan',
    'access_key': 'admin',
    'secret_key': 'gkb6codcod',
    'endpoint_url': 'http://172.19.228.50:9001',
    'region_name': 'us-east-1',
    'use_ssl': False,
}

# Cache Storage
DOCUMENTS_CACHE_STORAGE_BACKEND = 'storages.backends.s3boto3.S3Boto3Storage'
DOCUMENTS_CACHE_STORAGE_BACKEND_ARGUMENTS = {
    'bucket_name': 'mayan-cache',
    'access_key': 'admin',
    'secret_key': 'gkb6codcod',
    'endpoint_url': 'http://172.19.228.50:9001',
    'region_name': 'us-east-1',
    'use_ssl': False,
}

# Image Storage
DOCUMENTS_IMAGE_STORAGE_BACKEND = 'storages.backends.s3boto3.S3Boto3Storage'
DOCUMENTS_IMAGE_STORAGE_BACKEND_ARGUMENTS = {
    'bucket_name': 'mayan',
    'access_key': 'admin',
    'secret_key': 'gkb6codcod',
    'endpoint_url': 'http://172.19.228.50:9001',
    'region_name': 'us-east-1',
    'use_ssl': False,
}
