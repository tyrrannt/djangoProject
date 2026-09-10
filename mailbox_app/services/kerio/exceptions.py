"""Модуль пользовательских исключений для взаимодействия с Kerio Connect Administration API."""

from typing import Any, Dict, Optional


class KerioAPIError(Exception):
    """Базовое исключение для всех ошибок Kerio Connect Administration API.

    Attributes:
        message (str): Сообщение об ошибке.
        code (Optional[int]): Код ошибки JSON-RPC или HTTP.
        data (Optional[Dict[str, Any]]): Дополнительные метаданные ответа API.
    """

    def __init__(
        self,
        message: str,
        code: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Инициализирует базовое исключение KerioAPIError.

        Args:
            message (str): Текст описания ошибки.
            code (Optional[int]): Числовой код ошибки.
            data (Optional[Dict[str, Any]]): Сырые данные об ошибке от сервера.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки.

        Returns:
            str: Форматированное описание с кодом, если он задан.
        """
        if self.code is not None:
            return f"[Код {self.code}] {self.message}"
        return self.message


class KerioConnectionError(KerioAPIError):
    """Исключение при сетевых сбоях, недоступности хоста или таймаутах подключения к Kerio Connect."""

    pass


class KerioAuthenticationError(KerioAPIError):
    """Исключение при неверных учетных данных администратора Kerio Connect."""

    pass


class KerioSessionExpired(KerioAPIError):
    """Исключение при истечении срока действия административного токена/сессии Kerio Connect."""

    pass


class KerioValidationError(KerioAPIError):
    """Исключение при некорректных входных параметрах для методов API Kerio Connect."""

    pass


class KerioObjectNotFoundError(KerioAPIError):
    """Исключение, когда запрашиваемый объект (пользователь, домен, сборщик POP3) не найден в Kerio Connect."""

    pass
