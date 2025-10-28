// Обновленный cryptopro-integration.js
class CryptoProIntegration {
    constructor() {
        this.pluginAvailable = false;
        this.pluginLoaded = false;
        this.globalSelectboxContainer = []; // Используем глобальный контейнер
        this.diagnosticInfo = {};
        // this.checkPluginAvailability();
    }
    
    // async checkPluginAvailability() {
    //     // console.log('=== Начинаем диагностику КриптоПро ===');
        
    //     try {
    //         // Проверяем наличие объекта cadesplugin
    //         if (typeof window.cadesplugin === 'undefined') {
    //             console.log('❌ Объект cadesplugin не найден');
    //             this.diagnosticInfo.cadesplugin = 'not_found';
    //             this.showInstallationInstructions();
    //             return false;
    //         }
            
    //         // console.log('✅ Объект cadesplugin найден');
    //         this.diagnosticInfo.cadesplugin = 'found';
            
    //         // Проверяем поддержку браузера
    //         const browserInfo = this.checkBrowserSupport();
    //         console.log('Информация о браузере:', browserInfo);
    //         this.diagnosticInfo.browser = browserInfo;
            
    //         // if (browserInfo.isMobile) {
    //         //     console.log('❌ Мобильные устройства не поддерживаются');
    //         //     this.showMobileNotSupported();
    //         //     return false;
    //         // }
            
    //         // if (!browserInfo.isWindows) {
    //         //     console.log('❌ Только Windows поддерживается');
    //         //     this.showOSNotSupported();
    //         //     return false;
    //         // }
            
    //         // Пробуем загрузить плагин
    //         try {
    //             await window.cadesplugin;
    //             console.log('✅ Плагин загружен успешно');
    //             this.pluginAvailable = true;
    //             this.pluginLoaded = true;
                
    //             // Дополнительная проверка - пробуем создать объект
    //             try {
    //                 await window.cadesplugin.async_spawn(function*() {
    //                     const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
    //                     yield oStore.Open();
    //                     const certs = yield oStore.Certificates;
    //                     const count = yield certs.Count;
    //                     yield oStore.Close();
    //                     return count;
    //                 });
    //                 console.log('✅ Плагин полностью функционален');
    //                 return true;
    //             } catch (testError) {
    //                 console.log('⚠️ Плагин загружен, но есть проблемы:', testError);
    //                 this.pluginAvailable = true; // Все равно считаем доступным
    //                 this.pluginLoaded = true;
    //                 return true;
    //             }
                
    //         } catch (e) {
    //             console.log('❌ Ошибка загрузки плагина:', e);
    //             this.diagnosticInfo.loadError = e.message;
                
    //             // Пробуем альтернативный способ
    //             try {
    //                 await window.cadesplugin.async_spawn(function*() {
    //                     const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
    //                     return true;
    //                 });
    //                 console.log('✅ Плагин работает через альтернативный способ');
    //                 this.pluginAvailable = true;
    //                 this.pluginLoaded = true;
    //                 return true;
    //             } catch (altError) {
    //                 console.log('❌ Альтернативный способ тоже не работает:', altError);
    //                 this.showInstallationInstructions();
    //                 return false;
    //             }
    //         }
            
    //     } catch (e) {
    //         console.error('❌ Общая ошибка при проверке КриптоПро плагина:', e);
    //         this.diagnosticInfo.generalError = e.message;
    //         this.showInstallationInstructions();
    //         return false;
    //     }
    // }
    
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
        
        // if (browserInfo.isMobile) {
        //     instructions = `
        //         <div style="background: #ffebee; border: 1px solid #f44336; padding: 15px; border-radius: 5px; margin: 10px 0;">
        //             <h4>❌ Мобильные устройства не поддерживаются</h4>
        //             <p>КриптоПро ЭЦП Browser Plug-in работает только на компьютерах с Windows.</p>
        //             <p><strong>Для работы с электронной подписью необходимо:</strong></p>
        //             <ol>
        //                 <li>Использовать компьютер с операционной системой Windows</li>
        //                 <li>Установить КриптоПро CSP</li>
        //                 <li>Установить КриптоПро ЭЦП Browser Plug-in</li>
        //                 <li>Использовать Internet Explorer или Chrome с расширением</li>
        //             </ol>
        //         </div>
        //     `;
        // } 
        
