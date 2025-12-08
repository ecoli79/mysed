// Обновленный cryptopro-integration.js
class CryptoProIntegration {
    constructor() {
        this.pluginAvailable = false;
        this.pluginLoaded = false;
        this.globalSelectboxContainer = []; // Используем глобальный контейнер
        this.diagnosticInfo = {};
        // this.checkPluginAvailability();
    }
        
    checkBrowserSupport() {
        const userAgent = navigator.userAgent.toLowerCase();
        const isChrome = userAgent.includes('chrome') && !userAgent.includes('edge');
        const isFirefox = userAgent.includes('firefox');
        const isEdge = userAgent.includes('edge');
        const isIE = userAgent.includes('msie') || userAgent.includes('trident');
        const isSafari = userAgent.includes('safari') && !userAgent.includes('chrome');
        
        const isAndroid = userAgent.includes('android');
        const isIOS = userAgent.includes('iphone') || userAgent.includes('ipad');
        const isMobile = isAndroid || isIOS || userAgent.includes('mobile');
        
        const isWindows = userAgent.includes('windows');
        const isLinux = userAgent.includes('linux') && !userAgent.includes('android');
        const isMacOS = userAgent.includes('mac os x');
        
        return {
            userAgent: navigator.userAgent,
            isChrome, isFirefox, isEdge, isIE, isSafari,
            isAndroid, isIOS, isMobile,
            isWindows, isLinux, isMacOS,
            supportsNPAPI: isWindows && (isIE || (isChrome && !isEdge)),
            recommendedBrowser: isMobile ? 'Не поддерживается на мобильных устройствах' :
                              !isWindows ? 'Только Windows поддерживается' :
                              isIE ? 'Internet Explorer' : 
                              isEdge ? 'Edge (режим совместимости)' : 
                              isChrome ? 'Chrome с расширением КриптоПро' : 
                              'Internet Explorer или Chrome с расширением'
        };
    }
    
    showMobileNotSupported() {
        const message = 'КриптоПро ЭЦП Browser Plug-in не поддерживается на мобильных устройствах. Используйте компьютер с Windows.';
        console.warn(message);
        if (window.nicegui_handle_event) {
            window.nicegui_handle_event('mobile_not_supported', { message });
        }
    }
    
    showOSNotSupported() {
        const message = 'КриптоПро ЭЦП Browser Plug-in работает только на Windows. Используйте компьютер с Windows.';
        console.warn(message);
        if (window.nicegui_handle_event) {
            window.nicegui_handle_event('os_not_supported', { message });
        }
    }
    
    showInstallationInstructions() {
        const browserInfo = this.diagnosticInfo.browser || {};
        
        let instructions = '';
        
            instructions = `
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h4>КриптоПро плагин не установлен</h4>
                    <p>Для работы с электронной подписью необходимо:</p>
                    <ol>
                        <li>Установить <a href="https://www.cryptopro.ru/products/cades/plugin" target="_blank">КриптоПро ЭЦП Browser Plug-in</a></li>
                        <li>Установить расширение для вашего браузера:
                            <ul>
                                <li><strong>Chrome:</strong> <a href="https://chrome.google.com/webstore/detail/cryptopro-extension-for-c/iifchhfnnmpdbibifmljnfjhpififfog" target="_blank">CryptoPro Extension</a></li>
                                <li><strong>Firefox:</strong> Включить плагин в настройках браузера</li>
                                <li><strong>Internet Explorer:</strong> Добавить сайт в доверенные</li>
                            </ul>
                        </li>
                        <li>Перезапустить браузер</li>
                    </ol>
                    <p><strong>Диагностическая информация:</strong></p>
                    <pre>${JSON.stringify(this.diagnosticInfo, null, 2)}</pre>
                </div>
            `;
        // }
        
        if (window.nicegui_handle_event) {
            window.nicegui_handle_event('show_plugin_instructions', { 
                html: instructions,
                diagnostic: this.diagnosticInfo
            });
        }
    }
    
    // Используем готовые функции из Code.js и async_code.js
    async getAvailableCertificates() {
        // console.log('=== Начинаем получение сертификатов ===');
        
        try {
            // Проверяем наличие cadesplugin
            if (typeof window.cadesplugin === 'undefined') {
                const errorMsg = 'КриптоПро плагин не найден. Убедитесь, что скрипт cadesplugin_api.js загружен.';
                console.error(errorMsg);
                this.pluginAvailable = false;
                this.pluginLoaded = false;
                throw new Error(errorMsg);
            }
            
            console.log('=== Диагностика загрузки плагина КриптоПро ===');
            console.log('1. Проверяем наличие расширения...');
            
            // Проверяем наличие нового API расширения
            const hasNewAPI = typeof window.nmcades_plugin_api !== 'undefined' || 
                             typeof window.cpcsp_chrome_nmcades !== 'undefined';
            
            if (hasNewAPI) {
                console.log('✅ Обнаружен новый API расширения КриптоПро');
            } else {
                console.log('⚠️ Новый API расширения не найден, используем старый метод');
            }
            
            console.log('2. Пробуем получить плагин напрямую...');
            
            // В новом расширении плагин может быть уже готов, попробуем использовать его напрямую
            let cadesplugin;
            try {
                // Сначала пробуем получить плагин напрямую (для нового расширения)
                if (window.cadesplugin) {
                    if (typeof window.cadesplugin.then === 'function') {
                        // Это Promise - пробуем разрешить его с таймаутом
                        console.log('Плагин является Promise, пробуем разрешить...');
                        const loadTimeout = window.cadesplugin_load_timeout || 60000;
                        
                        // ВАЖНО: Promise может разрешиться в undefined, но сам объект cadesplugin уже создан
                        // Поэтому после разрешения Promise используем сам window.cadesplugin
                        try {
                            await Promise.race([
                                window.cadesplugin,
                                new Promise((_, reject) => 
                                    setTimeout(() => reject(new Error('Таймаут ожидания плагина')), loadTimeout)
                                )
                            ]);
                            console.log('✅ Promise разрешен');
                        } catch (e) {
                            console.warn('Promise отклонен или таймаут, но пробуем использовать плагин напрямую:', e);
                        }
                        
                        // После разрешения Promise, сам объект cadesplugin уже содержит все методы
                        // Проверяем, что это не Promise, а объект с методами
                        if (window.cadesplugin && typeof window.cadesplugin.then === 'function') {
                            // Если все еще Promise, значит плагин еще не загружен
                            // Но в новом расширении объект может быть уже готов
                            // Проверяем наличие методов напрямую
                            const tempPlugin = window.cadesplugin;
                            // Пробуем получить доступ к методам через сам Promise объект
                            // В новом расширении методы могут быть доступны напрямую
                            if (typeof tempPlugin.CreateObjectAsync !== 'undefined' || 
                                typeof tempPlugin.async_spawn !== 'undefined') {
                                cadesplugin = tempPlugin;
                                console.log('✅ Используем плагин напрямую из Promise объекта');
                            } else {
                                // Ждем еще немного и проверяем снова
                                await new Promise(resolve => setTimeout(resolve, 1000));
                                // После ожидания, объект должен быть готов
                                if (window.cadesplugin && typeof window.cadesplugin.CreateObjectAsync !== 'undefined') {
                                    cadesplugin = window.cadesplugin;
                                } else {
                                    throw new Error('Плагин не загружен после разрешения Promise');
                                }
                            }
                        } else if (window.cadesplugin) {
                            // Promise разрешился, и теперь это объект
                            cadesplugin = window.cadesplugin;
                            console.log('✅ Плагин получен после разрешения Promise');
                        } else {
                            throw new Error('Плагин не найден после разрешения Promise');
                        }
                    } else {
                        // Это уже готовый объект
                        console.log('✅ Плагин уже готов (не Promise)');
                        cadesplugin = window.cadesplugin;
                    }
                } else {
                    throw new Error('Плагин не найден');
                }
            } catch (pluginError) {
                // Если прямой доступ не сработал, пробуем через события (для совместимости со старым расширением)
                console.log('Прямой доступ не сработал, пробуем через события...');
                console.error('Ошибка:', pluginError);
                
                const pluginReady = new Promise((resolve, reject) => {
                    let resolved = false;
                    const loadTimeout = window.cadesplugin_load_timeout || 60000;
                    
                    console.log(`Ожидаем события от расширения (таймаут: ${loadTimeout} мс)...`);
                    
                    const timeoutId = setTimeout(() => {
                        if (!resolved) {
                            resolved = true;
                            window.removeEventListener('message', messageHandler);
                            console.error('❌ Таймаут ожидания события от расширения');
                            // Перед отклонением, пробуем использовать плагин напрямую
                            if (window.cadesplugin && typeof window.cadesplugin.CreateObjectAsync !== 'undefined') {
                                resolve(window.cadesplugin);
                            } else {
                                reject(new Error('Истекло время ожидания загрузки плагина'));
                            }
                        }
                    }, loadTimeout);
                    
                    const messageHandler = (event) => {
                        if (resolved) return;
                        
                        // Фильтруем сообщения от других расширений
                        if (typeof event.data !== 'string') {
                            return;
                        }
                        
                        if (event.data === 'cadesplugin_loaded' || 
                            event.data.includes('cadesplugin_loaded')) {
                            console.log('✅ Получено событие cadesplugin_loaded от расширения');
                            resolved = true;
                            clearTimeout(timeoutId);
                            window.removeEventListener('message', messageHandler);
                            
                            // После события, используем плагин напрямую
                            if (window.cadesplugin) {
                                if (typeof window.cadesplugin.then === 'function') {
                                    // Если все еще Promise, пробуем разрешить
                                    window.cadesplugin.then(plugin => {
                                        // Promise может вернуть undefined, используем window.cadesplugin
                                        resolve(plugin || window.cadesplugin);
                                    }).catch(err => {
                                        // Даже при ошибке, пробуем использовать window.cadesplugin
                                        if (window.cadesplugin && typeof window.cadesplugin.CreateObjectAsync !== 'undefined') {
                                            resolve(window.cadesplugin);
                                        } else {
                                            reject(err);
                                        }
                                    });
                                } else {
                                    resolve(window.cadesplugin);
                                }
                            } else {
                                reject(new Error('Плагин не найден после получения события загрузки'));
                            }
                        } else if (event.data === 'cadesplugin_load_error' || 
                                   event.data.includes('cadesplugin_load_error')) {
                            console.error('❌ Получено событие cadesplugin_load_error от расширения');
                            resolved = true;
                            clearTimeout(timeoutId);
                            window.removeEventListener('message', messageHandler);
                            reject(new Error('Расширение КриптоПро сообщило об ошибке загрузки'));
                        }
                    };
                    
                    window.addEventListener('message', messageHandler);
                    
                    // Также пробуем получить плагин напрямую
                    if (window.cadesplugin) {
                        if (typeof window.cadesplugin.then === 'function') {
                            window.cadesplugin.then(plugin => {
                                if (!resolved) {
                                    console.log('✅ Плагин загружен через Promise');
                                    resolved = true;
                                    clearTimeout(timeoutId);
                                    window.removeEventListener('message', messageHandler);
                                    // Используем plugin если он определен, иначе window.cadesplugin
                                    resolve(plugin || window.cadesplugin);
                                }
                            }).catch(err => {
                                // Игнорируем, ждем события
                            });
                        } else {
                            if (!resolved && typeof window.cadesplugin.CreateObjectAsync !== 'undefined') {
                                console.log('✅ Плагин уже загружен');
                                resolved = true;
                                clearTimeout(timeoutId);
                                window.removeEventListener('message', messageHandler);
                                resolve(window.cadesplugin);
                            }
                        }
                    }
                });
                
                cadesplugin = await pluginReady;
            }
            
            console.log('✅ Плагин КриптоПро успешно загружен');
            console.log('Тип cadesplugin:', typeof cadesplugin);
            console.log('cadesplugin:', cadesplugin);
            
            // ВАЖНО: Проверяем, что cadesplugin не undefined
            if (!cadesplugin || cadesplugin === undefined) {
                console.error('❌ cadesplugin is undefined, используем window.cadesplugin напрямую');
                // Если Promise разрешился в undefined, используем сам объект window.cadesplugin
                // который уже содержит все методы
                if (window.cadesplugin && typeof window.cadesplugin.CreateObjectAsync !== 'undefined') {
                    cadesplugin = window.cadesplugin;
                    console.log('✅ Используем window.cadesplugin напрямую');
                } else {
                    throw new Error('Плагин не загружен: cadesplugin is undefined');
                }
            }
            
            // Проверяем наличие метода CreateObjectAsync
            if (typeof cadesplugin.CreateObjectAsync === 'undefined') {
                const errorMsg = 'КриптоПро плагин не поддерживает асинхронное создание объектов. Возможно, требуется обновление плагина.';
                console.error(errorMsg);
                console.error('Доступные свойства cadesplugin:', Object.keys(cadesplugin));
                this.pluginAvailable = false;
                throw new Error(errorMsg);
            }
            
            // Устанавливаем доступность плагина
            this.pluginAvailable = true;
            this.pluginLoaded = true;
            
            console.log('Плагин доступен, начинаем получение сертификатов...');
            
            // Используем async_spawn для совместимости
            return new Promise((resolve, reject) => {
                cadesplugin.async_spawn(function*() {
                    try {
                        console.log('Создаем объект Store...');
                        const oStore = yield cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                        console.log('✅ Объект Store создан');
                        
                        console.log('Открываем хранилище сертификатов...');
                        yield oStore.Open();
                        console.log('✅ Хранилище открыто');
                        
                        console.log('Получаем список сертификатов...');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        console.log(`✅ Найдено сертификатов: ${certCnt}`);
                        
                        const certList = [];
                        window.global_selectbox_container = []; // Глобальный контейнер
                        
                        for (let i = 1; i <= certCnt; i++) {
                            try {
                                console.log(`Обрабатываем сертификат ${i}...`);
                                const cert = yield certs.Item(i);
                                const subject = yield cert.SubjectName;
                                const issuer = yield cert.IssuerName;
                                const serialNumber = yield cert.SerialNumber;
                                const validFrom = yield cert.ValidFromDate;
                                const validTo = yield cert.ValidToDate;
                                const hasPrivateKey = yield cert.HasPrivateKey();
                                
                                // Проверяем срок действия сертификата
                                const validToDate = new Date(validTo);
                                const isValid = validToDate > new Date();
                                
                                const certInfo = {
                                    subject: subject,
                                    issuer: issuer,
                                    serialNumber: serialNumber,
                                    validFrom: validFrom,
                                    validTo: validTo,
                                    isValid: isValid,
                                    hasPrivateKey: hasPrivateKey,
                                    index: i,  // Индекс в КриптоПро
                                    jsIndex: certList.length  // Индекс в JavaScript массиве
                                };
                                
                                // Добавляем только сертификаты с приватным ключом (для подписи)
                                if (hasPrivateKey) {
                                    certList.push(certInfo);
                                    window.global_selectbox_container.push(cert); // Сохраняем сертификат
                                    
                                    console.log(`Сертификат для подписи: ${subject} (КриптоПро индекс: ${i}, JS индекс: ${certList.length - 1})`);
                                } else {
                                    console.log(`Сертификат без приватного ключа: ${subject}`);
                                }
                                
                            } catch (certError) {
                                console.warn(`Ошибка при получении сертификата ${i}:`, certError);
                            }
                        }
                        
                        // console.log('Закрываем хранилище...');
                        yield oStore.Close();
                        // console.log(`✅ Успешно получено ${certList.length} сертификатов`);
                        
                        return certList;
                        
                    } catch (e) {
                        console.error('Ошибка при получении сертификатов:', e);
                        
                        // Если ошибка связана с разрешениями, даем более понятное сообщение
                        const errorMessage = e.message || String(e);
                        if (errorMessage.includes('permission') || errorMessage.includes('разрешение') || 
                            errorMessage.includes('доступ') || errorMessage.includes('access') ||
                            errorMessage.includes('denied') || errorMessage.includes('отказано')) {
                            throw new Error('Не получено разрешение на доступ к хранилищу сертификатов. Убедитесь, что вы нажали "Разрешить" в диалоге расширения КриптоПро.');
                        }
                        
                        throw e;
                    }
                }).then(resolve).catch(reject);
            });
            
        } catch (e) {
            console.error('Ошибка при получении сертификатов:', e);
            this.pluginAvailable = false;
            this.pluginLoaded = false;
            throw e;
        }
    }
}

