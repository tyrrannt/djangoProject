import datetime
from datetime import date, time
import hashlib
import logging
import os
import pathlib

logger = logging.getLogger(__name__)
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from dateutil import rrule
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from dateutil.rrule import DAILY
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q, Max
from django.utils import timezone
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field
from docx import Document
from docxtpl import DocxTemplate, Listing
from htmldocx import HtmlToDocx

from administration_app.utils import (
    ending_day,
    format_name_initials,
    timedelta_to_time,
    change_approval_status,
)
from contracts_app.models import CompanyProperty, Estate, TypeProperty
from customers_app.models import (
    DataBaseUser,
    Counteragent,
    HarmfulWorkingConditions,
    Division,
    Job,
    AccessLevel,
    HistoryChange,
    Affiliation,
)
from djangoProject import settings
from djangoProject.settings import BASE_DIR, EMAIL_HOST_USER, MEDIA_URL, DEBUG
from library_app.models import DocumentForm
from telegram_app.models import TelegramNotification, ChatID
from msoffice2pdf import convert
from openpyxl import load_workbook
from core import logger

WORK_DAY_HOURS = 8.5  # нормальный рабочий день
SHORT_DAY_HOURS = 7.5  # укороченный день (обычно пятница)
WORK_DAY_TIME = int(WORK_DAY_HOURS * 3600)
SHORT_DAY_TIME = int(SHORT_DAY_HOURS * 3600)


def custom_upload_to(instance, filename):
    """
    Универсальная upload_to — верхнего уровня, безопасная для миграций.
    Параметры берутся из атрибутов модели:
    - prefix_attr_<field>
    - prefix_ext_<field>  (опционально)
    - prefix_file_<field> (опционально)
    """

    # 1. Определяем, из какого поля вызвана функция
    field_name = None
    for f in instance._meta.fields:
        value = getattr(instance, f.name)
        if hasattr(value, 'name') and value and filename == os.path.basename(value.name):
            field_name = f.name

            break

    # 2. Если файл уже существует — вернуть старое имя
    if instance.pk and field_name:
        old_instance = instance.__class__.objects.filter(pk=instance.pk).first()
        if old_instance:
            old_file = getattr(old_instance, field_name)
            if old_file:
                return old_file.name

    # 3. Префикс и параметры
    prefix = getattr(instance, f'prefix_attr_{field_name}', None) \
             or getattr(instance, 'prefix_attr', None) \
             or instance.__class__.__name__.upper()

    prefix_file = getattr(instance, f'prefix_file_{field_name}', None)
    ext = getattr(instance, f'prefix_ext_{field_name}', None) \
          or os.path.splitext(filename)[1].lstrip('.') or 'pdf'

    # 4. UID
    max_pk = (instance.__class__.objects.aggregate(pk_max=models.Max('pk'))['pk_max'] or 0) + 1
    uid = f"{max_pk:07}"
    executor_pk = getattr(getattr(instance, 'executor', None), 'pk', 0)
    user_uid = f"{executor_pk:07}"

    # 5. Дата
    datefield = getattr(instance, 'date_entry', datetime.date.today())
    year = datefield.year if isinstance(datefield, datetime.date) else datetime.date.today().year
    # 6. Имя файла
    custom_name = f"{prefix}-{uid}-{datefield}-{prefix_file}-{user_uid}.{ext}"

    return os.path.join("docs", prefix, str(year), custom_name)


def filename_creator(instance, filename, prefix: str, datefield, filetype: str):
    """
    Генерирует уникальное имя файла на основе переданных параметров.

    Используется для формирования имен файлов при загрузке, основываясь на префиксе,
    дате, типе файла и уникальном идентификаторе. Уникальный идентификатор вычисляется
    на основе максимального значения поля `pk` в модели.

    Args:
        instance (Model): Экземпляр модели, к которой относится файл.
        filename (str): Исходное имя файла, используется для извлечения расширения.
        prefix (str): Префикс, добавляемый к имени файла.
        datefield (Union[datetime.date, Any]): Дата или значение, используемое для
                                               формирования части имени файла.
        filetype (str): Тип файла, добавляемый к имени.

    Returns:
        str: Сформированное имя файла в формате:
             '{prefix}-{date_str}-{filetype}-{uid}.{ext}'
    """
    max_pk = (instance.__class__.objects.aggregate(Max('pk'))['pk__max'] or 0) + 1
    uid = f'{max_pk:07}'

    ext = os.path.splitext(filename)[1].lstrip('.') or 'pdf'  # fallback если расширения нет

    if isinstance(datefield, datetime.date):
        date_str = datefield.strftime("%Y%m%d")
    else:
        date_str = str(datefield)

    return f"{prefix}-{date_str}-{filetype}-{uid}.{ext}"


# Create your models here.
def contract_directory_path(instance, filename):
    return f"hr/medical/{filename}"


# def mdc_directory_path_pmo(instance, filename):
#     prefix = "MED"
#     datefield = instance.date_entry
#     max_pk = (instance.__class__.objects.aggregate(Max('pk'))['pk__max'] or 0) + 1
#     uid = f'{max_pk:07}'
#     user_uid = f"{instance.executor.pk:07}"
#
#     custom_name = (
#         f"{prefix}-{uid}-{str(instance.working_status)}-{str(datefield)}-{user_uid}.docx"
#     )
#     return os.path.join("hr", "medical", str(user_uid), custom_name)
#
# def mdc_directory_path_po(instance, filename):
#     prefix = "MED"
#     datefield = instance.date_entry
#     max_pk = (instance.__class__.objects.aggregate(Max('pk'))['pk__max'] or 0) + 1
#     uid = f'{max_pk:07}'
#     user_uid = f"{instance.executor.pk:07}"
#
#     custom_name = (
#         f"{prefix}-{uid}-{str(instance.working_status)}-{str(datefield)}-{user_uid}PO.docx"
#     )
#     return os.path.join("hr", "medical", str(user_uid), custom_name)

# @receiver(post_save, sender=Medical)
# def rename_file_name(sender, instance, **kwargs):
#     try:
#         change = 0
#         # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
#         uid = f"{instance.pk:07}"
#         user_uid = f"{instance.person.pk:07}"
#         filename_pmo = (
#             f"MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}.docx"
#         )
#         filename_po = (
#             f"MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}PO.docx"
#         )
#         Med(
#             instance,
#             f"media/hr/medical/{user_uid}",
#             filename_pmo,
#             filename_po,
#             user_uid,
#         )
#         if f"hr/medical/{user_uid}/{filename_pmo}" != instance.medical_direction:
#             change = 1
#             instance.medical_direction = f"hr/medical/{user_uid}/{filename_pmo}"
#         if f"hr/medical/{user_uid}/{filename_po}" != instance.medical_direction2:
#             change = 1
#             instance.medical_direction2 = f"hr/medical/{user_uid}/{filename_po}"
#         if change == 1:
#             instance.save()
#     except Exception as _ex:
#         logger.error(f"Ошибка при переименовании файла {_ex}")

def poa_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def jds_directory_path(instance, filename):
    return custom_upload_to(instance, filename)


def ins_directory_path(instance, filename):
    return custom_upload_to(instance, filename)


def ins_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def lpi_directory_path(instance, filename):
    return custom_upload_to(instance, filename)


def lpi_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def prv_directory_path(instance, filename):
    return custom_upload_to(instance, filename)


def prv_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def gdc_directory_path(instance, filename):
    return custom_upload_to(instance, filename)


def gdc_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def brf_directory_path_doc(instance, filename):
    return custom_upload_to(instance, filename)


def brf_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def lbp_directory_path_doc(instance, filename):
    return custom_upload_to(instance, filename)


def lbp_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def opr_directory_path_scan(instance, filename):
    return custom_upload_to(instance, filename)


def ord_directory_path(instance, filename):
    year = instance.document_date
    return f"docs/ORD/{year.year}/{filename}"


def team_directory_path(instance, filename):
    year = instance.date_create
    return f"docs/ORD/{year.year}/{year.month}/{filename}"


def outfit_directory_path(instance, filename):
    prefix = "CARD"
    filetype = "SCAN"  # или подставь по логике, можно и вытянуть из instance, если надо
    datefield = instance.outfit_card_date

    custom_name = filename_creator(instance, filename, prefix, datefield, filetype)
    year = datefield.year if isinstance(datefield, datetime.date) else str(datefield)[:4]

    return os.path.join("docs", "CARD", str(year), custom_name)


class Documents(models.Model):
    class Meta:
        abstract = True

    ref_key = models.UUIDField(
        verbose_name="Уникальный номер", default=uuid.uuid4, unique=True
    )
    # type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
    #                                      null=True)
    date_entry = models.DateField(
        verbose_name="Дата ввода информации", auto_now_add=True
    )
    executor = models.ForeignKey(
        DataBaseUser,
        verbose_name="Исполнитель",
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(app_label)s_%(class)s_executor",
    )
    document_date = models.DateField(
        verbose_name="Дата документа", default=datetime.datetime.now
    )
    document_name = models.CharField(
        verbose_name="Наименование документа", max_length=200, default=""
    )
    document_number = models.CharField(
        verbose_name="Номер документа", max_length=18, default=""
    )

    access = models.ForeignKey(
        AccessLevel,
        verbose_name="Уровень доступа к документу",
        on_delete=models.SET_NULL,
        null=True,
        default=5,
    )
    employee = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Ответственное лицо",
        blank=True,
        related_name="%(app_label)s_%(class)s_employee",
    )
    allowed_placed = models.BooleanField(
        verbose_name="Разрешение на публикацию", default=False
    )
    validity_period_start = models.DateField(
        verbose_name="Документ действует с", blank=True, null=True
    )
    validity_period_end = models.DateField(
        verbose_name="Документ действует по", blank=True, null=True
    )
    actuality = models.BooleanField(verbose_name="Актуальность", default=False)
    previous_document = models.URLField(
        verbose_name="Примечание к предшествующему документу", blank=True
    )
    parent_document = models.ForeignKey(
        "self", verbose_name="Предшествующий документ", on_delete=models.SET_NULL, null=True, blank=True
    )
    applying_for_job = models.BooleanField(
        verbose_name="Обязательно к ознакомлению при приеме на работу", default=False
    )
    document_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'№ {self.document_number} от {self.document_date.strftime("%d.%m.%Y")}'


class Purpose(models.Model):
    class Meta:
        verbose_name = "Цель служебной записки"
        verbose_name_plural = "Цели служебной записки"

    title = models.CharField(verbose_name="Наименование", max_length=300)

    def __str__(self):
        return self.title

    @staticmethod
    def get_absolute_url():
        return reverse("hrdepartment_app:purpose_list")

    def get_data(self):
        return {
            "pk": self.pk,
            "title": self.title,
        }


class MedicalOrganisation(models.Model):
    class Meta:
        verbose_name = "Медицинская организация"
        verbose_name_plural = "Медицинскик организации"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    description = models.CharField(
        verbose_name="Наименование", max_length=250, default=""
    )
    alternative_name = models.CharField(
        verbose_name="Наименование", max_length=300, default=""
    )
    ogrn = models.CharField(verbose_name="ОГРН", max_length=13, default="")
    address = models.CharField(verbose_name="Адрес", max_length=250, default="")
    email = models.CharField(verbose_name="Email", max_length=150, default="")
    phone = models.CharField(verbose_name="Телефон", max_length=150, default="")

    def __str__(self):
        return self.description

    def get_title(self):
        return self.description

    @staticmethod
    def get_absolute_url():
        return reverse("hrdepartment_app:medicalorg_list")

    def get_data(self):
        return {
            "pk": self.pk,
            "description": self.description,
            "ogrn": self.ogrn,
            "address": self.address,
        }

def Med(obj_model, filepath: str, filename_pmo: str, filename_po: str, request_user_id: int) -> bool:
    """Генерирует файлы направлений на медицинский осмотр (ПМО) и психиатрическое освидетельствование (ПО).

    Заполняет docx-шаблоны данными сотрудника, организации, вредными факторами,
    типом и видом осмотра, и сохраняет готовые документы в медиа-хранилище.

    Args:
        obj_model (Medical): Экземпляр модели медицинского направления.
        filepath (str): Относительный путь к директории сохранения файлов.
        filename_pmo (str): Имя файла для направления на медосмотр (DOCX).
        filename_po (str): Имя файла для психиатрического освидетельствования (DOCX).
        request_user_id (int): Идентификатор пользователя-инициатора для логирования.

    Returns:
        bool: True при успешной генерации и сохранении файлов, False при возникновении ошибки.
    """
    # Преобразуем в словарь для быстрого и безопасного поиска (O(1))
    inspection_type = {
        "1": "Предварительный",
        "2": "Периодический",
        "3": "Внеплановый",
    }

    try:
        # Проверяем цепочку связей до division_affiliation безопасно
        work_profile = getattr(obj_model.person, 'user_work_profile', None)
        job = getattr(work_profile, 'job', None)
        division_affiliation = getattr(job, 'division_affiliation', None)

        if division_affiliation and division_affiliation.pk == 2:
            doc_path = "static/DocxTemplates/med.docx"
        else:
            doc_path = "static/DocxTemplates/med2.docx"

        doc = DocxTemplate(pathlib.Path(BASE_DIR) / doc_path)
        doc2 = DocxTemplate(pathlib.Path(BASE_DIR) / "static/DocxTemplates/med3.docx")

        gender = "муж." if obj_model.person.gender == "male" else "жен."

        # Безопасное формирование списка вредных факторов
        harmful = [f"{item.code}: {item.name}" for item in obj_model.harmful.iterator()]

        div_address = ""
        divisions = getattr(work_profile, 'divisions', None)
        if divisions and divisions.address:
            division_str = str(divisions)
            div_address = (
                f"Адрес обособленного подразделения места производственной деятельности {division_str[6:]} "
                f"(далее – {division_str}): {divisions.address}."
            )

        # Безопасное получение title (без риска StopIteration)
        title_raw = inspection_type.get(obj_model.type_inspection, "неизвестный")

        context = {
            "gender": gender,
            "title": title_raw.lower(),
            "number": obj_model.number,
            "birthday": obj_model.person.birthday.strftime("%d.%m.%Y") if obj_model.person.birthday else "",
            "division": divisions,
            "job": job,
            "FIO": obj_model.person,
            "snils": getattr(obj_model.person.user_profile, 'snils', ''),
            "oms": getattr(obj_model.person.user_profile, 'oms', ''),
            "status": obj_model.get_working_status_display(),
            "harmful": ", ".join(harmful),
            "organisation": obj_model.organisation,
            "ogrn": getattr(obj_model.organisation, 'ogrn', ''),
            "email": getattr(obj_model.organisation, 'email', ''),
            "tel": getattr(obj_model.organisation, 'phone', ''),
            "address": getattr(obj_model.organisation, 'address', ''),
            "div_address": div_address,
        }

        context2 = {
            "gender": gender,
            "number": obj_model.number,
            "birthday": obj_model.person.birthday.strftime("%d.%m.%Y") if obj_model.person.birthday else "",
            "division": divisions,
            "job": job,
            "FIO": obj_model.person,
            "snils": getattr(obj_model.person.user_profile, 'snils', ''),
            "oms": getattr(obj_model.person.user_profile, 'oms', ''),
            "div_address": div_address,
        }

        # Рендеринг и сохранение происходят только если context собран без ошибок
        doc.render(context)
        doc2.render(context2)

        path_obj = pathlib.Path(BASE_DIR) / filepath
        path_obj.mkdir(parents=True, exist_ok=True)

        doc.save(path_obj / filename_pmo)
        doc2.save(path_obj / filename_po)

        return True

    except Exception as e:
        # Используем .first() чтобы избежать падения DoesNotExist внутри обработчика ошибок
        initiator = DataBaseUser.objects.filter(pk=request_user_id).first()

        # logger.exception запишет в лог полный стек вызовов (traceback),
        # вы точно будете знать на какой строке произошла проблема
        logger.exception(f"Ошибка заполнения файла {filename_pmo}. Инициатор: {initiator}")

        # Функция не должна создавать сломанные файлы при ошибке,
        # возвращаем False чтобы вызывающий код понял что генерация не удалась
        return False


# def Med(obj_model, filepath, filename_pmo, filename_po, request):
#     inspection_type = [
#         ("1", "Предварительный"),
#         ("2", "Периодический"),
#         ("3", "Внеплановый"),
#     ]
#
#     if obj_model.person.user_work_profile.job.division_affiliation.pk == 2:
#         doc = DocxTemplate(
#             pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/med.docx")
#         )
#     else:
#         doc = DocxTemplate(
#             pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/med2.docx")
#         )
#     doc2 = DocxTemplate(
#         pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/med3.docx")
#     )
#     if obj_model.person.gender == "male":
#         gender = "муж."
#     else:
#         gender = "жен."
#     try:
#         harmful = list()
#         for items in obj_model.harmful.iterator():
#             harmful.append(f"{items.code}: {items.name}")
#         if obj_model.person.user_work_profile.divisions.address:
#             division = str(obj_model.person.user_work_profile.divisions)
#             div_address = (
#                 f"Адрес обособленного подразделения места производственной деятельности {division[6:]} "
#                 f"(далее – {obj_model.person.user_work_profile.divisions}): "
#                 f"{obj_model.person.user_work_profile.divisions.address}."
#             )
#         else:
#             div_address = ""
#         context = {
#             "gender": gender,
#             "title": next(
#                 x[1] for x in inspection_type if x[0] == obj_model.type_inspection
#             ).lower(),
#             "number": obj_model.number,
#             "birthday": obj_model.person.birthday.strftime("%d.%m.%Y"),
#             "division": obj_model.person.user_work_profile.divisions,
#             "job": obj_model.person.user_work_profile.job,
#             "FIO": obj_model.person,
#             "snils": obj_model.person.user_profile.snils,
#             "oms": obj_model.person.user_profile.oms,
#             "status": obj_model.get_working_status_display(),
#             "harmful": ", ".join(harmful),
#             "organisation": obj_model.organisation,
#             "ogrn": obj_model.organisation.ogrn,
#             "email": obj_model.organisation.email,
#             "tel": obj_model.organisation.phone,
#             "address": obj_model.organisation.address,
#             "div_address": div_address,
#         }
#         context2 = {
#             "gender": gender,
#             "number": obj_model.number,
#             "birthday": obj_model.person.birthday.strftime("%d.%m.%Y"),
#             "division": obj_model.person.user_work_profile.divisions,
#             "job": obj_model.person.user_work_profile.job,
#             "FIO": obj_model.person,
#             "snils": obj_model.person.user_profile.snils,
#             "oms": obj_model.person.user_profile.oms,
#             "div_address": div_address,
#         }
#     except Exception as _ex:
#         DataBaseUser.objects.get(pk=request)
#         logger.debug(
#             f"Ошибка заполнения файла {filename_pmo}: {DataBaseUser.objects.get(pk=request)} {_ex}"
#         )
#         context = {}
#         context2 = {}
#     doc.render(context)
#     doc2.render(context2)
#     path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
#     if not path_obj.exists():
#         path_obj.mkdir(parents=True)
#     doc.save(pathlib.Path.joinpath(path_obj, filename_pmo))
#     doc2.save(pathlib.Path.joinpath(path_obj, filename_po))
#     # ToDo: Попытка конвертации docx в pdf в Linux. Не работает
#     # convert(filename, (filename[:-4]+'pdf'))
#     # convert(filepath)


class Medical(models.Model):
    class Meta:
        verbose_name = "Медицинское направление"
        verbose_name_plural = "Медицинские направления"
        ordering = ["-date_entry"]

    type_of = [("1", "Поступающий на работу"), ("2", "Работающий")]

    inspection_view = [
        ("1", "Медицинский осмотр"),
        ("2", "Психиатрическое освидетельствование"),
    ]

    inspection_type = [
        ("1", "Предварительный"),
        ("2", "Периодический"),
        ("3", "Внеплановый"),
    ]

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    number = models.CharField(verbose_name="Номер", max_length=11, default="")
    person = models.ForeignKey(
        DataBaseUser, verbose_name="Сотрудник", on_delete=models.SET_NULL, null=True
    )
    date_entry = models.DateField(verbose_name="Дата ввода информации", null=True)
    date_of_inspection = models.DateField(verbose_name="Дата осмотра", null=True)
    organisation = models.ForeignKey(
        MedicalOrganisation,
        verbose_name="Медицинская организация",
        on_delete=models.SET_NULL,
        null=True,
    )
    working_status = models.CharField(
        verbose_name="Статус",
        max_length=40,
        choices=type_of,
        help_text="",
        blank=True,
        default="",
    )
    view_inspection = models.CharField(
        verbose_name="Вид осмотра",
        max_length=40,
        choices=inspection_view,
        help_text="",
        blank=True,
        default="",
    )
    type_inspection = models.CharField(
        verbose_name="Тип осмотра",
        max_length=15,
        choices=inspection_type,
        help_text="",
        blank=True,
        default="",
    )
    medical_direction = models.FileField(verbose_name="Файл ПМО", blank=True)  # upload_to=contract_directory_path,
    medical_direction2 = models.FileField(verbose_name="Файл ПО", blank=True)  # upload_to=contract_directory_path,
    harmful = models.ManyToManyField(
        HarmfulWorkingConditions, verbose_name="Вредные условия труда"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def get_data(self) -> dict:
        """Возвращает структурированные данные медицинского направления для AJAX/DataTables.

        Returns:
            dict: Словарь с форматированными полями направления (pk, number, date_entry,
                person, organisation, working_status, view_inspection, type_inspection).
        """
        return {
            "pk": self.pk,
            "number": self.number,
            "date_entry": f"{self.date_entry:%d.%m.%Y} г.",
            "person": self.person.get_title(),
            "organisation": self.organisation.get_title(),
            "working_status": self.get_working_status_display(),
            "view_inspection": self.get_view_inspection_display(),
            "type_inspection": self.get_type_inspection_display(),
        }

    def __str__(self) -> str:
        """Строковое представление медицинского направления.

        Returns:
            str: Строка формата '<номер> <сотрудник>'.
        """
        return f"{self.number} {self.person}"

    def generate_med_files(self) -> None:
        """Генерирует файлы бланков ПМО и ПО на основе текущих атрибутов направления.

        Формирует пути сохранения, вызывает функцию Med() и обновляет поля
        medical_direction и medical_direction2.
        """
        uid = f"{self.pk:07}"
        user_uid = f"{self.person.pk:07}"
        filename_pmo = f"MED-{uid}-{self.working_status}-{self.date_entry}-{uid}.docx"
        filename_po = f"MED-{uid}-{self.working_status}-{self.date_entry}-{uid}PO.docx"

        # Генерация файлов
        Med(self, f"media/hr/medical/{user_uid}", filename_pmo, filename_po, user_uid)

        # Обновляем поля путей
        self.medical_direction = f"hr/medical/{user_uid}/{filename_pmo}"
        self.medical_direction2 = f"hr/medical/{user_uid}/{filename_po}"

    def save(self, *args, **kwargs) -> None:
        """Сохраняет запись медицинского направления и перегенерирует сопутствующие документы.

        Args:
            *args: Позиционные аргументы сохранения.
            **kwargs: Именованные аргументы сохранения.
        """
        is_new = self.pk is None
        super().save(*args, **kwargs)  # сначала сохраняем, чтобы был pk
        self.generate_med_files()
        super().save(update_fields=["medical_direction", "medical_direction2"])  # обновляем только пути


#
#
# @receiver(post_save, sender=Medical)
# def rename_file_name(sender, instance, **kwargs):
#     try:
#         change = 0
#         # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
#         uid = f"{instance.pk:07}"
#         user_uid = f"{instance.person.pk:07}"
#         filename_pmo = (
#             f"MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}.docx"
#         )
#         filename_po = (
#             f"MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}PO.docx"
#         )
#         Med(
#             instance,
#             f"media/hr/medical/{user_uid}",
#             filename_pmo,
#             filename_po,
#             user_uid,
#         )
#         if f"hr/medical/{user_uid}/{filename_pmo}" != instance.medical_direction:
#             change = 1
#             instance.medical_direction = f"hr/medical/{user_uid}/{filename_pmo}"
#         if f"hr/medical/{user_uid}/{filename_po}" != instance.medical_direction2:
#             change = 1
#             instance.medical_direction2 = f"hr/medical/{user_uid}/{filename_po}"
#         if change == 1:
#             instance.save()
#     except Exception as _ex:
#         logger.error(f"Ошибка при переименовании файла {_ex}")


class PlaceProductionActivity(models.Model):
    class Meta:
        verbose_name = "Место назначения"
        verbose_name_plural = "Места назначения"

    name = models.CharField(verbose_name="Наименование", max_length=250)
    address = models.CharField(verbose_name="Адрес", max_length=250, blank=True)
    short_name = models.CharField(verbose_name="Краткое наименование", max_length=30, default="", blank=True)
    use_team_orders = models.BooleanField(verbose_name="Использовать в приказах",
                                          default=False)  # Использовать командные orders
    additional_payment = models.DecimalField(verbose_name="Дополнительная оплата", default=0, blank=True,
                                             decimal_places=2, max_digits=10)
    email = models.EmailField(verbose_name="Электронная почта", max_length=250, blank=True)
    work_email_password = models.CharField(
        verbose_name="Пароль от корпоративной почты",
        max_length=50,
        blank=True,
        default="",
    )
    in_planning = models.BooleanField(verbose_name='Используется в планировании', default=False)
    ticket_control = models.BooleanField(verbose_name='Вести контроль билетов', default=False)
    icao_code = models.CharField(
        verbose_name="Код ICAO метеостанции",
        max_length=4,
        blank=True,
        default="",
        help_text="4-буквенный ICAO код ближайшего аэродрома/метеостанции (например, UNNT, USRR, ULLI, UUEE)",
    )
    latitude = models.FloatField(
        verbose_name="Широта",
        null=True,
        blank=True,
        help_text="Географическая широта объекта в градусах",
    )
    longitude = models.FloatField(
        verbose_name="Долгота",
        null=True,
        blank=True,
        help_text="Географическая долгота объекта в градусах",
    )
    weather_monitoring_enabled = models.BooleanField(
        verbose_name="Мониторинг погоды",
        default=False,
        help_text="Автоматический сбор и архивирование METAR/TAF сводок",
    )
    elevation_msl_m = models.FloatField(
        verbose_name="Высота над уровнем моря (MSL, м)",
        null=True,
        blank=True,
        help_text="Абсолютная высота площадки над средним уровнем моря (MSL) в метрах",
    )
    ELEVATION_SOURCES = (
        ("MANUAL", "Ручной ввод"),
        ("DEM", "Цифровая модель рельефа (DEM)"),
        ("AERODROME", "Аэродромная съемка"),
        ("IMPORTED", "Импорт из 1С"),
    )
    elevation_source = models.CharField(
        verbose_name="Источник высоты",
        max_length=20,
        choices=ELEVATION_SOURCES,
        default="MANUAL",
        help_text="Метод определения высотной отметки площадки",
    )
    WEATHER_SOURCE_PREFERENCES = (
        ("AUTO", "Авто (METAR при наличии, иначе координаты)"),
        ("METAR_ONLY", "Только METAR"),
        ("COORDINATES_ONLY", "Только расчёт по координатам"),
    )
    weather_source_preference = models.CharField(
        verbose_name="Приоритет источника погоды",
        max_length=20,
        choices=WEATHER_SOURCE_PREFERENCES,
        default="AUTO",
        help_text="Правило выбора источника метеоданных для МПД",
    )
    weather_last_sync_at = models.DateTimeField(
        verbose_name="Время последней синхронизации погоды",
        null=True,
        blank=True,
        help_text="Дата и время последнего успешного опроса метеоданных (UTC)",
    )
    weather_sync_status = models.CharField(
        verbose_name="Статус последней синхронизации",
        max_length=50,
        blank=True,
        default="",
        help_text="Результат последней синхронизации (например, OK, NO_DATA, ERROR)",
    )

    def __str__(self) -> str:
        """Строковое представление места производственной деятельности.

        Returns:
            str: Полное наименование объекта.
        """
        return str(self.name)

    def get_data(self) -> dict:
        """Возвращает сериализованные данные МПД для AJAX DataTables.

        Returns:
            dict: Словарь с полями МПД (pk, name, short_name, address, email,
                additional_payment, use_team_orders, in_planning, ticket_control,
                icao_code, weather_monitoring_enabled, elevation_msl_m, elevation_source,
                weather_last_sync_at, weather_sync_status).
        """
        return {
            "pk": self.pk,
            "name": self.name,
            "short_name": self.short_name or "—",
            "address": self.address or "—",
            "email": self.email or "—",
            "additional_payment": f"{self.additional_payment:.2f} ₽" if self.additional_payment else "0.00 ₽",
            "use_team_orders": "Да" if self.use_team_orders else "Нет",
            "in_planning": "Да" if self.in_planning else "Нет",
            "ticket_control": "Да" if self.ticket_control else "Нет",
            "icao_code": self.icao_code.upper() if self.icao_code else "—",
            "weather_monitoring_enabled": "Да" if self.weather_monitoring_enabled else "Нет",
            "elevation_msl_m": f"{self.elevation_msl_m:.0f} м" if self.elevation_msl_m is not None else "—",
            "elevation_source": self.get_elevation_source_display(),
            "weather_source_preference": self.get_weather_source_preference_display(),
            "weather_last_sync_at": self.weather_last_sync_at.strftime("%d.%m.%Y %H:%M") if self.weather_last_sync_at else "—",
            "weather_sync_status": self.weather_sync_status or "—",
        }

    @staticmethod
    def get_absolute_url() -> str:
        """Возвращает канонический URL реестра мест производственной деятельности.

        Returns:
            str: URL-путь к списку МПД.
        """
        return reverse("hrdepartment_app:place_list")


class ReasonForCancellation(models.Model):
    class Meta:
        verbose_name = "Причина отмены"
        verbose_name_plural = "Причины отмены"

    name = models.CharField(verbose_name="Наименование", max_length=250, default="")

    def __str__(self):
        return self.name

    def get_title(self):
        return str(self.name)


class OfficialMemo(models.Model):
    class Meta:
        verbose_name = "Служебная записка"
        verbose_name_plural = "Служебные записки"
        ordering = ["-date_of_creation"]

    type_of_accommodation = [("1", "Квартира"), ("2", "Гостиница")]

    type_of_trip = [("1", "Служебная поездка"), ("2", "Командировка")]

    memo_type = [
        ("1", "Направление"),
        ("2", "Продление"),
        ("3", "Без выезда"),
    ]
    document_extension = models.ForeignKey(
        "self",
        verbose_name="Документ основания",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extension",
    )
    date_of_creation = models.DateTimeField(
        verbose_name="Дата и время создания", auto_now_add=True
    )  # При миграции указать 1 и вставить timezone.now()
    official_memo_type = models.CharField(
        verbose_name="Тип СП",
        max_length=9,
        choices=memo_type,
        help_text="",
        default="1",
    )
    person = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник",
        on_delete=models.SET_NULL,
        null=True,
        related_name="employee",
    )
    purpose_trip = models.ForeignKey(
        Purpose,
        verbose_name="Цель",
        on_delete=models.SET_NULL,
        null=True,
    )
    period_from = models.DateField(verbose_name="Дата начала", null=True)
    period_for = models.DateField(verbose_name="Дата окончания", null=True)
    place_departure = models.ForeignKey(
        PlaceProductionActivity,
        verbose_name="Место отправления",
        on_delete=models.SET_NULL,
        null=True,
        related_name="place_departure",
    )
    place_production_activity = models.ManyToManyField(
        PlaceProductionActivity,
        verbose_name="МПД",
        related_name="place_production_activity",
    )
    accommodation = models.CharField(
        verbose_name="Проживание",
        max_length=9,
        choices=type_of_accommodation,
        help_text="",
        blank=True,
        default="",
    )
    type_trip = models.CharField(
        verbose_name="Тип поездки",
        max_length=9,
        choices=type_of_trip,
        help_text="",
        blank=True,
        default="",
    )
    order = models.ForeignKey(
        "DocumentsOrder",
        verbose_name="Приказ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    comments = models.CharField(
        verbose_name="Примечание", max_length=250, default="", blank=True
    )
    document_accepted = models.BooleanField(
        verbose_name="Документ принят", default=False
    )
    responsible = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник",
        on_delete=models.SET_NULL,
        null=True,
        related_name="responsible",
    )
    cancellation = models.BooleanField(verbose_name="Отмена", default=False)
    reason_cancellation = models.ForeignKey(
        ReasonForCancellation,
        verbose_name="Причина отмены",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    expenses = models.BooleanField(verbose_name="Пометка выплаты", default=False)
    expenses_summ = models.DecimalField(
        verbose_name="Сумма аванса",
        default=0,
        max_digits=10,
        decimal_places=2,
    )
    history_change = GenericRelation(HistoryChange)
    title = models.CharField(
        verbose_name="Наименование", max_length=200, default="", blank=True
    )
    creation_retroactively = models.BooleanField(
        verbose_name="Документ введен задним числом", default=False
    )

    def __str__(self):
        return self.title

    def get_title(self):
        return self.title

    def get_data(self):
        place = [str(item) for item in self.place_production_activity.iterator()]
        if self.type_trip == "1":
            if self.official_memo_type == "1":
                type_trip = "СП"
            elif self.official_memo_type == "2":
                type_trip = "СП+"
            else:
                type_trip = "БВ"
        else:
            if self.official_memo_type == "1":
                type_trip = "К"
            else:
                type_trip = "К+"

        return {
            "pk": self.pk,
            "type_trip": type_trip,
            "person": str(self.person),
            "job": str(self.person.user_work_profile.job),
            "place_production_activity": "; ".join(place),
            "purpose_trip": str(self.purpose_trip),
            "period_from": f"{self.period_from:%d.%m.%Y} г.",  # .strftime(""),
            "period_for": f"{self.period_for:%d.%m.%Y} г.",  # .strftime(""),
            "accommodation": str(self.get_accommodation_display()),
            "order": str(self.order) if self.order else "",
            "comments": str(self.comments),
            "cancellation": self.cancellation,
            "document_accepted": self.document_accepted,
            "date_order": self.period_from,
            "expenses_summ": self.expenses_summ,
        }


@receiver(pre_save, sender=OfficialMemo)
def fill_title(sender, instance, **kwargs):
    if instance.official_memo_type == "1":
        type_memo = "(СП):" if instance.type_trip == "1" else "(К):"
    elif instance.official_memo_type == "2":
        type_memo = "(СП+):" if instance.type_trip == "1" else "(К+):"
    else:
        type_memo = "(БВ)"
    instance.title = f'{type_memo} {format_name_initials(instance.person) if instance.person else "None"} с {instance.period_from.strftime("%d.%m.%Y")} по {instance.period_for.strftime("%d.%m.%Y")}'


class ApprovalProcess(models.Model):
    """
    Служебная записка
    """

    class Meta:
        abstract = True

    date_of_creation = models.DateTimeField(
        verbose_name="Дата и время создания", auto_now_add=True
    )
    person_executor = models.ForeignKey(
        DataBaseUser,
        verbose_name="Исполнитель",
        on_delete=models.SET_NULL,
        null=True,
        related_name="person_executor",
    )
    submit_for_approval = models.BooleanField(
        verbose_name="Передан на согласование", default=False
    )
    comments_for_approval = models.CharField(
        verbose_name="Комментарий для согласования",
        max_length=200,
        help_text="",
        blank=True,
        default="",
    )
    person_agreement = models.ForeignKey(
        DataBaseUser,
        verbose_name="Согласующее лицо",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_agreement",
    )
    document_not_agreed = models.BooleanField(
        verbose_name="Документ согласован", default=False
    )
    reason_for_approval = models.CharField(
        verbose_name="Примечание к согласованию",
        max_length=200,
        help_text="",
        blank=True,
        default="",
    )
    person_distributor = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник НО",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_distributor",
    )
    location_selected = models.BooleanField(
        verbose_name="Выбрано место проживания", default=False
    )
    person_department_staff = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник ОК",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_department_staff",
    )
    process_accepted = models.BooleanField(verbose_name="Издан приказ", default=False)
    person_clerk = models.ForeignKey(
        DataBaseUser,
        verbose_name="Делопроизводитель",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_clerk",
    )
    originals_received = models.BooleanField(
        verbose_name="Получены оригиналы", default=False
    )
    person_hr = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник ОК",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_hr",
    )
    hr_accepted = models.BooleanField(verbose_name="Документы проверены", default=False)
    person_accounting = models.ForeignKey(
        DataBaseUser,
        verbose_name="Сотрудник Бухгалтерии",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_accounting",
    )
    accepted_accounting = models.BooleanField(
        verbose_name="Принято в бухгалтерии", default=False
    )
    history_change = GenericRelation(HistoryChange)


