# -*- coding: utf-8 -*-
import datetime
import pathlib

from loguru import logger

from customers_app.models import DataBaseUser
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
def report_card_separator():
    try:
        file = pathlib.Path.joinpath(BASE_DIR, 'rsync/timecontrol/PersonsWorkLite.txt')
        logger.info(f'File received: {file}')
    except Exception as _ex:
        logger.info(f'File opening error: {_ex}')
    import re
    result = {}
    try:
        with open(file, encoding='cp1251') as fd:
            for line in fd:
                match = re.search(r'\D*', line)
                start_time = line[len(match[0]) + 5:len(match[0]) + 21]
                end_time = line[len(match[0]) + 21:-1]
                if end_time:
                    result.update({f'{match[0]}': [start_time, end_time]})
                    search_user = match[0].split(' ')
                    try:
                        user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                            surname=search_user[2])
                        report_card_day = datetime.datetime.strptime(
                            xldate_to_datetime(float(start_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S')

                        kwargs = {
                            'report_card_day': report_card_day.date(),
                            'employee': user_obj,
                            'start_time': datetime.datetime.strptime(
                                xldate_to_datetime(float(start_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S').time(),
                            'end_time': datetime.datetime.strptime(
                                xldate_to_datetime(float(end_time.replace(',', '.'))), '%Y-%m-%d %H:%M:%S').time(),
                        }
                        ReportCard.objects.update_or_create(report_card_day=report_card_day.date(), employee=user_obj,
                                                            defaults=kwargs)
                        logger.error(f'File write: {kwargs}')
                    except Exception as _ex:
                        logger.error(f'{match[0]} not found in the database: {_ex}')
        return result
    except IOError:
        logger.error(f'File opening error: {IOError}')
    finally:
        fd.close()
