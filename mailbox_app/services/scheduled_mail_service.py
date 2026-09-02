"""Сервисный слой для работы с отложенной отправкой писем по расписанию."""

from datetime import datetime
import logging
from typing import Any, List, Optional, Tuple

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from mailbox_app.models import (
    MailAccount,
    MailContact,
    ScheduledEmail,
    ScheduledEmailAttachment,
)
from mailbox_app.services.smtp_service import SmtpMailService

logger = logging.getLogger(__name__)


def create_scheduled_email(
    user: Any,
    account: MailAccount,
    to_recipients: str,
    scheduled_at: datetime,
    subject: str = "(Без темы)",
    body_html: str = "",
    body_text: str = "",
    cc_recipients: str = "",
    bcc_recipients: str = "",
    uploaded_files: Optional[List[Any]] = None,
) -> ScheduledEmail:
    """Создает запись отложенного письма и сохраняет прикрепленные файлы.

    Args:
        user (Any): Пользователь, создающий письмо.
        account (MailAccount): Почтовый аккаунт отправителя.
        to_recipients (str): Строка адресатов через запятую.
        scheduled_at (datetime): Запланированное время отправки.
        subject (str, optional): Тема письма. По умолчанию "(Без темы)".
        body_html (str, optional): HTML-разметка тела письма.
        body_text (str, optional): Текстовая версия письма.
        cc_recipients (str, optional): Адреса в копии через запятую.
        bcc_recipients (str, optional): Адреса в скрытой копии через запятую.
        uploaded_files (list[Any], optional): Список загруженных файлов (UploadedFile).

    Returns:
        ScheduledEmail: Созданный экземпляр модели отложенного письма.

    Raises:
        ValueError: Если время запланированной отправки находится в прошлом
            или не указаны получатели.
    """
    if not to_recipients or not to_recipients.strip():
        raise ValueError("Необходимо указать хотя бы одного получателя.")

    now = timezone.now()
    if scheduled_at <= now:
        raise ValueError("Время отправки письма должно быть в будущем.")

    with transaction.atomic():
        scheduled_email = ScheduledEmail.objects.create(
            user=user,
            account=account,
            to_recipients=to_recipients.strip(),
            cc_recipients=cc_recipients.strip() if cc_recipients else "",
            bcc_recipients=bcc_recipients.strip() if bcc_recipients else "",
            subject=subject.strip() if subject else "(Без темы)",
            body_html=body_html or "",
            body_text=body_text or "",
            scheduled_at=scheduled_at,
            status=ScheduledEmail.STATUS_PENDING,
        )

        if uploaded_files:
            for f in uploaded_files:
                filename = getattr(f, "name", "attachment")
                content_type = getattr(f, "content_type", "application/octet-stream")
                content_bytes = f.read() if hasattr(f, "read") else bytes(f)
                file_size = len(content_bytes)

                attachment = ScheduledEmailAttachment(
                    scheduled_email=scheduled_email,
                    filename=filename,
                    content_type=content_type,
                    file_size=file_size,
                )
                attachment.file.save(filename, ContentFile(content_bytes), save=True)

    logger.info(
        f"[ScheduledMail] Создано запланированное письмо ID={scheduled_email.id} "
        f"пользователем {user} на {scheduled_at:%Y-%m-%d %H:%M}"
    )
    return scheduled_email


