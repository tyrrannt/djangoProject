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
    @patch.object(UniversalTelegramService, "is_proxy_alive", return_value=True)
    def test_get_proxies_configured(self, mock_alive):
        """Проверяет получение конфигурации прокси при установленном и доступном TELEGRAM_PROXY."""
        proxies = UniversalTelegramService.get_proxies()
        self.assertIsNotNone(proxies)
        self.assertEqual(proxies.get("http"), "http://127.0.0.1:8118")
        self.assertEqual(proxies.get("https"), "http://127.0.0.1:8118")

    @override_settings(TELEGRAM_PROXY="http://127.0.0.1:8118")
    @patch.object(UniversalTelegramService, "is_proxy_alive", return_value=False)
    def test_get_proxies_unreachable_fallback(self, mock_alive):
        """Проверяет автоматический переход на прямое соединение (None), если прокси недоступен."""
        proxies = UniversalTelegramService.get_proxies()
        self.assertIsNone(proxies)

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


from django.test import TestCase
from customers_app.models import DataBaseUser
from tasks_app.models import Task, TaskStatus
from telegram_app.models import ChatID
from telegram_app.bot.keyboards import (
    get_main_menu,
    get_tasks_filter_keyboard,
    get_task_card_keyboard,
    get_profile_keyboard,
    get_notifications_keyboard,
    get_unlink_confirm_keyboard,
    get_help_keyboard,
)
from telegram_app.bot.handlers.settings_router import (
    toggle_chat_notification,
    unlink_user_account,
    format_profile_text,
)
from telegram_app.bot.handlers.tasks_router import (
    fetch_tasks_page_data,
    fetch_task_details_data,
    execute_task_action,
)


class TelegramBotKeyboardsTestCase(SimpleTestCase):
    """Тестирование генерации клавиатур Telegram-бота."""

    def test_get_main_menu_authenticated(self):
        """Проверяет структуру рабочего меню для авторизованного сотрудника."""
        kb = get_main_menu(is_authenticated=True)
        self.assertTrue(kb.is_persistent)
        self.assertEqual(len(kb.keyboard), 3)
        self.assertEqual(kb.keyboard[0][0].text, "📋 Мои задачи")
        self.assertEqual(kb.keyboard[0][1].text, "📑 Служебные записки")
        self.assertEqual(kb.keyboard[2][1].text, "⚙️ Профиль")

    def test_get_main_menu_unauthenticated(self):
        """Проверяет структуру гостевого меню для неавторизованного пользователя."""
        kb = get_main_menu(is_authenticated=False)
        self.assertTrue(kb.is_persistent)
        self.assertEqual(len(kb.keyboard), 1)
        self.assertEqual(kb.keyboard[0][0].text, "🔐 Привязать аккаунт")
        self.assertEqual(kb.keyboard[0][1].text, "ℹ️ Справка и помощь")

    def test_get_tasks_filter_keyboard(self):
        """Проверяет генерацию инлайн-вкладок и кнопок задач."""
        tasks_list = [{"id": 101, "title": "Подготовить отчет", "badge": "🔵"}]
        kb = get_tasks_filter_keyboard(active_tab="assigned", page=1, total_pages=2, tasks_list=tasks_list)
        # Вкладки (1 ряд) + задачи (1 ряд) + пагинация (1 ряд) + обновить (1 ряд)
        self.assertEqual(len(kb.inline_keyboard), 4)
        self.assertIn("📥 Мне", kb.inline_keyboard[0][0].text)
        self.assertIn("#101", kb.inline_keyboard[1][0].text)
        self.assertEqual(kb.inline_keyboard[1][0].callback_data, "task_view:101:assigned:1")

    def test_get_task_card_keyboard(self):
        """Проверяет генерацию кнопок карточки задачи."""
        kb = get_task_card_keyboard(
            task_id=42,
            can_accept=True,
            can_complete=True,
            absolute_url="/tasks/42/",
            back_tab="assigned",
            back_page=1,
        )
        self.assertEqual(kb.inline_keyboard[0][0].text, "▶️ В работу")
        self.assertEqual(kb.inline_keyboard[0][1].text, "✅ Завершить")
        self.assertEqual(kb.inline_keyboard[1][0].text, "🔗 Открыть на портале")
        self.assertEqual(kb.inline_keyboard[2][0].text, "⬅️ Назад к списку задач")

    def test_get_profile_keyboard(self):
        """Проверяет генерацию кнопок личного кабинета."""
        kb_auth = get_profile_keyboard(is_authenticated=True)
        self.assertEqual(len(kb_auth.inline_keyboard), 3)
        self.assertEqual(kb_auth.inline_keyboard[0][0].text, "🔔 Настройка уведомлений")

        kb_guest = get_profile_keyboard(is_authenticated=False)
        self.assertEqual(len(kb_guest.inline_keyboard), 2)
        self.assertEqual(kb_guest.inline_keyboard[0][0].text, "🔑 Привязать аккаунт (УИН)")

    def test_get_notifications_keyboard(self):
        """Проверяет генерацию матрицы уведомлений."""
        class DummyChat:
            notify_tasks = True
            notify_memos = False
            notify_birthdays = True
            notify_emails = True
            notify_flights = False

        kb = get_notifications_keyboard(DummyChat())
        self.assertEqual(len(kb.inline_keyboard), 4)
        self.assertIn("🟢 Вкл", kb.inline_keyboard[0][0].text)
        self.assertIn("⚪ Откл", kb.inline_keyboard[0][1].text)


