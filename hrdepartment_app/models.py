import datetime
import pathlib
import uuid

import dateutil.relativedelta
from dateutil import rrule
from dateutil.relativedelta import relativedelta
from django.contrib.contenttypes.fields import GenericRelation
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field
from docxtpl import DocxTemplate
from loguru import logger

from administration_app.utils import ending_day, FIO_format, timedelta_to_time
from customers_app.models import DataBaseUser, Counteragent, HarmfulWorkingConditions, Division, Job, AccessLevel, \
    HistoryChange
from djangoProject.settings import BASE_DIR, EMAIL_HOST_USER, MEDIA_URL

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# Create your models here.
def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'hr/medical/{filename}'


def jds_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'docs/JDS/{instance.document_division.code}/{filename}'


def ord_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    year = instance.document_date
    return f'docs/ORD/{year.year}/{filename}'


class Documents(models.Model):
    class Meta:
        abstract = True

    ref_key = models.UUIDField(verbose_name='Уникальный номер', default=uuid.uuid4, unique=True)
    # type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
    #                                      null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True)
    executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                 null=True, related_name='%(app_label)s_%(class)s_executor')
    document_date = models.DateField(verbose_name='Дата документа', default=datetime.datetime.now)
    document_name = models.CharField(verbose_name='Наименование документа', max_length=200, default='')
    document_number = models.CharField(verbose_name='Номер документа', max_length=10, default='')

    access = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к документу', on_delete=models.SET_NULL,
                               null=True, default=5)
    employee = models.ManyToManyField(DataBaseUser, verbose_name='Ответственное лицо', blank=True,
                                      related_name='%(app_label)s_%(class)s_employee')
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)
    validity_period_start = models.DateField(verbose_name='Документ действует с', blank=True, null=True)
    validity_period_end = models.DateField(verbose_name='Документ действует по', blank=True, null=True)
    actuality = models.BooleanField(verbose_name='Актуальность', default=False)
    previous_document = models.URLField(verbose_name='Предшествующий документ', blank=True)

    def __str__(self):
        return f'№ {self.document_number} от {self.document_date.strftime("%d.%m.%Y")}'


class Purpose(models.Model):
    class Meta:
        verbose_name = "Цель служебной записки"
        verbose_name_plural = "Цели служебной записки"

    title = models.CharField(verbose_name='Наименование', max_length=300)

    def __str__(self):
        return self.title

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:purpose_list')

    def get_data(self):
        return {
            'pk': self.pk,
            'title': self.title,
        }


class MedicalOrganisation(models.Model):
    class Meta:
        verbose_name = 'Медицинская организация'
        verbose_name_plural = 'Медицинскик организации'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    description = models.CharField(verbose_name='Наименование', max_length=200, default='')
    ogrn = models.CharField(verbose_name='ОГРН', max_length=13, default='')
    address = models.CharField(verbose_name='Адрес', max_length=250, default='')
    email = models.CharField(verbose_name='Email', max_length=150, default='')
    phone = models.CharField(verbose_name='Телефон', max_length=150, default='')

    def __str__(self):
        return self.description

    def get_title(self):
        return self.description

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:medicalorg_list')

    def get_data(self):
        return {
            'pk': self.pk,
            'description': self.description,
            'ogrn': self.ogrn,
            'address': self.address,
        }


def Med(obj_model, filepath, filename_pmo, filename_po, request):
    inspection_type = [
        ('1', 'Предварительный'),
        ('2', 'Периодический'),
        ('3', 'Внеплановый')
    ]
    if obj_model.person.user_work_profile.job.type_of_job == '1':
        doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med.docx'))
    else:
        doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med2.docx'))
    doc2 = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med3.docx'))
    if obj_model.person.gender == 'male':
        gender = 'муж.'
    else:
        gender = 'жен.'
    try:
        harmful = list()
        for items in obj_model.harmful.iterator():
            harmful.append(f'{items.code}: {items.name}')
        if obj_model.person.user_work_profile.divisions.address:
            division = str(obj_model.person.user_work_profile.divisions)
            div_address = f'Адрес обособленного подразделения места производственной деятельности {division[6:]} ' \
                          f'(далее – {obj_model.person.user_work_profile.divisions}): ' \
                          f'{obj_model.person.user_work_profile.divisions.address}.'
        else:
            div_address = ''
        context = {'gender': gender,
                   'title': next(x[1] for x in inspection_type if x[0] == obj_model.type_inspection).lower(),
                   'number': obj_model.number,
                   'birthday': obj_model.person.birthday.strftime("%d.%m.%Y"),
                   'division': obj_model.person.user_work_profile.divisions,
                   'job': obj_model.person.user_work_profile.job,
                   'FIO': obj_model.person,
                   'snils': obj_model.person.user_profile.snils,
                   'oms': obj_model.person.user_profile.oms,
                   'status': obj_model.get_working_status_display(),
                   'harmful': ", ".join(harmful),
                   'organisation': obj_model.organisation,
                   'ogrn': obj_model.organisation.ogrn,
                   'email': obj_model.organisation.email,
                   'tel': obj_model.organisation.phone,
                   'address': obj_model.organisation.address,
                   'div_address': div_address,
                   }
        context2 = {'gender': gender,
                    'number': obj_model.number,
                    'birthday': obj_model.person.birthday.strftime("%d.%m.%Y"),
                    'division': obj_model.person.user_work_profile.divisions,
                    'job': obj_model.person.user_work_profile.job,
                    'FIO': obj_model.person,
                    'snils': obj_model.person.user_profile.snils,
                    'oms': obj_model.person.user_profile.oms,
                    'div_address': div_address,
                    }
    except Exception as _ex:
        DataBaseUser.objects.get(pk=request)
        logger.debug(f'Ошибка заполнения файла {filename_pmo}: {DataBaseUser.objects.get(pk=request)} {_ex}')
        context = {}
    doc.render(context)
    doc2.render(context2)
    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename_pmo))
    doc2.save(pathlib.Path.joinpath(path_obj, filename_po))
    # ToDo: Попытка конвертации docx в pdf в Linux. Не работает
    # convert(filename, (filename[:-4]+'pdf'))
    # convert(filepath)


