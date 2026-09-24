# -*- coding: utf-8 -*-
"""Модульные тесты для приложения telegram_app и сервиса UniversalTelegramService."""

from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings

from telegram_app.services.telegram_service import UniversalTelegramService
from telegram_app.tasks import send_universal_telegram_task, send_universal_telegram_document_task


class UniversalTelegramServiceTests(SimpleTestCase):
    """Набор тестов для проверки универсального сервиса Telegram."""

    def test_build_inline_keyboard(self):
        """Проверяет корректное формирование структуры InlineKeyboardMarkup."""
        rows = [
            [
                {"text": "✅ Согласовать", "callback_data": "bpmemo_approve:1"},
                {"text": "❌ Отклонить", "callback_data": "bpmemo_reject:1"},
            ],
            [
                {"text": "📄 Открыть", "url": "https://corp.barkol.ru/hr/bpmemo/1/update/"},
            ],
        ]
        result = UniversalTelegramService.build_inline_keyboard(rows)
        self.assertIn("inline_keyboard", result)
        self.assertEqual(len(result["inline_keyboard"]), 2)
        self.assertEqual(result["inline_keyboard"][0][0]["text"], "✅ Согласовать")
        self.assertEqual(result["inline_keyboard"][1][0]["url"], "https://corp.barkol.ru/hr/bpmemo/1/update/")

    @override_settings(TELEGRAM_PROXY="http://127.0.0.1:8118")
    def test_get_proxies_configured(self):
        """Проверяет получение конфигурации прокси при установленном TELEGRAM_PROXY."""
        proxies = UniversalTelegramService.get_proxies()
        self.assertIsNotNone(proxies)
        self.assertEqual(proxies.get("http"), "http://127.0.0.1:8118")
        self.assertEqual(proxies.get("https"), "http://127.0.0.1:8118")

    @override_settings(TELEGRAM_PROXY="", WEATHER_PROXY="")
    def test_get_proxies_empty(self):
        """Проверяет возврат None при отсутствии настроек прокси."""
        proxies = UniversalTelegramService.get_proxies()
        self.assertIsNone(proxies)

    @override_settings(TELEGRAM_TOKEN="test_token_123")
    @patch("requests.post")
    def test_send_message_sync_success(self, mock_post):
        """Проверяет успешную синхронную отправку сообщения через Telegram API."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        success, err = UniversalTelegramService.send_message_sync(
            chat_id="123456789",
            text="Тестовое уведомление",
        )
        self.assertTrue(success)
        self.assertIsNone(err)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["chat_id"], "123456789")
        self.assertEqual(kwargs["json"]["text"], "Тестовое уведомление")

    @override_settings(TELEGRAM_TOKEN="test_token_123")
    @patch("requests.post")
    def test_send_message_sync_api_error(self, mock_post):
        """Проверяет обработку ошибки API (HTTP 400)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"error": "Chat not found"}'
        mock_post.return_value = mock_resp

        success, err = UniversalTelegramService.send_message_sync(
            chat_id="00000",
            text="Ошибка",
        )
        self.assertFalse(success)
        self.assertIn("HTTP 400", err)

    @patch("telegram_app.tasks.send_universal_telegram_task.delay")
    def test_send_message_async(self, mock_delay):
        """Проверяет асинхронную постановку задачи в очередь Celery."""
        result = UniversalTelegramService.send_message_async(
            chat_id="987654",
            text="Асинхронный тест",
        )
        self.assertTrue(result)
        mock_delay.assert_called_once_with(
            chat_id="987654",
            text="Асинхронный тест",
            parse_mode="HTML",
            reply_markup=None,
            disable_web_page_preview=False,
        )

    def test_send_message_async_empty_chat_id(self):
        """Проверяет возврат False при пустом chat_id."""
        result = UniversalTelegramService.send_message_async(
            chat_id="",
            text="Тест",
        )
        self.assertFalse(result)

    @override_settings(TELEGRAM_TOKEN="test_token_123")
    @patch("telegram_app.services.telegram_service.UniversalTelegramService.send_message_sync")
    def test_send_universal_telegram_task_execution(self, mock_send_sync):
        """Проверяет исполнение Celery-задачи отправки."""
        mock_send_sync.return_value = (True, None)

        res = send_universal_telegram_task(
            chat_id="112233",
            text="Тест через Celery задачу",
        )
        self.assertTrue(res)
        mock_send_sync.assert_called_once()
