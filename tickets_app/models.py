"""Модели данных системы добровольных сообщений и заявок (tickets_app.models).

Модуль определяет ключевые сущности:
- Ticket: Заявка / добровольное сообщение по безопасности полетов и охране труда;
- Message: Сообщение в ленте обсуждения с поддержкой внутренних служебных заметок;
- Attachment: Прикрепленные файлы (PDF, JPG, PNG) к заявкам или сообщениям.
"""

import os
import uuid
from typing import Any, List, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def get_attachment_upload_path(instance: Any, filename: str) -> str:
    """Генерирует уникальный структурированный путь сохранения вложения.

    Формирует путь вида: tickets/attachments/YYYY/MM/DD/<uuid>.<ext>

    Args:
        instance: Экземпляр модели Attachment.
        filename (str): Исходное имя загруженного файла.

    Returns:
        str: Относительный путь для сохранения файла в MEDIA_ROOT.
    """
    ext = os.path.splitext(filename)[1].lower()
    unique_filename = f"{uuid.uuid4()}{ext}"
    now = timezone.now()
    return os.path.join(
        'tickets',
        'attachments',
        now.strftime('%Y'),
        now.strftime('%m'),
        now.strftime('%d'),
        unique_filename,
    )


def validate_file_extension(value: Any) -> None:
    """Валидирует допустимый формат и предельный размер прикрепляемого файла.

    Разрешены только документы формата PDF и изображения JPG, JPEG, PNG.
    Предельный размер файла ограничен 25 МБ во избежание перегрузки сервера.

    Args:
        value: Загруженный файл (FieldFile или UploadedFile).

    Raises:
        ValidationError: Если расширение недопустимо или размер превышает 25 МБ.
    """
    name = getattr(value, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    valid_extensions: List[str] = ['.pdf', '.jpg', '.jpeg', '.png']
    if ext not in valid_extensions:
        raise ValidationError(_('Разрешены только файлы: PDF, JPG, PNG.'))

    size = getattr(value, 'size', 0) or 0
    max_size_bytes = 25 * 1024 * 1024  # 25 MB
    if size > max_size_bytes:
        raise ValidationError(_('Размер файла не должен превышать 25 МБ.'))


class TicketStatus(models.TextChoices):
    """Статусы жизненного цикла заявки / добровольного сообщения."""

    NEW = 'new', _('Новое')
    IN_PROGRESS = 'in_progress', _('В работе')
    REDIRECTED = 'redirected', _('Переадресовано')
    RESOLVED = 'resolved', _('Решено')
    CLOSED = 'closed', _('Закрыто')


class Ticket(models.Model):
    """Заявка или добровольное сообщение по безопасности полетов и условиям труда.

    Attributes:
        title (CharField): Краткая тема / заголовок сообщения.
        description (TextField): Подробное описание инцидента или предложения.
        author (ForeignKey): Сотрудник, подавший сообщение.
        responsible (ForeignKey): Назначенный ответственный специалист (из штата).
        status (CharField): Текущий статус обработки заявки.
        parent_ticket (ForeignKey): Ссылка на родительское закрытое сообщение (обжалование).
        created_at (DateTimeField): Дата и время регистрации.
        updated_at (DateTimeField): Дата и время последнего изменения.
        resolved_at (DateTimeField): Дата и время перевода в статус 'Решено'.
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
        related_name='tickets',
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Ответственный',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_tickets',
        limit_choices_to={'is_staff': True},
    )
    status = models.CharField(
        verbose_name='Статус',
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.NEW,
    )
    parent_ticket = models.ForeignKey(
        'self',
        verbose_name='Родительское сообщение (обжалование)',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appeals',
        help_text='Если это обжалование, укажите предыдущее закрытое сообщение',
    )

    created_at = models.DateTimeField(verbose_name='Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name='Дата обновления', auto_now=True)
    resolved_at = models.DateTimeField(verbose_name='Дата решения', null=True, blank=True)

    def __str__(self) -> str:
        """Строковое представление заявки."""
        return f'#{self.pk} - {self.title}'

    def get_absolute_url(self) -> str:
        """Возвращает канонический URL детального просмотра заявки."""
        return reverse('tickets_app:detail', kwargs={'pk': self.pk})

    @property
    def is_closed_or_resolved(self) -> bool:
        """Проверяет, является ли заявка окончательно завершенной."""
        return self.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]

    @property
    def status_badge_class(self) -> str:
        """Возвращает CSS-класс бейджа в фирменном стиле БАРКОЛ."""
        badge_map = {
            TicketStatus.NEW: 'bg-primary',
            TicketStatus.IN_PROGRESS: 'bg-info text-dark',
            TicketStatus.REDIRECTED: 'bg-warning text-dark',
            TicketStatus.RESOLVED: 'bg-success',
            TicketStatus.CLOSED: 'bg-secondary',
        }
        return badge_map.get(self.status, 'bg-secondary')


class Message(models.Model):
    """Сообщение в ленте переписки по заявке.

    Attributes:
        ticket (ForeignKey): Связанная заявка.
        sender (ForeignKey): Отправитель сообщения.
        text (TextField): Текст сообщения или принятых мер.
        is_internal (BooleanField): Признак внутренней служебной заметки (скрыто от заявителя).
        created_at (DateTimeField): Дата и время публикации.
    """

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    ticket = models.ForeignKey(
        Ticket,
        verbose_name='Заявка',
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Отправитель',
        on_delete=models.CASCADE,
    )
    text = models.TextField(verbose_name='Текст сообщения')
    is_internal = models.BooleanField(
        verbose_name='Внутренняя заметка',
        default=False,
        help_text='Видно только руководству и сотрудникам',
    )
    created_at = models.DateTimeField(verbose_name='Дата создания', auto_now_add=True)

    def __str__(self) -> str:
        """Строковое представление сообщения."""
        return f'Сообщение в #{self.ticket.pk} от {self.sender}'


class Attachment(models.Model):
    """Прикрепленный файл к заявке или сообщению переписки.

    Attributes:
        file (FileField): Загруженный файл (PDF, JPG, PNG).
        message (ForeignKey): Связанное сообщение (опционально).
        ticket (ForeignKey): Связанная заявка (опционально).
        uploaded_at (DateTimeField): Дата и время загрузки.
        original_name (CharField): Исходное читаемое имя файла до хеширования.
    """

    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'

    file = models.FileField(
        verbose_name='Файл',
        upload_to=get_attachment_upload_path,
        validators=[validate_file_extension],
    )
    message = models.ForeignKey(
        Message,
        verbose_name='Сообщение',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments',
    )
    ticket = models.ForeignKey(
        Ticket,
        verbose_name='Заявка',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments',
    )
    uploaded_at = models.DateTimeField(verbose_name='Дата загрузки', auto_now_add=True)
    original_name = models.CharField(max_length=255, editable=False, null=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Переопределяет сохранение для фиксации исходного имени файла."""
        if not self.original_name and self.file:
            name = getattr(self.file, 'name', '') or ''
            self.original_name = os.path.basename(name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Строковое представление вложения."""
        return self.original_name or os.path.basename(getattr(self.file, 'name', '') or 'file')

    def clean(self) -> None:
        """Валидирует обязательную привязку файла к сообщению или заявке."""
        if not self.message and not self.ticket:
            raise ValidationError('Файл должен быть привязан к сообщению или заявке.')