"""Модульные тесты выгрузки печатной ведомости оборудования, КПА и инструмента в Excel (ФАП-145, 102-ФЗ).

Тестирует:
1. Сервис export_maintenance_equipment_to_excel (генерация книги openpyxl, формат A4 Landscape, шапка, строки, сводка, подписи);
2. Представление EquipmentExportExcelView (авторизация, Content-Disposition, поток .xlsx);
3. Фильтрацию данных при экспорте (поиск, МПД, категория, физический и метрологический статус);
4. Проверку защиты эндпоинта от неавторизованного доступа (302 Redirect).
"""

import io
from datetime import date, timedelta
from typing import Dict, Any, List

import openpyxl
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts_app.models import TypeProperty
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentOperationalStatus,
    EquipmentType,
    EquipmentTypeModel,
    EquipmentVerificationType,
    MaintenanceEquipment,
    PlaceProductionActivity,
)
from hrdepartment_app.services.equipment_export import export_maintenance_equipment_to_excel
from hrdepartment_app.views import filter_maintenance_equipment_queryset

User = get_user_model()


class EquipmentExportExcelTests(TestCase):
    """Набор тестов для сервиса и веб-представления выгрузки ведомости оборудования в Excel."""

    def setUp(self) -> None:
        """Инициализация тестовых данных для выгрузки в Excel."""
        super().setUp()
        self.user = User.objects.create_user(
            username="metrologist_export",
            password="testpassword",
            email="metro@example.com",
            first_name="Матвей",
            last_name="Метрологов",
            title="Метрологов М.М.",
            is_staff=True,
            is_superuser=True,
        )

        self.mpd_myachkovo = PlaceProductionActivity.objects.create(
            name="Участок ТО Мячково",
            short_name="Мячково",
        )
        self.mpd_penza = PlaceProductionActivity.objects.create(
            name="Участок ТО Пенза",
            short_name="Пенза",
        )

        self.aircraft_type = TypeProperty.objects.create(
            type_property="Ми-8Т",
        )

        # 1. Амперметр (СИ, годен)
        self.name_amp = EquipmentName.objects.create(
            name="Амперметр",
            category=EquipmentType.MEASURING,
        )
        self.model_amp = EquipmentTypeModel.objects.create(
            equipment_name=self.name_amp,
            name="М42300",
            part_number="M42300-01",
            default_interval_months=60,
            measurement_range="0 - 10А",
            accuracy_class="1,5",
        )
        self.eq_valid = MaintenanceEquipment.objects.create(
            name="Амперметр М42300",
            type_model=self.model_amp,
            part_number="M42300-01",
            serial_number="AMP-1001",
            marking_code="ИР-01-20",
            equipment_type=EquipmentType.MEASURING,
            production_place=self.mpd_myachkovo,
            location="Лаборатория / Стенд УКВ",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=date(2025, 1, 15),
            next_verification_date=timezone.now().date() + timedelta(days=180),
            interval_value=60,
            arshin_verification_number="С-БНГ/15-01-2025/112233",
            verification_organization="Ростест-Москва",
            responsible_person=self.user,
        )
        self.eq_valid.applicable_aircraft_types.add(self.aircraft_type)

        # 2. Секундомер (СИ, поверка истекает через 15 дней)
        self.name_sec = EquipmentName.objects.create(
            name="Секундомер",
            category=EquipmentType.MEASURING,
        )
        self.model_sec = EquipmentTypeModel.objects.create(
            equipment_name=self.name_sec,
            name="СОПпр",
            part_number="SOP-01",
            default_interval_months=12,
        )
        self.eq_expiring = MaintenanceEquipment.objects.create(
            name="Секундомер СОПпр",
            type_model=self.model_sec,
            part_number="SOP-01",
            serial_number="SEC-5544",
            marking_code="ИР-02-21",
            equipment_type=EquipmentType.MEASURING,
            production_place=self.mpd_myachkovo,
            location="Лаборатория",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=timezone.now().date() - timedelta(days=350),
            next_verification_date=timezone.now().date() + timedelta(days=15),
            interval_value=12,
            arshin_verification_number="С-ВТ/01-10-2025/998877",
            verification_organization="Брянский ЦСМ",
            responsible_person=self.user,
        )

        # 3. Вольтметр (СИ, просрочен)
        self.name_volt = EquipmentName.objects.create(
            name="Вольтметр",
            category=EquipmentType.MEASURING,
        )
        self.model_volt = EquipmentTypeModel.objects.create(
            equipment_name=self.name_volt,
            name="В7-40",
            part_number="V7-40",
            default_interval_months=12,
        )
        self.eq_expired = MaintenanceEquipment.objects.create(
            name="Вольтметр В7-40",
            type_model=self.model_volt,
            part_number="V7-40",
            serial_number="VOLT-9002",
            marking_code="ИР-03-22",
            equipment_type=EquipmentType.MEASURING,
            production_place=self.mpd_penza,
            location="Офис ИАС",
            operational_status=EquipmentOperationalStatus.QUARANTINED,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=date(2024, 1, 1),
            next_verification_date=timezone.now().date() - timedelta(days=10),
            interval_value=12,
            arshin_verification_number="С-БЕ/01-01-2024/443322",
            verification_organization="ЦАС",
            responsible_person=self.user,
        )

        # 4. Винт для СЗТВ (Специнструмент, не подлежит поверке)
        self.eq_tool = MaintenanceEquipment.objects.create(
            name="Винт для СЗТВ",
            part_number="SZTV-01",
            serial_number="TOOL-001",
            marking_code="ИР-0-60-22",
            equipment_type=EquipmentType.SPECIAL_TOOL,
            production_place=self.mpd_penza,
            location="Склад ИАС",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
            responsible_person=self.user,
        )

        self.client = Client(HTTP_HOST="127.0.0.1")

    def test_export_service_creates_valid_workbook(self) -> None:
        """Проверяет генерацию официальной печатной ведомости Excel сервисным слоем."""
        qs = MaintenanceEquipment.objects.all()
        response = export_maintenance_equipment_to_excel(
            queryset=qs,
            filters_summary="Тестовая сводка",
            generated_by="Метрологов М.М.",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertIn("Metrological_Equipment_Barkol_", response["Content-Disposition"])

        # Читаем байты книги через openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        self.assertIn("Ведомость СИ и инструмента", wb.sheetnames)
        ws = wb["Ведомость СИ и инструмента"]

        # Проверяем параметры печати
        self.assertEqual(ws.page_setup.orientation, ws.ORIENTATION_LANDSCAPE)
        self.assertEqual(str(ws.page_setup.paperSize), str(ws.PAPERSIZE_A4))
        self.assertIn("7", ws.print_title_rows)
        self.assertTrue(ws.sheet_properties.pageSetUpPr.fitToPage)
        self.assertEqual(ws.page_setup.fitToWidth, 1)

        # Проверяем титульные строки
        self.assertIn("ООО АВИАКОМПАНИЯ «БАРКОЛ»", ws.cell(row=1, column=1).value)
        self.assertIn("ИНЖЕНЕРНО-АВИАЦИОННАЯ СЛУЖБА", ws.cell(row=2, column=1).value)
        self.assertIn("ВЕДОМОСТЬ УЧЕТА И МЕТРОЛОГИЧЕСКОГО СОСТОЯНИЯ", ws.cell(row=3, column=1).value)

        # Проверяем заголовки таблицы (Строка 7)
        self.assertEqual(ws.cell(row=7, column=1).value, "№ п/п")
        self.assertEqual(ws.cell(row=7, column=2).value, "Наименование оборудования / инструмента")
        self.assertEqual(ws.cell(row=7, column=8).value, "Диапазон измерений")
        self.assertEqual(ws.cell(row=7, column=9).value, "Класс точности")
        self.assertEqual(ws.cell(row=7, column=22).value, "Примечание")

        # Проверяем наличие строк данных (Строки 8-11: 4 прибора)
        self.assertEqual(ws.cell(row=8, column=1).value, 1)
        self.assertEqual(ws.cell(row=9, column=1).value, 2)
        self.assertEqual(ws.cell(row=10, column=1).value, 3)
        self.assertEqual(ws.cell(row=11, column=1).value, 4)

        # Проверяем значения свойств модели и выгрузки (Строка 8: Амперметр)
        self.assertEqual(self.eq_valid.measurement_range, "0 - 10А")
        self.assertEqual(self.eq_valid.accuracy_class, "1,5")
        self.assertEqual(ws.cell(row=8, column=8).value, "0 - 10А")
        self.assertEqual(ws.cell(row=8, column=9).value, "1,5")

        # Проверяем прибор без модели (Строка 11: Винт СЗТВ)
        self.assertEqual(self.eq_tool.measurement_range, "")
        self.assertEqual(self.eq_tool.accuracy_class, "")
        self.assertEqual(ws.cell(row=11, column=8).value, "—")
        self.assertEqual(ws.cell(row=11, column=9).value, "—")

        # Проверяем итоговую строку (Строка 13)
        summary_val = str(ws.cell(row=13, column=1).value)
        self.assertIn("ИТОГО ПО ВЕДОМОСТИ", summary_val)
        self.assertIn("Всего оборудования: 4 ед.", summary_val)

        wb.close()

    def test_export_view_authenticated(self) -> None:
        """Проверяет выгрузку печатной ведомости через веб-представление авторизованным пользователем."""
        self.client.force_login(self.user)
        export_url = reverse("hrdepartment_app:equipment_export_excel")
        response = self.client.get(export_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(len(response.content) > 1000)

    def test_export_view_with_filters(self) -> None:
        """Проверяет применение фильтров (МПД, статус, поиск) при выгрузке в Excel."""
        self.client.force_login(self.user)
        export_url = reverse("hrdepartment_app:equipment_export_excel")

        # Фильтр по МПД Пенза (должно быть 2 прибора: Вольтметр и Винт)
        response = self.client.get(export_url, {"mpd": str(self.mpd_penza.pk)})
        self.assertEqual(response.status_code, 200)

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws = wb.active
        # Мета-строка 5 должна содержать Пензу и 2 записи
        meta_val = str(ws.cell(row=5, column=1).value)
        self.assertIn("Участок ТО Пенза", meta_val)
        self.assertIn("2 ед.", meta_val)
        wb.close()

    def test_export_view_anonymous_redirect(self) -> None:
        """Проверяет защиту эндпоинта от неавторизованного доступа (редирект на страницу входа)."""
        export_url = reverse("hrdepartment_app:equipment_export_excel")
        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_filter_maintenance_equipment_queryset_logic(self) -> None:
        """Проверяет функцию фильтрации filter_maintenance_equipment_queryset."""
        class DummyRequest:
            def __init__(self, get_params: Dict[str, str]):
                self.GET = get_params

        # 1. Фильтр по поисковой строке
        req_q = DummyRequest({"q": "AMP-1001"})
        qs_q, params_q = filter_maintenance_equipment_queryset(req_q)
        self.assertEqual(qs_q.count(), 1)
        self.assertIn("AMP-1001", params_q["filter_summary"])

        # 2. Фильтр по категории
        req_cat = DummyRequest({"category": EquipmentType.SPECIAL_TOOL})
        qs_cat, _ = filter_maintenance_equipment_queryset(req_cat)
        self.assertEqual(qs_cat.count(), 1)
        self.assertEqual(qs_cat.first(), self.eq_tool)

        # 3. Фильтр по статусу поверки (истекающие)
        req_exp = DummyRequest({"metrology_status": "EXPIRING"})
        qs_exp, _ = filter_maintenance_equipment_queryset(req_exp)
        self.assertEqual(qs_exp.count(), 1)
        self.assertEqual(qs_exp.first(), self.eq_expiring)
