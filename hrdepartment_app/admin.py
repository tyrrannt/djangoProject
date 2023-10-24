from django.contrib import admin

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
)

# Register your models here.

admin.site.register(DocumentsJobDescription)
admin.site.register(DocumentsOrder)
admin.site.register(PlaceProductionActivity)
admin.site.register(MedicalOrganisation)
admin.site.register(Medical)
admin.site.register(Purpose)
admin.site.register(OfficialMemo)
# admin.site.register(ApprovalOficialMemoProcess)
admin.site.register(BusinessProcessDirection)
admin.site.register(Groups)
admin.site.register(ReportCard)
admin.site.register(ReasonForCancellation)
# admin.site.register(OrderDescription)
admin.site.register(PreHolidayDay)
admin.site.register(WeekendDay)
admin.site.register(ProductionCalendar)
admin.site.register(TypesUserworktime)
admin.site.register(Instructions)
admin.site.register(Provisions)


@admin.register(ApprovalOficialMemoProcess)
class ApprovalOficialMemoProcessAdmin(admin.ModelAdmin):
    """
    Admin class for ApprovalOficialMemoProcess model.

    The ApprovalOficialMemoProcessAdmin class is responsible for managing the admin interface
    for the ApprovalOficialMemoProcess model. It provides customization for the list display,
    search fields, and list filter.

    Attributes:
        list_display (tuple): A tuple of fields to be displayed in the admin list view.
        search_fields (tuple): A tuple of fields to be used for searching in the admin interface.
        list_filter (tuple): A tuple of fields to be used for filtering the admin list view.

    """
    list_display = ("document", "order", "email_send", "cancellation")
    search_fields = (
        "document__title",
        "cancellation",
    )
    list_filter = (
        "cancellation",
        "accepted_accounting",
    )


@admin.register(OrderDescription)
class OrderDescriptionAdmin(admin.ModelAdmin):
    """
    The OrderDescriptionAdmin class is a Django ModelAdmin class used to manage the administration interface for the OrderDescription model.

    Attributes:
        form (Form): The form class used for creating and updating OrderDescription objects.
        list_display (tuple): The fields of the OrderDescription model to be displayed in the list view of the admin site.
        search_fields (tuple): The fields of the OrderDescription model to be searched in the admin site.
        list_filter (tuple): The fields of the OrderDescription model to be used as filters in the admin site.
        fieldsets (tuple): The fieldsets configuration for the OrderDescription model in the admin site.
        add_fieldsets (tuple): The fieldsets configuration for the OrderDescription model when creating a new object in the admin site.
        ordering (tuple): The field used to order the OrderDescription objects in the admin site.

    Methods:
        get_fieldsets(request, obj=None): Returns the fieldsets configuration for the OrderDescriptionAdmin class.

    """
    form = OrderDescriptionForm
    list_display = (
        "name",
        "affiliation",
    )
    search_fields = ("name",)
    list_filter = ("affiliation",)
    fieldsets = ((None, {"fields": ("name", "affiliation")}),)
    add_fieldsets = ((None, {"fields": ("name", "affiliation")}),)
    ordering = ("name",)

    def get_fieldsets(self, request, obj=None):
        """
        :param request: the HTTP request object
        :param obj: the OrderDescription object (optional)
        :return: the fieldsets list

        This method is used to dynamically determine the fieldsets configuration for the OrderDescriptionAdmin class in the Django admin site.

        If an obj is provided (an existing OrderDescription object), it will return the fieldsets defined in the OrderDescriptionAdmin class.

        If no obj is provided (when creating a new OrderDescription object), it will return the add_fieldsets defined in the OrderDescriptionAdmin class.
        """
        if obj:
            return self.fieldsets
        return self.add_fieldsets
