"""Фоновые задачи Celery для модуля тестирования персонала testing_app."""

import logging
from celery import shared_task
from testing_app.services.notification_service import (
    send_testing_assignment_notification,
    send_testing_result_notification,
    send_testing_deadline_reminders,
    check_and_expire_stale_attempts,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_assignment_notification_task(self, assignment_id: int):
    """Фоновая задача отправки email-уведомления сотруднику о назначении на тестирование.

    Args:
        assignment_id (int): Идентификатор назначения TestingAssignment.
    """
    logger.info("Старт задачи send_assignment_notification_task для назначения ID %s", assignment_id)
    try:
        success = send_testing_assignment_notification(assignment_id)
        logger.info("Завершена задача send_assignment_notification_task для назначения ID %s, результат: %s", assignment_id, success)
        return success
    except Exception as exc:
        logger.error("Ошибка в задаче send_assignment_notification_task (ID %s): %s", assignment_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_attempt_result_notification_task(self, attempt_id: int):
    """Фоновая задача отправки email-уведомления сотруднику с результатами сдачи теста.

    Args:
        attempt_id (int): Идентификатор попытки TestingAttempt.
    """
    logger.info("Старт задачи send_attempt_result_notification_task для попытки ID %s", attempt_id)
    try:
        success = send_testing_result_notification(attempt_id)
        logger.info("Завершена задача send_attempt_result_notification_task для попытки ID %s, результат: %s", attempt_id, success)
        return success
    except Exception as exc:
        logger.error("Ошибка в задаче send_attempt_result_notification_task (ID %s): %s", attempt_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_event_assignments_batch_task(self, testing_id: int):
    """Пакетная отправка уведомлений о назначении всем сотрудникам при активации приказа.

    Args:
        testing_id (int): Идентификатор мероприятия Testing.
    """
    logger.info("Старт пакетной отправки уведомлений для мероприятия ID %s", testing_id)
    from testing_app.models import TestingAssignment
    try:
        assignment_ids = list(
            TestingAssignment.objects.filter(testing_id=testing_id).values_list("id", flat=True)
        )
        for a_id in assignment_ids:
            send_assignment_notification_task.delay(a_id)

        logger.info("Пакетная отправка для мероприятия ID %s запущена: %s задач", testing_id, len(assignment_ids))
        return len(assignment_ids)
    except Exception as exc:
        logger.error("Ошибка в send_event_assignments_batch_task (Testing ID %s): %s", testing_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_deadline_reminders_task(self):
    """Периодическая задача проверки и отправки напоминаний за 3 дня и за 1 день до дедлайна."""
    logger.info("Старт периодической задачи send_deadline_reminders_task")
    try:
        stats = send_testing_deadline_reminders()
        logger.info("Периодическая задача send_deadline_reminders_task завершена: %s", stats)
        return stats
    except Exception as exc:
        logger.error("Ошибка в send_deadline_reminders_task: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def check_expired_attempts_task(self):
    """Периодическая задача закрытия зависших сессий тестирования с истекшим серверным таймером."""
    logger.info("Старт периодической задачи check_expired_attempts_task")
    try:
        closed_count = check_and_expire_stale_attempts()
        logger.info("Периодическая задача check_expired_attempts_task завершена. Закрыто сессий: %s", closed_count)
        return closed_count
    except Exception as exc:
        logger.error("Ошибка в check_expired_attempts_task: %s", exc)
        raise self.retry(exc=exc)
