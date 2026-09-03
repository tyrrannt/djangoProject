"""Модели данных системы периодического тестирования сотрудников (testing_app)."""

import os
import uuid
from typing import Optional, List, Dict, Any
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class QuestionCategory(models.Model):
    """Категория вопросов для тестирования.

    Attributes:
        name (str): Название категории.
        description (str): Подробное описание категории вопросов.
        is_active (bool): Признак активности категории.
        created_at (datetime): Дата и время создания.
        updated_at (datetime): Дата и время последнего обновления.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название категории"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активна"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Категория вопросов"
        verbose_name_plural = "Категории вопросов"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def active_questions_count(self) -> int:
        """Возвращает количество активных вопросов в категории."""
        return self.questions.filter(status=Question.Status.ACTIVE).count()


class Question(models.Model):
    """Вопрос из банка вопросов тестирования.

    Attributes:
        category (QuestionCategory): Категория, к которой относится вопрос.
        text (str): Текст вопроса.
        explanation (str): Пояснение к правильному ответу (опционально).
        status (str): Статус вопроса (активный, архивный).
        difficulty (str): Уровень сложности.
        times_used (int): Количество использований вопроса в тестах.
        times_correct (int): Количество правильных ответов сотрудников.
        times_incorrect (int): Количество неправильных ответов.
        last_used_at (datetime): Дата последнего включения в тест.
        author (User): Пользователь, создавший вопрос.
        created_at (datetime): Дата создания.
        updated_at (datetime): Дата изменения.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Активный"
        ARCHIVED = "archived", "Архивный"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Низкая"
        MEDIUM = "medium", "Средняя"
        HARD = "hard", "Повышенная"
        VERY_HARD = "very_hard", "Высокая"

    category = models.ForeignKey(
        QuestionCategory,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Категория"
    )
    text = models.TextField(
        verbose_name="Текст вопроса"
    )
    explanation = models.TextField(
        blank=True,
        default="",
        verbose_name="Пояснение правильного ответа"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="Статус"
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        verbose_name="Уровень сложности"
    )
    times_used = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество использований"
    )
    times_correct = models.PositiveIntegerField(
        default=0,
        verbose_name="Правильных ответов"
    )
    times_incorrect = models.PositiveIntegerField(
        default=0,
        verbose_name="Неправильных ответов"
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата последнего использования"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_questions",
        verbose_name="Автор вопроса"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения"
    )

    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Банк вопросов"
        ordering = ["category", "id"]

    def __str__(self) -> str:
        return f"[{self.category.name}] {self.text[:80]}"

    def get_correct_option(self) -> Optional["AnswerOption"]:
        """Возвращает правильный вариант ответа."""
        return self.options.filter(is_correct=True).first()

    @property
    def success_rate(self) -> float:
        """Рассчитывает процент успешных ответов на данный вопрос."""
        total = self.times_correct + self.times_incorrect
        if total == 0:
            return 0.0
        return round((self.times_correct / total) * 100, 1)


class AnswerOption(models.Model):
    """Вариант ответа на вопрос.

    Attributes:
        question (Question): Вопрос.
        text (str): Текст варианта ответа.
        order_num (int): Порядковый номер в вопросе.
        is_correct (bool): Признак правильности ответа.
    """

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Вопрос"
    )
    text = models.TextField(
        verbose_name="Текст варианта ответа"
    )
    order_num = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Порядковый номер"
    )
    is_correct = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Правильный ответ"
    )

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответов"
        ordering = ["order_num"]

    def __str__(self) -> str:
        mark = "✓" if self.is_correct else "✗"
        return f"{mark} {self.text[:60]}"


