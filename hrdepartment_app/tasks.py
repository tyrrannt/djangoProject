# -*- coding: utf-8 -*-
import datetime
import json
import pathlib

import requests
from dateutil.relativedelta import relativedelta
from decouple import config
from django.db.models import Q
from loguru import logger

from customers_app.models import DataBaseUser, Division, Posts
from djangoProject.celery import app
from djangoProject.settings import BASE_DIR
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


@app.task()
def happy_birthday():
    today = datetime.datetime.today()
    posts_dict = dict()
    division = [item.pk for item in Division.objects.filter(active=True)]
    list_birthday_people = DataBaseUser.objects.filter(Q(birthday__day=today.day) & Q(birthday__month=today.month))
    description = ''
    for item in list_birthday_people:
        description = f'Сегодня {item} празднует свой {today.year - item.birthday.year}-й день рождения!'
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
    # current_data = datetime.datetime.date(datetime.datetime.today())
    current_data1 = datetime.datetime.date(datetime.datetime(2023, 1, 1))
    current_data2 = datetime.datetime.date(datetime.datetime(2023, 5, 25))
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data1}&enddate={current_data2}"
    source_url = url
    try:
        response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts['data']:
        usr = item['FULLNAME']
        current_data = item['STARTDATE']
        start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
        end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
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
            }
            ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj,
                                                defaults=kwargs)
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts


def report_card_separator_loc():
    current_data = datetime.datetime.date(datetime.datetime.today())
    url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
    source_url = url
    try:
        response = requests.get(source_url, auth=(config('TC_LOGIN'), config('TC_PASS')))
    except Exception as _ex:
        return f"{_ex} ошибка"
    dicts = json.loads(response.text)
    for item in dicts['data']:
        usr = item['FULLNAME']
        start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
        if item['ISGO'] == '0':
            end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
        else:
            end_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time() + relativedelta(
                minutes=1)

        search_user = usr.split(' ')
        try:
            user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                surname=search_user[2])
            kwargs = {
                'report_card_day': current_data,
                'employee': user_obj,
                'start_time': start_time,
                'end_time': end_time,
                'record_type': 1,
            }
            ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj,
                                                defaults=kwargs)
        except Exception as _ex:
            logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
    return dicts