        // else if (!browserInfo.isWindows) {
        //     instructions = `
        //         <div style="background: #ffebee; border: 1px solid #f44336; padding: 15px; border-radius: 5px; margin: 10px 0;">
        //             <h4>❌ Операционная система не поддерживается</h4>
        //             <p>КриптоПро ЭЦП Browser Plug-in работает только на Windows.</p>
        //             <p><strong>Для работы с электронной подписью необходимо:</strong></p>
        //             <ol>
        //                 <li>Использовать компьютер с операционной системой Windows</li>
        //                 <li>Установить КриптоПро CSP</li>
        //                 <li>Установить КриптоПро ЭЦП Browser Plug-in</li>
        //                 <li>Использовать Internet Explorer или Chrome с расширением</li>
        //             </ol>
        //         </div>
        //     `;
        // } 
        // else {
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
        
        // Принудительно устанавливаем доступность плагина
        this.pluginAvailable = true;
        this.pluginLoaded = true;
        
        try {
            console.log('Плагин доступен, начинаем получение сертификатов...');
            
            // Используем async_spawn для совместимости
            return new Promise((resolve, reject) => {
                window.cadesplugin.async_spawn(function*() {
                    try {
                        console.log('Создаем объект Store...');
                        const oStore = yield window.cadesplugin.CreateObjectAsync("CAdESCOM.Store");
                        // console.log('✅ Объект Store создан');
                        
                        console.log('Открываем хранилище сертификатов...');
                        yield oStore.Open();
                        // console.log('✅ Хранилище открыто');
                        
                        console.log('Получаем список сертификатов...');
                        const certs = yield oStore.Certificates;
                        const certCnt = yield certs.Count;
                        // console.log(`✅ Найдено сертификатов: ${certCnt}`);
                        
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
                        throw e;
                    }
                }).then(resolve).catch(reject);
            });
            
        } catch (e) {
            console.error('Ошибка при получении сертификатов:', e);
            throw e;
        }
    }
    
    async signFile(fileContent, certificateIndex = 0) {
        if (!this.pluginAvailable) {
            throw new Error('КриптоПро плагин недоступен');
        }
        
        try {
            console.log('Начинаем подписание файла...');
            
            // Конвертируем содержимое файла в base64 если это еще не сделано
            let dataToSign;
            if (typeof fileContent === 'string') {
                dataToSign = fileContent;
            } else {
                dataToSign = btoa(String.fromCharCode(...new Uint8Array(fileContent)));
            }
            
            return await this.signData(dataToSign, certificateIndex);
            
        } catch (e) {
            console.error('Ошибка при подписании файла:', e);
            throw e;
        }
    }

    // Используем готовую функцию подписания из async_code.js
    async signData(data, certificateIndex = 0) {
        if (!this.pluginAvailable) {
            throw new Error('КриптоПро плагин недоступен');
        }
        
        try {
            console.log('Начинаем подписание данных...');
            
            return new Promise((resolve, reject) => {
                cadesplugin.async_spawn(function*(args) {
                    try {
                        const [dataToSign, certIndex] = args;
                        
                        // Получаем сертификат из глобального контейнера
                        if (!window.global_selectbox_container || window.global_selectbox_container.length === 0) {
                            throw new Error('Сертификаты не загружены');
                        }
                        
                        const certificate = window.global_selectbox_container[certIndex];
                        if (!certificate) {
                            throw new Error('Сертификат не найден');
                        }
                        
                        console.log('Создаем объект подписи...');
                        const oSigner = yield cadesplugin.CreateObjectAsync("CAdESCOM.CPSigner");
                        yield oSigner.propset_Certificate(certificate);
                        
                        console.log('Создаем объект для подписи данных...');
                        const oSignedData = yield cadesplugin.CreateObjectAsync("CAdESCOM.CadesSignedData");
                        yield oSignedData.propset_ContentEncoding(cadesplugin.CADESCOM_BASE64_TO_BINARY);
                        yield oSignedData.propset_Content(dataToSign);
                        
                        console.log('Выполняем подпись...');
                        const signature = yield oSignedData.SignCades(oSigner, cadesplugin.CADESCOM_CADES_BES, false);
                        
                        // Получаем информацию о сертификате
                        const certificateInfo = {
                            subject: yield certificate.SubjectName,
                            issuer: yield certificate.IssuerName,
                            serialNumber: yield certificate.SerialNumber,
                            validFrom: yield certificate.ValidFromDate,
                            validTo: yield certificate.ValidToDate
                        };
                        
                        console.log('Подписание завершено успешно');
                        return {
                            signature: signature,
                            certificateInfo: certificateInfo
                        };
                        
                    } catch (e) {
                        const errorMessage = "Не удалось создать подпись из-за ошибки: " + cadesplugin.getLastError(e);
                        console.error('Ошибка при подписании данных:', errorMessage);
                        throw new Error(errorMessage);
                    }
                }, [data, certificateIndex]).then(resolve).catch(reject);
            });
            
        } catch (e) {
            console.error('Ошибка при подписании данных:', e);
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
        if (result.action === 'update_select' && result.options) {
            console.log('Создаем select в области сертификатов...');
            
            // Ищем область для сертификатов
            const certArea = document.getElementById('certificates-area');
            if (!certArea) {
                console.log('Область сертификатов не найдена, создаем фиксированный контейнер');
                
                // Создаем фиксированный контейнер
                const container = document.createElement('div');
                container.id = 'certificates-container';
                container.style.position = 'fixed';
                container.style.top = '20px';
                container.style.right = '20px';
                container.style.width = '500px';
                container.style.maxWidth = '90vw';
                container.style.backgroundColor = 'white';
                container.style.border = '3px solid #4CAF50';
                container.style.borderRadius = '8px';
                container.style.padding = '20px';
                container.style.zIndex = '99999';
                container.style.boxShadow = '0 8px 16px rgba(0, 0, 0, 0.2)';
                container.style.fontFamily = 'Arial, sans-serif';
                
                // Заголовок
                const title = document.createElement('div');
                title.textContent = '🔐 Выберите сертификат для подписания:';
                title.style.fontWeight = 'bold';
                title.style.fontSize = '16px';
                title.style.marginBottom = '10px';
                title.style.color = '#4CAF50';
                title.style.borderBottom = '2px solid #4CAF50';
                title.style.paddingBottom = '8px';
                
                // Select элемент
                const tempSelect = document.createElement('select');
                tempSelect.id = 'temp-certificates-select';
                tempSelect.style.width = '100%';
                tempSelect.style.padding = '12px';
                tempSelect.style.margin = '10px 0';
                tempSelect.style.border = '2px solid #ddd';
                tempSelect.style.borderRadius = '6px';
                tempSelect.style.backgroundColor = 'white';
                tempSelect.style.fontSize = '14px';
                tempSelect.style.cursor = 'pointer';
                
                // Кнопка закрытия
                const closeButton = document.createElement('button');
                closeButton.textContent = '✕';
                closeButton.style.position = 'absolute';
                closeButton.style.top = '8px';
                closeButton.style.right = '8px';
                closeButton.style.border = 'none';
                closeButton.style.background = 'transparent';
                closeButton.style.fontSize = '18px';
                closeButton.style.cursor = 'pointer';
                closeButton.style.color = '#666';
                closeButton.style.width = '30px';
                closeButton.style.height = '30px';
                closeButton.style.borderRadius = '50%';
                closeButton.style.display = 'flex';
                closeButton.style.alignItems = 'center';
                closeButton.style.justifyContent = 'center';
                closeButton.onmouseover = function() {
                    this.style.backgroundColor = '#f0f0f0';
                };
                closeButton.onmouseout = function() {
                    this.style.backgroundColor = 'transparent';
                };
                closeButton.onclick = function() {
                    container.remove();
                };
                
                // Добавляем элементы в контейнер
                container.appendChild(closeButton);
                container.appendChild(title);
                container.appendChild(tempSelect);
                
                // Добавляем контейнер в body
                document.body.appendChild(container);
                
                // Заполняем select
                fillSelectWithCertificates(tempSelect, result.options);
                
            } else {
                // Создаем select в области сертификатов
                const tempSelect = document.createElement('select');
                tempSelect.id = 'temp-certificates-select';
                tempSelect.style.width = '100%';
                tempSelect.style.padding = '8px';
                tempSelect.style.margin = '10px 0';
                tempSelect.style.border = '2px solid #4CAF50';
                tempSelect.style.borderRadius = '4px';
                tempSelect.style.backgroundColor = 'white';
                tempSelect.style.fontSize = '14px';
                
                // Добавляем заголовок
                const title = document.createElement('div');
                title.textContent = 'Доступные сертификаты:';
                title.style.fontWeight = 'bold';
                title.style.marginBottom = '5px';
                title.style.color = '#4CAF50';
                
                certArea.appendChild(title);
                certArea.appendChild(tempSelect);
                
                // Заполняем select
                fillSelectWithCertificates(tempSelect, result.options);
            }
            
        } else if (result.action === 'certificate_selected') {
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
    
    // Добавляем placeholder
    const placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = 'Выберите сертификат...';
    placeholderOption.disabled = true;
    placeholderOption.selected = true;
    selectElement.appendChild(placeholderOption);
    
    // Добавляем сертификаты
    for (let [value, text] of Object.entries(options)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        selectElement.appendChild(option);
        console.log('Добавлена опция:', value, '->', text);
    }
    
    // Добавляем обработчик изменения
    selectElement.addEventListener('change', function() {
        const selectedValue = this.value;
        const selectedText = this.options[this.selectedIndex].text;
        console.log('Выбран сертификат:', selectedValue, '->', selectedText);
        
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