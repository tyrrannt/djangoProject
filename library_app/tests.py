from django.test import TestCase, RequestFactory
from django.contrib.auth.models import Permission
from django.urls import reverse

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser
from library_app.models import HelpTopic


class HelpItemViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        cls.factory = RequestFactory()

        cls.user = DataBaseUser.objects.create_user(
            username="testuser",
            password="12345",
            first_name="Тест",
            last_name="Тестов",
        )
        view_permission = Permission.objects.get(codename="view_helptopic")
        cls.user.user_permissions.add(view_permission)

        cls.portal_property = PortalProperty.objects.create(portal_name="Test Portal")
        cls.help_topic = HelpTopic.objects.create(title="Test Topic", text="Test")

    def setUp(self):
        self.client.login(username="testuser", password="12345")

    def test_help_item_view_url_accessible_by_name(self):
        response = self.client.get(reverse("library_app:help", kwargs={"pk": self.help_topic.pk}))
        self.assertEqual(response.status_code, 200)

    def test_help_item_view_correct_template_used(self):
        response = self.client.get(reverse("library_app:help", kwargs={"pk": self.help_topic.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "library_app/helptopic_detail.html"
        )  # change to your correct template

    def test_help_item_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("library_app:help", kwargs={"pk": self.help_topic.pk}))
        # It should redirect to login page because it's a LoginRequiredMixin
        self.assertEqual(response.status_code, 302)

    def test_help_item_permission_required(self):
        # Create a user without view permission
        user_without_permission = DataBaseUser.objects.create_user(
            username="testuser2", password="54321", first_name="Тест2", last_name="Пользователь2"
        )
        self.client.login(username="testuser2", password="54321")
        response = self.client.get(reverse("library_app:help", kwargs={"pk": self.help_topic.pk}))
        # It should return 403 because the user doesn't have the required permission
        self.assertEqual(response.status_code, 403)


class ErrorPagesTestCase(TestCase):
    """Тестирование страниц ошибок сервера и их статус-кодов (400, 403, CSRF, 404, 500, 503)."""

    def setUp(self) -> None:
        """Создает тестового пользователя в базе данных."""
        self.user = DataBaseUser.objects.create_user(
            username="error_test_user",
            password="testpassword",
            first_name="Тест",
            last_name="Ошибок",
        )
        self.client.force_login(self.user)

    def test_error_400_status_and_template(self) -> None:
        """Проверяет страницу ошибки 400 Bad Request."""
        response = self.client.get(reverse("library_app:error_400"))
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "library_app/400.html")
        self.assertIn("error_code", response.context)
        self.assertEqual(response.context["error_code"], "400")

    def test_error_403_status_and_template(self) -> None:
        """Проверяет страницу ошибки 403 Forbidden."""
        response = self.client.get(reverse("library_app:error_403"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "library_app/403.html")
        self.assertIn("error_code", response.context)
        self.assertEqual(response.context["error_code"], "403")

    def test_error_csrf_status_and_template(self) -> None:
        """Проверяет страницу сбоя CSRF токена."""
        response = self.client.get(reverse("library_app:error_csrf"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "library_app/csrf_failure.html")
        self.assertIn("error_code", response.context)
        self.assertEqual(response.context["error_code"], "CSRF")

    def test_error_404_status_and_template(self) -> None:
        """Проверяет страницу ошибки 404 Not Found."""
        response = self.client.get(reverse("library_app:error_404"))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "library_app/404.html")
        self.assertIn("error_code", response.context)
        self.assertEqual(response.context["error_code"], "404")

    def test_error_500_status_and_template(self) -> None:
        """Проверяет страницу ошибки 500 Internal Server Error и код инцидента."""
        response = self.client.get(reverse("library_app:error_500"))
        self.assertEqual(response.status_code, 500)
        self.assertTemplateUsed(response, "library_app/500.html")
        self.assertIn("incident_id", response.context)
        self.assertTrue(response.context["incident_id"].startswith("BARKOL-500-"))

    def test_error_503_status_and_template(self) -> None:
        """Проверяет страницу ошибки 503 Service Unavailable."""
        response = self.client.get(reverse("library_app:error_503"))
        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, "library_app/503.html")
        self.assertIn("error_code", response.context)
        self.assertEqual(response.context["error_code"], "503")

    def test_handler404_nonexistent_url(self) -> None:
        """Проверяет глобальный перехватчик 404 при переходе по несуществующему URL."""
        response = self.client.get("/totally-nonexistent-barkol-page-xyz-123/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "library_app/404.html")

