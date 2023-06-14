# -*- coding: utf-8 -*-
import datetime
import json
import pathlib
from random import randrange

import requests
from dateutil.relativedelta import relativedelta
from decouple import config
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from loguru import logger

from customers_app.models import DataBaseUser, Division, Posts, HappyBirthdayGreetings
from djangoProject.celery import app
from djangoProject.settings import BASE_DIR, EMAIL_HOST_USER
from hrdepartment_app.models import ReportCard

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


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
    print('It is work!')


def change_sign():
    list_obj = HappyBirthdayGreetings.objects.all()
    for item in list_obj:
        item.sign = 'Генеральный директор<br>ООО Авиакомпания "БАРКОЛ"<br>Бархотов В.С.<br>и весь коллектив!!!'
        item.save()


def send_mail(person: DataBaseUser, age: int, record: Posts):
    if not record.email_send:
        mail_to = person.email
        gender = person.gender
        if gender == 'male':
            color = '#b5e0ff'
        else:
            color = '#ffc0cb'
        subject_mail = f'{person.first_name} {person.surname} поздравляем Вас с днем рождения!'
        greet = HappyBirthdayGreetings.objects.filter(Q(gender=gender) & Q(age_from__lte=age) & Q(age_to__gte=age))
        rec_no = randrange(len(greet))
        text = greet[rec_no].greetings
        current_context = {
            'name': person.first_name,
            'surname': person.surname,
            'text': greet[rec_no].greetings,
            'sign': greet[rec_no].sign,
            'color': color,
        }
        logger.debug(f'Email string: {current_context}')
        text_content = render_to_string('hrdepartment_app/happy_birthday.html', current_context)
        html_content = render_to_string('hrdepartment_app/happy_birthday.html', current_context)
        plain_message = strip_tags(html_content)
        # first_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
        #                                    [mail_to, ])
        # first_msg.attach_alternative(html_content, "text/html")
        try:
            mail.send_mail(subject_mail, plain_message, EMAIL_HOST_USER, [mail_to, EMAIL_HOST_USER, ], html_message=html_content)
            record.email_send = True
            record.save()
        except Exception as _ex:
            logger.debug(f'Failed to send email. {_ex}')


def happy_birthday_loc():
    today = datetime.datetime.today()
    posts_dict = dict()
    division = [item.pk for item in Division.objects.filter(active=True)]
    list_birthday_people = DataBaseUser.objects.filter(Q(birthday__day=today.day) & Q(birthday__month=today.month))
    description = ''
    for item in list_birthday_people:
        age = today.year - item.birthday.year
        description = f'Сегодня {item} празднует свой {age}-й день рождения!'
        posts_dict = {
            'post_description': description,
            'allowed_placed': True,
            'responsible': DataBaseUser.objects.get(pk=1),
            'post_date_start': datetime.datetime.today(),
            'post_date_end': datetime.datetime.today(),
        }
        post, created = Posts.objects.update_or_create(post_description=description, defaults=posts_dict)

        if created:
            post.post_divisions.add(*division)
            post.save()
            if not post.email_send:
                send_mail(item, age, post)
        else:
            if not post.email_send:
                send_mail(item, age, Posts.objects.filter(post_description=description).first())

@app.task()
def happy_birthday():
    today = datetime.datetime.today()
    posts_dict = dict()
    division = [item.pk for item in Division.objects.filter(active=True)]
    list_birthday_people = DataBaseUser.objects.filter(Q(birthday__day=today.day) & Q(birthday__month=today.month)).exclude(is_active=False)
    description = ''
    for item in list_birthday_people:
        age = today.year - item.birthday.year
        description = f'Сегодня {item} празднует свой {age}-й день рождения!'
        posts_dict = {
            'post_description': description,
            'allowed_placed': True,
            'responsible': DataBaseUser.objects.get(pk=1),
            'post_date_start': datetime.datetime.today(),
            'post_date_end': datetime.datetime.today(),
        }
        post, created = Posts.objects.update_or_create(post_description=description, defaults=posts_dict)

        if created:
            post.post_divisions.add(*division)
            post.save()
            if not post.email_send:
                send_mail(item, age, post)
        else:
            if not post.email_send:
                send_mail(item, age, Posts.objects.filter(post_description=description).first())


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
        response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts['data']:
        usr = item['FULLNAME']
        # current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
        current_intervals = True if item['ISGO'] == '0' else False
        start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
        if current_intervals:
            end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item['rec_no'])

        search_user = usr.split(' ')
        try:
            user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                surname=search_user[2])
            kwargs = {
                'report_card_day': current_data,
                'employee': user_obj,
                'start_time': start_time,
                'end_time': end_time,
                'record_type': '1',
                'current_intervals': current_intervals,
            }
            ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj, rec_no=rec_no,
                                                defaults=kwargs)
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts


@app.task()
def report_card_separator_daily():
    current_data = datetime.datetime.date(datetime.datetime.today())
    rec_obj = ReportCard.objects.filter(Q(report_card_day=current_data) & Q(record_type='1'))
    for item in rec_obj:
        print(item)
        item.delete()
    # current_data1 = datetime.datetime.date(datetime.datetime(2023, 1, 1))
    # current_data2 = datetime.datetime.date(datetime.datetime(2023, 5, 25))
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
    source_url = url
    try:
        response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts['data']:
        usr = item['FULLNAME']
        # current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
        current_intervals = True if item['ISGO'] == '0' else False
        start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
        if current_intervals:
            end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item['rec_no'])

        search_user = usr.split(' ')
        try:
            user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                surname=search_user[2])
            kwargs = {
                'report_card_day': current_data,
                'employee': user_obj,
                'start_time': start_time,
                'end_time': end_time,
                'record_type': '1',
                'current_intervals': current_intervals,
            }
            ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj, rec_no=rec_no,
                                                defaults=kwargs)
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
    rec_obj = ReportCard.objects.filter(Q(report_card_day__gte=current_data1) & Q(report_card_day__lte=current_data2) & Q(record_type='1'))
    for item in rec_obj:
        print(item)
        item.delete()
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data1}&enddate={current_data2}"
    # url = 'http://192.168.10.233:5053/api/time/intervals?startdate=2020-01-01&enddate=2023-06-04&FULLNAME=Елистратова'
    source_url = url
    try:
        response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts['data']:
        usr = item['FULLNAME']
        current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
        current_intervals = True if item['ISGO'] == '0' else False
        start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
        if current_intervals:
            end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
        else:
            end_time = datetime.datetime(1, 1, 1, 0, 0).time()
        rec_no = int(item['rec_no'])

        search_user = usr.split(' ')
        try:
            user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                surname=search_user[2])
            kwargs = {
                'report_card_day': current_data,
                'employee': user_obj,
                'start_time': start_time,
                'end_time': end_time,
                'record_type': '1',
                'current_intervals': current_intervals,
            }
            ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj, rec_no=rec_no,
                                                defaults=kwargs)
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts
