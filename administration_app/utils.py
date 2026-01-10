import imaplib
import json
import os
import pathlib
import smtplib
import time
from datetime import datetime, timedelta
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from urllib.parse import urljoin

import pandas as pd
import requests
from dateutil import rrule, relativedelta
from decouple import config
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser, HistoryChange, DataBaseUserWorkProfile
from djangoProject import settings
from djangoProject.settings import BASE_DIR, EMAIL_HOST, EMAIL_IMAP_HOST, EMAIL_IAS_USER, \
    EMAIL_IAS_PASSWORD, EMAIL_FLY_USER, EMAIL_FLY_PASSWORD, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD

from core import logger


def time_it(func):
    """
       Декоратор для измерения времени выполнения функции.

       :param func: Функция, время выполнения которой нужно измерить.
       :return: Функция-обёртка, которая возвращает результат исходной функции и печатает время ее выполнения.

       Примечание:
           Декоратор должен быть применен к функции перед вызовом последней.
       """

    def wrapper(*args, **kwargs):
        start = time.time()
        res = func(*args, **kwargs)
        end = time.time()
        print(f'Время выполнения {func.__name__}: {end - start:.4f} сек.')
        return res

    return wrapper


def get_history(self, model):
    """
        Возвращает историю изменений для объекта модели.

        :param self: Объект класса (не используется напрямую)
        :param model: Модель, для которой нужно получить историю изменений.
        :return: Список списков с информацией о каждом изменении:
            - Дата изменения
            - Автор изменения
            - Тело изменения

        Примечание:
            Функция использует модели Django ContentType и HistoryChange для получения истории изменений.
        """
    # Получаем тип объекта
    obj = ContentType.objects.get_for_model(model)
    # obj_item = self.get_object()
    # Фильтруем по объекту
    objects_content = HistoryChange.objects.filter(
        content_type=obj, object_id=self.object.pk
    ).select_related("author")
    change_history = list()
    for item in objects_content:
        change_history.append([item.date_add, item.author, item.body])
    return change_history


# class GetAllObject:
#
#     @staticmethod
#     def get_object():
#         context = {}
#         all_users = DataBaseUser.objects.all()
#         # all_type_of_contract = TypeContract.objects.all()
#         # all_type_property = TypeProperty.objects.all()
#         all_counteragent = Counteragent.objects.all()
#         # all_prolongation = Contract.type_of_prolongation
#         all_divisions = Division.objects.all()
#         context['employee'] = all_users
#         # context['type_property'] = all_type_property
#         context['counteragent'] = all_counteragent
#         # context['prolongation'] = all_prolongation
#         context['division'] = all_divisions
#         # context['type_contract'] = all_type_of_contract
#         return context


def transliterate(name):
    """
    Функция транслитерации строки, с русского в английский
    :param name: Заданная строка
    :return: Результат транслитерации
    """
    slovar = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "u",
        "я": "ya",
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Е": "E",
        "Ё": "YO",
        "Ж": "ZH",
        "З": "Z",
        "И": "I",
        "Й": "I",
        "К": "K",
        "Л": "L",
        "М": "M",
        "Н": "N",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "У": "U",
        "Ф": "F",
        "Х": "H",
        "Ц": "C",
        "Ч": "CH",
        "Ш": "SH",
        "Щ": "SCH",
        "Ъ": "",
        "Ы": "y",
        "Ь": "",
        "Э": "E",
        "Ю": "U",
        "Я": "YA",
        ",": "",
        "?": "",
        " ": "_",
        "~": "",
        "!": "",
        "@": "",
        "#": "",
        "$": "",
        "%": "",
        "^": "",
        "&": "",
        "*": "",
        "(": "",
        ")": "",
        "-": "",
        "=": "",
        "+": "",
        ":": "",
        ";": "",
        "<": "",
        ">": "",
        "'": "",
        '"': "",
        "\\": "",
        "/": "",
        "№": "",
        "[": "",
        "]": "",
        "{": "",
        "}": "",
        "ґ": "",
        "ї": "",
        "є": "",
        "Ґ": "g",
        "Ї": "i",
        "Є": "e",
        "—": "",
    }

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
    if is_checked == "on":
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
        logger.error(f"Ошибка перевода строки в число. {ValueError}")
        return 0
    except TypeError:
        logger.error(f"Ошибка перевода строки в число. {TypeError}")
        return 0


def get_jsons_data(object_type: str, object_name: str, base_index: int, year=0) -> dict:
    """
    Получение JSON объекта из таблицы 1С
    :param year:
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
    "http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/Catalog_Сотрудники?$format=application/json;odata=nometadata"
    "http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/Document_НаправлениеНаМедицинскийОсмотр?$filter=year(ДатаОсмотра) gt 2024&$format=json"
    base = [
        "72095052-970f-11e3-84fb-00e05301b4e4",
        "59e20093-970f-11e3-84fb-00e05301b4e4",
    ]
    if year == 0:
        url = (
            f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/"
            f"{object_type}_{object_name}?$format=application/json;odata=nometadata"
        )
    else:
        url = (
            f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/"
            f"{object_type}_{object_name}?$filter=year(Date) gt 2024&$format=application/json;odata=nometadata"
        )
    source_url = url
    try:
        if base_index == 0:
            response = requests.get(
                source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
            )
        else:
            response = requests.get(
                source_url, auth=(config("ACC_LOGIN"), config("ACC_PASS"))
            )
    except Exception as _ex:
        logger.debug(f"{_ex}")
        print(_ex)
        return {"value": ""}
    return json.loads(response.text)


def get_jsons_data_filter(
        object_type: str,
        object_name: str,
        filter_obj: str,
        filter_content: str,
        logical: int,
        base_index: int,
        guid=True,
        separator=True,
) -> dict:
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
    :param logical: 0 - Равно, 1 - Не равно, 2 - Больше, 3 - Больше или равно, 4 - Меньше, 5 - Меньше или равно,
                    6 - Логическое И, 7 - Логическое ИЛИ, 8 - Отрицание
    :param base_index: Индекс базы 1С. 0 - Зарплата, 1 - Бухгалтерия
    :return: Возвращает JSON объект, в виде словаря.
    """
    guid_attribute = "guid" if guid else ""
    separator_attribute = "'" if separator else ""
    logical_operation = ["eq", "ne", "gt", "ge", "lt", "le", "or", "and", "not"]
    base = [
        "72095052-970f-11e3-84fb-00e05301b4e4",
        "59e20093-970f-11e3-84fb-00e05301b4e4",
    ]
    url = (
        f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/"
        f"{object_type}_{object_name}?$format=application/json;odata=nometadata"
        f"&$filter={filter_obj}%20{logical_operation[logical]}%20{guid_attribute}{separator_attribute}{filter_content}{separator_attribute}"
    )
    print(url)
    source_url = url
    try:
        if base_index == 0:
            response = requests.get(
                source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
            )
        else:
            response = requests.get(
                source_url, auth=(config("ACC_LOGIN"), config("ACC_PASS"))
            )
    except Exception as _ex:
        logger.debug(f"{_ex}")
        return {"value": ""}
    return json.loads(response.text)


