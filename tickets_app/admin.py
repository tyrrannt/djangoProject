"""Регистрация моделей модуля заявок в панели Django Unfold (tickets_app.admin).

Обеспечивает эргономичное администрирование добровольных сообщений,
вложенных комментариев, прикрепленных файлов и визуальных бейджей статусов.
"""

from typing import Any, Optional

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Attachment, Message, Ticket, TicketSettings, TicketStatus


class MessageInline(TabularInline):
    """Инлайн сообщений и служебных заметок внутри карточки заявки."""

    model = Message
    extra = 0
    fields = ['sender', 'text', 'is_internal', 'created_at']
    readonly_fields = ['created_at']
    show_change_link = True


class AttachmentInline(TabularInline):
    """Инлайн прикрепленных материалов внутри карточки заявки."""

    model = Attachment
    extra = 0
    fields = ['file', 'original_name', 'message', 'uploaded_at']
    readonly_fields = ['original_name', 'uploaded_at']


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    """Панель администрирования добровольных сообщений и заявок в Django Unfold."""

    list_display = [
        'id',
        'title',
        'author',
        'responsible',
        'status_badge',
        'has_appeals',
        'created_at',
    ]
    list_filter = ['status', 'created_at', 'responsible']
    list_filter_submit = True
    search_fields = ['title', 'description', 'author__username', 'author__last_name', 'responsible__username']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    compressed_fields = True
    warn_unsaved_form = True
    inlines = [MessageInline, AttachmentInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'author', 'parent_ticket'),
        }),
        ('Назначения и статусы', {
            'fields': ('responsible', 'status'),
        }),
        ('Временные отметки', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',),
        }),
    )

    @display(
        description='Статус',
        label={
            TicketStatus.NEW: 'info',
            TicketStatus.IN_PROGRESS: 'primary',
            TicketStatus.REDIRECTED: 'warning',
            TicketStatus.RESOLVED: 'success',
            TicketStatus.CLOSED: 'secondary',
        },
    )
    def status_badge(self, obj: Ticket) -> str:
        """Возвращает текстовый статус для бейджа Unfold."""
        return obj.status

    @display(description='Обжалования', boolean=True)
    def has_appeals(self, obj: Ticket) -> bool:
        """Проверяет наличие поданных апелляций."""
        return obj.appeals.exists()

    def save_model(self, request: Any, obj: Ticket, form: Any, change: bool) -> None:
        """Автоматически подставляет текущего пользователя в качестве автора при создании."""
        if not change and not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    """Панель администрирования сообщений переписки в Django Unfold."""

    list_display = ['id', 'ticket', 'sender', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    list_filter_submit = True
    search_fields = ['text', 'sender__username', 'sender__last_name', 'ticket__title']
    readonly_fields = ['created_at']
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Attachment)
class AttachmentAdmin(ModelAdmin):
    """Панель администрирования вложений в Django Unfold."""

    list_display = ['id', 'file_link', 'ticket', 'message', 'uploaded_at']
    list_filter = ['uploaded_at']
    list_filter_submit = True
    readonly_fields = ['uploaded_at']
    compressed_fields = True

    def file_link(self, obj: Attachment) -> str:
        """Формирует кликабельную ссылку на скачивание файла."""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank" class="text-primary font-weight-bold">{}</a>',
                obj.file.url,
                obj.original_name or obj.file.name,
            )
        return '—'

    file_link.short_description = 'Файл'


@admin.register(TicketSettings)
class TicketSettingsAdmin(ModelAdmin):
    """Панель глобальных настроек модуля заявок и куратора СДС в Django Unfold."""

    list_display = ['id', 'curator_name', 'updated_at', 'updated_by']
    autocomplete_fields = ['curator']
    readonly_fields = ['updated_at', 'updated_by']
    compressed_fields = True
    warn_unsaved_form = True

    @display(description='Куратор СДС')
    def curator_name(self, obj: TicketSettings) -> str:
        """Отображает полное имя назначенного куратора."""
        if obj.curator:
            return obj.curator.get_full_name() or obj.curator.username
        return 'Не назначен'

    def save_model(self, request: Any, obj: TicketSettings, form: Any, change: bool) -> None:
        """Фиксирует автора назначения настроек."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request: Any) -> bool:
        """Разрешает создание только одной записи настроек (Singleton)."""
        if TicketSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        """Запрещает удаление глобальных настроек модуля."""
        return False