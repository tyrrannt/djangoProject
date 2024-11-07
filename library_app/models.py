import pathlib
import uuid

from decouple import config
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django_ckeditor_5.fields import CKEditor5Field
from loguru import logger

from customers_app.models import DataBaseUser, Division
from djangoProject.settings import BASE_DIR

# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


def draft_directory_path(instance, filename):
    # Получаем расширение файла
    draft_ext = filename.split('.')[-1]
    # Формируем новое название файла
    filename_draft = f'BLK-{instance.ref_key}-DRAFT.{draft_ext}'
    return f'blank/draft/{filename_draft}'


def scan_directory_path(instance, filename):
    scan_ext = filename.split('.')[-1]
    filename_scan = f'BLK-{instance.ref_key}-SCAN.{scan_ext}'
    return f'blank/scan/{filename_scan}'

def sample_directory_path(instance, filename):
    sample_ext = filename.split('.')[-1]
    filename_sample = f'BLK-{instance.ref_key}-SAMPLE.{sample_ext}'
    return f'blank/sample/{filename_sample}'


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
    draft_visible = models.BooleanField(verbose_name='Показывать черновик', default=False)
    scan = models.FileField(verbose_name='Скан копия', upload_to=scan_directory_path, blank=True)
    sample = models.FileField(verbose_name='Образец заполнения', upload_to=sample_directory_path, blank=True)
    division = models.ManyToManyField(Division, blank=True, verbose_name='Подразделение')
    executor = models.ForeignKey(DataBaseUser, verbose_name='Исполнитель', on_delete=models.SET_NULL,
                                 null=True, related_name='%(app_label)s_%(class)s_executor')
    employee = models.ManyToManyField(DataBaseUser, verbose_name='Ответственное лицо', blank=True,
                                      related_name='%(app_label)s_%(class)s_employee')

    def get_data(self):
        return {
            'pk': self.pk,
            'title': self.title,
            'division': self.division.name if self.division else '',
            'draft': 'Есть' if self.draft else 'Отсутствует',
            'scan': 'Есть' if self.scan else 'Отсутствует',
            'sample': 'Есть' if self.sample else 'Отсутствует',
        }

    def __str__(self):
        return self.title


class Contest(models.Model):
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    voting_end_date = models.DateTimeField()

    def is_submission_open(self):
        return self.start_date <= timezone.now() < self.end_date

    def is_voting_open(self):
        return self.end_date <= timezone.now() < self.voting_end_date

class Poem(models.Model):
    user = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, verbose_name='Название стиха')
    content = models.TextField(verbose_name='Содержание стиха')
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)

    def __str__(self):
        return self.title

class Vote(models.Model):
    user = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE)
    poem = models.ForeignKey(Poem, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'poem')


# @receiver(post_save, sender=DocumentForm)
# def rename_file_name(sender, instance: DocumentForm, **kwargs):
#     try:
#         change = 0
#         # if instance.draft:
#         #     # Получаем имя сохраненного файла
#         #     draft_file_name = pathlib.Path(instance.draft.name).name
#         #     # Получаем путь к файлу
#         #     draft_path_name = pathlib.Path(instance.draft.name).parent
#         #     # Получаем расширение файла
#         #     draft_ext = draft_file_name.split('.')[-1]
#         #     filename_draft = f'BLK-{instance.ref_key}-DRAFT.{draft_ext}'
#         #     if draft_file_name != filename_draft:
#         #         pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', draft_path_name, draft_file_name),
#         #                             pathlib.Path.joinpath(BASE_DIR, 'media', draft_path_name, filename_draft))
#         #         instance.draft = f'{draft_path_name}/{filename_draft}'
#         #         change = 1
#
#         if instance.scan:
#             # Получаем имя сохраненного файла
#             scan_file_name = pathlib.Path(instance.scan.name).name
#             # Получаем путь к файлу
#             scan_path_name = pathlib.Path(instance.scan.name).parent
#             # Получаем расширение файла
#             scan_ext = scan_file_name.split('.')[-1]
#             filename_scan = f'BLK-{instance.ref_key}-SCAN.pdf'
#             if scan_file_name != filename_scan:
#                 pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', scan_path_name, scan_file_name),
#                                     pathlib.Path.joinpath(BASE_DIR, 'media', scan_path_name, filename_scan))
#                 instance.scan = f'{scan_path_name}/{filename_scan}'
#                 change = 1
#
#         if instance.sample:
#             # Получаем имя сохраненного файла
#             sample_file_name = pathlib.Path(instance.sample.name).name
#             # Получаем путь к файлу
#             sample_path_name = pathlib.Path(instance.sample.name).parent
#             # Получаем расширение файла
#             sample_ext = sample_file_name.split('.')[-1]
#             filename_sample = f'BLK-{instance.ref_key}-SAMPLE.pdf'
#             if sample_file_name != filename_sample:
#                 pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', sample_path_name, sample_file_name),
#                                     pathlib.Path.joinpath(BASE_DIR, 'media', sample_path_name, filename_sample))
#                 instance.sample = f'{sample_path_name}/{filename_sample}'
#                 change = 1
#
#         if change == 1:
#             instance.save()
#     except Exception as _ex:
#         logger.exception(f'Ошибка при переименовании файла {_ex}')