class Medical(models.Model):
    class Meta:
        verbose_name = 'Медицинское направление'
        verbose_name_plural = 'Медицинские направления'

    type_of = [
        ('1', 'Поступающий на работу'),
        ('2', 'Работающий')
    ]

    inspection_view = [
        ('1', 'Медицинский осмотр'),
        ('2', 'Психиатрическое освидетельствование')
    ]

    inspection_type = [
        ('1', 'Предварительный'),
        ('2', 'Периодический'),
        ('3', 'Внеплановый')
    ]

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    number = models.CharField(verbose_name='Номер', max_length=11, default='')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', null=True)
    date_of_inspection = models.DateField(verbose_name='Дата осмотра', null=True)
    organisation = models.ForeignKey(MedicalOrganisation, verbose_name='Медицинская организация',
                                     on_delete=models.SET_NULL, null=True)
    working_status = models.CharField(verbose_name='Статус', max_length=40, choices=type_of,
                                      help_text='', blank=True, default='')
    view_inspection = models.CharField(verbose_name='Вид осмотра', max_length=40, choices=inspection_view,
                                       help_text='', blank=True, default='')
    type_inspection = models.CharField(verbose_name='Тип осмотра', max_length=15, choices=inspection_type,
                                       help_text='', blank=True, default='')
    medical_direction = models.FileField(verbose_name='Файл ПМО', upload_to=contract_directory_path, blank=True)
    medical_direction2 = models.FileField(verbose_name='Файл ПО', upload_to=contract_directory_path, blank=True)
    harmful = models.ManyToManyField(HarmfulWorkingConditions, verbose_name='Вредные условия труда')

    def get_data(self):
        return {
            'pk': self.pk,
            'number': self.number,
            'date_entry': self.date_entry.strftime("%d.%m.%Y"),
            'person': self.person.get_title(),
            'organisation': self.organisation.get_title(),
            'working_status': self.get_working_status_display(),
            'view_inspection': self.get_view_inspection_display(),
            'type_inspection': self.get_type_inspection_display(),
        }

    def __str__(self):
        return f'{self.number} {self.person}'


@receiver(post_save, sender=Medical)
def rename_file_name(sender, instance, **kwargs):
    try:
        change = 0
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        user_uid = '0' * (7 - len(str(instance.person.pk))) + str(instance.person.pk)
        filename_pmo = f'MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}.docx'
        filename_po = f'MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}PO.docx'
        Med(instance, f'media/hr/medical/{user_uid}', filename_pmo, filename_po, user_uid)
        if f'hr/medical/{user_uid}/{filename_pmo}' != instance.medical_direction:
            change = 1
            instance.medical_direction = f'hr/medical/{user_uid}/{filename_pmo}'
        if f'hr/medical/{user_uid}/{filename_po}' != instance.medical_direction2:
            change = 1
            instance.medical_direction2 = f'hr/medical/{user_uid}/{filename_po}'
        if change == 1:
            instance.save()
    except Exception as _ex:
        logger.error(f'Ошибка при переименовании файла {_ex}')


class PlaceProductionActivity(models.Model):
    class Meta:
        verbose_name = 'Место назначения'
        verbose_name_plural = 'Места назначения'

    name = models.CharField(verbose_name='Наименование', max_length=250)
    address = models.CharField(verbose_name='Адрес', max_length=250, blank=True)
    short_name = models.CharField(verbose_name='', max_length=3, default='', blank=True)

    def __str__(self):
        return str(self.name)

    def get_data(self):
        return {
            'pk': self.pk,
            'name': self.name,
            'address': self.address,
        }

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:place_list')


class ReasonForCancellation(models.Model):
    class Meta:
        verbose_name = 'Причина отмены'
        verbose_name_plural = 'Причины отмены'

    name = models.CharField(verbose_name='Наименование', max_length=250, default='')

    def __str__(self):
        return self.name

    def get_title(self):
        return str(self.name)


