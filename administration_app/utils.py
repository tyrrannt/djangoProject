import json
import os
from datetime import datetime
from urllib.parse import urljoin

import requests
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from loguru import logger
from administration_app.models import PortalProperty
from contracts_app.models import TypeContract, TypeProperty, Contract
from customers_app.models import DataBaseUser, Counteragent, Division, HistoryChange
from djangoProject import settings

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


def get_history(self, model):
    # Получаем тип объекта
    obj = ContentType.objects.get_for_model(model)
    # obj_item = self.get_object()
    # Фильтруем по объекту
    objects_content = HistoryChange.objects.filter(content_type=obj, object_id=self.object.pk).select_related('author')
    change_history = list()
    for item in objects_content:
        change_history.append([item.date_add, item.author, item.body])
    return change_history



class GetAllObject:

    @staticmethod
    def get_object():
        context = {}
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context


def transliterate(name):
    """
    Функция транслитерации строки, с русского в английский
    :param name: Заданная строка
    :return: Результат транслитерации
    """
    slovar = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
              'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
              'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h',
              'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
              'ю': 'u', 'я': 'ya', 'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'YO',
              'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
              'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H',
              'Ц': 'C', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH', 'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'E',
              'Ю': 'U', 'Я': 'YA', ',': '', '?': '', ' ': '_', '~': '', '!': '', '@': '', '#': '',
              '$': '', '%': '', '^': '', '&': '', '*': '', '(': '', ')': '', '-': '', '=': '', '+': '',
              ':': '', ';': '', '<': '', '>': '', '\'': '', '"': '', '\\': '', '/': '', '№': '',
              '[': '', ']': '', '{': '', '}': '', 'ґ': '', 'ї': '', 'є': '', 'Ґ': 'g', 'Ї': 'i',
              'Є': 'e', '—': ''}

    # Циклически заменяем все буквы в строке
    for key in slovar:
        name = name.replace(key, slovar[key])
    return name


def ChangeAccess(obj):
    # for key, value in kwargs:
    #     obj[key] = True
    print(9)


def boolean_return(request, check_string):
    is_checked = request.POST.get(check_string, False)
    if is_checked == 'on':
        return True
    return False


def int_validate(check_string):
    """
    Перевод строки в число
    :param check_string: Строка
    :return: Число, в случае если строка не число, возвращается 0
    """
    try:
        return int(check_string)
    except ValueError:
        logger.error(f'Ошибка перевода строки в число. {ValueError}')
        return 0
    except TypeError:
        logger.error(f'Ошибка перевода строки в число. {TypeError}')
        return 0


def get_jsons_data(object_type: str, object_name: str, base_index: int) -> dict:
    """
    Получение JSON объекта из таблицы 1С
    :param object_type: Тип объекта: Справочник — Catalog; Документ — Document; Журнал документов — DocumentJournal;
    Константа — Constant; План обмена — ExchangePlan; План счетов — ChartOfAccounts;
    План видов расчета — ChartOfCalculationTypes; План видов характеристик — ChartOfCharacteristicTypes;
    Регистр сведений — InformationRegister; Регистр накопления — AccumulationRegister;
    Регистр расчета — CalculationRegister; Регистр бухгалтерии — AccountingRegister;
    Бизнес-процесс — BusinessProcess; Задача — Task.
    :param object_name: Название объекта. Список можно посмотреть в конфигурации
    :param base_index: Индекс базы 1С. 0 - Зарплата, 1 - Бухгалтерия
    :return: Возвращает JSON объект, в виде словаря.
    """
    base = ['72095052-970f-11e3-84fb-00e05301b4e4', '59e20093-970f-11e3-84fb-00e05301b4e4']
    url = f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/" \
          f"{object_type}_{object_name}?$format=application/json;odata=nometadata"
    source_url = url
    try:
        response = requests.get(source_url)
    except Exception as _ex:
        logger.debug(f'{_ex}')
        return {'value': ""}
    logger.info(f'Успешное получение данных: {object_type} {object_name} {base_index}')
    return json.loads(response.text)


