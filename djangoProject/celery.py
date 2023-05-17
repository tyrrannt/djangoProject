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
        # 'schedule': crontab(minute=0, hour=7),
        'schedule': crontab(minute='*/5'),
    },
    'birthday_gift': {
        'task': 'hrdepartment_app.tasks.happy_birthday',
        'schedule': crontab(minute='*/5'),
    },
}