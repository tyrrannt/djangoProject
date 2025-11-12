#  Copyright (c) 2025.
# core/loguru_setup.py
import inspect
import sys
from pathlib import Path

from loguru import logger
from django.conf import settings

from core.apps import get_app_name_from_module
from core.middleware.log_context import get_current_user


def setup_loguru():
    """Глобальная настройка loguru для всех приложений Django."""

    logger.remove()

    logs_dir = Path(settings.BASE_DIR) / "cplogs"
    logs_dir.mkdir(exist_ok=True)

    log_file = logs_dir / "django_global.log"

    def enrich_record(record):
        """Автоматически подставляет app, если не указано."""
        record["extra"]["app"] = record["extra"].get("app") or get_app_name_from_module(record["name"])
        record["extra"].setdefault("user", get_current_user() or "system")

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<cyan>{extra[app]}</cyan> | "
        "<yellow>{function}</yellow> | "
        "<magenta>{extra[user]}</magenta> | "
        "<level>{message}</level>"
    )

    # Добавляем файл логов (ротация, архивирование)
    logger.add(
        log_file,
        rotation="50 MB",  # новая ротация после 50 МБ
        retention="30 days",  # храним 30 дней
        compression="zip",  # старые логи сжимаем
        level="INFO" if not settings.DEBUG else "DEBUG",
        format=log_format,
        enqueue=True,  # безопасная запись из потоков
        backtrace=True,  # вывод traceback при исключениях
        diagnose=settings.DEBUG,  # подробности стека в debug
    )

    # В режиме DEBUG — дублируем в консоль
    if settings.DEBUG:
        logger.add(
            sys.stderr,
            level="DEBUG",
            colorize=True,
            format=log_format,
            backtrace=True,
            diagnose=True,
        )
    # Подключаем hook для автозаполнения record["extra"]["app"]
    patched_logger = logger.patch(enrich_record)
    return patched_logger