class TelegramBotDatabaseTestCase(TestCase):
    """Интеграционное тестирование функций бота, взаимодействующих с БД."""

    def setUp(self):
        """Создает тестового пользователя, ChatID и задачи."""
        self.user = DataBaseUser.objects.create_user(
            username="testpilot",
            first_name="Иван",
            last_name="Иванов",
            title="Иванов Иван",
            telegram_id="99887766",
            person_ref_key="11111111-2222-3333-4444-555555555555",
            is_active=True,
        )
        self.other_user = DataBaseUser.objects.create_user(
            username="testmanager",
            first_name="Петр",
            last_name="Петров",
            title="Петров Петр",
            telegram_id="11223344",
            person_ref_key="66666666-7777-8888-9999-000000000000",
            is_active=True,
        )
        self.chat = ChatID.objects.create(
            chat_id="99887766",
            ref_key=self.user.person_ref_key,
            is_active=True,
            notify_tasks=True,
        )

        # Создаем тестовые задачи
        self.task1 = Task.objects.create(
            user=self.other_user,
            responsible=self.user,
            title="Провести предполетный брифинг",
            status=TaskStatus.NEW,
        )
        self.task2 = Task.objects.create(
            user=self.user,
            responsible=self.other_user,
            title="Подготовить отчет по налету",
            status=TaskStatus.IN_PROGRESS,
        )

    async def test_toggle_chat_notification(self):
        """Проверяет переключение настроек уведомлений в ChatID."""
        updated = await toggle_chat_notification(99887766, "tasks")
        self.assertFalse(updated.notify_tasks)
        updated2 = await toggle_chat_notification(99887766, "tasks")
        self.assertTrue(updated2.notify_tasks)

    async def test_unlink_user_account(self):
        """Проверяет отвязку аккаунта сотрудника от Telegram."""
        success = await unlink_user_account(99887766)
        self.assertTrue(success)
        await self.user.arefresh_from_db()
        await self.chat.arefresh_from_db()
        self.assertEqual(self.user.telegram_id, "")
        self.assertFalse(self.chat.is_active)

    async def test_fetch_tasks_assigned(self):
        """Проверяет выборку задач, назначенных сотруднику."""
        tasks, page, total = await fetch_tasks_page_data(self.user, tab="assigned", page=1)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], self.task1.id)
        self.assertEqual(tasks[0]["status"], TaskStatus.NEW)

    async def test_fetch_tasks_authored(self):
        """Проверяет выборку задач, созданных сотрудником."""
        tasks, page, total = await fetch_tasks_page_data(self.user, tab="authored", page=1)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], self.task2.id)

    async def test_task_details_and_action(self):
        """Проверяет получение карточки задачи и смену статуса («В работу» и «Завершить»)."""
        details = await fetch_task_details_data(self.task1.id, self.user)
        self.assertIsNotNone(details)
        self.assertTrue(details["can_accept"])
        self.assertFalse(details["can_complete"])

        # Принимаем в работу
        success, msg = await execute_task_action(self.task1.id, self.user, "in_progress")
        self.assertTrue(success)
        await self.task1.arefresh_from_db()
        self.assertEqual(self.task1.status, TaskStatus.IN_PROGRESS)

        # Теперь можно завершить
        details_updated = await fetch_task_details_data(self.task1.id, self.user)
        self.assertTrue(details_updated["can_complete"])

        # Завершаем
        success_comp, msg_comp = await execute_task_action(self.task1.id, self.user, "completed")
        self.assertTrue(success_comp)
        await self.task1.arefresh_from_db()
        self.assertEqual(self.task1.status, TaskStatus.COMPLETED)
        self.assertTrue(self.task1.completed)