// Глобальный экземпляр
window.cryptoProIntegration = new CryptoProIntegration();

// Глобальный контейнер для сертификатов (как в примере)
window.global_selectbox_container = [];

// Функция для обработки событий NiceGUI
window.nicegui_handle_event = async function(event_name, event_data) {
    try {
        console.log('NiceGUI Event:', event_name, event_data);
        
        const response = await fetch('/api/cryptopro-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                event: event_name,
                data: event_data
            })
        });
        
        const result = await response.json();
        console.log('Событие отправлено успешно:', result);
        
        // Обрабатываем ответ от API
        if (result.action === 'update_certificates_select' && result.options) {
            console.log('Создаем карточки сертификатов...');
            console.log('result:', result);
            
            const taskId = result.task_id || '';
            const options = result.options || {};
            const certificates = result.certificates || [];
            
            console.log('task_id:', taskId);
            console.log('Сертификатов для отображения:', certificates.length);
            
            // Показываем контейнер сертификатов
            if (taskId) {
                const certContainer = document.querySelector(`[data-task-id="${taskId}"][data-cert-container]`);
                if (certContainer) {
                    // Очищаем контейнер от старого select
                    certContainer.innerHTML = '';
                    
                    // Показываем контейнер
                    certContainer.style.display = '';
                    certContainer.style.visibility = 'visible';
                    certContainer.removeAttribute('hidden');
                    certContainer.style.opacity = '1';
                    
                    // Заголовок
                    const title = document.createElement('div');
                    title.style.fontWeight = '600';
                    title.style.fontSize = '16px';
                    title.style.marginBottom = '4px';  // Уменьшено с 16px до 4px
                    title.style.color = '#374151';
                    
                    // Фильтруем действительные сертификаты для подсчета
                    const now = new Date();  // Объявляем один раз
                    const validCount = certificates.filter(cert => {
                        if (!cert.validTo) return false;
                        const validToDate = new Date(cert.validTo);
                        if (isNaN(validToDate.getTime())) return false;
                        return validToDate > now && cert.isValid !== false;
                    }).length;
                    
                    // if (result.show_all) {
                    //     title.textContent = `Доступные сертификаты (действительных: ${validCount} из ${certificates.length})`;
                    // } else {
                    //     title.textContent = `Доступные сертификаты (действительных: ${validCount} из ${result.total_count || certificates.length})`;
                    // }

                    if (result.show_all) {
                        title.textContent = `Доступные сертификаты (${validCount})`;
                    } else {
                        title.textContent = `Доступные сертификаты (${validCount})`;
                    }
                    certContainer.appendChild(title);

                    // Контейнер для карточек - создаем ДО фильтрации
                    const cardsContainer = document.createElement('div');
                    cardsContainer.className = 'certificates-cards-container';
                    cardsContainer.style.display = 'flex';
                    cardsContainer.style.flexDirection = 'column';
                    cardsContainer.style.gap = '4px';
                    cardsContainer.style.maxHeight = '400px';
                    cardsContainer.style.overflowY = 'auto';
                    cardsContainer.style.paddingRight = '4px';
                    
                    // Стили для скроллбара
                    cardsContainer.style.scrollbarWidth = 'thin';
                    cardsContainer.style.scrollbarColor = '#cbd5e1 #f1f5f9';

                    // Создаем карточки для каждого сертификата
                    // Используем уже объявленную переменную now (строка 469)
                    const validCertificates = certificates.filter(cert => {
                        if (!cert.validTo) return false;
                        const validToDate = new Date(cert.validTo);
                        if (isNaN(validToDate.getTime())) return false;
                        return validToDate > now && cert.isValid !== false;
                    });
                    
                    if (validCertificates.length === 0) {
                        // Показываем сообщение, если нет действительных сертификатов
                        const emptyMessage = document.createElement('div');
                        emptyMessage.className = 'certificates-empty-message';
                        emptyMessage.style.padding = '20px';
                        emptyMessage.style.textAlign = 'center';
                        emptyMessage.style.color = '#9ca3af';
                        emptyMessage.style.fontSize = '14px';
                        emptyMessage.textContent = 'Сертификаты привязанные к пользователю не найдены';
                        certContainer.appendChild(emptyMessage);
                        ///console.log('Действительные сертификаты не найдены');
                        return;
                    }
                    
                    validCertificates.forEach((cert, index) => {
                        // Функция для извлечения CN из строки
                        const extractCN = (str) => {
                            if (!str) return 'Неизвестно';
                            const cnMatch = str.match(/CN=([^,]+)/i);
                            if (cnMatch) {
                                return cnMatch[1].replace(/^["']|["']$/g, '').trim();
                            }
                            return str; // Если CN не найден, возвращаем всю строку
                        };
                        
                        const card = document.createElement('div');
                        card.className = 'certificate-card';
                        card.style.padding = '4px 6px';
                        card.style.border = '1px solid #e5e7eb';
                        card.style.borderRadius = '4px';
                        card.style.backgroundColor = '#ffffff';
                        card.style.cursor = 'pointer';
                        card.style.transition = 'all 0.2s ease';
                        card.style.position = 'relative';
                        card.style.maxWidth = '350px';  // Ограничиваем ширину карточки
                        
                        // Эффект при наведении
                        card.addEventListener('mouseenter', function() {
                            // Не меняем стили, если карточка уже выбрана
                            if (!this.hasAttribute('data-selected')) {
                                this.style.borderColor = '#3b82f6';
                                this.style.boxShadow = '0 1px 2px -1px rgba(0, 0, 0, 0.1)';
                                this.style.transform = 'translateY(-1px)';
                            }
                        });
                        
                        card.addEventListener('mouseleave', function() {
                            // Не сбрасываем стили, если карточка выбрана
                            if (!this.hasAttribute('data-selected')) {
                                this.style.borderColor = '#e5e7eb';
                                this.style.boxShadow = 'none';
                                this.style.transform = 'translateY(0)';
                            }
                        });
                        
                        // Обработчик клика
                        card.addEventListener('click', function() {
                            // Убираем выделение с других карточек
                            cardsContainer.querySelectorAll('.certificate-card').forEach(c => {
                                c.removeAttribute('data-selected');
                                c.style.borderColor = '#e5e7eb';
                                c.style.borderWidth = '1px';
                                c.style.backgroundColor = '#ffffff';
                            });
                            
                            // Выделяем выбранную карточку синей рамкой
                            this.setAttribute('data-selected', 'true');
                            this.style.borderColor = '#3b82f6';
                            this.style.borderWidth = '2px';
                            this.style.backgroundColor = '#eff6ff';
                            
                            // Находим оригинальный индекс в массиве certificates
                            const originalIndex = certificates.findIndex(c => 
                                c.subject === cert.subject && 
                                c.serialNumber === cert.serialNumber
                            );
                            
                            // Отправляем событие о выборе сертификата с оригинальным индексом
                            window.nicegui_handle_event('certificate_selected', {
                                value: String(originalIndex >= 0 ? originalIndex : index),
                                text: extractCN(cert.subject),
                                certificate: cert,
                                task_id: taskId
                            });
                            
                            console.log('Выбран сертификат:', extractCN(cert.subject));
                        });
                        
                        // CN пользователя (владелец) - разрешаем перенос
                        const subjectCN = extractCN(cert.subject);
                        const subjectDiv = document.createElement('div');
                        subjectDiv.style.fontWeight = '600';
                        subjectDiv.style.fontSize = '12px';
                        subjectDiv.style.color = '#111827';
                        subjectDiv.style.marginBottom = '2px';
                        subjectDiv.style.lineHeight = '1.3';
                        subjectDiv.style.wordWrap = 'break-word';
                        subjectDiv.style.wordBreak = 'break-word';
                        subjectDiv.style.overflowWrap = 'break-word';
                        subjectDiv.textContent = subjectCN;
                        card.appendChild(subjectDiv);
                        
                        // CN издателя
                        const issuerCN = extractCN(cert.issuer);
                        const issuerDiv = document.createElement('div');
                        issuerDiv.style.fontSize = '11px';
                        issuerDiv.style.color = '#6b7280';
                        issuerDiv.style.marginBottom = '2px';
                        issuerDiv.style.lineHeight = '1.2';
                        issuerDiv.style.wordWrap = 'break-word';
                        issuerDiv.style.wordBreak = 'break-word';
                        issuerDiv.textContent = `Издатель: ${issuerCN}`;
                        card.appendChild(issuerDiv);
                        
                        // Срок действия
                        const validToDate = new Date(cert.validTo);
                        const isValid = validToDate > now;
                        const validDiv = document.createElement('div');
                        validDiv.style.fontSize = '11px';
                        validDiv.style.marginBottom = '2px';
                        validDiv.style.display = 'flex';
                        validDiv.style.alignItems = 'center';
                        validDiv.style.gap = '3px';
                        validDiv.style.lineHeight = '1.2';
                        validDiv.style.flexWrap = 'wrap';
                        
                        const validIcon = document.createElement('span');
                        validIcon.textContent = isValid ? '✅' : '❌';
                        validIcon.style.fontSize = '10px';
                        validDiv.appendChild(validIcon);
                        
                        const validText = document.createElement('span');
                        validText.style.color = isValid ? '#059669' : '#dc2626';
                        validText.textContent = isValid 
                            ? `До: ${validToDate.toLocaleDateString('ru-RU')}`
                            : `Истек: ${validToDate.toLocaleDateString('ru-RU')}`;
                        validDiv.appendChild(validText);
                        card.appendChild(validDiv);
                        
                        // Серийный номер
                        const serialDiv = document.createElement('div');
                        serialDiv.style.fontSize = '10px';
                        serialDiv.style.color = '#9ca3af';
                        serialDiv.style.fontFamily = 'monospace';
                        serialDiv.style.lineHeight = '1.2';
                        serialDiv.style.wordBreak = 'break-all';
                        serialDiv.textContent = `№: ${cert.serialNumber || 'Неизвестно'}`;
                        card.appendChild(serialDiv);
                        
                        cardsContainer.appendChild(card);
                    });
                    
                    certContainer.appendChild(cardsContainer);
                    
                    console.log(`✅ Создано ${validCertificates.length} карточек сертификатов (отфильтровано ${certificates.length - validCertificates.length} просроченных)`);
                } else {
                    console.error('❌ Контейнер сертификатов не найден по data-task-id:', taskId);
                }
            }
        }
        
        if (result.action === 'certificate_selected') {
            console.log('Сертификат выбран:', result.selected);
            
            // Показываем уведомление
            const notification = document.createElement('div');
            notification.textContent = '✅ Сертификат выбран!';
            notification.style.position = 'fixed';
            notification.style.top = '80px';
            notification.style.right = '20px';
            notification.style.backgroundColor = '#4CAF50';
            notification.style.color = 'white';
            notification.style.padding = '10px 20px';
            notification.style.borderRadius = '4px';
            notification.style.zIndex = '100000';
            notification.style.fontWeight = 'bold';
            document.body.appendChild(notification);
            
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 3000);
            
        } else if (result.action === 'show_error' || result.action === 'show_warning') {
            console.log('Показываем уведомление:', result.message);
            
            const notification = document.createElement('div');
            notification.textContent = result.message;
            notification.style.position = 'fixed';
            notification.style.top = '20px';
            notification.style.left = '50%';
            notification.style.transform = 'translateX(-50%)';
            notification.style.backgroundColor = result.action === 'show_error' ? '#f44336' : '#ff9800';
            notification.style.color = 'white';
            notification.style.padding = '15px 30px';
            notification.style.borderRadius = '4px';
            notification.style.zIndex = '100000';
            notification.style.fontWeight = 'bold';
            document.body.appendChild(notification);
            
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 5000);
        }
        
    } catch (error) {
        console.error('Ошибка отправки события:', error);
    }
};

