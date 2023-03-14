import pathlib
import uuid

from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from docxtpl import DocxTemplate
from loguru import logger

from administration_app.utils import ending_day, FIO_format
from customers_app.models import DataBaseUser, Counteragent, HarmfulWorkingConditions, Division, Job, AccessLevel
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
    return f'docs/ORD/{instance.document_division.code}/{filename}'


class Documents(models.Model):
    class Meta:
        abstract = True

    ref_key = models.UUIDField(verbose_name='Уникальный номер', default=uuid.uuid4, unique=True)
    # type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
    #                                      null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True)
    executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                 null=True, related_name='%(app_label)s_%(class)s_executor')
    document_date = models.DateField(verbose_name='Дата документа', default='')
    document_name = models.CharField(verbose_name='Наименование документа', max_length=200, default='')
    document_number = models.CharField(verbose_name='Номер документа', max_length=10, default='')

    access = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к документу', on_delete=models.SET_NULL,
                               null=True, default=5)
    employee = models.ManyToManyField(DataBaseUser, verbose_name='Ответственное лицо', blank=True,
                                      related_name='%(app_label)s_%(class)s_employee')
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)
    validity_period_start = models.DateField(verbose_name='Документ действует с', default='')
    validity_period_end = models.DateField(verbose_name='Документ действует по', default='')
    actuality = models.BooleanField(verbose_name='Актуальность', default=False)
    previous_document = models.URLField(verbose_name='Предшествующий документ', blank=True)

    def __str__(self):
        return f'№ {self.document_number} от {self.document_date}'


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


def Med(obj_model, filepath, filename, request):
    inspection_type = [
        ('1', 'Предварительный'),
        ('2', 'Периодический'),
        ('3', 'Внеплановый')
    ]
    if obj_model.person.user_work_profile.job.type_of_job == '1':
        doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med.docx'))
        print('1')
    else:
        doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med2.docx'))
        print('2')
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
    except Exception as _ex:
        DataBaseUser.objects.get(pk=request)
        logger.debug(f'Ошибка заполнения файла {filename}: {DataBaseUser.objects.get(pk=request)} {_ex}')
        context = {}
    doc.render(context)
    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename))
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
    medical_direction = models.FileField(verbose_name='Файл документа', upload_to=contract_directory_path, blank=True)
    harmful = models.ManyToManyField(HarmfulWorkingConditions, verbose_name='Вредные условия труда')

    def get_data(self):
        return {
            'pk': self.pk,
            'number': self.number,
            'date_entry': self.date_entry,
            'person': self.person.get_title(),
            'organisation': self.organisation.get_title(),
            'working_status': self.get_working_status_display(),
            'view_inspection': self.get_view_inspection_display(),
            'type_inspection': self.get_type_inspection_display(),
        }


@receiver(post_save, sender=Medical)
def rename_file_name(sender, instance, **kwargs):
    try:
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        user_uid = '0' * (7 - len(str(instance.person.pk))) + str(instance.person.pk)
        filename = f'MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}.docx'
        Med(instance, f'media/hr/medical/{user_uid}', filename, user_uid)
        if f'hr/medical/{user_uid}/{filename}' != instance.medical_direction:
            instance.medical_direction = f'hr/medical/{user_uid}/{filename}'
            instance.save()
    except Exception as _ex:
        logger.error(f'Ошибка при переименовании файла {_ex}')


