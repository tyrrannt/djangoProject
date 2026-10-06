"""Модульные и интеграционные тесты сервиса и веб-интерфейса импорта оборудования из Excel (ФАП-145).

Тестирует:
1. Сервис `EquipmentExcelImportService`:
   - Парсинг дат и строковых значений;
   - Автоматическую классификацию категорий оборудования (Уровень 1);
   - Нормализацию моделей и типов (Уровень 2);
   - Выделение серийных номеров и кодов маркировки (Уровень 3);
   - Фиксацию метрологических поверок (EquipmentVerificationRecord);
   - Режим предварительного прогона (dry_run).
2. Management-команду `import_equipment_excel`.
3. Контроллер веб-интерфейса `EquipmentImportExcelView` и проверку прав доступа.
"""

import io
import datetime
from decimal import Decimal
import openpyxl

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from customers_app.models import DataBaseUser
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentTypeModel,
    MaintenanceEquipment,
    EquipmentOperationalStatus,
    EquipmentType,
    EquipmentVerificationType,
    EquipmentVerificationRecord,
    PlaceProductionActivity,
)
from hrdepartment_app.services.equipment_import import EquipmentExcelImportService


def create_test_excel_bytes() -> bytes:
    """Генерирует тестовую книгу Excel в памяти со структурой метрологического графика."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Все СИ и Инструмент"

    headers = [
        "N", "Наименование СИ", "Тип СИ", "Заводской номер", "Класс точности",
        "Номер в гос. Реестре", "Номер свидетельства", "Предел измерения",
        "Место установки", "Период поверки", "Последней поверки", "Последующей поверки",
        "Осталось дней", "Состояние", "Дата консервации", "Место проведения проверки",
        "Куда отправили", "Примечание",
    ]
    ws.append(headers)

    # Строка 1: Амперметр с поверкой
    ws.append([
        1, "Амперметр", "М42300", "210049059", "1,5",
        "68770-17", "С-БНГ/07-07-2021/76655622", "0 - 10А",
        "Лаборатория/ Стенд преоб", 60, datetime.datetime(2021, 7, 7), datetime.datetime(2026, 7, 7),
        0, "Исправен", None, "ЦАС", "Участок ТО \"Мячково\"", "Тестовая запись 1"
    ])

    # Строка 2: Винт без поверки с составным номером
    ws.append([
        2, "Винт для СЗТВ", "-", "847120    ИР-НО-50-17", None,
        None, None, None,
        "Офис ИАС", None, None, None,
        None, "Исправен", None, None, "МПД \"Пенза\"", "Тестовая запись 2"
    ])

    # Строка 3: Неисправный манометр
    ws.append([
        3, "Манометр", "МТИ", "998877", "0,6",
        "12345-10", "С-ТЕСТ/2023", "0 - 16 кгс/см2",
        "Участок ТО", 12, datetime.datetime(2023, 5, 10), datetime.datetime(2024, 5, 10),
        -100, "Неисправен", None, "Ростест", "Аэропорт Волгоград", "Брак"
    ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


class EquipmentExcelImportServiceTests(TestCase):
    """Тестирование бизнес-логики и отказоустойчивости сервиса EquipmentExcelImportService."""

    def setUp(self):
        self.service = EquipmentExcelImportService()
        self.excel_bytes = create_test_excel_bytes()

    def test_determine_category(self):
        """Проверяет классификацию наименований по ключевым словам."""
        self.assertEqual(
            self.service.detect_category("Манометр технический"),
            EquipmentType.MEASURING,
        )
        self.assertEqual(
            self.service.detect_category("Пульт проверки КПА-14"),
            EquipmentType.CONTROL_TEST,
        )
        self.assertEqual(
            self.service.detect_category("Съемник подшипников"),
            EquipmentType.SPECIAL_TOOL,
        )
        self.assertEqual(
            self.service.detect_category("Гидроподъемник самолетный"),
            EquipmentType.GROUND_EQUIPMENT,
        )

    def test_parse_date_and_int(self):
        """Проверяет корректность разбора дат и целых чисел."""
        self.assertIsNone(self.service.parse_date(None))
        self.assertIsNone(self.service.parse_date("-"))
        self.assertIsNone(self.service.parse_date("Некорректная дата"))

        d1 = self.service.parse_date("21.02.2025")
        self.assertEqual(d1, datetime.date(2025, 2, 21))

        d2 = self.service.parse_date(datetime.datetime(2024, 8, 15, 12, 0))
        self.assertEqual(d2, datetime.date(2024, 8, 15))

        self.assertEqual(self.service.parse_interval(60), 60)
        self.assertEqual(self.service.parse_interval("12 мес."), 12)
        self.assertIsNone(self.service.parse_interval(None))
        self.assertIsNone(self.service.parse_interval("-"))

    def test_dry_run_import(self):
        """Проверяет, что режим dry-run не сохраняет данные в БД."""
        report = self.service.import_from_excel(
            file_path_or_obj=self.excel_bytes,
            sheet_name="Все СИ и Инструмент",
            dry_run=True,
        )

        self.assertTrue(report.is_success)
        self.assertTrue(report.dry_run)
        self.assertEqual(report.total_rows_read, 3)
        self.assertEqual(report.created_equipment_count, 3)
        self.assertEqual(report.errors, [])

        # Проверяем, что в базе данных ничего не создано
        self.assertEqual(MaintenanceEquipment.objects.count(), 0)
        self.assertEqual(EquipmentName.objects.count(), 0)
        self.assertEqual(EquipmentTypeModel.objects.count(), 0)
        self.assertEqual(EquipmentVerificationRecord.objects.count(), 0)

    def test_live_import_and_duplicate_handling(self):
        """Проверяет боевую запись в БД и корректное обновление без дубликатов."""
        # 1. Первый боевой прогон
        report1 = self.service.import_from_excel(
            file_path_or_obj=self.excel_bytes,
            sheet_name="Все СИ и Инструмент",
            dry_run=False,
        )

        self.assertTrue(report1.is_success)
        self.assertFalse(report1.dry_run)
        self.assertEqual(report1.created_equipment_count, 3)
        self.assertEqual(report1.verifications_recorded, 2)  # Амперметр и Манометр

        self.assertEqual(MaintenanceEquipment.objects.count(), 3)
        self.assertEqual(EquipmentName.objects.count(), 3)
        self.assertEqual(EquipmentTypeModel.objects.count(), 3)
        self.assertEqual(EquipmentVerificationRecord.objects.count(), 2)

        # Проверяем атрибуты амперметра
        amp = MaintenanceEquipment.objects.get(serial_number="210049059")
        self.assertEqual(amp.operational_status, EquipmentOperationalStatus.SERVICEABLE)
        self.assertEqual(amp.type_model.name, "М42300")
        self.assertEqual(amp.type_model.accuracy_class, "1,5")
        self.assertEqual(amp.type_model.arshin_type_number, "68770-17")
        self.assertEqual(amp.arshin_verification_number, "С-БНГ/07-07-2021/76655622")
        self.assertEqual(amp.verification_organization, "ЦАС")
        self.assertEqual(amp.interval_value, 60)

        # Проверяем атрибуты составного номера винта
        vint = MaintenanceEquipment.objects.get(serial_number="847120")
        self.assertEqual(vint.marking_code, "ИР-НО-50-17")

        # Проверяем манометр (просрочен -> п. 25 ФАП-145 автоматический карантин)
        mano = MaintenanceEquipment.objects.get(serial_number="998877")
        self.assertEqual(mano.operational_status, EquipmentOperationalStatus.QUARANTINED)

        # 2. Второй прогон тем же файлом (проверка обновления существующих)
        service2 = EquipmentExcelImportService()
        report2 = service2.import_from_excel(
            file_path_or_obj=self.excel_bytes,
            sheet_name="Все СИ и Инструмент",
            dry_run=False,
        )

        self.assertTrue(report2.is_success)
        self.assertEqual(report2.created_equipment_count, 0)
        self.assertEqual(report2.updated_equipment_count, 3)
        self.assertEqual(MaintenanceEquipment.objects.count(), 3)


class EquipmentImportCommandTests(TestCase):
    """Тестирование вызова django management-команды import_equipment_excel."""

    def test_command_dry_run_with_custom_file(self):
        """Проверяет запуск команды через call_command с тестовым файлом."""
        import tempfile
        excel_bytes = create_test_excel_bytes()
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=True) as tmp:
            tmp.write(excel_bytes)
            tmp.flush()

            out = io.StringIO()
            call_command("import_equipment_excel", file=tmp.name, dry_run=True, stdout=out)
            output = out.getvalue()

            self.assertIn("СТАРТ ИМПОРТА ОБОРУДОВАНИЯ", output)
            self.assertIn("РЕЖИМ СИМУЛЯЦИИ", output)
            self.assertIn("Всего строк прочитано:           3", output)


class EquipmentImportExcelViewTests(TestCase):
    """Тестирование прав доступа и веб-интерфейса импорта оборудования."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("hrdepartment_app:equipment_import_excel")

        self.superuser = DataBaseUser.objects.create_superuser(
            username="admin_import",
            password="adminpassword",
            email="admin_import@barkol.ru",
            first_name="Администратор",
            last_name="Главный",
        )

        self.plain_engineer = DataBaseUser.objects.create_user(
            username="engineer_test",
            password="userpassword",
            first_name="Иван",
            last_name="Инженеров",
            is_staff=False,
        )

        self.staff_no_perm = DataBaseUser.objects.create_user(
            username="staff_no_perm",
            password="userpassword",
            first_name="Петр",
            last_name="Сотрудников",
            is_staff=True,
        )

        self.authorized_user = DataBaseUser.objects.create_user(
            username="editor_import",
            password="userpassword",
            first_name="Алексей",
            last_name="Метрологов",
            is_staff=False,
        )
        ct = ContentType.objects.get_for_model(MaintenanceEquipment)
        perm = Permission.objects.get(content_type=ct, codename="add_maintenanceequipment")
        self.authorized_user.user_permissions.add(perm)

        self.excel_bytes = create_test_excel_bytes()

    def test_anonymous_access_redirects_to_login(self):
        """Анонимный доступ перенаправляет на страницу авторизации."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_forbidden_for_user_without_permission(self):
        """Инженер без явного права add_maintenanceequipment получает 403 Forbidden."""
        self.client.force_login(self.plain_engineer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.staff_no_perm)
        response2 = self.client.get(self.url)
        self.assertEqual(response2.status_code, 403)

    def test_get_allowed_for_authorized_user_and_superuser(self):
        """Пользователь с правом add_maintenanceequipment и суперпользователь получают форму (200 OK)."""
        self.client.force_login(self.authorized_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пакетный импорт метрологического графика из Excel")

        self.client.force_login(self.superuser)
        response_super = self.client.get(self.url)
        self.assertEqual(response_super.status_code, 200)

    def test_post_upload_dry_run_and_live(self):
        """POST-запрос с файлом Excel отображает сводный отчет."""
        self.client.force_login(self.authorized_user)

        # 1. Загрузка в режиме Dry-Run
        uploaded = SimpleUploadedFile(
            "metrology_test.xlsx",
            self.excel_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response_dry = self.client.post(
            self.url,
            {
                "excel_file": uploaded,
                "sheet_name": "Все СИ и Инструмент",
                "dry_run": "on",
            },
        )
        self.assertEqual(response_dry.status_code, 200)
        self.assertContains(response_dry, "Тестовый прогон (Dry-Run)")
        self.assertEqual(MaintenanceEquipment.objects.count(), 0)

        # 2. Загрузка в боевом режиме
        uploaded_live = SimpleUploadedFile(
            "metrology_test.xlsx",
            self.excel_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response_live = self.client.post(
            self.url,
            {
                "excel_file": uploaded_live,
                "sheet_name": "Все СИ и Инструмент",
            },
        )
        self.assertEqual(response_live.status_code, 200)
        self.assertContains(response_live, "Боевой режим")
        self.assertEqual(MaintenanceEquipment.objects.count(), 3)
