from django.contrib import admin

from telegram_app.models import ChatID, TelegramNotification

from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(ChatID)
class ChatIDAdmin(ModelAdmin):
    pass
@admin.register(TelegramNotification)
class TelegramNotificationAdmin(ModelAdmin):
    pass