class ApprovalOficialMemoProcessManager(models.Manager):
    """Менеджер бизнес-процессов служебных записок."""

    def get_expense_report_data(self):
        """Получает агрегированные и детализированные данные для отчета по затратам на командировки.

        Returns:
            QuerySet: Набор значений согласованных бухгалтерией процессов с финансовыми показателями.
        """
        return self.select_related(
            'document',
            'document__person',
            'document__person__user_work_profile',
            'document__person__user_work_profile__job'
        ).filter(
            document__isnull=False,
            document__person__isnull=False,
            accepted_accounting=True,
            cancellation=False
        ).values(
            'id',
            'document__official_memo_type',
            'document__period_from',
            'document__period_for',
            'document__person__id',
            'document__person__last_name',
            'document__person__first_name',
            'document__person__surname',
            'document__person__service_number',
            'document__person__user_work_profile__job__name',
            'document__person__user_work_profile__job__type_of_job',
            'daily_allowance',
            'travel_expense',
            'accommodation_expense',
            'other_expense',
            'prepaid_expense_summ'
        )


class ApprovalOficialMemoProcess(ApprovalProcess):
    """
    Бизнес-процесс служебной записки
    """

    class Meta:
        verbose_name = "Служебная записка по служебной поездке"
        verbose_name_plural = "Служебные записки по служебным поездкам"
        ordering = ["-document__period_from"]

    type_of = [("1", "Квартира"), ("2", "Гостиница")]
    # ref_key = models.CharField(default=uuid.uuid4, max_length=37, null=True, blank=True)
    document = models.OneToOneField(
        OfficialMemo,
        verbose_name="Документ",
        on_delete=models.CASCADE,
        null=True,
        related_name="docs",
    )
    accommodation = models.CharField(
        verbose_name="Проживание",
        max_length=9,
        choices=type_of,
        help_text="",
        blank=True,
        default="",
    )
    order = models.ForeignKey(
        "DocumentsOrder",
        verbose_name="Приказ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    email_send = models.BooleanField(verbose_name="Письмо отправлено", default=False)
    cancellation = models.BooleanField(verbose_name="Отмена", default=False)
    check_apart = models.BooleanField(verbose_name="Не проверять квартиру", default=True)
    reason_cancellation = models.ForeignKey(
        ReasonForCancellation,
        verbose_name="Причина отмены",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    date_receipt_original = models.DateField(
        verbose_name="Дата получения", null=True, blank=True
    )
    originals_docs_comment = models.CharField(
        verbose_name="Примечание", max_length=100, help_text="", blank=True, default=""
    )
    submitted_for_signature = models.DateField(
        verbose_name="Дата передачи на подпись", null=True, blank=True
    )
    date_transfer_hr = models.DateField(
        verbose_name="Дата передачи в ОК", null=True, blank=True
    )
    number_business_trip_days = models.IntegerField(verbose_name="Дни СП", default=0)
    number_flight_days = models.IntegerField(verbose_name="Дни ЛД", default=0)
    start_date_trip = models.DateField(
        verbose_name="Дата начала по СЗ", null=True, blank=True
    )
    end_date_trip = models.DateField(
        verbose_name="Дата окончания по СЗ", null=True, blank=True
    )
    date_transfer_accounting = models.DateField(
        verbose_name="Дата передачи в бухгалтерию", null=True, blank=True
    )
    prepaid_expense = models.CharField(
        verbose_name="Пометка выплаты",
        max_length=100,
        help_text="",
        blank=True,
        default="",
    )
    prepaid_expense_summ = models.DecimalField(
        verbose_name="Сумма авансового отчета",
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    daily_allowance = models.DecimalField(
        verbose_name="Суточные",
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    travel_expense = models.DecimalField(
        verbose_name="Проезд",
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    accommodation_expense = models.DecimalField(
        verbose_name="Дополнительное проживание",
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    other_expense = models.DecimalField(
        verbose_name="Прочие расходы",
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    apartment = models.ForeignKey(
        'customers_app.Apartments',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    date_of_arrival = models.DateField(
        verbose_name="Дата приезда на МПД", null=True, blank=True
    )
    date_of_departure = models.DateField(
        verbose_name="Дата отъезда с МПД", null=True, blank=True
    )

    @property
    def needs_ticket_control(self):
        if self.document:
            return self.document.place_production_activity.filter(ticket_control=True).exists()
        return False

    objects = ApprovalOficialMemoProcessManager()

    def save(self, *args, **kwargs):
        # Автоматически рассчитываем сумму всех расходов
        summ = (
                self.daily_allowance +
                self.travel_expense +
                self.accommodation_expense +
                self.other_expense
        )
        if summ > 0:
            self.prepaid_expense_summ = summ
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super(ApprovalOficialMemoProcess, self).__init__(*args, **kwargs)
        self._save_initial_state()

    def _save_initial_state(self):
        """Фиксирует снимок ключевых статусов бизнес-процесса для отслеживания перехода состояний."""
        self._initial_state = {
            "submit_for_approval": bool(self.submit_for_approval),
            "document_not_agreed": bool(self.document_not_agreed),
            "location_selected": bool(self.location_selected),
            "process_accepted": bool(self.process_accepted),
            "originals_received": bool(self.originals_received),
            "date_receipt_original": self.date_receipt_original,
            "date_transfer_accounting": self.date_transfer_accounting,
            "accepted_accounting": bool(self.accepted_accounting),
            "cancellation": bool(self.cancellation),
            "email_send": bool(self.email_send),
        }

    def __str__(self):
        return str(self.document)

    def get_data(self):
        if self.document.official_memo_type == "3":
            location_selected = "--//--"
            process_accepted = "--//--"
        else:
            location_selected = (
                format_name_initials(self.person_distributor, self)
                if self.location_selected
                else ""
            )
            process_accepted = (
                format_name_initials(self.person_department_staff, self)
                if self.process_accepted
                else ""
            )
        return {
            "pk": self.pk,
            "document_type": "К" if self.document.type_trip == "2" else "СП",
            "document": str(self.document.title),
            "submit_for_approval": format_name_initials(self.person_executor, self) if self.submit_for_approval else "",
            "document_not_agreed": format_name_initials(self.person_agreement, self)
            if self.document_not_agreed
            else "",
            "location_selected": location_selected,
            "process_accepted": process_accepted,
            "accepted_accounting": format_name_initials(self.person_accounting, self)
            if self.accepted_accounting
            else "",
            "accommodation": str(self.get_accommodation_display()),
            "order": str(self.order) if self.order else "",
            "comments": str(self.document.comments),
            "cancellation": self.cancellation,
            "originals_received": True if self.originals_received and self.date_transfer_hr else False,
            "expenses_summ": self.document.expenses_summ if self.process_accepted and self.document.expenses_summ > 0 else "",
            "expenses_summ_check": self.document.expenses if self.process_accepted and self.document.expenses_summ > 0 else "-",
        }

    @staticmethod
    def get_absolute_url():
        return reverse("hrdepartment_app:bpmemo_list")

    def send_mail(self, title: str, trigger: int = 0, force: bool = True) -> tuple[bool, str]:
        """Отправляет служебные почтовые уведомления по процессу согласования поездки.

        Делегирует исполнение в MemoNotificationService с асинхронной отправкой через Celery,
        сохраняя обратную совместимость для вызовов из интерфейса и админки.

        Args:
            title (str): Тема сообщения (используется при отмене процесса).
            trigger (int, optional): Идентификатор действия:
                0 — отмена служебной поездки,
                1 — повторное уведомление командируемому сотруднику,
                2 — письмо исполнителю,
                3 — письмо на общую почту летной службы. По умолчанию 0.
            force (bool, optional): Принудительная отправка в обход дедупликации. Defaults to True.

        Returns:
            tuple[bool, str]: Кортеж (успех_отправки, адрес_получателя_или_текст_ошибки).
        """
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        if trigger == 0:
            MemoNotificationService.dispatch_event(
                self.pk,
                "CANCELLED",
                extra_context={"reason": str(self.reason_cancellation or title)},
                force=force,
            )
            recipient = self.document.person.email if (self.document and self.document.person) else "все участники"
            return True, recipient

        if trigger in (1, 2, 3):
            if not self.process_accepted:
                return False, "Приказ по служебной поездке еще не издан."

            MemoNotificationService.dispatch_event(self.pk, "ORDER_ISSUED", force=force)
            mail_to = ""
            if trigger == 2:
                mail_to = self.person_executor.email if self.person_executor else ""
            elif trigger == 3:
                mail_to = getattr(settings, "FLIGHT_DEPARTMENT_EMAIL", "fly@barkol.ru")
            else:
                mail_to = self.document.person.email if (self.document and self.document.person) else ""

            return True, mail_to or "отправлено асинхронно"

        return False, "Неизвестный триггер или условия отправки не выполнены."



def create_xlsx(instance):
    from openpyxl import load_workbook

    filepath = pathlib.Path.joinpath(MEDIA_URL, "wb.xlsx")
    wb = load_workbook(filepath)
    ws = wb.active()
    ws["C3"] = instance.document.person
    filepath2 = pathlib.Path.joinpath(MEDIA_URL, "wb-1.xlsx")
    ws.save(filepath2)


@receiver(pre_save, sender=ApprovalOficialMemoProcess)
def hr_accepted(sender, instance, **kwargs):
    obj_list = ReportCard.objects.filter(
        Q(doc_ref_key=instance.pk) & Q(employee=instance.document.person)
    )
    for item in obj_list:
        item.delete()
    if not instance.cancellation and instance.pk:
        if instance.start_date_trip and instance.end_date_trip:
            interval = list(
                rrule.rrule(
                    rrule.DAILY,
                    dtstart=instance.start_date_trip,
                    until=instance.end_date_trip,
                )
            )
        else:
            interval = list(
                rrule.rrule(
                    rrule.DAILY,
                    dtstart=instance.document.period_from,
                    until=instance.document.period_for,
                )
            )
        if len(interval) > 0:
            for date in interval:
                if instance.document.type_trip == "1":
                    record_type = "14"
                else:
                    record_type = "15"
                # Проверяем день на выходные дни и праздничные дни
                start_time, end_time, type_of_day = check_day(
                    date,
                    datetime.datetime(1, 1, 1, 9, 30).time(),
                    datetime.datetime(1, 1, 1, 18, 0).time(),
                    int(record_type)
                )
                report_kwargs = {
                    "report_card_day": date,
                    "rec_no": instance.pk + instance.document.person.pk,
                    "employee": instance.document.person,
                    "start_time": start_time,
                    "end_time": end_time,
                    "record_type": record_type,
                    "reason_adjustment": str(instance.document),
                    "doc_ref_key": instance.pk,
                    "confirmed": True if instance.hr_accepted else False,
                }
                obj, created = ReportCard.objects.update_or_create(
                    report_card_day=date,
                    doc_ref_key=instance.pk,
                    employee=instance.document.person,
                    defaults=report_kwargs,
                )
                obj.place_report_card.set(
                    instance.document.place_production_activity.all()
                )
                obj.save()


@receiver(post_save, sender=ApprovalOficialMemoProcess)
def create_report(sender, instance: ApprovalOficialMemoProcess, raw=False, **kwargs):
    """Сигнал пост-сохранения процесса служебной записки.

    Обновляет текстовый статус согласования и асинхронно диспетчеризирует уведомления
    через MemoNotificationService без блокировки веб-потока исключительно при смене
    соответствующих статусов бизнес-процесса.

    Args:
        sender: Класс модели ApprovalOficialMemoProcess.
        instance (ApprovalOficialMemoProcess): Экземпляр сохраняемой записи.
        raw (bool): Признак загрузки фикстур (loaddata).
        **kwargs: Дополнительные аргументы сигнала (created, update_fields и др.).
    """
    if raw or not instance.pk:
        return

    change_approval_status(instance)

    from hrdepartment_app.services.memo_notification_service import MemoNotificationService

    init = getattr(instance, "_initial_state", {})
    created = kwargs.get("created", False)

    # Определение фактических переходов состояний (State Transitions)
    became_cancelled = instance.cancellation and (created or not init.get("cancellation"))
    became_completed = instance.accepted_accounting and (created or not init.get("accepted_accounting"))
    became_transferred_accounting = (
        bool(instance.date_transfer_accounting)
        and not instance.accepted_accounting
        and (created or instance.date_transfer_accounting != init.get("date_transfer_accounting"))
    )
    became_originals_received = (
        instance.originals_received
        and bool(instance.date_receipt_original)
        and not instance.date_transfer_accounting
        and (
            created
            or not init.get("originals_received")
            or instance.date_receipt_original != init.get("date_receipt_original")
        )
    )
    became_order_issued = instance.process_accepted and not instance.email_send
    became_location_set = (
        instance.location_selected
        and not instance.process_accepted
        and (created or not init.get("location_selected"))
    )
    became_approved = (
        instance.document_not_agreed
        and not instance.location_selected
        and (created or not init.get("document_not_agreed"))
    )
    became_submitted = (
        instance.submit_for_approval
        and not instance.document_not_agreed
        and (created or not init.get("submit_for_approval"))
    )

    if became_cancelled:
        MemoNotificationService.dispatch_event(instance.pk, "CANCELLED")
    elif became_completed:
        MemoNotificationService.dispatch_event(instance.pk, "COMPLETED")
    elif became_transferred_accounting:
        MemoNotificationService.dispatch_event(instance.pk, "TRANSFERRED_TO_ACCOUNTING")
    elif became_originals_received:
        MemoNotificationService.dispatch_event(instance.pk, "ORIGINALS_RECEIVED")
    elif became_order_issued:
        MemoNotificationService.dispatch_event(instance.pk, "ORDER_ISSUED")
    elif became_location_set:
        MemoNotificationService.dispatch_event(instance.pk, "LOCATION_SET")
    elif became_approved:
        MemoNotificationService.dispatch_event(instance.pk, "APPROVED")
    elif became_submitted:
        MemoNotificationService.dispatch_event(instance.pk, "SUBMITTED")

    # Обновляем снимок состояния после обработки
    instance._save_initial_state()



# Более не используется
class BusinessProcessDirection(models.Model):
    type_of = [("1", "Служебная поездка"), ("2", "Приказы о старших бригадах")]

    class Meta:
        verbose_name = "(Удалено) Направление бизнес процесса"
        verbose_name_plural = "(Удалено) Направления бизнес процессов"

    business_process_type = models.CharField(
        verbose_name="Тип бизнес процесса",
        max_length=5,
        default="",
        blank=True,
        choices=type_of,
    )
    person_executor = models.ManyToManyField(
        Job, verbose_name="Исполнитель", related_name="person_executor"
    )
    person_agreement = models.ManyToManyField(
        Job, verbose_name="Согласующее лицо", related_name="person_agreement"
    )
    clerk = models.ManyToManyField(
        Job, verbose_name="Делопроизводитель", related_name="clerk"
    )
    person_hr = models.ManyToManyField(
        Job, verbose_name="Сотрудник ОК", related_name="person_hr"
    )
    date_start = models.DateField(verbose_name="Дата начала", null=True, blank=True)
    date_end = models.DateField(verbose_name="Дата окончания", null=True, blank=True)

    @staticmethod
    def get_absolute_url():
        return reverse("hrdepartment_app:bptrip_list")


class BusinessProcessRoutes(models.Model):
    """
     Модель для определения маршрутов бизнес-процессов.

     Описывает тип бизнес-процесса и назначает ответственных сотрудников
     на различные роли (исполнитель, согласующий, делопроизводитель и т.д.),
     а также задаёт временной интервал действия процесса.

     Используется для автоматизации и контроля выполнения бизнес-процессов,
     таких как служебные поездки или оформление приказов.

     Атрибуты:
     ---------
     BUSINESS_PROCESS_TYPES : list of tuple
         Список допустимых типов бизнес-процессов. Используется в поле `business_process_type`.
         Допустимые значения:
         - ("1", "Служебная поездка")
         - ("2", "Приказы о старших бригадах")
         - ("3", "Доверенности")

     business_process_type : CharField
         Тип бизнес-процесса. Определяет категорию маршрута.
         - max_length=5
         - choices=BUSINESS_PROCESS_TYPES
         - blank=True
         - default=""
         Примеры: "1" — служебная поездка, "2" — приказ о бригаде, "3" - доверенности.

     person_executor : ManyToManyField
         Исполнители бизнес-процесса — сотрудники, отвечающие за выполнение основных действий.
         - related_name="bp_person_executor"
         - blank=True
         - Связь с моделью `DataBaseUser`

     person_agreement : ManyToManyField
         Согласующие лица — сотрудники, которым необходимо согласовать процесс.
         - related_name="bp_person_agreement"
         - blank=True
         - Связь с моделью `DataBaseUser`

     person_clerk : ManyToManyField
         Делопроизводители — ответственные за ведение документации и учёт.
         - related_name="bp_person_clerk"
         - blank=True
         - Связь с моделью `DataBaseUser`

     person_hr : ManyToManyField
         Сотрудники отдела кадров (ОК), отвечающие за кадровое сопровождение.
         - related_name="bp_person_hr"
         - blank=True
         - Связь с моделью `DataBaseUser`

     person_sd : ManyToManyField
         Сотрудники отдела научной организации (ОНО), участвующие в процессах,
         требующих научно-организационного сопровождения.
         - related_name="bp_person_sd"
         - blank=True
         - Связь с моделью `DataBaseUser`

     person_accounting : ManyToManyField
         Сотрудники бухгалтерии, участвующие в финансовых операциях.
         - related_name="bp_person_accounting"
         - blank=True
         - Связь с моделью `DataBaseUser`

     date_start : DateField
         Дата начала действия бизнес-процесса.
         - null=True
         - blank=True

     date_end : DateField
         Дата окончания действия бизнес-процесса.
         - null=True
         - blank=True

        """

    BUSINESS_PROCESS_TYPES = [
        ("1", "Служебная поездка"),
        ("2", "Приказы о старших бригадах"),
        ("3", "Доверенности"),
    ]
    """
    Список допустимых типов бизнес-процессов.

    Используется как значение для поля `business_process_type`.
    Каждый элемент — кортеж из идентификатора и описательного названия.
    """

    business_process_type = models.CharField(
        verbose_name="Тип бизнес процесса",
        max_length=5,
        choices=BUSINESS_PROCESS_TYPES,
        default="",
        blank=True,
    )

    person_executor = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Исполнитель",
        related_name="bp_person_executor",
        blank=True,
    )

    person_agreement = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Согласующее лицо",
        related_name="bp_person_agreement",
        blank=True,
    )

    person_clerk = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Делопроизводитель/Инициатор",
        related_name="bp_person_clerk",
        blank=True,
    )

    person_hr = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Сотрудник ОК",
        related_name="bp_person_hr",
        blank=True,
    )

    person_sd = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Сотрудник ОНО",
        related_name="bp_person_sd",
        blank=True,
    )

    person_accounting = models.ManyToManyField(
        DataBaseUser,
        verbose_name="Сотрудник бухгалтерии",
        related_name="bp_person_accounting",
        blank=True,
    )

    date_start = models.DateField(
        verbose_name="Дата начала",
        null=True,
        blank=True,
    )

    date_end = models.DateField(
        verbose_name="Дата окончания",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Направление бизнес процесса"
        verbose_name_plural = "Направления бизнес процессов"
        ordering = ["-date_start"]

    def __str__(self):
        return f"{self.get_business_process_type_display()} ({self.date_start} - {self.date_end})"

    def get_absolute_url(self):
        return reverse("hrdepartment_app:business_process_routes_list")

    def save(self, *args, **kwargs):
        # Очищаем кэш перед или после сохранения
        cache.delete("global_bp_routes")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Очищаем кэш при удалении маршрута
        cache.delete("global_bp_routes")
        super().delete(*args, **kwargs)


class OrderDescription(models.Model):
    """
    Модель, представляющая описание приказа.

    Атрибуты:
        name (str): Название приказа
        affiliation (Affiliation): Принадлежность приказа к службе

    """

    class Meta:
        verbose_name = "Наименование приказа"
        verbose_name_plural = "Наименования приказов"

    name = models.CharField(
        verbose_name="",
        max_length=250,
        blank=True,
    )
    affiliation = models.ForeignKey(
        Affiliation,
        verbose_name="Принадлежность",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.name


class DocumentsOrder(Documents):
    type_of_order = [("1", "Общая деятельность"), ("2", "Личный состав")]

    class Meta:
        verbose_name = "Приказ"
        verbose_name_plural = "Приказы"
        ordering = ["-document_date"]

    document_name = models.ForeignKey(
        OrderDescription,
        verbose_name="Наименование документа",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
    )
    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=ord_directory_path, blank=True
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=ord_directory_path, blank=True
    )
    document_order_type = models.CharField(
        verbose_name="Тип приказа", max_length=18, choices=type_of_order
    )
    document_foundation = models.ForeignKey(
        OfficialMemo,
        verbose_name="Документ основание",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doc_foundation",
    )
    description = CKEditor5Field("Содержание", config_name="extends", blank=True)
    approved = models.BooleanField(verbose_name="Утверждён", default=False)
    cancellation = models.BooleanField(verbose_name="Отмена", default=False)
    custom_file = models.BooleanField(verbose_name="Ручная загрузка приказа", default=False)
    reason_cancellation = models.ForeignKey(
        ReasonForCancellation,
        verbose_name="Причина отмены",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    def get_data(self):
        status = ""
        dt = datetime.datetime.today()

        if (
                self.validity_period_end
                and datetime.date(dt.year, dt.month, dt.day) > self.validity_period_end
        ):
            status = "Действие завершил"
        else:
            status = "Действует"

        if self.cancellation:
            status = "Отменён"
        return {
            "pk": self.pk,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",  # .strftime(""),
            "document_name": self.document_name.name,
            "person": format_name_initials(self.document_foundation.person.get_title())
            if self.document_foundation
            else "",
            "approved": status,
            "cancellation": self.cancellation,
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:order_list")

    def __str__(self):
        return f'Пр. № {self.document_number} от {self.document_date.strftime("%d.%m.%Y")} г.'


def order_doc(obj_model: DocumentsOrder, filepath: str, filename: str, request):
    sub_doc_file = ""
    if obj_model.document_foundation:
        if obj_model.document_foundation.type_trip == "1":
            if (
                    "Командир воздушного судна"
                    in obj_model.document_foundation.person.user_work_profile.job.get_title()
            ):
                doc = DocxTemplate(
                    pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/aom2.docx")
                )
            else:
                doc = DocxTemplate(
                    pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/aom.docx")
                )
        else:
            doc = DocxTemplate(
                pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/aom3.docx")
            )

        delta = (
                obj_model.document_foundation.period_for
                - obj_model.document_foundation.period_from
        )
        place = [
            item.name
            for item in obj_model.document_foundation.place_production_activity.all()
        ]
        context = {
            "Number": obj_model.document_number,
            "DateDoc": f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
            "FIO": obj_model.document_foundation.person,
            "ServiceNum": obj_model.document_foundation.person.service_number,
            "Division": obj_model.document_foundation.person.user_work_profile.divisions,
            "Job": obj_model.document_foundation.person.user_work_profile.job,
            "Place": ", ".join(place),
            "DateCount": str(int(delta.days) + 1),
            "DateFrom": f'{obj_model.document_foundation.period_from.strftime("%d.%m.%Y")} г.',
            "DateFor": f'{obj_model.document_foundation.period_for.strftime("%d.%m.%Y")} г.',
            "Purpose": obj_model.document_foundation.purpose_trip,
            "DateAcquaintance": f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
        }

    else:
        doc = DocxTemplate(
            pathlib.Path.joinpath(BASE_DIR, "static/DocxTemplates/ord.docx")
        )
        sub_doc_file = pathlib.Path.joinpath(
            pathlib.Path.joinpath(BASE_DIR, filepath), f"subdoc-{filename}"
        )
        desc_document = Document()
        new_parser = HtmlToDocx()
        new_parser.add_html_to_document(obj_model.description, desc_document)
        desc_result_path = sub_doc_file
        desc_document.save(desc_result_path)
        sub_doc = doc.new_subdoc(desc_result_path)
        context = {
            "Number": obj_model.document_number,
            "DateDoc": f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
            # "Title": obj_model.document_name,
            "Description": sub_doc,
            # "Description": sub_doc,
        }

    try:
        doc.render(context, autoescape=True)
    except Exception as _ex:
        # DataBaseUser.objects.get(pk=request)
        logger.debug(f"Ошибка заполнения файла {filename}: {_ex}")
        context = {}

    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename))
    if os.path.isfile(sub_doc_file):
        os.remove(sub_doc_file)

    from msoffice2pdf import convert

    try:
        var = convert(
            source=str(pathlib.Path.joinpath(path_obj, filename)),
            output_dir=str(path_obj),
            soft=0,
        )
        logger.debug(
            f"Файл: {str(pathlib.Path.joinpath(path_obj, filename))}, Путь: {str(path_obj)}"
        )
        return var
    except Exception as _ex:
        logger.error(f"Ошибка сохранения файла в pdf {filename}: {_ex}")


@receiver(post_save, sender=DocumentsOrder)
def rename_order_file_name(sender, instance: DocumentsOrder, **kwargs):
    # Добавь эту строку в самое начало функции:
    if kwargs.get('raw'):
        return  # Пропускаем выполнение при загрузке фикстур
    if not instance.cancellation and not instance.custom_file:
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули

        # ext_scan = str(instance.scan_file).split('.')[-1]
        uid = f"{instance.pk:07}"
        filename = (
            f"ORD-{instance.document_order_type}-{instance.document_date}-{uid}.docx"
        )
        scanname = (
            f"ORD-{instance.document_order_type}-{instance.document_date}-{uid}.pdf"
        )
        date_doc = instance.document_date
        created_pdf = order_doc(
            instance,
            f"media/docs/ORD/{date_doc.year}/{date_doc.month}",
            filename,
            instance.document_order_type,
        )
        scan_name = pathlib.Path(created_pdf).name
        if f"docs/ORD/{date_doc.year}/{date_doc.month}/{filename}" != instance.doc_file:
            DocumentsOrder.objects.filter(pk=instance.pk).update(
                doc_file=f"docs/ORD/{date_doc.year}/{date_doc.month}/{filename}"
            )
        # if scanname != scan_name:
        try:
            pathlib.Path.rename(
                pathlib.Path.joinpath(
                    BASE_DIR,
                    "media",
                    f"docs/ORD/{date_doc.year}/{date_doc.month}",
                    scan_name,
                ),
                pathlib.Path.joinpath(
                    BASE_DIR,
                    "media",
                    f"docs/ORD/{date_doc.year}/{date_doc.month}",
                    scanname,
                ),
            )
        except Exception as _ex0:
            logger.error(f"Ошибка переименования файла: {_ex0}")
        DocumentsOrder.objects.filter(pk=instance.pk).update(
            scan_file=f"docs/ORD/{date_doc.year}/{date_doc.month}/{scanname}"
        )


class CreatingTeam(models.Model):
    class Meta:
        verbose_name = "Создание бригады"
        verbose_name_plural = "Создание бригад"
        ordering = ["-id"]

    doc_type = [
        ("0", "Новый документ"),
        ("1", "Замещающий документ"),
    ]
    document_type = models.CharField(verbose_name='Тип документа', max_length=1, choices=doc_type, default="0")
    replaceable_document = models.ForeignKey('self', verbose_name='Отменяемый документ', null=True, blank=True,
                                             on_delete=models.SET_NULL, )
    senior_brigade = models.ForeignKey(DataBaseUser, verbose_name="Старший бригады", on_delete=models.SET_NULL,
                                       null=True, related_name='senior_brigade')
    team_brigade = models.ManyToManyField(DataBaseUser, verbose_name="Состав бригады", related_name='team_brigade',
                                          blank=True)
    executor_person = models.ForeignKey(DataBaseUser, verbose_name="Исполнитель", on_delete=models.SET_NULL,
                                        null=True, related_name='executor_person')
    approving_person = models.ForeignKey(DataBaseUser, verbose_name="Согласующее лицо", on_delete=models.SET_NULL,
                                         null=True, related_name='approving_person')
    date_start = models.DateField(verbose_name="Дата начала", null=True, blank=True,
                                  default=datetime.date.today)  # Дата начала бригады.
    date_end = models.DateField(verbose_name="Дата окончания", null=True, blank=True,
                                default=datetime.date.today)  # Дата окончания бригады.
    date_create = models.DateField(verbose_name="Дата приказа", null=True, blank=True,
                                   default=datetime.date.today)  # Дата создания бригады.
    number = models.CharField(verbose_name="Номер приказа", max_length=255, blank=True, default='')
    place = models.ForeignKey(PlaceProductionActivity, verbose_name="МПД", on_delete=models.SET_NULL, null=True,
                              related_name='place')
    company_property = models.ManyToManyField(Estate, verbose_name="Задание на полет", related_name='company_property')
    agreed = models.BooleanField(verbose_name="Согласовано", default=False)
    doc_file = models.FileField(verbose_name="Файл документа", upload_to=team_directory_path, blank=True)
    scan_file = models.FileField(verbose_name="Скан документа", upload_to=team_directory_path, blank=True)
    cancellation = models.BooleanField(verbose_name="Отмена", default=False)
    email_send = models.BooleanField(verbose_name="Письмо отправлено", default=False)
    email_cancellation_send = models.BooleanField(verbose_name="Письмо от отмене отправлено", default=False)
    history_change = GenericRelation(HistoryChange)
    updated_at = models.DateTimeField(auto_now=True)

    def change_status(self, item: int, status: bool):
        match item:
            case 0:
                self.email_send = status
            case 1:
                self.email_cancellation_send = status

    def __str__(self):
        return f"{format_name_initials(self.senior_brigade)} - с: {self.date_start.strftime('%d.%m.%Y')} по: {self.date_end.strftime('%d.%m.%Y')}"

    def get_absolute_url(self):
        return reverse("hrdepartment_app:team_list")

    def get_data(self):
        status = ""
        dt = datetime.datetime.today()

        if (
                self.date_end
                and datetime.date(dt.year, dt.month, dt.day) > self.date_end
        ):
            status = "Действие завершил"
        else:
            status = "Действует"

        if self.cancellation:
            status = "Отменён"

        return {
            "pk": self.pk,
            "document_name": format_name_initials(self.senior_brigade),  # self.senior_brigade,
            "date_start": self.date_start.strftime("%d.%m.%Y"),
            "date_end": self.date_end.strftime("%d.%m.%Y"),
            "document_number": self.number,
            "document_date": f"{self.date_create:%d.%m.%Y} г.",  # .strftime(""),
            "document_division": self.place.name,
            "agreed": "Согласовано" if self.agreed else "Не согласовано",  # Согласовано, Не согласовано
            "actuality": status,
            "executor": format_name_initials(self.executor_person),
            "email_send": "Да" if self.email_send else "Нет",
        }


def ias_order(obj_model: CreatingTeam, filepath: str, filename: str, request, single=True, cancel=False):
    ordteam = "static/DocxTemplates/ord-ias-single.docx" if single else "static/DocxTemplates/ord-ias.docx"
    if cancel:
        ordteam = "static/DocxTemplates/ord-ias-single-cancel.docx" if single else "static/DocxTemplates/ord-ias-cancel.docx"
    doc = DocxTemplate(
        pathlib.Path.joinpath(BASE_DIR, ordteam)
    )
    sub_doc_file = pathlib.Path.joinpath(
        pathlib.Path.joinpath(BASE_DIR, filepath), f"subdoc-{filename}"
    )
    desc_document = Document()
    # new_parser = HtmlToDocx()
    # new_parser.add_html_to_document(obj_model.description, desc_document)
    desc_result_path = sub_doc_file
    desc_document.save(desc_result_path)
    sub_doc = doc.new_subdoc(desc_result_path)
    team_brigade_list = f"- {format_name_initials(obj_model.senior_brigade)} - {obj_model.senior_brigade.user_work_profile.job}\a"
    for item in obj_model.team_brigade.all():
        team_brigade_list += f"- {format_name_initials(item)} - {item.user_work_profile.job}\a"
    company_property = ''
    for item in obj_model.company_property.all():
        company_property += f" {item.type_property} {item},"
    context = {
        "DocNumber": '____' if obj_model.number == '' else obj_model.number,
        "DateDoc": f'{obj_model.date_create.strftime("%d.%m.%Y")} г.',
        "DateDocOrder": f'{obj_model.date_start.strftime("%d.%m.%Y")} г.',
        "DateStart": obj_model.date_start.strftime("%d.%m.%Y"),
        "DateEnd": obj_model.date_end.strftime("%d.%m.%Y"),
        "Place": obj_model.place,
        "CompanyProperty": company_property,
        "team_brigade": obj_model.senior_brigade,
        "team_brigade_job": obj_model.senior_brigade.user_work_profile.job,
        "ShortName": obj_model.place,
        "team_brigade_list": Listing(f"{team_brigade_list[:-1]}"),
        "additional_payment": str(obj_model.place.additional_payment),
        "number_order": obj_model.replaceable_document.number if obj_model.replaceable_document else '',
        "date_order": f'{obj_model.replaceable_document.date_create.strftime("%d.%m.%Y")} г.' if obj_model.replaceable_document else '',
    }
    doc.render(context, autoescape=True)
    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename))
    if os.path.isfile(sub_doc_file):
        os.remove(sub_doc_file)
    # from msoffice2pdf import convert
    #
    # try:
    #     var = convert(
    #         source=str(pathlib.Path.joinpath(path_obj, filename)),
    #         output_dir=str(path_obj),
    #         soft=0,
    #     )
    #     logger.debug(
    #         f"Файл: {str(pathlib.Path.joinpath(path_obj, filename))}, Путь: {str(path_obj)}"
    #     )
    #     return var
    # except Exception as _ex:
    #     logger.error(f"Ошибка сохранения файла в pdf {filename}: {_ex}")


@receiver(post_save, sender=CreatingTeam)
def rename_ias_order_file_name(sender, instance: CreatingTeam, **kwargs):
    if instance.agreed:
        tn = TelegramNotification.objects.filter(document_id=instance.pk)
        if tn:
            tn.delete()
    if instance.agreed and instance.number != '':
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        # ext_scan = str(instance.scan_file).split('.')[-1]
        uid = f"{instance.pk:07}"
        filename = (f"ORD-3-{instance.date_create}-{uid}.docx")
        scanname = (f"ORD-3-{instance.date_create}-{uid}.pdf")
        date_doc = instance.date_create
        single = True if instance.team_brigade.count() < 1 else False
        cancel = True if instance.replaceable_document else False
        created_pdf = ias_order(instance, f"media/docs/ORD/{date_doc.year}/{date_doc.month}", filename, '3', single,
                                cancel)
        # scan_name = pathlib.Path(created_pdf).name
        if f"docs/ORD/{date_doc.year}/{date_doc.month}/{filename}" != instance.doc_file:
            CreatingTeam.objects.filter(pk=instance.pk).update(
                doc_file=f"docs/ORD/{date_doc.year}/{date_doc.month}/{filename}"
            )
        if instance.scan_file:
            if f"docs/ORD/{date_doc.year}/{date_doc.month}/{scanname}" != instance.scan_file.name:
                try:
                    pathlib.Path.rename(
                        pathlib.Path.joinpath(
                            BASE_DIR,
                            "media",
                            instance.scan_file.name,
                        ),
                        pathlib.Path.joinpath(
                            BASE_DIR,
                            "media",
                            f"docs/ORD/{date_doc.year}/{date_doc.month}",
                            scanname,
                        ),
                    )
                except Exception as _ex0:
                    logger.error(f"Ошибка переименования файла: {_ex0}")
                CreatingTeam.objects.filter(pk=instance.pk).update(
                    scan_file=f"docs/ORD/{date_doc.year}/{date_doc.month}/{scanname}"
                )
            print(instance.scan_file.name)
        #
        # if not instance.email_send:

    else:
        # business_process = BusinessProcessDirection.objects.filter(
        #     person_executor=instance.executor_person.user_work_profile.job
        # )
        person_agreement_job_list = [item for item in BusinessProcessRoutes.objects.filter(
            person_executor=instance.executor_person).values_list('pk', flat=True)]
        person_agreement_list = []
        # for item in business_process:
        #     for job in item.person_agreement.all():
        #         person_agreement_job_list.append(job)
        for item in DataBaseUser.objects.filter(pk__in=set(person_agreement_job_list)):
            if item.telegram_id:
                person_agreement_list.append(
                    ChatID.objects.filter(chat_id=item.telegram_id).first()
                )
        kwargs_obj = {
            "message": f"Необходимо согласовать документ: {instance}",
            "document_url": f"https://corp.barkol.ru/hr/team/{instance.pk}/agreed/",
            "document_id": f"{instance.pk}",
            "sending_counter": 3,
            "send_time": datetime.datetime.now() + relativedelta(minutes=1),
            "send_date": datetime.datetime.today(),
        }
        tn, created = TelegramNotification.objects.update_or_create(
            document_id=instance.pk, defaults=kwargs_obj
        )
        tn.respondents.set(person_agreement_list)


class DocumentsJobDescription(Documents):
    class Meta:
        verbose_name = "Должностная инструкция"
        verbose_name_plural = "Должностные инструкции"
        ordering = ("-document_date",)

    prefix_attr_doc_file = "JDS"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "JDS"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=jds_directory_path, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['doc', 'docx']),
        ]
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=jds_directory_path, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    document_division = models.ForeignKey(
        Division, verbose_name="Подразделение", on_delete=models.SET_NULL, null=True
    )
    document_job = models.ForeignKey(
        Job, verbose_name="Должность", on_delete=models.SET_NULL, null=True
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )

    def get_data(self):
        get_actual = 0 if not DocumentsJobDescription.objects.filter(
            parent_document=self.pk).exists() and self.actuality else 1

        return {
            "pk": self.pk,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г." if self.document_date else "",
            "document_job": str(self.document_job),
            "document_division": str(self.document_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if get_actual == 0 else "Нет",
            "executor": str(self.executor),
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:jobdescription_list")

    def __str__(self):
        return f'ДИ {self.document_name} №{self.document_number} от {self.document_date.strftime("%d.%m.%Y")}'


class TimeSheet(models.Model):
    """
    Табель учета рабочего времени
    """
    date = models.DateField(verbose_name="Дата табеля", null=True, blank=True)
    employee = models.ForeignKey(
        DataBaseUser, verbose_name="Ответственный", on_delete=models.SET_NULL, null=True, blank=True
    )
    time_sheets_place = models.ForeignKey(
        PlaceProductionActivity, verbose_name="МПД", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="time_sheets_place")
    notes = models.TextField(verbose_name="Примечания", blank=True)
    is_draft = models.BooleanField(verbose_name="Черновик", default=True)

    class Meta:
        verbose_name = "Табель учета рабочего времени"
        verbose_name_plural = "Табели учета рабочего времени"
        ordering = ("-date",)

    def __str__(self):
        status_str = " (Черновик)" if self.is_draft else ""
        return f"Табель от {self.date} для {self.employee}{status_str}"

    def get_absolute_url(self):
        return reverse('hrdepartment_app:timesheet', kwargs={'pk': self.pk})

    def get_data(self):
        """Получает данные из экземпляра TimeSheet для табличного вывода.

        Returns:
            dict: Словарь с параметрами табеля (pk, date, employee, time_sheets_place, notes, is_draft, status).
        """
        emp_name = "—"
        if self.employee:
            title = getattr(self.employee, "title", "") or getattr(self.employee, "username", "")
            emp_name = format_name_initials(title) if title else str(self.employee)

        place_name = self.time_sheets_place.name if self.time_sheets_place else "—"

        return {
            "pk": self.pk,
            "date": f"{self.date:%d.%m.%Y} г." if self.date else "—",
            "employee": emp_name,
            "time_sheets_place": place_name,
            "notes": self.notes or "",
            "is_draft": self.is_draft,
            "status": "Черновик" if self.is_draft else "Утвержден",
        }

    def get_report_card_reason(self) -> str:
        """Формирует структурированную запись причины корректировки для строк ReportCard.

        Returns:
            str: Текст с реквизитами табеля (номер, дата смены, старший бригады, МПД, статус).
        """
        date_str = f"{self.date:%d.%m.%Y} г." if self.date else "—"
        emp_name = "Не указан"
        if self.employee:
            title = getattr(self.employee, "title", "") or getattr(self.employee, "username", "")
            emp_name = format_name_initials(title) if title else str(self.employee)
        place_name = str(self.time_sheets_place) if self.time_sheets_place else "Не указано"
        status_name = "Черновик" if self.is_draft else "Утвержден"
        ts_id = f" №{self.pk}" if self.pk else ""

        return (
            f"Табель учета рабочего времени на МПД{ts_id}\n"
            f"Дата табеля: {date_str}\n"
            f"Старший бригады: {emp_name}\n"
            f"Место деятельности (МПД): {place_name}\n"
            f"Статус: {status_name}"
        )


class OperationalWork(models.Model):
    """Справочник видов оперативных регламентных работ воздушных судов.

    Модель хранит перечень оперативных регламентных работ, выполняемых
    при оперативном техническом обслуживании воздушных судов (ОТО).

    Attributes:
        name (str): Полное наименование оперативной работы.
        code (str): Код или обозначение оперативной формы (например, 'А1', 'А2').
        description (str): Подробное описание регламентных процедур.
        air_bord_type (TypeProperty): Привязка к типу воздушного судна.
    """

    class Meta:
        verbose_name = "Оперативная работа"
        verbose_name_plural = "Оперативные работы"
        ordering = ("air_bord_type", "name")

    name = models.TextField(verbose_name="Наименование", blank=True)
    code = models.TextField(verbose_name="Код", blank=True)
    description = models.TextField(verbose_name="Описание", blank=True)
    air_bord_type = models.ForeignKey(
        TypeProperty,
        verbose_name="Тип ВС",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_works",
    )

    @property
    def type_property(self):
        """Возвращает связанный тип ВС (TypeProperty) для совместимости по именованию."""
        return self.air_bord_type

    @type_property.setter
    def type_property(self, value):
        self.air_bord_type = value

    def save(self, *args, **kwargs):
        """Сохраняет запись с автозаполнением наименования при необходимости."""
        if not self.name and self.code:
            self.name = self.code
        super().save(*args, **kwargs)

    def __str__(self):
        if self.air_bord_type:
            return f"{self.air_bord_type} - {self.code}"
        return self.code or f"Оперативная работа #{self.pk}"

    def get_absolute_url(self):
        """Возвращает канонический URL реестра оперативных работ."""
        return reverse("hrdepartment_app:operational_work_list")

    def get_data(self) -> dict:
        """Формирует сериализованные данные для таблицы DataTables.

        Returns:
            dict: Словарь с атрибутами для отображения в реестре.
        """
        return {
            "pk": self.pk,
            "air_bord_type": str(self.air_bord_type) if self.air_bord_type else "—",
            "code": self.code or "—",
            "name": self.name or "—",
            "description": self.description or "—",
        }


class PeriodicWorkColor(models.TextChoices):
    """Варианты цветовой индикации регламентных периодических работ."""
    YELLOW = "yellow", "желтый"
    GREEN = "green", "зеленый"
    RED = "red", "красный"


class PeriodicWork(models.Model):
    """Справочник видов периодических регламентных работ воздушных судов.

    Модель хранит перечень регламентных работ, выполняемых с определенной
    периодичностью (по наработке норма-часов), допустимые отклонения (лаги)
    и цветовую маркировку для визуализации в графиках и картах-нарядах.

    Attributes:
        name (str): Полное наименование регламентной работы.
        code (str): Код или обозначение регламента (например, 'Ф-1', '100 часов').
        ratio (float): Норма-часы наработки для выполнения работы.
        lag_minus (int): Число часов отклонения (минус).
        lag_plus (int): Число часов отклонения (плюс).
        color (str): Цветовая маркировка (желтый, зеленый, красный).
        description (str): Описание регламентных процедур.
        air_bord_type (TypeProperty): Привязка к типу воздушного судна (contracts_app.TypeProperty).
    """

    class Meta:
        verbose_name = "Периодическая работа"
        verbose_name_plural = "Периодические работы"
        ordering = ("air_bord_type", "ratio", "name")

    name = models.TextField(verbose_name="Наименование", blank=True)
    code = models.TextField(verbose_name="Код", blank=True)
    ratio = models.FloatField(verbose_name="Норма-часы", default=0.0, blank=True)
    lag_minus = models.PositiveIntegerField(
        verbose_name="Лаг минус",
        default=0,
        blank=True,
        help_text="Число часов отклонения (минус)",
    )
    lag_plus = models.PositiveIntegerField(
        verbose_name="Лаг плюс",
        default=0,
        blank=True,
        help_text="Число часов отклонения (плюс)",
    )
    color = models.CharField(
        verbose_name="Цвет",
        max_length=20,
        choices=PeriodicWorkColor.choices,
        default=PeriodicWorkColor.GREEN,
        blank=True,
        help_text="Цветовая индикация периодической работы (желтый, зеленый, красный)",
    )
    description = models.TextField(verbose_name="Описание", blank=True)
    air_bord_type = models.ForeignKey(
        TypeProperty,
        verbose_name="Тип ВС",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodic_works",
    )

    @property
    def type_property(self):
        """Возвращает связанный тип ВС (TypeProperty) для совместимости по именованию."""
        return self.air_bord_type

    @type_property.setter
    def type_property(self, value):
        self.air_bord_type = value

    def clean(self):
        """Нормализует значение цвета при валидации."""
        super().clean()
        if self.color:
            val = str(self.color).strip().lower()
            mapping = {
                "желтый": PeriodicWorkColor.YELLOW.value,
                "жёлтый": PeriodicWorkColor.YELLOW.value,
                "yellow": PeriodicWorkColor.YELLOW.value,
                "зеленый": PeriodicWorkColor.GREEN.value,
                "зелёный": PeriodicWorkColor.GREEN.value,
                "green": PeriodicWorkColor.GREEN.value,
                "красный": PeriodicWorkColor.RED.value,
                "red": PeriodicWorkColor.RED.value,
            }
            if val in mapping:
                self.color = mapping[val]

    def save(self, *args, **kwargs):
        """Сохраняет запись с предварительной нормализацией значений."""
        if self.color:
            val = str(self.color).strip().lower()
            mapping = {
                "желтый": PeriodicWorkColor.YELLOW.value,
                "жёлтый": PeriodicWorkColor.YELLOW.value,
                "yellow": PeriodicWorkColor.YELLOW.value,
                "зеленый": PeriodicWorkColor.GREEN.value,
                "зелёный": PeriodicWorkColor.GREEN.value,
                "green": PeriodicWorkColor.GREEN.value,
                "красный": PeriodicWorkColor.RED.value,
                "red": PeriodicWorkColor.RED.value,
            }
            if val in mapping:
                self.color = mapping[val]
        if not self.name and self.code:
            self.name = self.code
        super().save(*args, **kwargs)

    def __str__(self):
        if self.air_bord_type:
            return f"{self.air_bord_type} - {self.code}"
        return self.code or f"Работа #{self.pk}"

    def get_absolute_url(self):
        """Возвращает канонический URL реестра периодических работ."""
        return reverse("hrdepartment_app:periodic_work_list")

    def get_data(self) -> dict:
        """Формирует сериализованные данные для таблицы DataTables.

        Returns:
            dict: Словарь с атрибутами и HTML-бейджами для реестра.
        """
        color_badges = {
            PeriodicWorkColor.YELLOW.value: '<span class="badge bg-warning text-dark font-weight-semibold">желтый</span>',
            PeriodicWorkColor.GREEN.value: '<span class="badge bg-success text-white font-weight-semibold">зеленый</span>',
            PeriodicWorkColor.RED.value: '<span class="badge bg-danger text-white font-weight-semibold">красный</span>',
        }
        badge = color_badges.get(
            self.color,
            f'<span class="badge bg-secondary">{self.get_color_display() or self.color}</span>',
        )
        return {
            "pk": self.pk,
            "air_bord_type": str(self.air_bord_type) if self.air_bord_type else "—",
            "code": self.code or "—",
            "name": self.name or "—",
            "ratio": self.ratio,
            "lag_minus": self.lag_minus,
            "lag_plus": self.lag_plus,
            "color": badge,
            "description": self.description or "—",
        }


class OutfitCard(models.Model):
    """Карта-наряд на выполнение технического обслуживания воздушного судна.

    Модель производственно-технической документации по выполнению оперативного
    и периодического технического обслуживания ВС в соответствии с требованиями
    Федеральных авиационных правил (Приказ Минтранса РФ от 18.10.2024 N 367).

    Attributes:
        outfit_card_date (date): Дата открытия карты-наряда.
        start_time (time): Время начала выполнения ТО (UTC).
        outfit_card_number (str): Номер наряда-задания.
        employee (DataBaseUser): Ответственный за выполнение / старший бригады.
        outfit_card_place (PlaceProductionActivity): Место производственной деятельности (МПД).
        air_board (Estate): Обслуживаемое воздушное судно.
        operational_work (ManyToManyField): Выполняемые оперативные работы.
        periodic_work (ManyToManyField): Выполняемые периодические регламентные работы.
        other_work (str): Дополнительные или разовые работы.
        outfit_card_date_end (date): Дата окончания и приемки работ.
        end_time (time): Время окончания выполнения ТО (UTC).
        scan_document (FileField): Электронный скан оформленного наряда.
        notes (str): Особые отметки и примечания.
        flight_hours (Decimal): Наработка планера СНЭ на момент ТО в часах.
        flight_hours_tsor (Decimal): Наработка планера ППР на момент ТО в часах.
        flight_cycles (int): Количество посадок / циклов с начала эксплуатации.
        deferred_defects (str): Перечень перенесенных дефектов по MEL/CDL/РЭ.
        deferred_defects_agreed (bool): Отметка о согласовании переноса с эксплуатантом.
        certifying_staff (DataBaseUser): Специалист подтверждающего персонала, выпустивший ВС.
        crs_number (str): Порядковый номер Свидетельства о выполненном ТО (CRS).
        is_signed (bool): Флаг закрытия наряда и выпуска Свидетельства о ТО.
        signed_at (datetime): Дата и время подписания.
        signature_hash (str): Контрольная сумма SHA-256 неизменяемости по п. 40 ФАП-367.
    """

    class Meta:
        verbose_name = "Карта-наряд"
        verbose_name_plural = "Карты-наряды"
        ordering = ("-outfit_card_date",)

    outfit_card_date = models.DateField(verbose_name="Дата", null=True, blank=True)
    start_time = models.TimeField(
        verbose_name="Время начала (UTC)",
        null=True,
        blank=True,
        help_text="Время начала ТО в формате ЧЧ:ММ (UTC)",
    )
    outfit_card_number = models.CharField(verbose_name="Номер", max_length=20, default="", blank=True)
    employee = models.ForeignKey(
        DataBaseUser,
        verbose_name="Ответственный",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    outfit_card_place = models.ForeignKey(
        PlaceProductionActivity,
        verbose_name="МПД",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outfit_card_place",
    )
    air_board = models.ForeignKey(
        Estate,
        verbose_name="Воздушный борт",
        related_name="company_air_board",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    operational_work = models.ManyToManyField(
        OperationalWork,
        verbose_name="Оперативные работы",
        related_name="outfit_card_operational",
        blank=True,
    )
    periodic_work = models.ManyToManyField(
        PeriodicWork,
        verbose_name="Периодические работы",
        related_name="outfit_card_periodic",
        blank=True,
    )
    other_work = models.CharField(verbose_name="Другие работы", max_length=200, default="", blank=True)
    outfit_card_date_end = models.DateField(verbose_name="Дата окончания", null=True, blank=True)
    end_time = models.TimeField(
        verbose_name="Время окончания (UTC)",
        null=True,
        blank=True,
        help_text="Время окончания ТО в формате ЧЧ:ММ (UTC)",
    )
    scan_document = models.FileField(
        verbose_name="Скан документа",
        upload_to=outfit_directory_path,
        null=True,
        blank=True,
    )
    notes = models.TextField(verbose_name="Примечания", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Поля наработки планера ВС на дату ТО (ФАП-367, ручной ввод) ---
    flight_hours = models.DecimalField(
        verbose_name="Наработка СНЭ (ч)",
        max_digits=9,
        decimal_places=1,
        default=0.0,
        blank=True,
        null=True,
        help_text="Наработка планера с начала эксплуатации в часах",
    )
    flight_hours_tsor = models.DecimalField(
        verbose_name="Наработка ППР (ч)",
        max_digits=9,
        decimal_places=1,
        default=0.0,
        blank=True,
        null=True,
        help_text="Наработка планера после последнего ремонта в часах",
    )
    flight_cycles = models.PositiveIntegerField(
        verbose_name="Посадки / циклы",
        default=0,
        blank=True,
        null=True,
        help_text="Количество посадок/циклов с начала эксплуатации",
    )

    # --- Отложенные дефекты по MEL/CDL/РЭ (п. 87 ФАП-367) ---
    deferred_defects = models.TextField(
        verbose_name="Перенесенные дефекты",
        blank=True,
        default="",
        help_text="Перечень дефектов, перенесенных по процедурам MEL/CDL/РЭ",
    )
    deferred_defects_agreed = models.BooleanField(
        verbose_name="Перенос согласован с эксплуатантом",
        default=False,
        help_text="Отметка о согласовании переноса срока устранения дефектов с эксплуатантом ВС",
    )
    test_flight_required = models.BooleanField(
        verbose_name="Контрольный облет требуется",
        default=False,
        help_text="Отметка о необходимости выполнения контрольного облета после ТО (п. 17 CRS / ФАП-145)",
    )

    # --- Подтверждающий персонал и выпуск ВС в полет (CRS) (пп. 84-85 ФАП-367) ---
    certifying_staff = models.ForeignKey(
        DataBaseUser,
        verbose_name="Подтверждающий персонал",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certified_outfit_cards",
        help_text="Специалист подтверждающего персонала, выпустивший ВС",
    )
    crs_number = models.CharField(
        verbose_name="Номер свидетельства о ТО (CRS)",
        max_length=50,
        blank=True,
        default="",
        help_text="Порядковый номер Свидетельства о выполненном ТО ВС",
    )
    is_signed = models.BooleanField(
        verbose_name="Наряд закрыт и подписан",
        default=False,
        db_index=True,
        help_text="Флаг закрытия наряда и выпуска Свидетельства о ТО",
    )
    signed_at = models.DateTimeField(
        verbose_name="Дата и время подписания",
        null=True,
        blank=True,
    )
    signature_hash = models.CharField(
        verbose_name="Хэш неизменяемости (SHA-256)",
        max_length=64,
        blank=True,
        default="",
        help_text="Контрольная сумма SHA-256 для гарантии неизменяемости по п. 40 ФАП-367",
    )
    used_equipment = models.ManyToManyField(
        "MaintenanceEquipment",
        through="OutfitCardEquipmentUsage",
        related_name="outfit_cards",
        blank=True,
        verbose_name="Использованное оборудование и инструмент",
        help_text="Оборудование, КПА и специнструмент, использованные при выполнении ТО (ФАП-145, пп. 19-25)",
    )

    def clean(self) -> None:
        """Выполняет нормативную проверку карты-наряда перед сохранением и закрытием.

        Raises:
            ValidationError: Если при закрытии наряда выявлены неисправные или просроченные приборы/оборудование.
        """
        super().clean()
        if self.is_signed and self.pk:
            target_date = self.outfit_card_date_end or self.outfit_card_date or timezone.now().date()
            invalid_equipments = []
            for usage in self.used_equipment_records.select_related("equipment").all():
                is_allowed, reason = usage.equipment.can_be_used_for_maintenance(target_date)
                if not is_allowed:
                    invalid_equipments.append(
                        f"{usage.equipment.name} (S/N: {usage.equipment.serial_number or 'б/н'}): {reason}"
                    )
            if invalid_equipments:
                raise ValidationError({
                    "is_signed": (
                        "Невозможно закрыть наряд и выпустить CRS: использовано оборудование с нарушениями (ФАП-145, пп. 19–25): "
                        + "; ".join(invalid_equipments)
                    )
                })

    def __str__(self) -> str:
        return self.outfit_card_number or f"Карта-наряд #{self.pk}"

    def get_workers(self) -> str:
        """Возвращает форматированный список исполнителей из сменных табелей."""
        workers = ReportCard.objects.filter(outfit_card=self)
        return ", ".join(set([format_name_initials(worker.employee.title) for worker in workers if worker.employee]))

    def get_works(self) -> str:
        """Возвращает перечень выполненных регламентных и оперативных работ."""
        works = [item.code for item in self.periodic_work.all()] + [item.code for item in self.operational_work.all()]
        if self.other_work:
            works.append(self.other_work)
        return ", ".join(works)

    def generate_signature_hash(self) -> str:
        """Формирует контрольную сумму SHA-256 для гарантии неизменяемости карты-наряда по п. 40 ФАП-367.

        Returns:
            str: 64-значный шестнадцатеричный хэш SHA-256.
        """
        payload = (
            f"{self.pk}:{self.outfit_card_number}:{self.outfit_card_date}:"
            f"{self.air_board_id}:{self.flight_hours}:{self.flight_cycles}:"
            f"{self.certifying_staff_id}:{self.is_signed}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_data(self) -> Dict[str, Any]:
        """Формирует сериализованные данные для таблицы DataTables.

        Returns:
            dict: Словарь с атрибутами карты-наряда, наработкой и статусом подписания.
        """
        self.get_workers()
        status_badge = (
            '<span class="badge bg-success text-white">Подписан (CRS)</span>'
            if self.is_signed
            else '<span class="badge bg-warning text-dark">В работе</span>'
        )
        air_board_str = (
            f"{self.air_board.type_property} {self.air_board.registration_number}"
            if self.air_board
            else "—"
        )
        staff_badge = ""
        if self.certifying_staff:
            try:
                from hrdepartment_app.services.outfit_card_release_service import get_staff_fap145_qualification_status
                check_date = self.outfit_card_date_end or self.outfit_card_date
                qual = get_staff_fap145_qualification_status(self.certifying_staff, check_date)
                staff_badge = qual["badge_html"]
            except Exception:
                staff_badge = ""

        eq_count = self.used_equipment_records.count()

        return {
            "pk": self.pk,
            "outfit_card_date": f"{self.outfit_card_date:%d.%m.%Y} г." if self.outfit_card_date else "—",
            "air_board": air_board_str,
            "works": self.get_works(),
            "outfit_card_number": self.outfit_card_number or f"#{self.pk}",
            "workers": self.get_workers(),
            "employee": format_name_initials(self.employee.title) if self.employee else "—",
            "certifying_staff": format_name_initials(self.certifying_staff.title) if self.certifying_staff else "—",
            "certifying_staff_badge": staff_badge,
            "equipment_count": eq_count,
            "flight_hours": float(self.flight_hours or 0.0),
            "flight_cycles": self.flight_cycles or 0,
            "is_signed": self.is_signed,
            "status": status_badge,
            "crs_number": self.crs_number or "—",
        }

    def save(self, *args, **kwargs) -> None:
        """Сохраняет карту-наряд, синхронизирует хэш неизменяемости и наработку ВС."""
        if self.is_signed and not self.signature_hash:
            self.signature_hash = self.generate_signature_hash()
        super().save(*args, **kwargs)

        # Автоматическая фиксация наработки ВС в журнал AircraftHoursTracking
        if self.air_board_id and self.flight_hours and self.flight_hours > 0 and self.outfit_card_date:
            try:
                AircraftHoursTracking.objects.update_or_create(
                    outfit_card=self,
                    defaults={
                        "air_board": self.air_board,
                        "record_date": self.outfit_card_date,
                        "flight_hours": self.flight_hours,
                        "flight_hours_tsor": self.flight_hours_tsor or Decimal("0.0"),
                        "flight_cycles": self.flight_cycles or 0,
                        "source": HoursTrackingSource.OUTFIT_CARD,
                        "notes": f"Автоматически зафиксировано из карты-наряда {self.outfit_card_number}",
                        "created_by": self.employee,
                    },
                )
            except Exception as e:
                logger.warning(f"Ошибка автосинхронизации наработки ВС для карты-наряда #{self.pk}: {e}")

    def get_absolute_url(self) -> str:
        """Возвращает канонический URL детального просмотра карты-наряда.

        Returns:
            str: URL маршрута 'hrdepartment_app:outfit_card'.
        """
        return reverse("hrdepartment_app:outfit_card", kwargs={"pk": self.pk})


class HoursTrackingSource(models.TextChoices):
    """Источники фиксации наработки воздушного судна."""

    MANUAL = "manual", "Ручной ввод"
    IMPORT = "import", "Импорт из файла (Excel/CSV)"
    OUTFIT_CARD = "outfit_card", "Карта-наряд на ТО"


class AircraftHoursTracking(models.Model):
    """Журнал учета наработки и циклов воздушных судов (ФАП-367, разд. XIV).

    Хранит хронологические срезы наработки ВС: налет СНЭ (с начала эксплуатации),
    налет ППР (после последнего ремонта/оверхола), количество посадок/циклов,
    источник фиксации (ручной ввод, импорт из Excel/CSV или карта-наряд на ТО)
    и автора записи.

    Attributes:
        air_board (Estate): Обслуживаемое воздушное судно.
        record_date (date): Дата фиксации показателей наработки.
        flight_hours (Decimal): Наработка планера СНЭ в часах.
        flight_hours_tsor (Decimal): Наработка планера ППР в часах.
        flight_cycles (int): Количество посадок / циклов с начала эксплуатации.
        source (str): Источник данных (manual, import, outfit_card).
        outfit_card (OutfitCard): Ссылка на карту-наряд (при фиксации из наряда).
        notes (str): Служебное примечание.
        created_by (DataBaseUser): Пользователь / инженер, внесший данные.
        created_at (datetime): Дата и время создания записи.
        updated_at (datetime): Дата и время последнего изменения.
    """

    class Meta:
        verbose_name = "Учет наработки ВС"
        verbose_name_plural = "Учет наработки ВС"
        ordering = ("-record_date", "-created_at")
        indexes = [
            models.Index(fields=["air_board", "-record_date"], name="idx_hours_aircraft_date"),
            models.Index(fields=["record_date"], name="idx_hours_record_date"),
        ]

    air_board = models.ForeignKey(
        Estate,
        verbose_name="Воздушное судно",
        on_delete=models.CASCADE,
        related_name="hours_tracking_records",
        help_text="Воздушное судно, для которого фиксируется наработка",
    )
    record_date = models.DateField(
        verbose_name="Дата фиксации наработки",
        db_index=True,
        help_text="Календарная дата среза наработки",
    )
    flight_hours = models.DecimalField(
        verbose_name="Наработка СНЭ (ч)",
        max_digits=9,
        decimal_places=1,
        default=Decimal("0.0"),
        help_text="Наработка планера ВС с начала эксплуатации в часах",
    )
    flight_hours_tsor = models.DecimalField(
        verbose_name="Наработка ППР (ч)",
        max_digits=9,
        decimal_places=1,
        default=Decimal("0.0"),
        blank=True,
        null=True,
        help_text="Наработка планера ВС после последнего ремонта (ППР) в часах",
    )
    flight_cycles = models.PositiveIntegerField(
        verbose_name="Количество посадок / циклов",
        default=0,
        blank=True,
        null=True,
        help_text="Количество посадок/циклов с начала эксплуатации",
    )
    source = models.CharField(
        verbose_name="Источник данных",
        max_length=20,
        choices=HoursTrackingSource.choices,
        default=HoursTrackingSource.MANUAL,
        help_text="Способ внесения данных: ручной ввод, импорт из Excel или карта-наряд",
    )
    outfit_card = models.ForeignKey(
        OutfitCard,
        verbose_name="Карта-наряд",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hours_tracking_entries",
        help_text="Связанная карта-наряд на ТО (если запись создана автоматически)",
    )
    notes = models.TextField(
        verbose_name="Примечание",
        blank=True,
        default="",
        help_text="Служебные примечания к записи наработки",
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        verbose_name="Автор записи",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_hours_tracking",
        help_text="Сотрудник, зафиксировавший показатели наработки",
    )
    created_at = models.DateTimeField(
        verbose_name="Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="Дата изменения",
        auto_now=True,
    )

    def __str__(self) -> str:
        board_name = (
            f"{self.air_board.type_property} {self.air_board.registration_number}"
            if self.air_board
            else f"Борт #{self.air_board_id}"
        )
        return f"{board_name} от {self.record_date:%d.%m.%Y}: СНЭ {self.flight_hours} ч"

    def get_data(self) -> Dict[str, Any]:
        """Формирует сериализованные данные для таблицы DataTables.

        Returns:
            Dict[str, Any]: Словарь с форматированными полями и бейджами.
        """
        source_badges = {
            HoursTrackingSource.MANUAL.value: '<span class="badge bg-secondary">Ручной ввод</span>',
            HoursTrackingSource.IMPORT.value: '<span class="badge bg-info text-dark">Импорт Excel</span>',
            HoursTrackingSource.OUTFIT_CARD.value: '<span class="badge bg-primary">Карта-наряд</span>',
        }
        badge = source_badges.get(
            self.source,
            f'<span class="badge bg-secondary">{self.get_source_display()}</span>',
        )
        board_str = (
            f"{self.air_board.type_property} {self.air_board.registration_number}"
            if self.air_board
            else "—"
        )
        return {
            "pk": self.pk,
            "air_board": board_str,
            "air_board_id": self.air_board_id,
            "record_date": f"{self.record_date:%d.%m.%Y} г." if self.record_date else "—",
            "flight_hours": float(self.flight_hours or 0.0),
            "flight_hours_tsor": float(self.flight_hours_tsor or 0.0),
            "flight_cycles": self.flight_cycles or 0,
            "source": badge,
            "notes": self.notes or "—",
            "created_by": format_name_initials(self.created_by.title) if self.created_by else "—",
            "created_at": f"{self.created_at:%d.%m.%Y %H:%M}" if self.created_at else "—",
        }


def subcontractor_certificate_upload_path(instance: Any, filename: str) -> str:
    """Генерирует относительный путь для сохранения скан-копии сертификата сторонней организации.

    Args:
        instance: Экземпляр модели ExternalMaintenanceOrganization.
        filename: Имя загружаемого файла.

    Returns:
        str: Относительный путь вида 'subcontractors/certificates/<filename>'.
    """
    clean_name = filename.replace(" ", "_")
    return f"subcontractors/certificates/{clean_name}"


def component_release_doc_upload_path(instance: Any, filename: str) -> str:
    """Генерирует относительный путь для сохранения входящего документа о годности агрегата.

    Args:
        instance: Экземпляр модели AviationComponent.
        filename: Имя загружаемого файла.

    Returns:
        str: Относительный путь вида 'aviation_components/release_docs/<p_num>/<filename>'.
    """
    clean_name = filename.replace(" ", "_")
    p_num = instance.part_number.replace("/", "-").replace(" ", "_") if instance.part_number else "general"
    return f"aviation_components/release_docs/{p_num}/{clean_name}"


class ExternalMaintenanceOrganization(models.Model):
    """Реестр привлекаемых сторонних организаций по ТО компонентов (ФАП-367, Раздел XV).

    В соответствии с п. 96 ФАП-367, организация по ТО ведет перечень привлекаемых
    организаций для выполнения ТО и капитального ремонта компонентов (двигателей,
    ВСУ, винтов, агрегатов) по категориям B и C, контролирует наличие у них
    действующих сертификатов ФАВТ, область одобрения и сроки их действия.

    Attributes:
        name (str): Полное официальное наименование организации.
        short_name (str): Сокращенное наименование для быстрого отображения.
        counteragent (Counteragent): Связанный контрагент из учетной системы 1С.
        certificate_number (str): Номер сертификата организации по ТО (ФАВТ / Росавиация).
        certificate_agency (str): Наименование органа гражданской авиации, выдавшего сертификат.
        certificate_issue_date (date): Дата выдачи действующего сертификата.
        certificate_valid_until (date): Дата окончания срока действия (null, если бессрочный).
        approved_categories (str): Разрешенные категории, рейтинги и компоненты (B1/B2/B3, C1-C20).
        contract_number (str): Номер и дата действующего договора на ТО компонентов.
        contract_file (FileField): Электронная копия договора на ТО.
        certificate_scan (FileField): Электронная копия сертификата организации.
        is_active (bool): Признак одобренного статуса организации.
        notes (str): Служебные примечания и условия взаимодействия.
        created_at (datetime): Дата внесения записи.
        updated_at (datetime): Дата последнего обновления.
    """

    class Meta:
        verbose_name = "Привлеченная организация по ТО"
        verbose_name_plural = "Привлеченные организации по ТО (ФАП-367)"
        ordering = ("short_name", "name")
        indexes = [
            models.Index(fields=["certificate_number"], name="idx_subcontractor_cert"),
            models.Index(fields=["is_active"], name="idx_subcontractor_active"),
        ]

    name = models.CharField(
        verbose_name="Полное наименование",
        max_length=255,
        help_text="Официальное наименование авиаремонтного завода или организации по ТО",
    )
    short_name = models.CharField(
        verbose_name="Краткое наименование",
        max_length=150,
        help_text="Сокращенное наименование (например, АО 'СПАРК', АО '218 АРЗ')",
    )
    counteragent = models.ForeignKey(
        Counteragent,
        verbose_name="Контрагент 1С",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_subcontractor_profiles",
        help_text="Связанная карточка контрагента из 1С:Предприятие",
    )
    certificate_number = models.CharField(
        verbose_name="Номер сертификата ТО",
        max_length=100,
        db_index=True,
        help_text="Номер действующего сертификата организации по ТО (напр., СПАС-ТО-145-2023-01)",
    )
    certificate_agency = models.CharField(
        verbose_name="Орган, выдавший сертификат",
        max_length=150,
        default="Федеральное агентство воздушного транспорта (Росавиация)",
        help_text="Наименование уполномоченного органа в области гражданской авиации",
    )
    certificate_issue_date = models.DateField(
        verbose_name="Дата выдачи сертификата",
        help_text="Дата первоначальной выдачи или последнего продления сертификата",
    )
    certificate_valid_until = models.DateField(
        verbose_name="Срок действия сертификата",
        null=True,
        blank=True,
        help_text="Оставьте пустым, если сертификат действует бессрочно с периодическим контролем",
    )
    approved_categories = models.TextField(
        verbose_name="Разрешенные категории и компоненты",
        help_text="Область деятельности по сертификату: категории B1, B2, B3, C1-C20, конкретные типы компонентов",
    )
    contract_number = models.CharField(
        verbose_name="Номер и дата договора",
        max_length=150,
        blank=True,
        default="",
        help_text="Реквизиты действующего договора на ТО и ремонт компонентов",
    )
    contract_file = models.FileField(
        verbose_name="Скан договора",
        upload_to="subcontractors/contracts/",
        blank=True,
        null=True,
        help_text="Электронная копия договора с привлекаемой организацией",
    )
    certificate_scan = models.FileField(
        verbose_name="Скан сертификата ТО",
        upload_to=subcontractor_certificate_upload_path,
        blank=True,
        null=True,
        help_text="Электронная копия действующего сертификата организации по ТО",
    )
    is_active = models.BooleanField(
        verbose_name="Одобренный статус (активен)",
        default=True,
        help_text="Флаг активного допуска привлекаемой организации к выполнению работ",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Дополнительные условия, контакты ОТК, ограничения",
    )
    created_at = models.DateTimeField(
        verbose_name="Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="Дата изменения",
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"{self.short_name or self.name} (Сертификат {self.certificate_number})"

    def is_certificate_valid(self, on_date: Optional[datetime.date] = None) -> bool:
        """Проверяет легитимность сертификата организации на указанную дату.

        Args:
            on_date: Дата проверки (по умолчанию текущая дата).

        Returns:
            bool: True, если организация активна и сертификат действителен.
        """
        if not self.is_active:
            return False
        check_date = on_date or datetime.date.today()
        if self.certificate_issue_date and check_date < self.certificate_issue_date:
            return False
        if self.certificate_valid_until and check_date > self.certificate_valid_until:
            return False
        return True

    def get_data(self) -> Dict[str, Any]:
        """Формирует данные для отображения в реестрах DataTables.

        Returns:
            Dict[str, Any]: Словарь с сериализованными полями и HTML-бейджами.
        """
        today = datetime.date.today()
        if not self.is_active:
            status_badge = '<span class="badge bg-danger">Отозван / Не активен</span>'
        elif self.certificate_valid_until and self.certificate_valid_until < today:
            status_badge = '<span class="badge bg-danger">Сертификат просрочен</span>'
        elif self.certificate_valid_until and (self.certificate_valid_until - today).days <= 30:
            status_badge = '<span class="badge bg-warning text-dark">Истекает скоро</span>'
        else:
            status_badge = '<span class="badge bg-success">Действует</span>'

        valid_str = (
            f"до {self.certificate_valid_until:%d.%m.%Y} г."
            if self.certificate_valid_until
            else "Бессрочный"
        )
        return {
            "pk": self.pk,
            "name": self.name,
            "short_name": self.short_name or self.name,
            "certificate_number": self.certificate_number,
            "validity": f"от {self.certificate_issue_date:%d.%m.%Y} {valid_str}",
            "status": status_badge,
            "contract": self.contract_number or "—",
            "is_active": self.is_active,
        }


class AviationComponentStatus(models.TextChoices):
    """Жизненный цикл и статус годности авиационного компонента."""

    STOCK = "stock", "На складе (годен к установке)"
    INSTALLED = "installed", "Установлен на ВС"
    REPAIR = "repair", "В ремонте у сторонней организации"
    SCRAPPED = "scrapped", "Списан / Брак / Ресурс исчерпан"


class ComponentReleaseDocType(models.TextChoices):
    """Типы входящих документов о годности компонентов (ФАП-367, Раздел IV)."""

    FORM_1 = "form_1", "Талон годности компонента (Приложение № 2 к ФАП-367 / Form 1)"
    PASSPORT = "passport", "Паспорт / Формуляр агрегата завода"
    LABEL = "label", "Этикетка / Талон завода-изготовителя"
    OTHER = "other", "Иной входящий документ о годности"


class AviationComponent(models.Model):
    """Реестр авиационных компонентов и входящих документов о годности (ФАП-367, Разделы IV и XV).

    Содержит сведения обо всех критических компонентах ВС (двигателях, редукторах,
    агрегатах гидросистем, авионике), их номерах P/N и S/N, текущем статусе годности,
    реквизитах входящих паспортов / Талонов годности сторонних организаций по ТО
    и остатке назначенного / межремонтного ресурса.

    Attributes:
        name (str): Наименование компонента / агрегата.
        part_number (str): Чертежный номер (Part Number / P/N).
        serial_number (str): Заводской / серийный номер (Serial Number / S/N).
        aircraft_type (TypeProperty): Применимый тип ВС.
        status (str): Текущее состояние компонента (на складе, на ВС, в ремонте, списан).
        current_aircraft (Estate): Воздушное судно, на котором сейчас установлен компонент.
        last_repair_org (ExternalMaintenanceOrganization): Организация, выполнившая последнее ТО/ремонт.
        release_doc_type (str): Вид входящего документа о годности.
        release_doc_number (str): Номер входящего Талона годности / паспорта агрегата.
        release_doc_date (date): Дата оформления входящего документа о годности.
        release_doc_file (FileField): Электронный скан входящего документа о годности.
        hours_since_new (Decimal): Наработка с начала эксплуатации (СНЭ), часов.
        hours_since_overhaul (Decimal): Наработка после последнего ремонта (ППР), часов.
        resource_limit_hours (Decimal): Назначенный или межремонтный ресурс, часов.
        remaining_hours (Decimal): Остаток ресурса в часах.
        notes (str): Служебные примечания.
        created_at (datetime): Дата создания записи.
        updated_at (datetime): Дата обновления записи.
    """

    class Meta:
        verbose_name = "Авиационный компонент"
        verbose_name_plural = "Авиационные компоненты (ФАП-367)"
        ordering = ("name", "part_number", "serial_number")
        indexes = [
            models.Index(fields=["part_number", "serial_number"], name="idx_comp_pn_sn"),
            models.Index(fields=["status"], name="idx_comp_status"),
            models.Index(fields=["current_aircraft"], name="idx_comp_aircraft"),
        ]

    name = models.CharField(
        verbose_name="Наименование компонента",
        max_length=200,
        help_text="Наименование агрегата (напр., Двигатель ТВ2-117А, Редуктор ВР-8А, Насос НШ-39М)",
    )
    part_number = models.CharField(
        verbose_name="Чертежный номер (P/N)",
        max_length=100,
        db_index=True,
        help_text="Чертежный номер детали/агрегата по каталогу",
    )
    serial_number = models.CharField(
        verbose_name="Заводской номер (S/N)",
        max_length=100,
        db_index=True,
        help_text="Серийный или заводской номер экземпляра компонента",
    )
    aircraft_type = models.ForeignKey(
        TypeProperty,
        verbose_name="Тип ВС",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aviation_components",
        help_text="Тип воздушного судна, на котором применяется компонент",
    )
    status = models.CharField(
        verbose_name="Статус годности",
        max_length=20,
        choices=AviationComponentStatus.choices,
        default=AviationComponentStatus.STOCK,
        help_text="Текущее физическое состояние и местонахождение компонента",
    )
    current_aircraft = models.ForeignKey(
        Estate,
        verbose_name="Установлен на ВС",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installed_components",
        help_text="Воздушное судно, на котором смонтирован компонент (при статусе 'Установлен')",
    )
    last_repair_org = models.ForeignKey(
        ExternalMaintenanceOrganization,
        verbose_name="Привлеченная организация (последнее ТО)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repaired_components",
        help_text="Сторонняя сертифицированная организация (АРЗ), выполнившая последнее ТО или оверхол",
    )
    release_doc_type = models.CharField(
        verbose_name="Вид входящего документа",
        max_length=20,
        choices=ComponentReleaseDocType.choices,
        default=ComponentReleaseDocType.FORM_1,
        help_text="Вид документа, подтверждающего годность компонента перед установкой (п. 28 ФАП-367)",
    )
    release_doc_number = models.CharField(
        verbose_name="Номер документа о годности",
        max_length=100,
        blank=True,
        default="",
        help_text="Номер Талона годности по Приложению № 2, паспорта или этикетки",
    )
    release_doc_date = models.DateField(
        verbose_name="Дата документа о годности",
        null=True,
        blank=True,
        help_text="Дата оформления входящего документа о годности сторонней организацией",
    )
    release_doc_file = models.FileField(
        verbose_name="Скан документа о годности",
        upload_to=component_release_doc_upload_path,
        null=True,
        blank=True,
        help_text="Электронная скан-копия входящего Талона годности или паспорта агрегата",
    )
    hours_since_new = models.DecimalField(
        verbose_name="Наработка СНЭ (ч)",
        max_digits=9,
        decimal_places=1,
        default=Decimal("0.0"),
        help_text="Наработка компонента с начала эксплуатации в часах",
    )
    hours_since_overhaul = models.DecimalField(
        verbose_name="Наработка ППР (ч)",
        max_digits=9,
        decimal_places=1,
        default=Decimal("0.0"),
        help_text="Наработка компонента после последнего ремонта в часах",
    )
    resource_limit_hours = models.DecimalField(
        verbose_name="Назначенный ресурс (ч)",
        max_digits=9,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Полный назначенный ресурс компонента в часах",
    )
    remaining_hours = models.DecimalField(
        verbose_name="Остаток ресурса (ч)",
        max_digits=9,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Остаток ресурса до очередного ТО или списания",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Особые отметки, консервация, рекламации",
    )
    created_at = models.DateTimeField(
        verbose_name="Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="Дата изменения",
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"{self.name} (P/N {self.part_number}, S/N {self.serial_number})"

    def clean(self) -> None:
        """Проверяет полноту реквизитов документа о годности при годном статусе.

        Raises:
            ValidationError: Если компонент годен или установлен, но номер документа не указан.
        """
        super().clean()
        if self.status in (AviationComponentStatus.STOCK, AviationComponentStatus.INSTALLED):
            if not self.release_doc_number.strip():
                raise ValidationError({
                    "release_doc_number": (
                        "Для годного к установке компонента обязателен номер входящего документа о годности "
                        "(Талон годности Приложение № 2, паспорт или этикетка завода по п. 28 ФАП-367)."
                    )
                })

    def get_data(self) -> Dict[str, Any]:
        """Формирует данные для сериализации в таблицах DataTables.

        Returns:
            Dict[str, Any]: Словарь полей для фронтенда.
        """
        status_badges = {
            AviationComponentStatus.STOCK.value: '<span class="badge bg-success">На складе (годен)</span>',
            AviationComponentStatus.INSTALLED.value: '<span class="badge bg-primary">Установлен на ВС</span>',
            AviationComponentStatus.REPAIR.value: '<span class="badge bg-warning text-dark">В ремонте (АРЗ)</span>',
            AviationComponentStatus.SCRAPPED.value: '<span class="badge bg-danger">Списан</span>',
        }
        badge = status_badges.get(
            self.status,
            f'<span class="badge bg-secondary">{self.get_status_display()}</span>',
        )
        aircraft_str = (
            f"{self.current_aircraft.registration_number}"
            if self.current_aircraft
            else "—"
        )
        doc_str = (
            f"{self.get_release_doc_type_display()} № {self.release_doc_number}"
            if self.release_doc_number
            else "Без документа"
        )
        if self.release_doc_date:
            doc_str += f" от {self.release_doc_date:%d.%m.%Y}"

        return {
            "pk": self.pk,
            "name": self.name,
            "part_number": self.part_number,
            "serial_number": self.serial_number,
            "aircraft_type": str(self.aircraft_type) if self.aircraft_type else "—",
            "status": badge,
            "aircraft": aircraft_str,
            "release_doc": doc_str,
            "repair_org": self.last_repair_org.short_name if self.last_repair_org else "—",
            "remaining_hours": float(self.remaining_hours) if self.remaining_hours is not None else "—",
        }


class ComponentOperationType(models.TextChoices):
    """Типы технологических операций с компонентами в карте-наряде."""

    INSTALL = "install", "Установка компонента"
    REMOVE = "remove", "Демонтаж (снятие) компонента"
    REPLACE = "replace", "Замена (снятие и установка)"


class OutfitCardComponent(models.Model):
    """Фиксация установки и демонтажа компонентов при выполнении ТО (ФАП-367, пп. 38, 88).

    Отражает состав замененных компонентов в рамках карты-наряда: связывает
    устанавливаемый компонент с входящим документом о годности, фиксирует снятый агрегат,
    причину демонтажа и выполняет автоматический контроль легитимности привлеченной
    организации на дату выполнения наряда.

    Attributes:
        outfit_card (OutfitCard): Обслуживаемая карта-наряд.
        operation_type (str): Тип операции (установка, снятие, замена).
        installed_component (AviationComponent): Устанавливаемый на ВС компонент.
        removed_component_name (str): Наименование снятого агрегата.
        removed_part_number (str): Чертежный номер (P/N) снятого агрегата.
        removed_serial_number (str): Заводской номер (S/N) снятого агрегата.
        removal_reason (str): Основание для снятия (выработка ресурса, отказ, плановое ТО).
        operating_hours_on_install (Decimal): Наработка планера ВС на момент замены (часов).
        installed_position (str): Позиция установки (напр. 'Двигатель № 1', 'Основная гидросистема').
        notes (str): Служебные примечания.
        created_at (datetime): Дата фиксации операции.
        updated_at (datetime): Дата изменения записи.
    """

    class Meta:
        verbose_name = "Движение компонента при ТО"
        verbose_name_plural = "Движение компонентов при ТО (ФАП-367)"
        ordering = ("outfit_card", "-created_at")
        indexes = [
            models.Index(fields=["outfit_card"], name="idx_outfit_comp_card"),
            models.Index(fields=["installed_component"], name="idx_outfit_comp_installed"),
        ]

    outfit_card = models.ForeignKey(
        OutfitCard,
        verbose_name="Карта-наряд",
        on_delete=models.CASCADE,
        related_name="component_operations",
        help_text="Карта-наряд, в рамках которой выполняются работы с компонентом",
    )
    operation_type = models.CharField(
        verbose_name="Тип операции",
        max_length=20,
        choices=ComponentOperationType.choices,
        default=ComponentOperationType.REPLACE,
        help_text="Характер выполняемой операции с компонентом",
    )
    installed_component = models.ForeignKey(
        AviationComponent,
        verbose_name="Устанавливаемый агрегат",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="card_installations",
        help_text="Устанавливаемый агрегат с действующим входящим документом о годности",
    )
    removed_component_name = models.CharField(
        verbose_name="Наименование снятого агрегата",
        max_length=200,
        blank=True,
        default="",
        help_text="Наименование демонтированного с ВС компонента",
    )
    removed_part_number = models.CharField(
        verbose_name="Чертежный номер снятого (P/N)",
        max_length=100,
        blank=True,
        default="",
        help_text="Чертежный номер снятого агрегата",
    )
    removed_serial_number = models.CharField(
        verbose_name="Заводской номер снятого (S/N)",
        max_length=100,
        blank=True,
        default="",
        help_text="Заводской/серийный номер снятого агрегата",
    )
    removal_reason = models.CharField(
        verbose_name="Причина снятия",
        max_length=255,
        blank=True,
        default="Плановая замена по выработке ресурса",
        help_text="Причина демонтажа: выработка ресурса, отказ, плановое ТО, бюллетень",
    )
    operating_hours_on_install = models.DecimalField(
        verbose_name="Наработка ВС на момент установки (ч)",
        max_digits=9,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Показания наработки планера ВС на дату проведения операции",
    )
    installed_position = models.CharField(
        verbose_name="Место установки на ВС",
        max_length=150,
        blank=True,
        default="",
        help_text="Позиция агрегата на борту (напр., Двигатель левый, Рулевой винт)",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Дополнительные сведения о монтаже",
    )
    created_at = models.DateTimeField(
        verbose_name="Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="Дата изменения",
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"{self.get_operation_type_display()} к наряду {self.outfit_card.outfit_card_number or self.outfit_card_id}"

    def clean(self) -> None:
        """Выполняет проверку легитимности привлекаемой организации и документа о годности.

        Raises:
            ValidationError: Если нарушены требования ФАП-367 (Раздел IV и XV).
        """
        super().clean()
        if self.operation_type in (ComponentOperationType.INSTALL, ComponentOperationType.REPLACE):
            if not self.installed_component:
                raise ValidationError({
                    "installed_component": "При операции установки или замены необходимо выбрать устанавливаемый агрегат."
                })

            comp = self.installed_component
            if not comp.release_doc_number.strip():
                raise ValidationError({
                    "installed_component": (
                        f"Компонент '{comp.name}' (S/N {comp.serial_number}) не имеет входящего документа о годности "
                        "(Талон годности Приложение № 2, паспорт или этикетка по п. 28 ФАП-367). "
                        "Установка на воздушное судно запрещена."
                    )
                })

            # Проверка сертификата привлекаемой организации на дату наряда
            card_date = self.outfit_card.outfit_card_date if self.outfit_card else datetime.date.today()
            if comp.last_repair_org:
                org = comp.last_repair_org
                if not org.is_certificate_valid(card_date):
                    valid_to_str = (
                        f"{org.certificate_valid_until:%d.%m.%Y}"
                        if org.certificate_valid_until
                        else "отозван"
                    )
                    raise ValidationError({
                        "installed_component": (
                            f"Сертификат привлекаемой организации '{org.short_name}' "
                            f"(№ {org.certificate_number}) недействителен на дату ТО {card_date:%d.%m.%Y} "
                            f"(срок действия: {valid_to_str}). "
                            "Согласно п. 96 ФАП-367, установка агрегатов от организаций без действующего сертификата запрещена."
                        )
                    })

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет запись и автоматически синхронизирует статус компонента.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        super().save(*args, **kwargs)
        # Если компонент установлен, обновляем статус устанавливаемого компонента
        if self.installed_component and self.outfit_card:
            if self.operation_type in (ComponentOperationType.INSTALL, ComponentOperationType.REPLACE):
                self.installed_component.status = AviationComponentStatus.INSTALLED
                self.installed_component.current_aircraft = self.outfit_card.air_board
                self.installed_component.save(update_fields=["status", "current_aircraft", "updated_at"])


class EquipmentType(models.TextChoices):
    """Категории оборудования и инструментов для ТО ВС (Раздел III ФАП-145, п. 22)."""

    MEASURING = "measuring", "Средство измерений (СИ, 102-ФЗ)"
    CONTROL_TEST = "control_test", "Контрольно-поверочная аппаратура (КПА)"
    SPECIAL_TOOL = "special_tool", "Специальный инструмент"
    STANDARD_REFERENCE = "standard_reference", "Эталон / калибр / контрольный образец"
    GROUND_EQUIPMENT = "ground_equipment", "Наземное оборудование ТО"
    GENERAL_TOOL = "general_tool", "Общий инструмент"


class EquipmentOperationalStatus(models.TextChoices):
    """Эксплуатационный статус физического состояния оборудования (ФАП-145, пп. 19, 24, 25)."""

    SERVICEABLE = "serviceable", "Исправен (годен к применению)"
    DEFECTIVE = "defective", "Неисправен (п. 24 ФАП-145)"
    IN_REPAIR = "in_repair", "В ремонте / на ТО"
    QUARANTINED = "quarantined", "В изоляторе брака (карантин, п. 25 ФАП-145)"
    SCRAPPED = "scrapped", "Списан"


class EquipmentVerificationType(models.TextChoices):
    """Вид метрологического контроля и оценки пригодности (ФАП-145, пп. 19, 20)."""

    VERIFICATION = "verification", "Поверка (102-ФЗ)"
    CALIBRATION = "calibration", "Калибровка"
    INSPECTION = "inspection", "Проверка технического состояния"
    NOT_REQUIRED = "not_required", "Метрологический контроль не требуется"


class IntervalUnit(models.TextChoices):
    """Единицы измерения межповерочного интервала."""

    DAYS = "days", "дней"
    MONTHS = "months", "месяцев"
    YEARS = "years", "лет"


class EquipmentName(models.Model):
    """Справочник обобщенных наименований оборудования, СИ и инструмента (ФАП-145).

    Представляет верхний (1-й) уровень нормативно-справочной классификации приборов,
    средств измерений по 102-ФЗ, контрольно-поверочной аппаратуры (КПА) и специнструмента.
    Объединяет различные марки и модификации под единым родовым наименованием
    (например, 'Ареометр', 'Амперметр', 'Манометр', 'Динамометрический ключ').

    Attributes:
        name (str): Нормализованное наименование оборудования / СИ.
        category (str): Категория по классификации п. 22 ФАП-145 (из EquipmentType).
        is_measuring_instrument (bool): Признак средства измерений по 102-ФЗ.
        description (str): Описание, правила эксплуатации и условия хранения.
        created_at (datetime): Дата и время создания записи.
        updated_at (datetime): Дата и время последнего обновления.
    """

    class Meta:
        verbose_name = "Наименование оборудования и СИ"
        verbose_name_plural = "Справочник наименований оборудования и СИ (ФАП-145)"
        ordering = ("name",)

    name = models.CharField(
        verbose_name="Наименование оборудования / СИ",
        max_length=150,
        unique=True,
        db_index=True,
        help_text="Обобщенное наименование прибора или инструмента (напр. 'Ареометр', 'Амперметр')",
    )
    category = models.CharField(
        verbose_name="Категория оборудования",
        max_length=30,
        choices=EquipmentType.choices,
        default=EquipmentType.SPECIAL_TOOL,
        db_index=True,
        help_text="Категория оборудования по классификации п. 22 ФАП-145",
    )
    is_measuring_instrument = models.BooleanField(
        verbose_name="СИ по 102-ФЗ",
        default=True,
        help_text="Признак отнесения к средствам измерений, требующим поверки/калибровки",
    )
    description = models.TextField(
        verbose_name="Описание и правила хранения",
        blank=True,
        default="",
        help_text="Общие требования к условиям применения, консервации и хранения",
    )
    created_at = models.DateTimeField(verbose_name="Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата обновления", auto_now=True)

    def __str__(self) -> str:
        return self.name


class EquipmentTypeModel(models.Model):
    """Справочник типов, марок и моделей оборудования и СИ (ФАП-145, 102-ФЗ).

    Представляет средний (2-й) уровень классификации: конкретная конструктивная марка,
    модель или тип средства измерения (например, для Ареометра — 'АЭ-1', 'АНТ-2', 'АЭТ-1';
    для Амперметра — 'М42300', 'М42100'). Хранит нормативные метрологические свойства,
    номер Государственного реестра утвержденных типов СИ (ФГИС «АРШИН») и применимость к типам ВС.

    Attributes:
        equipment_name (EquipmentName): Родовое наименование прибора.
        name (str): Шифр, марка или модель (например, 'АЭ-1', 'М42300').
        part_number (str): Чертежный номер / Part Number (P/N) по каталогу изготовителя.
        arshin_type_number (str): Номер типа в Государственном реестре СИ РФ (ФГИС «АРШИН»).
        measurement_range (str): Диапазон измерений (напр. '1000...1060 кг/м³', '0...30 В').
        accuracy_class (str): Класс точности или предел допускаемой погрешности.
        default_interval_months (int): Базовый межповерочный интервал в месяцах.
        applicable_aircraft_types (ManyToManyField): Совместимость с типами ВС (пусто = универсально).
        created_at (datetime): Дата и время создания записи.
        updated_at (datetime): Дата и время последнего обновления.
    """

    class Meta:
        verbose_name = "Тип / модель оборудования и СИ"
        verbose_name_plural = "Справочник типов и моделей оборудования и СИ (ФАП-145)"
        ordering = ("equipment_name__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["equipment_name", "name"],
                name="uq_equipment_name_type_model",
            )
        ]

    equipment_name = models.ForeignKey(
        EquipmentName,
        verbose_name="Наименование оборудования",
        on_delete=models.PROTECT,
        related_name="type_models",
        help_text="Обобщенное наименование прибора/инструмента",
    )
    name = models.CharField(
        verbose_name="Тип / модель СИ",
        max_length=100,
        help_text="Обозначение типа/модели (напр. 'АЭ-1', 'АНТ-2', 'М42300')",
    )
    part_number = models.CharField(
        verbose_name="Чертежный номер / модель (P/N)",
        max_length=100,
        blank=True,
        default="",
        help_text="P/N по каталогу изготовителя или ГОСТ",
    )
    arshin_type_number = models.CharField(
        verbose_name="Номер Госреестра СИ РФ",
        max_length=50,
        blank=True,
        default="",
        help_text="Номер записи типа СИ в реестре ФГИС «АРШИН»",
    )
    measurement_range = models.CharField(
        verbose_name="Диапазон измерений",
        max_length=150,
        blank=True,
        default="",
        help_text="Диапазон измерений (напр. '1000...1060 кг/м³', '0...100 А')",
    )
    accuracy_class = models.CharField(
        verbose_name="Класс точности / Погрешность",
        max_length=100,
        blank=True,
        default="",
        help_text="Класс точности по ГОСТ или предел допускаемой погрешности",
    )
    default_interval_months = models.PositiveIntegerField(
        verbose_name="Межповерочный интервал (мес.)",
        default=12,
        help_text="Утвержденный межповерочный интервал в месяцах по методике поверки",
    )
    applicable_aircraft_types = models.ManyToManyField(
        "contracts_app.TypeProperty",
        blank=True,
        related_name="equipment_type_models",
        verbose_name="Применимость к типам ВС",
        help_text="Типы воздушных судов. Если список пуст — прибор применим ко всем типам ВС компании",
    )
    created_at = models.DateTimeField(verbose_name="Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата обновления", auto_now=True)

    def __str__(self) -> str:
        return f"{self.equipment_name.name} {self.name}"


class MaintenanceEquipment(models.Model):
    """Оборудование, приборы, КПА и специнструмент для ТО ВС (ФАП-145, пп. 19–25).

    Модель универсального реестра инструментов, средств измерений (102-ФЗ),
    контрольно-поверочной аппаратуры (КПА) и наземного оборудования технического
    обслуживания воздушных судов с дифференцированным контролем физического состояния,
    изолятора брака (п. 25) и метрологических сроков действия поверки/калибровки.

    Attributes:
        name (str): Полное наименование оборудования/прибора/инструмента.
        equipment_type (str): Категория (СИ по 102-ФЗ, КПА, специнструмент, эталон и др.).
        part_number (str): Чертежный номер / модель (P/N).
        serial_number (str): Заводской / серийный номер (S/N).
        inventory_number (str): Инвентарный номер бухгалтерского учета.
        marking_code (str): Код маркировки по системе маркировки ТО (п. 23 ФАП-145).
        applicable_aircraft_types (ManyToManyField): Применимость к типам воздушных судов.
        operational_status (str): Физическое состояние (исправен, неисправен, карантин, списан).
        verification_type (str): Вид контроля (поверка по 102-ФЗ, калибровка, проверка, не требуется).
        last_verification_date (date): Дата последней поверки/калибровки.
        next_verification_date (date): Дата окончания действия текущей поверки/калибровки.
        interval_value (int): Межповерочный / контрольный интервал.
        interval_unit (str): Единица измерения интервала (дни, месяцы, годы).
        interval_source (str): Основание интервала (РЭ изготовителя, методика поверки, 102-ФЗ).
        arshin_verification_number (str): Номер записи во ФГИС «АРШИН» / Свидетельства о поверке.
        verification_organization (str): Организация, проводившая поверку/калибровку.
        certificate_scan (FileField): Электронный скан-образ свидетельства/сертификата.
        location (str): Место нахождения / хранения (кладовая, участок, борт).
        production_place (PlaceProductionActivity): Место производственной деятельности (МПД).
        responsible_person (DataBaseUser): Лицо, ответственное за сохранность и метрологию.
        notes (str): Особые отметки и примечания.
        created_at (datetime): Дата внесения в реестр.
        updated_at (datetime): Дата последнего обновления.
    """

    class Meta:
        verbose_name = "Оборудование и инструмент ТО (ФАП-145)"
        verbose_name_plural = "Реестр оборудования и инструментов ТО (ФАП-145)"
        ordering = ("name", "serial_number")
        indexes = [
            models.Index(fields=["operational_status"], name="idx_eq_oper_status"),
            models.Index(fields=["equipment_type"], name="idx_eq_type"),
            models.Index(fields=["next_verification_date"], name="idx_eq_next_verif"),
            models.Index(fields=["serial_number"], name="idx_eq_serial"),
            models.Index(fields=["part_number"], name="idx_eq_part_num"),
        ]

    name = models.CharField(
        verbose_name="Наименование оборудования / инструмента",
        max_length=255,
        help_text="Полное наименование оборудования, прибора или специального инструмента",
    )
    type_model = models.ForeignKey(
        EquipmentTypeModel,
        verbose_name="Тип / модель СИ",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="instances",
        help_text="Ссылка на тип/модель из нормализованного справочника НСИ (ФАП-145)",
    )
    equipment_type = models.CharField(
        verbose_name="Категория оборудования",
        max_length=30,
        choices=EquipmentType.choices,
        default=EquipmentType.SPECIAL_TOOL,
        db_index=True,
        help_text="Категория оборудования по классификации п. 22 ФАП-145",
    )
    part_number = models.CharField(
        verbose_name="Чертежный номер / модель (P/N)",
        max_length=100,
        blank=True,
        default="",
        help_text="Part Number по каталогу изготовителя или маркировке",
    )
    serial_number = models.CharField(
        verbose_name="Заводской / серийный номер (S/N)",
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Заводской или серийный номер изделия (при наличии)",
    )
    inventory_number = models.CharField(
        verbose_name="Инвентарный номер",
        max_length=100,
        blank=True,
        default="",
        help_text="Бухгалтерский или складской инвентарный номер",
    )
    marking_code = models.CharField(
        verbose_name="Код маркировки (п. 23 ФАП-145)",
        max_length=100,
        blank=True,
        default="",
        help_text="Индивидуальный идентификационный код маркировки согласно п. 23 ФАП-145",
    )
    applicable_aircraft_types = models.ManyToManyField(
        "contracts_app.TypeProperty",
        blank=True,
        related_name="maintenance_equipments",
        verbose_name="Применимость к типам ВС",
        help_text="Типы воздушных судов, для ТО которых предназначен прибор/инструмент",
    )
    operational_status = models.CharField(
        verbose_name="Эксплуатационный статус",
        max_length=30,
        choices=EquipmentOperationalStatus.choices,
        default=EquipmentOperationalStatus.SERVICEABLE,
        db_index=True,
        help_text="Физическое состояние оборудования по пп. 19, 24, 25 ФАП-145",
    )
    verification_type = models.CharField(
        verbose_name="Вид метрологического контроля",
        max_length=30,
        choices=EquipmentVerificationType.choices,
        default=EquipmentVerificationType.NOT_REQUIRED,
        db_index=True,
        help_text="Вид обязательного метрологического подтверждения по п. 19, 20 ФАП-145",
    )
    last_verification_date = models.DateField(
        verbose_name="Дата последней поверки/калибровки",
        null=True,
        blank=True,
        help_text="Дата проведения последней поверки, калибровки или проверки состояния",
    )
    next_verification_date = models.DateField(
        verbose_name="Дата очередной поверки/калибровки",
        null=True,
        blank=True,
        db_index=True,
        help_text="Срок окончания действия текущей поверки/калибровки",
    )
    interval_value = models.PositiveIntegerField(
        verbose_name="Межповерочный / контрольный интервал",
        null=True,
        blank=True,
        help_text="Периодичность проведения поверки/калибровки",
    )
    interval_unit = models.CharField(
        verbose_name="Единица интервала",
        max_length=10,
        choices=IntervalUnit.choices,
        default=IntervalUnit.MONTHS,
    )
    interval_source = models.CharField(
        verbose_name="Основание интервала",
        max_length=255,
        blank=True,
        default="",
        help_text="Эксплуатационная документация изготовителя, методика поверки или регламент организации",
    )
    arshin_verification_number = models.CharField(
        verbose_name="Номер во ФГИС «АРШИН» / Свидетельства",
        max_length=100,
        blank=True,
        default="",
        help_text="Регистрационный номер свидетельства о поверке или записи в реестре ФГИС «АРШИН» (102-ФЗ)",
    )
    verification_organization = models.CharField(
        verbose_name="Организация-поверитель",
        max_length=255,
        blank=True,
        default="",
        help_text="Наименование аккредитованной метрологической службы / поверителя",
    )
    certificate_scan = models.FileField(
        verbose_name="Скан свидетельства / сертификата",
        upload_to="equipment_certificates/%Y/%m/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
        help_text="Электронный скан документа о поверке/калибровке",
    )
    location = models.CharField(
        verbose_name="Место хранения / нахождения",
        max_length=255,
        blank=True,
        default="",
        help_text="Инструментальная кладовая, борт ВС, контейнер, участок ТО",
    )
    production_place = models.ForeignKey(
        PlaceProductionActivity,
        verbose_name="МПД приписки",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipments",
        help_text="Место производственной деятельности постоянного базирования",
    )
    responsible_person = models.ForeignKey(
        DataBaseUser,
        verbose_name="Ответственное лицо",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_equipments",
        help_text="Сотрудник, ответственный за сохранность и метрологический контроль",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Особые условия эксплуатации, поверки или хранения",
    )
    created_at = models.DateTimeField(verbose_name="Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата обновления", auto_now=True)

    def __str__(self) -> str:
        ident = f"S/N: {self.serial_number}" if self.serial_number else f"P/N: {self.part_number or 'б/н'}"
        return f"{self.name} ({ident})"

    @property
    def metrology_status(self) -> str:
        """Вычисляет текущий метрологический статус оборудования на сегодня.

        Returns:
            str: Код статуса ('VALID', 'EXPIRING', 'EXPIRED', 'NOT_APPLICABLE', 'NOT_VERIFIED').
        """
        if self.verification_type == EquipmentVerificationType.NOT_REQUIRED:
            return "NOT_APPLICABLE"
        if not self.next_verification_date:
            return "NOT_VERIFIED"
        today = timezone.now().date()
        if self.next_verification_date < today:
            return "EXPIRED"
        if (self.next_verification_date - today).days <= 30:
            return "EXPIRING"
        return "VALID"

    @property
    def days_until_verification(self) -> Optional[int]:
        """Возвращает количество календарных дней до окончания действия поверки/калибровки.

        Returns:
            Optional[int]: Количество дней (отрицательное значение означает просрочку).
        """
        if not self.next_verification_date:
            return None
        return (self.next_verification_date - timezone.now().date()).days

    @property
    def is_metrology_valid(self) -> bool:
        """Проверяет пригодность оборудования к применению на текущую дату."""
        valid, _ = self.can_be_used_for_maintenance(timezone.now().date())
        return valid

    def can_be_used_for_maintenance(self, target_date: Optional[date] = None) -> Tuple[bool, str]:
        """Проверяет пригодность оборудования для выполнения ТО на заданную дату по ФАП-145 (пп. 19-25).

        Args:
            target_date (Optional[date]): Дата выполнения работ (по умолчанию текущая дата).

        Returns:
            Tuple[bool, str]: Кортеж (разрешено_к_применению, текстовое_обоснование).
        """
        check_date = target_date or timezone.now().date()

        # 1. Проверка физического состояния
        if self.operational_status == EquipmentOperationalStatus.QUARANTINED:
            return False, "Оборудование находится в изоляторе брака (карантин по п. 25 ФАП-145)"
        if self.operational_status == EquipmentOperationalStatus.DEFECTIVE:
            return False, "Оборудование признано неисправным (пп. 19, 24 ФАП-145)"
        if self.operational_status == EquipmentOperationalStatus.IN_REPAIR:
            return False, "Оборудование находится в ремонте / на ТО"
        if self.operational_status == EquipmentOperationalStatus.SCRAPPED:
            return False, "Оборудование списано"
        if self.operational_status != EquipmentOperationalStatus.SERVICEABLE:
            return False, f"Статус оборудования не позволяет применение: {self.get_operational_status_display()}"

        # 2. Проверка метрологического контроля
        if self.verification_type == EquipmentVerificationType.NOT_REQUIRED:
            return True, "Метрологический контроль не требуется, инструмент исправен"

        if not self.last_verification_date and not self.next_verification_date:
            return False, "Отсутствуют сведения о проведенной поверке/калибровке (пп. 19, 20 ФАП-145)"

        if self.next_verification_date and self.next_verification_date < check_date:
            return False, (
                f"Срок действия поверки/калибровки истек {self.next_verification_date:%d.%m.%Y} "
                f"(на дату ТО {check_date:%d.%m.%Y})"
            )

        return True, "Оборудование исправно и поверено"

    def clean(self) -> None:
        """Валидирует непротиворечивость метрологических данных и основания интервала.

        Raises:
            ValidationError: При логических несоответствиях дат или отсутствии основания интервала.
        """
        super().clean()
        if self.last_verification_date and self.next_verification_date:
            if self.next_verification_date <= self.last_verification_date:
                raise ValidationError({
                    "next_verification_date": "Дата очередной поверки должна быть позже даты последней поверки."
                })
        if self.verification_type != EquipmentVerificationType.NOT_REQUIRED and self.interval_value:
            if not self.interval_source.strip():
                raise ValidationError({
                    "interval_source": "При указании межповерочного интервала укажите его основание (РЭ изготовителя, методика поверки, 102-ФЗ)."
                })

    def get_data(self) -> Dict[str, Any]:
        """Формирует данные для сериализации в DataTables.

        Returns:
            Dict[str, Any]: Словарь атрибутов оборудования для отображения в реестре.
        """
        status_map = {
            "VALID": '<span class="badge bg-success text-white">Поверен (годен)</span>',
            "EXPIRING": '<span class="badge bg-warning text-dark">Истекает поверка</span>',
            "EXPIRED": '<span class="badge bg-danger text-white">Просрочен</span>',
            "NOT_VERIFIED": '<span class="badge bg-secondary text-white">Не поверен</span>',
            "NOT_APPLICABLE": '<span class="badge bg-light text-dark">Не требуется</span>',
        }
        return {
            "pk": self.pk,
            "name": self.name,
            "part_number": self.part_number or "—",
            "serial_number": self.serial_number or "—",
            "inventory_number": self.inventory_number or "—",
            "marking_code": self.marking_code or "—",
            "equipment_type": self.get_equipment_type_display(),
            "operational_status": self.get_operational_status_display(),
            "verification_type": self.get_verification_type_display(),
            "next_verification_date": (
                f"{self.next_verification_date:%d.%m.%Y} г." if self.next_verification_date else "—"
            ),
            "type_model": str(self.type_model) if self.type_model else "—",
            "type_model_id": self.type_model_id,
            "metrology_badge": status_map.get(self.metrology_status, "—"),
            "location": self.location or "—",
            "responsible_person": (
                format_name_initials(self.responsible_person.title) if self.responsible_person else "—"
            ),
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет прибор с автоматической синхронизацией реквизитов из нормализованного типа."""
        if self.type_model:
            full_title = f"{self.type_model.equipment_name.name} {self.type_model.name}".strip()
            if not self.name or self.name == "Оборудование без наименования":
                self.name = full_title
            if not self.part_number and self.type_model.part_number:
                self.part_number = self.type_model.part_number
            if not self.equipment_type and self.type_model.equipment_name.category:
                self.equipment_type = self.type_model.equipment_name.category
        super().save(*args, **kwargs)

    @property
    def verifications(self):
        """Возвращает QuerySet записей журнала поверок (псевдоним для verification_records).

        Returns:
            QuerySet: Записи о поверках и калибровках прибора.
        """
        return self.verification_records.all()


class EquipmentVerificationRecord(models.Model):
    """Журнал проведенных поверок, калибровок и проверок состояния оборудования (ФАП-145, пп. 19, 20).

    Хранит полную историю метрологического контроля каждой единицы оборудования
    с фиксацией номеров записей в ФГИС «АРШИН», результатов оценки пригодности и электронных
    скан-копий свидетельств о поверке.

    Attributes:
        equipment (MaintenanceEquipment): Обслуживаемое оборудование / прибор.
        verification_type (str): Вид выполненного контроля (поверка, калибровка, проверка состояния).
        verification_date (date): Дата проведения поверки/калибровки.
        valid_until (Optional[date]): Срок окончания действия свидетельства.
        arshin_number (str): Номер записи в Федеральном информационном фонде ФГИС «АРШИН».
        organization (str): Наименование аккредитованной организации-поверителя.
        result_serviceable (bool): Признак пригодности к дальнейшему применению (годен / забракован).
        certificate_scan (FileField): Электронный скан свидетельства о поверке.
        notes (str): Служебные примечания и протокол поверки.
        created_at (datetime): Дата фиксации записи в журнале.
        created_by (DataBaseUser): Специалист, внесший запись.
    """

    class Meta:
        verbose_name = "Запись о поверке оборудования"
        verbose_name_plural = "Журнал поверок и калибровок оборудования"
        ordering = ("-verification_date",)
        indexes = [
            models.Index(fields=["equipment", "-verification_date"], name="idx_verif_eq_date"),
            models.Index(fields=["verification_date"], name="idx_verif_date"),
        ]

    equipment = models.ForeignKey(
        MaintenanceEquipment,
        verbose_name="Оборудование / прибор",
        on_delete=models.CASCADE,
        related_name="verification_records",
    )
    verification_type = models.CharField(
        verbose_name="Вид контроля",
        max_length=30,
        choices=EquipmentVerificationType.choices,
        default=EquipmentVerificationType.VERIFICATION,
    )
    verification_date = models.DateField(
        verbose_name="Дата проведения",
        help_text="Дата фактического выполнения поверки / калибровки",
    )
    valid_until = models.DateField(
        verbose_name="Действительно до",
        null=True,
        blank=True,
        help_text="Дата окончания действия свидетельства о поверке",
    )
    arshin_number = models.CharField(
        verbose_name="Номер во ФГИС «АРШИН» / Свидетельства",
        max_length=100,
        blank=True,
        default="",
        help_text="Номер свидетельства или записи в реестре ФГИС «АРШИН» (102-ФЗ)",
    )
    organization = models.CharField(
        verbose_name="Организация, проводившая поверку",
        max_length=255,
        blank=True,
        default="",
        help_text="Наименование аккредитованной метрологической службы / поверителя",
    )
    result_serviceable = models.BooleanField(
        verbose_name="Годен к применению",
        default=True,
        help_text="Флаг успешного прохождения поверки (если False — прибор забракован)",
    )
    certificate_scan = models.FileField(
        verbose_name="Скан свидетельства",
        upload_to="equipment_verifications/%Y/%m/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
        help_text="Скан свидетельства о поверке или извещения о непригодности",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Параметры погрешности, замечания поверителя",
    )
    created_at = models.DateTimeField(verbose_name="Дата внесения", auto_now_add=True)
    created_by = models.ForeignKey(
        DataBaseUser,
        verbose_name="Кто внес запись",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_verifications",
    )

    def __str__(self) -> str:
        status_txt = "Годен" if self.result_serviceable else "Забракован"
        return f"{self.get_verification_type_display()} от {self.verification_date:%d.%m.%Y} ({status_txt})"

    def clean(self) -> None:
        """Валидирует корректность дат поверки."""
        super().clean()
        if self.valid_until and self.verification_date:
            if self.valid_until <= self.verification_date:
                raise ValidationError({
                    "valid_until": "Срок действия поверки должен быть позже даты ее проведения."
                })

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет запись и актуализирует метрологические реквизиты связанного оборудования."""
        super().save(*args, **kwargs)
        if self.equipment:
            eq = self.equipment
            update_fields = ["updated_at"]
            if not self.result_serviceable:
                eq.operational_status = EquipmentOperationalStatus.QUARANTINED
                update_fields.append("operational_status")
            elif not eq.last_verification_date or self.verification_date >= eq.last_verification_date:
                eq.last_verification_date = self.verification_date
                update_fields.append("last_verification_date")
                if self.valid_until:
                    eq.next_verification_date = self.valid_until
                    update_fields.append("next_verification_date")
                if self.arshin_number:
                    eq.arshin_verification_number = self.arshin_number
                    update_fields.append("arshin_verification_number")
                if self.organization:
                    eq.verification_organization = self.organization
                    update_fields.append("verification_organization")
                if self.certificate_scan and not eq.certificate_scan:
                    eq.certificate_scan = self.certificate_scan
                    update_fields.append("certificate_scan")
                if eq.operational_status in (EquipmentOperationalStatus.QUARANTINED, EquipmentOperationalStatus.DEFECTIVE):
                    eq.operational_status = EquipmentOperationalStatus.SERVICEABLE
                    update_fields.append("operational_status")
            eq.save(update_fields=list(set(update_fields)))


class OutfitCardEquipmentUsage(models.Model):
    """Исторический снимок применения оборудования в карте-наряде (ФАП-145, пп. 19-25, 40).

    Фиксирует неизменяемый аудит-снимок состояния оборудования, инструмента и метрологических
    реквизитов на дату выполнения карты-наряда ТО ВС, защищая систему от искажения истории
    при последующих переповерках или списании инструмента.

    Attributes:
        outfit_card (OutfitCard): Карта-наряд, в которой использовано оборудование.
        equipment (MaintenanceEquipment): Использованная единица оборудования/инструмента.
        equipment_name (str): Наименование инструмента на момент выполнения ТО.
        part_number (str): Чертежный номер / модель (P/N) на момент ТО.
        serial_number (str): Серийный / заводской номер (S/N) на момент ТО.
        inventory_number (str): Инвентарный номер на момент ТО.
        marking_code (str): Маркировочный код инструмента (п. 23 ФАП-145).
        equipment_type (str): Категория оборудования на момент ТО.
        verification_type (str): Вид метрологического контроля на момент ТО.
        last_verification_date (Optional[date]): Дата последней поверки на момент ТО.
        next_verification_date (Optional[date]): Срок действия поверки на момент ТО.
        arshin_number (str): Номер записи ФГИС «АРШИН» на момент ТО.
        is_valid_at_usage (bool): Признак пригодности и отсутствия просрочки на момент ТО.
        validation_message (str): Результат проверки метрологической годности.
        attached_by (DataBaseUser): Специалист, привязавший инструмент к наряду.
        attached_at (datetime): Дата и время фиксации использования.
        notes (str): Примечания по использованию (напр. технологический этап).
    """

    class Meta:
        verbose_name = "Применение оборудования в наряде"
        verbose_name_plural = "Применение оборудования в картах-нарядах (ФАП-145)"
        ordering = ("outfit_card", "-attached_at")
        indexes = [
            models.Index(fields=["outfit_card"], name="idx_outfit_eq_card"),
            models.Index(fields=["equipment"], name="idx_outfit_eq_inst"),
        ]

    outfit_card = models.ForeignKey(
        OutfitCard,
        verbose_name="Карта-наряд",
        on_delete=models.CASCADE,
        related_name="used_equipment_records",
        help_text="Карта-наряд, при выполнении которой использовался прибор/инструмент",
    )
    equipment = models.ForeignKey(
        MaintenanceEquipment,
        verbose_name="Оборудование / прибор",
        on_delete=models.PROTECT,
        related_name="outfit_usages",
        help_text="Использованная единица оборудования из реестра",
    )
    equipment_name = models.CharField(
        verbose_name="Наименование (снимок)",
        max_length=255,
        blank=True,
        default="",
        help_text="Наименование инструмента на дату проведения ТО",
    )
    part_number = models.CharField(
        verbose_name="P/N (снимок)",
        max_length=100,
        blank=True,
        default="",
    )
    serial_number = models.CharField(
        verbose_name="S/N (снимок)",
        max_length=100,
        blank=True,
        default="",
    )
    inventory_number = models.CharField(
        verbose_name="Инв. № (снимок)",
        max_length=100,
        blank=True,
        default="",
    )
    marking_code = models.CharField(
        verbose_name="Код маркировки (снимок)",
        max_length=100,
        blank=True,
        default="",
    )
    equipment_type = models.CharField(
        verbose_name="Категория (снимок)",
        max_length=30,
        blank=True,
        default="",
    )
    verification_type = models.CharField(
        verbose_name="Вид контроля (снимок)",
        max_length=30,
        blank=True,
        default="",
    )
    last_verification_date = models.DateField(
        verbose_name="Дата поверки (снимок)",
        null=True,
        blank=True,
    )
    next_verification_date = models.DateField(
        verbose_name="Действительно до (снимок)",
        null=True,
        blank=True,
    )
    arshin_number = models.CharField(
        verbose_name="ФГИС АРШИН (снимок)",
        max_length=100,
        blank=True,
        default="",
    )
    is_valid_at_usage = models.BooleanField(
        verbose_name="Годен на момент применения",
        default=True,
        help_text="Флаг пригодности прибора на дату проведения ТО",
    )
    validation_message = models.CharField(
        verbose_name="Результат проверки метрологии",
        max_length=255,
        blank=True,
        default="",
    )
    attached_by = models.ForeignKey(
        DataBaseUser,
        verbose_name="Специалист, зафиксировавший применение",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attached_equipment_usages",
    )
    attached_at = models.DateTimeField(verbose_name="Дата и время фиксации", auto_now_add=True)
    notes = models.CharField(
        verbose_name="Примечания",
        max_length=255,
        blank=True,
        default="",
        help_text="Этап или технологическая операция применения инструмента",
    )

    def __str__(self) -> str:
        card_num = self.outfit_card.outfit_card_number or f"#{self.outfit_card_id}"
        return f"{self.equipment_name or self.equipment.name} в наряде {card_num}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Фиксирует неизменяемый снимок метрологических реквизитов оборудования на момент добавления в наряд."""
        if self.equipment and not self.equipment_name:
            eq = self.equipment
            self.equipment_name = eq.name
            self.part_number = eq.part_number
            self.serial_number = eq.serial_number
            self.inventory_number = eq.inventory_number
            self.marking_code = eq.marking_code
            self.equipment_type = eq.equipment_type
            self.verification_type = eq.verification_type
            self.last_verification_date = eq.last_verification_date
            self.next_verification_date = eq.next_verification_date
            self.arshin_number = eq.arshin_verification_number

            target_date = (
                self.outfit_card.outfit_card_date_end
                or self.outfit_card.outfit_card_date
                or timezone.now().date()
            ) if self.outfit_card else timezone.now().date()

            is_valid, reason = eq.can_be_used_for_maintenance(target_date)
            self.is_valid_at_usage = is_valid
            self.validation_message = reason

        super().save(*args, **kwargs)


class MaintenanceWorkEquipmentRequirement(models.Model):
    """Нормативная потребность регламентных (ПТО) и оперативных (ОТО) работ в оборудовании (ФАП-145).

    Формализует табель обязательного инструмента, СИ и КПА для выполнения конкретной формы ТО
    (периодической PeriodicWork либо оперативной OperationalWork) согласно требованиям РО и РЭ ВС.
    Определяет критичность обязательности (п. 40 ФАП-145), требуемый объем (quantity)
    и допустимые взаимозаменяемые типы-аналоги (substitutes).

    Attributes:
        periodic_work (Optional[PeriodicWork]): Форма периодического ТО (ПТО).
        operational_work (Optional[OperationalWork]): Форма оперативного обслуживания (ОТО).
        equipment_name (EquipmentName): Родовое наименование требуемого инструмента / СИ.
        required_type (Optional[EquipmentTypeModel]): Строго предписанный тип/модель СИ.
        allowed_substitutes (ManyToManyField): Разрешенные взамен аналоги других типов/марок.
        quantity (int): Требуемое количество единиц (шт.).
        is_mandatory (bool): Критичность инструмента для допуска к ТО.
        task_reference (str): Ссылка на пункт РО / регламента ТО / технологической карты.
        created_at (datetime): Дата создания требования.
        updated_at (datetime): Дата обновления.
    """

    class Meta:
        verbose_name = "Требование работы ТО к оборудованию"
        verbose_name_plural = "Табель оснащения работ ТО оборудованием (ФАП-145)"
        ordering = ("periodic_work", "operational_work", "equipment_name__name")
        constraints = [
            models.UniqueConstraint(
                fields=["periodic_work", "equipment_name", "required_type"],
                condition=models.Q(periodic_work__isnull=False),
                name="uq_req_periodic_work_name_type",
            ),
            models.UniqueConstraint(
                fields=["operational_work", "equipment_name", "required_type"],
                condition=models.Q(operational_work__isnull=False),
                name="uq_req_operational_work_name_type",
            ),
        ]

    periodic_work = models.ForeignKey(
        PeriodicWork,
        verbose_name="Форма периодического ТО (ПТО)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_requirements",
        help_text="Регламентная форма ТО (напр. 'Ф-1', '100 ч', '300 ч')",
    )
    operational_work = models.ForeignKey(
        OperationalWork,
        verbose_name="Форма оперативного ТО (ОТО)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_requirements",
        help_text="Оперативное обслуживание (напр. 'Встречное', 'Предполетное')",
    )
    equipment_name = models.ForeignKey(
        EquipmentName,
        verbose_name="Наименование оборудования / СИ",
        on_delete=models.PROTECT,
        related_name="work_requirements",
        help_text="Обобщенное наименование прибора (напр. 'Ареометр', 'Манометр')",
    )
    required_type = models.ForeignKey(
        EquipmentTypeModel,
        verbose_name="Требуемый тип / модель (если строго)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="required_in_works",
        help_text="Если пусто — допускается любой исправный тип данного наименования",
    )
    allowed_substitutes = models.ManyToManyField(
        EquipmentTypeModel,
        blank=True,
        related_name="substitute_for_requirements",
        verbose_name="Допустимые взаимозаменяемые аналоги (типы)",
        help_text="Список утвержденных типов СИ, которые разрешено применять взамен основного",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="Требуемое количество (шт.)",
        default=1,
        help_text="Минимальное необходимое количество исправных единиц на МПД",
    )
    is_mandatory = models.BooleanField(
        verbose_name="Критически обязательный инструмент",
        default=True,
        help_text="Без данного инструмента выполнение ТО и выпуск ВС категорически запрещены (п. 40 ФАП-145)",
    )
    task_reference = models.CharField(
        verbose_name="Пункт РО / техкарты",
        max_length=150,
        blank=True,
        default="",
        help_text="Ссылка на пункт регламента ТО или технологической карты РО",
    )
    created_at = models.DateTimeField(verbose_name="Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата обновления", auto_now=True)

    def __str__(self) -> str:
        work_name = str(self.periodic_work or self.operational_work or "Без работы")
        type_str = f" [{self.required_type.name}]" if self.required_type else ""
        return f"{work_name} -> {self.equipment_name.name}{type_str} ({self.quantity} шт.)"

    def clean(self) -> None:
        """Валидирует взаимоисключаемость привязки к форме ТО и соответствие типа наименованию."""
        super().clean()
        from django.core.exceptions import ValidationError

        if not bool(self.periodic_work) ^ bool(self.operational_work):
            raise ValidationError(
                "Требование должно быть привязано либо к форме ПТО (PeriodicWork), "
                "либо к форме ОТО (OperationalWork) — строго к одной из них."
            )
        if self.required_type and self.required_type.equipment_name_id != self.equipment_name_id:
            raise ValidationError(
                f"Указанный тип '{self.required_type}' не относится к наименованию '{self.equipment_name}'."
            )


class EquipmentTransferStatus(models.TextChoices):
    """Статусы жизненного цикла заявки на меж-МПД перемещение инструмента."""

    DRAFT = "draft", "Черновик"
    REQUESTED = "requested", "Запрошено (ожидает отправки)"
    IN_TRANSIT = "in_transit", "В пути (отправлено с МПД-донора)"
    DELIVERED = "delivered", "Доставлено на целевое МПД"
    RETURNED = "returned", "Возвращено на МПД базирования"
    CANCELED = "canceled", "Отменено"


class EquipmentTransferRequest(models.Model):
    """Заявка на меж-МПД перемещение оборудования и СИ под выполнение ТО ВС (ФАП-145).

    Фиксирует электронную заявку на доставку приборов/инструментов с ближайших МПД-доноров
    на целевое МПД для обеспечения комплектности формы ТО. Отслеживает маршрут,
    требуемую дату доставки, трек-номер накладной и статус логистики.

    Attributes:
        equipment (MaintenanceEquipment): Перемещаемая единица оборудования/СИ.
        from_mpd (PlaceProductionActivity): МПД отправления (донор).
        to_mpd (PlaceProductionActivity): Целевое МПД (получатель).
        target_periodic_work (Optional[PeriodicWork]): Форма ПТО, под которую запрошен инструмент.
        target_operational_work (Optional[OperationalWork]): Форма ОТО, под которую запрошен инструмент.
        required_date (date): Дата, к которой прибор должен прибыть на целевое МПД.
        status (str): Статус перемещения (EquipmentTransferStatus).
        tracking_number (str): Номер транспортной накладной / рейса / отправления.
        notes (str): Служебные примечания и указания логисту.
        created_by (DataBaseUser): Инициатор заявки (инженер ПТО / ведущий инженер МПД).
        created_at (datetime): Дата и время создания заявки.
        updated_at (datetime): Дата и время последнего обновления.
    """

    class Meta:
        verbose_name = "Заявка на перемещение оборудования"
        verbose_name_plural = "Реестр перемещений оборудования между МПД (ФАП-145)"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"], name="idx_eq_transfer_status"),
            models.Index(fields=["required_date"], name="idx_eq_transfer_req_date"),
        ]

    equipment = models.ForeignKey(
        MaintenanceEquipment,
        verbose_name="Оборудование / прибор",
        on_delete=models.PROTECT,
        related_name="transfer_requests",
        help_text="Конкретная единица прибора/инструмента из реестра ТО",
    )
    from_mpd = models.ForeignKey(
        PlaceProductionActivity,
        verbose_name="МПД отправления (донор)",
        on_delete=models.PROTECT,
        related_name="equipment_transfers_out",
        help_text="Точка базирования, откуда перемещается прибор",
    )
    to_mpd = models.ForeignKey(
        PlaceProductionActivity,
        verbose_name="Целевое МПД (получатель)",
        on_delete=models.PROTECT,
        related_name="equipment_transfers_in",
        help_text="МПД, где запланировано выполнение технического обслуживания",
    )
    target_periodic_work = models.ForeignKey(
        PeriodicWork,
        verbose_name="Форма ПТО",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_transfers",
        help_text="Планируемая периодическая работа ТО ВС",
    )
    target_operational_work = models.ForeignKey(
        OperationalWork,
        verbose_name="Форма ОТО",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_transfers",
        help_text="Планируемая оперативная работа ТО ВС",
    )
    required_date = models.DateField(
        verbose_name="Требуемая дата доставки",
        help_text="Планируемая дата начала ТО, к которой инструмент должен быть на месте",
    )
    status = models.CharField(
        verbose_name="Статус логистики",
        max_length=20,
        choices=EquipmentTransferStatus.choices,
        default=EquipmentTransferStatus.REQUESTED,
        db_index=True,
    )
    tracking_number = models.CharField(
        verbose_name="Номер накладной / трек",
        max_length=100,
        blank=True,
        default="",
        help_text="Номер экспресс-накладной, борт рейса или сопроводительного документа",
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True,
        default="",
        help_text="Служебные пометки (условия транспортировки, габариты и т.д.)",
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        verbose_name="Инициатор",
        on_delete=models.PROTECT,
        related_name="created_equipment_transfers",
        help_text="Специалист, оформивший заявку на меж-МПД доставку",
    )
    created_at = models.DateTimeField(verbose_name="Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата обновления", auto_now=True)

    def __str__(self) -> str:
        from_name = self.from_mpd.short_name or self.from_mpd.name
        to_name = self.to_mpd.short_name or self.to_mpd.name
        return f"Заявка #{self.pk}: {self.equipment.name} ({from_name} -> {to_name}) [{self.get_status_display()}]"


class CompanyMaintenanceCertificate(models.Model):
    """Сертификат организации по техническому обслуживанию ВС (ФАП-145).

    Модель ведет нормативный учет выданных авиакомпании «БАРКОЛ» сертификатов
    организации по ТО (ФАП-145 / Приказ Минтранса РФ № 367), отслеживает сроки действия
    и формирует двуязычные реквизиты для подстановки в Свидетельства о выполнении ТО (CRS).

    Attributes:
        certificate_number (str): Официальный номер сертификата организации (например, '145-25-108').
        issue_date (date): Дата выдачи сертификата.
        valid_until (Optional[date]): Срок действия (None, если бессрочный).
        organization_name_ru (str): Официальное наименование держателя на русском языке.
        organization_name_en (str): Официальное наименование держателя на английском языке.
        is_active (bool): Признак действующего основного сертификата компании.
        scan_file (FileField): Электронный скан-образ сертификата.
        notes (str): Служебные примечания и область действия.
        created_at (datetime): Дата регистрации записи.
        updated_at (datetime): Дата последнего изменения.
    """

    class Meta:
        verbose_name = "Сертификат организации по ТО (ФАП-145)"
        verbose_name_plural = "Сертификаты организации по ТО (ФАП-145)"
        ordering = ("-issue_date",)

    certificate_number = models.CharField(
        verbose_name="Номер сертификата организации",
        max_length=100,
        default="145-25-108",
        help_text="Официальный номер сертификата по ФАП-145 (например, '145-25-108')",
    )
    issue_date = models.DateField(
        verbose_name="Дата выдачи",
        help_text="Дата решения уполномоченного органа о выдаче сертификата",
    )
    valid_until = models.DateField(
        verbose_name="Действителен до",
        null=True,
        blank=True,
        help_text="Оставьте пустым, если сертификат бессрочный",
    )
    organization_name_ru = models.CharField(
        verbose_name="Наименование организации (RU)",
        max_length=255,
        default="ООО АВИАКОМПАНИЯ «БАРКОЛ»",
        help_text="Официальное наименование организации на русском языке",
    )
    organization_name_en = models.CharField(
        verbose_name="Наименование организации (EN)",
        max_length=255,
        default="AVIACOMPANY «BARKOL» ltd",
        help_text="Официальное наименование организации на английском языке",
    )
    is_active = models.BooleanField(
        verbose_name="Действующий основной сертификат",
        default=True,
        db_index=True,
        help_text="Использовать данный сертификат по умолчанию для новых свидетельств CRS",
    )
    scan_file = models.FileField(
        verbose_name="Скан-копия сертификата",
        upload_to="company_certificates/",
        null=True,
        blank=True,
        help_text="Электронная скан-копия бланка сертификата с приложениями",
    )
    notes = models.TextField(
        verbose_name="Примечания / Область действия",
        blank=True,
        default="",
        help_text="Особые отметки, разрешенные рейтинги и типы ВС",
    )
    created_at = models.DateTimeField(verbose_name="Дата добавления", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата изменения", auto_now=True)

    def __str__(self) -> str:
        return f"Сертификат № {self.certificate_number} от {self.issue_date:%d.%m.%Y}"

    def get_bilingual_certificate_text(self) -> str:
        """Формирует нормативную двуязычную строку реквизитов сертификата для графы 2 CRS.

        Пример: 'от «25» декабря 2025 № 145-25-108 / № 145-25-108 Issued «25» December 2025'

        Returns:
            str: Двуязычная строка реквизитов сертификата.
        """
        if not self.issue_date:
            return f"№ {self.certificate_number}"

        ru_months = (
            "", "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        )
        en_months = (
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
        ru_m = ru_months[self.issue_date.month] if 1 <= self.issue_date.month <= 12 else ""
        en_m = en_months[self.issue_date.month] if 1 <= self.issue_date.month <= 12 else ""

        return (
            f"от «{self.issue_date.day:02d}» {ru_m} {self.issue_date.year} № {self.certificate_number} / "
            f"№ {self.certificate_number} Issued «{self.issue_date.day:02d}» {en_m} {self.issue_date.year}"
        )

    def get_bilingual_organization(self) -> str:
        """Возвращает нормативное двуязычное наименование организации.

        Returns:
            str: Строка вида 'ООО АВИАКОМПАНИЯ «БАРКОЛ»  / AVIACOMPANY «BARKOL» ltd'.
        """
        return f"{self.organization_name_ru}  / {self.organization_name_en}"


class MaintenanceReleaseCertificate(models.Model):
    """Свидетельство о выполнении технического обслуживания ВС (Журнал свидетельств о ТО ВС).

    Официальный журнал регистрации выданных Свидетельств о выполнении ТО ВС (CRS)
    в соответствии с Федеральными авиационными правилами (ФАП-145 / Приказ Минтранса РФ № 367).
    Свидетельство оформляется на основании карты-наряда (OutfitCard). Номера свидетельств
    имеют независимую годовую сквозную нумерацию без ведущих нулей в формате '<seq>/<YY>'.
    При выдаче свидетельства реквизиты подтверждающего персонала и номер CRS автоматически
    синхронизируются с соответствующей картой-нарядом.

    Attributes:
        number_seq (int): Порядковый номер свидетельства в пределах календарного года (1, 2, ...).
        year (int): Календарный год регистрации (например, 2026).
        certificate_number (str): Официальный номер свидетельства вида '1/26', '2/26'.
        outfit_card (OutfitCard): Основание выдачи (карта-наряд).
        maintenance_date (date): Дата выполнения ТО ВС.
        aircraft_type (str): Тип обслуживаемого воздушного судна.
        tail_number (str): Регистрационный (бортовой) номер ВС.
        factory_number (str): Заводской (серийный) номер ВС.
        operating_hours (str): Наработка ВС на момент проведения ТО (например, '693 ч. 53 м.').
        maintenance_work_scope (str): Вид ТО и объем выполненных работ.
        certifying_staff (DataBaseUser): Специалист подтверждающего персонала, выпустивший ВС.
        certifying_staff_name (str): ФИО подтверждающего персонала.
        certifying_staff_license (str): Номер свидетельства специалиста по ТО ВС.
        issue_date (date): Дата выдачи и подписания Свидетельства CRS.
        signature_stamp (str): Отметка об электронной подписи (ПЭП) или статус подписи.
        scan_file (FileField): Электронный скан подписанного свидетельства.
        created_at (datetime): Дата создания записи в журнале.
        updated_at (datetime): Дата последнего обновления записи.
    """

    class Meta:
        verbose_name = "Свидетельство о ТО ВС (CRS)"
        verbose_name_plural = "Журнал свидетельств о ТО ВС (CRS)"
        ordering = ("-year", "-number_seq")
        unique_together = [("year", "number_seq")]
        indexes = [
            models.Index(fields=["year", "number_seq"], name="idx_crs_year_seq"),
            models.Index(fields=["certificate_number"], name="idx_crs_cert_num"),
            models.Index(fields=["outfit_card"], name="idx_crs_outfit_card"),
        ]

    number_seq = models.PositiveIntegerField(
        verbose_name="№ п/п (в году)",
        db_index=True,
        blank=True,
        default=0,
        help_text="Порядковый номер свидетельства в текущем году (без ведущих нулей)",
    )
    year = models.PositiveIntegerField(
        verbose_name="Год",
        db_index=True,
        blank=True,
        default=0,
        help_text="Календарный год оформления свидетельства",
    )
    certificate_number = models.CharField(
        verbose_name="Номер свидетельства",
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        help_text="Уникальный номер свидетельства в формате '<seq>/<YY>' (например, 1/26)",
    )
    outfit_card = models.ForeignKey(
        OutfitCard,
        verbose_name="Карта-наряд (основание)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crs_certificates",
        help_text="Карта-наряд, на основании которой выписано свидетельство о ТО",
    )
    maintenance_date = models.DateField(
        verbose_name="Дата выполнения ТО ВС",
        blank=True,
        null=True,
        help_text="Фактическая дата выполнения работ по ТО",
    )
    aircraft_type = models.CharField(
        verbose_name="Тип ВС",
        max_length=100,
        blank=True,
        default="",
        help_text="Тип воздушного судна (например, Ми-8Т, Ан-2)",
    )
    tail_number = models.CharField(
        verbose_name="Рег. № ВС (бортовой)",
        max_length=50,
        blank=True,
        default="",
        help_text="Государственный регистрационный номер ВС",
    )
    factory_number = models.CharField(
        verbose_name="Зав. № ВС",
        max_length=50,
        blank=True,
        default="",
        help_text="Заводской (серийный) номер планера ВС",
    )
    operating_hours = models.CharField(
        verbose_name="Наработка ВС",
        max_length=100,
        blank=True,
        default="",
        help_text="Наработка ВС на момент ТО (например, 693 ч. 53 м.)",
    )
    maintenance_work_scope = models.TextField(
        verbose_name="Вид ТО (выполненные работы)",
        blank=True,
        default="",
        help_text="Перечень регламентов, оперативных и дополнительных работ",
    )
    certifying_staff = models.ForeignKey(
        DataBaseUser,
        verbose_name="Подтверждающий персонал",
        on_delete=models.PROTECT,
        related_name="crs_release_certificates",
        help_text="Специалист подтверждающего персонала, выпустивший ВС",
    )
    certifying_staff_name = models.CharField(
        verbose_name="ФИО специалиста",
        max_length=255,
        blank=True,
        default="",
        help_text="Фамилия, имя и отчество специалиста",
    )
    certifying_staff_license = models.CharField(
        verbose_name="Свидетельство специалиста",
        max_length=100,
        blank=True,
        default="",
        help_text="Номер бессрочного свидетельства специалиста по ТО ВС",
    )
    issue_date = models.DateField(
        verbose_name="Дата свидетельства",
        default=timezone.now,
        help_text="Дата подписания и выдачи Свидетельства CRS",
    )
    signature_stamp = models.CharField(
        verbose_name="Подпись / ПЭП",
        max_length=255,
        blank=True,
        default="",
        help_text="Отметка об электронной подписи или штамп подтверждающего персонала",
    )
    scan_file = models.FileField(
        verbose_name="Скан свидетельства",
        upload_to="crs_certificates/",
        null=True,
        blank=True,
        help_text="Электронная скан-копия оформленного свидетельства",
    )
    created_at = models.DateTimeField(verbose_name="Дата оформления", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Дата изменения", auto_now=True)

    def __str__(self) -> str:
        return f"Свидетельство о ТО № {self.certificate_number} от {self.issue_date:%d.%m.%Y}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет свидетельство, автоматически назначая порядковый номер и обновляя карту-наряд."""
        if not self.issue_date:
            self.issue_date = timezone.now().date()
        if not self.year:
            self.year = self.issue_date.year

        if self.outfit_card:
            from hrdepartment_app.services.crs_document_service import (
                build_work_scope_text,
                format_hours_minutes,
            )
            if not self.maintenance_date:
                self.maintenance_date = (
                    self.outfit_card.outfit_card_date_end
                    or self.outfit_card.outfit_card_date
                    or timezone.now().date()
                )
            if not self.aircraft_type:
                air_board = self.outfit_card.air_board
                self.aircraft_type = (
                    air_board.type_property.type_property
                    if air_board and air_board.type_property
                    else "ВС"
                )
            if not self.tail_number:
                air_board = self.outfit_card.air_board
                self.tail_number = air_board.registration_number if air_board else "—"
            if not self.factory_number and self.outfit_card.air_board:
                self.factory_number = self.outfit_card.air_board.factory_number or ""
            if not self.operating_hours:
                self.operating_hours = format_hours_minutes(self.outfit_card.flight_hours)
            if not self.maintenance_work_scope:
                self.maintenance_work_scope = build_work_scope_text(self.outfit_card)
            if not self.certifying_staff and self.outfit_card.certifying_staff:
                self.certifying_staff = self.outfit_card.certifying_staff

        if not self.maintenance_date:
            self.maintenance_date = self.issue_date

        if not self.number_seq:
            max_seq = (
                MaintenanceReleaseCertificate.objects.filter(year=self.year)
                .aggregate(models.Max("number_seq"))["number_seq__max"]
                or 0
            )
            self.number_seq = max_seq + 1

        if not self.certificate_number:
            yy = str(self.year)[-2:]
            self.certificate_number = f"{self.number_seq}/{yy}"

        if self.certifying_staff:
            if not self.certifying_staff_name:
                self.certifying_staff_name = self.certifying_staff.get_full_name()
            if not self.certifying_staff_license and getattr(self.certifying_staff, "maintenance_staff_certificate", ""):
                self.certifying_staff_license = self.certifying_staff.maintenance_staff_certificate

        if not self.signature_stamp:
            self.signature_stamp = "[Оформлено в СЭД БАРКОЛ]"

        super().save(*args, **kwargs)

        # Синхронизируем обратную связь в карту-наряд по требованию п. 2
        if self.outfit_card:
            needs_update = False
            update_fields = ["updated_at"]
            if self.outfit_card.crs_number != self.certificate_number:
                self.outfit_card.crs_number = self.certificate_number
                update_fields.append("crs_number")
                needs_update = True
            if self.certifying_staff and self.outfit_card.certifying_staff != self.certifying_staff:
                self.outfit_card.certifying_staff = self.certifying_staff
                update_fields.append("certifying_staff")
                needs_update = True
            if needs_update:
                self.outfit_card.save(update_fields=update_fields)

    @classmethod
    def create_from_outfit_card(
        cls,
        outfit_card: OutfitCard,
        certifying_staff: Optional[DataBaseUser] = None,
        issue_date: Optional[date] = None,
    ) -> "MaintenanceReleaseCertificate":
        """Фабричный метод создания Свидетельства о ТО (CRS) на основании карты-наряда.

        Извлекает нормативные реквизиты борта, выполненных регламентов, наработки планера
        и специалиста, регистрирует свидетельство в журнале и обновляет карту-наряд.

        Args:
            outfit_card (OutfitCard): Карта-наряд на выполнение ТО.
            certifying_staff (Optional[DataBaseUser]): Подтверждающий специалист (если не указан, берется из наряда).
            issue_date (Optional[date]): Дата оформления (по умолчанию дата окончания наряда или сегодня).

        Returns:
            MaintenanceReleaseCertificate: Созданный и зарегистрированный экземпляр свидетельства.
        """
        from hrdepartment_app.services.crs_document_service import (
            build_work_scope_text,
            format_hours_minutes,
        )

        staff = certifying_staff or outfit_card.certifying_staff
        if not staff:
            raise ValidationError("Для оформления Свидетельства CRS необходимо указать подтверждающий персонал.")

        m_date = outfit_card.outfit_card_date_end or outfit_card.outfit_card_date or timezone.now().date()
        iss_date = issue_date or m_date
        air_board = outfit_card.air_board
        ac_type = air_board.type_property.type_property if air_board and air_board.type_property else "ВС"
        tail_no = air_board.registration_number if air_board else "—"
        fact_no = air_board.factory_number if air_board and air_board.factory_number else "—"
        op_hours = format_hours_minutes(outfit_card.flight_hours)
        scope = build_work_scope_text(outfit_card)

        cert = cls(
            outfit_card=outfit_card,
            maintenance_date=m_date,
            aircraft_type=ac_type,
            tail_number=tail_no,
            factory_number=fact_no,
            operating_hours=op_hours,
            maintenance_work_scope=scope,
            certifying_staff=staff,
            certifying_staff_name=staff.get_full_name(),
            certifying_staff_license=getattr(staff, "maintenance_staff_certificate", ""),
            issue_date=iss_date,
            signature_stamp="[Оформлено в СЭД БАРКОЛ]",
        )
        cert.save()
        return cert

    def get_absolute_url(self) -> str:
        """Возвращает URL для скачивания или просмотра свидетельства."""
        return reverse("hrdepartment_app:crs_certificate_download", kwargs={"pk": self.pk})

    def get_data(self) -> Dict[str, Any]:
        """Формирует сериализованные данные для таблицы журнала DataTables.

        Returns:
            Dict[str, Any]: Словарь с атрибутами для 10 граф журнала свидетельств о ТО ВС.
        """
        download_url = reverse("hrdepartment_app:crs_certificate_download", kwargs={"pk": self.pk})
        outfit_url = (
            reverse("hrdepartment_app:outfit_card_detail", kwargs={"pk": self.outfit_card.pk})
            if self.outfit_card
            else ""
        )
        return {
            "pk": self.pk,
            "number_seq": self.number_seq,
            "maintenance_date": f"{self.maintenance_date:%d.%m.%Y} г." if self.maintenance_date else "—",
            "aircraft_type": self.aircraft_type,
            "tail_number": self.tail_number,
            "factory_number": self.factory_number or "—",
            "operating_hours": self.operating_hours or "—",
            "maintenance_work_scope": self.maintenance_work_scope,
            "certificate_number": self.certificate_number,
            "certifying_staff_name": self.certifying_staff_name or (format_name_initials(self.certifying_staff.title) if self.certifying_staff else "—"),
            "certifying_staff_license": self.certifying_staff_license or "—",
            "issue_date": f"{self.issue_date:%d.%m.%Y} г." if self.issue_date else "—",
            "signature_stamp": self.signature_stamp or "Подписано",
            "download_url": download_url,
            "outfit_url": outfit_url,
            "outfit_number": self.outfit_card.outfit_card_number if self.outfit_card else "—",
        }


class ReportCard(models.Model):
    """
    Атрибуты:
    _________
    report_card_day: Дата;
    rec_no = Номер записи;
    employee = Сотрудник;
    start_time = Время прихода;
    end_time = Время ухода';
    record_type = Тип записи;
    manual_input = Ручной ввод;
    reason_adjustment = Причина ручной корректировки;
    doc_ref_key = Уникальный номер документа;
    current_intervals = Текущий интервал;
    timesheet = Табель учета рабочего времени;
    lunch_time = Время обеда;
    flight_hours = Летные часы;
    operational_work = Оперативные работы;
    periodic_work = Периодические работы;
    air_board = Воздушный борт;
    additional_work = Дополнительные работы;
    other_work = Другие работы;
    sign_report_card = Признак табеля рабочего времени;
    """

    type_of_report = [
        ("1", "Явка"),
        ("2", "Ежегодный"),
        ("3", "Дополнительный ежегодный отпуск"),
        ("4", "Отпуск за свой счет"),
        ("5", "Дополнительный учебный отпуск (оплачиваемый)"),
        ("6", "Отпуск по уходу за ребенком"),
        ("7", "Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС"),
        ("8", "Отпуск по беременности и родам"),
        ("9", "Отпуск без оплаты согласно ТК РФ"),
        ("10", "Дополнительный отпуск"),
        ("11", "Дополнительный оплачиваемый отпуск пострадавшим в "),
        ("12", "Основной"),
        ("13", "Ручной ввод"),
        ("14", "Служебная поездка"),
        ("15", "Командировка"),
        ("16", "Больничный"),
        ("17", "Мед осмотр"),
        ("18", "График отпусков"),
        ("19", "Отпуск на санаторно курортное лечение"),
        ("20", "Отгул"),
    ]

    class Meta:
        verbose_name = "Рабочее время"
        verbose_name_plural = "Табель учета"
        ordering = ("-report_card_day",)

    report_card_day = models.DateField(verbose_name="Дата", null=True, blank=True)
    rec_no = models.IntegerField(verbose_name="Номер записи", default=0, blank=True)
    employee = models.ForeignKey(
        DataBaseUser, verbose_name="Сотрудник", on_delete=models.SET_NULL, null=True, blank=True
    )
    start_time = models.TimeField(verbose_name="Время прихода", null=True, blank=True)
    end_time = models.TimeField(verbose_name="Время ухода", null=True, blank=True)
    record_type = models.CharField(
        verbose_name="Тип записи",
        max_length=100,
        choices=type_of_report,
        default="",
        blank=True,
    )
    manual_input = models.BooleanField(verbose_name="Ручной ввод", default=False)
    reason_adjustment = models.TextField(
        verbose_name="Причина ручной корректировки", blank=True
    )
    doc_ref_key = models.CharField(
        verbose_name="Уникальный номер документа", max_length=37, default="", blank=True
    )
    current_intervals = models.BooleanField(
        verbose_name="Текущий интервал", default=True
    )
    confirmed = models.BooleanField(verbose_name="Подтвержденная СП", default=False)
    place_report_card = models.ManyToManyField(
        PlaceProductionActivity, verbose_name="МПД", related_name="place_report_card", blank=True
    )
    timesheet = models.ForeignKey(
        TimeSheet, verbose_name="Табель учета рабочего времени", on_delete=models.CASCADE, related_name="report_cards",
        null=True, blank=True
    )
    lunch_time = models.IntegerField(verbose_name="Время обеда", null=True, blank=True)
    flight_hours = models.IntegerField(verbose_name="Летные часы", null=True, blank=True)
    outfit_card = models.ManyToManyField(
        OutfitCard, verbose_name="Оперативные работы", related_name="outfit_card_report_card", blank=True
    )
    additional_work = models.CharField(verbose_name="Дополнительные работы", max_length=200, default="", blank=True)

    sign_report_card = models.BooleanField(verbose_name="Признак табеля рабочего времени", default=False)

    def get_data(self):
        """
        Получает данные из экземпляра ReportCard.

        :return: словарь, содержащий следующие данные:
            - "pk": первичный ключ экземпляра ReportCard.
            - "employee": форматированные инициалы имени сотрудника.
            - "report_card_day": день табеля в формате "ДД.ММ.ГГГГ"
            - "start_time": время начала в формате "ЧЧ:ММ"
            - "end_time": время окончания в формате "ЧЧ:ММ"
            - "reason_adjustment": причина корректировки.
            - "record_type": отображение типа записи.
        """
        return {
            "pk": self.pk,
            "employee": format_name_initials(self.employee.title),
            "report_card_day": f"{self.report_card_day:%d.%m.%Y} г.",  # .strftime(''),
            "start_time": f"{self.start_time:%H:%M}",  # .strftime(''),
            "end_time": f"{self.end_time:%H:%M}",  # .strftime(''),
            "reason_adjustment": self.reason_adjustment,
            "record_type": self.get_record_type_display(),
        }

    def __str__(self):
        return f"{self.employee}: {self.report_card_day} : {self.record_type}"


class PreHolidayDay(models.Model):
    """
    Обозначает предпраздничный день.

    Атрибуты:
        preholiday_day (DateField): дата предпраздничного дня.
        work_time (TimeField): рабочее время предпраздничного дня.
    """

    class Meta:
        verbose_name = "Предпраздничный день"
        verbose_name_plural = "Предпраздничные дни"
        ordering = ["-preholiday_day"]

    preholiday_day = models.DateField(verbose_name="Дата", null=True, blank=True)
    work_time = models.TimeField(verbose_name="Рабочее время", null=True, blank=True)

    def __str__(self):
        return str(self.preholiday_day)


class WeekendDay(models.Model):
    """
    Праздничные дни и выходные дни в связи с праздником
    Атрибуты:
    weekend_day - Дата, description - Описание, weekend_type - Тип дня (1 - Праздник, 2 - Выходной)
    """

    type_of_weekend = [
        ("1", "Праздник"),
        ("2", "Выходной"),
    ]

    class Meta:
        verbose_name = "Праздничный день"
        verbose_name_plural = "Праздничные дни"
        ordering = ["-weekend_day"]

    weekend_day = models.DateField(verbose_name="Дата", null=True, blank=True)
    description = models.CharField(
        verbose_name="Описание", max_length=200, default="", blank=True
    )
    weekend_type = models.CharField(
        verbose_name="Тип дня",
        max_length=8,
        choices=type_of_weekend,
        blank=True,
        null=True,
    )

    def __str__(self):
        return str(self.weekend_day)


def get_norm_time_at_custom_day(day, trigger=False, type_of_day=0):
    """
    Подсчет количества рабочих часов в указанном дне
    Если переменная trigger=False, то возвращается количество рабочих часов в указанном дне, иначе - возвращается тип
    дня (П - Праздник, В - Выходной, НБ - Не было на работе)
    Если передается переменная type_of_day, то если она равна 14 и 15, то возвращается обычный рабочий день
    """

    # Проверка на праздничный день
    if WeekendDay.objects.filter(weekend_day=day).exists():
        if trigger:
            return 'Праздничный день'
        return WORK_DAY_TIME if type_of_day in [14, 15] else 0

    # Проверка на предпраздничный день
    preholiday_day = PreHolidayDay.objects.filter(preholiday_day=day).first()
    if preholiday_day:
        preholiday_result = preholiday_day.work_time.hour * 3600 + preholiday_day.work_time.minute * 60
        if trigger:
            return 'Не было на работе'
        return -preholiday_result if type_of_day == 100 else preholiday_result

    # Проверка на обычный рабочий день
    if day.weekday() < 5:  # Понедельник - Пятница
        weekday_result = SHORT_DAY_TIME if day.weekday() == 4 else WORK_DAY_TIME
        if trigger:
            return 'Не было на работе'
        return -weekday_result if type_of_day == 100 else weekday_result

    # Выходной день
    if trigger:
        return 'Выходной'
    return WORK_DAY_TIME if type_of_day in [14, 15] else 0


class ProductionCalendar(models.Model):
    """
    Месяц в производственном календаре.
    Атрибуты:
    ____________
    calendar_month - Месяц, number_calendar_days - Количество календарных дней,
    number_working_days - Количество рабочих дней,
    number_days_off_and_holidays - Количество выходных и празднечных дней, description - Описание
    Методы:
    ____________
    get_friday_count - Подсчитывает количество пятниц в месяце
    get_norm_time - Подсчет количества рабочих часов в месяце
    """

    class Meta:
        verbose_name = "Месяц в производственом календаре"
        verbose_name_plural = "Производственный календарь"
        ordering = ["-calendar_month"]

    calendar_month = models.DateField(verbose_name="Месяц", null=True, blank=True)
    number_calendar_days = models.PositiveIntegerField(
        verbose_name="Количество календарных дней", default=0, null=True, blank=True
    )
    number_working_days = models.PositiveIntegerField(
        verbose_name="Количество рабочих дней", default=0, null=True, blank=True
    )
    number_days_off_and_holidays = models.PositiveIntegerField(
        verbose_name="Количество выходных и празднечных дней",
        default=0,
        null=True,
        blank=True,
    )
    description = models.CharField(
        verbose_name="Описание", max_length=200, default="", blank=True
    )

    def get_friday_count(self):
        """
        Подсчитывает количество пятниц в месяце
        :return: количество пятниц
        """
        first_day = self.calendar_month + relativedelta(day=1)
        last_day = self.calendar_month + relativedelta(day=31)
        friday = 0
        for item in range(first_day.day, last_day.day + 1):
            date_obj = first_day + datetime.timedelta(days=item - 1)
            if date_obj.weekday() == 4:
                if WeekendDay.objects.filter(weekend_day=date_obj).count() == 0:
                    friday += 1
        return friday

    def get_norm_time_on_day(self):
        last_day = datetime.datetime.today() - datetime.timedelta(days=1)
        first_day = self.calendar_month.replace(day=1)
        # Инициализация переменных
        total_hours = 0
        friday_count = 0
        preholiday_time = 0
        # Получаем все дни в диапазоне
        days_in_month = list(rrule.rrule(DAILY, dtstart=first_day, until=last_day))
        # Получаем предпраздничные и выходные дни из базы данных за один запрос
        preholiday_days = {
            item.preholiday_day: item.work_time
            for item in PreHolidayDay.objects.filter(preholiday_day__in=days_in_month)
        }
        weekend_days = {
            item.weekend_day
            for item in WeekendDay.objects.filter(weekend_day__in=days_in_month)
        }
        # Итерация по дням месяца
        for day in days_in_month:
            day_date = day.date()

            if day_date in weekend_days:
                continue  # Пропускаем выходные и праздничные дни

            if day_date in preholiday_days:
                # Обработка предпраздничных дней
                work_time = preholiday_days[day_date]
                preholiday_time += work_time.hour + work_time.minute / 60
            else:
                # Обработка обычных рабочих дней
                if day.weekday() < 5:  # Понедельник-пятница
                    total_hours += 8.5
                    if day.weekday() == 4:  # Пятница
                        friday_count += 1

        # Корректировка нормы времени
        norm_time = total_hours - friday_count + preholiday_time
        return norm_time

    def get_norm_time_at_day(self):
        """
        Подсчет количества рабочих часов в день
        :return: количество рабочих часов в день
        """
        first_day = self.calendar_month + relativedelta(day=1)
        last_day = self.calendar_month + relativedelta(day=datetime.datetime.today().day)
        last_day = last_day - datetime.timedelta(days=1)
        preholiday_time, day_count, preholiday_day_count, friday_count = 0, 0, 0, 0
        preholiday_day_list = [item.preholiday_day for item in PreHolidayDay.objects.filter(
            preholiday_day__in=list(rrule.rrule(rrule.DAILY, dtstart=first_day, until=last_day)))]
        weekday_day_list = [item.weekend_day for item in WeekendDay.objects.filter(
            weekend_day__in=list(rrule.rrule(rrule.DAILY, dtstart=first_day, until=last_day)))]

        for days in rrule.rrule(rrule.DAILY, dtstart=first_day, until=last_day):
            if datetime.date(days.year, days.month, days.day) in preholiday_day_list:
                preholiday_day_count += 1

                day = PreHolidayDay.objects.get(preholiday_day=days)
                if day.preholiday_day.weekday() == 4:
                    friday_count += 1
                    preholiday_time += day.work_time.hour + 1 + day.work_time.minute / 60
                else:
                    preholiday_time += day.work_time.hour + day.work_time.minute / 60
            elif datetime.date(days.year, days.month, days.day) in weekday_day_list:
                pass
            else:
                if days.weekday() == 4:
                    friday_count += 1
                    day_count += 1
                elif days.weekday() < 4:
                    day_count += 1

        return (day_count * 8) + (day_count / 2) - friday_count - (preholiday_day_count * 8.5 - preholiday_time)

    def get_norm_time(self):
        """
        Подсчет количества рабочих часов в месяце
        :return: количество рабочих часов в месяце
        """
        first_day = self.calendar_month + relativedelta(day=1)
        last_day = self.calendar_month + relativedelta(day=31)
        preholiday_time = 0
        preholiday_day_count = 0

        preholiday_day = PreHolidayDay.objects.filter(
            preholiday_day__in=list(rrule.rrule(rrule.DAILY, dtstart=first_day, until=last_day)))

        for item in preholiday_day:
            preholiday_day_count += 1
            if item.preholiday_day.weekday() == 4:
                preholiday_time += item.work_time.hour + 1 + item.work_time.minute / 60
            else:
                preholiday_time += item.work_time.hour + item.work_time.minute / 60
        norm_time = (self.number_working_days * 8) + (self.number_working_days / 2) - self.get_friday_count() - (
                preholiday_day_count * 8.5 - preholiday_time)

        return norm_time

    def __str__(self):
        return str(self.calendar_month)


def check_day(date: datetime.date, time_start: datetime.time, time_end: datetime.time, days_type=0):
    """
    Функция определяющая время начала и окончания рабочего дня на заданную дату
    :param date: дата
    :param time_start: время начала
    :param time_end: время окончания
    :return: три значения: время начала, время окончания и тип дня (Р - рабочий, В - выходной, П - праздник)
    """
    type_of_day = ""
    weekend = WeekendDay.objects.filter(weekend_day=date.date()).exists()
    preholiday = PreHolidayDay.objects.filter(preholiday_day=date.date()).exists()
    check_time_end = time_end
    check_time_start = time_start
    if not weekend:
        if date.weekday() in [0, 1, 2, 3]:
            if not preholiday:
                check_time_end = datetime.timedelta(
                    hours=time_end.hour, minutes=time_end.minute
                )
            else:
                preholiday_time = PreHolidayDay.objects.get(preholiday_day=date.date())
                check_time_end = datetime.timedelta(
                    hours=time_start.hour, minutes=time_start.minute
                ) + datetime.timedelta(
                    hours=preholiday_time.work_time.hour,
                    minutes=preholiday_time.work_time.minute,
                )
            type_of_day = "Р"
        elif date.weekday() == 4:
            if not preholiday:
                check_time_end = datetime.timedelta(
                    hours=time_end.hour, minutes=time_end.minute
                ) - datetime.timedelta(hours=1)
            else:
                preholiday_time = PreHolidayDay.objects.get(preholiday_day=date.date())
                check_time_end = datetime.timedelta(
                    hours=time_start.hour, minutes=time_start.minute
                ) + datetime.timedelta(
                    hours=preholiday_time.work_time.hour,
                    minutes=preholiday_time.work_time.minute,
                )
            type_of_day = "Р"
        else:
            if days_type in [14, 15]:
                check_time_end = datetime.timedelta(
                    hours=time_end.hour, minutes=time_end.minute
                )
            else:
                check_time_end = datetime.timedelta(hours=0, minutes=0)
                check_time_start = datetime.timedelta(hours=0, minutes=0)
            type_of_day = "В"
    else:
        if days_type in [14, 15]:
            print(type_of_day, "Сработало")
            check_time_end = datetime.timedelta(
                hours=time_end.hour, minutes=time_end.minute
            )
        else:
            check_time_end = datetime.timedelta(hours=0, minutes=0)
            check_time_start = datetime.timedelta(hours=0, minutes=0)
        type_of_day = "П"

    return (
        timedelta_to_time(check_time_start),
        timedelta_to_time(check_time_end),
        type_of_day,
    )


class TypesUserworktime(models.Model):
    """
    url = /odata/standard.odata/Catalog_ВидыИспользованияРабочегоВремени?$format=application/json;odata=nometadata
    """

    class Meta:
        verbose_name = "Вид использования рабочего времени"
        verbose_name_plural = "Виды использования рабочего времени"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )  # поле в 1с: Ref_Key
    description = models.CharField(
        verbose_name="Наименование", max_length=150, default=""
    )  # поле в 1с: Description
    letter_code = models.CharField(
        verbose_name="Буквенный код", max_length=5, default=""
    )  # поле в 1с: БуквенныйКод
    active = models.BooleanField(
        verbose_name="Используется", default=False
    )  # поле в 1с: БуквенныйКод

    def __str__(self):
        return self.description


class Instructions(Documents):
    class Meta:
        verbose_name = "Инструкция"
        verbose_name_plural = "Инструкции"

    prefix_attr_doc_file = "INS"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "INS"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=ins_directory_path, blank=True
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=ins_directory_path_scan, blank=True
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="instruction_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="instruction_document_division",
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )
    document_form = models.ManyToManyField(
        DocumentForm, verbose_name="Бланки документов"
    )

    def get_data(self):
        """
        Return a dictionary representing the data of the object.

        :return: A dictionary with the following keys:
                 - "pk": The primary key of the object.
                 - "document_name": The name of the document.
                 - "document_number": The number of the document.
                 - "document_date": The formatted date of the document ("dd.mm.yyyy г.").
                 - "document_division": The storage location division of the document (converted to string).
                 - "document_order": The document order (converted to string).
                 - "actuality": The actuality of the document ("Да" if true, "Нет" if false).
                 - "executor": The formatted name initials of the executor.

        """
        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "document_division": str(self.storage_location_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if self.actuality else "Нет",
            "executor": format_name_initials(self.executor),
        }

    # def get_absolute_url(self):
    #     return reverse('hrdepartment_app:instructions_list')

    def __str__(self):
        """
        Returns the string representation of the object.

        :return: The string representation of the object.
        :rtype: str
        """
        return self.document_name


class Provisions(Documents):
    class Meta:
        verbose_name = "Положение"
        verbose_name_plural = "Положения"
        ordering = ['-document_date']

    prefix_attr_doc_file = "PRV"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "PRV"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=prv_directory_path, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['doc', 'docx']),
        ]
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=prv_directory_path_scan, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="provisions_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="provisions_document_division",
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )
    document_form = models.ManyToManyField(
        DocumentForm, verbose_name="Бланки документов"
    )

    def get_data(self):
        today = datetime.date.today()
        get_date = self.validity_period_end is None or self.validity_period_end >= today
        get_actual = not Provisions.objects.filter(parent_document=self.pk).exists()
        is_actual = get_date and get_actual

        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г." if self.document_date else "",
            "document_division": str(self.storage_location_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if is_actual else "Нет",
            "executor": format_name_initials(self.executor),
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:provisions_list")

    def __str__(self):
        return f"{self.document_name} № {self.document_number} от {self.document_date.strftime('%d.%m.%Y')}"

    def get_scan_file_url(self):
        if not self.scan_file:
            return ""
        return f"{self.scan_file.url}?v={int(time.time())}"


class Briefings(Documents):
    class Meta:
        verbose_name = "Инструктаж"
        verbose_name_plural = "Инструктажи"
        ordering = ['-document_date']

    prefix_attr_doc_file = "BRF"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "BRF"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=brf_directory_path_doc, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['doc', 'docx']),
        ]
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=brf_directory_path_scan, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="briefings_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="briefings_document_division",
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )
    document_form = models.ManyToManyField(
        DocumentForm, verbose_name="Бланки документов"
    )

    def get_data(self):
        today = datetime.date.today()
        get_date = self.validity_period_end is None or self.validity_period_end >= today
        get_actual = not Briefings.objects.filter(parent_document=self.pk).exists()
        is_actual = get_date and get_actual

        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г." if self.document_date else "",
            "document_division": str(self.storage_location_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if is_actual else "Нет",
            "executor": format_name_initials(self.executor),
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:briefings_list")

    def __str__(self):
        return f"{self.document_name} № {self.document_number} от {self.document_date.strftime('%d.%m.%Y')}"


class Operational(Documents):
    class Meta:
        verbose_name = "Нормативный акт"
        verbose_name_plural = "Нормативные акты"
        ordering = ['-document_date']

    access = None
    employee = None
    previous_document = None

    prefix_attr_doc_file = "OPR"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "OPR"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    document_date = models.DateField(verbose_name="Дата документа", default=datetime.datetime.now, null=True,
                                     blank=True)
    document_number = models.CharField(verbose_name="Номер документа", max_length=18, default="", null=True, blank=True)

    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=opr_directory_path_scan, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="operational_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="operational_document_division",
    )

    def get_data(self):
        today = datetime.date.today()
        get_date = self.validity_period_end is None or self.validity_period_end >= today
        get_actual = not Operational.objects.filter(parent_document=self.pk).exists()
        is_actual = get_date and get_actual

        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г." if self.document_date else "",
            "document_division": str(self.storage_location_division),
            "actuality": "Да" if is_actual else "Нет",
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:operational_list")

    def __str__(self):
        return f"{self.document_name} № {self.document_number} от {self.document_date.strftime('%d.%m.%Y')}"


class GuidanceDocuments(Documents):
    class Meta:
        verbose_name = "Руководящий документ"
        verbose_name_plural = "Руководящие документы"

    prefix_attr_doc_file = "GDC"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "GDC"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=gdc_directory_path, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['doc', 'docx']),
        ]
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=gdc_directory_path_scan, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="guidance_documents_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="guidance_documents_document_division",
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )

    def get_data(self):
        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "document_division": str(self.storage_location_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if self.actuality else "Нет",
            "executor": format_name_initials(self.executor),
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:guidance_documents_list")

    def __str__(self):
        return self.document_name


class DocumentAcknowledgment(models.Model):
    """
    Модель для отслеживания подтверждения ознакомления пользователей с документами.

    Позволяет фиксировать факт ознакомления сотрудников с различными типами документов,
    такими как приказы, положения, должностные инструкции и другие. Использует
    GenericForeignKey для связи с разными моделями документов.

    Атрибуты:
        document_type (ForeignKey): Тип документа (ContentType), с которым связано подтверждение.
            Ограничено моделями: 'documentsorder', 'creatingteam', 'documentsjobdescription',
            'provisions', 'guidancedocuments', 'companyevent'.
        document_id (PositiveIntegerField): Идентификатор экземпляра связанного документа.
        document (GenericForeignKey): Обобщённая ссылка на сам документ, объединяющая
            document_type и document_id.
        user (ForeignKey): Пользователь (сотрудник), который подтвердил ознакомление.
            Связь с моделью DataBaseUser. При удалении пользователя удаляются и все его
            подтверждения.
        acknowledgment_date (DateTimeField): Дата и время подтверждения ознакомления.
            Устанавливается автоматически при создании записи.

    Meta:
        verbose_name (str): Человекочитаемое название модели в единственном числе.
        verbose_name_plural (str): Человекочитаемое название модели во множественном числе.

    Методы:
        __str__(self) -> str:
            Возвращает строковое представление объекта в формате:
            "ИмяПользователя ознакомился с документом 'НазваниеДокумента'".
    """

    class Meta:
        verbose_name = "Подтверждение документа"
        verbose_name_plural = "Подтверждения документов"

    document_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={'model__in': (
            'documentsorder', 'creatingteam', 'documentsjobdescription', 'provisions', 'guidancedocuments',
            'companyevent')}
    )
    document_id = models.PositiveIntegerField()
    document = GenericForeignKey('document_type', 'document_id')
    user = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE, related_name='document_acknowledgments')
    acknowledgment_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ознакомился с документом '{self.document}'"


class DataBaseUserEvent(models.Model):
    class Meta:
        verbose_name = 'Отметка'
        verbose_name_plural = 'Отметки'
        indexes = [
            models.Index(fields=['person', 'date_marks']),
            models.Index(fields=['checked']),
        ]

    person = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE, verbose_name='Сотрудник')
    date_marks = models.DateField(verbose_name='Дата отметки', null=True, blank=True)
    place = models.ForeignKey(PlaceProductionActivity, on_delete=models.SET_NULL, null=True, verbose_name='Место')
    checked = models.BooleanField(default=False, verbose_name='Проверено')
    road = models.BooleanField(default=False, verbose_name='В дороге')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    def __str__(self):
        return f"{self.person} - {self.date_marks} - {self.place}"

    def get_absolute_url(self):
        return reverse("hrdepartment_app:users_events_list")

    def get_data(self):
        return {
            "pk": self.pk,
            "date_marks": f"{self.date_marks:%d.%m.%Y} г.",
            "place": str(self.place),
            "checked": "Да" if self.checked else "Нет",
            "road": "Да" if self.road else "Нет",
            "created_at": f"{self.created_at:%d.%m.%Y} г.",
            "updated_at": f"{self.updated_at:%d.%m.%Y} г.",
            "executor": format_name_initials(self.person),
        }


