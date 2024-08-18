from django.db import models

from customers_app.models import DataBaseUser, Job


# Create your models here.

class PortalProperty(models.Model):
    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'

    portal_name = models.CharField(verbose_name='Название портала', max_length=100, blank=True,
                                   default='ООО Авиакомпания "БАРКОЛ"')
    portal_paginator = models.IntegerField(verbose_name='Пагинация по умолчанию', default=10)
    portal_session = models.BigIntegerField(verbose_name='Длительность сессии', default=3600)

    def __str__(self):
        return str(self.pk)

    def get_data(self):
        return {
            'portal_name': self.portal_name,
            'portal_paginator': self.portal_paginator,
            'portal_session': self.portal_session,
        }


class MetaMainMenu(models.Model):
    class Meta:
        abstract = True

    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(verbose_name='Название пункта меню', max_length=128, unique=True)
    url_address = models.CharField(verbose_name='URL адрес пункта', max_length=100)
    description = models.TextField(verbose_name='Описание пункта меню', blank=True)

    def __str__(self):
        if self.parent:
            return f'{self.parent}/{self.name}'
        else:
            return self.name


class MainMenu(MetaMainMenu):
    class Meta:
        verbose_name = 'Меню'
        verbose_name_plural = 'Меню'

    def __init__(self, *args, **kwargs):
        super(MainMenu, self).__init__(*args, **kwargs)


# ToDo: Доработать генератор меню
def make_menu():
    urls = ''
    items = MainMenu.objects.all()
    for item in items:
        urls = f'<li class="nav-parent"> <a class="nav-link" href="#"><i class="bx bx-file" aria-hidden="true">' \
               f'</i><span>{item}</span></a></li>'
    return urls


class BaseItems(models.Model):
    """
    Описание
        Класс BaseItems представляет собой базовый класс для моделей сущностей, содержащих уникальный номер (ref_key),
        код (code), название (name) и статус активности (active). Этот класс является абстрактным, что означает, что
        он не может быть создан напрямую и предназначен для наследования другими моделями.
    Поля
        ref_key: Уникальный номер сущности. Тип: строка (до 37 символов). Значение по умолчанию — пустая строка.
        code: Код сущности. Тип: строка (до 10 символов). Значение по умолчанию — пустая строка.
        name: Название сущности. Тип: строка (до 128 символов). Значение по умолчанию — пустая строка.
        active: Статус активности сущности. Тип: логический тип (True/False). Значение по умолчанию — True.
    Примечание
        Этот класс предназначен для наследования другими моделями, которые будут расширять или модифицировать его
        поля и поведение.
    """
    class Meta:
        abstract = True

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='', help_text='')
    code = models.CharField(verbose_name='Код', max_length=10, default='', help_text='')
    name = models.CharField(verbose_name='Название', max_length=128, default='')
    active = models.BooleanField(verbose_name='Активность', default=True)


class Notification(models.Model):
    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['name']
        unique_together = ('name', 'document_type', 'division_type')

    name = models.CharField(verbose_name='Наименование', max_length=128, default='')
    document_type = models.CharField(verbose_name='Тип документа', max_length=3, default='')
    division_type = models.CharField(verbose_name='Тип подразделения', max_length=128, default='')
    job_list = models.ManyToManyField(Job, verbose_name='Список должностей', blank=True)
    count = models.IntegerField(verbose_name='Количество уведомлений', default=0)
