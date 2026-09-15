"""Административные интерфейсы модуля периодического тестирования сотрудников."""

from typing import Optional, Tuple, Any
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter

from testing_app.models import (
    QuestionCategory,
    Question,
    AnswerOption,
    Testing,
    TestingGroup,
    TestingGroupPosition,
    TestingCategorySetting,
    TestingAssignment,
    TestingAttempt,
    AttemptQuestion,
    UserAnswer,
    TestingAuditLog,
    LectureMaterial,
    VideoLecture,
    MaterialViewLog,
)


class AnswerOptionInline(TabularInline):
    """Инлайн вариантов ответа в вопросе."""
    model = AnswerOption
    extra = 4
    fields = ("order_num", "text", "is_correct")


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(ModelAdmin):
    """Админка категорий вопросов."""
    list_display = ("name", "display_active", "questions_count", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_active", ("created_at", RangeDateFilter))
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Активна", boolean=True)
    def display_active(self, obj: QuestionCategory) -> bool:
        return obj.is_active

    def questions_count(self, obj: QuestionCategory) -> int:
        return obj.questions.count()

    questions_count.short_description = "Всего вопросов"


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    """Админка банка вопросов."""
    list_display = (
        "display_question_header",
        "category",
        "display_status",
        "display_difficulty",
        "times_used",
        "success_rate_display",
    )
    list_filter = (
        "status",
        "difficulty",
        "category",
    )
    search_fields = ("text", "explanation")
    autocomplete_fields = ["category"]
    inlines = [AnswerOptionInline]
    readonly_fields = (
        "times_used",
        "times_correct",
        "times_incorrect",
        "last_used_at",
        "created_at",
        "updated_at",
    )
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Вопрос", header=True)
    def display_question_header(self, obj: Question) -> Tuple[str, str]:
        """Возвращает ID вопроса и сокращенный текст."""
        short = obj.text[:70] + ("..." if len(obj.text) > 70 else "")
        return f"Вопрос #{obj.id}", short

    @display(
        description="Статус",
        label={
            "active": "success",
            "draft": "warning",
            "archived": "danger",
        },
    )
    def display_status(self, obj: Question) -> Tuple[str, str]:
        return obj.status, obj.get_status_display()

    @display(
        description="Сложность",
        label={
            "easy": "info",
            "medium": "warning",
            "hard": "danger",
        },
    )
    def display_difficulty(self, obj: Question) -> Tuple[str, str]:
        return obj.difficulty, obj.get_difficulty_display()

    def success_rate_display(self, obj: Question) -> str:
        return f"{obj.success_rate}%"

    success_rate_display.short_description = "% правильных"


class TestingGroupPositionInline(TabularInline):
    """Инлайн должностей в группе."""
    model = TestingGroupPosition
    extra = 1
    autocomplete_fields = ["job"]


@admin.register(TestingGroup)
class TestingGroupAdmin(ModelAdmin):
    """Админка групп тестирования."""
    list_display = ("name", "testing", "code")
    list_filter = ("code", "testing")
    search_fields = ("name",)
    autocomplete_fields = ["testing"]
    inlines = [TestingGroupPositionInline]
    compressed_fields = True
    warn_unsaved_form = True


class TestingCategorySettingInline(TabularInline):
    """Инлайн настроек категорий в мероприятии."""
    model = TestingCategorySetting
    extra = 1
    autocomplete_fields = ["category"]


@admin.register(Testing)
class TestingAdmin(ModelAdmin):
    """Админка мероприятий тестирования."""
    list_display = (
        "display_testing_header",
        "order_date",
        "start_datetime",
        "end_datetime",
        "display_status",
        "questions_count",
        "passing_score_percentage",
    )
    list_filter = (
        "status",
        ("order_date", RangeDateFilter),
        ("start_datetime", RangeDateFilter),
        ("end_datetime", RangeDateFilter),
    )
    search_fields = ("title", "order_number", "order_name")
    inlines = [TestingCategorySettingInline]
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Мероприятие", header=True)
    def display_testing_header(self, obj: Testing) -> Tuple[str, str]:
        """Возвращает название тестирования и номер приказа."""
        order_info = f"Приказ № {obj.order_number}" if obj.order_number else "Без приказа"
        return obj.title, order_info

    @display(
        description="Статус",
        label={
            "draft": "secondary",
            "scheduled": "info",
            "active": "success",
            "completed": "primary",
            "cancelled": "danger",
        },
    )
    def display_status(self, obj: Testing) -> Tuple[str, str]:
        return obj.status, obj.get_status_display()


@admin.register(TestingAssignment)
class TestingAssignmentAdmin(ModelAdmin):
    """Админка назначений сотрудников."""
    list_display = (
        "display_assignment_header",
        "group",
        "assigned_job_title",
        "display_status",
        "display_on_control",
        "attempts_used",
        "best_score",
    )
    list_filter = (
        "status",
        "is_on_control",
        "group",
        "testing",
    )
    search_fields = ("employee__last_name", "employee__first_name", "assigned_job_title", "assigned_division_title")
    autocomplete_fields = ["employee", "testing", "group"]
    readonly_fields = ("assigned_at", "passed_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Назначение", header=True)
    def display_assignment_header(self, obj: TestingAssignment) -> Tuple[str, str]:
        emp_name = obj.employee.title if obj.employee else "Сотрудник не указан"
        testing_name = obj.testing.title if obj.testing else "Тест не указан"
        return emp_name, testing_name

    @display(
        description="Статус",
        label={
            "assigned": "info",
            "in_progress": "warning",
            "passed": "success",
            "failed": "danger",
            "expired": "secondary",
        },
    )
    def display_status(self, obj: TestingAssignment) -> Tuple[str, str]:
        return obj.status, obj.get_status_display()

    @display(description="На контроле", boolean=True)
    def display_on_control(self, obj: TestingAssignment) -> bool:
        return obj.is_on_control


class AttemptQuestionInline(TabularInline):
    """Инлайн зафиксированных вопросов попытки."""
    model = AttemptQuestion
    extra = 0
    readonly_fields = ("order_num", "category_name", "question_text", "options_snapshot")
    can_delete = False


@admin.register(TestingAttempt)
class TestingAttemptAdmin(ModelAdmin):
    """Админка попыток тестирования."""
    list_display = (
        "display_attempt_header",
        "attempt_number",
        "display_status",
        "score_percentage",
        "display_passed",
        "started_at",
        "completed_at",
    )
    list_filter = (
        "status",
        "is_passed",
        "completion_reason",
        ("started_at", RangeDateFilter),
        ("completed_at", RangeDateFilter),
    )
    search_fields = ("assignment__employee__last_name", "assignment__employee__first_name", "result_number")
    autocomplete_fields = ["assignment"]
    readonly_fields = ("certificate_uuid", "result_number", "started_at", "planned_end_at", "completed_at")
    compressed_fields = True

    @display(description="Попытка", header=True)
    def display_attempt_header(self, obj: TestingAttempt) -> Tuple[str, str]:
        emp_name = obj.assignment.employee.title if obj.assignment and obj.assignment.employee else "Сотрудник"
        return f"Попытка #{obj.attempt_number} (ID: {obj.id})", emp_name

    @display(
        description="Статус",
        label={
            "in_progress": "warning",
            "completed": "info",
            "timed_out": "danger",
            "cancelled": "secondary",
        },
    )
    def display_status(self, obj: TestingAttempt) -> Tuple[str, str]:
        return obj.status, obj.get_status_display()

    @display(description="Сдано", boolean=True)
    def display_passed(self, obj: TestingAttempt) -> bool:
        return obj.is_passed


@admin.register(TestingAuditLog)
class TestingAuditLogAdmin(ModelAdmin):
    """Админка журнала аудита."""
    list_display = ("created_at", "user", "action", "object_repr", "ip_address")
    list_filter = ("action", ("created_at", RangeDateFilter))
    search_fields = ("user__last_name", "user__first_name", "object_repr", "action")
    readonly_fields = ("created_at", "user", "action", "object_repr", "details", "ip_address")
    compressed_fields = True

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(LectureMaterial)
class LectureMaterialAdmin(ModelAdmin):
    """Админка лекционных материалов."""
    list_display = ("title", "display_actual", "has_doc", "has_scan", "views_count_display", "created_by", "created_at")
    list_filter = ("is_actual", ("created_at", RangeDateFilter))
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Актуален", boolean=True)
    def display_actual(self, obj: LectureMaterial) -> bool:
        return obj.is_actual

    @display(description="DOC/DOCX", boolean=True)
    def has_doc(self, obj: LectureMaterial) -> bool:
        return bool(obj.doc_file)

    @display(description="Скан PDF", boolean=True)
    def has_scan(self, obj: LectureMaterial) -> bool:
        return bool(obj.scan_file)

    def views_count_display(self, obj: LectureMaterial) -> int:
        return obj.total_views_count

    views_count_display.short_description = "Просмотров"


@admin.register(VideoLecture)
class VideoLectureAdmin(ModelAdmin):
    """Админка видеолекций."""
    list_display = ("title", "display_actual", "has_video", "views_count_display", "created_by", "created_at")
    list_filter = ("is_actual", ("created_at", RangeDateFilter))
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Актуальна", boolean=True)
    def display_actual(self, obj: VideoLecture) -> bool:
        return obj.is_actual

    @display(description="Видео MP4", boolean=True)
    def has_video(self, obj: VideoLecture) -> bool:
        return bool(obj.video_file)

    def views_count_display(self, obj: VideoLecture) -> int:
        return obj.total_views_count

    views_count_display.short_description = "Просмотров"


@admin.register(MaterialViewLog)
class MaterialViewLogAdmin(ModelAdmin):
    """Админка журнала обращений к материалам."""
    list_display = ("user", "material_type", "material_title", "views_count", "first_viewed_at", "last_viewed_at", "last_ip")
    list_filter = ("material_type", ("last_viewed_at", RangeDateFilter))
    search_fields = ("user__last_name", "user__first_name", "lecture__title", "video_lecture__title", "last_ip")
    readonly_fields = ("user", "material_type", "lecture", "video_lecture", "first_viewed_at", "last_viewed_at", "views_count", "last_ip")
    compressed_fields = True

    def material_title(self, obj: MaterialViewLog) -> str:
        return obj.lecture.title if obj.lecture else (obj.video_lecture.title if obj.video_lecture else "—")

    material_title.short_description = "Материал"
