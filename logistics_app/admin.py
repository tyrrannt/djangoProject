from django.contrib import admin

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



# Register your models here.
@admin.register(WayBill)
class WayBillAdmin(ModelAdmin):
    list_display = ("document_date", "place_of_departure", "place_division",
                    "sender", "state", "responsible", "date_of_creation", "executor", "urgency")

@admin.register(PackageImage)
class PackageImageAdmin(ModelAdmin):
    list_display = ("date_of_creation", "package", "caption")

@admin.register(Package)
class PackageAdmin(ModelAdmin):
    list_display = ("date_of_dispatch", "number_of_dispatch", "place_of_dispatch", "get_executor", "type_of_dispatch")
    list_filter = (
        "type_of_dispatch",
    )

    def get_executor(self, obj: Package):
        return format_name_initials(obj.executor.title) if obj.executor else ''

    search_fields = ["number_of_dispatch", ]

@admin.register(Grade)
class GradeAdmin(ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(NomenclatureUnit)
class UnitAdmin(ModelAdmin):
    list_display = ('name', 'short_name')
    search_fields = ('name', 'short_name')

@admin.register(NomenclatureGroup)
class GroupAdmin(ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)
    list_filter = ('parent',)

@admin.register(Nomenclature)
class NomenclatureAdmin(ModelAdmin):
    list_display = ('name', 'group', 'price', 'quantity', 'unit', 'serial_number', 'year_of_manufacture', 'weight', 'dimensions', 'grade', 'location', 'estate')
    search_fields = ('name', 'description', 'serial_number')
    list_filter = ('group', 'unit', 'grade', 'location', 'estate')


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


@admin.register(DocFlowNumberCounter)
class DocFlowNumberCounterAdmin(ModelAdmin):
    """Панель управления счетчиками автонумерации документов СЭД."""
    list_display = ("year", "flow_type", "last_number")
    list_filter = ("year", "flow_type")
    ordering = ("-year", "flow_type")


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


@admin.register(DocFlowRouteTemplate)
class DocFlowRouteTemplateAdmin(ModelAdmin):
    """Панель управления шаблонами маршрутов согласования СЭД."""
    list_display = ("name", "doc_type", "is_default", "created_at")
    list_filter = ("doc_type__category", "is_default")
    search_fields = ("name", "description")
    inlines = [DocFlowRouteStepTemplateInline]


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


@admin.register(DocFlowDocument)
class DocFlowDocumentAdmin(ModelAdmin):
    """Панель управления учетными карточками документов СЭД."""
    list_display = (
        "reg_number",
        "title",
        "doc_type",
        "flow_type",
        "status",
        "urgency",
        "initiator",
        "responsible",
        "current_step_order",
        "created_at",
    )
    list_filter = ("flow_type", "status", "urgency", "doc_type")
    search_fields = ("reg_number", "title", "description", "initiator__title", "responsible__title")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [DocFlowFileInline, DocFlowRouteStepInline]


@admin.register(DocFlowApprovalLog)
class DocFlowApprovalLogAdmin(ModelAdmin):
    """Панель аудита визирования и юридически значимых действий в СЭД."""
    list_display = ("created_at", "document", "user", "action", "target_step_order", "ip_address")
    list_filter = ("action", "created_at")
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


@admin.register(DocFlowComment)
class DocFlowCommentAdmin(ModelAdmin):
    """Панель управления комментариями и внутренними обсуждениями СЭД."""
    list_display = ("created_at", "document", "author", "parent")
    list_filter = ("created_at",)
    search_fields = ("document__reg_number", "author__title", "text")
    readonly_fields = ("created_at",)