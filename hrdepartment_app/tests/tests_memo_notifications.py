# -*- coding: utf-8 -*-
"""Модульные тесты для сервиса MemoNotificationService и точечной адресации служебных заданий."""

import datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from hrdepartment_app.models import ApprovalOficialMemoProcess
from hrdepartment_app.services.memo_notification_service import MemoNotificationService


class MemoNotificationServiceTests(SimpleTestCase):
    """Набор модульных тестов для MemoNotificationService и разделения адресатов."""

    def setUp(self):
        """Очищает кэш перед каждым тестом для изоляции дедупликации."""
        from django.core.cache import cache
        cache.clear()

    def test_get_portal_url_default(self):
        """Проверяет получение базового URL портала по умолчанию."""
        url = MemoNotificationService.get_portal_url()
        self.assertTrue(url.startswith("http"))

    @override_settings(PORTAL_BASE_URL="https://test.barkol.ru/")
    def test_get_process_url(self):
        """Проверяет генерацию ссылки на карточку процесса без дублирования слэшей."""
        url = MemoNotificationService.get_process_url(42)
        self.assertEqual(url, "https://test.barkol.ru/hr/bpmemo/42/update/")

    @patch("django.db.transaction.on_commit")
    def test_dispatch_event_triggers_task(self, mock_on_commit):
        """Проверяет регистрацию отправки события через transaction.on_commit."""
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

    def _create_mock_order_process(self):
        """Вспомогательный метод для создания мока процесса с изданным приказом."""
        process = MagicMock()
        process.pk = 100
        process.order.document_number = "105-ОК"
        process.order.document_date = datetime.date(2026, 10, 1)
        process.document.person.email = "ivanov@barkol.ru"
        process.document.person.gender = "male"
        process.document.person.telegram_id = "777888"
        process.document.person.__str__.return_value = "Иванов И.И."
        process.document.type_trip = "2"  # СПК (летный состав)
        process.document.period_from = datetime.date(2026, 10, 10)
        process.document.period_for = datetime.date(2026, 10, 15)
        process.document.purpose_trip = "Выполнение лесоавиационных работ"
        process.document.place_production_activity.all.return_value = []
        process.person_executor.email = "petrov@barkol.ru"
        process.person_executor.__str__.return_value = "Петров П.П."
        process.person_distributor = None
        process.accommodation = "1"
        return process

    @patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.filter")
    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_notify_order_issued_target_mode_employee(self, mock_email, mock_tg, mock_pref, mock_filter):
        """Проверяет, что при target_mode='employee' письмо уходит строго командируемому и шлется TG."""
        mock_filter.return_value.update.return_value = 1
        process = self._create_mock_order_process()
        with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=(None, None)):
            res = MemoNotificationService._notify_order_issued(process, extra_context={"target_mode": "employee"})
            self.assertTrue(res)
            mock_email.assert_called_once()
            call_kwargs = mock_email.call_args[1]
            self.assertEqual(call_kwargs["recipient_list"], ["ivanov@barkol.ru"])
            self.assertTrue(mock_tg.called)

    @patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.filter")
    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_notify_order_issued_target_mode_executor(self, mock_email, mock_tg, mock_pref, mock_filter):
        """Проверяет, что при target_mode='executor' письмо уходит строго исполнителю, а TG сотруднику не шлется."""
        mock_filter.return_value.update.return_value = 1
        process = self._create_mock_order_process()
        with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=(None, None)):
            res = MemoNotificationService._notify_order_issued(process, extra_context={"target_mode": "executor"})
            self.assertTrue(res)
            mock_email.assert_called_once()
            call_kwargs = mock_email.call_args[1]
            self.assertEqual(call_kwargs["recipient_list"], ["petrov@barkol.ru"])
            self.assertFalse(mock_tg.called)

    @patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.filter")
    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_notify_order_issued_target_mode_flight_common(self, mock_email, mock_tg, mock_pref, mock_filter):
        """Проверяет, что при target_mode='flight_common' письмо уходит строго на общую почту летной службы."""
        mock_filter.return_value.update.return_value = 1
        process = self._create_mock_order_process()
        with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=(None, None)):
            res = MemoNotificationService._notify_order_issued(process, extra_context={"target_mode": "flight_common"})
            self.assertTrue(res)
            mock_email.assert_called_once()
            call_kwargs = mock_email.call_args[1]
            self.assertEqual(call_kwargs["recipient_list"], ["fly@barkol.ru"])
            self.assertFalse(mock_tg.called)

    @patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.filter")
    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_notify_order_issued_broadcast_default(self, mock_email, mock_tg, mock_pref, mock_filter):
        """Проверяет, что при штатном первичном издании приказа (target_mode=None) письмо уходит всем участникам."""
        mock_filter.return_value.update.return_value = 1
        process = self._create_mock_order_process()
        with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=(None, None)):
            res = MemoNotificationService._notify_order_issued(process, extra_context=None)
            self.assertTrue(res)
            mock_email.assert_called_once()
            call_kwargs = mock_email.call_args[1]
            self.assertEqual(call_kwargs["recipient_list"], ["ivanov@barkol.ru", "petrov@barkol.ru", "fly@barkol.ru"])
            self.assertTrue(mock_tg.called)

    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.dispatch_event")
    def test_send_mail_triggers_dispatch_with_target_mode(self, mock_dispatch):
        """Проверяет, что вызов send_mail передает корректный target_mode в extra_context."""
        mock_process = MagicMock()
        mock_process.pk = 55
        mock_process.process_accepted = True
        mock_process.document.person.email = "ivanov@barkol.ru"
        mock_process.person_executor.email = "petrov@barkol.ru"

        # trigger = 1: Повторное уведомление
        success, info = ApprovalOficialMemoProcess.send_mail(mock_process, title="Повторное уведомление", trigger=1)
        self.assertTrue(success)
        mock_dispatch.assert_called_with(
            55,
            "ORDER_ISSUED",
            extra_context={"target_mode": "employee"},
            force=True,
        )

        # trigger = 2: Письмо исполнителю
        success, info = ApprovalOficialMemoProcess.send_mail(mock_process, title="Письмо исполнителю", trigger=2)
        self.assertTrue(success)
        mock_dispatch.assert_called_with(
            55,
            "ORDER_ISSUED",
            extra_context={"target_mode": "executor"},
            force=True,
        )

        # trigger = 3: Письмо на общую почту
        success, info = ApprovalOficialMemoProcess.send_mail(mock_process, title="Письмо на общую почту", trigger=3)
        self.assertTrue(success)
        mock_dispatch.assert_called_with(
            55,
            "ORDER_ISSUED",
            extra_context={"target_mode": "flight_common"},
            force=True,
        )
