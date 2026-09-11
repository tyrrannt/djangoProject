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
        request.body = b'{"action": "delete_user", "login_name": "i.ivanov", "domain_name": "barkol.ru", "delete_external": true}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once_with(
            login_name="i.ivanov",
            domain_name="barkol.ru",
            delete_external=True,
        )

    @patch("mailbox_app.services.kerio.service.KerioAdminService.audit_mailboxes_sync")
    def test_kerio_action_api_audit_sync(self, mock_audit: MagicMock) -> None:
        """Тест AJAX API аудита синхронизации Kerio Connect и ISPmanager."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_audit.return_value = {
            "success": True,
            "domain": "barkol.ru",
            "summary": {"total_kerio": 2, "total_isp": 2, "synced_count": 2},
            "users": [],
            "orphans": [],
        }

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "audit_sync", "domain_name": "barkol.ru"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_audit.assert_called_once_with(domain_name="barkol.ru")

    @patch("mailbox_app.services.kerio.service.KerioAdminService.create_external_mailbox_for_user")
    def test_kerio_action_api_create_isp_mailbox(self, mock_create: MagicMock) -> None:
        """Тест AJAX API создания ящика в ISPmanager."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_create.return_value = {"success": True, "provider": "ispmanager", "email": "i.ivanov@barkol.ru"}

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "create_isp_mailbox", "login_name": "i.ivanov", "domain_name": "barkol.ru", "password": "SecretPassword123!"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_create.assert_called_once_with(
            login_name="i.ivanov",
            domain_name="barkol.ru",
            password="SecretPassword123!",
            full_name=None,
            quota_mb=None,
        )

    def test_kerio_provision_form_with_portal_integration_switches(self) -> None:
        """Тест валидации формы создания с переключателями сохранения в модель пользователя и 1С."""
        from mailbox_app.forms import KerioUserProvisionForm

        with patch("django.contrib.auth.get_user_model") as mock_user_model:
            mock_user_model.return_value.objects.filter.return_value.order_by.return_value = []
            form_data = {
                "login_name": "s.petrov",
                "domain_name": "barkol.ru",
                "password": "Password12345!",
                "confirm_password": "Password12345!",
                "full_name": "Петров Сергей",
                "save_email_to_user": True,
                "sync_1c": True,
            }
            form = KerioUserProvisionForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Ошибки формы: {form.errors}")
            self.assertTrue(form.cleaned_data["save_email_to_user"])
            self.assertTrue(form.cleaned_data["sync_1c"])

    @patch("mailbox_app.views.render")
    def test_kerio_user_create_view_get_with_user_param(self, mock_render: MagicMock) -> None:
        """Тест предвыбора сотрудника в KerioAdminUserCreateView при GET-запросе с ?user=<id>."""
        from mailbox_app.views import KerioAdminUserCreateView

        view = KerioAdminUserCreateView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.GET = {"user": "198"}

        mock_user = MagicMock()
        mock_user.pk = 198
        mock_user.is_active = True

        with patch("django.contrib.auth.get_user_model") as mock_user_model:
            mock_user_model.return_value.objects.filter.return_value.first.return_value = mock_user
            mock_user_model.return_value.objects.filter.return_value.select_related.return_value.only.return_value = []
            mock_user_model.return_value.objects.filter.return_value.order_by.return_value = []
            with patch.object(view, "get_context_data", return_value={}):
                view.get(request)
                self.assertTrue(mock_render.called)
                context = mock_render.call_args[0][2]
                self.assertEqual(context["form"].initial.get("link_django_user"), 198)

    @patch("mailbox_app.views.messages")
    @patch("mailbox_app.views.redirect")
    @patch("mailbox_app.services.kerio.service.KerioAdminService.provision_full_mailbox")
    def test_kerio_user_create_view_post_with_portal_and_1c_sync(
        self, mock_provision: MagicMock, mock_redirect: MagicMock, mock_messages: MagicMock
    ) -> None:
        """Тест отправки формы создания ящика с флагами save_email_to_user и sync_1c."""
        from mailbox_app.views import KerioAdminUserCreateView

        mock_provision.return_value = {
            "success": True,
            "email": "s.petrov@barkol.ru",
            "steps": {"sync_1c": {"status": "ok", "message": "Email записан в 1С"}},
        }

        view = KerioAdminUserCreateView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.POST = {
            "login_name": "s.petrov",
            "domain_name": "barkol.ru",
            "password": "Password12345!",
            "confirm_password": "Password12345!",
            "full_name": "Петров Сергей",
            "save_email_to_user": "on",
            "sync_1c": "on",
        }

        with patch("django.contrib.auth.get_user_model") as mock_user_model:
            mock_user_model.return_value.objects.filter.return_value.order_by.return_value = []
            with patch.object(view, "get_context_data", return_value={}):
                view.post(request)
                mock_provision.assert_called_once()
                call_kwargs = mock_provision.call_args[1]
                self.assertTrue(call_kwargs["save_email_to_user"])
                self.assertTrue(call_kwargs["sync_1c"])

    @patch("mailbox_app.services.kerio.service.KerioAdminService.sync_user_email_to_portal_and_1c")
    def test_kerio_action_api_sync_1c(self, mock_sync_1c: MagicMock) -> None:
        """Тест AJAX API принудительной синхронизации email с моделью пользователя и 1С (ЗУП)."""
        from mailbox_app.views import KerioAdminActionAPIView

        mock_sync_1c.return_value = {
            "success": True,
            "message": "Email успешно синхронизирован с 1С и порталом!",
            "email": "i.ivanov@barkol.ru",
            "one_c_synced": True,
        }

        view = KerioAdminActionAPIView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.content_type = "application/json"
        request.body = b'{"action": "sync_1c", "login_name": "i.ivanov", "domain_name": "barkol.ru"}'

        response = view.post(request)
        self.assertEqual(response.status_code, 200)
        mock_sync_1c.assert_called_once_with(
            login_name="i.ivanov",
            domain_name="barkol.ru",
            email=None,
        )

    def test_kerio_edit_form_with_sync_1c(self) -> None:
        """Тест формы редактирования с переключателем синхронизации с 1С."""
        from mailbox_app.forms import KerioUserEditForm

        form_data = {
            "full_name": "Петров Петр Петрович",
            "description": "Инженер",
            "is_enabled": True,
            "sync_1c": True,
        }
        form = KerioUserEditForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["sync_1c"])

    @patch("mailbox_app.views.render")
    @patch("mailbox_app.views.get_user_model")
    @patch("mailbox_app.views.KerioAdminService")
    def test_kerio_users_list_view_alphabetical_sorting(
        self,
        mock_service_cls: MagicMock,
        mock_user_model: MagicMock,
        mock_render: MagicMock,
    ) -> None:
        """Тест сортировки пользователей по алфавиту в представлении KerioAdminUsersListView."""
        from mailbox_app.views import KerioAdminUsersListView

        mock_service = mock_service_cls.return_value
        mock_service.get_domains_list.return_value = [{"name": "barkol.ru"}]
        mock_service.get_users_list.return_value = {
            "list": [
                {"id": "u3", "loginName": "z.zaytsev", "fullName": "Яковлев Яков", "isEnabled": True, "email": "z.zaytsev@barkol.ru"},
                {"id": "u1", "loginName": "b.borisov", "fullName": "Алексеев Алексей", "isEnabled": True, "email": "b.borisov@barkol.ru"},
                {"id": "u2", "loginName": "a.andreev", "fullName": "Борисов Борис", "isEnabled": True, "email": "a.andreev@barkol.ru"},
            ],
            "totalItems": 3,
        }
        mock_user_model.return_value.objects.filter.return_value = []
        mock_render.return_value = MagicMock(status_code=200)

        view = KerioAdminUsersListView()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_superuser = True
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        # Проверяем, что в context передан отсортированный список пользователей
        render_call_args = mock_render.call_args
        context = render_call_args[0][2]
        sorted_users = context["users"]
        self.assertEqual(sorted_users[0]["fullName"], "Алексеев Алексей")
        self.assertEqual(sorted_users[1]["fullName"], "Борисов Борис")
        self.assertEqual(sorted_users[2]["fullName"], "Яковлев Яков")

    @patch("mailbox_app.views.MailboxDownloadAttachmentsZipView.get_imap_service")
    @patch("mailbox_app.views.MailboxDownloadAttachmentsZipView.get_account")
    def test_download_attachments_zip_view(
        self,
        mock_get_account: MagicMock,
        mock_get_imap: MagicMock,
    ) -> None:
        """Тест формирования ZIP-архива вложений в представлении MailboxDownloadAttachmentsZipView."""
        import io
        import zipfile
        from mailbox_app.views import MailboxDownloadAttachmentsZipView

        mock_account = MagicMock()
        mock_get_account.return_value = mock_account

        mock_imap_svc = MagicMock()
        mock_get_imap.return_value.__enter__.return_value = mock_imap_svc

        # Настраиваем ответ get_message_detail и download_attachment
        mock_imap_svc.get_message_detail.return_value = {
            "uid": 105,
            "subject": "Документы по договору",
            "attachments": [
                {"part_index": 1, "filename": "договор.pdf"},
                {"part_index": 2, "filename": "акт.xlsx"},
            ],
        }
        mock_imap_svc.download_attachment.side_effect = [
            ("договор.pdf", "application/pdf", b"PDF_CONTENT_DATA"),
            ("акт.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"EXCEL_CONTENT_DATA"),
        ]

        view = MailboxDownloadAttachmentsZipView()
        request = MagicMock()
        request.user.is_authenticated = True

        response = view.get(request, folder="INBOX", uid=105)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment;", response["Content-Disposition"])

        # Проверяем распаковку сгенерированного ZIP-архива
        zip_buf = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            file_list = zf.namelist()
            self.assertIn("договор.pdf", file_list)
            self.assertIn("акт.xlsx", file_list)
            self.assertEqual(zf.read("договор.pdf"), b"PDF_CONTENT_DATA")
            self.assertEqual(zf.read("акт.xlsx"), b"EXCEL_CONTENT_DATA")


if __name__ == "__main__":
    unittest.main()

