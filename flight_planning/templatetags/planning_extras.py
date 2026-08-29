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


@register.filter(name='abs')
def abs_filter(val):
    """Возвращает абсолютное значение числа (модуль).

    Args:
        val: Число или строка с числом.

    Returns:
        int | float: Модуль числа или исходное значение при ошибке.
    """
    try:
        return abs(int(val))
    except (ValueError, TypeError):
        try:
            return abs(float(val))
        except (ValueError, TypeError):
            return val



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


@register.filter(name="can_view_flight_planning")
def filter_can_view_flight_planning(user) -> bool:
    """Шаблонный фильтр для проверки базовых прав доступа к разделу планирования полетов.

    Args:
        user (DataBaseUser): Объект текущего пользователя.

    Returns:
        bool: True при наличии доступа, иначе False.
    """
    try:
        from flight_planning.permissions import can_view_flight_planning
        return can_view_flight_planning(user)
    except Exception:
        return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=["Планирование полетов", "Руководство полетов", "Летный состав"]).exists()))


@register.filter(name="can_view_flight_reports")
def filter_can_view_flight_reports(user) -> bool:
    """Шаблонный фильтр для проверки прав доступа к аналитическим отчетам полетов.

    Args:
        user (DataBaseUser): Объект текущего пользователя.

    Returns:
        bool: True при наличии доступа к отчетам, иначе False.
    """
    try:
        from flight_planning.permissions import can_view_flight_reports
        return can_view_flight_reports(user)
    except Exception:
        return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=["Планирование полетов", "Руководство полетов"]).exists()))


@register.filter(name="is_flight_planner")
def filter_is_flight_planner(user) -> bool:
    """Шаблонный фильтр для проверки прав диспетчера планирования полетов.

    Args:
        user (DataBaseUser): Объект текущего пользователя.

    Returns:
        bool: True при наличии прав планировщика, иначе False.
    """
    try:
        from flight_planning.permissions import is_flight_planner
        return is_flight_planner(user)
    except Exception:
        return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name="Планирование полетов").exists()))


@register.filter(name="short_job")
def filter_short_job(job_name, mode: str = 'standard') -> str:
    """Шаблонный фильтр для компактного отображения должностей сотрудников.

    Применяет отраслевые авиационные сокращения (напр. «КВС Ми-8», «2П Ми-8»,
    «Б/М-инструктор Ми-8», «Авиатехник по экспл. ВС») для компактного вывода в таблицах и карточках.

    Args:
        job_name: Наименование должности или объект Job.
        mode (str): Режим сокращения: 'standard' (по умолчанию) или 'ultra'.

    Returns:
        str: Краткое наименование должности.
    """
    try:
        from flight_planning.services import format_short_job
        return format_short_job(job_name, mode=mode)
    except Exception:
        return str(job_name or "")


# Реэкспорт фильтра FIO_format для удобного использования во всех шаблонах планирования
try:
    from contracts_app.templatetags.custom import FIO_format
    register.filter("FIO_format", FIO_format)
except Exception:
    pass



