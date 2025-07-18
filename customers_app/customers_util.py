import datetime

from dateutil import rrule
from decouple import config
from loguru import logger

from administration_app.utils import (
    get_jsons_data_filter,
    get_jsons,
    get_jsons_data,
    transliterate,
    timedelta_to_time,
    get_json_vacation,
    timedelta_to_string, get_active_user,
)
from customers_app.models import (
    DataBaseUser,
    Job,
    Division,
    DataBaseUserWorkProfile,
    DataBaseUserProfile,
    IdentityDocuments,
    Citizenships,
)

logger.add(
    "debug.json",
    format=config("LOG_FORMAT"),
    level=config("LOG_LEVEL"),
    rotation=config("LOG_ROTATION"),
    compression=config("LOG_COMPRESSION"),
    serialize=config("LOG_SERIALIZE"),
)


def get_database_user_profile(ref_key):
    """
    Получение полиса ОМС из Регистра сведений
    :return: Найденную запись, или пустую строку
    """
    context = ""
    item = get_jsons_data_filter(
        "InformationRegister",
        "ПолисыОМСФизическихЛиц",
        "ФизическоеЛицо_Key",
        ref_key,
        0,
        0,
    )
    for record in item["value"]:
        context = record["НомерПолиса"]
    return context


def get_database_user_work_profile():
    """
    Получение подразделения, должности и даты приема на работу сотрудника,
    :return: Найденную запись, или пустую строку
    """
    from django.db import transaction

    context = ""
    users_list = DataBaseUser.objects.all().exclude(is_superuser=True, is_ppa=True).values("ref_key")
    profile_list = DataBaseUserWorkProfile.objects.all().values("ref_key")
    profile_list_items = list()
    for item in profile_list:
        profile_list_items.append(item["ref_key"])
    profile_list_update = list()
    todo_str_list = list()
    todo_str = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_КадроваяИсторияСотрудников?$format=application/json;odata=nometadata",
        0,
    )
    for item in todo_str["value"]:
        todo_str_list.append(item["RecordSet"][0])

    def get_filter_list(filter_list, variable, meaning):
        return list(
            filter(lambda item_filter: item_filter[variable] == meaning, filter_list)
        )

    for units in users_list:
        job_code, division_code, date_of_employment = "", "", "1900-01-01"

        todo_str = get_filter_list(todo_str_list, "Сотрудник_Key", units["ref_key"])
        period = datetime.datetime.strptime("1900-01-01", "%Y-%m-%d")
        if units["ref_key"] != "":
            moving = 0
            for items2 in todo_str:
                if (datetime.datetime.strptime(items2["ДействуетДо"][:10], "%Y-%m-%d") != datetime.datetime.strptime("0001-01-01", "%Y-%m-%d")) and (datetime.datetime.strptime(items2["ДействуетДо"][:10], "%Y-%m-%d") < datetime.datetime.today()):
                    continue
                    # Проверяем, если это дата временного перемещения, то если срок прощел, делаем пропуск цикла
                if items2["Active"] and items2["ВидСобытия"] == "Перемещение":
                    if period < datetime.datetime.strptime(
                        items2["Period"][:10], "%Y-%m-%d"
                    ):
                        period = datetime.datetime.strptime(
                            items2["Period"][:10], "%Y-%m-%d"
                        )
                        division_code = items2["Подразделение_Key"]
                        job_code = items2["Должность_Key"]
                        moving = 1

                if items2["Active"] and items2["ВидСобытия"] == "Прием":
                    date_of_employment = datetime.datetime.strptime(
                        items2["Period"][:10], "%Y-%m-%d"
                    )
                    if moving == 0:
                        division_code = items2["Подразделение_Key"]
                        job_code = items2["Должность_Key"]
            user_work_profile = {
                "date_of_employment": date_of_employment,
                "job": Job.objects.filter(ref_key=job_code).first()
                if job_code not in ["", "00000000-0000-0000-0000-000000000000"]
                else None,
                "divisions": Division.objects.filter(ref_key=division_code).first()
                if division_code not in ["", "00000000-0000-0000-0000-000000000000"]
                else None,
            }
            if units["ref_key"] in profile_list_items:
                user_work_profile["ref_key"] = units["ref_key"]
                profile_list_update.append(user_work_profile)
            else:
                obj, created = DataBaseUserWorkProfile.objects.update_or_create(
                    ref_key=units["ref_key"], defaults=user_work_profile
                )

                with transaction.atomic():
                    DataBaseUser.objects.filter(ref_key=units["ref_key"]).update(
                        user_work_profile=obj
                    )
    with transaction.atomic():
        for item in profile_list_update:
            DataBaseUserWorkProfile.objects.filter(ref_key=item["ref_key"]).update(
                **item
            )

    return context


