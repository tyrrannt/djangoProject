"""Административная панель для управления почтовыми аккаунтами."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from mailbox_app.models import MailAccount, Mailbox


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