class LaborProtection(Documents):
    class Meta:
        verbose_name = "Процедура по охране труда"
        verbose_name_plural = "Процедуры по охране труда"
        ordering = ['-document_date']

    prefix_attr_doc_file = "LBP"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "LBP"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа",
        upload_to=lbp_directory_path_doc,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['doc', 'docx']),
        ]
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=lbp_directory_path_scan, blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
        ]
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="labor_protection_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="labor_protection_document_division",
    )
    document_order = models.ForeignKey(
        DocumentsOrder, verbose_name="Приказ", on_delete=models.SET_NULL, null=True
    )
    document_form = models.ManyToManyField(
        DocumentForm, verbose_name="Бланки документов"
    )

    def get_data(self):
        today = datetime.date.today()
        get_date = self.validity_period_end is None or self.validity_period_end >= today
        get_actual = not LaborProtection.objects.filter(parent_document=self.pk).exists()
        is_actual = get_date and get_actual

        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г." if self.document_date else "",
            "document_division": str(self.storage_location_division),
            "document_order": str(self.document_order),
            "actuality": "Да" if is_actual else "Нет",
            "executor": format_name_initials(self.executor),
        }

    def get_absolute_url(self):
        return reverse("hrdepartment_app:labor_protection_list")

    def __str__(self):
        return f"{self.document_name} № {self.document_number} от {self.document_date.strftime('%d.%m.%Y')}"


