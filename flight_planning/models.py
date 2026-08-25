# flight_planning/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from contracts_app.models import Estate


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