class OfficialMemo(models.Model):
    class Meta:
        verbose_name = 'Служебная записка'
        verbose_name_plural = 'Служебные записки'

    type_of_accommodation = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]

    type_of_trip = [
        ('1', 'Служебная поездка'),
        ('2', 'Командировка')
    ]

    memo_type = [
        ('1', 'Направление'),
        ('2', 'Продление'),
        ('3', 'Без выезда'),
    ]
    document_extension = models.ForeignKey('self', verbose_name='Документ основания', on_delete=models.SET_NULL,
                                           null=True, blank=True)
    date_of_creation = models.DateTimeField(verbose_name='Дата и время создания',
                                            auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    official_memo_type = models.CharField(verbose_name='Тип СП', max_length=9, choices=memo_type,
                                          help_text='', default='1')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                               related_name='employee')
    purpose_trip = models.ForeignKey(Purpose, verbose_name='Цель', on_delete=models.SET_NULL, null=True, )
    period_from = models.DateField(verbose_name='Дата начала', null=True)
    period_for = models.DateField(verbose_name='Дата окончания', null=True)
    place_departure = models.ForeignKey(PlaceProductionActivity, verbose_name='Место отправления',
                                        on_delete=models.SET_NULL, null=True, related_name='place_departure')
    place_production_activity = models.ManyToManyField(PlaceProductionActivity, verbose_name='МПД',
                                                       related_name='place_production_activity')
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of_accommodation,
                                     help_text='', blank=True, default='')
    type_trip = models.CharField(verbose_name='Тип поездки', max_length=9, choices=type_of_trip,
                                 help_text='', blank=True, default='')
    order = models.ForeignKey('DocumentsOrder', verbose_name='Приказ', on_delete=models.SET_NULL, null=True, blank=True)
    comments = models.CharField(verbose_name='Примечание', max_length=250, default='', blank=True)
    document_accepted = models.BooleanField(verbose_name='Документ принят', default=False)
    responsible = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                                    related_name='responsible')
    cancellation = models.BooleanField(verbose_name='Отмена', default=False)
    reason_cancellation = models.ForeignKey(ReasonForCancellation, verbose_name='Причина отмены',
                                            on_delete=models.SET_NULL, blank=True, null=True)
    history_change = GenericRelation(HistoryChange)
    title = models.CharField(verbose_name='Наименование', max_length=200, default='', blank=True)

    def __str__(self):
        return self.title

    def get_title(self):
        return self.title

    def get_data(self):
        place = [str(item) for item in self.place_production_activity.iterator()]
        if self.type_trip == '1':
            if self.official_memo_type == '1':
                type_trip = 'СП'
            elif self.official_memo_type == '2':
                type_trip = 'СП+'
            else:
                type_trip = 'БВ'
        else:
            if self.official_memo_type == '1':
                type_trip = 'К'
            else:
                type_trip = 'К+'

        return {
            'pk': self.pk,
            'type_trip': type_trip,
            'person': str(self.person),
            'job': str(self.person.user_work_profile.job),
            'place_production_activity': '; '.join(place),
            'purpose_trip': str(self.purpose_trip),
            'period_from': self.period_from.strftime("%d.%m.%Y"),
            'period_for': self.period_for.strftime("%d.%m.%Y"),
            'accommodation': str(self.get_accommodation_display()),
            'order': str(self.order) if self.order else '',
            'comments': str(self.comments),
            'cancellation': self.cancellation,
            'document_accepted': self.document_accepted,
            'date_order': self.period_from,
        }


@receiver(pre_save, sender=OfficialMemo)
def fill_title(sender, instance, **kwargs):
    if instance.official_memo_type == '1':
        type_memo = "(СП):" if instance.type_trip == "1" else "(К):"
    elif instance.official_memo_type == '2':
        type_memo = "(СП+):" if instance.type_trip == "1" else "(К+):"
    else:
        type_memo = "(БВ)"
    instance.title = f'{type_memo} {FIO_format(instance.person)} с {instance.period_from.strftime("%d.%m.%Y")} по {instance.period_for.strftime("%d.%m.%Y")}'


class ApprovalProcess(models.Model):
    """
    Служебная записка
    """

    class Meta:
        abstract = True

    date_of_creation = models.DateTimeField(verbose_name='Дата и время создания', auto_now_add=True)
    person_executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                        null=True, related_name='person_executor')
    submit_for_approval = models.BooleanField(verbose_name='Передан на согласование', default=False)
    comments_for_approval = models.CharField(verbose_name='Комментарий для согласования', max_length=200, help_text='',
                                             blank=True, default='')
    person_agreement = models.ForeignKey(DataBaseUser, verbose_name='Согласующее лицо', on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='person_agreement')
    document_not_agreed = models.BooleanField(verbose_name='Документ согласован', default=False)
    reason_for_approval = models.CharField(verbose_name='Примечание к согласованию', max_length=200, help_text='',
                                           blank=True, default='')
    person_distributor = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник НО', on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='person_distributor')
    location_selected = models.BooleanField(verbose_name='Выбрано место проживания', default=False)
    person_department_staff = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник ОК', on_delete=models.SET_NULL,
                                                null=True, blank=True, related_name='person_department_staff')
    process_accepted = models.BooleanField(verbose_name='Издан приказ', default=False)
    person_clerk = models.ForeignKey(DataBaseUser, verbose_name='Делопроизводитель', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='person_clerk')
    originals_received = models.BooleanField(verbose_name='Получены оригиналы', default=False)
    person_hr = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник ОК', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='person_hr')
    hr_accepted = models.BooleanField(verbose_name='Документы проверены', default=False)
    person_accounting = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник Бухгалтерии', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='person_accounting')
    accepted_accounting = models.BooleanField(verbose_name='Принято в бухгалтерии', default=False)
    history_change = GenericRelation(HistoryChange)


