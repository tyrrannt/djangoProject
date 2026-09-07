"""Настройка административной панели Django (Unfold) для модуля tasks_app."""

from typing import Any
from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from tasks_app.models import (
    Category,
    SubTask,
    Task,
    TaskAssignment,
    TaskComment,
    TaskFile,
    TaskHistory,
    TaskStatus,
)


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    """Админка для справочника категорий задач."""
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


class TaskFileInline(TabularInline):
    """Встроенный интерфейс для управления файлами прямо в задаче."""
    model = TaskFile
    extra = 0
    fields = ('file', 'display_filename', 'uploaded_by', 'uploaded_at', 'display_file_size')
    readonly_fields = ('display_filename', 'uploaded_at', 'display_file_size')
    can_delete = True

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).order_by('-uploaded_at')

    @admin.display(description='Оригинальное имя')
    def display_filename(self, obj: TaskFile) -> str:
        filename = getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]
        if obj.file and obj.file.url:
            return format_html('<a href="{}" target="_blank" style="font-weight: 500;">📎 {}</a>', obj.file.url, filename)
        return filename

    @admin.display(description='Размер')
    def display_file_size(self, obj: TaskFile) -> str:
        if not obj.file or not obj.file.size:
            return '—'
        size = obj.file.size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024**2:
            return f"{size/1024:.1f} КБ"
        return f"{size/1024**2:.1f} МБ"


class SubTaskInline(TabularInline):
    """Инлайн подзадач / чек-листа в задаче."""
    model = SubTask
    extra = 0
    fields = ('title', 'assigned_to', 'is_completed', 'completed_by', 'completed_at', 'order')
    readonly_fields = ('completed_by', 'completed_at')


class TaskAssignmentInline(TabularInline):
    """Инлайн поручений и делегирования в задаче."""
    model = TaskAssignment
    extra = 0
    fields = ('assigned_to', 'role', 'status', 'assigned_by', 'assigned_at', 'accepted_at', 'completed_at', 'comment')
    readonly_fields = ('assigned_at', 'accepted_at', 'completed_at')


class TaskCommentInline(StackedInline):
    """Инлайн комментариев к задаче."""
    model = TaskComment
    extra = 0
    fields = ('author', 'text', 'created_at')
    readonly_fields = ('created_at',)


