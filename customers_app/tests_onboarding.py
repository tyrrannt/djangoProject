# -*- coding: utf-8 -*-
"""Модульные тесты интерактивной ознакомительной экскурсии по порталу (Onboarding Tour)."""

from django.test import Client, TestCase
from django.urls import reverse

from customers_app.models import DataBaseUser


class OnboardingTourTests(TestCase):
    """Тесты модели и API-эндпоинтов ознакомительной экскурсии по порталу."""

    def setUp(self) -> None:
        """Создаёт тестового сотрудника для проверки статуса и API экскурсии."""
        self.user = DataBaseUser.objects.create_user(
            username="tour_test_user",
            password="StrongPassword123!",
            first_name="Иван",
            last_name="Петров",
            email="tour_test@barkol.ru",
        )
        self.client = Client()
        self.complete_url = reverse("customers_app:onboarding_complete")
        self.reset_url = reverse("customers_app:onboarding_reset")

    def test_default_onboarding_flags(self) -> None:
        """Новый пользователь по умолчанию не проходил ознакомительную экскурсию."""
        self.assertFalse(self.user.onboarding_completed)
        self.assertIsNone(self.user.onboarding_completed_at)

    def test_complete_endpoint_marks_user_completed(self) -> None:
        """POST на onboarding_complete сохраняет отметку и дату прохождения в БД."""
        self.client.force_login(self.user)
        response = self.client.post(self.complete_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["onboarding_completed"])
        self.assertIn("completed_at", payload)

        self.user.refresh_from_db()
        self.assertTrue(self.user.onboarding_completed)
        self.assertIsNotNone(self.user.onboarding_completed_at)

    def test_reset_endpoint_clears_onboarding_status(self) -> None:
        """POST на onboarding_reset сбрасывает отметку прохождения в БД."""
        self.client.force_login(self.user)
        self.client.post(self.complete_url)

        response = self.client.post(self.reset_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["onboarding_completed"])

        self.user.refresh_from_db()
        self.assertFalse(self.user.onboarding_completed)
        self.assertIsNone(self.user.onboarding_completed_at)

    def test_complete_endpoint_requires_authentication(self) -> None:
        """Анонимный запрос к onboarding_complete перенаправляется на вход."""
        response = self.client.post(self.complete_url)
        self.assertEqual(response.status_code, 302)

    def test_complete_endpoint_rejects_get(self) -> None:
        """GET-запрос к onboarding_complete отклоняется кодом 405 Method Not Allowed."""
        self.client.force_login(self.user)
        response = self.client.get(self.complete_url)
        self.assertEqual(response.status_code, 405)
