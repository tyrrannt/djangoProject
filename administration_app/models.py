from django.db import models

from customers_app.models import DataBaseUser


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

#ToDo: Доработать генератор меню
def make_menu():
    items = MainMenu.objects.all()
    for item in items:
        urls = f'<li class="nav-parent"> <a class="nav-link" href="#"><i class="bx bx-file" aria-hidden="true"></i><span>{item}</span></a></li>'


class BaseItems(models.Model):
    class Meta:
        abstract = True

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='', help_text='')
    code = models.CharField(verbose_name='Код', max_length=10, default='', help_text='')
    name = models.CharField(verbose_name='Название', max_length=128, default='')
    active = models.BooleanField(verbose_name='Активность', default=True)
