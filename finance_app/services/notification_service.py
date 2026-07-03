from typing import Any
import requests
from django.conf import settings
from django.core.mail import send_mail
from loguru import logger

from finance_app.models import Notification, UserNotificationSetting


class NotificationService:
    """
    Сервис для отправки уведомлений по различным каналам.
    """

    @staticmethod
    def send_notification_to_user(user: Any, message: str) -> None:
        """
        Отправляет уведомление пользователю по всем включенным в его настройках каналам.

        Args:
            user: Экземпляр пользователя.
            message: Текст сообщения.
        """
        # Получаем или создаем настройки уведомлений для пользователя
        settings_obj, _ = UserNotificationSetting.objects.get_or_create(user=user)

        if settings_obj.portal_enabled:
            NotificationService.send_channel(user, message, "portal")

        if settings_obj.email_enabled and user.email:
            NotificationService.send_channel(user, message, "email")

        if settings_obj.telegram_enabled and getattr(user, "telegram_id", None):
            NotificationService.send_channel(user, message, "telegram")

    @staticmethod
    def send_channel(user: Any, message: str, channel: str) -> bool:
        """
        Отправляет уведомление пользователю по конкретному каналу.

        Args:
            user: Пользователь.
            message: Текст.
            channel: Канал ('portal', 'email', 'telegram').

        Returns:
            True, если отправка успешна, иначе False.
        """
        # Сначала создаем запись в БД
        notif = Notification.objects.create(
            user=user,
            message=message,
            channel=channel
        )

        success = False
        if channel == "portal":
            # Для портала уведомление считается сразу доставленным
            success = True
        elif channel == "email":
            success = NotificationService._send_email(user.email, message)
        elif channel == "telegram":
            telegram_id = getattr(user, "telegram_id", "")
            success = NotificationService._send_telegram(telegram_id, message)

        if success:
            notif.sent = True
            notif.save(update_fields=["sent"])

        return success

    @staticmethod
    def _send_email(email_address: str, message: str) -> bool:
        """
        Отправляет email сообщение.

        Args:
            email_address: Адрес получателя.
            message: Сообщение.

        Returns:
            bool: Успех отправки.
        """
        if not email_address:
            logger.warning("Email не указан.")
            return False
        try:
            from django.utils.html import strip_tags
            
            is_html = '<' in message and '>' in message
            plain_message = strip_tags(message.replace('<br>', '\n').replace('</p>', '\n')) if is_html else message
            html_message = message if is_html else None

            send_mail(
                subject="Финансовые уведомления портала ООО АК 'БАРКОЛ'",
                message=plain_message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email_address],
                fail_silently=False,
                html_message=html_message,
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки email на {email_address}: {e}")
            return False

    @staticmethod
    def _send_telegram(telegram_id: str, message: str) -> bool:
        """
        Отправляет Telegram сообщение.

        Args:
            telegram_id: Идентификатор чата.
            message: Сообщение.

        Returns:
            bool: Успех отправки.
        """
        if not telegram_id:
            logger.warning("Telegram ID не указан.")
            return False

        token = getattr(settings, "TELEGRAM_TOKEN", None)
        if not token:
            logger.warning("TELEGRAM_TOKEN не настроен.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": telegram_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Ошибка отправки Telegram на {telegram_id}: {e}")
            return False
