"""Unit-тесты аналитики начислений (КНД 1151162 XML + 1С OData read-only)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customers_app.models import (
    DataBaseUserProfile,
    PayrollFnsLine,
    PayrollODataDetail,
    PayrollReportBatch,
)
from customers_app.services_payroll_reports import (
    import_knd_1151162_xml,
    match_employee_for_report,
    sync_1c_odata_payroll_month,
)

SAMPLE_KND_XML = """<?xml version="1.0" encoding="windows-1251"?>
<Файл xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ИдФайл="NO_PERSSVFL_TEST_20261124_001" ВерсПрог="1С:ЗУП КОРП 3.1.39.53" ВерсФорм="5.01">
    <Документ КНД="1151162" ДатаДок="24.11.2026" НомКорр="0" Период="10" ОтчетГод="2026" КодНО="7728" ПоМесту="214">
        <СвНП Тлф="8-499-141-52-04">
            <НПЮЛ НаимОрг="ООО Авиакомпания БАРКОЛ" ИННЮЛ="7731246570" КПП="772801001"/>
        </СвНП>
        <ПерсСвФЛ ИННФЛ="298314511509" СНИЛС="146-552-817 58" СумВыпл="214420.99">
            <ФИО Фамилия="Абрам" Имя="Никола" Отчество="Феодорович"/>
        </ПерсСвФЛ>
        <ПерсСвФЛ ИННФЛ="772712349930" СНИЛС="147-381-644 38" СумВыпл="288027.32">
            <ФИО Фамилия="Яхан" Имя="Виталий" Отчество="Виторов"/>
        </ПерсСвФЛ>
    </Документ>
