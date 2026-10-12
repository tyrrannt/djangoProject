import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from django.db import models, transaction
from django.utils import timezone

from administration_app.utils import format_name_initials
from contracts_app.models import Estate
from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity


# Create your models here.
class NomenclatureUnit(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название единицы измерения")
    short_name = models.CharField(max_length=10, verbose_name="Краткое название")

    def __str__(self):
        return f"{self.name} ({self.short_name})"

    class Meta:
        verbose_name = "Единица измерения"
        verbose_name_plural = "Единицы измерения"

class Grade(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название градации")
    description = models.TextField(blank=True, verbose_name="Описание")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Класс годности"
        verbose_name_plural = "Классы годности"

class NomenclatureGroup(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название группы")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Родительская группа")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"

class Nomenclature(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    group = models.ForeignKey('NomenclatureGroup', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Группа")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Количество")
    unit = models.ForeignKey('NomenclatureUnit', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Единица измерения")

    # Дополнительные свойства
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="Серийный номер")
    year_of_manufacture = models.DateField(null=True, blank=True, verbose_name="Год выпуска")
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Вес")
    dimensions = models.CharField(max_length=100, blank=True, verbose_name="Размеры")
    grade = models.ForeignKey('Grade', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Класс годности")

    # Связи с местом нахождения и имуществом
    location = models.ForeignKey(PlaceProductionActivity, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name="Место нахождения")
    estate = models.ForeignKey(Estate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Имущество")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Номенклатура"
        verbose_name_plural = "Номенклатура"

class WayBill(models.Model):
    class Meta:
        verbose_name = "Транспортная накладная"
        verbose_name_plural = "Транспортные накладные"
        ordering = ["-date_of_creation"]

    STATES = (
        ("0", "Не обработана"),
        ("1", "Обработана"),
        ('2', "Отправлена"),
        ("3", "Принята"),
        ("4", "Отклонена"),
    )

    URGENCY_CHOICES = (
        ("0", "Не срочно"),
        ("1", "Срочно"),
        ("2", "Очень срочно"),
    )

    document_number = models.CharField(max_length=37, verbose_name="Номер документа", default=uuid.uuid4)
    document_date = models.DateField(verbose_name="Дата документа")
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Куда",
                                           on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="way_bill_place_of_departure")
    content = models.TextField(verbose_name="Содержание", default='')
    comment = models.CharField(verbose_name="Комментарий", default='', max_length=300)
    place_division = models.ForeignKey(Division, verbose_name="Подразделение", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    sender = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Инициатор",
                               on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_sender")
    state = models.CharField(max_length=100, verbose_name="Состояние", choices=STATES, default="0")
    responsible = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Получатель",
                                    on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="way_bill_responsible")
    date_of_creation = models.DateField(verbose_name="Дата и время создания",
                                        auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")
    urgency = models.CharField(max_length=100, verbose_name="Срочность", choices=URGENCY_CHOICES, default="0")
    package_number = models.ForeignKey('Package', verbose_name="Посылка", on_delete=models.SET_NULL, null=True,
                                       blank=True)

    def __str__(self):
        return self.content

    def get_data(self):
        """
        Получает данные из экземпляра ReportCard.

        :return: словарь, содержащий следующие данные:
            - "pk": первичный ключ экземпляра ReportCard.
            - "employee": форматированные инициалы имени сотрудника.
            - "report_card_day": день табеля в формате "ДД.ММ.ГГГГ"
            - "start_time": время начала в формате "ЧЧ:ММ"
            - "end_time": время окончания в формате "ЧЧ:ММ"
            - "reason_adjustment": причина корректировки.
            - "record_type": отображение типа записи.
        """
        return {
            "pk": self.pk,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "place_of_departure": self.place_of_departure.name,
            "content": self.content,
            "comment": self.comment,
            "place_division": self.place_division.name,
            "sender": format_name_initials(self.sender.title),
            "state": self.get_state_display(),
            "responsible": format_name_initials(self.responsible.title),
            "date_of_creation": f"{self.date_of_creation:%d.%m.%Y} г.",
            "executor": format_name_initials(self.executor.title),
            "urgency": self.get_urgency_display(),
        }


# ==============================================================================
# ВНУТРЕННЯЯ ЛОГИСТИКА: РЕЙСЫ НА МПД, ПОСЫЛКИ, ОПИСЬ И ПРИЕМКА
# ==============================================================================

class ShipmentCounter(models.Model):
    """Потокобезопасный счетчик регистрационных номеров для рейсов и посылок.

    Attributes:
        year (PositiveIntegerField): Календарный год регистрации.
        counter_type (CharField): Тип счетчика ('TRIP' для рейсов, 'PACKAGE' для посылок).
        last_number (PositiveIntegerField): Последний выданный порядковый номер.
    """

    year = models.PositiveIntegerField(verbose_name="Календарный год")
    counter_type = models.CharField(max_length=20, verbose_name="Тип счетчика")
    last_number = models.PositiveIntegerField(default=0, verbose_name="Последний номер")

    class Meta:
        verbose_name = "Счетчик номеров логистики"
        verbose_name_plural = "Счетчики номеров логистики"
        constraints = [
            models.UniqueConstraint(fields=["year", "counter_type"], name="unique_shipment_counter_year_type")
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление счетчика."""
        return f"{self.counter_type} ({self.year}): {self.last_number}"

    @classmethod
    def generate_number(cls, counter_type: str, year: Optional[int] = None) -> str:
        """Транзакционно генерирует следующий уникальный номер с блокировкой строки.

        Args:
            counter_type (str): Тип счетчика ('TRIP' или 'PACKAGE').
            year (Optional[int]): Год нумерации (по умолчанию текущий).

        Returns:
            str: Сгенерированный строковый номер вида 'РЕЙС-2026/0001' или 'ПКГ-2026/00001'.
        """
        if year is None:
            year = timezone.now().year

        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                year=year,
                counter_type=counter_type,
                defaults={"last_number": 0},
            )
            counter.last_number += 1
            counter.save(update_fields=["last_number"])

            if counter_type == "TRIP":
                return f"РЕЙС-{year}/{counter.last_number:04d}"
            else:
                return f"ПКГ-{year}/{counter.last_number:05d}"


class ShipmentTrip(models.Model):
    """Заявка на рейс / Маршрутный лист автомобиля на МПД.

    Описывает рейс машины (собственной или наемной), которая может заезжать
    на несколько МПД для доставки и забора посылок.

    Attributes:
        trip_number (CharField): Уникальный номер рейса вида РЕЙС-2026/0001.
        planned_date (DateField): Плановая дата выезда.
        actual_departure_at (DateTimeField): Фактическое время отправления.
        actual_completed_at (DateTimeField): Фактическое время завершения рейса.
        origin_point (ForeignKey): Пункт отправления (база или МПД).
        origin_custom (CharField): Название пункта отправления текстом (по умолчанию Москва).
        vehicle_type (CharField): Тип используемого транспорта.
        vehicle_model (CharField): Марка и модель транспортного средства.
        vehicle_reg_number (CharField): Государственный регистрационный номер ТС.
        driver_user (ForeignKey): Водитель (если является штатным сотрудником).
        driver_name (CharField): ФИО водителя / экспедитора / перевозчика.
        driver_phone (CharField): Контактный телефон водителя.
        dispatcher (ForeignKey): Логист/диспетчер, сформировавший заявку.
        status (CharField): Текущий статус рейса.
        comment (TextField): Маршрутные указания и примечания.
        created_at (DateTimeField): Время создания записи.
        updated_at (DateTimeField): Время последнего обновления.
    """

    class Status(models.TextChoices):
        """Статусы жизненного цикла рейса."""
        PLANNING = "PLANNING", "Планируется (сбор заявок)"
        CONSOLIDATED = "CONSOLIDATED", "Скомплектован (погрузка)"
        IN_TRANSIT = "IN_TRANSIT", "В пути"
        ARRIVED = "ARRIVED", "Прибыл в пункт назначения"
        COMPLETED = "COMPLETED", "Завершен"
        CANCELLED = "CANCELLED", "Отменен"

    class VehicleType(models.TextChoices):
        """Типы транспортных средств и способов доставки."""
        COMPANY_CAR = "COMPANY_CAR", "Собственный автотранспорт АК"
        HIRED_CAR = "HIRED_CAR", "Наемный автотранспорт"
        AIRCRAFT = "AIRCRAFT", "Авиарейс (борт АК)"
        CARRIER = "CARRIER", "Транспортная компания (СДЭК/ДЛ)"
        COURIER = "COURIER", "Курьер / Сотрудник (поезд/пеший)"

    trip_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Номер рейса"
    )
    planned_date = models.DateField(verbose_name="Плановая дата отправки")
    actual_departure_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое время выезда"
    )
    actual_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое время завершения"
    )
    origin_point = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips_departed",
        verbose_name="Пункт отправления (МПД/База)"
    )
    origin_custom = models.CharField(
        max_length=255,
        blank=True,
        default="Центральный склад (Москва)",
        verbose_name="Пункт отправления (наименование)"
    )
    vehicle_type = models.CharField(
        max_length=30,
        choices=VehicleType.choices,
        default=VehicleType.COMPANY_CAR,
        verbose_name="Тип транспорта"
    )
    vehicle_model = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Марка / Модель ТС"
    )
    vehicle_reg_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Гос. номер ТС"
    )
    driver_user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips_as_driver",
        verbose_name="Водитель (сотрудник)"
    )
    driver_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="ФИО водителя / экспедитора"
    )
    driver_phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Телефон водителя"
    )
    dispatcher = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="dispatched_trips",
        verbose_name="Диспетчер / Логист"
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PLANNING,
        db_index=True,
        verbose_name="Статус рейса"
    )
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name="Маршрут и примечания"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Рейс / Маршрутный лист"
        verbose_name_plural = "Рейсы / Маршрутные листы"
        ordering = ["-planned_date", "-created_at"]

    def __str__(self) -> str:
        """Возвращает строковое представление рейса."""
        return f"{self.trip_number} от {self.planned_date.strftime('%d.%m.%Y')} ({self.get_status_display()})"

    @property
    def origin_display(self) -> str:
        """Возвращает наименование пункта отправления рейса."""
        if self.origin_point:
            return self.origin_point.name
        return self.origin_custom or "База / Склад (Москва)"

    @property
    def driver_display(self) -> str:
        """Возвращает форматированное наименование водителя с приоритетом профиля."""
        if self.driver_user:
            return self.driver_user.title or self.driver_user.get_full_name() or self.driver_user.username
        return self.driver_name or "Не назначен"

    @property
    def vehicle_display(self) -> str:
        """Возвращает текстовое описание автомобиля."""
        parts = [p for p in [self.vehicle_model, self.vehicle_reg_number] if p]
        return " ".join(parts) if parts else self.get_vehicle_type_display()

    @property
    def packages_count(self) -> int:
        """Возвращает количество прикрепленных к рейсу посылок."""
        return self.packages.count()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Автоматически генерирует номер рейса при создании."""
        if not self.trip_number:
            year = self.planned_date.year if self.planned_date else timezone.now().year
            self.trip_number = ShipmentCounter.generate_number("TRIP", year=year)
        super().save(*args, **kwargs)


class TripStop(models.Model):
    """Точка маршрута / остановка рейса на конкретном МПД.

    Attributes:
        trip (ForeignKey): Ссылка на рейс ShipmentTrip.
        mpd (ForeignKey): МПД назначения из hrdepartment_app.PlaceProductionActivity.
        stop_order (PositiveIntegerField): Порядковый номер заезда по маршруту.
        planned_arrival_date (DateField): Плановая дата прибытия на точку.
        status (CharField): Статус прохождения точки.
        comment (CharField): Примечание к остановке.
    """

    class Status(models.TextChoices):
        """Статусы остановки на МПД."""
        PENDING = "PENDING", "Ожидает прибытия"
        ARRIVED = "ARRIVED", "Прибыл на точку"
        DISCHARGED = "DISCHARGED", "Разгружен / Приемка завершена"
        SKIPPED = "SKIPPED", "Пропущен"

    trip = models.ForeignKey(
        ShipmentTrip,
        on_delete=models.CASCADE,
        related_name="stops",
        verbose_name="Рейс"
    )
    mpd = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.PROTECT,
        related_name="trip_stops",
        verbose_name="МПД назначения"
    )
    stop_order = models.PositiveIntegerField(default=1, verbose_name="Порядок заезда")
    planned_arrival_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Плановая дата прибытия"
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус точки"
    )
    comment = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Примечание к остановке"
    )

    class Meta:
        verbose_name = "Остановка рейса (МПД)"
        verbose_name_plural = "Остановки рейса (МПД)"
        ordering = ["trip", "stop_order"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "mpd"], name="unique_trip_mpd_stop")
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление остановки."""
        return f"{self.trip.trip_number} — #{self.stop_order}: {self.mpd.name}"


class Package(models.Model):
    """Учетная карточка посылки / внутреннего грузового места.

    Обеспечивает сквозной учет отправлений как из офиса на МПД, так и обратно
    с МПД на базу, а также между различными МПД компании.

    Attributes:
        track_number (CharField): Уникальный трек-номер посылки вида ПКГ-2026/00001.
        number_of_dispatch (CharField): Устаревшее поле номера для обратной совместимости.
        trip (ForeignKey): Привязанный рейс автомобиля ShipmentTrip.
        origin (ForeignKey): МПД отправления (null, если отправка с центральной базы).
        origin_custom (CharField): Название пункта отправления текстом.
        destination (ForeignKey): МПД назначения.
        place_of_dispatch (ForeignKey): Алиас назначения для обратной совместимости.
        sender (ForeignKey): Инициатор отправки (DataBaseUser).
        sender_division (ForeignKey): Подразделение отправителя.
        recipient (ForeignKey): Назначенный получатель на МПД.
        status (CharField): Статус жизненного цикла посылки.
        urgency (CharField): Приоритет срочности.
        package_type (CharField): Тип тары/упаковки груза.
        description (TextField): Краткое описание содержимого / назначение.
        weight_kg (DecimalField): Вес посылки в килограммах.
        places_count (PositiveIntegerField): Количество физических мест.
        shipped_at (DateTimeField): Время фактической погрузки и отправки.
        received_at (DateTimeField): Время фактической приемки на МПД.
        received_by (ForeignKey): Сотрудник, фактически принявший посылку.
        reception_comment (TextField): Итоговый акт/замечания при приемке.
        has_discrepancy (BooleanField): Флаг наличия недостачи/дефектов/брака.
        qr_code_data (CharField): Данные для генерации QR-кода быстрой приемки.
        executor (ForeignKey): Назначенный исполнитель (обратная совместимость).
        type_of_dispatch (CharField): Способ отправки (обратная совместимость).
        date_of_creation (DateField): Дата создания записи.
        date_of_dispatch (DateField): Дата отправки (обратная совместимость).
        created_at (DateTimeField): Точная дата и время создания.
        updated_at (DateTimeField): Дата и время последнего обновления.
    """

    class Meta:
        verbose_name = "Посылка"
        verbose_name_plural = "Посылки"
        ordering = ["-created_at", "-date_of_creation"]

    class Status(models.TextChoices):
        """Статусы жизненного цикла посылки."""
        DRAFT = "DRAFT", "Черновик"
        AWAITING_SHIPMENT = "AWAITING_SHIPMENT", "Готова (ожидает рейс)"
        ASSIGNED_TO_TRIP = "ASSIGNED_TO_TRIP", "Включена в рейс"
        IN_TRANSIT = "IN_TRANSIT", "В пути"
        DELIVERED_AT_MPD = "DELIVERED_AT_MPD", "Доставлена на МПД (ожидает приемки)"
        RECEIVED_FULL = "RECEIVED_FULL", "Принята полностью"
        RECEIVED_WITH_DISCREPANCY = "RECEIVED_WITH_DISCREPANCY", "Принята с расхождениями"
        REJECTED = "REJECTED", "Отклонена / Не принята"
        RETURNED = "RETURNED", "Возврат отправителю"

    class Urgency(models.TextChoices):
        """Срочность доставки посылки."""
        NORMAL = "NORMAL", "Обычная"
        URGENT = "URGENT", "Срочно"
        CRITICAL = "CRITICAL", "Критически срочно (AOG / Простой ВС)"

    class PackageType(models.TextChoices):
        """Вид упаковки и тары груза."""
        BOX = "BOX", "Коробка"
        BAG = "BAG", "Мешок"
        CONTAINER = "CONTAINER", "Контейнер / Ящик"
        PALLET = "PALLET", "Паллета"
        DOCUMENTS = "DOCUMENTS", "Пакет с документами"
        OVERSIZED = "OVERSIZED", "Крупногабарит / Нестандарт"

    TYPE_OF_SENDING = (
        ("0", "Логистическая компания"),
        ("1", "Водитель"),
        ("2", "Сотрудник"),
    )

    # Идентификаторы
    track_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Трек-номер"
    )
    number_of_dispatch = models.CharField(
        max_length=50,
        default="",
        blank=True,
        verbose_name="Номер посылки (legacy)"
    )

    # Привязка к рейсу
    trip = models.ForeignKey(
        ShipmentTrip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packages",
        verbose_name="Рейс машины"
    )

    # Маршрут: Откуда -> Куда
    origin = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packages_origin",
        verbose_name="Пункт отправления (МПД)"
    )
    origin_custom = models.CharField(
        max_length=255,
        blank=True,
        default="Центральный склад (Москва)",
        verbose_name="Иной пункт отправления"
    )
    destination = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="packages_destination",
        verbose_name="Пункт назначения (МПД)"
    )
    place_of_dispatch = models.ForeignKey(
        PlaceProductionActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_packages",
        verbose_name="Точка назначения (legacy)"
    )

    # Участники процесса
    sender = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="packages_as_sender",
        verbose_name="Отправитель"
    )
    sender_division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Подразделение отправителя"
    )
    recipient = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packages_as_recipient",
        verbose_name="Назначенный получатель на МПД"
    )
    executor = models.ForeignKey(
        DataBaseUser,
        max_length=100,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispatch_executor",
        verbose_name="Исполнитель (legacy)"
    )

    # Статусы и характеристики
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус посылки"
    )
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.NORMAL,
        verbose_name="Срочность"
    )
    package_type = models.CharField(
        max_length=30,
        choices=PackageType.choices,
        default=PackageType.BOX,
        verbose_name="Вид упаковки"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Краткое описание груза"
    )
    weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Вес (кг)"
    )
    places_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Количество мест"
    )
    type_of_dispatch = models.CharField(
        max_length=100,
        choices=TYPE_OF_SENDING,
        default="0",
        verbose_name="Тип отправки (legacy)"
    )

    # Временные метки и фиксация приемки
    shipped_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое время отправки"
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Фактическое время приемки"
    )
    received_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packages_received_person",
        verbose_name="Фактически принял на МПД"
    )
    reception_comment = models.TextField(
        blank=True,
        default="",
        verbose_name="Акт / замечания при приемке"
    )
    has_discrepancy = models.BooleanField(
        default=False,
        verbose_name="Есть расхождения / недостача"
    )
    qr_code_data = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Данные QR-кода"
    )

    date_of_creation = models.DateField(
        auto_now_add=True,
        verbose_name="Дата создания (legacy)"
    )
    date_of_dispatch = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата отправки (legacy)"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата и время создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата и время обновления"
    )

    def __str__(self) -> str:
        """Возвращает строковое представление посылки."""
        num = self.track_number or self.number_of_dispatch or f"ID:{self.pk}"
        dest = self.destination.name if self.destination else (self.place_of_dispatch.name if self.place_of_dispatch else "МПД не указан")
        return f"{num} → {dest} ({self.get_status_display()})"

    @property
    def origin_display(self) -> str:
        """Возвращает наименование пункта отправления."""
        if self.origin:
            return self.origin.name
        return self.origin_custom or "База / Склад (Москва)"

    @property
    def destination_display(self) -> str:
        """Возвращает наименование пункта назначения."""
        if self.destination:
            return self.destination.name
        if self.place_of_dispatch:
            return self.place_of_dispatch.name
        return "Не указан"

    @property
    def sender_display(self) -> str:
        """Возвращает форматированное наименование отправителя."""
        if self.sender:
            return self.sender.title or self.sender.get_full_name() or self.sender.username
        return "Не указан"

    @property
    def recipient_display(self) -> str:
        """Возвращает форматированное наименование получателя на МПД."""
        if self.recipient:
            return self.recipient.title or self.recipient.get_full_name() or self.recipient.username
        return "Ответственный сотрудник МПД"

    @property
    def received_by_display(self) -> str:
        """Возвращает сотрудника, фактически принявшего посылку."""
        if self.received_by:
            return self.received_by.title or self.received_by.get_full_name() or self.received_by.username
        return "—"

    @property
    def items_count(self) -> int:
        """Возвращает количество позиций в описи вложения."""
        return self.items.count()

    @property
    def delivery_duration_hours(self) -> Optional[float]:
        """Возвращает фактическую длительность доставки в часах."""
        if self.shipped_at and self.received_at:
            delta = self.received_at - self.shipped_at
            return round(delta.total_seconds() / 3600.0, 1)
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Автоматически генерирует трек-номер и синхронизирует поля обратной совместимости."""
        if not self.track_number:
            year = timezone.now().year
            self.track_number = ShipmentCounter.generate_number("PACKAGE", year=year)

        if not self.number_of_dispatch:
            self.number_of_dispatch = self.track_number

        # Синхронизация полей назначения
        if self.destination and not self.place_of_dispatch:
            self.place_of_dispatch = self.destination
        elif self.place_of_dispatch and not self.destination:
            self.destination = self.place_of_dispatch

        if not self.qr_code_data:
            self.qr_code_data = f"BARKOL-PKG:{self.track_number}"

        super().save(*args, **kwargs)

    def get_data(self) -> Dict[str, Any]:
        """Сохраняет обратную совместимость для AJAX-сериализатора get_data()."""
        dest_name = self.destination_display
        exec_name = format_name_initials(self.executor.title) if self.executor else (
            format_name_initials(self.sender.title) if self.sender else ""
        )
        dispatch_dt = self.shipped_at.date() if self.shipped_at else (
            self.date_of_dispatch or self.created_at.date()
        )
        return {
            "pk": self.pk,
            "date_of_dispatch": f"{dispatch_dt:%d.%m.%Y} г.",
            "number_of_dispatch": self.track_number or self.number_of_dispatch,
            "place_of_dispatch": dest_name,
            "executor": exec_name,
            "type_of_dispatch": self.get_status_display(),
        }


class PackageItem(models.Model):
    """Позиция в описи вложения посылки.

    Описывает конкретный предмет/деталь/ТМЦ с возможностью построчной сверки
    при приемке на МПД.

    Attributes:
        package (ForeignKey): Ссылка на родительскую посылку Package.
        item_order (PositiveIntegerField): Порядковый номер строки в описи.
        name (CharField): Наименование ТМЦ / запчасти / документа.
        part_number (CharField): Каталожный / чертежный номер (P/N).
        serial_number (CharField): Заводской / серийный номер (S/N).
        quantity_sent (DecimalField): Количество отправленных единиц.
        unit (CharField): Единица измерения (шт., компл., кг, упак.).
        sender_comment (CharField): Примечание или назначение отправителя.
        quantity_received (DecimalField): Фактически принятое количество на МПД.
        item_status (CharField): Статус сверки позиции при приемке.
        discrepancy_comment (TextField): Подробные замечания при расхождении.
    """

    class ItemStatus(models.TextChoices):
        """Статусы позиции при приемочном контроле на МПД."""
        PENDING = "PENDING", "Ожидает приемки"
        ACCEPTED = "ACCEPTED", "Принято без замечаний"
        SHORTAGE = "SHORTAGE", "Недостача (не вложено)"
        DAMAGED = "DAMAGED", "Повреждено / дефект"
        EXCESS = "EXCESS", "Излишек"

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Посылка"
    )
    item_order = models.PositiveIntegerField(default=1, verbose_name="№ п/п")
    name = models.CharField(
        max_length=300,
        verbose_name="Наименование ТМЦ / груза"
    )
    part_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Каталожный номер / P/N"
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Заводской номер / S/N"
    )
    quantity_sent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="Отправлено"
    )
    unit = models.CharField(
        max_length=50,
        default="шт.",
        verbose_name="Ед. изм."
    )
    sender_comment = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Примечание отправителя"
    )
    quantity_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Принято фактически"
    )
    item_status = models.CharField(
        max_length=30,
        choices=ItemStatus.choices,
        default=ItemStatus.PENDING,
        verbose_name="Статус при приемке"
    )
    discrepancy_comment = models.TextField(
        blank=True,
        default="",
        verbose_name="Замечания принимающего"
    )

    class Meta:
        verbose_name = "Позиция описи посылки"
        verbose_name_plural = "Позиции описи посылки"
        ordering = ["package", "item_order"]

    def __str__(self) -> str:
        """Возвращает строковое представление позиции описи."""
        return f"#{self.item_order}. {self.name} ({self.quantity_sent} {self.unit})"

    @property
    def has_issue(self) -> bool:
        """Возвращает True, если по позиции зафиксирована недостача или дефект."""
        return self.item_status in [self.ItemStatus.SHORTAGE, self.ItemStatus.DAMAGED]


