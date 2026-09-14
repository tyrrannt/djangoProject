"""Фоновые задачи Celery для приложения корпоративной почты mailbox_app."""

import logging
from typing import Any, Dict, List, Optional

from celery import shared_task

from mailbox_app.services.scheduled_mail_service import (
    process_due_scheduled_emails,
    send_single_scheduled_email,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_scheduled_emails_task(self) -> int:
    """Периодическая задача Celery Beat для проверки очереди отложенных писем.

    Выбирает все запланированные письма со статусом 'pending', у которых
    наступило время отправки, и ставит задачи их индивидуальной отправки в очередь.

    Args:
        self: Экземпляр запущенной задачи Celery.

    Returns:
        int: Количество поставленных в очередь на отправку писем.
    """
    logger.info("[Celery:ScheduledMail] Старт периодической проверки очереди отложенных писем.")
    try:
        count = process_due_scheduled_emails()
        logger.info(
            f"[Celery:ScheduledMail] Успешно завершена проверка очереди. Отправлено на выполнение: {count} писем."
        )
        return count
    except Exception as exc:
        logger.error(f"[Celery:ScheduledMail] Ошибка при обработке очереди писем: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical("[Celery:ScheduledMail] Превышен лимит повторных попыток для process_scheduled_emails_task.")
            return 0


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_scheduled_email_task(self, scheduled_email_id: int) -> bool:
    """Фоновая задача Celery для отправки одного конкретного отложенного письма.

    Args:
        self: Экземпляр запущенной задачи Celery.
        scheduled_email_id (int): Первичный ключ (ID) запланированного письма в БД.

    Returns:
        bool: True при успешной отправке письма, иначе False.
    """
    logger.info(f"[Celery:ScheduledMail] Старт отправки запланированного письма ID={scheduled_email_id}.")
    try:
        success = send_single_scheduled_email(scheduled_email_id)
        if success:
            logger.info(
                f"[Celery:ScheduledMail] Письмо ID={scheduled_email_id} успешно отправлено адресатам."
            )
        else:
            logger.warning(
                f"[Celery:ScheduledMail] Письмо ID={scheduled_email_id} не было отправлено (пропущено или заблокировано)."
            )
        return success
    except Exception as exc:
        logger.error(
            f"[Celery:ScheduledMail] Ошибка при отправке письма ID={scheduled_email_id}: {exc}",
            exc_info=True,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                f"[Celery:ScheduledMail] Исчерпан лимит повторных попыток для письма ID={scheduled_email_id}."
            )
            return False


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def poll_mailboxes_unread_task(self) -> dict:
    """Периодическая фоновая задача Celery Beat для серверного опроса почтовых ящиков.

    Периодически проверяет статус непрочитанных писем на сервере IMAP (Kerio Connect)
    для всех активных корпоративных (Mailbox) и персональных (MailAccount) ящиков,
    актуализирует кэш счетчиков и рассылает Web Push уведомления о новых письмах.

    Args:
        self: Экземпляр запущенной задачи Celery.

    Returns:
        dict: Сводный результат выполнения опроса (число ящиков, новые письма, ошибки).
    """
    from mailbox_app.services.mail_poller_service import poll_all_active_mailboxes

    logger.info("[Celery:MailPoller] Старт периодического опроса почтовых ящиков.")
    try:
        summary = poll_all_active_mailboxes()
        logger.info(
            f"[Celery:MailPoller] Опрос успешно завершен: "
            f"ящиков={summary.get('processed')}, новых писем={summary.get('new_emails_total')}."
        )
        return summary
    except Exception as exc:
        logger.error(f"[Celery:MailPoller] Критическая ошибка при опросе ящиков: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical("[Celery:MailPoller] Исчерпан лимит повторных попыток для poll_mailboxes_unread_task.")
            return {"status": "error", "error": str(exc)}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_universal_email_task(
    self,
    subject: str,
    recipient_list: List[str],
    html_message: str,
    plain_message: Optional[str] = None,
    from_email: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Универсальная фоновая задача Celery для отправки email-сообщений во всех приложениях проекта.

    Позволяет любому сервису или представлению асинхронно отправлять email-уведомления
    в фоновом воркере Celery, исключая блокировку веб-потока и зависание интерфейса.

    Args:
        self: Экземпляр запущенной задачи Celery.
        subject (str): Тема электронного письма.
        recipient_list (List[str]): Список адресов получателей.
        html_message (str): HTML-разметка тела письма.
        plain_message (Optional[str]): Текстовая версия письма. Defaults to None.
        from_email (Optional[str]): Email отправителя. Defaults to settings.EMAIL_HOST_USER.
        attachments (Optional[List[Dict[str, Any]]]): Список вложений формата
            [{'filename': '...', 'content': base64_str|bytes, 'mimetype': '...'}].

    Returns:
        int: Количество успешно отправленных писем.
    """
    logger.info(
        "[Celery:UniversalEmail] Старт фоновой отправки email '%s' для %d адресатов.",
        subject,
        len(recipient_list),
    )
    try:
        from mailbox_app.services.email_service import UniversalEmailService

        sent_count, failed = UniversalEmailService.send_email_sync(
            subject=subject,
            recipient_list=recipient_list,
            html_message=html_message,
            plain_message=plain_message,
            from_email=from_email,
            attachments=attachments,
            fail_silently=True,
        )
        logger.info(
            "[Celery:UniversalEmail] Фоновая отправка завершена: отправлено %d, ошибок %d.",
            sent_count,
            len(failed),
        )
        return sent_count
    except Exception as exc:
        logger.error("[Celery:UniversalEmail] Ошибка при отправке email '%s': %s", subject, exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical(
                "[Celery:UniversalEmail] Превышен лимит повторов отправки email '%s' на %s.",
                subject,
                recipient_list,
            )
            return 0