class Testing(models.Model):
    """Мероприятие тестирования сотрудников (на основании приказа).

    Attributes:
        title (str): Наименование тестирования.
        order_number (str): Номер приказа.
        order_date (date): Дата приказа.
        order_name (str): Наименование приказа.
        description (str): Текстовое описание.
        start_datetime (datetime): Начало периода тестирования.
        end_datetime (datetime): Окончание периода тестирования.
        questions_count (int): Количество вопросов в тесте.
        passing_score_percentage (int): Проходной процент (по умолчанию 80%).
        max_attempts (int): Максимальное количество попыток (по умолчанию 5).
        attempt_duration_minutes (int): Продолжительность одной попытки в минутах (по умолчанию 60).
        status (str): Статус мероприятия (черновик, подготовка, активно, завершено, архив).
        author (User): Автор создания.
        updated_by (User): Автор последнего изменения.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PREPARING = "preparing", "Подготовка"
        SCHEDULED = "scheduled", "Запланировано"
        ACTIVE = "active", "Активно"
        COMPLETED = "completed", "Завершено"
        ARCHIVED = "archived", "Архив"

    title = models.CharField(
        max_length=255,
        verbose_name="Наименование тестирования"
    )
    order_number = models.CharField(
        max_length=100,
        verbose_name="Номер приказа"
    )
    order_date = models.DateField(
        verbose_name="Дата приказа"
    )
    order_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Наименование приказа"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание мероприятия"
    )
    start_datetime = models.DateTimeField(
        verbose_name="Дата и время начала"
    )
    end_datetime = models.DateTimeField(
        verbose_name="Дата и время окончания"
    )
    questions_count = models.PositiveIntegerField(
        default=20,
        verbose_name="Количество вопросов"
    )
    passing_score_percentage = models.PositiveIntegerField(
        default=80,
        verbose_name="Проходной процент (%)"
    )
    max_attempts = models.PositiveIntegerField(
        default=5,
        verbose_name="Максимум попыток"
    )
    attempt_duration_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Продолжительность попытки (мин)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус мероприятия"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_testings",
        verbose_name="Автор"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_testings",
        verbose_name="Автор последнего изменения"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения"
    )

    class Meta:
        verbose_name = "Мероприятие тестирования"
        verbose_name_plural = "Мероприятия тестирования"
        ordering = ["-start_datetime"]

    def __str__(self) -> str:
        return f"{self.title} (Приказ №{self.order_number} от {self.order_date.strftime('%d.%m.%Y')})"

    @property
    def is_active_now(self) -> bool:
        """Проверяет, активно ли мероприятие в данный момент по времени и статусу."""
        now = timezone.now()
        return self.status == self.Status.ACTIVE and self.start_datetime <= now <= self.end_datetime

    def check_readiness(self) -> List[str]:
        """Проверяет критерии готовности мероприятия к запуску согласно разделу 85 ТЗ.

        Returns:
            List[str]: Список ошибок/предупреждений (пустой, если готово к запуску).
        """
        errors = []
        if not self.title.strip():
            errors.append("Не указано наименование тестирования.")
        if not self.order_number.strip():
            errors.append("Не указан номер приказа.")
        if not self.order_date:
            errors.append("Не указана дата приказа.")
        if self.start_datetime >= self.end_datetime:
            errors.append("Дата начала должна быть строго раньше даты окончания.")
        if self.questions_count <= 0:
            errors.append("Количество вопросов должно быть больше нуля.")
        if not (1 <= self.passing_score_percentage <= 100):
            errors.append("Проходной процент должен быть в диапазоне от 1 до 100%.")
        if self.attempt_duration_minutes <= 0:
            errors.append("Продолжительность попытки должна быть больше 0 минут.")
        if self.max_attempts <= 0:
            errors.append("Количество попыток должно быть не менее 1.")

        # Проверка групп
        groups = self.groups.all()
        if groups.count() < 2:
            errors.append("Должны быть сформированы обе группы сотрудников.")

        # Проверка суммы процентов категорий
        cat_settings = self.category_settings.all()
        total_percent = sum(cs.percentage for cs in cat_settings)
        if total_percent != 100:
            errors.append(f"Сумма процентов категорий должна быть строго 100% (текущая: {total_percent}%).")

        # Проверка достаточности вопросов в категориях
        for cs in cat_settings:
            active_q = cs.category.active_questions_count()
            needed_q = cs.calculated_questions_count or round((cs.percentage / 100.0) * self.questions_count)
            if active_q < needed_q:
                errors.append(
                    f"Недостаточно активных вопросов в категории '{cs.category.name}': требуется {needed_q}, доступно {active_q}."
                )

        # Проверка наличия сотрудников
        assignments_count = self.assignments.count()
        if assignments_count == 0:
            errors.append("Не назначен ни один сотрудник.")

        return errors


class TestingGroup(models.Model):
    """Группа сотрудников в рамках мероприятия тестирования.

    Attributes:
        testing (Testing): Мероприятие тестирования.
        name (str): Наименование группы («Выполняющие работы по обеспечению ТО ВС» / «Выполняющие ТО ВС»).
        code (str): Служебный код группы.
        description (str): Описание группы.
    """

    class Code(models.TextChoices):
        ENSURING = "ensuring_maintenance", "Обеспечение ТО ВС"
        PERFORMING = "performing_maintenance", "Выполнение ТО ВС"
        OTHER = "other", "Другая"

    testing = models.ForeignKey(
        Testing,
        on_delete=models.CASCADE,
        related_name="groups",
        verbose_name="Мероприятие тестирования"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Наименование группы"
    )
    code = models.CharField(
        max_length=50,
        choices=Code.choices,
        default=Code.PERFORMING,
        verbose_name="Код группы"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание группы"
    )

    class Meta:
        verbose_name = "Группа тестирования"
        verbose_name_plural = "Группы тестирования"
        unique_together = [("testing", "name")]

    def __str__(self) -> str:
        return f"{self.name} ({self.testing.title})"


class TestingGroupPosition(models.Model):
    """Связь группы тестирования с должностями сотрудников.

    Attributes:
        group (TestingGroup): Группа сотрудников.
        job (Job): Должность из справочника customers_app.Job.
    """

    group = models.ForeignKey(
        TestingGroup,
        on_delete=models.CASCADE,
        related_name="group_positions",
        verbose_name="Группа тестирования"
    )
    job = models.ForeignKey(
        "customers_app.Job",
        on_delete=models.CASCADE,
        related_name="testing_group_positions",
        verbose_name="Должность"
    )

    class Meta:
        verbose_name = "Должность группы тестирования"
        verbose_name_plural = "Должности групп тестирования"
        unique_together = [("group", "job")]

    def __str__(self) -> str:
        return f"{self.group.name} -> {self.job.name}"


class TestingCategorySetting(models.Model):
    """Процентное распределение вопросов по категориям для мероприятия.

    Attributes:
        testing (Testing): Мероприятие тестирования.
        category (QuestionCategory): Категория вопросов.
        percentage (int): Процент участия категории в тесте (0-100).
        calculated_questions_count (int): Расчетное количество вопросов в тесте.
    """

    testing = models.ForeignKey(
        Testing,
        on_delete=models.CASCADE,
        related_name="category_settings",
        verbose_name="Мероприятие"
    )
    category = models.ForeignKey(
        QuestionCategory,
        on_delete=models.CASCADE,
        related_name="testing_settings",
        verbose_name="Категория вопросов"
    )
    percentage = models.PositiveIntegerField(
        verbose_name="Процент участия (%)"
    )
    calculated_questions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Рассчитанное количество вопросов"
    )

    class Meta:
        verbose_name = "Настройка категории для тестирования"
        verbose_name_plural = "Настройки категорий для тестирования"
        unique_together = [("testing", "category")]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.percentage}% ({self.calculated_questions_count} вопр.)"


class TestingAssignment(models.Model):
    """Назначение сотрудника на мероприятие тестирования.

    Хранит снимок должности и подразделения сотрудника на момент назначения,
    текущий статус прохождения и статистику попыток.

    Attributes:
        testing (Testing): Мероприятие тестирования.
        group (TestingGroup): Группа, к которой прикреплен сотрудник.
        employee (User): Сотрудник.
        assigned_job_title (str): Снимок должности на момент назначения.
        assigned_division_title (str): Снимок подразделения на момент назначения.
        assignment_type (str): Способ формирования (авто по должности / вручную).
        status (str): Статус тестирования сотрудника.
        is_on_control (bool): Признак направления на контроль (после исчерпания 5 попыток).
        attempts_used (int): Количество использованных попыток.
        best_score (float): Лучший набранный результат в процентах.
        last_score (float): Последний набранный результат в процентах.
        assigned_at (datetime): Дата назначения.
        passed_at (datetime): Дата успешного прохождения.
    """

    class AssignmentType(models.TextChoices):
        AUTO = "auto_by_position", "Автоматически по должности"
        MANUAL = "manual", "Добавлен вручную"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Не начато"
        IN_PROGRESS = "in_progress", "В процессе"
        PASSED = "passed", "Пройдено"
        FAILED = "failed", "Не пройдено"
        ATTEMPTS_EXHAUSTED = "attempts_exhausted", "Попытки исчерпаны"
        ON_CONTROL = "on_control", "Направлен на контроль"
        PERIOD_EXPIRED = "period_expired", "Период завершен"
        OVERDUE = "overdue", "Не завершено в установленный срок"

    testing = models.ForeignKey(
        Testing,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Мероприятие"
    )
    group = models.ForeignKey(
        TestingGroup,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Группа"
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="testing_assignments",
        verbose_name="Сотрудник"
    )
    assigned_job_title = models.CharField(
        max_length=255,
        verbose_name="Должность на момент назначения"
    )
    assigned_division_title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Подразделение на момент назначения"
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.AUTO,
        verbose_name="Способ назначения"
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        db_index=True,
        verbose_name="Статус тестирования"
    )
    is_on_control = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Направлен на контроль"
    )
    attempts_used = models.PositiveIntegerField(
        default=0,
        verbose_name="Использовано попыток"
    )
    best_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Лучший результат (%)"
    )
    last_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Последний результат (%)"
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата назначения"
    )
    passed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата успешной сдачи"
    )

    class Meta:
        verbose_name = "Назначение сотрудника на тестирование"
        verbose_name_plural = "Назначения сотрудников"
        unique_together = [("testing", "employee")]
        ordering = ["assigned_division_title", "assigned_job_title", "employee__last_name"]

    def __str__(self) -> str:
        return f"{self.employee.get_full_name()} — {self.testing.title} [{self.get_status_display()}]"

    @property
    def remaining_attempts(self) -> int:
        """Возвращает количество оставшихся попыток."""
        return max(0, self.testing.max_attempts - self.attempts_used)

    @property
    def can_start_new_attempt(self) -> bool:
        """Проверяет, имеет ли сотрудник право начать новую попытку."""
        if not self.testing.is_active_now:
            return False
        if self.status == self.Status.PASSED:
            return False
        if self.attempts_used >= self.testing.max_attempts:
            return False
        # Проверяем нет ли уже незавершенной попытки в статусе in_progress
        has_active = self.attempts.filter(status=TestingAttempt.Status.IN_PROGRESS).exists()
        return not has_active


class TestingAttempt(models.Model):
    """Попытка прохождения тестирования сотрудником.

    Attributes:
        assignment (TestingAssignment): Назначение сотрудника.
        attempt_number (int): Номер попытки (1..5).
        started_at (datetime): Дата и время старта.
        planned_end_at (datetime): Время истечения серверного таймера попытки.
        completed_at (datetime): Фактическое время завершения.
        duration_seconds (int): Фактическая продолжительность в секундах.
        status (str): Статус попытки (в процессе, завершена, время истекло, отменена).
        total_questions (int): Всего вопросов в тесте.
        correct_answers (int): Количество правильных ответов.
        score_percentage (float): Набранный процент правильных ответов.
        is_passed (bool): Сдано успешно или нет.
        completion_reason (str): Причина завершения попытки.
        certificate_uuid (UUID): Уникальный неизменяемый UUID для QR-кода и уведомления.
        result_number (str): Уникальный номер уведомления (БАРКОЛ-ТО-YYYY-XXXXXX).
        qr_code_image (Image): Сгенерированное изображение QR-кода.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершена"
        EXPIRED = "expired", "Время истекло"
        CANCELLED = "cancelled", "Отменена"

    class CompletionReason(models.TextChoices):
        USER_COMPLETED = "user_completed", "Завершено пользователем"
        TIME_EXPIRED = "time_expired", "Время попытки истекло"
        PERIOD_EXPIRED = "period_expired", "Период тестирования завершен"
        ADMIN_TERMINATED = "admin_terminated", "Административное завершение"

    CompletionReason.MANUAL = CompletionReason.USER_COMPLETED
    CompletionReason.TIMEOUT = CompletionReason.TIME_EXPIRED

    assignment = models.ForeignKey(
        TestingAssignment,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name="Назначение сотрудника"
    )
    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name="Номер попытки"
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время начала"
    )
    planned_end_at = models.DateTimeField(
        verbose_name="Плановое время окончания (таймер)"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время завершения"
    )
    duration_seconds = models.PositiveIntegerField(
        default=0,
        verbose_name="Продолжительность (сек)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
        verbose_name="Статус попытки"
    )
    total_questions = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего вопросов"
    )
    correct_answers = models.PositiveIntegerField(
        default=0,
        verbose_name="Правильных ответов"
    )
    score_percentage = models.FloatField(
        default=0.0,
        verbose_name="Результат (%)"
    )
    is_passed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Тест пройден успешно"
    )
    completion_reason = models.CharField(
        max_length=30,
        choices=CompletionReason.choices,
        default=CompletionReason.USER_COMPLETED,
        verbose_name="Причина завершения"
    )
    certificate_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        verbose_name="Уникальный UUID уведомления"
    )
    result_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Номер результата (TEST-YYYY-XXXX)"
    )
    qr_code_image = models.ImageField(
        upload_to="testing_qr_codes/",
        null=True,
        blank=True,
        verbose_name="QR-код проверки"
    )

    class Meta:
        verbose_name = "Попытка тестирования"
        verbose_name_plural = "Попытки тестирования"
        unique_together = [("assignment", "attempt_number")]
        ordering = ["-started_at"]

    def __str__(self) -> str:
        res = "ПРОЙДЕНО" if self.is_passed else "НЕ ПРОЙДЕНО"
        return f"{self.assignment.employee.get_full_name()} — Попытка {self.attempt_number} [{res}]"

    def get_remaining_seconds(self) -> int:
        """Рассчитывает оставшееся время попытки на сервере."""
        if self.status != self.Status.IN_PROGRESS:
            return 0
        now = timezone.now()
        # Лимит по таймеру попытки и лимит по дате окончания всего мероприятия
        effective_deadline = min(self.planned_end_at, self.assignment.testing.end_datetime)
        diff = (effective_deadline - now).total_seconds()
        return max(0, int(diff))

    @property
    def passing_score_percentage(self) -> int:
        """Проходной балл тестирования в процентах из родительского мероприятия.

        Returns:
            int: Пороговый процент успешного прохождения теста (по умолчанию 80).
        """
        if hasattr(self, "assignment") and self.assignment and hasattr(self.assignment, "testing") and self.assignment.testing:
            return self.assignment.testing.passing_score_percentage
        return 80

    @property
    def correct_answers_count(self) -> int:
        """Количество правильных ответов (псевдоним для поля correct_answers).

        Returns:
            int: Количество правильных ответов в попытке.
        """
        return self.correct_answers

    @correct_answers_count.setter
    def correct_answers_count(self, value: int) -> None:
        """Сеттер для обратной совместимости с correct_answers."""
        self.correct_answers = value

    @property
    def finished_at(self):
        """Дата и время завершения попытки (псевдоним для поля completed_at).

        Returns:
            Optional[datetime]: Время фактического завершения попытки.
        """
        return self.completed_at

    @finished_at.setter
    def finished_at(self, value) -> None:
        """Сеттер для обратной совместимости с completed_at."""
        self.completed_at = value


