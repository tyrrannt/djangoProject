# -*- coding: utf-8 -*-
import datetime
import json
from random import randrange

import requests
import telebot
from dateutil import rrule
from decouple import config
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from loguru import logger

from administration_app.utils import (
    get_jsons_data_filter2,
    get_date_interval,
    get_jsons_data_filter,
)

from customers_app.models import DataBaseUser, Division, Posts, HappyBirthdayGreetings, VacationScheduleList, \
    VacationSchedule
from djangoProject.celery import app
from djangoProject.settings import EMAIL_HOST_USER, API_TOKEN
from hrdepartment_app.models import (
    ReportCard,
    WeekendDay,
    check_day,
    ApprovalOficialMemoProcess,
)
from telegram_app.management.commands.bot import send_message_tg
from telegram_app.models import TelegramNotification, ChatID


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


def xldate_to_datetime(xldate):
    import xlrd

    # Calling the xldate_as_datetime() function to
    # convert the specified excel serial date into
    # datetime.datetime object
    datetime_date = xlrd.xldate_as_datetime(xldate, 0)
    # Getting the converted date date as output
    print(datetime_date)
    return datetime_date.strftime("%Y-%m-%d %H:%M:%S")


@app.task()
def send_email():
    print("It is work!")


@app.task()
def send_email_notification():
    count, errors = 0, 0
    for item in DataBaseUser.objects.filter(is_active=True).exclude(is_superuser=True):
        if item.user_work_profile.work_email_password:
            item.set_password(item.user_work_profile.work_email_password)
            item.save()
            mail_to = item.email
            subject_mail = (
                f"Уведомление о доступе к Вашей учетной записи на портале"
            )
            current_context = {
                "name": item.first_name,
                "surname": item.surname,
                "text": f"Уведомляем Вас, что Вам открыт доступ к Вашей учетной записи на корпоративном портале. Данные для авторизации указаны ниже:",
                "sign": f"Ваш логин: {item.username}<br>Ваш пароль: {item.user_work_profile.work_email_password}",
                "color": "white",
            }
            text_content = render_to_string(
                "hrdepartment_app/change_password.html", current_context
            )
            html_content = render_to_string(
                "hrdepartment_app/change_password.html", current_context
            )
            plain_message = strip_tags(html_content)
            try:
                mail.send_mail(
                    subject_mail,
                    plain_message,
                    EMAIL_HOST_USER,
                    [
                        mail_to,
                        EMAIL_HOST_USER,
                    ],
                    html_message=html_content,
                )
                logger.info(f"Сообщение для {mail_to} отправлено!")
            except Exception as _ex:
                logger.debug(f"Failed to send email to {mail_to} because {_ex}")
            count += 1
        else:
            errors += 1
        logger.debug(f"Failed to change {errors} passwords!")
    return count, errors



def change_sign():
    list_obj = HappyBirthdayGreetings.objects.all()
    for item in list_obj:
        item.sign = 'Генеральный директор<br>ООО Авиакомпания "БАРКОЛ"<br>Бархотов В.С.<br>и весь коллектив!!!'
        item.save()


def send_mail(person: DataBaseUser, age: int, record: Posts):
    if not record.email_send:
        mail_to = person.email
        gender = person.gender
        if gender == "male":
            color = "#b5e0ff"
        else:
            color = "#ffc0cb"
        subject_mail = (
            f"{person.first_name} {person.surname} поздравляем Вас с днем рождения!"
        )
        greet = HappyBirthdayGreetings.objects.filter(
            Q(gender=gender) & Q(age_from__lte=age) & Q(age_to__gte=age)
        )
        rec_no = randrange(len(greet))
        text = greet[rec_no].greetings
        current_context = {
            "name": person.first_name,
            "surname": person.surname,
            "text": greet[rec_no].greetings,
            "sign": greet[rec_no].sign,
            "color": color,
        }
        logger.debug(f"Email string: {current_context}")
        text_content = render_to_string(
            "hrdepartment_app/happy_birthday.html", current_context
        )
        html_content = render_to_string(
            "hrdepartment_app/happy_birthday.html", current_context
        )
        plain_message = strip_tags(html_content)
        # first_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
        #                                    [mail_to, ])
        # first_msg.attach_alternative(html_content, "text/html")
        try:
            mail.send_mail(
                subject_mail,
                plain_message,
                EMAIL_HOST_USER,
                [
                    mail_to,
                    EMAIL_HOST_USER,
                ],
                html_message=html_content,
            )
            record.email_send = True
            record.save()
        except Exception as _ex:
            logger.debug(f"Failed to send email. {_ex}")


