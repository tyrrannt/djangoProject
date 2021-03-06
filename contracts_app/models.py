from django.db import models
from django.urls import reverse

from customers_app.models import DataBaseUser, Counteragent, AccessLevel, Division


# Create your models here.
def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'contracts/{instance.contract_counteragent.inn}/{instance.contract_counteragent.kpp}/{filename}'


class TypeDocuments(models.Model):
    class Meta:
        verbose_name = 'Тип документа'
        verbose_name_plural = 'Тип документов'

    type_document = models.CharField(verbose_name='Тип документа', max_length=50, blank=True, null=True,
                                     help_text='')
    file_name_prefix = models.CharField(verbose_name='', max_length=3)

    def __str__(self):
        return f'{self.type_document}'


class TypeContract(models.Model):
    class Meta:
        verbose_name = 'Тип договора'
        verbose_name_plural = 'Тип договоров'

    type_contract = models.CharField(verbose_name='Тип договора', max_length=50, blank=True, null=True,
                                     help_text='')

    def __str__(self):
        return f'{self.type_contract}'


class TypeProperty(models.Model):
    class Meta:
        verbose_name = 'Тип имущества'
        verbose_name_plural = 'Тип имущества'

    type_property = models.CharField(verbose_name='Тип имущества', max_length=50, blank=True, null=True,
                                     help_text='')

    def __str__(self):
        return f'{self.type_property}'


class Estate(models.Model):
    class Meta:
        verbose_name = 'Имущество'
        verbose_name_plural = 'Имущество'

    type_property = models.ForeignKey(TypeProperty, on_delete=models.SET_NULL, null=True)
    release_date = models.DateField(verbose_name='дата выпуска')


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
    contract_counteragent = models.ForeignKey(Counteragent, verbose_name='Сторона договора', on_delete=models.SET_NULL,
                                              null=True)
    internal_number = models.CharField(verbose_name='Номер в папке', max_length=50, blank=True, null=True,
                                       help_text='')
    contract_number = models.CharField(verbose_name='Номер договора', max_length=50, blank=True, null=True,
                                       help_text='')
    date_conclusion = models.DateField(verbose_name='Дата заключения договора')
    subject_contract = models.TextField(verbose_name='Предмет договора', blank=True)
    cost = models.FloatField(verbose_name='Стоимость', default=0, null=True, blank=True)
    type_of_contract = models.ForeignKey(TypeContract, verbose_name='Тип договора', on_delete=models.SET_NULL,
                                         null=True)
    type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
                                         null=True)
    divisions = models.ManyToManyField(Division, verbose_name='Подразделение')
    type_property = models.ForeignKey(TypeProperty, verbose_name='Тип имущества', on_delete=models.SET_NULL, null=True)
    employee = models.ManyToManyField(DataBaseUser, verbose_name='Ответственное лицо', blank=True)
    closing_date = models.DateField(verbose_name='Дата закрытия договора', null=True, blank=True)
    prolongation = models.CharField(verbose_name='Пролонгация', max_length=40, choices=type_of_prolongation,
                                    help_text='',
                                    blank=True, null=True, )
    comment = models.TextField(verbose_name='Примечание', blank=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True)
    executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL, null=True,
                                 related_name='contract_executor')
    doc_file = models.FileField(verbose_name='Файл документа', upload_to=contract_directory_path, blank=True)
    access = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к документу', on_delete=models.SET_NULL,
                               null=True)
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)

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


class Contract(ContractModel):
    """
    Модель договора
    """

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договора'

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
    responsible_person = models.ForeignKey(DataBaseUser, verbose_name='Ответственное лицо', on_delete=models.SET_NULL,
                                           null=True)
