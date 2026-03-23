from django.contrib import admin
from contracts_app.models import TypeProperty, TypeContract, Estate, Contract, Posts, TypeDocuments, CompanyProperty
from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(TypeContract)
class TypeContractAdmin(ModelAdmin):
    pass


@admin.register(TypeProperty)
class TypePropertyAdmin(ModelAdmin):
    pass


@admin.register(TypeDocuments)
class TypeDocumentsAdmin(ModelAdmin):
    pass


@admin.register(Estate)
class EstateAdmin(ModelAdmin):
    pass


@admin.register(Posts)
class PostsAdmin(ModelAdmin):
    pass


@admin.register(CompanyProperty)
class CompanyPropertyAdmin(ModelAdmin):
    pass


@admin.register(Contract)
class DocumentsOrderAdmin(ModelAdmin):
    list_display = ("pk", "parent_category", "contract_number", "date_conclusion", "type_of_document",
                    "type_of_contract", "actuality", "contract_counteragent")  #
    autocomplete_fields = ['parent_category', 'contract_counteragent']  # Добавляем автопоиск
    list_filter = (
        "actuality", "allowed_placed",
    )
    search_fields = ["contract_number", "contract_counteragent__full_name", "date_conclusion", ]
