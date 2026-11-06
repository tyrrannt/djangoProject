"""Тесты функционала пересылки писем с вложениями (Forward Attachments).

Модуль тестирует:
- Метод пакетного скачивания вложений download_multiple_attachments в ImapMailService.
- Поля forward_uid и forward_folder в форме MailComposeForm.
- Извлечение данных и предзаполнение вложений в представлении MailboxComposeView (GET-запрос).
- Корректную отправку пересылаемых вложений через SMTP и планирование через ScheduledEmail (POST-запрос).
"""

import email
from email.message import EmailMessage
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from mailbox_app.forms import MailComposeForm
from mailbox_app.models import MailAccount
from mailbox_app.services.imap_service import ImapMailService
from mailbox_app.views import MailboxComposeView

User = get_user_model()


class ForwardAttachmentsTestCase(TestCase):
    """Набор тестов для проверки пересылки писем с вложениями."""

    def setUp(self) -> None:
        """Начальная настройка тестового окружения."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpassword123",
            email="testuser@barkol.ru",
            first_name="Иван",
            last_name="Иванов",
        )
        self.account = MailAccount.objects.create(
            user=self.user,
            email="testuser@barkol.ru",
            display_name="Тестовый Пользователь",
            imap_host="imap.barkol.ru",
            imap_port=993,
            imap_use_ssl=True,
            smtp_host="smtp.barkol.ru",
            smtp_port=465,
            smtp_use_ssl=True,
            is_active=True,
        )

    def test_mail_compose_form_fields(self) -> None:
        """Проверяет наличие скрытых полей forward_uid и forward_folder в форме MailComposeForm."""
        form = MailComposeForm()
        self.assertIn("forward_uid", form.fields)
        self.assertIn("forward_folder", form.fields)
        self.assertFalse(form.fields["forward_uid"].required)
        self.assertFalse(form.fields["forward_folder"].required)

        # Проверка валидации формы с заполненными полями
        data = {
            "to": "recipient@barkol.ru",
            "subject": "Fwd: Тестовое письмо",
            "body_html": "<p>Пересылаемый текст</p>",
            "forward_uid": "456",
            "forward_folder": "INBOX",
            "send_mode": "now",
        }
        form_valid = MailComposeForm(data=data)
        self.assertTrue(form_valid.is_valid(), form_valid.errors)
        self.assertEqual(form_valid.cleaned_data["forward_uid"], "456")
        self.assertEqual(form_valid.cleaned_data["forward_folder"], "INBOX")

    def test_download_multiple_attachments_imap_service(self) -> None:
        """Проверяет метод download_multiple_attachments сервиса ImapMailService."""
        # Создаем тестовое multipart email сообщение с двумя вложениями
        msg = EmailMessage()
        msg["From"] = "sender@barkol.ru"
        msg["To"] = "testuser@barkol.ru"
        msg["Subject"] = "Письмо с файлами"
        msg.set_content("Основной текст")

        att1_payload = b"Content of file 1"
        att2_payload = b"Content of file 2"
        msg.add_attachment(att1_payload, maintype="text", subtype="plain", filename="file1.txt")
        msg.add_attachment(att2_payload, maintype="application", subtype="pdf", filename="report.pdf")

        raw_bytes = msg.as_bytes()

        service = ImapMailService("imap.barkol.ru", 993, "testuser@barkol.ru", "password")
        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("OK", [(b"1 (RFC822 {" + str(len(raw_bytes)).encode() + b"}", raw_bytes)])
        service.client = mock_imap

        # Скачиваем вложение 1 (индекс 2 в msg.walk(), т.к. 0=контейнер, 1=текстовое тело)
        attachments = service.download_multiple_attachments("INBOX", 1, [2])
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0][0], "file1.txt")
        self.assertEqual(attachments[0][2], att1_payload)

        # Скачиваем оба вложения (индексы 2 и 3)
        all_attachments = service.download_multiple_attachments("INBOX", 1, [2, 3])
        self.assertEqual(len(all_attachments), 2)
        filenames = [a[0] for a in all_attachments]
        self.assertIn("file1.txt", filenames)
        self.assertIn("report.pdf", filenames)

    @patch.object(MailboxComposeView, "get_imap_service")
    def test_compose_view_get_initial_and_context_forward(self, mock_get_imap: MagicMock) -> None:
        """Проверяет предзаполнение формы и контекста в MailboxComposeView при пересылке письма."""
        mock_imap_inst = MagicMock()
        mock_get_imap.return_value.__enter__.return_value = mock_imap_inst

        # Имитируем получение оригинального письма
        mock_imap_inst.get_message_detail.return_value = {
            "uid": 123,
            "subject": "Важный договор",
            "from_raw": "partner@barkol.ru",
            "from_email": "partner@barkol.ru",
            "from_name": "Партнер",
            "date_raw": "05.11.2026 12:00",
            "body_html": "<p>Прошу согласовать договор.</p>",
            "body_text": "Прошу согласовать договор.",
            "attachments": [
                {
                    "part_index": 1,
                    "filename": "contract.pdf",
                    "size": 10240,
                    "size_human": "10.0 KB",
                    "content_type": "application/pdf",
                    "is_dangerous": False,
                    "risk_badge": None,
                }
            ],
        }
        mock_imap_inst.get_folders.return_value = [{"name": "INBOX", "raw_name": "INBOX", "type": "inbox"}]

        url = f"{reverse('mailbox_app:compose')}?forward_uid=123&folder=INBOX"
        request = self.factory.get(url)
        request.user = self.user
        request.session = {}

        view = MailboxComposeView()
        view.setup(request)

        # Проверка get_initial
        initial = view.get_initial()
        self.assertEqual(initial.get("forward_uid"), "123")
        self.assertEqual(initial.get("forward_folder"), "INBOX")
        self.assertEqual(initial.get("subject"), "Fwd: Важный договор")
        self.assertIn("Важный договор", initial.get("body_html", ""))

        # Проверка get_context_data
        context = view.get_context_data()
        self.assertEqual(context.get("forward_uid"), "123")
        self.assertEqual(context.get("forward_folder"), "INBOX")
        self.assertEqual(len(context.get("forward_attachments", [])), 1)
        self.assertEqual(context["forward_attachments"][0]["filename"], "contract.pdf")

    @patch.object(MailboxComposeView, "get_smtp_service")
    @patch.object(MailboxComposeView, "get_imap_service")
    def test_compose_view_form_valid_immediate_send(
        self, mock_get_imap: MagicMock, mock_get_smtp: MagicMock
    ) -> None:
        """Проверяет отправку через SMTP с объединением пересылаемых и новых вложений."""
        mock_imap_inst = MagicMock()
        mock_get_imap.return_value.__enter__.return_value = mock_imap_inst
        mock_imap_inst.download_multiple_attachments.return_value = [
            ("forwarded_doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"DOCXDATA")
        ]

        mock_smtp_inst = MagicMock()
        mock_get_smtp.return_value = mock_smtp_inst

        # Подготавливаем файл для загрузки
        uploaded_file = SimpleUploadedFile("new_file.txt", b"NEWFILEDATA", content_type="text/plain")

        post_data = {
            "to": "boss@barkol.ru",
            "subject": "Fwd: Согласование",
            "body_html": "<p>Пересылаю документ</p>",
            "send_mode": "now",
            "forward_uid": "99",
            "forward_folder": "INBOX",
            "forward_parts": ["1"],
        }

        url = reverse("mailbox_app:compose")
        request = self.factory.post(url, data=post_data)
        request.FILES["attachments"] = uploaded_file
        request.user = self.user

        # Добавляем хранилище сообщений Django
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        view = MailboxComposeView()
        view.setup(request)

        form = MailComposeForm(data=post_data, files={"attachments": uploaded_file})
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        # Проверяем вызов download_multiple_attachments с нужными индексами
        mock_imap_inst.download_multiple_attachments.assert_called_once_with("INBOX", 99, [1])

        # Проверяем вызов smtp_service.send_email
        mock_smtp_inst.send_email.assert_called_once()
        _, call_kwargs = mock_smtp_inst.send_email.call_args
        self.assertEqual(call_kwargs["to_list"], ["boss@barkol.ru"])
        self.assertEqual(call_kwargs["subject"], "Fwd: Согласование")

        sent_attachments = call_kwargs["attachments"]
        self.assertEqual(len(sent_attachments), 2)

        # 1-е вложение - пересылаемое
        self.assertEqual(sent_attachments[0][0], "forwarded_doc.docx")
        self.assertEqual(sent_attachments[0][2], b"DOCXDATA")

        # 2-е вложение - вновь загруженное
        self.assertEqual(sent_attachments[1][0], "new_file.txt")
        self.assertEqual(sent_attachments[1][2], b"NEWFILEDATA")

    @patch("mailbox_app.services.scheduled_mail_service.create_scheduled_email")
    @patch.object(MailboxComposeView, "get_imap_service")
    def test_compose_view_form_valid_scheduled_send(
        self, mock_get_imap: MagicMock, mock_create_scheduled: MagicMock
    ) -> None:
        """Проверяет отправку по расписанию с объединением пересылаемых и новых вложений."""
        mock_imap_inst = MagicMock()
        mock_get_imap.return_value.__enter__.return_value = mock_imap_inst
        mock_imap_inst.download_multiple_attachments.return_value = [
            ("forwarded_plan.pdf", "application/pdf", b"PDFPLAN")
        ]

        uploaded_file = SimpleUploadedFile("extra_notes.txt", b"NOTES", content_type="text/plain")

        post_data = {
            "to": "team@barkol.ru",
            "subject": "Fwd: Планирование",
            "body_html": "<p>Ознакомьтесь с планом</p>",
            "send_mode": "scheduled",
            "scheduled_at": "2026-12-31 10:00",
            "forward_uid": "77",
            "forward_folder": "INBOX",
            "forward_parts": ["2"],
        }

        url = reverse("mailbox_app:compose")
        request = self.factory.post(url, data=post_data)
        request.FILES["attachments"] = uploaded_file
        request.user = self.user

        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        view = MailboxComposeView()
        view.setup(request)

        form = MailComposeForm(data=post_data, files={"attachments": uploaded_file})
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        # Проверяем вызов create_scheduled_email
        mock_create_scheduled.assert_called_once()
        _, call_kwargs = mock_create_scheduled.call_args
        self.assertEqual(call_kwargs["to_recipients"], "team@barkol.ru")
        self.assertEqual(call_kwargs["subject"], "Fwd: Планирование")

        attached_files = call_kwargs["uploaded_files"]
        self.assertEqual(len(attached_files), 2)

        # Проверяем, что оба файла присутствуют как SimpleUploadedFile / UploadedFile
        file_names = [f.name for f in attached_files]
        self.assertIn("forwarded_plan.pdf", file_names)
        self.assertIn("extra_notes.txt", file_names)

    def test_compose_form_priority_and_receipt_fields(self) -> None:
        """Проверяет наличие полей is_important и request_read_receipt в MailComposeForm."""
        form = MailComposeForm()
        self.assertIn("is_important", form.fields)
        self.assertIn("request_read_receipt", form.fields)
        self.assertFalse(form.fields["is_important"].required)
        self.assertFalse(form.fields["request_read_receipt"].required)

        data = {
            "to": "recipient@barkol.ru",
            "subject": "Срочное сообщение",
            "body_html": "<p>Важная информация</p>",
            "is_important": True,
            "request_read_receipt": True,
            "send_mode": "now",
        }
        form_valid = MailComposeForm(data=data)
        self.assertTrue(form_valid.is_valid(), form_valid.errors)
        self.assertTrue(form_valid.cleaned_data["is_important"])
        self.assertTrue(form_valid.cleaned_data["request_read_receipt"])

    @patch.object(MailboxComposeView, "get_imap_service")
    def test_compose_view_get_initial_reply_all(self, mock_get_imap: MagicMock) -> None:
        """Проверяет предзаполнение формы в MailboxComposeView в режиме «Ответить всем» (reply_all_uid)."""
        mock_imap_inst = MagicMock()
        mock_get_imap.return_value.__enter__.return_value = mock_imap_inst

        # Имитируем исходное письмо от Alice получателям: testuser (я), Charlie и Dave (в копии)
        mock_imap_inst.get_message_detail.return_value = {
            "uid": 200,
            "subject": "Совещание по проекту",
            "from_raw": "Alice <alice@barkol.ru>",
            "from_email": "alice@barkol.ru",
            "from_name": "Alice",
            "to_raw": "testuser@barkol.ru, Charlie <charlie@barkol.ru>",
            "cc_raw": "Dave <dave@barkol.ru>",
            "bcc_raw": "",
            "date_raw": "06.11.2026 14:00",
            "body_html": "<p>Коллеги, прошу ознакомиться.</p>",
            "body_text": "Коллеги, прошу ознакомиться.",
            "attachments": [],
        }

        url = f"{reverse('mailbox_app:compose')}?reply_all_uid=200&folder=INBOX"
        request = self.factory.get(url)
        request.user = self.user
        request.session = {}

        view = MailboxComposeView()
        view.setup(request)

        initial = view.get_initial()

        # Автор письма должен быть в поле To
        self.assertEqual(initial.get("to"), "alice@barkol.ru")
        self.assertEqual(initial.get("subject"), "Re: Совещание по проекту")

        # В поле Cc должны попасть Charlie и Dave, но НЕ testuser (текущий ящик) и НЕ Alice (автор)
        cc_val = initial.get("cc", "")
        self.assertIn("charlie@barkol.ru", cc_val)
        self.assertIn("dave@barkol.ru", cc_val)
        self.assertNotIn("testuser@barkol.ru", cc_val)
        self.assertNotIn("alice@barkol.ru", cc_val)

    @patch.object(MailboxComposeView, "get_smtp_service")
    def test_compose_view_form_valid_with_priority_and_receipt(self, mock_get_smtp: MagicMock) -> None:
        """Проверяет передачу флагов высокой важности и уведомления о прочтении в SmtpMailService."""
        mock_smtp_inst = MagicMock()
        mock_get_smtp.return_value = mock_smtp_inst

        post_data = {
            "to": "partner@barkol.ru",
            "subject": "Важный документ",
            "body_html": "<p>Срочно в номер</p>",
            "send_mode": "now",
            "is_important": True,
            "request_read_receipt": True,
        }

        url = reverse("mailbox_app:compose")
        request = self.factory.post(url, data=post_data)
        request.user = self.user

        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        view = MailboxComposeView()
        view.setup(request)

        form = MailComposeForm(data=post_data)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)
        self.assertEqual(response.status_code, 302)

        # Проверяем, что smtp_service.send_email был вызван с is_important=True и request_read_receipt=True
        mock_smtp_inst.send_email.assert_called_once()
        _, call_kwargs = mock_smtp_inst.send_email.call_args
        self.assertTrue(call_kwargs.get("is_important"))
        self.assertTrue(call_kwargs.get("request_read_receipt"))

    @patch("smtplib.SMTP_SSL")
    def test_smtp_mail_service_headers_priority_and_receipt(self, mock_smtp_ssl: MagicMock) -> None:
        """Проверяет генерацию MIME-заголовков X-Priority, Importance и Disposition-Notification-To в SmtpMailService."""
        from mailbox_app.services.smtp_service import SmtpMailService

        mock_server = MagicMock()
        mock_server.login.return_value = (235, b"Authentication successful")
        mock_server.sendmail.return_value = {}
        mock_smtp_ssl.return_value = mock_server

        service = SmtpMailService(
            smtp_host="smtp.barkol.ru",
            smtp_port=465,
            email_addr="testuser@barkol.ru",
            password="testpassword",
            display_name="Тестовый Пользователь",
            use_ssl=True,
        )

        success = service.send_email(
            to_list=["client@barkol.ru"],
            subject="Срочный запрос",
            body_html="<p>Текст письма</p>",
            is_important=True,
            request_read_receipt=True,
        )
        self.assertTrue(success)

        # Проверяем отправленные данные в sendmail
        mock_server.sendmail.assert_called_once()
        from_addr, to_addrs, raw_msg_str = mock_server.sendmail.call_args[0]
        self.assertEqual(from_addr, "testuser@barkol.ru")
        self.assertEqual(to_addrs, ["client@barkol.ru"])

        # Проверяем наличие заголовков в MIME-сообщении
        self.assertIn("X-Priority: 1 (Highest)", raw_msg_str)
        self.assertIn("Importance: High", raw_msg_str)
        self.assertIn("Disposition-Notification-To: testuser@barkol.ru", raw_msg_str)
        self.assertIn("Return-Receipt-To: testuser@barkol.ru", raw_msg_str)
