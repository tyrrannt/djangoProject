from django.contrib import admin

from telegram_app.models import ChatID, TelegramNotification

from unfold.admin import ModelAdmin
from unfold.decorators import display


# Register your models here.
@admin.register(ChatID)
class ChatIDAdmin(ModelAdmin):
    """Конфигурация админ-панели Django Unfold для модели ChatID."""

    list_display = (
        "chat_id",
        "ref_key",
        "display_status",
        "notify_tasks",
        "notify_memos",
        "notify_birthdays",
        "notify_emails",
        "notify_flights",
    )
    list_filter = (
        "is_active",
        "notify_tasks",
        "notify_memos",
        "notify_birthdays",
        "notify_emails",
        "notify_flights",
    )
    search_fields = ("chat_id", "ref_key")
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Статус",
        boolean=True,
    )
    def display_status(self, instance: ChatID) -> bool:
        """Отображает булев индикатор активности подписки."""
        return instance.is_active


@admin.register(TelegramNotification)
class TelegramNotificationAdmin(ModelAdmin):
    """Конфигурация админ-панели Django Unfold для очереди TelegramNotification."""

    list_display = ("message", "send_date", "send_time", "sending_counter")
    list_filter = ("send_date", "sending_counter")
    search_fields = ("message", "document_id")
    filter_horizontal = ("respondents",)
    compressed_fields = True
    warn_unsaved_form = True
