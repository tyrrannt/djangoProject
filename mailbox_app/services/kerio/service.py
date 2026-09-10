"""Высокоуровневый сервис бизнес-логики администрирования Kerio Connect и интеграции с порталом BARKOL."""

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from mailbox_app.models import MailAccount, Mailbox
    from mailbox_app.services.crypto_service import encrypt_password
    User = get_user_model()
except ImportError:
    User = None
    MailAccount = None
    Mailbox = None
    encrypt_password = None
from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.domains import DomainManager
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioAuthenticationError,
    KerioConnectionError,
    KerioObjectNotFoundError,
    KerioValidationError,
)
from mailbox_app.services.kerio.external_provider import (
    BaseExternalMailProvider,
    ManualExternalMailProvider,
    RegRuExternalMailProvider,
)
from mailbox_app.services.kerio.pop3_download import Pop3DownloadManager
from mailbox_app.services.kerio.smtp_delivery import SmtpDeliveryManager
from mailbox_app.services.kerio.users import UserManager

logger = logging.getLogger(__name__)


class KerioAdminService:
    """Сервис бизнес-логики управления почтовой инфраструктурой Kerio Connect 9.4.1.

    Координирует работу с доменами, пользователями, правилами сбора почты POP3 Download,
    правилами исходящей ретрансляции Доставка SMTP, внешними провайдерами и синхронизацией
    с кадровыми профилями корпоративного портала.

    Attributes:
        client (KerioConnectAdminClient): Низкоуровневый клиент JSON-RPC.
        domains (DomainManager): Менеджер почтовых доменов.
        users (UserManager): Менеджер пользователей Kerio.
        pop3 (Pop3DownloadManager): Менеджер правил «Загрузка POP3» (сборщик почты).
        smtp_delivery (SmtpDeliveryManager): Менеджер правил исходящей ретрансляции «Доставка SMTP».
        external_provider (BaseExternalMailProvider): Адаптер внешнего почтового сервера.
    """

    def __init__(
        self,
        client: Optional[KerioConnectAdminClient] = None,
        external_provider: Optional[BaseExternalMailProvider] = None,
    ) -> None:
        """Инициализирует высокоуровневый сервис администрирования.

        Args:
            client (Optional[KerioConnectAdminClient]): Клиент API. Если None, создается экземпляр по умолчанию.
            external_provider (Optional[BaseExternalMailProvider]): Провайдер внешнего сервера (по умолчанию RegRu/Manual).
        """
        self.client = client or KerioConnectAdminClient()
        self.domains = DomainManager(self.client)
        self.users = UserManager(self.client)
        self.pop3 = Pop3DownloadManager(self.client)
        self.smtp_delivery = SmtpDeliveryManager(self.client)
        self.external_provider = external_provider or RegRuExternalMailProvider()

    def test_admin_connection(self) -> Dict[str, Any]:
        """Проверяет доступность и корректность авторизации в Kerio Connect Administration API.

        Returns:
            Dict[str, Any]: Структурированный отчет о проверке подключения (success, domains_count, message).
        """
        try:
            with self.client:
                domains = self.domains.get_domains()
                return {
                    "success": True,
                    "status": "online",
                    "api_url": self.client.api_url,
                    "username": self.client.username,
                    "domains": [d.get("name") for d in domains],
                    "domains_count": len(domains),
                    "message": f"Успешное подключение к Kerio Connect API. Доступно доменов: {len(domains)}.",
                }
        except KerioAuthenticationError as err:
            logger.error(f"[KerioAdminService] Ошибка аутентификации администратора: {err}")
            return {
                "success": False,
                "status": "auth_error",
                "error": str(err),
                "message": "Ошибка аутентификации: неверный логин или пароль администратора Kerio Connect.",
            }
        except KerioConnectionError as err:
            logger.error(f"[KerioAdminService] Ошибка сетевого подключения к Kerio API: {err}")
            return {
                "success": False,
                "status": "connection_error",
                "error": str(err),
                "message": f"Не удалось подключиться к серверу Kerio Connect ({self.client.api_url}): {err}",
            }
        except Exception as err:
            logger.error(f"[KerioAdminService] Непредвиденная ошибка при проверке API: {err}", exc_info=True)
            return {
                "success": False,
                "status": "error",
                "error": str(err),
                "message": f"Ошибка при обращении к Kerio Connect API: {err}",
            }

    def get_domains_list(self) -> List[Dict[str, Any]]:
        """Возвращает список зарегистрированных доменов Kerio Connect.

        Returns:
            List[Dict[str, Any]]: Список словарей с данными доменов.
        """
        with self.client:
            return self.domains.get_domains()

    def get_users_list(
        self,
        domain_name: Optional[str] = None,
        search_query: Optional[str] = None,
        start: int = 0,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Возвращает постраничный список пользователей Kerio Connect с обогащением информацией о POP3 сборщике.

        Args:
            domain_name (Optional[str]): Имя домена (например, 'barkol.ru').
            search_query (Optional[str]): Строка поиска.
            start (int): Смещение для пагинации.
            limit (int): Количество на страницу (по умолчанию 1000).

        Returns:
            Dict[str, Any]: Словарь со списком обогащенных пользователей и общим количеством.
        """
        with self.client:
            domain_id = None
            if domain_name and domain_name != "all":
                try:
                    domain_id = self.domains.get_domain_id(domain_name)
                except KerioObjectNotFoundError:
                    domain_id = None

            raw_users = self.users.get_users(
                domain_id=domain_id,
                query_string=search_query,
                start=start,
                limit=limit,
            )

            # Получаем все правила POP3 для быстрой состыковки
            try:
                pop3_accounts = self.pop3.get_accounts()
                pop3_map = {}
                for p in pop3_accounts:
                    tgt = str(p.get("targetUser", "")).strip().lower()
                    deliv = str(p.get("deliveryAddress", "")).strip().lower()
                    uname = str(p.get("userName", "")).strip().lower()
                    for k in (tgt, deliv, uname):
                        if k:
                            pop3_map[k] = p
                            if "@" in k:
                                pop3_map[k.split("@")[0]] = p
            except Exception as err:
                logger.warning(f"[KerioAdminService] Не удалось загрузить правила POP3 при получении пользователей: {err}")
                pop3_map = {}

            # Получаем все правила «Доставка SMTP» для быстрой состыковки
            try:
                smtp_routes = self.smtp_delivery.get_routes()
                smtp_map = {}
                for r in smtp_routes:
                    patt = str(r.get("matchPattern", "")).strip().lower()
                    snd = str(r.get("sender", "")).strip().lower()
                    un = str(r.get("userName", "")).strip().lower()
                    for k in (patt, snd, un):
                        if k:
                            smtp_map[k] = r
                            if "@" in k:
                                smtp_map[k.split("@")[0]] = r
            except Exception as err:
                logger.warning(f"[KerioAdminService] Не удалось загрузить правила SMTP доставки при получении пользователей: {err}")
                smtp_map = {}

            users_list = []
            for u in raw_users.get("list", []):
                login = u.get("loginName", "")
                email = f"{login}@{domain_name or 'barkol.ru'}" if "@" not in login else login
                clean_login = login.lower()
                clean_email = email.lower()
                pop3_rule = pop3_map.get(clean_login) or pop3_map.get(clean_email) or pop3_map.get(clean_login.split("@")[0])
                smtp_rule = smtp_map.get(clean_email) or smtp_map.get(clean_login) or smtp_map.get(clean_login.split("@")[0])

                u_enriched = dict(u)
                u_enriched["email"] = email
                u_enriched["has_pop3_download"] = bool(pop3_rule)
                u_enriched["pop3_details"] = pop3_rule
                u_enriched["has_smtp_delivery"] = bool(smtp_rule)
                u_enriched["smtp_delivery_details"] = smtp_rule
                users_list.append(u_enriched)

            return {
                "list": users_list,
                "totalItems": raw_users.get("totalItems", len(users_list)),
            }

    def provision_full_mailbox(
        self,
        login_name: str,
        password: str,
        domain_name: str = "barkol.ru",
        full_name: str = "",
        description: str = "",
        django_user_id: Optional[int] = None,
        quota_mb: Optional[int] = None,
        external_pop3_host: str = "mail.barkol.ru",
        external_pop3_port: int = 995,
        external_pop3_ssl: bool = True,
        external_leave_messages: bool = False,
        create_django_account: bool = True,
    ) -> Dict[str, Any]:
        """Выполняет полный цикл создания пользователя и настройки почтового ящика компании.

        Последовательность операций:
        1. Создание учетной записи на внешнем почтовом шлюзе (Reg.ru / внешний сервер);
        2. Создание почтового аккаунта в локальном Kerio Connect 9.4.1 (Users.create);
        3. Создание правила сбора почты «Доставка -> Загрузка POP3» (Pop3Download.create)
           с параметрами mail.barkol.ru:995 SSL, удаление сообщений с внешнего сервера;
        4. Создание / связывание MailAccount в базе Django с шифрованием пароля Fernet AES.

        Args:
            login_name (str): Логин пользователя (например, 'i.ivanov').
            password (str): Пароль учетной записи (единый для внешнего сервера, Kerio и портала).
            domain_name (str): Домен почты (по умолчанию 'barkol.ru').
            full_name (str): Полное имя сотрудника (ФИО).
            description (str): Должность / подразделение / примечание.
            django_user_id (Optional[int]): ID пользователя портала DataBaseUser (если есть).
            quota_mb (Optional[int]): Лимит квоты в МБ (None — без лимита).
            external_pop3_host (str): Хост внешнего POP3 (по умолчанию 'mail.barkol.ru').
            external_pop3_port (int): Порт внешнего POP3 (по умолчанию 995).
            external_pop3_ssl (bool): Использовать SSL для внешнего POP3 (по умолчанию True).
            external_leave_messages (bool): Оставлять ли письма на внешнем сервере (False — удалять).
            create_django_account (bool): Создавать ли модель MailAccount в Django.

        Returns:
            Dict[str, Any]: Полный отчет о созданных компонентах почтового ящика.

        Raises:
            KerioValidationError: При неполных входных данных.
            KerioAPIError: При ошибке создания в Kerio Connect.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name.strip().lower()}"

        if not clean_login or not password:
            raise KerioValidationError("Логин и пароль обязательны для создания почтового ящика.")

        report: Dict[str, Any] = {
            "email": full_email,
            "login": clean_login,
            "domain": domain_name,
            "steps": {},
            "success": False,
        }

        # Шаг 1. Внешний почтовый сервер
        try:
            ext_res = self.external_provider.create_mailbox(
                email=full_email,
                password=password,
                full_name=full_name,
                quota_mb=quota_mb,
            )
            report["steps"]["external_server"] = {"status": "ok", "details": ext_res}
        except Exception as exc:
            logger.warning(f"[KerioAdminService] Внешний провайдер вернул предупреждение: {exc}")
            report["steps"]["external_server"] = {"status": "warning", "error": str(exc)}

        # Шаг 2 и 3. Работа с Kerio Connect API
        with self.client:
            domain_id = self.domains.get_domain_id(domain_name)

            # Создаем пользователя Kerio Connect
            user_create_res = self.users.create_user(
                domain_id=domain_id,
                login_name=clean_login,
                password=password,
                full_name=full_name,
                description=description,
                is_enabled=True,
                quota_mb=quota_mb,
            )
            report["steps"]["kerio_user"] = {"status": "ok", "details": user_create_res}

            # Создаем правило Загрузка POP3
            try:
                pop3_res = self.pop3.create_pop3_account(
                    target_user=clean_login,
                    password=password,
                    server=external_pop3_host,
                    port=external_pop3_port,
                    username=full_email,
                    use_ssl=external_pop3_ssl,
                    leave_messages_on_server=external_leave_messages,
                    interval_minutes=1,
                    is_enabled=True,
                )
                report["steps"]["kerio_pop3_download"] = {"status": "ok", "details": pop3_res}
            except Exception as pop_exc:
                logger.error(f"[KerioAdminService] Ошибка создания POP3 правила в Kerio: {pop_exc}")
                report["steps"]["kerio_pop3_download"] = {"status": "error", "error": str(pop_exc)}

            # Создаем правило «Доставка SMTP» (ретрансляция через smtp.barkol.ru:587 с SMTP AUTH)
            try:
                smtp_relay_host = getattr(settings, "KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") if settings else "smtp.barkol.ru"
                smtp_relay_port = getattr(settings, "KERIO_DEFAULT_SMTP_RELAY_PORT", 587) if settings else 587
                smtp_route_res = self.smtp_delivery.create_delivery_route(
                    sender_email=full_email,
                    password=password,
                    relay_host=smtp_relay_host,
                    relay_port=smtp_relay_port,
                    auth_username=full_email,
                    is_enabled=True,
                )
                report["steps"]["kerio_smtp_delivery"] = {"status": "ok", "details": smtp_route_res}
            except Exception as smtp_exc:
                logger.warning(f"[KerioAdminService] Ошибка создания правила «Доставка SMTP» в Kerio: {smtp_exc}")
                report["steps"]["kerio_smtp_delivery"] = {"status": "warning", "error": str(smtp_exc)}

        # Шаг 4. Связывание в Django (MailAccount)
        if create_django_account and django_user_id:
            try:
                portal_user = User.objects.get(pk=django_user_id)
                with transaction.atomic():
                    mail_account, created = MailAccount.objects.get_or_create(
                        user=portal_user,
                        defaults={
                            "email": full_email,
                            "display_name": full_name or portal_user.get_full_name(),
                            "imap_host": "imap.barkol.ru",
                            "imap_port": 993,
                            "imap_use_ssl": True,
                            "smtp_host": "sm.barkol.ru",
                            "smtp_port": 465,
                            "smtp_use_ssl": True,
                            "is_active": True,
                        },
                    )
                    mail_account.set_password(password)
                    mail_account.email = full_email
                    if full_name:
                        mail_account.display_name = full_name
                    mail_account.save()

                    report["steps"]["django_account"] = {
                        "status": "ok",
                        "mail_account_id": mail_account.pk,
                        "created": created,
                    }
            except Exception as dj_exc:
                logger.error(f"[KerioAdminService] Ошибка сохранения MailAccount в Django: {dj_exc}")
                report["steps"]["django_account"] = {"status": "error", "error": str(dj_exc)}

        report["success"] = True
        logger.info(f"[KerioAdminService] Почтовый ящик '{full_email}' успешно подготовлен и сконфигурирован.")
        return report

    def ensure_user_smtp_delivery_route(
        self,
        login_name: str,
        password: Optional[str] = None,
        domain_name: str = "barkol.ru",
        relay_host: Optional[str] = None,
        relay_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Проверяет наличие и при необходимости создает/актуализирует правило «Доставка SMTP» для пользователя.

        Если пароль не указан явно, пытается извлечь его из связанного профиля MailAccount базы данных Django.

        Args:
            login_name (str): Логин или email пользователя.
            password (Optional[str]): Пароль ящика (если None, ищется в Django MailAccount).
            domain_name (str): Почтовый домен (barkol.ru).
            relay_host (Optional[str]): Сервер ретрансляции (по умолчанию 'smtp.barkol.ru').
            relay_port (Optional[int]): Порт сервера ретрансляции (по умолчанию 587).

        Returns:
            Dict[str, Any]: Отчет о проверке и создании правила Доставки SMTP.

        Raises:
            KerioValidationError: Если пароль не найден и не передан.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        target_password = password
        if not target_password and MailAccount:
            acc = MailAccount.objects.filter(email__iexact=full_email).first()
            if acc:
                target_password = acc.get_password()

        if not target_password:
            raise KerioValidationError(
                f"Не удалось определить пароль для '{full_email}'. Укажите пароль вручную."
            )

        with self.client:
            existing_route = self.smtp_delivery.get_route_for_sender(full_email)
            if existing_route and existing_route.get("id"):
                # Обновляем пароль в существующем правиле
                res = self.smtp_delivery.update_delivery_route(
                    route_id=existing_route["id"],
                    password=target_password,
                    relay_host=relay_host,
                    relay_port=relay_port,
                    is_enabled=True,
                )
                return {
                    "success": True,
                    "action": "updated",
                    "route_id": existing_route["id"],
                    "email": full_email,
                    "details": res,
                }
            else:
                # Создаем новое правило
                res = self.smtp_delivery.create_delivery_route(
                    sender_email=full_email,
                    password=target_password,
                    relay_host=relay_host,
                    relay_port=relay_port,
                    auth_username=full_email,
                    is_enabled=True,
                )
                return {
                    "success": True,
                    "action": "created",
                    "email": full_email,
                    "details": res,
                }

    def update_user_password(
        self,
        login_name: str,
        new_password: str,
        domain_name: str = "barkol.ru",
        update_django: bool = True,
    ) -> Dict[str, Any]:
        """Синхронно обновляет пароль в Kerio Connect, правиле POP3, правиле Доставка SMTP и MailAccount портала.

        Args:
            login_name (str): Логин пользователя.
            new_password (str): Новый пароль в открытом виде.
            domain_name (str): Имя домена.
            update_django (bool): Обновить ли пароль в MailAccount.

        Returns:
            Dict[str, Any]: Отчет об обновлении пароля по всем контурам.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        report: Dict[str, Any] = {"login": clean_login, "success": False, "steps": {}}

        # 1. Внешний провайдер
        try:
            self.external_provider.change_password(full_email, new_password)
            report["steps"]["external_server"] = "ok"
        except Exception as err:
            report["steps"]["external_server"] = f"warning: {err}"

        # 2. Kerio Connect
        with self.client:
            domain_id = self.domains.get_domain_id(domain_name)
            k_user = self.users.get_user_by_login(clean_login, domain_id=domain_id)
            if not k_user:
                raise KerioObjectNotFoundError(f"Пользователь '{clean_login}' не найден в Kerio Connect.")

            user_id = k_user.get("id")
            self.users.set_password(user_id, new_password)
            report["steps"]["kerio_user"] = "ok"

            # 3. POP3 Download правило
            pop3_rule = self.pop3.get_account_for_user(clean_login)
            if pop3_rule and "id" in pop3_rule:
                self.pop3.update_pop3_account(pop3_rule["id"], password=new_password)
                report["steps"]["kerio_pop3_download"] = "ok"

            # 4. Доставка SMTP правило (SMTP AUTH)
            try:
                self.smtp_delivery.set_route_password_for_sender(full_email, new_password)
                report["steps"]["kerio_smtp_delivery"] = "ok"
            except Exception as smtp_exc:
                logger.warning(f"[KerioAdminService] Ошибка обновления пароля в правиле Доставка SMTP: {smtp_exc}")
                report["steps"]["kerio_smtp_delivery"] = f"warning: {smtp_exc}"

        # 5. Django MailAccount
        if update_django:
            accounts = MailAccount.objects.filter(email__iexact=full_email)
            for acc in accounts:
                acc.set_password(new_password)
                acc.save(update_fields=["encrypted_password", "updated_at"])
            report["steps"]["django_account"] = f"updated {accounts.count()} accounts"

        report["success"] = True
        return report

    def toggle_user_active(
        self,
        login_name: str,
        is_enabled: bool,
        domain_name: str = "barkol.ru",
    ) -> Dict[str, Any]:
        """Блокирует или разблокирует пользователя в Kerio Connect, POP3 правиле, правиле Доставка SMTP и MailAccount.

        Args:
            login_name (str): Логин пользователя.
            is_enabled (bool): Флаг активности.
            domain_name (str): Домен.

        Returns:
            Dict[str, Any]: Отчет о блокировке.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        with self.client:
            domain_id = self.domains.get_domain_id(domain_name)
            k_user = self.users.get_user_by_login(clean_login, domain_id=domain_id)
            if not k_user:
                raise KerioObjectNotFoundError(f"Пользователь '{clean_login}' не найден в Kerio Connect.")

            self.users.set_enabled(k_user["id"], is_enabled=is_enabled)

            # POP3 правило
            pop3_rule = self.pop3.get_account_for_user(clean_login)
            if pop3_rule and "id" in pop3_rule:
                self.pop3.update_pop3_account(pop3_rule["id"], is_enabled=is_enabled)

            # Доставка SMTP правило
            try:
                self.smtp_delivery.toggle_route_for_sender(full_email, is_enabled=is_enabled)
            except Exception as smtp_exc:
                logger.warning(f"[KerioAdminService] Ошибка переключения активности правила Доставка SMTP: {smtp_exc}")

        # Django MailAccount
        MailAccount.objects.filter(email__iexact=full_email).update(is_active=is_enabled)

        return {"login": clean_login, "is_enabled": is_enabled, "success": True}

    def delete_user(
        self,
        login_name: str,
        domain_name: str = "barkol.ru",
    ) -> Dict[str, Any]:
        """Удаляет пользователя, его правило загрузки POP3 и правило Доставки SMTP из Kerio Connect.

        Args:
            login_name (str): Логин пользователя.
            domain_name (str): Домен.

        Returns:
            Dict[str, Any]: Отчет об удалении.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        with self.client:
            domain_id = self.domains.get_domain_id(domain_name)
            k_user = self.users.get_user_by_login(clean_login, domain_id=domain_id)
            if not k_user:
                raise KerioObjectNotFoundError(f"Пользователь '{clean_login}' не найден в Kerio Connect.")

            # Удаляем POP3 правило
            pop3_rule = self.pop3.get_account_for_user(clean_login)
            if pop3_rule and "id" in pop3_rule:
                self.pop3.remove_pop3_account(pop3_rule["id"])

            # Удаляем Доставка SMTP правило
            try:
                self.smtp_delivery.remove_route_for_sender(full_email)
            except Exception as smtp_exc:
                logger.warning(f"[KerioAdminService] Ошибка удаления правила Доставка SMTP: {smtp_exc}")

            # Удаляем пользователя
            self.users.remove_user(k_user["id"])

        return {"login": clean_login, "deleted": True, "success": True}