def get_type_of_employment(Ref_Key):
    data = get_jsons_data_filter(
        "Document", "ПриемНаРаботу", "Сотрудник_Key", Ref_Key, 0, 0, True, True
    )
    match len(data["value"]):
        case 0:
            return False
        case 1:
            if data["value"][0]["ВидЗанятости"] in ["ОсновноеМестоРаботы", "Совместительство"]:
                return True
        case _:
            for item in data["value"]:
                if (
                    item["ВидЗанятости"]  in ["ОсновноеМестоРаботы", "Совместительство"]
                    and item["ИсправленныйДокумент_Key"]
                    != "00000000-0000-0000-0000-000000000000"
                ):
                    return True
    return False


def get_filter_list(filter_list, variable, meaning):
    """
    Поиск элементов в списке словарей
    :param filter_list: Список значений
    :param variable: Ключ
    :param meaning: Значение
    :return: Вывод первого элемента списка в случае если поиск завершился успешно, иначе False
    """
    result = list(
        filter(lambda item_filter: item_filter[variable] == meaning, filter_list)
    )
    return result[0] if len(result) == 1 else False


def get_database_user():
    # ДУБЛИКАТ имеется в tasks.py
    count = DataBaseUser.objects.all().count() + 1
    staff = get_jsons_data_filter(
        "Catalog", "Сотрудники", "ВАрхиве", "false", 0, 0, False, False
    )
    individuals = get_jsons_data("Catalog", "ФизическиеЛица", 0)
    insurance_policy = get_jsons_data(
        "InformationRegister", "ПолисыОМСФизическихЛиц", 0
    )
    staff_set = set()
    for item in staff["value"]:
        if item["Description"] != "":
            staff_set.add(item["Ref_Key"])
    users_set = set()
    for item in DataBaseUser.objects.all().exclude(is_ppa=True):
        users_set.add(item.ref_key)
    users_set &= staff_set  # Есть везде
    staff_set -= users_set
    staff_set_list = list()  # Нет в системе
    for unit in list(staff_set):
        if get_type_of_employment(unit):
            staff_set_list.append(unit)
    personal_kwargs_list, divisions_kwargs_list = list(), list()
    # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
    for item in staff["value"]:
        if item["Description"] != "":
            (
                last_name,
                surname,
                birthday,
                gender,
                email,
                telephone,
                address,
            ) = (
                "",
                "",
                "1900-01-01",
                "",
                "",
                "",
                "",
            )
            find_item = get_filter_list(
                individuals["value"], "Ref_Key", item["ФизическоеЛицо_Key"]
            )
            if not find_item:
                continue
            Ref_Key = find_item["Ref_Key"]
            username = (
                "0" * (4 - len(str(count)))
                + str(count)
                + "_"
                + transliterate(find_item["Фамилия"]).lower()
                + "_"
                + transliterate(find_item["Имя"]).lower()[:1]
                + transliterate(find_item["Отчество"]).lower()[:1]
            )
            first_name = find_item["Имя"]
            last_name = find_item["Фамилия"]
            surname = find_item["Отчество"]
            gender = "male" if find_item["Пол"] == "Мужской" else "female"
            birthday = datetime.datetime.strptime(
                find_item["ДатаРождения"][:10], "%Y-%m-%d"
            )
            for item3 in find_item["КонтактнаяИнформация"]:
                if item3["Тип"] == "АдресЭлектроннойПочты":
                    email = item3["АдресЭП"]
                if item3["Тип"] == "Телефон":
                    telephone = "+" + item3["НомерТелефона"]
                if item3["Тип"] == "Адрес":
                    address = item3["Представление"]
            insurance_item = get_filter_list(
                insurance_policy["value"],
                "ФизическоеЛицо_Key",
                item["ФизическоеЛицо_Key"],
            )
            oms = insurance_item["НомерПолиса"] if insurance_item else ""
            personal_kwargs = {
                "inn": find_item["ИНН"],
                "snils": find_item["СтраховойНомерПФР"],
                "oms": oms,
            }

            divisions_kwargs = {
                "person_ref_key": Ref_Key,
                "service_number": item["Code"],
                "first_name": first_name,
                "last_name": last_name,
                "surname": surname,
                "birthday": birthday,
                "type_users": "staff_member",
                "gender": gender,
                "email": email,
                "personal_phone": telephone[:12],
                "address": address,
            }
            count += 1
            if item["Ref_Key"] in staff_set_list:
                try:
                    main_obj_item, main_created = DataBaseUser.objects.update_or_create(
                        ref_key=item["Ref_Key"], defaults={**divisions_kwargs}
                    )

                    if main_created:
                        main_obj_item.username = username
                except Exception as _ex:
                    logger.error(
                        f"Сохранение пользователя: {username}, {last_name} {first_name} {_ex}"
                    )
                try:
                    obj_item, created = DataBaseUserProfile.objects.update_or_create(
                        ref_key=item["Ref_Key"], defaults={**personal_kwargs}
                    )
                except Exception as _ex:
                    logger.error(f"Сохранение профиля пользователя: {_ex}")
                if not main_obj_item.user_profile:
                    try:
                        main_obj_item.user_profile = DataBaseUserProfile.objects.get(
                            ref_key=main_obj_item.ref_key
                        )
                        main_obj_item.save()
                    except Exception as _ex:
                        logger.error(
                            f"Сохранения профиля пользователя в модели пользователя: {_ex}"
                        )
            if item["Ref_Key"] in users_set:
                personal_kwargs["ref_key"] = item["Ref_Key"]
                divisions_kwargs["ref_key"] = item["Ref_Key"]
                personal_kwargs_list.append(personal_kwargs)
                divisions_kwargs_list.append(divisions_kwargs)
    from django.db import transaction

    with transaction.atomic():
        for item in divisions_kwargs_list:
            DataBaseUser.objects.filter(ref_key=item["ref_key"]).update(**item)
    with transaction.atomic():
        for item in personal_kwargs_list:
            DataBaseUserProfile.objects.filter(ref_key=item["ref_key"]).update(**item)


