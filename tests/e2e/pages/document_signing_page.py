"""
Page Object для страницы завершения задач (task_completion), где происходит подписание документов
"""
from playwright.async_api import Page
from typing import Optional, Dict, Any
import asyncio


class TaskCompletionPage:
    """Page Object для страницы завершения задач (task_completion), где происходит подписание документов"""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def navigate_to(self, base_url: str, task_id: Optional[str] = None):
        """Переходит на страницу завершения задач (task_completion)"""
        url = f'{base_url}/task_completion'
        if task_id:
            url = f'{url}?task_id={task_id}'
        
        await self.page.goto(url, wait_until='domcontentloaded')
        
        # Проверяем, не произошел ли редирект на страницу входа
        await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
        current_url = self.page.url
        
        if '/login' in current_url:
            raise Exception(f'Произошел редирект на страницу входа. Возможно, пользователь не авторизован. Текущий URL: {current_url}')
        
        # Ждем загрузки страницы
        await self.page.wait_for_load_state('networkidle', timeout=10000)
    
    async def is_on_task_completion_page(self) -> bool:
        """Проверяет, находимся ли мы на странице завершения задач"""
        current_url = self.page.url
        return '/task_completion' in current_url
    
    async def wait_for_tasks_loaded(self, timeout: int = 10000):
        """Ждет загрузки списка задач на странице завершения задач"""
        try:
            # Ждем появления табов или списка задач
            # Страница task_completion имеет табы: "Мои активные задачи", "Завершенные задачи", "Детали задачи"
            await self.page.wait_for_selector(
                '.q-tabs, .q-tab, .q-item, .task-item, text="Мои активные задачи", text="Завершенные задачи"',
                timeout=timeout,
                state='visible'
            )
        except:
            # Если не найдено, просто ждем загрузки
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
    
    async def get_tasks_count(self) -> int:
        """Получает количество активных задач"""
        try:
            # Ищем задачи в табе "Мои активные задачи"
            task_items = self.page.locator('.q-item, .task-item, [data-task-id], .q-list-item')
            count = await task_items.count()
            return count
        except:
            return 0
    
    async def switch_to_active_tasks_tab(self):
        """Переключается на таб с активными задачами"""
        try:
            active_tab = self.page.locator('.q-tab:has-text("Мои активные задачи"), .q-tab:has-text("Активные задачи")').first
            await active_tab.click()
            await self.page.wait_for_timeout(500)  # Ждем переключения
        except Exception as e:
            raise Exception(f'Не удалось переключиться на таб активных задач: {e}')
    
    async def open_task_by_id(self, task_id: str):
        """Открывает задачу по ID"""
        try:
            # Ищем задачу по ID и кликаем на неё
            task_link = self.page.locator(f'[data-task-id="{task_id}"], a:has-text("{task_id}")').first
            await task_link.click()
            await self.page.wait_for_timeout(1000)  # Ждем открытия задачи
        except Exception as e:
            raise Exception(f'Не удалось открыть задачу {task_id}: {e}')
    
    async def find_signing_task(self) -> Optional[str]:
        """Находит задачу на подписание (с именем 'Подписать документ')"""
        try:
            # Ищем задачу с именем "Подписать документ" в списке задач
            # Задачи могут быть в разных форматах: .q-item, .task-item, карточки
            task_card = self.page.locator(
                '.q-item:has-text("Подписать документ"), '
                '.task-item:has-text("Подписать документ"), '
                '[data-task-name*="Подписать документ"], '
                '.q-card:has-text("Подписать документ")'
            ).first
            
            # Пытаемся получить task_id из атрибута
            task_id = await task_card.get_attribute('data-task-id')
            
            # Если не нашли в атрибуте, пытаемся найти в родительском элементе
            if not task_id:
                parent = task_card.locator('..')
                task_id = await parent.get_attribute('data-task-id')
            
            # Если все еще не нашли, возвращаем True (задача найдена, но ID не нужен)
            return task_id if task_id else "found"
        except:
            return None
    
    async def open_signing_task(self):
        """Открывает задачу на подписание (находит задачу и нажимает 'Завершить задачу')"""
        try:
            # Ищем задачу с именем "Подписать документ"
            # Кнопка "Завершить задачу" для задачи подписания открывает форму подписания
            complete_button = self.page.locator(
                '.q-item:has-text("Подписать документ") ~ button:has-text("Завершить задачу"), '
                '.task-item:has-text("Подписать документ") ~ button:has-text("Завершить задачу"), '
                'button:has-text("Завершить задачу")'
            ).first
            
            await complete_button.wait_for(state='visible', timeout=10000)
            await complete_button.click()
            await self.page.wait_for_timeout(2000)  # Ждем открытия формы подписания
            
            # Ждем появления формы подписания
            await self.wait_for_signing_form()
        except Exception as e:
            # Если не нашли кнопку "Завершить задачу", пытаемся найти задачу и кликнуть на неё
            try:
                task_card = self.page.locator(
                    '.q-item:has-text("Подписать документ"), '
                    '.task-item:has-text("Подписать документ"), '
                    '[data-task-name*="Подписать документ"]'
                ).first
                await task_card.click()
                await self.page.wait_for_timeout(1000)
                await self.wait_for_signing_form()
            except:
                raise Exception(f'Не удалось открыть задачу на подписание: {e}')
    
    async def wait_for_signing_form(self, timeout: int = 10000):
        """Ждет появления формы подписания"""
        try:
            # Ждем появления элементов формы подписания
            await self.page.wait_for_selector(
                'select, .q-select, text="Сертификат", text="Подписать документ"',
                timeout=timeout,
                state='visible'
            )
        except:
            pass  # Форма может появиться позже
    
    async def click_sign_button(self, task_id: Optional[str] = None):
        """Нажимает кнопку подписания для задачи на странице task_completion"""
        try:
            # Кнопка "Подписать документ" появляется только после открытия формы подписания
            # Сначала нужно открыть задачу на подписание
            if not task_id:
                # Пытаемся найти и открыть задачу на подписание
                await self.open_signing_task()
            
            # Теперь ищем кнопку "Подписать документ" в форме
            sign_button = self.page.locator(
                'button:has-text("Подписать документ"), '
                '.q-btn:has-text("Подписать документ")'
            ).first
            
            await sign_button.wait_for(state='visible', timeout=10000)
            await sign_button.click()
            await self.page.wait_for_timeout(500)  # Ждем обработки клика
        except Exception as e:
            raise Exception(f'Не удалось найти или нажать кнопку подписания: {e}')
    
    async def wait_for_certificate_dialog(self, timeout: int = 5000):
        """Ждет появления диалога выбора сертификата"""
        try:
            await self.page.wait_for_selector(
                '.q-dialog, .certificate-dialog, select, [data-certificate-select]',
                timeout=timeout,
                state='visible'
            )
        except:
            pass  # Диалог может не появиться, если плагин не установлен
    
    async def select_certificate(self, index: int = 0):
        """Выбирает сертификат по индексу"""
        try:
            certificate_select = self.page.locator('select, .q-select').first
            await certificate_select.wait_for(state='visible', timeout=5000)
            await certificate_select.select_option(index=str(index))
        except Exception as e:
            raise Exception(f'Не удалось выбрать сертификат: {e}')
    
    async def wait_for_signature_complete(self, timeout: int = 30000):
        """Ждет завершения подписания"""
        try:
            # Ждем появления сообщения об успехе или ошибке
            await self.page.wait_for_selector(
                'text=/подписан|успешно|ошибка|error/i',
                timeout=timeout,
                state='visible'
            )
        except:
            # Если сообщение не появилось, просто ждем
            await self.page.wait_for_timeout(2000)
    
    async def is_plugin_available(self) -> bool:
        """Проверяет, доступен ли CryptoPro плагин"""
        try:
            # Проверяем наличие cadesplugin в консоли браузера
            result = await self.page.evaluate('typeof window.cadesplugin !== "undefined"')
            return result
        except:
            return False
    
    async def mock_plugin_available(self):
        """Мокирует CryptoPro плагин для тестирования"""
        await self.page.add_init_script("""
            // Мокируем cadesplugin для тестирования
            window.cadesplugin = {
                async_spawn: function(generator) {
                    return new Promise((resolve, reject) => {
                        try {
                            const gen = generator();
                            let result = gen.next();
                            
                            function handleResult(result) {
                                if (result.done) {
                                    resolve(result.value);
                                } else {
                                    Promise.resolve(result.value).then(
                                        value => handleResult(gen.next(value)),
                                        err => reject(err)
                                    );
                                }
                            }
                            
                            handleResult(result);
                        } catch (err) {
                            reject(err);
                        }
                    });
                },
                CreateObjectAsync: function(objectName) {
                    return Promise.resolve({
                        Open: function() { return Promise.resolve(); },
                        Certificates: Promise.resolve({
                            Count: Promise.resolve(1),
                            Item: function(index) {
                                return Promise.resolve({
                                    SubjectName: Promise.resolve("CN=Test User"),
                                    HasPrivateKey: function() { return Promise.resolve(true); }
                                });
                            }
                        }),
                        propset_Certificate: function(cert) { return Promise.resolve(); },
                        propset_Content: function(content) { return Promise.resolve(); },
                        propset_ContentEncoding: function(encoding) { return Promise.resolve(); },
                        propset_Options: function(options) { return Promise.resolve(); },
                        SignCades: function(signer, type, detached) {
                            // Возвращаем моковую подпись
                            return Promise.resolve("MOCK_SIGNATURE_BASE64_DATA");
                        }
                    });
                },
                CADESCOM_BASE64_TO_BINARY: 1,
                CADESCOM_CADES_BES: 1
            };
        """)
    
    async def simulate_certificate_selection(self, certificate_index: int = 0):
        """Симулирует выбор сертификата"""
        await self.page.evaluate(f"""
            if (window.nicegui_handle_event) {{
                window.nicegui_handle_event('certificate_selected', {{
                    index: {certificate_index},
                    certificate: {{
                        subject: 'CN=Test User',
                        validTo: '2025-12-31',
                        issuer: 'Test CA'
                    }}
                }});
            }}
        """)
    
    async def simulate_signature_complete(self, signature_data: str = "MOCK_SIGNATURE_BASE64"):
        """Симулирует завершение подписания"""
        await self.page.evaluate(f"""
            if (window.nicegui_handle_event) {{
                window.nicegui_handle_event('signature_completed', {{
                    signature_data: '{signature_data}',
                    certificate_info: {{
                        subject: 'CN=Test User',
                        validTo: '2025-12-31'
                    }}
                }});
            }}
        """)
    
    async def simulate_signature_error(self, error_message: str = "Ошибка подписания"):
        """Симулирует ошибку подписания"""
        await self.page.evaluate(f"""
            if (window.nicegui_handle_event) {{
                window.nicegui_handle_event('signature_error', {{
                    error: '{error_message}'
                }});
            }}
        """)

