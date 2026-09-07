"""Сервисный слой для управления жизненным циклом и операциями над задачами.

Реализует бизнес-логику смены статусов, назначения исполнителей, делегирования,
приемки результатов (с поддержкой опциональной ЭЦП КриптоПро) и аудита.
"""

from typing import List, Optional
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from customers_app.models import DataBaseUser
from tasks_app.models import (
    AssignmentStatus,
    Task,
    TaskAssignment,
    TaskHistory,
    TaskRole,
    TaskStatus,
)
from tasks_app.permissions import (
    can_accept_task,
    can_delegate_task,
    can_edit_task,
    can_return_task,
    can_start_task,
    can_submit_for_review,
)


class TaskService:
    """Сервис управления жизненным циклом задачи и операциями Workflow."""

    @staticmethod
    def start_task(task: Task, user: DataBaseUser) -> Task:
        """Переводит задачу в статус 'В работе' (IN_PROGRESS).

        Args:
            task (Task): Экземпляр задачи.
            user (DataBaseUser): Пользователь, принимающий задачу в работу.

        Returns:
            Task: Обновленный экземпляр задачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав на принятие задачи.
        """
        if not can_start_task(user, task):
            raise PermissionDenied("У вас нет прав для принятия данной задачи в работу.")

        old_status = task.status
        task.status = TaskStatus.IN_PROGRESS
        if not task.accepted_at:
            task.accepted_at = timezone.now()
        task.save(update_fields=['status', 'accepted_at', 'updated_at'])

        # Обновляем назначение если есть
        TaskAssignment.objects.filter(
            task=task,
            assigned_to=user,
            status=AssignmentStatus.PENDING
        ).update(status=AssignmentStatus.ACCEPTED, accepted_at=timezone.now())

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.ACCEPTED,
            old_value=old_status,
            new_value=TaskStatus.IN_PROGRESS,
            comment="Задача принята в работу"
        )
        return task

    @staticmethod
    def submit_for_review(task: Task, user: DataBaseUser, comment: str = '') -> Task:
        """Отправляет выполненную задачу на проверку постановщику (ON_REVIEW).

        Args:
            task (Task): Экземпляр задачи.
            user (DataBaseUser): Исполнитель, отправляющий задачу на проверку.
            comment (str): Пояснительный комментарий к результату работы.

        Returns:
            Task: Обновленный экземпляр задачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав для отправки на проверку.
        """
        if not can_submit_for_review(user, task):
            raise PermissionDenied("Вы не можете отправить данную задачу на проверку.")

        old_status = task.status
        task.status = TaskStatus.ON_REVIEW
        task.submitted_review_at = timezone.now()
        task.save(update_fields=['status', 'submitted_review_at', 'updated_at'])

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.SUBMITTED_REVIEW,
            old_value=old_status,
            new_value=TaskStatus.ON_REVIEW,
            comment=comment or "Задача отправлена на проверку"
        )

        # Фоновое уведомление постановщику о сдаче на проверку
        try:
            from tasks_app.tasks import send_task_notification_task
            if task.user_id and task.user_id != user.id:
                send_task_notification_task.delay(
                    task_id=task.pk,
                    sender_id=user.pk,
                    recipient_id=task.user_id,
                    event_type='review_submitted',
                    comment=comment
                )
        except Exception:
            pass

        return task

    @staticmethod
    def accept_task(
        task: Task,
        user: DataBaseUser,
        eds_signature: Optional[str] = None,
        comment: str = '',
        bypass_eds: bool = False
    ) -> Task:
        """Окончательно принимает и закрывает задачу со статусом COMPLETED.

        Поддерживает работу как в обычном режиме (без ЭЦП), так и в режиме
        квалифицированного подписания КриптоПро ЭЦП (если task.requires_eds=True),
        а также переходный режим приемки без ЭЦП по подтверждению пользователя.

        Args:
            task (Task): Экземпляр задачи.
            user (DataBaseUser): Постановщик (автор), принимающий задачу.
            eds_signature (Optional[str]): Строка ЭЦП подписи (если включен режим ЭЦП).
            comment (str): Итоговый комментарий приемки.
            bypass_eds (bool): Флаг подтверждения закрытия без ЭЦП в переходном режиме.

        Returns:
            Task: Завершенная задача.

        Raises:
            PermissionDenied: Если у пользователя нет прав на приемку задачи.
            ValidationError: Если задача требует обязательной ЭЦП, но подпись не передана и bypass_eds=False.
        """
        if not can_accept_task(user, task):
            raise PermissionDenied("Только постановщик задачи может принять ее выполнение.")

        if task.requires_eds and not eds_signature and not bypass_eds:
            raise ValidationError("Для данной задачи требуется подписание результата с помощью ЭЦП.")

        old_status = task.status
        task.status = TaskStatus.COMPLETED
        task.completed = True
        task.completed_at = timezone.now()

        update_fields = ['status', 'completed', 'completed_at', 'updated_at']

        if eds_signature:
            task.eds_signature = eds_signature
            task.eds_signed_by = user
            task.eds_signed_at = timezone.now()
            update_fields.extend(['eds_signature', 'eds_signed_by', 'eds_signed_at'])

        task.save(update_fields=update_fields)

        # Закрываем все поручения
        TaskAssignment.objects.filter(
            task=task,
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
        ).update(status=AssignmentStatus.COMPLETED, completed_at=timezone.now())

        action_type = TaskHistory.ActionType.EDS_SIGNED if eds_signature else TaskHistory.ActionType.COMPLETED
        history_comment = comment or ("Выполнение подтверждено с ЭЦП" if eds_signature else "Выполнение подтверждено")
        if task.requires_eds and not eds_signature:
            history_comment += " (Приемка выполнена без ЭЦП в переходном режиме)"

        TaskHistory.log(
            task=task,
            user=user,
            action=action_type,
            old_value=old_status,
            new_value=TaskStatus.COMPLETED,
            comment=history_comment
        )

        # Фоновое уведомление участникам о завершении
        try:
            from tasks_app.tasks import send_task_notification_task
            recipients = set([task.responsible_id] + list(task.assignees.values_list('id', flat=True)))
            for rec_id in recipients:
                if rec_id and rec_id != user.id:
                    send_task_notification_task.delay(
                        task_id=task.pk,
                        sender_id=user.pk,
                        recipient_id=rec_id,
                        event_type='completed',
                        comment=comment
                    )
        except Exception:
            pass

        return task

    @staticmethod
    def return_task(task: Task, user: DataBaseUser, reason: str = '') -> Task:
        """Возвращает задачу на доработку (RETURNED).

        Args:
            task (Task): Экземпляр задачи.
            user (DataBaseUser): Постановщик задачи.
            reason (str): Причина возврата / замечания.

        Returns:
            Task: Обновленный экземпляр задачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав на возврат задачи.
        """
        if not can_return_task(user, task):
            raise PermissionDenied("Вы не можете вернуть данную задачу на доработку.")

        old_status = task.status
        task.status = TaskStatus.RETURNED
        task.save(update_fields=['status', 'updated_at'])

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.RETURNED,
            old_value=old_status,
            new_value=TaskStatus.RETURNED,
            comment=reason or "Задача возвращена на доработку"
        )

        # Фоновое уведомление ответственным о возврате на доработку
        try:
            from tasks_app.tasks import send_task_notification_task
            recipients = set([task.responsible_id] + list(task.assignees.values_list('id', flat=True)))
            for rec_id in recipients:
                if rec_id and rec_id != user.id:
                    send_task_notification_task.delay(
                        task_id=task.pk,
                        sender_id=user.pk,
                        recipient_id=rec_id,
                        event_type='returned',
                        comment=reason
                    )
        except Exception:
            pass

        return task

    @staticmethod
    def cancel_task(task: Task, user: DataBaseUser, reason: str = '') -> Task:
        """Отменяет задачу (CANCELLED).

        Args:
            task (Task): Экземпляр задачи.
            user (DataBaseUser): Постановщик или администратор.
            reason (str): Причина отмены задачи.

        Returns:
            Task: Обновленный экземпляр задачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав на отмену задачи.
        """
        if not can_edit_task(user, task):
            raise PermissionDenied("Только автор может отменить задачу.")

        old_status = task.status
        task.status = TaskStatus.CANCELLED
        task.save(update_fields=['status', 'updated_at'])

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.CANCELLED,
            old_value=old_status,
            new_value=TaskStatus.CANCELLED,
            comment=reason or "Задача отменена"
        )
        return task

    @staticmethod
    def assign_user(
        task: Task,
        assigned_by: DataBaseUser,
        assigned_to: DataBaseUser,
        role: str = TaskRole.ASSIGNEE,
        comment: str = ''
    ) -> TaskAssignment:
        """Делегирует или назначает задачу сотруднику с фиксацией роли и аудита.

        Args:
            task (Task): Экземпляр задачи.
            assigned_by (DataBaseUser): Сотрудник, выдающий поручение.
            assigned_to (DataBaseUser): Назначаемый сотрудник.
            role (str): Роль из TaskRole.
            comment (str): Пояснение к поручению.

        Returns:
            TaskAssignment: Созданная запись назначения.

        Raises:
            PermissionDenied: Если у инициатора нет прав на делегирование.
        """
        if not can_delegate_task(assigned_by, task):
            raise PermissionDenied("У вас нет прав для назначения исполнителей на эту задачу.")

        assignment, _ = TaskAssignment.objects.update_or_create(
            task=task,
            assigned_to=assigned_to,
            defaults={
                'assigned_by': assigned_by,
                'role': role,
                'status': AssignmentStatus.PENDING,
                'comment': comment,
                'assigned_at': timezone.now()
            }
        )

        if role == TaskRole.RESPONSIBLE:
            task.responsible = assigned_to
            task.save(update_fields=['responsible', 'updated_at'])
        elif role == TaskRole.ASSIGNEE:
            task.assignees.add(assigned_to)
        elif role == TaskRole.OBSERVER:
            task.observers.add(assigned_to)

        # Синхронизируем legacy shared_with
        task.shared_with.add(assigned_to)

        TaskHistory.log(
            task=task,
            user=assigned_by,
            action=TaskHistory.ActionType.DELEGATED,
            new_value=f"{assigned_to.get_full_name()} ({role})",
            comment=comment or f"Назначен {assignment.get_role_display()}"
        )

        # Фоновое уведомление назначенному сотруднику
        try:
            from tasks_app.tasks import send_task_notification_task
            if assigned_to.id != assigned_by.id:
                send_task_notification_task.delay(
                    task_id=task.pk,
                    sender_id=assigned_by.pk,
                    recipient_id=assigned_to.pk,
                    event_type='assigned',
                    comment=comment
                )
        except Exception:
            pass

        return assignment
