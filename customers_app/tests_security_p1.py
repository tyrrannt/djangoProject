# -*- coding: utf-8 -*-
"""Модульные тесты устранения уязвимостей P1 (CSRF, Auth, Open Redirect, QR-токен)."""

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from customers_app.models import DataBaseUser


class SecurityP1Tests(TestCase):
    """Проверяет защиту от CSRF, Open Redirect и неавторизованного доступа."""

    def setUp(self) -> None:
        """Создаёт активного и неактивного тестовых пользователей."""
        self.user = DataBaseUser.objects.create_user(
            username="p1_user",
            password="StrongPassword123!",
            first_name="Антон",
            last_name="Проверкин",
            email="p1_user@barkol.ru",
            is_active=True,
            is_superuser=True,
        )
        self.inactive_user = DataBaseUser.objects.create_user(
            username="p1_inactive",
            password="StrongPassword123!",
            first_name="Борис",
            last_name="Уволенный",
            email="p1_inactive@barkol.ru",
            is_active=False,
        )
        self.client = Client()
        self.csrf_client = Client(enforce_csrf_checks=True)
        cache.clear()

    def test_auth_with_token_blocks_open_redirect(self) -> None:
        """Внешний URL в параметре next сбрасывается на корень сайта (защита от Open Redirect)."""
        token = "safe-test-token-123"
        cache.set(f"qr_auth_token:{token}", self.user.pk, timeout=30)

        url = reverse("customers_app:auth_with_token")
        response = self.client.get(url, {"token": token, "next": "https://evil.example.com/phish"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        # Токен одноразовый и должен быть удалён из кэша
        self.assertIsNone(cache.get(f"qr_auth_token:{token}"))

    def test_auth_with_token_allows_safe_internal_next(self) -> None:
        """Корректный внутренний путь в next сохраняется при входе по QR-токену."""
        token = "safe-test-token-456"
        cache.set(f"qr_auth_token:{token}", self.user.pk, timeout=30)

        url = reverse("customers_app:auth_with_token")
        target_path = f"/users/profile/{self.user.pk}/"
        response = self.client.get(url, {"token": token, "next": target_path})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], target_path)

    def test_auth_with_token_rejects_inactive_user_and_unprefixed_key(self) -> None:
        """Неактивный пользователь и ключ без префикса qr_auth_token не могут авторизоваться."""
        url = reverse("customers_app:auth_with_token")

        # 1. Ключ без префикса игнорируется
        cache.set("raw-token-999", self.user.pk, timeout=30)
        resp_raw = self.client.get(url, {"token": "raw-token-999", "next": "/"})
        self.assertEqual(resp_raw.status_code, 302)
        self.assertIn("/users/login/", resp_raw["Location"])

        # 2. Неактивный пользователь отклоняется
        cache.set("qr_auth_token:inactive-tok", self.inactive_user.pk, timeout=30)
        resp_inactive = self.client.get(url, {"token": "inactive-tok", "next": "/"})
        self.assertEqual(resp_inactive.status_code, 302)
        self.assertIn("/users/login/", resp_inactive["Location"])

    def test_anonymous_blocked_on_stats_leaderboard_and_outfit_cards(self) -> None:
        """Анонимные запросы к save_stats, get_leaderboard и filter_outfit_cards перенаправляются на вход."""
        for url_name, method in (
            ("customers_app:save_stats", "post"),
            ("customers_app:get_leaderboard", "get"),
            ("hrdepartment_app:filter_outfit_cards", "post"),
        ):
            url = reverse(url_name)
            resp = getattr(self.client, method)(url)
            self.assertEqual(resp.status_code, 302, f"Ожидался 302 для {url_name}")
            self.assertIn("/users/login/", resp["Location"])

    def test_csrf_enforced_on_previously_exempt_endpoints(self) -> None:
        """POST-запросы без CSRF-токена на ранее открытые эндпоинты отклоняются с кодом 403."""
        self.csrf_client.force_login(self.user)
        for url in (
            reverse("customers_app:save_stats"),
            reverse("hrdepartment_app:filter_outfit_cards"),
            "/flight/api/assign/",
            "/flight/api/resolve-conflict/",
            "/flight/api/remove/",
            "/flight/api/crew/batch-swap-aircraft/",
        ):
            resp = self.csrf_client.post(url, data="{}", content_type="application/json")
            self.assertEqual(resp.status_code, 403, f"Ожидался 403 CSRF для {url}, получен {resp.status_code}")
