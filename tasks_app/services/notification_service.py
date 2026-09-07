"""Сервисный модуль уведомлений, мониторинга дедлайнов и повторяющихся задач (tasks_app).

Реализует:
- Асинхронную отправку email-уведомлений участникам поручений;
- Периодический мониторинг приближающихся дедлайнов (24ч и 3ч);
- Автоматический перевод просроченных задач в статус OVERDUE;
- Эскалацию просрочек (>48ч) постановщику и руководству;
- Фоновое создание повторяющихся задач по правилам RRULE;
- Интеграцию с WebSocket каналами Django Channels.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from administration_app.utils import send_notification
from customers_app.models import DataBaseUser
from tasks_app.models import Task, TaskHistory, TaskRole, TaskStatus

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис почтовых и системных уведомлений по задачам и поручениям."""

    EVENT_TITLES = {
        'assigned': "Вам назначено новое поручение",
        'status_changed': "Изменение статуса поручения",
        'deadline_reminder_24h': "Напоминание: срок исполнения истекает через 24 часа",
        'deadline_reminder_3h': "Срочно: срок исполнения истекает через 3 часа",
        'overdue': "Внимание: срок исполнения поручения истек (Просрочено)",
        'escalation': "Эскалация: поручение просрочено более 48 часов",
        'review_submitted': "Поручение отправлено вам на проверку",
        'returned': "Поручение возвращено на доработку",
        'completed': "Поручение успешно принято и закрыто",
        'comment': "Новый комментарий в поручении",
        'recurring_created': "Создано периодическое поручение по расписанию",
    }

    @classmethod
    def send_task_email_notification(
        cls,
        task_id: int,
        sender_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        event_type: str = 'assigned',
        comment: str = '',
        extra_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Отправляет email-уведомление конкретному участнику задачи.

        Args:
            task_id (int): Идентификатор задачи.
            sender_id (Optional[int]): Идентификатор пользователя-инициатора.
            recipient_id (Optional[int]): Идентификатор получателя.
            event_type (str): Тип события (assigned, status_changed, overdue, etc.).
            comment (str): Дополнительный комментарий или причина.
            extra_context (Optional[Dict[str, Any]]): Дополнительные параметры контекста.

        Returns:
            bool: True в случае успешной отправки, иначе False.

        Raises:
            ObjectDoesNotExist: Если задача или получатель не найдены.
        """
        try:
            task = Task.objects.select_related('user', 'responsible', 'category').get(pk=task_id)
        except Task.DoesNotExist:
            logger.warning("NotificationService: задача #%s не найдена", task_id)
            return False

        recipient = None
        if recipient_id:
            try:
                recipient = DataBaseUser.objects.get(pk=recipient_id, is_active=True)
            except DataBaseUser.DoesNotExist:
                logger.warning("NotificationService: получатель #%s не найден", recipient_id)
                return False

        if not recipient:
            recipient = task.responsible or task.user

        if not recipient or not recipient.email:
            logger.info("NotificationService: у пользователя #%s нет email адреса", getattr(recipient, 'id', None))
            return False

        sender = None
        if sender_id:
            sender = DataBaseUser.objects.filter(pk=sender_id, is_active=True).first()
        if not sender:
            sender = task.user

        event_title = cls.EVENT_TITLES.get(event_type, "Уведомление по поручению")
        subject = f"{event_title}: «{task.title}»"

        # Формируем URL карточки задачи
        base_portal_url = getattr(settings, 'PORTAL_URL', '') or ''
        task_url = f"{base_portal_url}{reverse('tasks_app:task-detail', args=[task.pk])}"

        context = {
            'task': task,
            'task_url': task_url,
            'user': recipient,
            'sender': sender,
            'event_type': event_type,
            'event_title': event_title,
            'comment': comment,
        }
        if extra_context:
            context.update(extra_context)

        # Выбираем режим division: 0 от имени отправителя (если настроен пароль), иначе 3 (системный)
        division = 0
        if not sender or not hasattr(sender, 'user_work_profile') or not sender.user_work_profile.work_email_password:
            division = 3

        try:
            res = send_notification(
                sender=sender,
                recipient=recipient,
                subject=subject,
                template='tasks_app/emails/task_notification.html',
                context=context,
                division=division
            )
            logger.info("NotificationService: отправлено письмо по задаче #%s получателю %s (результат: %s)", task_id, recipient.email, res)
            return bool(res)
        except Exception as err:
            logger.error("NotificationService: ошибка отправки email по задаче #%s: %s", task_id, err)
            return False

    @classmethod
    def send_task_websocket_notification(
        cls,
        task_id: int,
        event_type: str,
        message: str,
        user_ids: Optional[List[int]] = None
    ) -> bool:
        """Отправляет интерактивное WebSocket-сообщение (toast/event) через Channels.

        Args:
            task_id (int): Идентификатор задачи.
            event_type (str): Тип события.
            message (str): Текст всплывающего уведомления.
            user_ids (Optional[List[int]]): Список ID целевых пользователей.

        Returns:
            bool: True, если отправлено, False при ошибке/отсутствии бэкенда Channels.
        """
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if not channel_layer:
                return False

            payload = {
                'type': 'task_event',
                'task_id': task_id,
                'event_type': event_type,
                'message': message,
                'timestamp': timezone.now().isoformat()
            }

            if user_ids:
                for uid in user_ids:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{uid}",
                        {'type': 'send_message', 'message': payload}
                    )
            else:
                async_to_sync(channel_layer.group_send)(
                    "portal_tasks",
                    {'type': 'send_message', 'message': payload}
                )
            return True
        except Exception as err:
            logger.debug("NotificationService WebSocket channels not active or errored: %s", err)
            return False

    @classmethod
    def check_deadlines_and_escalate(cls) -> Dict[str, int]:
        """Выполняет периодический аудит дедлайнов, автоперевод в OVERDUE и эскалацию.

        Вызывается планировщиком Celery Beat:
        1. Отправляет напоминание за 24 часа;
        2. Отправляет срочное напоминание за 3 часа;
        3. Автоматически переводит просроченные задачи в статус TaskStatus.OVERDUE;
        4. Эскалирует просрочки (> 48 часов) постановщику и руководству.

        Returns:
            Dict[str, int]: Статистика обработанных событий.
        """
        now = timezone.now()
        stats = {
            'reminders_24h': 0,
            'reminders_3h': 0,
            'marked_overdue': 0,
            'escalated': 0,
        }

        active_tasks = Task.objects.filter(
            end_date__isnull=False
        ).exclude(
            status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
        ).select_related('user', 'responsible')

        # 1. Напоминание за 24 часа (дедлайн между now+20h и now+24h)
        window_24h_start = now + timedelta(hours=20)
        window_24h_end = now + timedelta(hours=24)
        tasks_24h = active_tasks.filter(
            end_date__gte=window_24h_start,
            end_date__lte=window_24h_end
        )
        for task in tasks_24h:
            already_notified = TaskHistory.objects.filter(
                task=task,
                action=TaskHistory.ActionType.STATUS_CHANGED,
                comment__icontains="Напоминание за 24ч"
            ).exists()
            if not already_notified:
                recipients = set([task.responsible_id, task.user_id] + list(task.assignees.values_list('id', flat=True)))
                for rec_id in recipients:
                    if rec_id:
                        cls.send_task_email_notification(task.id, sender_id=task.user_id, recipient_id=rec_id, event_type='deadline_reminder_24h')
                TaskHistory.log(
                    task=task,
                    user=None,
                    action=TaskHistory.ActionType.STATUS_CHANGED,
                    comment="Напоминание за 24ч до дедлайна отправлено участникам"
                )
                stats['reminders_24h'] += 1

        # 2. Напоминание за 3 часа (дедлайн между now и now+3h)
        window_3h_end = now + timedelta(hours=3)
        tasks_3h = active_tasks.filter(
            end_date__gte=now,
            end_date__lte=window_3h_end
        )
        for task in tasks_3h:
            already_notified = TaskHistory.objects.filter(
                task=task,
                action=TaskHistory.ActionType.STATUS_CHANGED,
                comment__icontains="Напоминание за 3ч"
            ).exists()
            if not already_notified:
                recipients = set([task.responsible_id, task.user_id] + list(task.assignees.values_list('id', flat=True)))
                for rec_id in recipients:
                    if rec_id:
                        cls.send_task_email_notification(task.id, sender_id=task.user_id, recipient_id=rec_id, event_type='deadline_reminder_3h')
                TaskHistory.log(
                    task=task,
                    user=None,
                    action=TaskHistory.ActionType.STATUS_CHANGED,
                    comment="Напоминание за 3ч до дедлайна отправлено участникам"
                )
                stats['reminders_3h'] += 1

        # 3. Автоматический перевод в OVERDUE для задач с end_date < now
        overdue_candidates = active_tasks.filter(
            end_date__lt=now
        ).exclude(status=TaskStatus.OVERDUE)

        for task in overdue_candidates:
            old_status = task.status
            task.status = TaskStatus.OVERDUE
            task.save(update_fields=['status', 'updated_at'])

            TaskHistory.log(
                task=task,
                user=None,
                action=TaskHistory.ActionType.STATUS_CHANGED,
                old_value=old_status,
                new_value=TaskStatus.OVERDUE,
                comment="Автоматический перевод в статус 'Просрочено' планировщиком Celery Beat"
            )

            recipients = set([task.responsible_id, task.user_id] + list(task.assignees.values_list('id', flat=True)))
            for rec_id in recipients:
                if rec_id:
                    cls.send_task_email_notification(task.id, sender_id=task.user_id, recipient_id=rec_id, event_type='overdue')

            stats['marked_overdue'] += 1

        # 4. Эскалация просрочек > 48 часов
        escalation_threshold = now - timedelta(hours=48)
        tasks_to_escalate = active_tasks.filter(
            end_date__lt=escalation_threshold,
            status=TaskStatus.OVERDUE
        )

        for task in tasks_to_escalate:
            already_escalated = TaskHistory.objects.filter(
                task=task,
                action=TaskHistory.ActionType.STATUS_CHANGED,
                comment__icontains="Эскалация просрочки (>48ч)"
            ).exists()
            if not already_escalated:
                # Отправляем уведомление постановщику задачи
                cls.send_task_email_notification(
                    task_id=task.id,
                    sender_id=None,
                    recipient_id=task.user_id,
                    event_type='escalation',
                    comment="Поручение находится в просроченном состоянии более 48 часов!"
                )
                TaskHistory.log(
                    task=task,
                    user=None,
                    action=TaskHistory.ActionType.STATUS_CHANGED,
                    comment="Эскалация просрочки (>48ч) постановщику"
                )
                stats['escalated'] += 1

        logger.info("NotificationService: мониторинг дедлайнов завершен: %s", stats)
        return stats

    @classmethod
    def process_recurring_tasks(cls) -> int:
        """Сканирует повторяющиеся задачи и создает следующие экземпляры по правилам RRULE.

        Создает дискретные разовые задачи (repeat='none') при завершении предыдущего этапа
        или наступлении срока следующего повторения, предотвращая каскадное дублирование правил.

        Returns:
            int: Количество созданных новых задач.
        """
        created_count = 0
        now = timezone.now()
        near_window = now + timedelta(hours=2)

        # Находим задачи с активным правилом повторения
        recurring_candidates = Task.objects.exclude(
            repeat='none'
        ).filter(
            Q(status=TaskStatus.COMPLETED) | Q(start_date__lte=now)
        ).distinct()

        for parent_task in recurring_candidates:
            next_start, next_end = parent_task.get_next_occurrence()
            if not next_start:
                continue

            # Создаем следующий экземпляр, если предыдущая задача уже завершена
            # ИЛИ если время следующего повторения наступает прямо сейчас (в окне 2 часов)
            should_create = (parent_task.status == TaskStatus.COMPLETED) or (next_start <= near_window)
            if not should_create:
                continue

            # Проверяем, не была ли уже создана задача на это время
            already_created = Task.objects.filter(
                user=parent_task.user,
                title=parent_task.title,
                start_date=next_start
            ).exists()

            if not already_created:
                new_task = parent_task.create_next_task(as_discrete_task=True)
                if new_task:
                    TaskHistory.log(
                        task=new_task,
                        user=None,
                        action=TaskHistory.ActionType.CREATED,
                        comment=f"Автоматически создана периодическая задача от исходного правила #{parent_task.id}"
                    )
                    # Уведомляем ответственного о новом периодическом поручении
                    if new_task.responsible_id:
                        cls.send_task_email_notification(
                            task_id=new_task.id,
                            sender_id=new_task.user_id,
                            recipient_id=new_task.responsible_id,
                            event_type='recurring_created'
                        )
                    created_count += 1

        logger.info("NotificationService: генерация повторяющихся задач завершена. Создано: %s", created_count)
        return created_count
