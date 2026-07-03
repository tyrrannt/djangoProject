from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from customers_app.models import Counteragent

class Organization(models.Model):
    """
    Модель организации (наше юридическое лицо).
    """
    name = models.CharField(verbose_name="Наименование", max_length=400)
    inn = models.CharField(verbose_name="ИНН", max_length=12, db_index=True)
    kpp = models.CharField(verbose_name="КПП", max_length=9, blank=True, default="")
    ogrn = models.CharField(verbose_name="ОГРН", max_length=15, blank=True, default="")
    juridical_address = models.TextField(verbose_name="Юридический адрес", blank=True, default="")
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ObligationType(models.Model):
    """
    Модель типа финансового обязательства.
    """
    name = models.CharField(verbose_name="Наименование", max_length=100)
    code = models.CharField(verbose_name="Код", max_length=50, unique=True)

    class Meta:
        verbose_name = "Тип обязательства"
        verbose_name_plural = "Типы обязательств"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FinancialContract(models.Model):
    """
    Универсальная модель договора.
    """
    STATUS_CHOICES = [
        ("active", "Активный"),
        ("completed", "Завершен"),
        ("suspended", "Приостановлен"),
        ("terminated", "Расторгнут"),
    ]

    contract_number = models.CharField(verbose_name="Номер договора", max_length=100)
    date_conclusion = models.DateField(verbose_name="Дата договора")
    counteragent = models.ForeignKey(
        Counteragent,
        verbose_name="Контрагент",
        related_name="financial_contracts",
        on_delete=models.CASCADE
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="Организация",
        related_name="financial_contracts",
        on_delete=models.CASCADE
    )
    cost = models.DecimalField(
        verbose_name="Сумма договора",
        max_digits=15,
        decimal_places=2,
        default=0.00
    )
    currency = models.CharField(verbose_name="Валюта", max_length=3, default="RUB")
    start_date = models.DateField(verbose_name="Дата начала", null=True, blank=True)
    end_date = models.DateField(verbose_name="Дата окончания", null=True, blank=True)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Ответственный сотрудник",
        related_name="responsible_financial_contracts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    status = models.CharField(
        verbose_name="Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Финансовый договор"
        verbose_name_plural = "Финансовые договоры"
        ordering = ["-date_conclusion"]

    def __str__(self) -> str:
        return f"№ {self.contract_number} от {self.date_conclusion} ({self.counteragent.short_name})"


