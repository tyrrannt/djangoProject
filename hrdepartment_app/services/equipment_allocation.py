"""Сервис интеллектуального подбора и гео-логистики оборудования ТО по МПД (ФАП-145).

Реализует:
1. Валидацию нормативных требований табеля оснащения (MaintenanceWorkEquipmentRequirement)
   для периодических (PeriodicWork) и оперативных (OperationalWork) форм ТО;
2. Анализ локального наличия и пригодности СИ/инструмента на целевом МПД;
3. Защиту от двойного бронирования (Double Booking Prevention) путем исключения приборов,
   задействованных в параллельных незавершенных картах-нарядах (OutfitCard);
4. Корректный учет инструмента без поверки (EquipmentVerificationType.NOT_REQUIRED);
5. Контроль метрологического буфера безопасности (Safety Margin) на длительность ТО;
6. Геодезический поиск и ранжирование приборов-доноров на сторонних МПД компании
   по формуле Haversine (GeoStationService.haversine_distance) с формированием рекомендаций.
"""

from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass, field
from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from hrdepartment_app.models import (
    MaintenanceEquipment,
    EquipmentTypeModel,
    MaintenanceWorkEquipmentRequirement,
    EquipmentTransferRequest,
    EquipmentTransferStatus,
    PlaceProductionActivity,
    PeriodicWork,
    OperationalWork,
    OutfitCard,
    OutfitCardEquipmentUsage,
    EquipmentOperationalStatus,
    EquipmentVerificationType,
)
from flight_planning.weather_providers.geo_service import GeoStationService


@dataclass
class EquipmentDonorOption:
    """Рекомендованный прибор-донор с другого МПД компании."""

    equipment_id: int
    name: str
    serial_number: str
    part_number: str
    type_model_id: Optional[int]
    type_model_name: str
    mpd_id: int
    mpd_name: str
    distance_km: float
    days_until_expiration: Optional[int]
    next_verification_date: Optional[date]
    donor_reserve_count: int
    missing_coords: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует карточку донора в словарь для шаблонов и JSON API."""
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "serial_number": self.serial_number,
            "part_number": self.part_number,
            "type_model_id": self.type_model_id,
            "type_model_name": self.type_model_name,
            "mpd_id": self.mpd_id,
            "mpd_name": self.mpd_name,
            "distance_km": round(self.distance_km, 1) if self.distance_km < 90000 else None,
            "distance_display": f"{round(self.distance_km, 1)} км" if self.distance_km < 90000 else "Координаты не заданы",
            "days_until_expiration": self.days_until_expiration,
            "next_verification_date": (
                f"{self.next_verification_date:%d.%m.%Y}" if self.next_verification_date else "Не требуется"
            ),
            "donor_reserve_count": self.donor_reserve_count,
            "missing_coords": self.missing_coords,
        }


@dataclass
class AllocationItemResult:
    """Результат подбора оборудования по конкретному требованию табеля оснащения."""

    requirement_id: int
    equipment_name_id: int
    equipment_name: str
    required_type_id: Optional[int]
    required_type_name: str
    allowed_substitutes: List[str]
    required_quantity: int
    is_mandatory: bool
    task_reference: str
    status: str  # "AVAILABLE", "PARTIAL", "EXPIRED_LOCAL", "DEFICIT"
    allocated_equipment: List[Dict[str, Any]] = field(default_factory=list)
    allocated_count: int = 0
    deficit_count: int = 0
    expired_local_equipment: List[Dict[str, Any]] = field(default_factory=list)
    donors: List[EquipmentDonorOption] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует результат позиции в словарь."""
        return {
            "requirement_id": self.requirement_id,
            "equipment_name_id": self.equipment_name_id,
            "equipment_name": self.equipment_name,
            "required_type_id": self.required_type_id,
            "required_type_name": self.required_type_name,
            "allowed_substitutes": self.allowed_substitutes,
            "required_quantity": self.required_quantity,
            "is_mandatory": self.is_mandatory,
            "task_reference": self.task_reference,
            "status": self.status,
            "allocated_equipment": self.allocated_equipment,
            "allocated_count": self.allocated_count,
            "deficit_count": self.deficit_count,
            "expired_local_equipment": self.expired_local_equipment,
            "donors": [d.to_dict() for d in self.donors],
        }