class PlaceProductionActivity(models.Model):
    class Meta:
        verbose_name = 'Место назначения'
        verbose_name_plural = 'Места назначения'

    name = models.CharField(verbose_name='Наименование', max_length=250)
    address = models.CharField(verbose_name='Адрес', max_length=250, blank=True)

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
        ('2', 'Продление')
    ]
    date_of_creation = models.DateTimeField(verbose_name='Дата и время создания',
                                            auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    official_memo_type = models.CharField(verbose_name='Тип СП', max_length=9, choices=memo_type,
                                          help_text='', default='1')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                               related_name='employee')
    purpose_trip = models.ForeignKey(Purpose, verbose_name='Цель', on_delete=models.SET_NULL, null=True, )
    period_from = models.DateField(verbose_name='Дата начала', null=True)
    period_for = models.DateField(verbose_name='Дата окончания', null=True)
    place_production_activity = models.ManyToManyField(PlaceProductionActivity, verbose_name='МПД')
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of_accommodation,
                                     help_text='', blank=True, default='')
    type_trip = models.CharField(verbose_name='Тип поездки', max_length=9, choices=type_of_trip,
                                 help_text='', blank=True, default='')
    order = models.ForeignKey('DocumentsOrder', verbose_name='Приказ', on_delete=models.SET_NULL, null=True, blank=True)
    comments = models.CharField(verbose_name='Примечание', max_length=250, default='', blank=True)
    document_accepted = models.BooleanField(verbose_name='Документ принят', default=False)
    responsible = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                                    related_name='responsible')

    def __str__(self):
        return f'СЗ {FIO_format(self.person)} с {self.period_from} по {self.period_for}'

    def get_data(self):
        place = [str(item) for item in self.place_production_activity.iterator()]
        if self.type_trip == '1':
            if self.official_memo_type == '1':
                type_trip = 'СП'
            else:
                type_trip = 'СП+'
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
            'period_from': f'С: {self.period_from} \nПо: {self.period_for}',
            'accommodation': str(self.get_accommodation_display()),
            'order': str(self.order) if self.order else '',
            'comments': str(self.comments),
        }


class ApprovalProcess(models.Model):
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
    person_distributor = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник ГСМ и НТ', on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='person_distributor')
    location_selected = models.BooleanField(verbose_name='Выбрано место проживания', default=False)
    person_department_staff = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник ОК', on_delete=models.SET_NULL,
                                                null=True, blank=True, related_name='person_department_staff')
    process_accepted = models.BooleanField(verbose_name='Активность', default=False)


class ApprovalOficialMemoProcess(ApprovalProcess):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    document = models.OneToOneField(OfficialMemo, verbose_name='Документ', on_delete=models.CASCADE, null=True,
                                    related_name='docs')
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of,
                                     help_text='', blank=True, default='')
    order = models.ForeignKey('DocumentsOrder', verbose_name='Приказ', on_delete=models.SET_NULL, null=True, blank=True)

    # order_number = models.CharField(verbose_name='Номер приказа', max_length=20, default='', null=True, blank=True)
    # order_date = models.DateField(verbose_name='Дата приказа', null=True, blank=True)

    class Meta:
        verbose_name = 'Служебная записка по служебной поездке'
        verbose_name_plural = 'Служебные записки по служебным поездкам'

    def __init__(self, *args, **kwargs):
        super(ApprovalOficialMemoProcess, self).__init__(*args, **kwargs)

    def __str__(self):
        return str(self.document)

    def get_data(self):
        return {
            'pk': self.pk,
            'document': str(self.document),
            'submit_for_approval': FIO_format(self.person_executor, self) if self.submit_for_approval else '',
            'document_not_agreed': FIO_format(self.person_agreement, self) if self.document_not_agreed else '',
            'location_selected': FIO_format(self.person_distributor, self) if self.location_selected else '',
            'process_accepted': FIO_format(self.person_department_staff, self) if self.process_accepted else '',
            'accommodation': str(self.get_accommodation_display()),
            'order': str(self.order) if self.order else '',
            'comments': str(self.document.comments),
        }


def create_xlsx(instance):
    from openpyxl import load_workbook
    filepath = pathlib.Path.joinpath(MEDIA_URL, 'wb.xlsx')
    print(filepath)
    wb = load_workbook(filepath)
    ws = wb.active()
    ws['C3'] = instance.document.person
    filepath2 = pathlib.Path.joinpath(MEDIA_URL, 'wb-1.xlsx')
    ws.save(filepath2)


