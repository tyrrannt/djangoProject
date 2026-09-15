from typing import Optional, Tuple, Any
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter

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
    """Инлайн отображение обязательств в договоре."""
    model = FinancialObligation
    extra = 0
    show_change_link = True
    fields = ("obligation_type", "cost", "date_origin", "date_execution", "status")


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    """Администрирование организаций (собственных юридических лиц)."""
    list_display = ("name", "inn", "kpp", "ogrn", "ref_key")
    search_fields = ("name", "inn", "ogrn")
    list_filter = ("name",)
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(ObligationType)
class ObligationTypeAdmin(ModelAdmin):
    """Администрирование типов финансовых обязательств."""
    list_display = ("name", "code")
    search_fields = ("name", "code")
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(FinancialContract)
class FinancialContractAdmin(ModelAdmin):
    """Администрирование финансовых договоров."""
    list_display = (
        "display_contract_header",
        "date_conclusion",
        "organization",
        "counteragent",
        "cost",
        "currency",
        "display_status",
    )
    search_fields = ("contract_number", "counteragent__short_name", "organization__name")
    list_filter = (
        "status",
        "organization",
        "currency",
        ("date_conclusion", RangeDateFilter),
    )
    autocomplete_fields = ["counteragent", "organization", "employee"]
    inlines = [FinancialObligationInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Договор", header=True)
    def display_contract_header(self, obj: FinancialContract) -> Tuple[str, str]:
        """Возвращает заголовок договора и краткую информацию.

        Args:
            obj: Экземпляр FinancialContract.

        Returns:
            Кортеж (номер договора, организация и контрагент).
        """
        counteragent_name = obj.counteragent.short_name if obj.counteragent else "-"
        org_name = obj.organization.name if obj.organization else "-"
        return f"№ {obj.contract_number}", f"{org_name} ↔ {counteragent_name}"

    @display(
        description="Статус",
        label={
            "active": "success",
            "completed": "info",
            "suspended": "warning",
            "terminated": "danger",
        },
    )
    def display_status(self, obj: FinancialContract) -> Tuple[str, str]:
        """Возвращает статус договора с бейджем.

        Args:
            obj: Экземпляр FinancialContract.

        Returns:
            Кортеж (ключ статуса, человекочитаемое наименование).
        """
        return obj.status, obj.get_status_display()


class PaymentScheduleInline(TabularInline):
    """Инлайн отображение графика плановых платежей."""
    model = PaymentSchedule
    extra = 0
    fields = ("payment_date", "amount", "status")


class PaymentFactInline(TabularInline):
    """Инлайн отображение фактов оплат."""
    model = PaymentFact
    extra = 0
    fields = ("payment_date", "amount", "payment_doc_number", "status")


@admin.register(FinancialObligation)
class FinancialObligationAdmin(ModelAdmin):
    """Администрирование финансовых обязательств."""
    list_display = (
        "display_obligation_header",
        "counteragent",
        "cost",
        "obligation_type",
        "date_origin",
        "date_execution",
        "display_status",
    )
    search_fields = ("contract__contract_number", "counteragent__short_name")
    list_filter = (
        "status",
        "obligation_type",
        ("date_execution", RangeDateFilter),
        ("date_origin", RangeDateFilter),
    )
    autocomplete_fields = ["contract", "counteragent", "obligation_type"]
    inlines = [PaymentScheduleInline, PaymentFactInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Обязательство", header=True)
    def display_obligation_header(self, obj: FinancialObligation) -> Tuple[str, str]:
        """Возвращает заголовок обязательства и номер связанного договора.

        Args:
            obj: Экземпляр FinancialObligation.

        Returns:
            Кортеж (тип обязательства, номер договора).
        """
        contract_num = obj.contract.contract_number if obj.contract else "-"
        type_name = obj.obligation_type.name if obj.obligation_type else "Обязательство"
        return type_name, f"Договор № {contract_num}"

    @display(
        description="Статус",
        label={
            "active": "success",
            "planned": "info",
            "completed": "success",
            "overdue": "danger",
        },
    )
    def display_status(self, obj: FinancialObligation) -> Tuple[str, str]:
        """Возвращает статус обязательства с бейджем.

        Args:
            obj: Экземпляр FinancialObligation.

        Returns:
            Кортеж (ключ статуса, человекочитаемое наименование).
        """
        return obj.status, obj.get_status_display()


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(ModelAdmin):
    """Администрирование плановых платежей."""
    list_display = ("obligation", "payment_date", "amount", "display_status")
    list_filter = (
        "status",
        ("payment_date", RangeDateFilter),
    )
    search_fields = ("obligation__contract__contract_number",)
    autocomplete_fields = ["obligation"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Статус оплаты",
        label={
            "paid": "success",
            "partially_paid": "warning",
            "planned": "info",
            "overdue": "danger",
        },
    )
    def display_status(self, obj: PaymentSchedule) -> Tuple[str, str]:
        """Возвращает статус планового платежа с бейджем.

        Args:
            obj: Экземпляр PaymentSchedule.

        Returns:
            Кортеж (ключ статуса, человекочитаемое наименование).
        """
        return obj.status, obj.get_status_display()


@admin.register(PaymentFact)
class PaymentFactAdmin(ModelAdmin):
    """Администрирование фактических платежей."""
    list_display = ("obligation", "payment_date", "amount", "payment_doc_number", "display_status")
    list_filter = (
        "status",
        ("payment_date", RangeDateFilter),
    )
    search_fields = ("obligation__contract__contract_number", "payment_doc_number")
    autocomplete_fields = ["obligation"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Вид операции",
        label={
            "in": "success",
            "out": "warning",
        },
    )
    def display_status(self, obj: PaymentFact) -> Optional[Tuple[str, str]]:
        """Возвращает вид операции с бейджем.

        Args:
            obj: Экземпляр PaymentFact.

        Returns:
            Кортеж (ключ, наименование) или None.
        """
        if obj.status:
            return obj.status, obj.get_status_display()
        return None


@admin.register(DebtSnapshot)
class DebtSnapshotAdmin(ModelAdmin):
    """Администрирование снимков задолженности."""
    list_display = (
        "contract",
        "snapshot_date",
        "debt_amount",
        "overdue_debt_amount",
        "days_overdue",
    )
    list_filter = (
        ("snapshot_date", RangeDateFilter),
    )
    search_fields = ("contract__contract_number",)
    autocomplete_fields = ["contract"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    """Администрирование уведомлений."""
    list_display = ("user", "message", "display_channel", "sent", "read", "created_at")
    list_filter = (
        "channel",
        "sent",
        "read",
        ("created_at", RangeDateFilter),
    )
    search_fields = ("user__username", "message")
    autocomplete_fields = ["user"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Канал",
        label={
            "portal": "info",
            "email": "warning",
            "telegram": "primary",
        },
    )
    def display_channel(self, obj: Notification) -> Tuple[str, str]:
        """Возвращает канал уведомления с бейджем.

        Args:
            obj: Экземпляр Notification.

        Returns:
            Кортеж (код канала, наименование).
        """
        return obj.channel, obj.get_channel_display()


@admin.register(SyncLog)
class SyncLogAdmin(ModelAdmin):
    """Администрирование журнала синхронизации."""
    list_display = ("object_name", "timestamp", "records_count", "duration", "display_status")
    list_filter = (
        "status",
        ("timestamp", RangeDateFilter),
        "object_name",
    )
    readonly_fields = ("timestamp", "object_name", "records_count", "duration", "status", "errors")
    compressed_fields = True

    def has_add_permission(self, request) -> bool:
        return False

    @display(
        description="Статус",
        label={
            "success": "success",
            "error": "danger",
        },
    )
    def display_status(self, obj: SyncLog) -> Tuple[str, str]:
        """Возвращает статус синхронизации с бейджем.

        Args:
            obj: Экземпляр SyncLog.

        Returns:
            Кортеж (код статуса, наименование).
        """
        return obj.status, obj.get_status_display()


class CreditPaymentScheduleInline(TabularInline):
    """Инлайн отображение графиков оплат по кредитам."""
    model = CreditPaymentSchedule
    extra = 0
    fields = ("payment_date", "principal", "interest", "total_amount", "status")


class CreditPaymentFactInline(TabularInline):
    """Инлайн отображение фактов оплат по кредитам."""
    model = CreditPaymentFact
    extra = 0
    fields = ("payment_date", "amount", "payment_type", "payment_doc_number")


@admin.register(CreditAgreement)
class CreditAgreementAdmin(ModelAdmin):
    """Администрирование кредитных договоров."""
    list_display = (
        "display_credit_header",
        "contract_date",
        "bank",
        "amount",
        "interest_rate",
        "credit_end_date",
        "remaining_debt",
    )
    search_fields = ("contract_number", "bank__short_name")
    list_filter = (
        ("contract_date", RangeDateFilter),
        ("credit_end_date", RangeDateFilter),
        "bank",
    )
    autocomplete_fields = ["bank"]
    inlines = [CreditPaymentScheduleInline, CreditPaymentFactInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Кредитный договор", header=True)
    def display_credit_header(self, obj: CreditAgreement) -> Tuple[str, str]:
        """Возвращает заголовок кредитного договора и сумму.

        Args:
            obj: Экземпляр CreditAgreement.

        Returns:
            Кортеж (номер кредита, банк и сумма).
        """
        bank_name = obj.bank.short_name if obj.bank else "-"
        return f"Кредит № {obj.contract_number}", f"{bank_name} | {obj.amount:,.2f} ₽"


@admin.register(CreditPaymentSchedule)
class CreditPaymentScheduleAdmin(ModelAdmin):
    """Администрирование графиков оплат кредитов."""
    list_display = ("credit_agreement", "payment_date", "principal", "interest", "total_amount", "display_status")
    list_filter = (
        "status",
        ("payment_date", RangeDateFilter),
    )
    search_fields = ("credit_agreement__contract_number",)
    autocomplete_fields = ["credit_agreement"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Статус оплаты",
        label={
            "paid": "success",
            "partially_paid": "warning",
            "planned": "info",
            "overdue": "danger",
        },
    )
    def display_status(self, obj: CreditPaymentSchedule) -> Tuple[str, str]:
        """Возвращает статус платежа с бейджем.

        Args:
            obj: Экземпляр CreditPaymentSchedule.

        Returns:
            Кортеж (код статуса, наименование).
        """
        return obj.status, obj.get_status_display()


@admin.register(CreditPaymentFact)
class CreditPaymentFactAdmin(ModelAdmin):
    """Администрирование фактических платежей по кредитам."""
    list_display = ("credit_agreement", "payment_date", "amount", "display_payment_type", "payment_doc_number")
    list_filter = (
        "payment_type",
        ("payment_date", RangeDateFilter),
    )
    search_fields = ("credit_agreement__contract_number", "payment_doc_number")
    autocomplete_fields = ["credit_agreement", "schedule"]
    compressed_fields = True
    warn_unsaved_form = True

    @display(
        description="Тип платежа",
        label={
            "principal": "info",
            "interest": "warning",
        },
    )
    def display_payment_type(self, obj: CreditPaymentFact) -> Tuple[str, str]:
        """Возвращает тип платежа с бейджем.

        Args:
            obj: Экземпляр CreditPaymentFact.

        Returns:
            Кортеж (код типа, наименование).
        """
        return obj.payment_type, obj.get_payment_type_display()


@admin.register(FinanceAuditLog)
class FinanceAuditLogAdmin(ModelAdmin):
    """Администрирование журнала финансового аудита."""
    list_display = ("action", "content_type", "object_id", "field_name", "user", "timestamp")
    list_filter = (
        "action",
        ("timestamp", RangeDateFilter),
    )
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
    compressed_fields = True

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(UserNotificationSetting)
class UserNotificationSettingAdmin(ModelAdmin):
    """Администрирование настроек уведомлений пользователей."""
    list_display = ("user", "portal_enabled", "email_enabled", "telegram_enabled")
    search_fields = ("user__username", "user__last_name", "user__first_name")
    autocomplete_fields = ["user"]
    compressed_fields = True
    warn_unsaved_form = True