def send_single_scheduled_email(scheduled_email_id: int) -> bool:
    """Выполняет фактическую отправку одного отложенного письма по SMTP.

    Использует блокировку строки 'select_for_update(skip_locked=True)' для
    гарантии исключения параллельной отправки несколькими Celery-воркерами.

    Args:
        scheduled_email_id (int): Первичный ключ (ID) запланированного письма.

    Returns:
        bool: True в случае успешной отправки, иначе False.

    Raises:
        Exception: При критической ошибке SMTP-сервера или сетевого соединения.
    """
    scheduled_email: Optional[ScheduledEmail] = None

    with transaction.atomic():
        try:
            scheduled_email = (
                ScheduledEmail.objects.select_for_update(skip_locked=True)
                .select_related("account", "user")
                .get(id=scheduled_email_id)
            )
        except ScheduledEmail.DoesNotExist:
            logger.debug(
                f"[ScheduledMail] Письмо ID={scheduled_email_id} не найдено или заблокировано другим воркером."
            )
            return False

        if scheduled_email.status not in (
            ScheduledEmail.STATUS_PENDING,
            ScheduledEmail.STATUS_FAILED,
        ):
            logger.info(
                f"[ScheduledMail] Письмо ID={scheduled_email_id} уже имеет статус '{scheduled_email.status}', пропуск."
            )
            return False

        scheduled_email.status = ScheduledEmail.STATUS_PROCESSING
        scheduled_email.attempts_count += 1
        scheduled_email.save(update_fields=["status", "attempts_count", "updated_at"])

    account = scheduled_email.account
    to_list = scheduled_email.get_recipients_list("to")
    cc_list = scheduled_email.get_recipients_list("cc")
    bcc_list = scheduled_email.get_recipients_list("bcc")

    attachments_payload: List[Tuple[str, str, bytes]] = []
    for att in scheduled_email.attachments.all():
        try:
            with att.file.open("rb") as f:
                data = f.read()
                attachments_payload.append((att.filename, att.content_type, data))
        except Exception as file_err:
            logger.warning(
                f"[ScheduledMail] Ошибка чтения вложения ID={att.id} ({att.filename}): {file_err}"
            )

    smtp_service = SmtpMailService(
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        email_addr=account.email,
        password=account.get_password(),
        display_name=account.display_name,
        use_ssl=account.smtp_use_ssl,
        use_tls=account.smtp_use_tls,
        imap_host=account.imap_host,
        imap_port=account.imap_port,
        imap_use_ssl=account.imap_use_ssl,
    )

    try:
        smtp_service.send_email(
            to_list=to_list,
            subject=scheduled_email.subject,
            body_html=scheduled_email.body_html,
            body_text=scheduled_email.body_text,
            cc_list=cc_list,
            bcc_list=bcc_list,
            attachments=attachments_payload if attachments_payload else None,
        )

        with transaction.atomic():
            scheduled_email.status = ScheduledEmail.STATUS_SENT
            scheduled_email.sent_at = timezone.now()
            scheduled_email.last_error = ""
            scheduled_email.save(
                update_fields=["status", "sent_at", "last_error", "updated_at"]
            )

            # Автосохранение адресатов в адресную книгу
            all_recipients = to_list + cc_list + bcc_list
            for email_addr in all_recipients:
                if "@" in email_addr:
                    try:
                        MailContact.objects.get_or_create(
                            user=scheduled_email.user,
                            email=email_addr.lower(),
                            defaults={"name": email_addr.split("@")[0], "source": "auto"},
                        )
                    except Exception:
                        pass

        logger.info(
            f"[ScheduledMail] Запланированное письмо ID={scheduled_email.id} "
            f"успешно отправлено на {to_list}"
        )
        return True

    except Exception as exc:
        err_msg = str(exc)
        logger.error(
            f"[ScheduledMail] Сбой при отправке письма ID={scheduled_email.id}: {err_msg}",
            exc_info=True,
        )
        with transaction.atomic():
            if scheduled_email.attempts_count >= scheduled_email.max_attempts:
                scheduled_email.status = ScheduledEmail.STATUS_FAILED
            else:
                scheduled_email.status = ScheduledEmail.STATUS_PENDING
            scheduled_email.last_error = err_msg
            scheduled_email.save(
                update_fields=["status", "last_error", "updated_at"]
            )
        raise exc


