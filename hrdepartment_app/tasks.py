# -*- coding: utf-8 -*-
import datetime
import json
import random
import time
import urllib.request
from random import randrange
import csv
import pandas as pd
from dateutil.relativedelta import relativedelta
import requests
import telebot
import xlrd
from dateutil import rrule
from decouple import config
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from loguru import logger

from administration_app.utils import (
    get_jsons_data_filter2,
    get_date_interval,
    get_jsons_data_filter, process_group, adjust_time, process_group_year, export_persons_to_csv, format_name_initials,
    send_notification, get_jsons_data, transliterate,
)
from contracts_app.models import Contract

from customers_app.models import DataBaseUser, Division, Posts, HappyBirthdayGreetings, VacationScheduleList, \
    VacationSchedule, Counteragent, DataBaseUserProfile
from djangoProject.celery import app
from djangoProject.settings import EMAIL_HOST_USER, API_TOKEN, BASE_DIR, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, MEDIA_URL, \
    MEDIA_ROOT
from hrdepartment_app.models import (
    ReportCard,
    WeekendDay,
    check_day,
    ApprovalOficialMemoProcess, ProductionCalendar, get_norm_time_at_custom_day,
)
from telegram_app.management.commands.bot import send_message_tg
from telegram_app.models import TelegramNotification, ChatID


