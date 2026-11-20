# -*- coding: utf-8 -*-
"""Модульные тесты кадровых документов при приёме на работу, подписантов и доверенностей."""

import io
import os
import tempfile
import zipfile
from datetime import date

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from docx import Document

from administration_app.models import TemplateDocument
from customers_app.customers_util import prepare_consent_context
from customers_app.forms import BiometricConsentForm, HirePackageForm
from customers_app.models import BiometricConsent, ConsentType, DataBaseUser, DocumentSigner
from customers_app.services_onboarding_docs import generate_hire_package_zip
from hrdepartment_app.models import PowerOfAttorney


def _make_sample_docx_bytes(text: str) -> bytes:
    """Создаёт минимальный валидный .docx-файл в памяти с заданным текстом."""
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class HireDocumentsTestCase(TestCase):
    """Тесты подписантов, доверенностей, контекста шаблонов и пакетной выгрузки ZIP."""

    def setUp(self) -> None:
        """Создаёт сотрудника, кадровика, подписантов, доверенности и типы документов."""
        self.hr_user = DataBaseUser.objects.create_user(
            username="hr_manager",
            password="StrongPassword123!",
            first_name="Анна",
            last_name="Кадрова",
            email="hr@barkol.ru",
            is_superuser=True,
        )
        self.employee = DataBaseUser.objects.create_user(
            username="new_emp",
            password="StrongPassword123!",
            first_name="Виталий",
            last_name="Кузнецов",
            surname="Александрович",
            email="kuznetsov@barkol.ru",
        )
        self.deputy_user = DataBaseUser.objects.create_user(
            username="shmakov_da",
            password="StrongPassword123!",
            first_name="Дмитрий",
            last_name="Шмаков",
            surname="Александрович",
            email="shmakov@barkol.ru",
        )

        self.director_signer = DocumentSigner.objects.create(
            full_name_genitive="Бархотова Виктора Сергеевича",
            short_name="В.С. Бархотов",
            position_genitive="генерального директора",
            acts_by_charter=True,
            is_default=True,
            is_active=True,
        )
        self.deputy_signer = DocumentSigner.objects.create(
            employee=self.deputy_user,
            full_name_genitive="Шмакова Дмитрия Александровича",
            short_name="Д.А. Шмаков",
            position_genitive="первого заместителя генерального директора-исполнительного директора",
            acts_by_charter=False,
            is_default=False,
            is_active=True,
        )

        self.poa1 = PowerOfAttorney.objects.create(
            number="77 АЕ 3626402",
            issue_date=date(2026, 6, 30),
            expiry_date=date(2027, 6, 30),
            grantee_name_user=self.deputy_user,
        )
        self.poa2 = PowerOfAttorney.objects.create(
            number="77 АЕ 3626403",
            issue_date=date(2026, 6, 30),
            expiry_date=date(2027, 6, 30),
            grantee_name_user=self.deputy_user,
        )
        self.poa3 = PowerOfAttorney.objects.create(
            number="77 АЕ 9999999",
            issue_date=date(2026, 8, 15),
            expiry_date=date(2027, 8, 15),
            grantee_name_user=self.deputy_user,
        )

        self.type_dmo = ConsentType.objects.create(
            name="Договор о полной индивидуальной материальной ответственности",
            code="material_liability",
            number_prefix="ДМО",
            requires_signer=True,
            is_required_on_hire=True,
            is_active=True,
        )
        self.type_vu = ConsentType.objects.create(
            name="Обязанности граждан по воинскому учёту",
            code="military_duty",
            number_prefix="ВУ",
            requires_signer=False,
            is_required_on_hire=True,
            is_active=True,
        )

        self.client = Client()
        self.client.force_login(self.hr_user)

    def test_format_acting_basis_charter_and_poas(self) -> None:
        """Проверяет форматирование основания: Устав, одна, несколько одной даты и разных дат."""
        self.assertEqual(self.director_signer.format_acting_basis([]), "Устава")
        self.assertEqual(
            self.deputy_signer.format_acting_basis([self.poa1]),
            "Доверенности 77 АЕ 3626402 от 30.06.2026г.",
        )
        self.assertEqual(
            self.deputy_signer.format_acting_basis([self.poa1, self.poa2]),
            "Доверенности 77 АЕ 3626402, 77 АЕ 3626403 от 30.06.2026г.",
        )
        self.assertEqual(
            self.deputy_signer.format_acting_basis([self.poa1, self.poa3]),
            "Доверенностей 77 АЕ 3626402 от 30.06.2026г., 77 АЕ 9999999 от 15.08.2026г.",
        )

    def test_single_form_requires_signer_and_poa_when_not_charter(self) -> None:
        """Форма блокирует сохранение договора без подписанта или заместителя без доверенности."""
        # 1. Без подписанта для ДМО -> ошибка
        form_no_signer = BiometricConsentForm(
            data={
                "employee": self.employee.pk,
                "consent_type": self.type_dmo.pk,
                "consent_date": "2026-11-20",
                "is_active": True,
            }
        )
        self.assertFalse(form_no_signer.is_valid())
        self.assertIn("signer", form_no_signer.errors)

        # 2. Заместитель без доверенности -> ошибка
        form_no_poa = BiometricConsentForm(
            data={
                "employee": self.employee.pk,
                "consent_type": self.type_dmo.pk,
                "consent_date": "2026-11-20",
                "signer": self.deputy_signer.pk,
                "is_active": True,
            }
        )
        self.assertFalse(form_no_poa.is_valid())
        self.assertIn("powers_of_attorney", form_no_poa.errors)

        # 3. Заместитель с двумя доверенностями -> валидно
        form_ok = BiometricConsentForm(
            data={
                "employee": self.employee.pk,
                "consent_type": self.type_dmo.pk,
                "consent_date": "2026-11-20",
                "signer": self.deputy_signer.pk,
                "powers_of_attorney": [self.poa1.pk, self.poa2.pk],
                "is_active": True,
            }
        )
        self.assertTrue(form_ok.is_valid(), form_ok.errors)

        # 4. Директор по Уставу без доверенности -> валидно
        form_director = BiometricConsentForm(
            data={
                "employee": self.employee.pk,
                "consent_type": self.type_dmo.pk,
                "consent_date": "2026-11-20",
                "signer": self.director_signer.pk,
                "is_active": True,
            }
        )
        self.assertTrue(form_director.is_valid(), form_director.errors)

    def test_api_signer_poas_endpoint(self) -> None:
        """API возвращает флаг Устава и список доверенностей поверенного из PowerOfAttorney."""
        url_dir = reverse("customers_app:api_signer_poas", kwargs={"signer_id": self.director_signer.pk})
        resp_dir = self.client.get(url_dir)
        self.assertEqual(resp_dir.status_code, 200)
        self.assertTrue(resp_dir.json()["acts_by_charter"])

        url_dep = reverse("customers_app:api_signer_poas", kwargs={"signer_id": self.deputy_signer.pk})
        resp_dep = self.client.get(url_dep)
        self.assertEqual(resp_dep.status_code, 200)
        data_dep = resp_dep.json()
        self.assertFalse(data_dep["acts_by_charter"])
        poa_numbers = [p["number"] for p in data_dep["poas"]]
        self.assertIn("77 АЕ 3626402", poa_numbers)
        self.assertIn("77 АЕ 3626403", poa_numbers)

    def test_hire_package_zip_generation_with_template(self) -> None:
        """Пакетная генерация создаёт записи в БД и рендерит .docx с подстановкой подписанта и доверенностей."""
        docx_bytes = _make_sample_docx_bytes(
            "В лице {{подписант_в_лице}} и {{фио}} ({{фио_кратко}}), № {{номер}} от {{дата}}г."
        )
        tpl = TemplateDocument.objects.create(
            name="Тестовый шаблон ДМО",
            unique_code="test_dmo_tpl",
            template_type="word",
            template_file=SimpleUploadedFile(
                "test_dmo.docx",
                docx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_active=True,
        )
        self.type_dmo.template = tpl
        self.type_dmo.save()

        zip_buf, created, skipped = generate_hire_package_zip(
            employee=self.employee,
            consent_types=[self.type_dmo, self.type_vu],
            consent_date=date(2026, 11, 20),
            signer=self.deputy_signer,
            powers_of_attorney=[self.poa1, self.poa2],
            created_by=self.hr_user,
            employment_contract_number="74/26тд",
            employment_contract_date=date(2026, 11, 20),
        )

        self.assertEqual(len(created), 2)
        self.assertTrue(created[0].consent_number.startswith("ДМО-20261120-"))
        self.assertTrue(created[1].consent_number.startswith("ВУ-20261120-"))
        self.assertEqual(created[0].signer, self.deputy_signer)
        self.assertIsNone(created[1].signer)
        self.assertEqual(skipped, [self.type_vu.name])

        with zipfile.ZipFile(zip_buf, "r") as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 1)
            rendered_doc = Document(io.BytesIO(zf.read(names[0])))
            full_text = "\n".join(p.text for p in rendered_doc.paragraphs)
            self.assertIn("Шмакова Дмитрия Александровича", full_text)
            self.assertIn("Доверенности 77 АЕ 3626402, 77 АЕ 3626403 от 30.06.2026г.", full_text)
            self.assertIn("Кузнецов Виталий Александрович", full_text)
            self.assertIn("74/26тд", full_text)

        # Чистим тестовый файл шаблона
        if tpl.template_file and os.path.exists(tpl.template_file.path):
            os.remove(tpl.template_file.path)
