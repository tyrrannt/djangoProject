# Generated by Django 4.2 on 2023-05-20 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0040_weekendday_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductionCalendar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('calendar_month', models.DateField(blank=True, null=True, verbose_name='Месяц')),
                ('number_calendar_days', models.PositiveIntegerField(blank=True, default=0, null=True, verbose_name='Количество календарных дней')),
                ('number_working_days', models.PositiveIntegerField(blank=True, default=0, null=True, verbose_name='Количество рабочих дней')),
                ('number_days_off_and_holidays', models.PositiveIntegerField(blank=True, default=0, null=True, verbose_name='Количество выходных и празднечных дней')),
                ('description', models.CharField(blank=True, default='', max_length=200, verbose_name='Описание')),
            ],
            options={
                'verbose_name': 'Месяц в производственом календаре',
                'verbose_name_plural': 'Производственный календарь',
            },
        ),
    ]
