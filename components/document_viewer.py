"""
Компонент для просмотра документов с каруселью страниц
"""
from nicegui import ui
from typing import Optional
import logging
import base64

from components.loading_indicator import LoadingIndicator
from services.mayan_connector import MayanClient

logger = logging.getLogger(__name__)


async def show_document_viewer(document_id: str, document_name: Optional[str] = None, mayan_client=None):
    """
    Открывает диалог просмотра документа с каруселью страниц
    
    Args:
        document_id: ID документа в Mayan EDMS
        document_name: Название документа (опционально)
        mayan_client: Экземпляр MayanClient (если не указан, будет создан)
    """
    try:
        # Если клиент не передан, создаем его
        if mayan_client is None:
            mayan_client = await MayanClient.create_with_session_user()
        
        # Получаем все страницы документа
        pages = await mayan_client.get_document_pages(str(document_id))
        
        if not pages or len(pages) == 0:
            # Если страниц нет, пробуем получить хотя бы первую страницу
            preview_url = await mayan_client.get_document_preview_url(str(document_id))
            if preview_url:
                # Для просмотра используем window.open, так как это просмотр, а не скачивание
                ui.run_javascript(f'window.open("{preview_url}", "_blank")')
            else:
                ui.notify('Предварительный просмотр недоступен', type='warning')
            return
        
        # Создаем диалог с индикатором загрузки
        with ui.dialog().classes('w-full h-full') as dialog:
            with ui.card().classes('w-full h-full flex flex-col').style('max-width: 99vw; max-height: 99vh; height: 99vh; width: auto;'):
                # Заголовок
                title = f'Просмотр документа: {document_name}' if document_name else 'Просмотр документа'
                ui.label(title).classes('text-lg font-semibold mb-2 flex-shrink-0 px-4')
                
                # Контейнер для индикатора загрузки (отцентрирован)
                loading_container = ui.column().classes('flex-1').style('display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 1rem;')
                
                # Создаем индикатор загрузки
                loading = LoadingIndicator(loading_container, 'Загрузка страниц документа...')
                loading.show()
                
                # Убираем w-full и центрируем row
                if loading.row_widget:
                    loading.row_widget.classes(remove='w-full')
                    loading.row_widget.style('width: auto; margin: 0 auto;')
                
                dialog.open()
                
                # Загружаем изображения всех страниц с обновлением прогресса
                pages_data = []
                total_pages = len(pages)
                
                for index, page in enumerate(pages, 1):
                    image_url = page.get('image_url')
                    if image_url:
                        try:
                            # Обновляем прогресс
                            loading.update_message(f'Загрузка страниц документа... {index} / {total_pages}')
                            
                            if image_url.startswith('http://') or image_url.startswith('https://'):
                                response = await mayan_client.client.get(image_url)
                            else:
                                if image_url.startswith('/'):
                                    full_url = f'{mayan_client.base_url.rstrip("/")}{image_url}'
                                else:
                                    full_url = f'{mayan_client.api_url.rstrip("/")}/{image_url.lstrip("/")}'
                                response = await mayan_client.client.get(full_url)
                            
                            if response.status_code == 200:
                                image_data = response.content
                                img_base64 = base64.b64encode(image_data).decode()
                                
                                mimetype = 'image/jpeg'
                                if image_data[:4] == b'\x89PNG':
                                    mimetype = 'image/png'
                                elif image_data[:6] in [b'GIF87a', b'GIF89a']:
                                    mimetype = 'image/gif'
                                
                                data_uri = f'data:{mimetype};base64,{img_base64}'
                                pages_data.append({
                                    'page_number': page.get('page_number', len(pages_data) + 1),
                                    'data_uri': data_uri
                                })
                        except Exception as e:
                            logger.warning(f'Ошибка загрузки страницы {page.get("page_number")}: {e}')
                
                if not pages_data:
                    loading.update_message('Не удалось загрузить страницы документа')
                    ui.timer(3.0, dialog.close, once=True)
                    return
                
                # Скрываем индикатор загрузки
                loading.hide()
                loading_container.set_visibility(False)
                
                # Информация о странице (фиксированная высота)
                page_info_label = ui.label(f'Страница 1 из {len(pages_data)}').classes('text-sm text-gray-600 mb-2 flex-shrink-0 px-4')
                
                # Контейнер для изображения (занимает оставшееся пространство, без пустых отступов)
                image_container = ui.html('').classes('flex-1 overflow-auto').style('min-height: 0; width: 100%; display: flex; justify-content: center; align-items: center; padding: 0;')
                
                current_page = {'index': 0}
                
                def update_page_display():
                    page_data = pages_data[current_page['index']]
                    page_number = page_data['page_number']
                    page_info_label.text = f'Страница {current_page["index"] + 1} из {len(pages_data)} (страница документа: {page_number})'
                    # Изображение центрируется и занимает максимум доступного пространства
                    image_container.content = f'<img src="{page_data["data_uri"]}" alt="Страница {page_number}" style="max-width: 100%; max-height: calc(99vh - 250px); height: auto; width: auto; object-fit: contain; display: block; margin: 0 auto;" />'
                    image_container.update()
                
                # Кнопки навигации и закрытия (фиксированная высота, отцентрированы)
                with ui.row().classes('w-full justify-center items-center gap-4 mb-2 flex-shrink-0 px-4'):
                    prev_button = ui.button('Предыдущая', icon='arrow_back').classes('bg-blue-500 text-white')
                    next_button = ui.button('Следующая', icon='arrow_forward').classes('bg-blue-500 text-white')
                    close_button = ui.button('Закрыть', icon='close', on_click=dialog.close).classes('bg-gray-500 text-white')
                    
                    # Добавляем уникальные ID для поиска кнопок
                    prev_button_id = f'prev_btn_{id(prev_button)}'
                    next_button_id = f'next_btn_{id(next_button)}'
                    prev_button.props(f'id={prev_button_id}')
                    next_button.props(f'id={next_button_id}')
                    
                    def go_to_previous():
                        if current_page['index'] > 0:
                            current_page['index'] -= 1
                            update_page_display()
                            prev_button.set_enabled(current_page['index'] > 0)
                            next_button.set_enabled(current_page['index'] < len(pages_data) - 1)
                    
                    def go_to_next():
                        if current_page['index'] < len(pages_data) - 1:
                            current_page['index'] += 1
                            update_page_display()
                            prev_button.set_enabled(current_page['index'] > 0)
                            next_button.set_enabled(current_page['index'] < len(pages_data) - 1)
                    
                    prev_button.on_click(go_to_previous)
                    next_button.on_click(go_to_next)
                    
                    if len(pages_data) > 1:
                        prev_button.set_enabled(False)
                        next_button.set_enabled(True)
                    else:
                        prev_button.set_enabled(False)
                        next_button.set_enabled(False)
                
                # Добавляем обработку клавиш-стрелок для навигации
                # Используем задержку, чтобы диалог успел полностью отрендериться
                def setup_keyboard_navigation():
                    dialog_id = id(dialog)
                    ui.run_javascript(f'''
                        (function() {{
                            const handlerId = 'docViewerKeyHandler_{dialog_id}';
                            const prevBtnId = '{prev_button_id}';
                            const nextBtnId = '{next_button_id}';
                            
                            function handleKeyDown(event) {{
                                // Проверяем, что диалог открыт - используем несколько способов
                                let dialog = document.querySelector('.q-dialog--active');
                                if (!dialog) {{
                                    // Альтернативный способ поиска диалога
                                    dialog = document.querySelector('.q-dialog:not([style*="display: none"])');
                                }}
                                if (!dialog) return;
                                
                                // Игнорируем, если пользователь вводит текст
                                const activeEl = document.activeElement;
                                if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {{
                                    return;
                                }}
                                
                                if (event.key === 'ArrowLeft') {{
                                    event.preventDefault();
                                    event.stopPropagation();
                                    // Ищем кнопку по ID
                                    const prevBtn = document.getElementById(prevBtnId);
                                    if (prevBtn && !prevBtn.disabled && !prevBtn.classList.contains('disabled')) {{
                                        prevBtn.click();
                                    }}
                                }} else if (event.key === 'ArrowRight') {{
                                    event.preventDefault();
                                    event.stopPropagation();
                                    // Ищем кнопку по ID
                                    const nextBtn = document.getElementById(nextBtnId);
                                    if (nextBtn && !nextBtn.disabled && !nextBtn.classList.contains('disabled')) {{
                                        nextBtn.click();
                                    }}
                                }}
                            }}
                            
                            // Добавляем обработчик с небольшой задержкой для гарантии, что DOM готов
                            setTimeout(function() {{
                                document.addEventListener('keydown', handleKeyDown, true);
                                window[handlerId] = handleKeyDown;
                                console.log('Keyboard handler установлен для диалога', handlerId);
                            }}, 100);
                        }})();
                    ''')
                
                # Устанавливаем обработчик после небольшой задержки
                ui.timer(0.2, setup_keyboard_navigation, once=True)
                
                # Сохраняем оригинальный метод закрытия и добавляем очистку обработчика
                original_close = dialog.close
                def close_with_cleanup():
                    dialog_id = id(dialog)
                    ui.run_javascript(f'''
                        (function() {{
                            const handlerId = 'docViewerKeyHandler_{dialog_id}';
                            if (window[handlerId]) {{
                                document.removeEventListener('keydown', window[handlerId], true);
                                delete window[handlerId];
                                console.log('Keyboard handler удален', handlerId);
                            }}
                        }})();
                    ''')
                    original_close()
                dialog.close = close_with_cleanup
                
                # Отображаем первую страницу
                update_page_display()
            
    except Exception as e:
        logger.error(f"Ошибка при открытии просмотра документа {document_id}: {e}", exc_info=True)
        ui.notify(f'Ошибка при открытии просмотра: {str(e)}', type='error')
