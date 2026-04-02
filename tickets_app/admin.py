from django.contrib import admin
from django.utils.html import format_html
from .models import Ticket, Message, Attachment, TicketStatus


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'author', 'responsible', 'status_badge', 'created_at', 'has_appeals']
    list_filter = ['status', 'created_at', 'responsible']
    search_fields = ['title', 'description', 'author__username']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    filter_horizontal = []
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'author', 'parent_ticket')
        }),
        ('Назначения и статусы', {
            'fields': ('responsible', 'status')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'new': '#28a745',
            'in_progress': '#007bff',
            'redirected': '#ffc107',
            'resolved': '#17a2b8',
            'closed': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: white; background: {}; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Статус'

    def has_appeals(self, obj):
        return obj.appeals.count() > 0
    has_appeals.short_description = 'Есть обжалования'
    has_appeals.boolean = True

    def save_model(self, request, obj, form, change):
        if not change and not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'sender', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    search_fields = ['text', 'sender__username']
    readonly_fields = ['created_at']


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'file_link', 'ticket', 'message', 'uploaded_at']
    list_filter = ['uploaded_at']
    readonly_fields = ['uploaded_at']

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}">{}</a>', obj.file.url, os.path.basename(obj.file.name))
        return '—'
    file_link.short_description = 'Файл'