def cancel_scheduled_email(scheduled_email_id: int, user: Any) -> bool:
    """Отменяет отправку отложенного письма.

    Args:
        scheduled_email_id (int): ID запланированного письма.
        user (Any): Пользователь, запрашивающий отмену.

    Returns:
        bool: True, если письмо успешно отменено.

    Raises:
        PermissionError: Если у пользователя нет прав на данное письмо.
        ValueError: Если текущий статус письма не позволяет его отменить.
    """
    try:
        scheduled_email = ScheduledEmail.objects.get(id=scheduled_email_id)
    except ScheduledEmail.DoesNotExist:
        raise ValueError("Запланированное письмо не найдено.")

    if scheduled_email.user != user and not getattr(user, "is_superuser", False):
        raise PermissionError("У вас нет прав для отмены этого письма.")

    if not scheduled_email.can_cancel:
        raise ValueError(
            f"Невозможно отменить письмо со статусом '{scheduled_email.get_status_display()}'."
        )

    scheduled_email.status = ScheduledEmail.STATUS_CANCELLED
    scheduled_email.save(update_fields=["status", "updated_at"])
    logger.info(
        f"[ScheduledMail] Письмо ID={scheduled_email.id} отменено пользователем {user}."
    )
    return True


def reschedule_email(
    scheduled_email_id: int,
    new_scheduled_at: datetime,
    user: Any,
) -> bool:
    """Изменяет запланированное время отправки письма.

    Args:
        scheduled_email_id (int): ID запланированного письма.
        new_scheduled_at (datetime): Новая дата и время отправки.
        user (Any): Пользователь, запрашивающий перенос.

    Returns:
        bool: True в случае успешного переноса.

    Raises:
        PermissionError: Если у пользователя нет прав на данное письмо.
        ValueError: Если новое время в прошлом или статус не позволяет перенос.
    """
    if new_scheduled_at <= timezone.now():
        raise ValueError("Новое время отправки должно быть в будущем.")

    try:
        scheduled_email = ScheduledEmail.objects.get(id=scheduled_email_id)
    except ScheduledEmail.DoesNotExist:
        raise ValueError("Запланированное письмо не найдено.")

    if scheduled_email.user != user and not getattr(user, "is_superuser", False):
        raise PermissionError("У вас нет прав для редактирования этого письма.")

    if not scheduled_email.can_reschedule:
        raise ValueError(
            f"Невозможно изменить время для письма со статусом '{scheduled_email.get_status_display()}'."
        )

    scheduled_email.scheduled_at = new_scheduled_at
    scheduled_email.status = ScheduledEmail.STATUS_PENDING
    scheduled_email.save(update_fields=["scheduled_at", "status", "updated_at"])
    logger.info(
        f"[ScheduledMail] Письмо ID={scheduled_email.id} перенесено на {new_scheduled_at:%Y-%m-%d %H:%M}."
    )
    return True


def process_due_scheduled_emails() -> int:
    """Выбирает созревшие письма из очереди и инициирует их отправку.

    Вызывается планировщиком Celery Beat периодически (раз в минуту).

    Returns:
        int: Количество писем, переданных на отправку.
    """
    from mailbox_app.tasks import send_scheduled_email_task

    now = timezone.now()
    due_email_ids = list(
        ScheduledEmail.objects.filter(
            status=ScheduledEmail.STATUS_PENDING,
            scheduled_at__lte=now,
        ).values_list("id", flat=True)[:50]
    )

    if not due_email_ids:
        return 0

    logger.info(
        f"[ScheduledMail] Найдено {len(due_email_ids)} писем, готовых к отправке: {due_email_ids}"
    )

    dispatched_count = 0
    for email_id in due_email_ids:
        try:
            send_scheduled_email_task.delay(email_id)
            dispatched_count += 1
        except Exception as e:
            logger.error(
                f"[ScheduledMail] Ошибка диспетчеризации задачи для письма ID={email_id}: {e}"
            )

    return dispatched_count


def get_scheduled_email_for_user(scheduled_email_id: int, user: Any) -> ScheduledEmail:
    """Возвращает отложенное письмо с проверкой прав доступа пользователя.

    Args:
        scheduled_email_id (int): Идентификатор отложенного письма.
        user (Any): Пользователь Django, запрашивающий доступ.

    Returns:
        ScheduledEmail: Объект отложенного письма.

    Raises:
        ValueError: Если письмо не найдено.
        PermissionError: Если у пользователя нет прав на просмотр письма.
    """
    try:
        email_obj = (
            ScheduledEmail.objects.select_related("account", "user")
            .prefetch_related("attachments")
            .get(id=scheduled_email_id)
        )
    except ScheduledEmail.DoesNotExist:
        raise ValueError("Запланированное письмо не найдено.")

    if email_obj.user != user and not getattr(user, "is_superuser", False):
        raise PermissionError("У вас нет прав для доступа к этому письму.")

    return email_obj


