"""Сервисный слой для управления подзадачами и чек-листами (SubTask)."""

from typing import Optional
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from customers_app.models import DataBaseUser
from tasks_app.models import SubTask, Task, TaskHistory
from tasks_app.permissions import can_edit_task, can_toggle_subtask


class SubTaskService:
    """Сервис управления пунктами чек-листа и подзадачами."""

    @staticmethod
    def create_subtask(
        task: Task,
        user: DataBaseUser,
        title: str,
        assigned_to: Optional[DataBaseUser] = None,
        order: int = 0
    ) -> SubTask:
        """Создает новый пункт чек-листа в задаче.

        Args:
            task (Task): Родительская задача.
            user (DataBaseUser): Автор подзадачи.
            title (str): Наименование подзадачи.
            assigned_to (Optional[DataBaseUser]): Назначенный исполнитель пункта.
            order (int): Порядковый номер.

        Returns:
            SubTask: Созданный экземпляр подзадачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав на добавление подзадачи.
        """
        if not can_edit_task(user, task) and task.responsible_id != user.id:
            raise PermissionDenied("У вас нет прав для добавления подзадач в эту задачу.")

        subtask = SubTask.objects.create(
            task=task,
            title=title.strip(),
            assigned_to=assigned_to,
            order=order or (task.subtasks.count() + 1)
        )

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.SUBTASK_TOGGLED,
            new_value=f"+ {subtask.title}",
            comment="Добавлен пункт чек-листа"
        )
        return subtask

    @staticmethod
    def toggle_subtask(subtask: SubTask, user: DataBaseUser) -> SubTask:
        """Переключает статус выполнения подзадачи (Выполнено / Не выполнено).

        Args:
            subtask (SubTask): Экземпляр подзадачи.
            user (DataBaseUser): Пользователь, переключающий флаг.

        Returns:
            SubTask: Обновленный экземпляр подзадачи.

        Raises:
            PermissionDenied: Если у пользователя нет прав на переключение флага.
        """
        if not can_toggle_subtask(user, subtask):
            raise PermissionDenied("Вы не можете отметить данный пункт чек-листа.")

        subtask.is_completed = not subtask.is_completed
        if subtask.is_completed:
            subtask.completed_by = user
            subtask.completed_at = timezone.now()
        else:
            subtask.completed_by = None
            subtask.completed_at = None

        subtask.save(update_fields=['is_completed', 'completed_by', 'completed_at'])

        status_text = "выполнен" if subtask.is_completed else "возвращен в работу"
        TaskHistory.log(
            task=subtask.task,
            user=user,
            action=TaskHistory.ActionType.SUBTASK_TOGGLED,
            old_value=str(not subtask.is_completed),
            new_value=str(subtask.is_completed),
            comment=f"Пункт '{subtask.title}' {status_text}"
        )
        return subtask

    @staticmethod
    def delete_subtask(subtask: SubTask, user: DataBaseUser) -> None:
        """Удаляет пункт чек-листа.

        Args:
            subtask (SubTask): Удаляемый экземпляр подзадачи.
            user (DataBaseUser): Пользователь, инициирующий удаление.

        Raises:
            PermissionDenied: Если у пользователя нет прав на удаление.
        """
        task = subtask.task
        if not can_edit_task(user, task) and task.responsible_id != user.id:
            raise PermissionDenied("Вы не можете удалять подзадачи из этой задачи.")

        subtask_title = subtask.title
        subtask.delete()

        TaskHistory.log(
            task=task,
            user=user,
            action=TaskHistory.ActionType.SUBTASK_TOGGLED,
            old_value=f"- {subtask_title}",
            comment="Удален пункт чек-листа"
        )
