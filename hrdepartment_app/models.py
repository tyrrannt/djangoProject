import pathlib

from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from loguru import logger

from administration_app.utils import Med, ending_day, FIO_format
from customers_app.models import DataBaseUser, Counteragent, HarmfulWorkingConditions, Division, Job
from djangoProject.settings import BASE_DIR, EMAIL_HOST_USER, MEDIA_URL

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# Create your models here.
def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'hr/medical/{filename}'


class Purpose(models.Model):
    class Meta:
        verbose_name = "Цель служебной записки"
        verbose_name_plural = "Цели служебной записки"

    title = models.CharField(verbose_name='Наименование', max_length=300)

    def __str__(self):
        return self.title


class MedicalOrganisation(models.Model):
    class Meta:
        verbose_name = 'Медицинская организация'
        verbose_name_plural = 'Медицинскик организации'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    description = models.CharField(verbose_name='Наименование', max_length=200, default='')
    ogrn = models.CharField(verbose_name='ОГРН', max_length=13, default='')
    address = models.CharField(verbose_name='Адрес', max_length=250, default='')
    email = models.EmailField(verbose_name='Email', default='')
    phone = models.CharField(verbose_name='Телефон', max_length=15, default='')

    def __str__(self):
        return self.description

    @staticmethod
    def get_absolute_url():
        return reverse('hrdepartment_app:medicalorg_list')


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
    number = models.CharField(verbose_name='Номер', max_length=4, default='')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True, null=True)
    date_of_inspection = models.DateField(verbose_name='Дата осмотра', auto_now_add=True, null=True)
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
        print(_ex)


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
    place_production_activity = models.ManyToManyField(Division, verbose_name='МПД')
    other_place_production_activity = models.CharField(verbose_name='Другое место назначения', max_length=20,
                                                       default='', blank=True)
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of_accommodation,
                                     help_text='', blank=True, default='')
    type_trip = models.CharField(verbose_name='Тип поездки', max_length=9, choices=type_of_trip,
                                 help_text='', blank=True, default='')
    order_number = models.CharField(verbose_name='Номер приказа', max_length=20, default='', blank=True, null=True)
    order_date = models.DateField(verbose_name='Дата приказа', null=True, blank=True)
    comments = models.CharField(verbose_name='Примечание', max_length=250, default='', blank=True)
    document_accepted = models.BooleanField(verbose_name='Документ принят', default=False)
    responsible = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                                    related_name='responsible')

    def __str__(self):
        return f'{self.person} с {self.period_from} по {self.period_for}'


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
    order_number = models.CharField(verbose_name='Номер приказа', max_length=20, default='', null=True, blank=True)
    order_date = models.DateField(verbose_name='Дата приказа', null=True, blank=True)

    class Meta:
        verbose_name = 'Служебная записка по служебной поездке'
        verbose_name_plural = 'Служебные записки по служебным поездкам'

    def __init__(self, *args, **kwargs):
        super(ApprovalOficialMemoProcess, self).__init__(*args, **kwargs)


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
            ws['C6'] = 'Приказ № ' + str(instance.order_number)
            ws['F6'] = instance.order_date.strftime("%d.%m.%y")
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
                    'order_number': instance.order_number,
                    'order_date': instance.order_date,
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
