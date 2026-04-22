# tasks_app/admin.py
from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Category, Task, TaskFile


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'task_count')
    search_fields = ('name',)
    ordering = ('name',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(task_count=Count('tasks'))

    @admin.display(description='Количество задач', ordering='task_count')
    def task_count(self, obj):
        return obj.task_count


class TaskFileInline(TabularInline):
    """Встроенный интерфейс для управления файлами прямо в задаче."""
    model = TaskFile
    extra = 0
    fields = ('file', 'original_filename_display', 'uploaded_at')
    readonly_fields = ('uploaded_at',)
    can_delete = True

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-uploaded_at')

    @admin.display(description='Оригинальное имя')
    def original_filename_display(self, obj):
        # Безопасный fallback, если миграция ещё не применена
        return getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    # 📊 Список задач
    list_display = ('id', 'title', 'user', 'priority_badge', 'category', 'start_date', 'completed', 'has_files')
    list_filter = ('priority', 'completed', 'category', 'user', 'repeat', 'created_at')
    search_fields = ('title', 'description', 'user__username', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'category')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    save_as = True  # Кнопка "Сохранить как новую"
    actions = ['mark_completed', 'mark_incomplete']

    # 🧩 Структура формы редактирования
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'user', 'category', 'priority', 'completed')
        }),
        ('Сроки', {
            'fields': ('start_date', 'end_date', 'created_at')
        }),
        ('Повторение', {
            'fields': ('repeat', 'repeat_interval', 'repeat_days', 'repeat_end_date'),
            'classes': ('collapse',)  # Сворачивается по умолчанию для экономии места
        }),
        ('Доступ', {
            'fields': ('shared_with',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at',)
    filter_horizontal = ('shared_with',)  # Удобный виджет M2M
    inlines = [TaskFileInline]

    def get_queryset(self, request):
        # Аннотация для быстрого подсчёта файлов без N+1
        return super().get_queryset(request).annotate(files_count=Count('files', distinct=True))

    @admin.display(description='Приоритет', ordering='priority')
    def priority_badge(self, obj):
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
    def has_files(self, obj):
        return obj.files_count > 0 if hasattr(obj, 'files_count') else obj.files.exists()

    @admin.action(description='✅ Отметить как выполненные')
    def mark_completed(self, request, queryset):
        updated = queryset.update(completed=True)
        self.message_user(request, f'Отмечено {updated} задач как выполненные.')

    @admin.action(description='↩️ Отметить как невыполненные')
    def mark_incomplete(self, request, queryset):
        updated = queryset.update(completed=False)
        self.message_user(request, f'Отмечено {updated} задач как невыполненные.')


@admin.register(TaskFile)
class TaskFileAdmin(ModelAdmin):
    list_display = ('task_title', 'original_filename_display', 'uploaded_at', 'file_size')
    list_filter = ('uploaded_at',)
    search_fields = ('task__title', 'original_filename', 'file')
    list_select_related = ('task',)
    ordering = ('-uploaded_at',)
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('uploaded_at', 'file_size')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('task')

    @admin.display(description='Задача', ordering='task__title')
    def task_title(self, obj):
        return obj.task.title if obj.task else '—'

    @admin.display(description='Оригинальное имя')
    def original_filename_display(self, obj):
        return getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]

    @admin.display(description='Размер файла')
    def file_size(self, obj):
        if not obj.file or not obj.file.size:
            return '—'
        size = obj.file.size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024**2:
            return f"{size/1024:.1f} КБ"
        return f"{size/1024**2:.1f} МБ"