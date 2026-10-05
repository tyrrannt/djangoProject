from django.test import TestCase, Client
from django.urls import reverse
from contracts_app.models import TypeProperty
from customers_app.forms import StaffUpdateForm
from customers_app.models import DataBaseUser, Division, Job, AccessLevel


class StaffMaintenanceFieldsTests(TestCase):
    """Тестирование редактирования и отображения квалификационных данных ТО ВС (ФАП-145 / ФАП-147)."""

    def setUp(self):
        """Создает тестовые сущности: пользователя, типы ВС и права доступа."""
        self.client = Client()
        self.admin_user = DataBaseUser.objects.create_superuser(
            username="admin_test",
            email="admin@barkol.ru",
            password="adminpassword123",
            first_name="Админ",
            last_name="Тестовый",
            surname="Админович",
        )
        self.target_user = DataBaseUser.objects.create_user(
            username="engineer_test",
            email="engineer@barkol.ru",
            password="engpassword123",
            first_name="Иван",
            last_name="Инженеров",
            surname="Петрович",
            is_staff=True,
        )

        self.ac_an2 = TypeProperty.objects.create(type_property="АН-2")
        self.ac_mi8 = TypeProperty.objects.create(type_property="МИ-8Т")
        self.ac_cessna = TypeProperty.objects.create(type_property="Cessna 172S")

    def test_staff_update_form_fields_and_widgets(self):
        """Проверяет наличие полей ТО ВС и правильность настройки виджетов в StaffUpdateForm."""
        form = StaffUpdateForm(instance=self.target_user)
        self.assertIn("maintenance_staff_certificate", form.fields)
        self.assertIn("allowed_aircraft_types", form.fields)

        # Проверка атрибутов виджета allowed_aircraft_types
        widget = form.fields["allowed_aircraft_types"].widget
        self.assertTrue(widget.attrs.get("data-plugin-selectTwo"))
        self.assertEqual(widget.attrs.get("multiple"), "multiple")
        self.assertIn("form-control-modern", widget.attrs.get("class", ""))

        # Проверка атрибутов maintenance_staff_certificate
        cert_widget = form.fields["maintenance_staff_certificate"].widget
        self.assertIn("form-control-modern", cert_widget.attrs.get("class", ""))
        self.assertEqual(cert_widget.attrs.get("placeholder"), "например, III. № 0184728")

    def test_staff_update_form_save(self):
        """Проверяет корректность сохранения квалификационных полей через StaffUpdateForm."""
        form_data = {
            "last_name": "Инженеров",
            "first_name": "Иван",
            "surname": "Петрович",
            "email": "engineer@barkol.ru",
            "maintenance_staff_certificate": "III. № 9876543",
            "allowed_aircraft_types": [self.ac_an2.pk, self.ac_mi8.pk],
        }
        form = StaffUpdateForm(data=form_data, instance=self.target_user)
        self.assertTrue(form.is_valid(), f"Ошибки валидации формы: {form.errors}")
        saved_user = form.save()

        self.assertEqual(saved_user.maintenance_staff_certificate, "III. № 9876543")
        self.assertEqual(
            set(saved_user.allowed_aircraft_types.values_list("pk", flat=True)),
            {self.ac_an2.pk, self.ac_mi8.pk},
        )

    def test_staff_update_view_get(self):
        """Проверяет отображение вкладки 'Квалификация ТО ВС' на странице редактирования сотрудника."""
        self.client.force_login(self.admin_user)
        url = reverse("customers_app:staff_update", args=[self.target_user.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Квалификация ТО ВС")
        self.assertContains(response, "maintenance_staff_certificate")
        self.assertContains(response, "allowed_aircraft_types")

    def test_staff_update_view_post_updates_qualification(self):
        """Проверяет успешное обновление свидетельства и типов ВС через POST-запрос на портале."""
        self.client.force_login(self.admin_user)
        url = reverse("customers_app:staff_update", args=[self.target_user.pk])

        post_data = {
            "last_name": "Инженеров",
            "first_name": "Иван",
            "surname": "Петрович",
            "email": "engineer@barkol.ru",
            "type_users": "none",
            "gender": "none",
            "citizenship": "none",
            "job": "none",
            "divisions": "none",
            "internal_phone": "",
            "date_of_employment": "",
            "personal_work_schedule_start": "",
            "personal_work_schedule_end": "",
            "snils": "",
            "oms": "",
            "inn": "",
            "series": "",
            "number": "",
            "issued_by_whom": "",
            "date_of_issue": "",
            "division_code": "",
            "maintenance_staff_certificate": "Спец. № 555-ФАП",
            "allowed_aircraft_types": [self.ac_mi8.pk, self.ac_cessna.pk],
        }

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.maintenance_staff_certificate, "Спец. № 555-ФАП")
        self.assertEqual(
            set(self.target_user.allowed_aircraft_types.values_list("pk", flat=True)),
            {self.ac_mi8.pk, self.ac_cessna.pk},
        )

    def test_staff_detail_view_renders_qualification(self):
        """Проверяет отображение вкладки квалификации и бейджей типов ВС в детальной карточке."""
        self.target_user.maintenance_staff_certificate = "Спец. № 111-ФАП"
        self.target_user.save()
        self.target_user.allowed_aircraft_types.set([self.ac_an2, self.ac_cessna])

        self.client.force_login(self.admin_user)
        url = reverse("customers_app:staff", args=[self.target_user.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Квалификация ТО ВС")
        self.assertContains(response, "Спец. № 111-ФАП")
        self.assertContains(response, "АН-2")
        self.assertContains(response, "Cessna 172S")