class AttemptQuestion(models.Model):
    """Снимок конкретного вопроса в рамках попытки тестирования (НЕИЗМЕНЯЕМЫЙ SNAPSHOT).

    Attributes:
        attempt (TestingAttempt): Попытка.
        source_question (Question): Исходный вопрос из банка.
        category_name (str): Название категории на момент снимка.
        order_num (int): Порядковый номер вопроса в данной попытке (1..N).
        question_text (str): Зафиксированный текст вопроса.
        options_snapshot (list): JSON-список вариантов ответов в перемешанном порядке:
            [{'id': 1, 'text': '...', 'is_correct': True, 'order': 1}, ...]
    """

    attempt = models.ForeignKey(
        TestingAttempt,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Попытка"
    )
    source_question = models.ForeignKey(
        Question,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempt_questions",
        verbose_name="Исходный вопрос"
    )
    category_name = models.CharField(
        max_length=255,
        verbose_name="Категория вопроса (снимок)"
    )
    order_num = models.PositiveIntegerField(
        verbose_name="Порядковый номер"
    )
    question_text = models.TextField(
        verbose_name="Текст вопроса (снимок)"
    )
    options_snapshot = models.JSONField(
        default=list,
        verbose_name="Снимок вариантов ответов"
    )

    class Meta:
        verbose_name = "Вопрос попытки (снимок)"
        verbose_name_plural = "Вопросы попытки (снимки)"
        ordering = ["order_num"]
        unique_together = [("attempt", "order_num")]

    def __str__(self) -> str:
        return f"Вопрос {self.order_num} попытки #{self.attempt.id}"

    @property
    def explanation(self) -> str:
        """Пояснение к правильному ответу на основе исходного вопроса.

        Returns:
            str: Текст пояснения или пустая строка, если пояснение отсутствует.
        """
        if self.source_question and self.source_question.explanation:
            return self.source_question.explanation
        return ""

    def get_client_options(self) -> List[Dict[str, Any]]:
        """Возвращает варианты ответов для клиента БЕЗ поля 'is_correct' (защита от читерства)."""
        clean_options = []
        for opt in self.options_snapshot:
            clean_options.append({
                "id": opt.get("id"),
                "text": opt.get("text"),
                "order": opt.get("order")
            })
        return clean_options


