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
    ВАЖНО: Изменяет только текстовые узлы, не трогая интерактивные элементы (селекторы, кнопки и т.д.)
    """
    ui.run_javascript('''
        (function() {
            // Проверяем, не создан ли уже observer (чтобы избежать дублирования)
            if (window.aggridPaginationLocalized) {
                return;
            }
            window.aggridPaginationLocalized = true;
            
            function replacePageSizeText() {
                // Ищем только текстовые узлы в панели пагинации, которые содержат "Page Size"
                // НЕ трогаем элементы, которые содержат дочерние элементы (селекторы, кнопки и т.д.)
                const paginationPanels = document.querySelectorAll('.ag-paging-panel, .ag-paging-row-summary-panel');
                paginationPanels.forEach(function(panel) {
                    if (!panel) return;
                    
                    // Используем TreeWalker для поиска ТОЛЬКО текстовых узлов
                    const walker = document.createTreeWalker(
                        panel,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: function(node) {
                                // Проверяем, что это текстовый узел и содержит "Page Size"
                                if (node && node.nodeType === Node.TEXT_NODE) {
                                    const text = node.textContent.trim();
                                    // Проверяем, что родительский элемент не является интерактивным (select, button, input)
                                    const parent = node.parentElement;
                                    if (parent) {
                                        const tagName = parent.tagName.toLowerCase();
                                        // Пропускаем интерактивные элементы
                                        if (tagName === 'select' || tagName === 'button' || tagName === 'input' || tagName === 'option') {
                                            return NodeFilter.FILTER_REJECT;
                                        }
                                        // Проверяем, что родитель не содержит интерактивных элементов
                                        if (parent.querySelector('select, button, input')) {
                                            return NodeFilter.FILTER_REJECT;
                                        }
                                    }
                                    // Принимаем только узлы с текстом "Page Size"
                                    if (text === 'Page Size:' || text === 'Page Size' || (text.includes('Page Size') && text.length < 50)) {
                                        return NodeFilter.FILTER_ACCEPT;
                                    }
                                }
                                return NodeFilter.FILTER_SKIP;
                            }
                        },
                        false
                    );
                    
                    let node;
                    while (node = walker.nextNode()) {
                        if (node && node.nodeType === Node.TEXT_NODE && node.textContent) {
                            const originalText = node.textContent;
                            // Заменяем только текст "Page Size", не трогая остальное
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
            
            // Используем MutationObserver для отслеживания динамических изменений в ag-grid
            if (!window.aggridPaginationObserver) {
                window.aggridPaginationObserver = new MutationObserver(function(mutations) {
                    let shouldReplace = false;
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'childList' || mutation.type === 'characterData') {
                            const target = mutation.target;
                            if (target) {
                                // Проверяем, относится ли изменение к пагинации ag-grid
                                // НО только если это не интерактивный элемент
                                const isInteractive = target.tagName && ['SELECT', 'BUTTON', 'INPUT', 'OPTION'].includes(target.tagName);
                                const isInPagination = target.classList && (
                                    target.classList.contains('ag-paging-panel') || 
                                    target.classList.contains('ag-paging-row-summary-panel') ||
                                    target.closest('.ag-paging-panel') ||
                                    target.closest('.ag-paging-row-summary-panel')
                                );
                                
                                if (isInPagination && !isInteractive) {
                                    // Проверяем, что изменение не в селекторе
                                    if (!target.closest('select') && !target.closest('.ag-paging-page-size-selector select')) {
                                        shouldReplace = true;
                                    }
                                }
                            }
                        }
                    });
                    if (shouldReplace) {
                        // Небольшая задержка, чтобы ag-grid успел отрендерить элементы
                        setTimeout(replacePageSizeText, 50);
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

