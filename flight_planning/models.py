# flight_planning/models.py
from datetime import date
from typing import Optional

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from contracts_app.models import Estate, TypeProperty


FLIGHT_TYPES = (
    ('standard', 'Обычный полет'),
    ('check_flight_engineer', 'Проверочный полет бортмеханика'),
    ('check_pilot', 'Проверочный полет пилотов'),
    ('double_check', 'Двойной проверочный полет'),
)

CREW_ROLES = (
    ('commander', 'КВС (Командир воздушного судна)'),
    ('copilot', 'Второй пилот'),
    ('pilot_instructor', 'Пилот-инструктор (проверяющий)'),
    ('flight_engineer', 'Бортмеханик'),
    ('flight_engineer_instructor', 'Бортмеханик-инструктор (проверяющий)'),
)


class PilotAssignment(models.Model):
    """
    Назначение пилота на МПД на конкретную дату
    """
    pilot = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        verbose_name="Пилот",
        related_name="assignments"
    )
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        verbose_name="МПД",
        related_name="assignments"
    )
    date = models.DateField(
        verbose_name="Дата",
        db_index=True
    )
    crew = models.ForeignKey(
        'FlightCrew',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
        verbose_name="Экипаж"
    )
    role_in_crew = models.CharField(
        max_length=50,
        blank=True,
        default="",
        choices=CREW_ROLES,
        verbose_name="Роль в экипаже"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assignments",
        verbose_name="Кто назначил"
    )

    class Meta:
        # Один пилот не может быть в двух разных МПД в один день
        unique_together = [['pilot', 'date']]
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['mpd', 'date']),
            models.Index(fields=['pilot', 'date']),
        ]
        ordering = ['date', 'mpd__name']
        verbose_name = "Назначение пилота"
        verbose_name_plural = "Назначения пилотов"

    def __str__(self):
        pilot_name = self.pilot.title or self.pilot.username
        return f"{pilot_name} → {self.mpd.name} ({self.date})"

    def clean(self):
        """Валидация на уровне модели"""
        # Запрещаем назначение на прошедшие даты (опционально)
        if self.date and self.date < timezone.now().date():
            raise ValidationError({'date': 'Нельзя назначать пилота на прошедшие даты'})


class AircraftMovement(models.Model):
    """
    Журнал перемещения воздушных судов (ВС) по МПД (PlaceProductionActivity).
    Позволяет фиксировать перемещение борта на МПД и определять актуальное местонахождение ВС на любую дату.
    """
    aircraft = models.ForeignKey(
        Estate,
        on_delete=models.CASCADE,
        verbose_name="Воздушное судно",
        related_name="movements"
    )
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        verbose_name="МПД базирования",
        related_name="aircraft_movements"
    )
    date = models.DateField(
        verbose_name="Дата перемещения / базирования",
        db_index=True
    )
    comment = models.TextField(
        verbose_name="Примечание / Основание",
        blank=True,
        default=""
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_aircraft_movements",
        verbose_name="Кто переместил / зафиксировал"
    )

    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['aircraft', 'date']),
            models.Index(fields=['mpd', 'date']),
        ]
        ordering = ['-date', '-created_at']
        verbose_name = "Перемещение ВС"
        verbose_name_plural = "Журнал перемещений ВС"

    def __str__(self):
        aircraft_reg = self.aircraft.registration_number if self.aircraft else "Борт"
        mpd_name = self.mpd.name if self.mpd else "МПД"
        return f"{aircraft_reg} → {mpd_name} ({self.date})"


