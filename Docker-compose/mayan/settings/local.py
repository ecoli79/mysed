from mayan.settings.production import *

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "access_key": "admin",
            "secret_key": "gkb6codcod",
            "bucket_name": "mayan",
            "endpoint_url": "http://172.19.228.50:9001",
            "region_name": "ru",
            "use_ssl": False,
            "addressing_style": "path",
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