def image_directory_path(instance: "PackageImage", filename: str) -> str:
    """Генерирует структурированный путь сохранения фотографий посылок."""
    now = timezone.now()
    pkg_id = instance.package_id or "general"
    return f"logist/PKG/{now.year}/{now.month:02d}/{pkg_id}/{filename}"


class PackageImage(models.Model):
    """Фотография к посылке (при упаковке отправителем или при приемке на МПД).

    Attributes:
        date_of_creation (DateField): Дата загрузки (legacy).
        image (ImageField): Файл фотографии.
        caption (CharField): Описание / подпись к снимку.
        package (ForeignKey): Родительская посылка.
        item (ForeignKey): Связанная конкретная позиция с дефектом.
        stage (CharField): Этап фотофиксации (отправка / приемка).
        uploaded_by (ForeignKey): Сотрудник, загрузивший снимок.
        created_at (DateTimeField): Дата и время загрузки.
    """

    class Stage(models.TextChoices):
        """Этапы фотофиксации содержимого."""
        SHIPMENT = "SHIPMENT", "При упаковке / отправке"
        RECEPTION = "RECEPTION", "При приемке на МПД"

    date_of_creation = models.DateField(
        auto_now_add=True,
        verbose_name="Дата создания (legacy)"
    )
    image = models.ImageField(
        upload_to=image_directory_path,
        verbose_name="Фотография"
    )
    caption = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Подпись к фото"
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Посылка"
    )
    item = models.ForeignKey(
        PackageItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photos",
        verbose_name="Связанная позиция"
    )
    stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        default=Stage.SHIPMENT,
        verbose_name="Этап съемки"
    )
    uploaded_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Автор снимка"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата и время загрузки"
    )

    class Meta:
        verbose_name = "Фотография посылки"
        verbose_name_plural = "Фотографии посылок"
        ordering = ["-created_at", "-date_of_creation"]

    def __str__(self) -> str:
        """Возвращает строковое представление фотографии."""
        return f"Фото к {self.package} ({self.get_stage_display()})"