class UserAnswer(models.Model):
    """Ответ сотрудника на конкретный вопрос попытки (черновик / финальный ответ).

    Attributes:
        attempt (TestingAttempt): Попытка.
        attempt_question (AttemptQuestion): Вопрос в попытке.
        selected_option_id (int): Идентификатор выбранного варианта ответа.
        is_correct (bool): Признак правильности ответа.
        first_viewed_at (datetime): Время первого отображения вопроса.
        answered_at (datetime): Время выбора ответа.
        updated_at (datetime): Время последнего изменения ответа.
        seconds_spent (int): Время в секундах, проведенное на вопросе.
    """

    attempt = models.ForeignKey(
        TestingAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Попытка"
    )
    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="user_answers",
        verbose_name="Вопрос попытки"
    )
    selected_option_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Выбранный вариант ID"
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name="Ответ правильный"
    )
    first_viewed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время первого просмотра"
    )
    answered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время ответа"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Время изменения"
    )
    seconds_spent = models.PositiveIntegerField(
        default=0,
        verbose_name="Затрачено секунд"
    )

    class Meta:
        verbose_name = "Ответ сотрудника"
        verbose_name_plural = "Ответы сотрудников"
        unique_together = [("attempt", "attempt_question")]

    def __str__(self) -> str:
        return f"Ответ на вопрос {self.attempt_question.order_num} ({self.attempt})"


