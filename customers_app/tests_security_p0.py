# -*- coding: utf-8 -*-
"""Модульные тесты устранения критической уязвимости P0 (DataBaseUserViewSet / Mobile API)."""

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from customers_app.models import DataBaseUser
from customers_app.serializers import DataBaseUserSerializer
from customers_app.views import DataBaseUserViewSet


class SecurityP0MobileApiTests(TestCase):
    """Проверяет закрытие P0 в DataBaseUserViewSet и отключение неиспользуемого Android REST API."""

    def setUp(self) -> None:
        """Создаёт обычного сотрудника и администратора для проверки разграничения прав."""
        self.regular_user = DataBaseUser.objects.create_user(
            username="p0_regular",
            password="StrongPassword123!",
            first_name="Олег",
            last_name="Сотрудников",
            email="regular@barkol.ru",
            is_staff=False,
            is_superuser=False,
        )
        self.admin_user = DataBaseUser.objects.create_user(
            username="p0_admin",
            password="StrongPassword123!",
            first_name="Игорь",
            last_name="Админов",
            email="admin@barkol.ru",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.factory = APIRequestFactory()

    def test_serializer_excludes_sensitive_and_privileged_fields(self) -> None:
        """DataBaseUserSerializer не должен содержать пароли, права и служебные поля."""
        data = DataBaseUserSerializer(self.regular_user).data
        forbidden_fields = {
            "password",
            "passphrase",
            "is_superuser",
            "is_staff",
            "groups",
            "user_permissions",
            "personal_groups",
            "ref_key",
            "person_ref_key",
        }
        self.assertTrue(forbidden_fields.isdisjoint(set(data.keys())))
        self.assertIn("username", data)
        self.assertIn("title", data)

    def test_mobile_api_routes_disabled_by_default(self) -> None:
        """Неиспользуемые Android API маршруты возвращают 404 при ENABLE_MOBILE_API=False."""
        self.client.force_login(self.regular_user)
        for path in (
            "/users/api/databaseuser/",
            "/users/api/token/",
            "/api/schema/swagger-ui/",
            "/api/passwords/",
            "/api/finance/",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, f"Ожидался 404 для {path}, получен {response.status_code}")

    def test_pwa_push_endpoint_remains_active(self) -> None:
        """PWA Web Push API (/users/api/push/vapid-key/) остаётся доступным."""
        self.client.force_login(self.regular_user)
        url = reverse("customers_app:api_push_vapid_key")
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 404)

    def test_viewset_denies_regular_user_and_blocks_mutations(self) -> None:
        """Даже при прямом вызове DataBaseUserViewSet запрещает доступ не-админам и любые мутации."""
        list_view = DataBaseUserViewSet.as_view({"get": "list"})
        detail_view = DataBaseUserViewSet.as_view({"get": "retrieve"})

        # 1. Обычный пользователь -> 403 Forbidden
        req_regular = self.factory.get("/users/api/databaseuser/")
        force_authenticate(req_regular, user=self.regular_user)
        resp_regular = list_view(req_regular)
        self.assertEqual(resp_regular.status_code, 403)

        # 2. Администратор -> 200 OK на чтение, но без password/is_superuser
        req_admin = self.factory.get(f"/users/api/databaseuser/{self.regular_user.pk}/")
        force_authenticate(req_admin, user=self.admin_user)
        resp_admin = detail_view(req_admin, pk=self.regular_user.pk)
        self.assertEqual(resp_admin.status_code, 200)
        self.assertNotIn("password", resp_admin.data)
        self.assertNotIn("is_superuser", resp_admin.data)

        # 3. ReadOnlyModelViewSet не поддерживает create/update/destroy
        self.assertFalse(hasattr(DataBaseUserViewSet, "create"))
        self.assertFalse(hasattr(DataBaseUserViewSet, "update"))
        self.assertFalse(hasattr(DataBaseUserViewSet, "partial_update"))
        self.assertFalse(hasattr(DataBaseUserViewSet, "destroy"))
