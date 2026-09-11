"""Модуль управления списками рассылки (Mailing Lists) в Kerio Connect Administration API.

Официальная спецификация Kerio Connect IDL (MailingLists.idl):
- MailingLists.get: чтение списков рассылки домена (обязательный параметр domainId);
- MailingLists.getMlUserList: получение списка участников/модераторов (mlId, query);
- MailingLists.addMlUserList: добавление участников (mlId, members: [UserOrEmail]);
- MailingLists.removeMlUserList: удаление участников (mlId, members: [UserOrEmail]);
- MailingLists.create: создание нового списка рассылки;
- MailingLists.set: редактирование параметров списка;
- MailingLists.remove: удаление списков рассылки.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import KerioAPIError

logger = logging.getLogger(__name__)


class MailingListManager:
    """Менеджер операций со списками рассылки (Mailing Lists) в Kerio Connect.

    Attributes:
        client (KerioConnectAdminClient): Авторизованный клиент Kerio Connect API.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер списков рассылки.

        Args:
            client (KerioConnectAdminClient): Клиент Kerio Connect API.
        """
        self.client = client

    def _resolve_domain_id(self, domain_id_or_name: Optional[str] = None) -> Optional[str]:
        """Преобразует имя домена (например, 'barkol.ru') в системный domainId Kerio Connect.

        Args:
            domain_id_or_name (Optional[str]): Имя домена или системный ID.

        Returns:
            Optional[str]: Системный ID домена (domainId) или None, если домен не передан.
        """
        if not domain_id_or_name or domain_id_or_name == "all":
            return None

        # Если переданная строка уже выглядит как системный ID Kerio Connect
        if domain_id_or_name.startswith("keriodb://") or "/" in domain_id_or_name:
            return domain_id_or_name

        try:
            from mailbox_app.services.kerio.domains import DomainManager
            dom_mgr = DomainManager(self.client)
            return dom_mgr.get_domain_id(domain_id_or_name)
        except Exception as err:
            logger.debug(f"[MailingListManager] Не удалось разрешить ID для домена '{domain_id_or_name}': {err}")
            return None

    def get_mailing_lists(
        self,
        domain_id_or_name: Optional[str] = None,
        domain_id: Optional[str] = None,
        query_string: Optional[str] = None,
        start: int = 0,
        limit: int = -1,
    ) -> List[Dict[str, Any]]:
        """Получает список всех доступных списков рассылки домена или всех доменов сервера.

        Kerio Connect Administration API IDL требует обязательной передачи domainId в метод
        MailingLists.get. Если домен не передан, автоматически опрашиваются все зарегистрированные
        домены сервера через Domains.get и их списки рассылки объединяются.

        Args:
            domain_id_or_name (Optional[str]): Имя домена (например, 'barkol.ru') или системный ID.
            domain_id (Optional[str]): Алиас для domain_id_or_name (обратная совместимость).
            query_string (Optional[str]): Опциональная строка поиска.
            start (int): Смещение выборки.
            limit (int): Максимальное количество записей (-1 — без ограничений).

        Returns:
            List[Dict[str, Any]]: Список нормализованных словарей списков рассылки:
                - id (str): уникальный идентификатор (mlId, например 'keriodb://mailinglist/...');
                - name (str): имя списка (локальная часть email);
                - email (str): полный email адрес рассылки (например, 'all-staff@barkol.ru');
                - domainId (str): системный ID домена;
                - description (str): текстовое описание;
                - membersCount (int): количество подписчиков;
                - raw (dict): исходный ответ сервера Kerio Connect.
        """
        target_domain = domain_id_or_name or domain_id
        resolved_domain_id = self._resolve_domain_id(target_domain)

        query: Dict[str, Any] = {"start": start, "limit": limit}
        if query_string:
            query["queryString"] = query_string.strip()

        # Карта сопоставления ID домена -> имя домена для формирования корректного email
        domain_names_map: Dict[str, str] = {}
        domains_list: List[Dict[str, Any]] = []

        try:
            from mailbox_app.services.kerio.domains import DomainManager
            domains_list = DomainManager(self.client).get_domains()
            for d in domains_list:
                d_id = str(d.get("id", "")).strip()
                d_name = str(d.get("name", "")).strip()
                if d_id and d_name:
                    domain_names_map[d_id] = d_name
        except Exception as dom_err:
            logger.debug(f"[MailingListManager] Ошибка чтения реестра доменов: {dom_err}")

        # Если конкретный домен не указан, опрашиваем каждый домен по очереди
        target_domain_ids: List[str] = []
        if resolved_domain_id:
            target_domain_ids = [resolved_domain_id]
        elif domains_list:
            target_domain_ids = [str(d.get("id")) for d in domains_list if d.get("id")]
        else:
            # Fallback: пробуем получить дефолтный домен barkol.ru
            try:
                from mailbox_app.services.kerio.domains import DomainManager
                def_id = DomainManager(self.client).get_domain_id("barkol.ru")
                target_domain_ids = [def_id]
            except Exception:
                target_domain_ids = []

        all_raw_mls: List[Dict[str, Any]] = []
        for d_id in target_domain_ids:
            try:
                params: Dict[str, Any] = {
                    "query": query,
                    "domainId": d_id,
                }
                res = self.client.call("MailingLists.get", params=params)
                ml_list = (
                    res.get("list", [])
                    if isinstance(res, dict)
                    else (res if isinstance(res, list) else [])
                )
                all_raw_mls.extend(ml_list)
            except Exception as exc:
                d_name = domain_names_map.get(d_id, d_id)
                logger.warning(f"[MailingListManager] Ошибка вызова MailingLists.get для домена '{d_name}': {exc}")

        normalized_lists: List[Dict[str, Any]] = []
        for ml in all_raw_mls:
            if not isinstance(ml, dict):
                continue
            ml_id = str(ml.get("id", "")).strip()
            ml_name = str(ml.get("name", "")).strip()
            ml_dom_id = str(ml.get("domainId", "")).strip()
            dom_name = domain_names_map.get(ml_dom_id, "barkol.ru")
            primary_email = f"{ml_name}@{dom_name}" if ml_name else ""
            ml_desc = str(ml.get("description", "") or "").strip()
            members_count = int(ml.get("membersCount", 0) or 0)

            normalized_lists.append({
                "id": ml_id,
                "name": ml_name,
                "email": primary_email,
                "domainId": ml_dom_id,
                "domainName": dom_name,
                "description": ml_desc,
                "membersCount": members_count,
                "raw": ml,
            })

        normalized_lists.sort(key=lambda x: str(x.get("name", "")).casefold())
        return normalized_lists

    def get_members(self, mailing_list_id: str) -> List[Dict[str, Any]]:
        """Получает список участников и модераторов конкретного списка рассылки.

        Вызывает официальный IDL-метод Kerio Connect: MailingLists.getMlUserList.

        Args:
            mailing_list_id (str): Идентификатор списка рассылки в Kerio Connect (mlId).

        Returns:
            List[Dict[str, Any]]: Список словарей структуры UserOrEmail:
                - hasId (bool): True, если участник является пользователем Kerio;
                - userId (str): Системный ID пользователя (например, 'keriodb://user/...');
                - emailAddress (str): Email адрес (заполнен, если hasId == False);
                - fullName (str): Полное имя / ФИО;
                - kind (str): 'Member' или 'Moderator'.
        """
        raw_id = mailing_list_id.strip()
        if not raw_id:
            return []

        try:
            params = {
                "mlId": raw_id,
                "query": {"start": 0, "limit": -1},
            }
            res = self.client.call("MailingLists.getMlUserList", params=params)
            if isinstance(res, dict) and "list" in res:
                return res.get("list", [])
            if isinstance(res, list):
                return res
            return []
        except Exception as exc:
            logger.warning(f"[MailingListManager] Ошибка получения участников MailingLists.getMlUserList для {raw_id}: {exc}")
            return []

    def get_subscribers(self, mailing_list_id: str) -> List[Dict[str, Any]]:
        """Алиас для get_members с обратной совместимостью структуры словарей.

        Args:
            mailing_list_id (str): Идентификатор списка рассылки в Kerio Connect (mlId).

        Returns:
            List[Dict[str, Any]]: Список словарей участников.
        """
        members = self.get_members(mailing_list_id)
        subscribers: List[Dict[str, Any]] = []
        for m in members:
            if not isinstance(m, dict):
                continue
            has_id = bool(m.get("hasId", False))
            u_id = str(m.get("userId", "")).strip()
            email_addr = str(m.get("emailAddress", "")).strip()
            full_name = str(m.get("fullName", "")).strip()
            kind = str(m.get("kind", "Member")).strip()

            subscribers.append({
                "hasId": has_id,
                "userId": u_id,
                "id": u_id,
                "email": email_addr,
                "emailAddress": email_addr,
                "name": full_name,
                "fullName": full_name,
                "kind": kind,
                "raw": m,
            })
        return subscribers

    def add_user_to_mailing_list(
        self,
        mailing_list_id: str,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
        full_name: str = "",
        membership: str = "Member",
        domain_id: Optional[str] = None,
    ) -> bool:
        """Добавляет пользователя Kerio Connect или email в список рассылки.

        Вызывает официальный метод IDL Kerio Connect: MailingLists.addMlUserList.

        Args:
            mailing_list_id (str): ID списка рассылки в Kerio Connect (mlId).
            email (Optional[str]): Email адрес (заполняется, если user_id не задан).
            user_id (Optional[str]): Системный ID пользователя Kerio Connect (userId).
            full_name (str): Полное имя (ФИО) пользователя.
            membership (str): Тип членства ('Member' или 'Moderator'). По умолчанию 'Member'.
            domain_id (Optional[str]): Опциональный идентификатор домена.

        Returns:
            bool: True при успешном добавлении.
        """
        if membership not in {"Member", "Moderator"}:
            membership = "Member"

        raw_ml_id = mailing_list_id.strip()
        clean_user_id = str(user_id).strip() if user_id else ""
        clean_email = str(email).strip().lower() if email else ""

        if clean_user_id:
            member = {
                "hasId": True,
                "userId": clean_user_id,
                "emailAddress": "",
                "fullName": full_name or "",
                "kind": membership,
            }
        elif clean_email:
            member = {
                "hasId": False,
                "userId": "",
                "emailAddress": clean_email,
                "fullName": full_name or "",
                "kind": membership,
            }
        else:
            logger.warning("[MailingListManager] Не указан ни user_id, ни email для добавления в список рассылки.")
            return False

        try:
            self.client.call(
                "MailingLists.addMlUserList",
                params={
                    "mlId": raw_ml_id,
                    "members": [member],
                },
            )
            logger.info(
                f"[MailingListManager] Участник '{clean_user_id or clean_email}' "
                f"успешно добавлен в список рассылки {raw_ml_id}."
            )
            return True
        except Exception as exc:
            logger.error(f"[MailingListManager] Ошибка добавления в список рассылки {raw_ml_id}: {exc}")
            return False

    def remove_user_from_mailing_list(
        self,
        mailing_list_id: str,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
        full_name: str = "",
    ) -> bool:
        """Исключает пользователя или email из списка рассылки.

        Вызывает официальный метод IDL Kerio Connect: MailingLists.removeMlUserList.

        Args:
            mailing_list_id (str): ID списка рассылки в Kerio Connect (mlId).
            email (Optional[str]): Email адрес пользователя.
            user_id (Optional[str]): ID пользователя Kerio Connect (userId).
            full_name (str): Полное имя пользователя.

        Returns:
            bool: True при успешном исключении.
        """
        raw_ml_id = mailing_list_id.strip()
        clean_user_id = str(user_id).strip() if user_id else ""
        clean_email = str(email).strip().lower() if email else ""

        if clean_user_id:
            member = {
                "hasId": True,
                "userId": clean_user_id,
                "emailAddress": "",
                "fullName": full_name or "",
                "kind": "Member",
            }
        elif clean_email:
            member = {
                "hasId": False,
                "userId": "",
                "emailAddress": clean_email,
                "fullName": full_name or "",
                "kind": "Member",
            }
        else:
            return False

        try:
            self.client.call(
                "MailingLists.removeMlUserList",
                params={
                    "mlId": raw_ml_id,
                    "members": [member],
                },
            )
            logger.info(
                f"[MailingListManager] Участник '{clean_user_id or clean_email}' "
                f"исключен из списка рассылки {raw_ml_id}."
            )
            return True
        except Exception as exc:
            logger.error(f"[MailingListManager] Ошибка исключения из списка рассылки {raw_ml_id}: {exc}")
            return False

    def get_user_memberships(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        domain_id: Optional[str] = None,
    ) -> List[str]:
        """Определяет, в каких списках рассылки состоит указанный пользователь или email.

        Args:
            user_id (Optional[str]): Системный ID пользователя (например, 'keriodb://user/...').
            email (Optional[str]): Email адрес пользователя (например, 'i.ivanov@barkol.ru').
            domain_id (Optional[str]): Идентификатор домена или имя домена.

        Returns:
            List[str]: Список идентификаторов списков рассылки (MailingList ID / mlId),
                в которых состоит пользователь.
        """
        clean_email = str(email).strip().lower() if email else ""
        clean_uid = str(user_id).strip() if user_id else ""
        subscribed_ml_ids: List[str] = []

        all_mls = self.get_mailing_lists(domain_id_or_name=domain_id)
        for ml in all_mls:
            ml_id = ml.get("id")
            if not ml_id:
                continue
            members = self.get_members(ml_id)
            for m in members:
                if not isinstance(m, dict):
                    continue
                m_email = str(m.get("emailAddress", "") or m.get("email", "")).strip().lower()
                m_uid = str(m.get("userId", "") or m.get("id", "")).strip()

                if clean_uid and clean_uid == m_uid:
                    subscribed_ml_ids.append(ml_id)
                    break
                if clean_email and clean_email == m_email:
                    subscribed_ml_ids.append(ml_id)
                    break

        return list(set(subscribed_ml_ids))

    def set_user_memberships(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        selected_mailing_list_ids: Optional[List[str]] = None,
        target_list_ids: Optional[List[str]] = None,
        domain_id: Optional[str] = None,
        full_name: str = "",
    ) -> Dict[str, Any]:
        """Синхронизирует подписки пользователя на списки рассылки домена.

        Добавляет пользователя в выбранные списки рассылки и исключает из невыбранных,
        в которых он состоял ранее.

        Args:
            user_id (Optional[str]): Системный ID пользователя в Kerio Connect.
            email (Optional[str]): Email адрес пользователя.
            selected_mailing_list_ids (Optional[List[str]]): Список целевых ID рассылок.
            target_list_ids (Optional[List[str]]): Алиас для selected_mailing_list_ids.
            domain_id (Optional[str]): Идентификатор домена.
            full_name (str): Полное имя (ФИО) пользователя.

        Returns:
            Dict[str, Any]: Отчет о добавленных и удаленных подписках:
                {'success': bool, 'added': [...], 'removed': [...], 'total_selected': int}.
        """
        raw_targets = selected_mailing_list_ids if selected_mailing_list_ids is not None else target_list_ids
        selected_set: Set[str] = set(str(item).strip() for item in (raw_targets or []) if str(item).strip())

        current_subs: Set[str] = set(
            self.get_user_memberships(user_id=user_id, email=email, domain_id=domain_id)
        )

        to_add = selected_set - current_subs
        to_remove = current_subs - selected_set

        added_ok: List[str] = []
        removed_ok: List[str] = []

        for ml_id in to_add:
            if self.add_user_to_mailing_list(
                mailing_list_id=ml_id,
                email=email,
                user_id=user_id,
                full_name=full_name,
                domain_id=domain_id,
            ):
                added_ok.append(ml_id)

        for ml_id in to_remove:
            if self.remove_user_from_mailing_list(
                mailing_list_id=ml_id,
                email=email,
                user_id=user_id,
                full_name=full_name,
            ):
                removed_ok.append(ml_id)

        logger.info(
            f"[MailingListManager] Синхронизация рассылок для '{user_id or email}': "
            f"добавлено {len(added_ok)}, удалено {len(removed_ok)}."
        )
        return {
            "success": True,
            "added": added_ok,
            "removed": removed_ok,
            "total_selected": len(selected_set),
        }
