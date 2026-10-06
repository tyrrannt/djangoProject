"""Модульные и интеграционные тесты метрологического учета оборудования и нарядов ТО ВС (ФАП-145).

Данный модуль изолирован от общего монолита тестов приложения hrdepartment_app
для быстрого точечного запуска:
    python3 manage.py test hrdepartment_app.tests_metrology --keepdb

Покрывает:
1. Модели оборудования MaintenanceEquipment, EquipmentVerificationRecord, OutfitCardEquipmentUsage (пп. 19-25 ФАП-145, 102-ФЗ);
2. Транзакционный сервисный слой OutfitCardReleaseService (валидация перед CRS, SHA-256 хэш п. 40);
3. Форму карты-наряда OutfitCardForm с полем used_equipment и валидацией типов ВС;
4. Разграничение прав доступа к вводу и редактированию на портале (права моделей и is_superuser, а не staff).
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts_app.models import Estate, TypeProperty
from customers_app.models import DataBaseUser
from hrdepartment_app.forms import (
    EquipmentVerificationRecordForm,
    MaintenanceEquipmentForm,
    OutfitCardForm,
)
from hrdepartment_app.models import (
    EquipmentOperationalStatus,
    EquipmentType,
    EquipmentVerificationRecord,
    EquipmentVerificationType,
    MaintenanceEquipment,
    OutfitCard,
    OutfitCardEquipmentUsage,
    PlaceProductionActivity,
)
from hrdepartment_app.services.outfit_card_release_service import (
    attach_equipment_to_outfit_card,
    get_outfit_card_equipment_summary,
    get_staff_fap145_qualification_status,
    release_and_sign_outfit_card,
    validate_outfit_card_for_release,
)
from testing_app.models import (
    Testing,
    TestingAssignment,
    TestingGroup,
)


class MaintenanceEquipmentAndReleaseServiceTests(TestCase):
    """Тестирование метрологического учета оборудования (ФАП-145, пп. 19-25) и сервиса закрытия нарядов."""

    def setUp(self):
        """Подготовка тестовых данных."""
        self.user = DataBaseUser.objects.create_user(
            username="metrologist",
            email="metro@barkol.ru",
            password="pass",
            first_name="Сергей",
            last_name="Метрологов",
            title="Метрологов С.И.",
            maintenance_staff_certificate="Специалист ТО № 77-9988",
            is_staff=True,
        )
        self.type_mi8 = TypeProperty.objects.create(type_property="Ми-8Т")
        self.type_an2 = TypeProperty.objects.create(type_property="Ан-2")

        self.board = Estate.objects.create(
            registration_number="RA-24429",
            factory_number="9904429",
            type_property=self.type_mi8,
            release_date=datetime.date(2015, 1, 1),
        )
        self.place = PlaceProductionActivity.objects.create(
            name="МПД Тахтамышево",
            use_team_orders=True,
        )

        self.card = OutfitCard.objects.create(
            outfit_card_number="127/ТО",
            outfit_card_date=datetime.date(2026, 4, 10),
            outfit_card_date_end=datetime.date(2026, 4, 10),
            air_board=self.board,
            outfit_card_place=self.place,
            employee=self.user,
            certifying_staff=self.user,
            flight_hours=Decimal("750.5"),
            other_work="Регламентные работы ТО Ф-9",
        )

        # 1. Годный динамометрический ключ
        self.wrench = MaintenanceEquipment.objects.create(
            name="Ключ динамометрический щелчковый",
            equipment_type=EquipmentType.MEASURING,
            part_number="TORQ-50-200",
            serial_number="WR-8842",
            inventory_number="ИНВ-00912",
            marking_code="БАР-ИНСТР-042",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=datetime.date(2026, 1, 15),
            next_verification_date=datetime.date(2027, 1, 15),
            interval_value=12,
            interval_source="Методика поверки МИ 184-2023 / 102-ФЗ",
            arshin_verification_number="АРШИН-2026-99120",
            responsible_person=self.user,
        )
        self.wrench.applicable_aircraft_types.add(self.type_mi8)

        # 2. Просроченный прибор КПА
        self.expired_kpa = MaintenanceEquipment.objects.create(
            name="Пульт проверки датчиков КПА-14",
            equipment_type=EquipmentType.CONTROL_TEST,
            part_number="KPA-14M",
            serial_number="KPA-007",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.CALIBRATION,
            last_verification_date=datetime.date(2025, 1, 10),
            next_verification_date=datetime.date(2026, 1, 10),
            responsible_person=self.user,
        )

        # 3. Инструмент в изоляторе брака (п. 25 ФАП-145)
        self.quarantined_tool = MaintenanceEquipment.objects.create(
            name="Манометр шинный МШ-1",
            equipment_type=EquipmentType.MEASURING,
            part_number="MSH-10",
            serial_number="MAN-666",
            operational_status=EquipmentOperationalStatus.QUARANTINED,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=datetime.date(2026, 1, 10),
            next_verification_date=datetime.date(2027, 1, 10),
            responsible_person=self.user,
        )

    def test_equipment_metrology_status_properties(self):
        """Проверяет динамические свойства метрологического статуса и дней до поверки."""
        self.assertEqual(self.wrench.metrology_status, "VALID")
        self.assertTrue(self.wrench.is_metrology_valid)

        is_allowed, reason = self.wrench.can_be_used_for_maintenance(datetime.date(2026, 4, 10))
        self.assertTrue(is_allowed)
        self.assertIn("исправно и поверено", reason)

        is_allowed_exp, reason_exp = self.expired_kpa.can_be_used_for_maintenance(datetime.date(2026, 4, 10))
        self.assertFalse(is_allowed_exp)
        self.assertIn("Срок действия поверки/калибровки истек", reason_exp)

        is_allowed_quar, reason_quar = self.quarantined_tool.can_be_used_for_maintenance(datetime.date(2026, 4, 10))
        self.assertFalse(is_allowed_quar)
        self.assertIn("изоляторе брака", reason_quar)

    def test_attach_equipment_creates_snapshot(self):
        """Проверяет привязку оборудования к наряду с фиксацией исторического снимка."""
        usage = attach_equipment_to_outfit_card(
            outfit_card=self.card,
            equipment=self.wrench,
            user=self.user,
            notes="Затяжка гаек крепления лопастей НВ",
        )
        self.assertEqual(usage.equipment_name, self.wrench.name)
        self.assertEqual(usage.serial_number, "WR-8842")
        self.assertEqual(usage.part_number, "TORQ-50-200")
        self.assertEqual(usage.marking_code, "БАР-ИНСТР-042")
        self.assertEqual(usage.arshin_number, "АРШИН-2026-99120")
        self.assertTrue(usage.is_valid_at_usage)

        summary = get_outfit_card_equipment_summary(self.card)
        self.assertEqual(summary["total_count"], 1)
        self.assertEqual(summary["valid_count"], 1)
        self.assertEqual(summary["invalid_count"], 0)
        self.assertTrue(summary["is_metrology_ready"])

    def test_validation_blocks_outfit_card_with_expired_or_quarantined_equipment(self):
        """Проверяет блокировку закрытия наряда при наличии просроченного оборудования."""
        attach_equipment_to_outfit_card(self.card, self.expired_kpa, user=self.user)

        is_valid, errors = validate_outfit_card_for_release(self.card)
        self.assertFalse(is_valid)
        self.assertTrue(any("Срок действия поверки/калибровки истек" in err for err in errors))

        with self.assertRaises(ValidationError):
            release_and_sign_outfit_card(self.card, certifying_staff=self.user)

        self.card.is_signed = True
        with self.assertRaises(ValidationError):
            self.card.clean()

    def test_equipment_verification_record_updates_equipment(self):
        """Проверяет обновление реквизитов оборудования при регистрации новой поверки."""
        record = EquipmentVerificationRecord.objects.create(
            equipment=self.quarantined_tool,
            verification_type=EquipmentVerificationType.VERIFICATION,
            verification_date=datetime.date(2026, 4, 1),
            valid_until=datetime.date(2027, 4, 1),
            arshin_number="АРШИН-НОВЫЙ-12345",
            organization="ФБУ Томский ЦСМ",
            result_serviceable=True,
            created_by=self.user,
        )

        self.quarantined_tool.refresh_from_db()
        self.assertEqual(self.quarantined_tool.last_verification_date, datetime.date(2026, 4, 1))
        self.assertEqual(self.quarantined_tool.next_verification_date, datetime.date(2027, 4, 1))
        self.assertEqual(self.quarantined_tool.arshin_verification_number, "АРШИН-НОВЫЙ-12345")
        self.assertEqual(self.quarantined_tool.verification_organization, "ФБУ Томский ЦСМ")
        self.assertEqual(self.quarantined_tool.operational_status, EquipmentOperationalStatus.SERVICEABLE)

    def test_successful_release_and_sign_outfit_card_with_hash(self):
        """Проверяет успешное подписание наряда с генерацией CRS и SHA-256 хэша."""
        attach_equipment_to_outfit_card(self.card, self.wrench, user=self.user)

        certificate = release_and_sign_outfit_card(
            outfit_card=self.card,
            certifying_staff=self.user,
            user_ip="192.168.1.100",
        )

        self.card.refresh_from_db()
        self.assertTrue(self.card.is_signed)
        self.assertIsNotNone(self.card.signed_at)
        self.assertEqual(len(self.card.signature_hash), 64)
        self.assertIsNotNone(certificate)
        self.assertEqual(certificate.outfit_card, self.card)
        self.assertEqual(certificate.certifying_staff, self.user)

    def test_staff_fap145_qualification_and_6_months_validity(self):
        """Проверяет расчет 6 месяцев допуска по результатам аттестации в testing_app."""
        now = timezone.now()
        exam_test = Testing.objects.create(
            title="Квалификационный экзамен ФАП-145 для подтверждающего персонала",
            author=self.user,
            order_number="ПР-145/26",
            order_date=datetime.date(2026, 1, 1),
            start_datetime=now - datetime.timedelta(days=30),
            end_datetime=now + datetime.timedelta(days=365),
        )
        group = TestingGroup.objects.create(
            testing=exam_test,
            name="Группа подтверждающего персонала",
        )
        passed_time = timezone.make_aware(datetime.datetime(2026, 1, 15, 10, 0))
        TestingAssignment.objects.create(
            employee=self.user,
            testing=exam_test,
            group=group,
            assigned_job_title="Инженер по ТО ВС",
            status=TestingAssignment.Status.PASSED,
            best_score=95.0,
            passed_at=passed_time,
        )

        qual = get_staff_fap145_qualification_status(self.user, datetime.date(2026, 4, 10))
        self.assertTrue(qual["has_passed_exam"])
        self.assertTrue(qual["is_valid"])
        self.assertEqual(qual["status"], "VALID")
        self.assertEqual(qual["valid_until"], datetime.date(2026, 7, 15))
        self.assertIn("Аттестован по ФАП-145", qual["badge_html"])

        qual_aug = get_staff_fap145_qualification_status(self.user, datetime.date(2026, 8, 1))
        self.assertFalse(qual_aug["is_valid"])
        self.assertEqual(qual_aug["status"], "EXPIRED")
        self.assertIn("Допуск просрочен", qual_aug["badge_html"])

    def test_staff_aircraft_type_mismatch_blocks_release(self):
        """Проверяет блокировку выпуска ВС, если подтверждающий персонал не допущен к данному типу ВС."""
        self.user.allowed_aircraft_types.set([self.type_an2])

        is_valid, errors = validate_outfit_card_for_release(self.card)
        self.assertFalse(is_valid)
        self.assertTrue(any("не имеет допуска к типу ВС" in err for err in errors))

    def test_outfit_card_form_with_used_equipment(self):
        """Проверяет сохранение и синхронизацию оборудования через форму OutfitCardForm."""
        second_tool = MaintenanceEquipment.objects.create(
            name="Мультиметр цифровой APPA-109N",
            equipment_type=EquipmentType.MEASURING,
            part_number="APPA-109N",
            serial_number="AP-9012",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
            last_verification_date=datetime.date(2026, 1, 1),
            next_verification_date=datetime.date(2027, 1, 1),
        )

        form_data = {
            "outfit_card_number": "130/ТО",
            "outfit_card_date": "15.04.2026",
            "outfit_card_date_end": "15.04.2026",
            "start_time": "08:00",
            "end_time": "17:00",
            "air_board": self.board.pk,
            "outfit_card_place": self.place.pk,
            "employee": self.user.pk,
            "other_work": "Проверка электросистемы",
            "used_equipment": [self.wrench.pk, second_tool.pk],
        }

        form = OutfitCardForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        created_card = form.save()

        usages = OutfitCardEquipmentUsage.objects.filter(outfit_card=created_card)
        self.assertEqual(usages.count(), 2)
        eq_ids = set(usages.values_list("equipment_id", flat=True))
        self.assertEqual(eq_ids, {self.wrench.pk, second_tool.pk})

        wrench_usage = usages.get(equipment=self.wrench)
        self.assertEqual(wrench_usage.part_number, self.wrench.part_number)
        self.assertEqual(wrench_usage.serial_number, self.wrench.serial_number)
        self.assertTrue(wrench_usage.is_valid_at_usage)

        update_data = form_data.copy()
        update_data["used_equipment"] = [self.wrench.pk]
        update_form = OutfitCardForm(data=update_data, instance=created_card, user=self.user)
        self.assertTrue(update_form.is_valid(), update_form.errors)
        update_form.save()

        updated_usages = OutfitCardEquipmentUsage.objects.filter(outfit_card=created_card)
        self.assertEqual(updated_usages.count(), 1)
        self.assertEqual(updated_usages.first().equipment_id, self.wrench.pk)

    def test_outfit_card_form_equipment_aircraft_type_mismatch(self):
        """Проверяет валидацию в форме, если выбран инструмент, не применимый к типу ВС."""
        an2_tool = MaintenanceEquipment.objects.create(
            name="Спецприспособление для Ан-2",
            equipment_type=EquipmentType.SPECIAL_TOOL,
            part_number="AN2-TOOL-1",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.NOT_REQUIRED,
        )
        an2_tool.applicable_aircraft_types.add(self.type_an2)

        form_data = {
            "outfit_card_number": "131/ТО",
            "outfit_card_date": "15.04.2026",
            "outfit_card_date_end": "15.04.2026",
            "start_time": "08:00",
            "end_time": "17:00",
            "air_board": self.board.pk,
            "outfit_card_place": self.place.pk,
            "employee": self.user.pk,
            "other_work": "Тест оборудования",
            "used_equipment": [an2_tool.pk],
        }

        form = OutfitCardForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("used_equipment", form.errors)
        self.assertTrue(any("не применимо к типу ВС" in err for err in form.errors["used_equipment"]))


class MaintenanceEquipmentPortalPermissionTests(TestCase):
    """Тестирование разграничения прав доступа к вводу и редактированию оборудования на портале."""

    def setUp(self):
        """Подготовка тестовых пользователей с различными уровнями доступа."""
        # 1. Обычный пользователь без специальных прав
        self.plain_user = DataBaseUser.objects.create_user(
            username="plain_engineer",
            email="plain@barkol.ru",
            password="pass",
            first_name="Иван",
            last_name="Рядовой",
            is_staff=False,
            is_superuser=False,
        )
        # 2. Пользователь со статусом staff, но БЕЗ прав на модель (не должен иметь доступа)
        self.staff_no_perm = DataBaseUser.objects.create_user(
            username="staff_no_perm",
            email="staff@barkol.ru",
            password="pass",
            first_name="Петр",
            last_name="Сотрудников",
            is_staff=True,
            is_superuser=False,
        )
        # 3. Пользователь с явным правом на добавление оборудования
        self.editor_user = DataBaseUser.objects.create_user(
            username="equipment_editor",
            email="editor@barkol.ru",
            password="pass",
            first_name="Алексей",
            last_name="Метрологов",
            is_staff=False,
            is_superuser=False,
        )
        content_type = ContentType.objects.get_for_model(MaintenanceEquipment)
        add_perm = Permission.objects.get(content_type=content_type, codename="add_maintenanceequipment")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_maintenanceequipment")
        verif_ct = ContentType.objects.get_for_model(EquipmentVerificationRecord)
        add_verif_perm = Permission.objects.get(content_type=verif_ct, codename="add_equipmentverificationrecord")

        self.editor_user.user_permissions.add(add_perm, change_perm, add_verif_perm)

        # 4. Суперпользователь
        self.super_user = DataBaseUser.objects.create_user(
            username="super_admin",
            email="admin@barkol.ru",
            password="pass",
            first_name="Админ",
            last_name="Главный",
            is_staff=True,
            is_superuser=True,
        )

        self.client = Client()

        # Тестовый прибор
        self.tool = MaintenanceEquipment.objects.create(
            name="Осциллограф портативный С1-107",
            equipment_type=EquipmentType.CONTROL_TEST,
            part_number="S1-107",
            serial_number="OSC-5541",
            operational_status=EquipmentOperationalStatus.SERVICEABLE,
            verification_type=EquipmentVerificationType.VERIFICATION,
        )

    def test_create_equipment_access_denied_for_plain_and_staff_without_perm(self):
        """Проверяет, что обычный пользователь и staff без прав получают 403 при создании оборудования."""
        # 1. Обычный пользователь
        self.client.force_login(self.plain_user)
        resp1 = self.client.get(reverse("hrdepartment_app:equipment_create"))
        self.assertEqual(resp1.status_code, 403)

        # 2. Staff пользователь БЕЗ прав на модель (требование: staff не дает права)
        self.client.force_login(self.staff_no_perm)
        resp2 = self.client.get(reverse("hrdepartment_app:equipment_create"))
        self.assertEqual(resp2.status_code, 403)

    def test_create_equipment_allowed_for_permitted_user_and_superuser(self):
        """Проверяет, что пользователь с правом add_maintenanceequipment и суперпользователь имеют доступ."""
        # 1. Пользователь с правом
        self.client.force_login(self.editor_user)
        resp1 = self.client.get(reverse("hrdepartment_app:equipment_create"))
        self.assertEqual(resp1.status_code, 200)

        post_data = {
            "name": "Теодолит оптический 3Т5КП",
            "equipment_type": EquipmentType.MEASURING,
            "part_number": "3T5KP",
            "serial_number": "TEO-1290",
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "interval_value": 12,
            "interval_unit": "months",
            "interval_source": "РЭ изготовителя / ГОСТ",
        }
        create_resp = self.client.post(reverse("hrdepartment_app:equipment_create"), data=post_data)
        self.assertEqual(create_resp.status_code, 302)
        self.assertTrue(MaintenanceEquipment.objects.filter(serial_number="TEO-1290").exists())

        # 2. Суперпользователь
        self.client.force_login(self.super_user)
        resp2 = self.client.get(reverse("hrdepartment_app:equipment_create"))
        self.assertEqual(resp2.status_code, 200)

    def test_update_equipment_permissions(self):
        """Проверяет разграничение прав на редактирование оборудования на портале."""
        update_url = reverse("hrdepartment_app:equipment_update", kwargs={"pk": self.tool.pk})

        # Staff без прав -> 403
        self.client.force_login(self.staff_no_perm)
        self.assertEqual(self.client.get(update_url).status_code, 403)

        # Пользователь с change_maintenanceequipment -> 200
        self.client.force_login(self.editor_user)
        self.assertEqual(self.client.get(update_url).status_code, 200)

        # Суперпользователь -> 200
        self.client.force_login(self.super_user)
        self.assertEqual(self.client.get(update_url).status_code, 200)

    def test_equipment_verification_create_portal(self):
        """Проверяет регистрацию поверки через веб-форму на портале и обновление статуса оборудования."""
        # Переводим прибор в карантин
        self.tool.operational_status = EquipmentOperationalStatus.QUARANTINED
        self.tool.save()

        self.client.force_login(self.editor_user)
        verif_url = reverse("hrdepartment_app:equipment_verification_create")
        get_resp = self.client.get(f"{verif_url}?equipment={self.tool.pk}")
        self.assertEqual(get_resp.status_code, 200)

        post_data = {
            "equipment": self.tool.pk,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "verification_date": "05.10.2026",
            "valid_until": "05.10.2027",
            "arshin_number": "АРШИН-ПОРТАЛ-7711",
            "organization": "ФБУ Новосибирский ЦСМ",
            "result_serviceable": "on",
            "notes": "Поверка выполнена в полном объеме",
        }
        post_resp = self.client.post(verif_url, data=post_data)
        self.assertEqual(post_resp.status_code, 302)

        self.tool.refresh_from_db()
        self.assertEqual(self.tool.operational_status, EquipmentOperationalStatus.SERVICEABLE)
        self.assertEqual(self.tool.arshin_verification_number, "АРШИН-ПОРТАЛ-7711")
        self.assertEqual(self.tool.verification_organization, "ФБУ Новосибирский ЦСМ")

    def test_equipment_detail_view_renders_successfully(self):
        """Проверяет успешное отображение страницы детального просмотра карточки оборудования."""
        EquipmentVerificationRecord.objects.create(
            equipment=self.tool,
            verification_type=EquipmentVerificationType.VERIFICATION,
            verification_date=datetime.date(2026, 1, 10),
            valid_until=datetime.date(2027, 1, 10),
            organization="Тест-ЦСМ",
            arshin_number="АРШИН-9988",
            result_serviceable=True,
            created_by=self.super_user,
        )

        detail_url = reverse("hrdepartment_app:equipment_detail", kwargs={"pk": self.tool.pk})

        resp_anon = self.client.get(detail_url)
        self.assertEqual(resp_anon.status_code, 302)

        self.client.force_login(self.plain_user)
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.tool.name)
        self.assertContains(resp, "АРШИН-9988")
        self.assertIn("verifications", resp.context)
        self.assertEqual(len(resp.context["verifications"]), 1)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.next_verification_date, datetime.date(2027, 1, 10))
