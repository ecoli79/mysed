"""
Переиспользуемый компонент для отображения индикатора загрузки
"""
from nicegui import ui
from typing import Optional, Callable, Any
from contextlib import contextmanager
import functools
import asyncio
from typing import TypeVar, ParamSpec

P = ParamSpec('P')
R = TypeVar('R')

class LoadingIndicator:
    """
    Класс для управления индикатором загрузки (progress bar)
    
    Пример использования:
        loading = LoadingIndicator(container)
        with loading:
            # Ваш код с долгими операциями
            search_documents(query)
    """
    
    def __init__(self, container: ui.column, message: str = 'Загрузка...'):
        """
        Инициализирует индикатор загрузки
        
        Args:
            container: Контейнер, в котором будет отображаться индикатор
            message: Сообщение, отображаемое рядом с индикатором
        """
        self.container = container
        self.message = message
        self.spinner_widget: Optional[ui.spinner] = None
        self.message_widget: Optional[ui.label] = None
        self.row_widget: Optional[ui.row] = None
        self.is_visible = False
    
    def show(self) -> None:
        """Показывает индикатор загрузки"""
        if self.is_visible:
            return
        
        with self.container:
            self.row_widget = ui.row().classes('w-full items-center gap-4 p-4')
            with self.row_widget:
                # Используем spinner для индикации загрузки (более подходящий вариант)
                self.spinner_widget = ui.spinner(type='bars', size='lg')
                self.message_widget = ui.label(self.message).classes('text-sm text-gray-600 whitespace-nowrap')
        
        self.is_visible = True
    
    def hide(self) -> None:
        """Скрывает индикатор загрузки"""
        if not self.is_visible:
            return
        
        # Удаляем всю строку (row) с индикатором
        if self.row_widget:
            self.row_widget.delete()
            self.row_widget = None
        
        self.spinner_widget = None
        self.message_widget = None
        self.is_visible = False
    
    def update_message(self, message: str) -> None:
        """Обновляет сообщение индикатора"""
        self.message = message
        if self.message_widget:
            self.message_widget.text = message
    
    @contextmanager
    def __enter__(self):
        """Контекстный менеджер для автоматического показа/скрытия"""
        self.show()
        try:
            yield self
        finally:
            self.hide()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Завершение контекстного менеджера"""
        self.hide()
        return False


def with_loading(container: ui.column, message: str = 'Загрузка...'):
    """
    Декоратор для автоматического показа индикатора загрузки во время выполнения функции
    
    Args:
        container: Контейнер, в котором будет отображаться индикатор
        message: Сообщение для индикатора
    
    Пример использования:
        @with_loading(container, 'Поиск документов...')
        def search_documents(query):
            # Ваш код поиска
            pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            loading = LoadingIndicator(container, message)
            with loading:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def with_loading_async(container: ui.column, message: str = 'Загрузка...'):
    """
    Декоратор для асинхронных функций с индикатором загрузки
    
    Args:
        container: Контейнер, в котором будет отображаться индикатор
        message: Сообщение для индикатора
    """
    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            loading = LoadingIndicator(container, message)
            loading.show()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                loading.hide()
        return wrapper
    return decorator
