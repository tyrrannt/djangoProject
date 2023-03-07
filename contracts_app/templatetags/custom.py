from django import template
from django.conf import settings

register = template.Library()


def media_folder_products(string):
    """
    Автоматически добавляет относительный URL-путь к медиафайлам продуктов
    products_images/product1.jpg --> /media/products_images/product1.jpg
    """
    if not string:
        string = ''
    return f'{settings.MEDIA_URL}{string}'


def empty_item(string):
    if not string:
        string = ''
    return string


def FIO_format(value):
    string_obj = str(value)
    list_obj = string_obj.split(' ')
    result = f'{list_obj[0]} {list_obj[1][:1]}.{list_obj[2][:1]}.'
    return result


register.filter('FIO_format', FIO_format)
register.filter('empty_item', empty_item)
register.filter('media_folder_products', media_folder_products)
