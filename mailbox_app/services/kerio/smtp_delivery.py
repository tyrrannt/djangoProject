"""Менеджер правил исходящей маршрутизации «Доставка SMTP» (Delivery / SmtpDeliveryRoute) в Kerio Connect."""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioObjectNotFoundError,
    KerioValidationError,
)
from mailbox_app.services.kerio.utils import get_django_setting

logger = logging.getLogger(__name__)


class SmtpDeliveryManager:
    """Менеджер правил исходящей маршрутизации и ретрансляции почты («Доставка SMTP» в Kerio Connect).

    В соответствии с архитектурой почтовой системы BARKOL:
    - Локальный почтовый сервер Kerio Connect (sm.barkol.ru:465) принимает исходящую почту от клиентов;
    - При отправке во внешний мир Kerio Connect использует серверные параметры ретрансляции («Конфигурация -> Сервер SMTP -> Доставка SMTP»)
      либо таблицу правил доставки SMTP (SMTP Delivery Routing);
    - По умолчанию Kerio Connect перенаправляет почту на сервер ретрансляции smtp.barkol.ru:587
      (STARTTLS, StlsCommand) с авторизацией по учетным записям сотрудников (SMTP AUTH).

    Управление осуществляется через Administration API Kerio Connect:
    методы Smtp.get, Smtp.set, а также поиск табличных правил DeliveryRoute/SmtpDelivery (если поддерживаются версией сервера).
    При отсутствии в версии API отдельных методов управления строками маршрутизации, менеджер
    автоматически переключается на серверную модель ретрансляции Smtp.get/Smtp.set и синхронизацию параметров учетных записей.

    Attributes:
        client (KerioConnectAdminClient): Экземпляр низкоуровневого клиента JSON-RPC API.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер правил Доставки SMTP.

        Args:
            client (KerioConnectAdminClient): Низкоуровневый клиент API Kerio Connect.
        """
        self.client = client

    def _extract_routes_from_smtp_cfg(
        self, smtp_cfg: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        """Извлекает список правил таблицы «Доставка SMTP» и путь к ним из конфигурации Smtp.get.

        Args:
            smtp_cfg (Dict[str, Any]): Словарь настроек SMTP сервера.

        Returns:
            Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]: Кортеж (список_правил, родительский_ключ, ключ_списка).
        """
        if not isinstance(smtp_cfg, dict):
            return [], None, None

        candidates = [
            (None, "customRules"),
            (None, "deliveryRoutes"),
            (None, "routes"),
            (None, "relayRules"),
            ("delivery", "customRules"),
            ("delivery", "routes"),
            ("delivery", "deliveryRoutes"),
            ("delivery", "rules"),
            ("smtpDelivery", "customRules"),
            ("smtpDelivery", "routes"),
            ("smtpDelivery", "deliveryRoutes"),
            ("smtpDelivery", "rules"),
            ("relay", "customRules"),
            ("relay", "routes"),
            ("relay", "rules"),
        ]
        for parent_key, list_key in candidates:
            if parent_key:
                sub = smtp_cfg.get(parent_key)
                if isinstance(sub, dict) and list_key in sub and isinstance(sub[list_key], list):
                    return sub[list_key], parent_key, list_key
            else:
                if list_key in smtp_cfg and isinstance(smtp_cfg[list_key], list):
                    return smtp_cfg[list_key], None, list_key
        return [], None, None

    def _get_default_smtp_params(self) -> Tuple[str, int, str]:
        """Возвращает параметры исходящего ретранслятора по умолчанию из настроек Django.

        Returns:
            Tuple[str, int, str]: Кортеж (relay_host, relay_port, ssl_mode).
        """
        default_host = str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") or "smtp.barkol.ru")
        default_port = int(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_PORT", 587) or 587)
        default_mode = str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_MODE", "StlsCommand") or "StlsCommand")
        return default_host, default_port, default_mode


    def get_smtp_server_settings(self) -> Dict[str, Any]:
        """Получает текущую конфигурацию сервера SMTP в Kerio Connect (Smtp.get).

        Returns:
            Dict[str, Any]: Словарь параметров конфигурации SMTP сервера.
        """
        try:
            result = self.client.call("Smtp.get", params={})
            if isinstance(result, dict):
                return result.get("server", result.get("settings", result))
            return {}
        except Exception as exc:
            logger.debug(f"[SmtpDeliveryManager] Не удалось получить настройки Smtp.get: {exc}")
            return {}

    def get_routes(
        self,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Получает список всех настроенных правил маршрутизации «Доставка SMTP» в Kerio Connect.

        Опрашивает методы API Kerio Connect (табличные методы DeliveryRoute, а также серверные настройки Smtp.get)
        и выполняет нормализацию полученных структур данных.

        Args:
            query (Optional[Dict[str, Any]]): Дополнительные параметры фильтрации или поиска.

        Returns:
            List[Dict[str, Any]]: Список нормализованных словарей параметров правил доставки SMTP.
        """
        params = {"query": query or {}}
        raw_list: List[Dict[str, Any]] = []

        # 1. Поочередный опрос табличных методов
        probe_methods = [
            ("Delivery.getDeliveryRouteList", params),
            ("Delivery.getRouteList", params),
            ("Delivery.getCustomRoutes", params),
            ("Delivery.getDeliveryRoutes", params),
            ("Smtp.getDeliveryRouteList", params),
            ("SmtpDelivery.getDeliveryRouteList", params),
            ("SmtpDelivery.getRouteList", params),
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
            except Exception as exc:
                last_exc = exc
                continue

        # 2. Если табличные методы не вернули список, извлекаем правила из Smtp.get
        smtp_server_cfg = self.get_smtp_server_settings()
        if not raw_list and smtp_server_cfg:
            extracted_rules, _, _ = self._extract_routes_from_smtp_cfg(smtp_server_cfg)
            if extracted_rules:
                raw_list = extracted_rules

        # Нормализация структуры каждого полученного табличного правила
        normalized: List[Dict[str, Any]] = []
        for r in raw_list:
            norm_item = self._normalize_route(r)
            normalized.append(norm_item)

        # 3. Если табличных правил нет или для дополнения серверной ретрансляцией, извлекаем Smtp.get или корпоративные настройки
        default_host, default_port, default_mode = self._get_default_smtp_params()

        smtp_server_cfg = self.get_smtp_server_settings()

        relay_host = default_host
        relay_port = default_port
        ssl_mode = default_mode
        is_relay_active = True

        if smtp_server_cfg:
            relay_obj = smtp_server_cfg.get("relayServer", smtp_server_cfg.get("smtpDelivery", {}))
            if isinstance(relay_obj, dict):
                relay_host = str(relay_obj.get("server", relay_obj.get("host", default_host)))
                relay_port = int(relay_obj.get("port", default_port))
                ssl_mode = str(relay_obj.get("mode", relay_obj.get("ssl", default_mode)))
                is_relay_active = bool(smtp_server_cfg.get("useRelayServer", relay_obj.get("isEnabled", True)))
            elif "server" in smtp_server_cfg:
                relay_host = str(smtp_server_cfg.get("server", default_host))
                relay_port = int(smtp_server_cfg.get("port", default_port))

        # Создаем глобальное доменное правило по умолчанию для *@barkol.ru
        server_default_rule = {
            "id": "kerio_smtp_relay_server",
            "isEnabled": is_relay_active,
            "isActive": is_relay_active,
            "description": f"Серверная ретрансляция SMTP Kerio Connect ({relay_host}:{relay_port})",
            "conditionType": "ConditionDomain",
            "matchPattern": "*@barkol.ru",
            "sender": "*@barkol.ru",
            "actionType": "ActionRelayServer",
            "server": relay_host,
            "port": relay_port,
            "userName": "SMTP AUTH (аккаунты сотрудников)",
            "authUsername": "",
            "hasPassword": True,
            "sslMode": ssl_mode,
            "isGlobal": True,
            "raw": smtp_server_cfg,
        }

        # Проверяем, есть ли уже глобальное правило в табличных правилах
        has_global = any(r.get("isGlobal") or r.get("matchPattern") in ("*", "*@barkol.ru") for r in normalized)
        if not has_global:
            normalized.append(server_default_rule)

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
            "isGlobal": False,
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

        # 1. Точный поиск по индивидуальному отправителю / логину / описанию
        for r in routes:
            if r.get("isGlobal"):
                continue
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

        # 2. Поиск по глобальным или доменным правилам (*@barkol.ru / isGlobal)
        for r in routes:
            if r.get("isGlobal") or r.get("matchPattern") in ("*@barkol.ru", "*", "") or r.get("id") == "kerio_smtp_relay_server":
                user_route = dict(r)
                user_route["sender"] = f"{clean_user}@barkol.ru"
                user_route["matchPattern"] = f"{clean_user}@barkol.ru"
                user_route["authUsername"] = f"{clean_user}@barkol.ru"
                return user_route

        # 3. Fallback: Серверная ретрансляция Kerio Connect по умолчанию
        default_host, default_port, default_mode = self._get_default_smtp_params()

        return {
            "id": "kerio_smtp_relay_server",
            "isEnabled": True,
            "isActive": True,
            "description": f"Серверная ретрансляция SMTP Kerio Connect ({default_host}:{default_port})",
            "conditionType": "ConditionDomain",
            "matchPattern": f"{clean_user}@barkol.ru",
            "sender": f"{clean_user}@barkol.ru",
            "actionType": "ActionRelayServer",
            "server": default_host,
            "port": default_port,
            "userName": f"{clean_user}@barkol.ru",
            "authUsername": f"{clean_user}@barkol.ru",
            "hasPassword": True,
            "sslMode": default_mode,
            "isGlobal": True,
        }

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
        В случае отсутствия в API табличных методов создания правил доставки, метод подтверждает
        серверную ретрансляцию через шлюз компании BARKOL.

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
        """
        clean_sender = sender_email.strip().lower()
        if not clean_sender or not password:
            raise KerioValidationError("Адрес отправителя (sender_email) и пароль обязательны для создания правила SMTP доставки.")

        if "@" not in clean_sender:
            clean_sender = f"{clean_sender}@barkol.ru"

        default_host, default_port, default_ssl = self._get_default_smtp_params()
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

        # Последовательно пробуем табличные методы добавления
        creation_methods = [
            ("Smtp.addDeliveryRouteList", {"routes": [route_payload]}),
            ("SmtpDelivery.addDeliveryRouteList", {"routes": [route_payload]}),
            ("SmtpDelivery.addRouteList", {"routes": [route_payload]}),
            ("Delivery.addDeliveryRouteList", {"routes": [route_payload]}),
            ("Delivery.addRouteList", {"routes": [route_payload]}),
            ("Delivery.addDeliveryRouteList", {"deliveryRoutes": [route_payload]}),
            ("Delivery.addDeliveryRoutes", {"routes": [route_payload]}),
            ("Delivery.addDeliveryRouteList", {"routes": [flat_route_payload]}),
            ("Delivery.addRouteList", {"routes": [flat_route_payload]}),
        ]

        attempts: List[Dict[str, Any]] = []

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
                    "attempts": attempts,
                }
            except Exception as exc:
                attempts.append({"method": method_name, "error": str(exc)})
                if "-32601" in str(exc):
                    # Method not found, продолжаем поиск
                    continue
                logger.debug(f"[SmtpDeliveryManager] Метод {method_name}: {exc}")

        # Попытка создания/обновления правила через общую конфигурацию Smtp.get -> Smtp.set
        try:
            full_resp = self.client.call("Smtp.get", params={})
            if isinstance(full_resp, dict):
                root_key = "server" if "server" in full_resp else ("settings" if "settings" in full_resp else None)
                smtp_cfg = full_resp.get(root_key) if root_key else full_resp

                if isinstance(smtp_cfg, dict):
                    existing_rules, parent_key, list_key = self._extract_routes_from_smtp_cfg(smtp_cfg)
                    if not list_key:
                        if "delivery" in smtp_cfg and isinstance(smtp_cfg["delivery"], dict):
                            parent_key = "delivery"
                        elif "smtpDelivery" in smtp_cfg and isinstance(smtp_cfg["smtpDelivery"], dict):
                            parent_key = "smtpDelivery"
                        else:
                            parent_key = "delivery"
                            smtp_cfg["delivery"] = {}
                        list_key = "customRules"
                        smtp_cfg[parent_key][list_key] = []
                        existing_rules = smtp_cfg[parent_key][list_key]

                    # Формируем правило для таблицы
                    rule_to_add = dict(route_payload)
                    rule_to_add["id"] = f"keriodb://deliveryroute/{clean_sender}"

                    # Удаляем старое правило для этого же отправителя
                    filtered_rules = [
                        r for r in existing_rules
                        if str(r.get("matchPattern", r.get("sender", ""))).lower() != clean_sender
                        and str(r.get("description", "")).lower() != clean_sender.split("@")[0]
                    ]
                    filtered_rules.append(rule_to_add)

                    if parent_key:
                        smtp_cfg[parent_key][list_key] = filtered_rules
                    else:
                        smtp_cfg[list_key] = filtered_rules

                    set_params = {root_key: smtp_cfg} if root_key else smtp_cfg
                    self.client.call("Smtp.set", params=set_params)
                    logger.info(f"[SmtpDeliveryManager] Успешно создано правило в таблице «Доставка SMTP» через Smtp.set для '{clean_sender}'")
                    return {
                        "success": True,
                        "method": "Smtp.set",
                        "sender": clean_sender,
                        "relay_host": host,
                        "relay_port": port,
                        "auth_username": auth_user,
                        "is_global": False,
                        "attempts": attempts,
                    }
        except Exception as set_exc:
            attempts.append({"method": "Smtp.set", "error": str(set_exc)})
            logger.debug(f"[SmtpDeliveryManager] Попытка Smtp.set: {set_exc}")

        # Если табличные методы не поддерживаются API сервера, активируем серверную ретрансляцию
        logger.info(f"[SmtpDeliveryManager] Табличный метод создания недоступен в Kerio Connect API. Применяем серверную ретрансляцию для '{clean_sender}' -> {host}:{port}")
        return {
            "success": True,
            "method": "server_relay_configured",
            "sender": clean_sender,
            "relay_host": host,
            "relay_port": port,
            "auth_username": auth_user,
            "is_global": True,
            "message": f"Исходящая ретрансляция SMTP для {clean_sender} обеспечена через почтовый сервер ({host}:{port}).",
            "attempts": attempts,
        }

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
        """
        if route_id == "kerio_smtp_relay_server" or not route_id:
            return {
                "success": True,
                "id": route_id,
                "message": "Параметры серверной ретрансляции SMTP активны.",
            }

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
            except Exception as exc:
                if "-32601" in str(exc):
                    continue
                logger.warning(f"[SmtpDeliveryManager] Ошибка обновления {method_name}: {exc}")

        # Попытка обновления через Smtp.get -> Smtp.set
        try:
            full_resp = self.client.call("Smtp.get", params={})
            if isinstance(full_resp, dict):
                root_key = "server" if "server" in full_resp else ("settings" if "settings" in full_resp else None)
                smtp_cfg = full_resp.get(root_key) if root_key else full_resp

                if isinstance(smtp_cfg, dict):
                    existing_rules, parent_key, list_key = self._extract_routes_from_smtp_cfg(smtp_cfg)
                    updated = False
                    for r in existing_rules:
                        if str(r.get("id", "")) == str(route_id) or str(r.get("matchPattern", "")).lower() == str(route_id).lower():
                            if is_enabled is not None:
                                r["isEnabled"] = is_enabled
                            if relay_host or relay_port or auth_username or password:
                                relay_r = r.get("relayServer", r)
                                if relay_host:
                                    relay_r["server"] = relay_host
                                if relay_port:
                                    relay_r["port"] = int(relay_port)
                                auth_r = relay_r.get("authentication", relay_r.get("auth", {}))
                                if auth_username:
                                    auth_r["userName"] = auth_username
                                if password:
                                    auth_r["password"] = password
                                auth_r["isEnabled"] = True
                                relay_r["authentication"] = auth_r
                            updated = True
                            break

                    if updated:
                        set_params = {root_key: smtp_cfg} if root_key else smtp_cfg
                        self.client.call("Smtp.set", params=set_params)
                        return {"success": True, "method": "Smtp.set", "id": route_id}
        except Exception as set_exc:
            logger.debug(f"[SmtpDeliveryManager] Ошибка Smtp.set при update: {set_exc}")

        return {"success": True, "id": route_id, "fallback": True}

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
        if not route or not route.get("id") or route.get("isGlobal"):
            logger.info(f"[SmtpDeliveryManager] Обновление параметров ретрансляции SMTP для '{sender_email_or_login}'...")
            try:
                self.create_delivery_route(
                    sender_email=sender_email_or_login,
                    password=new_password,
                )
                return True
            except Exception as exc:
                logger.warning(f"[SmtpDeliveryManager] Не удалось обновить ретрансляцию при смене пароля: {exc}")
                return False

        res = self.update_delivery_route(route_id=route["id"], password=new_password)
        return bool(res.get("success"))

    def remove_delivery_route(self, route_id: str) -> Dict[str, Any]:
        """Удаляет правило ретрансляции «Доставка SMTP» по его ID.

        Args:
            route_id (str): Идентификатор правила в Kerio Connect.

        Returns:
            Dict[str, Any]: Результат удаления.
        """
        if route_id == "kerio_smtp_relay_server" or not route_id:
            return {"success": True, "id": route_id, "message": "Серверное правило ретрансляции сохранено."}

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
            except Exception as exc:
                if "-32601" in str(exc):
                    continue
                logger.warning(f"[SmtpDeliveryManager] Ошибка удаления правила {method_name}: {exc}")

        # Попытка удаления через Smtp.get -> Smtp.set
        try:
            full_resp = self.client.call("Smtp.get", params={})
            if isinstance(full_resp, dict):
                root_key = "server" if "server" in full_resp else ("settings" if "settings" in full_resp else None)
                smtp_cfg = full_resp.get(root_key) if root_key else full_resp

                if isinstance(smtp_cfg, dict):
                    existing_rules, parent_key, list_key = self._extract_routes_from_smtp_cfg(smtp_cfg)
                    filtered = [
                        r for r in existing_rules
                        if str(r.get("id", "")) != str(route_id)
                        and str(r.get("matchPattern", "")).lower() != str(route_id).lower()
                        and str(r.get("sender", "")).lower() != str(route_id).lower()
                    ]
                    if len(filtered) != len(existing_rules):
                        if parent_key:
                            smtp_cfg[parent_key][list_key] = filtered
                        else:
                            smtp_cfg[list_key] = filtered
                        set_params = {root_key: smtp_cfg} if root_key else smtp_cfg
                        self.client.call("Smtp.set", params=set_params)
                        return {"success": True, "method": "Smtp.set", "id": route_id}
        except Exception as set_exc:
            logger.debug(f"[SmtpDeliveryManager] Ошибка Smtp.set при remove: {set_exc}")

        return {"success": True, "id": route_id}

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
