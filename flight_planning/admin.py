# flight_planning/admin.py
from django.contrib import admin
from .models import PilotAssignment
from unfold.admin import ModelAdmin


@admin.register(PilotAssignment)
class PilotAssignmentAdmin(ModelAdmin):
    list_display = ['pilot', 'mpd', 'date', 'created_at', 'created_by']
    list_filter = ['mpd', 'date']
    search_fields = ['pilot__username', 'pilot__first_name', 'pilot__last_name', 'mpd__name']
    date_hierarchy = 'date'
    raw_id_fields = ['pilot', 'mpd', 'created_by']
