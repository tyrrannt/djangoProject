"""Модульные тесты табеля оснащения регламентных работ ТО ВС (ФАП-145).

Тестирует:
1. Валидацию фильтра EquipmentAllocationFilterForm (прием форматов дат dd.mm.yyyy и yyyy-mm-dd без сброса);
2. Представление PeriodicWorkRequirementsView (GET список требований, POST добавление строгой модели СИ и допустимых аналогов);
3. Представление PeriodicWorkRequirementDeleteView (удаление позиции табеля с сохранением контекста);
4. Корректность отбора типов СИ через EquipmentTypesByNameHTMXView.
"""

from datetime import date
from typing import Dict, Any

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from contracts_app.models import TypeProperty
from hrdepartment_app.forms import (
    EquipmentAllocationFilterForm,
    MaintenanceWorkEquipmentRequirementForm,
)
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentType,
    EquipmentTypeModel,
    MaintenanceWorkEquipmentRequirement,
    PeriodicWork,
    PlaceProductionActivity,
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