class FlightCrew(models.Model):
    """
    Экипаж воздушного судна на МПД на конкретную дату.
    """
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        verbose_name="МПД",
        related_name="flight_crews"
    )
    aircraft = models.ForeignKey(
        Estate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Воздушное судно",
        related_name="flight_crews"
    )
    date = models.DateField(
        verbose_name="Дата",
        db_index=True
    )
    flight_type = models.CharField(
        max_length=50,
        choices=FLIGHT_TYPES,
        default='standard',
        verbose_name="Тип полета"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Наименование экипажа"
    )
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name="Примечание"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_flight_crews",
        verbose_name="Кто создал"
    )

    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['mpd', 'date']),
            models.Index(fields=['aircraft', 'date']),
        ]
        ordering = ['date', 'mpd__name']
        verbose_name = "Летный экипаж"
        verbose_name_plural = "Летные экипажи"
        permissions = [
            ("can_manage_flight_planning", "Может управлять планированием полетов (полный доступ)"),
            ("can_view_flight_planning", "Может просматривать таблицу планирования полетов"),
            ("can_view_flight_reports", "Может просматривать отчеты по планированию полетов"),
        ]

    def __str__(self):
        ac_title = self.aircraft.registration_number if self.aircraft else "Резервный экипаж"
        type_title = dict(FLIGHT_TYPES).get(self.flight_type, self.flight_type)
        return f"Экипаж {ac_title} ({type_title}) на {self.mpd.name} ({self.date})"

    def clean(self):
        """
        Проверка: за одним бортом в один день не может быть закреплено 2 и более экипажей.
        """
        if self.aircraft and self.date:
            qs = FlightCrew.objects.filter(aircraft=self.aircraft, date=self.date)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({
                    'aircraft': f"За бортом {self.aircraft.registration_number} на дату {self.date} уже закреплен другой экипаж."
                })


class CrewMember(models.Model):
    """
    Член экипажа и его роль.
    """
    crew = models.ForeignKey(
        FlightCrew,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="Экипаж"
    )
    member = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name="crew_memberships",
        verbose_name="Сотрудник"
    )
    role = models.CharField(
        max_length=50,
        choices=CREW_ROLES,
        verbose_name="Роль в экипаже"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления"
    )

    class Meta:
        unique_together = [['crew', 'member']]
        indexes = [
            models.Index(fields=['crew', 'member']),
            models.Index(fields=['member', 'role']),
        ]
        verbose_name = "Член экипажа"
        verbose_name_plural = "Члены экипажа"

    def __str__(self):
        role_label = dict(CREW_ROLES).get(self.role, self.role)
        name = self.member.title or self.member.username
        return f"{name} ({role_label})"


