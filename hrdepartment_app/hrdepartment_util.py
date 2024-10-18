import datetime

from dateutil import rrule
from dateutil.relativedelta import relativedelta
from decouple import config
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from loguru import logger

from administration_app.utils import get_jsons_data, time_difference
from customers_app.models import DataBaseUser, HarmfulWorkingConditions
from djangoProject.settings import EMAIL_HOST_USER
from hrdepartment_app.models import (
    MedicalOrganisation,
    Medical,
    ReportCard,
    PreHolidayDay,
    WeekendDay,
    check_day,
)


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


def get_medical_documents():
    """
        Функция для получения документов по медицинскому осмотру
    :return:
    """
    type_inspection = [
        ("1", "Предварительный"),
        ("2", "Периодический"),
        ("3", "Внеплановый"),
    ]
    todos = get_jsons_data("Document", "НаправлениеНаМедицинскийОсмотр", 0)
    db_users = DataBaseUser.objects.all().exclude(is_active=False)
    harmfuls = HarmfulWorkingConditions.objects.all()
    # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
    for item in todos["value"]:
        if item["Posted"]:
            db_user = db_users.filter(person_ref_key=item["ФизическоеЛицо_Key"], is_active=True)
            db_med_org = item["МедицинскаяОрганизация_Key"]
            if (
                    db_user.count() > 0
                    and db_med_org != "00000000-0000-0000-0000-000000000000"
            ):
                qs = list()
                for items in item["ВредныеФакторыИВидыРабот"]:
                    qs.append(harmfuls.get(ref_key=items["ВредныйФактор_Key"]))
                try:
                    divisions_kwargs = {
                        "ref_key": item["Ref_Key"],
                        "number": item["Number"],
                        "person": db_users.get(
                            person_ref_key=item["ФизическоеЛицо_Key"]
                        ),
                        "date_entry": datetime.datetime.strptime(
                            item["Date"][:10], "%Y-%m-%d"
                        ),
                        "date_of_inspection": datetime.datetime.strptime(
                            item["ДатаОсмотра"][:10], "%Y-%m-%d"
                        ),
                        "organisation": MedicalOrganisation.objects.get(
                            ref_key=item["МедицинскаяОрганизация_Key"]
                        ),
                        "working_status": 1
                        if next(
                            x[0] for x in type_inspection if x[1] == item["ТипОсмотра"]
                        )
                           == 1
                        else 2,
                        "view_inspection": 1
                        if item["ВидОсмотра"] == "МедицинскийОсмотр"
                        else 2,
                        "type_inspection": next(
                            x[0] for x in type_inspection if x[1] == item["ТипОсмотра"]
                        ),
                        # 'harmful': qs,
                    }
                    db_instance, created = Medical.objects.update_or_create(
                        ref_key=item["Ref_Key"], defaults=divisions_kwargs
                    )
                    db_instance.harmful.set(qs)
                except Exception as _ex:
                    logger.error(
                        f"Не найдена медицинская организация. Физическое лицо: {db_user}"
                    )
                    return f"{_ex}: Необходимо обновить список медицинских организаций."
    return ""


def check_email(obj):
    """
    Этот метод принимает объект в качестве параметра и проверяет, существует ли он. Если объект существует, он
    возвращает атрибут электронной почты объекта. Если объект не существует, он возвращает пустую строку.
    :param obj: Объект для проверки
    :return: Атрибут электронной почты объекта, если он существует, иначе пустая строка
    """
    return obj.email if obj else ""