</Файл>
""".encode("windows-1251")


class PayrollReportsTestCase(TestCase):
    """Тестирование импорта КНД 1151162, OData read-only синхронизации и отчётов."""

    def setUp(self) -> None:
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="payroll_admin",
            password="Password123!",
            first_name="Админ",
            last_name="Зарплатный",
            is_superuser=True,
        )
        self.read_user = User.objects.create_user(
            username="payroll_reader",
            password="Password123!",
            first_name="Читатель",
            last_name="Зарплатный",
        )
        from customers_app.models import Groups
        read_group, _ = Groups.objects.get_or_create(name="Аналитика начислений (чтение)")
        self.read_user.groups.add(read_group)

        self.full_user = User.objects.create_user(
            username="payroll_editor",
            password="Password123!",
            first_name="Редактор",
            last_name="Зарплатный",
        )
        full_group, _ = Groups.objects.get_or_create(name="Аналитика начислений (полный доступ)")
        self.full_user.groups.add(full_group)
        self.regular_user = User.objects.create_user(
            username="payroll_user",
            password="Password123!",
            first_name="Обычный",
            last_name="Юзер",
        )
        # Эмулируем сотрудника, который уволился и принялся заново (две учётки на один СНИЛС и person_ref_key)
        p_old = DataBaseUserProfile.objects.create(snils="146-552-817 58", inn="298314511509")
        self.emp_old = User.objects.create_user(
            username="abram_old",
            password="Password123!",
            first_name="Никола",
            last_name="Абрам",
            surname="Феодорович",
            person_ref_key="person-guid-abram",
            ref_key="emp-guid-old",
            user_profile=p_old,
            is_active=False,
        )
        p_new = DataBaseUserProfile.objects.create(snils="146-552-817 58", inn="298314511509")
        self.emp_new = User.objects.create_user(
            username="abram_new",
            password="Password123!",
            first_name="Никола",
            last_name="Абрам",
            surname="Феодорович",
            person_ref_key="person-guid-abram",
            ref_key="emp-guid-new",
            user_profile=p_new,
            is_active=True,
        )

    def test_match_prefers_active_user(self) -> None:
        """При дублях (уволен и принят заново) выбирается активная учётка и сохраняется person_ref_key."""
        emp, pkey = match_employee_for_report(snils="14655281758")
        self.assertEqual(emp, self.emp_new)
        self.assertEqual(pkey, "person-guid-abram")

    def test_import_knd_1151162_xml_and_duplicate_guard(self) -> None:
        """Проверяет импорт XML КНД 1151162 в windows-1251 и защиту от повторной загрузки."""
        batch, total, matched = import_knd_1151162_xml(SAMPLE_KND_XML, filename="test.xml", user=self.staff_user)
        self.assertEqual(batch.year, 2026)
        self.assertEqual(batch.month, 10)
        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(PayrollFnsLine.objects.filter(batch=batch).count(), 2)

        with self.assertRaises(ValueError):
            import_knd_1151162_xml(SAMPLE_KND_XML, filename="test.xml", user=self.staff_user)

    @patch("customers_app.services_payroll_reports.requests.get")
    def test_sync_1c_odata_payroll_month_read_only(self, mock_get: MagicMock) -> None:
        """Проверяет read-only загрузку и агрегацию начислений/удержаний из 1С OData."""
        def fake_get(url, auth=None, params=None, timeout=30):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "ChartOfCalculationTypes_Начисления" in url:
                resp.json.return_value = {
                    "value": [
                        {"Ref_Key": "calc-oklad", "Description": "Оплата по окладу"},
                        {"Ref_Key": "calc-meal", "Description": "Компенсация питания летных экипажей"},
                    ]
                }
            elif "ChartOfCalculationTypes_Удержания" in url:
                resp.json.return_value = {"value": [{"Ref_Key": "calc-uderzh", "Description": "Удержание по ИЛ"}]}
            else:
                resp.json.return_value = {
                    "value": [
                        {
                            "Active": True,
                            "ФизическоеЛицо_Key": "person-guid-abram",
                            "Сотрудник_Key": "emp-guid-new",
                            "Подразделение_Key": "",
                            "НачислениеУдержание": "calc-oklad",
                            "НачислениеУдержание_Type": "StandardODATA.ChartOfCalculationTypes_Начисления",
                            "Сумма": 150000,
                            "ГруппаНачисленияУдержанияВыплаты": "Начислено",
                            "Сторно": False,
                        },
                        {
                            "Active": True,
                            "ФизическоеЛицо_Key": "person-guid-abram",
                            "Сотрудник_Key": "emp-guid-new",
                            "Подразделение_Key": "",
                            "НачислениеУдержание": "calc-meal",
                            "НачислениеУдержание_Type": "StandardODATA.ChartOfCalculationTypes_Начисления",
                            "Сумма": 12000,
                            "ГруппаНачисленияУдержанияВыплаты": "Начислено",
                            "Сторно": False,
                        },
                        {
                            "Active": True,
                            "ФизическоеЛицо_Key": "person-guid-abram",
                            "Сотрудник_Key": "emp-guid-new",
                            "Подразделение_Key": "",
                            "НачислениеУдержание": "calc-uderzh",
                            "НачислениеУдержание_Type": "StandardODATA.ChartOfCalculationTypes_Удержания",
                            "Сумма": 19500,
                            "ГруппаНачисленияУдержанияВыплаты": "Удержано",
                            "Сторно": False,
                        },
                    ]
                }
            return resp

        mock_get.side_effect = fake_get
        res = sync_1c_odata_payroll_month(2026, 10)
        self.assertEqual(res["raw_count"], 3)
        self.assertEqual(res["saved_count"], 3)
        self.assertEqual(PayrollODataDetail.objects.filter(year=2026, month=10).count(), 3)
        oklad = PayrollODataDetail.objects.get(calculation_type_key="calc-oklad")
        self.assertEqual(oklad.calculation_type_name, "Оплата по окладу")
        self.assertEqual(oklad.amount, Decimal("150000.00"))

        # Проверяем, что компенсация питания выделяется отдельно и не ломает базу ЗП
        from customers_app.views_payroll_reports import _build_employee_summary_rows
        rows = _build_employee_summary_rows(year=2026, month=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accrued_total"], Decimal("150000.00"))
        self.assertEqual(rows[0]["compensation_total"], Decimal("12000.00"))

    def test_views_access_dashboard_card_and_export(self) -> None:
        """Проверяет права доступа, дашборд, карточку сотрудника и экспорт в Excel."""
        import_knd_1151162_xml(SAMPLE_KND_XML, filename="test.xml", user=self.staff_user)

        self.client.force_login(self.regular_user)
        resp_forbidden = self.client.get(reverse("customers_app:payroll_reports_dashboard"))
        self.assertEqual(resp_forbidden.status_code, 403)

        self.client.force_login(self.staff_user)
        resp_dash = self.client.get(reverse("customers_app:payroll_reports_dashboard") + "?year=2026&month=10")
        self.assertEqual(resp_dash.status_code, 200)
        self.assertContains(resp_dash, "Абрам")

        resp_card = self.client.get(
            reverse("customers_app:payroll_employee_card", kwargs={"person_key": "person-guid-abram"}) + "?year=2026"
        )
        self.assertEqual(resp_card.status_code, 200)
        self.assertContains(resp_card, "Абрам")
        self.assertContains(resp_card, "Октябрь")
        self.assertContains(resp_card, ",99")

        resp_xlsx = self.client.get(reverse("customers_app:payroll_export_excel") + "?year=2026&month=10")
        self.assertEqual(resp_xlsx.status_code, 200)
        self.assertIn("spreadsheetml", resp_xlsx["Content-Type"])

        # Пользователь с группой «чтение» видит отчёты, но не видит вкладку импорта и не может загружать/удалять
        self.client.force_login(self.read_user)
        resp_read_dash = self.client.get(reverse("customers_app:payroll_reports_dashboard") + "?year=2026&month=10")
        self.assertEqual(resp_read_dash.status_code, 200)
        self.assertContains(resp_read_dash, "Средняя зарплата (КНД 1151162)")
        self.assertNotContains(resp_read_dash, "Импорт данных (XML / 1С)")
        self.assertNotContains(resp_read_dash, "Загрузить XML")
        resp_read_upload = self.client.post(reverse("customers_app:payroll_upload_xml"))
        self.assertEqual(resp_read_upload.status_code, 403)
        resp_read_sync = self.client.post(reverse("customers_app:payroll_sync_odata"))
        self.assertEqual(resp_read_sync.status_code, 403)

        # Пользователь с группой «полный доступ» видит вкладку импорта и формы управления
        self.client.force_login(self.full_user)
        resp_full_dash = self.client.get(reverse("customers_app:payroll_reports_dashboard") + "?year=2026&month=10")
        self.assertEqual(resp_full_dash.status_code, 200)
        self.assertContains(resp_full_dash, "Импорт данных (XML / 1С)")
        self.assertContains(resp_full_dash, "Загрузить XML")

    def test_staff_categories_override_and_reports(self) -> None:
        """Проверяет справочник категорий персонала, приоритет индивидуального выбора и свод."""
        from customers_app.models import DataBaseUserWorkProfile, Job, StaffCategory

        cat_chl, _ = StaffCategory.objects.get_or_create(short_name="ЧЛЭ", defaults={"name": "Члены лётных экипажей"})
        cat_aup, _ = StaffCategory.objects.get_or_create(short_name="АУП", defaults={"name": "Административно-управленческий персонал"})

        job = Job.objects.create(name="Командир ВС", staff_category=cat_chl)
        wp = DataBaseUserWorkProfile.objects.create(job=job)
        self.emp_new.user_work_profile = wp
        self.emp_new.save()

        # По умолчанию категория берётся от должности
        self.assertEqual(self.emp_new.get_staff_category(), cat_chl)

        # Индивидуальное переопределение перекрывает должность
        wp.staff_category = cat_aup
        wp.save()
        self.emp_new.refresh_from_db()
        self.assertEqual(self.emp_new.get_staff_category(), cat_aup)

        # Проверка страницы управления и фильтрации в отчёте
        import_knd_1151162_xml(SAMPLE_KND_XML, filename="test.xml", user=self.staff_user)
        self.client.force_login(self.full_user)
        resp_manage = self.client.get(reverse("customers_app:staff_categories_manage"))
        self.assertEqual(resp_manage.status_code, 200)
        self.assertContains(resp_manage, "АУП")

        resp_filtered = self.client.get(
            reverse("customers_app:payroll_reports_dashboard") + f"?year=2026&month=10&staff_category={cat_aup.pk}"
        )
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertContains(resp_filtered, "Абрам")

    def test_avg_salary_report_with_dismissed_employee(self) -> None:
        """Проверяет расчёт средней ЗП по месяцам, кварталам, полугодиям и году, включая уволенных."""
        from customers_app.models import DataBaseUserWorkProfile, Job, StaffCategory
        from customers_app.views_payroll_reports import _build_fns_avg_salary_report

        cat_itp, _ = StaffCategory.objects.get_or_create(short_name="ИТП", defaults={"name": "Инженерно-технический персонал"})
        job = Job.objects.create(name="Авиатехник", staff_category=cat_itp)
        wp = DataBaseUserWorkProfile.objects.create(job=job)
        self.emp_old.user_work_profile = wp
        self.emp_old.save()

        b_jan = PayrollReportBatch.objects.create(file_id="TEST_JAN", year=2025, month=1)
        b_feb = PayrollReportBatch.objects.create(file_id="TEST_FEB", year=2025, month=2)
        PayrollFnsLine.objects.create(
            batch=b_jan, employee=self.emp_old, person_ref_key="p-dismissed",
            snils="999-000-111 22", full_name="Уволенный Сотрудник", total_amount=Decimal("100000.00"),
        )
        PayrollFnsLine.objects.create(
            batch=b_feb, employee=self.emp_old, person_ref_key="p-dismissed",
            snils="999-000-111 22", full_name="Уволенный Сотрудник", total_amount=Decimal("200000.00"),
        )

        report = _build_fns_avg_salary_report(year=2025)
        self.assertEqual(len(report["groups"]), 1)
        grp = report["groups"][0]
        self.assertEqual(grp["name"], "ИТП")
        row = grp["rows"][0]
        self.assertFalse(row["is_active"])
        self.assertEqual(row["q1"], Decimal("150000.00"))
        self.assertIsNone(row["q2"])
        self.assertEqual(row["h1"], Decimal("150000.00"))
        self.assertEqual(row["year_avg"], Decimal("150000.00"))

    def test_shmakov_report_both_years_and_gph(self) -> None:
        """Проверяет отчёт Шмакова Д.А.: соотношение чел./% за оба года и автоотнесение ГПХ к Прочему персоналу."""
        from django.contrib.auth import get_user_model
        from customers_app.models import DataBaseUserWorkProfile, Job, StaffCategory
        from customers_app.views_payroll_reports import _build_shmakov_report

        User = get_user_model()
        cat_aup, _ = StaffCategory.objects.get_or_create(short_name="АУП", defaults={"name": "АУП"})
        job_dir = Job.objects.create(name="Директор", staff_category=cat_aup)
        wp = DataBaseUserWorkProfile.objects.create(job=job_dir)
        self.emp_new.user_work_profile = wp
        self.emp_new.save()

        gph_user = User.objects.create_user(
            username="gph_worker", password="Password123!",
            first_name="Подрядчик", last_name="ГПХ", type_users="freelancer",
        )

        # 2025 (предыдущий) и 2026 (текущий), а 2024 не должен попасть
        b_2024 = PayrollReportBatch.objects.create(file_id="SHM_2024", year=2024, month=1)
        PayrollFnsLine.objects.create(batch=b_2024, employee=self.emp_new, person_ref_key="p-1", total_amount=Decimal("99999.00"))

        b_2025 = PayrollReportBatch.objects.create(file_id="SHM_2025", year=2025, month=1)
        PayrollFnsLine.objects.create(batch=b_2025, employee=self.emp_new, person_ref_key="p-1", total_amount=Decimal("100000.00"))
        PayrollFnsLine.objects.create(batch=b_2025, employee=gph_user, person_ref_key="p-gph", total_amount=Decimal("50000.00"))

        b_2026 = PayrollReportBatch.objects.create(file_id="SHM_2026", year=2026, month=1)
        PayrollFnsLine.objects.create(batch=b_2026, employee=self.emp_new, person_ref_key="p-1", total_amount=Decimal("120000.00"))

        rep = _build_shmakov_report(year=2026)
        self.assertEqual(rep["prev_year"], 2025)
        self.assertEqual(rep["curr_year"], 2026)
        self.assertEqual(len(rep["months_rows"]), 1)

        jan = rep["months_rows"][0]
        self.assertEqual(jan["prev_total_count"], 2)
        self.assertEqual(jan["curr_total_count"], 1)

        aup_cell = next(g for g in jan["groups"] if g["name"] == "АУП")
        other_cell = next(g for g in jan["groups"] if g["name"] == "Прочий персонал")
        self.assertEqual(aup_cell["prev_count"], 1)
        self.assertEqual(aup_cell["prev_share"], Decimal("50.0"))
        self.assertEqual(aup_cell["curr_count"], 1)
        self.assertEqual(aup_cell["curr_share"], Decimal("100.0"))
        self.assertEqual(other_cell["prev_count"], 1)
        self.assertEqual(other_cell["prev_share"], Decimal("50.0"))
        self.assertEqual(other_cell["prev_amount"], Decimal("50000.00"))

    def test_bulk_upload_xml_files(self) -> None:
        """Проверяет групповую загрузку нескольких XML-файлов КНД 1151162."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        xml_2 = SAMPLE_KND_XML.decode("windows-1251").replace(
            "NO_PERSSVFL_TEST_20261124_001", "NO_PERSSVFL_TEST_20261124_002"
        ).replace('Период="10"', 'Период="11"').encode("windows-1251")

        f1 = SimpleUploadedFile("oct.xml", SAMPLE_KND_XML, content_type="text/xml")
        f2 = SimpleUploadedFile("nov.xml", xml_2, content_type="text/xml")

        self.client.force_login(self.full_user)
        resp = self.client.post(
            reverse("customers_app:payroll_upload_xml"),
            {"xml_file": [f1, f2]},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PayrollReportBatch.objects.count(), 2)
