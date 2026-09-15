from typing import Optional, Tuple
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter

from contracts_app.models import (
    TypeProperty,
    TypeContract,
    Estate,
    Contract,
    Posts,
    TypeDocuments,
    CompanyProperty,
)


@admin.register(TypeContract)
class TypeContractAdmin(ModelAdmin):
    """Администрирование типов договоров."""
    list_display = ("pk", "type_contract")
    search_fields = ("type_contract",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(TypeProperty)
class TypePropertyAdmin(ModelAdmin):
    """Администрирование типов имущества/техники."""
    list_display = ("pk", "type_property")
    search_fields = ("type_property",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(TypeDocuments)
class TypeDocumentsAdmin(ModelAdmin):
    """Администрирование типов документов."""
    list_display = ("pk", "type_document", "short_name", "file_name_prefix")
    search_fields = ("type_document", "short_name", "file_name_prefix")
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Estate)
class EstateAdmin(ModelAdmin):
    """Администрирование имущества и воздушных судов компании."""
    list_display = (
        "display_estate_header",
        "type_property",
        "release_date",
        "decommission_date",
        "display_is_decommissioned",
    )
    list_filter = (
        "type_property",
        ("release_date", RangeDateFilter),
        ("decommission_date", RangeDateFilter),
    )
    search_fields = (
        "registration_number",
        "factory_number",
        "passport",
        "ownership_right",
        "exploits",
    )
    date_hierarchy = "release_date"
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Имущество / Бортовой номер", header=True)
    def display_estate_header(self, obj: Estate) -> Tuple[str, str]:
        """Возвращает заголовок борта/имущества и заводской номер.

        Args:
            obj: Экземпляр Estate.

        Returns:
            Кортеж (регистрационный номер, тип и заводской номер).
        """
        prop_type = obj.type_property.type_property if obj.type_property else "Имущество"
        factory = f"Зав.№ {obj.factory_number}" if obj.factory_number else ""
        return obj.registration_number or "Без номера", f"{prop_type} {factory}".strip()

    @display(description="Списано", boolean=True)
    def display_is_decommissioned(self, obj: Estate) -> bool:
        """Проверяет вывод из эксплуатации.

        Args:
            obj: Экземпляр Estate.

        Returns:
            True, если объект выведен из эксплуатации.
        """
        return obj.is_decommissioned


@admin.register(Posts)
class PostsAdmin(ModelAdmin):
    """Администрирование заметок к договорам."""
    list_display = ("pk", "contract_number", "responsible_person", "creation_date")
    search_fields = ("post_description", "contract_number__contract_number")
    list_filter = (
        "responsible_person",
        ("creation_date", RangeDateFilter),
    )
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(CompanyProperty)
class CompanyPropertyAdmin(ModelAdmin):
    """Администрирование архивных записей имущества."""
    list_display = ("pk", "name", "category")
    search_fields = ("name",)
    list_filter = ("category",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Contract)
class DocumentsOrderAdmin(ModelAdmin):
    """Администрирование договоров и соглашений компании."""
    list_display = (
        "display_contract_header",
        "date_conclusion",
        "type_of_contract",
        "type_of_document",
        "display_prolongation",
        "display_actuality",
        "display_allowed_placed",
    )
    autocomplete_fields = [
        "parent_category",
        "contract_counteragent",
        "type_of_contract",
        "type_of_document",
    ]
    list_filter = (
        "actuality",
        "allowed_placed",
        "type_of_contract",
        "type_of_document",
        ("date_conclusion", RangeDateFilter),
        ("closing_date", RangeDateFilter),
    )
    search_fields = [
        "contract_number",
        "contract_counteragent__short_name",
        "contract_counteragent__inn",
        "subject_contract",
    ]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Договор", header=True)
    def display_contract_header(self, obj: Contract) -> Tuple[str, str]:
        """Возвращает заголовок контракта и контрагента.

        Args:
            obj: Экземпляр Contract.

        Returns:
            Кортеж (номер договора, контрагент и краткий предмет).
        """
        counteragent_name = obj.contract_counteragent.short_name if obj.contract_counteragent else "Контрагент не указан"
        subj = f" | {obj.subject_contract[:35]}..." if obj.subject_contract else ""
        return f"№ {obj.contract_number or 'б/н'}", f"{counteragent_name}{subj}"

    @display(description="Актуален", boolean=True)
    def display_actuality(self, obj: Contract) -> bool:
        """Флаг актуальности договора."""
        return obj.actuality

    @display(description="Опубликован", boolean=True)
    def display_allowed_placed(self, obj: Contract) -> bool:
        """Флаг публикации договора на портале."""
        return obj.allowed_placed

    @display(
        description="Пролонгация",
        label={
            "auto": "info",
            "ag": "warning",
        },
    )
    def display_prolongation(self, obj: Contract) -> Optional[Tuple[str, str]]:
        """Возвращает тип пролонгации с бейджем.

        Args:
            obj: Экземпляр Contract.

        Returns:
            Кортеж (код, наименование) или None.
        """
        if obj.prolongation:
            return obj.prolongation, obj.get_prolongation_display()
        return None
