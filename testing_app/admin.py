"""Административные интерфейсы модуля периодического тестирования сотрудников."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline, StackedInline

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
)


class AnswerOptionInline(TabularInline):
    """Инлайн вариантов ответа в вопросе."""

    model = AnswerOption
    extra = 4
    fields = ("order_num", "text", "is_correct")


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(ModelAdmin):
    """Админка категорий вопросов."""

    list_display = ("name", "is_active", "questions_count", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_active",)

    def questions_count(self, obj):
        return obj.questions.count()
    questions_count.short_description = "Всего вопросов"


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    """Админка банка вопросов."""

    list_display = ("id", "category", "short_text", "status", "difficulty", "times_used", "success_rate_display")
    list_filter = ("status", "difficulty", "category")
    search_fields = ("text", "explanation")
    inlines = [AnswerOptionInline]
    readonly_fields = ("times_used", "times_correct", "times_incorrect", "last_used_at", "created_at", "updated_at")

    def short_text(self, obj):
        return obj.text[:80] + ("..." if len(obj.text) > 80 else "")
    short_text.short_description = "Текст вопроса"

    def success_rate_display(self, obj):
        return f"{obj.success_rate}%"
    success_rate_display.short_description = "% правильных"


class TestingGroupPositionInline(TabularInline):
    """Инлайн должностей в группе."""

    model = TestingGroupPosition
    extra = 1


@admin.register(TestingGroup)
class TestingGroupAdmin(ModelAdmin):
    """Админка групп тестирования."""

    list_display = ("name", "testing", "code")
    list_filter = ("code", "testing")
    search_fields = ("name",)
    inlines = [TestingGroupPositionInline]


class TestingCategorySettingInline(TabularInline):
    """Инлайн настроек категорий в мероприятии."""

    model = TestingCategorySetting
    extra = 1


@admin.register(Testing)
class TestingAdmin(ModelAdmin):
    """Админка мероприятий тестирования."""

    list_display = ("title", "order_number", "order_date", "start_datetime", "end_datetime", "status", "questions_count", "passing_score_percentage")
    list_filter = ("status", "order_date")
    search_fields = ("title", "order_number", "order_name")
    inlines = [TestingCategorySettingInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(TestingAssignment)
class TestingAssignmentAdmin(ModelAdmin):
    """Админка назначений сотрудников."""

    list_display = ("employee", "testing", "group", "assigned_job_title", "status", "is_on_control", "attempts_used", "best_score")
    list_filter = ("status", "is_on_control", "group", "testing")
    search_fields = ("employee__last_name", "employee__first_name", "assigned_job_title", "assigned_division_title")
    readonly_fields = ("assigned_at", "passed_at")


class AttemptQuestionInline(TabularInline):
    """Инлайн зафиксированных вопросов попытки."""

    model = AttemptQuestion
    extra = 0
    readonly_fields = ("order_num", "category_name", "question_text", "options_snapshot")
    can_delete = False


@admin.register(TestingAttempt)
class TestingAttemptAdmin(ModelAdmin):
    """Админка попыток тестирования."""

    list_display = ("id", "assignment", "attempt_number", "status", "score_percentage", "is_passed", "started_at", "completed_at")
    list_filter = ("status", "is_passed", "completion_reason")
    search_fields = ("assignment__employee__last_name", "result_number")
    readonly_fields = ("certificate_uuid", "result_number", "started_at", "planned_end_at", "completed_at")


@admin.register(TestingAuditLog)
class TestingAuditLogAdmin(ModelAdmin):
    """Админка журнала аудита."""

    list_display = ("created_at", "user", "action", "object_repr", "ip_address")
    list_filter = ("action",)
    search_fields = ("user__last_name", "object_repr", "action")
    readonly_fields = ("created_at", "user", "action", "object_repr", "details", "ip_address")