def get_active_user(ref_key):
    # ur1 = (f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=Сотрудник_Key%20eq%20guid%2765f4800d-970f-11e3-84fb-00e05301b4e4%27%20and%20Состояние%20eq%20%27Увольнение%27")
    url = (
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=Сотрудник_Key%20eq%20guid%27{ref_key}%27%20and%20Состояние%20eq%20%27Увольнение%27")
    response = requests.get(
        url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
    )
    dicts = json.loads(response.text)
    if dicts['value'] == []:
        return True
    else:
        if dicts['value'][0]['Active'] == True:
            return False


def get_json_vacation(ref_key):
    exclude_vacation = {
        "dd940e62-cfaf-11e6-bad8-902b345cadc2": "Отпуск за свой счет",
        "b51bdb10-8fb9-11e9-80cc-309c23d346b4": "Дополнительный оплачиваемый отпуск пострадавшим на ЧАЭС",
        "c3e8c3e8-cfb6-11e6-bad8-902b345cadc2": "Дополнительный неоплачиваемый отпуск пострадавшим на ЧАЭС",
        "c3e8c3e7-cfb6-11e6-bad8-902b345cadc2": "Дополнительный учебный отпуск (оплачиваемый)",
        "dd940e63-cfaf-11e6-bad8-902b345cadc2": "Дополнительный учебный отпуск без оплаты",
        "6f4631a7-df12-11e6-950a-0cc47a7917f4": "Дополнительный отпуск КЛО, ЗКЛО, начальник ИБП",
        "56f643c6-bf49-11e9-a3dc-0cc47a7917f4": "Дополнительный оплачиваемый отпуск пострадавшим в аварии на ЧАЭС",
        "dd940e60-cfaf-11e6-bad8-902b345cadc2": "Дополнительный ежегодный отпуск",
        "ebbd9c67-cfaf-11e6-bad8-902b345cadc2": "Основной",
    }
    url_date_admission = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ТекущиеКадровыеДанныеСотрудников?$format=application/json;odata=nometadata&$filter=Сотрудник_Key%20eq%20guid%27{ref_key}%27"
    url_vacation = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ФактическиеОтпуска_RecordType?$format=application/json;odata=nometadata&$filter=Сотрудник_Key%20eq%20guid%27{ref_key}%27"
    url_children = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ПериодыОтпусков_RecordType?$format=application/json;odata=nometadata&$filter=Сотрудник_Key%20eq%20guid%27{ref_key}%27"
    date_admission = datetime(1, 1, 1, 0, 0)
    children_days = 0
    try:
        response_date_admission = requests.get(
            url_date_admission, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
        response_vacation = requests.get(
            url_vacation, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
        response_children = requests.get(
            url_children, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
        json_date_admission = json.loads(response_date_admission.text)
        json_children = json.loads(response_children.text)
        json_vacation = json.loads(response_vacation.text)
        for item in json_date_admission["value"]:
            date_admission = datetime.strptime(item["ДатаПриема"][:10], "%Y-%m-%d")
        for item in json_children["value"]:
            if item["Состояние"] == "ОтпускПоУходуЗаРебенком":
                children_days += int(item["КоличествоДней"])
        date_admission_correct = date_admission + relativedelta.relativedelta(
            days=children_days
        )
        # for item in json_vacation['value']:
        #     print(datetime.strptime(item['ДатаНачала'][:10], "%Y-%m-%d"), exclude_vacation[item['ВидЕжегодногоОтпуска_Key']], item['Количество'])
        #     print(item['Количество'])
    except Exception as _ex:
        logger.debug(f"{_ex}")
        return {"value": ""}
    # logger.info(f'Успешное получение данных: {response.text}')
    return [date_admission, date_admission_correct, json.loads(response_vacation.text)]


def get_jsons_data_filter2(
        object_type: str,
        object_name: str,
        filter_obj: str,
        filter_content: str,
        filter_obj2: str,
        filter_content2: str,
        logical: int,
        base_index: int,
) -> dict:
    logical_operation = ["eq", "ne", "gt", "ge", "lt", "le", "or", "and", "not"]
    base = [
        "72095052-970f-11e3-84fb-00e05301b4e4",
        "59e20093-970f-11e3-84fb-00e05301b4e4",
    ]
    url = (
        f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/"
        f"{object_type}_{object_name}?$format=application/json;odata=nometadata"
        f"&$filter={filter_obj}%20{logical_operation[logical]}%20guid'{filter_content}'"
        f"and {filter_obj2}%20{logical_operation[logical]}%20{filter_content2}"
    )
    source_url = url
    try:
        if base_index == 0:
            response = requests.get(
                source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
            )
        else:
            response = requests.get(
                source_url, auth=(config("ACC_LOGIN"), config("ACC_PASS"))
            )
    except Exception as _ex:
        logger.debug(f"{_ex}")
        return {"value": ""}
    return json.loads(response.text)


def get_jsons(url, base_index):
    source_url = url
    if base_index == 0:
        response = requests.get(
            source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
    else:
        response = requests.get(
            source_url, auth=(config("ACC_LOGIN"), config("ACC_PASS"))
        )
    return json.loads(response.text)


def change_session_get(request, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param request: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    result = request.GET.get("result", None)
    sort_item = request.GET.get("sort_item", None)
    if sort_item:
        self.request.session["sort_item"] = sort_item
    if result:
        self.request.session["portal_paginator"] = result


def change_session_context(context, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param context: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    try:
        context["portal_paginator"] = int(self.request.session["portal_paginator"])
    except Exception as _ex:
        message = f"Параметр пагинации в сессии отсутствует. {_ex}"
        logger.info(message)
        context["portal_paginator"] = self.paginate_by

    try:
        context["sort_item"] = int(self.request.session["sort_item"])
    except Exception as _ex:
        message = f"Параметр сортировки в сессии отсутствует. {_ex}"
        logger.info(message)
        context["sort_item"] = 0


def change_session_queryset(request, self):
    """
    Получает параметры пагинации и сортировки со страницы, и изменяет переменные сессии: Параметр сортировки, и
    параметр пагинации
    :param request: Запрос со страницы
    :param self: Представления экземпляра класса, из которого вызывается функция
    :return:
    """
    try:
        if self.request.session["portal_paginator"]:
            self.paginate_by = int(self.request.session["portal_paginator"])
        else:
            self.paginate_by = PortalProperty.objects.all().first().portal_paginator
    except Exception as _ex:
        message = f"Параметр пагинации в сессии отсутствует. {_ex}"
        logger.info(message)
        self.paginate_by = PortalProperty.objects.all().first().portal_paginator

    try:
        if self.request.session["sort_item"]:
            self.item_sorted = self.sorted_list[int(self.request.session["sort_item"])]
        else:
            self.item_sorted = "pk"
    except Exception as _ex:
        message = f"Параметр сортировки в сессии отсутствует. {_ex}"
        logger.info(message)
        self.item_sorted = "pk"


def ending_day(value: int) -> str:
    """
    Преобразует числовое значение в соответствующее словесное представление для слов «день», «дни» или «день»
    на русском языке.

    :param value: Числовое значение для преобразования.
    :return: Слово, представляющее заданное значение для «день», «дни» или «день» на русском языке.
    """
    value = abs(
        value
    )  # Принимает абсолютное значение, так как отрицательные числа также должны быть правильно преобразованы

    # Последние две цифры нужны, чтобы найти форму на русском языке
    last_two_digits = value % 100

    # Последняя цифра используется, когда последние две цифры от 10 до 19
    last_digit = value % 10

    if 10 <= last_two_digits <= 20 or last_digit in [0, 5, 6, 7, 8, 9]:
        return f"{value} дней"
    elif last_digit == 1:
        return f"{value} день"
    else:  # Если последняя цифра от 2 до 4
        return f"{value} дня"


def format_name_initials(value: str, obj=None) -> str:
    """
    Форматирование ФИО человека, до вида Фамилия И.О.
    :param value: Строка с ФИО
    :param obj: принимает объект, чтоб в результате ошибки вывести в логах, где произошла ошибка
    :return: возвращает форматированную строку
    """
    try:
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
    except Exception as _ex:
        logger.error(
            f"Error while formatting name. Value: {value}; Document: {obj}; Error: {_ex}"
        )
        return ""


class CkeditorCustomStorage(FileSystemStorage):
    """
    Кастомное расположение для медиа файлов редактора
    """

    def get_folder_name(self):
        return datetime.now().strftime("%Y/%m/%d")

    def get_valid_name(self, name):
        return name

    def _save(self, name, content):
        folder_name = self.get_folder_name()
        name = os.path.join(folder_name, self.get_valid_name(name))
        return super()._save(name, content)

    location = os.path.join(settings.MEDIA_ROOT, "uploads/")
    base_url = urljoin(settings.MEDIA_URL, "uploads/")


def change_users_password():
    """
    Функция смены паролей пользователей. В качестве списка принимает файл eggs.csv. Который состоит из записей вида:
    ФИО;username;email;password
    :return: Возврат не предусмотрен. В качестве результата работы функции - смена всех паролей пользователей на сайте.
    """
    users_list = DataBaseUser.objects.all()
    error_list = list()
    import csv

    with open(pathlib.Path.joinpath(BASE_DIR, "eggs.csv"), newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            list_item = row[0].split(";")
            try:
                user_obj = DataBaseUser.objects.get(username=list_item[1])
                user_obj.set_password(list_item[3])
                user_obj.save()
            except Exception as _ex:
                error_list.append(list_item)
            try:
                user_obj = DataBaseUser.objects.get(username=list_item[1])
                work_profile = DataBaseUserWorkProfile.objects.get(
                    pk=user_obj.user_work_profile.pk
                )
                work_profile.work_email_password = list_item[3]
                work_profile.save()
            except Exception as _ex:
                error_list.append(list_item)


def get_users_info():
    """
    Этот метод извлекает информацию о пользователях из базы данных и создает файл CSV со сведениями о пользователе.

    :возврат: Нет
    """
    users_list = DataBaseUser.objects.all().exclude(is_ppa=True)
    import csv

    with open("eggs.csv", "w", newline="") as csvfile:
        spamwriter = csv.writer(
            csvfile, delimiter=";", quotechar="|", quoting=csv.QUOTE_MINIMAL
        )
        for item in users_list:
            if item.email:
                spamwriter.writerow(
                    [
                        f"{item.last_name} {item.first_name} {item.surname}",
                        f"{item.username}",
                        f"{item.email}",
                    ]
                )
            else:
                spamwriter.writerow(
                    [
                        f"{item.last_name} {item.first_name} {item.surname}",
                        f"{item.username}",
                        f"E-mail отсутствует",
                    ]
                )


MONTHS = {
    "1": "Январь",
    "2": "Февраль",
    "3": "Март",
    "4": "Апрель",
    "5": "Май",
    "6": "Июнь",
    "7": "Июль",
    "8": "Август",
    "9": "Сентябрь",
    "10": "Октябрь",
    "11": "Ноябрь",
    "12": "Декабрь",
}


def get_year_interval(year=2020):
    """
    Возвращает два словаря, месяца и года, для полей SELECT в формах на текущую дату. В качестве генератора списка
    используется rrule, где dtstart - начальный год, until - дата до которой следует составить список.
    :param year: Год по умолчанию = 2020-й, с него начинается статистика на сайте
    :return: Словарь месяцев - MONTHS, Словарь лет - year_dict
    """

    intervals = list(
        rrule.rrule(
            rrule.YEARLY,
            dtstart=datetime(year=year, month=1, day=1),
            until=datetime.today(),
        )
    )
    year_dict = {item.year: item.year for item in intervals}
    return MONTHS, year_dict


def timedelta_to_time(time):
    """
    Преобразование timedelta во время.
    :param time: Время в формате timedelta или в формате строки '00:00:00'
    :return: Время в формате datetime.time
    """
    return datetime.strptime(str(time), "%H:%M:%S").time()


def timedelta_to_string(time):
    """
    Преобразование timedelta в строку.
    :param time: Время в формате timedelta или в формате строки '00:00:00'
    :return: Время в формате строки
    """
    return datetime.strptime(str(time), "%H:%M:%S").time().strftime("%H:%M")


def time_difference(start_time: datetime.time, end_time: datetime.time):
    """
    Получение разности времени
    :param start_time: время начала
    :param end_time: время окончания
    :return: количество секунд между start_time и end_time
    """
    if start_time > end_time:
        raise ValueError("start_time должно быть раньше, чем end_time.")
    result = (
            timedelta(hours=end_time.hour, minutes=end_time.minute).total_seconds()
            - timedelta(hours=start_time.hour, minutes=start_time.minute).total_seconds()
    )
    return result


def get_date_interval(dtstart: datetime, until: datetime) -> list:
    """
    Возвращает список дат. В качестве генератора списка
    используется rrule, где dtstart - начальный дата, until - дата до которой следует составить список.
    :param dtstart: Дата начала
    :param until: Дата окончания
    :return: Список дат
    """
    return list(rrule.rrule(rrule.DAILY, dtstart=dtstart, until=until))


def get_types_userworktime():
    url = (
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/"
        f"Catalog_ВидыИспользованияРабочегоВремени?$format=application/json;odata=nometadata"
    )
    source_url = url
    try:
        response = requests.get(
            source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
    except Exception as _ex:
        logger.debug(f"{_ex}")
        return {"value": ""}

    return json.loads(response.text)


def change_approval_status(self):
    """
    :param self: Экземпляр класса, для которого вызывается метод.
    :return: None

    Метод `change_approval_status` используется для обновления статуса утверждения документа на основе нескольких
    условий. Он устанавливает комментарии и атрибуты document_accepted документа на основе выполненных условий.

    Условия и соответствующие комментарии определяются в списке `conditions_with_comments`. Первое условие, которое
    оценивается как True, соответственно установит комментарии и атрибуты document_accepted.

    Если комментарии не равны «Документооборот начат» и атрибут отмены имеет значение False, метод обновляет атрибуты
    comment и document_accepted документа.

    Метод ничего не возвращает.
    """
    conditions_with_comments = [
        (self.submit_for_approval, "Передан на согласование"),
        (self.document_not_agreed, "Документ согласован"),
        (self.location_selected, "Утверждено место проживания"),
        (self.process_accepted, "Создан приказ"),
        (self.originals_received and self.date_receipt_original, "Получены оригиналы"),
        (self.originals_received and self.date_transfer_hr, "Передано в ОК"),
        (self.hr_accepted, "Передано в бухгалтерию"),
        (self.accepted_accounting, "Документооборот завершен"),
    ]

    comments = "Документооборот начат"
    document_accepted = False
    for condition, comment in conditions_with_comments:
        if condition:
            comments = comment
            document_accepted = comment == "Документооборот завершен"

    if comments != "Документооборот начат" and not self.cancellation:
        self.document.comments = comments
        self.document.document_accepted = document_accepted
        self.document.save()

    return ""


# def change_password():
#     count, errors = 0, 0
#     for item in DataBaseUser.objects.all().exclude(is_superuser=True):
#         if item.user_work_profile.work_email_password:
#             item.set_password(item.user_work_profile.work_email_password)
#             item.save()
#             count += 1
#         else:
#             errors += 1
#
#     return count, errors

def change_password():
    """
    Изменяет пароли пользователей в базе данных на пароли из профиля пользователя.

    Returns:
    - tuple: Кортеж, содержащий два значения:
        - count (int): Количество успешно измененных паролей.
        - errors (int): Количество пользователей, у которых пароль не был изменен
          (например, отсутствует work_email_password).

    """
    count, errors = 0, 0

    # Используем транзакцию для обеспечения атомарности операции
    with transaction.atomic():
        for item in DataBaseUser.objects.filter(is_superuser=False).exclude(
                user_work_profile__work_email_password__isnull=True):
            try:
                item.set_password(item.user_work_profile.work_email_password)
                item.save()
                count += 1
            except Exception as e:
                errors += 1
                print(f"Ошибка смены пароля для пользователя {item.username}: {e}")

    return count, errors


# def make_custom_field(f: forms.Field):
#     """
#     Функция make_custom_field принимает в качестве аргумента объект класса forms.Field.
#         Функция использует тип поля (isinstance) для определения типа поля и настройки соответствующих атрибутов.
#     :param f:
#         class: класс CSS для стилизации поля
#         data-plugin-datepicker: включает дату для поля даты
#         data-date-language: язык для даты
#         todayBtn: включает кнопку "Сегодня" для поля даты
#         clearBtn: включает кнопку "Очистить" для поля даты
#         data-plugin-options: настройки для плагина даты
#         autocomplete: включает автодополнение для текстовых полей
#         rows: количество строк для текстовых полей
#         data-plugin-selectTwo: включает плагин Select2 для полей выбора
#         class: класс CSS для стилизации поля выбора
#         multiple: включает возможность выбора нескольких значений для полей выбора
#         data-plugin-multiselect: включает плагин MultiSelect для полей выбора
#         data-plugin-fileinput: включает плагин FileInput для поля файла
#
#     :return:
#         возвращает объект с настроенными атрибутами для отображения поля в формате.
#     """
#     if isinstance(f, forms.DateField):
#         return f.widget.attrs.update(
#             {"class": "form-control form-control-modern",
#              "data-plugin-datepicker": True, "type": "text",
#              "data-date-language": "ru", "todayBtn": True, "clearBtn": True,
#              "data-plugin-options": '{"orientation": "bottom", "format": "dd.mm.yyyy"}',
#              }
#         )
#     if isinstance(f, forms.BooleanField):
#         return f.widget.attrs.update({"class": "todo-check", "data-plugin-ios-switch": True})
#     if isinstance(f, forms.CharField) or isinstance(f, forms.DecimalField) or isinstance(f, forms.IntegerField):
#         return f.widget.attrs.update({"class": "form-control form-control-modern", "autocomplete": "on", "rows": "3"})
#     if isinstance(f, forms.ChoiceField):
#         return f.widget.attrs.update({"class": "form-control form-control-modern", "data-plugin-selectTwo": True})
#     if isinstance(f, forms.ModelChoiceField):
#         return f.widget.attrs.update(
#             {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
#         )
#     if isinstance(f, forms.ModelMultipleChoiceField):
#         return f.widget.attrs.update(
#             {"class": "form-select select2 form-control-modern",
#              "data-plugin-multiselect": True,
#              "multiple": "multiple",
#              "data-plugin-options": '{ "maxHeight": 400, "includeSelectAllOption": true }',
#              }
#         )
#     if isinstance(f, forms.FileField):
#         return f.widget.attrs.update({"class": "form-control form-control-modern", "data-plugin-fileinput": True})


def make_custom_field(f: forms.Field):
    """
    Функция make_custom_field принимает в качестве аргумента объект класса forms.Field.
    Функция использует тип поля (isinstance) для определения типа поля и настройки соответствующих атрибутов.
    :param f:
    :return: возвращает объект с настроенными атрибутами для отображения поля в формате.
    """
    field_attrs = {
        forms.DateField: {
            "class": "form-control form-control-modern",
            "data-plugin-datepicker": True,
            "type": "date",
            "data-date-language": "ru",
            "todayBtn": True,
            "clearBtn": True,
            "data-plugin-options": '{"orientation": "bottom", "format": "dd.mm.yyyy"}',
        },
        forms.BooleanField: {
            "class": "todo-check",
            "data-plugin-ios-switch": True,
        },
        forms.CharField: {
            "class": "form-control form-control-modern",
            "autocomplete": "on",
            "rows": "3",
        },
        forms.DecimalField: {
            "class": "form-control form-control-modern",
            "autocomplete": "on",
            "rows": "3",
        },
        forms.IntegerField: {
            "class": "form-control form-control-modern",
            "autocomplete": "on",
            "rows": "3",
        },
        forms.ChoiceField: {
            "class": "form-control form-control-modern",
            "data-plugin-selectTwo": True,
        },
        forms.ModelChoiceField: {
            "class": "form-control form-control-modern",
            "data-plugin-selectTwo": True,
        },
        forms.ModelMultipleChoiceField: {
            "class": "form-select select2 form-control-modern",
            "data-plugin-multiselect": True,
            "multiple": "multiple",
            "data-plugin-options": '{ "maxHeight": 400, "includeSelectAllOption": true }',
        },
        forms.FileField: {
            "class": "form-control form-control-modern",
            "data-plugin-fileinput": True,
        },
    }

    for field_type, attrs in field_attrs.items():
        if isinstance(f, field_type):
            f.widget.attrs.update(attrs)
            break

    return f


def ajax_search(request, self, field_list, model_name, query, triger=None):
    """
    Оптимизированный метод для поиска по модели с использованием AJAX-запросов.
    """
    data = request.GET
    draw = int(data.get("draw", 1))
    start = int(data.get("start", 0))
    length = int(data.get("length", 10))
    context = {
        "draw": draw,
        "iDisplayStart": start,
    }

    # Функция для создания Q-объектов для поиска
    def build_query(field, search_value):
        if triger == 1 and field == 'contract_counteragent__short_name':
            return (
                    Q(contract_counteragent__short_name__iregex=search_value) |
                    Q(contract_counteragent__full_name__iregex=search_value) |
                    Q(contract_counteragent__inn__iregex=search_value)
            )
        elif triger == 2 and field == 'document__type_trip':
            if search_value.lower() in 'сп':
                return Q(document__type_trip__iregex="1")
            elif search_value.lower() in 'к':
                return Q(document__type_trip__iregex="2")
            elif search_value.lower() in 'сп+':
                return Q(document__type_trip__iregex="1") & Q(document__official_memo_type__iregex="2")
            elif search_value.lower() in 'к+':
                return Q(document__type_trip__iregex="2") & Q(document__official_memo_type__iregex="2")
        elif triger == 2 and field == 'accommodation':
            if search_value.lower() in "гостиница":
                return Q(accommodation__iregex="2")
            elif search_value.lower() in "квартира":
                return Q(accommodation__iregex="1")
            else:
                return Q(accommodation__iregex="0")
        return Q(**{f"{field}__iregex": search_value})

    # Построение общего запроса
    for counter, field in enumerate(field_list):
        search_value = data.get(f"columns[{counter}][search][value]")
        if search_value:
            search_list = search_value.split('!')
            for search in search_list:
                if search:
                    query &= build_query(field, search)

    # Фильтрация данных
    order_list = model_name.objects.filter(query) if query else model_name.objects.all()

    # Пагинация и формирование контекста
    total = order_list.count()
    context.update({
        "recordsTotal": total,
        "recordsFiltered": total,
        "data": [order_item.get_data() for order_item in order_list[start:start + length]],
    })

    return context


# def ajax_search(request, self, field_list, model_name, query, triger=None):
#     """
#     Метод для поиска по модели.
#     Цель:
#         Метод ajax_search предназначен для выполнения поиска по указанной модели с помощью AJAX-запросов. Он принимает
#         четыре параметра: request, self, field_list, model_name и query.
#     Параметры:
#         request: Объект HTTP-запроса.
#         self: Экземпляр класса, к которому принадлежит этот метод.
#         field_list: Список полей, которые нужно искать в модели.
#         model_name: Имя модели Django, которую нужно искать.
#         query: Строка поиска.
#     Описание метода:
#         Метод ajax_search выполняет следующие задачи:
#         Он получает параметры поиска из AJAX-запроса.
#         Он проходит по списку field_list и применяет строку поиска к каждому полю с помощью ORM-объекта Q.
#         Если строка поиска не пуста, он фильтрует экземпляры модели с помощью метода filter. В противном случае он
#         возвращает все экземпляры модели.
#         Он рассчитывает общее количество записей в таблице и устанавливает ключ recordsTotal в контексте.
#         Он устанавливает ключ draw в контексте в значение текущей страницы.
#         Он устанавливает ключ recordsFiltered в контексте в значение общего количества записей.
#         Он устанавливает ключ iDisplayStart в контексте в значение начальной позиции страницы.
#         Он пагинирует результаты поиска с помощью атрибута paginate_by и устанавливает ключ data в контексте в значение
#         пагинированных результатов.
#     Возвращаемое значение:
#         Метод возвращает словарь, содержащий результаты поиска и метаданные пагинации.
#     """
#     context = {}
#     data = request.GET
#     draw = int(data.get("draw"))
#     start = int(data.get("start"))
#     length = int(data.get("length"))
#     counter = 0
#
#     if triger == 1: #Поиск в договорах
#         for field in field_list:
#             if request.GET.get(f"columns[{counter}][search][value]"):
#                 search_value = request.GET.get(f"columns[{counter}][search][value]")
#                 search_list = search_value.split('!')
#                 if len(search_list) > 1:
#                     for search in search_list:
#                         if len(search) > 0:
#                             if field == 'contract_counteragent__short_name':
#                                 multiply_search = Q(
#                                     **{'contract_counteragent__short_name' + '__iregex': search}) | Q(
#                                     **{'contract_counteragent__full_name' + '__iregex': search}) | Q(
#                                     **{'contract_counteragent__inn' + '__iregex': search})
#                             else:
#                                 multiply_search = Q(**{field + '__iregex': search})
#                             query &= multiply_search
#                 else:
#                     if field == 'contract_counteragent__short_name':
#                         multiply_search = Q(**{'contract_counteragent__short_name' + '__iregex': search_value}) | Q(
#                             **{'contract_counteragent__full_name' + '__iregex': search_value}) | Q(
#                             **{'contract_counteragent__inn' + '__iregex': search_value})
#                     else:
#                         multiply_search = Q(**{field + '__iregex': search_value})
#                     query &= multiply_search
#             counter += 1
#         if query:
#             order_list = model_name.objects.filter(query)
#         else:
#             order_list = model_name.objects.all()
#     elif triger == 2: # Поиск в бизнес-процессах
#         for field in field_list:
#             if request.GET.get(f"columns[{counter}][search][value]"):
#                 search_value = request.GET.get(f"columns[{counter}][search][value]")
#                 search_list = search_value.split('!')
#                 if len(search_list) > 0:
#                     for search in search_list:
#                         if len(search) > 0:
#                             if field == 'document__type_trip':
#                                 if search.lower() in 'сп':
#                                     multiply_search = Q(**{'document__type_trip' + '__iregex': "1"})
#                                 elif search.lower() in 'к':
#                                     multiply_search = Q(**{'document__type_trip' + '__iregex': "2"})
#                                 elif search.lower() in 'сп+':
#                                     multiply_search = Q(**{'document__type_trip' + '__iregex': "1"}) & Q(
#                                         **{'document__official_memo_type' + '__iregex': "2"})
#                                 elif search.lower() in 'к+':
#                                     multiply_search = Q(**{'document__type_trip' + '__iregex': "2"}) & Q(
#                                         **{'document__official_memo_type' + '__iregex': "2"})
#                                 else:
#                                     multiply_search = Q(**{field + '__iregex': search})
#                                 query &= multiply_search
#                             elif field == 'accommodation':
#                                 if search.lower() in "гостиница":
#                                     search = "2"
#                                 elif search.lower() in "квартира":
#                                     search = "1"
#                                 else:
#                                     search = "0"
#                                 query &= Q(**{field + '__iregex': search})
#                             else:
#                                 query &= Q(**{field + '__iregex': search})
#             counter += 1
#         if query:
#             order_list = model_name.objects.filter(query)
#         else:
#             order_list = model_name.objects.all()
#     else:
#         for field in field_list:
#             if request.GET.get(f"columns[{counter}][search][value]"):
#                 search_value = request.GET.get(f"columns[{counter}][search][value]")
#                 search_list = search_value.split('!')
#                 if len(search_list) > 1:
#                     for search in search_list:
#                         if len(search) > 0:
#                             query &= Q(**{field + '__iregex': search})
#                 else:
#                     query &= Q(**{field + '__iregex': request.GET.get(f"columns[{counter}][search][value]")})
#             counter += 1
#         if query:
#             order_list = model_name.objects.filter(query)
#         else:
#             order_list = model_name.objects.all()
#
#     total = order_list.count()  # Получаем общее количество записей в таблице
#     context["recordsTotal"] = total  # Общее количество записей в таблице
#     context["draw"] = draw  # Количество записей на странице
#     context["recordsFiltered"] = total  # Общее количество записей в таблице
#     context['iDisplayStart'] = start  # Стартовая позиция
#     order_list = order_list[start:start + length]
#     self.paginate_by = int(length)
#
#     context["data"] = [order_item.get_data() for order_item in order_list]
#     return context


def send_notification(sender: DataBaseUser, recipient, subject: str, template: str, context: dict,
                      attachment='', division=0, document=0):
    """
    Функция отправки письма
    :param document: 0 - обычное письмо, 1 - Старшие бригад, 2 - Командировка и служебные
    :param division: 0 - <username>@barkol.ru, 1 - ias@barkol.ru, 2 - fly@barkol.ru, Другое - corp@barkol.ru
    :param sender: Отправитель
    :param recipient: Получатель
    :param subject: Тема
    :param template: Шаблон письма
    :param context: Контекст для заполнения шаблона
    :param attachment: Вложение к письму, в виде ссылки на файл
    :return:
    """
    match division:
        case 0:
            from_mail = sender.email  # адрес отправителя
            from_passwd = sender.user_work_profile.work_application_password  # пароль от почты отправителя
        case 1:
            from_mail = EMAIL_IAS_USER  # адрес отправителя
            from_passwd = EMAIL_IAS_PASSWORD  # пароль от почты отправителя
        case 2:
            from_mail = EMAIL_FLY_USER  # адрес отправителя
            from_passwd = EMAIL_FLY_PASSWORD  # пароль от почты отправителя
        case _:
            from_mail = EMAIL_HOST_USER  # адрес отправителя
            from_passwd = EMAIL_HOST_PASSWORD  # пароль от почты отправителя
    server_adr = EMAIL_HOST  # адрес почтового сервера
    server_imap = EMAIL_IMAP_HOST  # адрес imap сервера
    match document:
        case 0:
            to_mail = [recipient.email, ]  # адрес получателя
        case 1:
            to_mail = [recipient.senior_brigade.email, recipient.place.email, ]  # адрес получателя
        case 2:
            to_mail = [recipient.document.person.email, ]
        case _:
            to_mail = [recipient, ]
    message = render_to_string(template, context)
    msg = MIMEMultipart()  # Создаем сообщение
    msg["From"] = from_mail  # Добавляем адрес отправителя
    msg['To'] = ','.join(to_mail)  # Добавляем адрес получателя
    msg["Subject"] = Header(subject, 'utf-8')  # Пишем тему сообщения
    msg["Date"] = formatdate(localtime=True)  # Дата сообщения
    msg.attach(MIMEText(message, 'html', 'utf-8'))  # Добавляем форматированный текст сообщения

    # Добавляем файл
    if attachment != '':
        filepath = str(BASE_DIR) + attachment  # путь к файлу
        part = MIMEBase('application', "octet-stream")  # Создаем объект для загрузки файла
        part.set_payload(open(filepath, "rb").read())  # Подключаем файл
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                        f'attachment; filename="{os.path.basename(filepath)}"')
        msg.attach(part)  # Добавляем файл в письмо
    try:
        smtp = smtplib.SMTP_SSL(server_adr, 465)  # Создаем объект для отправки сообщения
    except Exception as _ex:
        logger.error(f"Ошибка: {_ex}")
    try:
        smtp.login(from_mail, from_passwd)  # Логинимся в свой ящик
        smtp.sendmail(from_mail, to_mail, msg.as_string())  # Отправляем сообщения
        smtp.quit()  # Закрываем соединение
    except smtplib.SMTPAuthenticationError:
        logger.error(f"SMTPAuthenticationError")
        return 0
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"SMTPRecipientsRefused")
        return 0
    except Exception as _ex:
        logger.error(f"Не удалось подключиться к серверу: {_ex}")
        return 0

    # Сохраняем сообщение в исходящие
    imap = imaplib.IMAP4_SSL(server_imap, 993)  # Подключаемся в почтовому серверу
    imap.login(from_mail, from_passwd)  # Логинимся в свой ящик
    list_imap = imap.list()  # Получаем список папок
    box = ''
    if list_imap[0] == 'OK':
        for i in list_imap[1]:
            strings = i.decode().split(' ')
            if 'Sent' in strings[0]:
                box = strings[2].replace('"', '')
    imap.append(box, None,  # Добавляем наше письмо в папку Исходящие
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes())
    return 1  # Сообщение успешно отправлено


def check_user(request):
    """Проверка пользователя.
    :param request: request - объект запроса
    :return: Если пользователь не аутентифицирован, то перенаправляет на страницу логина
    """
    if request.user.is_anonymous:
        return redirect(reverse('customers_app:login'))


def get_client_ip(request):
    """
        Возвращает IP-адрес клиента из HTTP-запроса.

        :param request: Объект запроса (HttpRequest)
        :return: Строка с IP-адресом клиента

        Примечание:
            Если в HTTP-запросе есть заголовок "X-Forwarded-For", функция будет использовать его для определения IP-адреса.
            В противном случае, функция будет использовать значение "REMOTE_ADDR" из META-объекта запроса.
        """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def process_group_year(group):
    """
    Обрабатывает группу данных по году, возвращая соответствующее значение времени в зависимости от типа записей.

    Функция анализирует значения столбца 'Type' в переданной группе данных и возвращает значение времени
    в соответствии со следующими правилами:
    - Если в группе присутствуют типы 14, 15, 16, 17 или 20, возвращается первое значение из столбца 'Time'
      для записей с этими типами.
    - Если в группе присутствуют типы от 1 до 13 включительно или тип 19, возвращается сумма значений 'Time'
      для всех таких записей.
    - Во всех остальных случаях возвращается сумма всех значений 'Time' в группе.

    Параметры:
        group (pandas.DataFrame): Группа данных, содержащая столбцы 'Type' и 'Time'.

    Возвращает:
        float или int: Рассчитанное значение времени в зависимости от типов записей в группе.
    """
    if any(t in [14, 15, 16, 17, 20] for t in group["Type"].values):
        return group[group["Type"].isin([14, 15, 16, 17, 20])]["Time"].values[0]
    elif any(t in range(1, 14) or t == 19 for t in group["Type"].values):
        return group[group["Type"].isin(list(range(1, 14)) + [19])]["Time"].sum()
    else:
        return group["Time"].sum()


def process_group(group):
    if any(t in [14, 15, 16, 17, 20] for t in group["Type"].values):
        new_type = group[group["Type"].isin([14, 15, 16, 17, 20])]["Type"].values[0]
        new_time = group[group["Type"].isin([14, 15, 16, 17, 20])]["Time"].values[0]
    elif any(t in range(1, 14) or t == 19 for t in group["Type"].values):
        new_type = group[group["Type"].isin(list(range(1, 14)) + [19])]["Type"].values[0]
        new_time = group[group["Type"].isin(list(range(1, 14)) + [19])]["Time"].sum()
    else:
        new_type = group["Type"].values[0]
        new_time = group["Time"].sum()
    return pd.DataFrame({
        'Дата': [group['Дата'].iloc[0]],
        'Интервал': [group['Интервал'].iloc[0]],
        'Type': [new_type],
        'Time': [new_time]
    })


# Функция для проверки и корректировки пересечений
def adjust_time(group):
    """
    Функция adjust_time предназначена для проверки и корректировки пересечений временных интервалов в группе записей.
    Она сортирует записи по времени начала и проверяет пересечения для записей с типом 1 или 13. Если обнаружено
    пересечение, функция корректирует время начала и окончания следующей записи, чтобы избежать пересечения.

    Подробное описание логики
        Сортировка по времени начала:
            Записи сортируются по столбцу Start в порядке возрастания.
        Проверка пересечений:
            Для каждой пары соседних записей проверяется, являются ли они типа 1 или 13.
            Если обе записи имеют тип 1 или 13, проверяется, пересекаются ли их временные интервалы.
        Корректировка времени:
            Если время начала следующей записи (start2) меньше времени окончания предыдущей записи (end1),
            то время начала следующей записи корректируется на время окончания предыдущей записи (end1).
            Время окончания следующей записи корректируется на максимальное значение между end1 и end2.

    :param group: group (pandas.DataFrame): Группа записей, которую нужно обработать. Должна содержать столбцы Start,
                  End и Type.
    :return: group (pandas.DataFrame): Группа записей с корректированными временными интервалами, если были обнаружены
             пересечения.
    """
    group = group.sort_values(by='Start')

    # Проверяем пересечения для записей с типом 1 или 13
    for i in range(len(group) - 1):
        if group.iloc[i]['Type'] in [1, 13] and group.iloc[i + 1]['Type'] in [1, 13]:
            start1, end1 = group.iloc[i]['Start'], group.iloc[i]['End']
            start2, end2 = group.iloc[i + 1]['Start'], group.iloc[i + 1]['End']

            # Проверяем пересечение
            if start2 < end1:
                # Корректируем время
                group.at[group.index[i + 1], 'Start'] = end1
                group.at[group.index[i + 1], 'End'] = max(end1, end2)

    return group


"""
Задан датафрейм:
Дата               Start                 End  Type     Time
03 1900-01-01 09:30:00 1900-01-01 18:00:00    16  30600.0
03 1900-01-01 11:47:15 1900-01-01 18:00:00    13  22365.0
04 1900-01-01 09:17:00 1900-01-01 18:00:00     1  31380.0
05 1900-01-01 09:41:00 1900-01-01 18:11:00     1  30600.0
06 1900-01-01 09:12:00 1900-01-01 11:12:54    13   7254.0
06 1900-01-01 11:12:54 1900-01-01 18:00:00     1  24426.0

Надо к каждой записи создать новое поле Интервал в которое поместить значение в следующем формате {df[Start]:df[End]}, но с условием, если запись с такой датой одна, то просто передаем значения, если же таких записей больше одной, то проверить, если хотя бы у одной значение поля Type равняется 14, 15, 16, 17 или 20 то тогда всем схожим записям установить значение поля Интервал из этой записи, а если  1 и 13, то берется наименьшее значение поля Start и наибольшее End

Для решения задачи можно использовать функцию apply вместе с группировкой по дате. Мы будем проверять условия для каждой группы и устанавливать соответствующие значения в новом столбце "Интервал".

Вот пример кода, который решает эту задачу:

python
Copy code
import pandas as pd

# Создаем DataFrame
data = {
    'Дата': ['1900-01-01', '1900-01-01', '1900-01-01', '1900-01-01', '1900-01-01', '1900-01-01'],
    'Start': ['09:30:00', '11:47:15', '09:17:00', '09:41:00', '09:12:00', '11:12:54'],
    'End': ['18:00:00', '18:00:00', '18:00:00', '18:11:00', '11:12:54', '18:00:00'],
    'Type': [16, 13, 1, 1, 13, 1],
    'Time': [30600.0, 22365.0, 31380.0, 30600.0, 7254.0, 24426.0]
}

df = pd.DataFrame(data)

# Преобразуем столбцы Start и End в datetime
df['Start'] = pd.to_datetime(df['Start'], format='%H:%M:%S').dt.time
df['End'] = pd.to_datetime(df['End'], format='%H:%M:%S').dt.time



# Группируем по дате и применяем функцию
df = df.groupby('Дата').apply(process_group_interval).reset_index(drop=True)

print(df)
Пояснение:
Преобразование столбцов Start и End в тип datetime.time:

Это необходимо для корректного сравнения и вычисления минимальных и максимальных значений.

Функция process_group:

Если в группе только одна запись, то просто устанавливаем значение Интервал как {Start}:{End}.

Если в группе есть хотя бы одна запись с Type в [14, 15, 16, 17, 20], то все записи в группе получают интервал из этой записи.

Если в группе есть хотя бы одна запись с Type в [1, 13], то устанавливаем интервал как {min(Start)}:{max(End)}.

Если ни одно из условий не выполняется, то устанавливаем интервал как {Start}:{End} для первой записи в группе.

Группировка и применение функции:

df.groupby('Дата').apply(process_group).reset_index(drop=True): Группируем DataFrame по столбцу "Дата" и применяем функцию process_group к каждой группе. Затем сбрасываем индекс, чтобы получить плоский DataFrame.

Результат:
plaintext
Copy code
         Дата      Start       End  Type      Time    Интервал
0  1900-01-01  09:30:00  18:00:00    16  30600.0  09:30:00:18:00:00
1  1900-01-01  11:47:15  18:00:00    13  22365.0  09:12:00:18:00:00
2  1900-01-01  09:17:00  18:00:00     1  31380.0  09:12:00:18:00:00
3  1900-01-01  09:41:00  18:11:00     1  30600.0  09:12:00:18:11:00
4  1900-01-01  09:12:00  11:12:54    13   7254.0  09:12:00:18:00:00
5  1900-01-01  11:12:54  18:00:00     1  24426.0  09:12:00:18:00:00
Этот код корректно обрабатывает записи в соответствии с заданными условиями и устанавливает значения в новом столбце "Интервал".
"""


# Функция для обработки групп
def process_group_interval(group):
    """
    Функция process_group_interval обрабатывает группу записей, вычисляя интервал времени для каждой группы на основе
    значений столбцов Start, End и Type. Функция возвращает группу с добавленным столбцом Интервал, содержащим строковое
    представление интервала времени.

        Подробное описание логики
        Если в группе только одна запись:
            Интервал времени формируется на основе единственной записи.
            Формат интервала: "HH:MM-HH:MM".
        Если в группе более одной записи:
            Если есть хотя бы одна запись с Type в списке [14, 15, 16, 17, 20]:
                Интервал времени формируется на основе первой записи с таким Type.
                Формат интервала: "HH:MM-HH:MM".
            Если есть хотя бы одна запись с Type в списке [1, 13]:
                Интервал времени формируется на основе минимального значения Start и максимального значения End среди
                всех записей.
                Формат интервала: "HH:MM-HH:MM".
            Если нет записей с Type в списке [14, 15, 16, 17, 20] или [1, 13]:
                Интервал времени формируется на основе первой записи в группе.
                Формат интервала: "HH:MM-HH:MM".

    :param group: group (pandas.DataFrame): Группа записей, которую нужно обработать. Должна содержать столбцы Start,
                  End и Type.
    :return: group (pandas.DataFrame): Группа записей с добавленным столбцом Интервал, содержащим строковое
             представление интервала времени.
    """
    if len(group) == 1:
        # Если запись одна, просто передаем значения
        group['Интервал'] = f"{group['Start'].iloc[0].strftime('%H:%M')}-{group['End'].iloc[0].strftime('%H:%M')}"
    else:
        if any(t in [14, 15, 16, 17, 20] for t in group['Type']):
            # Если есть хотя бы одна запись с Type в [14, 15, 16, 17, 20]
            interval_record = group[group['Type'].isin([14, 15, 16, 17, 20])].iloc[0]
            group[
                'Интервал'] = f"{interval_record['Start'].strftime('%H:%M')}-{interval_record['End'].strftime('%H:%M')}"
        elif any(t in [1, 13] for t in group['Type']):
            # Если есть хотя бы одна запись с Type в [1, 13]
            min_start = group['Start'].min()
            max_end = group['End'].max()
            group['Интервал'] = f"{min_start.strftime('%H:%M')}-{max_end.strftime('%H:%M')}"
        else:
            # Если нет записей с Type в [14, 15, 16, 17, 20] или [1, 13]
            group['Интервал'] = f"{group['Start'].iloc[0].strftime('%H:%M')}-{group['End'].iloc[0].strftime('%H:%M')}"
    return group


# def seconds_to_hhmm(seconds):
#     """
#     Описание:
#         Функция seconds_to_hhmm преобразует количество секунд в строку, форматированную как "HHH:MM".
#         Если входное значение отрицательное, строка будет начинаться с минуса.
#     Параметры
#         seconds (int): Количество секунд для преобразования. Может быть положительным или отрицательным.
#     Возвращаемое значение
#         str : Строка, представляющая время в формате "HHH:MM". Если входное значение отрицательное, строка будет
#         начинаться с минуса.
#     """
#     is_negative = seconds < 0
#     total_seconds = abs(seconds)
#     hours = int(total_seconds // 3600)
#     minutes = int((total_seconds % 3600) // 60)
#     sign = "-" if is_negative else ""
#     return f"{sign}{hours:03}:{minutes:02}"
def seconds_to_hhmm(seconds):
    """
    Описание:
        Функция seconds_to_hhmm преобразует количество секунд в строку, форматированную как "HH:MM".
        Если входное значение отрицательное, строка будет начинаться с минуса.
        Количество символов в часах зависит от их значения (например, 1 → "01", 10 → "10").

    Параметры:
        seconds (int): Количество секунд для преобразования. Может быть положительным или отрицательным.

    Возвращаемое значение:
        str: Строка, представляющая время в формате "HH:MM" (или "-HH:MM" для отрицательных значений).
    """
    # Определяем знак и абсолютное значение секунд
    sign = "-" if seconds < 0 else ""
    total_seconds = abs(seconds)

    # Вычисляем часы и минуты
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)

    # Форматируем часы с динамическим количеством символов
    hours_str = f"{hours:01}"  # Всегда минимум 2 символа (например, 1 → "01", 10 → "10")

    # Возвращаем отформатированную строку
    return f"{sign}{hours_str}:{minutes:02}"


def export_persons_to_csv(file_path: str, model):
    """
        Эта функция экспортирует все записи из указанной модели в CSV-файл.

        Аргументы:
        file_path (str): Путь к файлу, куда будут экспортированы данные.
        model (django.db.models.Model): Модель Django, из которой будут получены данные.

        Возвращает:
        None

        Примечание:
        Функция использует pandas для преобразования QuerySet в DataFrame и сохранения его в CSV-файл.
        Если в DataFrame есть пропущенные значения, они будут заменены на пустую строку ('').
        """
    # Получаем все записи из модели model
    dates = model.objects.all().values()

    # Преобразуем QuerySet в DataFrame
    df = pd.DataFrame.from_records(dates)

    # Сохраняем DataFrame в CSV-файл
    df.to_csv(file_path, sep=';', index=False, encoding='utf-8', na_rep='')


def get_year_suffix(years):
    """
        Возвращает правильное окончание для слова "год" в зависимости от числа лет.

        Parameters:
        - years (int): Количество лет.

        Returns:
        - str: Окончание для слова "год" ('год', 'года', 'лет').
        """
    try:
        if years % 10 == 1 and years % 100 != 11:
            return "год"
        elif 2 <= years % 10 <= 4 and (years % 100 < 10 or years % 100 >= 20):
            return "года"
        else:
            return "лет"
    except:
        return ""


def get_month_suffix(months):
    """
        Возвращает правильное окончание для слова "месяц" в зависимости от числа месяцев.

        Parameters:
        - months (int): Количество месяцев.

        Returns:
        - str: Окончание для слова "месяц" ('месяц', 'месяца', 'месяцев').

        """
    if months % 10 == 1 and months % 100 != 11:
        return "месяц"
    elif 2 <= months % 10 <= 4 and (months % 100 < 10 or months % 100 >= 20):
        return "месяца"
    else:
        return "месяцев"


def get_day_suffix(days):
    """
        Возвращает правильное окончание для слова "день" в зависимости от числа дней.

        Parameters:
        - days (int): Количество дней.

        Returns:
        - str: Окончание для слова "день" ('день', 'дня', 'дней').

        """
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    elif 2 <= days % 10 <= 4 and (days % 100 < 10 or days % 100 >= 20):
        return "дня"
    else:
        return "дней"


def get_today_data_delta(dtstart, trigger):
    """
        Возвращает строку с разницей между датой начала и сегодняшней датой в зависимости от триггера.

        Parameters:
        - dtstart (datetime.date): Дата начала.
        - trigger (int): Триггер для выбора формата вывода:
            - 0: Полный формат (годы, месяцы, дни).
            - 1: Только годы.

        Returns:
        - str: Строка с разницей между датами в указанном формате.

        """
    start = datetime.combine(dtstart, datetime.min.time())
    until = datetime.today()
    delta = relativedelta.relativedelta(until, start)
    match trigger:
        case 0:
            return f"{delta.years} {get_year_suffix(delta.years)} {delta.months} {get_month_suffix(delta.months)} {delta.days} {get_day_suffix(delta.days)}"
        case 1:
            return f"{delta.years} {get_year_suffix(delta.years)}"
        case _:
            raise ValueError("Недопустимое значение триггера. Ожидается 0 или 1.")
