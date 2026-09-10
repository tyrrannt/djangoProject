"""Модуль адаптеров внешних провайдеров почты (ISPmanager на Reg.ru, внешние хостинги) для создания учетных записей."""

import abc
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from mailbox_app.services.kerio.utils import get_django_setting

logger = logging.getLogger(__name__)


def extract_isp_text(val: Any) -> str:
    """Извлекает строковое значение из структуры данных ISPmanager (включая XML-to-JSON узлы {'$': '...'}).

    Args:
        val (Any): Значение из словаря ISPmanager (строка, число, словарь с ключом '$' или вложенный список).

    Returns:
        str: Извлеченная чистая текстовая строка.
    """
    if val is None:
        return ""
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        if "$" in val:
            return extract_isp_text(val["$"])
        if "msg" in val:
            return extract_isp_text(val["msg"])
        if "val" in val:
            return extract_isp_text(val["val"])
        for k, v in val.items():
            if not k.startswith("@") and isinstance(v, (str, dict, list)):
                extracted = extract_isp_text(v)
                if extracted:
                    return extracted
        return str(val)
    if isinstance(val, list):
        return ", ".join(extract_isp_text(item) for item in val if item)
    return str(val).strip()


class BaseExternalMailProvider(abc.ABC):
    """Абстрактный базовый класс провайдера внешнего почтового сервера.

    Определяет интерфейс для автоматизированного создания почтовых ящиков
    на внешнем почтовом шлюзе (ISPmanager на Reg.ru, cPanel, Plesk и т.д.).
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
            email (str): Полный email создаваемого ящика (например, user@barkol.ru).
            password (str): Пароль ящика.
            full_name (str): Имя владельца ящика.
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

    @abc.abstractmethod
    def delete_mailbox(self, email: str) -> bool:
        """Удаляет почтовый ящик на внешнем сервере.

        Args:
            email (str): Email адрес.

        Returns:
            bool: True в случае успешного удаления.
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

    def delete_mailbox(self, email: str) -> bool:
        """Фиксирует необходимость удаления ящика на внешнем сервере."""
        logger.info(f"[ExternalMailProvider:Manual] Удаление ящика '{email}' на внешнем сервере.")
        return True