class LaborProtectionInstructions(Documents):
    class Meta:
        verbose_name = "Инструкция по ТО ВС"
        verbose_name_plural = "Инструкции по ТО ВС"

    prefix_attr_doc_file = "LPI"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "LPI"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    doc_file = models.FileField(
        verbose_name="Файл документа", upload_to=lpi_directory_path, blank=True
    )
    scan_file = models.FileField(
        verbose_name="Скан документа", upload_to=lpi_directory_path_scan, blank=True
    )
    storage_location_division = models.ForeignKey(
        Division,
        verbose_name="Подразделение где хранится оригинал",
        on_delete=models.SET_NULL,
        null=True,
        related_name="lp_instruction_location_division",
    )
    document_division = models.ManyToManyField(
        Division,
        verbose_name="Подразделения",
        related_name="lp_instruction_document_division",
    )
    employee = None
    applying_for_job = None

    def get_data(self):
        """
        Return a dictionary representing the data of the object.

        :return: A dictionary with the following keys:
                 - "pk": The primary key of the object.
                 - "document_name": The name of the document.
                 - "document_number": The number of the document.
                 - "document_date": The formatted date of the document ("dd.mm.yyyy г.").
                 - "document_division": The storage location division of the document (converted to string).
                 - "document_order": The document order (converted to string).
                 - "actuality": The actuality of the document ("Да" if true, "Нет" if false).
                 - "executor": The formatted name initials of the executor.

        """
        return {
            "pk": self.pk,
            "document_name": self.document_name,
            "document_number": self.document_number,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "document_division": str(self.storage_location_division),
            "actuality": "Да" if self.actuality else "Нет",
            "executor": format_name_initials(self.executor),
        }

    def get_absolute_url(self):
        return reverse('hrdepartment_app:lpi_list')

    def __str__(self):
        """
        Returns the string representation of the object.

        :return: The string representation of the object.
        :rtype: str
        """
        return self.document_name