def get_identity_documents():
    """
    Получение паспортных данных сотрудника,
    :return: Найденную запись, или пустую строку
    """
    from django.db import transaction

    context = ""
    profile_list = DataBaseUserProfile.objects.all().values("ref_key")
    profile_list_items = list()
    for item in profile_list:
        profile_list_items.append(item["ref_key"])
    todo_str_list = list()
    todo_str = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДокументыФизическихЛиц?$format=application/json;odata=nometadata",
        0,
    )
    for item in todo_str["value"]:
        todo_str_list.append(item)

    def get_filter_list(filter_list, variable, meaning):
        return list(
            filter(lambda item_filter: item_filter[variable] == meaning, filter_list)
        )

    users_list = (
        DataBaseUser.objects.all().exclude(is_active=False)
        .exclude(is_superuser=True, is_ppa=True)
        .values("ref_key", "person_ref_key")
    )
    citizenship = Citizenships.objects.filter(city="Российская Федерация").first()
    for units in users_list:
        ref_key, series, number, issued_by_whom, date_of_issue, division_code = (
            "",
            "",
            "",
            "",
            "1900-01-01",
            "",
        )
        view_description = ""

        period = datetime.datetime.strptime("1900-01-01", "%Y-%m-%d")
        if units["person_ref_key"] != "":
            user_identity_documents = {}
            register = get_filter_list(
                todo_str_list, "Физлицо_Key", units["person_ref_key"]
            )
            for items in register:
                if items["ВидДокумента_Key"] == "ebbd9c1f-cfaf-11e6-bad8-902b345cadc2":
                    if period < datetime.datetime.strptime(
                        items["ДатаВыдачи"][:10], "%Y-%m-%d"
                    ):
                        period = datetime.datetime.strptime(
                            items["ДатаВыдачи"][:10], "%Y-%m-%d"
                        )
                        view_description = item["Представление"]
                        series = items["Серия"]
                        number = items["Номер"]
                        issued_by_whom = items["КемВыдан"]
                        date_of_issue = datetime.datetime.strptime(
                            items["ДатаВыдачи"][:10], "%Y-%m-%d"
                        )
                        division_code = items["КодПодразделения"]

            user_identity_documents = {
                "series": series,
                "number": number,
                "issued_by_whom": issued_by_whom,
                "date_of_issue": date_of_issue,
                "division_code": division_code,
            }
            main_obj_item, main_created = IdentityDocuments.objects.update_or_create(
                ref_key=units["ref_key"], defaults=user_identity_documents
            )
            with transaction.atomic():
                if view_description.find("Паспорт гражданина РФ") == 0:
                    DataBaseUserProfile.objects.filter(ref_key=units["ref_key"]).update(
                        passport=main_obj_item, citizenship=citizenship
                    )
                else:
                    DataBaseUserProfile.objects.filter(ref_key=units["ref_key"]).update(
                        passport=main_obj_item
                    )

    return context


