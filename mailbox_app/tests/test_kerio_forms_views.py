"""Unit-тесты для форм и представлений администрирования Kerio Connect."""

import unittest
from unittest.mock import MagicMock, patch


class KerioAdminFormsViewsTestCase(unittest.TestCase):
    """Тестирование форм и представлений администрирования Kerio Connect."""

    def test_kerio_provision_form_validation(self) -> None:
        """Тест валидации формы создания пользователя Kerio."""
        from mailbox_app.forms import KerioUserProvisionForm

        with patch("django.contrib.auth.get_user_model") as mock_user_model:
            mock_user_model.return_value.objects.filter.return_value.order_by.return_value = []
            form_data = {
                "login_name": "i.ivanov",
                "domain_name": "barkol.ru",
                "password": "SecretPassword123!",
                "confirm_password": "SecretPassword123!",
                "full_name": "Иванов Иван Иванович",
                "description": "Пилот Ми-8",
                "quota_mb": 5120,
                "configure_pop3_download": True,
                "external_pop3_host": "mail.barkol.ru",
                "external_pop3_port": 995,
                "external_pop3_ssl": True,
                "external_leave_messages": False,
                "create_django_account": True,
            }
            form = KerioUserProvisionForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Ошибки формы: {form.errors}")
            self.assertEqual(form.cleaned_data["login_name"], "i.ivanov")

    def test_kerio_provision_form_password_mismatch(self) -> None:
        """Тест обнаружения несовпадения паролей в форме создания."""
        from mailbox_app.forms import KerioUserProvisionForm

        with patch("django.contrib.auth.get_user_model") as mock_user_model:
            mock_user_model.return_value.objects.filter.return_value.order_by.return_value = []
            form_data = {
                "login_name": "i.ivanov",
                "domain_name": "barkol.ru",
                "password": "Password123",
                "confirm_password": "DifferentPassword456",
            }
            form = KerioUserProvisionForm(data=form_data)
            self.assertFalse(form.is_valid())
            self.assertIn("confirm_password", form.errors)

    def test_kerio_edit_form_validation(self) -> None:
        """Тест валидации формы редактирования параметров пользователя Kerio."""
        from mailbox_app.forms import KerioUserEditForm

        form_data = {
            "full_name": "Петров Петр Петрович",
            "description": "Инженер по АиРЭО",
            "quota_mb": 10240,
            "is_enabled": True,
        }
        form = KerioUserEditForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Ошибки: {form.errors}")
        self.assertEqual(form.cleaned_data["quota_mb"], 10240)

    def test_kerio_password_reset_form(self) -> None:
        """Тест формы смены пароля."""
        from mailbox_app.forms import KerioUserPasswordResetForm

        form_data = {
            "new_password": "NewSecretPassword2026!",
            "confirm_password": "NewSecretPassword2026!",
        }
        form = KerioUserPasswordResetForm(data=form_data)
        self.assertTrue(form.is_valid())

        form_data_invalid = {
            "new_password": "NewSecretPassword2026!",
            "confirm_password": "WrongPassword",
        }
        form_invalid = KerioUserPasswordResetForm(data=form_data_invalid)
        self.assertFalse(form_invalid.is_valid())

    @patch("mailbox_app.services.kerio.service.KerioAdminService.test_admin_connection")
    def test_kerio_action_api_test_connection(self, mock_test_conn: MagicMock) -> None:
        """Тест AJAX API проверки связи с Kerio Connect."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_test_conn.return_value = {
            "success": True,
            "status": "online",
            "domains": ["barkol.ru"],
            "domains_count": 1,
        }

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "test_connection"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)

    @patch("mailbox_app.services.kerio.service.KerioAdminService.update_user_password")
    def test_kerio_action_api_reset_password(self, mock_reset_pwd: MagicMock) -> None:
        """Тест AJAX API сброса пароля пользователя."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_reset_pwd.return_value = {"login": "i.ivanov", "success": True}

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "reset_password", "login_name": "i.ivanov", "new_password": "NewPassword123!", "domain_name": "barkol.ru"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_reset_pwd.assert_called_once_with(
            login_name="i.ivanov",
            new_password="NewPassword123!",
            domain_name="barkol.ru",
        )

    @patch("mailbox_app.services.kerio.service.KerioAdminService.toggle_user_active")
    def test_kerio_action_api_toggle_active(self, mock_toggle: MagicMock) -> None:
        """Тест AJAX API переключения активности пользователя."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_toggle.return_value = {"login": "i.ivanov", "is_enabled": False, "success": True}

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "toggle_active", "login_name": "i.ivanov", "is_enabled": false, "domain_name": "barkol.ru"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_toggle.assert_called_once_with(
            login_name="i.ivanov",
            is_enabled=False,
            domain_name="barkol.ru",
        )

    @patch("mailbox_app.services.kerio.service.KerioAdminService.delete_user")
    def test_kerio_action_api_delete_user(self, mock_delete: MagicMock) -> None:
        """Тест AJAX API удаления пользователя."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_delete.return_value = {"login": "i.ivanov", "deleted": True, "success": True}

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "delete_user", "login_name": "i.ivanov", "domain_name": "barkol.ru"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once_with(
            login_name="i.ivanov",
            domain_name="barkol.ru",
        )


if __name__ == "__main__":
    unittest.main()
