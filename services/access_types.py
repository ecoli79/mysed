from enum import Enum
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AccessType(Enum):
    """Типы доступа к документам"""
    VIEW_DOCUMENT = "view_document"
    VIEW_AND_DOWNLOAD = "view_and_download",
    SUBSCRIBE_DOCUMENT = 'subscribe_document'

class AccessTypeManager:
    """Менеджер типов доступа к документам"""
    
    # Маппинг типов доступа на необходимые permissions
    ACCESS_TYPE_PERMISSIONS = {
        AccessType.VIEW_DOCUMENT: [
            'View documents',
            'View document versions',
            'View document files'
        ],
        AccessType.VIEW_AND_DOWNLOAD: [
            'View documents', 
            'View document files',
            'View document versions',
            'Download document files'
        ],
        AccessType.SUBSCRIBE_DOCUMENT: [
            'Create new document files',
            'Delete document files',
            'Edit document files',
            'Edit document versions',
            'Print document files',
            'Print document versions',
            'View document files',
            'View document versions',
            'View documents',
            'Download document files'
        ]
    }
    
    # Человекочитаемые названия типов доступа
    ACCESS_TYPE_LABELS = {
        AccessType.VIEW_DOCUMENT: 'Просмотр документа',
        AccessType.VIEW_AND_DOWNLOAD: 'Просмотр и скачивание',
        AccessType.SUBSCRIBE_DOCUMENT: 'Подписание документа'
    }
    
    @classmethod
    def get_access_type_permissions(cls, access_type: AccessType) -> List[str]:
        """
        Получает список permissions для типа доступа
        
        Args:
            access_type: Тип доступа
            
        Returns:
            Список названий permissions
        """
        return cls.ACCESS_TYPE_PERMISSIONS.get(access_type, [])
    
    @classmethod
    def get_access_type_label(cls, access_type: AccessType) -> str:
        """
        Получает человекочитаемое название типа доступа
        
        Args:
            access_type: Тип доступа
            
        Returns:
            Название типа доступа
        """
        return cls.ACCESS_TYPE_LABELS.get(access_type, str(access_type.value))
    
    @classmethod
    def get_all_access_types(cls) -> List[Dict[str, Any]]:
        """
        Получает все доступные типы доступа
        
        Returns:
            Список словарей с информацией о типах доступа
        """
        access_types = []
        for access_type in AccessType:
            access_types.append({
                'value': access_type.value,
                'label': cls.get_access_type_label(access_type),
                'permissions': cls.get_access_type_permissions(access_type)
            })
        return access_types
    
    @classmethod
    def get_access_type_by_value(cls, value: str) -> AccessType:
        """
        Получает тип доступа по значению
        
        Args:
            value: Значение типа доступа
            
        Returns:
            Тип доступа или None
        """
        for access_type in AccessType:
            if access_type.value == value:
                return access_type
        return None