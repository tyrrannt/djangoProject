# flight_planning/admin.py
from django.contrib import admin
from .models import PilotAssignment, AircraftMovement, FlightCrew, CrewMember, FlightCrewNote
from unfold.admin import ModelAdmin, TabularInline


class FlightCrewNoteInline(TabularInline):
    model = FlightCrewNote
    extra = 0
    raw_id_fields = ['author']


class CrewMemberInline(TabularInline):
    model = CrewMember
    extra = 1
    raw_id_fields = ['member']


@admin.register(FlightCrew)
class FlightCrewAdmin(ModelAdmin):
    list_display = ['aircraft', 'mpd', 'date', 'flight_type', 'name', 'created_by', 'created_at']
    list_filter = ['mpd', 'flight_type', 'date']
    search_fields = ['name', 'aircraft__registration_number', 'mpd__name', 'comment']
    date_hierarchy = 'date'
    raw_id_fields = ['aircraft', 'mpd', 'created_by']
    inlines = [CrewMemberInline, FlightCrewNoteInline]


@admin.register(FlightCrewNote)
class FlightCrewNoteAdmin(ModelAdmin):
    list_display = ['crew', 'author', 'author_role', 'message', 'created_at']
    list_filter = ['author_role', 'created_at', 'crew__date']
    search_fields = ['message', 'author__username', 'author__title', 'crew__aircraft__registration_number']
    raw_id_fields = ['crew', 'author']



@admin.register(CrewMember)
class CrewMemberAdmin(ModelAdmin):
    list_display = ['crew', 'member', 'role', 'created_at']
    list_filter = ['role', 'crew__flight_type', 'crew__date']
    search_fields = ['member__username', 'member__first_name', 'member__last_name', 'crew__aircraft__registration_number']
    raw_id_fields = ['crew', 'member']


@admin.register(PilotAssignment)
class PilotAssignmentAdmin(ModelAdmin):
    list_display = ['pilot', 'mpd', 'date', 'crew', 'role_in_crew', 'created_at', 'created_by']
    list_filter = ['mpd', 'date', 'role_in_crew']
    search_fields = ['pilot__username', 'pilot__first_name', 'pilot__last_name', 'mpd__name']
    date_hierarchy = 'date'
    raw_id_fields = ['pilot', 'mpd', 'crew', 'created_by']


@admin.register(AircraftMovement)
class AircraftMovementAdmin(ModelAdmin):
    list_display = ['aircraft', 'mpd', 'date', 'created_by', 'created_at']
    list_filter = ['mpd', 'date', 'aircraft__type_property']
    search_fields = [
        'aircraft__registration_number',
        'aircraft__factory_number',
        'mpd__name',
        'comment'
    ]
    date_hierarchy = 'date'
    raw_id_fields = ['aircraft', 'mpd', 'created_by']
