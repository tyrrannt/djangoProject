"""Административная панель для управления почтовыми аккаунтами."""

from typing import Optional, Tuple
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter

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
        "display_account_header",
        "imap_host",
        "smtp_host",
        "display_active",
        "updated_at",
    )
    search_fields = (
        "user__username",
        "user__last_name",
        "user__first_name",
        "email",
    )
    list_filter = (
        "is_active",
        "imap_use_ssl",
        "smtp_use_ssl",
        ("updated_at", RangeDateFilter),
    )
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Почтовый аккаунт", header=True)
    def display_account_header(self, obj: MailAccount) -> Tuple[str, str]:
        """Возвращает email и владельца аккаунта."""
        owner = obj.user.title if obj.user else "Владелец не указан"
        return obj.email, owner

    @display(description="Активен", boolean=True)
    def display_active(self, obj: MailAccount) -> bool:
        """Флаг активности почтового ящика."""
        return obj.is_active

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
        "display_mailbox_header",
        "domain",
        "imap_host",
        "smtp_host",
        "display_active",
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
        ("updated_at", RangeDateFilter),
    )
    filter_horizontal = ("users",)
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Корпоративный ящик", header=True)
    def display_mailbox_header(self, obj: Mailbox) -> Tuple[str, str]:
        """Возвращает название ящика и email."""
        return obj.name, obj.email

    @display(description="Активен", boolean=True)
    def display_active(self, obj: Mailbox) -> bool:
        """Флаг активности корпоративного ящика."""
        return obj.is_active

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
        "display_email_header",
        "user",
        "get_sender_display",
        "scheduled_at",
        "display_status",
        "attempts_count",
        "sent_at",
    )
    list_filter = (
        "status",
        ("scheduled_at", RangeDateFilter),
        ("sent_at", RangeDateFilter),
    )
    search_fields = ("subject", "to_recipients", "user__username", "user__last_name", "body_text")
    readonly_fields = ("created_at", "updated_at", "sent_at", "last_error")
    inlines = [ScheduledEmailAttachmentInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Отложенное письмо", header=True)
    def display_email_header(self, obj: ScheduledEmail) -> Tuple[str, str]:
        """Возвращает тему письма и получателей."""
        to = f"Кому: {obj.to_recipients[:35]}..." if len(obj.to_recipients) > 35 else f"Кому: {obj.to_recipients}"
        return obj.subject, to

    @display(
        description="Статус",
        label={
            "pending": "info",
            "sent": "success",
            "failed": "danger",
            "cancelled": "secondary",
        },
    )
    def display_status(self, obj: ScheduledEmail) -> Tuple[str, str]:
        """Возвращает статус отправки письма."""
        return obj.status, obj.get_status_display()

    @admin.display(description="Отправитель")
    def get_sender_display(self, obj: ScheduledEmail) -> str:
        return obj.sender_email


@admin.register(ScheduledEmailAttachment)
class ScheduledEmailAttachmentAdmin(ModelAdmin):
    """Административное представление вложений отложенных писем."""

    list_display = ("filename", "scheduled_email", "content_type", "file_size")
    search_fields = ("filename", "scheduled_email__subject")
    readonly_fields = ("file_size",)
    compressed_fields = True


@admin.register(MailContact)
class MailContactAdmin(ModelAdmin):
    """Административное представление персональной адресной книги."""

    list_display = ("name", "email", "user", "source", "created_at")
    list_filter = ("source", ("created_at", RangeDateFilter))
    search_fields = ("name", "email", "user__username", "user__last_name")
    readonly_fields = ("created_at",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(MailTemplate)
class MailTemplateAdmin(ModelAdmin):
    """Административное представление шаблонов быстрых ответов."""

    list_display = ("name", "subject", "user", "display_global", "created_at", "updated_at")
    list_filter = ("is_global", ("created_at", RangeDateFilter))
    search_fields = ("name", "subject", "user__username")
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Общий", boolean=True)
    def display_global(self, obj: MailTemplate) -> bool:
        """Флаг глобального шаблона."""
        return obj.is_global


@admin.register(MailPrintSettings)
class MailPrintSettingsAdmin(ModelAdmin):
    """Административное представление настроек официального печатного бланка."""

    list_display = ("organization_name", "header_title", "sub_header", "show_logo", "updated_at")
    readonly_fields = ("updated_at",)
    compressed_fields = True
    warn_unsaved_form = True
