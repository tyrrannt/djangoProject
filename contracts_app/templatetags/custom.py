import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

from django import template
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Получить значение из словаря по ключу"""
    if dictionary is None:
        return {}
    return dictionary.get(key, {})


@register.simple_tag
def get_file_icon(file_extension):
    file_icons = {
        'pdf': 'far fa-file-pdf',
        'doc': 'far fa-file-word',
        'docx': 'far fa-file-word',
        'xls': 'far fa-file-excel',
        'xlsx': 'far fa-file-excel',
        'jpg': 'far fa-file-image',
        'jpeg': 'far fa-file-image',
        'png': 'far fa-file-image',
        'txt': 'far fa-file-alt',
        'zip': 'far fa-file-archive',
        'rar': 'far fa-file-archive',
        'mp3': 'far fa-file-audio',
        'mp4': 'far fa-file-video',
        'ppt': 'far fa-file-powerpoint',
        'pptx': 'far fa-file-powerpoint',
        'default': 'far fa-file'
    }
    return file_icons.get(file_extension, file_icons['default'])


@register.filter
def split(value, delimiter):
    """Разделяет строку по разделителю и возвращает список."""
    return value.split(delimiter)


@register.filter
def basename(value):
    """Возвращает имя файла из полного пути."""
    return os.path.basename(value)


@register.filter
def url_encode(value):
    return quote(value)


@register.filter
def content_type_id(obj):
    return ContentType.objects.get_for_model(obj).id


def media_folder_products(string):
    """
    Автоматически добавляет относительный URL-путь к медиафайлам продуктов
    products_images/product1.jpg --> /media/products_images/product1.jpg
    """
    if not string:
        string = ""
    return f"{settings.MEDIA_URL}{string}"


def empty_item(string):
    """
    :param string: Входная строка, которую нужно проверить на пустоту.
    :return: Возвращает входную строку, если она не пуста, иначе возвращает пустую строку ('').
    """
    return string or ""


@register.filter
def FIO_format(value: Any, reverse: bool = False) -> str:
    """
    Форматирует ФИО в виде:
      - Обычный: "Фамилия И.О."
      - Reverse:  "И.О. Фамилия"

    Поддерживает 1–3 части имени. Лишние части игнорируются.
    Пустые строки, None и некорректные значения обрабатываются корректно.
    """
    if not value:
        return ""

    # Приводим к строке и разбиваем по пробелам, удаляя пустые
    parts = str(value).strip().split()
    parts = [part for part in parts if part]

    if not parts:
        return ""

    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    else:  # len >= 3
        last_name, first_name, patronymic = parts[0], parts[1], parts[2]
        formatted = f"{first_name[0]}.{patronymic[0]}." if not reverse else f"{last_name}"
        if reverse:
            return f"{first_name[0]}.{patronymic[0]}. {last_name}"
        else:
            return f"{last_name} {first_name[0]}.{patronymic[0]}."


@register.simple_tag()
def multiply(first, second, *args, **kwargs):
    """Возвращает произведение двух чисел в виде кастомного шаблонного фильтра Django.

    Кастомный фильтр для использования в шаблонах Django. Принимает два аргумента —
    первый и второй множители — и возвращает их произведение. Может использоваться
    в HTML-шаблонах для выполнения простых арифметических операций без предварительного
    вычисления значений в представлении (view).

    Поддерживает передачу дополнительных позиционных (*args) и именованных (**kwargs)
    аргументов для возможного расширения функциональности (например, локализация,
    форматирование результата), хотя в текущей реализации они не используются.

    Внимание: фильтр не выполняет проверку типов. Если переданные значения не поддерживают
    операцию умножения, будет выброшено исключение во время рендеринга шаблона.

    Args:
        first (int | float): Первый множитель. Ожидается числовое значение.
        second (int | float): Второй множитель. Ожидается числовое значение.
        *args: Дополнительные позиционные аргументы (не используются).
        **kwargs: Дополнительные именованные аргументы (не используются).

    Returns:
        int | float: Результат умножения `first` на `second`. Тип зависит от входных данных
        (например, умножение целых даст int, смешанные типы могут привести к float).

    Raises:
        TypeError: Может быть выброшено, если `first` или `second` не являются
                   типами, поддерживающими операцию умножения (например, str, None).

    Example:
        В шаблоне Django:
        {% load custom %}
        {{ 5|multiply:3 }}  <!-- выведет 15 -->

        Также можно использовать с переменными:
        {{ value|multiply:2 }}

    Note:
        Убедитесь, что в шаблоне загружены кастомные теги:
        {% load custom %}
    """
    return first * second


@register.filter(name="has_group")
def has_group(user, group_name):
    """Проверяет, состоит ли пользователь в группе Django с указанным именем.

    Кастомный шаблонный фильтр для Django, используемый в HTML-шаблонах
    для управления отображением элементов интерфейса на основе принадлежности
    пользователя к определённой группе (например, 'Managers', 'Editors' и т.д.).

    Фильтр работает через связь Many-to-Many между моделью User и Group
    (auth.Group). Выполняет запрос к базе данных: проверяет существование
    связи пользователя с группой, имеющей заданное имя. Используется метод
    `.exists()`, который эффективен по производительности, так как возвращает
    булево значение и останавливает выполнение запроса при первом совпадении.

    Пример использования в шаблоне:
        {% if request.user|has_group:"Managers" %}
            <a href="/admin/">Админ-панель</a>
        {% endif %}

    Args:
        user (django.contrib.auth.models.User): Объект пользователя,
            полученный, например, из `request.user`. Должен быть экземпляром
            модели User из Django auth.
        group_name (str): Название группы (соответствует полю `name` в таблице `auth_group`).

    Returns:
        bool: True, если пользователь состоит в группе с указанным именем;
              False в противном случае.

    Raises:
        Никакие исключения не выбрасываются. Если пользователь анонимный
        (AnonymousUser), метод `.groups.filter(...)` вернёт пустой QuerySet,
        и результат будет False — поведение безопасно.

    Note:
        Убедитесь, что в шаблоне загружены кастомные теги:
        {% load custom %}
    """
    return user.groups.filter(name=group_name).exists()


@register.filter(name="change_key")
def change_key(key2):
    result_dict = {
        "value": "Наименование компании",
        "inn": "ИНН",
        "kpp": "КПП",
        "ogrn": "ОГРН",
        "ogrn_date": "Дата выдачи ОГРН",
        "hid": "Внутренний идентификатор",
        "type": "Тип организации",
        "name": "Наименование",
        "full_with_opf": "полное наименование",
        "short_with_opf": "краткое наименование",
        "okato": "Код ОКАТО",
        "oktmo": "Код ОКМО",
        "okpo": "Код ОКПО",
        "okogu": "Код ОКОГУ",
        "okfs": "Код ОКФС",
        "okved": "Код ОКВЭД",
        "okved_type": "Версия справочника ОКВЭД (2001 или 2014)",
        "opf": "Организационно-правовая форма",
        "management": "Руководитель",
        "name": "ФИО руководителя",
        "post": "должность руководителя",
        "branch_count": "Количество филиалов",
        "branch_type": "Тип подразделения",
        "address": "Адрес",
        "source": "адрес одной строкой как в ЕГРЮЛ",
        "qc": "код проверки адреса",
        "state": "Состояние",
        "actuality_date": "дата последних изменений",
        "registration_date": "дата регистрации",
        "liquidation_date": "дата ликвидации",
        "unrestricted_value": "Наименование",
        "postal_code": "Почтовый индекс",
        "country": "Страна",
        "country_iso_code": "Код страны",
        "federal_district": "Округ",
        "city": "Город",
        "city_type": "Наименование",
        "city_type_full": "Полное наименование",
        "full": "Полное наименование",
        "short": "Краткое наименование",
        "geo_lat": "Географическая привязка",
        "geo_lon": "Географическая привязка",
        "house": "Дом",
        "street": "Улица",
        "street_type": "Тип",
        "street_type_full": "Полное наименование",
        "floor": "Этаж",
        "metro": "Метро",
        "finance": "Налоговый режим",
        "phones": "Телефон",
        "emails": "Электронная почта",
        "timezone": "Часовой пояс",
        "tax_office": "Код налогового органа",
        "region": "Регион",
        "region_type": "Тип региона",
        "region_type_full": "Полное наименование региона",
        "status": "Статус",
        "code": "Код",
        "data": "Данные",
        "fio": "ФИО",
        "surname": "Фамилия",
        "patronymic": "Отчество",
    }
    result = result_dict[key2] if key2 in result_dict else ""
    return result if result != "" else key2


@register.filter(name="change_value")
def change_value(key, value):
    result_dict = {
        "LEGAL": "юридическое лицо",
        "INDIVIDUAL": "индивидуальный предприниматель",
        "MAIN": "головная организация",
        "BRANCH": "филиал",
        "ACTIVE": "действующая",
        "LIQUIDATING": "ликвидируется",
        "LIQUIDATED": "ликвидирована",
        "BANKRUPT": "банкротство",
        "REORGANIZING": "в процессе присоединения к другому юрлицу, с последующей ликвидацией",
    }
    try:
        result = result_dict[value]
        return result
    except TypeError:
        result = value
    except KeyError:
        result = value
    if key in ["actuality_date", "registration_date", "liquidation_date", "issue_date", "valid_from",
               "valid_to", "ogrn_date", ]:
        ts = int(value) / 1000
        print(ts)
        result = datetime.fromtimestamp(ts).strftime('%d.%m.%Y %H:%M:%S')
    return result


@register.filter(name="format_bytes")
def format_bytes(size):
    # 2**10 = 1024
    power = 2 ** 10
    n = 0
    power_labels = {0: '', 1: 'К', 2: 'M', 3: 'Г', 4: 'Т'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}б"


@register.filter(name="filename")
def filename(value):
    try:
        return os.path.basename(value.file.name)
    except FileNotFoundError:
        return 'Файл отсутствует'


@register.filter
def get_key(dictionary, key):
    return dictionary.get(key, 0)


@register.filter
def get_url(obj, url_name):
    """
    Универсальный фильтр для получения URL по имени маршрута.
    """
    if hasattr(obj, 'pk') and obj.pk:
        try:
            return reverse(url_name, args=[obj.pk])
        except:
            pass
    return '#'


@register.filter
def index(list_, index):
    """Возвращает элемент списка по индексу."""
    try:
        return list_[index]
    except (IndexError, TypeError):
        return ""


@register.filter
def div(value, arg):
    """Делит value на arg с обработкой нуля"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0


@register.filter(name='get_trip_type_display')
def get_trip_type_display(value):
    trip_types = {
        '1': 'Служебная поездка',
        '2': 'Командировка'
    }
    return trip_types.get(value, 'Неизвестный тип')


register.filter("has_group", has_group)
register.filter("multiply", multiply)
register.filter("empty_item", empty_item)
register.filter("media_folder_products", media_folder_products)
