# Generated by Django 5.0.6 on 2024-11-25 19:22

import django_ckeditor_5.fields
import library_app.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library_app", "0012_alter_poem_content_alter_poem_title"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyEvent",
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
                ("title", models.CharField(max_length=200, verbose_name="Заголовок")),
                (
                    "event_date",
                    models.DateField(blank=True, null=True, verbose_name="Дата"),
                ),
                (
                    "decoding",
                    django_ckeditor_5.fields.CKEditor5Field(
                        blank=True, verbose_name="Расшифровка"
                    ),
                ),
                (
                    "results",
                    django_ckeditor_5.fields.CKEditor5Field(
                        blank=True, verbose_name="Итоги"
                    ),
                ),
                (
                    "event_report",
                    models.FileField(
                        blank=True,
                        upload_to=library_app.models.scan_directory_path,
                        verbose_name="Отчёт по встрече",
                    ),
                ),
                (
                    "event_media",
                    models.FileField(
                        blank=True,
                        upload_to=library_app.models.scan_directory_path,
                        verbose_name="Медиафайл",
                    ),
                ),
                (
                    "participants",
                    models.ManyToManyField(
                        blank=True,
                        related_name="%(app_label)s_%(class)s_employee",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Участники",
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие",
                "verbose_name_plural": "События",
            },
        ),
    ]