def send_mail_change(counter, obj, message=""):
    mail_to = check_email(obj.person)
    mail_to_copy_first = check_email(obj.responsible)
    mail_to_copy_second = check_email(obj.docs.person_distributor)
    mail_to_copy_third = check_email(obj.docs.person_department_staff)
    subject_mail = obj.get_title()

    current_context = {
        "title": obj.get_title(),
        "order_number": str(obj.order.document_number) if obj.order else "",
        "order_date": str(obj.order.document_date.strftime("%d.%m.%Y"))
        if obj.order
        else "",
        "message": message,
        "person_executor": obj.responsible,
        "mail_to_copy": check_email(obj.responsible),
        "person_department_staff": str(obj.docs.person_department_staff)
        if obj.docs.person_department_staff
        else "",
        "person_distributor": str(obj.docs.person_distributor)
        if obj.docs.person_distributor
        else "",
    }

    text_content = render_to_string(
        "hrdepartment_app/email_change_bpmemo.html", current_context
    )
    html_content = render_to_string(
        "hrdepartment_app/email_change_bpmemo.html", current_context
    )

    try:
        if counter == 1:
            first_msg = EmailMultiAlternatives(
                subject_mail,
                text_content,
                EMAIL_HOST_USER,
                [mail_to, mail_to_copy_first],
            )
            second_msg = EmailMultiAlternatives(
                subject_mail,
                text_content,
                EMAIL_HOST_USER,
                [mail_to_copy_second, mail_to_copy_third],
            )
            first_msg.attach_alternative(html_content, "text/html")
            second_msg.attach_alternative(html_content, "text/html")
            first_msg.send()
            second_msg.send()
        if counter == 2:
            first_msg = EmailMultiAlternatives(
                subject_mail,
                text_content,
                EMAIL_HOST_USER,
                [mail_to_copy_first, mail_to_copy_second],
            )
            first_msg.attach_alternative(html_content, "text/html")
            first_msg.send()
        if counter == 3:
            first_msg = EmailMultiAlternatives(
                subject_mail,
                text_content,
                EMAIL_HOST_USER,
                [mail_to, mail_to_copy_third],
            )
            first_msg.attach_alternative(html_content, "text/html")
            first_msg.send()

    except Exception as _ex:
        logger.debug(f"Failed to send email. {_ex}")


def get_month(period):
    """
    Функция get_month, принимает в качестве аргумента переменную datetime, и на основании нее определяет первый и
    последний день месяца. В качестве результата работы выдает список [[день, Я], [день, В]...]
    :param period: Любой день месяца
    :return: Список [[день, Я], [день, В]...]
    """
    first_day = period + relativedelta(day=1)
    last_day = period + relativedelta(day=31)
    weekend_days = [
        item.weekend_day
        for item in WeekendDay.objects.filter(
            Q(weekend_day__gte=first_day) & Q(weekend_day__lte=last_day)
        )
    ]
    get_month_obj = []
    for item in range(first_day.day, last_day.day + 1):
        date_obj = first_day + datetime.timedelta(days=item - 1)
        current_day = datetime.date(date_obj.year, date_obj.month, date_obj.day)
        if date_obj.weekday() in [0, 1, 2, 3, 4]:
            if current_day in list(weekend_days):
                get_month_obj.append([current_day, "В"])
            else:
                get_month_obj.append([current_day, "Я"])
        else:
            get_month_obj.append([current_day, "В"])
    return get_month_obj


def get_preholiday_day(item, hour, minute, user_start_time, user_end_time):
    """
    Проверка даты на предпраздничный день.
    :param curent_day: День
    :param hour: Количество часов
    :param minute: Количество минут
    :return: Если передано нулевое время, то возвращается тоже нулевое. Если передано не нулевое время, а день оказался
    предпраздничным, то возвращается время заданное в предпраздничном дне, иначе возвращается, то время, которое пришло.
    Также возвращается вторым аргументом время окончания рабочего времени
    """
    check = 0
    curent_day = item.report_card_day
    if item.record_type == "1":
        check = 0
    if item.record_type in ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
        check = 1
    start_time = datetime.timedelta(
        hours=user_start_time.hour, minutes=user_start_time.minute
    )
    new_start_time = datetime.timedelta(hours=0, minutes=0)
    # Проверка на выходной. Если истина, то вернуть нулевое время
    holiday_day = WeekendDay.objects.filter(weekend_day=curent_day).exists()
    if check == 1:
        end_time = datetime.timedelta(hours=0, minutes=0)
        new_start_time = datetime.timedelta(hours=0, minutes=0)
        if curent_day.weekday() in [0, 1, 2, 3]:
            return datetime.timedelta(hours=8, minutes=30), new_start_time, end_time
        elif curent_day.weekday() == 4:
            return datetime.timedelta(hours=7, minutes=30), new_start_time, end_time
        else:
            return datetime.timedelta(hours=0, minutes=0), new_start_time, end_time
    if holiday_day:
        end_time = start_time + datetime.timedelta(hours=0, minutes=0)
        return datetime.timedelta(hours=0, minutes=0), new_start_time, end_time
    try:
        pre_holiday_day = PreHolidayDay.objects.get(preholiday_day=curent_day)
        if hour == 0 and minute == 0:
            end_time = start_time + datetime.timedelta(hours=hour, minutes=minute)
            return (
                datetime.timedelta(hours=hour, minutes=minute),
                new_start_time,
                end_time,
            )
        else:
            end_time = start_time + datetime.timedelta(
                hours=pre_holiday_day.work_time.hour,
                minutes=pre_holiday_day.work_time.minute,
            )
            return (
                datetime.timedelta(
                    hours=pre_holiday_day.work_time.hour,
                    minutes=pre_holiday_day.work_time.minute,
                ),
                new_start_time,
                end_time,
            )

    except Exception as _ex:
        end_time = start_time + datetime.timedelta(hours=hour, minutes=minute)
        return datetime.timedelta(hours=hour, minutes=minute), new_start_time, end_time


