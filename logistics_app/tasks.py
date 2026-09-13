"""Фоновые задачи Celery для подсистемы электронного документооборота logistics_app."""

import logging
import uuid
from typing import Any, Dict, Optional

from celery import shared_task
from django.utils import timezone

from logistics_app.models import DocFlowDocument, DocFlowRouteStep
from logistics_app.services.docflow_notification_service import DocFlowNotificationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_docflow_sla_deadlines_task(self) -> int:
    """Периодическая задача Celery Beat для контроля SLA и дедлайнов этапов согласования СЭД.

    Проверяет все активные этапы согласования (IN_PROGRESS) с установленным due_date.
    Если до наступления дедлайна осталось менее 24 часов или он уже просрочен,
    отправляет уведомление согласующему лицу и логирует предупреждение.

    Args:
        self: Экземпляр текущей запущенной задачи Celery.

    Returns:
        int: Количество отправленных уведомлений по SLA.
    """
    logger.info("[Celery:DocFlowSLA] Старт плановой проверки дедлайнов согласования СЭД.")
    sent_count = 0

    try:
        now = timezone.now()
        # Выбираем активные шаги согласования
        active_steps = (
            DocFlowRouteStep.objects.filter(
                status=DocFlowRouteStep.Status.IN_PROGRESS,
                due_date__isnull=False,
            )
            .select_related("document", "assigned_user", "assigned_division")
            .prefetch_related("assigned_users")
        )

        for step in active_steps:
            if not step.due_date:
                continue

            time_left = step.due_date - now
            hours_left = time_left.total_seconds() / 3600.0

            # Если срок истек или осталось менее 24 часов
            if hours_left <= 24.0:
                recipients = []
                if step.assigned_user and step.assigned_user.email:
                    recipients.append(step.assigned_user.email)
                elif step.assigned_division:
                    from customers_app.models import DataBaseUser
                    div_users = DataBaseUser.objects.filter(
                        user_work_profile__divisions=step.assigned_division,
                        is_active=True,
                    )
                    for u in div_users:
                        if u.email:
                            recipients.append(u.email)
                for u in step.assigned_users.all():
                    if u.email and u.email not in recipients:
                        recipients.append(u.email)

                for email in set(recipients):
                    try:
                        DocFlowNotificationService.send_sla_warning_email(
                            recipient_email=email,
                            step=step,
                            hours_remaining=hours_left,
                        )
                        sent_count += 1
                    except Exception as exc:
                        logger.warning(
                            "Ошибка отправки SLA-уведомления на %s по шагу ID %d: %s",
                            email,
                            step.id,
                            exc,
                        )

        logger.info("[Celery:DocFlowSLA] Проверка завершена. Отправлено %d предупреждений.", sent_count)
        return sent_count

    except Exception as exc:
        logger.error("[Celery:DocFlowSLA] Критическая ошибка при проверке SLA: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical("[Celery:DocFlowSLA] Превышен лимит попыток выполнения check_docflow_sla_deadlines_task.")
            return sent_count


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_docflow_assignment_notification_task(
    self,
    step_id: int,
    recipient_email: str,
) -> bool:
    """Фоновая асинхронная задача отправки письма о назначении нового этапа согласования.

    Args:
        self: Экземпляр текущей запущенной задачи Celery.
        step_id (int): Идентификатор назначенного этапа согласования.
        recipient_email (str): Адрес электронной почты адресата.

    Returns:
        bool: True при успешной отправке письма, иначе False.
    """
    logger.info("[Celery:DocFlowNotification] Отправка уведомления по шагу ID=%d на %s.", step_id, recipient_email)
    try:
        step = DocFlowRouteStep.objects.select_related("document").get(id=step_id)
        return DocFlowNotificationService.send_assignment_notification(step, recipient_email)
    except Exception as exc:
        logger.error("[Celery:DocFlowNotification] Ошибка отправки уведомления: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical("[Celery:DocFlowNotification] Превышен лимит попыток для send_docflow_assignment_notification_task.")
            return False
