import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory, SimpleTestCase, override_settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.models import Permission
from customers_app.models import DataBaseUser
from hrdepartment_app.models import OfficialMemo
from hrdepartment_app.views import OfficialMemoDetail


class OfficialMemoDetailViewTest(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        # Create an instance of HttpRequest
        self.factory = RequestFactory()
        # Example object
        view_permission = Permission.objects.get(codename="view_officialmemo")
        self.user = DataBaseUser.objects.create_user(
            username="jacob",
            email="jacob@…",
            password="top_secret",
            first_name="Виталий",
            last_name="Шакиров",
            surname="Рустамович",
            title="Шакиров Виталий Рустамович",
        )
        self.user.user_permissions.add(view_permission)
        kwargs = {
            "person": self.user,
            "period_from": datetime.date(2023, 8, 1),
            "period_for": datetime.date(2023, 8, 1),
            "official_memo_type": "1",
        }
        self.official_memo = OfficialMemo.objects.create(**kwargs)

    def test_context_data(self):
        # Создайте экземпляр запроса GET.
        request = self.factory.get("/detail")

        # Напомним, что промежуточное ПО не поддерживается. Вы можете имитировать
        # авторизованный пользователь, установив request.user вручную.
        request.user = self.user

        # Test OfficialMemoDetail.as_view() as a logged in user.
        response = OfficialMemoDetail.as_view()(request, pk=self.official_memo.id)

        # # Check that user is logged in
        # print(response.context_data)
        # assert str(response.context_data["user"]) == "jacob"
        # assert response.status_code == 200

        # Check csrf_token exist in request
        # self.assertIn("csrf_token", response.context_data)
        self.assertIn("view", response.context_data)

        # Check change history in context
        self.assertIn("change_history", response.context_data)


class MemoNotificationServiceTests(SimpleTestCase):
    """Набор модульных тестов для MemoNotificationService."""

    def test_get_portal_url_default(self):
        """Проверяет получение базового URL портала по умолчанию."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        url = MemoNotificationService.get_portal_url()
        self.assertTrue(url.startswith("http"))

    @override_settings(PORTAL_BASE_URL="https://test.barkol.ru/")
    def test_get_process_url(self):
        """Проверяет генерацию ссылки на карточку процесса без дублирования слэшей."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        url = MemoNotificationService.get_process_url(42)
        self.assertEqual(url, "https://test.barkol.ru/hr/bpmemo/42/update/")

    @patch("django.db.transaction.on_commit")
    def test_dispatch_event_triggers_task(self, mock_on_commit):
        """Проверяет регистрацию отправки события через transaction.on_commit."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_on_commit.side_effect = lambda cb: cb()
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res = MemoNotificationService.dispatch_event(
                process_id=10,
                event_type="APPROVED",
                actor_id=5,
            )
            self.assertTrue(res)
            mock_delay.assert_called_once_with(
                process_id=10,
                event_type="APPROVED",
                actor_id=5,
                extra_context=None,
            )

    def test_cleanup_temp_files_deletes_existing_and_ignores_missing(self):
        """Проверяет удаление временных файлов и корректную обработку несуществующих."""
        import os
        import tempfile
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            temp_path = f.name

        self.assertTrue(os.path.exists(temp_path))
        MemoNotificationService._cleanup_temp_files([temp_path, "/non/existent/path/file.pdf"])
        self.assertFalse(os.path.exists(temp_path))

    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_handle_event_sync_sends_email_and_telegram(self, mock_email, mock_tg):
        """Проверяет отправку уведомлений по почте и Telegram при наличии адресатов."""
        from unittest.mock import MagicMock, patch
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_process = MagicMock()
        mock_process.pk = 15
        mock_process.id = 15
        mock_process.person_agreement.email = "boss@barkol.ru"
        mock_process.person_agreement.telegram_id = "123456"
        mock_process.document.official_memo_type = "1"
        mock_process.document.person.title = "Иванов Иван Иванович"
        mock_process.document.period_from.strftime.return_value = "01.01.2026"
        mock_process.document.period_for.strftime.return_value = "10.01.2026"

        with patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.select_related") as mock_sr:
            mock_sr.return_value.get.return_value = mock_process
            with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=[]):
                res = MemoNotificationService.handle_event_sync(
                    process_id=15,
                    event_type="SUBMITTED",
                    actor_id=1,
                )
                self.assertTrue(res)
                self.assertTrue(mock_email.called)
                self.assertTrue(mock_tg.called)