@dataclass
class EquipmentAllocationReport:
    """Сводный отчет готовности МПД к проведению регламентной или оперативной формы ТО."""

    work_id: int
    work_name: str
    work_code: str
    work_category: str  # "PERIODIC" или "OPERATIONAL"
    target_mpd_id: int
    target_mpd_name: str
    target_date_start: date
    target_date_end: date
    safety_buffer_days: int
    readiness_percentage: float
    total_requirements_count: int
    satisfied_requirements_count: int
    deficit_items_count: int
    mandatory_deficit_count: int
    is_fully_ready: bool
    items: List[AllocationItemResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует сводный отчет в словарь."""
        return {
            "work_id": self.work_id,
            "work_name": self.work_name,
            "work_code": self.work_code,
            "work_category": self.work_category,
            "target_mpd_id": self.target_mpd_id,
            "target_mpd_name": self.target_mpd_name,
            "target_date_start": f"{self.target_date_start:%d.%m.%Y}",
            "target_date_end": f"{self.target_date_end:%d.%m.%Y}",
            "safety_buffer_days": self.safety_buffer_days,
            "readiness_percentage": round(self.readiness_percentage, 1),
            "total_requirements_count": self.total_requirements_count,
            "satisfied_requirements_count": self.satisfied_requirements_count,
            "deficit_items_count": self.deficit_items_count,
            "mandatory_deficit_count": self.mandatory_deficit_count,
            "is_fully_ready": self.is_fully_ready,
            "items": [it.to_dict() for it in self.items],
        }


class EquipmentAllocationService:
    """Сервисный слой интеллектуального подбора оборудования ТО по МПД (ФАП-145)."""

    DEFAULT_SAFETY_BUFFER_DAYS: int = 7
    VIRTUAL_MAX_DISTANCE_KM: float = 99999.0

    def __init__(
        self,
        work_object: Union[PeriodicWork, OperationalWork],
        target_mpd: PlaceProductionActivity,
        target_date_start: Optional[date] = None,
        target_date_end: Optional[date] = None,
        safety_buffer_days: Optional[int] = None,
    ) -> None:
        """Инициализирует сервис подбора оборудования.

        Args:
            work_object (Union[PeriodicWork, OperationalWork]): Объект формы ТО.
            target_mpd (PlaceProductionActivity): Целевое МПД проведения обслуживания.
            target_date_start (Optional[date]): Дата начала ТО (по умолчанию текущая дата).
            target_date_end (Optional[date]): Планируемая дата завершения ТО.
            safety_buffer_days (Optional[int]): Метрологический буфер надежности в днях.
        """
        self.work_object = work_object
        self.target_mpd = target_mpd
        self.target_date_start = target_date_start or timezone.now().date()
        self.safety_buffer_days = (
            safety_buffer_days if safety_buffer_days is not None else self.DEFAULT_SAFETY_BUFFER_DAYS
        )
        self.target_date_end = target_date_end or (
            self.target_date_start + timedelta(days=self.safety_buffer_days)
        )

    def calculate_allocation(self) -> EquipmentAllocationReport:
        """Выполняет полный расчет обеспеченности МПД оборудованием под выбранную форму ТО.

        Returns:
            EquipmentAllocationReport: Детализированный отчет обеспеченности с донорами.
        """
        is_periodic = isinstance(self.work_object, PeriodicWork)
        work_category = "PERIODIC" if is_periodic else "OPERATIONAL"

        requirements_qs = MaintenanceWorkEquipmentRequirement.objects.select_related(
            "equipment_name", "required_type", "periodic_work", "operational_work"
        ).prefetch_related("allowed_substitutes")

        if is_periodic:
            requirements = list(requirements_qs.filter(periodic_work=self.work_object))
        else:
            requirements = list(requirements_qs.filter(operational_work=self.work_object))

        # Вычисляем занятые приборы на целевом МПД в период ТО (Double Booking)
        busy_equipment_ids = self._get_busy_equipment_ids(
            mpd=self.target_mpd,
            date_start=self.target_date_start,
            date_end=self.target_date_end,
        )

        item_results: List[AllocationItemResult] = []
        satisfied_count = 0
        mandatory_deficit_count = 0

        for req in requirements:
            item_res = self._evaluate_requirement(req, busy_equipment_ids)
            item_results.append(item_res)

            if item_res.status == "AVAILABLE":
                satisfied_count += 1
            else:
                if req.is_mandatory:
                    mandatory_deficit_count += 1

        total_reqs = len(requirements)
        readiness_pct = (satisfied_count / total_reqs * 100.0) if total_reqs > 0 else 100.0
        deficit_count = total_reqs - satisfied_count
        is_fully_ready = (deficit_count == 0)

        work_name = self.work_object.name or (
            f"Форма #{self.work_object.pk}"
        )
        work_code = getattr(self.work_object, "code", "") or "—"

        return EquipmentAllocationReport(
            work_id=self.work_object.pk,
            work_name=work_name,
            work_code=work_code,
            work_category=work_category,
            target_mpd_id=self.target_mpd.pk,
            target_mpd_name=self.target_mpd.short_name or self.target_mpd.name,
            target_date_start=self.target_date_start,
            target_date_end=self.target_date_end,
            safety_buffer_days=self.safety_buffer_days,
            readiness_percentage=readiness_pct,
            total_requirements_count=total_reqs,
            satisfied_requirements_count=satisfied_count,
            deficit_items_count=deficit_count,
            mandatory_deficit_count=mandatory_deficit_count,
            is_fully_ready=is_fully_ready,
            items=item_results,
        )

    def _evaluate_requirement(
        self,
        req: MaintenanceWorkEquipmentRequirement,
        busy_equipment_ids: set,
    ) -> AllocationItemResult:
        """Оценивает обеспеченность МПД по одному требованию табеля оснащения."""
        # 1. Формируем список допустимых типов (основной тип + аналоги)
        allowed_type_ids = set()
        if req.required_type_id:
            allowed_type_ids.add(req.required_type_id)
        for sub in req.allowed_substitutes.all():
            allowed_type_ids.add(sub.pk)

        # 2. Ищем физические единицы на целевом МПД
        local_qs = MaintenanceEquipment.objects.filter(
            production_place=self.target_mpd,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
        )

        # Фильтруем по наименованию (через type_model или имя)
        if allowed_type_ids:
            local_qs = local_qs.filter(type_model_id__in=allowed_type_ids)
        else:
            # Если строгий тип не задан, допускается любой тип данного наименования
            local_qs = local_qs.filter(
                Q(type_model__equipment_name_id=req.equipment_name_id)
                | Q(name__icontains=req.equipment_name.name)
            )

        local_equipments = list(local_qs.select_related("type_model", "type_model__equipment_name"))

        valid_local: List[Dict[str, Any]] = []
        expired_local: List[Dict[str, Any]] = []

        for eq in local_equipments:
            # Проверяем, не занят ли прибор в параллельном наряде
            if eq.pk in busy_equipment_ids:
                continue

            # Проверяем метрологическую годность на всю длительность ТО
            is_valid, reason = self._is_equipment_metrology_valid(eq)
            eq_dict = {
                "id": eq.pk,
                "name": eq.name,
                "serial_number": eq.serial_number or "б/н",
                "part_number": eq.part_number or (eq.type_model.part_number if eq.type_model else ""),
                "type_name": eq.type_model.name if eq.type_model else "—",
                "status_reason": reason,
                "next_verification_date": (
                    f"{eq.next_verification_date:%d.%m.%Y}" if eq.next_verification_date else "—"
                ),
            }
            if is_valid:
                valid_local.append(eq_dict)
            else:
                expired_local.append(eq_dict)

        required_qty = req.quantity
        available_qty = len(valid_local)
        allocated = valid_local[:required_qty]
        allocated_count = len(allocated)
        deficit_count = max(0, required_qty - allocated_count)

        if allocated_count >= required_qty:
            status = "AVAILABLE"
        elif allocated_count > 0:
            status = "PARTIAL"
        elif len(expired_local) > 0:
            status = "EXPIRED_LOCAL"
        else:
            status = "DEFICIT"

        # 3. Если есть дефицит, производим гео-поиск доноров на других МПД
        donors: List[EquipmentDonorOption] = []
        if deficit_count > 0:
            donors = self._find_donor_equipment(req, allowed_type_ids, deficit_count)

        allowed_sub_names = [sub.name for sub in req.allowed_substitutes.all()]

        return AllocationItemResult(
            requirement_id=req.pk,
            equipment_name_id=req.equipment_name_id,
            equipment_name=req.equipment_name.name,
            required_type_id=req.required_type_id,
            required_type_name=req.required_type.name if req.required_type else "Любой утвержденный тип",
            allowed_substitutes=allowed_sub_names,
            required_quantity=required_qty,
            is_mandatory=req.is_mandatory,
            task_reference=req.task_reference,
            status=status,
            allocated_equipment=allocated,
            allocated_count=allocated_count,
            deficit_count=deficit_count,
            expired_local_equipment=expired_local,
            donors=donors,
        )

    def _is_equipment_metrology_valid(self, eq: MaintenanceEquipment) -> Tuple[bool, str]:
        """Проверяет пригодность прибора с учетом даты окончания ТО и исключения NOT_REQUIRED."""
        if eq.verification_type == EquipmentVerificationType.NOT_REQUIRED:
            return True, "Метрологический контроль не требуется, инструмент исправен"

        if not eq.next_verification_date and not eq.last_verification_date:
            return False, "Отсутствуют сведения о проведенной поверке (ФАП-145)"

        if eq.next_verification_date and eq.next_verification_date < self.target_date_end:
            return False, (
                f"Поверка истекает {eq.next_verification_date:%d.%m.%Y} "
                f"(ранее окончания ТО {self.target_date_end:%d.%m.%Y})"
            )

        return True, "Поверен и годен"

    def _find_donor_equipment(
        self,
        req: MaintenanceWorkEquipmentRequirement,
        allowed_type_ids: set,
        deficit_count: int,
    ) -> List[EquipmentDonorOption]:
        """Ищет свободные годные приборы на сторонних МПД компании и ранжирует по удаленности."""
        today = timezone.now().date()

        donor_qs = MaintenanceEquipment.objects.filter(
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
        ).exclude(production_place=self.target_mpd).exclude(production_place__isnull=True)

        if allowed_type_ids:
            donor_qs = donor_qs.filter(type_model_id__in=allowed_type_ids)
        else:
            donor_qs = donor_qs.filter(
                Q(type_model__equipment_name_id=req.equipment_name_id)
                | Q(name__icontains=req.equipment_name.name)
            )

        donor_qs = donor_qs.select_related(
            "production_place", "type_model", "type_model__equipment_name"
        )

        donor_options: List[EquipmentDonorOption] = []
        target_lat = self.target_mpd.latitude
        target_lon = self.target_mpd.longitude

        for eq in donor_qs:
            # Проверяем метрологическую годность
            is_valid, _ = self._is_equipment_metrology_valid(eq)
            if not is_valid:
                continue

            mpd = eq.production_place
            if not mpd:
                continue

            # Расчет расстояния по формуле Haversine
            missing_coords = False
            if target_lat is not None and target_lon is not None and mpd.latitude is not None and mpd.longitude is not None:
                dist = GeoStationService.haversine_distance(
                    target_lat, target_lon, mpd.latitude, mpd.longitude
                )
            else:
                dist = self.VIRTUAL_MAX_DISTANCE_KM
                missing_coords = True

            days_until = (
                (eq.next_verification_date - today).days
                if eq.next_verification_date
                else None
            )

            # Число приборов этого типа на МПД-доноре (резерв)
            reserve_count = MaintenanceEquipment.objects.filter(
                production_place=mpd,
                type_model=eq.type_model,
                operational_status=EquipmentOperationalStatus.SERVICEABLE,
            ).count()

            type_name = eq.type_model.name if eq.type_model else "—"

            donor_options.append(
                EquipmentDonorOption(
                    equipment_id=eq.pk,
                    name=eq.name,
                    serial_number=eq.serial_number or "б/н",
                    part_number=eq.part_number or (eq.type_model.part_number if eq.type_model else ""),
                    type_model_id=eq.type_model_id,
                    type_model_name=type_name,
                    mpd_id=mpd.pk,
                    mpd_name=mpd.short_name or mpd.name,
                    distance_km=dist,
                    days_until_expiration=days_until,
                    next_verification_date=eq.next_verification_date,
                    donor_reserve_count=reserve_count,
                    missing_coords=missing_coords,
                )
            )

        # Ранжируем доноров:
        # 1. По дистанции (ближайшие в первую очередь);
        # 2. По остаточному запасу дней поверки (больший запас лучше);
        # 3. По величине резерва на МПД-доноре.
        donor_options.sort(
            key=lambda d: (
                d.distance_km,
                -(d.days_until_expiration or 9999),
                -d.donor_reserve_count,
            )
        )

        return donor_options

    @staticmethod
    def _get_busy_equipment_ids(
        mpd: PlaceProductionActivity,
        date_start: date,
        date_end: date,
    ) -> set:
        """Находит ID приборов, занятых в незавершенных картах-нарядах на этом МПД в период ТО."""
        # 1. Карты-наряды на данном МПД, которые еще не подписаны (is_signed=False)
        # и перекрывают период [date_start, date_end]
        overlapping_cards = OutfitCard.objects.filter(
            outfit_card_place=mpd,
            is_signed=False,
        ).filter(
            Q(outfit_card_date_end__gte=date_start) | Q(outfit_card_date_end__isnull=True),
            outfit_card_date__lte=date_end,
        )

        busy_m2m = set(
            overlapping_cards.values_list("used_equipment", flat=True)
        )
        busy_audit = set(
            OutfitCardEquipmentUsage.objects.filter(
                outfit_card__in=overlapping_cards
            ).values_list("equipment_id", flat=True)
        )

        # 2. Приборы, зарезервированные в заявках на перемещение (в пути или запрошены)
        busy_transfers = set(
            EquipmentTransferRequest.objects.filter(
                status__in=[
                    EquipmentTransferStatus.REQUESTED,
                    EquipmentTransferStatus.IN_TRANSIT,
                ]
            ).values_list("equipment_id", flat=True)
        )

        all_busy = (busy_m2m | busy_audit | busy_transfers) - {None}
        return all_busy


@transaction.atomic
def copy_work_equipment_requirements(
    source_work: Union[PeriodicWork, OperationalWork],
    target_work: Union[PeriodicWork, OperationalWork],
    mode: str = "append",
) -> Tuple[int, int]:
    """Копирует или тиражирует нормативы табеля оснащения между формами ТО ВС (ФАП-145).

    Позволяет перенести утвержденный комплект требований из одной формы ТО
    (например, 'Ми-8Т - Ф-1') в другую форму ('Ми-8Т - Ф-2' или оперативное обслуживание)
    в режиме дополнения (пропуская существующие позиции) или полной перезаписи.

    Args:
        source_work (Union[PeriodicWork, OperationalWork]): Исходная форма ТО с требованиями.
        target_work (Union[PeriodicWork, OperationalWork]): Целевая форма ТО, куда копируются нормативы.
        mode (str): Режим копирования ('append' - дополнить, 'replace' - перезаписать с удалением). Defaults to 'append'.

    Returns:
        Tuple[int, int]: Кортеж (число_созданных_позиций, число_пропущенных_дубликатов).

    Raises:
        ValueError: Если указан некорректный режим копирования или исходная форма совпадает с целевой.
    """
    if source_work == target_work:
        raise ValueError("Исходная форма ТО совпадает с целевой формой.")

    if mode not in ("append", "replace"):
        raise ValueError(f"Неизвестный режим копирования: {mode}. Ожидается 'append' или 'replace'.")

    is_target_periodic = isinstance(target_work, PeriodicWork)

    if mode == "replace":
        target_work.equipment_requirements.all().delete()

    created_count = 0
    skipped_count = 0

    source_requirements = source_work.equipment_requirements.select_related(
        "equipment_name", "required_type"
    ).prefetch_related("allowed_substitutes").all()

    for src_req in source_requirements:
        lookup_kwargs = {
            "equipment_name": src_req.equipment_name,
            "required_type": src_req.required_type,
        }
        if is_target_periodic:
            lookup_kwargs["periodic_work"] = target_work
        else:
            lookup_kwargs["operational_work"] = target_work

        existing = MaintenanceWorkEquipmentRequirement.objects.filter(**lookup_kwargs).first()
        if existing and mode == "append":
            skipped_count += 1
            continue

        if existing:
            target_req = existing
            target_req.quantity = src_req.quantity
            target_req.is_mandatory = src_req.is_mandatory
            target_req.task_reference = src_req.task_reference
            target_req.save()
        else:
            target_req = MaintenanceWorkEquipmentRequirement.objects.create(
                periodic_work=target_work if is_target_periodic else None,
                operational_work=None if is_target_periodic else target_work,
                equipment_name=src_req.equipment_name,
                required_type=src_req.required_type,
                quantity=src_req.quantity,
                is_mandatory=src_req.is_mandatory,
                task_reference=src_req.task_reference,
            )

        substitutes = list(src_req.allowed_substitutes.all())
        if substitutes:
            target_req.allowed_substitutes.set(substitutes)
        else:
            target_req.allowed_substitutes.clear()

        created_count += 1

    return created_count, skipped_count