def happy_birthday_loc():
    today = datetime.datetime.today()
    posts_dict = dict()
    division = [item.pk for item in Division.objects.filter(active=True)]
    list_birthday_people = DataBaseUser.objects.filter(
        Q(birthday__day=today.day) & Q(birthday__month=today.month)
    )
    description = ""
    for item in list_birthday_people:
        age = today.year - item.birthday.year
        description = f"Сегодня {item} празднует свой {age}-й день рождения!"
        posts_dict = {
            "post_description": description,
            "allowed_placed": True,
            "responsible": DataBaseUser.objects.get(pk=1),
            "post_date_start": datetime.datetime.today(),
            "post_date_end": datetime.datetime.today(),
        }
        post, created = Posts.objects.update_or_create(
            post_description=description, defaults=posts_dict
        )

        if created:
            post.post_divisions.add(*division)
            post.save()
            if not post.email_send:
                send_mail(item, age, post)
        else:
            if not post.email_send:
                send_mail(
                    item,
                    age,
                    Posts.objects.filter(post_description=description).first(),
                )


@app.task()
def send_telegram_notify():
    print(send_message_tg())
    dt = datetime.datetime.now()
    # if dt.hour == 23 and dt.minute == 10:
    #     try:
    #         qs = ApprovalOficialMemoProcess.objects.all().exclude(cancellation=True)
    #         for item in qs:
    #             item.save()
    #             logger.error(f"Saved")
    #     except Exception as _ex:
    #         logger.error(f"{_ex}")
    if dt.hour == 23 and dt.minute == 30:
        get_sick_leave(dt.year, 1)
    if dt.hour == 23 and dt.minute == 35:
        get_sick_leave(dt.year, 2)
    if dt.hour == 23 and dt.minute == 40:
        report_card_separator_daily()
    if dt.hour == 23 and dt.minute == 50:
        get_vacation()


@app.task()
def happy_birthday():
    today = datetime.datetime.today()
    posts_dict = dict()
    division = [item.pk for item in Division.objects.filter(active=True)]
    list_birthday_people = DataBaseUser.objects.filter(
        Q(birthday__day=today.day) & Q(birthday__month=today.month)
    ).exclude(is_active=False)
    description = ""
    for item in list_birthday_people:
        age = today.year - item.birthday.year
        if item.gender == "male":
            description = f"Сегодня {item} празднует свой {age}-й день рождения!"
        else:
            description = f"Сегодня {item} празднует свой 18-й день рождения!"
        posts_dict = {
            "post_description": description,
            "allowed_placed": True,
            "responsible": DataBaseUser.objects.get(pk=1),
            "post_date_start": datetime.datetime.today(),
            "post_date_end": datetime.datetime.today(),
        }
        post, created = Posts.objects.update_or_create(
            post_description=description, defaults=posts_dict
        )

        if created:
            post.post_divisions.add(*division)
            post.save()
            person_list = DataBaseUser.objects.filter(telegram_id__regex=r"^\d")
            person_tg_list = [item.telegram_id for item in person_list]
            person_tg_list_chat_id = ChatID.objects.filter(chat_id__in=person_tg_list)
            kwargs_obj = {
                "message": description,
                "document_url": "",
                "document_id": post.pk,
                "sending_counter": 1,
                "send_time": datetime.datetime(1, 1, 1, 9, 30),
                "send_date": datetime.datetime.today(),
            }
            tn, created = TelegramNotification.objects.update_or_create(
                document_id=post.pk, defaults=kwargs_obj
            )
            tn.respondents.set(person_tg_list_chat_id)
            if not post.email_send:
                send_mail(item, age, post)
        else:
            if not post.email_send:
                send_mail(
                    item,
                    age,
                    Posts.objects.filter(post_description=description).first(),
                )