class FinancialObligation(models.Model):
    """
    Финансовое обязательство.
    """
    STATUS_CHOICES = [
        ("planned", "Запланировано"),
        ("active", "Активно"),
        ("completed", "Исполнено"),
        ("overdue", "Просрочено"),
    ]

    contract = models.ForeignKey(
        FinancialContract,
        verbose_name="Договор",
        related_name="obligations",
        on_delete=models.CASCADE
    )
    counteragent = models.ForeignKey(
        Counteragent,
        verbose_name="Контрагент",
        related_name="financial_obligations",
        on_delete=models.CASCADE
    )
    cost = models.DecimalField(verbose_name="Сумма обязательства", max_digits=15, decimal_places=2)
    date_origin = models.DateField(verbose_name="Дата возникновения")
    date_execution = models.DateField(verbose_name="Дата исполнения")
    obligation_type = models.ForeignKey(
        ObligationType,
        verbose_name="Тип обязательства",
        related_name="obligations",
        on_delete=models.PROTECT
    )
    status = models.CharField(
        verbose_name="Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Финансовое обязательство"
        verbose_name_plural = "Финансовые обязательства"
        ordering = ["-date_execution"]

    def __str__(self) -> str:
        return f"{self.obligation_type.name} по договору {self.contract.contract_number} на сумму {self.cost}"


class PaymentSchedule(models.Model):
    """
    Плановые платежи.
    """
    STATUS_CHOICES = [
        ("planned", "Запланирован"),
        ("partially_paid", "Частично оплачен"),
        ("paid", "Оплачен"),
        ("overdue", "Просрочен"),
    ]

    obligation = models.ForeignKey(
        FinancialObligation,
        verbose_name="Обязательство",
        related_name="payment_schedules",
        on_delete=models.CASCADE
    )
    payment_date = models.DateField(verbose_name="Дата платежа")
    amount = models.DecimalField(verbose_name="Сумма платежа", max_digits=15, decimal_places=2)
    status = models.CharField(
        verbose_name="Статус оплаты",
        max_length=20,
        choices=STATUS_CHOICES,
        default="planned"
    )

    class Meta:
        verbose_name = "Плановый платеж"
        verbose_name_plural = "Плановые платежи"
        ordering = ["payment_date"]

    def __str__(self) -> str:
        return f"Платеж на {self.amount} от {self.payment_date} ({self.get_status_display()})"


class PaymentFact(models.Model):
    """
    Фактические платежи из 1С.
    """
    STATUS_CHOICES = [
        ("in", "Поступление"),
        ("out", "Списание"),
    ]
    obligation = models.ForeignKey(
        FinancialObligation,
        verbose_name="Обязательство",
        related_name="payment_facts",
        on_delete=models.CASCADE
    )
    payment_date = models.DateField(verbose_name="Дата платежа")
    amount = models.DecimalField(verbose_name="Сумма платежа", max_digits=15, decimal_places=2)
    payment_doc_number = models.CharField(verbose_name="Номер платежного документа", max_length=100, blank=True, default="")
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)
    status = models.CharField(
        verbose_name="Вид операции",
        max_length=20,
        choices=STATUS_CHOICES,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Фактический платеж"
        verbose_name_plural = "Фактические платежи"
        ordering = ["-payment_date"]

    def __str__(self) -> str:
        return f"Факт оплаты на {self.amount} от {self.payment_date} (Док. №{self.payment_doc_number})"


class DebtSnapshot(models.Model):
    """
    Снимок задолженности на дату.
    """
    contract = models.ForeignKey(
        FinancialContract,
        verbose_name="Договор",
        related_name="debt_snapshots",
        on_delete=models.CASCADE
    )
    snapshot_date = models.DateField(verbose_name="Дата снимка")
    debt_amount = models.DecimalField(verbose_name="Сумма задолженности", max_digits=15, decimal_places=2, default=0.00)
    overdue_debt_amount = models.DecimalField(verbose_name="Сумма просроченной задолженности", max_digits=15, decimal_places=2, default=0.00)
    days_overdue = models.IntegerField(verbose_name="Количество дней просрочки", default=0)

    class Meta:
        verbose_name = "Снимок задолженности"
        verbose_name_plural = "Снимки задолженности"
        ordering = ["-snapshot_date"]

    def __str__(self) -> str:
        return f"Задолженность по договору {self.contract.contract_number} на {self.snapshot_date}"


class Notification(models.Model):
    """
    Уведомления пользователям.
    """
    CHANNEL_CHOICES = [
        ("portal", "Внутреннее уведомление портала"),
        ("email", "Email"),
        ("telegram", "Telegram"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        related_name="financial_notifications",
        on_delete=models.CASCADE
    )
    message = models.TextField(verbose_name="Текст уведомления")
    created_at = models.DateTimeField(verbose_name="Дата и время создания", auto_now_add=True)
    channel = models.CharField(
        verbose_name="Канал уведомлений",
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="portal"
    )
    sent = models.BooleanField(verbose_name="Отправлено", default=False)
    read = models.BooleanField(verbose_name="Прочитано", default=False)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Уведомление для {self.user.username} ({self.channel})"


class SyncLog(models.Model):
    """
    Журнал синхронизации с 1С.
    """
    STATUS_CHOICES = [
        ("success", "Успех"),
        ("error", "Ошибка"),
    ]

    timestamp = models.DateTimeField(verbose_name="Дата и время выполнения", auto_now_add=True)
    object_name = models.CharField(verbose_name="Объект обмена", max_length=100)
    records_count = models.IntegerField(verbose_name="Количество полученных записей", default=0)
    duration = models.FloatField(verbose_name="Длительность выполнения (сек)")
    status = models.CharField(
        verbose_name="Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default="success"
    )
    errors = models.TextField(verbose_name="Ошибки", blank=True, default="")

    class Meta:
        verbose_name = "Журнал синхронизации"
        verbose_name_plural = "Журналы синхронизации"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.object_name} - {self.timestamp:%d.%m.%Y %H:%M} ({self.get_status_display()})"


class CreditAgreement(models.Model):
    """
    Кредитные договоры банков.
    """
    bank = models.ForeignKey(
        Counteragent,
        verbose_name="Банк",
        related_name="credit_agreements",
        on_delete=models.CASCADE
    )
    contract_number = models.CharField(verbose_name="Номер договора", max_length=100)
    contract_date = models.DateField(verbose_name="Дата договора")
    amount = models.DecimalField(verbose_name="Сумма кредита", max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(verbose_name="Процентная ставка", max_digits=5, decimal_places=2)
    term_months = models.IntegerField(verbose_name="Срок кредита (в месяцах)")
    tranche_repayment_days = models.IntegerField(verbose_name="Дней на погашение транша", default=45)
    remaining_debt = models.DecimalField(verbose_name="Остаток долга", max_digits=15, decimal_places=2, default=0.00)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Ответственный сотрудник",
        related_name="responsible_credits",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Кредитный договор"
        verbose_name_plural = "Кредитные договоры"
        ordering = ["-contract_date"]

    def __str__(self) -> str:
        return f"Кредит № {self.contract_number} в {self.bank.short_name}"


class CreditPaymentSchedule(models.Model):
    """
    Графики платежей по кредитам.
    """
    STATUS_CHOICES = [
        ("planned", "Запланирован"),
        ("partially_paid", "Частично оплачен"),
        ("paid", "Оплачен"),
        ("overdue", "Просрочен"),
    ]

    credit_agreement = models.ForeignKey(
        CreditAgreement,
        verbose_name="Кредитный договор",
        related_name="payment_schedules",
        on_delete=models.CASCADE
    )
    payment_date = models.DateField(verbose_name="Дата платежа")
    principal = models.DecimalField(verbose_name="Основной долг", max_digits=15, decimal_places=2)
    interest = models.DecimalField(verbose_name="Проценты", max_digits=15, decimal_places=2)
    total_amount = models.DecimalField(verbose_name="Общая сумма", max_digits=15, decimal_places=2)
    status = models.CharField(
        verbose_name="Статус оплаты",
        max_length=20,
        choices=STATUS_CHOICES,
        default="planned"
    )

    class Meta:
        verbose_name = "График платежа по кредиту"
        verbose_name_plural = "Графики платежей по кредитам"
        ordering = ["payment_date"]

    def __str__(self) -> str:
        return f"Платеж по кредиту на {self.total_amount} от {self.payment_date}"


class CreditPaymentFact(models.Model):
    """
    Фактические платежи по кредитам.
    """
    PAYMENT_TYPE_CHOICES = [
        ("principal", "Основной долг (ОД)"),
        ("interest", "Проценты"),
    ]

    credit_agreement = models.ForeignKey(
        CreditAgreement,
        verbose_name="Кредитный договор",
        related_name="payment_facts",
        on_delete=models.CASCADE
    )
    schedule = models.ForeignKey(
        CreditPaymentSchedule,
        verbose_name="График платежа",
        related_name="payment_facts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    payment_date = models.DateField(verbose_name="Дата платежа")
    amount = models.DecimalField(verbose_name="Сумма платежа", max_digits=15, decimal_places=2)
    payment_type = models.CharField(
        verbose_name="Тип платежа",
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default="principal"
    )
    payment_doc_number = models.CharField(verbose_name="Номер платежного документа", max_length=100, blank=True, default="")
    ref_key = models.CharField(verbose_name="Уникальный номер 1С", max_length=37, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Факт оплаты кредита"
        verbose_name_plural = "Факты оплаты кредитов"
        ordering = ["-payment_date"]

    def __str__(self) -> str:
        return f"Оплата кредита на {self.amount} от {self.payment_date}"


class FinanceAuditLog(models.Model):
    """
    Журнал изменений финансовых объектов.
    """
    ACTION_CHOICES = [
        ("create", "Создание"),
        ("update", "Изменение"),
        ("delete", "Удаление"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто изменил",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    timestamp = models.DateTimeField(verbose_name="Дата изменения", auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    field_name = models.CharField(verbose_name="Поле", max_length=100, blank=True, default="")
    old_value = models.TextField(verbose_name="Старое значение", blank=True, null=True)
    new_value = models.TextField(verbose_name="Новое значение", blank=True, null=True)
    action = models.CharField(
        verbose_name="Действие",
        max_length=20,
        choices=ACTION_CHOICES
    )

    class Meta:
        verbose_name = "Журнал аудита финансов"
        verbose_name_plural = "Журнал аудита финансов"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.action} - {self.content_type.model} #{self.object_id} by {self.user}"


class UserNotificationSetting(models.Model):
    """
    Настройки каналов уведомлений пользователя.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        related_name="finance_notification_settings",
        on_delete=models.CASCADE
    )
    portal_enabled = models.BooleanField(verbose_name="Внутренние уведомления", default=True)
    email_enabled = models.BooleanField(verbose_name="Уведомления по Email", default=True)
    telegram_enabled = models.BooleanField(verbose_name="Уведомления в Telegram", default=False)

    class Meta:
        verbose_name = "Настройка уведомлений"
        verbose_name_plural = "Настройки уведомлений"

    def __str__(self) -> str:
        return f"Настройки уведомлений {self.user.username}"

class CentralBankKeyRate(models.Model):
    """
    Ключевая ставка ЦБ.
    """
    date_from = models.DateField(verbose_name="Действует с")
    rate = models.DecimalField(verbose_name="Ставка (%)", max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "Ключевая ставка ЦБ"
        verbose_name_plural = "Ключевые ставки ЦБ"
        ordering = ["-date_from"]

    def __str__(self) -> str:
        return f"{self.rate}% с {self.date_from}"


class CreditTranche(models.Model):
    """
    Транши по кредиту (овердрафту).
    """
    credit_agreement = models.ForeignKey(
        CreditAgreement,
        verbose_name="Кредитный договор",
        related_name="tranches",
        on_delete=models.CASCADE
    )
    date = models.DateField(verbose_name="Дата выдачи транша")
    amount = models.DecimalField(verbose_name="Сумма транша", max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = "Транш кредита"
        verbose_name_plural = "Транши кредитов"
        ordering = ["date"]

    def __str__(self) -> str:
        return f"Транш на {self.amount} от {self.date} по {self.credit_agreement}"
