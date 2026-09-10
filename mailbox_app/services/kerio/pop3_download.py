"""Менеджер управления службой сбора почты «Загрузка POP3» (Delivery / Pop3Account) в Kerio Connect."""

import logging
from typing import Any, Dict, List, Optional
from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioObjectNotFoundError,
    KerioValidationError,
)
from mailbox_app.services.kerio.utils import get_django_setting

logger = logging.getLogger(__name__)


class Pop3DownloadManager:
    """Менеджер правил внешней доставки и сборщика писем (Панель «Доставка» -> «Загрузка POP3» в Kerio Connect).

    Обеспечивает автоматическое конфигурирование забора корреспонденции с внешнего почтового
    сервера (mail.barkol.ru:995 SSL) для локальных почтовых ящиков сотрудников через интерфейс Delivery
    (Delivery.getPop3AccountList, Delivery.addPop3AccountList, Delivery.setPop3Account, Delivery.removePop3AccountList, Delivery.runPop3Downloads).

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
        raw_list: List[Dict[str, Any]] = []

        try:
            # Основной официальный метод согласно спецификации Delivery.idl в Kerio Connect
            result = self.client.call("Delivery.getPop3AccountList", params=params)
            if isinstance(result, dict) and "list" in result:
                raw_list = result["list"]
            elif isinstance(result, list):
                raw_list = result
        except KerioAPIError as exc:
            logger.warning(f"[KerioAdmin] Вызов Delivery.getPop3AccountList вернул ошибку ({exc}), попытка fallback...")
            try:
                # Fallback на альтернативные наименования методов
                result = self.client.call("Pop3Download.get", params=params)
                if isinstance(result, dict) and "list" in result:
                    raw_list = result["list"]
                elif isinstance(result, list):
                    raw_list = result
            except Exception:
                try:
                    result = self.client.call("Delivery.getPop3Accounts", params=params)
                    if isinstance(result, dict) and "list" in result:
                        raw_list = result["list"]
                    elif isinstance(result, list):
                        raw_list = result
                except Exception:
                    raise exc

        # Нормализация структуры данных для универсальной совместимости с шаблонами
        normalized: List[Dict[str, Any]] = []
        for acc in raw_list:
            is_active = acc.get("isActive", acc.get("isEnabled", True))
            leave_on_server_obj = acc.get("leaveOnServer")
            if isinstance(leave_on_server_obj, dict):
                leave_msgs = leave_on_server_obj.get("enabled", False)
            else:
                leave_msgs = bool(acc.get("leaveMessagesOnServer", False))

            mode_val = str(acc.get("mode", "SpecialPort"))
            use_ssl = mode_val in ("SpecialPort", "StlsCommand") or bool(acc.get("use_ssl", True))
            target_user = str(acc.get("deliveryAddress") or acc.get("targetUser", "")).strip()

            acc_copy = dict(acc)
            acc_copy.update({
                "id": acc.get("id", ""),
                "isActive": is_active,
                "isEnabled": is_active,
                "server": acc.get("server", "mail.barkol.ru"),
                "port": acc.get("port", 995),
                "userName": acc.get("userName", ""),
                "deliveryAddress": target_user,
                "targetUser": target_user,
                "description": acc.get("description", ""),
                "mode": mode_val,
                "use_ssl": use_ssl,
                "leaveMessagesOnServer": leave_msgs,
                "interval": acc.get("interval", 1),
            })
            normalized.append(acc_copy)

        return normalized

    def get_account_for_user(self, email_or_login: str) -> Optional[Dict[str, Any]]:
        """Находит правило загрузки POP3 для конкретного пользователя или email.

        Args:
            email_or_login (str): Логин или email пользователя.

        Returns:
            Optional[Dict[str, Any]]: Найденное правило POP3 или None.
        """
        clean_target = email_or_login.strip().lower()
        clean_login = clean_target.split("@")[0]
        accounts = self.get_accounts()

        for acc in accounts:
            delivery_addr = str(acc.get("deliveryAddress", "")).strip().lower()
            target_user = str(acc.get("targetUser", "")).strip().lower()
            username = str(acc.get("userName", "")).strip().lower()

            if clean_target in (delivery_addr, target_user, username):
                return acc
            if clean_login in (delivery_addr.split("@")[0], target_user.split("@")[0], username.split("@")[0]):
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

        По умолчанию используются стандартные корпоративные параметры:
        хост mail.barkol.ru, порт 995, SSL (SpecialPort), удаление писем с внешнего сервера (leaveOnServer.enabled=False).

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

        ext_host = server or str(get_django_setting("KERIO_EXTERNAL_POP3_HOST", "mail.barkol.ru") or "mail.barkol.ru")
        ext_port = int(port or get_django_setting("KERIO_EXTERNAL_POP3_PORT", 995) or 995)
        ext_ssl = use_ssl if use_ssl is not None else bool(get_django_setting("KERIO_EXTERNAL_POP3_SSL", True))
        ext_leave = leave_messages_on_server if leave_messages_on_server is not None else bool(get_django_setting("KERIO_EXTERNAL_POP3_LEAVE_MESSAGES", False))
        ext_username = username or target_user


        # Структура Pop3Account строго по спецификации Delivery.idl
        account_data: Dict[str, Any] = {
            "isActive": is_enabled,
            "server": ext_host,
            "port": ext_port,
            "userName": ext_username,
            "password": password,
            "description": f"Загрузка POP3: {ext_username}@{ext_host}",
            "deliveryAddress": target_user,
            "useSortingRules": False,
            "dropDuplicates": False,
            "mode": "SpecialPort" if ext_ssl else "NoSsl",
            "authentication": "PlainPop3",
            "leaveOnServer": {
                "enabled": ext_leave,
            },
        }

        try:
            result = self.client.call("Delivery.addPop3AccountList", params={"accounts": [account_data]})
            if isinstance(result, dict) and result.get("errors"):
                err_list = result.get("errors", [])
                err_msg = "; ".join([str(e.get("message", e)) for e in err_list if isinstance(e, dict)]) or str(err_list)
                raise KerioAPIError(f"Ошибка создания правила POP3 в Kerio Connect: {err_msg}")
        except KerioAPIError as exc:
            # Fallback для старых форматов API
            try:
                result = self.client.call("Pop3Download.create", params={"accounts": [account_data]})
            except Exception:
                raise exc

        logger.info(
            f"[KerioAdmin] Правило загрузки POP3 для '{target_user}' (внешний сервер {ext_host}:{ext_port}) успешно создано."
        )
        return result or {}

    def update_pop3_account(
        self,
        account_id: str,
        password: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        leave_messages_on_server: Optional[bool] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Обновляет параметры существующего правила загрузки POP3.

        Args:
            account_id (str): Идентификатор учетной записи POP3 в Kerio Connect.
            password (Optional[str]): Новый пароль на внешнем сервере.
            is_enabled (Optional[bool]): Флаг активности правила.
            leave_messages_on_server (Optional[bool]): Оставлять копии сообщений.
            extra_fields (Optional[Dict[str, Any]]): Дополнительные параметры.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        # Сначала получаем текущие параметры аккаунта для аккуратного патча
        all_accounts = self.get_accounts()
        target_account = next((a for a in all_accounts if a.get("id") == account_id), None)

        account_payload: Dict[str, Any] = {}
        if target_account:
            account_payload.update(target_account)

        if password is not None:
            account_payload["password"] = password
        if is_enabled is not None:
            account_payload["isActive"] = is_enabled
        if leave_messages_on_server is not None:
            account_payload["leaveOnServer"] = {"enabled": leave_messages_on_server}
        if extra_fields:
            account_payload.update(extra_fields)

        params = {
            "accountId": account_id,
            "account": account_payload,
        }

        try:
            return self.client.call("Delivery.setPop3Account", params=params)
        except KerioAPIError:
            # Fallback на альтернативный вызов
            return self.client.call("Pop3Download.set", params={"accountIds": [account_id], "pattern": account_payload})

    def remove_pop3_account(self, account_id: str) -> Dict[str, Any]:
        """Удаляет правило загрузки POP3 из Kerio Connect.

        Args:
            account_id (str): Идентификатор правила в Kerio.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        try:
            return self.client.call("Delivery.removePop3AccountList", params={"ids": [account_id]})
        except KerioAPIError:
            return self.client.call("Pop3Download.remove", params={"accountIds": [account_id]})

    def download_now(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Инициирует внеочередной немедленный сбор почты по правилам POP3.

        Args:
            account_id (Optional[str]): Идентификатор конкретного правила или None для всех.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        try:
            return self.client.call("Delivery.runPop3Downloads", params={})
        except KerioAPIError:
            params = {"accountIds": [account_id]} if account_id else {}
            return self.client.call("Pop3Download.downloadNow", params=params)
