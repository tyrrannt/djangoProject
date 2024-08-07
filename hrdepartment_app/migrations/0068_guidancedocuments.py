# Generated by Django 5.0.1 on 2024-02-11 21:13

import datetime
import django.db.models.deletion
import hrdepartment_app.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers_app", "0046_alter_vacationschedulelist_options"),
        ("hrdepartment_app", "0067_officialmemo_creation_retroactively"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuidanceDocuments",
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
                    "ref_key",
                    models.UUIDField(
                        default=uuid.uuid4, unique=True, verbose_name="Уникальный номер"
                    ),
                ),
                (
                    "date_entry",
                    models.DateField(
                        auto_now_add=True, verbose_name="Дата ввода информации"
                    ),
                ),
                (
                    "document_date",
                    models.DateField(
                        default=datetime.datetime.now, verbose_name="Дата документа"
                    ),
                ),
                (
                    "document_name",
                    models.CharField(
                        default="",
                        max_length=200,
                        verbose_name="Наименование документа",
                    ),
                ),
                (
                    "document_number",
                    models.CharField(
                        default="", max_length=18, verbose_name="Номер документа"
                    ),
                ),
                (
                    "allowed_placed",
                    models.BooleanField(
                        default=False, verbose_name="Разрешение на публикацию"
                    ),
                ),
                (
                    "validity_period_start",
                    models.DateField(
                        blank=True, null=True, verbose_name="Документ действует с"
                    ),
                ),
                (
                    "validity_period_end",
                    models.DateField(
                        blank=True, null=True, verbose_name="Документ действует по"
                    ),
                ),
                (
                    "actuality",
                    models.BooleanField(default=False, verbose_name="Актуальность"),
                ),
                (
                    "previous_document",
                    models.URLField(blank=True, verbose_name="Предшествующий документ"),
                ),
                (
                    "applying_for_job",
                    models.BooleanField(
                        default=False,
                        verbose_name="Обязательно к ознакомлению при приеме на работу",
                    ),
                ),
                (
                    "doc_file",
                    models.FileField(
                        blank=True,
                        upload_to=hrdepartment_app.models.prv_directory_path,
                        verbose_name="Файл документа",
                    ),
                ),
                (
                    "scan_file",
                    models.FileField(
                        blank=True,
                        upload_to=hrdepartment_app.models.prv_directory_path,
                        verbose_name="Скан документа",
                    ),
                ),
                (
                    "access",
                    models.ForeignKey(
                        default=5,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="customers_app.accesslevel",
                        verbose_name="Уровень доступа к документу",
                    ),
                ),
                (
                    "document_division",
                    models.ManyToManyField(
                        related_name="guidance_documents_document_division",
                        to="customers_app.division",
                        verbose_name="Подразделения",
                    ),
                ),
                (
                    "document_order",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="hrdepartment_app.documentsorder",
                        verbose_name="Приказ",
                    ),
                ),
                (
                    "employee",
                    models.ManyToManyField(
                        blank=True,
                        related_name="%(app_label)s_%(class)s_employee",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Ответственное лицо",
                    ),
                ),
                (
                    "executor",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_executor",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Исполнитель",
                    ),
                ),
                (
                    "parent_document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="hrdepartment_app.guidancedocuments",
                        verbose_name="Предшествующий документ",
                    ),
                ),
                (
                    "storage_location_division",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guidance_documents_location_division",
                        to="customers_app.division",
                        verbose_name="Подразделение где хранится оригинал",
                    ),
                ),
            ],
            options={
                "verbose_name": "Руководящий документ",
                "verbose_name_plural": "Руководящие документы",
            },
        ),
    ]
