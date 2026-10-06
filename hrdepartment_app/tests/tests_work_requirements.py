"""Модульные тесты табеля оснащения регламентных работ ТО ВС (ФАП-145).

Тестирует:
1. Валидацию фильтра EquipmentAllocationFilterForm (прием форматов дат dd.mm.yyyy и yyyy-mm-dd без сброса);
2. Представление PeriodicWorkRequirementsView (GET список требований, POST добавление строгой модели СИ и допустимых аналогов);
3. Представление PeriodicWorkRequirementDeleteView (удаление позиции табеля с сохранением контекста);
4. Корректность отбора типов СИ через EquipmentTypesByNameHTMXView;
5. Сервис и представление тиражирования табелей оснащения (copy_work_equipment_requirements, PeriodicWorkRequirementsCopyView);
6. Реестр заявок на перемещение оборудования и переходы статусов (EquipmentTransferRequestListView, EquipmentTransferRequestStatusUpdateView);
7. Сервис и представление контроля обеспеченности карт-нарядов оборудованием (get_outfit_card_requirements_allocation, OutfitCardDetailView).
"""

from datetime import date, timedelta
from typing import Dict, Any, List

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts_app.models import TypeProperty
from hrdepartment_app.forms import (
    EquipmentAllocationFilterForm,
    MaintenanceWorkEquipmentRequirementForm,
    MaintenanceWorkRequirementsCopyForm,
)
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentTransferRequest,
    EquipmentType,
    EquipmentTypeModel,
    MaintenanceEquipment,
    MaintenanceWorkEquipmentRequirement,
    OutfitCard,
    OutfitCardEquipmentUsage,
    PeriodicWork,
    PlaceProductionActivity,
)
from hrdepartment_app.services.equipment_allocation import copy_work_equipment_requirements
from hrdepartment_app.services.outfit_card_release_service import (
    get_outfit_card_requirements_allocation,
)

User = get_user_model()


