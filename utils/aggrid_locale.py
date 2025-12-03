"""
Централизованная локализация для ag-grid компонентов
"""

from nicegui import ui

# Русская локализация для ag-grid
AGGGRID_RUSSIAN_LOCALE = {
    # Пагинация - добавляем все возможные варианты ключей для "Page Size"
    # В разных версиях ag-grid могут использоваться разные ключи
    'pageSize': 'Размер страницы',
    'pageSizeSelector': 'Размер страницы',
    'paginationPageSizeSelectorLabel': 'Размер страницы',
    'paginationPageSizeSelectorLabelAriaLabel': 'Размер страницы',
    'paginationPageSizeSelector': 'Размер страницы',
    'paginationPageSize': 'Размер страницы',
    'pageSizeLabel': 'Размер страницы',
    'pageSizeLabelAriaLabel': 'Размер страницы',
    'pageSizeLabelText': 'Размер страницы',
    # Варианты с разными регистрами и форматами
    'Page Size': 'Размер страницы',
    'PageSize': 'Размер страницы',
    'page-size': 'Размер страницы',
    'page_size': 'Размер страницы',
    # Дополнительные варианты для селектора размера страницы
    'paginationPageSizeSelectorLabelText': 'Размер страницы',
    'paginationPageSizeSelectorText': 'Размер страницы',
    'paginationPageSizeLabel': 'Размер страницы',
    'paginationPageSizeLabelText': 'Размер страницы',
    'to': 'до',
    'of': 'из',
    'page': 'Страница',
    'first': 'Первая',
    'previous': 'Предыдущая',
    'next': 'Следующая',
    'last': 'Последняя',
    'paginationFirst': 'Первая',
    'paginationPrevious': 'Предыдущая',
    'paginationNext': 'Следующая',
    'paginationLast': 'Последняя',
    'paginationPage': 'Страница',
    'paginationOf': 'из',
    'paginationTo': 'до',
    'paginationRowCount': 'Строк',
    'paginationRowCountShowAll': 'Показать все',
    'paginationRowCountAll': 'Все',
    
    # Общие
    'noRowsToShow': 'Нет строк для отображения',
    'loadingOoo': 'Загрузка...',
    'filterOoo': 'Фильтр...',
    'blanks': '(Пусто)',
    
    # Фильтры
    'equals': 'Равно',
    'notEqual': 'Не равно',
    'lessThan': 'Меньше чем',
    'greaterThan': 'Больше чем',
    'lessThanOrEqual': 'Меньше или равно',
    'greaterThanOrEqual': 'Больше или равно',
    'inRange': 'В диапазоне',
    'contains': 'Содержит',
    'notContains': 'Не содержит',
    'startsWith': 'Начинается с',
    'endsWith': 'Заканчивается на',
    'andCondition': 'И',
    'orCondition': 'ИЛИ',
    'applyFilter': 'Применить фильтр',
    'resetFilter': 'Сбросить фильтр',
    'clearFilter': 'Очистить фильтр',
    'selectAll': 'Выбрать все',
    'searchOoo': 'Поиск...',
    'noMatches': 'Совпадений не найдено'
}


def apply_aggrid_pagination_localization():
    """
    Применяет JavaScript локализацию для пагинации ag-grid
    Используется как fallback, если localeText не работает для некоторых элементов
    """
    ui.run_javascript('''
        (function() {
            // Проверяем, не создан ли уже observer (чтобы избежать дублирования)
            if (window.aggridPaginationLocalized) {
                return;
            }
            window.aggridPaginationLocalized = true;
            
            function replacePageSizeText() {
                // Метод 1: Используем специфичные селекторы ag-grid для "Page Size"
                // Ищем все возможные селекторы, которые могут содержать "Page Size"
                const selectors = [
                    '.ag-paging-page-size-label',
                    '.ag-paging-page-size-selector-label',
                    '[class*="ag-paging-page-size"]',
                    '.ag-paging-panel span',
                    '.ag-paging-row-summary-panel span',
                    '.ag-paging-panel label'
                ];
                
                selectors.forEach(function(selector) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(function(el) {
                            if (el && el.textContent) {
                                const text = el.textContent.trim();
                                if (text === 'Page Size:' || text === 'Page Size' || text.includes('Page Size')) {
                                    el.textContent = el.textContent.replace(/Page Size:/gi, 'Размер страницы:');
                                    el.textContent = el.textContent.replace(/Page Size/gi, 'Размер страницы');
                                }
                            }
                        });
                    } catch (e) {
                        // Игнорируем ошибки селекторов
                    }
                });
                
                // Метод 2: Ищем по тексту во всех элементах пагинации ag-grid
                const paginationPanels = document.querySelectorAll('.ag-paging-panel, .ag-paging-row-summary-panel, .ag-paging-page-size-selector');
                paginationPanels.forEach(function(panel) {
                    if (!panel) return;
                    
                    // Ищем все текстовые узлы внутри панели пагинации
                    const walker = document.createTreeWalker(
                        panel,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: function(node) {
                                if (node.textContent && (node.textContent.includes('Page Size') || node.textContent.trim() === 'Page Size:')) {
                                    return NodeFilter.FILTER_ACCEPT;
                                }
                                return NodeFilter.FILTER_SKIP;
                            }
                        },
                        false
                    );
                    
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.textContent) {
                            const originalText = node.textContent;
                            const newText = originalText.replace(/Page Size:/gi, 'Размер страницы:').replace(/Page Size/gi, 'Размер страницы');
                            if (newText !== originalText) {
                                node.textContent = newText;
                            }
                        }
                    }
                });
            }
            
            // Выполняем замену несколько раз с задержками для надежности
            replacePageSizeText();
            setTimeout(replacePageSizeText, 100);
            setTimeout(replacePageSizeText, 300);
            setTimeout(replacePageSizeText, 600);
            setTimeout(replacePageSizeText, 1000);
            setTimeout(replacePageSizeText, 2000);
            setTimeout(replacePageSizeText, 3000);
            
            // Используем MutationObserver для отслеживания динамических изменений в ag-grid
            if (!window.aggridPaginationObserver) {
                window.aggridPaginationObserver = new MutationObserver(function(mutations) {
                    let shouldReplace = false;
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'childList' || mutation.type === 'characterData') {
                            const target = mutation.target;
                            if (target) {
                                // Проверяем, относится ли изменение к пагинации ag-grid
                                if (target.classList && (
                                    target.classList.contains('ag-paging-panel') || 
                                    target.classList.contains('ag-paging-row-summary-panel') ||
                                    target.closest('.ag-paging-panel') ||
                                    target.closest('.ag-paging-row-summary-panel')
                                )) {
                                    shouldReplace = true;
                                }
                                // Также проверяем по тексту
                                if (target.textContent && target.textContent.includes('Page Size')) {
                                    shouldReplace = true;
                                }
                            }
                        }
                    });
                    if (shouldReplace) {
                        replacePageSizeText();
                    }
                });
                
                window.aggridPaginationObserver.observe(document.body, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });
            }
        })();
    ''')