// Вспомогательная функция для заполнения select
function fillSelectWithCertificates(selectElement, options) {
    // Очищаем существующие опции
    selectElement.innerHTML = '';
    
    // Добавляем placeholder с улучшенным стилем
    const placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = 'Выберите сертификат...';
    placeholderOption.disabled = true;
    placeholderOption.selected = true;
    placeholderOption.style.color = '#9ca3af';
    placeholderOption.style.fontStyle = 'italic';
    selectElement.appendChild(placeholderOption);
    
    // Добавляем сертификаты
    for (let [value, text] of Object.entries(options)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        option.style.padding = '10px';
        option.style.color = '#1f2937';
        selectElement.appendChild(option);
        console.log('Добавлена опция:', value, '->', text);
    }
    
    // Добавляем обработчик изменения
    selectElement.addEventListener('change', function() {
        const selectedValue = this.value;
        const selectedText = this.options[this.selectedIndex].text;
        console.log('Выбран сертификат:', selectedValue, '->', selectedText);
        
        // Визуальная обратная связь при выборе
        if (selectedValue) {
            this.style.backgroundColor = '#eff6ff';
            this.style.borderColor = '#2563eb';
            setTimeout(() => {
                this.style.backgroundColor = '#ffffff';
            }, 200);
        }
        
        // Отправляем событие о выборе сертификата
        window.nicegui_handle_event('certificate_selected', {
            value: selectedValue,
            text: selectedText
        });
    });
    
    console.log('Select заполнен сертификатами');
}

