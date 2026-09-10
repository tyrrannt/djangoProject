"""Менеджер управления почтовыми доменами Kerio Connect Administration API."""

import logging
from typing import Any, Dict, List, Optional

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.exceptions import KerioAPIError, KerioObjectNotFoundError

logger = logging.getLogger(__name__)


class DomainManager:
    """Менеджер для работы с почтовыми доменами Kerio Connect.

    Attributes:
        client (KerioConnectAdminClient): Авторизованный клиент Kerio Connect.
    """

    def __init__(self, client: KerioConnectAdminClient) -> None:
        """Инициализирует менеджер доменов.

        Args:
            client (KerioConnectAdminClient): Экземпляр клиента API.
        """
        self.client = client

    def get_domains(
        self,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Получает список всех зарегистрированных доменов на сервере Kerio Connect.

        Args:
            query (Optional[Dict[str, Any]]): Параметры поиска/пагинации/сортировки Kerio Connect.

        Returns:
            List[Dict[str, Any]]: Список словарей с атрибутами доменов (id, name, description, isPrimary, etc.).

        Raises:
            KerioAPIError: При ошибке выполнения запроса API.
        """
        params: Dict[str, Any] = {"query": query or {}}
        result = self.client.call("Domains.get", params=params)
        if isinstance(result, dict) and "list" in result:
            return result["list"]
        if isinstance(result, list):
            return result
        return []

    def get_domain_by_name(self, name: str) -> Dict[str, Any]:
        """Находит и возвращает данные домена по его имени (например, 'barkol.ru').

        Args:
            name (str): Имя домена без учета регистра.

        Returns:
            Dict[str, Any]: Словарь с атрибутами найденного домена.

        Raises:
            KerioObjectNotFoundError: Если домен с указанным именем не найден.
        """
        clean_name = name.strip().lower()
        domains = self.get_domains()
        for dom in domains:
            if dom.get("name", "").strip().lower() == clean_name:
                return dom

        raise KerioObjectNotFoundError(f"Домен '{name}' не найден на сервере Kerio Connect.")

    def get_domain_id(self, name: str = "barkol.ru") -> str:
        """Возвращает системный ID домена в Kerio Connect по его имени.

        Args:
            name (str): Имя домена. По умолчанию 'barkol.ru'.

        Returns:
            str: Идентификатор домена (domainId).
        """
        dom = self.get_domain_by_name(name)
        dom_id = dom.get("id")
        if not dom_id:
            raise KerioObjectNotFoundError(f"У домена '{name}' отсутствует атрибут 'id'.")
        return str(dom_id)