def update_scheduled_email(
    scheduled_email_id: int,
    user: Any,
    to_recipients: str,
    subject: str,
    body_html: str,
    scheduled_at: datetime,
    cc_recipients: str = "",
    bcc_recipients: str = "",
    body_text: str = "",
    new_files: Optional[List[Any]] = None,
    delete_attachment_ids: Optional[List[int]] = None,
) -> ScheduledEmail:
    """Обновляет параметры, адресатов, текст и вложения отложенного письма.

    Args:
        scheduled_email_id (int): Идентификатор письма.
        user (Any): Пользователь, вносящий изменения.
        to_recipients (str): Получатели письма через запятую.
        subject (str): Тема письма.
        body_html (str): HTML-разметка тела письма.
        scheduled_at (datetime): Новое запланированное время отправки.
        cc_recipients (str, optional): Копия адресатов.
        bcc_recipients (str, optional): Скрытая копия.
        body_text (str, optional): Текстовая версия письма.
        new_files (list[Any], optional): Новые файлы для прикрепления.
        delete_attachment_ids (list[int], optional): ID вложений для удаления.

    Returns:
        ScheduledEmail: Обновленный экземпляр письма.

    Raises:
        ValueError: Если письмо не может быть отредактировано или дата в прошлом.
        PermissionError: Если у пользователя нет прав доступа.
    """
    if not to_recipients or not to_recipients.strip():
        raise ValueError("Необходимо указать хотя бы одного получателя.")

    now = timezone.now()
    if scheduled_at <= now:
        raise ValueError("Время отправки письма должно быть в будущем.")

    scheduled_email = get_scheduled_email_for_user(scheduled_email_id, user)

    if scheduled_email.status in (
        ScheduledEmail.STATUS_PROCESSING,
        ScheduledEmail.STATUS_SENT,
    ):
        raise ValueError(
            f"Нельзя редактировать письмо в статусе '{scheduled_email.get_status_display()}'."
        )

    with transaction.atomic():
        scheduled_email.to_recipients = to_recipients.strip()
        scheduled_email.cc_recipients = cc_recipients.strip() if cc_recipients else ""
        scheduled_email.bcc_recipients = bcc_recipients.strip() if bcc_recipients else ""
        scheduled_email.subject = subject.strip() if subject else "(Без темы)"
        scheduled_email.body_html = body_html or ""
        scheduled_email.body_text = body_text or ""
        scheduled_email.scheduled_at = scheduled_at
        # При редактировании возвращаем статус в очередь и сбрасываем ошибку
        scheduled_email.status = ScheduledEmail.STATUS_PENDING
        scheduled_email.last_error = ""
        scheduled_email.save()

        # Удаление выбранных старых вложений
        if delete_attachment_ids:
            for att in scheduled_email.attachments.filter(id__in=delete_attachment_ids):
                try:
                    att.file.delete(save=False)
                except Exception as e:
                    logger.warning(
                        f"[ScheduledMail] Ошибка физического удаления файла {att.filename}: {e}"
                    )
                att.delete()

        # Добавление новых вложений
        if new_files:
            for upload in new_files:
                file_content = upload.read()
                filename = upload.name
                content_type = getattr(
                    upload, "content_type", "application/octet-stream"
                )
                file_size = upload.size

                attachment = ScheduledEmailAttachment(
                    scheduled_email=scheduled_email,
                    filename=filename,
                    content_type=content_type,
                    file_size=file_size,
                )
                attachment.file.save(filename, ContentFile(file_content), save=True)

    logger.info(
        f"[ScheduledMail] Письмо ID={scheduled_email.id} успешно обновлено пользователем {user}."
    )
    return scheduled_email