# -------------------------------------------------------------------------------------------------------------------


def get_working_hours(pk, start_date, state=0):
    """
    Вывод табеля по сотруднику, за заданный интервал, с выводом всех состояний (явка, отпуск, больничный ...)
    :param pk: уин пользователя в базе данных
    :param start_date: начальная дата (как правило начало месяца)
    :param state: переключатель, в зависимости от которого меняется выходные данные
    :return: в зависимости от state.
            Если state = 0:
            dict_obj = {'сотрудник': [r1-Дата, r2-Начало, r3-Окончание, r4-Знак, r5-Скалярное общее время за день,
                                      r6-Начало по графику, r7-Окончание по графику, r8-Тип записи,
                                      r9-Было ли объединение интервалов, r10-Текущий интервал, r11-Общее за день,
                                      r12-Общее по табелю]},
            total_time = Общее время за интервал,
            start_date = Начальная дата,
            cnt = Конечная дата
            Если state = 1:
            dict_obj = {'сотрудник': [r1-Дата, r2-Начало, r3-Окончание, r4-Знак, r5-Скалярное общее время за день,
                                      r6-Начало по графику, r7-Окончание по графику, r8-Тип записи,
                                      r9-Было ли объединение интервалов, r10-Текущий интервал, r11-Общее за день]},
            all_total_time = Общее время за интервал,
            all_days_count = Общее количество дней за интервал,
            all_vacation_days = Количество дней в отпуске,
            all_vacation_time = Количество часов в отпуске,
            holiday_delta = Количество выходных и праздников
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
    }
    user_id = DataBaseUser.objects.get(pk=pk)
    cnt = start_date + relativedelta(day=31)
    period = list(rrule.rrule(rrule.DAILY, count=cnt.day, dtstart=start_date.date()))
    dict_obj = dict()
    total_time = 0
    all_total_time = 0
    all_days_count = 0
    all_vacation_days = 0
    all_vacation_time = 0
    holiday_delta = 0
    for date in period:
        if not dict_obj.get(str(user_id)):
            dict_obj[str(user_id)] = []
        report_record = (
            ReportCard.objects.filter(employee=user_id, report_card_day=date)
            .order_by("record_type")
            .reverse()
        )
        total_day_time, time_worked = 0, 0
        start_time, end_time, record_type, sign, merge_interval, type_of_day = (
            "",
            "",
            "",
            "",
            "",
            "",
        )
        user_start_time = (
            user_start
        ) = user_id.user_work_profile.personal_work_schedule_start
        user_end_time = user_end = user_id.user_work_profile.personal_work_schedule_end
        current_intervals = True
        dayly_interval = []
        # получаем рабочее время и тип дня
        user_start_time, user_end_time, type_of_day = check_day(
            date, user_start_time, user_end_time
        )
        table_total_time = time_difference(user_start_time, user_end_time)
        for record in report_record:
            # Выбираем только завершенные записи, если человек не отметился на выход, то current_intervals = False
            current_intervals = (
                False if not current_intervals else record.current_intervals
            )
            if (record.record_type in ["1", "13"]) and (
                    record_type
                    not in [
                        "СП",
                        "К",
                        "Б",
                        "М",
                    ]
            ):
                if current_intervals:
                    dayly_interval += list(
                        rrule.rrule(
                            rrule.MINUTELY,
                            dtstart=datetime.datetime(
                                1,
                                1,
                                1,
                                record.start_time.hour,
                                record.start_time.minute,
                            ),
                            until=datetime.datetime(
                                1, 1, 1, record.end_time.hour, record.end_time.minute
                            ),
                        )
                    )

                if start_time == "":
                    start_time = record.start_time
                else:
                    if start_time == datetime.datetime(1, 1, 1, 0, 0).time():
                        start_time = record.start_time
                    if (
                            record.start_time < start_time
                            and record.start_time != datetime.datetime(1, 1, 1, 0, 0).time()
                    ):
                        start_time = record.start_time
                if end_time == "":
                    end_time = record.end_time
                else:
                    if record.end_time > end_time:
                        end_time = record.end_time
                if record_type not in [
                    "О",
                    "СП",
                    "К",
                    "Б",
                    "М",
                ]:
                    record_type = "Я"
            else:
                if (record.record_type in ["14", "15"]) and record_type not in [
                    "Б",
                    "М",
                ]:
                    total_day_time = time_difference(record.start_time, record.end_time)
                    start_time = record.start_time
                    end_time = record.end_time
                    if record.record_type == "14" and record_type != "О":
                        record_type = "СП"
                    if record.record_type == "15" and record_type != "О":
                        record_type = "К"
                elif record.record_type == "16" or record.record_type == "17":
                    start_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    end_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    total_day_time += 0
                    if record.record_type == "16":
                        record_type = "Б"
                    else:
                        record_type = "М"
                else:
                    start_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    end_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    total_day_time += 0
                    if record_type not in [
                        "Б",
                        "М",
                    ] and record.record_type != "18":
                        record_type = "О"
                    else:
                        if record_type in ["Б",] and record.record_type in ["1", "13"]:
                            record_type = "Б"
                        else:
                            record_type = "ГО"
        if record_type not in [
            "СП",
            "К",
            "Б",
            "М",
        ]:
            dayly_interval_set = set(dayly_interval)
            total_day_time = (
                ((len(dayly_interval_set) - 1) * 60)
                if len(dayly_interval_set) > 0
                else 0
            )

        if record_type != "":
            if report_record.count() == 1:
                merge_interval = False
            else:
                merge_interval = True
            # user_start_time, user_end_time, type_of_day = check_day(date, user_start_time, user_end_time)
            # Если только явка или ручной ввод
            if record_type == "Я":
                all_days_count += 1
                if current_intervals:
                    time_worked = total_day_time
                    # От отработанного времени отнимаем рабочее, чтоб получить дельту
                    total_day_time -= (
                            datetime.timedelta(
                                hours=user_end_time.hour, minutes=user_end_time.minute
                            ).total_seconds()
                            - datetime.timedelta(
                        hours=user_start_time.hour, minutes=user_start_time.minute
                    ).total_seconds()
                    )
            if record_type == "СП" or record_type == "К":
                all_days_count += 1
                time_worked = total_day_time
                # От отработанного времени отнимаем рабочее, чтоб получить дельту
                total_day_time -= (
                        datetime.timedelta(
                            hours=user_end_time.hour, minutes=user_end_time.minute
                        ).total_seconds()
                        - datetime.timedelta(
                    hours=user_start_time.hour, minutes=user_start_time.minute
                ).total_seconds()
                )
            # Если только отпуск
            if (
                    record_type == "О" or record_type == "Б" or record_type == "М"
            ) and report_record.count() == 1:
                total_time += 0
                all_total_time += 0
                if user_end_time.hour > 0:
                    all_vacation_days += 1
                all_vacation_time += (
                        datetime.timedelta(
                            hours=user_end_time.hour, minutes=user_end_time.minute
                        ).total_seconds()
                        - datetime.timedelta(
                    hours=user_start_time.hour, minutes=user_start_time.minute
                ).total_seconds()
                )
            if record_type == "Я":
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour == 0:
                    holiday_delta += 1
            if record_type == "СП" or record_type == "К":
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour == 0:
                    holiday_delta += 1
            if (
                    record_type == "О" or record_type == "Б" or record_type == "М"
            ) and merge_interval:
                time_worked = total_day_time
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour > 0:
                    all_vacation_days += 1
                all_vacation_time += (
                        datetime.timedelta(
                            hours=user_end_time.hour, minutes=user_end_time.minute
                        ).total_seconds()
                        - datetime.timedelta(
                    hours=user_start_time.hour, minutes=user_start_time.minute
                ).total_seconds()
                )
            if record_type == "К" and merge_interval:
                time_worked = total_day_time
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour > 0:
                    all_vacation_days += 1
                all_vacation_time += (
                        datetime.timedelta(
                            hours=user_end_time.hour, minutes=user_end_time.minute
                        ).total_seconds()
                        - datetime.timedelta(
                    hours=user_start_time.hour, minutes=user_start_time.minute
                ).total_seconds()
                )
            sign = ""
            if total_day_time < 0:
                sign = "-"
        start_time = (
            start_time if start_time != "" else datetime.datetime(1, 1, 1, 0, 0).time()
        )
        end_time = (
            end_time if end_time != "" else datetime.datetime(1, 1, 1, 0, 0).time()
        )
        if state == 0:
            if record_type == "":
                record_type = type_of_day
            if not current_intervals:
                table_total_time = 0
            dict_obj[str(user_id)].append(
                [
                    date.date(),
                    start_time,
                    end_time,
                    sign,
                    abs(total_day_time),
                    user_start_time,
                    user_end_time,
                    record_type,
                    merge_interval,
                    current_intervals,
                    time_worked,
                    table_total_time,
                ]
            )
        elif state == 2:
            if record_type == "":
                record_type = type_of_day
            time_worker = (
                datetime.datetime(1, 1, 1, 0, 0).time().strftime("%H:%M")
                if time_worked == 0
                else datetime.datetime.strptime(
                    str(datetime.timedelta(seconds=time_worked)), "%H:%M:%S"
                )
                .time()
                .strftime("%H:%M")
            )
            dict_obj[str(user_id)].append([start_time, end_time, time_worker])
        else:
            if record_type == "":
                record_type = type_of_day
            time_worker = (
                datetime.datetime(1, 1, 1, 0, 0).time().strftime("%H:%M")
                if time_worked == 0
                else datetime.datetime.strptime(
                    str(datetime.timedelta(seconds=time_worked)), "%H:%M:%S"
                )
                .time()
                .strftime("%H:%M")
            )
            dict_obj[str(user_id)].append([date.date(), record_type, time_worker])
    if state == 0:
        # return dict_obj, total_time, start_date, cnt, user_start, user_end
        return dict_obj, all_total_time, start_date, cnt, user_start, user_end
    elif state == 1:
        result = dict_obj[str(user_id)]
        return (
            result,
            all_total_time,
            all_days_count,
            all_vacation_days,
            all_vacation_time,
            holiday_delta,
        )
    else:
        result = dict_obj[str(user_id)]
        return (
            result,
            all_total_time,
            all_days_count,
            all_vacation_days,
            all_vacation_time,
            holiday_delta,
        )


def get_notify(data_table, data_query: Q, notify_table, notify_dict: dict, rules_table, rules_query: Q, rules_list: str):
    """
    Обновляем уведомление о согласовании или создаем новое при необходимости
    :param data_table: Модель данных документов (служебные поездки, приказы старших бригад и т.д.)
    :param data_query: Фильтр выборки документов = тип Q
    :param notify_table: Модель уведомлений = класс Notification
    :param notify_dict: Словарь с данными уведомления = тип dict
    :param rules_table: Модель правил бизнес-процессов = класс BusinessProcessDirection
    :param rules_query: Фильтр выборки бизнес-процессов = тип Q
    :param rules_list: Поля бизнес-процессов

    :return:

    """
    # Обновляем список согласующих
    approve_list = [item[0] for item in rules_table.objects.filter(rules_query).values_list(rules_list)]
    # Получаем уведомление о согласовании или создаем новое при необходимости
    notify, created = notify_table.objects.get_or_create(**notify_dict)
    # Сохраняем уведомление записав в него количество требуемых согласований
    notify.count = data_table.objects.filter(data_query).exclude(cancellation=True).count()
    notify.save()
    notify.job_list.add(*approve_list)  # добавляем список согласующих лиц