# @app.task()
# def report_card_separator():
#     try:
#         file = pathlib.Path.joinpath(BASE_DIR, 'rsync/timecontrol/PersonsWorkLite.txt')
#         logger.info(f'File received: {file}')
#     except Exception as _ex:
#         logger.info(f'File opening error: {_ex}')
#     import re
#     result = {}
#     try:
#         with open(file, encoding='cp1251') as fd:
#             for line in fd:
#                 match = re.search(r'\D*', line)
#                 start_time = line[len(match[0]) + 5:len(match[0]) + 21]
#                 end_time = line[len(match[0]) + 21:-1]
#                 if end_time:
#                     result.update({f'{match[0]}': [start_time, end_time]})
#                     search_user = match[0].split(' ')
#                     try:
#                         user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
#                                                             surname=search_user[2])
#                         report_card_day = datetime.datetime.strptime(
#                             xldate_to_datetime(float(start_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S')
#
#                         kwargs = {
#                             'report_card_day': report_card_day.date(),
#                             'employee': user_obj,
#                             'start_time': datetime.datetime.strptime(
#                                 xldate_to_datetime(float(start_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S').time(),
#                             'end_time': datetime.datetime.strptime(
#                                 xldate_to_datetime(float(end_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S').time(),
#                         }
#                         ReportCard.objects.update_or_create(report_card_day=report_card_day.date(), employee=user_obj,
#                                                             defaults=kwargs)
#                     except Exception as _ex:
#                         logger.error(f'{match[0]} not found in the database: {_ex}')
#         return result
#     except IOError:
#         logger.error(f'File opening error: {IOError}')
#     finally:
#         fd.close()


# @app.task()
# def report_card_separator():
#     import pandas as pd
#     # Load the xlsx file
#     excel_data = pd.read_excel(pathlib.Path.joinpath(BASE_DIR, 'rsync/timecontrol/PersonsWorkLite.xls'))
#     # Read the values of the file in the dataframe
#     data = pd.DataFrame(excel_data, columns=['ФИО', 'Дата', 'Время прихода', 'Время ухода'])
#     # # Print the content
#     dictionary = data.to_dict('records')
#     for key in dictionary:
#         usr, d1, t1, t2 = key['ФИО'], key['Дата'], key['Время прихода'], key['Время ухода']
#
#         search_user = usr.split(' ')
#         try:
#             user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
#                                                 surname=search_user[2])
#             kwargs = {
#                 'report_card_day': datetime.datetime.date(d1),
#                 'employee': user_obj,
#                 'start_time': datetime.datetime.time(t1),
#                 'end_time': datetime.datetime.time(t2),
#             }
#             ReportCard.objects.update_or_create(report_card_day=datetime.datetime.date(d1), employee=user_obj,
#                                                 defaults=kwargs)
#         except Exception as _ex:
#             logger.error(f'{key} not found in the database: {_ex}')
#     return dictionary


@app.task()
def report_card_separator():
    current_data = datetime.datetime.date(datetime.datetime.today())
    # current_data1 = datetime.datetime.date(datetime.datetime(2023, 1, 1))
    # current_data2 = datetime.datetime.date(datetime.datetime(2023, 5, 25))
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
    source_url = url
    try:
        response = requests.get(source_url, auth=("proxmox", "PDO#rLv@Server"))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts["data"]:
        usr = item["FULLNAME"]
        # current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
        current_intervals = True if item["ISGO"] == "0" else False
        start_time = datetime.datetime.strptime(
            item["STARTTIME"], "%d.%m.%Y %H:%M:%S"
        ).time()
        if current_intervals:
            end_time = datetime.datetime.strptime(
                item["ENDTIME"], "%d.%m.%Y %H:%M:%S"
            ).time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item["rec_no"])

        search_user = usr.split(" ")
        try:
            user_obj = DataBaseUser.objects.get(
                last_name=search_user[0],
                first_name=search_user[1],
                surname=search_user[2],
            )
            kwargs = {
                "report_card_day": current_data,
                "employee": user_obj,
                "start_time": start_time,
                "end_time": end_time,
                "record_type": "1",
                "current_intervals": current_intervals,
            }
            ReportCard.objects.update_or_create(
                report_card_day=current_data,
                employee=user_obj,
                rec_no=rec_no,
                defaults=kwargs,
            )
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts


@app.task()
def get_vacation():
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
    all_records = 0
    exclude_list = ["proxmox", "shakirov"]
    year = datetime.datetime.today().year
    for report_record in ReportCard.objects.filter(
            Q(report_card_day__year=year)
            & Q(
                record_type__in=[
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",
                    "12",
                    "19",
                ]
            )
    ):
        report_record.delete()
    report_card_list = list()
    for rec_item in (
            DataBaseUser.objects.all().exclude(username__in=exclude_list).values("ref_key")
    ):
        dt = get_jsons_data_filter2(
            "InformationRegister",
            "ДанныеОтпусковКарточкиСотрудника",
            "Сотрудник_Key",
            rec_item["ref_key"],
            "year(ДатаОкончания)",
            year,
            0,
            0,
        )
        for key in dt:
            for item in dt[key]:
                usr_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"])
                start_date = datetime.datetime.strptime(
                    item["ДатаНачала"][:10], "%Y-%m-%d"
                )
                end_date = datetime.datetime.strptime(
                    item["ДатаОкончания"][:10], "%Y-%m-%d"
                )
                weekend_count = WeekendDay.objects.filter(
                    Q(weekend_day__gte=start_date)
                    & Q(weekend_day__lte=end_date)
                    & Q(weekend_type="1")
                ).count()
                count_date = int(item["КоличествоДней"]) + weekend_count
                period = list(
                    rrule.rrule(rrule.DAILY, count=count_date, dtstart=start_date)
                )
                weekend = [
                    item.weekend_day
                    for item in WeekendDay.objects.filter(
                        Q(weekend_day__gte=start_date.date())
                        & Q(weekend_day__lte=end_date.date())
                    )
                ]
                for unit in period:
                    if unit.weekday() in [0, 1, 2, 3] and unit.date() not in weekend:
                        delta_time = datetime.timedelta(
                            hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                            minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute,
                        )
                        start_time = (
                            usr_obj.user_work_profile.personal_work_schedule_start
                        )
                        end_time = datetime.datetime.strptime(
                            str(delta_time), "%H:%M:%S"
                        ).time()
                    elif unit.weekday() == 4 and unit not in weekend:
                        delta_time = datetime.timedelta(
                            hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                            minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute,
                        ) - datetime.timedelta(hours=1)
                        start_time = (
                            usr_obj.user_work_profile.personal_work_schedule_start
                        )
                        end_time = datetime.datetime.strptime(
                            str(delta_time), "%H:%M:%S"
                        ).time()
                    else:
                        start_time = datetime.datetime.strptime(
                            "00:00:00", "%H:%M:%S"
                        ).time()
                        end_time = datetime.datetime.strptime(
                            "00:00:00", "%H:%M:%S"
                        ).time()

                    value = [
                        i
                        for i in type_of_report
                        if type_of_report[i] == item["ВидОтпускаПредставление"]
                    ]
                    # print(item)
                    kwargs_obj = {
                        "report_card_day": unit,
                        "employee": usr_obj,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_type": value[0],
                        "reason_adjustment": item["Основание"],
                        "doc_ref_key": item["ДокументОснование"],
                    }
                    report_card_list.append(kwargs_obj)
    try:
        objs = ReportCard.objects.bulk_create(
            [ReportCard(**q) for q in report_card_list]
        )
    except Exception as _ex:
        logger.error(f"Ошибка синхронизации записей отпуска {_ex}")

    return logger.info(f"Создано {len(objs)} записей")