class ApprovalOficialMemoProcess(ApprovalProcess):
    """
    Бизнес-процесс служебной записки
    """
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    # ref_key = models.CharField(default=uuid.uuid4, max_length=37, null=True, blank=True)
    document = models.OneToOneField(OfficialMemo, verbose_name='Документ', on_delete=models.CASCADE, null=True,
                                    related_name='docs')
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of,
                                     help_text='', blank=True, default='')
    order = models.ForeignKey('DocumentsOrder', verbose_name='Приказ', on_delete=models.SET_NULL, null=True, blank=True)
    email_send = models.BooleanField(verbose_name='Письмо отправлено', default=False)
    cancellation = models.BooleanField(verbose_name='Отмена', default=False)
    reason_cancellation = models.ForeignKey(ReasonForCancellation, verbose_name='Причина отмены',
                                            on_delete=models.SET_NULL, blank=True, null=True)
    date_receipt_original = models.DateField(verbose_name='Дата получения', null=True, blank=True)
    originals_docs_comment = models.CharField(verbose_name='Примечание', max_length=100,
                                              help_text='', blank=True, default='')
    submitted_for_signature = models.DateField(verbose_name='Дата передачи на подпись', null=True, blank=True)
    date_transfer_hr = models.DateField(verbose_name='Дата передачи в ОК', null=True, blank=True)
    number_business_trip_days = models.IntegerField(verbose_name='Дни СП', default=0)
    number_flight_days = models.IntegerField(verbose_name='Дни ЛД', default=0)
    start_date_trip = models.DateField(verbose_name='Дата начала по СЗ', null=True, blank=True)
    end_date_trip = models.DateField(verbose_name='Дата окончания по СЗ', null=True, blank=True)
    date_transfer_accounting = models.DateField(verbose_name='Дата передачи в бухгалтерию', null=True, blank=True)
    prepaid_expense = models.CharField(verbose_name='Пометка выплаты', max_length=100,
                                       help_text='', blank=True, default='')
    prepaid_expense_summ = models.DecimalField(verbose_name='Сумма авансового отчета', default=0, max_digits=10,
                                               decimal_places=2)

    class Meta:
        verbose_name = 'Служебная записка по служебной поездке'
        verbose_name_plural = 'Служебные записки по служебным поездкам'

    def __init__(self, *args, **kwargs):
        super(ApprovalOficialMemoProcess, self).__init__(*args, **kwargs)

    def __str__(self):
        return str(self.document)

    def get_data(self):
        if self.document.official_memo_type == '3':
            location_selected = '--//--'
            process_accepted = '--//--'
        else:
            location_selected = FIO_format(self.person_distributor, self) if self.location_selected else ''
            process_accepted = FIO_format(self.person_department_staff, self) if self.process_accepted else ''
        return {
            'pk': self.pk,
            'document': str(self.document.title),
            'submit_for_approval': FIO_format(self.person_executor, self) if self.submit_for_approval else '',
            'document_not_agreed': FIO_format(self.person_agreement, self) if self.document_not_agreed else '',
            'location_selected': location_selected,
            'process_accepted': process_accepted,
            'accepted_accounting': FIO_format(self.person_accounting, self) if self.accepted_accounting else '',
            'accommodation': str(self.get_accommodation_display()),
            'order': str(self.order) if self.order else '',
            'comments': str(self.document.comments),
            'cancellation': self.cancellation,
            'originals_received': True if self.originals_received and self.date_transfer_hr else False,
        }

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:bpmemo_list')

    def send_mail(self, title):
        if not self.cancellation:
            mail_to = self.document.person.email
            mail_to_copy_first = self.person_executor.email
            mail_to_copy_second = self.person_distributor.email
            mail_to_copy_third = self.person_department_staff.email
            subject_mail = title

            current_context = {
                'title': self.document.title,
                'order_number': str(self.order.document_number) if self.order else '--//--',
                'order_date': str(self.order.document_date) if self.order else '--//--',
                'reason_cancellation': str(self.reason_cancellation.get_title()),
                'person_executor': str(self.person_executor),
                'person_distributor': str(self.person_distributor),
                'person_department_staff': str(self.person_department_staff)
            }
            logger.debug(f'Email string: {current_context}')
            text_content = render_to_string('hrdepartment_app/email_cancel_bpmemo.html', current_context)
            html_content = render_to_string('hrdepartment_app/email_cancel_bpmemo.html', current_context)
            first_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
                                               [mail_to, mail_to_copy_first])
            second_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
                                                [mail_to_copy_second, mail_to_copy_third])
            first_msg.attach_alternative(html_content, "text/html")
            second_msg.attach_alternative(html_content, "text/html")

            try:
                # send_mass_mail((first_msg, second_msg), fail_silently=False)
                first_msg.send()
                second_msg.send()
            except Exception as _ex:
                logger.debug(f'Failed to send email. {_ex}')


def create_xlsx(instance):
    from openpyxl import load_workbook
    filepath = pathlib.Path.joinpath(MEDIA_URL, 'wb.xlsx')
    wb = load_workbook(filepath)
    ws = wb.active()
    ws['C3'] = instance.document.person
    filepath2 = pathlib.Path.joinpath(MEDIA_URL, 'wb-1.xlsx')
    ws.save(filepath2)


