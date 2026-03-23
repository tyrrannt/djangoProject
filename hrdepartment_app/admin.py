import datetime

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from administration_app.utils import format_name_initials
from customers_app.mixin import ActiveUsersFilterMixin
from customers_app.models import Groups
from hrdepartment_app.forms import OrderDescriptionForm
from hrdepartment_app.models import (
    Medical, Purpose, OfficialMemo, ApprovalOficialMemoProcess, BusinessProcessDirection,
    MedicalOrganisation, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity,
    ReportCard, ReasonForCancellation, OrderDescription, PreHolidayDay,
    WeekendDay, ProductionCalendar, TypesUserworktime, Instructions, Provisions,
    CreatingTeam, TimeSheet, OperationalWork, PeriodicWork, OutfitCard, DocumentAcknowledgment, Briefings, Operational,
    DataBaseUserEvent, LaborProtection, BusinessProcessRoutes, GuidanceDocuments, LaborProtectionInstructions,
    TrainingUnit, TrainingProgram, StudentAgreement,
)
from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(DocumentsJobDescription)
class DocumentsJobDescriptionAdmin(ModelAdmin):
    pass


@admin.register(Purpose)
class PurposeAdmin(ModelAdmin):
    pass


@admin.register(Groups)
class GroupsAdmin(ModelAdmin):
    pass


@admin.register(ReasonForCancellation)
class ReasonForCancellationAdmin(ModelAdmin):
    pass


@admin.register(TypesUserworktime)
class TypesUserworktimeAdmin(ModelAdmin):
    pass


@admin.register(Instructions)
class InstructionsAdmin(ModelAdmin):
    pass


@admin.register(LaborProtectionInstructions)
class LaborProtectionInstructionsAdmin(ModelAdmin):
    pass


@admin.register(DocumentAcknowledgment)
class DocumentAcknowledgmentAdmin(ModelAdmin):
    pass


@admin.register(DataBaseUserEvent)
class DataBaseUserEventAdmin(ModelAdmin):
    pass


