"""Универсальный сервис отправки электронных писем (mailbox_app.services.email_service).

Предоставляет централизованный API для синхронной и асинхронной отправки
корпоративных email-уведомлений для всех модулей и приложений проекта.
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class UniversalEmailService:
    """Универсальный сервис формирования и отправки корпоративных email-сообщений.

    Поддерживает:
    - Автоматическую генерацию текстовой копии (plain text) из HTML;
    - Валидацию и очистку списков адресатов;
    - Прикрепление файловых вложений;
    - Асинхронную постановку задач в очередь Celery с безопасным Fallback.
    """

    @classmethod
    def send_email_sync(
        cls,
        subject: str,
        recipient_list: List[str],
        html_message: str,
        plain_message: Optional[str] = None,
        from_email: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        fail_silently: bool = False,
    ) -> Tuple[int, List[str]]:
        """Выполняет прямую синхронную отправку email-сообщения адресатам.

        Args:
            subject (str): Тема электронного письма.
            recipient_list (List[str]): Список адресов получателей.
            html_message (str): HTML-разметка тела письма.
            plain_message (Optional[str]): Текстовая версия письма. Defaults to None.
            from_email (Optional[str]): Адрес отправителя. Defaults to settings.EMAIL_HOST_USER.
            attachments (Optional[List[Dict[str, Any]]]): Список вложений формата
                [{'filename': '...', 'content': base64_str|bytes, 'mimetype': '...'}].
            fail_silently (bool): Не выбрасывать исключения при ошибках SMTP. Defaults to False.

        Returns:
            Tuple[int, List[str]]: Кортеж (количество_успешно_отправленных, список_ошибочных_адресов).
        """
        valid_recipients = [
            email.strip()
            for email in recipient_list
            if email and "@" in email and "." in email
        ]

        if not valid_recipients:
            logger.debug("[UniversalEmail] Список валидных получателей пуст, отправка отменена.")
            return 0, []

        if not plain_message:
            plain_message = strip_tags(
                html_message.replace("<br>", "\n").replace("<br/>", "\n").replace("</p>", "\n")
            )

        sender = from_email or getattr(settings, "EMAIL_HOST_USER", "office@barkol.ru")

        sent_count = 0
        failed_recipients: List[str] = []

        for recipient in valid_recipients:
            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_message,
                    from_email=sender,
                    to=[recipient],
                )
                msg.attach_alternative(html_message, "text/html")

                if attachments:
                    for att in attachments:
                        fname = att.get("filename", "attachment")
                        raw_content = att.get("content", b"")
                        mimetype = att.get("mimetype", "application/octet-stream")

                        if isinstance(raw_content, str):
                            try:
                                content_bytes = base64.b64decode(raw_content)
                            except Exception:
                                content_bytes = raw_content.encode("utf-8")
                        else:
                            content_bytes = raw_content

                        msg.attach(fname, content_bytes, mimetype)

                msg.send(fail_silently=False)
                sent_count += 1
                logger.info("[UniversalEmail] Email успешно отправлен на '%s', тема: '%s'", recipient, subject)
            except Exception as exc:
                failed_recipients.append(recipient)
                logger.error("[UniversalEmail] Ошибка отправки на '%s': %s", recipient, exc, exc_info=True)
                if not fail_silently and len(valid_recipients) == 1:
                    raise

        return sent_count, failed_recipients

    @classmethod
    def send_async_email(
        cls,
        subject: str,
        recipient_list: List[str],
        html_message: str,
        plain_message: Optional[str] = None,
        from_email: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Ставит задачу отправки email в фоновую очередь Celery с защитой от падения брокера.

        Args:
            subject (str): Тема электронного письма.
            recipient_list (List[str]): Список адресов получателей.
            html_message (str): HTML-разметка тела письма.
            plain_message (Optional[str]): Текстовая версия письма. Defaults to None.
            from_email (Optional[str]): Адрес отправителя. Defaults to settings.EMAIL_HOST_USER.
            attachments (Optional[List[Dict[str, Any]]]): Список вложений.

        Returns:
            bool: True, если задача успешно поставлена в очередь Celery, иначе False.
        """
        valid_recipients = [
            email.strip()
            for email in recipient_list
            if email and "@" in email and "." in email
        ]

        if not valid_recipients:
            logger.debug("[UniversalEmail:Async] Список адресатов пуст, задача не создается.")
            return False

        try:
            from mailbox_app.tasks import send_universal_email_task
            send_universal_email_task.delay(
                subject=subject,
                recipient_list=valid_recipients,
                html_message=html_message,
                plain_message=plain_message,
                from_email=from_email,
                attachments=attachments,
            )
            logger.info(
                "[UniversalEmail:Async] Задача отправки email '%s' поставлена в очередь Celery для %d получателей.",
                subject,
                len(valid_recipients),
            )
            return True
        except Exception as exc:
            logger.warning(
                "[UniversalEmail:Async] Брокер Celery недоступен при постановке задачи email ('%s'): %s. "
                "Пропуск фоновой отправки без прерывания веб-запроса.",
                subject,
                exc,
            )
            return False