def get_chart_of_calculation_types(select_uuid):
    """
    :param select_uuid: The UUID used to select the specific Chart of Calculation Type.
    :return: The description of the selected Chart of Calculation Type.
    """
    todo_str = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/ChartOfCalculationTypes_Начисления?$format=application/json;odata=nometadata&$filter=Ref_Key%20eq%20guid%27{select_uuid}%27&$select=Description",
        0,
    )
    result = ""
    try:
        for item in todo_str["value"]:
            result = item["Description"]
    except Exception as _ex:
        pass
    return result


def get_worked_out_by_the_workers(
    selected_month, selected_year, users_uuid, calculation_uud
) -> list:
    acc_reg_time = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ОтработанноеВремяПоСотрудникам_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27%20and%20Начисление_Key%20eq%20guid%27{calculation_uud}%27",
        0,
    )
    days_worked, hours_worked, paid_days = "", "", ""
    try:
        for item in acc_reg_time["value"]:
            days_worked = item["ОтработаноДней"]
            hours_worked = item["ОтработаноЧасов"]
            paid_days = item["ОплаченоДней"]
    except Exception as _ex:
        pass
    result = [days_worked, hours_worked, paid_days]
    return result


def get_report_card_table(
    data_dict, total_score, first_day, last_day, user_start, user_end
):  # , user_start_time, user_end_time
    """

    :param data_dict: {'сотрудник': [r1-Дата, r2-Начало, r3-Окончание, r4-Знак, r5-Скалярное общее время за день,
                                      r6-Начало по графику, r7-Окончание по графику, r8-Тип записи,
                                      r9-Было ли объединение интервалов, r10-Текущий интервал, r11-Общее за день]}
    :param total_score:
    :param first_day: Первый день запрашиваемого периода
    :param last_day: Последний день запрашиваемого периода
    :return:
    """
    html_obj = f"""<table class="table table-ecommerce-simple mb-0" id="datatable-ecommerce-list"
                                   style="min-width: 300px; display: block; height: 600px; overflow: auto;">
                        <tbody>
                            
                            <tr>
                                <td colspan="4">За период с: {first_day.strftime('%d-%m-%Y')} по: {last_day.strftime('%d-%m-%Y')}</td>
                            </tr>
                            <tr>
                                <td colspan="4">Ваше рабочее время с {user_start.strftime('%H:%M')} по {user_end.strftime('%H:%M')}</td>
                            </tr>"""
    for key in data_dict:
        html_obj += f"""                        
                        <tr>
                            <th>Дата</th>
                            <th>+/-</th>                            
                            <th>Факт</th>
                            <th>Статус</th>
                        </tr>"""
        table_time = 0
        for r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12 in data_dict[key]:
            """r1-Дата, r2-Начало, r3-Окончание, r4-Знак, r5-Скалярное общее время за день, r6-Начало по графику,
            r7-Окончание по графику, r8-Тип записи, r9-Было ли объединение интервалов, r10-Текущий интервал, r11-Общее за день
            """
            if r1 <= datetime.datetime.today().date():
                if r8 not in [
                    "О",
                    "Б",
                    "М",
                ]:
                    table_time += r12
                start_time = timedelta_to_string(r2)
                if r10:
                    end_time = timedelta_to_string(r3)
                else:
                    end_time = timedelta_to_string("00:00:00")
                delta = timedelta_to_string(datetime.timedelta(seconds=r5))
                if r9:
                    style = "background-color: #b0ffd5"
                else:
                    if r8 == "Р":
                        style = "color: red"
                    elif r8 == "В":
                        style = "color: #afafaf"
                    elif r8 == "О":
                        style = "color: #0c00ad"
                    else:
                        style = "color: #000000"
                html_obj += f"""<tr style="{style}">
                                    <td>{r1.strftime('%d')}</td>"""
                if r10:
                    html_obj += f"""<td><span style="{' color: #ff0000;' if r4 == '-' else ''}">{r4}{delta}</span></td>"""
                else:
                    html_obj += f"""<td><span> --//-- </span></td>"""
                if r10:
                    html_obj += f"""<td>{start_time}-{end_time}</td>"""
                else:
                    html_obj += f"""<td>{start_time}-по н.в.</td>"""
                if r8 == "Р":
                    html_obj += f"""<td>Н</td></tr>"""
                else:
                    html_obj += f"""<td>{r8}</td></tr>"""
        table_time_delta = total_score - table_time
        html_obj += f"""
                         <tr>
                            <th>Итого:</th>
                            <th><span style="{' color: #ff0000;' if table_time_delta < 0 else ''}">{'-' if table_time_delta < 0 else ''}{datetime.timedelta(seconds=abs(table_time_delta))}</span></th>
                            <th></th>
                            <th></th>
                            <th></th>
                            </tr>"""

    html_obj += f"""
        </tbody>
    </table>     
    """
    return html_obj