# Регистрируем модели и их file-поля
FILE_FIELDS_REGISTRY = {
    Operational: ['doc_file', 'scan_file'],
    LaborProtection: ['doc_file', 'scan_file'],
    GuidanceDocuments: ['doc_file', 'scan_file'],
    Provisions: ['doc_file', 'scan_file'],
    Briefings: ['doc_file', 'scan_file'],
    Instructions: ['doc_file', 'scan_file'],
    DocumentsJobDescription: ['doc_file', 'scan_file'],
}


@receiver(pre_save)
def delete_old_file_on_change(sender, instance, **kwargs):
    # Проверяем, зарегистрирована ли модель в реестре
    if sender not in FILE_FIELDS_REGISTRY:
        return

    if not instance.pk:
        return  # Новый объект — нечего удалять

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    for field in FILE_FIELDS_REGISTRY[sender]:
        old_file = getattr(old_instance, field)
        new_file = getattr(instance, field)

        if old_file and old_file.name != getattr(new_file, 'name', None):
            try:
                if os.path.isfile(old_file.path):
                    os.remove(old_file.path)
            except Exception as e:
                logger.warning(f"Ошибка удаления старого файла в поле '{field}' для {sender.__name__}: {e}")


# ToDo: Блок кода для автоматического удаления старых файлов
# @receiver(pre_save)
# def auto_delete_old_files(sender, instance, **kwargs):
#     if not instance.pk:
#         return
#
#     try:
#         old_instance = sender.objects.get(pk=instance.pk)
#     except sender.DoesNotExist:
#         return
#
#     for field in sender._meta.get_fields():
#         if field.get_internal_type() == 'FileField':
#             field_name = field.name
#             old_file = getattr(old_instance, field_name)
#             new_file = getattr(instance, field_name)
#
#             if old_file and old_file.name != getattr(new_file, 'name', None):
#                 try:
#                     if os.path.isfile(old_file.path):
#                         os.remove(old_file.path)
#                 except Exception as e:
#                     logger.warning(
#                         f"Ошибка удаления файла {old_file.path} ({field_name}) для {sender.__name__}: {e}"
#                     )

