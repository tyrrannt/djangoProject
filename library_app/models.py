import pathlib
import uuid

from decouple import config
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field
from loguru import logger

from customers_app.models import DataBaseUser
from djangoProject.settings import BASE_DIR

logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'))

def draft_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'blank/draft/{filename}'

def scan_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename>
    return f'blank/scan/{filename}'

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


class DocumentForm(models.Model):
    class Meta:
        verbose_name = 'Бланк документа'
        verbose_name_plural = 'Бланки документов'

    ref_key = models.UUIDField(verbose_name='Уникальный номер', default=uuid.uuid4, unique=True)
    title = models.CharField(verbose_name='Наименование', max_length=200, default='Бланк ')
    draft = models.FileField(verbose_name='Черновик', upload_to=draft_directory_path, blank=True)
    scan = models.FileField(verbose_name='Скан копия', upload_to=scan_directory_path, blank=True)
    sample = models.URLField(verbose_name='Образец заполнения', blank=True)

    def get_data(self):
        return {
            'pk': self.pk,
            'title': self.title,
            'draft': 'Есть' if self.draft else 'Отсутствует',
            'scan': 'Есть' if self.scan else 'Отсутствует',
            'sample': 'Есть' if self.sample else 'Отсутствует',
        }

    def __str__(self):
        return self.title

@receiver(post_save, sender=DocumentForm)
def rename_file_name(sender, instance, **kwargs):
    try:
        change = 0
        if instance.draft:
            # Получаем имя сохраненного файла
            draft_file_name = pathlib.Path(instance.draft.name).name
            # Получаем путь к файлу
            draft_path_name = pathlib.Path(instance.draft.name).parent
            # Получаем расширение файла
            draft_ext = draft_file_name.split('.')[-1]
            filename_draft = f'BLK-{instance.ref_key}-DRAFT.{draft_ext}'
            if draft_file_name != filename_draft:
                pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', draft_path_name, draft_file_name),
                                    pathlib.Path.joinpath(BASE_DIR, 'media', draft_path_name, filename_draft))
                instance.draft = f'{draft_path_name}/{filename_draft}'
                change = 1

        if instance.scan:
            # Получаем имя сохраненного файла
            scan_file_name = pathlib.Path(instance.scan.name).name
            # Получаем путь к файлу
            scan_path_name = pathlib.Path(instance.scan.name).parent
            # Получаем расширение файла
            scan_ext = scan_file_name.split('.')[-1]
            filename_scan = f'BLK-{instance.ref_key}-SCAN.pdf'
            if scan_file_name != filename_scan:
                pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', scan_path_name, scan_file_name),
                                    pathlib.Path.joinpath(BASE_DIR, 'media', scan_path_name, filename_scan))
                instance.scan = f'{scan_path_name}/{filename_scan}'
                change = 1

        if change == 1:
            instance.save()
    except Exception as _ex:
        logger.error(f'Ошибка при переименовании файла {_ex}')