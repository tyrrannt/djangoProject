"""
Сервисный слой для работы с фоновыми задачами Celery.
Вся бизнес-логика (парсинг, обращения к API, сложные выборки БД) выносится сюда.
Задачи из tasks.py должны лишь вызывать функции из этого файла.
"""
import calendar
import datetime
import json
from collections import defaultdict
from typing import Dict, Any, List, Optional, Union

from dateutil import rrule
from dateutil.relativedelta import relativedelta
import pandas as pd
import requests
from decouple import config
from django.db import transaction
from django.db.models import Q

from core import logger
from administration_app.utils import (
    get_jsons_data_filter, get_jsons_data_filter2, get_jsons_data,
    get_date_interval, transliterate, adjust_time, process_group_year
)
from customers_app.models import DataBaseUser, DataBaseUserProfile, VacationScheduleList, VacationSchedule
from hrdepartment_app.models import ReportCard, WeekendDay, check_day, ProductionCalendar, get_norm_time_at_custom_day


def bulk_upsert_report_cards(to_create: List[ReportCard]):
    """
    Массовое добавление/обновление ReportCard,
    без использования update_conflicts/conflict_target.
    """
    if not to_create:
        return

    lookup_keys = ["report_card_day", "doc_ref_key", "employee"]
    key_tuples = {
        (getattr(obj, lookup_keys[0]),
         getattr(obj, lookup_keys[1]),
         getattr(obj, lookup_keys[2]))
        for obj in to_create
    }

    existing = ReportCard.objects.filter(
        **{
            f"{lookup_keys[0]}__in": [key[0] for key in key_tuples],
            f"{lookup_keys[1]}__in": [key[1] for key in key_tuples],
            f"{lookup_keys[2]}__in": [key[2] for key in key_tuples],
        }
    )

    existing_keys = {
        (e.report_card_day, e.doc_ref_key, e.employee): e
        for e in existing
    }

    to_insert = []
    to_update = []

    for obj in to_create:
        key = (obj.report_card_day, obj.doc_ref_key, obj.employee)
        if key in existing_keys:
            db_obj = existing_keys[key]
            db_obj.employee = obj.employee
            db_obj.rec_no = obj.rec_no
            db_obj.record_type = obj.record_type
            db_obj.reason_adjustment = obj.reason_adjustment
            db_obj.start_time = obj.start_time
            db_obj.end_time = obj.end_time
            to_update.append(db_obj)
        else:
            to_insert.append(obj)

    with transaction.atomic():
        if to_insert:
            ReportCard.objects.bulk_create(to_insert, batch_size=500)
        if to_update:
            ReportCard.objects.bulk_update(
                to_update,
                fields=[
                    "employee", "rec_no", "record_type",
                    "reason_adjustment", "start_time", "end_time"
                ],
                batch_size=500
            )


