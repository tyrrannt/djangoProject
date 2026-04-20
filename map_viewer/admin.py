from django.contrib import admin
from .models import MapSource
from unfold.admin import ModelAdmin

@admin.register(MapSource)
class MapSourceAdmin(ModelAdmin):
    list_display = ('name', 'owner', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)