def get_jsons_data_filter(object_type: str, object_name: str, filter_obj: str, filter_content: str, logical: int,
                          base_index: int) -> dict:
    """
    Получение JSON объекта из таблицы 1С
    :param object_type: Тип объекта: Справочник — Catalog; Документ — Document; Журнал документов — DocumentJournal;
    Константа — Constant; План обмена — ExchangePlan; План счетов — ChartOfAccounts;
    План видов расчета — ChartOfCalculationTypes; План видов характеристик — ChartOfCharacteristicTypes;
    Регистр сведений — InformationRegister; Регистр накопления — AccumulationRegister;
    Регистр расчета — CalculationRegister; Регистр бухгалтерии — AccountingRegister;
    Бизнес-процесс — BusinessProcess; Задача — Task.
    :param object_name: Название объекта. Список можно посмотреть в конфигурации
    :param filter_obj: Ключ (поле), по которому фильтруем
    :param filter_content: Фильтр
    :param logical: 1 - Равно, 2 - Не равно, 3 - Больше, 4 - Больше или равно, 5 - Меньше, 6 - Меньше или равно,
                    7 - Логическое И, 8 - Логическое ИЛИ, 9 - Отрицание
    :param base_index: Индекс базы 1С. 0 - Зарплата, 1 - Бухгалтерия
    :return: Возвращает JSON объект, в виде словаря.
    """
    logical_operation = ['eq', 'ne', 'gt', 'ge', 'lt', 'le', 'or', 'and', 'not']
    base = ['72095052-970f-11e3-84fb-00e05301b4e4', '59e20093-970f-11e3-84fb-00e05301b4e4']
    url = f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/" \
          f"{object_type}_{object_name}?$format=application/json;odata=nometadata" \
          f"&$filter={filter_obj}%20{logical_operation[logical]}%20guid'{filter_content}'"
    source_url = url
    try:
        response = requests.get(source_url)
    except Exception as _ex:
        logger.debug(f'{_ex}')
        return {'value': ""}
    logger.info(
        f'Успешное получение данных: {object_type} {object_name} {filter_obj} {filter_content} {logical} {base_index}')
    return json.loads(response.text)


def get_jsons(url):
    source_url = url
    response = requests.get(source_url)
    return json.loads(response.text)


def change_session_get(request, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param request: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    result = request.GET.get('result', None)
    sort_item = request.GET.get('sort_item', None)
    if sort_item:
        self.request.session['sort_item'] = sort_item
    if result:
        self.request.session['portal_paginator'] = result


def change_session_context(context, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param context: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    try:
        context['portal_paginator'] = int(self.request.session['portal_paginator'])
    except Exception as _ex:
        message = f'Параметр пагинации в сессии отсутствует. {_ex}'
        logger.info(message)
        context['portal_paginator'] = self.paginate_by

    try:
        context['sort_item'] = int(self.request.session['sort_item'])
    except Exception as _ex:
        message = f'Параметр сортировки в сессии отсутствует. {_ex}'
        logger.info(message)
        context['sort_item'] = 0


def change_session_queryset(request, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param request: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    try:
        if self.request.session['portal_paginator']:
            self.paginate_by = int(self.request.session['portal_paginator'])
        else:
            self.paginate_by = PortalProperty.objects.all().first().portal_paginator
    except Exception as _ex:
        message = f'Параметр пагинации в сессии отсутствует. {_ex}'
        logger.info(message)
        self.paginate_by = PortalProperty.objects.all().first().portal_paginator

    try:
        if self.request.session['sort_item']:
            self.item_sorted = self.sorted_list[int(self.request.session['sort_item'])]
        else:
            self.item_sorted = 'pk'
    except Exception as _ex:
        message = f'Параметр сортировки в сессии отсутствует. {_ex}'
        logger.info(message)
        self.item_sorted = 'pk'


def ending_day(value):
    first_answer = [1, 21, 31, 41, ]  # День
    second_answer = [2, 3, 4, 22, 23, 24, 32, 33, 34, 42, 43, 44, ]  # Дня
    third_answer = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 25, 26, 27, 28, 29, 30, 35, 36, 37, 38,
                    39, 40, 45, 46, 47, 48, 49, 50, ]  # Дней

    if int(value) in first_answer:
        return f'{value} день'
    if int(value) in second_answer:
        return f'{value} дня'
    if int(value) in third_answer:
        return f'{value} дней'


def FIO_format(value, self=None):
    try:
        string_obj = str(value)
        list_obj = string_obj.split(' ')
        result = f'{list_obj[0]} {list_obj[1][:1]}.{list_obj[2][:1]}.'
    except Exception as _ex:
        logger.error(f'Ошибка при сокращении ФИО, Значение: {str(value)}; Документ: {self}; Ошибка: {_ex}')
        result = ''
    return result

class CkeditorCustomStorage(FileSystemStorage):
    """
    Кастомное расположение для медиа файлов редактора
    """
    def get_folder_name(self):
        return datetime.now().strftime('%Y/%m/%d')

    def get_valid_name(self, name):
        return name

    def _save(self, name, content):
        folder_name = self.get_folder_name()
        name = os.path.join(folder_name, self.get_valid_name(name))
        return super()._save(name, content)

    location = os.path.join(settings.MEDIA_ROOT, 'uploads/')
    base_url = urljoin(settings.MEDIA_URL, 'uploads/')


def change_users_password():
    pass

def get_users_info():
    users_list = DataBaseUser.objects.all()
    import csv
    with open('eggs.csv', 'w', newline='') as csvfile:
        spamwriter = csv.writer(csvfile, delimiter=';', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        for item in users_list:
            if item.email:
                spamwriter.writerow([f'{item.last_name} {item.first_name} {item.surname}', f'{item.username}', f'{item.email}'])
            else:
                spamwriter.writerow(
                    [f'{item.last_name} {item.first_name} {item.surname}', f'{item.username}', f'E-mail отсутствует'])
