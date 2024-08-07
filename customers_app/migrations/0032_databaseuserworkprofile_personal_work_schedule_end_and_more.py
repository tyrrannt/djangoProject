# Generated by Django 4.2 on 2023-05-25 15:05

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0031_alter_job_type_of_job'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseuserworkprofile',
            name='personal_work_schedule_end',
            field=models.TimeField(default=datetime.time(18, 0), verbose_name='Окончание рабочего времени'),
        ),
        migrations.AddField(
            model_name='databaseuserworkprofile',
            name='personal_work_schedule_start',
            field=models.TimeField(default=datetime.time(9, 30), verbose_name='Начало рабочего времени'),
        ),
    ]
