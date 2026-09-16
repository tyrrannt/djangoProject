"""Менеджер правил исходящей маршрутизации «Доставка SMTP» в Kerio Connect.

Используется официальный Administration API Kerio Connect:

    Smtp.getRelayDeliveryRuleList
    Smtp.setRelayDeliveryRuleList

Основная модель:

    RelayDeliveryRule
        id
        isEnabled
        description
        hostName
        port
        authentication
        condition

Для изменения пароля SMTP AUTH после записи в Kerio выполняется
дополнительная реальная проверка SMTP AUTH через smtplib.
"""

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
    """Менеджер правил «Доставка SMTP» Kerio Connect.

    Менеджер работает исключительно с официальными методами:

        Smtp.getRelayDeliveryRuleList
        Smtp.setRelayDeliveryRuleList

    Важный принцип:
        GET -> read/modify -> SET -> GET

    При изменении или создании пароля SMTP AUTH дополнительно выполняется
    реальная SMTP AUTH проверка на relay-сервере.
    """

    GET_METHOD = "Smtp.getRelayDeliveryRuleList"
    SET_METHOD = "Smtp.setRelayDeliveryRuleList"

    DEFAULT_DOMAIN = "barkol.ru"

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер.

        Args:
            client: Авторизованный клиент Kerio Connect Administration API.
        """
        self.client = client

    # =========================================================================
    # Общие вспомогательные методы
    # =========================================================================

    def _get_default_smtp_params(self) -> Tuple[str, int, str]:
        """Возвращает настройки SMTP relay из Django settings.

        Returns:
            Кортеж:
                (relay_host, relay_port, ssl_mode)
        """
        host = str(
            get_django_setting(
                "KERIO_DEFAULT_SMTP_RELAY_HOST",
                "smtp.barkol.ru",
            )
            or "smtp.barkol.ru"
        )

        port = int(
            get_django_setting(
                "KERIO_DEFAULT_SMTP_RELAY_PORT",
                587,
            )
            or 587
        )

        mode = str(
            get_django_setting(
                "KERIO_DEFAULT_SMTP_RELAY_MODE",
                "StlsCommand",
            )
            or "StlsCommand"
        )

        return host, port, mode

    @staticmethod
    def _normalize_email(email_or_login: str) -> str:
        """Нормализует email или логин.

        Args:
            email_or_login: Email или логин пользователя.

        Returns:
            Полный email в нижнем регистре.
        """
        value = str(email_or_login or "").strip().lower()

        if not value:
            return ""

        if "@" not in value:
            value = f"{value}@{SmtpDeliveryManager.DEFAULT_DOMAIN}"

        return value

    @staticmethod
    def _get_condition(rule: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает condition правила."""
        condition = rule.get("condition")

        if isinstance(condition, dict):
            return condition

        return {}

    @classmethod
    def _get_rule_pattern(cls, rule: Dict[str, Any]) -> str:
        """Возвращает pattern условия правила."""
        condition = cls._get_condition(rule)

        return str(condition.get("pattern", "")).strip().lower()

    @classmethod
    def _is_sender_rule(cls, rule: Dict[str, Any]) -> bool:
        """Проверяет, является ли правило персональным правилом отправителя."""
        condition = cls._get_condition(rule)

        return (
            str(condition.get("test", "")).strip()
            == "RelayCondSender"
            and str(condition.get("comparator", "RelayCompEqual")).strip()
            == "RelayCompEqual"
        )

    @staticmethod
    def _get_authentication(
        rule: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Возвращает authentication правила.

        Если структура отсутствует, создаёт минимальную корректную структуру.
        """
        authentication = rule.get("authentication")

        if isinstance(authentication, dict):
            return authentication

        authentication = {
            "isRequired": True,
            "authType": "Auth",
        }

        rule["authentication"] = authentication

        return authentication

    @staticmethod
    def _is_method_not_found(exc: Exception) -> bool:
        """Проверяет, является ли ошибка отсутствием метода API.

        Используется только для диагностики. Legacy fallback намеренно
        отсутствует.
        """
        message = str(exc).lower()

        return (
            "-32601" in message
            or "method not found" in message
            or "unknown method" in message
        )

    # =========================================================================
    # Получение правил
    # =========================================================================

    def get_relay_rules(self) -> List[Dict[str, Any]]:
        """Получает полный список RelayDeliveryRule из Kerio.

        Returns:
            Список сырых правил Kerio.

        Raises:
            KerioAPIError: Если Kerio вернул некорректную структуру.
            Exception: Ошибка Administration API пробрасывается наружу.
        """
        try:
            result = self.client.call(
                self.GET_METHOD,
                params={},
            )
        except Exception as exc:
            logger.error(
                "[SmtpDeliveryManager] Ошибка %s: %s",
                self.GET_METHOD,
                exc,
            )
            raise

        if isinstance(result, list):
            return result

        if not isinstance(result, dict):
            raise KerioAPIError(
                "Kerio Connect вернул некорректный ответ "
                f"{self.GET_METHOD}: ожидался объект."
            )

        rules = result.get("list")

        if not isinstance(rules, list):
            raise KerioAPIError(
                "Kerio Connect не вернул список правил в поле 'list'. "
                f"Метод: {self.GET_METHOD}"
            )

        return rules

    def get_routes(
        self,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Получает нормализованный список правил SMTP Delivery.

        Args:
            query: Параметр оставлен для обратной совместимости.
                Фильтрация выполняется локально при необходимости.

        Returns:
            Список нормализованных правил.
        """
        rules = self.get_relay_rules()

        normalized = [
            self._normalize_route(rule)
            for rule in rules
        ]

        if not query:
            return normalized

        return self._filter_routes(normalized, query)

    @staticmethod
    def _filter_routes(
        routes: List[Dict[str, Any]],
        query: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Фильтрует нормализованные маршруты.

        Поддерживает наиболее очевидные параметры:
            sender
            matchPattern
            userName
            id
        """
        result = routes

        for field in ("sender", "matchPattern", "userName", "id"):
            value = query.get(field)

            if value is None:
                continue

            target = str(value).strip().lower()

            result = [
                route
                for route in result
                if str(route.get(field, "")).strip().lower() == target
            ]

        return result

    # =========================================================================
    # Нормализация
    # =========================================================================

    def _normalize_route(
        self,
        raw_route: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Преобразует RelayDeliveryRule в удобное плоское представление.

        Важно:
            raw содержит исходный объект Kerio без удаления полей.
        """
        condition = self._get_condition(raw_route)
        authentication = raw_route.get("authentication")

        if not isinstance(authentication, dict):
            authentication = {}

        route_id = str(raw_route.get("id", "") or "")

        is_enabled = bool(
            raw_route.get(
                "isEnabled",
                True,
            )
        )

        pattern = str(
            condition.get("pattern", "")
            or ""
        ).strip().lower()

        condition_test = str(
            condition.get("test", "")
            or ""
        )

        condition_comparator = str(
            condition.get(
                "comparator",
                "RelayCompEqual",
            )
            or "RelayCompEqual"
        )

        host = str(
            raw_route.get(
                "hostName",
                "",
            )
            or ""
        )

        try:
            port = int(
                raw_route.get(
                    "port",
                    587,
                )
                or 587
            )
        except (TypeError, ValueError):
            port = 587

        username = str(
            authentication.get(
                "userName",
                "",
            )
            or ""
        )

        has_password = bool(
            authentication.get("password")
        )

        return {
            "id": route_id,
            "isEnabled": is_enabled,
            "isActive": is_enabled,
            "description": str(
                raw_route.get(
                    "description",
                    "",
                )
                or ""
            ),
            "conditionType": condition_test,
            "conditionComparator": condition_comparator,
            "matchPattern": pattern,
            "sender": pattern,
            "actionType": "ActionRelayServer",
            "server": host,
            "hostName": host,
            "port": port,
            "userName": username,
            "authUsername": username,
            "hasPassword": has_password,
            "sslMode": "StlsCommand",
            "isGlobal": condition_test == "RelayCondNone",
            "raw": raw_route,
        }

    # =========================================================================
    # Поиск правила
    # =========================================================================

    def get_route_for_sender(
        self,
        sender_email_or_login: str,
    ) -> Optional[Dict[str, Any]]:
        """Находит персональное SMTP Delivery правило отправителя.

        В отличие от старой реализации, метод НЕ создаёт синтетическое
        глобальное правило.

        Args:
            sender_email_or_login: Email или логин.

        Returns:
            Нормализованное правило или None.
        """
        target_email = self._normalize_email(
            sender_email_or_login
        )

        if not target_email:
            return None

        target_login = target_email.split("@", 1)[0]

        routes = self.get_routes()

        for route in routes:
            if not self._is_personal_route(route):
                continue

            pattern = str(
                route.get("matchPattern", "")
            ).strip().lower()

            username = str(
                route.get("userName", "")
            ).strip().lower()

            if pattern == target_email:
                return route

            if username == target_email:
                return route

            if pattern.split("@", 1)[0] == target_login:
                return route

            if username.split("@", 1)[0] == target_login:
                return route

        return None

    @staticmethod
    def _is_personal_route(
        route: Dict[str, Any],
    ) -> bool:
        """Проверяет, является ли маршрут персональным."""
        condition_type = str(
            route.get(
                "conditionType",
                "",
            )
        )

        pattern = str(
            route.get(
                "matchPattern",
                "",
            )
        ).strip().lower()

        return (
            condition_type == "RelayCondSender"
            and pattern not in {
                "",
                "*",
                "*@barkol.ru",
            }
        )

    # =========================================================================
    # Создание / обновление
    # =========================================================================

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
        """Создаёт или заменяет персональное SMTP Delivery правило.

        После записи выполняется:
            1. GET;
            2. read-modify-write;
            3. SET;
            4. повторный GET;
            5. SMTP AUTH новым паролем.

        Args:
            sender_email: Email отправителя.
            password: Пароль SMTP relay.
            relay_host: SMTP relay host.
            relay_port: SMTP relay port.
            auth_username: SMTP AUTH username.
            is_enabled: Активность правила.
            description: Описание.
            ssl_mode: Оставлен для совместимости API менеджера.

        Returns:
            Информация о созданном/обновлённом правиле.

        Raises:
            KerioValidationError: Некорректные параметры.
            KerioAPIError: Ошибка Kerio или SMTP AUTH.
        """
        del ssl_mode

        clean_sender = self._normalize_email(sender_email)

        if not clean_sender:
            raise KerioValidationError(
                "sender_email обязателен."
            )

        if not password:
            raise KerioValidationError(
                "password обязателен."
            )

        default_host, default_port, _ = (
            self._get_default_smtp_params()
        )

        host = str(
            relay_host or default_host
        ).strip()

        port = int(
            relay_port or default_port
        )

        auth_user = (
            auth_username.strip()
            if auth_username
            else clean_sender
        )

        if not auth_user:
            auth_user = clean_sender

        description_value = (
            description.strip()
            if description
            else f"Ретрансляция SMTP для {clean_sender}"
        )

        new_rule: Dict[str, Any] = {
            "isEnabled": bool(is_enabled),
            "description": description_value,
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

        current_rules = self.get_relay_rules()

        updated_list: List[Dict[str, Any]] = []
        existing_rule: Optional[Dict[str, Any]] = None

        for rule in current_rules:
            if not isinstance(rule, dict):
                raise KerioAPIError(
                    "Kerio вернул элемент списка правил "
                    "не в виде объекта."
                )

            if (
                self._is_sender_rule(rule)
                and self._get_rule_pattern(rule)
                == clean_sender
            ):
                existing_rule = rule

                replacement = dict(new_rule)

                if rule.get("id"):
                    replacement["id"] = rule["id"]

                updated_list.append(replacement)
            else:
                updated_list.append(rule)

        if existing_rule is None:
            updated_list.append(new_rule)

        self._set_relay_rules(updated_list)

        verified_rule = self._find_rule_in_list(
            self.get_relay_rules(),
            sender_email=clean_sender,
        )

        if verified_rule is None:
            raise KerioAPIError(
                "Kerio принял Smtp.setRelayDeliveryRuleList, "
                "но правило отправителя не найдено после повторного GET: "
                f"{clean_sender}"
            )

        smtp_result = self.verify_smtp_auth(
            sender_email=auth_user,
            password=password,
            relay_host=host,
            relay_port=port,
        )

        if not smtp_result["success"]:
            raise KerioAPIError(
                "Правило SMTP Delivery записано в Kerio, "
                "но проверка SMTP AUTH не пройдена: "
                f"{smtp_result.get('error', 'неизвестная ошибка')}"
            )

        return {
            "success": True,
            "method": self.SET_METHOD,
            "id": verified_rule.get("id"),
            "sender": clean_sender,
            "relay_host": host,
            "relay_port": port,
            "auth_username": auth_user,
            "smtp_auth": smtp_result,
            "route": self._normalize_route(
                verified_rule
            ),
            "is_global": False,
            "created": existing_rule is None,
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
        """Обновляет существующее RelayDeliveryRule.

        Если передан password, после SET выполняется реальный SMTP AUTH.

        Args:
            route_id: Реальный ID правила Kerio.
            password: Новый пароль SMTP AUTH.
            is_enabled: Новый статус активности.
            relay_host: Новый relay host.
            relay_port: Новый relay port.
            auth_username: Новый SMTP AUTH username.

        Returns:
            Результат операции.

        Raises:
            KerioObjectNotFoundError: Правило не найдено.
            KerioAPIError: Ошибка API или SMTP AUTH.
        """
        if not route_id:
            raise KerioValidationError(
                "route_id обязателен."
            )

        if route_id == "kerio_smtp_relay_server":
            raise KerioValidationError(
                "Синтетические/серверные правила больше не поддерживаются. "
                "Необходимо использовать реальный ID RelayDeliveryRule."
            )

        current_rules = self.get_relay_rules()

        target_rule: Optional[Dict[str, Any]] = None

        for rule in current_rules:
            if not isinstance(rule, dict):
                continue

            if str(rule.get("id", "")) == str(route_id):
                target_rule = rule
                break

        if target_rule is None:
            raise KerioObjectNotFoundError(
                f"Правило SMTP Delivery с ID '{route_id}' не найдено."
            )

        original_rule = dict(target_rule)

        # -------------------------------------------------------------
        # Изменяем только необходимые поля.
        # -------------------------------------------------------------

        if is_enabled is not None:
            target_rule["isEnabled"] = bool(
                is_enabled
            )

        if relay_host:
            target_rule["hostName"] = (
                relay_host.strip()
            )

        if relay_port is not None:
            target_rule["port"] = int(
                relay_port
            )

        authentication = self._get_authentication(
            target_rule
        )

        if auth_username:
            authentication["userName"] = (
                auth_username.strip()
            )

        if password is not None:
            if not password:
                raise KerioValidationError(
                    "password не может быть пустым."
                )

            authentication["password"] = password

        authentication["isRequired"] = True

        if not authentication.get("authType"):
            authentication["authType"] = "Auth"

        target_rule["authentication"] = authentication

        # -------------------------------------------------------------
        # SET полного списка правил.
        # -------------------------------------------------------------

        self._set_relay_rules(current_rules)

        # -------------------------------------------------------------
        # Повторный GET.
        # -------------------------------------------------------------

        verified_rule = self._find_rule_by_id(
            self.get_relay_rules(),
            route_id,
        )

        if verified_rule is None:
            raise KerioAPIError(
                "Kerio принял изменение, но правило "
                f"'{route_id}' не найдено после повторного GET."
            )

        result: Dict[str, Any] = {
            "success": True,
            "method": self.SET_METHOD,
            "id": route_id,
            "route": self._normalize_route(
                verified_rule
            ),
        }

        # -------------------------------------------------------------
        # Реальная проверка нового SMTP пароля.
        # -------------------------------------------------------------

        if password is not None:
            verified_auth = verified_rule.get(
                "authentication"
            )

            if not isinstance(
                verified_auth,
                dict,
            ):
                verified_auth = {}

            auth_user = (
                auth_username
                or verified_auth.get("userName")
                or original_rule.get(
                    "authentication",
                    {},
                ).get("userName")
            )

            if not auth_user:
                raise KerioAPIError(
                    "Пароль изменён, но невозможно определить "
                    "SMTP AUTH username для проверки."
                )

            verified_host = (
                relay_host
                or verified_rule.get(
                    "hostName"
                )
            )

            verified_port = (
                relay_port
                or verified_rule.get(
                    "port"
                )
            )

            if not verified_host:
                default_host, _, _ = (
                    self._get_default_smtp_params()
                )
                verified_host = default_host

            if not verified_port:
                _, default_port, _ = (
                    self._get_default_smtp_params()
                )
                verified_port = default_port

            smtp_result = self.verify_smtp_auth(
                sender_email=str(auth_user),
                password=password,
                relay_host=str(verified_host),
                relay_port=int(verified_port),
            )

            result["smtp_auth"] = smtp_result

            if not smtp_result["success"]:
                raise KerioAPIError(
                    "Пароль записан в Kerio, но SMTP AUTH "
                    "с новым паролем не прошёл: "
                    f"{smtp_result.get('error', 'неизвестная ошибка')}"
                )

        return result

    def set_route_password_for_sender(
        self,
        sender_email_or_login: str,
        new_password: str,
    ) -> bool:
        """Устанавливает пароль SMTP AUTH для отправителя.

        Алгоритм:

            1. Найти персональное правило.
            2. Если найдено — обновить его.
            3. Если не найдено — создать персональное правило.
            4. Проверить SMTP AUTH новым паролем.

        Returns:
            True только если Kerio успешно записал пароль и SMTP AUTH
            реально прошёл.
        """
        if not new_password:
            raise KerioValidationError(
                "Новый пароль не может быть пустым."
            )

        sender = self._normalize_email(
            sender_email_or_login
        )

        if not sender:
            raise KerioValidationError(
                "sender_email_or_login обязателен."
            )

        route = self.get_route_for_sender(
            sender
        )

        if route is None:
            logger.info(
                "[SmtpDeliveryManager] Персональное правило для '%s' "
                "не найдено. Создание нового правила.",
                sender,
            )

            result = self.create_delivery_route(
                sender_email=sender,
                password=new_password,
            )

            return bool(
                result.get("success")
            )

        route_id = str(
            route.get("id", "")
        )

        if not route_id:
            raise KerioAPIError(
                f"Найдено правило для '{sender}', "
                "но Kerio не вернул его ID."
            )

        result = self.update_delivery_route(
            route_id=route_id,
            password=new_password,
        )

        return bool(
            result.get("success")
        )

    # =========================================================================
    # Удаление
    # =========================================================================

    def remove_delivery_route(
        self,
        route_id: str,
    ) -> Dict[str, Any]:
        """Удаляет RelayDeliveryRule по реальному ID.

        Args:
            route_id: ID правила Kerio.

        Returns:
            Результат удаления.
        """
        if not route_id:
            raise KerioValidationError(
                "route_id обязателен."
            )

        if route_id == "kerio_smtp_relay_server":
            raise KerioValidationError(
                "Синтетические серверные правила не поддерживаются."
            )

        current_rules = self.get_relay_rules()

        filtered_rules = [
            rule
            for rule in current_rules
            if str(rule.get("id", "")) != str(route_id)
        ]

        if len(filtered_rules) == len(current_rules):
            return {
                "success": True,
                "method": self.SET_METHOD,
                "id": route_id,
                "deleted": False,
                "message": "Правило не найдено.",
            }

        self._set_relay_rules(
            filtered_rules
        )

        remaining_rules = self.get_relay_rules()

        if self._find_rule_by_id(
            remaining_rules,
            route_id,
        ) is not None:
            raise KerioAPIError(
                "Kerio принял SET, но правило "
                f"'{route_id}' осталось после удаления."
            )

        return {
            "success": True,
            "method": self.SET_METHOD,
            "id": route_id,
            "deleted": True,
        }

    def remove_route_for_sender(
        self,
        sender_email_or_login: str,
    ) -> bool:
        """Удаляет персональное правило отправителя."""
        route = self.get_route_for_sender(
            sender_email_or_login
        )

        if route is None:
            return False

        route_id = str(
            route.get("id", "")
        )

        if not route_id:
            return False

        result = self.remove_delivery_route(
            route_id
        )

        return bool(
            result.get("success")
            and result.get("deleted")
        )

    # =========================================================================
    # Включение / выключение
    # =========================================================================

    def toggle_route_for_sender(
        self,
        sender_email_or_login: str,
        is_enabled: bool,
    ) -> bool:
        """Включает или отключает персональное правило."""
        route = self.get_route_for_sender(
            sender_email_or_login
        )

        if route is None:
            return False

        route_id = str(
            route.get("id", "")
        )

        if not route_id:
            return False

        result = self.update_delivery_route(
            route_id=route_id,
            is_enabled=is_enabled,
        )

        return bool(
            result.get("success")
        )

    # =========================================================================
    # Низкоуровневый SET
    # =========================================================================

    def _set_relay_rules(
        self,
        rules: List[Dict[str, Any]],
    ) -> None:
        """Записывает полный список RelayDeliveryRule в Kerio.

        Это непосредственный аналог нажатия Apply в GUI для списка
        «Доставка SMTP».

        Args:
            rules: Полный актуальный список правил.

        Raises:
            KerioAPIError: При некорректном ответе API.
        """
        if not isinstance(rules, list):
            raise KerioValidationError(
                "rules должен быть списком."
            )

        # Защита от случайной записи пустого списка.
        #
        # В нормальной конфигурации пустой список может быть легитимным,
        # поэтому запрет применяется только если вызов выглядит подозрительно.
        # Здесь мы не запрещаем пустой список, поскольку remove последнего
        # правила может быть штатной операцией.
        result = self.client.call(
            self.SET_METHOD,
            params={
                "list": rules,
            },
        )

        logger.info(
            "[SmtpDeliveryManager] %s успешно выполнен. "
            "Количество правил: %d",
            self.SET_METHOD,
            len(rules),
        )

        # Некоторые версии API могут вернуть None/{} при успешном SET.
        # Наличие исключения из client.call является основным признаком ошибки.
        if result is not None and not isinstance(
            result,
            (dict, list),
        ):
            raise KerioAPIError(
                f"Kerio вернул неожиданный результат {self.SET_METHOD}."
            )

    # =========================================================================
    # Поиск
    # =========================================================================

    @classmethod
    def _find_rule_by_id(
        cls,
        rules: List[Dict[str, Any]],
        route_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Находит правило по реальному Kerio ID."""
        target_id = str(route_id)

        for rule in rules:
            if str(
                rule.get("id", "")
            ) == target_id:
                return rule

        return None

    @classmethod
    def _find_rule_in_list(
        cls,
        rules: List[Dict[str, Any]],
        sender_email: str,
    ) -> Optional[Dict[str, Any]]:
        """Находит персональное правило отправителя."""
        target = cls._normalize_email(
            sender_email
        )

        for rule in rules:
            if not isinstance(rule, dict):
                continue

            if not cls._is_sender_rule(rule):
                continue

            if (
                cls._get_rule_pattern(rule)
                == target
            ):
                return rule

        return None

    # =========================================================================
    # Реальная проверка SMTP AUTH
    # =========================================================================

    def verify_smtp_auth(
        self,
        sender_email: str,
        password: str,
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """Проверяет SMTP AUTH непосредственно на relay-сервере.

        Для:
            465 -> SMTPS
            587 -> SMTP + STARTTLS
            остальные -> SMTP; если сервер предоставляет STARTTLS,
                    он используется.

        В лог пароль никогда не выводится.

        Args:
            sender_email: SMTP AUTH username.
            password: Проверяемый пароль.
            relay_host: SMTP relay host.
            relay_port: SMTP relay port.
            timeout: Таймаут подключения.

        Returns:
            Словарь с результатом проверки.
        """
        if not sender_email:
            raise KerioValidationError(
                "sender_email обязателен для SMTP AUTH проверки."
            )

        if not password:
            raise KerioValidationError(
                "password обязателен для SMTP AUTH проверки."
            )

        default_host, default_port, _ = (
            self._get_default_smtp_params()
        )

        host = (
            relay_host.strip()
            if relay_host
            else default_host
        )

        port = int(
            relay_port or default_port
        )

        auth_user = self._normalize_email(
            sender_email
        )

        server: Optional[
            Union[
                smtplib.SMTP,
                smtplib.SMTP_SSL,
            ]
        ] = None

        try:
            context = self._create_ssl_context()

            # -------------------------------------------------------------
            # SMTPS 465
            # -------------------------------------------------------------

            if port == 465:
                server = smtplib.SMTP_SSL(
                    host,
                    port,
                    timeout=timeout,
                    context=context,
                )

                server.ehlo()

            # -------------------------------------------------------------
            # SMTP + STARTTLS
            # -------------------------------------------------------------

            else:
                server = smtplib.SMTP(
                    host,
                    port,
                    timeout=timeout,
                )

                server.ehlo()

                if port == 587:
                    if not server.has_extn(
                        "STARTTLS"
                    ):
                        return {
                            "success": False,
                            "host": host,
                            "port": port,
                            "auth_user": auth_user,
                            "code": None,
                            "error": (
                                "SMTP сервер не объявил STARTTLS "
                                f"на {host}:{port}."
                            ),
                        }

                    server.starttls(
                        context=context
                    )
                    server.ehlo()

                elif server.has_extn("STARTTLS"):
                    server.starttls(
                        context=context
                    )
                    server.ehlo()

            # -------------------------------------------------------------
            # AUTH
            # -------------------------------------------------------------

            server.login(
                auth_user,
                password,
            )

            logger.info(
                "[SmtpDeliveryManager] SMTP AUTH успешно проверен "
                "для '%s' на %s:%s",
                auth_user,
                host,
                port,
            )

            return {
                "success": True,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": 235,
                "error": None,
            }

        except smtplib.SMTPAuthenticationError as exc:
            logger.warning(
                "[SmtpDeliveryManager] SMTP AUTH отклонён "
                "для '%s' на %s:%s: код=%s",
                auth_user,
                host,
                port,
                exc.smtp_code,
            )

            return {
                "success": False,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": exc.smtp_code,
                "error": (
                    "Ошибка SMTP AUTH "
                    f"({exc.smtp_code}): "
                    f"{exc.smtp_error!r}"
                ),
            }

        except smtplib.SMTPResponseException as exc:
            logger.warning(
                "[SmtpDeliveryManager] SMTP ошибка "
                "для '%s' на %s:%s: код=%s",
                auth_user,
                host,
                port,
                exc.smtp_code,
            )

            return {
                "success": False,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": exc.smtp_code,
                "error": (
                    f"SMTP ошибка ({exc.smtp_code}): "
                    f"{exc.smtp_error!r}"
                ),
            }

        except (
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPException,
            OSError,
        ) as exc:
            logger.warning(
                "[SmtpDeliveryManager] Ошибка подключения/SMTP "
                "для '%s' на %s:%s: %s",
                auth_user,
                host,
                port,
                exc,
            )

            return {
                "success": False,
                "host": host,
                "port": port,
                "auth_user": auth_user,
                "code": None,
                "error": (
                    f"Сбой подключения/SMTP "
                    f"({host}:{port}): {exc}"
                ),
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

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """Создаёт SSL context для SMTP.

        Kerio/relay может использовать внутренний или самоподписанный
        сертификат, поэтому проверка сертификата здесь отключена.

        Для production желательно вынести этот параметр в Django settings
        и включать проверку сертификата при наличии доверенного CA.
        """
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        return context