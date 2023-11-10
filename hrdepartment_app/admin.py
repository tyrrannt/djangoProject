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
    Класс администратора для модели ApprovalOficialMemoProcess.

    Класс ApprovalOficialMemoProcessAdmin отвечает за управление интерфейсом администратора.
    для модели ApprovalOficialMemoProcess. Он обеспечивает настройку отображения списка,
    поля поиска и фильтр списка.

    Атрибуты:
        list_display (кортеж): кортеж полей, которые будут отображаться в представлении списка администратора.
        search_fields (кортеж): кортеж полей, которые будут использоваться для поиска в интерфейсе администратора.
        list_filter (кортеж): кортеж полей, которые будут использоваться для фильтрации представления списка администраторов.

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
    Класс OrderDescriptionAdmin — это класс Django ModelAdmin, используемый для управления интерфейсом администрирования модели OrderDescription.

    Атрибуты:
        form (Form): класс формы, используемый для создания и обновления объектов OrderDescription.
        list_display (tuple): поля модели OrderDescription, которые будут отображаться в виде списка на сайте администрирования.
        search_fields (кортеж): поля модели OrderDescription, по которым осуществляется поиск на сайте администрирования.
        list_filter (кортеж): поля модели OrderDescription, которые будут использоваться в качестве фильтров на сайте администрирования.
        наборы полей (кортеж): конфигурация наборов полей для модели OrderDescription на сайте администрирования.
        add_fieldsets (кортеж): конфигурация наборов полей для модели OrderDescription при создании нового объекта на сайте администрирования.
        заказ (кортеж): поле, используемое для упорядочивания объектов OrderDescription на сайте администрирования.

    Методы:
        get_fieldsets(request, obj=None): возвращает конфигурацию наборов полей для класса OrderDescriptionAdmin.

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