class PackageEventLog(models.Model):
    """Неизменяемый журнал аудита и трекинга жизненного цикла посылки.

    Attributes:
        package (ForeignKey): Отслеживаемая посылка.
        event_type (CharField): Тип зафиксированного события.
        user (ForeignKey): Сотрудник, инициировавший событие.
        timestamp (DateTimeField): Точное время наступления события.
        message (TextField): Человекочитаемое описание события.
        location (CharField): Местоположение / пункт фиксации.
    """

    class EventType(models.TextChoices):
        """Типы регистрируемых событий трекинга."""
        CREATED = "CREATED", "Посылка сформирована отправителем"
        READY = "READY", "Посылка готова к отправке (в очереди)"
        ATTACHED_TO_TRIP = "ATTACHED_TO_TRIP", "Включена в рейс автомобиля"
        REMOVED_FROM_TRIP = "REMOVED_FROM_TRIP", "Исключена из рейса"
        SHIPPED = "SHIPPED", "Отправлена (машина выехала)"
        ARRIVED_AT_MPD = "ARRIVED_AT_MPD", "Доставлена на МПД"
        RECEIVED_FULL = "RECEIVED_FULL", "Принята на МПД без замечаний"
        RECEIVED_DISCREPANCY = "RECEIVED_DISCREPANCY", "Принята на МПД с расхождениями"
        REJECTED = "REJECTED", "Отклонена получателем"
        PHOTO_ADDED = "PHOTO_ADDED", "Прикреплена фотография"
        COMMENT_ADDED = "COMMENT_ADDED", "Добавлен комментарий"

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="event_logs",
        verbose_name="Посылка"
    )
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        verbose_name="Тип события"
    )
    user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь"
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name="Время события"
    )
    message = models.TextField(verbose_name="Описание события")
    location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Местоположение"
    )

    class Meta:
        verbose_name = "Событие трекинга посылки"
        verbose_name_plural = "События трекинга посылок"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        """Возвращает строковое представление записи трекинга."""
        return f"{self.timestamp.strftime('%d.%m.%Y %H:%M')} — {self.get_event_type_display()}"


