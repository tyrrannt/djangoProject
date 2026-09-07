"""Сервисный слой для управления комментариями и обсуждением задач."""

from typing import Optional
from django.core.exceptions import PermissionDenied

from customers_app.models import DataBaseUser
from tasks_app.models import Task, TaskComment, TaskHistory
from tasks_app.permissions import can_view_task


class CommentService:
    """Сервис добавления и управления комментариями к задачам."""

    @staticmethod
    def add_comment(
        task: Task,
        author: DataBaseUser,
        text: str,
        parent: Optional[TaskComment] = None
    ) -> TaskComment:
        """Добавляет новый комментарий к задаче.

        Args:
            task (Task): Экземпляр задачи.
            author (DataBaseUser): Автор комментария.
            text (str): Текст комментария.
            parent (Optional[TaskComment]): Родительский комментарий (для веток ответов).

        Returns:
            TaskComment: Созданный комментарий.

        Raises:
            PermissionDenied: Если у автора нет прав на просмотр/комментирование задачи.
            ValueError: Если текст комментария пуст.
        """
        if not can_view_task(author, task):
            raise PermissionDenied("У вас нет доступа к этой задаче для публикации комментариев.")

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Комментарий не может быть пустым.")

        comment = TaskComment.objects.create(
            task=task,
            author=author,
            text=clean_text,
            parent=parent
        )

        TaskHistory.log(
            task=task,
            user=author,
            action=TaskHistory.ActionType.COMMENT_ADDED,
            comment=f"Добавлен комментарий ({clean_text[:50]}...)" if len(clean_text) > 50 else f"Добавлен комментарий: {clean_text}"
        )
        return comment
