from typing import Dict, Optional
from threading import Lock

class TokenStorage:
    def __init__(self):
        self._tokens: Dict[str, str] = {}  # client_id -> token
        self._lock = Lock()
    
    def set_token(self, client_id: str, token: str) -> None:
        with self._lock:
            self._tokens[client_id] = token
    
    def get_token(self, client_id: str) -> Optional[str]:
        with self._lock:
            return self._tokens.get(client_id)
    
    def remove_token(self, client_id: str) -> None:
        with self._lock:
            self._tokens.pop(client_id, None)
    
    def clear_expired_tokens(self) -> None:
        # Очистка истекших токенов будет реализована позже
        pass

# Глобальное хранилище токенов
token_storage = TokenStorage()

# Простое глобальное хранилище для последнего токена
last_token = None

def set_last_token(token: str) -> None:
    global last_token
    last_token = token

def get_last_token() -> Optional[str]:
    global last_token
    return last_token

def clear_last_token() -> None:
    global last_token
    last_token = None