def vacation_check():
    obj = VacationSchedule.objects.all()
    for item in obj:
        item.delete()
    VACATION_TYPE = [
        ("dd940e62-cfaf-11e6-bad8-902b345cadc2", "Отпуск за свой счет"),
        ("b51bdb10-8fb9-11e9-80cc-309c23d346b4", "Дополнительный оплачиваемый отпуск пострадавшим на ЧАЭС"),
        ("c3e8c3e8-cfb6-11e6-bad8-902b345cadc2", "Дополнительный неоплачиваемый отпуск пострадавшим на ЧАЭС"),
        ("c3e8c3e7-cfb6-11e6-bad8-902b345cadc2", "Дополнительный учебный отпуск (оплачиваемый)"),
        ("dd940e63-cfaf-11e6-bad8-902b345cadc2", "Дополнительный учебный отпуск без оплаты"),
        ("6f4631a7-df12-11e6-950a-0cc47a7917f4", "Дополнительный отпуск КЛО, ЗКЛО, начальник ИБП"),
        ("56f643c6-bf49-11e9-a3dc-0cc47a7917f4", "Дополнительный оплачиваемый отпуск пострадавшим в аварии на ЧАЭС"),
        ("dd940e60-cfaf-11e6-bad8-902b345cadc2", "Дополнительный ежегодный отпуск"),
        ("ebbd9c67-cfaf-11e6-bad8-902b345cadc2", "Основной"),
    ]
    vacation_list = VacationScheduleList.objects.all()
    all_vacation_list = list()
    for vacation in vacation_list:
        graph_vacacion = get_jsons_data_filter(
            "Document", "ГрафикОтпусков", "Number", vacation.document_number, 0, 0, False, True
        )
        for item in graph_vacacion["value"][0]["Сотрудники"]:
            if DataBaseUser.objects.filter(ref_key=item["Сотрудник_Key"]).exists():
                kwargs_obj = {
                    "employee": DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"]),
                    "start_date": datetime.datetime.strptime(item["ДатаНачала"][:10], "%Y-%m-%d"),
                    "end_date": datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d"),
                    "type_vacation": [v[0] for i, v in enumerate(VACATION_TYPE) if v[0] == item["ВидОтпуска_Key"]][0],
                    "days": item["КоличествоДней"],
                    "years": vacation.document_year,
                    "comment": item["Примечание"],
                }
                all_vacation_list.append(kwargs_obj)
    objs = ""
    try:
        objs = VacationSchedule.objects.bulk_create(
            [VacationSchedule(**q) for q in all_vacation_list]
        )
    except Exception as _ex:
        logger.error(f"Ошибка синхронизации графика отпусков {_ex}")
    return logger.info(f"Создано {len(objs)} записей")


def vacation_schedule_send():
    employee = DataBaseUser.objects.all().exclude(is_active=False)
    for item in employee:
        get_vacation_shedule = VacationSchedule.objects.filter(employee=item, years=2024)
        message = ""
        for unit in get_vacation_shedule:
            message += f"С {unit.start_date.strftime('%d.%m.%Y')} на {unit.days} календарных дней. <br />"
        current_context = {
            "greetings": "Уважаемый"
            if item.gender == "male"
            else "Уважаемая",
            "person": str(item),
            "message": message,
        }
        print(current_context)
        logger.debug(f"Email string: {current_context}")
        text_content = render_to_string(
            "administration_app/vacation_send.html", current_context
        )
        html_content = render_to_string(
            "administration_app/vacation_send.html", current_context
        )
        subject_mail = "График отпусков"
        mail_to = item.email
        msg = EmailMultiAlternatives(
            subject_mail,
            text_content,
            EMAIL_HOST_USER,
            [
                mail_to,
            ],
        )
        msg.attach_alternative(html_content, "text/html")
        try:
            res = msg.send()
        except Exception as _ex:
            logger.debug(f"Failed to send email. {_ex}")


