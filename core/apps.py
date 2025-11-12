#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
# core/apps.py
# from django.apps import AppConfig
# from django.conf import settings
#
#
# class CoreConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'core'
#
#     def ready(self):
#         # Защита от двойной инициализации в dev-режиме
#         if settings.USE_LOGURU and not getattr(self, '_loguru_setup_done', False):
#             from .loguru_setup import setup_loguru
#             setup_loguru()
#             self._loguru_setup_done = True
from django.apps import apps


def get_app_name_from_module(module_name: str) -> str:
    """Определяет Django app по имени модуля."""
    try:
        app_config = apps.get_containing_app_config(module_name)
        return app_config.label if app_config else "unknown"
    except Exception:
        return "unknown"