class MaintenanceWorkRequirementsTests(TestCase):
    """Набор тестов для табеля оснащения регламентов ТО и фильтрации распределения."""

    def setUp(self) -> None:
        """Инициализация тестовых данных."""
        super().setUp()
        self.user = User.objects.create_user(
            username="engineer_fap",
            password="testpassword",
            email="engineer@example.com",
            first_name="Иван",
            last_name="Инженеров",
            title="Инженеров И.И.",
            is_staff=True,
            is_superuser=True,
        )

        self.mpd = PlaceProductionActivity.objects.create(
            name="Аэродром Мячково",
            short_name="Мячково",
        )

        self.aircraft_type = TypeProperty.objects.create(
            type_property="МИ-8Т",
        )

        self.periodic_work = PeriodicWork.objects.create(
            air_bord_type=self.aircraft_type,
            code="Ф-1",
            name="Форма регламента Ф-1 МИ-8Т",
            ratio=25.0,
        )

        self.eq_name_amp = EquipmentName.objects.create(
            name="Амперметр",
            category=EquipmentType.MEASURING,
        )

        self.model_amp_m42 = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_amp,
            name="М42300",
            part_number="M42300",
            default_interval_months=60,
        )

        self.model_amp_sub = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name_amp,
            name="М42100",
            part_number="M42100",
            default_interval_months=60,
        )

        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.user)

    def test_filter_form_date_formats(self) -> None:
        """Проверяет прием даты начала ТО в форматах dd.mm.yyyy и yyyy-mm-dd без сброса."""
        # 1. Формат dd.mm.yyyy
        form_dot = EquipmentAllocationFilterForm(
            data={
                "work_type": "periodic",
                "periodic_work": self.periodic_work.pk,
                "target_mpd": self.mpd.pk,
                "date_start": "06.10.2026",
                "safety_buffer_days": 7,
            }
        )
        self.assertTrue(form_dot.is_valid(), form_dot.errors)
        self.assertEqual(form_dot.cleaned_data["date_start"], date(2026, 10, 6))

        # 2. Формат yyyy-mm-dd
        form_iso = EquipmentAllocationFilterForm(
            data={
                "work_type": "periodic",
                "periodic_work": self.periodic_work.pk,
                "target_mpd": self.mpd.pk,
                "date_start": "2026-10-06",
                "safety_buffer_days": 7,
            }
        )
        self.assertTrue(form_iso.is_valid(), form_iso.errors)
        self.assertEqual(form_iso.cleaned_data["date_start"], date(2026, 10, 6))

    def test_filter_form_requires_work(self) -> None:
        """Проверяет обязательность выбора формы ТО при заполнении фильтра."""
        form_empty = EquipmentAllocationFilterForm(
            data={
                "work_type": "periodic",
                "target_mpd": self.mpd.pk,
                "date_start": "06.10.2026",
                "safety_buffer_days": 7,
            }
        )
        self.assertFalse(form_empty.is_valid())
        self.assertIn("periodic_work", form_empty.errors)

    def test_get_requirements_page(self) -> None:
        """Проверяет успешное отображение страницы табеля оснащения регламента."""
        url = reverse(
            "hrdepartment_app:periodic_work_requirements",
            kwargs={"pk": self.periodic_work.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Форма регламента Ф-1 МИ-8Т")
        self.assertContains(response, "Нормативные требования регламента к оборудованию")

    def test_post_add_requirement_strict_type_and_substitutes(self) -> None:
        """Проверяет добавление требования со строгим типом СИ и аналогами."""
        url = reverse(
            "hrdepartment_app:periodic_work_requirements",
            kwargs={"pk": self.periodic_work.pk},
        )
        post_data = {
            "equipment_name": self.eq_name_amp.pk,
            "required_type": self.model_amp_m42.pk,
            "allowed_substitutes": [self.model_amp_sub.pk],
            "quantity": 2,
            "is_mandatory": "on",
            "task_reference": "РО п. 4.1.2",
            "return_to": "dashboard",
            "target_mpd": str(self.mpd.pk),
            "date_start": "06.10.2026",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("return_to=dashboard", response.url)

        req = MaintenanceWorkEquipmentRequirement.objects.filter(
            periodic_work=self.periodic_work,
            equipment_name=self.eq_name_amp,
        ).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.required_type, self.model_amp_m42)
        self.assertEqual(req.quantity, 2)
        self.assertTrue(req.is_mandatory)
        self.assertEqual(req.task_reference, "РО п. 4.1.2")
        self.assertIn(self.model_amp_sub, req.allowed_substitutes.all())

    def test_post_add_requirement_any_type(self) -> None:
        """Проверяет добавление требования без строгого типа (любой исправный тип)."""
        url = reverse(
            "hrdepartment_app:periodic_work_requirements",
            kwargs={"pk": self.periodic_work.pk},
        )
        post_data = {
            "equipment_name": self.eq_name_amp.pk,
            "required_type": "",
            "quantity": 1,
            "is_mandatory": "on",
            "task_reference": "РО п. 5.0",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)

        req = MaintenanceWorkEquipmentRequirement.objects.filter(
            periodic_work=self.periodic_work,
            equipment_name=self.eq_name_amp,
        ).first()
        self.assertIsNotNone(req)
        self.assertIsNone(req.required_type)
        self.assertEqual(req.quantity, 1)

    def test_delete_requirement(self) -> None:
        """Проверяет удаление позиции из табеля оснащения."""
        req = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.periodic_work,
            equipment_name=self.eq_name_amp,
            required_type=self.model_amp_m42,
            quantity=1,
            is_mandatory=True,
        )
        delete_url = reverse(
            "hrdepartment_app:periodic_work_requirement_delete",
            kwargs={"pk": req.pk},
        )
        response = self.client.post(
            delete_url,
            data={
                "return_to": "dashboard",
                "target_mpd": str(self.mpd.pk),
                "date_start": "06.10.2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            MaintenanceWorkEquipmentRequirement.objects.filter(pk=req.pk).exists()
        )

    def test_types_by_name_ajax(self) -> None:
        """Проверяет AJAX/HTMX эндпоинт фильтрации типов СИ по родовому наименованию."""
        url = reverse("hrdepartment_app:equipment_types_by_name")
        response = self.client.get(url, {"name_id": self.eq_name_amp.pk})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("М42300", content)
        self.assertIn("М42100", content)


class MaintenanceWorkRequirementsCopyTests(TestCase):
    """Набор тестов для сервиса и представления тиражирования табелей оснащения ТО (Шаг 2)."""

    def setUp(self) -> None:
        """Инициализация тестовых данных для копирования табелей."""
        super().setUp()
        self.user = User.objects.create_user(
            username="tech_engineer",
            password="testpassword",
            email="tech@example.com",
            first_name="Петр",
            last_name="Технологов",
            title="Технологов П.П.",
            is_staff=True,
            is_superuser=True,
        )

        self.aircraft_type = TypeProperty.objects.create(
            type_property="Ан-2",
        )

        self.source_work = PeriodicWork.objects.create(
            air_bord_type=self.aircraft_type,
            code="Ф-1",
            name="Форма Ф-1 Ан-2 (Источник)",
            ratio=10.0,
        )

        self.target_work = PeriodicWork.objects.create(
            air_bord_type=self.aircraft_type,
            code="Ф-2",
            name="Форма Ф-2 Ан-2 (Целевая)",
            ratio=20.0,
        )

        self.eq_amp = EquipmentName.objects.create(
            name="Амперметр",
            category=EquipmentType.MEASURING,
        )
        self.model_amp = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_amp,
            name="М42300",
            default_interval_months=60,
        )
        self.sub_amp = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_amp,
            name="М42100",
            default_interval_months=60,
        )

        self.eq_volt = EquipmentName.objects.create(
            name="Вольтметр",
            category=EquipmentType.MEASURING,
        )
        self.model_volt = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_volt,
            name="В7-40",
            default_interval_months=12,
        )

        # Создаем требования для формы-источника
        self.req_source_1 = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.source_work,
            equipment_name=self.eq_amp,
            required_type=self.model_amp,
            quantity=2,
            is_mandatory=True,
            task_reference="РО п. 1.1",
        )
        self.req_source_1.allowed_substitutes.add(self.sub_amp)

        self.req_source_2 = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.source_work,
            equipment_name=self.eq_volt,
            required_type=self.model_volt,
            quantity=1,
            is_mandatory=True,
            task_reference="РО п. 1.2",
        )

        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.user)

    def test_copy_service_append_mode(self) -> None:
        """Проверяет копирование табеля в режиме дополнения (append) без дубликатов."""
        # Создаем одно существующее требование в целевой форме (Амперметр)
        MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.target_work,
            equipment_name=self.eq_amp,
            required_type=self.model_amp,
            quantity=1,
            is_mandatory=False,
        )

        copied_count, skipped_count = copy_work_equipment_requirements(
            source_work=self.source_work,
            target_work=self.target_work,
            mode="append",
        )

        self.assertEqual(copied_count, 1)  # Добавлен только Вольтметр
        self.assertEqual(skipped_count, 1)  # Амперметр пропущен
        self.assertEqual(self.target_work.equipment_requirements.count(), 2)

        volt_req = self.target_work.equipment_requirements.filter(equipment_name=self.eq_volt).first()
        self.assertIsNotNone(volt_req)
        self.assertEqual(volt_req.required_type, self.model_volt)

    def test_copy_service_replace_mode(self) -> None:
        """Проверяет копирование табеля в режиме полной перезаписи (replace)."""
        # Создаем старое требование в целевой форме
        MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.target_work,
            equipment_name=self.eq_amp,
            quantity=99,
        )

        copied_count, skipped_count = copy_work_equipment_requirements(
            source_work=self.source_work,
            target_work=self.target_work,
            mode="replace",
        )

        self.assertEqual(copied_count, 2)
        self.assertEqual(skipped_count, 0)
        self.assertEqual(self.target_work.equipment_requirements.count(), 2)

        copied_amp = self.target_work.equipment_requirements.filter(equipment_name=self.eq_amp).first()
        self.assertIsNotNone(copied_amp)
        self.assertEqual(copied_amp.quantity, 2)
        self.assertEqual(copied_amp.task_reference, "РО п. 1.1")
        self.assertIn(self.sub_amp, copied_amp.allowed_substitutes.all())

    def test_copy_view_post_success(self) -> None:
        """Проверяет выполнение тиражирования табеля через веб-представление."""
        copy_url = reverse(
            "hrdepartment_app:periodic_work_requirements_copy",
            kwargs={"pk": self.target_work.pk},
        )
        post_data = {
            "source_work": self.source_work.pk,
            "mode": "replace",
        }
        response = self.client.post(copy_url, data=post_data)
        expected_redirect = reverse(
            "hrdepartment_app:periodic_work_requirements",
            kwargs={"pk": self.target_work.pk},
        )
        self.assertRedirects(response, expected_redirect)
        self.assertEqual(self.target_work.equipment_requirements.count(), 2)


