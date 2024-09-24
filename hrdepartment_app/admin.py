from django.contrib import admin

from administration_app.utils import format_name_initials
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
    CreatingTeam, TimeSheet, OperationalWork, PeriodicWork,
)

# Register your models here.

admin.site.register(DocumentsJobDescription)
admin.site.register(Purpose)

admin.site.register(Groups)
admin.site.register(ReasonForCancellation)
admin.site.register(TypesUserworktime)
admin.site.register(Instructions)



@admin.register(TimeSheet)
class TimeSheetAdmin(admin.ModelAdmin):
    list_display = ("date", "get_person", "time_sheets_place", "notes")
    list_filter = ("employee", "time_sheets_place")

    @admin.display(description="Ответственный")
    def get_person(self, obj: TimeSheet):
        try:
            return format_name_initials(obj.employee.title)
        except AttributeError:
            return ""



@admin.register(Medical)
class MedicalAdmin(admin.ModelAdmin):
    list_display = ("get_person", "get_inspection_view", "number", "date_of_inspection")  #

    def get_inspection_view(self, obj: Medical):
        return obj.get_type_inspection_display()

    def get_person(self, obj: Medical):
        return format_name_initials(obj.person.title)

@admin.register(MedicalOrganisation)
class MedicalOrganisationAdmin(admin.ModelAdmin):
    list_display = ("description", "ogrn", "address", "email", "phone")  #
    search_fields = ["description"]


@admin.register(PlaceProductionActivity)
class PlaceProductionActivityAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "short_name", "use_team_orders", "additional_payment", "email")  #
    list_filter = (
        "use_team_orders",
    )
    search_fields = ["name", "short_name"]


@admin.register(ProductionCalendar)
class ProductionCalendarAdmin(admin.ModelAdmin):
    list_display = ("calendar_month", "number_calendar_days", "number_working_days", "number_days_off_and_holidays",
                    "description")  #
    search_fields = ["calendar_month", ]


@admin.register(WeekendDay)
class WeekendDayAdmin(admin.ModelAdmin):
    list_display = ("weekend_day", "weekend_type", "description")  #
    list_filter = (
        "weekend_type",
    )
    search_fields = ["weekend_day", ]


@admin.register(PreHolidayDay)
class PreHolidayDayAdmin(admin.ModelAdmin):
    list_display = ("preholiday_day", "work_time")  #
    search_fields = ["preholiday_day", ]


@admin.register(DocumentsOrder)
class DocumentsOrderAdmin(admin.ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access", "get_employee",
                    "validity_period_start", "get_document_order_type")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]

    def get_document_order_type(self, obj: DocumentsOrder):
        return obj.get_document_order_type_display()

    def get_employee(self, obj: DocumentsOrder):
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return '; '.join(s)


