from django.contrib import admin

from telegram_app.models import ChatID, TelegramNotification

# Register your models here.

admin.site.register(ChatID)
admin.site.register(TelegramNotification)
