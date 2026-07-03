from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from finance_app.models import (
    Organization,
    ObligationType,
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    Notification,
    SyncLog,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
    FinanceAuditLog,
    UserNotificationSetting,
)


class FinancialObligationInline(TabularInline):
    """
    Инлайн отображение обязательств в договоре.
    """
    model = FinancialObligation
    extra = 0
    show_change_link = True


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    """
    Администрирование организаций.
    """
    list_display = ("name", "inn", "kpp", "ogrn", "ref_key")
    search_fields = ("name", "inn")
    list_filter = ("name",)


@admin.register(ObligationType)
class ObligationTypeAdmin(ModelAdmin):
    """
    Администрирование типов обязательств.
    """
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(FinancialContract)
class FinancialContractAdmin(ModelAdmin):
    """
    Администрирование финансовых договоров.
    """
    list_display = (
        "contract_number",
        "date_conclusion",
        "organization",
        "counteragent",
        "cost",
        "currency",
        "status",
    )
    search_fields = ("contract_number", "counteragent__short_name", "organization__name")
    list_filter = ("status", "organization", "currency")
    inlines = [FinancialObligationInline]


class PaymentScheduleInline(TabularInline):
    """
    Инлайн отображение графика платежей.
    """
    model = PaymentSchedule
    extra = 0


class PaymentFactInline(TabularInline):
    """
    Инлайн отображение фактов оплат.
    """
    model = PaymentFact
    extra = 0


@admin.register(FinancialObligation)
class FinancialObligationAdmin(ModelAdmin):
    """
    Администрирование финансовых обязательств.
    """
    list_display = (
        "contract",
        "counteragent",
        "cost",
        "obligation_type",
        "date_origin",
        "date_execution",
        "status",
    )
    search_fields = ("contract__contract_number", "counteragent__short_name")
    list_filter = ("status", "obligation_type", "date_execution")
    inlines = [PaymentScheduleInline, PaymentFactInline]


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(ModelAdmin):
    """
    Администрирование плановых платежей.
    """
    list_display = ("obligation", "payment_date", "amount", "status")
    list_filter = ("status", "payment_date")
    search_fields = ("obligation__contract__contract_number",)


@admin.register(PaymentFact)
class PaymentFactAdmin(ModelAdmin):
    """
    Администрирование фактических платежей.
    """
    list_display = ("obligation", "payment_date", "amount", "payment_doc_number")
    list_filter = ("payment_date",)
    search_fields = ("obligation__contract__contract_number", "payment_doc_number")


@admin.register(DebtSnapshot)
class DebtSnapshotAdmin(ModelAdmin):
    """
    Администрирование снимков задолженности.
    """
    list_display = (
        "contract",
        "snapshot_date",
        "debt_amount",
        "overdue_debt_amount",
        "days_overdue",
    )
    list_filter = ("snapshot_date", "days_overdue")
    search_fields = ("contract__contract_number",)


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    """
    Администрирование уведомлений.
    """
    list_display = ("user", "message", "channel", "sent", "read", "created_at")
    list_filter = ("channel", "sent", "read", "created_at")
    search_fields = ("user__username", "message")


@admin.register(SyncLog)
class SyncLogAdmin(ModelAdmin):
    """
    Администрирование журнала синхронизации.
    """
    list_display = ("object_name", "timestamp", "records_count", "duration", "status")
    list_filter = ("status", "timestamp", "object_name")
    readonly_fields = ("timestamp", "object_name", "records_count", "duration", "status", "errors")

    def has_add_permission(self, request) -> bool:
        return False


class CreditPaymentScheduleInline(TabularInline):
    """
    Инлайн отображение графиков оплат по кредитам.
    """
    model = CreditPaymentSchedule
    extra = 0


class CreditPaymentFactInline(TabularInline):
    """
    Инлайн отображение фактов оплат по кредитам.
    """
    model = CreditPaymentFact
    extra = 0


@admin.register(CreditAgreement)
class CreditAgreementAdmin(ModelAdmin):
    """
    Администрирование кредитных договоров.
    """
    list_display = (
        "contract_number",
        "contract_date",
        "bank",
        "amount",
        "interest_rate",
        "term_months",
        "tranche_repayment_days",
        "remaining_debt",
    )
    search_fields = ("contract_number", "bank__short_name")
    list_filter = ("contract_date", "bank")
    inlines = [CreditPaymentScheduleInline, CreditPaymentFactInline]


@admin.register(CreditPaymentSchedule)
class CreditPaymentScheduleAdmin(ModelAdmin):
    """
    Администрирование графиков оплат кредитов.
    """
    list_display = ("credit_agreement", "payment_date", "total_amount", "status")
    list_filter = ("status", "payment_date")
    search_fields = ("credit_agreement__contract_number",)


@admin.register(CreditPaymentFact)
class CreditPaymentFactAdmin(ModelAdmin):
    """
    Администрирование фактических платежей по кредитам.
    """
    list_display = ("credit_agreement", "payment_date", "amount", "payment_doc_number")
    list_filter = ("payment_date",)
    search_fields = ("credit_agreement__contract_number", "payment_doc_number")


@admin.register(FinanceAuditLog)
class FinanceAuditLogAdmin(ModelAdmin):
    """
    Администрирование журнала аудита.
    """
    list_display = ("action", "content_type", "object_id", "field_name", "user", "timestamp")
    list_filter = ("action", "content_type", "timestamp")
    search_fields = ("user__username", "field_name")
    readonly_fields = (
        "user",
        "timestamp",
        "content_type",
        "object_id",
        "field_name",
        "old_value",
        "new_value",
        "action",
    )

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(UserNotificationSetting)
class UserNotificationSettingAdmin(ModelAdmin):
    """
    Администрирование настроек уведомлений.
    """
    list_display = ("user", "portal_enabled", "email_enabled", "telegram_enabled")
    search_fields = ("user__username",)