@app.task()
def vacation_schedule():
    def search_vacation(name, people):
        """
        Поиск отпуска по названию в списке людей.

        Аргументы:
            name (str): Имя для поиска.
            people (list): список словарей, представляющих людей, каждый из которых содержит ключ «Сотрудник_Key».

        Возврат:
            list: список словарей, представляющих людей, у которых «Сотрудник_Key» равен данному имени.
        """
        return [element for element in people if element["Сотрудник_Key"] == name]

    vacation_list = list()
    graph_vacacion = get_jsons_data_filter(
        "Document", "ГрафикОтпусков", "Number", "710-лс", 0, 0, False, True
    )
    postponement_of_vacation = get_jsons_data_filter(
        "Document",
        "ПереносОтпуска",
        "year(ИсходнаяДатаНачала)",
        2023,
        0,
        0,
        False,
        False,
    )
    for item in graph_vacacion["value"][0]["Сотрудники"]:
        postponement_list = search_vacation(
            item["Сотрудник_Key"], postponement_of_vacation["value"]
        )
        finded = 0
        if len(postponement_list) == 0:
            vacation_list.append(item)
        else:
            for unit in postponement_list:
                if unit["ИсходнаяДатаНачала"] == item["ДатаНачала"]:
                    for slice_element in unit["Переносы"]:
                        item["ДатаНачала"] = slice_element["ДатаНачала"]
                        item["ДатаОкончания"] = slice_element["ДатаОкончания"]
                        item["КоличествоДней"] = slice_element["КоличествоДней"]
                        item["Примечание"] = "Перенос отпуска №: " + unit["Number"]
                        vacation_list.append(item)
                        finded = 1
                if finded == 0:
                    vacation_list.append(item)
    year = datetime.datetime.today().year
    for report_record in ReportCard.objects.filter(
            Q(report_card_day__year=year) & Q(record_type="18")
    ):
        report_record.delete()
    docs = graph_vacacion["value"][0]["Ref_Key"]
    counter = 1
    report_card_list = list()
    for item in vacation_list:
        if (
                datetime.datetime.strptime(item["ДатаОкончания"][:10], "%Y-%m-%d")
                >= datetime.datetime.today()
        ):
            if DataBaseUser.objects.filter(ref_key=item["Сотрудник_Key"]).exists():
                del item["Ref_Key"]
                del item["LineNumber"]
                del item["ФизическоеЛицо_Key"]
                usr_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"])
                item["Сотрудник_Key"] = DataBaseUser.objects.get(
                    ref_key=item["Сотрудник_Key"]
                ).title
                item["ДатаНачала"] = datetime.datetime.strptime(
                    item["ДатаНачала"][:10], "%Y-%m-%d"
                )
                # item['ДатаОкончания'] = datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d")
                period = list(
                    rrule.rrule(
                        rrule.DAILY,
                        count=item["КоличествоДней"],
                        dtstart=item["ДатаНачала"],
                    )
                )
                for unit in period:
                    if unit > datetime.datetime.today():
                        kwargs_obj = {
                            "report_card_day": unit,
                            "employee": usr_obj,
                            "start_time": datetime.datetime(1, 1, 1, 9, 30),
                            "end_time": datetime.datetime(1, 1, 1, 18, 00),
                            "record_type": "18",
                            "reason_adjustment": "График отпусков"
                            if item["Примечание"] == ""
                            else item["Примечание"],
                            "doc_ref_key": docs,
                        }
                        report_card_list.append(kwargs_obj)
                        counter += 1

    try:
        objs = ReportCard.objects.bulk_create(
            [ReportCard(**q) for q in report_card_list]
        )
    except Exception as _ex:
        logger.error(f"Ошибка синхронизации графика отпусков {_ex}")
    return logger.info(f"Создано {len(objs)} записей")


@app.task()
def report_card_separator_daily(year=0, month=0, day=0):
    if year == 0 and month == 0 and day == 0:
        current_data = datetime.datetime.date(datetime.datetime.today())
    else:
        current_data = datetime.datetime.date(datetime.datetime(year, month, day))
    rec_obj = ReportCard.objects.filter(
        Q(report_card_day=current_data) & Q(record_type="1")
    )
    for item in rec_obj:
        print(item)
        item.delete()
    # current_data1 = datetime.datetime.date(datetime.datetime(2023, 1, 1))
    # current_data2 = datetime.datetime.date(datetime.datetime(2023, 5, 25))
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
    source_url = url
    try:
        response = requests.get(source_url, auth=("proxmox", "PDO#rLv@Server"))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts["data"]:
        usr = item["FULLNAME"]
        # current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
        current_intervals = True if item["ISGO"] == "0" else False
        start_time = datetime.datetime.strptime(
            item["STARTTIME"], "%d.%m.%Y %H:%M:%S"
        ).time()
        if current_intervals:
            end_time = datetime.datetime.strptime(
                item["ENDTIME"], "%d.%m.%Y %H:%M:%S"
            ).time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item["rec_no"])

        search_user = usr.split(" ")
        try:
            user_obj = DataBaseUser.objects.get(
                last_name=search_user[0],
                first_name=search_user[1],
                surname=search_user[2],
            )
            kwargs = {
                "report_card_day": current_data,
                "employee": user_obj,
                "start_time": start_time,
                "end_time": end_time,
                "record_type": "1",
                "current_intervals": current_intervals,
            }
            ReportCard.objects.update_or_create(
                report_card_day=current_data,
                employee=user_obj,
                rec_no=rec_no,
                defaults=kwargs,
            )
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")

    return dicts