class TaskHistoryInline(TabularInline):
    """Инлайн журнала аудита действий по задаче."""
    model = TaskHistory
    extra = 0
    fields = ('created_at', 'user', 'action', 'old_value', 'new_value', 'comment')
    readonly_fields = ('created_at', 'user', 'action', 'old_value', 'new_value', 'comment')
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    """Административный интерфейс для управления задачами и поручениями."""

    list_display = (
        'id', 'title', 'user', 'responsible', 'status_badge',
        'priority_badge', 'category', 'start_date', 'end_date', 'has_files'
    )
    list_filter = (
        'status', 'priority', 'category', 'user', 'responsible',
        'requires_eds', 'repeat', 'created_at'
    )
    search_fields = (
        'title', 'description', 'user__username', 'user__first_name',
        'user__last_name', 'responsible__username'
    )
    list_select_related = ('user', 'responsible', 'category')
    ordering = ('-created_at',)
    save_as = True
    actions = ['mark_completed', 'mark_in_progress']

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'category', 'priority', 'status', 'requires_eds')
        }),
        ('Участники и ответственность', {
            'fields': ('user', 'responsible', 'assignees', 'observers', 'shared_with')
        }),
        ('Сроки и исполнение', {
            'fields': (
                'start_date', 'end_date', 'accepted_at', 'submitted_review_at',
                'completed_at', 'created_at', 'updated_at'
            )
        }),
        ('Электронная цифровая подпись (ЭЦП)', {
            'fields': ('eds_signed_by', 'eds_signed_at', 'eds_signature'),
            'classes': ('collapse',)
        }),
        ('Повторение (RRULE)', {
            'fields': ('repeat', 'repeat_interval', 'repeat_days', 'repeat_end_date'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'completed_at', 'accepted_at', 'submitted_review_at')
    filter_horizontal = ('assignees', 'observers', 'shared_with')
    inlines = [SubTaskInline, TaskAssignmentInline, TaskFileInline, TaskCommentInline, TaskHistoryInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).annotate(files_count=Count('files', distinct=True))

    @admin.display(description='Статус', ordering='status')
    def status_badge(self, obj: Task) -> str:
        colors = {
            TaskStatus.NEW: '#0dcaf0',
            TaskStatus.ASSIGNED: '#6f42c1',
            TaskStatus.IN_PROGRESS: '#0d6efd',
            TaskStatus.ON_REVIEW: '#ffc107',
            TaskStatus.RETURNED: '#fd7e14',
            TaskStatus.COMPLETED: '#198754',
            TaskStatus.CANCELLED: '#6c757d',
            TaskStatus.OVERDUE: '#dc3545',
            TaskStatus.DRAFT: '#adb5bd',
        }
        bg = colors.get(obj.status, '#6c757d')
        text = '#000' if obj.status in (TaskStatus.ON_REVIEW, TaskStatus.NEW, TaskStatus.DRAFT) else '#fff'
        return format_html(
            '<span style="background: {}; color: {}; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">{}</span>',
            bg, text, obj.get_status_display()
        )

    @admin.display(description='Приоритет', ordering='priority')
    def priority_badge(self, obj: Task) -> str:
        colors = {
            'primary': '#0d6efd', 'warning': '#ffc107', 'info': '#0dcaf0',
            'danger': '#dc3545', 'dark': '#212529'
        }
        bg = colors.get(obj.priority, '#6c757d')
        text = '#fff' if obj.priority not in ('warning', 'info') else '#000'
        return format_html(
            '<span style="background: {}; color: {}; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500;">{}</span>',
            bg, text, obj.get_priority_display()
        )

    @admin.display(description='Файлы', boolean=True)
    def has_files(self, obj: Task) -> bool:
        return obj.files_count > 0 if hasattr(obj, 'files_count') else obj.files.exists()

    @admin.action(description='✅ Отметить как выполненные')
    def mark_completed(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(status=TaskStatus.COMPLETED, completed=True)
        self.message_user(request, f'Отмечено {updated} задач как выполненные.')

    @admin.action(description='▶️ Перевести в работу')
    def mark_in_progress(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(status=TaskStatus.IN_PROGRESS, completed=False)
        self.message_user(request, f'Переведено {updated} задач в статус "В работе".')


@admin.register(SubTask)
class SubTaskAdmin(ModelAdmin):
    """Админка для подзадач."""
    list_display = ('title', 'task', 'assigned_to', 'is_completed', 'completed_by', 'completed_at')
    list_filter = ('is_completed', 'created_at')
    search_fields = ('title', 'task__title')


@admin.register(TaskComment)
class TaskCommentAdmin(ModelAdmin):
    """Админка для комментариев."""
    list_display = ('author', 'task', 'short_text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'author__username', 'task__title')

    @admin.display(description='Текст')
    def short_text(self, obj: TaskComment) -> str:
        return obj.text[:60] + ('...' if len(obj.text) > 60 else '')


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(ModelAdmin):
    """Админка для поручений."""
    list_display = ('task', 'assigned_by', 'assigned_to', 'role', 'status', 'assigned_at')
    list_filter = ('role', 'status', 'assigned_at')
    search_fields = ('task__title', 'assigned_to__username', 'assigned_by__username')


@admin.register(TaskHistory)
class TaskHistoryAdmin(ModelAdmin):
    """Админка для журнала аудита."""
    list_display = ('created_at', 'task', 'user', 'action', 'comment')
    list_filter = ('action', 'created_at')
    search_fields = ('task__title', 'user__username', 'comment', 'new_value')
    readonly_fields = ('task', 'user', 'action', 'old_value', 'new_value', 'comment', 'created_at')

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(TaskFile)
class TaskFileAdmin(ModelAdmin):
    """Админка для файлов задач."""
    list_display = ('task_title', 'display_filename', 'uploaded_by', 'uploaded_at', 'display_file_size')
    list_filter = ('uploaded_at',)
    search_fields = ('task__title', 'original_filename', 'file')
    list_select_related = ('task', 'uploaded_by')
    ordering = ('-uploaded_at',)
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('uploaded_at', 'display_file_size', 'display_filename')

    @admin.display(description='Задача', ordering='task__title')
    def task_title(self, obj: TaskFile) -> str:
        return obj.task.title if obj.task else '—'

    @admin.display(description='Оригинальное имя')
    def display_filename(self, obj: TaskFile) -> str:
        filename = getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]
        if obj.file and obj.file.url:
            return format_html('<a href="{}" target="_blank">📎 {}</a>', obj.file.url, filename)
        return filename

    @admin.display(description='Размер файла')
    def display_file_size(self, obj: TaskFile) -> str:
        if not obj.file or not obj.file.size:
            return '—'
        size = obj.file.size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024**2:
            return f"{size/1024:.1f} КБ"
        return f"{size/1024**2:.1f} МБ"