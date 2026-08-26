# flight_planning/templatetags/planning_extras.py
import os
import pathlib
from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Получить значение из словаря по ключу"""
    if dictionary is None:
        return {}
    return dictionary.get(key, {})


@register.simple_tag
def static_version(path):
    """
    Возвращает URL статического файла с query-параметром версии (на основе mtime файла):
    /static/admin_templates/js/flight_planning.js?v=1724687220
    При изменении файла на сервере mtime автоматически обновляется,
    гарантируя загрузку свежей версии в браузерах пользователей без необходимости ручной очистки кэша.
    """
    url = static(path)
    clean_path = str(path).lstrip('/')

    full_path = None
    # 1. Проверяем STATICFILES_DIRS
    for s_dir in getattr(settings, 'STATICFILES_DIRS', []):
        p = pathlib.Path(s_dir) / clean_path
        if p.is_file():
            full_path = p
            break

    # 2. Проверяем STATIC_ROOT
    if not full_path and getattr(settings, 'STATIC_ROOT', None):
        p = pathlib.Path(settings.STATIC_ROOT) / clean_path
        if p.is_file():
            full_path = p

    # 3. Проверяем BASE_DIR / 'static' / clean_path
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

    # Fallback: глобальная версия из settings или timestamp
    app_version = getattr(settings, 'STATIC_VERSION', getattr(settings, 'APP_VERSION', '1.0'))
    return f"{url}?v={app_version}"


@register.filter
def static_version_filter(path):
    """Фильтр-обертка для static_version"""
    return static_version(path)

