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
            username="testuser", password="12345"
        )
        view_permission = Permission.objects.get(codename="view_helptopic")
        cls.user.user_permissions.add(view_permission)

        cls.portal_property = PortalProperty.objects.create(portal_name="Test Portal")
        cls.help_topic = HelpTopic.objects.create(title="Test Topic", text="Test")

    def setUp(self):
        self.client.login(username="testuser", password="12345")

    def test_help_item_view_url_accessible_by_name(self):
        response = self.client.get(reverse("help", kwargs={"pk": self.help_topic.pk}))
        self.assertEqual(response.status_code, 200)

    def test_help_item_view_correct_template_used(self):
        response = self.client.get(reverse("help", kwargs={"pk": self.help_topic.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "library_app/helptopic_detail.html"
        )  # change to your correct template

    def test_help_item_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("help", kwargs={"pk": self.help_topic.pk}))
        # It should redirect to login page because it's a LoginRequiredMixin
        self.assertEqual(response.status_code, 302)

    def test_help_item_permission_required(self):
        # Create a user without view permission
        user_without_permission = DataBaseUser.objects.create_user(
            username="testuser2", password="54321"
        )
        self.client.login(username="testuser2", password="54321")
        response = self.client.get(reverse("help", kwargs={"pk": self.help_topic.pk}))
        # It should return 403 because the user doesn't have the required permission
        self.assertEqual(response.status_code, 403)
