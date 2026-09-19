"""Административная панель планирования полетов и управления экипажами."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from .models import (
    AircraftMovement,
    AviationWeatherForecast,
    AviationWeatherObservation,
    AviationWeatherStation,
    CoordinateWeatherForecast,
    CrewMember,
    EmployeeRequiredCheck,
    EmployeeStatusRecord,
    EmployeeStatusType,
    FlightCrew,
    FlightCrewNote,
    PeriodicCheckRecord,
    PeriodicCheckType,
    PilotAssignment,
)


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


@admin.register(AviationWeatherObservation)
class AviationWeatherObservationAdmin(ModelAdmin):
    """Панель архива фактических метеонаблюдений (METAR / SPECI)."""

    list_display = [
        "get_header",
        "flight_category_badge",
        "get_wind",
        "get_vis",
        "get_cloud",
        "get_temp",
        "get_pressure",
        "weather_phenomena",
        "observation_time",
        "report_type",
    ]
    list_filter = [
        "flight_category",
        "report_type",
        "cavok",
        ("observation_time", RangeDateFilter),
        "mpd",
    ]
    search_fields = ["icao_code", "raw_text", "mpd__name", "weather_phenomena"]
    date_hierarchy = "observation_time"
    autocomplete_fields = ["mpd"]
    readonly_fields = ["created_at"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(header=True, description="Станция / МПД")
    def get_header(self, obj: AviationWeatherObservation) -> list:
        """Двухстрочный заголовок: Код ICAO + Название МПД."""
        mpd_name = obj.mpd.name if obj.mpd else "Без привязки к МПД"
        return [obj.icao_code, mpd_name]

    @display(
        description="Условия",
        label={
            "VFR": "success",
            "MVFR": "info",
            "IFR": "danger",
            "LIFR": "dark",
        },
    )
    def flight_category_badge(self, obj: AviationWeatherObservation) -> str:
        """Цветной бейдж летной категории."""
        return obj.flight_category

    @display(description="Ветер")
    def get_wind(self, obj: AviationWeatherObservation) -> str:
        """Форматированное описание ветра."""
        return obj.get_wind_display()

    @display(description="Видимость")
    def get_vis(self, obj: AviationWeatherObservation) -> str:
        """Форматированная видимость."""
        return obj.get_visibility_display()

    @display(description="НГО")
    def get_cloud(self, obj: AviationWeatherObservation) -> str:
        """Форматированная облачность."""
        return obj.get_cloud_display()

    @display(description="Температура")
    def get_temp(self, obj: AviationWeatherObservation) -> str:
        """Температура воздуха."""
        if obj.temperature is None:
            return "—"
        prefix = "+" if obj.temperature > 0 else ""
        return f"{prefix}{obj.temperature:.0f}°C"

    @display(description="Давление QNH")
    def get_pressure(self, obj: AviationWeatherObservation) -> str:
        """Давление QNH."""
        if not obj.pressure_mmhg:
            return "—"
        return f"{obj.pressure_mmhg:.1f} мм"


@admin.register(AviationWeatherForecast)
class AviationWeatherForecastAdmin(ModelAdmin):
    """Панель архива авиационных прогнозов погоды (TAF)."""

    list_display = ["get_header", "issued_at", "valid_from", "valid_to", "is_valid_badge", "created_at"]
    list_filter = [
        ("issued_at", RangeDateFilter),
        ("valid_from", RangeDateFilter),
        "mpd",
    ]
    search_fields = ["icao_code", "raw_text", "mpd__name"]
    date_hierarchy = "issued_at"
    autocomplete_fields = ["mpd"]
    readonly_fields = ["created_at"]
    compressed_fields = True

    @display(header=True, description="Аэродром")
    def get_header(self, obj: AviationWeatherForecast) -> list:
        """Двухстрочный заголовок: TAF ICAO + МПД."""
        mpd_name = obj.mpd.name if obj.mpd else "—"
        return [f"TAF {obj.icao_code}", mpd_name]

    @display(description="Статус действия", boolean=True)
    def is_valid_badge(self, obj: AviationWeatherForecast) -> bool:
        """Флаг актуальности прогноза в текущий момент."""
        return obj.is_currently_valid()


@admin.register(AviationWeatherStation)
class AviationWeatherStationAdmin(ModelAdmin):
    """Панель управления справочником сертифицированных метеостанций (ICAO/АМСГ)."""

    list_display = ["icao_code", "name_ru", "name", "latitude", "longitude", "elevation_msl_m", "country", "is_active"]
    list_filter = ["is_active", "country"]
    search_fields = ["icao_code", "name", "name_ru"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(CoordinateWeatherForecast)
class CoordinateWeatherForecastAdmin(ModelAdmin):
    """Панель архива координатных сеточных прогнозов численных моделей (ECMWF/GFS)."""

    list_display = [
        "get_header",
        "forecast_for",
        "model",
        "model_flight_category_badge",
        "get_temp",
        "get_wind",
        "get_cloud",
        "get_pressure",
        "weather_description_display",
        "nearest_station_display",
        "fetched_at",
    ]
    list_filter = [
        ("forecast_for", RangeDateFilter),
        "model",
        "model_flight_category",
        "mpd",
    ]
    search_fields = ["mpd__name", "model", "nearest_station__icao_code", "nearest_station__name_ru"]
    date_hierarchy = "forecast_for"
    autocomplete_fields = ["mpd", "nearest_station"]
    readonly_fields = ["fetched_at"]
    compressed_fields = True

    @display(header=True, description="МПД / Координаты")
    def get_header(self, obj: CoordinateWeatherForecast) -> list:
        """Двухстрочный заголовок: МПД + координаты."""
        coords = f"{obj.latitude:.4f}°N, {obj.longitude:.4f}°E"
        return [obj.mpd.name, coords]

    @display(
        description="Условия (модель)",
        label={
            "VFR": "success",
            "MVFR": "info",
            "IFR": "danger",
            "LIFR": "dark",
        },
    )
    def model_flight_category_badge(self, obj: CoordinateWeatherForecast) -> str:
        """Цветной бейдж расчетных летных условий."""
        return obj.model_flight_category

    @display(description="Температура")
    def get_temp(self, obj: CoordinateWeatherForecast) -> str:
        """Температура воздуха."""
        if obj.temperature is None:
            return "—"
        prefix = "+" if obj.temperature > 0 else ""
        return f"{prefix}{obj.temperature:.0f}°C"

    @display(description="Ветер")
    def get_wind(self, obj: CoordinateWeatherForecast) -> str:
        """Форматированное описание ветра."""
        return obj.get_wind_display()

    @display(description="НГО / Облачность")
    def get_cloud(self, obj: CoordinateWeatherForecast) -> str:
        """Форматированная облачность."""
        return obj.get_cloud_display()

    @display(description="Давление пов.")
    def get_pressure(self, obj: CoordinateWeatherForecast) -> str:
        """Давление на поверхности площадки."""
        if not obj.surface_pressure_mmhg:
            return "—"
        return f"{obj.surface_pressure_mmhg:.1f} мм"

    @display(description="Погода")
    def weather_description_display(self, obj: CoordinateWeatherForecast) -> str:
        """Явление погоды по WMO."""
        return obj.weather_description

    @display(description="Опорная станция")
    def nearest_station_display(self, obj: CoordinateWeatherForecast) -> str:
        """Опорная метеостанция с кодом."""
        if not obj.nearest_station:
            return "—"
        return str(obj.nearest_station)


@admin.register(PeriodicCheckType)
class PeriodicCheckTypeAdmin(ModelAdmin):
    """Панель видов периодических проверок и мероприятий."""

    list_display = ["name", "code", "aircraft_type", "validity_months", "validity_days", "applies_to", "order", "is_active"]
    list_filter = ["is_active", "aircraft_type", "applies_to"]
    search_fields = ["name", "code", "description"]
    autocomplete_fields = ["aircraft_type"]
    compressed_fields = True


@admin.register(PeriodicCheckRecord)
class PeriodicCheckRecordAdmin(ModelAdmin):
    """Панель журнала периодических проверок персонала."""

    list_display = ["employee", "check_type", "start_date", "end_date", "is_active_record", "created_at"]
    list_filter = ["check_type", "aircraft_type", ("end_date", RangeDateFilter)]
    search_fields = ["employee__username", "employee__first_name", "employee__last_name", "check_type__name"]
    date_hierarchy = "end_date"
    autocomplete_fields = ["employee", "check_type", "aircraft_type", "created_by"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Действительно", boolean=True)
    def is_active_record(self, obj: PeriodicCheckRecord) -> bool:
        """Флаг актуальности проверки."""
        return obj.is_currently_valid


@admin.register(EmployeeStatusType)
class EmployeeStatusTypeAdmin(ModelAdmin):
    """Панель видов статусов сотрудников."""

    list_display = ["name", "code", "color", "is_blocking", "order", "is_active"]
    list_filter = ["is_blocking", "is_active"]
    search_fields = ["name", "code", "description"]
    compressed_fields = True


@admin.register(EmployeeStatusRecord)
class EmployeeStatusRecordAdmin(ModelAdmin):
    """Панель записей о статусах и отсутствиях сотрудников."""

    list_display = ["employee", "status_type", "start_date", "end_date", "created_at"]
    list_filter = ["status_type", ("start_date", RangeDateFilter)]
    search_fields = ["employee__username", "employee__first_name", "employee__last_name"]
    date_hierarchy = "start_date"
    autocomplete_fields = ["employee", "status_type", "created_by"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(EmployeeRequiredCheck)
class EmployeeRequiredCheckAdmin(ModelAdmin):
    """Панель закрепления обязательных проверок за персоналом."""

    list_display = ["employee", "check_type", "is_required", "created_at"]
    list_filter = ["is_required", "check_type"]
    search_fields = ["employee__username", "employee__first_name", "employee__last_name", "check_type__name"]
    autocomplete_fields = ["employee", "check_type", "assigned_by"]
    compressed_fields = True

