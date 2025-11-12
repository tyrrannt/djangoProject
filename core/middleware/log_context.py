#  Copyright (c) 2025.
# core/middleware/log_context.py
import threading

_local = threading.local()


def set_current_user(user):
    _local.user = getattr(user, "username", "Anonymous")


def get_current_user():
    return getattr(_local, "user", "Anonymous")


class LogContextMiddleware:
    """Сохраняет имя пользователя для логов"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(request.user)
        response = self.get_response(request)
        set_current_user(None)
        return response