@receiver(pre_save, sender=ApprovalOficialMemoProcess)
def hr_accepted(sender, instance, **kwargs):
    if instance.hr_accepted:
        obj_list = ReportCard.objects.filter(Q(doc_ref_key=instance.pk) & Q(employee=instance.document.person))
        interval = list(rrule.rrule(rrule.DAILY, dtstart=instance.start_date_trip, until=instance.end_date_trip))
        if obj_list.count() != len(interval):
            for item in obj_list:
                item.delete()
            for date in interval:
                if instance.document.type_trip == '1':
                    record_type = '14'
                else:
                    record_type = '15'
                start_time, end_time, type_of_day = check_day(date, datetime.datetime(1, 1, 1, 9, 30).time(),
                                                 datetime.datetime(1, 1, 1, 18, 0).time())
                report_kwargs = {
                    'report_card_day': date,
                    'rec_no': instance.pk + instance.document.person.pk,
                    'employee': instance.document.person,
                    'start_time': start_time,
                    'end_time': end_time,
                    'record_type': record_type,
                    'reason_adjustment': str(instance.document),
                    'doc_ref_key': instance.pk,
                }
                ReportCard.objects.update_or_create(report_card_day=date, doc_ref_key=instance.pk,
                                                    employee=instance.document.person, defaults=report_kwargs)
    else:
        obj_list = ReportCard.objects.filter(Q(doc_ref_key=instance.pk) & Q(employee=instance.document.person))
        for item in obj_list:
            item.delete()


@receiver(post_save, sender=ApprovalOficialMemoProcess)
def create_report(sender, instance, **kwargs):
    type_of = ['Служебная квартира', 'Гостиница']

    if instance.process_accepted and not instance.email_send:
        from openpyxl import load_workbook
        delta = instance.document.period_for - instance.document.period_from
        try:
            place = [item.name for item in instance.document.place_production_activity.all()]
        except Exception as _ex:
            place = []
        # Получаем ссылку на файл шаблона
        if instance.document.person.user_work_profile.job.type_of_job == '1':
            if instance.document.type_trip == '2':
                filepath_name = 'spk.xlsx'
            else:
                filepath_name = 'sp.xlsx'
        else:
            if instance.document.type_trip == '2':
                filepath_name = 'sp2k.xlsx'
            else:
                filepath_name = 'sp2.xlsx'
        filepath = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates'), filepath_name)
        wb = load_workbook(filepath)
        ws = wb.active
        ws['C3'] = str(instance.document.person)
        ws['M3'] = str(instance.document.person.service_number)
        ws['C4'] = str(instance.document.person.user_work_profile.job)
        ws['C5'] = str(instance.document.person.user_work_profile.divisions)
        ws['C6'] = 'Приказ № ' + str(instance.order.document_number)
        ws['F6'] = instance.order.document_date.strftime("%d.%m.%y")
        ws['H6'] = 'на ' + ending_day(int(delta.days) + 1)
        ws['L6'] = instance.document.period_from.strftime("%d.%m.%y")
        ws['O6'] = instance.document.period_for.strftime("%d.%m.%y")
        ws['C8'] = str(place).strip('[]')
        ws['C9'] = str(instance.document.purpose_trip)
        ws['A90'] = str(instance.person_agreement.user_work_profile.job) + ', ' + FIO_format(
            instance.person_agreement)

        wb.save(pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), filepath_name))
        wb.close()
        # Конвертируем xlsx в pdf
        # Удалить
        from msoffice2pdf import convert
        source = str(pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), filepath_name))
        output_dir = str(pathlib.Path.joinpath(BASE_DIR, 'media'))
        file_name = convert(source=source, output_dir=output_dir, soft=0)

        # from msoffice2pdf import convert
        # source = str(pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), filepath_name))
        # output_dir = str(pathlib.Path.joinpath(BASE_DIR, 'media'))
        # file_name = convert(source=source, output_dir=output_dir, soft=0)
        mail_to = instance.document.person.email
        mail_to_copy = instance.person_executor.email
        subject_mail = 'Направление'

        if instance.accommodation == '1':
            accommodation = 'Квартира'
        else:
            accommodation = 'Гостиница'
        current_context = {
            'greetings': 'Уважаемый' if instance.document.person.gender == 'male' else 'Уважаемая',
            'person': str(instance.document.person),
            'place': str(place).strip('[]'),
            'purpose_trip': str(instance.document.purpose_trip),
            'order_number': str(instance.order.document_number),
            'order_date': str(instance.order.document_date),
            'delta': str(ending_day(int(delta.days) + 1)),
            'period_from': str(instance.document.period_from),
            'period_for': str(instance.document.period_for),
            'accommodation': accommodation,
            'person_executor': str(instance.person_executor),
            'person_distributor': str(instance.person_distributor),
        }
        logger.debug(f'Email string: {current_context}')
        text_content = render_to_string('hrdepartment_app/email_template.html', current_context)
        html_content = render_to_string('hrdepartment_app/email_template.html', current_context)

        msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER, [mail_to, mail_to_copy, ])
        msg.attach_alternative(html_content, "text/html")
        if instance.document.official_memo_type == '1':
            msg.attach_file(str(file_name))
        try:
            res = msg.send()
            instance.email_send = True
            instance.save()
        except Exception as _ex:
            logger.debug(f'Failed to send email. {_ex}')


class BusinessProcessDirection(models.Model):
    type_of = [
        ('1', 'SP')
    ]

    class Meta:
        verbose_name = 'Направление бизнес процесса'
        verbose_name_plural = 'Направления бизнес процессов'

    business_process_type = models.CharField(verbose_name='Тип бизнес процесса', max_length=5, default='', blank=True,
                                             choices=type_of)
    person_executor = models.ManyToManyField(Job, verbose_name='Исполнитель', related_name='person_executor')
    person_agreement = models.ManyToManyField(Job, verbose_name='Согласующее лицо', related_name='person_agreement')
    clerk = models.ManyToManyField(Job, verbose_name='Делопроизводитель', related_name='clerk')
    person_hr = models.ManyToManyField(Job, verbose_name='Сотрудник ОК', related_name='person_hr')
    date_start = models.DateField(verbose_name='Дата начала', null=True, blank=True)
    date_end = models.DateField(verbose_name='Дата окончания', null=True, blank=True)

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:bptrip_list')