def get_settlement_sheet(selected_month, selected_year, users_uuid):
    """
    Получение расчетного листка сотрудника,
    :return: Найденную запись, или пустую строку
    """
    ref_key = ""
    series = ""
    number = ""
    issued_by_whom = ""
    date_of_issue = "1900-01-01"
    division_code = ""
    acc_reg_acc = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_НачисленияУдержанияПоСотрудникам_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27",
        0,
    )
    # Поля Active = True, ФизическоеЛицо_Key = uuid, Начисление_Key = uuid, ОтработаноДней, ОтработаноЧасов, ОплаченоДней, ОплаченоЧасов, ГруппаНачисленияУдержанияВыплаты = Выплачено
    acc_reg_set = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ВзаиморасчетыССотрудниками_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27%20and%20ГруппаНачисленияУдержанияВыплаты%20eq%20%27Выплачено%27",
        0,
    )
    print(acc_reg_acc, acc_reg_set)
    # Поля Active = True, ФизическоеЛицо_Key = uuid, СтатьяРасходов_Key = uuid, СуммаВзаиморасчетов, ГруппаНачисленияУдержанияВыплаты = Выплачено, Recorder = uuid, Recorder_Type = Document_ВедомостьНаВыплатуЗарплатыВКассу или Document_ВедомостьНаВыплатуЗарплатыВБанк
    # f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/{Recorder_Type}?$format=application/json;odata=nometadata&$filter=Состав/any(d:%20d/Ref_Key%20eq%20guid%27{Recorder}%27)&$select=Number,%20Date"
    period = datetime.datetime.strptime(
        f"{selected_year}-{selected_month}-01", "%Y-%m-%d"
    )
    data_positive = list()
    data_negative = list()
    data_paid = list()
    positive = 0
    negative = 0
    paid = 0
    result_positive = dict()
    result_negative = dict()
    result_paid = dict()
    for items in acc_reg_acc["value"]:
        if (
            period == datetime.datetime.strptime(items["Period"][:10], "%Y-%m-%d")
            and items["Active"]
        ):
            work_time = get_worked_out_by_the_workers(
                selected_month, selected_year, users_uuid, items["НачислениеУдержание"]
            )
            if items["ГруппаНачисленияУдержанияВыплаты"] == "Начислено":
                result_positive = {
                    "description": get_chart_of_calculation_types(
                        items["НачислениеУдержание"]
                    ),
                    "days_worked": work_time[0] if work_time[0] != 0 else "",
                    "hours_worked": work_time[1] if work_time[1] != 0 else "",
                    "paid_days": work_time[2] if work_time[2] != 0 else "",
                    "summ": "{:.2f}".format(items["Сумма"]),
                }
                data_positive.append(result_positive)
            else:
                result_negative = {
                    "description": items["НачислениеУдержание"],
                    "summ": "{:.2f}".format(items["Сумма"]),
                }
                data_negative.append(result_negative)
            if items["ГруппаНачисленияУдержанияВыплаты"] == "Начислено":
                try:
                    positive += float(items["Сумма"])
                except Exception as _ex:
                    pass
            else:
                try:
                    negative += float(items["Сумма"])
                except Exception as _ex:
                    pass
    for items in acc_reg_set["value"]:
        result_paid = {
            "document": items["ВидВзаиморасчетов"],
            "summ": "{:.2f}".format(items["СуммаВзаиморасчетов"]),
        }
        paid += float(items["СуммаВзаиморасчетов"])
        data_paid.append(result_paid)
    accrued_table_set = ""
    withheld_table_set = ""
    paid_table_set = ""
    accrued_table_set_list = ""
    for count in data_positive:
        accrued_table_set_list += "<tr>"
        for key in count:
            if key == "summ":
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            elif key in ["days_worked", "hours_worked", "paid_days"]:
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">{count[key]}</td>'
            else:
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        accrued_table_set_list += "</tr>"

    withheld_table_set_list = ""
    for count in data_negative:
        withheld_table_set_list += "<tr>"
        for key in count:
            if key == "summ":
                withheld_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            else:
                withheld_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        withheld_table_set_list += "</tr>"
    paid_table_set_list = ""
    for count in data_paid:
        paid_table_set_list += "<tr>"
        for key in count:
            if key == "summ":
                paid_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            else:
                paid_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        paid_table_set_list += "</tr>"
    html_obj = list()
    accrued_table_set = f"""<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a"><thead>
    <tr>
        <th rowspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
        <th colspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Рабочие</th>
        <th rowspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Оплачено</th>
        <th rowspan="2" width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
    </tr>
        <tr>
        <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Дни</th>
        <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Часы</th>
    </tr>
    </thead>
    <tbody>
    <tr><td colspan="4" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Начислено:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(positive)}</strong></span></td></tr>
    {accrued_table_set_list}
     </tbody>
     </table>"""
    withheld_table_set = f"""<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a">
    <thead>
        <tr>
            <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
            <th width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
        </tr>
    </thead>
    <tbody>
         <tr><td colspan="1" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Удержано:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(negative)}</strong></span></td></tr>
    {withheld_table_set_list}
    </tbody>
    </table>"""
    paid_table_set = f"""<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a">
    <thead>
        <tr>
            <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
            <th width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
        </tr>
    </thead>
    <tbody>
         <tr><td colspan="1" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Выплачено:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(paid)}</strong></span></td></tr>
    {paid_table_set_list}
    </tbody>
    </table>"""
    html_obj = [accrued_table_set, withheld_table_set, paid_table_set]
    return html_obj


