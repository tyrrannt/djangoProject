# Generated by Django 4.2 on 2023-05-30 16:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0033_happybirthdaygreetings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='happybirthdaygreetings',
            name='age_from',
            field=models.IntegerField(default=0, verbose_name=''),
        ),
        migrations.AlterField(
            model_name='happybirthdaygreetings',
            name='age_to',
            field=models.IntegerField(default=0, verbose_name=''),
        ),
    ]