class FlightCrewNote(models.Model):
    """
    Пометки и оперативные сообщения к полету / экипажу (для второго пилота и членов экипажа).
    Позволяет фиксировать оперативные статусы (перенос, отмена, метеоусловия, особые указания).
    """
    crew = models.ForeignKey(
        FlightCrew,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name="Экипаж"
    )
    author = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crew_notes",
        verbose_name="Автор пометки"
    )
    author_role = models.CharField(
        max_length=50,
        blank=True,
        default="",
        choices=CREW_ROLES,
        verbose_name="Роль автора в экипаже"
    )
    message = models.TextField(
        verbose_name="Текст сообщения / пометки"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата и время обновления"
    )

    class Meta:
        indexes = [
            models.Index(fields=['crew', '-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = "Пометка к полету"
        verbose_name_plural = "Пометки к полетам"

    def __str__(self):
        author_name = self.author.title if (self.author and self.author.title) else (self.author.username if self.author else "Аноним")
        role_label = dict(CREW_ROLES).get(self.author_role, self.author_role)
        role_str = f" ({role_label})" if role_label else ""
        return f"{self.created_at.strftime('%d.%m.%Y %H:%M')} — {author_name}{role_str}: {self.message[:40]}"


DOCUMENT_STATUSES = (
    ('draft', 'Черновик'),
    ('pending', 'На утверждении'),
    ('approved', 'Утвержден'),
    ('archived', 'Архивный'),
)


class FlightPlanningDocument(models.Model):
    """Официальный документ расстановки экипажей на месяц с версионированием.

    Модель хранит зафиксированное состояние сетки планирования полетов на месяц
    в виде неизменяемого JSON-снимка, служебные реквизиты (номер, дата, автор, утверждающий),
    а также журнал изменений (diff) относительно предыдущей редакции.

    Attributes:
        number (str): Номер документа в формате ММ-ВВ/ГГГГ (например, 09-01/2026).
        year (int): Год планирования.
        month (int): Месяц планирования (1-12).
        version (int): Порядковый номер редакции в указанном месяце.
        status (str): Статус документа (draft, pending, approved, archived).
        title (str): Полное наименование документа.
        reason (str): Основание / причина внесения изменений.
        author (DataBaseUser): Диспетчер, сформировавший документ.
        approved_by (DataBaseUser): Руководитель, утвердивший документ.
        approved_at (datetime): Дата и время утверждения.
        created_at (datetime): Дата и время составления документа.
        updated_at (datetime): Дата и время последнего обновления.
        snapshot_data (dict): Полный сериализованный снимок сетки планирования.
        diff_data (list): Список зафиксированных изменений относительно предыдущей версии.
        previous_document (FlightPlanningDocument): Ссылка на предшествующую редакцию.
    """

    number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Номер документа",
        db_index=True
    )
    year = models.PositiveIntegerField(
        verbose_name="Год планирования",
        db_index=True
    )
    month = models.PositiveSmallIntegerField(
        verbose_name="Месяц планирования",
        db_index=True
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Номер редакции"
    )
    status = models.CharField(
        max_length=20,
        choices=DOCUMENT_STATUSES,
        default='pending',
        verbose_name="Статус документа",
        db_index=True
    )
    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок документа"
    )
    reason = models.TextField(
        blank=True,
        default="",
        verbose_name="Основание / Причина изменений"
    )
    author = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="flight_planning_documents_created",
        verbose_name="Составил (диспетчер)"
    )
    approved_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flight_planning_documents_approved",
        verbose_name="Утвердил (руководитель)"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата и время утверждения"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата составления"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    snapshot_data = models.JSONField(
        default=dict,
        verbose_name="Снимок сетки планирования (JSON)"
    )
    diff_data = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Список изменений (JSON)"
    )
    previous_document = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subsequent_documents",
        verbose_name="Предыдущая редакция"
    )

    class Meta:
        indexes = [
            models.Index(fields=['year', 'month', 'status']),
            models.Index(fields=['-created_at']),
        ]
        ordering = ['-year', '-month', '-version']
        verbose_name = "Документ расстановки экипажей"
        verbose_name_plural = "Документы расстановки экипажей"

    def __str__(self) -> str:
        """Возвращает строковое представление документа.

        Returns:
            str: Номер и статус документа.
        """
        status_label = dict(DOCUMENT_STATUSES).get(self.status, self.status)
        return f"Документ № {self.number} ({status_label})"

    @property
    def is_approved(self) -> bool:
        """Проверяет, утвержден ли документ.

        Returns:
            bool: True, если статус 'approved', иначе False.
        """
        return self.status == 'approved'

    @property
    def is_pending(self) -> bool:
        """Проверяет, находится ли документ на утверждении.

        Returns:
            bool: True, если статус 'pending', иначе False.
        """
        return self.status == 'pending'


CHECK_APPLIES_TO = (
    ('all', 'Весь персонал'),
    ('crew', 'Летный состав (Пилоты и Бортмеханики)'),
    ('pilots', 'Только пилоты'),
    ('flight_engineers', 'Только бортмеханики'),
    ('technicians', 'Только авиатехники'),
)


