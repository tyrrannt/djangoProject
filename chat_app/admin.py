from django.contrib import admin

from chat_app.models import Message
from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(Message)
class MessageAdmin(ModelAdmin):
    pass
