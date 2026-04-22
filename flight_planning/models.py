# flight_planning/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity


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
