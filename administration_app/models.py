# models.py
import datetime
import pathlib
import uuid

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
import os

# from customers_app.models import DataBaseUser, Job


# Create your models here.

class PortalProperty(models.Model):
    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'

    portal_name = models.CharField(verbose_name='Название портала', max_length=100, blank=True,
                                   default='ООО Авиакомпания "БАРКОЛ"')
    portal_paginator = models.IntegerField(verbose_name='Пагинация по умолчанию', default=10)
    portal_session = models.BigIntegerField(verbose_name='Длительность сессии', default=3600)
    mobile_app_version = models.CharField(verbose_name='Версия мобильного приложения', max_length=20, blank=True, default='1.0.0')

    def __str__(self):
        return str(self.pk)

    def get_data(self):
        return {
            'portal_name': self.portal_name,
            'portal_paginator': self.portal_paginator,
            'portal_session': self.portal_session,
            'mobile_app_version': self.mobile_app_version,
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
    job_list = models.ManyToManyField('customers_app.Job', verbose_name='Список должностей', blank=True)
    count = models.IntegerField(verbose_name='Количество уведомлений', default=0)


def get_template_document_upload_path(instance, filename):
    """
    Генерирует путь для сохранения файла шаблона:

    Args:
        instance: Экземпляр модели, содержащий FileField.
        filename (str): Оригинальное имя файла.

    Returns:
        str: Относительный путь для сохранения файла.
    """
    # Извлекаем расширение с помощью pathlib — более надёжно
    ext = pathlib.Path(filename).suffix.lower()

    # Генерируем уникальное имя
    unique_name = f"{uuid.uuid4().hex}{ext}"

    # Определяем дату: из поля или текущая
    upload_date = instance.start_date or timezone.now().date()
    if isinstance(upload_date, datetime.datetime):
        upload_date = upload_date.date()

    date_path = upload_date.strftime("%Y/%m/%d")

    return f"templates/documents/{date_path}/{unique_name}"


class TemplateDocument(models.Model):
    """
    Модель для хранения версионированных шаблонов документов
    """
    TEMPLATE_TYPES = [
        ('word', 'Microsoft Word'),
        ('excel', 'Microsoft Excel'),
        ('other', 'Другой тип'),
    ]

    # Основная информация
    name = models.CharField('Наименование шаблона', max_length=255)
    unique_code = models.SlugField('Уникальный код шаблона', max_length=100, unique=True)
    template_type = models.CharField('Тип шаблона', max_length=20, choices=TEMPLATE_TYPES, default='word')

    # Файл шаблона
    template_file = models.FileField(
        'Файл шаблона',
        upload_to=get_template_document_upload_path,
        help_text='Поддерживаются форматы: .docx, .xlsx, .doc, .xls'
    )

    # Период действия
    start_date = models.DateTimeField('Дата начала использования', default=timezone.now)
    end_date = models.DateTimeField('Дата окончания использования', null=True, blank=True)

    # Метаданные
    is_active = models.BooleanField('Активен', default=True)
    version = models.PositiveIntegerField('Версия', default=1)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    # Дополнительная информация
    description = models.TextField('Описание', blank=True)
    created_by = models.ForeignKey(
        'customers_app.DataBaseUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал'
    )

    class Meta:
        verbose_name = 'Шаблон документа'
        verbose_name_plural = 'Шаблоны документов'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['unique_code', 'is_active']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version}) - {self.unique_code}"

    def clean(self):
        """Валидация дат и файлов"""
        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError('Дата окончания должна быть позже даты начала')

        # Проверка расширения файла
        if self.template_file:
            ext = os.path.splitext(self.template_file.name)[1].lower()
            valid_extensions = ['.docx', '.xlsx', '.doc', '.xls']
            if ext not in valid_extensions:
                raise ValidationError(f'Неподдерживаемый формат файла. Разрешены: {", ".join(valid_extensions)}')

    def save(self, *args, **kwargs):
        """Автоматическое управление версиями и активностью"""
        # Если это новый шаблон с таким же unique_code
        if not self.pk:
            last_template = TemplateDocument.objects.filter(
                unique_code=self.unique_code
            ).order_by('-version').first()

            if last_template:
                self.version = last_template.version + 1
                # Деактивируем предыдущие активные шаблоны
                TemplateDocument.objects.filter(
                    unique_code=self.unique_code,
                    is_active=True
                ).update(is_active=False)

        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_active_template(cls, unique_code):
        """
        Получить активный шаблон по уникальному коду на текущий момент
        """
        now = timezone.now()
        return cls.objects.filter(
            unique_code=unique_code,
            is_active=True,
            start_date__lte=now,
        ).exclude(
            end_date__lt=now
        ).first()

    @property
    def is_currently_valid(self):
        """Проверяет, действителен ли шаблон сейчас"""
        now = timezone.now()
        return (self.start_date <= now and
                (self.end_date is None or self.end_date > now) and
                self.is_active)