class TrainingUnit(models.Model):
    class Meta:
        verbose_name = "Модуль"
        verbose_name_plural = "Модули"
        unique_together = (
            ('program_units', 'unit_name_short'),
        )

    unit_name_short = models.CharField(
        verbose_name="Краткое наименование",
        max_length=30,
        default=''
    )
    unit_name = models.CharField(
        verbose_name="Полное наименование",
        max_length=350
    )

    program_units = models.ForeignKey(
        'hrdepartment_app.TrainingProgram',
        verbose_name="Программа обучения",
        on_delete=models.CASCADE,
    )

    @property
    def full_unit_name(self):
        """Объединяет краткое и полное наименование модуля"""
        if self.unit_name_short and self.unit_name:
            return f"{self.unit_name_short} - {self.unit_name}"
        elif self.unit_name_short:
            return self.unit_name_short
        elif self.unit_name:
            return self.unit_name
        return ""

    def __str__(self):
        return f'{self.full_unit_name}'


class TrainingProgram(models.Model):
    class Meta:
        verbose_name = "Программа обучения"
        verbose_name_plural = "Программы обучения"

    program_name = models.CharField(
        verbose_name="Наименование",
        max_length=300,
    )

    counteragent_name = models.ForeignKey(
        'customers_app.Counteragent',
        verbose_name="Наименование АУЦ",
        on_delete=models.CASCADE,
        limit_choices_to={'educational_organization': True}
    )

    def __str__(self):
        return f'{self.program_name}'