@admin.register(Provisions)
class ProvisionsAdmin(admin.ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access", "get_employee",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]

    def get_employee(self, obj: Provisions):
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return '; '.join(s)


@admin.register(CreatingTeam)
class CreatingTeamAdmin(admin.ModelAdmin):
    list_display = ("get_document_type", "date_create", "number", "senior_brigade", "get_team_brigade",
                    "place", "date_start", "date_end", "agreed", "email_send")  #
    list_filter = (
        "agreed", "email_send",
    )
    search_fields = ["senior_brigade__title", ]

    def get_document_type(self, obj: CreatingTeam):
        return obj.get_document_type_display()

    def get_team_brigade(self, obj: CreatingTeam):
        s = [format_name_initials(item.title) for item in obj.team_brigade.iterator()]
        return '; '.join(s)


@admin.register(BusinessProcessDirection)
class BusinessProcessDirectionAdmin(admin.ModelAdmin):
    # какие поля будут отображаться
    list_display = (
        "business_process_type", "get_person_executor", "get_person_agreement", "get_person_hr", "get_clerk",)  #

    def get_clerk(self, obj: BusinessProcessDirection):
        s = [item.name for item in obj.clerk.iterator()]
        return '; '.join(s)

    def get_person_executor(self, obj: BusinessProcessDirection):
        s = [item.name for item in obj.person_executor.iterator()]
        return '; '.join(s)

    def get_person_agreement(self, obj: BusinessProcessDirection):
        s = [item.name for item in obj.person_agreement.iterator()]
        return '; '.join(s)

    def get_person_hr(self, obj: BusinessProcessDirection):
        s = [item.name for item in obj.person_hr.iterator()]
        return '; '.join(s)

    # какие поля будут использоваться для поиска
    # search_fields = ["employee__title", ]
    # какие поля будут использоваться для фильтрации
    list_filter = (
        "business_process_type",
    )
    # какие поля будут в виде ссылок
    # list_display_links = ("business_process_type", )
    # какие поля будут использоваться для сортировки
    ordering = ['business_process_type', ]
    # какие поля будут отображаться в списке
    # list_editable = ("type_trip", "cancellation")
    # сколько строк будут использоваться для постраничного отображения
    list_per_page = 100
    # показывать ли пустые значения
    empty_value_display = '-empty-'
    # какие поля будут использоваться из других моделей, для уменьшения запросов
    # list_select_related = ("person_executor", "person_agreement", "clerk", "person_hr" )


@admin.register(ReportCard)
class ReportCardAdmin(admin.ModelAdmin):
    # какие поля будут отображаться
    list_display = ("report_card_day", "employee", "record_type", "start_time", "end_time")
    # какие поля будут использоваться для поиска
    search_fields = ["employee__title", ]
    # какие поля будут использоваться для фильтрации
    list_filter = (
        "report_card_day",
        "employee",
        "record_type",
    )
    # какие поля будут в виде ссылок
    list_display_links = ("employee", "record_type")
    # какие поля будут использоваться для сортировки
    ordering = ['-report_card_day', ]
    # какие поля будут отображаться в списке
    # list_editable = ("type_trip", "cancellation")
    # сколько строк будут использоваться для постраничного отображения
    list_per_page = 100
    # показывать ли пустые значения
    empty_value_display = '-empty-'
    # какие поля будут использоваться из других моделей, для уменьшения запросов
    list_select_related = ('employee',)


@admin.register(OfficialMemo)
class OfficialMemoAdmin(admin.ModelAdmin):
    """
    Класс администратора для модели OfficialMemo.

    Класс OfficialMemoAdmin отвечает за управление интерфейсом администратора.
    для модели OfficialMemo. Он обеспечивает настройку отображения списка,
    поля поиска и фильтр списка.

    Атрибуты:
        list_display (кортеж): кортеж полей, которые будут отображаться в представлении списка администратора.
        search_fields (кортеж): кортеж полей, которые будут использоваться для поиска в интерфейсе администратора.
        list_filter (кортеж): кортеж полей, которые будут использоваться для фильтрации представления списка администраторов.

    """
    # какие поля будут отображаться
    list_display = ("person", "type_trip", "period_from", "period_for", "cancellation")
    # какие поля будут использоваться для поиска
    search_fields = ["title", ]
    # какие поля будут использоваться для фильтрации
    list_filter = (
        "purpose_trip",
        "type_trip",
    )
    # какие поля будут в виде ссылок
    list_display_links = ("person",)
    # какие поля будут использоваться для сортировки
    ordering = ['-period_from', 'person', 'type_trip']
    # какие поля будут отображаться в списке
    list_editable = ("type_trip", "cancellation")
    # сколько строк будут использоваться для постраничного отображения
    list_per_page = 100
    # показывать ли пустые значения
    empty_value_display = '-empty-'
    # какие поля будут использоваться из других моделей, для уменьшения запросов
    list_select_related = ('person', 'purpose_trip')


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
    # какие поля будут использоваться для поиска
    search_fields = (
        "document__title",
        "cancellation",
    )
    list_filter = (
        "cancellation",
        "accepted_accounting",
    )
    # какие поля будут в виде ссылок
    list_display_links = ("document",)
    # # какие поля будут использоваться для сортировки
    ordering = ['-start_date_trip', 'document__person']
    # какие поля будут отображаться в списке
    list_editable = ("email_send", "cancellation")
    # сколько строк будут использоваться для постраничного отображения
    list_per_page = 100
    # показывать ли пустые значения
    empty_value_display = '-empty-'
    # какие поля будут использоваться из других моделей, для уменьшения запросов
    list_select_related = ('order',)


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

@admin.register(OperationalWork)
class OperationalWorkAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "description", "air_bord_type", )  #
    list_filter = (
        "air_bord_type",
    )
    search_fields = ["name", 'code']


def copy_periodic_work(modeladmin, request, queryset):
    for periodic_work in queryset:
        periodic_work.pk = None  # Устанавливаем pk в None, чтобы создать новую запись
        periodic_work.save()

copy_periodic_work.short_description = "Копировать выбранные табели"

@admin.register(PeriodicWork)
class PeriodicWorkAdmin(admin.ModelAdmin):
    list_display = ("pk", "code", "name", "description", "air_bord_type", "ratio")  #
    list_filter = (
        "air_bord_type",
    )
    search_fields = ["name", "code"]
    actions = [copy_periodic_work]