"""Административная панель для управления почтовыми аккаунтами."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from mailbox_app.models import MailAccount


@admin.register(MailAccount)
class MailAccountAdmin(ModelAdmin):
    """Административное представление почтовых ящиков сотрудников."""

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