def report_card_separator_loc():
    # user_obj = DataBaseUser.objects.get(username='0231_elistratova_av')
    # rec_obj = ReportCard.objects.filter(employee=user_obj)
    # for item in rec_obj:
    #     item.delete()
    # current_data = datetime.datetime.date(datetime.datetime.today())
    current_data1 = datetime.datetime.date(datetime.datetime(2023, 6, 1))
    current_data2 = datetime.datetime.date(datetime.datetime(2023, 6, 7))
    rec_obj = ReportCard.objects.filter(
        Q(report_card_day__gte=current_data1)
        & Q(report_card_day__lte=current_data2)
        & Q(record_type="1")
    )
    for item in rec_obj:
        print(item)
        item.delete()
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data1}&enddate={current_data2}"
    # url = 'http://192.168.10.233:5053/api/time/intervals?startdate=2020-01-01&enddate=2023-06-04&FULLNAME=Елистратова'
    source_url = url
    try:
        response = requests.get(source_url, auth=("proxmox", "PDO#rLv@Server"))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts["data"]:
        usr = item["FULLNAME"]
        current_data = datetime.datetime.strptime(item["STARTDATE"], "%d.%m.%Y").date()
        current_intervals = True if item["ISGO"] == "0" else False
        start_time = datetime.datetime.strptime(
            item["STARTTIME"], "%d.%m.%Y %H:%M:%S"
        ).time()
        if current_intervals:
            end_time = datetime.datetime.strptime(
                item["ENDTIME"], "%d.%m.%Y %H:%M:%S"
            ).time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item["rec_no"])

        search_user = usr.split(" ")
        try:
            user_obj = DataBaseUser.objects.get(
                last_name=search_user[0],
                first_name=search_user[1],
                surname=search_user[2],
            )
            kwargs = {
                "report_card_day": current_data,
                "employee": user_obj,
                "start_time": start_time,
                "end_time": end_time,
                "record_type": "1",
                "current_intervals": current_intervals,
            }
            ReportCard.objects.update_or_create(
                report_card_day=current_data,
                employee=user_obj,
                rec_no=rec_no,
                defaults=kwargs,
            )
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts


@app.task()
def get_sick_leave(year, trigger):
    """
    Получение неявок на рабочее место.
    :param year: Год, за который запрашиваем информацию.
    :param trigger: 1 - больничные, 2 - мед осмотры.
    :return:
    """
    if trigger == 1:
        url = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27Болезнь%27"
        trigger_type = "StandardODATA.Document_БольничныйЛист"
        record_type = "16"
    if trigger == 2:
        url = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20ВидВремени_Key%20eq%20guid%27e58f3899-3c5b-11ea-a186-0cc47a7917f4%27"
        trigger_type = "StandardODATA.Document_ОплатаПоСреднемуЗаработку"
        record_type = "17"

    source_url = url
    print(source_url)
    try:
        response = requests.get(
            source_url, auth=(config("HRM_LOGIN"), config("HRM_PASS"))
        )
        dt = json.loads(response.text)
        rec_number_count = 0
        for item in dt["value"]:
            if item["Recorder_Type"] == trigger_type and item["Active"]:
                interval = get_date_interval(
                    datetime.datetime.strptime(item["Начало"][:10], "%Y-%m-%d"),
                    datetime.datetime.strptime(item["Окончание"][:10], "%Y-%m-%d"),
                )
                rec_list = ReportCard.objects.filter(
                    doc_ref_key=item["ДокументОснование"]
                )
                for record in rec_list:
                    record.delete()
                user_obj = ""

                try:
                    user_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"])
                    print(user_obj)
                except Exception as _ex:
                    logger.error(f"{item['Сотрудник_Key']} не найден в базе данных")
                if user_obj != "":
                    for date in interval:
                        rec_number_count += 1
                        start_time, end_time, type_of_day = check_day(
                            date,
                            datetime.datetime(1, 1, 1, 9, 30).time(),
                            datetime.datetime(1, 1, 1, 18, 0).time(),
                        )
                        kwargs_obj = {
                            "report_card_day": date,
                            "employee": user_obj,
                            "rec_no": rec_number_count,
                            "doc_ref_key": item["ДокументОснование"],
                            "record_type": record_type,
                            "reason_adjustment": "Запись введена автоматически из 1С ЗУП",
                            "start_time": start_time,
                            "end_time": end_time,
                        }
                        ReportCard.objects.update_or_create(
                            report_card_day=date,
                            doc_ref_key=item["ДокументОснование"],
                            defaults=kwargs_obj,
                        )

    except Exception as _ex:
        logger.debug(f"654654654 {_ex}")
        return {"value": ""}
