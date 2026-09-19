# flight_planning/models.py
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

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


class AviationWeatherStation(models.Model):
    """Справочник сертифицированных метеостанций и аэродромов гражданской авиации (АМСГ/ICAO).

    Хранит координатную привязку, высоту над уровнем моря и международные идентификаторы
    метеостанций, публикующих регулярные сводки METAR/SPECI и прогнозы TAF.
    Служит опорной геодезической базой для расчета расстояний и перепадов высот до мест деятельности (МПД).

    Attributes:
        icao_code (str): 4-буквенный международный код ICAO (например, USRR, USTR, UNNT, ULLI).
        name (str): Наименование метеостанции/аэродрома на латинице (например, 'Surgut', 'Roshchino').
        name_ru (str): Наименование метеостанции/аэродрома на русском языке (например, 'Сургут', 'Тюмень (Рощино)').
        latitude (float): Географическая широта контрольной точки аэродрома в градусах.
        longitude (float): Географическая долгота контрольной точки аэродрома в градусах.
        elevation_msl_m (Optional[float]): Абсолютная высота контрольной точки аэродрома над уровнем моря (MSL, м).
        country (str): Страна расположения (по умолчанию 'Russia').
        is_active (bool): Флаг активности метеостанции для регулярного мониторинга.
        created_at (datetime): Дата и время создания записи в БД.
        updated_at (datetime): Дата и время последнего обновления записи.
    """

    icao_code = models.CharField(
        max_length=4,
        unique=True,
        db_index=True,
        verbose_name="Код ICAO",
        help_text="4-буквенный международный код метеостанции/аэродрома (например, USRR, UNNT, USTR)",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Наименование (латиница)",
        help_text="Международное наименование аэропорта/станции",
    )
    name_ru = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Наименование (русский)",
        help_text="Русскоязычное наименование аэропорта или населенного пункта",
    )
    latitude = models.FloatField(
        verbose_name="Широта",
        help_text="Географическая широта контрольной точки аэродрома в градусах",
    )
    longitude = models.FloatField(
        verbose_name="Долгота",
        help_text="Географическая долгота контрольной точки аэродрома в градусах",
    )
    elevation_msl_m = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Высота аэродрома (MSL, м)",
        help_text="Высота контрольной точки аэродрома над средним уровнем моря (MSL) в метрах",
    )
    country = models.CharField(
        max_length=100,
        default="Russia",
        verbose_name="Страна",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна для мониторинга",
        help_text="Включить регулярный сбор фактических сводок METAR/TAF",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Метеостанция (АМСГ/ICAO)"
        verbose_name_plural = "Справочник метеостанций (ICAO)"
        ordering = ["icao_code"]
        indexes = [
            models.Index(fields=["icao_code"]),
            models.Index(fields=["is_active", "icao_code"]),
        ]

    def __str__(self) -> str:
        """Строковое представление метеостанции.

        Returns:
            str: Код ICAO и русское/латинское наименование.
        """
        title = self.name_ru or self.name
        return f"{self.icao_code} — {title}"


class AviationWeatherObservation(models.Model):
    """Архив фактических метеонаблюдений (METAR / SPECI) по аэродромам и МПД.

    Сохраняет хронологические замеры погоды (тайм-серии) с автоматической расшифровкой
    параметров ветра, видимости, нижней кромки облачности (НГО), температуры,
    давления QNH и летной категории условий (VFR / MVFR / IFR / LIFR).

    Attributes:
        station (Optional[AviationWeatherStation]): Связанная опорная метеостанция из справочника.
        mpd (PlaceProductionActivity): Место производственной деятельности (опционально).
        icao_code (str): 4-буквенный международный код метеостанции/аэродрома ICAO.
        observation_time (datetime): Дата и время фиксации метеонаблюдения (UTC).
        report_type (str): Тип сводки ('METAR' - регулярная, 'SPECI' - специальная штормовая).
        raw_text (str): Исходная телеграмма METAR/SPECI без изменений.
        flight_category (str): Летная категория ('VFR', 'MVFR', 'IFR', 'LIFR').
        wind_direction (int): Направление ветра в градусах (0-360, None для штиля/VRB).
        wind_speed (float): Скорость ветра в м/с.
        wind_gust (float): Порывы ветра в м/с (если зафиксированы).
        wind_variable (bool): Флаг переменного направления ветра (VRB).
        visibility_meters (int): Горизонтальная видимость в метрах.
        cavok (bool): Флаг условий CAVOK (видимость >10 км, нет облаков ниже 1500м, нет опасных явлений).
        cloud_base_meters (int): Нижняя граница облачности (НГО) в метрах.
        cloud_coverage (str): Тип покрытия облачностью ('FEW', 'SCT', 'BKN', 'OVC', 'VV', 'NSC/CLR').
        temperature (float): Температура воздуха в градусах Цельсия.
        dew_point (float): Точка росы в градусах Цельсия.
        pressure_hpa (float): Атмосферное давление QNH в гектопаскалях (hPa).
        pressure_mmhg (float): Атмосферное давление QNH в миллиметрах ртутного столба (мм рт. ст.).
        weather_phenomena (str): Расшифрованные погодные явления на русском языке.
        created_at (datetime): Дата и время сохранения записи в БД.
    """

    REPORT_TYPES = (
        ("METAR", "Регулярная сводка (METAR)"),
        ("SPECI", "Специальная сводка (SPECI)"),
    )

    FLIGHT_CATEGORIES = (
        ("VFR", "ПВП (VFR) — Визуальные метеоусловия"),
        ("MVFR", "ОПВП (MVFR) — Ухудшенные визуальные"),
        ("IFR", "ППП (IFR) — Приборные метеоусловия"),
        ("LIFR", "НППП (LIFR) — Низкие приборные"),
    )

    station = models.ForeignKey(
        AviationWeatherStation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="observations",
        verbose_name="Метеостанция",
    )
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="weather_observations",
        verbose_name="МПД базирования",
    )
    icao_code = models.CharField(
        max_length=4,
        db_index=True,
        verbose_name="Код ICAO",
        help_text="4-буквенный код ICAO (например, UNNT, USRR, ULLI, UUEE)",
    )
    observation_time = models.DateTimeField(
        db_index=True,
        verbose_name="Время наблюдения (UTC)",
    )
    report_type = models.CharField(
        max_length=10,
        choices=REPORT_TYPES,
        default="METAR",
        verbose_name="Тип сводки",
    )
    raw_text = models.TextField(
        verbose_name="Исходная телеграмма (METAR/SPECI)",
    )
    flight_category = models.CharField(
        max_length=10,
        choices=FLIGHT_CATEGORIES,
        default="VFR",
        verbose_name="Летные условия",
    )
    wind_direction = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Направление ветра (°)",
    )
    wind_speed = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Скорость ветра (м/с)",
    )
    wind_gust = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Порывы ветра (м/с)",
    )
    wind_variable = models.BooleanField(
        default=False,
        verbose_name="Переменное направление ветра (VRB)",
    )
    visibility_meters = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Видимость (м)",
    )
    cavok = models.BooleanField(
        default=False,
        verbose_name="CAVOK (Хорошая погода)",
    )
    cloud_base_meters = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Нижняя граница облачности (м)",
    )
    cloud_coverage = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Покрытие облачностью",
    )
    temperature = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Температура (°C)",
    )
    dew_point = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Точка росы (°C)",
    )
    pressure_hpa = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление QNH (гПа)",
    )
    pressure_mmhg = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление QNH (мм рт. ст.)",
    )
    weather_phenomena = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Погодные явления",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Сохранено в системе",
    )

    class Meta:
        verbose_name = "Метеонаблюдение (METAR)"
        verbose_name_plural = "Архив метеонаблюдений (METAR)"
        ordering = ["-observation_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["icao_code", "observation_time"],
                name="uniq_aviation_observation_icao_time",
            ),
        ]
        indexes = [
            models.Index(fields=["icao_code", "observation_time"]),
            models.Index(fields=["mpd", "observation_time"]),
            models.Index(fields=["flight_category", "observation_time"]),
            models.Index(fields=["station", "observation_time"]),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление метеонаблюдения.

        Returns:
            str: Код ICAO, время наблюдения и летная категория.
        """
        obs_str = self.observation_time.strftime("%d.%m.%Y %H:%M") if self.observation_time else "—"
        return f"{self.icao_code} [{obs_str} UTC] — {self.flight_category}"

    def get_flight_category_color(self) -> str:
        """Возвращает цвет бейджа летных условий для UI.

        Returns:
            str: Bootstrap/CSS класс цвета ('success', 'info', 'danger', 'dark').
        """
        mapping = {
            "VFR": "success",
            "MVFR": "info",
            "IFR": "danger",
            "LIFR": "dark",
        }
        return mapping.get(self.flight_category, "secondary")

    def get_flight_category_name_ru(self) -> str:
        """Возвращает русское обозначение летных правил.

        Returns:
            str: ПВП, ОПВП, ППП или НППП.
        """
        mapping = {
            "VFR": "ПВП",
            "MVFR": "ОПВП",
            "IFR": "ППП",
            "LIFR": "НППП",
        }
        return mapping.get(self.flight_category, self.flight_category)

    def get_wind_display(self) -> str:
        """Возвращает форматированное описание ветра.

        Returns:
            str: Направление и скорость с порывами (например, '240° 6 м/с (порывы 12)').
        """
        if self.wind_speed is None or self.wind_speed == 0:
            return "Штиль (0 м/с)"
        dir_str = "VRB" if self.wind_variable or self.wind_direction is None else f"{self.wind_direction:03d}°"
        spd_str = f"{self.wind_speed:.0f} м/с"
        gust_str = f" (порывы {self.wind_gust:.0f} м/с)" if self.wind_gust else ""
        return f"{dir_str} {spd_str}{gust_str}"

    def get_visibility_display(self) -> str:
        """Возвращает форматированное значение видимости.

        Returns:
            str: Видимость в км/метрах.
        """
        if self.cavok:
            return "> 10 км (CAVOK)"
        if self.visibility_meters is None:
            return "—"
        if self.visibility_meters >= 10000:
            return "≥ 10 км"
        if self.visibility_meters >= 1000:
            return f"{self.visibility_meters / 1000:.1f} км"
        return f"{self.visibility_meters} м"

    def get_cloud_display(self) -> str:
        """Возвращает форматированное значение облачности и НГО.

        Returns:
            str: Описание облачности с высотой НГО в метрах.
        """
        if self.cavok:
            return "Ясно / CAVOK"
        if self.cloud_base_meters is None:
            return self.cloud_coverage or "Ясно (NSC)"
        cov = self.cloud_coverage or "НГО"
        return f"{cov} ({self.cloud_base_meters} м)"


class AviationWeatherForecast(models.Model):
    """Архив авиационных прогнозов погоды по аэродромам (TAF).

    Хранит официальные телеграммы TAF со сроками действия (горизонт 24-30 часов)
    и структурированными периодами прогноза изменений (TEMPO, BECMG, PROB).

    Attributes:
        station (Optional[AviationWeatherStation]): Связанная метеостанция из справочника.
        mpd (PlaceProductionActivity): Место производственной деятельности (опционально).
        icao_code (str): 4-буквенный международный код метеостанции/аэродрома ICAO.
        issued_at (datetime): Время выпуска прогноза (UTC).
        valid_from (datetime): Начало периода действия прогноза (UTC).
        valid_to (datetime): Окончание периода действия прогноза (UTC).
        raw_text (str): Исходная телеграмма TAF без изменений.
        forecast_json (dict): Структурированные периоды и тренды прогноза в формате JSON.
        created_at (datetime): Дата и время сохранения записи в БД.
    """

    station = models.ForeignKey(
        AviationWeatherStation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forecasts",
        verbose_name="Метеостанция",
    )
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="weather_forecasts",
        verbose_name="МПД базирования",
    )
    icao_code = models.CharField(
        max_length=4,
        db_index=True,
        verbose_name="Код ICAO",
        help_text="4-буквенный код ICAO аэродрома",
    )
    issued_at = models.DateTimeField(
        db_index=True,
        verbose_name="Время выпуска (UTC)",
    )
    valid_from = models.DateTimeField(
        db_index=True,
        verbose_name="Действует с (UTC)",
    )
    valid_to = models.DateTimeField(
        db_index=True,
        verbose_name="Действует по (UTC)",
    )
    raw_text = models.TextField(
        verbose_name="Исходная телеграмма TAF",
    )
    forecast_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Расшифрованные периоды (JSON)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Сохранено в системе",
    )

    class Meta:
        verbose_name = "Прогноз погоды (TAF)"
        verbose_name_plural = "Архив прогнозов погоды (TAF)"
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["icao_code", "issued_at"],
                name="uniq_aviation_forecast_icao_issued",
            ),
        ]
        indexes = [
            models.Index(fields=["icao_code", "issued_at"]),
            models.Index(fields=["valid_from", "valid_to"]),
            models.Index(fields=["mpd", "issued_at"]),
            models.Index(fields=["station", "issued_at"]),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление прогноза TAF.

        Returns:
            str: Код ICAO и интервал действия прогноза.
        """
        from_str = self.valid_from.strftime("%d.%m %H:%M") if self.valid_from else "—"
        to_str = self.valid_to.strftime("%d.%m %H:%M") if self.valid_to else "—"
        return f"TAF {self.icao_code} [{from_str} – {to_str} UTC]"

    def is_currently_valid(self) -> bool:
        """Проверяет, действует ли прогноз в текущий момент времени.

        Returns:
            bool: True, если текущее время UTC входит в интервал [valid_from, valid_to].
        """
        now = timezone.now()
        if self.valid_from and self.valid_to:
            return self.valid_from <= now <= self.valid_to
        return False


# Таблица трансляции кодов погодных явлений WMO 4677 в русскоязычное описание
WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Осаждающий иней (туман)",
    51: "Слабая морось",
    53: "Умеренная морось",
    55: "Плотная морось",
    56: "Слабая замерзающая морось",
    57: "Плотная замерзающая морось",
    61: "Слабый дождь",
    63: "Умеренный дождь",
    65: "Сильный дождь",
    66: "Слабый ледяной (замерзающий) дождь",
    67: "Сильный ледяной (замерзающий) дождь",
    71: "Слабый снегопад",
    73: "Умеренный снегопад",
    75: "Сильный снегопад",
    77: "Снежные зерна",
    80: "Слабый ливневый дождь",
    81: "Умеренный ливневый дождь",
    82: "Сильный ливень",
    85: "Слабый снегопад (ливневый)",
    86: "Сильный снегопад (ливневый)",
    95: "Гроза (слабая или умеренная)",
    96: "Гроза с мелким градом",
    99: "Гроза с сильным градом",
}


