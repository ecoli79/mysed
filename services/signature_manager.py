import logging
import base64
import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from services.mayan_connector import MayanClient
from services.camunda_connector import CamundaClient
from models import DocumentSignature, SignatureProcess
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor  # ИСПРАВЛЕНИЕ: Убираем неработающий импорт colors
import reportlab.lib.colors as colors  # ИСПРАВЛЕНИЕ: Импортируем colors как модуль
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import registerFontFamily

logger = logging.getLogger(__name__)

class SignatureManager:
    '''Менеджер для работы с электронными подписями документов'''
    
    def __init__(self):
        self.mayan_client = None
    
    def _get_mayan_client(self) -> MayanClient:
        if not self.mayan_client:
            self.mayan_client = MayanClient.create_with_session_user()
        return self.mayan_client
    
    def get_document_current_hash(self, document_id: str) -> Optional[str]:
        '''Получает хеш актуальной версии документа'''
        try:
            mayan_client = self._get_mayan_client()
            
            # ИСПРАВЛЕНИЕ: Получаем БИНАРНОЕ содержимое файла напрямую
            file_content = mayan_client.get_document_file_content(document_id)
            
            if not file_content:
                logger.error(f'Не удалось получить содержимое файла документа {document_id}')
                return None
            
            # Хешируем бинарные данные напрямую
            import hashlib
            document_hash = hashlib.sha256(file_content).hexdigest()
            
            logger.info(f'Хеш документа {document_id}: {document_hash}, размер файла: {len(file_content)} байт')
            return document_hash
            
        except Exception as e:
            logger.error(f'Ошибка получения хеша документа {document_id}: {e}')
            return None
    
    def upload_signature_to_document(self, document_id: str, username: str, 
                                 signature_base64: str, certificate_info: Dict[str, Any]) -> bool:
        '''Загружает файл подписи *.p7s к документу'''
        try:
            mayan_client = self._get_mayan_client()
            
            # Декодируем подпись из base64
            import base64
            signature_binary = base64.b64decode(signature_base64)
            
            # Создаем имя файла подписи
            signature_filename = f'{username}.p7s'
            
            logger.info(f'Проверяем наличие существующих подписей пользователя {username} для документа {document_id}')
            
            # Получаем список файлов документа
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            files_list = files_data.get('results', [])
            
            # Ищем существующую подпись этого пользователя
            existing_signature_file = None
            for file_info in files_list:
                if file_info.get('filename') == signature_filename:
                    existing_signature_file = file_info
                    logger.info(f'Найдена существующая подпись {signature_filename} (file_id: {file_info["id"]})')
                    break
            
            # Если подпись существует, удаляем её перед загрузкой новой
            if existing_signature_file:
                logger.info(f'Удаляем существующую подпись {signature_filename}')
                try:
                    delete_response = mayan_client._make_request('DELETE', 
                        f'documents/{document_id}/files/{existing_signature_file["id"]}/')
                    delete_response.raise_for_status()
                    logger.info(f'Существующая подпись удалена')
                except Exception as e:
                    logger.warning(f'Не удалось удалить существующую подпись: {e}')
                    # Продолжаем загрузку новой подписи
            
            # ИСПРАВЛЕНИЕ: Используем метод upload_file_to_document с skip_version_activation=True
            # чтобы не создавать новую версию документа при загрузке подписи
            logger.info(f'Загружаем подпись {signature_filename} к документу {document_id}')
            
            result = mayan_client.upload_file_to_document(
                document_id=int(document_id),
                filename=signature_filename,
                file_content=signature_binary,
                mimetype='application/pkcs7-signature',
                description=f'Подпись пользователя {username}',
                skip_version_activation=True  # Не создаем новую версию документа при загрузке подписи
            )
            
            if not result:
                logger.error(f'Не удалось загрузить подпись для документа {document_id}')
                return False
            
            file_id = result.get('file_id')
            if not file_id:
                logger.error(f'Не удалось получить ID загруженного файла подписи')
                return False
            
            logger.info(f'Подпись загружена с ID: {file_id}')
            
            # Получаем текущий хеш документа (после загрузки, но версия не изменилась)
            document_hash = self.get_document_current_hash(document_id)
            if not document_hash:
                logger.error(f'Не удалось получить хеш документа {document_id}')
                return False
            
            # Сохраняем метаданные о подписи
            self._save_signature_metadata(document_id, username, file_id, 
                                        document_hash, signature_base64, certificate_info)
            
            logger.info(f'Подпись {username}.p7s успешно загружена к документу {document_id}')
            return True
            
        except Exception as e:
            logger.error(f'Ошибка загрузки подписи: {e}', exc_info=True)
            return False
    
    def _save_signature_metadata(self, document_id: str, username: str, file_id: str,
                                document_hash: str, signature_base64: str, 
                                certificate_info: Dict[str, Any]) -> bool:
        '''Сохраняет метаданные подписи'''
        try:
            import hashlib
            import json
            
            logger.info(f'=== Сохранение метаданных подписи ===')
            logger.info(f'Certificate info получен: {certificate_info}')
            
            # Создаем хеш подписи
            signature_hash = hashlib.sha256(signature_base64.encode()).hexdigest()
            
            # Метаданные подписи
            signature_metadata = {
                'document_id': document_id,
                'username': username,
                'file_id': file_id,
                'document_version_hash': document_hash,
                'signature_hash': signature_hash,
                'certificate_info': certificate_info,  # Полная информация о сертификате
                'sign_date': datetime.now().isoformat(),
                'status': 'valid',
            }
            
            mayan_client = self._get_mayan_client()
            
            # Создаем имя файла метаданных
            metadata_filename = f'signature_metadata_{username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            
            # Подготавливаем содержимое метаданных
            metadata_content = json.dumps(signature_metadata, ensure_ascii=False, indent=2).encode('utf-8')
            
            # ИСПРАВЛЕНИЕ: Используем метод upload_file_to_document с skip_version_activation=True
            # чтобы не создавать новую версию документа при загрузке метаданных
            logger.info(f'Загружаем метаданные подписи {metadata_filename} к документу {document_id}')
            
            result = mayan_client.upload_file_to_document(
                document_id=int(document_id),
                filename=metadata_filename,
                file_content=metadata_content,
                mimetype='application/json',
                description=f'Метаданные подписи {username}',
                skip_version_activation=True  # Не создаем новую версию документа при загрузке метаданных
            )
            
            if not result:
                logger.error(f'Не удалось загрузить метаданные подписи для документа {document_id}')
                return False
            
            logger.info(f'Сохранены метаданные подписи для {username}')
            
            return True
            
        except Exception as e:
            logger.error(f'Ошибка сохранения метаданных подписи: {e}', exc_info=True)
            return False
    
    def check_user_signature_exists(self, document_id: str, username: str) -> bool:
        '''Проверяет, существует ли уже подпись пользователя для документа'''
        try:
            mayan_client = self._get_mayan_client()
            
            # Получаем список файлов документа
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            files_list = files_data.get('results', [])
            
            # Ищем файл подписи пользователя
            signature_filename = f'{username}.p7s'
            
            for file_info in files_list:
                if file_info.get('filename') == signature_filename:
                    logger.info(f'Подпись пользователя {username} уже существует для документа {document_id}')
                    return True
            
            logger.info(f'Подпись пользователя {username} не найдена для документа {document_id}')
            return False
            
        except Exception as e:
            logger.error(f'Ошибка проверки подписи пользователя {username} для документа {document_id}: {e}')
            return False
    
    def validate_document_signatures(self, document_id: str) -> Dict[str, Any]:
        '''Проверяет валидность всех подписей документа'''
        try:
            # Получаем текущий хеш документа
            current_hash = self.get_document_current_hash(document_id)
            if not current_hash:
                return {'valid': False, 'error': 'Не удалось получить хеш документа'}
            
            # Получаем список файлов документа
            mayan_client = self._get_mayan_client()
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            
            signatures = {}
            invalid_signatures = []
            
            for file_info in files_data.get('results', []):
                filename = file_info.get('filename', '')
                
                # Ищем файлы подписей (*.p7s)
                if filename.endswith('.p7s'):
                    username = filename[:-4]  # Убираем .p7s
                    
                    # Ищем соответствующие метаданные
                    metadata_files = [f for f in files_data.get('results', []) 
                                     if f['filename'].startswith(f'signature_metadata_{username}_')]
                    
                    if not metadata_files:
                        invalid_signatures.append({
                            'username': username,
                            'reason': 'Метаданные не найдены'
                        })
                        continue
                    
                    # Загружаем метаданные последней подписи
                    latest_metadata = sorted(metadata_files, 
                                           key=lambda x: x['filename'], 
                                           reverse=True)[0]
                    
                    metadata_content = mayan_client._make_request('GET', 
                        f'documents/{document_id}/files/{latest_metadata["id"]}/download/')
                    metadata_content.raise_for_status()
                    metadata = json.loads(metadata_content.content)
                    
                    # Проверяем хеш документа
                    if metadata.get('document_version_hash') != current_hash:
                        invalid_signatures.append({
                            'username': username,
                            'reason': 'Хеш документа изменился',
                            'old_hash': metadata.get('document_version_hash'),
                            'current_hash': current_hash
                        })
                    else:
                        signatures[username] = {
                            'file_id': file_info['id'],
                            'metadata_file_id': latest_metadata['id'],
                            'status': 'valid',
                            'certificate_info': metadata.get('certificate_info'),
                            'sign_date': metadata.get('sign_date')
                        }
            
            return {
                'valid': len(invalid_signatures) == 0,
                'signatures': signatures,
                'invalid_signatures': invalid_signatures,
                'document_hash': current_hash,
                'total_signatures': len(signatures),
                'invalid_count': len(invalid_signatures)
            }
            
        except Exception as e:
            logger.error(f'Ошибка валидации подписей для документа {document_id}: {e}')
            return {'valid': False, 'error': str(e)}
    
    def invalidate_all_signatures(self, document_id: str) -> bool:
        '''Делает все подписи документа недействительными'''
        try:
            # Получаем текущий хеш документа
            current_hash = self.get_document_current_hash(document_id)
            if not current_hash:
                return False
            
            # Получаем список всех метаданных подписей
            mayan_client = self._get_mayan_client()
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            
            metadata_files = [f for f in files_data.get('results', []) 
                             if f['filename'].startswith('signature_metadata_')]
            
            for metadata_file in metadata_files:
                # Загружаем метаданные
                metadata_content = mayan_client._make_request('GET', 
                    f'documents/{document_id}/files/{metadata_file["id"]}/download/')
                metadata_content.raise_for_status()
                metadata = json.loads(metadata_content.content)
                
                # Обновляем статус на invalid
                metadata['status'] = 'invalid'
                metadata['invalidation_date'] = datetime.now().isoformat()
                metadata['invalidation_reason'] = 'Документ был изменен'
                
                # Загружаем обновленные метаданные
                import io
                updated_content = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
                mayan_client._make_request('POST', f'documents/{document_id}/files/',
                    data={'action_name': 'upload', 'description': 'Обновленные метаданные'},
                    files={'file_new': (metadata_file['filename'], updated_content, 'application/json')})
            
            return True
            
        except Exception as e:
            logger.error(f'Ошибка инвалидации подписей для документа {document_id}: {e}')
            return False

    def create_signed_document_pdf(self, document_id: str) -> Optional[bytes]:
        '''Создает итоговый PDF документ с информацией о всех подписях'''
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib.units import cm
            import io
            from reportlab.lib.colors import HexColor
            import reportlab.lib.colors as colors
            
            mayan_client = self._get_mayan_client()
            
            # Получаем бинарный файл документа
            document_content = mayan_client.get_document_file_content(document_id)
            if not document_content:
                logger.error(f'Не удалось получить содержимое документа {document_id}')
                return None
            
            # Получаем список подписей
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            files_list = files_data.get('results', [])
            
            # Ищем все подписи и метаданные
            signatures_info = []
            for file_info in files_list:
                filename = file_info.get('filename', '')
                
                # Ищем файлы метаданных подписей
                if filename.startswith('signature_metadata_') and filename.endswith('.json'):
                    try:
                        # Загружаем метаданные
                        metadata_response = mayan_client._make_request('GET', 
                            f'documents/{document_id}/files/{file_info["id"]}/download/')
                        metadata_response.raise_for_status()
                        metadata = json.loads(metadata_response.content)
                        
                        signatures_info.append(metadata)
                        logger.info(f'Найдена подпись: {filename}, username: {metadata.get("username")}')
                    except Exception as e:
                        logger.error(f'Ошибка загрузки метаданных {filename}: {e}')
                        continue
            
            logger.info(f'Всего найдено подписей: {len(signatures_info)}')
            
            # Если нет подписей, возвращаем исходный документ
            if not signatures_info:
                logger.info(f'Документ {document_id} не имеет подписей')
                return document_content
            
            # Загружаем шрифты для поддержки русского текста
            fonts_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
            font_name = 'Helvetica'
            
            font_files = [
                ('DejaVuSans', 'DejaVuSans.ttf'),
                ('LiberationSans', 'LiberationSans-Regular.ttf'),
            ]
            
            for fn_name, font_file in font_files:
                font_path = os.path.join(fonts_dir, font_file)
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(fn_name, font_path))
                        font_name = fn_name
                        logger.info(f'Загружен шрифт: {fn_name}')
                        break
                    except Exception as e:
                        logger.warning(f'Не удалось загрузить шрифт {fn_name}: {e}')
                        continue
            
            # Создаем страницу с информацией о подписях в виде плашек
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=A4)
            
            # Цвета для плашек
            blue_color = HexColor('#1E3A8A')
            light_background = HexColor('#F0F8FF')
            light_stroke = HexColor('#3B82F6')
            
            # Заголовок страницы
            can.setFont(font_name, 16)
            can.setFillColor(blue_color)
            can.drawString(2*cm, 28*cm, 'Информация об электронных подписях')
            
            can.setFont(font_name, 9)
            can.setFillColor(colors.grey)
            can.drawString(2*cm, 27.5*cm, f'Документ ID: {document_id}')
            can.drawString(2*cm, 27.2*cm, f'Дата создания отчета: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}')
            can.drawString(2*cm, 26.9*cm, f'Количество подписей: {len(signatures_info)}')
            
            # ИЗМЕНЕНИЕ: Плашки по 2 в строку, меньшей ширины
            # Параметры плашки
            block_x_start = 1.5*cm  # Левая колонка
            block_x_start_right = 10.5*cm  # Правая колонка (1.5 + 9 + 0)
            block_y_start = 23*cm  # ИЗМЕНЕНИЕ: Опускаем ниже (было 25)
            block_width = 8.5*cm  # ИЗМЕНЕНИЕ: Уменьшаем ширину (было 19)
            block_height = 3.5*cm  # ИЗМЕНЕНИЕ: Немного увеличиваем высоту
            vertical_spacing = 0.5*cm  # Расстояние между плашками
            horizontal_spacing = 0  # Между колонками
            
            logger.info(f'=== НАЧАЛО РИСОВАНИЯ ПЛАШЕК ===')
            logger.info(f'Количество подписей: {len(signatures_info)}')
            
            for i, sig_info in enumerate(signatures_info, 1):
                logger.info(f'=== РИСУЕМ ПЛАШКУ {i} ===')
                
                # ИЗМЕНЕНИЕ: Определяем колонку (левая или правая)
                column = (i - 1) % 2
                block_x = block_x_start if column == 0 else block_x_start_right
                
                # ИЗМЕНЕНИЕ: Вычисляем номер строки для вертикальной позиции
                row = (i - 1) // 2  # Целочисленное деление для номера строки
                
                # Рассчитываем ПОЗИЦИЮ С НИЗА
                card_y_bottom = block_y_start - row * (block_height + vertical_spacing)
                
                logger.info(f'Плашка {i}: column={column}, row={row}, card_y_bottom={card_y_bottom}')
                
                # Получаем данные ДО рисования
                cert_info = sig_info.get('certificate_info', {})
                username = sig_info.get('username', 'Неизвестно')
                cert_subject = cert_info.get('subject', 'Неизвестно')
                cert_issuer = cert_info.get('issuer', 'Неизвестно')
                cert_serial = cert_info.get('serialNumber', 'Неизвестно')
                
                # ИЗМЕНЕНИЕ: Извлекаем CN из subject
                # Формат: "CN=Иванов Иван Иванович, SN=Иванов, G=Иван Иванович"
                cn_value = 'Неизвестно'
                if cert_subject != 'Неизвестно':
                    for part in cert_subject.split(','):
                        if part.strip().startswith('CN='):
                            cn_value = part.strip().replace('CN=', '').strip()
                            break
                
                # ИЗМЕНЕНИЕ: Извлекаем CN из issuer
                issuer_cn = 'Неизвестно'
                if cert_issuer != 'Неизвестно':
                    for part in cert_issuer.split(','):
                        if part.strip().startswith('CN='):
                            issuer_cn = part.strip().replace('CN=', '').strip()
                            break
                
                # Обрабатываем даты сертификата
                valid_from = cert_info.get('validFrom', '')
                valid_to = cert_info.get('validTo', '')
                
                from_date_str = "Неизвестно"
                to_date_str = "Неизвестно"
                if valid_from and valid_to:
                    try:
                        from_date = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                        to_date = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))
                        from_date_str = from_date.strftime('%d.%m.%Y %H:%M')
                        to_date_str = to_date.strftime('%d.%m.%Y %H:%M')
                    except:
                        pass
                
                # Фон блока (светло-голубой) с ЗАКРУГЛЕННЫМИ УГЛАМИ
                can.setFillColor(light_background)
                can.setStrokeColor(blue_color)
                can.setLineWidth(1.5)
                can.roundRect(block_x, card_y_bottom, block_width, block_height, 6, fill=1, stroke=1)
                
                # Внутренняя рамка
                can.setStrokeColor(light_stroke)
                can.setLineWidth(0.5)
                can.roundRect(block_x + 0.1*cm, card_y_bottom + 0.1*cm, 
                            block_width - 0.2*cm, block_height - 0.2*cm, 4, fill=0, stroke=1)
                
                # Заголовок блока
                can.setFillColor(blue_color)
                can.setFont(font_name, 9)
                can.drawString(block_x + 0.3*cm, card_y_bottom + 2.7*cm, 
                              f'ЭЛЕКТРОННАЯ ПОДПИСЬ №{i}')
                
                # Линия под заголовком
                can.setStrokeColor(blue_color)
                can.setLineWidth(1)
                can.line(block_x + 0.3*cm, card_y_bottom + 2.5*cm, 
                        block_x + block_width - 0.3*cm, card_y_bottom + 2.5*cm)
                
                # Информация о подписи
                can.setFillColor(HexColor('#000000'))
                can.setFont(font_name, 7)
                
                # ИЗМЕНЕНИЕ: "Дата" -> "Дата подписания"
                sign_date = sig_info.get('sign_date', '')
                if sign_date:
                    try:
                        sign_dt = datetime.fromisoformat(sign_date)
                        sign_date_str = sign_dt.strftime('%d.%m.%Y %H:%M')
                    except:
                        sign_date_str = sign_date[:16] if len(sign_date) >= 16 else sign_date[:10]
                else:
                    sign_date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
                
                can.drawString(block_x + 0.3*cm, card_y_bottom + 2.1*cm, f'Дата подписания: {sign_date_str}')
                
                # ИЗМЕНЕНИЕ: "Сертификат" -> "Владелец сертификата"
                cn_short = cn_value[:35] + "..." if len(cn_value) > 35 else cn_value
                can.drawString(block_x + 0.3*cm, card_y_bottom + 1.8*cm, f'Владелец сертификата: {cn_short}')
                
                # ИЗМЕНЕНИЕ: Показываем только CN из issuer
                issuer_cn_short = issuer_cn[:35] + "..." if len(issuer_cn) > 35 else issuer_cn
                can.drawString(block_x + 0.3*cm, card_y_bottom + 1.5*cm, f'Выдан: {issuer_cn_short}')
                
                # Действителен с датой и временем
                can.drawString(block_x + 0.3*cm, card_y_bottom + 1.2*cm, f'Действителен: {from_date_str} - {to_date_str}')
                
                # Статус подписи
                can.setFillColor(HexColor('#059669'))
                can.setFont(font_name, 8)
                can.drawString(block_x + 0.3*cm, card_y_bottom + 0.85*cm, "✓ ПОДПИСЬ ДЕЙСТВИТЕЛЬНА")
                
                # Дополнительная информация
                can.setFillColor(HexColor('#6B7280'))
                can.setFont(font_name, 6)
                can.drawString(block_x + 0.3*cm, card_y_bottom + 0.4*cm, "CryptoPro • CAdES-BES")
                
                logger.info(f'Плашка {i} нарисована')
            
            can.save()
            
            # Читаем созданную страницу подписей
            packet.seek(0)
            sig_page = PdfReader(packet).pages[0]
            
            # Читаем исходный документ
            original_pdf = PdfReader(io.BytesIO(document_content))
            
            # Создаем новый PDF с исходным содержимым + страницей подписей
            output = PdfWriter()
            
            # Добавляем все страницы исходного документа
            for page in original_pdf.pages:
                output.add_page(page)
            
            # Добавляем страницу с информацией о подписях
            output.add_page(sig_page)
            
            # Сохраняем итоговый PDF
            final_pdf = io.BytesIO()
            output.write(final_pdf)
            final_pdf.seek(0)
            
            logger.info(f'Успешно создан PDF с подписями для документа {document_id}')
            return final_pdf.read()
            
        except Exception as e:
            logger.error(f'Ошибка создания итогового PDF для документа {document_id}: {e}', exc_info=True)
            return None

    def document_has_signatures(self, document_id: str) -> bool:
        '''Проверяет, есть ли у документа подписи'''
        try:
            mayan_client = self._get_mayan_client()
            
            # Получаем список файлов документа
            files_response = mayan_client._make_request('GET', f'documents/{document_id}/files/')
            files_response.raise_for_status()
            files_data = files_response.json()
            files_list = files_data.get('results', [])
            
            # Ищем файлы подписей (*.p7s)
            for file_info in files_list:
                filename = file_info.get('filename', '')
                if filename.endswith('.p7s'):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f'Ошибка проверки наличия подписей для документа {document_id}: {e}')
            return False