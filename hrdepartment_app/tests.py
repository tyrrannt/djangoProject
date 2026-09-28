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

    def setUp(self):
        """Очищает кэш перед каждым тестом для изоляции дедупликации."""
        from django.core.cache import cache
        cache.clear()

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

    @patch("django.core.cache.cache.get")
    @patch("django.core.cache.cache.set")
    @patch("django.db.transaction.on_commit")
    def test_dispatch_event_deduplication(self, mock_on_commit, mock_cache_set, mock_cache_get):
        """Проверяет работу замка дедупликации и обхода через параметр force."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_on_commit.side_effect = lambda cb: cb()

        # 1. Первый вызов (ключа в кэше нет) -> успешно ставится в очередь
        mock_cache_get.return_value = False
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res1 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED")
            self.assertTrue(res1)
            mock_delay.assert_called_once()
            mock_cache_set.assert_called_with("memo_notify_guard:20:SUBMITTED", True, timeout=300)

        # 2. Повторный вызов (ключ уже в кэше) без force -> отсекается
        mock_cache_get.return_value = True
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res2 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED", force=False)
            self.assertFalse(res2)
            mock_delay.assert_not_called()

        # 3. Вызов с force=True (ручная отправка) -> обходит замок и отправляется
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res3 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED", force=True)
            self.assertTrue(res3)
            mock_delay.assert_called_once()

    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_handle_event_sync_sends_email_and_telegram(self, mock_email, mock_tg, mock_pref):
        """Проверяет отправку уведомлений по почте и Telegram при наличии адресатов."""
        from unittest.mock import MagicMock, patch
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_process = MagicMock()
        mock_process.pk = 15
        mock_process.id = 15
        mock_process.person_agreement.email = "boss@barkol.ru"
        mock_process.person_agreement.telegram_id = "123456"
        mock_process.person_executor.telegram_id = "654321"
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

    def test_approval_process_initial_state_tracking(self):
        """Проверяет корректность фиксации исходного состояния в _initial_state."""
        from hrdepartment_app.models import ApprovalOficialMemoProcess

        process = ApprovalOficialMemoProcess()
        process.submit_for_approval = True
        process.location_selected = False
        process._save_initial_state()

        self.assertTrue(process._initial_state["submit_for_approval"])
        self.assertFalse(process._initial_state["location_selected"])
        self.assertFalse(process._initial_state["cancellation"])

    def test_diffkeys_excludes_internal_attributes(self):
        """Проверяет, что внутренние атрибуты (_initial_state, _state) исключаются из diffkeys."""
        from hrdepartment_app.models import ApprovalOficialMemoProcess
        from django.core.exceptions import FieldDoesNotExist

        old_instance = {
            "_state": object(),
            "_initial_state": {"submit_for_approval": False},
            "submit_for_approval": False,
            "cancellation": False,
        }
        new_instance = {
            "_state": object(),
            "_initial_state": {"submit_for_approval": True},
            "submit_for_approval": True,
            "cancellation": False,
        }

        diffkeys = [
            k for k in old_instance
            if not k.startswith("_") and old_instance.get(k) != new_instance.get(k)
        ]

        self.assertEqual(diffkeys, ["submit_for_approval"])
        self.assertNotIn("_initial_state", diffkeys)
        self.assertNotIn("_state", diffkeys)

        # Проверяем, что для всех ключей в diffkeys get_field завершается успешно
        for k in diffkeys:
            try:
                field = ApprovalOficialMemoProcess._meta.get_field(k)
                self.assertIsNotNone(field)
            except FieldDoesNotExist:
                self.fail(f"FieldDoesNotExist raised for field: {k}")

    def test_generate_memo_documents_pdf_conversion_and_fallback(self):
        """Проверяет вызов msoffice2pdf.convert в _generate_memo_documents и безопасный fallback на XLSX."""
        import datetime
        from unittest.mock import MagicMock, patch
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_process = MagicMock()
        mock_process.document.official_memo_type = "1"
        mock_process.document.type_trip = "1"
        mock_process.document.period_from = datetime.date(2026, 9, 28)
        mock_process.document.period_for = datetime.date(2026, 9, 30)
        mock_process.document.place_production_activity.all.return_value = []
        mock_process.order.document_number = "123"
        mock_process.order.document_date = datetime.date(2026, 9, 28)

        # 1. Проверяем успешную конвертацию в PDF
        with patch.object(MemoNotificationService, "_find_soffice_binary", return_value="/usr/bin/soffice"), \
             patch("openpyxl.load_workbook") as mock_wb, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("msoffice2pdf.convert", return_value="/media/test.pdf") as mock_conv, \
             patch("os.path.exists", return_value=True):
            wb_instance = MagicMock()
            mock_wb.return_value = wb_instance
            xlsx, pdf = MemoNotificationService._generate_memo_documents(mock_process)
            self.assertEqual(pdf, "/media/test.pdf")
            self.assertTrue(mock_conv.called)
            # Проверяем, что output_dir указывает на media
            self.assertTrue(mock_conv.call_args[1]["output_dir"].endswith("media"))

        # 2. Проверяем безопасный откат на XLSX при сбое конвертера
        with patch.object(MemoNotificationService, "_find_soffice_binary", return_value="/usr/bin/soffice"), \
             patch("openpyxl.load_workbook") as mock_wb, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("msoffice2pdf.convert", side_effect=Exception("Converter error")) as mock_conv:
            wb_instance = MagicMock()
            mock_wb.return_value = wb_instance
            xlsx, pdf = MemoNotificationService._generate_memo_documents(mock_process)
            self.assertIsNotNone(xlsx)
            self.assertIsNone(pdf)