class EquipmentTransferRequestManagementTests(TestCase):
    """Набор тестов для пользовательского интерфейса управления перемещениями оборудования (Шаг 3)."""

    def setUp(self) -> None:
        """Инициализация данных для перемещений СИ между МПД."""
        super().setUp()
        self.user = User.objects.create_user(
            username="logist_user",
            password="testpassword",
            email="logist@example.com",
            first_name="Сергей",
            last_name="Логистов",
            title="Логистов С.С.",
            is_staff=True,
            is_superuser=True,
        )

        self.mpd_myachkovo = PlaceProductionActivity.objects.create(
            name="Участок ТО Мячково",
            short_name="Мячково",
        )
        self.mpd_lopatino = PlaceProductionActivity.objects.create(
            name="Участок ТО Лопатино",
            short_name="Лопатино",
        )

        self.eq_name = EquipmentName.objects.create(
            name="Ваттметр",
            category=EquipmentType.MEASURING,
        )
        self.eq_model = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name,
            name="М3-56",
            default_interval_months=12,
        )

        self.equipment = MaintenanceEquipment.objects.create(
            name="Ваттметр М3-56 (14111)",
            type_model=self.eq_model,
            serial_number="14111",
            equipment_type=EquipmentType.MEASURING,
            production_place=self.mpd_myachkovo,
            operational_status="serviceable",
            verification_type="verification",
            next_verification_date=date(2026, 12, 31),
        )

        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.user)

    def test_transfer_list_view_and_kpis(self) -> None:
        """Проверяет отображение реестра перемещений и расчет KPI-счетчиков."""
        # Создаем заявки в разных статусах
        EquipmentTransferRequest.objects.create(
            equipment=self.equipment,
            from_mpd=self.mpd_myachkovo,
            to_mpd=self.mpd_lopatino,
            required_date=date(2026, 10, 10),
            status="requested",
            created_by=self.user,
        )
        EquipmentTransferRequest.objects.create(
            equipment=self.equipment,
            from_mpd=self.mpd_myachkovo,
            to_mpd=self.mpd_lopatino,
            required_date=date(2026, 10, 11),
            status="in_transit",
            tracking_number="CDEK-100",
            created_by=self.user,
        )
        EquipmentTransferRequest.objects.create(
            equipment=self.equipment,
            from_mpd=self.mpd_lopatino,
            to_mpd=self.mpd_myachkovo,
            required_date=date(2026, 10, 12),
            status="delivered",
            created_by=self.user,
        )

        list_url = reverse("hrdepartment_app:equipment_transfer_list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["kpi_total"], 3)
        self.assertEqual(response.context["kpi_requested"], 1)
        self.assertEqual(response.context["kpi_in_transit"], 1)
        self.assertEqual(response.context["kpi_delivered"], 1)
        self.assertEqual(response.context["kpi_returned"], 0)

        # Проверяем фильтрацию по статусу
        filter_resp = self.client.get(list_url, {"status": "in_transit"})
        self.assertEqual(len(filter_resp.context["transfers"]), 1)
        self.assertContains(filter_resp, "CDEK-100")

    def test_transfer_status_transitions_and_location_update(self) -> None:
        """Проверяет жизненный цикл заявки и автоматическое перемещение оборудования между МПД."""
        transfer = EquipmentTransferRequest.objects.create(
            equipment=self.equipment,
            from_mpd=self.mpd_myachkovo,
            to_mpd=self.mpd_lopatino,
            required_date=date(2026, 10, 15),
            status="requested",
            created_by=self.user,
        )

        update_url = reverse(
            "hrdepartment_app:equipment_transfer_status_update",
            kwargs={"pk": transfer.pk},
        )

        # 1. Смена статуса на "В пути" с трек-номером
        post_transit = {
            "status": "in_transit",
            "tracking_number": "TRK-555444",
            "notes": "Передано курьеру",
        }
        resp = self.client.post(update_url, data=post_transit)
        self.assertEqual(resp.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "in_transit")
        self.assertEqual(transfer.tracking_number, "TRK-555444")
        self.assertIn("Передано курьеру", transfer.notes)

        # 2. Смена статуса на "Доставлено на МПД" -> прибор должен сменить местонахождение на mpd_lopatino
        post_delivered = {
            "status": "delivered",
            "notes": "Принято кладовщиком в Лопатино",
        }
        self.client.post(update_url, data=post_delivered)
        transfer.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(transfer.status, "delivered")
        self.assertEqual(self.equipment.production_place, self.mpd_lopatino)

        # 3. Смена статуса на "Возвращено" -> прибор возвращается на исходный МПД mpd_myachkovo
        post_returned = {
            "status": "returned",
            "notes": "Возвращено после выполнения ТО",
        }
        self.client.post(update_url, data=post_returned)
        transfer.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(transfer.status, "returned")
        self.assertEqual(self.equipment.production_place, self.mpd_myachkovo)


class OutfitCardEquipmentRequirementsAllocationTests(TestCase):
    """Набор тестов для сервиса и карточки наряда по контролю обеспеченности ТО (Шаг 4)."""

    def setUp(self) -> None:
        """Инициализация данных для карты-наряда и табеля оснащения."""
        super().setUp()
        self.user = User.objects.create_user(
            username="brigade_lead",
            password="testpassword",
            email="lead@example.com",
            first_name="Алексей",
            last_name="Бригадиров",
            title="Бригадиров А.А.",
            is_staff=True,
            is_superuser=True,
        )

        self.mpd = PlaceProductionActivity.objects.create(
            name="Участок ТО Пенза",
            short_name="Пенза",
        )

        self.aircraft_type = TypeProperty.objects.create(
            type_property="МИ-8АМТ",
        )

        self.periodic_work = PeriodicWork.objects.create(
            air_bord_type=self.aircraft_type,
            code="Ф-300",
            name="Форма 300 ч МИ-8АМТ",
            ratio=50.0,
        )

        self.eq_name = EquipmentName.objects.create(
            name="Секундомер",
            category=EquipmentType.MEASURING,
        )
        self.eq_model = EquipmentTypeModel.objects.create(
            equipment_name=self.eq_name,
            name="СОПпр",
            default_interval_months=12,
        )

        # Создаем норматив в табеле: требуется 1 секундомер
        self.req = MaintenanceWorkEquipmentRequirement.objects.create(
            periodic_work=self.periodic_work,
            equipment_name=self.eq_name,
            required_type=self.eq_model,
            quantity=1,
            is_mandatory=True,
            task_reference="РО 5.2.1",
        )

        self.outfit_card = OutfitCard.objects.create(
            outfit_card_number="НАР-2026-001",
            outfit_card_date=date(2026, 10, 10),
            outfit_card_place=self.mpd,
            employee=self.user,
        )
        self.outfit_card.periodic_work.add(self.periodic_work)

        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.user)

    def test_outfit_card_allocation_deficit_and_full(self) -> None:
        """Проверяет обнаружение дефицита и последующее 100% покрытие табеля при наличии прибора."""
        # 1. Прибора на МПД нет -> дефицит
        alloc_deficit = get_outfit_card_requirements_allocation(self.outfit_card)
        self.assertFalse(alloc_deficit["is_fully_ready"])
        self.assertEqual(alloc_deficit["deficit_count"], 1)
        self.assertTrue(alloc_deficit["has_mandatory_deficit"])
        self.assertEqual(len(alloc_deficit["work_reports"]), 1)
        req_item = alloc_deficit["work_reports"][0]["items_detail"][0]
        self.assertEqual(req_item["item"].status, "DEFICIT")
        self.assertEqual(req_item["item"].allocated_count, 0)
        self.assertEqual(req_item["item"].deficit_count, 1)

        # 2. Создаем исправный секундомер на МПД Пенза с действующей поверкой
        equipment = MaintenanceEquipment.objects.create(
            name="Секундомер СОПпр (00991)",
            type_model=self.eq_model,
            serial_number="00991",
            equipment_type=EquipmentType.MEASURING,
            production_place=self.mpd,
            operational_status="serviceable",
            verification_type="verification",
            next_verification_date=date(2026, 12, 31),
        )

        alloc_ok = get_outfit_card_requirements_allocation(self.outfit_card)
        self.assertTrue(alloc_ok["is_fully_ready"])
        self.assertEqual(alloc_ok["deficit_count"], 0)
        self.assertFalse(alloc_ok["has_mandatory_deficit"])
        item_ok = alloc_ok["work_reports"][0]["items_detail"][0]
        self.assertEqual(item_ok["item"].status, "AVAILABLE")
        self.assertEqual(item_ok["item"].allocated_count, 1)
        self.assertEqual(item_ok["item"].deficit_count, 0)

        # 3. Фиксируем применение прибора в наряде через OutfitCardEquipmentUsage
        OutfitCardEquipmentUsage.objects.create(
            outfit_card=self.outfit_card,
            equipment=equipment,
            equipment_name=equipment.name,
            part_number="СОПпр",
            serial_number="00991",
            is_valid_at_usage=True,
        )

        alloc_used = get_outfit_card_requirements_allocation(self.outfit_card)
        item_used = alloc_used["work_reports"][0]["items_detail"][0]
        self.assertTrue(item_used["is_attached_to_card"])
        self.assertIn("00991", item_used["attached_equipment_sn"])

    def test_outfit_card_detail_view_context(self) -> None:
        """Проверяет передачу структуры обеспеченности в контекст детального просмотра наряда."""
        detail_url = reverse(
            "hrdepartment_app:outfit_card_detail",
            kwargs={"pk": self.outfit_card.pk},
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("requirements_allocation", response.context)
        self.assertIn("equipment_summary", response.context)
        content = response.content.decode("utf-8")
        self.assertIn("Обеспеченность табеля оснащения ТО на МПД", content)