// Диагностическая функция для тестирования
window.testCryptoPro = function() {
    console.log('=== Тестирование КриптоПро ===');
    console.log('cadesplugin доступен:', typeof window.cadesplugin !== 'undefined');
    console.log('cryptoProIntegration доступен:', typeof window.cryptoProIntegration !== 'undefined');
    console.log('pluginAvailable:', window.cryptoProIntegration.pluginAvailable);
    console.log('pluginLoaded:', window.cryptoProIntegration.pluginLoaded);
    console.log('Диагностическая информация:', window.cryptoProIntegration.diagnosticInfo);
    
    if (window.cryptoProIntegration.pluginAvailable) {
        console.log('Попытка получения сертификатов...');
        window.cryptoProIntegration.getAvailableCertificates()
            .then(certs => {
                console.log('Сертификаты получены:', certs);
                if (certs.length === 0) {
                    console.log('⚠️ Сертификаты для подписи не найдены.');
                    console.log('Проверьте:');
                    console.log('1. Установлены ли сертификаты с приватным ключом');
                    console.log('2. Есть ли права доступа к приватным ключам');
                    console.log('3. Правильно ли настроен КриптоПро CSP');
                }
            })
            .catch(err => console.error('Ошибка:', err));
    }
};

window.debugCryptoPro = function() {
    console.log('=== Отладка КриптоПро ===');
    console.log('cadesplugin:', typeof window.cadesplugin);
    console.log('cryptoProIntegration:', typeof window.cryptoProIntegration);
    console.log('pluginAvailable:', window.cryptoProIntegration?.pluginAvailable);
    console.log('pluginLoaded:', window.cryptoProIntegration?.pluginLoaded);
    
    // Проверяем доступность плагина
    if (typeof window.cadesplugin !== 'undefined') {
        console.log('Плагин cadesplugin найден');
        
        // Пробуем создать объект
        try {
            window.cadesplugin.async_spawn(function*() {
                console.log('Пробуем создать объект Store...');
                const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                console.log('✅ Объект Store создан успешно');
                
                console.log('Пробуем открыть хранилище...');
                yield oStore.Open();
                console.log('✅ Хранилище открыто успешно');
                
                console.log('Пробуем получить сертификаты...');
                const certs = yield oStore.Certificates;
                const count = yield certs.Count;
                console.log(`✅ Найдено сертификатов: ${count}`);
                
                yield oStore.Close();
                console.log('✅ Хранилище закрыто');
                
                return count;
            }).then(count => {
                console.log(`Итого сертификатов: ${count}`);
            }).catch(error => {
                console.error('❌ Ошибка при тестировании:', error);
            });
        } catch (e) {
            console.error('❌ Ошибка при создании объекта:', e);
        }
    } else {
        console.log('❌ Плагин cadesplugin не найден');
    }
};

window.forcePluginAvailable = function() {
    console.log('Принудительно устанавливаем pluginAvailable = true');
    if (window.cryptoProIntegration) {
        window.cryptoProIntegration.pluginAvailable = true;
        window.cryptoProIntegration.pluginLoaded = true;
        console.log('pluginAvailable установлен в true');
    }
};