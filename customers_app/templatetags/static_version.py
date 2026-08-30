import os
import pathlib
from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_version(path: str) -> str:
    """Возвращает URL статического файла с query-параметром версии на основе mtime.

    При изменении файла на сервере mtime автоматически обновляется,
    гарантируя немедленную загрузку свежей версии стилей/скриптов в браузерах
    пользователей без необходимости ручной очистки кэша или истории.

    Args:
        path (str): Относительный путь к статическому файлу (напр. 'admin_templates/css/custom.css').

    Returns:
        str: URL файла с версией вида '/static/admin_templates/css/custom.css?v=1725020400'.

    Example:
        {% load static_version %}
        <link rel="stylesheet" href="{% static_version 'admin_templates/css/custom.css' %}">
    """
    url = static(path)
    clean_path = str(path).lstrip('/')

    full_path = None
    for s_dir in getattr(settings, 'STATICFILES_DIRS', []):
        p = pathlib.Path(s_dir) / clean_path
        if p.is_file():
            full_path = p
            break

    if not full_path and getattr(settings, 'STATIC_ROOT', None):
        p = pathlib.Path(settings.STATIC_ROOT) / clean_path
        if p.is_file():
            full_path = p

    if not full_path:
        p = pathlib.Path(settings.BASE_DIR) / 'static' / clean_path
        if p.is_file():
            full_path = p

    if full_path and os.path.exists(full_path):
        try:
            mtime = int(os.path.getmtime(full_path))
            return f"{url}?v={mtime}"
        except OSError:
            pass

    app_version = getattr(settings, 'STATIC_VERSION', getattr(settings, 'APP_VERSION', '1.0'))
    return f"{url}?v={app_version}"


@register.filter
def static_version_filter(path: str) -> str:
    """Фильтр-обертка для функции static_version.

    Args:
        path (str): Относительный путь к статическому файлу.

    Returns:
        str: URL файла с версией.
    """
    return static_version(path)
