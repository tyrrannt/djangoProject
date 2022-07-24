from django.db import models


# Create your models here.

class PortalProperty(models.Model):
    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'

    portal_name = models.CharField(verbose_name='Название портала', max_length=100, blank=True,
                                   default='ООО Авиакомпания "БАРКОЛ"')
    portal_paginator = models.IntegerField(verbose_name='Пагинация по умолчанию', default=10)