class TestingAuditLog(models.Model):
    """Журнал аудита значимых действий в системе тестирования.

    Attributes:
        user (User): Пользователь, выполнивший действие.
        action (str): Код действия.
        object_repr (str): Текстовое описание целевого объекта.
        details (dict): Дополнительные параметры (старые/новые значения).
        ip_address (str): IP-адрес клиента.
        created_at (datetime): Дата и время действия.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь"
    )
    action = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Действие"
    )
    object_repr = models.CharField(
        max_length=255,
        verbose_name="Объект"
    )
    details = models.JSONField(
        default=dict,
        verbose_name="Детали изменения"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата и время"
    )

    class Meta:
        verbose_name = "Запись аудита тестирования"
        verbose_name_plural = "Журнал аудита тестирования"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        user_name = self.user.get_full_name() if self.user else "Система"
        return f"[{self.created_at.strftime('%d.%m.%Y %H:%M')}] {user_name}: {self.action} ({self.object_repr})"


# ==============================================================================
# ЛЕКЦИОННЫЕ И ВИДЕОМАТЕРИАЛЫ ДЛЯ ТЕСТИРОВАНИЯ
# ==============================================================================

def lecture_upload_path(instance, filename: str, prefix_dir: str, file_prefix: str) -> str:
    """Генерирует путь сохранения файла по шаблону: префикс/год/месяц/Префикс_UUID.расширение.

    Аналогично системе хранения документов и инструктажей Briefings.

    Args:
        instance (models.Model): Экземпляр модели (LectureMaterial или VideoLecture).
        filename (str): Исходное имя загружаемого пользователем файла.
        prefix_dir (str): Относительный базовый каталог сохранения.
        file_prefix (str): Префикс имени файла (DOC, SCAN, VIDEO).

    Returns:
        str: Относительный путь для сохранения файла в директории MEDIA.
    """
    now = timezone.now()
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    unique_id = uuid.uuid4().hex
    new_filename = f"{file_prefix}_{unique_id}.{ext}" if ext else f"{file_prefix}_{unique_id}"
    return os.path.join(prefix_dir, year_str, month_str, new_filename)


def lecture_doc_upload_to(instance, filename: str) -> str:
    """Формирует путь сохранения исходного документа лекции (.doc, .docx).

    Args:
        instance (LectureMaterial): Экземпляр лекционного материала.
        filename (str): Исходное имя файла.

    Returns:
        str: Относительный путь в формате: 'lectures/docs/YYYY/MM/DOC_UUID.ext'.
    """
    return lecture_upload_path(instance, filename, "lectures/docs", "DOC")


def lecture_scan_upload_to(instance, filename: str) -> str:
    """Формирует путь сохранения электронного образа (скана) лекции (.pdf).

    Args:
        instance (LectureMaterial): Экземпляр лекционного материала.
        filename (str): Исходное имя файла.

    Returns:
        str: Относительный путь в формате: 'lectures/scans/YYYY/MM/SCAN_UUID.ext'.
    """
    return lecture_upload_path(instance, filename, "lectures/scans", "SCAN")


def video_lecture_upload_to(instance, filename: str) -> str:
    """Формирует путь сохранения видеофайла лекции (.mp4).

    Args:
        instance (VideoLecture): Экземпляр видеолекции.
        filename (str): Исходное имя файла.

    Returns:
        str: Относительный путь в формате: 'lectures/videos/YYYY/MM/VIDEO_UUID.ext'.
    """
    return lecture_upload_path(instance, filename, "lectures/videos", "VIDEO")


class LectureMaterial(models.Model):
    """Модель лекционного материала для теоретической подготовки сотрудников.

    Хранит текстовые методические материалы, исходные редактируемые файлы (.doc, .docx)
    и электронные образы (.pdf) для онлайн-просмотра сотрудниками перед сдачей тестов.

    Attributes:
        title (str): Наименование лекционного материала.
        doc_file (FieldFile): Исходный файл документа (форматы doc, docx).
        scan_file (FieldFile): Скан документа для встроенного просмотра (формат pdf).
        is_actual (bool): Признак актуальности лекции (неактуальные скрыты от обычных сотрудников).
        description (str): Краткое описание или аннотация к лекции.
        created_by (ForeignKey): Пользователь (ответственный), добавивший лекцию.
        created_at (datetime): Дата и время добавления записи.
        updated_at (datetime): Дата и время последнего обновления.
    """

    title = models.CharField(
        max_length=255,
        verbose_name="Наименование лекции",
        db_index=True
    )
    doc_file = models.FileField(
        upload_to=lecture_doc_upload_to,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["doc", "docx"])],
        verbose_name="Файл документа (doc, docx)",
        help_text="Исходный редактируемый файл лекции в формате .doc или .docx"
    )
    scan_file = models.FileField(
        upload_to=lecture_scan_upload_to,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Скан документа (pdf)",
        help_text="Электронный образ или скан документа в формате PDF для встроенного просмотра"
    )
    is_actual = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Актуальность",
        help_text="Признак актуальности материала (неактуальные скрываются от сотрудников)"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание / Аннотация",
        help_text="Краткое содержание или методические указания к лекционному материалу"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_lectures",
        verbose_name="Создал"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Лекционный материал"
        verbose_name_plural = "Лекционные материалы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def total_views_count(self) -> int:
        """Суммарное количество обращений сотрудников к данному материалу."""
        res = self.view_logs.aggregate(total=models.Sum("views_count"))
        return res["total"] or 0

    @property
    def unique_viewers_count(self) -> int:
        """Количество уникальных сотрудников, открывавших данный материал."""
        return self.view_logs.values("user_id").distinct().count()


class VideoLecture(models.Model):
    """Модель видеолекции для теоретической подготовки сотрудников.

    Хранит видеоматериалы в формате MP4 для просмотра сотрудниками на портале.

    Attributes:
        title (str): Наименование видеолекции.
        video_file (FieldFile): Видеозапись лекции в формате .mp4.
        is_actual (bool): Признак актуальности видеоматериала.
        description (str): Краткое описание или план видеолекции.
        created_by (ForeignKey): Пользователь (ответственный), добавивший видео.
        created_at (datetime): Дата и время добавления записи.
        updated_at (datetime): Дата и время последнего обновления.
    """

    title = models.CharField(
        max_length=255,
        verbose_name="Наименование видеолекции",
        db_index=True
    )
    video_file = models.FileField(
        upload_to=video_lecture_upload_to,
        validators=[FileExtensionValidator(allowed_extensions=["mp4"])],
        verbose_name="Видеофайл (mp4)",
        help_text="Видеозапись в формате MP4"
    )
    is_actual = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Актуальность",
        help_text="Признак актуальности видеоматериала (неактуальные скрываются от сотрудников)"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание / Аннотация",
        help_text="Краткое содержание или таймкоды видеолекции"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_video_lectures",
        verbose_name="Создал"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Дата добавления"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Видеолекция"
        verbose_name_plural = "Видеолекции"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def total_views_count(self) -> int:
        """Суммарное количество обращений сотрудников к данной видеолекции."""
        res = self.view_logs.aggregate(total=models.Sum("views_count"))
        return res["total"] or 0

    @property
    def unique_viewers_count(self) -> int:
        """Количество уникальных сотрудников, просмотревших данную видеолекцию."""
        return self.view_logs.values("user_id").distinct().count()


class MaterialViewLog(models.Model):
    """Журнал фиксации обращений сотрудников к лекционным и видеоматериалам.

    Позволяет формировать сводную аналитику и отчетность по изучению
    теоретической базы перед сдачей тестирования.

    Attributes:
        user (ForeignKey): Сотрудник, изучавший материал.
        material_type (str): Тип учебного материала ('lecture' или 'video').
        lecture (ForeignKey): Ссылка на лекционный материал (если материал текстовый).
        video_lecture (ForeignKey): Ссылка на видеолекцию (если материал видео).
        first_viewed_at (datetime): Дата и время первого обращения сотрудника.
        last_viewed_at (datetime): Дата и время последнего обращения сотрудника.
        views_count (int): Общее число открытий / просмотров данным сотрудником.
        last_ip (str): IP-адрес сотрудника при последнем обращении.
    """

    class MaterialType(models.TextChoices):
        LECTURE = "lecture", "Лекционный материал"
        VIDEO = "video", "Видеолекция"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="material_views",
        verbose_name="Сотрудник"
    )
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        db_index=True,
        verbose_name="Тип материала"
    )
    lecture = models.ForeignKey(
        LectureMaterial,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="view_logs",
        verbose_name="Лекционный материал"
    )
    video_lecture = models.ForeignKey(
        VideoLecture,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="view_logs",
        verbose_name="Видеолекция"
    )
    first_viewed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Первое обращение"
    )
    last_viewed_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name="Последнее обращение"
    )
    views_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Количество обращений"
    )
    last_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес"
    )

    class Meta:
        verbose_name = "Запись журнала обращений к материалам"
        verbose_name_plural = "Журнал обращений к материалам"
        ordering = ["-last_viewed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lecture"],
                name="unique_user_lecture_view",
                condition=models.Q(lecture__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["user", "video_lecture"],
                name="unique_user_video_view",
                condition=models.Q(video_lecture__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        mat_title = self.lecture.title if self.lecture else (self.video_lecture.title if self.video_lecture else "Не указан")
        user_name = self.user.get_full_name() if self.user else "Неизвестный"
        return f"{user_name} -> {mat_title} ({self.get_material_type_display()}, обращений: {self.views_count})"

