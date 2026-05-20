from django.contrib import admin
from django.utils.html import format_html

from .models import PortalProperty, MainMenu, Notification, TemplateDocument
from unfold.admin import ModelAdmin


# Register your models here.

@admin.register(PortalProperty)
class PortalPropertyAdmin(ModelAdmin):
    pass


@admin.register(MainMenu)
class MainMenuAdmin(ModelAdmin):
    pass


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    pass


@admin.register(TemplateDocument)
class TemplateDocumentAdmin(ModelAdmin):
    list_display = ['name', 'unique_code', 'version', 'is_active',
                    'is_currently_valid_display', 'start_date', 'end_date', 'created_at']
    list_filter = ['is_active', 'template_type', 'created_at']
    search_fields = ['name', 'unique_code', 'description']
    readonly_fields = ['version', 'created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'unique_code', 'template_type', 'description')
        }),
        ('Файл шаблона', {
            'fields': ('template_file',),
            'classes': ('wide',)
        }),
        ('Период действия', {
            'fields': ('start_date', 'end_date', 'is_active'),
            'classes': ('wide',)
        }),
        ('Метаданные', {
            'fields': ('version', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def is_currently_valid_display(self, obj):
        """Отображение статуса валидности в админке"""
        if obj.is_currently_valid:
            return format_html('<span style="color: green;">✓ Действителен</span>')
        else:
            return format_html('<span style="color: red;">✗ Не действителен</span>')

    is_currently_valid_display.short_description = 'Статус'

    actions = ['activate_templates', 'deactivate_templates']

    def activate_templates(self, request, queryset):
        """Активировать выбранные шаблоны"""
        for template in queryset:
            # Деактивируем другие версии этого шаблона
            TemplateDocument.objects.filter(
                unique_code=template.unique_code
            ).update(is_active=False)
            template.is_active = True
            template.save()
        self.message_user(request, f"{queryset.count()} шаблон(ов) активировано")

    activate_templates.short_description = "Активировать выбранные шаблоны"

    def deactivate_templates(self, request, queryset):
        """Деактивировать выбранные шаблоны"""
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} шаблон(ов) деактивировано")

    deactivate_templates.short_description = "Деактивировать выбранные шаблоны"