# ==============================================================================
# ПОДСИСТЕМА ЭЛЕКТРОННОГО ДОКУМЕНТООБОРОТА (СЭД) И МАРШРУТИЗАЦИИ СОГЛАСОВАНИЯ
# ==============================================================================

def docflow_file_upload_to(instance: "DocFlowFileVersion", filename: str) -> str:
    """Генерирует структурированный относительный путь для сохранения файлов СЭД.

    Файлы организуются по структуре: `docflow/YYYY/MM/DD/<doc_uuid>/<filename>`,
    что обеспечивает масштабируемость файлового хранилища и исключает коллизии имен.

    Args:
        instance (DocFlowFileVersion): Экземпляр версии файла документа.
        filename (str): Исходное имя загружаемого файла.

    Returns:
        str: Относительный путь для сохранения файла в директории MEDIA_ROOT.
    """
    now = timezone.now()
    doc_id = "general"
    if instance.doc_file_id and instance.doc_file.document_id:
        doc_id = str(instance.doc_file.document_id)
    return f"docflow/{now.year}/{now.month:02d}/{now.day:02d}/{doc_id}/{filename}"


class DocFlowDocumentType(models.Model):
    """Справочник типов документов электронного документооборота (СЭД).

    Классифицирует входящие, исходящие и внутренние документы компании,
    определяет нормативный SLA согласования и правила маршрутизации.

    Attributes:
        name (CharField): Человекочитаемое название типа документа.
        category (CharField): Категория документооборота (INBOUND / OUTBOUND / INTERNAL).
        code (CharField): Уникальный мнемонический код типа (например, IN_STUDENT_CONTRACT).
        description (TextField): Подробное описание назначения и регламента.
        default_sla_hours (PositiveIntegerField): Нормативный срок согласования по умолчанию (в часах).
        is_active (BooleanField): Флаг доступности типа для создания документов.
        created_at (DateTimeField): Дата и время создания записи.
        updated_at (DateTimeField): Дата и время последнего обновления.
    """

    class Category(models.TextChoices):
        """Категории документооборота."""
        INBOUND = "INBOUND", "Входящий"
        OUTBOUND = "OUTBOUND", "Исходящий"
        INTERNAL = "INTERNAL", "Внутренний"

    name = models.CharField(max_length=255, verbose_name="Название типа документа")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.INBOUND,
        verbose_name="Категория"
    )
    code = models.CharField(max_length=50, unique=True, verbose_name="Символьный код")
    description = models.TextField(blank=True, verbose_name="Описание и регламент")
    default_sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Срок согласования по умолчанию (в часах)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Тип документа СЭД"
        verbose_name_plural = "Типы документов СЭД"
        ordering = ["category", "name"]

    def __str__(self) -> str:
        """Возвращает строковое представление типа документа."""
        return f"{self.get_category_display()}: {self.name}"


