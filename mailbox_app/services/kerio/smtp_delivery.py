"""Менеджер правил исходящей маршрутизации «Доставка SMTP» (RelayDeliveryRule / Smtp.getRelayDeliveryRuleList) в Kerio Connect."""

import logging
import smtplib
import ssl
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

    В соответствии с официальной спецификацией Kerio Connect Administration API (Smtp.idl):
    - Управление правилами ретрансляции исходящей почты («Конфигурация -> Сервер SMTP -> Доставка SMTP»)
      осуществляется через методы `Smtp.getRelayDeliveryRuleList` и `Smtp.setRelayDeliveryRuleList`.
    - Каждое правило представляет собой структуру `RelayDeliveryRule`:
        * `id`: глобальный идентификатор правила в Kerio Connect (read-only, назначается сервером);
        * `isEnabled`: флаг активности правила (bool);
        * `description`: описание правила (строка);
        * `hostName`: адрес SMTP relay сервера (например, smtp.barkol.ru);
        * `port`: порт SMTP relay (например, 587);
        * `authentication`: структура `RelayAuthentication` {
              isRequired: bool,
              userName: str,
              password: str,
              authType: "Auth" | "Pop3Based"
          };
        * `condition`: структура `RelayRuleCondition` {
              test: "RelayCondSender" | "RelayCondRecipient" | "RelayCondNone",
              comparator: "RelayCompEqual" | "RelayCompNotEqual",
              pattern: str
          }.

    Менеджер реализует:
    - Получение списка правил ретрансляции: `get_relay_rules()` и `get_routes()`;
    - Поиск персонального правила для отправителя: `get_route_for_sender()`;
    - Создание/добавление индивидуального правила: `create_delivery_route()` по модели «read-modify-write» с обязательной верификацией;
    - Обновление параметров и пароля в правиле: `update_delivery_route()` и `set_route_password_for_sender()`;
    - Удаление индивидуальных правил: `remove_delivery_route()` и `remove_route_for_sender()`;
    - Переключение активности: `toggle_route_for_sender()`;
    - Прямую верификацию SMTP AUTH через SMTP-соединение: `verify_smtp_auth()`.

    Attributes:
        client (KerioConnectAdminClient): Экземпляр низкоуровневого клиента JSON-RPC API.
    """

    GET_METHOD = "Smtp.getRelayDeliveryRuleList"
    SET_METHOD = "Smtp.setRelayDeliveryRuleList"

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер правил Доставки SMTP.

        Args:
            client (KerioConnectAdminClient): Низкоуровневый клиент API Kerio Connect.
        """
        self.client = client

    def _get_default_smtp_params(self) -> Tuple[str, int, str]:
        """Возвращает параметры исходящего ретранслятора по умолчанию из настроек Django.

        Returns:
            Tuple[str, int, str]: Кортеж (relay_host, relay_port, ssl_mode).
        """
        default_host = str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") or "smtp.barkol.ru")
        default_port = int(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_PORT", 587) or 587)
        default_mode = str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_MODE", "StlsCommand") or "StlsCommand")
        return default_host, default_port, default_mode

    def get_relay_rules(self) -> Optional[List[Dict[str, Any]]]:
        """Получает список правил ретрансляции напрямую через метод API Smtp.getRelayDeliveryRuleList.

        Returns:
            Optional[List[Dict[str, Any]]]: Список сырых структур RelayDeliveryRule или None при отсутствии метода (-32601).

        Raises:
            KerioAPIError: При ошибке обращения к API Kerio Connect (за исключением отсутствия метода -32601).
        """
        try:
            result = self.client.call(self.GET_METHOD, params={})
            if isinstance(result, dict):
                if "list" in result and isinstance(result["list"], list):
                    return result["list"]
                elif "rules" in result and isinstance(result["rules"], list):
                    return result["rules"]
                elif "smtp" in result and isinstance(result["smtp"], dict) and "deliveryRules" in result["smtp"]:
                    return result["smtp"]["deliveryRules"]
                elif "deliveryRules" in result and isinstance(result["deliveryRules"], list):
                    return result["deliveryRules"]
                return []
            elif isinstance(result, list):
                return result
        except Exception as exc:
            err_msg = str(exc)
            logger.debug(f"[SmtpDeliveryManager] {self.GET_METHOD}: {err_msg}")
            # Если метод не поддерживается сервером (-32601), возвращаем None для fallback
            if "-32601" in err_msg or "Method not found" in err_msg:
                return None
            # При реальной ошибке сети или авторизации пробрасываем исключение во избежание повреждения списка правил
            raise KerioAPIError(f"Ошибка получения списка правил Доставки SMTP ({self.GET_METHOD}): {err_msg}") from exc
        return []

    def get_routes(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Получает список всех настроенных правил маршрутизации «Доставка SMTP» в Kerio Connect.

        Опрашивает методы API Kerio Connect (официальный `Smtp.getRelayDeliveryRuleList`,
        а при необходимости fallback-методы) и выполняет нормализацию полученных структур данных.

        Args:
            query (Optional[Dict[str, Any]]): Дополнительные параметры фильтрации (для обратной совместимости).

        Returns:
            List[Dict[str, Any]]: Список нормализованных словарей параметров правил доставки SMTP.
        """
        try:
            raw_list = self.get_relay_rules()
        except Exception as exc:
            logger.warning(f"[SmtpDeliveryManager] Не удалось получить правила через {self.GET_METHOD}: {exc}")
            raw_list = None

        # Fallback для устаревших версий или нестандартных ответов
        if raw_list is None:
            raw_list = self._fallback_get_routes(query)

        # Нормализация структуры каждого полученного правила
        normalized: List[Dict[str, Any]] = []
        for r in (raw_list or []):
            norm_item = self._normalize_route(r)
            normalized.append(norm_item)

        return normalized

    def _normalize_route(self, raw_route: Dict[str, Any]) -> Dict[str, Any]:
        """Нормализует сырой объект правила RelayDeliveryRule в стандартный плоский словарь.

        Args:
            raw_route (Dict[str, Any]): Исходный словарь из ответа API Kerio Connect.

        Returns:
            Dict[str, Any]: Стандартизированный словарь параметров правила доставки.
        """
        route_id = str(raw_route.get("id", ""))
        is_enabled = bool(raw_route.get("isEnabled", raw_route.get("isActive", True)))
        description = str(raw_route.get("description", raw_route.get("name", "")))

        # 1. Извлечение условия condition (структура RelayRuleCondition: test, comparator, pattern)
        cond_obj = raw_route.get("condition")
        condition_test = ""
        condition_comp = "RelayCompEqual"
        match_pattern = ""

        if isinstance(cond_obj, dict):
            condition_test = str(cond_obj.get("test", cond_obj.get("type", "")))
            condition_comp = str(cond_obj.get("comparator", "RelayCompEqual"))
            match_pattern = str(cond_obj.get("pattern", cond_obj.get("value", ""))).strip().lower()
        else:
            condition_test = str(raw_route.get("conditionType", raw_route.get("matchType", "RelayCondSender")))
            match_pattern = str(
                raw_route.get("matchPattern")
                or raw_route.get("sender")
                or raw_route.get("pattern")
                or ""
            ).strip().lower()

        # 2. Извлечение параметров хоста и порта (hostName / port)
        relay_server = str(
            raw_route.get("hostName")
            or raw_route.get("server")
            or (raw_route.get("relayServer", {}).get("server") if isinstance(raw_route.get("relayServer"), dict) else "")
            or "smtp.barkol.ru"
        )
        relay_port = int(
            raw_route.get("port")
            or (raw_route.get("relayServer", {}).get("port") if isinstance(raw_route.get("relayServer"), dict) else 587)
            or 587
        )

        # 3. Извлечение параметров аутентификации authentication (структура RelayAuthentication: isRequired, userName, password, authType)
        auth_username = ""
        has_password = False
        auth_obj = raw_route.get("authentication")
        if isinstance(auth_obj, dict):
            auth_username = str(auth_obj.get("userName", auth_obj.get("user", "")))
            has_password = bool(auth_obj.get("password") or auth_obj.get("hasPassword") or auth_obj.get("isRequired"))
        else:
            relay_obj = raw_route.get("relayServer")
            if isinstance(relay_obj, dict) and isinstance(relay_obj.get("authentication"), dict):
                sub_auth = relay_obj["authentication"]
                auth_username = str(sub_auth.get("userName", ""))
                has_password = bool(sub_auth.get("password") or sub_auth.get("hasPassword") or sub_auth.get("isEnabled"))
            else:
                auth_username = str(raw_route.get("userName", raw_route.get("authUsername", "")))
                has_password = bool(raw_route.get("password") or raw_route.get("hasPassword"))

        # Определение признака глобальности/серверности правила
        is_global = bool(
            condition_test in ("RelayCondNone", "ConditionDomain")
            or match_pattern in ("*", "*@barkol.ru", "")
            or raw_route.get("isGlobal", False)
        )

        return {
            "id": route_id,
            "isEnabled": is_enabled,
            "isActive": is_enabled,
            "description": description,
            "conditionType": condition_test or "RelayCondSender",
            "conditionComparator": condition_comp,
            "matchPattern": match_pattern,
            "sender": match_pattern,
            "actionType": "ActionRelayServer",
            "server": relay_server,
            "port": relay_port,
            "userName": auth_username,
            "authUsername": auth_username,
            "hasPassword": has_password,
            "sslMode": "StlsCommand",
            "isGlobal": is_global,
            "raw": raw_route,
        }

    def get_route_for_sender(self, sender_email_or_login: str) -> Optional[Dict[str, Any]]:
        """Находит настроенное правило ретрансляции SMTP для конкретного отправителя (email или логин).

        Сначала выполняет строгий поиск персонального правила (RelayCondSender).
        Если персонального правила нет — возвращает найденное серверное правило или синтетический fallback (isGlobal=True).

        Args:
            sender_email_or_login (str): Email сотрудника (например, a.administrator@barkol.ru) или логин.

        Returns:
            Optional[Dict[str, Any]]: Словарь параметров правила или серверный fallback с флагом isGlobal=True.
        """
        clean_target = sender_email_or_login.strip().lower()
        clean_user = clean_target.split("@")[0]
        target_email = f"{clean_user}@barkol.ru" if "@" not in clean_target else clean_target

        routes = self.get_routes()

        # 1. Строгий поиск по индивидуальному правилу отправителя
        for r in routes:
            if r.get("isGlobal"):
                continue
            patt = str(r.get("matchPattern", "")).lower()
            sender = str(r.get("sender", "")).lower()
            uname = str(r.get("userName", "")).lower()
            desc = str(r.get("description", "")).lower()

            if target_email in (patt, sender, uname) or clean_target in (patt, sender, uname):
                return r
            if clean_user in (patt.split("@")[0], sender.split("@")[0], uname.split("@")[0]):
                return r
            if target_email in desc or f"<{target_email}>" in desc:
                return r

        # 2. Поиск по глобальным/серверным правилам (*@barkol.ru / isGlobal)
        for r in routes:
            if r.get("isGlobal") or r.get("matchPattern") in ("*@barkol.ru", "*", "") or r.get("id") == "kerio_smtp_relay_server":
                return r

        # 3. Серверный fallback по умолчанию (isGlobal=True)
        default_host, default_port, default_mode = self._get_default_smtp_params()
        return {
            "id": "kerio_smtp_relay_server",
            "isEnabled": True,
            "isActive": True,
            "description": f"Серверная ретрансляция SMTP Kerio Connect ({default_host}:{default_port})",
            "conditionType": "RelayCondNone",
            "conditionComparator": "RelayCompEqual",
            "matchPattern": "*@barkol.ru",
            "sender": "*@barkol.ru",
            "actionType": "ActionRelayServer",
            "server": default_host,
            "port": default_port,
            "userName": "SMTP AUTH (аккаунты сотрудников)",
            "authUsername": "",
            "hasPassword": True,
            "sslMode": default_mode,
            "isGlobal": True,
            "raw": {},
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
        """Создает или перезаписывает правило ретрансляции «Доставка SMTP» для исходящих писем сотрудника.

        Использует официальный метод Kerio Connect API `Smtp.setRelayDeliveryRuleList`:
        1. Запрашивает текущий список правил через `Smtp.getRelayDeliveryRuleList`;
        2. Формирует структуру `RelayDeliveryRule` с SMTP AUTH и условием `RelayCondSender`;
        3. Обновляет существующее правило для отправителя или добавляет новое в список;
        4. Отправляет обновленный список через `Smtp.setRelayDeliveryRuleList`;
        5. Верифицирует факт создания записи в таблице Kerio Connect.

        Args:
            sender_email (str): Полный email отправителя (например, a.administrator@barkol.ru).
            password (str): Пароль учетной записи для авторизации на сервере ретрансляции.
            relay_host (Optional[str]): Адрес SMTP relay сервера (по умолчанию из настроек или smtp.barkol.ru).
            relay_port (Optional[int]): Порт SMTP relay (по умолчанию из настроек или 587).
            auth_username (Optional[str]): Имя пользователя для SMTP AUTH (по умолчанию равен sender_email).
            is_enabled (bool): Активность правила (по умолчанию True).
            description (Optional[str]): Пользовательское описание правила.
            ssl_mode (str): Режим шифрования (сохранен для обратной совместимости).

        Returns:
            Dict[str, Any]: Результат создания правила в Kerio Connect API.

        Raises:
            KerioValidationError: При отсутствии обязательных параметров (sender_email, password).
            KerioAPIError: При ошибке API или неудачной верификации создания правила.
        """
        clean_sender = sender_email.strip().lower()
        if not clean_sender or not password:
            raise KerioValidationError(
                "Адрес отправителя (sender_email) и пароль обязательны для создания правила SMTP доставки."
            )

        if "@" not in clean_sender:
            clean_sender = f"{clean_sender}@barkol.ru"

        default_host, default_port, _ = self._get_default_smtp_params()
        host = relay_host or default_host
        port = int(relay_port or default_port)
        auth_user = auth_username or clean_sender
        desc = description or f"Ретрансляция SMTP для {clean_sender}"

        # Формирование структуры RelayDeliveryRule в точном соответствии с Smtp.idl Kerio Connect
        new_rule: Dict[str, Any] = {
            "isEnabled": is_enabled,
            "description": desc,
            "hostName": host,
            "port": port,
            "authentication": {
                "isRequired": True,
                "userName": auth_user,
                "password": password,
                "authType": "Auth",
            },
            "condition": {
                "test": "RelayCondSender",
                "comparator": "RelayCompEqual",
                "pattern": clean_sender,
            },
        }

        # 1. Основной путь: Smtp.getRelayDeliveryRuleList -> Smtp.setRelayDeliveryRuleList
        try:
            current_rules = self.get_relay_rules()
            if current_rules is not None:
                updated_list: List[Dict[str, Any]] = []
                found_existing = False

                for r in current_rules:
                    cond = r.get("condition", {}) if isinstance(r.get("condition"), dict) else {}
                    patt = str(cond.get("pattern", r.get("matchPattern", r.get("sender", "")))).strip().lower()
                    test = str(cond.get("test", r.get("conditionType", "")))
                    r_desc = str(r.get("description", ""))

                    if (patt == clean_sender and test == "RelayCondSender") or (r_desc == desc):
                        # Обновляем существующее правило, сохраняя назначенный Kerio ID
                        rule_to_put = dict(new_rule)
                        if r.get("id"):
                            rule_to_put["id"] = r["id"]
                        updated_list.append(rule_to_put)
                        found_existing = True
                    else:
                        updated_list.append(r)

                if not found_existing:
                    updated_list.append(new_rule)

                self.client.call(self.SET_METHOD, params={"list": updated_list})
                logger.info(f"[SmtpDeliveryManager] Успешно вызван {self.SET_METHOD} для '{clean_sender}'")

                # Верификация создания
                refetched_rules = self.get_relay_rules() or []
                verified_rule: Optional[Dict[str, Any]] = None
                for r in refetched_rules:
                    cond = r.get("condition", {}) if isinstance(r.get("condition"), dict) else {}
                    patt = str(cond.get("pattern", r.get("matchPattern", r.get("sender", "")))).strip().lower()
                    test = str(cond.get("test", r.get("conditionType", "")))
                    if patt == clean_sender and (not test or test == "RelayCondSender"):
                        verified_rule = r
                        break

                if verified_rule:
                    norm_rule = self._normalize_route(verified_rule)
                    return {
                        "success": True,
                        "method": self.SET_METHOD,
                        "id": verified_rule.get("id"),
                        "sender": clean_sender,
                        "relay_host": host,
                        "relay_port": port,
                        "auth_username": auth_user,
                        "route": norm_rule,
                        "is_global": False,
                    }
                elif refetched_rules or not current_rules:
                    return {
                        "success": True,
                        "method": self.SET_METHOD,
                        "sender": clean_sender,
                        "relay_host": host,
                        "relay_port": port,
                        "auth_username": auth_user,
                        "route": self._normalize_route(new_rule),
                        "is_global": False,
                    }
        except Exception as primary_exc:
            err_str = str(primary_exc)
            logger.warning(f"[SmtpDeliveryManager] {self.SET_METHOD}: {err_str}")
            if "-32601" not in err_str and "Method not found" not in err_str:
                # Если метод поддерживается, но вызов завершился ошибкой, пробрасываем её
                raise

        # 2. Fallback для серверов без Smtp.setRelayDeliveryRuleList
        return self._fallback_create_delivery_route(
            clean_sender=clean_sender,
            password=password,
            host=host,
            port=port,
            auth_user=auth_user,
            desc=desc,
            is_enabled=is_enabled,
            ssl_mode=ssl_mode,
        )

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
                "success": False,
                "id": route_id,
                "error": "Нельзя обновить виртуальное серверное правило. Создайте персональное правило.",
            }

        # 1. Основной путь через Smtp.setRelayDeliveryRuleList
        try:
            current_rules = self.get_relay_rules()
            if current_rules is not None:
                updated = False
                for r in current_rules:
                    cond = r.get("condition", {}) if isinstance(r.get("condition"), dict) else {}
                    patt = str(cond.get("pattern", r.get("matchPattern", r.get("sender", "")))).strip().lower()

                    if str(r.get("id")) == str(route_id) or patt == str(route_id).lower():
                        if is_enabled is not None:
                            r["isEnabled"] = is_enabled
                        if relay_host:
                            r["hostName"] = relay_host
                        if relay_port:
                            r["port"] = int(relay_port)

                        auth = r.get("authentication")
                        if not isinstance(auth, dict):
                            auth = {"isRequired": True, "authType": "Auth"}
                            r["authentication"] = auth

                        if auth_username:
                            auth["userName"] = auth_username
                        if password:
                            auth["password"] = password
                        auth["isRequired"] = True
                        updated = True
                        break

                if updated:
                    self.client.call(self.SET_METHOD, params={"list": current_rules})
                    logger.info(
                        f"[SmtpDeliveryManager] Успешно обновлено правило {route_id} через {self.SET_METHOD}"
                    )
                    return {"success": True, "method": self.SET_METHOD, "id": route_id}
        except Exception as exc:
            err_str = str(exc)
            logger.warning(f"[SmtpDeliveryManager] Ошибка обновления через {self.SET_METHOD}: {err_str}")
            if "-32601" not in err_str and "Method not found" not in err_str:
                raise

        # 2. Fallback
        return self._fallback_update_delivery_route(
            route_id=route_id,
            password=password,
            is_enabled=is_enabled,
            relay_host=relay_host,
            relay_port=relay_port,
            auth_username=auth_username,
        )

    def set_route_password_for_sender(
        self,
        sender_email_or_login: str,
        new_password: str,
    ) -> bool:
        """Обновляет пароль авторизации SMTP AUTH для правила указанного отправителя.

        Если индивидуальное правило отсутствует или является глобальным серверным правилом,
        создает персональное правило для отправителя.

        Args:
            sender_email_or_login (str): Email или логин сотрудника.
            new_password (str): Новый пароль учетной записи.

        Returns:
            bool: True, если пароль успешно обновлен в правиле, иначе False.
        """
        route = self.get_route_for_sender(sender_email_or_login)
        if not route or not route.get("id") or route.get("isGlobal"):
            logger.info(
                f"[SmtpDeliveryManager] Создание персонального правила Доставки SMTP при установке пароля для '{sender_email_or_login}'..."
            )
            try:
                res = self.create_delivery_route(
                    sender_email=sender_email_or_login,
                    password=new_password,
                )
                return bool(res.get("success"))
            except Exception as exc:
                logger.warning(f"[SmtpDeliveryManager] Не удалось создать правило при смене пароля: {exc}")
                return False

        res = self.update_delivery_route(route_id=route["id"], password=new_password)
        return bool(res.get("success"))

    def verify_smtp_auth(
        self,
        sender_email: str,
        password: str,
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """Проверяет учетные данные SMTP AUTH против реального SMTP relay сервера через прямое соединение smtplib.

        Выполняет подключение к SMTP relay серверу (например, smtp.barkol.ru:587 с STARTTLS
        или порту 465 с SSL), отправляет EHLO и выполняет команду AUTH LOGIN/PLAIN.

        Args:
            sender_email (str): Email сотрудника для аутентификации.
            password (str): Проверяемый пароль учетной записи.
            relay_host (Optional[str]): Хост SMTP relay (по умолчанию из Django settings).
            relay_port (Optional[int]): Порт SMTP relay (по умолчанию 587).
            timeout (int): Таймаут сетевого соединения в секундах (по умолчанию 10).

        Returns:
            Dict[str, Any]: Результат проверки:
                - success (bool): True при успешной аутентификации (код 235 2.7.0 Authentication successful).
                - host (str): Проверенный хост.
                - port (int): Проверенный порт.
                - auth_user (str): Логин аутентификации.
                - code (Optional[int]): Код ответа SMTP сервера.
                - error (Optional[str]): Описание ошибки при сбое.
        """
        default_host, default_port, _ = self._get_default_smtp_params()
        host = relay_host or default_host
        port = int(relay_port or default_port)
        auth_user = sender_email.strip().lower()
        if "@" not in auth_user:
            auth_user = f"{auth_user}@barkol.ru"

        def _build_ssl_context() -> ssl.SSLContext:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        server: Optional[Union[smtplib.SMTP, smtplib.SMTP_SSL]] = None
        try:
            if port == 465:
                context = _build_ssl_context()
                server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
                server.ehlo()
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    context = _build_ssl_context()
                    server.starttls(context=context)
                    server.ehlo()

            server.login(auth_user, password)
            logger.info(f"[SmtpDeliveryManager] Верификация SMTP AUTH успешна для '{auth_user}' на {host}:{port}")
            return {
                "success": True,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": 235,
                "error": None,
            }
        except smtplib.SMTPAuthenticationError as auth_err:
            logger.warning(
                f"[SmtpDeliveryManager] Ошибка SMTP AUTH для '{auth_user}' на {host}:{port} "
                f"({auth_err.smtp_code}): {auth_err.smtp_error}"
            )
            return {
                "success": False,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": auth_err.smtp_code,
                "error": f"Ошибка авторизации SMTP AUTH ({auth_err.smtp_code}): {auth_err.smtp_error}",
            }
        except Exception as exc:
            logger.warning(
                f"[SmtpDeliveryManager] Сбой подключения/проверки SMTP для '{auth_user}' на {host}:{port}: {exc}"
            )
            return {
                "success": False,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": None,
                "error": f"Сбой подключения к SMTP relay ({host}:{port}): {str(exc)}",
            }
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass

    def remove_delivery_route(self, route_id: str) -> Dict[str, Any]:
        """Удаляет правило ретрансляции «Доставка SMTP» по его ID.

        Args:
            route_id (str): Идентификатор правила в Kerio Connect.

        Returns:
            Dict[str, Any]: Результат удаления.
        """
        if route_id == "kerio_smtp_relay_server" or not route_id:
            return {"success": True, "id": route_id, "message": "Серверное правило ретрансляции сохранено."}

        # 1. Основной путь через Smtp.setRelayDeliveryRuleList
        try:
            current_rules = self.get_relay_rules()
            if current_rules is not None:
                filtered = [
                    r for r in current_rules
                    if str(r.get("id")) != str(route_id)
                    and str(r.get("condition", {}).get("pattern", "")).lower() != str(route_id).lower()
                ]
                if len(filtered) != len(current_rules):
                    self.client.call(self.SET_METHOD, params={"list": filtered})
                    logger.info(f"[SmtpDeliveryManager] Удалено правило {route_id} через {self.SET_METHOD}")
                    return {"success": True, "method": self.SET_METHOD, "id": route_id}
                return {"success": True, "id": route_id, "message": "Правило не найдено или уже удалено."}
        except Exception as exc:
            err_str = str(exc)
            logger.warning(f"[SmtpDeliveryManager] Ошибка удаления через {self.SET_METHOD}: {err_str}")
            if "-32601" not in err_str and "Method not found" not in err_str:
                raise

        # 2. Fallback
        return self._fallback_remove_delivery_route(route_id)

    def remove_route_for_sender(self, sender_email_or_login: str) -> bool:
        """Находит и удаляет правило доставки SMTP для указанного отправителя.

        Args:
            sender_email_or_login (str): Email или логин сотрудника.

        Returns:
            bool: True, если правило найдено и удалено, False в противном случае.
        """
        route = self.get_route_for_sender(sender_email_or_login)
        if not route or not route.get("id") or route.get("isGlobal"):
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
        if not route or not route.get("id") or route.get("isGlobal"):
            return False

        res = self.update_delivery_route(route["id"], is_enabled=is_enabled)
        return bool(res.get("success"))

    # =========================================================================
    # Fallback методы для старых версий Kerio Connect (обратная совместимость)
    # =========================================================================

    def _fallback_get_routes(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Fallback опрос устаревших табличных методов при отсутствии Smtp.getRelayDeliveryRuleList.

        Args:
            query (Optional[Dict[str, Any]]): Параметры поискового запроса.

        Returns:
            List[Dict[str, Any]]: Список сырых правил.
        """
        params = {"query": query or {}}
        probe_methods = [
            ("Delivery.getDeliveryRouteList", params),
            ("Delivery.getRouteList", params),
            ("Delivery.getCustomRoutes", params),
            ("Delivery.getDeliveryRoutes", params),
            ("Smtp.getDeliveryRouteList", params),
            ("SmtpDelivery.getDeliveryRouteList", params),
        ]
        for method_name, method_params in probe_methods:
            try:
                result = self.client.call(method_name, params=method_params)
                if isinstance(result, dict) and "list" in result and isinstance(result["list"], list):
                    return result["list"]
                elif isinstance(result, list):
                    return result
            except Exception:
                continue

        # Попытка извлечения из Smtp.get
        try:
            full_resp = self.client.call("Smtp.get", params={})
            if isinstance(full_resp, dict):
                root_key = "server" if "server" in full_resp else ("settings" if "settings" in full_resp else None)
                smtp_cfg = full_resp.get(root_key) if root_key else full_resp
                if isinstance(smtp_cfg, dict):
                    rules, _, _ = self._extract_routes_from_smtp_cfg(smtp_cfg)
                    if rules:
                        return rules
        except Exception:
            pass

        return []

    def _extract_routes_from_smtp_cfg(
        self, smtp_cfg: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
        """Извлекает список правил таблицы «Доставка SMTP» и путь к ним из конфигурации Smtp.get.

        Args:
            smtp_cfg (Dict[str, Any]): Словарь настроек Smtp.get.

        Returns:
            Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]: (список правил, parent_key, list_key).
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
            ("smtpDelivery", "customRules"),
            ("smtpDelivery", "routes"),
            ("smtpDelivery", "deliveryRoutes"),
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

    def _fallback_create_delivery_route(
        self,
        clean_sender: str,
        password: str,
        host: str,
        port: int,
        auth_user: str,
        desc: str,
        is_enabled: bool,
        ssl_mode: str,
    ) -> Dict[str, Any]:
        """Fallback создание правила через Smtp.get -> Smtp.set или legacy методы.

        Args:
            clean_sender (str): Email отправителя.
            password (str): Пароль SMTP AUTH.
            host (str): Адрес SMTP сервера.
            port (int): Порт SMTP.
            auth_user (str): Имя пользователя SMTP AUTH.
            desc (str): Описание правила.
            is_enabled (bool): Флаг активности.
            ssl_mode (str): Режим SSL.

        Returns:
            Dict[str, Any]: Результат создания.

        Raises:
            KerioAPIError: Если создание не удалось ни одним методом.
        """
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

        # Пробуем через Smtp.get -> Smtp.set
        try:
            full_resp = self.client.call("Smtp.get", params={})
            if isinstance(full_resp, dict):
                root_key = "server" if "server" in full_resp else ("settings" if "settings" in full_resp else None)
                smtp_cfg = full_resp.get(root_key) if root_key else full_resp

                if isinstance(smtp_cfg, dict):
                    existing_rules, parent_key, list_key = self._extract_routes_from_smtp_cfg(smtp_cfg)
                    if not list_key:
                        parent_key = "delivery"
                        if parent_key not in smtp_cfg or not isinstance(smtp_cfg[parent_key], dict):
                            smtp_cfg[parent_key] = {}
                        list_key = "customRules"
                        smtp_cfg[parent_key][list_key] = []
                        existing_rules = smtp_cfg[parent_key][list_key]

                    rule_to_add = dict(route_payload)
                    rule_to_add["id"] = f"keriodb://deliveryroute/{clean_sender}"

                    filtered = [
                        r for r in existing_rules
                        if str(r.get("matchPattern", r.get("sender", ""))).lower() != clean_sender
                    ]
                    filtered.append(rule_to_add)

                    if parent_key:
                        smtp_cfg[parent_key][list_key] = filtered
                    else:
                        smtp_cfg[list_key] = filtered

                    set_params = {root_key: smtp_cfg} if root_key else smtp_cfg
                    self.client.call("Smtp.set", params=set_params)
                    return {
                        "success": True,
                        "method": "Smtp.set",
                        "sender": clean_sender,
                        "relay_host": host,
                        "relay_port": port,
                        "auth_username": auth_user,
                        "is_global": False,
                    }
        except Exception as exc:
            logger.debug(f"[SmtpDeliveryManager] Fallback Smtp.set: {exc}")

        # Если создание не удалось ни одним методом, возбуждаем ошибку
        raise KerioAPIError(
            f"Не удалось создать правило «Доставка SMTP» для '{clean_sender}'. "
            "Метод Smtp.setRelayDeliveryRuleList не поддерживается сервером."
        )

    def _fallback_update_delivery_route(
        self,
        route_id: str,
        password: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
        auth_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback обновление правила через Smtp.get -> Smtp.set.

        Args:
            route_id (str): Идентификатор правила.
            password (Optional[str]): Пароль.
            is_enabled (Optional[bool]): Флаг активности.
            relay_host (Optional[str]): Хост.
            relay_port (Optional[int]): Порт.
            auth_username (Optional[str]): Логин.

        Returns:
            Dict[str, Any]: Результат обновления.
        """
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
        except Exception as exc:
            logger.debug(f"[SmtpDeliveryManager] Fallback update Smtp.set: {exc}")

        return {"success": False, "error": f"Не удалось обновить правило {route_id}"}

    def _fallback_remove_delivery_route(self, route_id: str) -> Dict[str, Any]:
        """Fallback удаление правила через Smtp.get -> Smtp.set.

        Args:
            route_id (str): Идентификатор правила.

        Returns:
            Dict[str, Any]: Результат удаления.
        """
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
        except Exception as exc:
            logger.debug(f"[SmtpDeliveryManager] Fallback remove Smtp.set: {exc}")

        return {"success": False, "error": f"Не удалось удалить правило {route_id}"}
