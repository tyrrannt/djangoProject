import os
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from customers_app.models import DataBaseUser


def get_attachment_upload_path(instance, filename):
    # Извлекаем расширение файла (например, .jpg)
    ext = filename.split('.')[-1]
    # Генерируем UUID и создаем новое имя
    filename = f"{uuid.uuid4()}.{ext}"

    # Формируем путь: tickets/attachments/YYYY/MM/DD/uuid.ext
    # Используем timezone.now() для консистентности с Django
    now = timezone.now()
    return os.path.join(
        'tickets', 'attachments',
        now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'),
        filename
    )


def validate_file_extension(value):
    """Валидация расширений файлов"""
    ext = os.path.splitext(value.name)[1]
    valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    if ext.lower() not in valid_extensions:
        raise ValidationError(_('Разрешены только файлы: PDF, JPG, PNG'))


class TicketStatus(models.TextChoices):
    """Статусы заявки"""
    NEW = 'new', _('Новое')
    IN_PROGRESS = 'in_progress', _('В работе')
    REDIRECTED = 'redirected', _('Переадресовано')
    RESOLVED = 'resolved', _('Решено')
    CLOSED = 'closed', _('Закрыто')


class Ticket(models.Model):
    """
    Заявка (жалоба/предложение)
    """
    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']

    title = models.CharField(verbose_name='Заголовок', max_length=200)
    description = models.TextField(verbose_name='Описание')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Автор',
        on_delete=models.CASCADE,
        related_name='tickets'
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Ответственный',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_tickets',
        limit_choices_to={'is_staff': True}
    )
    status = models.CharField(
        verbose_name='Статус',
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.NEW
    )
    parent_ticket = models.ForeignKey(
        'self',
        verbose_name='Родительское сообщение (обжалование)',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appeals',
        help_text='Если это обжалование, укажите предыдущее закрытое сообщение'
    )

    created_at = models.DateTimeField(verbose_name='Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name='Дата обновления', auto_now=True)
    resolved_at = models.DateTimeField(verbose_name='Дата решения', null=True, blank=True)

    def __str__(self):
        return f'#{self.pk} - {self.title}'

    def get_absolute_url(self):
        return reverse('tickets_app:detail', kwargs={'pk': self.pk})




class Message(models.Model):
    """
    Сообщение в заявке (история переписки)
    """
    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    ticket = models.ForeignKey(
        Ticket,
        verbose_name='Заявка',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Отправитель',
        on_delete=models.CASCADE
    )
    text = models.TextField(verbose_name='Текст сообщения')
    is_internal = models.BooleanField(
        verbose_name='Внутренняя заметка',
        default=False,
        help_text='Видно только руководству и сотрудникам'
    )
    created_at = models.DateTimeField(verbose_name='Дата создания', auto_now_add=True)

    def __str__(self):
        return f'Сообщение в #{self.ticket.pk} от {self.sender}'


class Attachment(models.Model):
    """
    Вложения к заявкам и сообщениям
    """
    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'

    file = models.FileField(
        verbose_name='Файл',
        upload_to=get_attachment_upload_path,
        validators=[validate_file_extension]
    )
    message = models.ForeignKey(
        Message,
        verbose_name='Сообщение',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments'
    )
    ticket = models.ForeignKey(
        Ticket,
        verbose_name='Заявка',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments'
    )
    uploaded_at = models.DateTimeField(verbose_name='Дата загрузки', auto_now_add=True)

    original_name = models.CharField(max_length=255, editable=False, null=True)

    def save(self, *args, **kwargs):
        if not self.original_name and self.file:
            self.original_name = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return os.path.basename(self.file.name)

    def clean(self):
        """Файл должен быть привязан либо к сообщению, либо к заявке"""
        if not self.message and not self.ticket:
            raise ValidationError('Файл должен быть привязан к сообщению или заявке')