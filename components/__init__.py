"""UI компоненты для приложения"""

from .loading_indicator import LoadingIndicator, with_loading
from .document_viewer import show_document_viewer

__all__ = [
    'LoadingIndicator',
    'with_loading',
    'show_document_viewer',
]
