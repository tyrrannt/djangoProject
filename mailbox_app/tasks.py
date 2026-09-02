"""Фоновые задачи Celery для приложения корпоративной почты mailbox_app."""

import logging
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
