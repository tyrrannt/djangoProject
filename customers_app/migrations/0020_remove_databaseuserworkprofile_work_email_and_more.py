# Generated by Django 4.1.7 on 2023-03-14 13:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0019_delete_useraccessmode'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='databaseuserworkprofile',
            name='work_email',
        ),
        migrations.RemoveField(
            model_name='databaseuserworkprofile',
            name='work_phone',
        ),
    ]