class EducationFormChoices(models.TextChoices):
    FULL_TIME = 'full_time', 'очная'
    PART_TIME = 'part_time', 'заочная'
    DISTANCE = 'distance', 'дистанционно'


class StudentAgreement(models.Model):
    class Meta:
        verbose_name = "Ученический договор"
        verbose_name_plural = "Ученические договоры"
        ordering = ['-student_agreement_date__year', '-student_agreement_number']

    # Реквизиты договоров
    student_agreement_number = models.CharField(
        verbose_name="№ ученического договора с работником",
        max_length=100,
    )
    student_agreement_date = models.DateField(
        verbose_name="Дата ученического договора"
    )

    counteragent_contract = models.ForeignKey(
        'contracts_app.Contract',
        verbose_name="Договор",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_counteragent_contract',
        help_text="Выберите договор из системы"
    )

    # Обучение
    training_center_name = models.ForeignKey(
        'customers_app.Counteragent',
        verbose_name="Наименование АУЦ",
        on_delete=models.CASCADE,
        limit_choices_to={'educational_organization': True}
    )
    training_program = models.ForeignKey(
        'hrdepartment_app.TrainingProgram',
        verbose_name="Программа обучения",
        on_delete=models.CASCADE
    )

    training_unit = models.ManyToManyField(
        'hrdepartment_app.TrainingUnit',
        verbose_name="Модули",
        blank=True
    )

    training_place = models.CharField(
        verbose_name="Место оказания услуг",
        max_length=255
    )

    form_education = models.CharField(
        max_length=20,
        choices=EducationFormChoices.choices,
        verbose_name="Форма обучения",
        default=EducationFormChoices.FULL_TIME,
    )

    remotely = models.BooleanField(
        verbose_name='С отрывом от работы',
        default=True
    )

    academic_hours = models.IntegerField(
        verbose_name="академических часа",
        default=0
    )

    # Обучающийся
    full_name = models.ForeignKey(
        'customers_app.DataBaseUser',
        verbose_name="Ф.И.О.",
        on_delete=models.CASCADE
    )

    # Период обучения
    training_start_date = models.DateField(
        verbose_name="Дата начала обучения"
    )
    training_end_date = models.DateField(
        verbose_name="Дата окончания обучения"
    )

    # Финансы и обязательства
    training_cost = models.DecimalField(
        verbose_name="Сумма обучения, руб.",
        max_digits=10,
        decimal_places=2
    )
    work_period_years = models.PositiveSmallIntegerField(
        verbose_name="Срок отработки (года)", default=0
    )

    work_period_month = models.PositiveSmallIntegerField(
        verbose_name="Срок отработки (месяцы)", default=0
    )

    # Прочее
    note = models.TextField(
        "Примечание",
        blank=True
    )

    signed = models.BooleanField('Подписан', default=False)

    def get_remaining_work_period(self):
        """
        Вычисляет оставшееся время отработки в формате "X лет Y месяцев"
        """
        if not self.training_end_date or not (self.work_period_years or self.work_period_month):
            return "Не указано"

        # Дата окончания отработки = дата договора + количество лет отработки
        end_work_date = self.training_end_date + relativedelta(years=self.work_period_years, months=self.work_period_month)

        # Текущая дата
        current_date = datetime.datetime.now().date()

        # Если дата окончания уже прошла
        if current_date >= end_work_date:
            return "Отработка завершена"

        # Вычисляем разницу
        remaining = relativedelta(end_work_date, current_date)

        # Форматируем результат
        years = remaining.years
        months = remaining.months

        if years == 0 and months == 0:
            return "Менее месяца"

        result_parts = []
        if years > 0:
            result_parts.append(f"{years} {self._pluralize(years, 'год', 'года', 'лет')}")
        if months > 0:
            result_parts.append(f"{months} {self._pluralize(months, 'месяц', 'месяца', 'месяцев')}")

        return " ".join(result_parts) if result_parts else "Менее месяца"

    def _pluralize(self, count, one, few, many):
        """
        Вспомогательный метод для склонения существительных
        """
        if count % 10 == 1 and count % 100 != 11:
            return one
        elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
            return few
        else:
            return many

    def get_data(self):
        # Попытка извлечь число из строкового номера договора для сортировки
        number_sort = 0
        if self.student_agreement_number:
            # Извлекаем все цифры из строки, например "Д-100/2024" -> 1002024
            digits = re.sub(r'\D', '', self.student_agreement_number)
            if digits:
                number_sort = int(digits)
        return {
            "pk": self.pk,
            "document_number": self.student_agreement_number,
            # Поле для корректной сортировки чисел (даже если номер строковый)
            "document_number_sort": number_sort,
            "document_date": f"{self.student_agreement_date:%d.%m.%Y} г.",
            # Поле для корректной сортировки дат (ISO формат)
            "document_date_sort": self.student_agreement_date.isoformat(),
            "full_name": format_name_initials(self.full_name),
            "training_center_name": self.training_center_name.short_name,
            "counteragent_contract": self.counteragent_contract.contract_number if self.counteragent_contract else "",
            "active": self.full_name.is_active,
            "group": self.full_name.user_work_profile.job.get_type_of_job_display(),
            "remaining_work_period": self.get_remaining_work_period(),  # Новое поле
            "work_period_years": self.work_period_years,  # Исходное значение для справки
            "training_end_date": f"{self.training_end_date:%d.%m.%Y}",  # Дата окончания обучения
            "training_cost": float(self.training_cost),  # Сумма обучения
            "signed": self.signed,
        }

    def __str__(self):
        return f"{self.student_agreement_number} — {self.full_name}"

    def clean(self):
        # Вызываем родительский clean
        super().clean()

        # Проверяем, заполнено ли поле
        if self.training_center_name:
            if not self.training_center_name.educational_organization:
                raise ValidationError({
                    'training_center_name': 'Можно выбрать только Образовательную организацию.'
                })

    # В модели StudentAgreement
    def calculate_debt_by_days(self, dismissal_date):
        """
        Рассчитывает задолженность по дням для исключения ошибок округления.

        Логика:
        - До окончания обучения: 100% стоимости
        - После: пропорционально оставшимся дням отработки
        """
        from dateutil.relativedelta import relativedelta
        from decimal import Decimal, ROUND_HALF_UP

        work_off_end_date = self.training_end_date + relativedelta(
            years=self.work_period_years, months=self.work_period_month
        )
        total_days = (work_off_end_date - self.training_end_date).days

        if dismissal_date <= self.training_end_date:
            # Полная стоимость, если увольнение до окончания обучения
            return self.training_cost, total_days

        if dismissal_date >= work_off_end_date:
            # Отработка завершена
            return Decimal('0'), 0

        # Пропорциональный расчёт по дням
        remaining_days = (work_off_end_date - dismissal_date).days
        daily_cost = self.training_cost / total_days
        debt = (daily_cost * remaining_days).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        return debt, remaining_days


