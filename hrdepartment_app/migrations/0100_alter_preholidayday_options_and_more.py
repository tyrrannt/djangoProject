# Generated by Django 5.0.6 on 2024-09-15 13:04

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0099_alter_provisions_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="preholidayday",
            options={
                "ordering": ["-preholiday_day"],
                "verbose_name": "Предпраздничный день",
                "verbose_name_plural": "Предпраздничные дни",
            },
        ),
        migrations.AlterModelOptions(
            name="productioncalendar",
            options={
                "ordering": ["-calendar_month"],
                "verbose_name": "Месяц в производственом календаре",
                "verbose_name_plural": "Производственный календарь",
            },
        ),
        migrations.AlterModelOptions(
            name="weekendday",
            options={
                "ordering": ["-weekend_day"],
                "verbose_name": "Праздничный день",
                "verbose_name_plural": "Праздничные дни",
            },
        ),
        migrations.CreateModel(
            name="TimeSheet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date",
                    models.DateField(blank=True, null=True, verbose_name="Дата табеля"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Примечания")),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Ответственный",
                    ),
                ),
            ],
            options={
                "verbose_name": "Табель учета рабочего времени",
                "verbose_name_plural": "Табели учета рабочего времени",
                "ordering": ("-date",),
            },
        ),
    ]