logger.add("debug_archive/debug_task.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'), backtrace=True, diagnose=True)


def xldate_to_datetime(xldate):
    """
        Преобразует Excel-дату (в виде числа) в строку формата 'YYYY-MM-DD HH:MM:SS'.

        Использует библиотеку `xlrd`, чтобы конвертировать Excel-дату (float)
        в объект `datetime`, а затем в удобную для отображения строку.

        Args:
            xldate (float): Дата в формате Excel (серийное число).

        Returns:
            str: Строка даты и времени в формате 'YYYY-MM-DD HH:MM:SS'.
    """
    try:
        # Конвертируем Excel-дату в объект datetime
        datetime_date = xlrd.xldate_as_datetime(xldate, 0)

        # Возвращаем строку в нужном формате
        return datetime_date.strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        # Лучше логировать ошибки, чем просто печатать
        logger.error(f"Ошибка при преобразовании Excel-даты: {e}")
        return None


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
                "text": f"Уведомляем Вас, что для Вам открыт доступ к корпоративному порталу. Данные для авторизации указаны ниже:",
                "sign": f"Ваш логин: <u>{item.username}</u><br>Ваш пароль: <u>{item.user_work_profile.work_email_password}</u>",
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
                logger.error(f"Failed to send email to {mail_to} because {_ex}")
            count += 1
        else:
            errors += 1
        logger.error(f"Failed to change {errors} passwords!")
    return count, errors

@app.task()
def send_email_single_notification(pk):
    item = DataBaseUser.objects.get(pk=pk, is_active=True)
    mail_to = item.email
    subject_mail = (
        f"Уведомление о доступе к Вашей учетной записи на портале"
    )
    current_context = {
        "name": item.first_name,
        "surname": item.surname,
        "text": f"Уведомляем Вас, что для Вам открыт доступ к корпоративному порталу. Данные для авторизации указаны ниже:",
        "sign": f"Ваш логин: <u>{item.username}</u><br>Ваш пароль: <u>{item.user_work_profile.work_email_password}</u>",
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


def change_sign():
    """
    Обновляет поле 'sign' всех объектов модели HappyBirthdayGreetings.

    Эта функция извлекает все записи из модели `HappyBirthdayGreetings` и устанавливает
    для каждого объекта одно и то же значение в поле `sign`. После установки нового значения
    каждый объект сохраняется в базе данных.

    Атрибуты:
        list_obj (QuerySet): Все объекты модели HappyBirthdayGreetings.
        item (HappyBirthdayGreetings): Отдельный объект модели, чьё поле sign обновляется.
    """
    list_obj = HappyBirthdayGreetings.objects.all()
    for item in list_obj:
        item.sign = 'Генеральный директор<br>ООО Авиакомпания "БАРКОЛ"<br>Бархотов В.С.<br>и весь коллектив!!!'
        item.save()



def send_mail(person: DataBaseUser, age: int, record: Posts):
    """
    Отправляет поздравительное email-сообщение пользователю с днем рождения.

    Функция проверяет, было ли уже отправлено сообщение (через флаг `record.email_send`),
    и если нет — формирует персонализированное поздравление, в зависимости от пола и возраста
    пользователя. Сообщение отправляется по электронной почте в HTML и текстовом формате.

    Args:
        person (DataBaseUser): Пользователь, которому отправляется поздравление.
        age (int): Возраст пользователя.
        record (Posts): Объект модели, связанный с записью о рождении, используемый для
                        отслеживания статуса отправки (`email_send`).
    """
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
            logger.error(f"Failed to send email. {_ex}")


@app.task()
def birthday_telegram():
    today = datetime.datetime.today()
    list_obj = DataBaseUser.objects.filter(Q(birthday__day=today.day) & Q(birthday__month=today.month)).exclude(
        is_active=False).order_by('title')
    api_url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    messages = f'<b>\U0001F382 Сегодня {today.strftime("%d.%m.%Y")}:\n</b>'
    count = 0
    for item in list_obj:
        if item.gender == "male":
            age = today.year - item.birthday.year
            messages += f'\n<blockquote>{item.user_work_profile.job.name}\n<b>{item.title}</b>\nпразднует свой {age}-й день рождения!</blockquote>\n'
        else:
            messages += f'\n<blockquote>{item.user_work_profile.job.name}\n<b>{item.title}</b>\nпразднует свой 18-й день рождения! \U0001F339 </blockquote>\n'
        count += 1
    messages += '\n<b>Поздравляем\nС Днём Рождения! \U0001f389 \U0001f389 \U0001f389</b>'
    # Вставка картинки в сообщение, если есть. &#8205; - это символ невидимого неразрывного пробела
    messages += '<a href="https://corp.barkol.ru/static/admin_templates/img/Cakes_Candles_Holidays.jpg">&#8205;</a>'
    # Указаваем в параметрах CHAT_ID и само сообщение
    input_data = json.dumps(
        {
            'chat_id': TELEGRAM_CHAT_ID,
            'parse_mode': 'html',
            'text': messages,
            'disable_web_page_preview': False,
        }
    ).encode()
    if count >= 1:
        try:
            req = urllib.request.Request(
                url=api_url,
                data=input_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                # Тут выводим ответ
                print(response.read().decode('utf-8'))

        except Exception as e:
            print(e)


@app.task()
def holiday_telegram():
    today = datetime.datetime.today()
    api_url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    messages = f'<b>Уважаемые коллеги!\n</b>'
    count = 1
    messages += f'\n<blockquote> Поздравляем вас с Днём Победы! Желаем вам чистого неба над головой, мира и добра. Пусть в вашей жизни всегда будет радость и счастье!</blockquote>\n'
    # Вставка картинки в сообщение, если есть. &#8205; - это символ невидимого неразрывного пробела
    messages += '<a href="https://corp.barkol.ru/static/admin_templates/img/9may.jpg">&#8205;</a>'
    # Указаваем в параметрах CHAT_ID и само сообщение
    input_data = json.dumps(
        {
            'chat_id': TELEGRAM_CHAT_ID,
            'parse_mode': 'html',
            'text': messages,
            'disable_web_page_preview': False,
        }
    ).encode()
    if count >= 1:
        try:
            req = urllib.request.Request(
                url=api_url,
                data=input_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                # Тут выводим ответ
                print(response.read().decode('utf-8'))

        except Exception as e:
            print(e)


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
            "responsible": DataBaseUser.objects.get(pk=1, is_active=True),
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
        try:
            responsible = DataBaseUser.objects.get(pk=1, is_active=True)
        except Exception as _ex:
            responsible = DataBaseUser.objects.get(username='proxmox', is_active=True)
        posts_dict = {
            "post_title": f"День рождения: {format_name_initials(item.title)}",
            "post_description": description,
            "allowed_placed": True,
            "responsible": responsible,
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
                is_active=True
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

def calc_diff(start, end):
    today = datetime.date.today()
    d_start = datetime.datetime.combine(today, start)
    d_end = datetime.datetime.combine(today, end)
    if d_start < d_end:
        diff = d_end - d_start
    else:
        diff = end
    return diff

@app.task()
def save_report():
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
    dates = ReportCard.objects.all().exclude(employee=None)
    report_card_list = list()
    for report_record in dates:
        report_card_list.append([report_record.employee.title, report_record.report_card_day, report_record.start_time, report_record.end_time, report_record.record_type, report_record.manual_input, report_record.reason_adjustment, ])
    # Преобразуем QuerySet в DataFrame
    df = pd.DataFrame.from_records(report_card_list, columns=fields)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df["start"] = pd.to_datetime(df["start"], format="%H:%M:%S")
    df["end"] = pd.to_datetime(df["end"], format="%H:%M:%S")
    df["type"] = pd.to_numeric(df["type"], errors='coerce').fillna(0).astype(int)
    df['types'] = df['type'].map(type_of_report)
    # Сохраняем DataFrame в CSV-файл
    df.to_csv('dates.csv', sep=';', index=False, encoding='utf-8', na_rep='')

@app.task()
def get_year_report(html_mode=True):
    errors = []
    year = datetime.datetime.today().year
    current_date = datetime.datetime.today()
    first_day_of_current_month = datetime.datetime(current_date.year, current_date.month, 1)
    try:
        user_list = ReportCard.objects.filter(Q(report_card_day__year=year) & Q(record_type__in=["1", "13",])&Q(employee__is_active=True)).values_list('employee', flat=True)
        user_set = set(list(user_list))
    except Exception as e:
        errors.append(e)
    report_card_list = list()

    try:
        for report_record in ReportCard.objects.filter(Q(report_card_day__year=year) & Q(report_card_day__lt=first_day_of_current_month ) & Q(employee__in=user_set)).exclude(record_type="18"):
            report_card_list.append([report_record.employee.title, report_record.report_card_day, report_record.start_time, report_record.end_time, report_record.record_type])
    except Exception as e:
        errors.append(e)
    # field names
    fields = ["FIO", "Дата", "Start", "End","Type"]

    # Создание DataFrame
    df = pd.DataFrame(report_card_list, columns=fields)
    try:
        # Преобразование столбцов в нужные типы данных
        df["Дата"] = pd.to_datetime(df["Дата"])
        df["Start"] = pd.to_datetime(df["Start"], format="%H:%M:%S")
        df["End"] = pd.to_datetime(df["End"], format="%H:%M:%S")
        df["Type"] = df["Type"].astype(int)
    except Exception as e:
        errors.append(e)


    # Группируем по FIO и Date и применяем функцию
    df = df.groupby(['FIO', 'Дата']).apply(adjust_time).reset_index(drop=True)

    # Вычисление разности между End и Start и сохранение в новом столбце Time
    df["Time"] = (df["End"] - df["Start"]).dt.total_seconds()  # В часах
    # Проверяем корректность заполнения столбца 'Time', если 14, 15, 16, 17, 20, то устанавливаем время согласно производственному календарю.
    # df['Time'] = df.apply(lambda row: row['Time'] if row['Type'] not in [14, 15, 16, 17, 20] else get_norm_time_at_custom_day(row['Дата']), axis=1)
    df['Time'] = df.apply(lambda row: row['Time'] if row['Type'] not in [14, 15, 16, 17, 20] else get_norm_time_at_custom_day(row['Дата'], type_of_day=row['Type']), axis=1)


    # Группировка по месяцам и ФИО
    df["Month"] = df["Дата"].dt.to_period("M")

    grouped = df.groupby(["Month", "FIO", "Дата"]).apply(process_group_year).reset_index(name="Time")
    grouped = grouped.groupby(["Month", "FIO"])["Time"].sum().reset_index()
    # Вывод результата
    # grouped["Time"] = (grouped["Time"] // 3600) + (((grouped["Time"] % 3600) // 60) / 100) # В часах
    grouped["Time"] = grouped["Time"] // 60 # В минутах

    # Текущая дата
    current_date = datetime.datetime.now()

    # Начало текущего года
    start_of_year = datetime.datetime(current_date.year, 1, 1,0,0,0)

    # Список для хранения первых дней каждого месяца
    first_days_of_months = []

    # Итерация по месяцам с начала года до текущей даты
    current_month_start = start_of_year
    while current_month_start <= current_date:
        first_days_of_months.append(current_month_start)
        current_month_start += relativedelta(months=1)

    # Словарь с вычитаемыми значениями
    subtraction_dict = dict()
    for date in first_days_of_months[:-1]:
        key = date.strftime('%Y-%m')
        norm_time = ProductionCalendar.objects.get(calendar_month=date)
        subtraction_dict[key] = ((norm_time.get_norm_time() // 1) * 60) + (norm_time.get_norm_time() % 1)*60

    grouped = grouped.fillna('')
    # Функция для вычитания значения из словаря
    def subtract_value(row):
        month = str(row["Month"])
        ttime = row["Time"]
        return ttime - subtraction_dict.get(month, 0)

    # Применение функции к столбцу Time
    grouped["Time"] = grouped.apply(subtract_value, axis=1)

    pivot_df = grouped.pivot(index="FIO", columns="Month", values="Time")
    pivot_df = pivot_df.fillna(0)
    pivot_df['Sum'] = pivot_df.sum(axis=1)

    def convert_time(minutes):
        # Преобразуем минуты в часы и минуты
        hours = abs(minutes) // 60
        minutes_left = abs(minutes) % 60
        if minutes < 0:
            return f'-{hours:.0f} ч. {minutes_left:.0f} мин.'
        else:
            return f'{hours:.0f} ч. {minutes_left:.0f} мин.'

    pivot_df = pivot_df.applymap(convert_time)
    html_table = pivot_df.to_html(classes='table table-ecommerce-simple table-striped dataTable mb-0', table_id='datatable-editable', border=1, justify='center')

    if errors:
        return errors
    if html_mode == False:
        return pivot_df
    else:
        return html_table

@app.task()
def get_vacation(year=None):
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
    if not year:
        year = datetime.datetime.today().year

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
                usr_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"], is_active=True)
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

        if len(report_card_list) > 0:
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

        objs = ReportCard.objects.bulk_create(
            [ReportCard(**q) for q in report_card_list]
        )
    except Exception as _ex:
        logger.error(f"Ошибка синхронизации записей отпуска {_ex}")

    return logger.info(f"Создано {len(objs)} записей")

@app.task()
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
                    "employee": DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"], is_active=True),
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

@app.task()
def vacation_schedule_send():
    employee = DataBaseUser.objects.all().exclude(is_active=False)
    # employee = DataBaseUser.objects.filter(is_superuser=True).exclude(is_active=False)
    sender = DataBaseUser.objects.get(last_name="Кирюшкина", is_active=True)
    for item in employee:
        get_vacation_shedule = VacationSchedule.objects.filter(employee=item, years=2025)
        if len(get_vacation_shedule) > 0:
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
            # print(current_context)
            logger.debug(f"Email string: {current_context}")
            # text_content = render_to_string(
            #     "administration_app/vacation_send.html", current_context
            # )
            # html_content = render_to_string(
            #     "administration_app/vacation_send.html", current_context
            # )
            subject_mail = "График отпусков"
            mail_to = item.email
            # msg = EmailMultiAlternatives(
            #     subject_mail,
            #     text_content,
            #     EMAIL_HOST_USER,
            #     [
            #         mail_to,
            #     ],
            # )
            # msg.attach_alternative(html_content, "text/html")
            try:
                send_notification(sender, mail_to, subject_mail, "administration_app/vacation_send.html",
                                  current_context, attachment='', division=3, document=3)
                # res = msg.send()
                # time.sleep(random.randint(5, 10))
            except Exception as _ex:
                logger.debug(f"Failed to send email. {_ex}")


# @app.task()
# def vacation_schedule():
#     def search_vacation(name, people):
#         """
#         Поиск отпуска по названию в списке людей.
#
#         Аргументы:
#             name (str): Имя для поиска.
#             people (list): список словарей, представляющих людей, каждый из которых содержит ключ «Сотрудник_Key».
#
#         Возврат:
#             list: список словарей, представляющих людей, у которых «Сотрудник_Key» равен данному имени.
#         """
#         return [element for element in people if element["Сотрудник_Key"] == name]
#
#     vacation_list = list()
#     graph_vacacion = get_jsons_data_filter(
#         "Document", "ГрафикОтпусков", "Number", "710-лс", 0, 0, False, True
#     )
#     postponement_of_vacation = get_jsons_data_filter(
#         "Document",
#         "ПереносОтпуска",
#         "year(ИсходнаяДатаНачала)",
#         2023,
#         0,
#         0,
#         False,
#         False,
#     )
#     for item in graph_vacacion["value"][0]["Сотрудники"]:
#         postponement_list = search_vacation(
#             item["Сотрудник_Key"], postponement_of_vacation["value"]
#         )
#         finded = 0
#         if len(postponement_list) == 0:
#             vacation_list.append(item)
#         else:
#             for unit in postponement_list:
#                 if unit["ИсходнаяДатаНачала"] == item["ДатаНачала"]:
#                     for slice_element in unit["Переносы"]:
#                         item["ДатаНачала"] = slice_element["ДатаНачала"]
#                         item["ДатаОкончания"] = slice_element["ДатаОкончания"]
#                         item["КоличествоДней"] = slice_element["КоличествоДней"]
#                         item["Примечание"] = "Перенос отпуска №: " + unit["Number"]
#                         vacation_list.append(item)
#                         finded = 1
#                 if finded == 0:
#                     vacation_list.append(item)
#     year = datetime.datetime.today().year
#     for report_record in ReportCard.objects.filter(
#             Q(report_card_day__year=year) & Q(record_type="18")
#     ):
#         report_record.delete()
#     docs = graph_vacacion["value"][0]["Ref_Key"]
#     counter = 1
#     report_card_list = list()
#     for item in vacation_list:
#         if (
#                 datetime.datetime.strptime(item["ДатаОкончания"][:10], "%Y-%m-%d")
#                 >= datetime.datetime.today()
#         ):
#             if DataBaseUser.objects.filter(ref_key=item["Сотрудник_Key"]).exists():
#                 del item["Ref_Key"]
#                 del item["LineNumber"]
#                 del item["ФизическоеЛицо_Key"]
#                 usr_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"])
#                 item["Сотрудник_Key"] = DataBaseUser.objects.get(
#                     ref_key=item["Сотрудник_Key"]
#                 ).title
#                 item["ДатаНачала"] = datetime.datetime.strptime(
#                     item["ДатаНачала"][:10], "%Y-%m-%d"
#                 )
#                 # item['ДатаОкончания'] = datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d")
#                 period = list(
#                     rrule.rrule(
#                         rrule.DAILY,
#                         count=item["КоличествоДней"],
#                         dtstart=item["ДатаНачала"],
#                     )
#                 )
#                 for unit in period:
#                     if unit > datetime.datetime.today():
#                         kwargs_obj = {
#                             "report_card_day": unit,
#                             "employee": usr_obj,
#                             "start_time": datetime.datetime(1, 1, 1, 9, 30),
#                             "end_time": datetime.datetime(1, 1, 1, 18, 00),
#                             "record_type": "18",
#                             "reason_adjustment": "График отпусков"
#                             if item["Примечание"] == ""
#                             else item["Примечание"],
#                             "doc_ref_key": docs,
#                         }
#                         report_card_list.append(kwargs_obj)
#                         counter += 1
#
#     try:
#         objs = ReportCard.objects.bulk_create(
#             [ReportCard(**q) for q in report_card_list]
#         )
#     except Exception as _ex:
#         logger.error(f"Ошибка синхронизации графика отпусков {_ex}")
#     return logger.info(f"Создано {len(objs)} записей")


@app.task()
def vacation_schedule(year=None):
    # Предзагрузка сотрудников
    users = DataBaseUser.objects.all()
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

    # Получение данных
    graph_vacacion = get_jsons_data_filter("Document", "ГрафикОтпусков", "Number", vacation_schedule_number, 0, 0, False, True)
    postponement_of_vacation = get_jsons_data_filter("Document", "ПереносОтпуска", "year(ИсходнаяДатаНачала)", str(year), 0, 0, False, False)

    # Группировка переносов
    postponement_dict = {}
    for unit in postponement_of_vacation["value"]:
        key = unit["Сотрудник_Key"]
        postponement_dict.setdefault(key, []).append(unit)

    # Обработка отпусков
    vacation_list = []
    for item in graph_vacacion["value"][0]["Сотрудники"]:
        postponement_list = postponement_dict.get(item["Сотрудник_Key"], [])
        if not postponement_list:
            vacation_list.append(item)
            continue

        processed = False
        for unit in postponement_list:
            if unit["ИсходнаяДатаНачала"] == item["ДатаНачала"]:
                for slice_element in unit["Переносы"]:
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

    # Удаление старых записей и создание новых
    with transaction.atomic():
        ReportCard.objects.filter(Q(report_card_day__year=year) & Q(record_type="18")).delete()

        docs = graph_vacacion["value"][0]["Ref_Key"]
        report_card_list = []
        today = datetime.datetime.today()

        for item in vacation_list:
            end_date = datetime.datetime.strptime(item["ДатаОкончания"][:10], "%Y-%m-%d")
            # if end_date < today or item["Сотрудник_Key"] not in user_dict:
            #     continue
            if item["Сотрудник_Key"] not in user_dict:
                continue
            start_date = datetime.datetime.strptime(item["ДатаНачала"][:10], "%Y-%m-%d")
            usr_obj = user_dict[item["Сотрудник_Key"]]
            reason = item["Примечание"] if item["Примечание"] else "График отпусков"

            for day in range(item["КоличествоДней"]):
                current_day = start_date + datetime.timedelta(days=day)
                report_card_list.append(ReportCard(
                    report_card_day=current_day,
                    employee=usr_obj,
                    start_time=datetime.time(9, 30),
                    end_time=datetime.time(18, 0),
                    record_type="18",
                    reason_adjustment=reason,
                    doc_ref_key=docs,
                ))

                # if current_day > today:
                #     report_card_list.append(ReportCard(
                #         report_card_day=current_day,
                #         employee=usr_obj,
                #         start_time=datetime.time(9, 30),
                #         end_time=datetime.time(18, 0),
                #         record_type="18",
                #         reason_adjustment=reason,
                #         doc_ref_key=docs,
                #     ))

        # Пакетное сохранение
        batch_size = 1000
        objs_created = 0
        for i in range(0, len(report_card_list), batch_size):
            batch = report_card_list[i:i + batch_size]
            objs = ReportCard.objects.bulk_create(batch)
            objs_created += len(objs)

        logger.info(f"Создано {objs_created} записей")


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
                is_active=True
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
                is_active=True
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
    if trigger == 3:
        url = f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27ДополнительныеВыходныеДниНеОплачиваемые%27"
        trigger_type = "StandardODATA.Document_Отгул"
        record_type = "20"

    source_url = url
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
                    user_obj = DataBaseUser.objects.get(ref_key=item["Сотрудник_Key"], is_active=True)
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
        return {"value": _ex}


@app.task(bind=True)
def send_mail_notification(self, mail_attributes: dict, obj, item):
    """
    Метод для отправки писем
    :param mail_attributes: Словарь с параметрами для отправки писем, содержащий следующие параметры:
    - subject: Тема письма.
    - sender: Адрес отправителя.
    - receiver: Адрес получателя. Тип: список
    - template_name: Название шаблона.
    - attachment_path: Путь к файлу для отправки.
    - current_context: Контекст для шаблона. Для шаблона используется словарь с данными из контекста.

    :return: Возвращает True если письмо отправлено, иначе False
    """
    # Метод для отправки писем
    html_content = render_to_string(
        mail_attributes["template_name"], mail_attributes["current_context"]
    )
    plain_message = strip_tags(html_content)

    try:
        email = EmailMultiAlternatives(mail_attributes["subject"], plain_message, mail_attributes["sender"],
                                       [*mail_attributes["receiver"]])
        email.attach_alternative(html_content, "text/html")
        if "attachment_path" in mail_attributes:
            # file_name = pathlib.Path.joinpath(BASE_DIR, mail_attributes["attachment_path"])
            file_name_string = str(BASE_DIR) + mail_attributes["attachment_path"]
            print(file_name_string)
            with open(file_name_string, 'rb') as file:
                file_content = file.read()
            # mime_type = magic.from_buffer(file_content, mime=True)
            # Extract the filename from the attachment_path

            # email.attach(file_name_string, file_content, mime_type)
            email.attach_file(file_name_string)
        # Send the email
        email.send()
        logger.info(f"Сообщение для {mail_attributes['receiver']} отправлено!")
        obj.change_status(item, True)
        obj.save()
    except Exception as exc:
        logger.debug(f"Failed to send email to {mail_attributes['receiver']} because {exc}")
        raise self.retry(exc=exc)


@app.task()
def upload_json(data, trigger):
    match trigger:
        case 0:
            for item in data:
                counteragent = {
                    "ref_key": item['fields']['ref_key'],
                    "short_name": item['fields']['short_name'] if item['fields']['short_name'] else '',
                    "full_name": item['fields']['full_name'],
                    "inn": item['fields']['inn'],
                    "kpp": item['fields']['kpp'] if item['fields']['kpp'] else '',
                    "ogrn": item['fields']['ogrn'],
                    "type_counteragent": item['fields']['type_counteragent'],
                    "juridical_address": item['fields']['juridical_address'],
                    "physical_address": item['fields']['physical_address'],
                    "email": item['fields']['email'] if item['fields']['email'] else '',
                    "phone": item['fields']['phone'] if item['fields']['phone'] else '',
                    "base_counteragent": item['fields']['base_counteragent'],
                    "director": item['fields']['director'],
                    "accountant": item['fields']['accountant'],
                    "contact_person": item['fields']['contact_person'],
                }
                try:
                    obj, created = Counteragent.objects.update_or_create(inn=item['fields']['inn'],
                                                                         kpp=item['fields']['kpp'],
                                                                         defaults=counteragent)
                    if created:
                        logger.info(f"Объект: {item} успешно создан")
                except Exception as _exc:
                    logger.error(f"Не удалось создать объект  {item}")
        case 1:
            Contract.objects.all().delete()
            for item in data:
                contract = {
                    "contract_counteragent_id": int(item['contract_counteragent']),
                    "contract_number": item['contract_number'],
                    "date_conclusion": item['date_conclusion'] if item['date_conclusion'] else None,
                    "subject_contract": item['subject_contract'],
                    "cost": float(item['cost']) if item['cost'] else 0,
                    "type_of_contract_id": item['type_of_contract'],
                    "type_of_document_id": item['type_of_document'],
                    "closing_date": item['closing_date'] if item['closing_date'] else None,
                    "prolongation": item['prolongation'],
                    "comment": item['comment'],
                    "date_entry": item['date_entry'] if item['date_entry'] else None,
                    "executor_id": item['executor'],
                    "doc_file": item['doc_file'],
                    "access_id": item['access'],
                    "allowed_placed": item['allowed_placed'],
                    "actuality": item['actuality'],
                    "official_information": item['official_information'],
                }

                try:
                    obj, created = Contract.objects.update_or_create(
                        contract_counteragent_id=item['contract_counteragent'],
                        contract_number=item['contract_number'],
                        date_conclusion=item['date_conclusion'],
                        defaults=contract)
                    if created:
                        try:
                            if len(item['divisions']) > 0:
                                obj.divisions.set(item['divisions'])
                        except TypeError:
                            pass
                        try:
                            if len(item['type_property']) > 0:
                                obj.type_property.set(item['type_property'])
                        except TypeError:
                            pass
                        try:
                            if len(item['employee']) > 0:
                                obj.employee.set(item['employee'])
                        except TypeError:
                            pass
                        logger.info(f"Объект: {item} успешно создан")
                except Exception as _exc:
                    logger.error(f"Не удалось создать объект  {_exc}")

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

@app.task()
def get_database_user():
    # ДУБЛИКАТ имеется в customers_util.py
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