def order_doc(obj_model, filepath, filename, request):
    if obj_model.document_foundation:
        if obj_model.document_foundation.type_trip == '1':
            if 'Командир воздушного судна' in obj_model.document_foundation.person.user_work_profile.job.get_title():
                doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/aom2.docx'))
            else:
                doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/aom.docx'))
        else:
            doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/aom3.docx'))

        delta = obj_model.document_foundation.period_for - obj_model.document_foundation.period_from
        place = [item.name for item in obj_model.document_foundation.place_production_activity.all()]
        try:
            context = {'Number': obj_model.document_number,
                       'DateDoc': f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
                       'FIO': obj_model.document_foundation.person,
                       'ServiceNum': obj_model.document_foundation.person.service_number,
                       'Division': obj_model.document_foundation.person.user_work_profile.divisions,
                       'Job': obj_model.document_foundation.person.user_work_profile.job,
                       'Place': str(place).strip('[]').replace("'", ""),
                       'DateCount': str(int(delta.days) + 1),
                       'DateFrom': f'{obj_model.document_foundation.period_from.strftime("%d.%m.%Y")} г.',
                       'DateFor': f'{obj_model.document_foundation.period_for.strftime("%d.%m.%Y")} г.',
                       'Purpose': obj_model.document_foundation.purpose_trip,
                       'DateAcquaintance': f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
                       }
        except Exception as _ex:
            # DataBaseUser.objects.get(pk=request)
            logger.debug(f'Ошибка заполнения файла {filename}: {_ex}')
            context = {}
    else:
        doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/ord.docx'))
        try:
            context = {'Number': obj_model.document_number,
                       'DateDoc': f'{obj_model.document_date.strftime("%d.%m.%Y")} г.',
                       'Title': obj_model.document_name,
                       'Description': '',
                       }
        except Exception as _ex:
            # DataBaseUser.objects.get(pk=request)
            logger.debug(f'Ошибка заполнения файла {filename}: {_ex}')
            context = {}
    doc.render(context)
    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename))


class OrderDescription(models.Model):
    class Meta:
        verbose_name = 'Наименование приказа'
        verbose_name_plural = 'Наименования приказов'

    name = models.CharField(verbose_name='', max_length=150)

    def __str__(self):
        return self.name


class DocumentsOrder(Documents):
    type_of_order = [
        ('1', 'Общая деятельность'),
        ('2', 'Личный состав')
    ]

    class Meta:
        verbose_name = 'Приказ'
        verbose_name_plural = 'Приказы'
        # default_related_name = 'order'

    document_name = models.ForeignKey(OrderDescription, verbose_name='Наименование документа',
                                      on_delete=models.SET_NULL, null=True, default=None)
    # doc_name = models.ForeignKey(OrderDescription, verbose_name='Наименование документа', on_delete=models.SET_NULL, null=True, default=1)
    doc_file = models.FileField(verbose_name='Файл документа', upload_to=ord_directory_path, blank=True)
    scan_file = models.FileField(verbose_name='Скан документа', upload_to=ord_directory_path, blank=True)
    document_order_type = models.CharField(verbose_name='Тип приказа', max_length=18, choices=type_of_order)
    document_foundation = models.ForeignKey(OfficialMemo, verbose_name='Документ основание', on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='doc_foundation')
    description = CKEditor5Field('Содержание', config_name='extends', blank=True)
    approved = models.BooleanField(verbose_name='Утверждён', default=False)
    cancellation = models.BooleanField(verbose_name='Отмена', default=False)
    reason_cancellation = models.ForeignKey(ReasonForCancellation, verbose_name='Причина отмены',
                                            on_delete=models.SET_NULL, blank=True, null=True)

    def get_data(self):
        status = ''
        dt = datetime.datetime.today()

        if self.validity_period_end and datetime.date(dt.year, dt.month, dt.day) > self.validity_period_end:
            status = 'Действие завершил'
        else:
            status = 'Действует'

        if self.cancellation:
            status = 'Отменён'
        return {
            'pk': self.pk,
            'document_number': self.document_number,
            'document_date': self.document_date.strftime("%d.%m.%Y"),
            'document_name': self.document_name.name,
            'person': FIO_format(self.document_foundation.person.get_title()) if self.document_foundation else '',
            'approved': status,
            'cancellation': self.cancellation,
        }

    def get_absolute_url(self):
        return reverse('hrdepartment_app:order_list')

    def __str__(self):
        return f'Пр. № {self.document_number} от {self.document_date.strftime("%d.%m.%Y")} г.'


