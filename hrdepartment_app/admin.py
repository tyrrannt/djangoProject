from typing import Optional, Tuple, Any, List
import datetime

from django.contrib import admin
from administration_app.utils import format_name_initials
from customers_app.mixin import ActiveUsersFilterMixin
from customers_app.models import Groups
from hrdepartment_app.forms import OrderDescriptionForm
from hrdepartment_app.models import (
    Medical,
    Purpose,
    OfficialMemo,
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
    MedicalOrganisation,
    DocumentsJobDescription,
    DocumentsOrder,
    PlaceProductionActivity,
    ReportCard,
    ReasonForCancellation,
    OrderDescription,
    PreHolidayDay,
    WeekendDay,
    ProductionCalendar,
    TypesUserworktime,
    Instructions,
    Provisions,
    CreatingTeam,
    TimeSheet,
    OperationalWork,
    PeriodicWork,
    OutfitCard,
    DocumentAcknowledgment,
    Briefings,
    Operational,
    DataBaseUserEvent,
    LaborProtection,
    BusinessProcessRoutes,
    GuidanceDocuments,
    LaborProtectionInstructions,
    TrainingUnit,
    TrainingProgram,
    StudentAgreement,
    PowerOfAttorney,
    AircraftHoursTracking,
    HoursTrackingSource,
    ExternalMaintenanceOrganization,
    AviationComponent,
    AviationComponentStatus,
    ComponentReleaseDocType,
    ComponentOperationType,
    OutfitCardComponent,
    CompanyMaintenanceCertificate,
    MaintenanceReleaseCertificate,
)
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter


@admin.register(DocumentsJobDescription)
class DocumentsJobDescriptionAdmin(ModelAdmin):
    """Администрирование должностных инструкций."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Purpose)
class PurposeAdmin(ModelAdmin):
    """Администрирование целей служебных командировок/поездок."""
    list_display = ("pk", "title")
    search_fields = ("title",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Groups)
class GroupsAdmin(ModelAdmin):
    """Администрирование рабочих групп."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(ReasonForCancellation)
