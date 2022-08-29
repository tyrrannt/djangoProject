import pathlib

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from administration_app.utils import Med
from customers_app.models import DataBaseUser, Counteragent, HarmfulWorkingConditions
from djangoProject.settings import BASE_DIR


# Create your models here.
def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'hr/medical/{filename}'


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
    harmful = models.ForeignKey(HarmfulWorkingConditions, verbose_name='Вредные условия труда', on_delete=models.SET_NULL, null=True)

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