class CoordinateWeatherForecast(models.Model):
    """Почасовой модельный расчет метеорологических параметров по координатам площадки.

    Хранит расчетные параметры численных моделей атмосферы (ECMWF IFS, GFS, ICON)
    для конкретного места деятельности (МПД) на заданный целевой час (forecast_for).
    Обеспечивает независимый аудит времени прогона модели (model_run_at), срока прогноза (forecast_for)
    и времени сохранения в базу данных (fetched_at).

    Attributes:
        mpd (PlaceProductionActivity): Место производственной деятельности / вертолетная площадка.
        latitude (float): Географическая широта точки запроса в градусах.
        longitude (float): Географическая долгота точки запроса в градусах.
        elevation_msl_m (Optional[float]): Высота рельефа площадки над уровнем моря (MSL, м).
        provider (str): Имя поставщика данных (по умолчанию 'open-meteo').
        model (str): Наименование численной модели атмосферы (например, 'ecmwf_ifs', 'gfs_seamless').
        model_resolution (str): Пространственное разрешение сеточной модели (например, '0.1' ~9-11 км).
        model_run_at (datetime): Дата и время инициализации прогона модели (UTC).
        forecast_for (datetime): Целевой срок действия прогноза (UTC).
        fetched_at (datetime): Дата и время выгрузки записи из внешнего шлюза в БД (UTC).
        temperature (Optional[float]): Расчетная температура воздуха на высоте 2м (°C).
        dew_point (Optional[float]): Расчетная точка росы на высоте 2м (°C).
        relative_humidity (Optional[float]): Относительная влажность воздуха (%).
        surface_pressure_hpa (Optional[float]): Расчетное давление на уровне поверхности площадки (гПа).
        surface_pressure_mmhg (Optional[float]): Расчетное давление на уровне поверхности площадки (мм рт. ст.).
        pressure_msl_hpa (Optional[float]): Расчетное давление, приведенное к уровню моря (гПа).
        pressure_mmhg (Optional[float]): Расчетное давление, приведенное к уровню моря (мм рт. ст.).
        wind_speed (Optional[float]): Скорость приземного ветра на высоте 10м (м/с).
        wind_direction (Optional[int]): Направление ветра в градусах (0-360).
        wind_gust (Optional[float]): Порывы приземного ветра на высоте 10м (м/с).
        cloud_cover_total (Optional[int]): Общее покрытие облачностью (%).
        cloud_cover_low (Optional[int]): Облачность нижнего яруса (%).
        cloud_cover_mid (Optional[int]): Облачность среднего яруса (%).
        cloud_cover_high (Optional[int]): Облачность верхнего яруса (%).
        cloud_base_agl_m (Optional[int]): Высота нижней границы облачности над поверхностью площадки (AGL, м).
        visibility_m (Optional[int]): Расчетная модельная видимость в метрах.
        freezing_level_msl_m (Optional[int]): Высота нулевой изотермы над уровнем моря (MSL, м).
        precipitation_mm (float): Интенсивность осадков (мм/ч).
        precipitation_probability (Optional[float]): Вероятность выпадения осадков (%).
        weather_code (Optional[int]): Код метеоявления по международной классификации WMO 4677.
        model_flight_category (str): Расчетная модельная оценка метеоусловий ('VFR', 'MVFR', 'IFR', 'LIFR').
        nearest_station (Optional[AviationWeatherStation]): Ближайшая опорная метеостанция с METAR.
    """

    FLIGHT_CATEGORIES = (
        ("VFR", "ПВП (VFR) — Расчетные визуальные"),
        ("MVFR", "ОПВП (MVFR) — Расчетные ухудшенные"),
        ("IFR", "ППП (IFR) — Расчетные приборные"),
        ("LIFR", "НППП (LIFR) — Расчетные низкие приборные"),
    )

    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.CASCADE,
        related_name="coordinate_forecasts",
        verbose_name="МПД базирования",
    )
    latitude = models.FloatField(
        verbose_name="Широта точки",
    )
    longitude = models.FloatField(
        verbose_name="Долгота точки",
    )
    elevation_msl_m = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Высота рельефа (MSL, м)",
        help_text="Высота поверхности площадки над уровнем моря (MSL) в метрах",
    )
    provider = models.CharField(
        max_length=50,
        default="open-meteo",
        verbose_name="Провайдер данных",
    )
    model = models.CharField(
        max_length=50,
        default="ecmwf_ifs",
        verbose_name="Модель атмосферы",
        help_text="Идентификатор численной модели (например, ecmwf_ifs, gfs_seamless, icon_seamless)",
    )
    model_resolution = models.CharField(
        max_length=20,
        default="0.1",
        blank=True,
        verbose_name="Разрешение сетки",
    )
    model_run_at = models.DateTimeField(
        db_index=True,
        verbose_name="Инициализация прогона (UTC)",
        help_text="Время запуска/прогона численной модели атмосферы",
    )
    forecast_for = models.DateTimeField(
        db_index=True,
        verbose_name="Срок прогноза (UTC)",
        help_text="Целевой час, на который рассчитаны метеопараметры",
    )
    fetched_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Загружено в БД (UTC)",
    )
    temperature = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Температура 2м (°C)",
    )
    dew_point = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Точка росы 2м (°C)",
    )
    relative_humidity = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Относительная влажность (%)",
    )
    surface_pressure_hpa = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление поверхности (гПа)",
        help_text="Расчетное атмосферное давление на уровне поверхности площадки",
    )
    surface_pressure_mmhg = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление поверхности (мм рт. ст.)",
    )
    pressure_msl_hpa = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление MSL (гПа)",
        help_text="Атмосферное давление, приведенное к среднему уровню моря (QNH/MSLP)",
    )
    pressure_mmhg = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Давление MSL (мм рт. ст.)",
    )
    wind_speed = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Скорость ветра 10м (м/с)",
    )
    wind_direction = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Направление ветра 10м (°)",
    )
    wind_gust = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Порывы ветра 10м (м/с)",
    )
    cloud_cover_total = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Общая облачность (%)",
    )
    cloud_cover_low = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Нижняя облачность (%)",
    )
    cloud_cover_mid = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Средняя облачность (%)",
    )
    cloud_cover_high = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Верхняя облачность (%)",
    )
    cloud_base_agl_m = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Высота НГО (AGL, м)",
        help_text="Высота нижней границы облачности над поверхностью площадки (AGL) в метрах",
    )
    visibility_m = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Расчетная видимость (м)",
    )
    freezing_level_msl_m = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Высота нулевой изотермы (MSL, м)",
        help_text="Высота изотермы 0°C над средним уровнем моря (MSL)",
    )
    precipitation_mm = models.FloatField(
        default=0.0,
        verbose_name="Осадки (мм/ч)",
    )
    precipitation_probability = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Вероятность осадков (%)",
    )
    weather_code = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Код погоды WMO",
        help_text="Код метеорологического явления по стандарту WMO 4677",
    )
    model_flight_category = models.CharField(
        max_length=10,
        choices=FLIGHT_CATEGORIES,
        default="VFR",
        verbose_name="Модельная оценка условий",
        help_text="Ориентировочная модельная категория условий полета (VFR/MVFR/IFR/LIFR)",
    )
    nearest_station = models.ForeignKey(
        AviationWeatherStation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referenced_forecasts",
        verbose_name="Опорная метеостанция",
    )

    class Meta:
        verbose_name = "Координатный прогноз погоды"
        verbose_name_plural = "Архив координатных прогнозов"
        ordering = ["-forecast_for"]
        constraints = [
            models.UniqueConstraint(
                fields=["mpd", "forecast_for", "model"],
                name="uniq_mpd_forecast_model",
            ),
        ]
        indexes = [
            models.Index(fields=["mpd", "forecast_for"]),
            models.Index(fields=["forecast_for"]),
            models.Index(fields=["model_run_at"]),
            models.Index(fields=["nearest_station", "forecast_for"]),
        ]

    def __str__(self) -> str:
        """Строковое представление координатного прогноза.

        Returns:
            str: Наименование МПД, целевой час прогноза и модель.
        """
        fc_str = self.forecast_for.strftime("%d.%m %H:%M") if self.forecast_for else "—"
        return f"{self.mpd.name} [{fc_str} UTC] — {self.model} ({self.model_flight_category})"

    @property
    def weather_description(self) -> str:
        """Возвращает русскоязычное описание метеоявления по WMO коду.

        Returns:
            str: Текстовое описание явления (например, 'Слабый снег', 'Туман').
        """
        if self.weather_code is None:
            return "Без осадков"
        return WMO_WEATHER_CODES.get(self.weather_code, f"Код WMO {self.weather_code}")

    def get_flight_category_color(self) -> str:
        """Возвращает цвет бейджа летных условий для UI.

        Returns:
            str: Bootstrap/CSS класс цвета ('success', 'info', 'danger', 'dark').
        """
        mapping = {
            "VFR": "success",
            "MVFR": "info",
            "IFR": "danger",
            "LIFR": "dark",
        }
        return mapping.get(self.model_flight_category, "secondary")

    def get_flight_category_name_ru(self) -> str:
        """Возвращает русское обозначение расчетных условий.

        Returns:
            str: ПВП, ОПВП, ППП или НППП.
        """
        mapping = {
            "VFR": "ПВП (модель)",
            "MVFR": "ОПВП (модель)",
            "IFR": "ППП (модель)",
            "LIFR": "НППП (модель)",
        }
        return mapping.get(self.model_flight_category, self.model_flight_category)

    def get_wind_display(self) -> str:
        """Возвращает форматированное описание ветра.

        Returns:
            str: Направление и скорость с порывами (например, '280° 5 м/с (порывы 9)').
        """
        if self.wind_speed is None or self.wind_speed == 0:
            return "Штиль (0 м/с)"
        dir_str = "—" if self.wind_direction is None else f"{self.wind_direction:03d}°"
        spd_str = f"{self.wind_speed:.0f} м/с"
        gust_str = f" (порывы {self.wind_gust:.0f} м/с)" if self.wind_gust else ""
        return f"{dir_str} {spd_str}{gust_str}"

    def get_visibility_display(self) -> str:
        """Возвращает форматированное значение видимости.

        Returns:
            str: Видимость в км/метрах.
        """
        if self.visibility_m is None:
            return "—"
        if self.visibility_m >= 10000:
            return "≥ 10 км"
        if self.visibility_m >= 1000:
            return f"{self.visibility_m / 1000:.1f} км"
        return f"{self.visibility_m} м"

    def get_cloud_display(self) -> str:
        """Возвращает форматированное значение облачности и НГО.

        Returns:
            str: Общая облачность и высота НГО (AGL, м).
        """
        cov_str = f"{self.cloud_cover_total}%" if self.cloud_cover_total is not None else ""
        base_str = f"НГО {self.cloud_base_agl_m} м AGL" if self.cloud_base_agl_m is not None else "Без потолка"
        if cov_str and base_str:
            return f"{cov_str} ({base_str})"
        return cov_str or base_str