class PowerOfAttorney(models.Model):
    """
    Модель для учета выданных доверенностей.
    """

    class Meta:
        verbose_name = "Доверенность"
        verbose_name_plural = "Доверенности"
        ordering = ['-issue_date', '-number']
        constraints = [
            models.UniqueConstraint(
                fields=['number', 'issue_date'],
                name='unique_poa_number_per_date'
            )
        ]

    prefix_attr_document = "POA"
    prefix_file_doc_file = "DRAFT"
    prefix_ext_doc_file = "docx"
    prefix_attr_scan_file = "POA"
    prefix_file_scan_file = "SCAN"
    prefix_ext_scan_file = "pdf"

    number = models.CharField(
        verbose_name="Номер доверенности",
        max_length=50,
        help_text="Уникальный номер доверенности"
    )
    issue_date = models.DateField(
        verbose_name="Дата выдачи",
        default=datetime.date.today
    )
    expiry_date = models.DateField(
        verbose_name="Дата окончания действия"
    )

    initiator_name_user = models.ForeignKey(
        'customers_app.DataBaseUser',
        verbose_name="ФИО инициатора",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiator_poas'
    )

    grantee_name_user = models.ForeignKey(
        'customers_app.DataBaseUser',
        verbose_name="ФИО поверенного",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grantee_poas'
    )

    organization = models.ForeignKey(
        'customers_app.Counteragent',
        verbose_name="Организация/Орган",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organization_poas'
    )

    cancellation_date = models.DateField(
        verbose_name="Дата отмены",
        null=True,
        blank=True,
        help_text="Заполняется в случае досрочного отзыва"
    )

    scan_file = models.FileField(
        verbose_name="Скан документа",
        upload_to=poa_directory_path_scan,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])]
    )

    # Отметка о получении
    is_received = models.BooleanField(
        verbose_name="Получена подпись",
        default=False
    )
    received_at = models.DateTimeField(
        verbose_name="Дата и время получения",
        null=True,
        blank=True
    )
    received_by_user = models.ForeignKey(
        'customers_app.DataBaseUser',
        verbose_name="Кто зафиксировал получение",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_poas'
    )

    executor = models.ForeignKey(
        'customers_app.DataBaseUser',
        verbose_name="Исполнитель",
        on_delete=models.SET_NULL,
        null=True,
        related_name="poa_executor"
    )
    date_entry = models.DateField(
        verbose_name="Дата ввода информации", auto_now_add=True
    )

    def __str__(self):
        return f"Доверенность №{self.number} от {self.issue_date}"

    def get_absolute_url(self):
        return reverse('hrdepartment_app:poa_detail', kwargs={'pk': self.pk})

    def get_data(self):

        return {
            "pk": self.pk,
            "number": self.number,
            "issue_date": self.issue_date, #f"{self.issue_date:%d.%m.%Y} г.",
            "expiry_date": self.expiry_date, #f"{self.expiry_date:%d.%m.%Y} г.",
            "grantee_name_user": format_name_initials(self.grantee_name_user.title),
            "organization": str(self.organization.short_name) if self.organization else "",
            "is_received": self.is_received,
            "cancellation_date": self.cancellation_date,

        }

    def clean(self):
        super().clean()
        if self.number and self.issue_date:
            exists = PowerOfAttorney.objects.filter(
                number=self.number,
                issue_date__year=self.issue_date.year
            ).exclude(pk=self.pk).exists()
            if exists:
                raise ValidationError({
                    'number': f"Доверенность с номером {self.number} уже существует в {self.issue_date.year} году."
                })

# Сигналы сработают при сохранении или удалении любой из этих моделей
# Сигналы сработают при сохранении или удалении любой из этих моделей
@receiver([post_save, post_delete], sender=ApprovalOficialMemoProcess)
@receiver([post_save, post_delete], sender=CreatingTeam)
def invalidate_memo_notifications(sender, instance, **kwargs):
    """
    При изменении приказов увеличиваем глобальную версию кэша уведомлений.
    Это мгновенно сбросит кэш для всех пользователей.
    """
    try:
        # Увеличиваем версию на 1
        cache.incr("memo_notif_version")
    except ValueError:
        # Если ключа еще нет в кэше, cache.incr выдаст ошибку. Создаем его.
        cache.set("memo_notif_version", 2, timeout=None)

