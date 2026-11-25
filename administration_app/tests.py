"""Unit-тесты для модуля утилит administration_app.utils (интеграция OData с 1С)."""

from unittest.mock import MagicMock, patch
from django.test import TestCase

from administration_app.utils import (
    EMAIL_1C_CONTACT_KIND,
    EMAIL_1C_CONTACT_TYPE,
    _build_1c_email_contact,
    update_1c_physical_person_email,
)


class Update1CPhysicalPersonEmailTestCase(TestCase):
    """Тестирование функции обновления/записи email физлица в 1С ЗУП через OData."""

    def test_build_1c_email_contact_structure(self) -> None:
        """Тест формирования структуры элемента КонтактнаяИнформация для email."""
        contact = _build_1c_email_contact("o.adygezalov@barkol.ru", line_number=2)
        self.assertEqual(contact["LineNumber"], "2")
        self.assertEqual(contact["Тип"], EMAIL_1C_CONTACT_TYPE)
        self.assertEqual(contact["Вид_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertEqual(contact["Представление"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["Значение"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["АдресЭП"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["ДоменноеИмяСервера"], "barkol.ru")
        self.assertEqual(contact["ВидДляСписка_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertIn("xsi:type=\"ЭлектроннаяПочта\"", contact["ЗначенияПолей"])
        self.assertIn("Значение=\"o.adygezalov@barkol.ru\"", contact["ЗначенияПолей"])

    def test_update_1c_email_invalid_guid(self) -> None:
        """Тест отклонения пустого или невалидного GUID."""
        success, msg = update_1c_physical_person_email("", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("person_ref_key отсутствует", msg)

        success, msg = update_1c_physical_person_email("00000000-0000-0000-0000-000000000000", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("пустой GUID", msg)

        success, msg = update_1c_physical_person_email("not-a-valid-guid", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("Некорректный GUID", msg)

    def test_update_1c_email_invalid_email(self) -> None:
        """Тест отклонения некорректного формата email."""
        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "invalid-email")
        self.assertFalse(success)
        self.assertIn("Некорректный формат", msg)

        success, msg = update_1c_physical_person_email(guid, "@barkol.ru")
        self.assertFalse(success)
        self.assertIn("Некорректный формат", msg)

    def test_update_1c_email_invalid_base_index(self) -> None:
        """Тест отклонения некорректного индекса базы."""
        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "test@barkol.ru", base_index=99)
        self.assertFalse(success)
        self.assertIn("Некорректный индекс", msg)

    @patch("requests.patch")
    @patch("requests.get")
    def test_update_1c_email_create_new_contact(self, mock_get: MagicMock, mock_patch: MagicMock) -> None:
        """Тест добавления новой строки email, когда у физлица в 1С есть только телефон и адрес."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Ref_Key": "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419",
            "КонтактнаяИнформация": [
                {
                    "LineNumber": "1",
                    "Тип": "Телефон",
                    "Вид_Key": "d34fea50-cfaf-11e6-bad8-902b345cadc2",
                    "Представление": "+7 (925) 045-23-43",
                }
            ],
        }

        mock_patch.return_value.status_code = 204

        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "o.adygezalov@barkol.ru")

        self.assertTrue(success)
        self.assertIn("успешно записан", msg)

        # Проверяем, что в PATCH отправлено 2 элемента (телефон + новый email)
        patch_kwargs = mock_patch.call_args[1]
        contacts = patch_kwargs["json"]["КонтактнаяИнформация"]
        self.assertEqual(len(contacts), 2)
        email_row = contacts[1]
        self.assertEqual(email_row["LineNumber"], "2")
        self.assertEqual(email_row["Тип"], EMAIL_1C_CONTACT_TYPE)
        self.assertEqual(email_row["Вид_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertEqual(email_row["Представление"], "o.adygezalov@barkol.ru")
        self.assertEqual(email_row["АдресЭП"], "o.adygezalov@barkol.ru")
        self.assertEqual(email_row["ДоменноеИмяСервера"], "barkol.ru")

    @patch("requests.patch")
    @patch("requests.get")
    def test_update_1c_email_update_existing_contact(self, mock_get: MagicMock, mock_patch: MagicMock) -> None:
        """Тест обновления уже существующей строки email в 1С."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Ref_Key": "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419",
            "КонтактнаяИнформация": [
                {
                    "LineNumber": "1",
                    "Тип": "АдресЭлектроннойПочты",
                    "Вид_Key": EMAIL_1C_CONTACT_KIND,
                    "Представление": "old@barkol.ru",
                    "АдресЭП": "old@barkol.ru",
                    "Значение": "old@barkol.ru",
                }
            ],
        }

        mock_patch.return_value.status_code = 200

        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "new@barkol.ru")

        self.assertTrue(success)
        self.assertIn("успешно записан", msg)

        patch_kwargs = mock_patch.call_args[1]
        contacts = patch_kwargs["json"]["КонтактнаяИнформация"]
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["Представление"], "new@barkol.ru")
        self.assertEqual(contacts[0]["АдресЭП"], "new@barkol.ru")
        self.assertEqual(contacts[0]["Значение"], "new@barkol.ru")


class UserAccessServiceTestCase(TestCase):
    """Тестирование трехуровневой модели синхронизации прав и ролей UserAccessService."""

    def setUp(self) -> None:
        """Подготовка тестовых данных: групп, должности и пользователя."""
        from django.contrib.auth.models import Group
        from administration_app.access_service import UserAccessService
        from customers_app.models import DataBaseUser, DataBaseUserWorkProfile, Groups, Job

        self.UserAccessService = UserAccessService
        self.group_job, _ = Groups.objects.get_or_create(name="Группа Должности Тест")
        self.group_personal, _ = Group.objects.get_or_create(name="Группа Персональная Тест")
        self.group_lpc, _ = Group.objects.get_or_create(name="[ЛПК] Руководство")
        self.group_extra, _ = Group.objects.get_or_create(name="Группа Экстра Тест")

        self.job, _ = Job.objects.get_or_create(name="Инженер-тестировщик Тест")
        self.job.group.add(self.group_job)

        self.user, _ = DataBaseUser.objects.get_or_create(
            username="test_access_engineer",
            defaults={
                "password": "testpassword123",
                "first_name": "Иван",
                "last_name": "Иванов",
            }
        )
        if not getattr(self.user, "user_work_profile", None):
            self.user.user_work_profile = DataBaseUserWorkProfile.objects.create(job=self.job)
            self.user.save()
        else:
            self.user.user_work_profile.job = self.job
            self.user.user_work_profile.save()

    def test_sync_user_groups_adds_job_and_personal(self) -> None:
        """Проверяет добавление должностных и персональных групп при синхронизации."""
        self.user.personal_groups.clear()
        self.user.groups.clear()
        self.user.personal_groups.add(self.group_personal)

        # Проверяем, что сигнал m2m_changed автоматически добавил группы
        current_names = {g.name for g in self.user.groups.all()}
        self.assertIn(self.group_job.name, current_names)
        self.assertIn(self.group_personal.name, current_names)

        # Проверяем явный вызов sync_user_groups при очищенных groups
        self.user.groups.clear()
        stat = self.UserAccessService.sync_user_groups(self.user)
        self.assertFalse(stat["skipped"])
        self.assertEqual(stat["added"], 2)  # group_job + group_personal

        current_names = {g.name for g in self.user.groups.all()}
        self.assertIn(self.group_job.name, current_names)
        self.assertIn(self.group_personal.name, current_names)

    def test_sync_user_groups_preserves_protected_roles(self) -> None:
        """Проверяет, что защищенные роли (например [ЛПК] *) никогда не удаляются."""
        self.user.groups.clear()
        self.user.groups.add(self.group_lpc)

        stat = self.UserAccessService.sync_user_groups(self.user)
        self.assertEqual(stat["retained_protected"], 1)

        current_names = {g.name for g in self.user.groups.all()}
        self.assertIn(self.group_lpc.name, current_names)
        self.assertIn(self.group_job.name, current_names)

    def test_sync_user_groups_removes_stale_job_group_but_protects_personal_and_lpc(self) -> None:
        """Проверяет корректное удаление устаревших должностных групп с защитой персональных и ЛПК ролей."""
        from customers_app.models import Groups

        self.user.groups.clear()
        self.user.personal_groups.clear()
        old_job_group, _ = Groups.objects.get_or_create(name="Старая Группа Должности Тест")
        self.user.groups.add(old_job_group, self.group_lpc)
        self.user.personal_groups.add(self.group_personal)

        self.UserAccessService.sync_user_groups(self.user)
        current_names = {g.name for g in self.user.groups.all()}
        self.assertIn(self.group_job.name, current_names)
        self.assertIn(self.group_personal.name, current_names)
        self.assertIn(self.group_lpc.name, current_names)
        # Устаревшая группа удалена:
        self.assertNotIn(old_job_group.name, current_names)

    def test_promote_extra_groups_to_personal(self) -> None:
        """Проверяет фиксацию нестандартных групп в качестве персональных."""
        self.user.groups.clear()
        self.user.personal_groups.clear()
        self.user.groups.add(self.group_job, self.group_extra)

        report = self.UserAccessService.get_permissions_audit_report()
        user_report = next((item for item in report if item["user_id"] == self.user.pk), None)
        self.assertIsNotNone(user_report)
        self.assertIn(self.group_extra.name, user_report["unclassified_groups"])

        promoted_count = self.UserAccessService.promote_extra_groups_to_personal(self.user.pk)
        self.assertEqual(promoted_count, 1)

        personal_names = {g.name for g in self.user.personal_groups.all()}
        self.assertIn(self.group_extra.name, personal_names)

        new_report = self.UserAccessService.get_permissions_audit_report()
        user_report_after = next((item for item in new_report if item["user_id"] == self.user.pk), None)
        self.assertIsNone(user_report_after)

    def test_promote_all_extra_groups_to_personal(self) -> None:
        """Проверяет массовую фиксацию нераспределенных прав для всех пользователей."""
        self.user.groups.clear()
        self.user.personal_groups.clear()
        self.user.groups.add(self.group_extra)
        summary = self.UserAccessService.promote_all_extra_groups_to_personal()
        self.assertGreaterEqual(summary["users_count"], 1)
        self.assertGreaterEqual(summary["groups_count"], 1)
        personal_names = {g.name for g in self.user.personal_groups.all()}
        self.assertIn(self.group_extra.name, personal_names)

    def test_revoke_user_group_personal(self) -> None:
        """Проверяет успешный отзыв персонального права сотрудника."""
        self.user.personal_groups.add(self.group_personal)
        self.user.groups.add(self.group_personal)

        success, msg = self.UserAccessService.revoke_user_group(self.user.pk, self.group_personal.pk)
        self.assertTrue(success)
        self.assertIn("успешно отозвано", msg)

        self.assertNotIn(self.group_personal, self.user.personal_groups.all())
        self.assertNotIn(self.group_personal, self.user.groups.all())

    def test_revoke_user_group_direct_system_group(self) -> None:
        """Проверяет отзыв права, назначенного напрямую в системе (в user.groups)."""
        self.user.personal_groups.clear()
        self.user.groups.add(self.group_extra)

        success, msg = self.UserAccessService.revoke_user_group(self.user.pk, self.group_extra.pk)
        self.assertTrue(success)
        self.assertIn("успешно отозвано", msg)

        self.assertNotIn(self.group_extra, self.user.groups.all())

    def test_revoke_user_group_domain_role(self) -> None:
        """Проверяет отзыв защищенной роли ЛПК при явном административном действии."""
        self.user.groups.add(self.group_lpc)

        success, msg = self.UserAccessService.revoke_user_group(self.user.pk, self.group_lpc.pk)
        self.assertTrue(success)
        self.assertIn("успешно отозвано", msg)

        self.assertNotIn(self.group_lpc, self.user.groups.all())

    def test_revoke_user_group_blocked_for_job_group(self) -> None:
        """Проверяет блокировку отзыва прав, наследуемых из штатной должности."""
        self.user.groups.add(self.group_job)

        success, msg = self.UserAccessService.revoke_user_group(self.user.pk, self.group_job.pk)
        self.assertFalse(success)
        self.assertIn("наследуется автоматически", msg)
        self.assertIn("Инженер-тестировщик Тест", msg)
        self.assertIn("штатном расписании", msg)


class WebTerminalTestCase(TestCase):
    """Набор тестов для проверки безопасности, контекста и моделей веб-терминала."""

    def setUp(self) -> None:
        """Создает тестовых пользователей: обычного и суперадминистратора."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.regular_user = User.objects.create_user(
            username="regular_test_user",
            email="regular@barkol.ru",
            password="testpassword123",
            first_name="Обычный",
            last_name="Пользователь",
        )
        self.super_user = User.objects.create_superuser(
            username="super_test_user",
            email="superuser@barkol.ru",
            password="superpassword123",
            first_name="Супер",
            last_name="Администратор",
        )

    def test_web_terminal_requires_login(self) -> None:
        """Проверяет редирект анонимного пользователя на страницу авторизации."""
        from django.urls import reverse
        url = reverse("administration_app:web_terminal")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_web_terminal_forbidden_for_regular_user(self) -> None:
        """Проверяет запрет доступа (403 PermissionDenied) для обычного пользователя."""
        from django.urls import reverse
        url = reverse("administration_app:web_terminal")
        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_web_terminal_accessible_for_superuser(self) -> None:
        """Проверяет успешный доступ суперадминистратора и корректность контекста."""
        from django.urls import reverse
        url = reverse("administration_app:web_terminal")
        self.client.force_login(self.super_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("production_dir", response.context)
        self.assertEqual(response.context["production_dir"], "/home/proxmox/djangoProject")
        self.assertIn("tmux_available", response.context)
        self.assertIn("recent_sessions", response.context)
        self.assertTemplateUsed(response, "administration_app/web_terminal.html")

    def test_web_terminal_session_model_and_duration(self) -> None:
        """Проверяет создание модели WebTerminalSession и расчет ее длительности."""
        from administration_app.models import WebTerminalSession
        from django.utils import timezone
        import datetime

        start = timezone.now() - datetime.timedelta(seconds=125)
        end = timezone.now()
        session = WebTerminalSession.objects.create(
            user=self.super_user,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 Test",
            tab_id="tab_2",
            is_tmux=True,
            started_at=start,
            ended_at=end,
        )
        session.calculate_duration()
        session.save()

        self.assertEqual(session.duration_seconds, 125)
        self.assertIn("super_test_user [tmux]", str(session))


class ODataBuilderViewsTestCase(TestCase):
    """Тестирование конструктора и тестера OData-запросов (/portal/odata/)."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.regular_user = User.objects.create_user(
            username="odata_regular",
            password="Password123!",
            first_name="Обычный",
            last_name="Пользователь",
        )
        self.staff_user = User.objects.create_user(
            username="odata_staff",
            password="Password123!",
            first_name="Админ",
            last_name="Сотрудник",
            is_staff=True,
        )
        self.base_zup = "72095052-970f-11e3-84fb-00e05301b4e4"

    def test_odata_access_control(self) -> None:
        """Обычному пользователю доступ к /portal/odata/ и API запрещён."""
        from django.urls import reverse

        self.client.force_login(self.regular_user)
        resp_page = self.client.get(reverse("administration_app:1c_odata_request"))
        self.assertEqual(resp_page.status_code, 403)

        resp_gen = self.client.get(reverse("administration_app:generate_1c_odata_request"))
        self.assertEqual(resp_gen.status_code, 403)

        self.client.force_login(self.staff_user)
        resp_ok = self.client.get(reverse("administration_app:1c_odata_request"))
        self.assertEqual(resp_ok.status_code, 200)
        self.assertTemplateUsed(resp_ok, "administration_app/odata.html")

    def test_generate_odata_filters_and_orderby(self) -> None:
        """Проверяет генерацию $filter (datetime, guid, substringof, or), $orderby без дублей и опции."""
        import json
        from django.urls import reverse

        self.client.force_login(self.staff_user)
        filters = [
            {"field": "Period", "operator": "ge", "value": "2026-11-01", "value_type": "datetime", "logic": "and"},
            {"field": "ФизическоеЛицо_Key", "operator": "eq", "value": "11111111-1111-1111-1111-111111111111", "value_type": "guid", "logic": "and"},
            {"field": "Description", "operator": "substringof", "value": "Иванов", "value_type": "string", "logic": "or"},
        ]
        resp = self.client.get(
            reverse("administration_app:generate_1c_odata_request"),
            {
                "base": self.base_zup,
                "object_type": "AccumulationRegister",
                "object_name": "НачисленияУдержанияПоСотрудникам",
                "resource_mode": "record_type",
                "format": "json_nometadata",
                "filters_json": json.dumps(filters),
                "$orderby": "Period desc",
                "direction": "asc",
                "$expand": "ФизическоеЛицо",
                "$allowedOnly": "true",
                "$inlinecount": "allpages",
            },
        )
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["request_url"]
        self.assertIn("AccumulationRegister_НачисленияУдержанияПоСотрудникам_RecordType?", url)
        self.assertIn("$filter=Period ge datetime'2026-11-01T00:00:00' and ФизическоеЛицо_Key eq guid'11111111-1111-1111-1111-111111111111' or substringof('Иванов', Description) eq true", url)
        self.assertIn("$orderby=Period desc", url)
        self.assertNotIn("Period desc asc", url)
        self.assertIn("$expand=ФизическоеЛицо", url)
        self.assertIn("$allowedOnly=true", url)
        self.assertIn("$inlinecount=allpages", url)
        self.assertIn("$format=application/json;odata=nometadata", url)

    def test_generate_odata_key_and_count_modes(self) -> None:
        """Проверяет режимы key (с навигацией) и /$count."""
        from django.urls import reverse

        self.client.force_login(self.staff_user)
        resp_key = self.client.get(
            reverse("administration_app:generate_1c_odata_request"),
            {
                "base": self.base_zup,
                "object_type": "Catalog",
                "object_name": "Сотрудники",
                "resource_mode": "key",
                "entity_key": "8d04ce3c-6360-11e9-dd92-fa163e8ba11d",
                "property_path": "ФизическоеЛицо/Description",
                "format": "atom",
            },
        )
        self.assertEqual(resp_key.status_code, 200)
        self.assertIn(
            "/Catalog_Сотрудники(guid'8d04ce3c-6360-11e9-dd92-fa163e8ba11d')/ФизическоеЛицо/Description?$format=atom",
            resp_key.json()["request_url"],
        )

        resp_count = self.client.get(
            reverse("administration_app:generate_1c_odata_request"),
            {
                "base": self.base_zup,
                "object_type": "Catalog",
                "object_name": "Сотрудники",
                "resource_mode": "count",
            },
        )
        self.assertEqual(resp_count.status_code, 200)
        self.assertTrue(resp_count.json()["request_url"].endswith("/Catalog_Сотрудники/$count"))

    @patch("administration_app.views.requests.get")
    def test_test_1c_odata_request_ssrf_and_xml_error(self, mock_get: MagicMock) -> None:
        """Проверяет защиту от SSRF и разбор XML-ошибки 1С OData."""
        from django.urls import reverse

        self.client.force_login(self.staff_user)

        # Пустой URL
        resp_empty = self.client.get(reverse("administration_app:test_1c_odata_request"))
        self.assertEqual(resp_empty.status_code, 400)

        # Сторонний хост (SSRF)
        resp_ssrf = self.client.get(
            reverse("administration_app:test_1c_odata_request"),
            {"url": "http://evil.example.com/odata/standard.odata/Catalog_Users"},
        )
        self.assertEqual(resp_ssrf.status_code, 400)

        # Ошибка 1С OData в XML
        mock_get.return_value.status_code = 404
        mock_get.return_value.headers = {"Content-Type": "application/xml"}
        mock_get.return_value.text = (
            '<m:error xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
            "<m:code>9</m:code>"
            "<m:message>Экземпляр сущности не найден</m:message>"
            "</m:error>"
        )
        resp_err = self.client.get(
            reverse("administration_app:test_1c_odata_request"),
            {"url": f"http://192.168.10.11/{self.base_zup}/odata/standard.odata/Catalog_Сотрудники"},
        )
        self.assertEqual(resp_err.status_code, 200)
        payload = resp_err.json()
        self.assertEqual(payload["status_code"], 404)
        self.assertEqual(payload["format"], "xml")
        self.assertEqual(payload["odata_error"]["code"], "9")
        self.assertIn("не найден", payload["odata_error"]["message"])

    @patch("administration_app.views.requests.get")
    def test_get_1c_entity_fields_csdl(self, mock_get: MagicMock) -> None:
        """Проверяет парсинг полей сущности из CSDL $metadata."""
        from django.core.cache import cache
        from django.urls import reverse

        cache.clear()
        self.client.force_login(self.staff_user)
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = """<?xml version="1.0" encoding="utf-8"?>
        <edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
          <edmx:DataServices>
            <Schema Namespace="StandardODATA" xmlns="http://schemas.microsoft.com/ado/2009/11/edm">
              <EntityType Name="Catalog_Сотрудники">
                <Property Name="Ref_Key" Type="Edm.Guid" Nullable="false"/>
                <Property Name="Description" Type="Edm.String" Nullable="true"/>
                <NavigationProperty Name="ФизическоеЛицо"/>
              </EntityType>
            </Schema>
          </edmx:DataServices>
        </edmx:Edmx>"""

        resp = self.client.get(
            reverse("administration_app:get_1c_entity_fields"),
            {"base": self.base_zup, "object_type": "Catalog", "object_name": "Сотрудники"},
        )
        self.assertEqual(resp.status_code, 200)
        fields = resp.json()["fields"]
        self.assertEqual(len(fields), 3)
        self.assertEqual(fields[0]["name"], "Ref_Key")
        self.assertEqual(fields[0]["type"], "Edm.Guid")
        self.assertTrue(fields[2]["is_navigation"])






