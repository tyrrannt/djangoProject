import pathlib
import uuid

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from contracts_app.models import TypeDocuments
from customers_app.models import AccessLevel, Division, DataBaseUser, Job

from djangoProject.settings import BASE_DIR


# Create your models here.

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




class DocumentsOrder(Documents):
    type_of_order = [
        ('1', 'Общая деятельность'),
        ('2', 'Личный состав')
    ]

    class Meta:
        verbose_name = 'Приказ'
        verbose_name_plural = 'Приказы'
        #default_related_name = 'order'

    doc_file = models.FileField(verbose_name='Файл документа', upload_to=ord_directory_path, blank=True)
    scan_file = models.FileField(verbose_name='Скан документа', upload_to=ord_directory_path, blank=True)
    document_order_type = models.CharField(verbose_name='Тип приказа', max_length=18, choices=type_of_order)
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
        return reverse('library_app:order_list')

    def __str__(self):
        return f'№ {self.document_number} от {self.document_date} г.'


class DocumentsJobDescription(Documents):
    class Meta:
        verbose_name = 'Должностная инструкция'
        verbose_name_plural = 'Должностные инструкции'
        #default_related_name = 'job'

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
            'actuality': self.actuality,
            'executor': str(self.executor),
        }

    def get_absolute_url(self):
        return reverse('library_app:jobdescription_list')


@receiver(post_save, sender=DocumentsJobDescription)
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
