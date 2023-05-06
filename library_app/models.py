import pathlib
import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field

from customers_app.models import DataBaseUser


class HashTag(models.Model):
    class Meta:
        verbose_name = 'Хэштэг'
        verbose_name_plural = 'Хэштэги'

    title = models.CharField('Хэштег', max_length=100)

    def __str__(self):
        return self.title


class HelpCategory(models.Model):
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    title = models.CharField('Наименование', max_length=100)

    def __str__(self):
        return self.title


class HelpTopic(models.Model):
    class Meta:
        verbose_name = 'Топик'
        verbose_name_plural = 'Топики'

    title = models.CharField('Заголовок', max_length=200)
    category = models.ForeignKey(HelpCategory, on_delete=models.SET_NULL, blank=True, null=True)
    text = CKEditor5Field('Содержание', config_name='extends', blank=True)
    hash_tag = models.ManyToManyField(HashTag, blank=True)

    def __str__(self):
        return self.title

    def get_data(self):
        hash_tag = [str(item) for item in self.hash_tag.iterator()]
        return {
            'pk': self.pk,
            'title': self.title,
            'category': self.category.title,
            'hash_tag': '; '.join(hash_tag),

        }

    def get_absolute_url(self):
        return reverse('library_app:help_list')

