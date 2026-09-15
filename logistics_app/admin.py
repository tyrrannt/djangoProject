from django.contrib import admin
from django.utils.html import format_html

from administration_app.utils import format_name_initials
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowComment,
    DocFlowDocument,
    DocFlowDocumentType,
    DocFlowFile,
    DocFlowFileVersion,
    DocFlowNumberCounter,
    DocFlowRouteStep,
    DocFlowRouteStepTemplate,
    DocFlowRouteTemplate,
    Grade,
    Nomenclature,
    NomenclatureGroup,
    NomenclatureUnit,
    Package,
    PackageImage,
    WayBill,
)
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display


# ==============================================================================
# ПУТЕВЫЕ ЛИСТЫ, ПОСЫЛКИ И СКЛАД
# ==============================================================================

@admin.register(WayBill)
class WayBillAdmin(ModelAdmin):
    """Панель управления путевыми листами."""

    list_display = (
        "document_date",
        "place_of_departure",
        "place_division",
        "sender",
        "state_badge",
        "responsible",
        "urgency_badge",
        "date_of_creation",
    )
    list_filter = (
        ("document_date", RangeDateFilter),
        "state",
        "urgency",
        "place_division",
    )
    search_fields = ("place_of_departure", "sender", "responsible", "executor")
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Состояние",
        label={
            "created": "info",
            "sent": "warning",
            "received": "success",
            "rejected": "danger",
        },
    )
    def state_badge(self, obj: WayBill) -> str:
        """Цветной бейдж статуса путевого листа."""
        return str(obj.state) if obj.state else "—"

    @display(
        description="Срочность",
        label={
            "regular": "base",
            "urgent": "warning",
            "critical": "danger",
        },
    )
    def urgency_badge(self, obj: WayBill) -> str:
        """Цветной бейдж срочности."""
        return str(obj.urgency) if obj.urgency else "—"


@admin.register(PackageImage)
class PackageImageAdmin(ModelAdmin):
    """Панель управления изображениями посылок."""

    list_display = ("date_of_creation", "package", "caption")
    search_fields = ("caption", "package__number_of_dispatch")
    compressed_fields = True


@admin.register(Package)
class PackageAdmin(ModelAdmin):
    """Панель управления посылками."""

    list_display = (
        "number_of_dispatch",
        "date_of_dispatch",
        "place_of_dispatch",
        "get_executor",
        "type_badge",
    )
    list_filter = (
        "type_of_dispatch",
        ("date_of_dispatch", RangeDateFilter),
    )
    search_fields = ("number_of_dispatch", "place_of_dispatch", "executor__title")
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Тип отправления",
        label={
            "regular": "info",
            "valuable": "warning",
            "documents": "success",
        },
    )
    def type_badge(self, obj: Package) -> str:
        """Цветной бейдж типа отправления."""
        return str(obj.type_of_dispatch) if obj.type_of_dispatch else "—"

    @display(description="Исполнитель")
    def get_executor(self, obj: Package) -> str:
        return format_name_initials(obj.executor.title) if obj.executor else ""


@admin.register(Grade)
class GradeAdmin(ModelAdmin):
    """Панель управления грейдами."""

    list_display = ("name", "description")
    search_fields = ("name",)
    compressed_fields = True


@admin.register(NomenclatureUnit)
class UnitAdmin(ModelAdmin):
    """Панель управления единицами измерения номенклатуры."""

    list_display = ("name", "short_name")
    search_fields = ("name", "short_name")
    compressed_fields = True


@admin.register(NomenclatureGroup)
class GroupAdmin(ModelAdmin):
    """Панель управления группами номенклатуры."""

    list_display = ("name", "parent")
    search_fields = ("name",)
    list_filter = ("parent",)
    compressed_fields = True


@admin.register(Nomenclature)
class NomenclatureAdmin(ModelAdmin):
    """Панель управления номенклатурными единицами."""

    list_display = (
        "name",
        "group",
        "price",
        "quantity",
        "unit",
        "serial_number",
        "year_of_manufacture",
        "location",
        "estate",
    )
    search_fields = ("name", "description", "serial_number")
    list_filter = (
        "group",
        "unit",
        "grade",
        "location",
        "estate",
    )
    compressed_fields = True
    warn_unsaved_form = True


# ==============================================================================
# АДМИНИСТРАТИВНАЯ ПАНЕЛЬ СЭД И МАРШРУТИЗАЦИИ ДОКУМЕНТОВ
# ==============================================================================

@admin.register(DocFlowDocumentType)
class DocFlowDocumentTypeAdmin(ModelAdmin):
    """Панель управления справочником типов документов СЭД."""

    list_display = ("name", "category", "code", "default_sla_hours", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "code", "description")
    ordering = ("category", "name")
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(DocFlowNumberCounter)
class DocFlowNumberCounterAdmin(ModelAdmin):
    """Панель управления счетчиками автонумерации документов СЭД."""

    list_display = ("year", "flow_type_badge", "last_number")
    list_filter = ("year", "flow_type")
    ordering = ("-year", "flow_type")
    compressed_fields = True

    @display(
        description="Поток",
        label={
            "INTERNAL": "info",
            "INCOMING": "success",
            "OUTGOING": "warning",
        },
    )
    def flow_type_badge(self, obj: DocFlowNumberCounter) -> str:
        return obj.get_flow_type_display()


