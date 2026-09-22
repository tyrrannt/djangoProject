"""Сервисный слой модуля заявок и добровольных сообщений (tickets_app.services).

Содержит бизнес-логику асинхронной рассылки email-уведомлений через Celery,
валидации и сохранения вложений, а также управления жизненным циклом заявок.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from customers_app.models import DataBaseUser
from mailbox_app.services.email_service import UniversalEmailService
from .models import Attachment, Message, Ticket, TicketStatus, validate_file_extension

logger = logging.getLogger(__name__)


def send_ticket_notification_async(
    event_type: str,
    ticket: Ticket,
    request: Optional[HttpRequest] = None,
    actor: Optional[DataBaseUser] = None,
    new_message: Optional[Message] = None,
) -> bool:
    """Формирует и асинхронно отправляет почтовое уведомление о событии заявки через Celery.

    Использует UniversalEmailService для неблокирующей постановки задачи в очередь Celery
    (send_universal_email_task), исключая зависание веб-воркеров при работе с почтовым сервером.

    Args:
        event_type (str): Тип события ('new', 'assigned', 'resolved', 'message').
        ticket (Ticket): Экземпляр заявки СДС.
        request (Optional[HttpRequest]): Текущий HTTP-запрос для генерации абсолютного URL.
        actor (Optional[DataBaseUser]): Пользователь, инициировавший событие.
        new_message (Optional[Message]): Новое сообщение (при event_type == 'message').

    Returns:
        bool: True, если задача успешно поставлена в очередь Celery, иначе False.
    """
    try:
        if request:
            ticket_url = request.build_absolute_uri(ticket.get_absolute_url())
        else:
            base_url = getattr(settings, 'PROJECT_URL', 'https://corp.barkol.ru').rstrip('/')
            ticket_url = f"{base_url}{ticket.get_absolute_url()}"

        sender_name = str(actor) if actor else 'Система'
        author_name = str(ticket.author) if ticket.author else 'Не указан'

        context: Dict[str, Any] = {
            'event_type': event_type,
            'ticket_pk': ticket.pk,
            'ticket_title': ticket.title,
            'ticket_description': ticket.description,
            'author_name': author_name,
            'sender_name': sender_name,
            'ticket_url': ticket_url,
            'new_message_text': new_message.text if new_message else '',
            'year': timezone.now().year,
        }

        # Определяем тему письма и список получателей
        recipients: List[str] = []
        subject: str = f'Добровольное сообщение #{ticket.pk}: {ticket.title}'

        if event_type == 'new':
            subject = f'Новое добровольное сообщение #{ticket.pk}: {ticket.title}'
            leadership_users = DataBaseUser.objects.filter(
                groups__name='Руководство',
                is_active=True,
            ).exclude(email='').values_list('email', flat=True)
            recipients = list(set(leadership_users))

        elif event_type == 'assigned':
            subject = f'Вам назначено добровольное сообщение #{ticket.pk}: {ticket.title}'
            if ticket.responsible and ticket.responsible.email:
                recipients.append(ticket.responsible.email)

        elif event_type == 'resolved':
            subject = f'Добровольное сообщение #{ticket.pk} решено: {ticket.title}'
            if ticket.author and ticket.author.email:
                recipients.append(ticket.author.email)

        elif event_type == 'message':
            subject = f'Новое сообщение в заявке #{ticket.pk}: {ticket.title}'
            # Если сообщение не от автора, уведомляем автора
            if ticket.author and ticket.author.email and (not actor or actor != ticket.author):
                recipients.append(ticket.author.email)
            # Если сообщение не от ответственного, уведомляем ответственного
            if ticket.responsible and ticket.responsible.email and (not actor or actor != ticket.responsible):
                recipients.append(ticket.responsible.email)

        # Убираем дубликаты и пустые строки
        recipients = list({email.strip() for email in recipients if email and email.strip()})
        if not recipients:
            logger.info(
                "[TicketsService] Нет активных email-адресатов для события '%s' заявки #%s",
                event_type,
                ticket.pk,
            )
            return False

        html_message = render_to_string('tickets_app/email_notification.html', context)

        # Отправляем через асинхронную задачу Celery
        success = UniversalEmailService.send_async_email(
            subject=subject,
            recipient_list=recipients,
            html_message=html_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'office@barkol.ru'),
        )
        logger.info(
            "[TicketsService] Задача отправки email (событие '%s', заявка #%s) поставлена в Celery для %d получателей",
            event_type,
            ticket.pk,
            len(recipients),
        )
        return success

    except Exception as exc:
        logger.error(
            "[TicketsService] Ошибка при подготовке асинхронного email-уведомления для заявки #%s: %s",
            getattr(ticket, 'pk', 'unknown'),
            exc,
            exc_info=True,
        )
        return False


def save_ticket_attachments(
    files: Any,
    ticket: Optional[Ticket] = None,
    message: Optional[Message] = None,
) -> List[Attachment]:
    """Валидирует и сохраняет список загруженных файлов для заявки или сообщения.

    Args:
        files: Список файлов (или одиночный файл) из request.FILES или cleaned_data.
        ticket (Optional[Ticket]): Экземпляр заявки СДС.
        message (Optional[Message]): Экземпляр сообщения в переписке.

    Returns:
        List[Attachment]: Список успешно сохраненных вложений.

    Raises:
        ValidationError: При обнаружении недопустимого расширения или превышении лимита размера.
    """
    if not files:
        return []

    if not isinstance(files, (list, tuple)):
        files = [files]

    created_attachments: List[Attachment] = []

    for f in files:
        if not f:
            continue

        # Принудительно вызываем валидатор расширения и размера файла
        validate_file_extension(f)

        orig_name = getattr(f, 'name', '') or 'file'
        orig_name = os.path.basename(orig_name)

        attachment = Attachment.objects.create(
            file=f,
            ticket=ticket,
            message=message,
            original_name=orig_name,
        )
        created_attachments.append(attachment)

    return created_attachments