class ReasonForCancellationAdmin(ModelAdmin):
    """Администрирование причин аннулирования служебных записок."""
    list_display = ("pk", "name")
    search_fields = ("name",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(TypesUserworktime)
class TypesUserworktimeAdmin(ModelAdmin):
    """Администрирование типов рабочего времени."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Instructions)
class InstructionsAdmin(ModelAdmin):
    """Администрирование общих инструкций."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(LaborProtectionInstructions)
class LaborProtectionInstructionsAdmin(ModelAdmin):
    """Администрирование инструкций по охране труда."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(DocumentAcknowledgment)
class DocumentAcknowledgmentAdmin(ModelAdmin):
    """Администрирование журнала ознакомления с документами."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(DataBaseUserEvent)
class DataBaseUserEventAdmin(ModelAdmin):
    """Администрирование событий пользователей."""
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(PowerOfAttorney)
class PowerOfAttorneyAdmin(ModelAdmin):
    """Администрирование доверенностей сотрудников."""
    list_display = ("number", "issue_date", "expiry_date", "display_received")
    list_filter = (
        ("issue_date", RangeDateFilter),
        ("expiry_date", RangeDateFilter),
        "is_received",
    )
    search_fields = ("number",)
    readonly_fields = ("received_at", "received_by_user")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Получено", boolean=True)
    def display_received(self, obj: PowerOfAttorney) -> bool:
        """Флаг фактического получения доверенности."""
        return obj.is_received


@admin.register(GuidanceDocuments)
class GuidanceDocumentsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование руководящих документов."""
    list_display = (
        "display_doc_header",
        "document_date",
        "access",
        "validity_period_start",
        "validity_period_end",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Руководящий документ", header=True)
    def display_doc_header(self, obj: GuidanceDocuments) -> Tuple[str, str]:
        """Возвращает наименование и номер документа."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: GuidanceDocuments) -> bool:
        """Флаг актуальности документа."""
        return obj.actuality


@admin.register(TimeSheet)
class TimeSheetAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование табелей рабочего времени."""
    list_display = ("date", "get_person", "time_sheets_place", "notes")
    list_filter = (
        ("date", RangeDateFilter),
        "time_sheets_place",
    )
    search_fields = ["notes", "employee__title", "employee__last_name"]
    compressed_fields = True
    warn_unsaved_form = True

    @admin.display(description="Ответственный")
    def get_person(self, obj: TimeSheet) -> str:
        try:
            return format_name_initials(obj.employee.title)
        except AttributeError:
            return ""


class OutfitCardComponentInline(TabularInline):
    """Инлайн технологических операций с компонентами в карте-наряде."""
    model = OutfitCardComponent
    extra = 0
    autocomplete_fields = ["installed_component"]
    fields = (
        "operation_type",
        "installed_component",
        "installed_position",
        "removed_component_name",
        "removed_part_number",
        "removed_serial_number",
        "removal_reason",
    )


@admin.register(OutfitCard)
class OutfitCardAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование карт нарядов на ТО."""
    list_display = ("display_card_header", "outfit_card_date", "get_person", "outfit_card_place", "air_board")
    list_filter = (
        "air_board",
        "outfit_card_place",
        ("outfit_card_date", RangeDateFilter),
    )
    search_fields = ["outfit_card_number"]
    inlines = [OutfitCardComponentInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Карта наряда", header=True)
    def display_card_header(self, obj: OutfitCard) -> Tuple[str, str]:
        """Возвращает номер карты наряда и борт."""
        return f"№ {obj.outfit_card_number}", f"Борт: {obj.air_board or '—'}"

    @admin.display(description="Ответственный")
    def get_person(self, obj: OutfitCard) -> str:
        try:
            return format_name_initials(obj.employee.title)
        except AttributeError:
            return ""


@admin.register(AircraftHoursTracking)
class AircraftHoursTrackingAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование журнала учета наработки воздушных судов (ФАП-367)."""

    list_display = (
        "display_aircraft_header",
        "record_date",
        "flight_hours",
        "flight_hours_tsor",
        "flight_cycles",
        "display_source",
        "get_author",
    )
    list_filter = (
        "source",
        "air_board__type_property",
        ("record_date", RangeDateFilter),
    )
    search_fields = [
        "air_board__registration_number",
        "air_board__factory_number",
        "notes",
    ]
    autocomplete_fields = ["air_board", "outfit_card", "created_by"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Воздушное судно", header=True)
    def display_aircraft_header(self, obj: AircraftHoursTracking) -> Tuple[str, str]:
        """Возвращает бортовой номер и тип ВС."""
        board = obj.air_board
        type_name = str(board.type_property) if board and board.type_property else "Тип не указан"
        reg_num = board.registration_number if board else "—"
        return reg_num, type_name

    @display(
        description="Источник",
        label={
            HoursTrackingSource.MANUAL.value: "info",
            HoursTrackingSource.IMPORT.value: "warning",
            HoursTrackingSource.OUTFIT_CARD.value: "success",
        },
    )
    def display_source(self, obj: AircraftHoursTracking) -> str:
        """Цветной бейдж источника наработки."""
        return obj.source

    @admin.display(description="Автор")
    def get_author(self, obj: AircraftHoursTracking) -> str:
        """Возвращает инициалы автора записи."""
        if obj.created_by:
            return format_name_initials(obj.created_by.title)
        return "—"


@admin.register(ExternalMaintenanceOrganization)
class ExternalMaintenanceOrganizationAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование привлекаемых организаций по ТО компонентов (ФАП-367, разд. XV)."""

    list_display = (
        "display_org_header",
        "certificate_number",
        "certificate_agency",
        "valid_until_display",
        "display_status",
        "contract_number",
    )
    list_filter = (
        "is_active",
        ("certificate_issue_date", RangeDateFilter),
        ("certificate_valid_until", RangeDateFilter),
    )
    search_fields = [
        "name",
        "short_name",
        "certificate_number",
        "approved_categories",
        "contract_number",
    ]
    autocomplete_fields = ["counteragent"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Организация ТО", header=True)
    def display_org_header(self, obj: ExternalMaintenanceOrganization) -> Tuple[str, str]:
        """Возвращает наименование организации и реквизиты договора."""
        return obj.short_name or obj.name, f"Договор: {obj.contract_number or 'б/н'}"

    @display(description="Срок сертификата")
    def valid_until_display(self, obj: ExternalMaintenanceOrganization) -> str:
        """Отображает срок действия сертификата."""
        if obj.certificate_valid_until:
            return f"до {obj.certificate_valid_until:%d.%m.%Y}"
        return "Бессрочный"

    @display(
        description="Статус допуска",
        label={
            "valid": "success",
            "warning": "warning",
            "expired": "danger",
            "inactive": "danger",
        },
    )
    def display_status(self, obj: ExternalMaintenanceOrganization) -> str:
        """Отображает статус легитимности организации."""
        if not obj.is_active:
            return "inactive"
        today = datetime.date.today()
        if obj.certificate_valid_until and obj.certificate_valid_until < today:
            return "expired"
        if obj.certificate_valid_until and (obj.certificate_valid_until - today).days <= 30:
            return "warning"
        return "valid"


@admin.register(AviationComponent)
class AviationComponentAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование реестра авиационных компонентов и агрегатов (ФАП-367, разд. IV)."""

    list_display = (
        "display_component_header",
        "aircraft_type",
        "display_status",
        "display_current_aircraft",
        "release_doc_display",
        "display_repair_org",
        "remaining_hours",
    )
    list_filter = (
        "status",
        "aircraft_type",
        "release_doc_type",
        "last_repair_org",
    )
    search_fields = [
        "name",
        "part_number",
        "serial_number",
        "release_doc_number",
        "notes",
    ]
    autocomplete_fields = ["current_aircraft", "last_repair_org"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Агрегат (P/N, S/N)", header=True)
    def display_component_header(self, obj: AviationComponent) -> Tuple[str, str]:
        """Возвращает название компонента, P/N и S/N."""
        return obj.name, f"P/N: {obj.part_number} | S/N: {obj.serial_number}"

    @display(
        description="Статус годности",
        label={
            AviationComponentStatus.STOCK.value: "success",
            AviationComponentStatus.INSTALLED.value: "info",
            AviationComponentStatus.REPAIR.value: "warning",
            AviationComponentStatus.SCRAPPED.value: "danger",
        },
    )
    def display_status(self, obj: AviationComponent) -> str:
        """Цветной бейдж статуса компонента."""
        return obj.status

    @display(description="Установлен на ВС")
    def display_current_aircraft(self, obj: AviationComponent) -> str:
        """Бортовой номер ВС, на котором установлен агрегат."""
        return obj.current_aircraft.registration_number if obj.current_aircraft else "—"

    @display(description="Документ о годности")
    def release_doc_display(self, obj: AviationComponent) -> str:
        """Реквизиты входящего документа о годности."""
        if not obj.release_doc_number:
            return "Без документа"
        date_str = f" от {obj.release_doc_date:%d.%m.%Y}" if obj.release_doc_date else ""
        return f"№ {obj.release_doc_number}{date_str}"

    @display(description="АРЗ / Организация ТО")
    def display_repair_org(self, obj: AviationComponent) -> str:
        """Организация, выполнившая последнее ТО."""
        return obj.last_repair_org.short_name if obj.last_repair_org else "—"


@admin.register(OutfitCardComponent)
class OutfitCardComponentAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование операций установки и демонтажа агрегатов при ТО."""

    list_display = (
        "display_op_header",
        "outfit_card",
        "installed_component",
        "display_removed",
        "installed_position",
        "created_at",
    )
    list_filter = (
        "operation_type",
        ("created_at", RangeDateFilter),
    )
    search_fields = [
        "outfit_card__outfit_card_number",
        "installed_component__name",
        "installed_component__part_number",
        "installed_component__serial_number",
        "removed_component_name",
        "removed_part_number",
        "removed_serial_number",
    ]
    autocomplete_fields = ["outfit_card", "installed_component"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Операция", header=True)
    def display_op_header(self, obj: OutfitCardComponent) -> Tuple[str, str]:
        """Возвращает тип операции и наряд."""
        card_num = obj.outfit_card.outfit_card_number if obj.outfit_card else f"#{obj.outfit_card_id}"
        return obj.get_operation_type_display(), f"Наряд № {card_num}"

    @display(description="Снятый агрегат")
    def display_removed(self, obj: OutfitCardComponent) -> str:
        """Сведения о демонтированном агрегате."""
        if obj.removed_component_name:
            sn_str = f" (S/N {obj.removed_serial_number})" if obj.removed_serial_number else ""
            return f"{obj.removed_component_name}{sn_str}"
        return "—"


@admin.register(CompanyMaintenanceCertificate)
class CompanyMaintenanceCertificateAdmin(ModelAdmin):
    """Администрирование сертификатов организации по ТО (ФАП-145)."""

    list_display = (
        "display_cert_header",
        "issue_date",
        "valid_until",
        "organization_name_ru",
        "display_is_active",
    )
    list_filter = (
        "is_active",
        ("issue_date", RangeDateFilter),
    )
    search_fields = ["certificate_number", "organization_name_ru", "organization_name_en", "notes"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Сертификат", header=True)
    def display_cert_header(self, obj: CompanyMaintenanceCertificate) -> Tuple[str, str]:
        """Возвращает номер сертификата и статус."""
        return f"№ {obj.certificate_number}", f"Выдан: {obj.issue_date:%d.%m.%Y}"

    @display(description="Статус", boolean=True)
    def display_is_active(self, obj: CompanyMaintenanceCertificate) -> bool:
        """Признак активности основного сертификата."""
        return obj.is_active


@admin.register(MaintenanceReleaseCertificate)
class MaintenanceReleaseCertificateAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование Журнала свидетельств о выполнении ТО ВС (CRS)."""

    list_display = (
        "display_crs_header",
        "maintenance_date",
        "aircraft_type",
        "tail_number",
        "factory_number",
        "operating_hours",
        "display_staff",
        "issue_date",
    )
    list_filter = (
        "year",
        "aircraft_type",
        ("maintenance_date", RangeDateFilter),
        ("issue_date", RangeDateFilter),
    )
    search_fields = [
        "certificate_number",
        "tail_number",
        "factory_number",
        "maintenance_work_scope",
        "certifying_staff_name",
        "certifying_staff_license",
        "outfit_card__outfit_card_number",
    ]
    autocomplete_fields = ["outfit_card", "certifying_staff"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Свидетельство CRS", header=True)
    def display_crs_header(self, obj: MaintenanceReleaseCertificate) -> Tuple[str, str]:
        """Возвращает номер свидетельства и борт."""
        return f"Свидетельство № {obj.certificate_number}", f"Борт: {obj.tail_number} ({obj.aircraft_type})"

    @display(description="Подтверждающий персонал")
    def display_staff(self, obj: MaintenanceReleaseCertificate) -> str:
        """ФИО и номер бессрочного свидетельства специалиста."""
        lic = f" [{obj.certifying_staff_license}]" if obj.certifying_staff_license else ""
        return f"{obj.certifying_staff_name}{lic}"


@admin.register(Medical)
class MedicalAdmin(ModelAdmin):
    """Администрирование медицинских осмотров сотрудников."""
    list_display = ("get_person", "get_inspection_view", "number", "date_of_inspection")
    list_filter = (("date_of_inspection", RangeDateFilter),)
    search_fields = ["number", "person__title", "person__last_name"]
    compressed_fields = True
    warn_unsaved_form = True

    def get_inspection_view(self, obj: Medical) -> str:
        return obj.get_type_inspection_display()

    def get_person(self, obj: Medical) -> str:
        return format_name_initials(obj.person.title)


@admin.register(MedicalOrganisation)
class MedicalOrganisationAdmin(ModelAdmin):
    """Администрирование медицинских организаций."""
    list_display = ("description", "ogrn", "address", "email", "phone")
    search_fields = ["description", "ogrn", "email"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(PlaceProductionActivity)
class PlaceProductionActivityAdmin(ModelAdmin):
    """Администрирование мест производственной деятельности."""
    list_display = (
        "name",
        "short_name",
        "icao_code",
        "address",
        "email",
        "additional_payment",
        "use_team_orders",
        "in_planning",
        "ticket_control",
        "weather_monitoring_enabled",
    )
    list_filter = ("in_planning", "weather_monitoring_enabled", "use_team_orders", "ticket_control")
    search_fields = ["name", "short_name", "icao_code", "address", "email"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(ProductionCalendar)
class ProductionCalendarAdmin(ModelAdmin):
    """Администрирование производственного календаря."""
    list_display = (
        "calendar_month",
        "number_calendar_days",
        "number_working_days",
        "number_days_off_and_holidays",
        "description",
    )
    search_fields = ["calendar_month"]
    compressed_fields = True
    warn_unsaved_form = True


def copy_weekend_day(modeladmin, request, queryset):
    for weekend_day in queryset:
        weekend_day.pk = None
        weekend_day.save()


copy_weekend_day.short_description = "Копировать праздничный день"


@admin.register(WeekendDay)
class WeekendDayAdmin(ModelAdmin):
    """Администрирование выходных и праздничных дней."""
    list_display = ("weekend_day", "weekend_type", "description")
    list_filter = (
        "weekend_type",
        ("weekend_day", RangeDateFilter),
    )
    search_fields = ["weekend_day", "description"]
    actions = [copy_weekend_day]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(PreHolidayDay)
class PreHolidayDayAdmin(ModelAdmin):
    """Администрирование предпраздничных дней."""
    list_display = ("preholiday_day", "work_time")
    search_fields = ["preholiday_day"]
    list_filter = (("preholiday_day", RangeDateFilter),)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(DocumentsOrder)
class DocumentsOrderAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование приказов по предприятию."""
    list_display = (
        "display_doc_header",
        "document_date",
        "access",
        "get_employee",
        "validity_period_start",
        "get_document_order_type",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Приказ", header=True)
    def display_doc_header(self, obj: DocumentsOrder) -> Tuple[str, str]:
        """Возвращает наименование приказа и номер."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: DocumentsOrder) -> bool:
        """Флаг актуальности приказа."""
        return obj.actuality

    def get_document_order_type(self, obj: DocumentsOrder) -> str:
        return obj.get_document_order_type_display()

    def get_employee(self, obj: DocumentsOrder) -> str:
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return "; ".join(s)


@admin.register(Provisions)
class ProvisionsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование положений предприятия."""
    list_display = (
        "display_doc_header",
        "document_date",
        "access",
        "get_employee",
        "validity_period_start",
        "validity_period_end",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Положение", header=True)
    def display_doc_header(self, obj: Provisions) -> Tuple[str, str]:
        """Возвращает наименование и номер положения."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: Provisions) -> bool:
        """Флаг актуальности положения."""
        return obj.actuality

    def get_employee(self, obj: Provisions) -> str:
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return "; ".join(s)


@admin.register(Briefings)
class BriefingsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование инструктажей."""
    list_display = (
        "display_doc_header",
        "document_date",
        "access",
        "get_employee",
        "validity_period_start",
        "validity_period_end",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Инструктаж", header=True)
    def display_doc_header(self, obj: Briefings) -> Tuple[str, str]:
        """Возвращает наименование и номер инструктажа."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: Briefings) -> bool:
        """Флаг актуальности инструктажа."""
        return obj.actuality

    def get_employee(self, obj: Briefings) -> str:
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return "; ".join(s)


@admin.register(LaborProtection)
class LaborProtectionAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование документов по охране труда."""
    list_display = (
        "display_doc_header",
        "document_date",
        "access",
        "get_employee",
        "validity_period_start",
        "validity_period_end",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Документ по охране труда", header=True)
    def display_doc_header(self, obj: LaborProtection) -> Tuple[str, str]:
        """Возвращает наименование и номер документа по охране труда."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: LaborProtection) -> bool:
        """Флаг актуальности документа."""
        return obj.actuality

    def get_employee(self, obj: LaborProtection) -> str:
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return "; ".join(s)


@admin.register(Operational)
class OperationalAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование оперативных распоряжений."""
    list_display = (
        "display_doc_header",
        "document_date",
        "document_number",
        "validity_period_start",
        "validity_period_end",
        "display_actuality",
    )
    list_filter = (
        "actuality",
        "applying_for_job",
        ("document_date", RangeDateFilter),
    )
    search_fields = ["document_name", "document_number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Оперативное распоряжение", header=True)
    def display_doc_header(self, obj: Operational) -> Tuple[str, str]:
        """Возвращает наименование и номер распоряжения."""
        return obj.document_name, f"№ {obj.document_number or 'б/н'}"

    @display(description="Актуально", boolean=True)
    def display_actuality(self, obj: Operational) -> bool:
        """Флаг актуальности распоряжения."""
        return obj.actuality


@admin.register(CreatingTeam)
class CreatingTeamAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование формирования выездных бригад."""
    list_display = (
        "display_team_header",
        "date_create",
        "get_team_brigade",
        "place",
        "date_start",
        "date_end",
        "display_agreed",
        "display_email_send",
    )
    list_filter = (
        "agreed",
        "email_send",
        ("date_start", RangeDateFilter),
        ("date_end", RangeDateFilter),
    )
    search_fields = ["senior_brigade__title", "number"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Бригада", header=True)
    def display_team_header(self, obj: CreatingTeam) -> Tuple[str, str]:
        """Возвращает номер приказа и бригадира."""
        senior = format_name_initials(obj.senior_brigade.title) if obj.senior_brigade else "Бригадир не указан"
        return f"№ {obj.number or 'б/н'}", f"{senior} | {obj.place or 'База'}"

    @display(description="Согласовано", boolean=True)
    def display_agreed(self, obj: CreatingTeam) -> bool:
        """Флаг согласования состава бригады."""
        return obj.agreed

    @display(description="Email отправлен", boolean=True)
    def display_email_send(self, obj: CreatingTeam) -> bool:
        """Флаг отправки оповещений по email."""
        return obj.email_send

    def get_team_brigade(self, obj: CreatingTeam) -> str:
        s = [format_name_initials(item.title) for item in obj.team_brigade.iterator()]
        return "; ".join(s)


@admin.register(BusinessProcessDirection)
class BusinessProcessDirectionAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование направлений маршрутизации бизнес-процессов."""
    list_display = (
        "business_process_type",
        "get_person_executor",
        "get_person_agreement",
        "get_person_hr",
        "get_clerk",
    )
    list_filter = ("business_process_type",)
    ordering = ["business_process_type"]
    list_per_page = 100
    compressed_fields = True
    warn_unsaved_form = True

    def get_clerk(self, obj: BusinessProcessDirection) -> str:
        s = [item.name for item in obj.clerk.iterator()]
        return "; ".join(s)

    def get_person_executor(self, obj: BusinessProcessDirection) -> str:
        s = [item.name for item in obj.person_executor.iterator()]
        return "; ".join(s)

    def get_person_agreement(self, obj: BusinessProcessDirection) -> str:
        s = [item.name for item in obj.person_agreement.iterator()]
        return "; ".join(s)

    def get_person_hr(self, obj: BusinessProcessDirection) -> str:
        s = [item.name for item in obj.person_hr.iterator()]
        return "; ".join(s)


@admin.register(BusinessProcessRoutes)
class BusinessProcessRoutesAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование маршрутов бизнес-процессов."""
    list_display = (
        "business_process_type",
        "get_person_executor",
        "get_person_agreement",
        "get_person_hr",
        "get_clerk",
    )
    list_filter = ("business_process_type",)
    ordering = ["business_process_type"]
    list_per_page = 100
    compressed_fields = True
    warn_unsaved_form = True

    def get_clerk(self, obj: BusinessProcessRoutes) -> str:
        s = [format_name_initials(item.title) for item in obj.person_clerk.iterator()]
        return "; ".join(s)

    get_clerk.short_description = "Делопроизводители"

    def get_person_executor(self, obj: BusinessProcessRoutes) -> str:
        s = [format_name_initials(item.title) for item in obj.person_executor.iterator()]
        return "; ".join(s)

    get_person_executor.short_description = "Исполнители"

    def get_person_agreement(self, obj: BusinessProcessRoutes) -> str:
        s = [format_name_initials(item.title) for item in obj.person_agreement.iterator()]
        return "; ".join(s)

    get_person_agreement.short_description = "Согласующие"

    def get_person_hr(self, obj: BusinessProcessRoutes) -> str:
        s = [format_name_initials(item.title) for item in obj.person_hr.iterator()]
        return "; ".join(s)

    get_person_hr.short_description = "Специалисты ОК"


@admin.register(ReportCard)
class ReportCardAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование табелей учета рабочего времени."""
    list_display = ("display_report_header", "record_type", "start_time", "end_time")
    search_fields = ["employee__title", "employee__last_name", "employee__first_name"]
    list_filter = (
        ("report_card_day", RangeDateFilter),
        "record_type",
    )
    ordering = ["-report_card_day"]
    list_per_page = 100
    list_select_related = ("employee",)
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Сотрудник / День", header=True)
    def display_report_header(self, obj: ReportCard) -> Tuple[str, str]:
        """Возвращает ФИО сотрудника и дату табеля."""
        emp_name = format_name_initials(obj.employee.title) if obj.employee else "Сотрудник не указан"
        return emp_name, f"Дата: {obj.report_card_day}"


@admin.register(OfficialMemo)
class OfficialMemoAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование служебных записок."""
    list_display = (
        "display_memo_header",
        "display_type_trip",
        "period_from",
        "period_for",
        "display_cancellation",
    )
    search_fields = ["comments", "person__title", "person__last_name", "person__first_name"]
    list_filter = (
        "cancellation",
        "type_trip",
        "purpose_trip",
        ("period_from", RangeDateFilter),
        ("period_for", RangeDateFilter),
    )
    ordering = ["-period_from", "person"]
    list_per_page = 100
    list_select_related = ("person", "purpose_trip")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Служебная записка", header=True)
    def display_memo_header(self, obj: OfficialMemo) -> Tuple[str, str]:
        """Возвращает сотрудника и цель поездки."""
        person_name = format_name_initials(obj.person.title) if obj.person else "Сотрудник не указан"
        purpose = obj.purpose_trip.title if obj.purpose_trip else "Цель не указана"
        return person_name, purpose

    @display(description="Аннулирована", boolean=True)
    def display_cancellation(self, obj: OfficialMemo) -> bool:
        """Флаг аннулирования служебной записки."""
        return obj.cancellation

    @display(
        description="Тип поездки",
        label={
            "1": "info",
            "2": "warning",
            "3": "success",
        },
    )
    def display_type_trip(self, obj: OfficialMemo) -> Tuple[str, str]:
        """Возвращает тип поездки с бейджем."""
        return str(obj.type_trip), obj.get_type_trip_display()


@admin.register(ApprovalOficialMemoProcess)
class ApprovalOficialMemoProcessAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование процессов согласования служебных записок."""
    list_display = (
        "display_process_header",
        "order",
        "start_date_trip",
        "end_date_trip",
        "display_email_send",
        "display_cancellation",
        "display_accounting",
    )
    search_fields = (
        "document__person__last_name",
        "document__person__first_name",
        "document__person__title",
    )
    list_filter = (
        "cancellation",
        "accepted_accounting",
        "email_send",
        ("start_date_trip", RangeDateFilter),
        ("end_date_trip", RangeDateFilter),
        ("date_of_creation", RangeDateFilter),
    )
    ordering = ["-start_date_trip", "document__person"]
    list_per_page = 100
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Процесс согласования СЗ", header=True)
    def display_process_header(self, obj: ApprovalOficialMemoProcess) -> Tuple[str, str]:
        """Возвращает номер процесса и инициатора."""
        person_name = (
            format_name_initials(obj.document.person.title)
            if obj.document and obj.document.person
            else "Сотрудник не указан"
        )
        return f"Процесс #{obj.pk}", f"СЗ: {person_name}"

    @display(description="Email отправлен", boolean=True)
    def display_email_send(self, obj: ApprovalOficialMemoProcess) -> bool:
        """Флаг отправки email."""
        return obj.email_send

    @display(description="Аннулировано", boolean=True)
    def display_cancellation(self, obj: ApprovalOficialMemoProcess) -> bool:
        """Флаг аннулирования процесса."""
        return obj.cancellation

    @display(description="Бухгалтерия", boolean=True)
    def display_accounting(self, obj: ApprovalOficialMemoProcess) -> bool:
        """Флаг принятия бухгалтерией."""
        return obj.accepted_accounting

    def save_model(self, request, obj, form, change):
        if any(
            f in form.changed_data
            for f in ["daily_allowance", "travel_expense", "accommodation_expense", "other_expense"]
        ):
            obj.prepaid_expense_summ = (
                obj.daily_allowance + obj.travel_expense + obj.accommodation_expense + obj.other_expense
            )
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "document",
            "order",
            "reason_cancellation",
            "person_executor",
            "person_agreement",
            "person_accounting",
        )


@admin.register(OrderDescription)
class OrderDescriptionAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование типов распоряжений и оснований приказов."""
    form = OrderDescriptionForm
    list_display = ("name", "affiliation")
    search_fields = ("name",)
    list_filter = ("affiliation",)
    fieldsets = ((None, {"fields": ("name", "affiliation")}),)
    add_fieldsets = ((None, {"fields": ("name", "affiliation")}),)
    ordering = ("name",)
    compressed_fields = True
    warn_unsaved_form = True

    def get_fieldsets(self, request, obj=None):
        if obj:
            return self.fieldsets
        return self.add_fieldsets


def copy_operational_work(modeladmin, request, queryset):
    for operational_work in queryset:
        operational_work.pk = None
        operational_work.save()


copy_operational_work.short_description = "Копировать выбранные оперативные работы"


@admin.register(OperationalWork)
class OperationalWorkAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование видов оперативных работ."""
    list_display = ("code", "name", "description", "air_bord_type")
    list_filter = ("air_bord_type",)
    search_fields = ["name", "code"]
    actions = [copy_operational_work]
    compressed_fields = True
    warn_unsaved_form = True


def copy_periodic_work(modeladmin, request, queryset):
    """Копирует выбранные записи периодических работ.

    Args:
        modeladmin: Экземпляр ModelAdmin.
        request: Объект HTTP-запроса.
        queryset: QuerySet выбранных объектов PeriodicWork.
    """
    for periodic_work in queryset:
        periodic_work.pk = None
        periodic_work.save()


copy_periodic_work.short_description = "Копировать выбранные периодические работы"


@admin.register(PeriodicWork)
class PeriodicWorkAdmin(ActiveUsersFilterMixin, ModelAdmin):
    """Администрирование видов периодических регламентных работ."""

    list_display = (
        "pk",
        "air_bord_type",
        "code",
        "name",
        "ratio",
        "lag_minus",
        "lag_plus",
        "display_color",
    )
    list_filter = ("air_bord_type", "color")
    search_fields = ["name", "code"]
    actions = [copy_periodic_work]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Цвет",
        label={
            "yellow": "warning",
            "green": "success",
            "red": "danger",
        },
    )
    def display_color(self, obj: PeriodicWork) -> str:
        """Отображает цветную плашку статуса регламентной работы.

        Args:
            obj: Экземпляр PeriodicWork.

        Returns:
            str: Код цвета ('yellow', 'green', 'red') для бейджа Unfold.
        """
        return obj.color



@admin.register(TrainingProgram)
class TrainingProgramAdmin(ModelAdmin):
    """Администрирование программ обучения авиационного персонала."""
    list_display = ("pk", "counteragent_name", "program_name")
    search_fields = ["program_name", "counteragent_name__short_name"]
    list_filter = ("counteragent_name",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(TrainingUnit)
class TrainingUnitAdmin(ModelAdmin):
    """Администрирование учебных модулей и дисциплин."""
    list_display = ("pk", "unit_name_short", "program_units")
    search_fields = ["unit_name", "unit_name_short"]
    list_filter = ("program_units",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(StudentAgreement)
class StudentAgreementAdmin(ModelAdmin):
    """Администрирование ученических договоров."""
    search_fields = ["student_agreement_number"]
    compressed_fields = True
    warn_unsaved_form = True