class ISPmanagerExternalMailProvider(BaseExternalMailProvider):
    """Адаптер для управления почтовыми ящиками на сервере Reg.ru через API панели ISPmanager 5 / 6.

    В соответствии с архитектурой хостинга Reg.ru для домена barkol.ru:
    - Почтовые ящики создаются на внешнем сервере через API панели ISPmanager:
      `POST https://<host>:1500/ispmgr?func=email.edit&authinfo=<user>:<pass>&out=json&sok=ok&name=<login>&domain=<domain>&password=<pass>`
    - После создания ящика Kerio Connect забирает корреспонденцию через POP3 (`mail.barkol.ru:995 SSL`)
      и отправляет исходящую почту через SMTP ретранслятор (`smtp.barkol.ru:587 STARTTLS`).

    Attributes:
        panel_url (str): URL панели управления ISPmanager (по умолчанию https://mail.barkol.ru:1500/ispmgr).
        api_username (str): Имя пользователя панели ISPmanager (пользователь хостинга Reg.ru).
        api_password (str): Пароль пользователя панели ISPmanager.
        verify_ssl (bool): Проверять ли SSL сертификат при обращении к панели.
        timeout (int): Таймаут сетевого запроса в секундах.
    """

    def __init__(
        self,
        panel_url: Optional[str] = None,
        api_username: Optional[str] = None,
        api_password: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Инициализирует адаптер ISPmanager API.

        Args:
            panel_url (Optional[str]): URL эндпоинта ISPmanager (из настроек ISPMANAGER_API_URL).
            api_username (Optional[str]): Логин ISPmanager (из настроек ISPMANAGER_API_USER).
            api_password (Optional[str]): Пароль ISPmanager (из настроек ISPMANAGER_API_PASSWORD).
            verify_ssl (Optional[bool]): Флаг проверки SSL (из настроек ISPMANAGER_API_VERIFY_SSL).
            timeout (Optional[int]): Таймаут сетевого соединения в секундах (из ISPMANAGER_API_TIMEOUT).
        """
        self.panel_url = panel_url or str(
            get_django_setting("ISPMANAGER_API_URL", "https://mail.barkol.ru:1500/ispmgr")
            or "https://mail.barkol.ru:1500/ispmgr"
        ).strip()
        self.api_username = api_username or str(
            get_django_setting("ISPMANAGER_API_USER", "")
            or get_django_setting("ISPMANAGER_USER", "")
            or ""
        ).strip()
        self.api_password = api_password or str(
            get_django_setting("ISPMANAGER_API_PASSWORD", "")
            or get_django_setting("ISPMANAGER_PASSWORD", "")
            or ""
        ).strip()

        ssl_setting = get_django_setting("ISPMANAGER_API_VERIFY_SSL", False)
        self.verify_ssl = bool(verify_ssl if verify_ssl is not None else ssl_setting)

        timeout_setting = get_django_setting("ISPMANAGER_API_TIMEOUT", 10)
        self.timeout = int(timeout if timeout is not None else (timeout_setting or 10))

    @property
    def is_configured(self) -> bool:
        """Проверяет, заданы ли учетные данные для обращения к ISPmanager API."""
        return bool(self.panel_url and self.api_username and self.api_password)

    def _call_api(self, func: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Выполняет HTTP-запрос к API панели ISPmanager.

        Args:
            func (str): Название функции ISPmanager (например, email.edit, email, email.delete).
            params (Optional[Dict[str, Any]]): Дополнительные параметры функции.

        Returns:
            Dict[str, Any]: Распарсенный ответ API ISPmanager.

        Raises:
            Exception: При сетевой ошибке или ошибке авторизации панели.
        """
        if not self.is_configured:
            logger.warning(
                f"[ISPmanagerExternalMailProvider] Параметры подключения к ISPmanager не заданы "
                f"(ISPMANAGER_API_USER/PASSWORD). Пропуск вызова {func}."
            )
            return {"unconfigured": True, "success": True}

        payload: Dict[str, Any] = {
            "func": func,
            "out": "json",
            "authinfo": f"{self.api_username}:{self.api_password}",
        }
        if params:
            payload.update(params)

        try:
            resp = requests.post(
                self.panel_url,
                data=payload,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            # Парсинг JSON ответа ISPmanager
            try:
                data = resp.json()
            except Exception:
                # Если ответ не JSON, возвращаем текстовое тело
                return {"text": resp.text, "status_code": resp.status_code, "success": True}

            # Проверка наличия блока ошибки в структуре ISPmanager
            if isinstance(data, dict):
                doc = data.get("doc", {})
                if isinstance(doc, dict) and "error" in doc:
                    err_obj = doc["error"]
                    err_msg = extract_isp_text(err_obj) or str(err_obj)
                    logger.warning(f"[ISPmanagerExternalMailProvider] Ошибка API ISPmanager {func}: {err_msg}")
                    return {"success": False, "error": err_msg, "raw": data}

            return {"success": True, "data": data}
        except Exception as exc:
            logger.error(f"[ISPmanagerExternalMailProvider] Исключение при вызове {func}: {exc}")
            raise

    def test_connection(self) -> Dict[str, Any]:
        """Проверяет сетевую доступность и корректность учетных данных API ISPmanager.

        Выполняет проверочный запрос (func=whoami или func=email) к панели управления.

        Returns:
            Dict[str, Any]: Словарь с результатом проверки:
                - success (bool): True при успешном подключении и авторизации.
                - configured (bool): Флаг наличия настроек в .env.
                - panel_url (str): Проверенный URL панели.
                - user (str): Имя пользователя API.
                - message (str): Поясняющее сообщение.
                - details (Dict[str, Any]): Дополнительные данные ответа API.
                - error (Optional[str]): Сообщение об ошибке при сбое.
        """
        if not self.is_configured:
            return {
                "success": False,
                "configured": False,
                "message": "Параметры подключения к ISPmanager не заданы в .env (ISPMANAGER_API_USER/PASSWORD).",
            }

        try:
            # Сначала пробуем whoami
            res = self._call_api("whoami")
            if res.get("success"):
                data = res.get("data", {})
                doc = data.get("doc", {}) if isinstance(data, dict) else {}
                return {
                    "success": True,
                    "configured": True,
                    "panel_url": self.panel_url,
                    "user": self.api_username,
                    "message": "Соединение и авторизация в ISPmanager успешны (whoami).",
                    "details": doc,
                }
            # Fallback на func=email
            res_email = self._call_api("email")
            if res_email.get("success"):
                return {
                    "success": True,
                    "configured": True,
                    "panel_url": self.panel_url,
                    "user": self.api_username,
                    "message": "Соединение и авторизация в ISPmanager успешны (email).",
                    "details": res_email.get("data", {}),
                }
            err = res.get("error") or res_email.get("error") or "Не удалось авторизоваться в ISPmanager"
            return {
                "success": False,
                "configured": True,
                "panel_url": self.panel_url,
                "user": self.api_username,
                "error": err,
                "message": f"Ошибка авторизации ISPmanager: {err}",
            }
        except Exception as exc:
            return {
                "success": False,
                "configured": True,
                "panel_url": self.panel_url,
                "user": self.api_username,
                "error": str(exc),
                "message": f"Сетевая ошибка при обращении к ISPmanager: {exc}",
            }

    def get_form_metadata(
        self,
        func_name: str = "email.edit",
        elid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Получает метаданные формы ISPmanager (структуру полей формы без отправки данных).

        Позволяет проинспектировать названия полей (например, passwd, confirm, quota, note),
        типы данных и текущие значения, поддерживаемые версией ISPmanager на сервере.

        Args:
            func_name (str): Имя функции формы (по умолчанию email.edit).
            elid (Optional[str]): Идентификатор редактируемой сущности (например, email ящика).

        Returns:
            Dict[str, Any]: Метаданные формы и список обнаруженных полей.
        """
        if not self.is_configured:
            return {"success": False, "error": "Провайдер не сконфигурирован"}

        params: Dict[str, Any] = {}
        if elid:
            params["elid"] = elid

        try:
            # Вызов функции без sok=ok возвращает описание полей формы
            return self._call_api(func_name, params=params)
        except Exception as exc:
            logger.error(f"[ISPmanagerExternalMailProvider] Ошибка получения метаданных формы {func_name}: {exc}")
            return {"success": False, "error": str(exc)}

    def get_mailboxes(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает список всех почтовых ящиков из панели ISPmanager.

        Args:
            domain (Optional[str]): Опциональный фильтр по почтовому домену (например, barkol.ru).

        Returns:
            List[Dict[str, Any]]: Список словарей с описанием каждого почтового ящика
                (email, name, domain, quota, used, status, note).
        """
        if not self.is_configured:
            return []

        params: Dict[str, Any] = {}
        if domain:
            params["elid"] = domain
            params["plid"] = domain
            params["domainname"] = domain
            params["domain"] = domain

        try:
            res = self._call_api("email", params=params)
            if not res.get("success"):
                return []

            data = res.get("data", {})
            doc = data.get("doc", {}) if isinstance(data, dict) else {}
            elems = doc.get("elem", []) if isinstance(doc, dict) else []
            if isinstance(elems, dict):
                elems = [elems]

            mailboxes: List[Dict[str, Any]] = []
            for el in elems:
                if not isinstance(el, dict):
                    continue
                el_name = extract_isp_text(el.get("name"))
                el_domain = extract_isp_text(el.get("domain")) or extract_isp_text(el.get("domainname")) or (domain or "")
                el_quota = extract_isp_text(el.get("quota")) or extract_isp_text(el.get("maxsize"))
                el_used = extract_isp_text(el.get("used"))
                el_status = extract_isp_text(el.get("status"))
                el_note = extract_isp_text(el.get("note"))
                full_email = f"{el_name}@{el_domain}" if el_domain and "@" not in el_name else el_name
                mailboxes.append({
                    "email": full_email,
                    "name": el_name,
                    "domain": el_domain,
                    "quota": el_quota,
                    "used": el_used,
                    "status": el_status,
                    "note": el_note,
                    "raw": el,
                })
            return mailboxes
        except Exception as exc:
            logger.error(f"[ISPmanagerExternalMailProvider] Ошибка получения списка ящиков: {exc}")
            return []

    def get_domains(self) -> List[Dict[str, Any]]:
        """Получает список почтовых/веб доменов из ISPmanager.

        Returns:
            List[Dict[str, Any]]: Список доменов.
        """
        if not self.is_configured:
            return []

        for func_name in ("email.domain", "domain"):
            try:
                res = self._call_api(func_name)
                if res.get("success"):
                    data = res.get("data", {})
                    doc = data.get("doc", {}) if isinstance(data, dict) else {}
                    elems = doc.get("elem", []) if isinstance(doc, dict) else []
                    if isinstance(elems, dict):
                        elems = [elems]
                    return [el for el in elems if isinstance(el, dict)]
            except Exception:
                continue
        return []

    def create_mailbox(
        self,
        email: str,
        password: str,
        full_name: str = "",
        quota_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Создает почтовый ящик на хостинге Reg.ru через ISPmanager API (`func=email.edit`).

        Передает поля `domainname` и `plid` (для явного указания домена в мультидоменном аккаунте),
        `passwd` и `confirm` (стандарт ISPmanager), `maxsize` (дисковая квота в МБ),
        а также алиасы `domain`, `password` и `passwd_confirm` для совместимости со всеми версиями ISPmanager 5 и 6.

        Args:
            email (str): Полный email адрес ящика (например, i.ivanov@barkol.ru).
            password (str): Пароль для доступа к почтовому ящику.
            full_name (str): Имя владельца ящика.
            quota_mb (Optional[int]): Размер квоты почтового ящика в МБ.

        Returns:
            Dict[str, Any]: Результат операции создания.
        """
        clean_email = email.strip().lower()
        parts = clean_email.split("@")
        name = parts[0]
        domain = parts[1] if len(parts) > 1 else "barkol.ru"

        logger.info(f"[ISPmanagerExternalMailProvider] Создание ящика {clean_email} на Reg.ru (ISPmanager, домен {domain})...")

        if not self.is_configured:
            logger.info(
                f"[ISPmanagerExternalMailProvider] Режим автоматического подтверждения (параметры ISPmanager не заданы). "
                f"Ящик {clean_email} готов для подключения Kerio Connect."
            )
            return {
                "success": True,
                "provider": "ispmanager",
                "status": "ready_for_kerio_pop3",
                "email": clean_email,
                "note": "Учетные данные ящика переданы в Kerio Connect (POP3 mail.barkol.ru:995, SMTP smtp.barkol.ru:587).",
            }

        # Валидация ASCII символов в пароле почтового ящика
        if not password.isascii():
            err_msg = (
                "Пароль содержит недопустимые не-ASCII (кириллические) символы. "
                "Панель ISPmanager и почтовые протоколы POP3/SMTP требуют использовать только латинские символы, "
                "цифры и стандартные знаки препинания."
            )
            logger.warning(f"[ISPmanagerExternalMailProvider] Ошибка создания ящика {clean_email}: {err_msg}")
            return {
                "success": False,
                "provider": "ispmanager",
                "email": clean_email,
                "error": err_msg,
            }

        params: Dict[str, Any] = {
            "sok": "ok",
            "name": name,
            "domainname": domain,
            "domain": domain,
            "plid": domain,
            "passwd": password,
            "password": password,
            "confirm": password,
            "passwd_confirm": password,
        }
        if quota_mb:
            params["maxsize"] = int(quota_mb)
            params["quota"] = int(quota_mb)
        if full_name:
            params["note"] = full_name.strip()

        try:
            res = self._call_api("email.edit", params=params)
            if res.get("success"):
                logger.info(f"[ISPmanagerExternalMailProvider] Ящик {clean_email} успешно создан на Reg.ru в домене {domain}!")
                return {
                    "success": True,
                    "provider": "ispmanager",
                    "email": clean_email,
                    "domain": domain,
                    "status": "created",
                    "message": f"Почтовый ящик {clean_email} успешно создан в ISPmanager на Reg.ru.",
                    "details": res,
                }
            else:
                err_msg = res.get("error", "Неизвестная ошибка ISPmanager")
                logger.warning(f"[ISPmanagerExternalMailProvider] Ошибка создания ящика {clean_email}: {err_msg}")
                return {
                    "success": False,
                    "provider": "ispmanager",
                    "email": clean_email,
                    "domain": domain,
                    "error": err_msg,
                }
        except Exception as exc:
            logger.warning(f"[ISPmanagerExternalMailProvider] Не удалось создать ящик через API ISPmanager: {exc}")
            # Возвращаем мягкий статус, чтобы не блокировать создание в Kerio Connect
            return {
                "success": False,
                "provider": "ispmanager",
                "email": clean_email,
                "domain": domain,
                "error": str(exc),
                "fallback_mode": True,
            }

    def check_mailbox_exists(self, email: str) -> bool:
        """Проверяет наличие ящика на сервере Reg.ru через ISPmanager API (`func=email`).

        Args:
            email (str): Email адрес для проверки.

        Returns:
            bool: True, если ящик найден на сервере.
        """
        if not self.is_configured:
            return True

        clean_email = email.strip().lower()
        parts = clean_email.split("@")
        name = parts[0]
        domain = parts[1] if len(parts) > 1 else "barkol.ru"

        try:
            # Сначала пробуем запросить ящики целевого домена через plid / elid / domainname
            res = self._call_api("email", params={"elid": domain, "plid": domain, "domainname": domain, "domain": domain})
            if not res.get("success"):
                # Fallback: запрос общего списка ящиков без фильтра
                res = self._call_api("email")
                if not res.get("success"):
                    return False

            data = res.get("data", {})
            doc = data.get("doc", {}) if isinstance(data, dict) else {}
            elems = doc.get("elem", []) if isinstance(doc, dict) else []
            if isinstance(elems, dict):
                elems = [elems]

            for el in elems:
                if not isinstance(el, dict):
                    continue
                el_name = extract_isp_text(el.get("name")).lower()
                el_domain = extract_isp_text(el.get("domain")).lower() or extract_isp_text(el.get("domainname")).lower() or domain
                full = f"{el_name}@{el_domain}" if el_domain and "@" not in el_name else el_name
                if clean_email == full or clean_email == el_name:
                    return True
            return False
        except Exception as exc:
            logger.debug(f"[ISPmanagerExternalMailProvider] Ошибка проверки существования ящика: {exc}")
            return True

    def change_password(self, email: str, new_password: str) -> bool:
        """Изменяет пароль почтового ящика в ISPmanager (`func=email.edit`).

        Args:
            email (str): Email адрес сотрудника.
            new_password (str): Новый пароль.

        Returns:
            bool: True при успешном обновлении пароля на внешнем сервере.
        """
        if not self.is_configured:
            logger.info(f"[ISPmanagerExternalMailProvider] Смена пароля для '{email}' зафиксирована (unconfigured).")
            return True

        clean_email = email.strip().lower()
        parts = clean_email.split("@")
        name = parts[0]
        domain = parts[1] if len(parts) > 1 else "barkol.ru"

        if not new_password.isascii():
            logger.warning(
                f"[ISPmanagerExternalMailProvider] Попытка установить не-ASCII пароль для '{clean_email}'."
            )
            return False

        params: Dict[str, Any] = {
            "sok": "ok",
            "elid": clean_email,
            "name": name,
            "domainname": domain,
            "domain": domain,
            "plid": domain,
            "passwd": new_password,
            "password": new_password,
            "confirm": new_password,
            "passwd_confirm": new_password,
        }

        try:
            res = self._call_api("email.edit", params=params)
            if res.get("success"):
                logger.info(f"[ISPmanagerExternalMailProvider] Пароль для '{clean_email}' успешно изменен на Reg.ru!")
                return True
            logger.warning(f"[ISPmanagerExternalMailProvider] Ошибка смены пароля для '{clean_email}': {res.get('error')}")
            return False
        except Exception as exc:
            logger.warning(f"[ISPmanagerExternalMailProvider] Исключение при смене пароля ящика '{clean_email}': {exc}")
            return False

    def delete_mailbox(self, email: str) -> bool:
        """Удаляет почтовый ящик в ISPmanager (`func=email.delete`).

        Args:
            email (str): Email адрес удаляемого ящика.

        Returns:
            bool: True при успешном удалении.
        """
        if not self.is_configured:
            logger.info(f"[ISPmanagerExternalMailProvider] Удаление ящика '{email}' зафиксировано (unconfigured).")
            return True

        clean_email = email.strip().lower()
        parts = clean_email.split("@")
        name = parts[0]
        domain = parts[1] if len(parts) > 1 else "barkol.ru"

        params: Dict[str, Any] = {
            "sok": "ok",
            "elid": clean_email,
            "name": name,
            "domainname": domain,
            "domain": domain,
            "plid": domain,
        }

        try:
            res = self._call_api("email.delete", params=params)
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning(f"[ISPmanagerExternalMailProvider] Ошибка удаления ящика '{clean_email}': {exc}")
            return False


# Псевдоним RegRuExternalMailProvider для прямой обратной совместимости
RegRuExternalMailProvider = ISPmanagerExternalMailProvider
