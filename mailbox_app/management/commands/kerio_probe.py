"""Команда управления Django для проверки методов Delivery и POP3 в Kerio Connect API."""

from typing import Any
import urllib3
from django.conf import settings
from django.core.management.base import BaseCommand

from mailbox_app.services.kerio.client import KerioConnectAdminClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Command(BaseCommand):
    """Команда для проверки методов Delivery.getPop3AccountList в Kerio Connect 9.4.1."""

    help = "Тестирует методы Delivery.getPop3AccountList и параметры POP3 в Kerio Connect 9.4.1."

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа."""
        api_url = getattr(settings, "KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/")
        username = getattr(settings, "KERIO_API_USER", "admin")
        password = getattr(settings, "KERIO_API_PASSWORD", "")

        client = KerioConnectAdminClient(
            api_url=api_url,
            username=username,
            password=password,
            verify_ssl=False,
            timeout=10,
        )

        client.login()
        self.stdout.write(self.style.SUCCESS(f"Авторизация успешна (токен {client.token[:12]}...)"))

        # Проверка Delivery.getPop3AccountList
        try:
            res = client.call("Delivery.getPop3AccountList", params={"query": {}})
            self.stdout.write(self.style.SUCCESS(f"Delivery.getPop3AccountList УСПЕШНО ВЫПОЛНЕН: {res}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Delivery.getPop3AccountList ошибка: {exc}"))

        # Проверка Delivery.getInternetSettings
        try:
            res = client.call("Delivery.getInternetSettings", params={})
            self.stdout.write(self.style.SUCCESS(f"Delivery.getInternetSettings: {res}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Delivery.getInternetSettings ошибка: {exc}"))
