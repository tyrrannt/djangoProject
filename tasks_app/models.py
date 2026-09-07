"""Модели данных для подсистемы управления задачами и поручениями (tasks_app).

Модуль реализует корпоративную модель управления поручениями, задачами,
делегированием, чек-листами (подзадачами), комментариями, историей аудита,
повторяемостью (RRULE) и опциональным подтверждением приемки через ЭЦП.
"""

import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any, List, Optional, Tuple

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule
from django.db import models
from django.urls import reverse
from django.utils import timezone

from customers_app.models import DataBaseUser

logger = logging.getLogger(__name__)


class Category(models.Model):
    """Справочник категорий задач для тематической группировки.

    Attributes:
        name (str): Название категории задачи (например, 'Отчетность', 'IT', 'Кадры').
    """

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    name = models.CharField(max_length=100, unique=True, verbose_name='Название категории')

    def __str__(self) -> str:
        """Возвращает строковое представление категории.

        Returns:
            str: Название категории.
        """
        return self.name


class TaskStatus(models.TextChoices):
    """Статусный автомат жизненного цикла задачи / поручения.

    Состояния:
        DRAFT: Черновик, задача еще не отправлена в работу.
        NEW: Новая задача, назначена, ожидает подтверждения исполнителем.
        ASSIGNED: Назначена конкретному ответсвенному/исполнителям.
        IN_PROGRESS: Принята в работу исполнителем.
        ON_REVIEW: Выполнена исполнителем, ожидает проверки постановщиком.
        RETURNED: Возвращена постановщиком на доработку.
        COMPLETED: Окончательно принята и завершена.
        CANCELLED: Отменена постановщиком.
        OVERDUE: Дедлайн истек, задача просрочена.
    """

    DRAFT = 'draft', 'Черновик'
    NEW = 'new', 'Новая'
    ASSIGNED = 'assigned', 'Назначена'
    IN_PROGRESS = 'in_progress', 'В работе'
    ON_REVIEW = 'on_review', 'На проверке'
    RETURNED = 'returned', 'Возвращена на доработку'
    COMPLETED = 'completed', 'Выполнена'
    CANCELLED = 'cancelled', 'Отменена'
    OVERDUE = 'overdue', 'Просрочена'


class TaskRole(models.TextChoices):
    """Роли пользователей в рамках поручения/задачи.

    Состояния:
        RESPONSIBLE: Главный ответственный за исполнение.
        ASSIGNEE: Соисполнитель.
        OBSERVER: Наблюдатель (только чтение и комментарии).
    """

    RESPONSIBLE = 'responsible', 'Ответственный'
    ASSIGNEE = 'assignee', 'Исполнитель'
    OBSERVER = 'observer', 'Наблюдатель'


class AssignmentStatus(models.TextChoices):
    """Статусы делегирования и назначения поручений.

    Состояния:
        PENDING: Назначено, ожидает подтверждения.
        ACCEPTED: Принято сотрудником к исполнению.
        COMPLETED: Исполнено сотрудником.
        REJECTED: Отклонено с указанием причины.
    """

    PENDING = 'pending', 'Ожидает принятия'
    ACCEPTED = 'accepted', 'Принято в работу'
    COMPLETED = 'completed', 'Исполнено'
    REJECTED = 'rejected', 'Отклонено'