class DocFlowNumberCounter(models.Model):
    """Счетчик регистрационных номеров документов СЭД.

    Обеспечивает непрерывную и транзакционно-безопасную автонумерацию документов
    в разрезе года и категории потока (например, СЭД-ВХ-2026/00001, СЭД-ИС-2026/00001).

    Attributes:
        year (PositiveIntegerField): Календарный год регистрации (например, 2026).
        flow_type (CharField): Категория документооборота (INBOUND / OUTBOUND / INTERNAL).
        last_number (PositiveIntegerField): Последний выданный порядковый номер в году.
    """

    year = models.PositiveIntegerField(verbose_name="Год")
    flow_type = models.CharField(
        max_length=20,
        choices=DocFlowDocumentType.Category.choices,
        verbose_name="Тип документооборота"
    )
    last_number = models.PositiveIntegerField(default=0, verbose_name="Последний выданный номер")

    class Meta:
        verbose_name = "Счетчик номеров СЭД"
        verbose_name_plural = "Счетчики номеров СЭД"
        constraints = [
            models.UniqueConstraint(
                fields=["year", "flow_type"],
                name="unique_docflow_counter_year_flow"
            )
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление счетчика номеров."""
        return f"Счетчик {self.flow_type} ({self.year}) — {self.last_number}"

    @classmethod
    def generate_number(cls, flow_type: str, year: Optional[int] = None) -> str:
        """Генерирует следующий уникальный регистрационный номер документа СЭД.

        Формирует номер вида `СЭД-ВХ-YYYY/XXXXX` (для входящих), `СЭД-ИС-YYYY/XXXXX`
        (для исходящих) и `СЭД-ВН-YYYY/XXXXX` (для внутренних) с 5-значным счетчиком.
        Обеспечивает потокобезопасность и защиту от гонок (Race Conditions)
        с помощью `select_for_update()` и `transaction.atomic()`.

        Args:
            flow_type (str): Категория документооборота (INBOUND, OUTBOUND, INTERNAL).
            year (Optional[int]): Календарный год регистрации (по умолчанию текущий год).

        Returns:
            str: Сгенерированный официальный регистрационный номер (например, 'СЭД-ВХ-2026/00001').
        """
        if year is None:
            year = timezone.now().year

        prefix_map = {
            DocFlowDocumentType.Category.INBOUND: "СЭД-ВХ",
            DocFlowDocumentType.Category.OUTBOUND: "СЭД-ИС",
            DocFlowDocumentType.Category.INTERNAL: "СЭД-ВН",
        }
        prefix = prefix_map.get(flow_type, f"СЭД-{flow_type}")

        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                year=year,
                flow_type=flow_type,
                defaults={"last_number": 0}
            )
            counter.last_number += 1
            counter.save(update_fields=["last_number"])
            return f"{prefix}-{year}/{counter.last_number:05d}"


class DocFlowDocument(models.Model):
    """Учетная карточка документа электронного документооборота (СЭД).

    Центральная сущность подсистемы СЭД, объединяющая метаданные документа,
    прикрепленные файлы, маршрут визирования, аудиторский след и связи
    со смежными подсистемами предприятия (контрагенты, договоры, накладные, грузы).

    Attributes:
        id (UUIDField): Первичный ключ (UUIDv4) для защищенных ссылок и верификации.
        reg_number (CharField): Официальный регистрационный номер (например, СЭД-ВХ-2026/00012).
        reg_date (DateField): Дата официальной регистрации документа.
        doc_type (ForeignKey): Тип документа из справочника DocFlowDocumentType.
        title (CharField): Краткое наименование / тема документа.
        description (TextField): Развернутое содержание или сопроводительный текст.
        status (CharField): Текущий статус жизненного цикла документа.
        flow_type (CharField): Категория потока (Входящий / Исходящий / Внутренний).
        urgency (CharField): Приоритет срочности рассмотрения.
        initiator (ForeignKey): Автор / Инициатор карточки документа (DataBaseUser).
        responsible (ForeignKey): Ответственный сотрудник за документ (DataBaseUser).
        counteragent (ForeignKey): Связанный контрагент из customers_app.Counteragent.
        counteragent_contact_email (EmailField): Контактный email для уведомлений.
        current_step_order (PositiveIntegerField): Порядковый номер активного шага маршрута.
        deadline (DateTimeField): Плановый предельный срок завершения согласования.
        created_at (DateTimeField): Дата и время создания карточки.
        updated_at (DateTimeField): Дата и время последнего изменения.
        related_waybill (ForeignKey): Связанная накладная WayBill.
        related_package (ForeignKey): Связанная посылка Package.
        related_contract (ForeignKey): Связанный договор contracts_app.Contract.
    """

    class Status(models.TextChoices):
        """Статусы жизненного цикла документа СЭД."""
        DRAFT = "DRAFT", "Черновик"
        ON_REGISTRATION = "ON_REGISTRATION", "На первичной регистрации"
        ON_APPROVAL = "ON_APPROVAL", "На согласовании"
        ON_REWORK = "ON_REWORK", "На доработке"
        APPROVED = "APPROVED", "Согласован / Принят"
        SIGNED = "SIGNED", "Подписан сторонами"
        EXECUTED = "EXECUTED", "Исполнен"
        REJECTED = "REJECTED", "Отклонен"
        ARCHIVED = "ARCHIVED", "В архиве"

    class Urgency(models.TextChoices):
        """Срочность рассмотрения документа."""
        NORMAL = "NORMAL", "Обычная"
        URGENT = "URGENT", "Срочно"
        CRITICAL = "CRITICAL", "Критически срочно"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Идентификатор UUID"
    )
    reg_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Регистрационный номер"
    )
    reg_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата регистрации"
    )
    doc_type = models.ForeignKey(
        DocFlowDocumentType,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name="Тип документа"
    )
    title = models.CharField(max_length=500, verbose_name="Краткое наименование / тема")
    description = models.TextField(blank=True, verbose_name="Содержание / описание")
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус"
    )
    flow_type = models.CharField(
        max_length=20,
        choices=DocFlowDocumentType.Category.choices,
        default=DocFlowDocumentType.Category.INBOUND,
        verbose_name="Поток / Категория"
    )
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.NORMAL,
        verbose_name="Срочность"
    )
    initiator = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_initiated_docs",
        verbose_name="Инициатор (Автор)"
    )
    responsible = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_responsible_docs",
        null=True,
        blank=True,
        verbose_name="Ответственный сотрудник"
    )
    counteragent = models.ForeignKey(
        'customers_app.Counteragent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Контрагент"
    )
    counteragent_contact_email = models.EmailField(
        blank=True,
        verbose_name="Email контрагента для уведомлений"
    )
    current_step_order = models.PositiveIntegerField(
        default=1,
        verbose_name="Порядок текущего этапа"
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Плановый срок (дедлайн)"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата и время изменения")

    # Связи со смежными сущностями
    related_waybill = models.ForeignKey(
        'logistics_app.WayBill',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанная накладная"
    )
    related_package = models.ForeignKey(
        'logistics_app.Package',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанная посылка"
    )
    related_contract = models.ForeignKey(
        'contracts_app.Contract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанный договор"
    )

    class Meta:
        verbose_name = "Документ СЭД"
        verbose_name_plural = "Документы СЭД"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "flow_type"], name="idx_docflow_status_flow"),
            models.Index(fields=["initiator", "status"], name="idx_docflow_init_status"),
            models.Index(fields=["responsible", "status"], name="idx_docflow_resp_status"),
            models.Index(fields=["reg_date", "status"], name="idx_docflow_date_status"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление документа с номером и названием."""
        num = self.reg_number or f"UUID:{str(self.id)[:8]}"
        return f"{num} — {self.title}"

    @property
    def is_draft(self) -> bool:
        """Возвращает True, если документ находится в статусе черновика."""
        return self.status == self.Status.DRAFT

    @property
    def is_on_approval(self) -> bool:
        """Возвращает True, если документ находится в процессе согласования."""
        return self.status == self.Status.ON_APPROVAL

    @property
    def is_approved(self) -> bool:
        """Возвращает True, если документ полностью согласован / принят."""
        return self.status in [self.Status.APPROVED, self.Status.SIGNED, self.Status.EXECUTED]

    @property
    def is_finalized(self) -> bool:
        """Возвращает True, если документ находится в финальном неизменяемом статусе."""
        return self.status in [
            self.Status.APPROVED,
            self.Status.SIGNED,
            self.Status.EXECUTED,
            self.Status.REJECTED,
            self.Status.ARCHIVED,
        ]

    @property
    def can_modify_files(self) -> bool:
        """Возвращает True, если разрешено изменение файлов или загрузка новых версий."""
        return not self.is_finalized

    @property
    def is_on_rework(self) -> bool:
        """Возвращает True, если документ возвращен на доработку."""
        return self.status == self.Status.ON_REWORK

    @property
    def main_file(self) -> Optional["DocFlowFile"]:
        """Возвращает основной прикрепленный файл документа."""
        return self.files.filter(is_main=True).first() or self.files.first()

    @property
    def active_steps(self):
        """Возвращает QuerySet активных шагов маршрута в статусе IN_PROGRESS."""
        return self.route_steps.filter(status="IN_PROGRESS")

    def assign_registration_number(self, save: bool = True) -> str:
        """Присваивает официальный регистрационный номер документу СЭД.

        Если номер уже существует, возвращает его без изменений. В противном случае
        обращается к транзакционному счетчику DocFlowNumberCounter для получения
        следующего уникального номера текущего года.

        Args:
            save (bool): Сохранять ли изменения в базе данных немедленно. Defaults to True.

        Returns:
            str: Официальный регистрационный номер документа.
        """
        if not self.reg_number:
            year = self.reg_date.year if self.reg_date else timezone.now().year
            if not self.reg_date:
                self.reg_date = timezone.now().date()
            if self.doc_type_id:
                self.flow_type = self.doc_type.category
            self.reg_number = DocFlowNumberCounter.generate_number(self.flow_type, year=year)
            if save and self.pk:
                self.save(update_fields=["reg_number", "reg_date", "flow_type", "updated_at"])
        return self.reg_number

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Переопределенный метод сохранения карточки документа СЭД.

        Синхронизирует категорию flow_type с типом документа doc_type при создании.

        Args:
            *args (Any): Позиционные аргументы сохранения Django ORM.
            **kwargs (Any): Именованные аргументы сохранения Django ORM.
        """
        if self.doc_type_id and (not self.flow_type or self._state.adding):
            self.flow_type = self.doc_type.category
        super().save(*args, **kwargs)


class DocFlowFile(models.Model):
    """Учетная запись файла, прикрепленного к документу СЭД.

    Служит контейнером для версий конкретного документа (например, основного проекта договора,
    технического задания, сметы или приложений).

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        title (CharField): Наименование документа/файла.
        is_main (BooleanField): Флаг основного файла документа.
        current_version_number (CharField): Номер актуальной версии.
        created_at (DateTimeField): Дата добавления.
    """

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Документ СЭД"
    )
    title = models.CharField(max_length=255, verbose_name="Название документа / файла")
    is_main = models.BooleanField(default=True, verbose_name="Основной файл документа")
    current_version_number = models.CharField(
        max_length=20,
        default="1.0",
        verbose_name="Текущая версия"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Файл документа СЭД"
        verbose_name_plural = "Файлы документов СЭД"
        ordering = ["-is_main", "title"]

    def __str__(self) -> str:
        """Возвращает строковое представление файла."""
        return f"{self.title} (v{self.current_version_number})"

    @property
    def latest_version(self) -> Optional["DocFlowFileVersion"]:
        """Возвращает последнюю загруженную версию файла."""
        return self.versions.order_by("-uploaded_at").first()


class DocFlowFileVersion(models.Model):
    """Конкретная физическая версия файла документа СЭД.

    Обеспечивает неизменяемость истории правок, фиксирует автора загрузки,
    время, контрольную сумму SHA-256 и признаки рецензирования согласующим.

    Attributes:
        doc_file (ForeignKey): Связанный файл DocFlowFile.
        version_number (CharField): Номер редакции (например, '1.0', '1.1', '2.0').
        file (FileField): Физический файл в хранилище MEDIA_ROOT.
        file_size (PositiveBigIntegerField): Размер файла в байтах.
        file_hash (CharField): Контрольный хэш SHA-256 для защиты от подделки.
        uploaded_by (ForeignKey): Сотрудник, загрузивший версию (DataBaseUser).
        change_comment (TextField): Комментарий автора или согласующего к версии.
        is_reviewer_edit (BooleanField): Флаг загрузки версии согласующим лицом.
        uploaded_at (DateTimeField): Точная временная метка загрузки.
    """

    doc_file = models.ForeignKey(
        DocFlowFile,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="Файл документа"
    )
    version_number = models.CharField(
        max_length=20,
        verbose_name="Номер версии (например, 1.0, 1.1)"
    )
    file = models.FileField(
        upload_to=docflow_file_upload_to,
        verbose_name="Физический файл"
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Размер файла (байт)"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Контрольная сумма SHA-256"
    )
    uploaded_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_uploaded_versions",
        verbose_name="Кем загружен"
    )
    change_comment = models.TextField(
        blank=True,
        verbose_name="Комментарий к версии / замечания"
    )
    is_reviewer_edit = models.BooleanField(
        default=False,
        verbose_name="Правка согласующего лица"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время загрузки")

    class Meta:
        verbose_name = "Версия файла СЭД"
        verbose_name_plural = "Версии файлов СЭД"
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        """Возвращает строковое представление версии файла."""
        return f"{self.doc_file.title} v{self.version_number} ({self.uploaded_by})"

    @property
    def file_hash_sha256(self) -> str:
        """Возвращает контрольную сумму SHA-256 (псевдоним для обратной совместимости)."""
        return self.file_hash

    @property
    def comment(self) -> str:
        """Возвращает комментарий к версии файла (псевдоним для обратной совместимости)."""
        return self.change_comment

    @property
    def file_size_formatted(self) -> str:
        """Возвращает форматированный размер файла с единицей измерения (Б, КБ, МБ).

        Returns:
            str: Человекочитаемая строка размера файла (напр. '250.5 КБ', '12.40 МБ').
        """
        size = self.file_size or 0
        if size < 1024:
            return f"{size} Б"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        else:
            return f"{size / (1024 * 1024):.2f} МБ"


class DocFlowRouteTemplate(models.Model):
    """Шаблон маршрута согласования СЭД.

    Определяет типовую цепочку этапов визирования для конкретного типа документа.

    Attributes:
        name (CharField): Название шаблона (например, «Типовой маршрут ученического договора»).
        doc_type (ForeignKey): Тип документа, к которому привязан шаблон.
        is_default (BooleanField): Использовать ли шаблон по умолчанию для данного типа.
        description (TextField): Пояснение логики и участников маршрута.
        created_at (DateTimeField): Дата создания шаблона.
    """

    name = models.CharField(max_length=255, verbose_name="Наименование шаблона")
    doc_type = models.ForeignKey(
        DocFlowDocumentType,
        on_delete=models.CASCADE,
        related_name="route_templates",
        verbose_name="Тип документа"
    )
    is_default = models.BooleanField(
        default=True,
        verbose_name="Использовать по умолчанию для типа"
    )
    description = models.TextField(blank=True, verbose_name="Описание маршрута")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Шаблон маршрута СЭД"
        verbose_name_plural = "Шаблоны маршрутов СЭД"
        ordering = ["doc_type", "name"]

    def __str__(self) -> str:
        """Возвращает строковое представление шаблона."""
        return f"{self.doc_type.name}: {self.name}"


class DocFlowRouteStepTemplate(models.Model):
    """Шаг шаблона маршрута согласования СЭД.

    Определяет исполнителей этапа (пользователь, подразделение или группа),
    тип согласования (последовательное, параллельное «И» / «ИЛИ») и нормативный SLA.

    Attributes:
        route_template (ForeignKey): Шаблон маршрута DocFlowRouteTemplate.
        step_order (PositiveIntegerField): Порядковый номер этапа в цепочке (1, 2, 3...).
        step_name (CharField): Название этапа (например, «Визирование Юротделом»).
        step_type (CharField): Тип выполнения шага (SEQUENTIAL, PARALLEL_AND, PARALLEL_OR, HEAD_OF_DEPARTMENT).
        assigned_division (ForeignKey): Назначенное подразделение.
        assigned_user (ForeignKey): Персонально назначенный сотрудник.
        assigned_users (ManyToManyField): Группа сотрудников для параллельного согласования.
        sla_hours (PositiveIntegerField): Нормативный срок на рассмотрение в часах.
        allow_reviewer_file_edit (BooleanField): Разрешить ли согласующему прикреплять файл с правками.
        can_rollback_to (BooleanField): Разрешить ли целевой откат на этот шаг.
    """

    class StepType(models.TextChoices):
        """Типы шагов маршрута согласования."""
        SEQUENTIAL = "SEQUENTIAL", "Последовательный (Один сотрудник)"
        PARALLEL_AND = "PARALLEL_AND", "Параллельный «И» (Все должны согласовать)"
        PARALLEL_OR = "PARALLEL_OR", "Параллельный «ИЛИ» (Любой из группы)"
        HEAD_OF_DEPARTMENT = "HEAD_OF_DEPARTMENT", "Руководитель подразделения автора"

    route_template = models.ForeignKey(
        DocFlowRouteTemplate,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="Шаблон маршрута"
    )
    step_order = models.PositiveIntegerField(default=1, verbose_name="Порядковый номер этапа")
    step_name = models.CharField(max_length=255, verbose_name="Название этапа")
    step_type = models.CharField(
        max_length=25,
        choices=StepType.choices,
        default=StepType.SEQUENTIAL,
        verbose_name="Тип этапа"
    )
    assigned_division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_step_templates",
        verbose_name="Назначенное подразделение"
    )
    assigned_user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_user_step_templates",
        verbose_name="Назначенный сотрудник"
    )
    assigned_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_parallel_step_templates",
        verbose_name="Группа согласующих сотрудников"
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Срок на рассмотрение (в часах)"
    )
    allow_reviewer_file_edit = models.BooleanField(
        default=True,
        verbose_name="Разрешить согласующему загружать файл с правками"
    )
    can_rollback_to = models.BooleanField(
        default=True,
        verbose_name="Разрешить откат на данный шаг"
    )

    class Meta:
        verbose_name = "Шаг шаблона маршрута СЭД"
        verbose_name_plural = "Шаги шаблонов маршрутов СЭД"
        ordering = ["route_template", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["route_template", "step_order"],
                name="unique_template_step_order"
            )
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление шага шаблона."""
        return f"Шаг {self.step_order}: {self.step_name} ({self.get_step_type_display()})"


class DocFlowRouteStep(models.Model):
    """Экземпляр этапа маршрута согласования конкретного документа СЭД.

    Хранит состояние согласования этапа, назначенных участников, отметки о завершении
    и контроль сроков SLA.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        step_order (PositiveIntegerField): Порядковый номер этапа в цепочке.
        step_name (CharField): Название этапа.
        step_type (CharField): Тип выполнения шага.
        assigned_division (ForeignKey): Назначенное подразделение.
        assigned_user (ForeignKey): Назначенный сотрудник.
        assigned_users (ManyToManyField): Группа назначенных согласующих.
        approved_users (ManyToManyField): Сотрудники, фактически согласовавшие данный шаг.
        status (CharField): Текущий статус этапа (PENDING, IN_PROGRESS, APPROVED, RETURNED, REJECTED, SKIPPED).
        started_at (DateTimeField): Время поступления документа на этап.
        completed_at (DateTimeField): Время завершения этапа.
        due_date (DateTimeField): Расчетный предельный дедлайн этапа по SLA.
        sla_hours (PositiveIntegerField): Нормативный срок на рассмотрение в часах.
        can_rollback_to (BooleanField): Доступен ли данный шаг для целевого отката.
        allow_reviewer_file_edit (BooleanField): Разрешена ли загрузка правок согласующими.
    """

    class Status(models.TextChoices):
        """Статусы этапа согласования."""
        PENDING = "PENDING", "Ожидает очереди"
        IN_PROGRESS = "IN_PROGRESS", "В процессе согласования"
        APPROVED = "APPROVED", "Согласован"
        RETURNED = "RETURNED", "Возвращен на доработку / Шаг отката"
        REJECTED = "REJECTED", "Отклонен"
        SKIPPED = "SKIPPED", "Пропущен"

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="route_steps",
        verbose_name="Документ СЭД"
    )
    step_order = models.PositiveIntegerField(default=1, verbose_name="Порядковый номер этапа")
    step_name = models.CharField(max_length=255, verbose_name="Название этапа")
    step_type = models.CharField(
        max_length=25,
        choices=DocFlowRouteStepTemplate.StepType.choices,
        default=DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
        verbose_name="Тип этапа"
    )
    assigned_division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_route_steps",
        verbose_name="Назначенное подразделение"
    )
    assigned_user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_route_user_steps",
        verbose_name="Назначенный сотрудник"
    )
    assigned_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_route_parallel_steps",
        verbose_name="Назначенные согласующие (группа)"
    )
    approved_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_step_approved_by",
        verbose_name="Сотрудники, фактически согласовавшие шаг"
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус шага"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время поступления на этап"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время завершения этапа"
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дедлайн этапа"
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Нормативный срок SLA (в часах)"
    )
    can_rollback_to = models.BooleanField(
        default=True,
        verbose_name="Доступен ли шаг для целевого отката"
    )
    allow_reviewer_file_edit = models.BooleanField(
        default=True,
        verbose_name="Разрешить согласующему загружать файл с правками"
    )

    class Meta:
        verbose_name = "Шаг маршрута согласования СЭД"
        verbose_name_plural = "Шаги маршрутов согласования СЭД"
        ordering = ["document", "step_order"]
        indexes = [
            models.Index(fields=["document", "status", "step_order"], name="idx_docstep_doc_stat_order"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление этапа маршрута."""
        return f"{self.document.reg_number or 'Документ'} — Шаг {self.step_order}: {self.step_name} [{self.get_status_display()}]"

    @property
    def is_active(self) -> bool:
        """Возвращает True, если данный шаг сейчас активен."""
        return self.status == self.Status.IN_PROGRESS


class DocFlowApprovalLog(models.Model):
    """Журнал аудита, визирования и юридически значимых действий в СЭД.

    Неизменяемый журнал (Audit Trail), фиксирующий наложение виз ПЭП,
    возвраты на доработку, откаты на шаги, загрузку версий и комментарии.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        route_step (ForeignKey): Связанный шаг маршрута DocFlowRouteStep.
        user (ForeignKey): Сотрудник, совершивший действие (DataBaseUser).
        action (CharField): Тип выполненного действия.
        target_step_order (PositiveIntegerField): Номер целевого шага при откате.
        comment (TextField): Текстовая резолюция, замечания или комментарий.
        created_at (DateTimeField): Точная временная метка совершения действия.
        ip_address (GenericIPAddressField): IP-адрес клиентского устройства.
        user_agent (CharField): Браузер / клиентское приложение пользователя.
        pep_signature_hash (CharField): Цифровой криптографический слепок ПЭП (SHA-256).
        pep_certificate_id (CharField): Уникальный номер сертификата ПЭП.
    """

    class Action(models.TextChoices):
        """Типы действий в журнале аудита СЭД."""
        REGISTERED = "REGISTERED", "Документ зарегистрирован"
        STARTED = "STARTED", "Маршрут согласования запущен"
        APPROVED = "APPROVED", "Согласовано (Виза наложена)"
        APPROVED_WITH_COMMENTS = "APPROVED_WITH_COMMENTS", "Согласовано с замечаниями / правками"
        RETURNED_TO_AUTHOR = "RETURNED_TO_AUTHOR", "Возвращено автору на доработку"
        ROLLBACK_TO_STEP = "ROLLBACK_TO_STEP", "Откат на предыдущий шаг"
        REJECTED = "REJECTED", "Документ отклонен"
        DELEGATED = "DELEGATED", "Шаг делегирован другому сотруднику"
        RESTARTED = "RESTARTED", "Маршрут возобновлен / перезапущен"
        NEW_VERSION_UPLOADED = "NEW_VERSION_UPLOADED", "Загружена новая версия файла"
        COMMENTED = "COMMENTED", "Добавлен комментарий"

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="approval_logs",
        verbose_name="Документ СЭД"
    )
    route_step = models.ForeignKey(
        DocFlowRouteStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name="Связанный шаг маршрута"
    )
    user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_action_logs",
        verbose_name="Сотрудник (автор действия)"
    )
    action = models.CharField(
        max_length=35,
        choices=Action.choices,
        verbose_name="Действие"
    )
    target_step_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Целевой шаг при откате"
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Резолюция / Замечания / Особое мнение"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время совершения действия"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес пользователя"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Клиентское приложение (User Agent)"
    )
    pep_signature_hash = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="Цифровой хэш ПЭП (SHA-256)"
    )
    pep_certificate_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Идентификатор сертификата ПЭП"
    )

    class Meta:
        verbose_name = "Запись аудита и визирования СЭД"
        verbose_name_plural = "Журнал аудита и визирования СЭД"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["document", "created_at"], name="idx_doclog_doc_created"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление записи аудита."""
        return f"{self.created_at:%d.%m.%Y %H:%M} — {self.user}: {self.get_action_display()}"


class DocFlowComment(models.Model):
    """Комментарий и внутреннее обсуждение в карточке документа СЭД.

    Позволяет участникам маршрута вести рабочее обсуждение документа,
    прикреплять замечания и отвечать на комментарии коллег.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        author (ForeignKey): Автор комментария (DataBaseUser).
        text (TextField): Текст сообщения.
        parent (ForeignKey): Родительский комментарий (для древовидных ответов).
        created_at (DateTimeField): Дата и время отправки комментария.
    """

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Документ СЭД"
    )
    author = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_comments",
        verbose_name="Автор комментария"
    )
    text = models.TextField(verbose_name="Текст сообщения / обсуждения")
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="Родительский комментарий"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время отправки")

    class Meta:
        verbose_name = "Комментарий к документу СЭД"
        verbose_name_plural = "Комментарии к документам СЭД"
        ordering = ["created_at"]

    def __str__(self) -> str:
        """Возвращает строковое представление комментария."""
        return f"Комментарий {self.author} ({self.created_at:%d.%m.%Y %H:%M})"


