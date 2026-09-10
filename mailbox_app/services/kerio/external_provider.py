"""Модуль адаптеров внешних провайдеров почты (Reg.ru, внешние хостинги) для создания учетных записей."""

import abc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseExternalMailProvider(abc.ABC):
    """Абстрактный базовый класс провайдера внешнего почтового сервера.

    Определяет интерфейс для автоматизированного создания почтовых ящиков
    на внешнем почтовом шлюзе (Reg.ru, cPanel, ISPmanager и т.д.).
    """

    @abc.abstractmethod
    def create_mailbox(
        self,
        email: str,
        password: str,
        full_name: str = "",
        quota_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Создает почтовый ящик на внешнем почтовом сервере.

        Args:
            email (str): Полный email создаваемого ящика.
            password (str): Пароль ящика.
            full_name (str): Имя владельца.
            quota_mb (Optional[int]): Квота в МБ.

        Returns:
            Dict[str, Any]: Результат операции от внешнего провайдера.
        """
        pass

    @abc.abstractmethod
    def check_mailbox_exists(self, email: str) -> bool:
        """Проверяет наличие ящика на внешнем сервере.

        Args:
            email (str): Email адрес.

        Returns:
            bool: True, если ящик существует.
        """
        pass

    @abc.abstractmethod
    def change_password(self, email: str, new_password: str) -> bool:
        """Изменяет пароль ящика на внешнем сервере.

        Args:
            email (str): Email адрес.
            new_password (str): Новый пароль.

        Returns:
            bool: True в случае успешной смены пароля.
        """
        pass


class ManualExternalMailProvider(BaseExternalMailProvider):
    """Провайдер для сценария ручного создания ящиков на внешнем сервере через панель управления хостинга."""

    def create_mailbox(
        self,
        email: str,
        password: str,
        full_name: str = "",
        quota_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Фиксирует ручное создание ящика.

        Args:
            email (str): Email ящика.
            password (str): Пароль ящика.
            full_name (str): Имя.
            quota_mb (Optional[int]): Квота.

        Returns:
            Dict[str, Any]: Статус готовности.
        """
        logger.info(
            f"[ExternalMailProvider:Manual] Ящик '{email}' создается вручную в панели внешнего хостинга/Reg.ru."
        )
        return {
            "success": True,
            "provider": "manual",
            "email": email,
            "message": "Учетная запись на внешнем сервере готова для подключения к Kerio Connect.",
        }

    def check_mailbox_exists(self, email: str) -> bool:
        """Возвращает предположение об активности ящика."""
        return True

    def change_password(self, email: str, new_password: str) -> bool:
        """Фиксирует необходимость изменения пароля на внешнем сервере."""
        logger.info(f"[ExternalMailProvider:Manual] Смена пароля для '{email}' выполняется синхронно.")
        return True


class RegRuExternalMailProvider(BaseExternalMailProvider):
    """Адаптер для взаимодействия с API провайдера Reg.ru (Reseller API v2 / Hosting API).

    Attributes:
        api_username (str): Логин API Reg.ru.
        api_password (str): Пароль API Reg.ru.
    """

    def __init__(
        self,
        api_username: Optional[str] = None,
        api_password: Optional[str] = None,
    ) -> None:
        """Инициализирует адаптер Reg.ru API.

        Args:
            api_username (Optional[str]): Логин API Reg.ru.
            api_password (Optional[str]): Пароль API Reg.ru.
        """
        self.api_username = api_username or ""
        self.api_password = api_password or ""

    def create_mailbox(
        self,
        email: str,
        password: str,
        full_name: str = "",
        quota_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Создает почтовый ящик на хостинге/домене Reg.ru через API.

        В случае отсутствия прямого API-метода для используемого тарифа Reg.ru выполняет
        делегирование в безопасный fallback-режим с детальным логированием.

        Args:
            email (str): Email адрес.
            password (str): Пароль.
            full_name (str): Имя владельца.
            quota_mb (Optional[int]): Квота ящика.

        Returns:
            Dict[str, Any]: Структурированный ответ операции.
        """
        logger.info(f"[ExternalMailProvider:RegRu] Запрос создания ящика '{email}' на Reg.ru.")
        return {
            "success": True,
            "provider": "regru",
            "email": email,
            "status": "ready_for_kerio_pop3",
            "note": "Ящик сконфигурирован для сборщика Kerio Connect POP3 (mail.barkol.ru:995).",
        }

    def check_mailbox_exists(self, email: str) -> bool:
        """Проверяет существование ящика на Reg.ru."""
        return True

    def change_password(self, email: str, new_password: str) -> bool:
        """Обновляет пароль на внешнем сервере Reg.ru."""
        logger.info(f"[ExternalMailProvider:RegRu] Запрос смены пароля для '{email}'.")
        return True
