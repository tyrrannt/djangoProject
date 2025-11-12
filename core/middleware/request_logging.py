#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
# core/middleware/request_logging.py
import time
from loguru import logger
from django.utils.deprecation import MiddlewareMixin


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware для логирования всех HTTP-запросов и ответов."""

    def process_request(self, request):
        request._start_time = time.monotonic()
        return None

    def process_response(self, request, response):
        try:
            duration = time.monotonic() - getattr(request, "_start_time", time.monotonic())
            user = getattr(request, "user", None)
            username = (
                user.username
                if getattr(user, "is_authenticated", False)
                else "anonymous"
            )

            ip = (
                    request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0]
                    or request.META.get("REMOTE_ADDR", "")
            )

            method = request.method
            path = request.path
            status = response.status_code

            app_name = self._detect_app_from_path(path)

            logger.bind(app=app_name).info(
                f"{method} {path} | {status} | user={username} | ip={ip} | {duration:.3f}s"
            )

        except Exception as e:
            logger.bind(app="middleware").exception(f"Ошибка логирования запроса: {e}")

        return response

    def process_exception(self, request, exception):
        app_name = self._detect_app_from_path(request.path)
        logger.bind(app=app_name).exception(
            f"Исключение при обработке запроса {request.method} {request.path}: {exception}"
        )

    @staticmethod
    def _detect_app_from_path(path: str) -> str:
        """Грубая эвристика: определяем приложение по URL."""
        parts = [p for p in path.split("/") if p]
        if not parts:
            return "root"
        first = parts[0].lower()
        return first if len(first) < 30 else "unknown"
