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
        case 0: return ""
        case 1: return list_obj[0]
        case 2: return f"{list_obj[0]} {list_obj[1][:1]}."
        case 3: return f"{list_obj[0]} {list_obj[1][:1]}.{list_obj[2][:1]}."


@register.simple_tag()
def multiply(first, second, *args, **kwargs):
    # you would need to do any localization of the result here
    return first * second


@register.filter(name="has_group")
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


register.filter("has_group", has_group)
register.filter("multiply", multiply)
register.filter("FIO_format", FIO_format)
register.filter("empty_item", empty_item)
register.filter("media_folder_products", media_folder_products)
