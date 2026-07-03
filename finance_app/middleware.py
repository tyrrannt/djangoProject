import threading
from typing import Any, Callable
from django.http import HttpRequest, HttpResponse

_thread_locals = threading.local()

def get_current_user() -> Any:
    """
    Возвращает текущего пользователя из локального контекста потока.

    Returns:
        User или None.
    """
    return getattr(_thread_locals, "user", None)


class FinanceCurrentUserMiddleware:
    """
    Middleware для сохранения текущего пользователя в контексте потока.
    """
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """
        Инициализация middleware.

        Args:
            get_response: Функция для обработки запроса.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Сохранение пользователя в thread-local при каждом запросе.

        Args:
            request: Объект запроса.

        Returns:
            Объект ответа.
        """
        _thread_locals.user = request.user if hasattr(request, "user") and not request.user.is_anonymous else None
        try:
            response = self.get_response(request)
        finally:
            if hasattr(_thread_locals, "user"):
                del _thread_locals.user
        return response
