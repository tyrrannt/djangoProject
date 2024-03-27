import datetime
import pathlib

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from customers_app.models import DataBaseUser, Counteragent, AccessLevel, Division
from djangoProject import settings
from djangoProject.settings import BASE_DIR
# from hrdepartment_app.models import PlaceProductionActivity


def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'contracts/{instance.contract_counteragent.inn}/{instance.contract_counteragent.kpp}/{filename}'


class TypeDocuments(models.Model):
    class Meta:
        verbose_name = 'Тип документа'
        verbose_name_plural = 'Тип документов'

    type_document = models.CharField(verbose_name='Тип документа', max_length=50)
    short_name = models.CharField(verbose_name='Краткое наименование', max_length=3, default='')
    file_name_prefix = models.CharField(verbose_name='Префикс файла', max_length=3)

    def __str__(self):
        return f'{self.type_document}'

    def get_data(self):
        return {
            'pk': self.pk,
            'type_document': self.type_document,
            'short_name': self.short_name,
            'file_name_prefix': self.file_name_prefix,
        }


class TypeContract(models.Model):
    class Meta:
        verbose_name = 'Тип договора'
        verbose_name_plural = 'Тип договоров'

    type_contract = models.CharField(verbose_name='Тип договора', max_length=50)
    authorized_person = models.ManyToManyField(DataBaseUser, verbose_name='Авторизованное лицо')

    def __str__(self):
        return f'{self.type_contract}'

    def get_data(self):
        return {
            'pk': self.pk,
            'type_contract': self.type_contract,
        }


class TypeProperty(models.Model):
    class Meta:
        verbose_name = 'Тип имущества'
        verbose_name_plural = 'Тип имущества'

    type_property = models.CharField(verbose_name='Тип имущества', max_length=50, blank=True, default='',
                                     help_text='')

    def __str__(self):
        return f'{self.type_property}'

    def get_data(self):
        return {
            'pk': self.pk,
            'type_property': self.type_property,
        }


class CompanyProperty(models.Model):

    class Meta:
        verbose_name = 'УДАЛЕНО'
        verbose_name_plural = 'УДАЛЕНО'
        ordering = ['name']

    category = models.ForeignKey(TypeProperty, verbose_name='Тип имущества', on_delete=models.SET_NULL, null=True)
    name = models.CharField(verbose_name='Наименование', max_length=200)

    def __str__(self):
        return f'{self.name}'

class Estate(models.Model):
    class Meta:
        verbose_name = 'Имущество'
        verbose_name_plural = 'Имущество'

    type_property = models.ForeignKey(TypeProperty, verbose_name='Тип имущества', on_delete=models.SET_NULL, null=True)
    registration_number = models.CharField(verbose_name='Номер машины', max_length=100, default='', blank=True)
    release_date = models.DateField(verbose_name='Дата выпуска')
    factory_number = models.CharField(verbose_name='Заводской номер', max_length=100, default='', blank=True)
    exploits = models.CharField(verbose_name='Баркол эксплуатирует', max_length=100, default='', blank=True)
    gtd = models.CharField(verbose_name='GTD', max_length=100, default='', blank=True)
    passport = models.CharField(verbose_name='Паспорт', max_length=100, default='', blank=True)
    ownership_right = models.CharField(verbose_name='Право владения', max_length=100, default='', blank=True)
    year_of_manufacture = models.CharField(verbose_name='Год выпуска авто', max_length=100, default='', blank=True)

    def __str__(self):
        return f'{self.registration_number}'

