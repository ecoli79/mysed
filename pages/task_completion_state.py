"""
Модуль для управления состоянием страницы завершения задач.

Этот модуль содержит класс TaskCompletionPageState, который инкапсулирует
все глобальные переменные состояния страницы task_completion_page.py.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Callable
from nicegui import ui

from models import CamundaTask, CamundaHistoryTask, GroupedHistoryTask


@dataclass
class TaskCompletionPageState:
    """
    Класс для управления состоянием страницы завершения задач.
    
    Инкапсулирует все глобальные переменные, которые ранее использовались
    для хранения состояния UI компонентов и данных страницы.
    """
    
    # UI контейнеры для активных задач
    tasks_container: Optional[ui.column] = None
    tasks_header_container: Optional[ui.column] = None
    
    # UI контейнеры для завершенных задач
    completed_tasks_container: Optional[ui.column] = None
    completed_tasks_header_container: Optional[ui.row] = None
    pagination_container: Optional[ui.row] = None
    
    # UI контейнеры для деталей задачи
    details_container: Optional[ui.column] = None
    
    # UI контейнеры для загрузки файлов
    uploaded_files_container: Optional[ui.column] = None
    
    # UI компоненты для табов
    tabs: Optional[ui.tabs] = None
    task_details_tab: Optional[ui.tab] = None
    active_tasks_tab: Optional[ui.tab] = None
    
    # Данные для активных задач
    active_tasks_list: List[CamundaTask] = field(default_factory=list)
    active_tasks_sort_type: str = 'start_time_desc'
    
    # Данные для завершенных задач
    all_completed_tasks: List[Union[GroupedHistoryTask, CamundaHistoryTask]] = field(default_factory=list)
    current_page: int = 1
    page_size: int = 10
    sort_type: str = 'start_time_desc'
    
    # Данные для управления задачами
    selected_task_id: Optional[str] = None
    pending_task_id: Optional[str] = None
    task_cards: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Данные для загрузки файлов
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    
    # Данные для подписания документов
    certificate_select_global: Optional[Any] = None
    selected_certificate: Optional[Dict[str, Any]] = None
    certificates_cache: List[Dict[str, Any]] = field(default_factory=list)
    document_for_signing: Optional[Dict[str, Any]] = None
    signature_result_handler: Optional[Callable] = None
    show_all_certificates: bool = False
    
    # Контейнеры для сертификатов (для поддержки нескольких задач одновременно)
    task_certificates_containers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def reset_active_tasks(self) -> None:
        """Сбрасывает состояние активных задач"""
        self.active_tasks_list.clear()
        self.task_cards.clear()
        self.selected_task_id = None
        if self.tasks_container:
            self.tasks_container.clear()
    
    def reset_completed_tasks(self) -> None:
        """Сбрасывает состояние завершенных задач"""
        self.all_completed_tasks.clear()
        self.current_page = 1
        if self.completed_tasks_container:
            self.completed_tasks_container.clear()
    
    def reset_uploaded_files(self) -> None:
        """Сбрасывает список загруженных файлов"""
        self.uploaded_files.clear()
        if self.uploaded_files_container:
            self.uploaded_files_container.clear()
    
    def reset_signing_state(self) -> None:
        """Сбрасывает состояние подписания документа"""
        self.certificates_cache.clear()
        self.selected_certificate = None
        self.document_for_signing = None
        self.show_all_certificates = False
        self.task_certificates_containers.clear()
    
    def reset_all(self) -> None:
        """Сбрасывает все состояние страницы"""
        self.reset_active_tasks()
        self.reset_completed_tasks()
        self.reset_uploaded_files()
        self.reset_signing_state()
        
        # Сбрасываем UI контейнеры
        self.tasks_container = None
        self.tasks_header_container = None
        self.completed_tasks_container = None
        self.completed_tasks_header_container = None
        self.pagination_container = None
        self.details_container = None
        self.uploaded_files_container = None
        self.tabs = None
        self.task_details_tab = None
        self.active_tasks_tab = None
        
        # Сбрасываем другие поля
        self.pending_task_id = None
        self.certificate_select_global = None
        self.signature_result_handler = None
    
    def get_task_card_info(self, task_id: str, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о карточке задачи по ID задачи или процесса.
        
        Args:
            task_id: ID задачи
            process_id: ID процесса
            
        Returns:
            Словарь с информацией о карточке или None, если не найдена
        """
        return self.task_cards.get(task_id) or self.task_cards.get(process_id)
    
    def set_task_card_info(self, task_id: str, process_id: str, card_info: Dict[str, Any]) -> None:
        """
        Сохраняет информацию о карточке задачи.
        
        Args:
            task_id: ID задачи
            process_id: ID процесса
            card_info: Словарь с информацией о карточке
        """
        # Сохраняем по обоим ключам для удобства поиска
        self.task_cards[task_id] = card_info
        if process_id and process_id != task_id:
            self.task_cards[process_id] = card_info


# Глобальный экземпляр состояния
# В будущем можно сделать это thread-local или session-specific
_state = TaskCompletionPageState()


def get_state() -> TaskCompletionPageState:
    """
    Получает глобальный экземпляр состояния страницы.
    
    Returns:
        Экземпляр TaskCompletionPageState
    """
    return _state


def reset_state() -> None:
    """Сбрасывает глобальное состояние страницы"""
    _state.reset_all()

