from django.contrib import admin
from contracts_app.models import TypeProperty, TypeContract, Estate, Contract, Posts, TypeDocuments, CompanyProperty

# Register your models here.
admin.site.register(TypeContract)
admin.site.register(TypeProperty)
admin.site.register(TypeDocuments)
admin.site.register(Estate)
admin.site.register(Posts)
# admin.site.register(Hotel)
admin.site.register(CompanyProperty)

@admin.register(Contract)
class DocumentsOrderAdmin(admin.ModelAdmin):
    list_display = ("pk", "contract_number", "date_conclusion", "type_of_document",
                    "type_of_contract", "actuality", "contract_counteragent")  #
    list_filter = (
        "actuality", "allowed_placed",
    )
    search_fields = ["contract_number",  "contract_counteragent__full_name",  "date_conclusion", ]
    # def get_document_order_type(self, obj: DocumentsOrder):
    #     return obj.get_document_order_type_display()
    #
    # def get_employee(self, obj: Provisions):
    #     s = [format_name_initials(item.title) for item in obj.employee.iterator()]
    #     return '; '.join(s)