from django.contrib import admin
from .models import PortalProperty, MainMenu, Notification
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
