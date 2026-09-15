"""Административная панель для управления почтовыми аккаунтами."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from mailbox_app.models import (
    MailAccount,
    Mailbox,
    MailContact,
    MailPrintSettings,
    MailTemplate,
    ScheduledEmail,
    ScheduledEmailAttachment,
)


@admin.register(MailAccount)
class MailAccountAdmin(ModelAdmin):
    """Административное представление персональных почтовых ящиков сотрудников."""

    list_display = (
        "user",
        "email",
        "imap_host",
        "smtp_host",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "user__username",
        "user__last_name",
        "user__first_name",
        "email",
    )
    list_filter = ("is_active", "imap_use_ssl", "smtp_use_ssl")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "user",
                    "email",
                    "display_name",
                    "is_active",
                )
            },
        ),
        (
            "Параметры IMAP (Входящая почта)",
            {
                "fields": (
                    "imap_host",
                    "imap_port",
                    "imap_use_ssl",
                )
            },
        ),
        (
            "Параметры SMTP (Исходящая почта)",
            {
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_use_ssl",
                    "smtp_use_tls",
                )
            },
        ),
        (
            "Безопасность и подпись",
            {
                "fields": (
                    "encrypted_password",
                    "signature_html",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(Mailbox)
class MailboxAdmin(ModelAdmin):
    """Административное представление корпоративных и дополнительных почтовых ящиков."""

    list_display = (
        "name",
        "email",
        "domain",
        "imap_host",
        "smtp_host",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "name",
        "email",
        "domain",
        "description",
    )
    list_filter = (
        "is_active",
        "incoming_protocol",
        "imap_security",
        "smtp_security",
    )
    filter_horizontal = ("users",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "name",
                    "email",
                    "domain",
                    "display_name",
                    "description",
                    "is_active",
                )
            },
        ),
        (
            "Доступ сотрудников",
            {
                "fields": ("users",),
            },
        ),
        (
            "Параметры входящей почты (IMAP)",
            {
                "fields": (
                    "incoming_protocol",
                    "imap_host",
                    "imap_port",
                    "imap_security",
                    "imap_username",
                    "encrypted_imap_password",
                )
            },
        ),
        (
            "Параметры исходящей почты (SMTP)",
            {
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_security",
                    "smtp_username",
                    "encrypted_smtp_password",
                )
            },
        ),
        (
            "Подпись и метаданные",
            {
                "fields": (
                    "signature_html",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


class ScheduledEmailAttachmentInline(TabularInline):
    """Инлайн вложений для отложенного электронного письма."""

    model = ScheduledEmailAttachment
    extra = 0
    fields = ("filename", "file", "content_type", "file_size")
    readonly_fields = ("file_size",)


@admin.register(ScheduledEmail)
class ScheduledEmailAdmin(ModelAdmin):
    """Административное представление отложенных писем по расписанию."""

    list_display = (
        "subject",
        "user",
        "get_sender_display",
        "to_recipients",
        "scheduled_at",
        "status",
        "attempts_count",
        "sent_at",
    )
    list_filter = ("status", "scheduled_at", "sent_at")
    search_fields = ("subject", "to_recipients", "user__username", "user__last_name", "body_text")
    readonly_fields = ("created_at", "updated_at", "sent_at", "last_error")
    inlines = [ScheduledEmailAttachmentInline]

    @admin.display(description="Отправитель")
    def get_sender_display(self, obj: ScheduledEmail) -> str:
        return obj.sender_email


@admin.register(ScheduledEmailAttachment)
class ScheduledEmailAttachmentAdmin(ModelAdmin):
    """Административное представление вложений отложенных писем."""

    list_display = ("filename", "scheduled_email", "content_type", "file_size")
    search_fields = ("filename", "scheduled_email__subject")
    readonly_fields = ("file_size",)


@admin.register(MailContact)
class MailContactAdmin(ModelAdmin):
    """Административное представление персональной адресной книги."""

    list_display = ("name", "email", "user", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("name", "email", "user__username", "user__last_name")
    readonly_fields = ("created_at",)


@admin.register(MailTemplate)
class MailTemplateAdmin(ModelAdmin):
    """Административное представление шаблонов быстрых ответов."""

    list_display = ("name", "subject", "user", "is_global", "created_at", "updated_at")
    list_filter = ("is_global", "created_at")
    search_fields = ("name", "subject", "user__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MailPrintSettings)
class MailPrintSettingsAdmin(ModelAdmin):
    """Административное представление настроек официального печатного бланка."""

    list_display = ("organization_name", "header_title", "sub_header", "show_logo", "updated_at")
    readonly_fields = ("updated_at",)


