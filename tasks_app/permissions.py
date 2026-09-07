"""Модуль разграничения прав доступа и авторизации действий над задачами (tasks_app).

Содержит функции проверки прав пользователя для различных операций над задачами,
поручениями, подзадачами, комментариями и вложениями.
"""

from typing import TYPE_CHECKING
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

if TYPE_CHECKING:
    from customers_app.models import DataBaseUser
    from tasks_app.models import SubTask, Task


def can_view_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, имеет ли пользователь право просматривать задачу.

    Пользователь имеет право просмотра, если он:
    - Суперпользователь / администратор;
    - Автор / Постановщик задачи (`task.user`);
    - Главный ответственный (`task.responsible`);
    - Включен в список соисполнителей (`task.assignees`);
    - Включен в список наблюдателей (`task.observers`);
    - Включен в список общего доступа (`task.shared_with`).

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если доступ разрешен, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if task.user_id == user.id or task.responsible_id == user.id:
        return True
    if task.assignees.filter(id=user.id).exists():
        return True
    if task.observers.filter(id=user.id).exists():
        return True
    if task.shared_with.filter(id=user.id).exists():
        return True
    return False


def can_edit_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, имеет ли пользователь право редактировать параметры задачи.

    Редактировать основные атрибуты (название, описание, сроки, важность, категорию)
    может только автор (постановщик) или суперпользователь.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если редактирование разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return task.user_id == user.id


def can_delete_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, имеет ли пользователь право удалять задачу.

    Удалять задачу может только автор или суперпользователь.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если удаление разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return task.user_id == user.id


def can_start_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, может ли пользователь принять задачу в работу (перевести в IN_PROGRESS).

    Принять в работу может ответственный или исполнитель, если задача находится
    в статусе 'new', 'assigned' или 'returned'.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если действие разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if task.status not in ('new', 'assigned', 'returned'):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if task.responsible_id == user.id or task.user_id == user.id:
        return True
    return task.assignees.filter(id=user.id).exists()


def can_submit_for_review(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, может ли пользователь отправить задачу на проверку (статус ON_REVIEW).

    Отправить на проверку может ответственный или исполнитель из статуса 'in_progress'.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если действие разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if task.status != 'in_progress':
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if task.responsible_id == user.id or task.user_id == user.id:
        return True
    return task.assignees.filter(id=user.id).exists()


def can_accept_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, может ли пользователь окончательно принять выполнение задачи (COMPLETED).

    Принять выполнение может только постановщик (автор) задачи или администратор.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если приемка разрешена, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if task.status == 'completed':
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return task.user_id == user.id


def can_return_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, может ли пользователь вернуть задачу на доработку (RETURNED).

    Вернуть на доработку может автор задачи из статуса 'on_review' (или 'in_progress').

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если возврат разрешен, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if task.status not in ('on_review', 'in_progress'):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return task.user_id == user.id


def can_delegate_task(user: 'DataBaseUser', task: 'Task') -> bool:
    """Проверяет, может ли пользователь делегировать задачу другим сотрудникам.

    Делегировать может автор, ответственный или администратор.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        task (Task): Экземпляр задачи.

    Returns:
        bool: True если делегирование разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return task.user_id == user.id or task.responsible_id == user.id


def can_toggle_subtask(user: 'DataBaseUser', subtask: 'SubTask') -> bool:
    """Проверяет, может ли пользователь переключить отметку выполнения подзадачи.

    Отметить чек-лист может автор задачи, ответственный, назначенный исполнитель
    подзадачи или любой соисполнитель задачи.

    Args:
        user (DataBaseUser): Проверяемый пользователь.
        subtask (SubTask): Экземпляр подзадачи.

    Returns:
        bool: True если переключение разрешено, иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if subtask.assigned_to_id == user.id:
        return True
    task = subtask.task
    if task.user_id == user.id or task.responsible_id == user.id:
        return True
    return task.assignees.filter(id=user.id).exists()
