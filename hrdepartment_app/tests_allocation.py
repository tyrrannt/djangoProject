"""Модульные и интеграционные тесты сервиса распределения оборудования ТО и логистики (ФАП-145).

Данный модуль изолирован для точечного запуска:
    python3 manage.py test hrdepartment_app.tests_allocation --keepdb

Покрывает:
1. Валидацию обеспечения МПД под периодические (PeriodicWork) и оперативные (OperationalWork) формы ТО;
2. Двойное бронирование (Double Booking Prevention) через параллельные незавершенные карты-наряды (OutfitCard);
3. Исключение инструмента без поверки (EquipmentVerificationType.NOT_REQUIRED) без ложных отбраковок;
4. Защиту от просроченных СИ (expired metrology check);
5. Гео-поиск и ранжирование доноров по расстоянию Haversine (GeoStationService);
6. Полный жизненный цикл заявок EquipmentTransferRequest со сменой МПД при приемке и возврате.
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts_app.models import Estate, TypeProperty
from customers_app.models import DataBaseUser
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentOperationalStatus,
    EquipmentTransferRequest,
    EquipmentTransferStatus,
    EquipmentType,
    EquipmentTypeModel,
    EquipmentVerificationType,
    MaintenanceEquipment,
    MaintenanceWorkEquipmentRequirement,
    OperationalWork,
    OutfitCard,
    PlaceProductionActivity,
    PeriodicWork,
)
from hrdepartment_app.services.equipment_allocation import (
    AllocationItemResult,
    EquipmentAllocationReport,
    EquipmentAllocationService,
    EquipmentDonorOption,
)


class EquipmentAllocationServiceTestCase(TestCase):
    """Тестирование сервиса интеллектуального подбора оборудования ТО (EquipmentAllocationService)."""

    def setUp(self) -> None:
        """Инициализация тестовых сущностей МПД, каталогов, регламентов и оборудования."""
        super().setUp()
        self.today = timezone.now().date()

        # 1. Пользователь
        self.user = DataBaseUser.objects.create_user(
            username="engineer_pto",
            email="pto@barkol.ru",
            password="pass",
            first_name="Иван",
            last_name="Инженеров",
            title="Инженеров И.И.",
            is_staff=True,
        )

        # 2. МПД базирования с координатами (Тюмень, Тобольск, Сургут)
        self.mpd_tyumen = PlaceProductionActivity.objects.create(
            name="МПД Тюмень (Рощино)",
            short_name="Тюмень",
            latitude=57.17,
            longitude=65.32,
        )
        self.mpd_tobolsk = PlaceProductionActivity.objects.create(
            name="МПД Тобольск",
            short_name="Тобольск",
            latitude=58.20,
            longitude=68.25,
        )
        self.mpd_surgut = PlaceProductionActivity.objects.create(
            name="МПД Сургут",
            short_name="Сургут",
            latitude=61.34,
            longitude=73.40,
        )

        # 3. Тип ВС и формы ТО (ПТО и ОТО)
        self.type_mi8 = TypeProperty.objects.create(type_property="Ми-8Т")
        self.pw_100 = PeriodicWork.objects.create(
            name="Форма 100 часов ТО Ми-8Т",
            code="100H",
            air_bord_type=self.type_mi8,
            ratio=8.0,
        )
        self.ow_a1 = OperationalWork.objects.create(
            name="Форма А1 оперативного ТО Ми-8Т",
            code="А1",
            air_bord_type=self.type_mi8,
        )

        # 4. Нормализованный каталог СИ (Уровни 1 и 2)
        self.eq_name_torque = EquipmentName.objects.create(
            name="Динамометрический ключ предельный",
            category=EquipmentType.SPECIAL_TOOL,
        )
        self.model_torque_km = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_torque,
            name="КМ-100",
            part_number="KM-100",
            default_interval_months=12,
        )
        self.model_torque_sta = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_torque,
            name="Stahlwille 730N/20",
            part_number="730N/20",
            default_interval_months=12,
        )

        self.eq_name_multimeter = EquipmentName.objects.create(
            name="Мультиметр цифровой прецизионный",
            category=EquipmentType.MEASURING,
        )
        self.model_fluke = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_multimeter,
            name="Fluke 179",
            part_number="FLUKE-179",
            default_interval_months=12,
            arshin_type_number="50000-12",
        )

        self.eq_name_ladder = EquipmentName.objects.create(
            name="Стремянка технологическая ТО",
            category=EquipmentType.GROUND_EQUIPMENT,
        )
        self.model_ladder = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_ladder,
            name="СП-1",
            part_number="SP-1",
        )

        # 5. Требования табеля оснащения под ПТО (pw_100)
        self.req_torque = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.pw_100,
            equipment_name=self.eq_name_torque,
            required_type=self.model_torque_km,
            quantity=1,
            is_mandatory=True,
            task_reference="Карта-смазка п. 4.1",
        )
        self.req_torque.allowed_substitutes.add(self.model_torque_sta)

        self.req_multimeter = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.pw_100,
            equipment_name=self.eq_name_multimeter,
            required_type=self.model_fluke,
            quantity=1,
            is_mandatory=True,
            task_reference="Проверка цепей п. 2.3",
        )

        self.req_ladder = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.pw_100,
            equipment_name=self.eq_name_ladder,
            required_type=self.model_ladder,
            quantity=1,
            is_mandatory=False,
            task_reference="Доступ к агрегатам",
        )

        # 6. Требования табеля оснащения под ОТО (ow_a1)
        self.req_ow_multimeter = MaintenanceWorkEquipmentRequirement.objects.create(
            operational_work=self.ow_a1,
            equipment_name=self.eq_name_multimeter,
            required_type=self.model_fluke,
            quantity=1,
            is_mandatory=True,
            task_reference="Контроль АКБ",
        )

    def test_full_satisfaction_allocation(self) -> None:
        """Проверяет 100% готовность МПД при наличии всех исправных и поверенных приборов."""
        # Создаем приборы в Тюмени
        MaintenanceEquipment.objects.create(
            type_model=self.model_torque_km,
            serial_number="TK-001",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=90),
        )
        MaintenanceEquipment.objects.create(
            type_model=self.model_fluke,
            serial_number="FLK-001",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=90),
        )
        MaintenanceEquipment.objects.create(
            type_model=self.model_ladder,
            serial_number="LAD-001",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
            next_verification_date=None,
        )

        service = EquipmentAllocationService(
            work_object=self.pw_100,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        report: EquipmentAllocationReport = service.calculate_allocation()

        self.assertTrue(report.is_fully_ready)
        self.assertEqual(report.readiness_percentage, 100.0)
        self.assertEqual(report.total_requirements_count, 3)
        self.assertEqual(report.satisfied_requirements_count, 3)
        self.assertEqual(report.deficit_items_count, 0)
        self.assertEqual(report.mandatory_deficit_count, 0)

        # Проверяем детальный статус каждой позиции
        for item in report.items:
            self.assertEqual(item.status, "AVAILABLE")
            self.assertEqual(item.allocated_count, 1)
            self.assertEqual(item.deficit_count, 0)

    def test_double_booking_exclusion(self) -> None:
        """Проверяет исключение прибора, занятого в незавершенной карте-наряде на целевом МПД."""
        torque_tool = MaintenanceEquipment.objects.create(
            type_model=self.model_torque_km,
            serial_number="TK-002",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=90),
        )
        MaintenanceEquipment.objects.create(
            type_model=self.model_fluke,
            serial_number="FLK-002",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=90),
        )
        MaintenanceEquipment.objects.create(
            type_model=self.model_ladder,
            serial_number="LAD-002",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
        )

        # Создаем открытую (неподписанную) карту-наряд на этом МПД, занимающую динамометрический ключ
        estate = Estate.objects.create(
            registration_number="RA-22222",
            type_property=self.type_mi8,
            release_date=self.today,
        )
        card = OutfitCard.objects.create(
            air_board=estate,
            outfit_card_place=self.mpd_tyumen,
            outfit_card_date=self.today,
            outfit_card_date_end=self.today + timedelta(days=5),
            is_signed=False,
        )
        card.used_equipment.add(torque_tool)

        service = EquipmentAllocationService(
            work_object=self.pw_100,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        report = service.calculate_allocation()

        self.assertFalse(report.is_fully_ready)
        # Динамометрический ключ должен быть исключен (дефицит), а остальные 2 прибора выделены
        torque_item = next(
            (it for it in report.items if it.requirement_id == self.req_torque.pk), None
        )
        self.assertIsNotNone(torque_item)
        self.assertEqual(torque_item.allocated_count, 0)
        self.assertEqual(torque_item.deficit_count, 1)
        self.assertEqual(torque_item.status, "DEFICIT")

    def test_metrology_not_required_bypass(self) -> None:
        """Проверяет корректность признания годным инструмента с видом NOT_REQUIRED без даты поверки."""
        ladder = MaintenanceEquipment.objects.create(
            type_model=self.model_ladder,
            serial_number="LAD-BYPASS",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
            next_verification_date=None,
        )
        service = EquipmentAllocationService(
            work_object=self.pw_100,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        is_valid, reason = service._is_equipment_metrology_valid(ladder)
        self.assertTrue(is_valid)
        self.assertIn("не требуется", reason)

    def test_expired_metrology_rejected(self) -> None:
        """Проверяет отбраковку просроченного СИ и фиксацию статуса EXPIRED_LOCAL."""
        MaintenanceEquipment.objects.create(
            type_model=self.model_fluke,
            serial_number="FLK-EXPIRED",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today - timedelta(days=3),  # Просрочен
        )

        service = EquipmentAllocationService(
            work_object=self.ow_a1,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        report = service.calculate_allocation()

        self.assertFalse(report.is_fully_ready)
        item = report.items[0]
        self.assertEqual(item.status, "EXPIRED_LOCAL")
        self.assertEqual(len(item.expired_local_equipment), 1)
        self.assertEqual(item.allocated_count, 0)

    def test_donor_ranking_haversine_distance(self) -> None:
        """Проверяет гео-поиск и ранжирование доноров по расстоянию от МПД назначения (Haversine)."""
        # В Тюмени прибор отсутствует.
        # Создаем прибор в Тобольске (~180 км от Тюмени)
        MaintenanceEquipment.objects.create(
            type_model=self.model_torque_km,
            serial_number="TK-TOBOLSK",
            production_place=self.mpd_tobolsk,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=120),
        )
        # Создаем прибор в Сургуте (~650 км от Тюмени)
        MaintenanceEquipment.objects.create(
            type_model=self.model_torque_km,
            serial_number="TK-SURGUT",
            production_place=self.mpd_surgut,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=120),
        )

        service = EquipmentAllocationService(
            work_object=self.pw_100,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        report = service.calculate_allocation()

        torque_item = next(it for it in report.items if it.requirement_id == self.req_torque.pk)
        self.assertGreaterEqual(len(torque_item.donors), 2)

        donor_1 = torque_item.donors[0]
        donor_2 = torque_item.donors[1]

        # Ближайший донор обязан быть Тобольск, второй — Сургут
        self.assertEqual(donor_1.mpd_id, self.mpd_tobolsk.pk)
        self.assertEqual(donor_2.mpd_id, self.mpd_surgut.pk)
        self.assertLess(donor_1.distance_km, donor_2.distance_km)

    def test_operational_work_allocation(self) -> None:
        """Проверяет валидацию обеспечения оперативной формы обслуживания (OperationalWork)."""
        MaintenanceEquipment.objects.create(
            type_model=self.model_fluke,
            serial_number="FLK-OW-01",
            production_place=self.mpd_tyumen,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            next_verification_date=self.today + timedelta(days=90),
        )

        service = EquipmentAllocationService(
            work_object=self.ow_a1,
            target_mpd=self.mpd_tyumen,
            target_date_start=self.today,
        )
        report = service.calculate_allocation()

        self.assertEqual(report.work_category, "OPERATIONAL")
        self.assertEqual(report.total_requirements_count, 1)
        self.assertTrue(report.is_fully_ready)
        self.assertEqual(report.items[0].status, "AVAILABLE")


class EquipmentTransferWorkflowTestCase(TestCase):
    """Интеграционное тестирование заявок на перемещение оборудования между МПД."""

    def setUp(self) -> None:
        """Подготовка пользователей, МПД и единицы оборудования."""
        super().setUp()
        self.today = timezone.now().date()
        self.client = Client()

        self.user = DataBaseUser.objects.create_user(
            username="logistician",
            email="logist@barkol.ru",
            password="testpassword",
            first_name="Олег",
            last_name="Логистов",
            title="Логистов О.А.",
            is_staff=True,
        )
        # Назначаем права доступа к заявкам
        content_type = ContentType.objects.get_for_model(EquipmentTransferRequest)
        perms = Permission.objects.filter(content_type=content_type)
        self.user.user_permissions.set(perms)

        self.mpd_donor = PlaceProductionActivity.objects.create(
            name="МПД Тобольск",
            short_name="Тобольск",
            latitude=58.20,
            longitude=68.25,
        )
        self.mpd_target = PlaceProductionActivity.objects.create(
            name="МПД Тюмень",
            short_name="Тюмень",
            latitude=57.17,
            longitude=65.32,
        )

        self.eq_name = EquipmentName.objects.create(
            name="Ключ моментный",
            category=EquipmentType.SPECIAL_TOOL,
        )
        self.model = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name,
            name="КМ-100",
            part_number="KM-100",
        )
        self.equipment = MaintenanceEquipment.objects.create(
            type_model=self.model,
            serial_number="LOG-001",
            production_place=self.mpd_donor,
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
        )

    def test_transfer_status_transitions_and_production_place_updates(self) -> None:
        """Проверяет переключение статусов заявки и автоматическую смену production_place оборудования."""
        self.client.login(username="logistician", password="testpassword")

        # 1. Создаем заявку
        transfer = EquipmentTransferRequest.objects.create(
            equipment=self.equipment,
            from_mpd=self.mpd_donor,
            to_mpd=self.mpd_target,
            required_date=self.today + timedelta(days=2),
            status=EquipmentTransferStatus.REQUESTED,
            created_by=self.user,
        )
        self.assertEqual(self.equipment.production_place, self.mpd_donor)

        status_update_url = reverse(
            "hrdepartment_app:equipment_transfer_status_update",
            kwargs={"pk": transfer.pk},
        )

        # 2. Переводим статус в IN_TRANSIT
        response = self.client.post(
            status_update_url,
            {"status": EquipmentTransferStatus.IN_TRANSIT, "tracking_number": "TRACK-777"},
        )
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(transfer.status, EquipmentTransferStatus.IN_TRANSIT)
        self.assertEqual(transfer.tracking_number, "TRACK-777")
        self.assertEqual(self.equipment.production_place, self.mpd_donor)

        # 3. Доставка на целевое МПД (DELIVERED) -> МПД оборудования должно стать mpd_target (Тюмень)
        response = self.client.post(
            status_update_url,
            {"status": EquipmentTransferStatus.DELIVERED},
        )
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(transfer.status, EquipmentTransferStatus.DELIVERED)
        self.assertEqual(self.equipment.production_place, self.mpd_target)

        # 4. Возврат на домашнее МПД (RETURNED) -> МПД оборудования должно вернуться в mpd_donor (Тобольск)
        response = self.client.post(
            status_update_url,
            {"status": EquipmentTransferStatus.RETURNED},
        )
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(transfer.status, EquipmentTransferStatus.RETURNED)
        self.assertEqual(self.equipment.production_place, self.mpd_donor)