class DateRangeFilter(SimpleListFilter):
    """Базовый фильтр по диапазону дат"""
    title = _('Период')
    parameter_name = 'date_range'
    date_field = None  # переопределяется в наследниках

    def lookups(self, request, model_admin):
        return (
            ('today', _('Сегодня')),
            ('week', _('За неделю')),
            ('month', _('За месяц')),
            ('quarter', _('За квартал')),
            ('year', _('За год')),
            ('custom', _('Произвольный период')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'today':
            return queryset.filter(**{f'{self.date_field}__date': datetime.date.today()})
        elif self.value() == 'week':
            week_ago = datetime.date.today() - datetime.timedelta(days=7)
            return queryset.filter(**{f'{self.date_field}__date__gte': week_ago})
        elif self.value() == 'month':
            month_ago = datetime.date.today() - datetime.timedelta(days=30)
            return queryset.filter(**{f'{self.date_field}__date__gte': month_ago})
        elif self.value() == 'quarter':
            quarter_ago = datetime.date.today() - datetime.timedelta(days=90)
            return queryset.filter(**{f'{self.date_field}__date__gte': quarter_ago})
        elif self.value() == 'year':
            year_ago = datetime.date.today() - datetime.timedelta(days=365)
            return queryset.filter(**{f'{self.date_field}__date__gte': year_ago})
        return queryset


class StartDateTripFilter(DateRangeFilter):
    """Фильтр по дате начала поездки"""
    title = _('Дата начала поездки')
    parameter_name = 'start_date_range'
    date_field = 'start_date_trip'


class EndDateTripFilter(DateRangeFilter):
    """Фильтр по дате окончания поездки"""
    title = _('Дата окончания поездки')
    parameter_name = 'end_date_range'
    date_field = 'end_date_trip'


class CreationDateFilter(DateRangeFilter):
    """Фильтр по дате создания"""
    title = _('Дата создания')
    parameter_name = 'creation_date_range'
    date_field = 'date_of_creation'


@admin.register(GuidanceDocuments)
class GuidanceDocumentsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]


@admin.register(TimeSheet)
class TimeSheetAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("date", "get_person", "time_sheets_place", "notes")
    list_filter = ("employee", "time_sheets_place")

    @admin.display(description="Ответственный")
    def get_person(self, obj: TimeSheet):
        try:
            return format_name_initials(obj.employee.title)
        except AttributeError:
            return ""


@admin.register(OutfitCard)
class OutfitCardAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("outfit_card_date", "outfit_card_number", "get_person", "outfit_card_place", "air_board")
    list_filter = ("air_board", "outfit_card_place", "employee",)
    search_fields = ["outfit_card_number"]

    @admin.display(description="Ответственный")
    def get_person(self, obj: OutfitCard):
        try:
            return format_name_initials(obj.employee.title)
        except AttributeError:
            return ""


@admin.register(Medical)
class MedicalAdmin(ModelAdmin):
    list_display = ("get_person", "get_inspection_view", "number", "date_of_inspection")  #

    def get_inspection_view(self, obj: Medical):
        return obj.get_type_inspection_display()

    def get_person(self, obj: Medical):
        return format_name_initials(obj.person.title)


@admin.register(MedicalOrganisation)
class MedicalOrganisationAdmin(ModelAdmin):
    list_display = ("description", "ogrn", "address", "email", "phone")  #
    search_fields = ["description"]


@admin.register(PlaceProductionActivity)
class PlaceProductionActivityAdmin(ModelAdmin):
    list_display = ("name", "address", "short_name", "use_team_orders", "additional_payment", "email")  #
    list_filter = (
        "use_team_orders",
    )
    search_fields = ["name", "short_name"]


@admin.register(ProductionCalendar)
class ProductionCalendarAdmin(ModelAdmin):
    list_display = ("calendar_month", "number_calendar_days", "number_working_days", "number_days_off_and_holidays",
                    "description")  #
    search_fields = ["calendar_month", ]


def copy_weekend_day(modeladmin, request, queryset):
    for weekend_day in queryset:
        weekend_day.pk = None  # Устанавливаем pk в None, чтобы создать новую запись
        weekend_day.save()


copy_weekend_day.short_description = "Копировать праздничный день"


@admin.register(WeekendDay)
class WeekendDayAdmin(ModelAdmin):
    list_display = ("weekend_day", "weekend_type", "description")  #
    list_filter = (
        "weekend_type",
    )
    search_fields = ["weekend_day", ]
    actions = [copy_weekend_day]


@admin.register(PreHolidayDay)
class PreHolidayDayAdmin(ModelAdmin):
    list_display = ("preholiday_day", "work_time")  #
    search_fields = ["preholiday_day", ]


@admin.register(DocumentsOrder)
class DocumentsOrderAdmin(ActiveUsersFilterMixin, ModelAdmin):
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
class ProvisionsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access", "get_employee",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]

    def get_employee(self, obj: Provisions):
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return '; '.join(s)


@admin.register(Briefings)
class BriefingsAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access", "get_employee",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]

    def get_employee(self, obj: Briefings):
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return '; '.join(s)


@admin.register(LaborProtection)
class LaborProtectionAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("document_name", "document_date", "document_number", "access", "get_employee",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]

    def get_employee(self, obj: LaborProtection):
        s = [format_name_initials(item.title) for item in obj.employee.iterator()]
        return '; '.join(s)


@admin.register(Operational)
class OperationalAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("document_name", "document_date", "document_number",
                    "validity_period_start", "validity_period_end")  #
    list_filter = (
        "actuality", "applying_for_job",
    )
    search_fields = ["document_name", ]


@admin.register(CreatingTeam)
class CreatingTeamAdmin(ActiveUsersFilterMixin, ModelAdmin):
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
class BusinessProcessDirectionAdmin(ActiveUsersFilterMixin, ModelAdmin):
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


@admin.register(BusinessProcessRoutes)
class BusinessProcessRoutesAdmin(ActiveUsersFilterMixin, ModelAdmin):
    # какие поля будут отображаться
    list_display = (
        "business_process_type", "get_person_executor", "get_person_agreement", "get_person_hr", "get_clerk",)  #

    def get_clerk(self, obj: BusinessProcessRoutes):
        s = [format_name_initials(item.title) for item in obj.person_clerk.iterator()]
        return '; '.join(s)

    get_clerk.short_description = "Делопроизводители"

    def get_person_executor(self, obj: BusinessProcessRoutes):
        s = [format_name_initials(item.title) for item in obj.person_executor.iterator()]
        return '; '.join(s)

    get_person_executor.short_description = "Исполнители"

    def get_person_agreement(self, obj: BusinessProcessRoutes):
        s = [format_name_initials(item.title) for item in obj.person_agreement.iterator()]
        return '; '.join(s)

    get_person_agreement.short_description = "Согласующие"

    def get_person_hr(self, obj: BusinessProcessRoutes):
        s = [format_name_initials(item.title) for item in obj.person_hr.iterator()]
        return '; '.join(s)

    get_person_hr.short_description = "Специалисты ОК"

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
class ReportCardAdmin(ActiveUsersFilterMixin, ModelAdmin):
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
class OfficialMemoAdmin(ActiveUsersFilterMixin, ModelAdmin):
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
class ApprovalOficialMemoProcessAdmin(ActiveUsersFilterMixin, ModelAdmin):
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
    list_display = (
        "document",
        "order",
        "email_send",
        "cancellation",
        "start_date_trip",
        "end_date_trip",
        "accepted_accounting",
    )
    # какие поля будут использоваться для поиска
    search_fields = (
        "document__title",
        "cancellation",
    )
    list_filter = (
        "cancellation",
        "accepted_accounting",
        "email_send",
        StartDateTripFilter,
        EndDateTripFilter,
        CreationDateFilter,
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
    list_select_related = ('order', 'document', 'reason_cancellation')

    # --- Переопределение save_model для пересчёта суммы ---

    def save_model(self, request, obj, form, change):
        # Пересчитываем сумму расходов при сохранении из админки
        if any(f in form.changed_data for f in [
            'daily_allowance', 'travel_expense',
            'accommodation_expense', 'other_expense'
        ]):
            obj.prepaid_expense_summ = (
                    obj.daily_allowance +
                    obj.travel_expense +
                    obj.accommodation_expense +
                    obj.other_expense
            )
        super().save_model(request, obj, form, change)

    # --- Оптимизация запросов ---

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            'document', 'order', 'reason_cancellation',
            'person_executor', 'person_agreement', 'person_accounting'
        )


@admin.register(OrderDescription)
class OrderDescriptionAdmin(ActiveUsersFilterMixin, ModelAdmin):
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


def copy_operational_work(modeladmin, request, queryset):
    for operational_work in queryset:
        operational_work.pk = None  # Устанавливаем pk в None, чтобы создать новую запись
        operational_work.save()


copy_operational_work.short_description = "Копировать выбранные оперативные работы"


@admin.register(OperationalWork)
class OperationalWorkAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("code", "name", "description", "air_bord_type",)  #
    list_filter = (
        "air_bord_type",
    )
    search_fields = ["name", 'code']
    actions = [copy_operational_work]


def copy_periodic_work(modeladmin, request, queryset):
    for periodic_work in queryset:
        periodic_work.pk = None  # Устанавливаем pk в None, чтобы создать новую запись
        periodic_work.save()


copy_periodic_work.short_description = "Копировать выбранные периодические работы"


@admin.register(PeriodicWork)
class PeriodicWorkAdmin(ActiveUsersFilterMixin, ModelAdmin):
    list_display = ("pk", "code", "name", "description", "air_bord_type", "ratio")  #
    list_filter = (
        "air_bord_type",
    )
    search_fields = ["name", "code"]
    actions = [copy_periodic_work]


@admin.register(TrainingProgram)
class TrainingProgramAdmin(ModelAdmin):
    search_fields = ["program_name", ]


@admin.register(TrainingUnit)
class TrainingUnitAdmin(ModelAdmin):
    search_fields = ["unit_name", ]


@admin.register(StudentAgreement)
class StudentAgreementAdmin(ModelAdmin):
    search_fields = ["student_agreement_number", ]
