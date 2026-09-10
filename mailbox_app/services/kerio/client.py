"""Базовый клиент взаимодействия с Kerio Connect 9.4.1 Administration API по протоколу JSON-RPC."""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
import urllib3

from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioAuthenticationError,
    KerioConnectionError,
    KerioObjectNotFoundError,
    KerioSessionExpired,
    KerioValidationError,
)
from mailbox_app.services.kerio.utils import get_django_setting

logger = logging.getLogger(__name__)

# Подавление предупреждений о самоподписанных SSL-сертификатах Kerio Connect при verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class KerioConnectAdminClient:
    """Клиент Kerio Connect Administration API (JSON-RPC over HTTPS).

    Обеспечивает авторизацию административной сессии (Session.login/logout),
    хранение и передачу сессионных токенов (X-Token, куки SESSION_CONNECT_WEBADMIN),
    автоматическое обновление протухших сессий и централизованную обработку ошибок.

    Attributes:
        api_url (str): Полный URL эндпоинта JSON-RPC (например, https://192.168.10.242:4040/admin/api/jsonrpc/).
        username (str): Логин администратора Kerio Connect.
        password (str): Пароль администратора Kerio Connect.
        verify_ssl (bool): Флаг проверки SSL-сертификата.
        timeout (int): Таймаут сетевого запроса в секундах.
        session (requests.Session): HTTP-сессия для переиспользования TCP-соединений.
        token (Optional[str]): Текущий активный токен сессии Kerio Connect.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Инициализирует экземпляр клиента Kerio Connect.

        Args:
            api_url (Optional[str]): URL JSON-RPC эндпоинта. Если None, берется из settings.KERIO_API_URL.
            username (Optional[str]): Логин администратора. Если None, берется из settings.KERIO_API_USER.
            password (Optional[str]): Пароль администратора. Если None, берется из settings.KERIO_API_PASSWORD.
            verify_ssl (Optional[bool]): Проверка SSL. Если None, берется из settings.KERIO_API_VERIFY_SSL.
            timeout (Optional[int]): Таймаут в секундах. Если None, берется из settings.KERIO_API_TIMEOUT.
        """
        self.api_url = str(api_url or get_django_setting("KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/") or "https://192.168.10.242:4040/admin/api/jsonrpc/")
        self.username = str(username or get_django_setting("KERIO_API_USER", "") or "")
        self.password = str(password or get_django_setting("KERIO_API_PASSWORD", "") or "")
        self.verify_ssl = (
            verify_ssl
            if verify_ssl is not None
            else bool(get_django_setting("KERIO_API_VERIFY_SSL", False))
        )
        self.timeout = int(timeout or get_django_setting("KERIO_API_TIMEOUT", 15) or 15)

        self.session: requests.Session = requests.Session()
        self.token: Optional[str] = None
        self._request_id: int = 1

    def __enter__(self) -> "KerioConnectAdminClient":
        """Вход в контекстный менеджер: выполняет авторизацию при отсутствии активного токена.

        Returns:
            KerioConnectAdminClient: Экземпляр авторизованного клиента.
        """
        if not self.token:
            self.login()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Выход из контекстного менеджера."""
        pass

    def _get_next_id(self) -> int:
        """Генерирует монотонно возрастающий идентификатор JSON-RPC запроса.

        Returns:
            int: Порядковый номер запроса.
        """
        self._request_id += 1
        return self._request_id

    def login(self) -> str:
        """Выполняет аутентификацию администратора на сервере Kerio Connect (Session.login).

        Returns:
            str: Полученный авторизационный токен сессии.

        Raises:
            KerioAuthenticationError: При неверном логине/пароле или их отсутствии.
            KerioConnectionError: При сетевых ошибках или недоступности сервера.
            KerioAPIError: При прочих ошибках API Kerio.
        """
        if not self.username or not self.password:
            raise KerioAuthenticationError(
                "Учетные данные администратора Kerio Connect не настроены. "
                "Укажите переменные KERIO_API_USER и KERIO_API_PASSWORD в файле .env."
            )

        # Очистка устаревших сессионных кук и заголовков перед запросом авторизации
        self.token = None
        self.session.cookies.clear()
        self.session.headers.pop("X-Token", None)

        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "Session.login",
            "params": {
                "userName": self.username,
                "password": self.password,
                "application": {
                    "name": "Barkol Corporate Portal (Mailbox Admin)",
                    "vendor": "Barkol Aviation",
                    "version": "1.0.0",
                },
            },
        }

        try:
            response = self.session.post(
                self.api_url,
                json=payload,
                verify=self.verify_ssl,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as err:
            logger.error(f"[KerioAdmin] Таймаут подключения к {self.api_url}: {err}")
            raise KerioConnectionError(f"Превышен таймаут подключения к Kerio Connect ({self.timeout}с).") from err
        except requests.exceptions.RequestException as err:
            logger.error(f"[KerioAdmin] Сетевая ошибка при вызове Session.login: {err}")
            raise KerioConnectionError(f"Ошибка сетевого соединения с сервером Kerio Connect: {err}") from err
        except ValueError as err:
            logger.error(f"[KerioAdmin] Некорректный JSON в ответе Session.login: {err}")
            raise KerioAPIError("Сервер Kerio Connect вернул некорректный ответ (не JSON).") from err

        if "error" in data and data["error"]:
            err_obj = data["error"]
            err_msg = err_obj.get("message", "Ошибка авторизации Kerio")
            err_code = err_obj.get("code")
            logger.warning(f"[KerioAdmin] Ошибка авторизации в Kerio Connect (код {err_code}): {err_msg}")
            raise KerioAuthenticationError(f"Ошибка авторизации в Kerio Connect: {err_msg}", code=err_code, data=err_obj)

        result = data.get("result", {})
        self.token = result.get("token")
        if not self.token:
            raise KerioAuthenticationError("Сервер Kerio Connect не вернул токен сессии в ответе Session.login.")

        self.session.headers.update({
            "X-Token": self.token,
            "Content-Type": "application/json",
        })
        if not self.session.cookies.get("SESSION_CONNECT_WEBADMIN"):
            self.session.cookies.set("SESSION_CONNECT_WEBADMIN", self.token)
        logger.info(f"[KerioAdmin] Успешная авторизация в Kerio Connect под пользователем '{self.username}'.")
        return self.token

    def logout(self) -> bool:
        """Завершает текущую административную сессию на сервере Kerio Connect (Session.logout).

        Returns:
            bool: True в случае успешного завершения сессии.
        """
        token_to_close = self.token
        self.token = None

        if token_to_close:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._get_next_id(),
                    "method": "Session.logout",
                    "params": {},
                    "token": token_to_close,
                }
                headers = {
                    "Content-Type": "application/json",
                    "X-Token": token_to_close,
                }
                self.session.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    verify=self.verify_ssl,
                    timeout=min(self.timeout, 5),
                )
            except Exception as exc:
                logger.debug(f"[KerioAdmin] Фоновое завершение сессии: {exc}")

        try:
            self.session.close()
        except Exception:
            pass

        self.session = requests.Session()
        return True

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        retry_on_expired: bool = True,
        suppress_log: bool = False,
    ) -> Any:
        """Выполняет вызов произвольного JSON-RPC метода API Kerio Connect.

        Args:
            method (str): Наименование метода API (например, 'Domains.get', 'Users.create').
            params (Optional[Dict[str, Any]]): Словарь параметров метода.
            retry_on_expired (bool): Выполнять ли однократную повторную авторизацию при протухании сессии.
            suppress_log (bool): Подавлять ли вывод ошибок в лог на уровне ERROR (логировать на уровне DEBUG).

        Returns:
            Any: Поле 'result' из успешного ответа Kerio Connect.

        Raises:
            KerioAuthenticationError: При отказе авторизации.
            KerioSessionExpired: При недействительной сессии (если retry_on_expired=False).
            KerioConnectionError: При сбое сети или недоступности хоста.
            KerioAPIError: При ошибке бизнес-логики сервера Kerio.
        """
        if not self.token and method != "Session.login":
            self.login()

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": method,
            "params": params or {},
        }
        if self.token:
            payload["token"] = self.token

        headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            headers["X-Token"] = self.token

        try:
            response = self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as err:
            if not suppress_log:
                logger.error(f"[KerioAdmin] Таймаут вызова метода '{method}': {err}")
            raise KerioConnectionError(f"Превышен таймаут выполнения запроса к Kerio Connect ({self.timeout}с).") from err
        except requests.exceptions.RequestException as err:
            if not suppress_log:
                logger.error(f"[KerioAdmin] Сетевая ошибка при вызове метода '{method}': {err}")
            raise KerioConnectionError(f"Сетевой сбой при обращении к Kerio Connect: {err}") from err
        except ValueError as err:
            if not suppress_log:
                logger.error(f"[KerioAdmin] Некорректный JSON в ответе метода '{method}': {err}")
            raise KerioAPIError(f"Сервер Kerio вернул некорректный ответ при вызове {method}.") from err

        if "error" in data and data["error"]:
            err_obj = data["error"]
            err_code = err_obj.get("code")
            err_msg = err_obj.get("message", "Неизвестная ошибка Kerio API")

            msg_lower = err_msg.lower()
            is_session_expired = (
                self.token is not None
                and (
                    err_code == -32001
                    or "session expired" in msg_lower
                    or "invalid token" in msg_lower
                    or "please login first" in msg_lower
                )
            )

            if is_session_expired and retry_on_expired:
                logger.warning(f"[KerioAdmin] Сессия Kerio Connect протухла при вызове {method} ({err_msg}). Повторная авторизация...")
                self.token = None
                self.login()
                return self.call(method, params=params, retry_on_expired=False, suppress_log=suppress_log)

            if is_session_expired:
                raise KerioSessionExpired(err_msg, code=err_code, data=err_obj)

            if "permission denied" in msg_lower or "authentication" in msg_lower or "invalid user" in msg_lower:
                raise KerioAuthenticationError(err_msg, code=err_code, data=err_obj)

            if "not found" in msg_lower or err_code == -32601:
                raise KerioObjectNotFoundError(err_msg, code=err_code, data=err_obj)

            if suppress_log:
                logger.debug(f"[KerioAdmin] Ошибка API в методе '{method}' (код {err_code}): {err_msg}")
            else:
                logger.error(f"[KerioAdmin] Ошибка API в методе '{method}' (код {err_code}): {err_msg}")
            raise KerioAPIError(err_msg, code=err_code, data=err_obj)

        return data.get("result")
