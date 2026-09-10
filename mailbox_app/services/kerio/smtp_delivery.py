"""Менеджер правил исходящей маршрутизации «Доставка SMTP» (Delivery / SmtpDeliveryRoute) в Kerio Connect."""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

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


class SmtpDeliveryManager:
    """Менеджер правил исходящей маршрутизации и ретрансляции почты («Доставка SMTP» в Kerio Connect).

    В соответствии с архитектурой почтовой системы BARKOL:
    - Локальный почтовый сервер Kerio Connect (sm.barkol.ru:465) принимает исходящую почту от клиентов;
    - При отправке во внешний мир Kerio Connect использует таблицу правил «Доставка SMTP» (SMTP Delivery Routing);
    - Для каждого сотрудника создается персональное правило: если адрес отправителя равен полному адресу
      пользователя (<user>@barkol.ru), перенаправлять почту на сервер ретрансляции smtp.barkol.ru:587
      (STARTTLS) с авторизацией по полному адресу и паролю учетной записи (SMTP AUTH).

    Управление правилами осуществляется через Administration API Kerio Connect:
    методы Delivery.getDeliveryRouteList, Delivery.addDeliveryRouteList, Delivery.setDeliveryRoute,
    Delivery.removeDeliveryRouteList, либо Delivery.get / Delivery.set.

    Attributes:
        client (KerioConnectAdminClient): Экземпляр низкоуровневого клиента JSON-RPC API.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер правил Доставки SMTP.

        Args:
            client (KerioConnectAdminClient): Низкоуровневый клиент API Kerio Connect.
        """
        self.client = client

    def get_routes(
        self,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Получает список всех настроенных правил маршрутизации «Доставка SMTP» в Kerio Connect.

        Опрашивает методы API Kerio Connect (Delivery.getDeliveryRouteList, Delivery.getRouteList,
        Delivery.getCustomRoutes, Delivery.get) и выполняет нормализацию полученных структур данных.

        Args:
            query (Optional[Dict[str, Any]]): Дополнительные параметры фильтрации или поиска.

        Returns:
            List[Dict[str, Any]]: Список нормализованных словарей параметров правил доставки SMTP.

        Raises:
            KerioAPIError: При критической ошибке выполнения вызова API.
        """
        params = {"query": query or {}}
        raw_list: List[Dict[str, Any]] = []

        # Поочередный опрос методов по спецификации Delivery.idl
        probe_methods = [
            ("Delivery.getDeliveryRouteList", params),
            ("Delivery.getRouteList", params),
            ("Delivery.getCustomRoutes", params),
            ("Delivery.getDeliveryRoutes", params),
            ("Smtp.getDeliveryRouteList", params),
            ("Delivery.get", {}),
        ]

        last_exc: Optional[Exception] = None
        for method_name, method_params in probe_methods:
            try:
                result = self.client.call(method_name, params=method_params)
                if isinstance(result, dict):
                    if "list" in result and isinstance(result["list"], list):
                        raw_list = result["list"]
                        break
                    elif "customRules" in result and isinstance(result["customRules"], list):
                        raw_list = result["customRules"]
                        break
                    elif "routes" in result and isinstance(result["routes"], list):
                        raw_list = result["routes"]
                        break
                    elif "relayRules" in result and isinstance(result["relayRules"], list):
                        raw_list = result["relayRules"]
                        break
                    elif "deliveryRoutes" in result and isinstance(result["deliveryRoutes"], list):
                        raw_list = result["deliveryRoutes"]
                        break
                elif isinstance(result, list):
                    raw_list = result
                    break
            except KerioAPIError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                continue

        if not raw_list and last_exc and "-32601" not in str(last_exc):
            logger.debug(f"[SmtpDeliveryManager] Информация о правилах SMTP доставки: {last_exc}")

        # Нормализация структуры каждого правила
        normalized: List[Dict[str, Any]] = []
        for r in raw_list:
            norm_item = self._normalize_route(r)
            normalized.append(norm_item)

        return normalized

    def _normalize_route(self, raw_route: Dict[str, Any]) -> Dict[str, Any]:
        """Нормализует сырой объект правила доставки Kerio Connect в стандартный плоский словарь.

        Args:
            raw_route (Dict[str, Any]): Исходный словарь из ответа API Kerio Connect.

        Returns:
            Dict[str, Any]: Стандартизированный словарь параметров правила доставки.
        """
        route_id = str(raw_route.get("id", ""))
        is_enabled = bool(raw_route.get("isEnabled", raw_route.get("isActive", True)))
        description = str(raw_route.get("description", raw_route.get("name", "")))

        # Извлечение условия (отправитель / шаблон)
        condition_type = str(raw_route.get("conditionType", raw_route.get("matchType", "ConditionSender")))
        match_pattern = str(
            raw_route.get("matchPattern")
            or raw_route.get("sender")
            or raw_route.get("pattern")
            or raw_route.get("value")
            or ""
        ).strip().lower()

        # Если условие задано вложенным объектом condition
        cond_obj = raw_route.get("condition")
        if isinstance(cond_obj, dict):
            condition_type = str(cond_obj.get("type", condition_type))
            match_pattern = str(cond_obj.get("pattern", cond_obj.get("value", match_pattern))).strip().lower()

        # Извлечение действия и параметров ретрансляции
        action_type = str(raw_route.get("actionType", raw_route.get("type", "ActionRelayServer")))
        relay_server = "smtp.barkol.ru"
        relay_port = 587
        auth_username = ""
        has_password = False
        ssl_mode = "StlsCommand"

        relay_obj = raw_route.get("relayServer", raw_route.get("action"))
        if isinstance(relay_obj, dict):
            relay_server = str(relay_obj.get("server", relay_obj.get("host", relay_server)))
            relay_port = int(relay_obj.get("port", relay_port))
            ssl_mode = str(relay_obj.get("mode", relay_obj.get("ssl", ssl_mode)))
            auth_info = relay_obj.get("authentication", relay_obj.get("auth", {}))
            if isinstance(auth_info, dict):
                auth_username = str(auth_info.get("userName", auth_info.get("user", "")))
                has_password = bool(auth_info.get("password") or auth_info.get("hasPassword"))
        else:
            relay_server = str(raw_route.get("server", raw_route.get("host", relay_server)))
            relay_port = int(raw_route.get("port", relay_port))
            auth_username = str(raw_route.get("userName", raw_route.get("user", "")))
            has_password = bool(raw_route.get("password"))

        return {
            "id": route_id,
            "isEnabled": is_enabled,
            "isActive": is_enabled,
            "description": description,
            "conditionType": condition_type,
            "matchPattern": match_pattern,
            "sender": match_pattern,
            "actionType": action_type,
            "server": relay_server,
            "port": relay_port,
            "userName": auth_username,
            "authUsername": auth_username,
            "hasPassword": has_password,
            "sslMode": ssl_mode,
            "raw": raw_route,
        }

    def get_route_for_sender(self, sender_email_or_login: str) -> Optional[Dict[str, Any]]:
        """Находит настроенное правило ретрансляции SMTP для конкретного отправителя (email или логин).

        Args:
            sender_email_or_login (str): Email сотрудника (например, 'a.administrator@barkol.ru') или логин.

        Returns:
            Optional[Dict[str, Any]]: Словарь параметров правила или None, если правило не найдено.
        """
        clean_target = sender_email_or_login.strip().lower()
        clean_user = clean_target.split("@")[0]
        routes = self.get_routes()

        for r in routes:
            patt = r.get("matchPattern", "").lower()
            sender = r.get("sender", "").lower()
            uname = r.get("userName", "").lower()
            desc = r.get("description", "").lower()

            if clean_target in (patt, sender, uname):
                return r
            if clean_user in (patt.split("@")[0], sender.split("@")[0], uname.split("@")[0]):
                return r
            if clean_target in desc or f"<{clean_target}>" in desc:
                return r

        return None

    def create_delivery_route(
        self,
        sender_email: str,
        password: str,
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
        auth_username: Optional[str] = None,
        is_enabled: bool = True,
        description: Optional[str] = None,
        ssl_mode: str = "StlsCommand",
    ) -> Dict[str, Any]:
        """Создает правило ретрансляции «Доставка SMTP» для исходящих писем сотрудника.

        При отправке писем с адреса sender_email Kerio Connect передает их на ретранслятор
        relay_host (по умолчанию smtp.barkol.ru:587) с авторизацией SMTP AUTH по полному адресу и паролю.

        Args:
            sender_email (str): Полный email отправителя (например, 'a.administrator@barkol.ru').
            password (str): Пароль учетной записи для авторизации на сервере ретрансляции.
            relay_host (Optional[str]): Адрес SMTP relay сервера (по умолчанию из настроек или 'smtp.barkol.ru').
            relay_port (Optional[int]): Порт SMTP relay (по умолчанию из настроек или 587).
            auth_username (Optional[str]): Имя пользователя для SMTP AUTH (по умолчанию равен sender_email).
            is_enabled (bool): Активность правила (по умолчанию True).
            description (Optional[str]): Пользовательское описание правила.
            ssl_mode (str): Режим шифрования ('StlsCommand' для STARTTLS на порту 587, 'SpecialPort' для SSL 465).

        Returns:
            Dict[str, Any]: Результат создания правила в Kerio Connect API.

        Raises:
            KerioValidationError: При отсутствии обязательных параметров (sender_email, password).
            KerioAPIError: При ошибке вызова API Kerio Connect.
        """
        clean_sender = sender_email.strip().lower()
        if not clean_sender or not password:
            raise KerioValidationError("Адрес отправителя (sender_email) и пароль обязательны для создания правила SMTP доставки.")

        if "@" not in clean_sender:
            clean_sender = f"{clean_sender}@barkol.ru"

        default_host = getattr(settings, "KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") if settings else "smtp.barkol.ru"
        default_port = getattr(settings, "KERIO_DEFAULT_SMTP_RELAY_PORT", 587) if settings else 587

        host = relay_host or default_host
        port = int(relay_port or default_port)
        auth_user = auth_username or clean_sender
        desc = description or f"Ретрансляция SMTP для {clean_sender}"

        # 1. Структура по официальной IDL спецификации Delivery.idl Kerio Connect
        route_payload: Dict[str, Any] = {
            "isEnabled": is_enabled,
            "description": desc,
            "conditionType": "ConditionSender",
            "matchPattern": clean_sender,
            "actionType": "ActionRelayServer",
            "relayServer": {
                "server": host,
                "port": port,
                "mode": ssl_mode,
                "authentication": {
                    "isEnabled": True,
                    "userName": auth_user,
                    "password": password,
                },
            },
        }

        # 2. Плоская альтернативная структура для обратной совместимости
        flat_route_payload: Dict[str, Any] = {
            "isEnabled": is_enabled,
            "description": desc,
            "sender": clean_sender,
            "matchPattern": clean_sender,
            "server": host,
            "port": port,
            "userName": auth_user,
            "password": password,
            "mode": ssl_mode,
        }

        # Последовательно пробуем методы добавления
        creation_methods = [
            ("Delivery.addDeliveryRouteList", {"routes": [route_payload]}),
            ("Delivery.addRouteList", {"routes": [route_payload]}),
            ("Delivery.addDeliveryRouteList", {"deliveryRoutes": [route_payload]}),
            ("Delivery.addDeliveryRoutes", {"routes": [route_payload]}),
            ("Delivery.addDeliveryRouteList", {"routes": [flat_route_payload]}),
            ("Delivery.addRouteList", {"routes": [flat_route_payload]}),
        ]

        last_error: Optional[Exception] = None
        for method_name, payload_params in creation_methods:
            try:
                result = self.client.call(method_name, params=payload_params)
                logger.info(f"[SmtpDeliveryManager] Успешно создано правило доставки SMTP через {method_name} для '{clean_sender}'")
                return {
                    "success": True,
                    "method": method_name,
                    "sender": clean_sender,
                    "relay_host": host,
                    "relay_port": port,
                    "auth_username": auth_user,
                    "result": result,
                }
            except KerioAPIError as exc:
                last_error = exc
                if "-32601" in str(exc):
                    # Method not found, продолжаем поиск
                    continue
                logger.warning(f"[SmtpDeliveryManager] Метод {method_name} вернул ошибку: {exc}")
            except Exception as exc:
                last_error = exc
                continue

        logger.error(f"[SmtpDeliveryManager] Не удалось создать правило SMTP доставки для '{clean_sender}': {last_error}")
        raise last_error or KerioAPIError(f"Не удалось создать правило SMTP доставки для {clean_sender}")

    def update_delivery_route(
        self,
        route_id: str,
        password: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
        auth_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Обновляет параметры существующего правила «Доставка SMTP».

        Args:
            route_id (str): Идентификатор правила в Kerio Connect.
            password (Optional[str]): Новый пароль авторизации SMTP AUTH.
            is_enabled (Optional[bool]): Флаг активности правила.
            relay_host (Optional[str]): Адрес сервера ретрансляции.
            relay_port (Optional[int]): Порт сервера ретрансляции.
            auth_username (Optional[str]): Имя пользователя для SMTP AUTH.

        Returns:
            Dict[str, Any]: Результат выполнения операции в API.

        Raises:
            KerioAPIError: При ошибке вызова API Kerio Connect.
        """
        route_data: Dict[str, Any] = {"id": route_id}
        if is_enabled is not None:
            route_data["isEnabled"] = is_enabled

        relay_obj: Dict[str, Any] = {}
        if relay_host:
            relay_obj["server"] = relay_host
        if relay_port:
            relay_obj["port"] = int(relay_port)

        auth_obj: Dict[str, Any] = {}
        if auth_username:
            auth_obj["userName"] = auth_username
        if password:
            auth_obj["password"] = password

        if auth_obj:
            auth_obj["isEnabled"] = True
            relay_obj["authentication"] = auth_obj

        if relay_obj:
            route_data["relayServer"] = relay_obj

        update_methods = [
            ("Delivery.setDeliveryRoute", {"id": route_id, "route": route_data}),
            ("Delivery.setRoute", {"id": route_id, "route": route_data}),
            ("Delivery.setDeliveryRoute", {"deliveryRoute": route_data}),
        ]

        for method_name, params in update_methods:
            try:
                result = self.client.call(method_name, params=params)
                logger.info(f"[SmtpDeliveryManager] Успешно обновлено правило SMTP доставки {route_id} через {method_name}")
                return {"success": True, "result": result}
            except KerioAPIError as exc:
                if "-32601" in str(exc):
                    continue
                logger.warning(f"[SmtpDeliveryManager] Ошибка обновления {method_name}: {exc}")

        return {"success": False, "id": route_id}

    def set_route_password_for_sender(
        self,
        sender_email_or_login: str,
        new_password: str,
    ) -> bool:
        """Обновляет пароль авторизации SMTP AUTH для правила указанного отправителя.

        Args:
            sender_email_or_login (str): Email или логин сотрудника.
            new_password (str): Новый пароль учетной записи.

        Returns:
            bool: True, если пароль успешно обновлен в правиле, иначе False.
        """
        route = self.get_route_for_sender(sender_email_or_login)
        if not route or not route.get("id"):
            logger.info(f"[SmtpDeliveryManager] Правило доставки SMTP для '{sender_email_or_login}' не найдено, создаем заново...")
            try:
                self.create_delivery_route(
                    sender_email=sender_email_or_login,
                    password=new_password,
                )
                return True
            except Exception as exc:
                logger.warning(f"[SmtpDeliveryManager] Не удалось создать правило при обновлении пароля: {exc}")
                return False

        res = self.update_delivery_route(route_id=route["id"], password=new_password)
        return bool(res.get("success"))

    def remove_delivery_route(self, route_id: str) -> Dict[str, Any]:
        """Удаляет правило ретрансляции «Доставка SMTP» по его ID.

        Args:
            route_id (str): Идентификатор правила в Kerio Connect.

        Returns:
            Dict[str, Any]: Результат удаления.

        Raises:
            KerioAPIError: При ошибке выполнения вызова API.
        """
        delete_methods = [
            ("Delivery.removeDeliveryRouteList", {"ids": [route_id]}),
            ("Delivery.removeRouteList", {"ids": [route_id]}),
            ("Delivery.removeDeliveryRoutes", {"ids": [route_id]}),
        ]

        for method_name, params in delete_methods:
            try:
                result = self.client.call(method_name, params=params)
                logger.info(f"[SmtpDeliveryManager] Удалено правило SMTP доставки {route_id} через {method_name}")
                return {"success": True, "result": result}
            except KerioAPIError as exc:
                if "-32601" in str(exc):
                    continue
                logger.warning(f"[SmtpDeliveryManager] Ошибка удаления правила {method_name}: {exc}")

        return {"success": False, "id": route_id}

    def remove_route_for_sender(self, sender_email_or_login: str) -> bool:
        """Находит и удаляет правило доставки SMTP для указанного отправителя.

        Args:
            sender_email_or_login (str): Email или логин сотрудника.

        Returns:
            bool: True, если правило найдено и удалено, False в противном случае.
        """
        route = self.get_route_for_sender(sender_email_or_login)
        if not route or not route.get("id"):
            return False

        res = self.remove_delivery_route(route["id"])
        return bool(res.get("success"))

    def toggle_route_for_sender(self, sender_email_or_login: str, is_enabled: bool) -> bool:
        """Переключает активность правила доставки SMTP для указанного отправителя.

        Args:
            sender_email_or_login (str): Email или логин сотрудника.
            is_enabled (bool): Флаг активности правила.

        Returns:
            bool: True при успешном обновлении, иначе False.
        """
        route = self.get_route_for_sender(sender_email_or_login)
        if not route or not route.get("id"):
            return False

        res = self.update_delivery_route(route["id"], is_enabled=is_enabled)
        return bool(res.get("success"))