def get_vacation_days(self, dates):
    date_admission, date_admission_correct, vacation = get_json_vacation(
        self.request.user.ref_key
    )
    days = 0
    for item in vacation["value"]:
        if item["Active"] and not item["Компенсация"]:
            """
            "Ref_Key": "ebbd9c67-cfaf-11e6-bad8-902b345cadc2" - Основной
            --------------------------------------------------------------------------------------------------------------------
            "Ref_Key": "dd940e62-cfaf-11e6-bad8-902b345cadc2" - Отпуск за свой счет
            "Ref_Key": "b51bdb10-8fb9-11e9-80cc-309c23d346b4" - Дополнительный оплачиваемый отпуск пострадавшим на ЧАЭС
            "Ref_Key": "c3e8c3e8-cfb6-11e6-bad8-902b345cadc2" - Дополнительный неоплачиваемый отпуск пострадавшим на ЧАЭС
            "Ref_Key": "c3e8c3e7-cfb6-11e6-bad8-902b345cadc2" - Дополнительный учебный отпуск (оплачиваемый)
            "Ref_Key": "dd940e63-cfaf-11e6-bad8-902b345cadc2" - Дополнительный учебный отпуск без оплаты
            "Ref_Key": "6f4631a7-df12-11e6-950a-0cc47a7917f4" - Дополнительный отпуск КЛО, ЗКЛО, начальник ИБП
            "Ref_Key": "56f643c6-bf49-11e9-a3dc-0cc47a7917f4" - Дополнительный оплачиваемый отпуск пострадавшим в аварии на ЧАЭС
            "Ref_Key": "dd940e60-cfaf-11e6-bad8-902b345cadc2" - Дополнительный ежегодный отпуск

            """
            exclude_vacation = [
                "dd940e62-cfaf-11e6-bad8-902b345cadc2",
                "b51bdb10-8fb9-11e9-80cc-309c23d346b4",
                "c3e8c3e8-cfb6-11e6-bad8-902b345cadc2",
                "c3e8c3e7-cfb6-11e6-bad8-902b345cadc2",
                "dd940e63-cfaf-11e6-bad8-902b345cadc2",
                "6f4631a7-df12-11e6-950a-0cc47a7917f4",
                "56f643c6-bf49-11e9-a3dc-0cc47a7917f4",
                "dd940e60-cfaf-11e6-bad8-902b345cadc2",
            ]
            if item["ВидЕжегодногоОтпуска_Key"] not in exclude_vacation:
                if (
                    datetime.datetime.strptime(item["ДатаНачала"][:10], "%Y-%m-%d")
                    > date_admission
                ):
                    days += int(item["Количество"])

    dates = [
        dt
        for dt in rrule.rrule(
            rrule.MONTHLY,
            dtstart=date_admission_correct,
            until=datetime.datetime.strptime(dates, "%Y-%m-%d"),
        )
    ]
    print(((len(dates) - 1) * (28 / 12)), days)
    return round(((len(dates) - 1) * (28 / 12)) - days)

