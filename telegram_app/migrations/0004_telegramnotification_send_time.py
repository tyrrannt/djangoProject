# Generated by Django 4.2.1 on 2023-06-26 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('telegram_app', '0003_alter_telegramnotification_sending_counter'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramnotification',
            name='send_time',
            field=models.TimeField(blank=True, null=True, verbose_name='Время отправки'),
        ),
    ]
