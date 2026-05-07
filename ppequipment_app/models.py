from django.db import models
from django.urls import reverse
from django.utils.text import slugify


# ─── Справочники ─────────────────────────────────────────────────────────────

class DestLit(models.Model):
    """Справочник «Назн-лит» (журнал, суд. док, другая и т.д.)"""
    name = models.CharField("Название", max_length=50, unique=True)

    class Meta:
        db_table = "ppequipment_dest_lit"
        verbose_name = "Назн-лит"
        verbose_name_plural = "Назн-лит (справочник)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class LocationRef(models.Model):
    """Справочник местоположений (ИАС, Мячково, Волгоград и т.д.)"""
    name = models.CharField("Местоположение", max_length=70, unique=True)

    class Meta:
        db_table = "ppequipment_location_ref"
        verbose_name = "Местоположение (справочник)"
        verbose_name_plural = "Местоположения (справочник)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AircraftType(models.Model):
    """Справочник типов ВС (Ми-8, Як-40, Робинсон R-66 и т.д.)"""
    name = models.CharField("Тип ВС", max_length=50, unique=True)

    class Meta:
        db_table = "ppequipment_aircraft_type"
        verbose_name = "Тип ВС"
        verbose_name_plural = "Типы ВС (справочник)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ContractorStatus(models.Model):
    """Справочник статусов контр-раб (раб, архив, уничт, конт и т.д.)"""
    name = models.CharField("Статус", max_length=20, unique=True)

    class Meta:
        db_table = "ppequipment_contractor_status"
        verbose_name = "Статус контр-раб"
        verbose_name_plural = "Статусы контр-раб (справочник)"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ─── Основные модели ─────────────────────────────────────────────────────────

class Equipment(models.Model):
    """Справочник оборудования / ТМЦ (таблица «наименование»)"""
    number = models.AutoField("Номер", primary_key=True)
    name = models.TextField("Наименование")
    aircraft_type = models.ForeignKey(
        AircraftType,
        on_delete=models.SET_NULL,
        related_name="equipment",
        verbose_name="Тип ВС",
        blank=True, null=True,
    )
    edition = models.TextField("Издание", blank=True, null=True)
    issue = models.CharField("Выпуск", max_length=4, blank=True, null=True)
    approved_by = models.TextField("Кем утверждён", blank=True, null=True)
    approval_date = models.DateField("Дата утверждения", blank=True, null=True)
    priority = models.IntegerField("Приоритет", blank=True, null=True)
    dest_lit = models.ForeignKey(
        DestLit,
        on_delete=models.SET_NULL,
        related_name="equipment",
        verbose_name="Назн-лит",
        blank=True, null=True,
    )

    class Meta:
        db_table = "ppequipment_equipment"
        verbose_name = "Производственно техническая документация"
        verbose_name_plural = "Производственно техническая документация"
        ordering = ["number"]
        indexes = [models.Index(fields=["number"], name="equip_number_idx")]

    def __str__(self):
        return f"{self.number} — {self.name}"


class Location(models.Model):
    """Связь оборудования с местоположением (таблица «где»)"""
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="locations",
        db_column="номер",
        verbose_name="ПТД",
    )
    location_ref = models.ForeignKey(
        LocationRef,
        on_delete=models.CASCADE,
        related_name="location_entries",
        verbose_name="Местоположение",
    )

    class Meta:
        db_table = "ppequipment_location"
        verbose_name = "Местоположение ПТД"
        verbose_name_plural = "Местоположения ПТД"
        constraints = [
            models.UniqueConstraint(fields=["equipment", "location_ref"], name="uq_equip_location")
        ]
        indexes = [models.Index(fields=["equipment"], name="loc_equip_idx")]

    def __str__(self):
        return f"{self.equipment} → {self.location_ref}"


class Verification(models.Model):
    """Данные инвентаризации / сверки (таблица «сверка»)"""
    location_ref = models.ForeignKey(
        LocationRef,
        on_delete=models.SET_NULL,
        related_name="verifications",
        verbose_name="Где",
        blank=True, null=True,
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="verifications",
        db_column="номер",
        verbose_name="ПТД",
        blank=True, null=True,
    )
    inventory_number = models.CharField("Инвентарный №", max_length=50, primary_key=True)
    contractor_status = models.ForeignKey(
        ContractorStatus,
        on_delete=models.SET_NULL,
        related_name="verifications",
        verbose_name="Контр-раб",
        blank=True, null=True,
    )
    last_verification_date = models.DateField("Последняя сверка", blank=True, null=True)
    notes = models.TextField("Примечание", blank=True, null=True)
    vs_number = models.CharField("№ ВС", max_length=5, blank=True, null=True)
    end_date = models.DateField("Дата оконч.", blank=True, null=True)
    is_destroyed = models.BooleanField("Уничтожен", default=False)
    slug = models.SlugField(max_length=150, blank=True, editable=False)

    class Meta:
        db_table = "ppequipment_verification"
        verbose_name = "Сверка"
        verbose_name_plural = "Сверки"
        indexes = [models.Index(fields=["equipment"], name="verif_equip_idx")]

    def __str__(self):
        return f"Инв. {self.inventory_number} — {self.equipment}"

    def get_slug(self):
        """Генерирует безопасный slug из inventory_number"""
        # Заменяем / на - и другие проблемные символы
        safe_string = self.inventory_number.replace('/', '-').replace('р', 'p')
        return slugify(safe_string)

    def save(self, *args, **kwargs):
        """Автоматически создаем slug при сохранении"""
        if not self.slug:  # Если slug пустой или None
            safe_string = self.inventory_number.replace('/', '-').replace('р', 'p')
            base_slug = slugify(safe_string)
            self.slug = base_slug

            # Проверка уникальности slug
            counter = 1
            while Verification.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('ppequipment_app:verification_detail', kwargs={'slug': self.slug})


class VerificationDate(models.Model):
    """Даты сверок (таблица «Таблица дата сверки»)"""
    verification_date = models.DateField("Дата сверки", blank=True, null=True)

    class Meta:
        db_table = "ppequipment_verification_date"
        verbose_name = "Дата сверки"
        verbose_name_plural = "Даты сверок"

    def __str__(self):
        return str(self.verification_date) if self.verification_date else "—"
