"""Фоновые асинхронные и периодические задачи Celery для модуля tasks_app.

Модуль содержит:
- send_task_notification_task: фоновая отправка email-уведомления отдельному участнику;
- notify_task_participants_batch_task: пакетная рассылка уведомлений всем участникам поручения;
- check_task_deadlines_task: периодический мониторинг приближения дедлайнов (24ч, 3ч), автоперевод в OVERDUE и эскалация;
- create_recurring_tasks_task: периодическая автогенерация повторяющихся задач (RRULE Engine);
- send_task_websocket_event_task: асинхронная отправка событий через Django Channels.
"""

import logging
from typing import Any, Dict, List, Optional

from celery import shared_task

from tasks_app.models import Task
from tasks_app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_task_notification_task(
    self,
    task_id: int,
    sender_id: Optional[int] = None,
    recipient_id: Optional[int] = None,
    event_type: str = 'assigned',
    comment: str = ''
) -> bool:
    """Асинхронная Celery-задача отправки email-уведомления участнику поручения.

    Args:
        self: Экземпляр задачи Celery (bind=True).
        task_id (int): Идентификатор задачи.
        sender_id (Optional[int]): Идентификатор отправителя.
        recipient_id (Optional[int]): Идентификатор получателя.
        event_type (str): Тип события (assigned, status_changed, overdue, etc.).
        comment (str): Пояснительный комментарий или причина.

    Returns:
        bool: Результат отправки.
    """
    logger.info(
        "Celery: старт send_task_notification_task для задачи #%s (получатель: #%s, тип: %s)",
        task_id, recipient_id, event_type
    )
    try:
        success = NotificationService.send_task_email_notification(
            task_id=task_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            event_type=event_type,
            comment=comment
        )
        logger.info("Celery: задача send_task_notification_task #%s завершена (результат: %s)", task_id, success)
        return success
    except Exception as exc:
        logger.error("Celery: ошибка в send_task_notification_task (задача #%s): %s", task_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_task_participants_batch_task(
    self,
    task_id: int,
    sender_id: Optional[int] = None,
    event_type: str = 'assigned',
    comment: str = ''
) -> int:
    """Пакетная асинхронная рассылка уведомлений всем участникам задачи.

    Извлекает список участников (ответственный, соисполнители, наблюдатели, шаринг)
    и порождает индивидуальные Celery-задачи для каждого адресата.

    Args:
        self: Экземпляр задачи Celery.
        task_id (int): Идентификатор задачи.
        sender_id (Optional[int]): Идентификатор инициатора.
        event_type (str): Тип события.
        comment (str): Пояснительный комментарий.

    Returns:
        int: Количество поставленных в очередь уведомлений.
    """
    logger.info("Celery: старт пакетной рассылки для задачи #%s (тип: %s)", task_id, event_type)
    try:
        task = Task.objects.prefetch_related('assignees', 'observers', 'shared_with').get(pk=task_id)
        recipient_ids = set()

        if task.responsible_id and task.responsible_id != sender_id:
            recipient_ids.add(task.responsible_id)
        if task.user_id and task.user_id != sender_id:
            recipient_ids.add(task.user_id)

        for u in task.assignees.all():
            if u.id != sender_id:
                recipient_ids.add(u.id)

        for u in task.observers.all():
            if u.id != sender_id:
                recipient_ids.add(u.id)

        for u in task.shared_with.all():
            if u.id != sender_id:
                recipient_ids.add(u.id)

        queued_count = 0
        for rec_id in recipient_ids:
            send_task_notification_task.delay(
                task_id=task_id,
                sender_id=sender_id,
                recipient_id=rec_id,
                event_type=event_type,
                comment=comment
            )
            queued_count += 1

        logger.info("Celery: пакетная рассылка для задачи #%s запущена: %s задач", task_id, queued_count)
        return queued_count
    except Exception as exc:
        logger.error("Celery: ошибка в notify_task_participants_batch_task (задача #%s): %s", task_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def check_task_deadlines_task(self) -> Dict[str, int]:
    """Периодическая задача проверки дедлайнов, автоперевода в OVERDUE и эскалации.

    Запускается планировщиком Celery Beat.
    """
    logger.info("Celery Beat: запуск периодического мониторинга дедлайнов задач")
    try:
        stats = NotificationService.check_deadlines_and_escalate()
        logger.info("Celery Beat: мониторинг дедлайнов завершен: %s", stats)
        return stats
    except Exception as exc:
        logger.error("Celery: ошибка в check_task_deadlines_task: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def create_recurring_tasks_task(self) -> int:
    """Периодическая задача автогенерации повторяющихся задач по правилам RRULE.

    Запускается планировщиком Celery Beat.
    """
    logger.info("Celery Beat: запуск проверки повторяющихся задач")
    try:
        count = NotificationService.process_recurring_tasks()
        logger.info("Celery Beat: проверка повторяющихся задач завершена. Создано: %s", count)
        return count
    except Exception as exc:
        logger.error("Celery: ошибка в create_recurring_tasks_task: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_task_websocket_event_task(
    self,
    task_id: int,
    event_type: str,
    message: str,
    user_ids: Optional[List[int]] = None
) -> bool:
    """Асинхронная задача отправки WebSocket-уведомления в Channels."""
    try:
        return NotificationService.send_task_websocket_notification(
            task_id=task_id,
            event_type=event_type,
            message=message,
            user_ids=user_ids
        )
    except Exception as exc:
        logger.error("Celery: ошибка в send_task_websocket_event_task: %s", exc)
        raise self.retry(exc=exc)