class Task(models.Model):
    """Основная модель задачи, поручения и календарного события.

    Поддерживает распределение ролей (автор, ответственный, исполнители, наблюдатели),
    статусный Workflow, расчет прогресса по чек-листу, движок повторяемости RRULE,
    а также гибкий режим визирования (без ЭЦП или с КриптоПро ЭЦП).

    Attributes:
        user (ForeignKey): Постановщик / Автор задачи (DataBaseUser).
        responsible (ForeignKey): Главный ответственный исполнитель.
        assignees (ManyToManyField): Список соисполнителей.
        observers (ManyToManyField): Список наблюдателей.
        shared_with (ManyToManyField): Список пользователей с общим доступом (обратная совместимость).
        title (str): Краткий заголовок поручения.
        description (str): Детальное описание и требования к задаче.
        status (str): Текущий статус задачи из TaskStatus.
        completed (bool): Флаг завершения (автосинхронизируется со статусом).
        priority (str): Уровень важности ('primary', 'warning', 'info', 'danger', 'dark').
        category (ForeignKey): Тематическая категория (Category).
        start_date (datetime): Дата и время начала/события.
        end_date (datetime): Плановый срок завершения (дедлайн).
        accepted_at (datetime): Дата и время принятия в работу.
        submitted_review_at (datetime): Дата отправки на проверку.
        completed_at (datetime): Дата и время фактического закрытия.
        requires_eds (bool): Требуется ли подписание результата ЭЦП при приемке.
        eds_signature (str): Сохраненная отсоединенная/присоединенная ЭЦП подпись.
        eds_signed_by (ForeignKey): Пользователь, подписавший приемку ЭЦП.
        eds_signed_at (datetime): Штамп времени подписания ЭЦП.
        repeat (str): Тип повторения ('none', 'daily', 'weekly', 'monthly', 'yearly', 'custom').
        repeat_interval (int): Шаг повторения.
        repeat_days (str): Дни недели повторения (например, "0,2,4").
        repeat_end_date (datetime): Предельный срок завершения цикла повторений.
        created_at (datetime): Дата создания записи.
        updated_at (datetime): Дата последней модификации записи.
    """

    PRIORITY_CHOICES = [
        ('primary', 'Основной (Обычный)'),
        ('warning', 'Внимание (Средний)'),
        ('info', 'Информационный (Низкий)'),
        ('danger', 'Высокий (Срочный)'),
        ('dark', 'Критический (Блокирующий)'),
    ]

    REPEAT_CHOICES = [
        ('none', 'Нет'),
        ('daily', 'Ежедневно'),
        ('weekly', 'Еженедельно'),
        ('monthly', 'Ежемесячно'),
        ('yearly', 'Ежегодно'),
        ('custom', 'Пользовательский интервал'),
    ]

    # Роли и участники
    user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='Постановщик / Автор'
    )
    responsible = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_tasks',
        verbose_name='Ответственный'
    )
    assignees = models.ManyToManyField(
        DataBaseUser,
        related_name='assigned_tasks',
        blank=True,
        verbose_name='Исполнители'
    )
    observers = models.ManyToManyField(
        DataBaseUser,
        related_name='observed_tasks',
        blank=True,
        verbose_name='Наблюдатели'
    )
    shared_with = models.ManyToManyField(
        DataBaseUser,
        related_name='shared_tasks',
        blank=True,
        verbose_name='Доступ для (шаринг)'
    )

    # Содержимое и статус
    title = models.CharField(max_length=200, verbose_name='Заголовок')
    description = models.TextField(blank=True, null=True, verbose_name='Описание задачи')
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.NEW,
        db_index=True,
        verbose_name='Статус'
    )
    completed = models.BooleanField(default=False, db_index=True, verbose_name='Завершено')
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='primary',
        db_index=True,
        verbose_name='Важность'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name='Категория'
    )

    # Временные рамки
    start_date = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name='Дата начала')
    end_date = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name='Дата завершения (дедлайн)')
    accepted_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата принятия в работу')
    submitted_review_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата отправки на проверку')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата фактического завершения')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    # ЭЦП-визирование (гибкий режим)
    requires_eds = models.BooleanField(default=False, verbose_name='Требуется ЭЦП при приемке')
    eds_signature = models.TextField(blank=True, null=True, verbose_name='ЭЦП подпись')
    eds_signed_by = models.ForeignKey(
        DataBaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='eds_signed_tasks',
        verbose_name='Подписал ЭЦП'
    )
    eds_signed_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата подписания ЭЦП')

    # Повторяемость (RRULE)
    repeat = models.CharField(
        max_length=10,
        choices=REPEAT_CHOICES,
        default='none',
        verbose_name='Повторяемость'
    )
    repeat_interval = models.PositiveIntegerField(default=1, verbose_name='Интервал повторения')
    repeat_days = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        verbose_name='Дни недели'
    )
    repeat_end_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата окончания повторения')

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['responsible', 'status']),
            models.Index(fields=['status', 'end_date']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['priority']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление задачи.

        Returns:
            str: Заголовок задачи.
        """
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Переопределенный метод сохранения с автосинхронизацией полей.

        Автоматически синхронизирует boolean-флаг completed со статусом COMPLETED,
        устанавливает дату завершения и выставляет ответственного по умолчанию.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        if self.status == TaskStatus.COMPLETED:
            self.completed = True
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.completed = False
            self.completed_at = None

        if not self.responsible_id and self.user_id:
            self.responsible = self.user

        super().save(*args, **kwargs)

    @property
    def progress_percent(self) -> int:
        """Рассчитывает процент выполнения задачи на основе чек-листа подзадач.

        Returns:
            int: Значение от 0 до 100.
        """
        if self.status == TaskStatus.COMPLETED:
            return 100

        total_subtasks = self.subtasks.count()
        if total_subtasks == 0:
            return 50 if self.status in (TaskStatus.IN_PROGRESS, TaskStatus.ON_REVIEW) else 0

        completed_subtasks = self.subtasks.filter(is_completed=True).count()
        return int((completed_subtasks / total_subtasks) * 100)

    @property
    def is_overdue(self) -> bool:
        """Проверяет, просрочена ли задача относительно текущего времени.

        Returns:
            bool: True если дедлайн наступил и задача не завершена, иначе False.
        """
        if self.status == TaskStatus.COMPLETED or not self.end_date:
            return False
        return self.end_date < timezone.now()

    def get_rrule(self) -> Optional[rrule]:
        """Возвращает объект dateutil.rrule для повторяющейся задачи.

        Returns:
            Optional[rrule]: Сконфигурированный объект правила повторения или None.
        """
        if self.repeat == 'none' or not self.start_date:
            return None

        freq_map = {
            'daily': DAILY,
            'weekly': WEEKLY,
            'monthly': MONTHLY,
            'yearly': YEARLY,
        }
        freq = freq_map.get(self.repeat, WEEKLY)

        byweekday = None
        if self.repeat_days and self.repeat_days not in ('', '[]', 'null', 'None'):
            try:
                if self.repeat_days.startswith('['):
                    days_list = json.loads(self.repeat_days)
                    byweekday = [int(day) for day in days_list if day is not None]
                else:
                    byweekday = [int(day.strip()) for day in self.repeat_days.split(',') if day.strip()]
            except (ValueError, json.JSONDecodeError, TypeError):
                byweekday = None

        try:
            return rrule(
                freq=freq,
                interval=self.repeat_interval or 1,
                dtstart=self.start_date,
                until=self.repeat_end_date if self.repeat_end_date else None,
                byweekday=byweekday
            )
        except (ValueError, TypeError) as exc:
            logger.error(f"Error creating rrule for task {self.id}: {exc}")
            return None

    def get_next_occurrence(self) -> Tuple[Optional[timezone.datetime], Optional[timezone.datetime]]:
        """Возвращает даты следующего повторения события (start, end).

        Returns:
            Tuple[Optional[datetime], Optional[datetime]]: Кортеж (next_start, next_end).
        """
        if self.repeat == 'none' or not self.start_date:
            return None, None

        if self.repeat_end_date and self.repeat_end_date < timezone.now():
            return None, None

        rule = self.get_rrule()
        if not rule:
            return None, None

        after_date = timezone.now()
        next_start = rule.after(after_date, inc=False)
        if not next_start:
            return None, None

        next_end = None
        if self.end_date and self.start_date:
            duration = self.end_date - self.start_date
            next_end = next_start + duration

        return next_start, next_end

    def create_next_task(self) -> Optional['Task']:
        """Создает в БД следующий экземпляр задачи на основе RRULE.

        Returns:
            Optional[Task]: Созданный объект задачи или None.
        """
        next_start, next_end = self.get_next_occurrence()
        if not next_start:
            return None

        next_task = Task.objects.create(
            user=self.user,
            responsible=self.responsible,
            title=self.title,
            description=self.description,
            start_date=next_start,
            end_date=next_end,
            priority=self.priority,
            category=self.category,
            repeat=self.repeat,
            repeat_interval=self.repeat_interval,
            repeat_days=self.repeat_days,
            repeat_end_date=self.repeat_end_date,
            requires_eds=self.requires_eds,
            status=TaskStatus.NEW
        )

        next_task.assignees.set(self.assignees.all())
        next_task.observers.set(self.observers.all())
        next_task.shared_with.set(self.shared_with.all())

        return next_task

    def get_absolute_url(self) -> str:
        """Возвращает канонический URL детального просмотра задачи.

        Returns:
            str: URL детальной карточки.
        """
        return reverse('tasks_app:task-detail', args=[str(self.id)])


class TaskAssignment(models.Model):
    """Модель делегирования и назначения поручения сотруднику.

    Фиксирует факт передачи задачи, роль, статус принятия и временные метки.

    Attributes:
        task (ForeignKey): Ссылка на родительскую задачу (Task).
        assigned_by (ForeignKey): Пользователь, выдавший поручение.
        assigned_to (ForeignKey): Назначенный сотрудник.
        role (str): Назначенная роль (TaskRole).
        status (str): Статус принятия поручения (AssignmentStatus).
        comment (str): Комментарий к поручению.
        assigned_at (datetime): Дата и время выдачи поручения.
        accepted_at (datetime): Дата и время подтверждения исполнителем.
        completed_at (datetime): Дата и время завершения поручения.
    """

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Задача'
    )
    assigned_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name='task_assignments_given',
        verbose_name='Кто назначил'
    )
    assigned_to = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name='task_assignments_received',
        verbose_name='Кому назначено'
    )
    role = models.CharField(
        max_length=20,
        choices=TaskRole.choices,
        default=TaskRole.ASSIGNEE,
        verbose_name='Роль'
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.PENDING,
        verbose_name='Статус поручения'
    )
    comment = models.TextField(blank=True, default='', verbose_name='Комментарий к поручению')
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата назначения')
    accepted_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата принятия')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата завершения')

    class Meta:
        verbose_name = 'Поручение / Делегирование'
        verbose_name_plural = 'Поручения и делегирование'
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['task', 'assigned_to']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self) -> str:
        """Строковое представление назначения.

        Returns:
            str: Описание назначения.
        """
        return f"{self.task.title} -> {self.assigned_to.get_full_name()} ({self.get_role_display()})"


class SubTask(models.Model):
    """Модель подзадачи / элемента чек-листа в рамках задачи.

    Attributes:
        task (ForeignKey): Ссылка на родительскую задачу (Task).
        title (str): Наименование пункта чек-листа.
        assigned_to (ForeignKey): Ответственный за данный пункт сотрудник.
        is_completed (bool): Флаг выполнения пункта.
        completed_by (ForeignKey): Пользователь, отметивший выполнение.
        completed_at (datetime): Дата и время отметки выполнения.
        order (int): Порядковый номер для сортировки в интерфейсе.
        created_at (datetime): Дата создания подзадачи.
    """

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='subtasks',
        verbose_name='Задача'
    )
    title = models.CharField(max_length=255, verbose_name='Наименование подзадачи')
    assigned_to = models.ForeignKey(
        DataBaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='subtasks',
        verbose_name='Исполнитель'
    )
    is_completed = models.BooleanField(default=False, db_index=True, verbose_name='Выполнено')
    completed_by = models.ForeignKey(
        DataBaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='completed_subtasks',
        verbose_name='Кто выполнил'
    )
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата выполнения')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Подзадача / Чек-лист'
        verbose_name_plural = 'Подзадачи и чек-листы'
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['task', 'is_completed']),
        ]

    def __str__(self) -> str:
        """Строковое представление подзадачи.

        Returns:
            str: Название подзадачи и статус.
        """
        status_icon = '✓' if self.is_completed else '○'
        return f"[{status_icon}] {self.title}"


class TaskComment(models.Model):
    """Модель комментария и обсуждения в карточке задачи.

    Attributes:
        task (ForeignKey): Ссылка на задачу (Task).
        author (ForeignKey): Автор комментария (DataBaseUser).
        parent (ForeignKey): Родительский комментарий (для древовидных ответов).
        text (str): Текст комментария.
        created_at (datetime): Дата и время создания комментария.
        updated_at (datetime): Дата и время последнего редактирования.
    """

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Задача'
    )
    author = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name='task_comments',
        verbose_name='Автор комментария'
    )
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies',
        verbose_name='Ответ на комментарий'
    )
    text = models.TextField(verbose_name='Текст комментария')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Комментарий к задаче'
        verbose_name_plural = 'Комментарии к задачам'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['task', 'created_at']),
        ]

    def __str__(self) -> str:
        """Строковое представление комментария.

        Returns:
            str: Краткий фрагмент комментария.
        """
        author_name = self.author.get_full_name() or self.author.username
        return f"{author_name}: {self.text[:40]}"


class TaskHistory(models.Model):
    """Модель журнала аудита действий и изменений по задаче.

    Attributes:
        task (ForeignKey): Ссылка на задачу (Task).
        user (ForeignKey): Пользователь, совершивший действие (DataBaseUser).
        action (str): Тип совершенного действия (ActionType).
        old_value (str): Старое значение изменяемого параметра.
        new_value (str): Новое значение изменяемого параметра.
        comment (str): Пояснительный комментарий или причина изменения.
        created_at (datetime): Дата и время совершения действия.
    """

    class ActionType(models.TextChoices):
        CREATED = 'created', 'Задача создана'
        STATUS_CHANGED = 'status_changed', 'Изменен статус'
        ASSIGNED = 'assigned', 'Назначен исполнитель'
        DELEGATED = 'delegated', 'Задача делегирована'
        ACCEPTED = 'accepted', 'Принята в работу'
        SUBMITTED_REVIEW = 'submitted_review', 'Отправлена на проверку'
        RETURNED = 'returned', 'Возвращена на доработку'
        COMPLETED = 'completed', 'Выполнена'
        CANCELLED = 'cancelled', 'Отменена'
        DEADLINE_CHANGED = 'deadline_changed', 'Изменен дедлайн'
        SUBTASK_TOGGLED = 'subtask_toggled', 'Изменен чек-лист'
        FILE_ADDED = 'file_added', 'Прикреплен файл'
        FILE_DELETED = 'file_deleted', 'Удален файл'
        COMMENT_ADDED = 'comment_added', 'Добавлен комментарий'
        EDS_SIGNED = 'eds_signed', 'Подписано ЭЦП'

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Задача'
    )
    user = models.ForeignKey(
        DataBaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='task_history_records',
        verbose_name='Пользователь'
    )
    action = models.CharField(
        max_length=30,
        choices=ActionType.choices,
        verbose_name='Действие'
    )
    old_value = models.TextField(blank=True, null=True, verbose_name='Старое значение')
    new_value = models.TextField(blank=True, null=True, verbose_name='Новое значение')
    comment = models.TextField(blank=True, default='', verbose_name='Примечание / Причина')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время фиксации')

    class Meta:
        verbose_name = 'Запись истории задачи'
        verbose_name_plural = 'История изменений задач'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', '-created_at']),
        ]

    def __str__(self) -> str:
        """Строковое представление записи аудита.

        Returns:
            str: Краткое описание действия.
        """
        user_name = self.user.get_full_name() if self.user else 'Система'
        return f"{self.created_at.strftime('%d.%m.%Y %H:%M')} [{user_name}] {self.get_action_display()}"

    @classmethod
    def log(
        cls,
        task: Task,
        user: Optional[DataBaseUser],
        action: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        comment: str = ''
    ) -> 'TaskHistory':
        """Вспомогательный метод для удобного создания записи аудита.

        Args:
            task (Task): Экземпляр задачи.
            user (Optional[DataBaseUser]): Пользователь, инициировавший действие.
            action (str): Код действия из ActionType.
            old_value (Optional[str]): Предыдущее значение.
            new_value (Optional[str]): Новое значение.
            comment (str): Пояснительный комментарий.

        Returns:
            TaskHistory: Созданная запись аудита.
        """
        return cls.objects.create(
            task=task,
            user=user,
            action=action,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            comment=comment
        )


def get_task_file_path(instance: 'TaskFile', filename: str) -> str:
    """Генерирует изолированный путь для сохранения вложений к задачам.

    Формат пути: task_files/YYYY/MM/<username>/<uuid4>.<ext>

    Args:
        instance (TaskFile): Экземпляр прикрепляемого файла.
        filename (str): Исходное имя загруженного файла.

    Returns:
        str: Относительный путь для сохранения в хранилище Django.
    """
    ext = os.path.splitext(filename)[1].lower()
    new_name = f"{uuid.uuid4().hex}{ext}"
    date_path = timezone.now().strftime("%Y/%m")

    username = "unknown"
    if instance.task and instance.task.user:
        username = getattr(instance.task.user, 'username', str(instance.task.user.id))

    return f"task_files/{date_path}/{username}/{new_name}"


class TaskFile(models.Model):
    """Модель прикрепленного к задаче файла / документа.

    Attributes:
        task (ForeignKey): Ссылка на задачу (Task).
        uploaded_by (ForeignKey): Пользователь, загрузивший файл (DataBaseUser).
        file (FileField): Физический файл в хранилище.
        original_filename (str): Исходное имя файла при загрузке.
        file_size (int): Размер файла в байтах.
        description (str): Описание назначения файла.
        uploaded_at (datetime): Дата и время загрузки.
    """

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files', verbose_name='Задача')
    uploaded_by = models.ForeignKey(
        DataBaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_task_files',
        verbose_name='Загрузил'
    )
    file = models.FileField(upload_to=get_task_file_path, verbose_name="Файл")
    original_filename = models.CharField(max_length=255, blank=True, null=True, verbose_name="Оригинальное имя")
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="Размер файла (байт)")
    description = models.CharField(max_length=255, blank=True, default='', verbose_name="Описание файла")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = 'Файл задачи'
        verbose_name_plural = 'Файлы задач'
        indexes = [
            models.Index(fields=['task', '-uploaded_at']),
        ]

    def __str__(self) -> str:
        """Строковое представление файла.

        Returns:
            str: Исходное или сгенерированное имя файла.
        """
        return self.original_filename or self.file.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Автоматически заполняет размер файла при сохранении.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        if self.file and hasattr(self.file, 'size') and not self.file_size:
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Удаляет физический файл с диска при удалении записи из базы данных.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)