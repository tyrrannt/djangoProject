import pathlib

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from administration_app.utils import Med
from customers_app.models import DataBaseUser, Counteragent, HarmfulWorkingConditions, Division
from djangoProject.settings import BASE_DIR


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


class Medical(models.Model):
    class Meta:
        verbose_name = 'Медицинское направление'
        verbose_name_plural = 'Медицинские направления'

    type_of = [
        ('1', 'Поступающий на работу'),
        ('2', 'Работающий')
    ]

    number = models.CharField(verbose_name='Номер', max_length=4, default='')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True, null=True)
    organisation = models.ForeignKey(Counteragent, verbose_name='Медицинская организация',
                                     on_delete=models.SET_NULL, null=True)
    working_status = models.CharField(verbose_name='Статус', max_length=40, choices=type_of,
                                      help_text='', blank=True, default='')
    medical_direction = models.FileField(verbose_name='Файл документа', upload_to=contract_directory_path, blank=True)
    harmful = models.ForeignKey(HarmfulWorkingConditions, verbose_name='Вредные условия труда',
                                on_delete=models.SET_NULL, null=True)


@receiver(post_save, sender=Medical)
def rename_file_name(sender, instance, **kwargs):
    try:
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        user_uid = '0' * (7 - len(str(instance.person.pk))) + str(instance.person.pk)
        filename = f'MED-{uid}-{instance.working_status}-{instance.date_entry}-{uid}.docx'
        Med(instance, f'media/hr/medical/{user_uid}', filename)
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

    official_memo_type = models.CharField(verbose_name='Тип СП', max_length=9, choices=memo_type,
                                          help_text='', default='1')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True,
                               related_name='employee')
    purpose_trip = models.ForeignKey(Purpose, verbose_name='Цель', on_delete=models.SET_NULL, null=True, )
    period_from = models.DateField(verbose_name='Дата начала', null=True)
    period_for = models.DateField(verbose_name='Дата окончания', null=True)
    place_production_activity = models.ManyToManyField(Division, verbose_name='МПД')
    accommodation = models.CharField(verbose_name='Проживание', max_length=9, choices=type_of_accommodation,
                                     help_text='', blank=True, default='')
    type_trip = models.CharField(verbose_name='Тип поездки', max_length=9, choices=type_of_trip,
                                     help_text='', blank=True, default='')
    order_number = models.CharField(verbose_name='Номер приказа', max_length=20, default='', null=True, blank=True)
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