class ContractModel(models.Model):
    """
    Абстрактная модель договоров. Введена для возможности реализации иерархической вложенности. Элемент модели
    может выступать в качестве родителя и дочернего объекта.
    """

    class Meta:
        abstract = True

    type_of_prolongation = [
        ('auto', 'Автоматическая пролонгация'),
        ('ag', 'Оформление ДС')
    ]
    parent_category = models.ForeignKey('self', verbose_name='Главный документ', on_delete=models.CASCADE, null=True,
                                        blank=True)
    contract_counteragent = models.ForeignKey(Counteragent, verbose_name='Контрагент', on_delete=models.SET_NULL,
                                              null=True)
    contract_number = models.CharField(verbose_name='Номер договора', max_length=50, blank=True, default='',
                                       help_text='')
    date_conclusion = models.DateField(verbose_name='Дата заключения договора')
    subject_contract = models.TextField(verbose_name='Предмет договора', blank=True)
    cost = models.FloatField(verbose_name='Стоимость', default=0, null=True, blank=True)
    type_of_contract = models.ForeignKey(TypeContract, verbose_name='Тип договора', on_delete=models.SET_NULL,
                                         null=True)
    type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
                                         null=True)
    divisions = models.ManyToManyField(Division, verbose_name='Подразделение', blank=True)
    type_property = models.ManyToManyField(TypeProperty, verbose_name='Тип имущества', blank=True)
    employee = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо', blank=True)
    closing_date = models.DateField(verbose_name='Дата закрытия договора', null=True, blank=True)
    prolongation = models.CharField(verbose_name='Пролонгация', max_length=40, choices=type_of_prolongation,
                                    help_text='', blank=True, default='', )
    comment = models.TextField(verbose_name='Примечание', blank=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True)
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                 null=True,
                                 related_name='contract_executor')
    doc_file = models.FileField(verbose_name='Файл документа', upload_to=contract_directory_path, blank=True)
    access = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к документу', on_delete=models.SET_NULL,
                               null=True, default=5)
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)
    actuality = models.BooleanField(verbose_name='Актуальность', default=False)

    @property
    def is_past_due(self):
        today = datetime.datetime.today()
        return today.date() < self.closing_date

    def __str__(self):
        if self.parent_category:
            if self.contract_number:
                return f'{self.parent_category}/{self.contract_counteragent}-{self.contract_number}'
            else:
                return f'{self.parent_category}/{self.contract_counteragent}-(без номера)'
        else:
            if self.contract_number:
                return f'{self.contract_counteragent}-{self.contract_number}'
            else:
                return f'{self.contract_counteragent}-(без номера)'

    def get_absolute_url(self):
        return reverse('contracts_app:detail', kwargs={'pk': self.pk})

    # def save(
    #         self, force_insert=False, force_update=False, using=None, update_fields=None
    # ):
    #     ext = self.doc_file.name.split('.')[-1]
    #     uid = '0' * (7 - len(str(self.pk))) + str(self.pk)
    #
    #     filename = f'{self.type_of_document.file_name_prefix}-{self.contract_counteragent.inn}-' \
    #                f'{self.contract_counteragent.kpp}-{self.date_conclusion}-{uid}.{ext}'
    #     self.doc_file.name = filename
    #     return super(ContractModel, self).save(force_insert=False, force_update=False, using=None, update_fields=None)


class Contract(ContractModel):
    """
    Модель договора
    """

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договора'

    def get_data(self):
        return {
            'pk': self.pk,
            'contract_number': self.contract_number,
            'date_conclusion': f'{self.date_conclusion:%d.%m.%Y} г.', #  self.date_conclusion.strftime("%d.%m.%Y"),
            'type_of_document': str(self.type_of_document),
            'type_of_contract': str(self.type_of_contract),
            'parent_category': str(self.parent_category) if self.parent_category else '--//--',
            'contract_counteragent': str(self.contract_counteragent),
            'actuality': 'Да' if self.actuality else 'Нет',
        }

    def __init__(self, *args, **kwargs):
        super(Contract, self).__init__(*args, **kwargs)


class Posts(models.Model):
    """
    Модель Posts - введена для возможности ведения заметок к договорам.
    """

    class Meta:
        verbose_name = 'Заметка'
        verbose_name_plural = 'Заметки'

    contract_number = models.ForeignKey(Contract, verbose_name='Номер договора', on_delete=models.CASCADE)
    creation_date = models.DateField(verbose_name='Дата создания', auto_now_add=True)
    post_description = models.TextField(verbose_name='Текст заметки', blank=True)
    responsible_person = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо',
                                           on_delete=models.SET_NULL, null=True)


# class Hotel(models.Model):
#     """
#         Модель Hotel - введена для возможности ведения квартир.
#     """
#
#     class Meta:
#         verbose_name = 'Квартира'
#         verbose_name_plural = 'Квартиры'
#
#     contract_number = models.ForeignKey(Contract, verbose_name='Номер договора', on_delete=models.CASCADE)
#     name = models.CharField(verbose_name='Наименование', max_length=150, default='')
#     place_production_activity = models.ForeignKey(PlaceProductionActivity, verbose_name='Наименование точки',
#                                                   on_delete=models.SET_NULL, null=True, related_name='place_production')
#     address = models.CharField(verbose_name='Адрес', max_length=250, default='', blank=True)
#     container = models.BigIntegerField(verbose_name='Количество мест', default=0)
#
#     def __str__(self):
#         return f'{self.name}'


@receiver(post_save, sender=Contract)
def rename_file_name(sender, instance, **kwargs):
    try:
        # Получаем имя сохраненного файла
        file_name = pathlib.Path(instance.doc_file.name).name
        # Получаем путь к файлу
        path_name = pathlib.Path(instance.doc_file.name).parent
        # Получаем расширение файла
        ext = file_name.split('.')[-1]
        # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
        uid = '0' * (7 - len(str(instance.pk))) + str(instance.pk)
        filename = f'{instance.type_of_document.file_name_prefix}-{instance.contract_counteragent.inn}-' \
                   f'{instance.contract_counteragent.kpp}-{instance.date_conclusion}-{uid}.{ext}'
        if file_name:
            pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', path_name, file_name),
                                pathlib.Path.joinpath(BASE_DIR, 'media', path_name, filename))

        instance.doc_file = f'contracts/{instance.contract_counteragent.inn}/' \
                            f'{instance.contract_counteragent.kpp}/{filename}'
        if file_name != filename:
            instance.save()
    except Exception as _ex:
        print(_ex)
