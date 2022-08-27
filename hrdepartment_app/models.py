from django.db import models

from customers_app.models import DataBaseUser, Counteragent


# Create your models here.
def contract_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'hr/medical/{instance.person.pk}/{filename}'


class Medical(models.Model):
    class Meta:
        verbose_name = ''
        verbose_name_plural = ''

    type_of = [
        ('1', 'Поступающий на работу'),
        ('2', 'Работающий')
    ]

    number = models.CharField(verbose_name='Номер', max_length=4, default='')
    person = models.ForeignKey(DataBaseUser, verbose_name='Сотрудник', on_delete=models.SET_NULL, null=True)
    organisation = models.ForeignKey(Counteragent, verbose_name='Медицинская организация',
                                     on_delete=models.SET_NULL, null=True)
    working_status = models.CharField(verbose_name='Статус', max_length=40, choices=type_of,
                                      help_text='', blank=True, default='')
    medical_direction = models.FileField(verbose_name='Файл документа', upload_to=contract_directory_path, blank=True)