@receiver(post_save, sender=DocumentsOrder)
def rename_order_file_name(sender, instance, **kwargs):
    try:
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули

        # ext_scan = str(instance.scan_file).split('.')[-1]
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        filename = f'ORD-{instance.document_order_type}-{instance.document_date}-{uid}.docx'
        scanname = f'ORD-{instance.document_order_type}-{instance.document_date}-{uid}.pdf'
        date_doc = instance.document_date
        order_doc(instance, f'media/docs/ORD/{date_doc.year}/{date_doc.month}', filename, instance.document_order_type)
        scan_name = pathlib.Path(instance.scan_file.name).name
        if f'docs/ORD/{date_doc.year}/{date_doc.month}/{filename}' != instance.doc_file:
            DocumentsOrder.objects.filter(pk=instance.pk).update(
                doc_file=f'docs/ORD/{date_doc.year}/{date_doc.month}/{filename}')
        if f'docs/ORD/{date_doc.year}/{date_doc.month}/{scanname}' != instance.scan_file:
            try:
                pathlib.Path.rename(
                    pathlib.Path.joinpath(BASE_DIR, 'media', f'docs/ORD/{date_doc.year}/{date_doc.month}', scan_name),
                    pathlib.Path.joinpath(BASE_DIR, 'media', f'docs/ORD/{date_doc.year}/{date_doc.month}', scanname))
            except Exception as _ex0:
                logger.error(f'Ошибка переименования файла: {_ex0}')
            DocumentsOrder.objects.filter(pk=instance.pk).update(
                scan_file=f'docs/ORD/{date_doc.year}/{date_doc.month}/{scanname}')

    except Exception as _ex:
        logger.error(f'Ошибка при переименовании файла {_ex}')


class DocumentsJobDescription(Documents):
    class Meta:
        verbose_name = 'Должностная инструкция'
        verbose_name_plural = 'Должностные инструкции'
        # default_related_name = 'job'

    doc_file = models.FileField(verbose_name='Файл документа', upload_to=jds_directory_path, blank=True)
    scan_file = models.FileField(verbose_name='Скан документа', upload_to=jds_directory_path, blank=True)
    document_division = models.ForeignKey(Division, verbose_name='Подразделение', on_delete=models.SET_NULL, null=True)
    document_job = models.ForeignKey(Job, verbose_name='Должность', on_delete=models.SET_NULL, null=True)
    document_order = models.ForeignKey(DocumentsOrder, verbose_name='Приказ', on_delete=models.SET_NULL, null=True)

    def get_data(self):
        return {
            'pk': self.pk,
            'document_number': self.document_number,
            'document_date': self.document_date.strftime("%d.%m.%Y"),
            'document_job': str(self.document_job),
            'document_division': str(self.document_division),
            'document_order': str(self.document_order),
            'actuality': 'Да' if self.actuality else 'Нет',
            'executor': str(self.executor),
        }

    def get_absolute_url(self):
        return reverse('hrdepartment_app:jobdescription_list')

    def __str__(self):
        return f'ДИ {self.document_name} №{self.document_number} от {self.document_date.strftime("%d.%m.%Y")}'


