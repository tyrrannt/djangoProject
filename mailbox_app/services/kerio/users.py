"""Менеджер управления почтовыми пользователями в Kerio Connect Administration API."""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

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
        limit: int = 500,
        order_by: str = "loginName",
        direction: str = "Asc",
    ) -> Dict[str, Any]:
        """Получает постраничный список пользователей Kerio Connect с возможностью фильтрации.

        Если domain_id не указан, автоматически запрашиваются все зарегистрированные домены
        сервера Kerio Connect и их пользователи объединяются в единый список.

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

        # Если domain_id не передан, Kerio Connect API требует явного domainId.
        # В этом случае опрашиваем все домены через Domains.get и объединяем пользователей.
        if not domain_id:
            try:
                domains_res = self.client.call("Domains.get", params={"query": {}})
                domains_list = (
                    domains_res.get("list", [])
                    if isinstance(domains_res, dict)
                    else (domains_res if isinstance(domains_res, list) else [])
                )
            except Exception as err:
                logger.warning(f"[UserManager] Ошибка получения списка доменов для Users.get: {err}")
                domains_list = []

            all_users: List[Dict[str, Any]] = []
            total = 0
            for d in domains_list:
                d_id = d.get("id")
                if not d_id:
                    continue
                try:
                    d_res = self.get_users(
                        domain_id=d_id,
                        query_string=query_string,
                        start=0,
                        limit=limit,
                        order_by=order_by,
                        direction=direction,
                    )
                    all_users.extend(d_res.get("list", []))
                    total += d_res.get("totalItems", len(d_res.get("list", [])))
                except Exception as d_err:
                    logger.warning(f"[UserManager] Не удалось получить пользователей домена '{d.get('name')}': {d_err}")

            all_users.sort(
                key=lambda u: (
                    (u.get("fullName") or u.get("loginName") or u.get("email") or "")
                    .strip()
                    .casefold()
                )
            )
            return {"list": all_users, "totalItems": total or len(all_users)}

        params: Dict[str, Any] = {"domainId": domain_id, "query": query}
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
        raw_id = user_id.strip()
        if raw_id.startswith("keriodb:/") and not raw_id.startswith("keriodb://"):
            raw_id = "keriodb://" + raw_id[9:]

        result = self.client.call("Users.getDetails", params={"userIds": [raw_id]})
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
        """Ищет пользователя по логину в указанном домене или по всем доменам.

        Args:
            login_name (str): Логин пользователя (например, 'shakirov' или 'shakirov@barkol.ru').
            domain_id (Optional[str]): Идентификатор домена.

        Returns:
            Optional[Dict[str, Any]]: Словарь пользователя или None, если не найден.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        res = self.get_users(domain_id=domain_id, query_string=clean_login, limit=500)
        for user in res.get("list", []):
            if user.get("loginName", "").strip().lower() == clean_login:
                return user

        # Резервный поиск по всем пользователям без фильтра query_string (если сервер не применил substring)
        all_res = self.get_users(domain_id=domain_id, limit=500)
        for user in all_res.get("list", []):
            if user.get("loginName", "").strip().lower() == clean_login:
                return user
        return None

    def get_user_by_id_or_login(
        self,
        identifier: str,
        domain_name: Optional[str] = None,
        domain_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ищет пользователя Kerio Connect по логину или системному ID с защитой от нормализации URL.

        Поддерживает:
        - Имя пользователя (например, 'shakirov', 'grinyak', 'a.deryanin');
        - Полный email (например, 'grinyak@barkol.ru');
        - Системный ID вида 'keriodb://user/...';
        - Восстановление нормализованных веб-сервером URL-идентификаторов ('keriodb:/user/...').

        Args:
            identifier (str): Логин или системный ID пользователя.
            domain_name (Optional[str]): Имя домена (по умолчанию None).
            domain_id (Optional[str]): Идентификатор домена (по умолчанию None).

        Returns:
            Dict[str, Any]: Словарь с полными данными пользователя Kerio Connect.

        Raises:
            KerioObjectNotFoundError: Если пользователь с указанным идентификатором не найден.
        """
        raw_id = identifier.strip()
        if raw_id.startswith("keriodb:/") and not raw_id.startswith("keriodb://"):
            raw_id = "keriodb://" + raw_id[9:]

        # 1. Если это системный ID, получаем через Users.getDetails
        if raw_id.startswith("keriodb://"):
            try:
                return self.get_user_by_id(raw_id)
            except Exception as err:
                logger.debug(f"[UserManager] get_user_by_id не сработал для '{raw_id}': {err}")

        # 2. Поиск по логину через get_user_by_login
        clean_login = raw_id.split("@")[0].lower()
        user = self.get_user_by_login(clean_login, domain_id=domain_id)
        if user:
            u_id = user.get("id")
            if u_id:
                try:
                    return self.get_user_by_id(u_id)
                except Exception:
                    pass
            return user

        # 3. Полный перебор всех пользователей сервера при несовпадении регистра или алиаса
        res = self.get_users(domain_id=domain_id, limit=500)
        for u in res.get("list", []):
            u_login = u.get("loginName", "").strip().lower()
            u_email = u.get("emailAddresses", [f"{u_login}@barkol.ru"])[0].lower() if u.get("emailAddresses") else f"{u_login}@barkol.ru"
            if u_login == clean_login or u.get("id") == raw_id or u_email == raw_id.lower():
                u_id = u.get("id")
                if u_id:
                    try:
                        return self.get_user_by_id(u_id)
                    except Exception:
                        pass
                return u

        raise KerioObjectNotFoundError(f"Пользователь '{identifier}' не найден в Kerio Connect.")

    def create_user(
        self,
        domain_id: str,
        login_name: str,
        password: str,
        full_name: str = "",
        description: str = "",
        is_enabled: bool = True,
        auth_type: str = "UInternalAuth",
        quota_mb: Optional[int] = None,
        email_alias: Optional[str] = None,
        can_change_password: bool = False,
        first_name: str = "",
        middle_name: str = "",
        last_name: str = "",
        job_title: str = "",
        department: str = "",
        company: str = "Авиакомпания БАРКОЛ",
        phone: str = "",
        mobile_phone: str = "",
        contact: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Создает нового почтового пользователя в Kerio Connect.

        Args:
            domain_id (str): Идентификатор домена в Kerio Connect.
            login_name (str): Имя пользователя (логин) без доменной части.
            password (str): Пароль учетной записи.
            full_name (str): Полное имя (ФИО) сотрудника.
            description (str): Описание / должность.
            is_enabled (bool): Активен ли аккаунт (по умолчанию True).
            auth_type (str): Тип аутентификации в Kerio ('UInternalAuth', 'UWindowsNTAuth' и др., по умолчанию 'UInternalAuth').
            quota_mb (Optional[int]): Лимит дисковой квоты в мегабайтах (если None или 0 — без ограничений).
            email_alias (Optional[str]): Дополнительный псевдоним / алиас.
            can_change_password (bool): Разрешить ли пользователю менять свой пароль в Kerio Connect Client (по умолчанию False — запрещено).
            first_name (str): Имя сотрудника для вкладки «Контакт».
            middle_name (str): Отчество сотрудника для вкладки «Контакт».
            last_name (str): Фамилия сотрудника для вкладки «Контакт».
            job_title (str): Должность для вкладки «Контакт».
            department (str): Подразделение / отдел для вкладки «Контакт».
            company (str): Название организации для вкладки «Контакт» (по умолчанию 'Авиакомпания БАРКОЛ').
            phone (str): Рабочий / внутренний телефон для вкладки «Контакт».
            mobile_phone (str): Мобильный телефон для вкладки «Контакт».
            contact (Optional[Dict[str, Any]]): Произвольный словарь контактных данных Kerio Connect.

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

        # Нормализация authType: в спецификации Kerio Connect Administration API IDL перечисление UserAuthType
        # содержит значения: UInternalAuth, UWindowsNTAuth, UPamAuth, UKerberosAuth, UAppleAuth, ULDAPAuth.
        valid_auth_type = "UInternalAuth" if auth_type in ("UInternalAuth", "Internal", "TypeInternal", "Local", "AuthInternal") else auth_type

        user_data: Dict[str, Any] = {
            "domainId": domain_id,
            "loginName": clean_login,
            "password": password,
            "fullName": full_name.strip(),
            "description": description.strip(),
            "isEnabled": is_enabled,
            "authType": valid_auth_type,
            "canChangePassword": bool(can_change_password),
        }

        # Формирование контактных данных (вкладка «Контакт» в Kerio Connect)
        contact_dict: Dict[str, Any] = {}
        if contact and isinstance(contact, dict):
            contact_dict.update(contact)
        if first_name:
            contact_dict["firstName"] = first_name.strip()
        if middle_name:
            contact_dict["middleName"] = middle_name.strip()
        if last_name:
            contact_dict["lastName"] = last_name.strip()
        if job_title:
            contact_dict["jobTitle"] = job_title.strip()
        if department:
            contact_dict["department"] = department.strip()
        if company:
            contact_dict["company"] = company.strip()
        if phone:
            contact_dict["businessPhone"] = phone.strip()
        if mobile_phone:
            contact_dict["mobilePhone"] = mobile_phone.strip()

        if contact_dict:
            user_data["contact"] = contact_dict

        if quota_mb is not None and int(quota_mb) > 0:
            user_data["itemBox"] = {
                "limit": int(quota_mb),
                "isEnabled": True,
            }
        else:
            user_data["itemBox"] = {
                "limit": 0,
                "isEnabled": False,
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
        can_change_password: Optional[bool] = None,
        first_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        last_name: Optional[str] = None,
        job_title: Optional[str] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        mobile_phone: Optional[str] = None,
        contact: Optional[Dict[str, Any]] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Обновляет атрибуты существующего пользователя в Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.
            full_name (Optional[str]): Новое полное имя.
            description (Optional[str]): Новое описание / должность.
            is_enabled (Optional[bool]): Флаг активности.
            quota_mb (Optional[int]): Новое значение квоты ящика в МБ.
            can_change_password (Optional[bool]): Разрешить ли смену пароля в Kerio Connect Client.
            first_name (Optional[str]): Имя сотрудника для вкладки «Контакт».
            middle_name (Optional[str]): Отчество сотрудника для вкладки «Контакт».
            last_name (Optional[str]): Фамилия сотрудника для вкладки «Контакт».
            job_title (Optional[str]): Должность для вкладки «Контакт».
            department (Optional[str]): Подразделение для вкладки «Контакт».
            company (Optional[str]): Организация для вкладки «Контакт».
            phone (Optional[str]): Рабочий / внутренний телефон для вкладки «Контакт».
            mobile_phone (Optional[str]): Мобильный телефон для вкладки «Контакт».
            contact (Optional[Dict[str, Any]]): Словарь контактных параметров.
            extra_fields (Optional[Dict[str, Any]]): Дополнительные параметры Kerio.

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect.
        """
        raw_id = user_id.strip()
        if raw_id.startswith("keriodb:/") and not raw_id.startswith("keriodb://"):
            raw_id = "keriodb://" + raw_id[9:]

        pattern: Dict[str, Any] = {}
        if full_name is not None:
            pattern["fullName"] = full_name.strip()
        if description is not None:
            pattern["description"] = description.strip()
        if is_enabled is not None:
            pattern["isEnabled"] = is_enabled
        if can_change_password is not None:
            pattern["canChangePassword"] = bool(can_change_password)

        contact_dict: Dict[str, Any] = {}
        if contact and isinstance(contact, dict):
            contact_dict.update(contact)
        if first_name is not None:
            contact_dict["firstName"] = first_name.strip()
        if middle_name is not None:
            contact_dict["middleName"] = middle_name.strip()
        if last_name is not None:
            contact_dict["lastName"] = last_name.strip()
        if job_title is not None:
            contact_dict["jobTitle"] = job_title.strip()
        if department is not None:
            contact_dict["department"] = department.strip()
        if company is not None:
            contact_dict["company"] = company.strip()
        if phone is not None:
            contact_dict["businessPhone"] = phone.strip()
        if mobile_phone is not None:
            contact_dict["mobilePhone"] = mobile_phone.strip()

        if contact_dict:
            pattern["contact"] = contact_dict

        if quota_mb is not None:
            pattern["itemBox"] = {
                "limit": int(quota_mb) if quota_mb else 0,
                "isEnabled": bool(quota_mb and int(quota_mb) > 0),
            }
        if extra_fields:
            pattern.update(extra_fields)

        params = {
            "userIds": [raw_id],
            "pattern": pattern,
        }
        result = self.client.call("Users.set", params=params)
        logger.info(f"[KerioAdmin] Пользователь ID '{raw_id}' успешно обновлен.")
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

        raw_id = user_id.strip()
        if raw_id.startswith("keriodb:/") and not raw_id.startswith("keriodb://"):
            raw_id = "keriodb://" + raw_id[9:]

        try:
            return self.client.call("Users.setPassword", params={"userIds": [raw_id], "password": password})
        except Exception:
            # Fallback на метод Users.set
            return self.client.call("Users.set", params={"userIds": [raw_id], "pattern": {"password": password}})

    def set_enabled(self, user_id: str, is_enabled: bool) -> Dict[str, Any]:
        """Блокирует или разблокирует учетную запись пользователя в Kerio Connect.

        Args:
            user_id (str): Идентификатор пользователя.
            is_enabled (bool): True — активен, False — заблокирован.

        Returns:
            Dict[str, Any]: Результат вызова API.
        """
        return self.update_user(user_id=user_id, is_enabled=is_enabled)

    def remove_user(
        self,
        user_id: str,
        domain_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Удаляет пользователя с сервера Kerio Connect.

        Выполняет отказоустойчивое удаление пользователя через JSON-RPC метод API `Users.remove`
        с передачей массива структур параметров `requests` (`method: DeleteFolder`,
        `mode: DSModeDelete`, `removeReferences: True`, `targetUserId: ""`) в соответствии
        со спецификацией Kerio Connect Administration API IDL (`Users.idl`), а также
        поддерживает каскадные fallback-варианты при различных форматах идентификаторов (URI
        `keriodb://user/...` и GUID).

        Args:
            user_id (str): Идентификатор пользователя (полный URI `keriodb://user/...`, GUID или логин).
            domain_id (Optional[str]): Идентификатор домена (`keriodb://domain/...` или GUID, если известен).

        Returns:
            Dict[str, Any]: Ответ сервера Kerio Connect (например, `{'errors': []}`).

        Raises:
            KerioObjectNotFoundError: Если пользователь не найден на сервере.
            KerioAPIError: При ошибке API сервера Kerio Connect.
        """
        raw_id = user_id.strip()
        if raw_id.startswith("keriodb:/") and not raw_id.startswith("keriodb://"):
            raw_id = "keriodb://" + raw_id[9:]

        user_guid: Optional[str] = None
        extracted_domain_guid: Optional[str] = None

        if "keriodb://user/" in raw_id:
            try:
                parts = raw_id.replace("keriodb://user/", "").split("/")
                if len(parts) >= 2:
                    extracted_domain_guid = parts[0]
                    user_guid = parts[1]
                elif len(parts) == 1:
                    user_guid = parts[0]
            except Exception:
                pass

        resolved_domain_id = domain_id
        if not resolved_domain_id and extracted_domain_guid:
            resolved_domain_id = f"keriodb://domain/{extracted_domain_guid}"

        domain_guid: Optional[str] = None
        if resolved_domain_id:
            if "keriodb://domain/" in resolved_domain_id:
                domain_guid = resolved_domain_id.replace("keriodb://domain/", "").strip("/")
            else:
                domain_guid = resolved_domain_id.strip()

        # Варианты идентификаторов пользователя
        target_ids: List[str] = [raw_id]
        if user_guid and user_guid != raw_id:
            target_ids.append(user_guid)

        # Кандидаты вызова API Kerio Connect в порядке убывания приоритета
        candidates: List[Tuple[str, Dict[str, Any]]] = []

        # 1. Приоритетные вызовы по официальной спецификации IDL: Users.remove(in RemovalRequestList requests)
        for t_id in target_ids:
            # 1.1 Полная структура RemovalRequest
            candidates.append((
                "Users.remove",
                {
                    "requests": [
                        {
                            "userId": t_id,
                            "method": "DeleteFolder",
                            "mode": "DSModeDelete",
                            "removeReferences": True,
                            "targetUserId": "",
                        }
                    ]
                },
            ))
            # 1.2 Структура KeepFolder
            candidates.append((
                "Users.remove",
                {
                    "requests": [
                        {
                            "userId": t_id,
                            "method": "KeepFolder",
                            "mode": "DSModeDelete",
                            "removeReferences": True,
                            "targetUserId": "",
                        }
                    ]
                },
            ))
            # 1.3 Упрощенные структуры requests
            candidates.append((
                "Users.remove",
                {
                    "requests": [
                        {
                            "userId": t_id,
                            "method": "DeleteFolder",
                            "removeReferences": True,
                        }
                    ]
                },
            ))
            candidates.append((
                "Users.remove",
                {
                    "requests": [
                        {
                            "userId": t_id,
                            "removeReferences": True,
                        }
                    ]
                },
            ))
            candidates.append((
                "Users.remove",
                {
                    "requests": [
                        {
                            "userId": t_id,
                        }
                    ]
                },
            ))

        # 2. Варианты с domainId на верхнем уровне
        if resolved_domain_id:
            for t_id in target_ids:
                candidates.append((
                    "Users.remove",
                    {
                        "domainId": resolved_domain_id,
                        "requests": [
                            {
                                "userId": t_id,
                                "method": "DeleteFolder",
                                "mode": "DSModeDelete",
                                "removeReferences": True,
                                "targetUserId": "",
                            }
                        ],
                    },
                ))

        # 3. Fallback: альтернативные форматы ключей (request, userIds, ids)
        for t_id in target_ids:
            candidates.append((
                "Users.remove",
                {
                    "request": {
                        "userId": t_id,
                        "method": "DeleteFolder",
                        "mode": "DSModeDelete",
                        "removeReferences": True,
                        "targetUserId": "",
                    }
                },
            ))
            candidates.append((
                "Users.remove",
                {
                    "userIds": [t_id],
                    "request": {
                        "method": "DeleteFolder",
                        "mode": "DSModeDelete",
                        "removeReferences": True,
                        "targetUserId": "",
                    },
                },
            ))
            candidates.append(("Users.remove", {"userIds": [t_id]}))
            candidates.append(("Users.remove", {"ids": [t_id]}))

        last_exc: Optional[Exception] = None
        for method_name, params in candidates:
            try:
                result = self.client.call(method_name, params=params, suppress_log=True)
                # Проверяем, вернул ли сервер массив ошибок внутри result (out ErrorList errors)
                if isinstance(result, dict) and result.get("errors"):
                    err_list = result.get("errors", [])
                    if err_list:
                        err_msg = "; ".join([str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in err_list])
                        logger.warning(f"[KerioAdmin] Сервер вернул ошибку при удалении: {err_msg}")
                        raise KerioAPIError(f"Ошибка удаления пользователя в Kerio Connect: {err_msg}")

                logger.info(f"[KerioAdmin] Пользователь ID '{raw_id}' успешно удален вызовом {method_name}.")
                return result
            except (KerioAPIError, KerioObjectNotFoundError) as exc:
                last_exc = exc
                err_code = getattr(exc, "code", None)
                err_msg = str(exc)
                # Если метод не найден (-32601) или неверные параметры (-32602), пробуем следующий вариант
                if err_code in (-32601, -32602) or "invalid params" in err_msg.lower() or "method not found" in err_msg.lower():
                    logger.debug(f"[KerioAdmin] Вызов {method_name} с params={params} вернул ошибку [{err_code}]: {err_msg}. Пробуем следующий кандидат.")
                    continue
                # Иные критические ошибки (например, permission denied) выбрасываем сразу
                raise

        if last_exc:
            logger.error(f"[KerioAdmin] Не удалось удалить пользователя '{raw_id}': {last_exc}")
            raise last_exc
        raise KerioAPIError(f"Не удалось удалить пользователя '{raw_id}'.")


