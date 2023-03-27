import pathlib

from customers_app.models import DataBaseUser
from djangoProject.celery import app
from djangoProject.settings import BASE_DIR
from hrdepartment_app.models import ReportCard


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
    file = pathlib.Path.joinpath(BASE_DIR, 'rsync/timecontrol/PersonsWorkLite.txt')
    import re
    result = {}
    try:
        with open(file) as fd:
            for line in fd:
                match = re.search(r'\D*', line)
                search_day = line[len(match[0]):len(match[0]) + 5]
                start_time = line[len(match[0]) + 5:len(match[0]) + 21]
                end_time = line[len(match[0]) + 21:-1]
                if end_time:
                    result.update({f'{match[0]}': [start_time, end_time]})
                    search_user = match[0].split(' ')
                    user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                        surname=search_user[2])
                    kwargs = {
                        'employee': user_obj,
                        'start_time': xldate_to_datetime(start_time),
                        'end_time': xldate_to_datetime(end_time),
                    }
                    ReportCard.objects.update_or_create(kwargs)
        return result
    except IOError:
        pass
    finally:
        fd.close()
