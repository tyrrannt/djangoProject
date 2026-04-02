import os
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from customers_app.models import DataBaseUser


def validate_file_extension(value):
    """Валидация расширений файлов"""
    ext = os.path.splitext(value.name)[1]
    valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    if ext.lower() not in valid_extensions:
        raise ValidationError(_('Разрешены только файлы: PDF, JPG, PNG'))


class TicketStatus(models.TextChoices):
    """Статусы заявки"""
    NEW = 'new', _('Новая')
    IN_PROGRESS = 'in_progress', _('В работе')
    REDIRECTED = 'redirected', _('Переадресована')
    RESOLVED = 'resolved', _('Решена')
    CLOSED = 'closed', _('Закрыта')


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
        verbose_name='Родительская заявка (обжалование)',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appeals',
        help_text='Если это обжалование, укажите предыдущую закрытую заявку'
    )
    created_at = models.DateTimeField(verbose_name='Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name='Дата обновления', auto_now=True)
    resolved_at = models.DateTimeField(verbose_name='Дата решения', null=True, blank=True)

    def __str__(self):
        return f'#{self.pk} - {self.title}'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('tickets_app:detail', kwargs={'pk': self.pk})

    def clean(self):
        """Проверка корректности обжалования"""
        if self.parent_ticket:
            if self.parent_ticket.author != self.author:
                raise ValidationError('Можно обжаловать только свои заявки')
            if self.parent_ticket.status != TicketStatus.CLOSED:
                raise ValidationError('Можно обжаловать только закрытые заявки')


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
        upload_to='tickets/attachments/%Y/%m/%d/',
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

    def __str__(self):
        return os.path.basename(self.file.name)

    def clean(self):
        """Файл должен быть привязан либо к сообщению, либо к заявке"""
        if not self.message and not self.ticket:
            raise ValidationError('Файл должен быть привязан к сообщению или заявке')