# -*- coding: utf-8 -*-
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

app = Celery('djangoProject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'load_report_card': {
        'task': 'hrdepartment_app.tasks.report_card_separator',
        'schedule': crontab(minute='*/5'),
    },
    'report_card_separator_daily': {
        'task': 'hrdepartment_app.tasks.report_card_separator_daily',
        'schedule': crontab(hour=23, minute=45),
    },
    'birthday_gift': {
        'task': 'hrdepartment_app.tasks.happy_birthday',
        'schedule': crontab(minute='*/5'),
    },
}

"""
Запуск планировщика (только в виртуальной среде: $source venv/bin/activate) :  $celery -A djangoProject worker -l INFO --beat
Пример планировщика: Смысл

crontab(): Выполняйте каждую минуту.
crontab(minute=0, hour=0): Выполнять ежедневно в полночь.
crontab(minute=0, hour='*/3') :Выполнять каждые три часа: полночь, 3 утра, 6 утра, 9 утра, полдень, 3 вечера, 6 вечера, 9 вечера.
crontab(minute=0, hour='0,3,6,9,12,15,18,21'): То же, что и предыдущий.
crontab(minute='*/15'): Выполняется каждые 15 минут.
crontab(day_of_week='sunday'): Выполняется каждую минуту (!) по воскресеньям.
crontab(minute='*', hour='*', day_of_week='sun'): То же, что и предыдущий.
crontab(minute='*/10',hour='3,17,22', day_of_week='thu,fri'): Выполнять каждые десять минут, но только между 3-4 часами утра, 5-6 часами вечера и 10-11 часами вечера по четвергам или пятницам.
crontab(minute=0, hour='*/2,*/3'): Выполнять каждый четный час и каждый час, кратный трем. Это означает: в каждый час за исключением: 1 утра, 5 утра, 7 утра, 11 утра, 1 вечера, 5 вечера, 7 вечера, 11 вечера.
crontab(minute=0, hour='*/5'): Выполнение часа, кратного 5. Это означает, что он срабатывает в 15:00, а не в 17:00 (так как 15:00 равно 24-часовому значению часов «15», которое делится на 5).
crontab(minute=0, hour='*/3,8-17'): Выполнять каждый час, кратный 3, и каждый час в рабочее время (с 8 утра до 5 вечера).
crontab(0, 0, day_of_month='2'): Выполнять во второй день каждого месяца.
crontab(0, 0, day_of_month='2-30/2'): Выполняйте в каждый четный день.
crontab(0, 0, day_of_month='1-7,15-21'): Выполнять в первую и третью недели месяца.
crontab(0, 0, day_of_month='11', month_of_year='5'): Выполняется одиннадцатого мая каждого года.
crontab(0, 0, month_of_year='*/3'): Выполнять каждый день в первый месяц каждого квартала.
"""