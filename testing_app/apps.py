"""Конфигурация Django-приложения testing_app."""

from django.apps import AppConfig


class TestingAppConfig(AppConfig):
    """Класс конфигурации приложения системы периодического тестирования сотрудников."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "testing_app"
    verbose_name = "Тестирование сотрудников"
