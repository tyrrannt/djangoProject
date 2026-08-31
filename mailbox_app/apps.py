"""Конфигурация Django-приложения mailbox_app."""

from django.apps import AppConfig


class MailboxAppConfig(AppConfig):
    """Класс конфигурации приложения корпоративной веб-почты."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "mailbox_app"
    verbose_name = "Корпоративная почта"
