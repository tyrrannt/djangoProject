import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

app = Celery('djangoProject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'send-spam': {
        'task': 'hrdepartment_app.tasks.report_card_separator',
        'schedule': crontab(minute=10, hour=0),
    }
}