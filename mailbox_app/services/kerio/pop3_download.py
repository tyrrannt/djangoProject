"""Менеджер управления службой сбора почты «Загрузка POP3» (Pop3Download) в Kerio Connect."""

import logging
from typing import Any, Dict, List, Optional
try:
    from django.conf import settings
except ImportError:
    settings = None

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioObjectNotFoundError,
    KerioValidationError,
)

logger = logging.getLogger(__name__)


class Pop3DownloadManager:
    """Менеджер правил внешней доставки и сборщика писем (Панель «Доставка» -> «Загрузка POP3» в Kerio Connect).

    Позволяет автоматически конфигурировать забор корреспонденции с внешнего почтового
    сервера (mail.barkol.ru:995 SSL) для локальных почтовых ящиков сотрудников.

    Attributes:
        client (KerioConnectAdminClient): Экземпляр клиента API.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер загрузки POP3.

        Args:
            client (KerioConnectAdminClient): Клиент API Kerio Connect.
        """
        self.client = client

    def get_accounts(
        self,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Получает список всех настроенных правил загрузки POP3 в Kerio Connect.

        Args:
            query (Optional[Dict[str, Any]]): Параметры поиска/фильтрации.

        Returns:
            List[Dict[str, Any]]: Список словарей параметров POP3-сборщиков.

        Raises:
            KerioAPIError: При ошибке выполнения вызова API.
        """
        params = {"query": query or {}}
        try:
            result = self.client.call("Pop3Download.get", params=params)
        except KerioAPIError as exc:
            # Fallback на альтернативное наименование метода в некоторых подверсиях Kerio
            try:
                result = self.client.call("Delivery.getPop3Accounts", params=params)
            except Exception:
                raise exc

        if isinstance(result, dict) and "list" in result:
            return result["list"]
        if isinstance(result, list):
            return result
        return []

    def get_account_for_user(self, email_or_login: str) -> Optional[Dict[str, Any]]:
        """Находит правило загрузки POP3 для конкретного пользователя или email.

        Args:
            email_or_login (str): Логин или email пользователя.

        Returns:
            Optional[Dict[str, Any]]: Найденное правило POP3 или None.
        """
        clean_target = email_or_login.strip().lower()
        accounts = self.get_accounts()
        for acc in accounts:
            target_user = str(acc.get("targetUser", "")).strip().lower()
            username = str(acc.get("userName", "")).strip().lower()
            if clean_target in (target_user, username) or clean_target.split("@")[0] in (target_user, username):
                return acc
        return None

    def create_pop3_account(
        self,
        target_user: str,
        password: str,
        server: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        leave_messages_on_server: Optional[bool] = None,
        interval_minutes: int = 1,
        is_enabled: bool = True,
    ) -> Dict[str, Any]:
        """Создает новое правило загрузки POP3 для забора почты с внешнего сервера.

        По умолчанию используются стандартные настройки компании:
        хост mail.barkol.ru, порт 995, SSL=True, удаление писем с внешнего сервера=True,
        интервал=1 мин.

        Args:
            target_user (str): Имя локального пользователя или email в Kerio, куда доставлять почту.
            password (str): Пароль на внешнем POP3 сервере.
            server (Optional[str]): Адрес внешнего POP3 сервера. По умолчанию из settings.KERIO_EXTERNAL_POP3_HOST ('mail.barkol.ru').
            port (Optional[int]): Порт POP3. По умолчанию из settings.KERIO_EXTERNAL_POP3_PORT (995).
            username (Optional[str]): Логин на внешнем сервере. Если не указан, берется target_user.
            use_ssl (Optional[bool]): Использовать SSL/TLS. По умолчанию из settings.KERIO_EXTERNAL_POP3_SSL (True).
            leave_messages_on_server (Optional[bool]): Оставлять копии писем на внешнем сервере. По умолчанию False (удалять).
            interval_minutes (int): Интервал опроса в минутах (по умолчанию 1).
            is_enabled (bool): Активно ли правило сбора.

        Returns:
            Dict[str, Any]: Результат вызова API Kerio Connect.

        Raises:
            KerioValidationError: При неполных или некорректных параметрах.
            KerioAPIError: При ошибке на стороне сервера Kerio.
        """
        if not target_user:
            raise KerioValidationError("Целевой пользователь Kerio (target_user) не может быть пустым.")
        if not password:
            raise KerioValidationError("Пароль для внешнего POP3 сервера не может быть пустым.")

        ext_host = server or getattr(settings, "KERIO_EXTERNAL_POP3_HOST", "mail.barkol.ru")
        ext_port = port or getattr(settings, "KERIO_EXTERNAL_POP3_PORT", 995)
        ext_ssl = use_ssl if use_ssl is not None else getattr(settings, "KERIO_EXTERNAL_POP3_SSL", True)
        ext_leave = (
            leave_messages_on_server
            if leave_messages_on_server is not None
            else getattr(settings, "KERIO_EXTERNAL_POP3_LEAVE_MESSAGES", False)
        )
        ext_username = username or target_user

        account_data: Dict[str, Any] = {
            "server": ext_host,
            "port": ext_port,
            "security": "Ssl" if ext_ssl else "None",
            "userName": ext_username,
            "password": password,
            "authType": "Plain",
            "targetUser": target_user,
            "leaveMessagesOnServer": ext_leave,
            "interval": max(1, interval_minutes),
            "isEnabled": is_enabled,
        }

        params = {"accounts": [account_data]}
        try:
            result = self.client.call("Pop3Download.create", params=params)
        except KerioAPIError as exc:
            try:
                result = self.client.call("Delivery.createPop3Account", params=params)
            except Exception:
                raise exc

        logger.info(
            f"[KerioAdmin] Правило загрузки POP3 для '{target_user}' (внешний сервер {ext_host}:{ext_port}) успешно создано."
        )
        return result

    def update_pop3_account(
        self,
        account_id: str,
        password: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        leave_messages_on_server: Optional[bool] = None,
        interval_minutes: Optional[int] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Обновляет параметры существующего правила загрузки POP3.

        Args:
            account_id (str): Идентификатор учетной записи POP3 в Kerio Connect.
            password (Optional[str]): Новый пароль на внешнем сервере.
            is_enabled (Optional[bool]): Флаг активности правила.
            leave_messages_on_server (Optional[bool]): Оставлять копии сообщений.
            interval_minutes (Optional[int]): Интервал опроса.
            extra_fields (Optional[Dict[str, Any]]): Дополнительные параметры.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        pattern: Dict[str, Any] = {}
        if password is not None:
            pattern["password"] = password
        if is_enabled is not None:
            pattern["isEnabled"] = is_enabled
        if leave_messages_on_server is not None:
            pattern["leaveMessagesOnServer"] = leave_messages_on_server
        if interval_minutes is not None:
            pattern["interval"] = max(1, interval_minutes)
        if extra_fields:
            pattern.update(extra_fields)

        params = {
            "accountIds": [account_id],
            "pattern": pattern,
        }
        return self.client.call("Pop3Download.set", params=params)

    def remove_pop3_account(self, account_id: str) -> Dict[str, Any]:
        """Удаляет правило загрузки POP3 из Kerio Connect.

        Args:
            account_id (str): Идентификатор правила в Kerio.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        return self.client.call("Pop3Download.remove", params={"accountIds": [account_id]})

    def download_now(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Инициирует внеочередной немедленный сбор почты по правилу POP3.

        Args:
            account_id (Optional[str]): Идентификатор конкретного правила или None для всех.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        params: Dict[str, Any] = {}
        if account_id:
            params["accountIds"] = [account_id]
        return self.client.call("Pop3Download.downloadNow", params=params)
