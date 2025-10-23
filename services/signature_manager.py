import logging
import base64
import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from services.mayan_connector import MayanClient
from services.camunda_connector import CamundaClient
from models import DocumentSignature, SignatureProcess

logger = logging.getLogger(__name__)

class SignatureManager:
    """Менеджер для работы с электронными подписями документов"""
    
    def __init__(self):
        self.mayan_client = None
        self.camunda_client = None
    
    def _get_mayan_client(self) -> MayanClient:
        if not self.mayan_client:
            self.mayan_client = MayanClient.create_with_session_user()
        return self.mayan_client
    
    def _get_camunda_client(self) -> CamundaClient:
        if not self.camunda_client:
            from services.camunda_connector import create_camunda_client
            self.camunda_client = create_camunda_client()
        return self.camunda_client
    
    def initiate_document_signing(self, document_id: str, signer_list: List[str], 
                                initiator: str, deadline: Optional[datetime] = None) -> Optional[str]:
        """Инициирует процесс подписания документа"""
        try:
            # Получаем информацию о документе
            mayan_client = self._get_mayan_client()
            document_info = mayan_client.get_document_info_for_review(document_id)
            
            if not document_info:
                logger.error(f"Документ {document_id} не найден")
                return None
            
            # Запускаем процесс в Camunda
            camunda_client = self._get_camunda_client()
            process_id = camunda_client.start_document_signing_process(
                document_id=document_id,
                document_name=document_info["label"],
                signer_list=signer_list,
                business_key=f"signing_{document_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            
            if process_id:
                logger.info(f"Процесс подписания документа {document_id} запущен: {process_id}")
                return process_id
            else:
                logger.error("Не удалось запустить процесс подписания")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при инициации подписания документа {document_id}: {e}")
            return None
    
    def get_signing_tasks_for_user(self, username: str) -> List[Dict[str, Any]]:
        """Получает задачи подписания для пользователя"""
        try:
            camunda_client = self._get_camunda_client()
            # Исправляем вызов метода - убираем несуществующий параметр
            tasks = camunda_client.get_user_tasks(username, active_only=True)
            
            signing_tasks = []
            for task in tasks:
                # Фильтруем только задачи подписания по имени задачи
                if task.name == "Подписать документ":
                    # Получаем переменные процесса для получения информации о документе
                    process_variables = camunda_client.get_process_variables(task.process_instance_id)
                    
                    signing_tasks.append({
                        'task_id': task.id,
                        'process_instance_id': task.process_instance_id,
                        'document_id': process_variables.get('documentId'),
                        'document_name': process_variables.get('documentName'),
                        'created': task.created,
                        'assignee': task.assignee
                    })
            
            return signing_tasks
            
        except Exception as e:
            logger.error(f"Ошибка при получении задач подписания для пользователя {username}: {e}")
            return []
    
    def complete_signing_task(self, task_id: str, signature_data: str, 
                            certificate_info: Dict[str, Any], comment: str = "") -> bool:
        """Завершает задачу подписания"""
        try:
            camunda_client = self._get_camunda_client()
            
            # Проверяем подпись (базовая проверка)
            if not self._validate_signature_data(signature_data, certificate_info):
                logger.error("Недействительная подпись")
                return False
            
            # Завершаем задачу в Camunda
            success = camunda_client.complete_signing_task(
                task_id=task_id,
                signature_data=signature_data,
                certificate_info=certificate_info,
                comment=comment
            )
            
            if success:
                # Сохраняем информацию о подписи в Mayan EDMS
                self._save_signature_to_mayan(task_id, signature_data, certificate_info)
                logger.info(f"Задача подписания {task_id} успешно завершена")
                return True
            else:
                logger.error(f"Ошибка при завершении задачи подписания {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при завершении задачи подписания {task_id}: {e}")
            return False
    
    def _validate_signature_data(self, signature_data: str, certificate_info: Dict[str, Any]) -> bool:
        """Базовая валидация данных подписи"""
        try:
            # Проверяем, что подпись не пустая
            if not signature_data or len(signature_data) < 100:
                return False
            
            # Проверяем информацию о сертификате
            required_fields = ['subject', 'issuer', 'serialNumber', 'validFrom', 'validTo']
            for field in required_fields:
                if field not in certificate_info:
                    logger.warning(f"Отсутствует поле {field} в информации о сертификате")
                    return False
            
            # Проверяем срок действия сертификата
            valid_to = datetime.fromisoformat(certificate_info['validTo'].replace('Z', '+00:00'))
            if valid_to < datetime.now():
                logger.error("Сертификат истек")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при валидации подписи: {e}")
            return False
    
    def _save_signature_to_mayan(self, task_id: str, signature_data: str, 
                                certificate_info: Dict[str, Any]) -> bool:
        """Сохраняет информацию о подписи в Mayan EDMS"""
        try:
            mayan_client = self._get_mayan_client()
            
            # Создаем метаданные для подписи
            signature_metadata = {
                'signature_type': 'electronic_signature',
                'signature_provider': 'cryptopro',
                'certificate_subject': certificate_info.get('subject', ''),
                'certificate_issuer': certificate_info.get('issuer', ''),
                'certificate_serial': certificate_info.get('serialNumber', ''),
                'signature_date': datetime.now().isoformat(),
                'task_id': task_id
            }
            
            # Сохраняем как отдельный документ в Mayan EDMS
            signature_filename = f"signature_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            signature_content = json.dumps(signature_metadata, ensure_ascii=False, indent=2)
            
            result = mayan_client.upload_document_result(
                task_id=task_id,
                process_instance_id="",  # Будет заполнено автоматически
                filename=signature_filename,
                file_content=signature_content.encode('utf-8'),
                mimetype='application/json',
                description=f"Электронная подпись для задачи {task_id}"
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении подписи в Mayan EDMS: {e}")
            return False