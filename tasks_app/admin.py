# tasks_app/admin.py
from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Category, Task, TaskFile


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    pass
    # list_display = ('name', 'task_count')
    # search_fields = ('name',)
    # ordering = ('name',)
    #
    # def get_queryset(self, request):
    #     return super().get_queryset(request).annotate(task_count=Count('tasks'))
    #
    # @admin.display(description='Количество задач', ordering='task_count')
    # def task_count(self, obj):
    #     return obj.task_count


class TaskFileInline(TabularInline):
    """Встроенный интерфейс для управления файлами прямо в задаче."""
    model = TaskFile
    extra = 0
    # Используем readonly поля для отображения информации
    fields = ('file', 'display_filename', 'uploaded_at', 'display_file_size')
    readonly_fields = ('display_filename', 'uploaded_at', 'display_file_size')
    can_delete = True

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-uploaded_at')

    @admin.display(description='Оригинальное имя')
    def display_filename(self, obj):
        """Отображает оригинальное имя файла со ссылкой"""
        filename = getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]
        if obj.file and obj.file.url:
            return format_html('<a href="{}" target="_blank" style="font-weight: 500;">📎 {}</a>',
                             obj.file.url, filename)
        return filename

    @admin.display(description='Размер')
    def display_file_size(self, obj):
        """Отображает размер файла"""
        if not obj.file or not obj.file.size:
            return '—'
        size = obj.file.size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024**2:
            return f"{size/1024:.1f} КБ"
        return f"{size/1024**2:.1f} МБ"


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    # 📊 Список задач
    list_display = ('id', 'title', 'user', 'priority_badge', 'category', 'start_date', 'completed', 'has_files')
    list_filter = ('priority', 'completed', 'category', 'user', 'repeat', 'created_at')
    search_fields = ('title', 'description', 'user__username', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'category')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    save_as = True
    actions = ['mark_completed', 'mark_incomplete']

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'user', 'category', 'priority', 'completed')
        }),
        ('Сроки', {
            'fields': ('start_date', 'end_date', 'created_at')
        }),
        ('Повторение', {
            'fields': ('repeat', 'repeat_interval', 'repeat_days', 'repeat_end_date'),
            'classes': ('collapse',)
        }),
        ('Доступ', {
            'fields': ('shared_with',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at',)
    filter_horizontal = ('shared_with',)
    inlines = [TaskFileInline]

    def get_queryset(self, request):
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
    list_display = ('task_title', 'display_filename', 'uploaded_at', 'display_file_size')
    list_filter = ('uploaded_at',)
    search_fields = ('task__title', 'original_filename', 'file')
    list_select_related = ('task',)
    ordering = ('-uploaded_at',)
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('uploaded_at', 'display_file_size', 'display_filename')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('task')

    @admin.display(description='Задача', ordering='task__title')
    def task_title(self, obj):
        return obj.task.title if obj.task else '—'

    @admin.display(description='Оригинальное имя')
    def display_filename(self, obj):
        filename = getattr(obj, 'original_filename', None) or obj.file.name.split('/')[-1]
        if obj.file and obj.file.url:
            return format_html('<a href="{}" target="_blank">📎 {}</a>', obj.file.url, filename)
        return filename

    @admin.display(description='Размер файла')
    def display_file_size(self, obj):
        if not obj.file or not obj.file.size:
            return '—'
        size = obj.file.size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024**2:
            return f"{size/1024:.1f} КБ"
        return f"{size/1024**2:.1f} МБ"