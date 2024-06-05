from django import template
from django.conf import settings

register = template.Library()


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


def FIO_format(value):
    string_obj = str(value)
    list_obj = string_obj.split(" ")
    match len(list_obj):
        case 0:
            return ""
        case 1:
            return list_obj[0]
        case 2:
            return f"{list_obj[0]} {list_obj[1][:1]}."
        case 3:
            return f"{list_obj[0]} {list_obj[1][:1]}.{list_obj[2][:1]}."


@register.simple_tag()
def multiply(first, second, *args, **kwargs):
    # you would need to do any localization of the result here
    return first * second


@register.filter(name="has_group")
def has_group(user, group_name):
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
        "status":  "Статус",
        "code":  "Код",
        "data":  "Данные",
    }
    result = result_dict[key2] if key2 in result_dict else ""
    return result if result != "" else key2


@register.filter(name="change_value")
def change_value(key):
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
    result = result_dict[key] if key in result_dict else ""
    return result if result != "" else key


register.filter("has_group", has_group)
register.filter("multiply", multiply)
register.filter("FIO_format", FIO_format)
register.filter("empty_item", empty_item)
register.filter("media_folder_products", media_folder_products)