def process_sick_leave(year: int, trigger: int) -> Dict[str, Any]:
    """
    Получение неявок на рабочее место из 1С ЗУП.
    """
    config_map = {
        1: {
            "url": f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27Болезнь%27",
            "trigger_type": "StandardODATA.Document_БольничныйЛист",
            "record_type": "16"
        },
        2: {
            "url": f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20ВидВремени_Key%20eq%20guid%27e58f3899-3c5b-11ea-a186-0cc47a7917f4%27",
            "trigger_type": "StandardODATA.Document_ОплатаПоСреднемуЗаработку",
            "record_type": "17"
        },
        3: {
            "url": f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27ДополнительныеВыходныеДниНеоплачиваемые%27",
            "trigger_type": "StandardODATA.Document_Отгул",
            "record_type": "20"
        }
    }

    if trigger not in config_map:
        logger.error(f"Неизвестный триггер: {trigger}")
        return {"error": f"Неизвестный триггер: {trigger}"}

    source_url = config_map[trigger]["url"]
    trigger_type = config_map[trigger]["trigger_type"]
    record_type = config_map[trigger]["record_type"]

    # Исключения requests будут обработаны в Celery Task (raise self.retry)
    response = requests.get(
        source_url,
        auth=(config("HRM_LOGIN"), config("HRM_PASS")),
        timeout=10
    )
    response.raise_for_status()
    dt = response.json()
    
    rec_number_count = 0
    users = {user.ref_key: user for user in DataBaseUser.objects.filter(is_active=True).only("ref_key", "id")}

    doc_ref_keys = set(
        item["ДокументОснование"]
        for item in dt.get("value", [])
        if item["Recorder_Type"] == trigger_type and item.get("Active", False)
    )

    existing_reportcards = ReportCard.objects.filter(doc_ref_key__in=doc_ref_keys)
    existing_by_doc = defaultdict(set)
    for rc in existing_reportcards:
        existing_by_doc[rc.doc_ref_key].add(rc.report_card_day)

    to_create = []
    to_delete = []

    for item in dt.get("value", []):
        if item["Recorder_Type"] != trigger_type or not item.get("Active", False):
            continue

        doc_key = item["ДокументОснование"]
        employee_key = item["Сотрудник_Key"]
        user_obj = users.get(employee_key)

        if not user_obj:
            logger.error(f"{employee_key} не найден в базе данных")
            continue

        start_date = datetime.datetime.strptime(item["Начало"][:10], "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(item["Окончание"][:10], "%Y-%m-%d").date()
        interval = set(get_date_interval(start_date, end_date))

        existing_dates = existing_by_doc.get(doc_key, set())

        to_add = interval - existing_dates
        to_remove = existing_dates - interval

        if to_remove:
            to_delete.append({
                "doc_ref_key": doc_key,
                "days": to_remove
            })

        for date in sorted(to_add):
            rec_number_count += 1
            start_time, end_time, _ = check_day(
                date,
                datetime.time(9, 30),
                datetime.time(18, 0)
            )

            to_create.append(ReportCard(
                report_card_day=date,
                employee=user_obj,
                rec_no=rec_number_count,
                doc_ref_key=doc_key,
                record_type=record_type,
                reason_adjustment="Запись введена автоматически из 1С ЗУП",
                start_time=start_time,
                end_time=end_time
            ))

    with transaction.atomic():
        for entry in to_delete:
            ReportCard.objects.filter(
                doc_ref_key=entry["doc_ref_key"],
                report_card_day__in=entry["days"]
            ).delete()
        if to_create:
            bulk_upsert_report_cards(to_create)

    return {"status": "success", "count": rec_number_count}


def process_report_card_daily(year: int = 0, month: int = 0, day: int = 0):
    """
    Загрузка табеля из системы учета рабочего времени за день.
    """
    if year == 0 and month == 0 and day == 0:
        current_data = datetime.datetime.today().date()
    else:
        current_data = datetime.date(year, month, day)
        
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
    
    # Сетевые исключения обрабатываются через retry в задаче
    response = requests.get(url, auth=("proxmox", "PDO#rLv@Server"), timeout=10)
    response.raise_for_status()
    dicts = response.json()

    # Предзагрузка активных пользователей в словарь
    users = DataBaseUser.objects.filter(is_active=True).only("last_name", "first_name", "surname")
    users_dict = {
        f"{u.last_name} {u.first_name} {u.surname}": u 
        for u in users 
        if u.last_name and u.first_name and u.surname
    }

    report_cards_to_create = []

    with transaction.atomic():
        # Удаляем старые записи за этот день (record_type="1")
        ReportCard.objects.filter(
            report_card_day=current_data,
            record_type="1"
        ).delete()

        for item in dicts.get("data", []):
            usr_fullname = item.get("FULLNAME", "")
            current_intervals = True if item.get("ISGO") == "0" else False
            
            try:
                start_time = datetime.datetime.strptime(item["STARTTIME"], "%d.%m.%Y %H:%M:%S").time()
                end_time = datetime.datetime.strptime(item["ENDTIME"], "%d.%m.%Y %H:%M:%S").time() if current_intervals else datetime.time(0, 0)
                rec_no = int(item.get("rec_no", 0))
            except (ValueError, KeyError) as e:
                logger.error(f"Data parse error for user {usr_fullname}: {e}")
                continue

            user_obj = users_dict.get(usr_fullname)
            if not user_obj:
                logger.error(f"{usr_fullname} не найден в базе данных")
                continue

            report_cards_to_create.append(ReportCard(
                report_card_day=current_data,
                employee=user_obj,
                rec_no=rec_no,
                start_time=start_time,
                end_time=end_time,
                record_type="1",
                current_intervals=current_intervals,
            ))

        if report_cards_to_create:
            # bulk_create будет достаточно, так как мы предварительно удалили записи.
            ReportCard.objects.bulk_create(report_cards_to_create, batch_size=500)

    return {"status": "success", "count": len(report_cards_to_create)}


def process_vacation_check():
    """
    Синхронизация графика отпусков.
    """
    VACATION_TYPE = {
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

    # Массовое удаление старых записей
    VacationSchedule.objects.all().delete()
    
    # Предзагрузка пользователей для быстрого поиска
    users_dict = {user.ref_key: user for user in DataBaseUser.objects.filter(is_active=True).only("ref_key", "id")}

    vacation_lists = VacationScheduleList.objects.all()
    all_vacation_list = []

    for vacation in vacation_lists:
        graph_vacacion = get_jsons_data_filter(
            "Document", "ГрафикОтпусков", "Number", vacation.document_number, 0, 0, False, True
        )
        if not graph_vacacion or not graph_vacacion.get("value") or not graph_vacacion["value"][0].get("Сотрудники"):
            continue

        for item in graph_vacacion["value"][0]["Сотрудники"]:
            ref_key = item.get("Сотрудник_Key")
            user_obj = users_dict.get(ref_key)
            if not user_obj:
                continue

            try:
                vacation_type_key = item.get("ВидОтпуска_Key")
                kwargs_obj = VacationSchedule(
                    employee=user_obj,
                    start_date=datetime.datetime.strptime(item["ДатаНачала"][:10], "%Y-%m-%d"),
                    end_date=datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d"),
                    type_vacation=vacation_type_key if vacation_type_key in VACATION_TYPE else vacation_type_key,
                    days=item.get("КоличествоДней", 0),
                    years=vacation.document_year,
                    comment=item.get("Примечание", ""),
                )
                all_vacation_list.append(kwargs_obj)
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Error parsing vacation data for user {user_obj}: {e}")
                continue

    objs_created = 0
    with transaction.atomic():
        if all_vacation_list:
            objs = VacationSchedule.objects.bulk_create(all_vacation_list, batch_size=500)
            objs_created = len(objs)
            
    logger.info(f"Создано {objs_created} записей графика отпусков")
    return {"status": "success", "count": objs_created}


def process_save_report():
    """
    Формирование и сохранение CSV отчета табеля.
    """
    type_of_report = {
        1: "Явка",
        2: "Отпуск",
        3: "Дополнительный ежегодный отпуск",
        4: "Отпуск за свой счет",
        5: "Дополнительный учебный отпуск",
        6: "Отпуск по уходу за ребенком",
        7: "Дополнительный неоплачиваемый отпуск",
        8: "Отпуск по беременности и родам",
        9: "Отпуск без оплаты согласно ТК РФ",
        10: "Дополнительный отпуск",
        11: "Дополнительный оплачиваемый отпуск",
        12: "Основной",
        13: "Ручной ввод",
        14: "Служебная поездка",
        15: "Командировка",
        16: "Больничный",
        17: "Мед осмотр",
        18: "График отпусков",
        19: "Отпуск на санаторно курортное лечение",
        20: "Отгул",
    }
    fields = ["user", "date", "start", "end", "type", "manual_input", "reason"]
    dates = ReportCard.objects.exclude(employee=None).select_related('employee')
    report_card_list = [
        [
            report_record.employee.title, 
            report_record.report_card_day, 
            report_record.start_time,
            report_record.end_time, 
            report_record.record_type, 
            report_record.manual_input,
            report_record.reason_adjustment
        ] 
        for report_record in dates
    ]
    df = pd.DataFrame.from_records(report_card_list, columns=fields)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df["start"] = pd.to_datetime(df["start"], format="%H:%M:%S")
    df["end"] = pd.to_datetime(df["end"], format="%H:%M:%S")
    df["type"] = pd.to_numeric(df["type"], errors='coerce').fillna(0).astype(int)
    df['types'] = df['type'].map(type_of_report)
    df.to_csv('dates.csv', sep=';', index=False, encoding='utf-8', na_rep='')
    return {"status": "success"}


def process_vacation_schedule(year=None):
    """
    Генерация и загрузка графика отпусков на год.
    """
    users = DataBaseUser.objects.filter(is_active=True).only("ref_key", "id")
    user_dict = {user.ref_key: user for user in users}

    if year:
        year = int(year)
    else:
        year = datetime.datetime.now().year

    try:
        vacation_schedule_item = VacationScheduleList.objects.get(document_year=year)
        vacation_schedule_number = vacation_schedule_item.document_number
    except VacationScheduleList.DoesNotExist:
        vacation_schedule_number = ""

    graph_vacacion = get_jsons_data_filter("Document", "ГрафикОтпусков", "Number", vacation_schedule_number, 0, 0,
                                           False, True)
    postponement_of_vacation = get_jsons_data_filter("Document", "ПереносОтпуска", "year(ИсходнаяДатаНачала)",
                                                     str(year), 0, 0, False, False)

    postponement_dict = {}
    for unit in postponement_of_vacation.get("value", []):
        key = unit["Сотрудник_Key"]
        postponement_dict.setdefault(key, []).append(unit)

    vacation_list = []
    if graph_vacacion and graph_vacacion.get("value") and graph_vacacion["value"][0].get("Сотрудники"):
        for item in graph_vacacion["value"][0]["Сотрудники"]:
            postponement_list = postponement_dict.get(item["Сотрудник_Key"], [])
            if not postponement_list:
                vacation_list.append(item)
                continue

            processed = False
            for unit in postponement_list:
                if unit["ИсходнаяДатаНачала"] == item["ДатаНачала"]:
                    for slice_element in unit.get("Переносы", []):
                        new_item = item.copy()
                        new_item.update({
                            "ДатаНачала": slice_element["ДатаНачала"],
                            "ДатаОкончания": slice_element["ДатаОкончания"],
                            "КоличествоДней": slice_element["КоличествоДней"],
                            "Примечание": f"Перенос отпуска №: {unit['Number']}",
                        })
                        vacation_list.append(new_item)
                        processed = True
            if not processed:
                vacation_list.append(item)

    with transaction.atomic():
        ReportCard.objects.filter(
            Q(report_card_day__year=year) & Q(record_type="18")
        ).delete()

        docs = graph_vacacion["value"][0]["Ref_Key"] if graph_vacacion and graph_vacacion.get("value") else ""
        report_card_list = []

        for item in vacation_list:
            if item["Сотрудник_Key"] not in user_dict:
                continue
            try:
                start_date = datetime.datetime.strptime(item["ДатаНачала"][:10], "%Y-%m-%d")
                usr_obj = user_dict[item["Сотрудник_Key"]]
                reason = item["Примечание"] if item.get("Примечание") else "График отпусков"
                days = int(item.get("КоличествоДней", 0))
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Error parsing vacation schedule item: {e}")
                continue

            for day in range(days):
                current_day = start_date + datetime.timedelta(days=day)
                report_card_list.append(ReportCard(
                    report_card_day=current_day,
                    employee=usr_obj,
                    start_time=datetime.time(0, 0),
                    end_time=datetime.time(0, 0),
                    record_type="18",
                    reason_adjustment=reason,
                    doc_ref_key=docs,
                ))

        batch_size = 1000
        objs_created = 0
        for i in range(0, len(report_card_list), batch_size):
            batch = report_card_list[i:i + batch_size]
            objs = ReportCard.objects.bulk_create(batch)
            objs_created += len(objs)

        logger.info(f"Создано {objs_created} записей (vacation schedule)")
    return {"status": "success", "count": objs_created}


def process_get_vacation(year: Optional[int] = None) -> Dict[str, Any]:
    """Синхронизирует фактические данные по отпускам сотрудников из 1С ЗУП в табель (ReportCard).

    Выполняет запрос в регистр сведений 1С ЗУП 'ДанныеОтпусковКарточкиСотрудника'
    за указанный год, сопоставляет периоды с учетом производственного календаря (WeekendDay),
    рабочих графиков сотрудников и формирует записи табеля (ReportCard) с помощью bulk_create.

    Args:
        year (Optional[int]): Год, за который выполняется синхронизация отпусков.
            Если не указан, берется текущий календарный год.

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            - status (str): Статус ('success' или 'error').
            - count (int): Количество созданных записей табеля.
            - year (int): Обработанный год.

    Raises:
        Exception: При критических ошибках синхронизации (перехватывается в Celery task).

    Example:
        >>> res = process_get_vacation(2026)
        >>> print(res["count"])
        154
    """
    type_of_report = {
        "2": "Ежегодный",
        "3": "Дополнительный ежегодный отпуск",
        "4": "Отпуск за свой счет",
        "5": "Дополнительный учебный отпуск (оплачиваемый)",
        "6": "Отпуск по уходу за ребенком",
        "7": "Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС",
        "8": "Отпуск по беременности и родам",
        "9": "Отпуск без оплаты согласно ТК РФ",
        "10": "Дополнительный отпуск",
        "11": "Дополнительный оплачиваемый отпуск пострадавшим в ",
        "12": "Основной",
        "19": "Отпуск на СКЛ (за счет ФСС)",
    }
    reverse_type_of_report = {v: k for k, v in type_of_report.items()}
    vacation_record_types = list(type_of_report.keys())

    exclude_list = ["proxmox", "shakirov"]
    if not year:
        year = datetime.datetime.today().year
    else:
        year = int(year)

    # 1. Предзагрузка активных пользователей вместе с рабочими профилями (1 запрос)
    users_qs = DataBaseUser.objects.filter(is_active=True).exclude(
        username__in=exclude_list
    ).select_related("user_work_profile")
    users_dict = {u.ref_key: u for u in users_qs if u.ref_key}

    # 2. Предзагрузка производственного календаря за смежные годы (1 запрос)
    weekend_qs = WeekendDay.objects.filter(
        weekend_day__year__gte=year - 1,
        weekend_day__year__lte=year + 1
    )
    holiday_dates_type1 = {w.weekend_day for w in weekend_qs if w.weekend_type == "1" and w.weekend_day}
    all_weekend_dates = {w.weekend_day for w in weekend_qs if w.weekend_day}

    # 3. Запрос данных из 1С OData (сначала пакетный за год, при необходимости fallback по сотрудникам)
    vacation_data = get_jsons_data_filter(
        "InformationRegister",
        "ДанныеОтпусковКарточкиСотрудника",
        "year(ДатаОкончания)",
        str(year),
        0,
        0,
        False,
        False
    )

    vacation_items = []
    if vacation_data and isinstance(vacation_data, dict) and vacation_data.get("value"):
        vacation_items = vacation_data["value"]
    else:
        # Fallback: опрос по каждому пользователю
        for ref_key in users_dict.keys():
            dt = get_jsons_data_filter2(
                "InformationRegister",
                "ДанныеОтпусковКарточкиСотрудника",
                "Сотрудник_Key",
                ref_key,
                "year(ДатаОкончания)",
                str(year),
                0,
                0,
            )
            if isinstance(dt, dict):
                for key in dt:
                    if isinstance(dt[key], list):
                        vacation_items.extend(dt[key])

    report_cards_to_create = []

    for item in vacation_items:
        ref_key = item.get("Сотрудник_Key")
        if not ref_key or ref_key not in users_dict:
            continue

        usr_obj = users_dict[ref_key]
        try:
            start_date_str = item.get("ДатаНачала", "")[:10]
            end_date_str = item.get("ДатаОкончания", "")[:10]
            if not start_date_str or not end_date_str:
                continue

            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

            start_d = start_date.date()
            end_d = end_date.date()

            # Подсчет праздничных дней (тип 1) в интервале отпуска
            weekend_count = sum(1 for d in holiday_dates_type1 if start_d <= d <= end_d)
            raw_days = int(item.get("КоличествоДней", 0))
            count_date = raw_days + weekend_count if raw_days > 0 else (end_d - start_d).days + 1

            period = list(rrule.rrule(rrule.DAILY, count=count_date, dtstart=start_date))
            local_weekend = {d for d in all_weekend_dates if start_d <= d <= end_d}

            view_type = item.get("ВидОтпускаПредставление", "")
            record_type = reverse_type_of_report.get(view_type)
            if not record_type:
                for code, name in type_of_report.items():
                    if name in view_type or view_type in name:
                        record_type = code
                        break
            if not record_type:
                record_type = "2"

            profile = getattr(usr_obj, "user_work_profile", None)
            sched_start = profile.personal_work_schedule_start if profile and profile.personal_work_schedule_start else datetime.time(8, 0)
            sched_end = profile.personal_work_schedule_end if profile and profile.personal_work_schedule_end else datetime.time(17, 0)

            reason = item.get("Основание", "") or "Отпуск"
            doc_ref_key = item.get("ДокументОснование", "")

            for unit in period:
                u_date = unit.date()
                if unit.weekday() in [0, 1, 2, 3] and u_date not in local_weekend:
                    start_time = sched_start
                    end_time = sched_end
                elif unit.weekday() == 4 and u_date not in local_weekend:
                    # В пятницу на 1 час короче
                    delta_time = datetime.timedelta(hours=sched_end.hour, minutes=sched_end.minute) - datetime.timedelta(hours=1)
                    start_time = sched_start
                    total_sec = max(0, int(delta_time.total_seconds()) % 86400)
                    end_time = datetime.time(total_sec // 3600, (total_sec % 3600) // 60, total_sec % 60)
                else:
                    start_time = datetime.time(0, 0)
                    end_time = datetime.time(0, 0)

                report_cards_to_create.append(ReportCard(
                    report_card_day=unit,
                    employee=usr_obj,
                    start_time=start_time,
                    end_time=end_time,
                    record_type=record_type,
                    reason_adjustment=reason,
                    doc_ref_key=doc_ref_key,
                ))

        except Exception as e:
            logger.error(f"Ошибка парсинга отпуска для {usr_obj}: {e}")

    # 4. Атомарная замена записей отпусков за год
    with transaction.atomic():
        ReportCard.objects.filter(
            report_card_day__year=year,
            record_type__in=vacation_record_types
        ).delete()

        batch_size = 1000
        objs_created = 0
        for i in range(0, len(report_cards_to_create), batch_size):
            batch = report_cards_to_create[i:i + batch_size]
            objs = ReportCard.objects.bulk_create(batch)
            objs_created += len(objs)

    logger.info(f"Синхронизация отпусков ({year} год) завершена. Создано записей: {objs_created}")
    return {"status": "success", "count": objs_created, "year": year}


def get_type_of_employment(ref_key: str) -> bool:
    """Проверяет вид занятости сотрудника по документу 'ПриемНаРаботу' в 1С ЗУП.

    Args:
        ref_key (str): Уникальный GUID сотрудника в 1С.

    Returns:
        bool: True, если сотрудник принят на основное место работы или по совместительству, иначе False.
    """
    try:
        data = get_jsons_data_filter(
            "Document", "ПриемНаРаботу", "Сотрудник_Key", ref_key, 0, 0, True, True
        )
        if not data or not isinstance(data, dict) or not data.get("value"):
            return False

        val_list = data["value"]
        if len(val_list) == 1:
            return val_list[0].get("ВидЗанятости") in ["ОсновноеМестоРаботы", "Совместительство"]
        else:
            for item in val_list:
                if (
                    item.get("ВидЗанятости") in ["ОсновноеМестоРаботы", "Совместительство"]
                    and item.get("ИсправленныйДокумент_Key") != "00000000-0000-0000-0000-000000000000"
                ):
                    return True
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки вида занятости для {ref_key}: {e}")
        return False


def process_sync_database_users() -> Dict[str, Any]:
    """Синхронизирует справочник сотрудников и физлиц из 1С ЗУП с DataBaseUser и DataBaseUserProfile.

    Выгружает актуальный список сотрудников (Каталог 'Сотрудники'), физических лиц (Каталог 'ФизическиеЛица')
    и полисы ОМС (Регистр 'ПолисыОМСФизическихЛиц') из 1С ЗУП.
    - Для существующих сотрудников выполняет массовое пакетное обновление через bulk_update.
    - Для новых принятых сотрудников создает учетную запись и профиль.

    Returns:
        Dict[str, Any]: Результаты синхронизации:
            - status (str): Статус ('success').
            - updated_users (int): Количество обновленных пользователей.
            - updated_profiles (int): Количество обновленных профилей.
            - created_users (int): Количество созданных новых сотрудников.

    Raises:
        Exception: При ошибках взаимодействия с 1С (перехватывается в Celery task).
    """
    count = DataBaseUser.objects.all().count() + 1

    staff = get_jsons_data_filter("Catalog", "Сотрудники", "ВАрхиве", "false", 0, 0, False, False)
    individuals = get_jsons_data("Catalog", "ФизическиеЛица", 0)
    insurance_policy = get_jsons_data("InformationRegister", "ПолисыОМСФизическихЛиц", 0)

    staff_list = staff.get("value", []) if isinstance(staff, dict) else []
    individuals_list = individuals.get("value", []) if isinstance(individuals, dict) else []
    insurance_list = insurance_policy.get("value", []) if isinstance(insurance_policy, dict) else []

    # 1. Построение словарей для мгновенного поиска O(1)
    individuals_dict = {
        item["Ref_Key"]: item for item in individuals_list if item.get("Ref_Key")
    }
    insurance_dict = {
        item["ФизическоеЛицо_Key"]: item.get("НомерПолиса", "")
        for item in insurance_list if item.get("ФизическоеЛицо_Key")
    }

    # 2. Анализ сотрудников в 1С и в Django
    staff_set = {item["Ref_Key"] for item in staff_list if item.get("Description") and item.get("Ref_Key")}
    existing_users_qs = DataBaseUser.objects.all().exclude(is_ppa=True)
    existing_users_dict = {u.ref_key: u for u in existing_users_qs if u.ref_key}
    existing_profiles_dict = {p.ref_key: p for p in DataBaseUserProfile.objects.all() if p.ref_key}

    users_set = set(existing_users_dict.keys()) & staff_set
    new_staff_keys = staff_set - users_set

    # 3. Фильтрация новых сотрудников по типу занятости
    staff_set_list = set()
    for unit_key in new_staff_keys:
        if get_type_of_employment(unit_key):
            staff_set_list.add(unit_key)

    users_to_bulk_update = []
    profiles_to_bulk_update = []
    created_users_count = 0

    for item in staff_list:
        ref_key = item.get("Ref_Key")
        if not ref_key or item.get("Description") == "":
            continue

        person_key = item.get("ФизическоеЛицо_Key")
        find_item = individuals_dict.get(person_key)
        if not find_item:
            continue

        first_name = find_item.get("Имя", "")
        last_name = find_item.get("Фамилия", "")
        surname = find_item.get("Отчество", "")
        gender = "male" if find_item.get("Пол") == "Мужской" else "female"

        raw_birthday = find_item.get("ДатаРождения", "")[:10]
        try:
            birthday = datetime.datetime.strptime(raw_birthday, "%Y-%m-%d").date() if raw_birthday else None
        except Exception:
            birthday = None

        email = ""
        telephone = ""
        address = ""
        for contact in find_item.get("КонтактнаяИнформация", []):
            contact_type = contact.get("Тип")
            if contact_type == "АдресЭлектроннойПочты":
                email = contact.get("АдресЭП", "")
            elif contact_type == "Телефон":
                raw_tel = contact.get("НомерТелефона", "")
                telephone = ("+" + raw_tel) if raw_tel else ""
            elif contact_type == "Адрес":
                address = contact.get("Представление", "")

        oms = insurance_dict.get(person_key, "")
        inn = find_item.get("ИНН", "")
        snils = find_item.get("СтраховойНомерПФР", "")

        personal_kwargs = {
            "inn": inn,
            "snils": snils,
            "oms": oms,
        }

        divisions_kwargs = {
            "person_ref_key": person_key,
            "service_number": item.get("Code", ""),
            "first_name": first_name,
            "last_name": last_name,
            "surname": surname,
            "birthday": birthday,
            "type_users": "staff_member",
            "gender": gender,
            "email": email,
            "personal_phone": telephone[:12] if telephone else "",
            "address": address,
        }

        # Создание новых сотрудников
        if ref_key in staff_set_list:
            username = (
                "0" * (4 - len(str(count)))
                + str(count)
                + "_"
                + transliterate(last_name).lower()
                + "_"
                + transliterate(first_name).lower()[:1]
                + transliterate(surname).lower()[:1]
            )
            count += 1
            try:
                profile_obj, _ = DataBaseUserProfile.objects.update_or_create(
                    ref_key=ref_key,
                    defaults=personal_kwargs
                )
                user_obj, user_created = DataBaseUser.objects.update_or_create(
                    ref_key=ref_key,
                    defaults={**divisions_kwargs, "user_profile": profile_obj}
                )
                if user_created:
                    user_obj.username = username
                    user_obj.save(update_fields=["username"])
                created_users_count += 1
                logger.info(f"Создан новый пользователь: {username} ({last_name} {first_name})")
            except Exception as ex:
                logger.error(f"Ошибка создания пользователя {username} ({last_name} {first_name}): {ex}")

        # Обновление существующих сотрудников (через bulk_update)
        elif ref_key in users_set:
            user_obj = existing_users_dict.get(ref_key)
            if user_obj:
                user_modified = False
                for field_name, new_val in divisions_kwargs.items():
                    if hasattr(user_obj, field_name):
                        cur_val = getattr(user_obj, field_name)
                        if cur_val != new_val:
                            setattr(user_obj, field_name, new_val)
                            user_modified = True
                if user_modified:
                    users_to_bulk_update.append(user_obj)

            profile_obj = existing_profiles_dict.get(ref_key)
            if profile_obj:
                profile_modified = False
                for field_name, new_val in personal_kwargs.items():
                    if hasattr(profile_obj, field_name):
                        cur_val = getattr(profile_obj, field_name)
                        if cur_val != new_val:
                            setattr(profile_obj, field_name, new_val)
                            profile_modified = True
                if profile_modified:
                    profiles_to_bulk_update.append(profile_obj)

    # 4. Пакетное обновление данных в базе
    with transaction.atomic():
        if users_to_bulk_update:
            update_fields = [
                "person_ref_key", "service_number", "first_name", "last_name",
                "surname", "birthday", "type_users", "gender", "email",
                "personal_phone", "address"
            ]
            DataBaseUser.objects.bulk_update(users_to_bulk_update, fields=update_fields, batch_size=500)

        if profiles_to_bulk_update:
            DataBaseUserProfile.objects.bulk_update(
                profiles_to_bulk_update, fields=["inn", "snils", "oms"], batch_size=500
            )

    logger.info(
        f"Синхронизация пользователей завершена: обновлено {len(users_to_bulk_update)} пользователей, "
        f"{len(profiles_to_bulk_update)} профилей, создано {created_users_count} новых."
    )
    return {
        "status": "success",
        "updated_users": len(users_to_bulk_update),
        "updated_profiles": len(profiles_to_bulk_update),
        "created_users": created_users_count
    }


def process_get_year_report(report_year: Optional[int] = None, html_mode: bool = True) -> Union[str, pd.DataFrame, Dict[str, Any]]:
    """Формирует годовой отчет учета рабочего времени сотрудников.

    Анализирует отметки СКУД (типы 1, 13) и отклонения (отпуска, командировки, больничные),
    сопоставляет их с нормами производственного календаря и рассчитывает переработки/недоработки по месяцам.

    Args:
        report_year (Optional[int]): Год для формирования отчета (по умолчанию текущий календарный год).
        html_mode (bool): Если True, возвращает отформатированную HTML-таблицу. Если False — pandas DataFrame.

    Returns:
        Union[str, pd.DataFrame, Dict[str, Any]]: HTML-разметка таблицы или DataFrame с расчетами.
    """
    current_dt = datetime.datetime.now()
    current_year = current_dt.year

    if report_year and report_year < current_year:
        year = report_year
        start_of_year = datetime.datetime(year, 1, 1, 0, 0, 0)
        current_date = datetime.datetime(year + 1, 1, 1)
        first_day_of_current_month = current_date
    else:
        year = current_year
        start_of_year = datetime.datetime(year, 1, 1, 0, 0, 0)
        current_date = current_dt
        if current_dt.month == 1:
            last_day = calendar.monthrange(year, 1)[1]
            first_day_of_current_month = datetime.datetime(year, 1, last_day)
        else:
            first_day_of_current_month = datetime.datetime(year, current_dt.month, 1)

    user_set = set(
        ReportCard.objects.filter(
            report_card_day__year=year,
            record_type__in=["1", "13"],
            employee__is_active=True
        ).values_list("employee", flat=True)
    )

    report_card_list = list(
        ReportCard.objects.filter(
            report_card_day__year=year,
            report_card_day__lt=first_day_of_current_month,
            employee__in=user_set
        )
        .exclude(record_type="18")
        .select_related("employee")
        .values_list(
            "employee__title",
            "report_card_day",
            "start_time",
            "end_time",
            "record_type"
        )
    )

    if not report_card_list:
        if not html_mode:
            return pd.DataFrame()
        return "<div class='alert alert-info'>Нет данных для построения годового отчета за указанный период.</div>"

    fields = ["FIO", "Дата", "Start", "End", "Type"]
    df = pd.DataFrame(report_card_list, columns=fields)

    df["Дата"] = pd.to_datetime(df["Дата"])
    df["Start"] = pd.to_datetime(df["Start"], format="%H:%M:%S")
    df["End"] = pd.to_datetime(df["End"], format="%H:%M:%S")
    df["Type"] = df["Type"].astype(int)

    df = df.groupby(["FIO", "Дата"]).apply(adjust_time).reset_index(drop=True)
    df["Time"] = (df["End"] - df["Start"]).dt.total_seconds()
    df["Time"] = df.apply(
        lambda row: row["Time"] if row["Type"] not in [14, 15, 16, 17, 20] else get_norm_time_at_custom_day(
            row["Дата"], type_of_day=row["Type"]
        ),
        axis=1
    )

    df["Month"] = df["Дата"].dt.to_period("M")
    grouped = df.groupby(["Month", "FIO", "Дата"]).apply(process_group_year).reset_index(name="Time")
    grouped = grouped.groupby(["Month", "FIO"])["Time"].sum().reset_index()
    grouped["Time"] = grouped["Time"] // 60  # в минутах

    first_days_of_months = []
    current_month_start = start_of_year
    while current_month_start <= current_date:
        first_days_of_months.append(current_month_start)
        current_month_start += relativedelta(months=1)

    subtraction_dict = {}
    for date_item in first_days_of_months[:-1]:
        key = date_item.strftime("%Y-%m")
        try:
            norm_time = ProductionCalendar.objects.get(calendar_month=date_item)
            subtraction_dict[key] = ((norm_time.get_norm_time() // 1) * 60) + (norm_time.get_norm_time() % 1) * 60
        except ProductionCalendar.DoesNotExist:
            subtraction_dict[key] = 0

    grouped = grouped.fillna("")

    def subtract_value(row):
        month_str = str(row["Month"])
        ttime = row["Time"]
        return ttime - subtraction_dict.get(month_str, 0)

    grouped["Time"] = grouped.apply(subtract_value, axis=1)

    pivot_df = grouped.pivot(index="FIO", columns="Month", values="Time")
    pivot_df = pivot_df.fillna(0)
    pivot_df["Sum"] = pivot_df.sum(axis=1)

    def convert_time(minutes):
        hours = abs(minutes) // 60
        minutes_left = abs(minutes) % 60
        if minutes < 0:
            return f"-{hours:.0f} ч. {minutes_left:.0f} мин."
        else:
            return f"{hours:.0f} ч. {minutes_left:.0f} мин."

    if hasattr(pivot_df, "map"):
        formatted_pivot_df = pivot_df.map(convert_time)
    else:
        formatted_pivot_df = pivot_df.applymap(convert_time)

    html_table = formatted_pivot_df.to_html(
        classes="table table-ecommerce-simple table-striped dataTable mb-0",
        table_id="datatable-editable",
        border=1,
        justify="center"
    )

    if not html_mode:
        return pivot_df
    return html_table


