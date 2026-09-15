"""Административная панель планирования полетов и управления экипажами."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from .models import AircraftMovement, CrewMember, FlightCrew, FlightCrewNote, PilotAssignment


class FlightCrewNoteInline(TabularInline):
    """Инлайн оперативных заметок к полету."""

    model = FlightCrewNote
    extra = 0
    autocomplete_fields = ["author"]


class CrewMemberInline(TabularInline):
    """Инлайн членов экипажа."""

    model = CrewMember
    extra = 1
    autocomplete_fields = ["member"]


@admin.register(FlightCrew)
class FlightCrewAdmin(ModelAdmin):
    """Панель управления летными экипажами."""

    list_display = [
        "get_aircraft_header",
        "mpd",
        "date",
        "flight_type_badge",
        "name",
        "created_by",
        "created_at",
    ]
    list_filter = [
        ("date", RangeDateFilter),
        "mpd",
        "flight_type",
    ]
    search_fields = ["name", "aircraft__registration_number", "mpd__name", "comment"]
    date_hierarchy = "date"
    autocomplete_fields = ["aircraft", "mpd", "created_by"]
    inlines = [CrewMemberInline, FlightCrewNoteInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(header=True, description="Воздушное судно")
    def get_aircraft_header(self, obj: FlightCrew) -> list:
        """Двухстрочный заголовок: бортовой номер + наименование ВС."""
        reg = obj.aircraft.registration_number if obj.aircraft else "—"
        desc = obj.aircraft.estate_name if obj.aircraft and hasattr(obj.aircraft, "estate_name") else "ВС"
        return [reg, desc]

    @display(
        description="Тип рейса",
        label={
            "commercial": "success",
            "monitored": "info",
            "sanitary": "danger",
            "transport": "primary",
            "special": "warning",
            "patrol": "info",
            "training": "warning",
        },
    )
    def flight_type_badge(self, obj: FlightCrew) -> str:
        """Цветной бейдж типа рейса."""
        return obj.get_flight_type_display()


@admin.register(FlightCrewNote)
class FlightCrewNoteAdmin(ModelAdmin):
    """Панель управления оперативными заметок к экипажам."""

    list_display = ["crew", "author", "author_role_badge", "short_message", "created_at"]
    list_filter = [
        "author_role",
        ("created_at", RangeDateFilter),
    ]
    search_fields = ["message", "author__username", "author__title", "crew__aircraft__registration_number"]
    autocomplete_fields = ["crew", "author"]
    compressed_fields = True

    @display(
        description="Роль автора",
        label={
            "pilot": "info",
            "dispatcher": "warning",
            "engineer": "primary",
            "management": "danger",
        },
    )
    def author_role_badge(self, obj: FlightCrewNote) -> str:
        """Бейдж роли автора заметки."""
        return obj.get_author_role_display() if hasattr(obj, "get_author_role_display") else str(obj.author_role)

    @display(description="Сообщение")
    def short_message(self, obj: FlightCrewNote) -> str:
        """Краткий текст заметки."""
        return obj.message[:60] + ("..." if len(obj.message) > 60 else "")


@admin.register(CrewMember)
class CrewMemberAdmin(ModelAdmin):
    """Панель управления назначениями членов экипажей."""

    list_display = ["crew", "member", "role_badge", "created_at"]
    list_filter = [
        "role",
        "crew__flight_type",
        ("crew__date", RangeDateFilter),
    ]
    search_fields = [
        "member__username",
        "member__first_name",
        "member__last_name",
        "crew__aircraft__registration_number",
    ]
    autocomplete_fields = ["crew", "member"]
    compressed_fields = True

    @display(
        description="Роль в экипаже",
        label={
            "pic": "success",
            "sic": "info",
            "operator": "warning",
            "instructor": "primary",
            "technician": "base",
        },
    )
    def role_badge(self, obj: CrewMember) -> str:
        """Цветной бейдж роли пилота в экипаже."""
        return obj.get_role_display() if hasattr(obj, "get_role_display") else str(obj.role)


@admin.register(PilotAssignment)
class PilotAssignmentAdmin(ModelAdmin):
    """Панель индивидуальных назначений пилотов на МПД."""

    list_display = ["pilot", "mpd", "date", "crew", "role_in_crew_badge", "created_at", "created_by"]
    list_filter = [
        ("date", RangeDateFilter),
        "mpd",
        "role_in_crew",
    ]
    search_fields = ["pilot__username", "pilot__first_name", "pilot__last_name", "mpd__name"]
    date_hierarchy = "date"
    autocomplete_fields = ["pilot", "mpd", "crew", "created_by"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Роль",
        label={
            "pic": "success",
            "sic": "info",
            "operator": "warning",
            "instructor": "primary",
        },
    )
    def role_in_crew_badge(self, obj: PilotAssignment) -> str:
        """Цветной бейдж роли."""
        return obj.get_role_in_crew_display() if hasattr(obj, "get_role_in_crew_display") else str(obj.role_in_crew)


@admin.register(AircraftMovement)
class AircraftMovementAdmin(ModelAdmin):
    """Панель учета дислокации и перемещений ВС."""

    list_display = ["aircraft", "mpd", "date", "created_by", "created_at"]
    list_filter = [
        ("date", RangeDateFilter),
        "mpd",
        "aircraft__type_property",
    ]
    search_fields = [
        "aircraft__registration_number",
        "aircraft__factory_number",
        "mpd__name",
        "comment",
    ]
    date_hierarchy = "date"
    autocomplete_fields = ["aircraft", "mpd", "created_by"]
    compressed_fields = True
    warn_unsaved_form = True
