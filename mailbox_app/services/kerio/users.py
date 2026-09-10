"""Менеджер управления почтовыми пользователями в Kerio Connect Administration API."""

import logging
from typing import Any, Dict, List, Optional, Union

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioObjectNotFoundError,
    KerioValidationError,
)

logger = logging.getLogger(__name__)


class UserManager:
    """Менеджер операций над пользователями (Users) почтового сервера Kerio Connect.

    Attributes:
        client (KerioConnectAdminClient): Экземпляр клиента API.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер пользователей.

        Args:
            client (KerioConnectAdminClient): Клиент API Kerio Connect.
        """
        self.client = client

    def get_users(
        self,
        domain_id: Optional[str] = None,
        query_string: Optional[str] = None,
        start: int = 0,
        limit: int = 100,
        order_by: str = "loginName",
        direction: str = "Asc",
    ) -> Dict[str, Any]:
        """Получает постраничный список пользователей Kerio Connect с возможностью фильтрации.

        Args:
            domain_id (Optional[str]): Идентификатор домена в Kerio. Если None, выбираются все домены.
            query_string (Optional[str]): Строка поиска (по логину, ФИО, описанию).
            start (int): Смещение для пагинации.
            limit (int): Количество записей на страницу.
            order_by (str): Имя поля для сортировки (по умолчанию 'loginName').
            direction (str): Направление сортировки ('Asc' или 'Desc').

        Returns:
            Dict[str, Any]: Словарь со списком пользователей ('list') и общим количеством ('totalItems').

        Raises:
            KerioAPIError: При ошибке запроса к API.
        """
        query: Dict[str, Any] = {
            "start": start,
            "limit": limit,
            "orderBy": [{"columnName": order_by, "direction": direction}],
        }
        if query_string:
            query["queryString"] = query_string

        params: Dict[str, Any] = {"query": query}
        if domain_id:
            params["domainId"] = domain_id

        result = self.client.call("Users.get", params=params)
        if isinstance(result, dict):
            return {
                "list": result.get("list", []),
                "totalItems": result.get("totalItems", len(result.get("list", []))),
            }
        if isinstance(result, list):
            return {"list": result, "totalItems": len(result)}
        return {"list": [], "totalItems": 0}

    def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """Получает детальную информацию о пользователе по его системному идентификатору.

        Args:
            user_id (str): Идентификатор пользователя в Kerio Connect (ID).

        Returns:
            Dict[str, Any]: Словарь с полными параметрами пользователя.

        Raises:
            KerioObjectNotFoundError: Если пользователь с данным ID не найден.
        """
        result = self.client.call("Users.getDetails", params={"userIds": [user_id]})
        users_list = []
        if isinstance(result, dict):
            users_list = result.get("list", [])
        elif isinstance(result, list):
            users_list = result

        if not users_list:
            raise KerioObjectNotFoundError(f"Пользователь с ID '{user_id}' не найден в Kerio Connect.")
        return users_list[0]

    def get_user_by_login(
        self,
        login_name: str,
        domain_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Ищет пользователя по логину в указанном домене.

        Args:
            login_name (str): Логин пользователя (например, 'shakirov' или 'shakirov@barkol.ru').
            domain_id (Optional[str]): Идентификатор домена.

        Returns:
            Optional[Dict[str, Any]]: Словарь пользователя или None, если не найден.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        res = self.get_users(domain_id=domain_id, query_string=clean_login, limit=100)
        for user in res.get("list", []):
            if user.get("loginName", "").strip().lower() == clean_login:
                return user
        return None

    def create_user(
        self,
        domain_id: str,
        login_name: str,
        password: str,
        full_name: str = "",
        description: str = "",
        is_enabled: bool = True,
        auth_type: str = "TypeInternal",
        quota_mb: Optional[int] = None,
        email_alias: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Создает нового почтового пользователя в Kerio Connect.

        Args:
            domain_id (str): Идентификатор домена в Kerio Connect.
            login_name (str): Имя пользователя (логин) без доменной части.
            password (str): Пароль учетной записи.
            full_name (str): Полное имя (ФИО) сотрудника.
            description (str): Описание / должность.
            is_enabled (bool): Активен ли аккаунт (по умолчанию True).
            auth_type (str): Тип аутентификации в Kerio (по умолчанию 'TypeInternal').
            quota_mb (Optional[int]): Лимит дисковой квоты в мегабайтах (если None — без ограничений).
            email_alias (Optional[str]): Дополнительный псевдоним / алиас.

        Returns:
            Dict[str, Any]: Словарь с результатом создания и присвоенным ID.

        Raises:
            KerioValidationError: При передаче некорректных или пустых обязательных полей.
            KerioAPIError: При ошибке на стороне Kerio Connect (например, дубликат логина).
        """
        clean_login = login_name.split("@")[0].strip().lower()
        if not clean_login:
            raise KerioValidationError("Логин пользователя не может быть пустым.")
        if not password:
            raise KerioValidationError("Пароль пользователя не может быть пустым.")

        user_data: Dict[str, Any] = {
            "domainId": domain_id,
            "loginName": clean_login,
            "password": password,
            "fullName": full_name.strip(),
            "description": description.strip(),
            "isEnabled": is_enabled,
            "authType": auth_type,
        }

        if quota_mb is not None and quota_mb > 0:
            user_data["itemBox"] = {
                "limit": quota_mb,
                "isEnabled": True,
            }

        if email_alias:
            user_data["emailAddresses"] = [email_alias.strip()]

        params = {
            "domainId": domain_id,
            "users": [user_data],
        }
        result = self.client.call("Users.create", params=params)
        logger.info(f"[KerioAdmin] Пользователь '{clean_login}' успешно создан в Kerio Connect.")
        return result

    def update_user(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        description: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        quota_mb: Optional[int] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Обновляет атрибуты существующего пользователя в Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.
            full_name (Optional[str]): Новое полное имя.
            description (Optional[str]): Новое описание / должность.
            is_enabled (Optional[bool]): Флаг активности.
            quota_mb (Optional[int]): Новое значение квоты ящика в МБ.
            extra_fields (Optional[Dict[str, Any]]): Дополнительные параметры Kerio.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        pattern: Dict[str, Any] = {}
        if full_name is not None:
            pattern["fullName"] = full_name.strip()
        if description is not None:
            pattern["description"] = description.strip()
        if is_enabled is not None:
            pattern["isEnabled"] = is_enabled
        if quota_mb is not None:
            pattern["itemBox"] = {
                "limit": quota_mb,
                "isEnabled": quota_mb > 0,
            }
        if extra_fields:
            pattern.update(extra_fields)

        params = {
            "userIds": [user_id],
            "pattern": pattern,
        }
        result = self.client.call("Users.set", params=params)
        logger.info(f"[KerioAdmin] Пользователь ID '{user_id}' успешно обновлен.")
        return result

    def set_password(self, user_id: str, password: str) -> Dict[str, Any]:
        """Устанавливает новый пароль для пользователя Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.
            password (str): Новый пароль в открытом виде.

        Returns:
            Dict[str, Any]: Результат вызова API.

        Raises:
            KerioValidationError: Если пароль пустой.
        """
        if not password:
            raise KerioValidationError("Пароль не может быть пустым.")

        try:
            return self.client.call("Users.setPassword", params={"userIds": [user_id], "password": password})
        except Exception:
            # Fallback на метод Users.set
            return self.client.call("Users.set", params={"userIds": [user_id], "pattern": {"password": password}})

    def set_enabled(self, user_id: str, is_enabled: bool) -> Dict[str, Any]:
        """Блокирует или разблокирует учетную запись пользователя в Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.
            is_enabled (bool): True — активен, False — заблокирован.

        Returns:
            Dict[str, Any]: Результат вызова API.
        """
        return self.update_user(user_id=user_id, is_enabled=is_enabled)

    def remove_user(self, user_id: str) -> Dict[str, Any]:
        """Удаляет пользователя с сервера Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        result = self.client.call("Users.remove", params={"userIds": [user_id]})
        logger.warning(f"[KerioAdmin] Пользователь ID '{user_id}' удален из Kerio Connect.")
        return result