@receiver(post_save, sender=ApprovalOficialMemoProcess)
def create_report(sender, instance, **kwargs):
    type_of = ['Служебная квартира', 'Гостиница']
    try:
        if instance.process_accepted:
            from openpyxl import load_workbook
            delta = instance.document.period_for - instance.document.period_from
            place = [item.name for item in instance.document.place_production_activity.all()]
            # Получаем ссылку на файл шаблона
            filepath = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), 'sp.xlsx')
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

            wb.save(pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), 'sp.xlsx'))
            wb.close()
            # Конвертируем xlsx в pdf
            from msoffice2pdf import convert
            source = str(pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, 'media'), 'sp.xlsx'))
            output_dir = str(pathlib.Path.joinpath(BASE_DIR, 'media'))
            file_name = convert(source=source, output_dir=output_dir, soft=0)

            TO = instance.document.person.email
            TO_COPY = instance.person_executor.email
            SUBJECT = "Направление"

            try:
                current_context = {
                    'greetings': 'Уважаемый' if instance.document.person.gender == 'male' else 'Уважаемая',
                    'person': instance.document.person,
                    'place': str(place).strip('[]'),
                    'purpose_trip': instance.document.purpose_trip,
                    'order_number': instance.order.document_number,
                    'order_date': instance.order.document_date,
                    'delta': ending_day(int(delta.days) + 1),
                    'period_from': instance.document.period_from,
                    'period_for': instance.document.period_for,
                    'accommodation': type_of[int(instance.accommodation)],
                    'person_executor': instance.person_executor,
                    'person_distributor': instance.person_distributor,
                }
                text_content = render_to_string('hrdepartment_app/email_template.html', current_context)
                html_content = render_to_string('hrdepartment_app/email_template.html', current_context)

                msg = EmailMultiAlternatives(SUBJECT, text_content, EMAIL_HOST_USER, [TO, TO_COPY, ])
                msg.attach_alternative(html_content, "text/html")
                msg.attach_file(str(file_name))
                # res = msg.send()

            except Exception as _ex:
                logger.debug(f'Failed to send email. {_ex}')

    except Exception as _ex:
        logger.error(f'Ошибка при создании файла СП. {_ex}')


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
    date_start = models.DateField(verbose_name='Дата начала', null=True, blank=True)
    date_end = models.DateField(verbose_name='Дата окончания', null=True, blank=True)

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:bptrip_list')


class DocumentsOrder(Documents):
    type_of_order = [
        ('1', 'Общая деятельность'),
        ('2', 'Личный состав')
    ]

    class Meta:
        verbose_name = 'Приказ'
        verbose_name_plural = 'Приказы'
        # default_related_name = 'order'

    doc_file = models.FileField(verbose_name='Файл документа', upload_to=ord_directory_path, blank=True)
    scan_file = models.FileField(verbose_name='Скан документа', upload_to=ord_directory_path, blank=True)
    document_order_type = models.CharField(verbose_name='Тип приказа', max_length=18, choices=type_of_order)
    document_foundation = models.ForeignKey(OfficialMemo, verbose_name='Документ основание', on_delete=models.SET_NULL,
                                            null=True, blank=True)
    approved = models.BooleanField(verbose_name='Утверждён', default=False)

    def get_data(self):
        return {
            'pk': self.pk,
            'document_number': self.document_number,
            'document_date': self.document_date,
            'document_name': self.document_name,
            'approved': self.approved,
        }

    def get_absolute_url(self):
        return reverse('hrdepartment_app:order_list')

    def __str__(self):
        return f'Пр. № {self.document_number} от {self.document_date} г.'


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
            'document_date': self.document_date,
            'document_job': str(self.document_job),
            'document_division': str(self.document_division),
            'document_order': str(self.document_order),
            'actuality': 'Да' if self.actuality else 'Нет',
            'executor': str(self.executor),
        }

    def get_absolute_url(self):
        return reverse('hrdepartment_app:jobdescription_list')

    def __str__(self):
        return f'ДИ {self.document_name} №{self.document_number} от {self.document_date}'


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