class PeriodicCheckType(models.Model):
    """Вид периодического мероприятия квалификации и годности персонала.

    Определяет наименование мероприятия, привязку к типу воздушного судна (или
    универсальный характер), стандартную периодичность в месяцах и целевую категорию персонала.

    Attributes:
        name (str): Наименование мероприятия (напр. "Тренажер", "ВЛЭК", "Опасные грузы").
        code (str): Краткий символьный код / шифр мероприятия.
        aircraft_type (TypeProperty): Привязка к типу ВС (None = для всех типов *).
        validity_months (int): Периодичность действия мероприятия в месяцах.
        validity_days (int): Дополнительные дни действия (по умолчанию 0).
        applies_to (str): Категория персонала, подлежащая данному мероприятию.
        description (str): Нормативное основание и описание программы мероприятия.
        is_active (bool): Флаг активности вида мероприятия.
        order (int): Порядковый номер для сортировки в отчетах.
    """
    name = models.CharField(max_length=200, verbose_name="Наименование мероприятия")
    code = models.CharField(max_length=50, blank=True, default="", verbose_name="Код / Обозначение")
    aircraft_type = models.ForeignKey(
        TypeProperty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Тип ВС",
        related_name="check_types",
        help_text="Оставьте пустым для универсальных мероприятий (*)"
    )
    validity_months = models.PositiveIntegerField(
        default=12,
        verbose_name="Периодичность (в месяцах)",
        help_text="Срок действия по умолчанию для автоматического расчета даты окончания"
    )
    validity_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Дополнительные дни",
        help_text="Дополнительные дни к месяцам при расчете (обычно 0)"
    )
    applies_to = models.CharField(
        max_length=50,
        choices=CHECK_APPLIES_TO,
        default='crew',
        verbose_name="Категория персонала"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание / Нормативный документ"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активно"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок сортировки"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Вид периодического мероприятия"
        verbose_name_plural = "Виды периодических мероприятий"
        indexes = [
            models.Index(fields=['is_active', 'aircraft_type']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление вида мероприятия.

        Returns:
            str: Наименование, тип ВС и срок действия.
        """
        ac_name = self.aircraft_type.type_property if self.aircraft_type else "*"
        return f"{self.name} [{ac_name}] ({self.validity_months} мес.)"

    @property
    def aircraft_display(self) -> str:
        """Возвращает отображаемое имя типа ВС или символ * для универсальных проверок.

        Returns:
            str: Название типа ВС или '*'
        """
        return self.aircraft_type.type_property if self.aircraft_type else "*"


class PeriodicCheckRecord(models.Model):
    """Запись о прохождении периодического мероприятия сотрудником.

    Фиксирует факт сдачи/прохождения мероприятия, дату начала действия,
    дату окончания (срок годности), номер подтверждающего документа и скан-копию.

    Attributes:
        employee (DataBaseUser): Сотрудник, прошедший мероприятие.
        check_type (PeriodicCheckType): Вид периодического мероприятия.
        aircraft_type (TypeProperty): Тип ВС (наследуется из вида мероприятия или уточняется).
        start_date (date): Дата прохождения / начала действия.
        end_date (date): Дата окончания действия / срок годности.
        document_number (str): Номер свидетельства / сертификата / справки.
        issued_by (str): Организация / Учебный центр / ВЛЭК / Инструктор.
        scan_file (FileField): Электронная скан-копия документа.
        notes (str): Примечание или комментарий.
        created_by (DataBaseUser): Пользователь, создавший запись.
        created_at (datetime): Дата и время создания.
        updated_at (datetime): Дата и время обновления.
    """
    employee = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        verbose_name="Сотрудник",
        related_name="flight_periodic_checks"
    )
    check_type = models.ForeignKey(
        PeriodicCheckType,
        on_delete=models.CASCADE,
        verbose_name="Вид мероприятия",
        related_name="records"
    )
    aircraft_type = models.ForeignKey(
        TypeProperty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Тип ВС",
        related_name="check_records",
        help_text="Оставьте пустым для универсальных мероприятий (*)"
    )
    start_date = models.DateField(
        verbose_name="Дата прохождения (Начало)",
        db_index=True
    )
    end_date = models.DateField(
        verbose_name="Действует до (Окончание)",
        db_index=True
    )
    document_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Номер документа / сертификата"
    )
    issued_by = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Кем выдано / Инструктор / УЦ"
    )
    scan_file = models.FileField(
        upload_to="flight_planning/check_scans/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Скан документа"
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Примечание"
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Автор записи",
        related_name="created_periodic_checks"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        ordering = ['-end_date', '-start_date']
        verbose_name = "Запись о прохождении мероприятия"
        verbose_name_plural = "Журнал прохождения мероприятий"
        indexes = [
            models.Index(fields=['employee', 'check_type', '-end_date']),
            models.Index(fields=['end_date']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление записи мероприятия.

        Returns:
            str: ФИО сотрудника, наименование мероприятия и дата окончания.
        """
        emp_name = self.employee.title or self.employee.username
        return f"{emp_name} — {self.check_type.name} (до {self.end_date.strftime('%d.%m.%Y')})"

    def clean(self) -> None:
        """Валидирует корректность дат начала и окончания.

        Raises:
            ValidationError: Если дата окончания раньше даты начала.
        """
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': "Дата окончания не может быть раньше даты начала прохождения проверки."
            })

    def save(self, *args, **kwargs) -> None:
        """Автоматически подтягивает тип ВС из вида проверки, если он не указан."""
        if not self.aircraft_type_id and self.check_type and self.check_type.aircraft_type_id:
            self.aircraft_type = self.check_type.aircraft_type
        super().save(*args, **kwargs)

    def status_on_date(self, target_date=None) -> str:
        """Определяет статус действия проверки на указанную дату.

        Args:
            target_date (date, optional): Проверяемая дата. По умолчанию сегодняшний день.

        Returns:
            str: 'valid' (действует), 'warning' (истекает в течение 30 дней), 'expired' (просрочена).
        """
        if target_date is None:
            target_date = timezone.now().date()

        if target_date > self.end_date:
            return 'expired'
        elif target_date < self.start_date:
            return 'future'
        else:
            days_left = (self.end_date - target_date).days
            if days_left <= 30:
                return 'warning'
            return 'valid'

    @property
    def days_remaining(self) -> int:
        """Возвращает количество дней до окончания действия проверки относительно сегодняшней даты.

        Returns:
            int: Количество дней (отрицательное значение, если проверка уже просрочена).
        """
        today = timezone.now().date()
        return (self.end_date - today).days

    @property
    def is_currently_valid(self) -> bool:
        """Проверяет, действует ли проверка на текущий момент.

        Returns:
            bool: True, если сегодняшняя дата находится в интервале действия проверки.
        """
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def days_overdue(self) -> int:
        """Возвращает модуль количества дней просрочки (положительное число).

        Returns:
            int: Количество дней, прошедших с момента истечения проверки.
        """
        return abs(self.days_remaining)

    def get_successor(self):
        """Возвращает более новую (последующую) запись проверки того же вида для данного сотрудника, если она существует.

        Returns:
            Optional[PeriodicCheckRecord]: Следующая/актуальная запись или None.
        """
        if hasattr(self, '_successor_cached'):
            return self._successor_cached
        qs = PeriodicCheckRecord.objects.filter(
            employee_id=self.employee_id,
            check_type_id=self.check_type_id
        ).exclude(id=self.id)
        if self.aircraft_type_id:
            qs = qs.filter(models.Q(aircraft_type_id=self.aircraft_type_id) | models.Q(aircraft_type__isnull=True))
        successor = qs.filter(
            models.Q(end_date__gt=self.end_date) | models.Q(start_date__gt=self.start_date)
        ).order_by('-end_date', '-start_date').first()
        self._successor_cached = successor
        return successor

    @property
    def is_superseded(self) -> bool:
        """Проверяет, была ли данная проверка продлена / заменена более новой записью.

        Returns:
            bool: True, если для сотрудника уже внесена более новая проверка того же вида.
        """
        if hasattr(self, '_is_superseded_cached'):
            return self._is_superseded_cached
        return self.get_successor() is not None



# ========================================================
# МОДУЛЬ «СОСТОЯНИЯ И СТАТУСЫ ПЕРСОНАЛА» (EMPLOYEE STATUSES)
# ========================================================

EMPLOYEE_STATUS_CODES = (
    ('VACATION', 'Отпуск'),
    ('EXTRA_VACATION', 'Дополнительный отпуск'),
    ('SICK_LEAVE', 'Больничный'),
    ('RESERVE', 'Резерв'),
    ('MEDICAL_EXAM', 'Медосмотр'),
    ('KPK', 'КПК'),
    ('VLEK', 'ВЛЭК'),
    ('BUSINESS_TRIP', 'Командировка'),
    ('DAY_OFF', 'Отгул'),
    ('OTHER', 'Другое'),
)


class EmployeeStatusType(models.Model):
    """Справочник видов состояний и статусов доступности персонала (Отпуск, Больничный, Резерв, КПК, ВЛЭК и др.).

    Attributes:
        name (str): Наименование статуса (напр. «Отпуск», «Больничный», «Резерв»).
        code (str): Уникальный код/шифр статуса ('VACATION', 'SICK_LEAVE', 'RESERVE', 'KPK', 'VLEK' и др.).
        color (str): Цвет для индикации и бейджей в hex-формате (напр. #ef4444).
        is_blocking (bool): Флаг несовместимости с назначением в экипаж (вызывает предупреждение/конфликт).
        description (str): Описание статуса.
        is_active (bool): Флаг активности вида статуса.
        order (int): Порядок сортировки.
    """
    name = models.CharField(
        max_length=100,
        verbose_name="Наименование статуса",
        help_text="Например: Отпуск, Доп отпуск, Больничный, Резерв, Медосмотр, КПК, ВЛЭК"
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        choices=EMPLOYEE_STATUS_CODES,
        verbose_name="Код статуса",
        help_text="Системный код типа состояния"
    )
    color = models.CharField(
        max_length=20,
        default="#64748b",
        verbose_name="Цвет бейджа",
        help_text="HEX-код цвета (например, #ef4444 для больничного, #f59e0b для отпуска)"
    )
    is_blocking = models.BooleanField(
        default=True,
        verbose_name="Предупреждать при назначении в экипаж",
        help_text="Если включено, назначение сотрудника с этим статусом в экипаж будет вызывать предупреждение о занятости"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    order = models.PositiveIntegerField(
        default=10,
        verbose_name="Порядок сортировки"
    )

    class Meta:
        verbose_name = "Вид состояния сотрудника"
        verbose_name_plural = "Справочник состояний сотрудников"
        ordering = ['order', 'name']

    def __str__(self) -> str:
        """Возвращает наименование вида статуса.

        Returns:
            str: Название статуса.
        """
        return self.name


class EmployeeStatusRecord(models.Model):
    """Журнал учета состояний и периодов занятости персонала (Отпуск, Больничный, Резерв, КПК, ВЛЭК).

    Attributes:
        employee (DataBaseUser): Сотрудник (пилот, бортмеханик, техник).
        status_type (EmployeeStatusType): Вид состояния / статуса.
        start_date (date): Дата начала действия статуса (С).
        end_date (date): Дата окончания действия статуса (ПО).
        document_number (str): Номер приказа, больничного листа, направления или распоряжения.
        notes (str): Служебные примечания и комментарии.
        created_by (DataBaseUser): Пользователь (диспетчер/кадровик), создавший запись.
        created_at (datetime): Дата и время создания записи.
        updated_at (datetime): Дата и время последнего обновления записи.
    """
    employee = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        related_name='status_records',
        verbose_name="Сотрудник"
    )
    status_type = models.ForeignKey(
        EmployeeStatusType,
        on_delete=models.PROTECT,
        related_name='records',
        verbose_name="Вид состояния"
    )
    start_date = models.DateField(
        verbose_name="Дата начала (С)",
        db_index=True
    )
    end_date = models.DateField(
        verbose_name="Дата окончания (ПО)",
        db_index=True
    )
    document_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Номер документа / приказа"
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Примечание"
    )
    created_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_status_records',
        verbose_name="Кто создал"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Запись о состоянии сотрудника"
        verbose_name_plural = "Журнал состояний сотрудников"
        ordering = ['-start_date', 'employee__last_name']
        indexes = [
            models.Index(fields=['employee', 'start_date', 'end_date']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление записи состояния сотрудника.

        Returns:
            str: ФИО, название статуса и интервал дат.
        """
        emp_name = self.employee.title or self.employee.username
        return f"{emp_name} — {self.status_type.name} ({self.start_date.strftime('%d.%m.%Y')} — {self.end_date.strftime('%d.%m.%Y')})"

    def clean(self) -> None:
        """Валидирует корректность дат начала и окончания периода.

        Raises:
            ValidationError: Если дата окончания раньше даты начала.
        """
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': "Дата окончания (ПО) не может быть раньше даты начала (С)."
            })

    def is_active_on_date(self, target_date: Optional[date] = None) -> bool:
        """Проверяет, активно ли состояние сотрудника на указанную дату.

        Args:
            target_date (Optional[date]): Проверяемая дата (по умолчанию сегодня).

        Returns:
            bool: True, если целевая дата попадает в интервал [start_date, end_date].
        """
        if target_date is None:
            target_date = timezone.now().date()
        return self.start_date <= target_date <= self.end_date

    @property
    def duration_days(self) -> int:
        """Возвращает продолжительность периода в календарных днях (включительно).

        Returns:
            int: Количество дней.
        """
        return (self.end_date - self.start_date).days + 1


class EmployeeRequiredCheck(models.Model):
    """Закрепление обязательных периодических мероприятий за конкретным сотрудником.

    Определяет индивидуальный перечень периодических мероприятий, обязательных
    для прохождения конкретным пилотом, бортмехаником или техником.
    Если мероприятие не закреплено за сотрудником, оно не требуется к сдаче,
    не блокирует вылеты и не отображается как просроченное.

    Attributes:
        employee (DataBaseUser): Сотрудник (пилот, бортмеханик, инженер).
        check_type (PeriodicCheckType): Вид периодического мероприятия.
        is_required (bool): Флаг обязательности прохождения (по умолчанию True).
        notes (str): Примечание или основание закрепления/исключения.
        assigned_by (DataBaseUser): Диспетчер/руководитель, закрепивший мероприятие.
        created_at (datetime): Дата назначения.
        updated_at (datetime): Дата изменения.
    """
    employee = models.ForeignKey(
        DataBaseUser,
        on_delete=models.CASCADE,
        verbose_name="Сотрудник",
        related_name="required_periodic_checks"
    )
    check_type = models.ForeignKey(
        PeriodicCheckType,
        on_delete=models.CASCADE,
        verbose_name="Вид мероприятия",
        related_name="employee_assignments"
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name="Обязательно к прохождению",
        help_text="Если флаг снят, мероприятие считается необязательным для данного сотрудника."
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Примечание"
    )
    assigned_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Кем назначено",
        related_name="assigned_employee_checks"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата назначения"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Закрепление мероприятия за сотрудником"
        verbose_name_plural = "Закрепления мероприятий за персоналом"
        unique_together = ('employee', 'check_type')
        ordering = ['employee__last_name', 'check_type__order']
        indexes = [
            models.Index(fields=['employee', 'is_required']),
            models.Index(fields=['check_type', 'is_required']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление закрепления.

        Returns:
            str: ФИО сотрудника и название мероприятия.
        """
        emp_name = self.employee.title or self.employee.username
        req_str = "Обязательно" if self.is_required else "Не требуется"
        return f"{emp_name} — {self.check_type.name} ({req_str})"