@receiver(post_save, sender=DocumentsJobDescription)
def rename_jds_file_name(sender, instance, **kwargs):
    try:
        # Получаем имя сохраненного файла
        file_name = pathlib.Path(instance.doc_file.name).name
        # Получаем путь к файлу
        path_name = pathlib.Path(instance.doc_file.name).parent
        # Получаем расширение файла
        ext = file_name.split('.')[-1]
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        filename = f'JDS-{instance.document_division.code}-' \
                   f'{instance.document_job.code}-{uid}-{instance.document_date}.{ext}'
        if file_name:
            pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', path_name, file_name),
                                pathlib.Path.joinpath(BASE_DIR, 'media', path_name, filename))

        instance.doc_file = f'docs/JDS/{instance.document_division.code}/{filename}'
        if file_name != filename:
            instance.save()
    except Exception as _ex:
        print(_ex)


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
    """
    type_of_report = [
        ('1', 'Явка'),
        ('2', 'Ежегодный'),
        ('3', 'Дополнительный ежегодный отпуск'),
        ('4', 'Отпуск за свой счет'),
        ('5', 'Дополнительный учебный отпуск (оплачиваемый)'),
        ('6', 'Отпуск по уходу за ребенком'),
        ('7', 'Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС'),
        ('8', 'Отпуск по беременности и родам'),
        ('9', 'Отпуск без оплаты согласно ТК РФ'),
        ('10', 'Дополнительный отпуск'),
        ('11', 'Дополнительный оплачиваемый отпуск пострадавшим в '),
        ('12', 'Основной'),
        ('13', 'Ручной ввод'),
        ('14', 'Служебная поездка'),
        ('15', 'Командировка'),
        ('16', 'Больничный'),
        ('16', 'Мед осмотр'),
    ]

    class Meta:
        verbose_name = 'Рабочее время'
        verbose_name_plural = 'Табель учета'

    report_card_day = models.DateField(verbose_name='Дата', null=True, blank=True)
    rec_no = models.IntegerField(verbose_name='Номер записи', default=0, blank=True)
    employee = models.ForeignKey(DataBaseUser, on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.TimeField(verbose_name='Время прихода', null=True, blank=True)
    end_time = models.TimeField(verbose_name='Время ухода', null=True, blank=True)
    record_type = models.CharField(verbose_name='Тип записи', max_length=100, choices=type_of_report, default='',
                                   blank=True)
    manual_input = models.BooleanField(verbose_name='Ручной ввод', default=False)
    reason_adjustment = models.TextField(verbose_name='Причина ручной корректировки', blank=True)
    doc_ref_key = models.CharField(verbose_name='Уникальный номер документа', max_length=37, default='', blank=True)
    current_intervals = models.BooleanField(verbose_name='Текущий интервал', default=True)

    def get_data(self):
        return {
            'pk': self.pk,
            'report_card_day': self.report_card_day,
            'start_time': self.start_time,
            'end_time': str(self.end_time),
            'reason_adjustment': self.reason_adjustment,
        }

    def __str__(self):
        return f'{self.employee}: {self.report_card_day} : {self.record_type}'


class PreHolidayDay(models.Model):
    class Meta:
        verbose_name = 'Предпраздничный день'
        verbose_name_plural = 'Предпраздничные дни'

    preholiday_day = models.DateField(verbose_name='Дата', null=True, blank=True)
    work_time = models.TimeField(verbose_name='Рабочее время', null=True, blank=True)

    def __str__(self):
        return str(self.preholiday_day)


class WeekendDay(models.Model):
    """
    Праздничные дни и выходные дни в связи с праздником
    Атрибуты:
    weekend_day - Дата, description - Описание, weekend_type - Тип дня (1 - Праздник, 2 - Выходной)
    """
    type_of_weekend = [
        ('1', 'Праздник'),
        ('2', 'Выходной'),
    ]

    class Meta:
        verbose_name = 'Праздничный день'
        verbose_name_plural = 'Праздничные дни'

    weekend_day = models.DateField(verbose_name='Дата', null=True, blank=True)
    description = models.CharField(verbose_name='Описание', max_length=200, default='', blank=True)
    weekend_type = models.CharField(verbose_name='Тип дня', max_length=8, choices=type_of_weekend, blank=True,
                                    null=True)

    def __str__(self):
        return str(self.weekend_day)


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
        verbose_name = 'Месяц в производственом календаре'
        verbose_name_plural = 'Производственный календарь'

    calendar_month = models.DateField(verbose_name='Месяц', null=True, blank=True)
    number_calendar_days = models.PositiveIntegerField(verbose_name='Количество календарных дней', default=0, null=True,
                                                       blank=True)
    number_working_days = models.PositiveIntegerField(verbose_name='Количество рабочих дней', default=0, null=True,
                                                      blank=True)
    number_days_off_and_holidays = models.PositiveIntegerField(verbose_name='Количество выходных и празднечных дней',
                                                               default=0, null=True, blank=True)
    description = models.CharField(verbose_name='Описание', max_length=200, default='', blank=True)

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

    def get_norm_time(self):
        """
        Подсчет количества рабочих часов в месяце
        :return: количество рабочих часов в месяце
        """
        return (self.number_working_days * 8) + (self.number_working_days / 2) - self.get_friday_count()

    def __str__(self):
        return str(self.calendar_month)


def check_day(date: datetime.date, time_start: datetime.time, time_end: datetime.time):
    """
    Функция определяющая время начала и окончания рабочего дня на заданную дату
    :param date: дата
    :param time_start: время начала
    :param time_end: время окончания
    :return: три значения: время начала, время окончания и тип дня (Р - рабочий, В - выходной, П - праздник)
    """
    type_of_day = ''
    weekend = WeekendDay.objects.filter(weekend_day=date.date()).exists()
    preholiday = PreHolidayDay.objects.filter(preholiday_day=date.date()).exists()
    check_time_end = time_end
    check_time_start = time_start
    if not weekend:
        if date.weekday() in [0, 1, 2, 3]:
            if not preholiday:
                check_time_end = datetime.timedelta(hours=time_end.hour, minutes=time_end.minute)
            else:
                preholiday_time = PreHolidayDay.objects.get(preholiday_day=date.date())
                check_time_end = datetime.timedelta(hours=time_start.hour,
                                                    minutes=time_start.minute) + \
                                 datetime.timedelta(hours=preholiday_time.work_time.hour,
                                                    minutes=preholiday_time.work_time.minute)
            type_of_day = 'Р'
        elif date.weekday() == 4:
            if not preholiday:
                check_time_end = datetime.timedelta(hours=time_end.hour, minutes=time_end.minute) - datetime.timedelta(
                    hours=1)
            else:
                preholiday_time = PreHolidayDay.objects.get(preholiday_day=date.date())
                check_time_end = datetime.timedelta(hours=time_start.hour,
                                                    minutes=time_start.minute) + \
                                 datetime.timedelta(hours=preholiday_time.work_time.hour,
                                                    minutes=preholiday_time.work_time.minute)
            type_of_day = 'Р'
        else:
            check_time_end = datetime.timedelta(hours=0, minutes=0)
            check_time_start = datetime.timedelta(hours=0, minutes=0)
            type_of_day = 'В'
    else:
        check_time_end = datetime.timedelta(hours=0, minutes=0)
        check_time_start = datetime.timedelta(hours=0, minutes=0)
        type_of_day = 'П'

    return timedelta_to_time(check_time_start), timedelta_to_time(check_time_end), type_of_day

class TypesUserworktime(models.Model):
    """
    url = /odata/standard.odata/Catalog_ВидыИспользованияРабочегоВремени?$format=application/json;odata=nometadata
    """
    class Meta:
        verbose_name = 'Вид использования рабочего времени'
        verbose_name_plural = 'Виды использования рабочего времени'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='') # поле в 1с: Ref_Key
    description = models.CharField(verbose_name='Наименование', max_length=150, default='') # поле в 1с: Description
    letter_code = models.CharField(verbose_name='Буквенный код', max_length=5, default='') # поле в 1с: БуквенныйКод
    active = models.BooleanField(verbose_name='Используется', default=False) # поле в 1с: БуквенныйКод

    def __str__(self):
        return self.description