class DocFlowRouteStepTemplateInline(TabularInline):
    """Встроенный редактор шагов в шаблоне маршрута согласования."""

    model = DocFlowRouteStepTemplate
    extra = 1
    fields = (
        "step_order",
        "step_name",
        "step_type",
        "assigned_division",
        "assigned_user",
        "sla_hours",
        "allow_reviewer_file_edit",
        "can_rollback_to",
    )
    autocomplete_fields = ["assigned_division", "assigned_user"]


@admin.register(DocFlowRouteTemplate)
class DocFlowRouteTemplateAdmin(ModelAdmin):
    """Панель управления шаблонами маршрутов согласования СЭД."""

    list_display = ("name", "doc_type", "is_default", "created_at")
    list_filter = ("doc_type__category", "is_default")
    search_fields = ("name", "description")
    inlines = [DocFlowRouteStepTemplateInline]
    compressed_fields = True
    warn_unsaved_form = True


class DocFlowFileVersionInline(TabularInline):
    """Встроенный просмотр версий файлов документа."""

    model = DocFlowFileVersion
    extra = 0
    readonly_fields = ("version_number", "file", "file_size", "file_hash", "uploaded_by", "uploaded_at", "is_reviewer_edit")


class DocFlowFileInline(TabularInline):
    """Встроенный список прикрепленных файлов документа."""

    model = DocFlowFile
    extra = 0
    fields = ("title", "is_main", "current_version_number", "created_at")
    readonly_fields = ("created_at",)


class DocFlowRouteStepInline(TabularInline):
    """Встроенный список шагов маршрута согласования конкретного документа."""

    model = DocFlowRouteStep
    extra = 0
    fields = (
        "step_order",
        "step_name",
        "step_type",
        "status",
        "assigned_division",
        "assigned_user",
        "sla_hours",
        "started_at",
        "completed_at",
    )
    readonly_fields = ("started_at", "completed_at")
    autocomplete_fields = ["assigned_division", "assigned_user"]


@admin.register(DocFlowDocument)
class DocFlowDocumentAdmin(ModelAdmin):
    """Панель управления учетными карточками документов СЭД."""

    list_display = (
        "get_document_header",
        "doc_type",
        "flow_type_badge",
        "status_badge",
        "urgency_badge",
        "get_initiator_info",
        "current_step_order",
        "created_at",
    )
    list_filter = (
        "status",
        "urgency",
        "flow_type",
        "doc_type",
        ("created_at", RangeDateFilter),
    )
    search_fields = ("reg_number", "title", "description", "initiator__title", "responsible__title")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["initiator", "responsible", "doc_type"]
    inlines = [DocFlowFileInline, DocFlowRouteStepInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(header=True, description="Документ")
    def get_document_header(self, obj: DocFlowDocument) -> list:
        """Двухстрочное отображение: номер + наименование документа."""
        reg_num = obj.reg_number or "б/н"
        return [f"№ {reg_num}", obj.title]

    @display(
        description="Статус",
        label={
            "DRAFT": "warning",
            "ON_REVIEW": "info",
            "APPROVED": "success",
            "REJECTED": "danger",
            "ARCHIVED": "base",
        },
    )
    def status_badge(self, obj: DocFlowDocument) -> str:
        """Цветной бейдж статуса документа."""
        return obj.get_status_display()

    @display(
        description="Срочность",
        label={
            "REGULAR": "base",
            "URGENT": "warning",
            "CRITICAL": "danger",
        },
    )
    def urgency_badge(self, obj: DocFlowDocument) -> str:
        """Цветной бейдж срочности."""
        return obj.get_urgency_display()

    @display(
        description="Поток",
        label={
            "INTERNAL": "info",
            "INCOMING": "success",
            "OUTGOING": "warning",
        },
    )
    def flow_type_badge(self, obj: DocFlowDocument) -> str:
        """Цветной бейдж потока документа."""
        return obj.get_flow_type_display()

    @display(description="Инициатор")
    def get_initiator_info(self, obj: DocFlowDocument) -> str:
        """ФИО инициатора в инициальном формате."""
        return format_name_initials(obj.initiator.title) if obj.initiator else "—"


@admin.register(DocFlowApprovalLog)
class DocFlowApprovalLogAdmin(ModelAdmin):
    """Панель аудита визирования и юридически значимых действий в СЭД."""

    list_display = ("created_at", "document", "user", "action_badge", "target_step_order", "ip_address")
    list_filter = ("action", ("created_at", RangeDateFilter))
    search_fields = ("document__reg_number", "document__title", "user__title", "comment", "pep_signature_hash")
    readonly_fields = (
        "document",
        "route_step",
        "user",
        "action",
        "target_step_order",
        "comment",
        "created_at",
        "ip_address",
        "user_agent",
        "pep_signature_hash",
        "pep_certificate_id",
    )
    compressed_fields = True

    @display(
        description="Действие",
        label={
            "APPROVE": "success",
            "REJECT": "danger",
            "SIGN": "info",
            "COMMENT": "base",
            "ROLLBACK": "warning",
            "DELEGATE": "info",
        },
    )
    def action_badge(self, obj: DocFlowApprovalLog) -> str:
        """Цветной бейдж действия визирования."""
        return str(obj.action)


@admin.register(DocFlowComment)
class DocFlowCommentAdmin(ModelAdmin):
    """Панель управления комментариями и внутренними обсуждениями СЭД."""

    list_display = ("created_at", "document", "author", "parent")
    list_filter = (("created_at", RangeDateFilter),)
    search_fields = ("document__reg_number", "author__title", "text")
    readonly_fields = ("created_at",)
    compressed_fields = True