import pathlib

from django.db import models
from django.urls import reverse

from contracts_app.models import TypeDocuments
from customers_app.models import AccessLevel, Division, DataBaseUser

from djangoProject.settings import BASE_DIR


# Create your models here.

def document_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'library/{filename}'




class Documents(models.Model):
    class Meta:
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    type_of_document = models.ForeignKey(TypeDocuments, verbose_name='Тип документа', on_delete=models.SET_NULL,
                                         null=True)
    date_entry = models.DateField(verbose_name='Дата ввода информации', auto_now_add=True)
    executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                 null=True, related_name='document_executor')
    document_date = models.DateField(verbose_name='Дата документа', default='')
    document_number = models.CharField(verbose_name='Номер документа', max_length=10, default='')
    doc_file = models.FileField(verbose_name='Файл документа', upload_to=document_directory_path, blank=True)
    access = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к документу', on_delete=models.SET_NULL,
                               null=True, default=5)
    document_division = models.ManyToManyField(Division, verbose_name='Принадлежность к подразделению')
    employee = models.ManyToManyField(DataBaseUser, verbose_name='Ответственное лицо', blank=True,
                                      related_name='document_employee')
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)
    validity_period_start = models.DateField(verbose_name='Документ действует с', default='')
    validity_period_end = models.DateField(verbose_name='Документ действует по', default='')
    actuality = models.BooleanField(verbose_name='Актуальность', default=False)
    previous_document = models.URLField(verbose_name='Предшествующий документ')


    def get_absolute_url(self):
        return reverse('library_app:documents', kwargs={'pk': self.pk})

# @receiver(post_save, sender=Documents)
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
