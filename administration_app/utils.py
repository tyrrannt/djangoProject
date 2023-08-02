import json
import os
import pathlib
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from dateutil import rrule, relativedelta
from decouple import config
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from loguru import logger
from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser, HistoryChange, DataBaseUserWorkProfile
from djangoProject import settings
from djangoProject.settings import BASE_DIR

logger.add(
    "debug.json",
    format=config("LOG_FORMAT"),
    level=config("LOG_LEVEL"),
    rotation=config("LOG_ROTATION"),
    compression=config("LOG_COMPRESSION"),
    serialize=config("LOG_SERIALIZE"),
)


def get_history(self, model):
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
    "http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/Catalog_Сотрудники?$format=application/json;odata=nometadata"
    base = [
        "72095052-970f-11e3-84fb-00e05301b4e4",
        "59e20093-970f-11e3-84fb-00e05301b4e4",
    ]
    url = (
        f"http://192.168.10.11/{base[base_index]}/odata/standard.odata/"
        f"{object_type}_{object_name}?$format=application/json;odata=nometadata"
    )
    source_url = url
    print(url)
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
    )  # Taking absolute value, as negative numbers should also convert properly

    # Last two digits are needed to find the form in Russian language
    last_two_digits = value % 100

    # Last digit is used when the last two digits are from 10 to 19
    last_digit = value % 10

    if 10 <= last_two_digits <= 20 or last_digit == 0 or 5 <= last_digit <= 9:
        return f"{value} дней"
    elif last_digit == 1:
        return f"{value} день"
    else:  # If the last digit is from 2 to 4
        return f"{value} дня"


def format_name_initials(value, obj=None):
    """
    Форматирование ФИО человека, до вида Фамилия И.О.
    :param value: Строка с ФИО
    :param obj: принимает объект, чтоб в результате ошибки вывести в логах, где произошла ошибка
    :return: возвращает форматированную строку
    """
    if not value:
        return ""

    try:
        parts = str(value).split(" ")
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
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
    users_list = DataBaseUser.objects.all()
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


def timedelta_to_time(time, trigger=0):
    """
    Перевод времени timedelta в time
    :param trigger: в зависимости от переключателя, меняется формат вывода 0 - time, 1 - str
    :param time: время в формате timedelta или в формате строки '00:00:00'
    :return: время в формате datetime.time
    """
    if trigger == 0:
        return datetime.strptime(str(time), "%H:%M:%S").time()
    if trigger == 1:
        return datetime.strptime(str(time), "%H:%M:%S").time().strftime("%H:%M")


def time_difference(start_time: datetime.time, end_time: datetime.time):
    """
    Получение разности времени
    :param start_time: время начала
    :param end_time: время окончания
    :return: количество секунд между start_time и end_time
    """
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
            break

    if comments != "Документооборот начат" and not self.cancellation:
        self.document.comments = comments
        self.document.document_accepted = document_accepted
        self.document.save()

    return ""
