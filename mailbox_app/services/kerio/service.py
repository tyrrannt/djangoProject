"""Высокоуровневый сервис бизнес-логики администрирования Kerio Connect и интеграции с порталом BARKOL."""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from django.contrib.auth import get_user_model
    from django.db import models, transaction
    from mailbox_app.models import MailAccount, Mailbox
    from mailbox_app.services.crypto_service import encrypt_password
    User = get_user_model()
except Exception:
    models = None
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
from mailbox_app.services.kerio.utils import get_django_setting

logger = logging.getLogger(__name__)


def _sync_user_work_profile_password(portal_user: Any, password: str) -> None:
    """Синхронизирует пароль от корпоративной почты в рабочем профиле сотрудника DataBaseUserWorkProfile.

    Записывает пароль в поле work_email_password рабочего профиля пользователя портала,
    а при отсутствии профиля — автоматически создает его.

    Args:
        portal_user (Any): Экземпляр пользователя Django (DataBaseUser / User).
        password (str): Пароль от почты в открытом виде.
    """
    if not portal_user or not password:
        return
    try:
        if hasattr(portal_user, "user_work_profile") and portal_user.user_work_profile:
            portal_user.user_work_profile.work_email_password = password
            portal_user.user_work_profile.save(update_fields=["work_email_password"])
            logger.info(
                f"[KerioAdminService] Пароль корпоративной почты записан в рабочий профиль сотрудника {portal_user.username}."
            )
        else:
            try:
                from customers_app.models import DataBaseUserWorkProfile
                work_profile = DataBaseUserWorkProfile.objects.create(work_email_password=password)
                portal_user.user_work_profile = work_profile
                portal_user.save(update_fields=["user_work_profile"])
                logger.info(
                    f"[KerioAdminService] Создан рабочий профиль DataBaseUserWorkProfile и сохранен пароль почты для {portal_user.username}."
                )
            except Exception as e_prof:
                logger.debug(
                    f"[KerioAdminService] Не удалось создать DataBaseUserWorkProfile для {portal_user}: {e_prof}"
                )
    except Exception as exc:
        logger.warning(
            f"[KerioAdminService] Ошибка сохранения work_email_password для {portal_user}: {exc}"
        )


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
            domains = self.domains.get_domains()
            client_api_url = getattr(self.client, "api_url", str(get_django_setting("KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/") or "https://192.168.10.242:4040/admin/api/jsonrpc/"))
            client_username = getattr(self.client, "username", str(get_django_setting("KERIO_API_USER", "admin") or "admin"))
            return {
                "success": True,
                "status": "online",
                "api_url": client_api_url,
                "username": client_username,
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
            client_api_url = getattr(self.client, "api_url", str(get_django_setting("KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/") or "https://192.168.10.242:4040/admin/api/jsonrpc/"))
            logger.error(f"[KerioAdminService] Ошибка сетевого подключения к Kerio API: {err}")
            return {
                "success": False,
                "status": "connection_error",
                "error": str(err),
                "message": f"Не удалось подключиться к серверу Kerio Connect ({client_api_url}): {err}",
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

            # 1. Поиск индивидуального правила для сотрудника в таблице Доставка SMTP
            indiv_smtp_rule = (
                smtp_map.get(clean_email)
                or smtp_map.get(clean_login)
                or smtp_map.get(clean_login.split("@")[0])
            )

            if indiv_smtp_rule and not indiv_smtp_rule.get("isGlobal"):
                smtp_rule = indiv_smtp_rule
                is_individual = True
            else:
                # 2. Поиск общего серверного правила ретрансляции
                server_smtp_rule = (
                    smtp_map.get("*@barkol.ru")
                    or smtp_map.get(f"*@{domain_name or 'barkol.ru'}")
                    or smtp_map.get("*")
                    or next((r for r in smtp_routes if r.get("isGlobal")), None)
                )
                smtp_rule = server_smtp_rule
                is_individual = False

            u_enriched = dict(u)
            u_enriched["email"] = email
            u_enriched["has_pop3_download"] = bool(pop3_rule)
            u_enriched["pop3_details"] = pop3_rule
            u_enriched["has_smtp_delivery"] = bool(smtp_rule)
            u_enriched["is_individual_smtp_delivery"] = is_individual
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
        configure_smtp_delivery: bool = True,
        external_smtp_host: str = "smtp.barkol.ru",
        external_smtp_port: int = 587,
        save_email_to_user: bool = True,
        sync_1c: bool = True,
    ) -> Dict[str, Any]:
        """Комплексный конвейер подготовки и полного развертывания почтового ящика.

        Выполняет 6 взаимосвязанных этапов развертывания:
        1. Создание ящика на внешнем почтовом сервере ISPmanager / Reg.ru (ISPmanagerExternalMailProvider);
        2. Создание учетной записи пользователя в Kerio Connect (Users.create);
        3. Создание правила внешнего сборщика «Загрузка POP3» (Pop3Download.create);
        4. Создание правила исходящей ретрансляции «Доставка SMTP» (SmtpDelivery.create);
        5. Создание / связывание MailAccount в базе Django с шифрованием пароля Fernet AES;
        6. Запись email и пароля в профиль сотрудника DataBaseUser и синхронизация с 1С (ЗУП) через OData.

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
            configure_smtp_delivery (bool): Настраивать ли правило исходящей ретрансляции Доставка SMTP.
            external_smtp_host (str): Хост SMTP relay (по умолчанию 'smtp.barkol.ru').
            external_smtp_port (int): Порт SMTP relay (по умолчанию 587).
            save_email_to_user (bool): Записывать ли созданный email адрес в модель DataBaseUser (по умолчанию True).
            sync_1c (bool): Вызывать ли функцию синхронизации email в 1С (ЗУП) через OData (по умолчанию True).

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
            smtp_relay_host = str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") or "smtp.barkol.ru")
            smtp_relay_port = int(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_PORT", 587) or 587)
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

        # Шаг 4. Связывание в Django (MailAccount и DataBaseUserWorkProfile)
        portal_user = None
        if django_user_id and User:
            try:
                portal_user = User.objects.filter(pk=django_user_id).select_related("user_work_profile").first()
            except Exception:
                pass

        if not portal_user and User and models:
            # Автоматический поиск пользователя по email или логину
            portal_user = User.objects.filter(
                models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
            ).select_related("user_work_profile").first()

        if portal_user:
            # 4.1 Записываем пароль корпоративной почты в рабочий профиль сотрудника на сайте
            _sync_user_work_profile_password(portal_user, password)

            # 4.2 Записываем созданный email в модель DataBaseUser
            if save_email_to_user:
                try:
                    portal_user.email = full_email
                    portal_user.save(update_fields=["email"])
                    report["steps"]["user_email_saved"] = {
                        "status": "ok",
                        "email": full_email,
                        "user_id": portal_user.pk,
                    }
                    logger.info(
                        f"[KerioAdminService] Адрес '{full_email}' успешно записан в модель DataBaseUser сотрудника {portal_user.username}."
                    )
                except Exception as u_exc:
                    logger.error(
                        f"[KerioAdminService] Ошибка записи email в профиль пользователя {portal_user.username}: {u_exc}"
                    )
                    report["steps"]["user_email_saved"] = {"status": "error", "error": str(u_exc)}

            # 4.3 Передаем данные в 1С (ЗУП) через OData
            if sync_1c:
                person_key = getattr(portal_user, "person_ref_key", None)
                if person_key and str(person_key) not in ["", "00000000-0000-0000-0000-000000000000"]:
                    try:
                        from administration_app.utils import update_1c_physical_person_email
                        sync_1c_ok, sync_1c_msg = update_1c_physical_person_email(
                            person_ref_key=str(person_key),
                            email=full_email,
                            base_index=0,
                        )
                        report["steps"]["sync_1c"] = {
                            "status": "ok" if sync_1c_ok else "warning",
                            "success": sync_1c_ok,
                            "message": sync_1c_msg,
                            "person_ref_key": str(person_key),
                        }
                        if sync_1c_ok:
                            logger.info(
                                f"[KerioAdminService] Email '{full_email}' успешно синхронизирован с 1С (ЗУП) для физлица {person_key}."
                            )
                        else:
                            logger.warning(
                                f"[KerioAdminService] Замечание синхронизации email с 1С для {portal_user.username}: {sync_1c_msg}"
                            )
                    except Exception as one_c_exc:
                        logger.error(f"[KerioAdminService] Ошибка при синхронизации с 1С: {one_c_exc}")
                        report["steps"]["sync_1c"] = {
                            "status": "error",
                            "success": False,
                            "message": str(one_c_exc),
                        }
                else:
                    guid_msg = "GUID физлица в 1С отсутствует (person_ref_key не указан)"
                    report["steps"]["sync_1c"] = {
                        "status": "skipped",
                        "success": False,
                        "message": guid_msg,
                    }
                    logger.info(
                        f"[KerioAdminService] Синхронизация с 1С пропущена ({guid_msg}) для пользователя {portal_user.username}."
                    )

        if create_django_account and portal_user and MailAccount:
            try:
                with transaction.atomic():
                    mail_account, created = MailAccount.objects.get_or_create(
                        user=portal_user,
                        defaults={
                            "email": full_email,
                            "display_name": full_name or portal_user.get_full_name() or portal_user.username,
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

        if not target_password and User and models:
            u = User.objects.filter(
                models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
            ).select_related("user_work_profile").first()
            if u and hasattr(u, "user_work_profile") and u.user_work_profile and u.user_work_profile.work_email_password:
                target_password = u.user_work_profile.work_email_password.strip()

        existing_route = self.smtp_delivery.get_route_for_sender(full_email)
        is_individual_existing = bool(existing_route and existing_route.get("id") and not existing_route.get("isGlobal"))

        if not target_password:
            if is_individual_existing:
                return {
                    "success": True,
                    "action": "verified",
                    "route_id": existing_route.get("id"),
                    "email": full_email,
                    "is_individual": True,
                    "details": existing_route,
                    "message": f"Индивидуальная ретрансляция SMTP для '{full_email}' активна ({existing_route.get('server')}:{existing_route.get('port')}).",
                }
            if existing_route and existing_route.get("isGlobal"):
                return {
                    "success": True,
                    "action": "server_relay",
                    "route_id": existing_route.get("id"),
                    "email": full_email,
                    "is_individual": False,
                    "details": existing_route,
                    "message": f"Пользователь '{full_email}' использует общий серверный шлюз ({existing_route.get('server')}:{existing_route.get('port')}). Для создания индивидуальной записи в таблице Kerio укажите пароль.",
                }
            raise KerioValidationError(
                f"Не удалось определить пароль для '{full_email}'. Укажите пароль учетной записи для привязки SMTP AUTH."
            )

        # Синхронизируем Django MailAccount и рабочий профиль сотрудника
        if target_password and User and models:
            matched_users = User.objects.filter(
                models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
            ).select_related("user_work_profile")
            for u in matched_users:
                _sync_user_work_profile_password(u, target_password)

        if MailAccount and target_password:
            try:
                m_acc = MailAccount.objects.filter(email__iexact=full_email).first()
                if m_acc:
                    m_acc.set_password(target_password)
                    m_acc.smtp_host = relay_host or str(get_django_setting("KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru") or "smtp.barkol.ru")
                    m_acc.smtp_port = int(relay_port or get_django_setting("KERIO_DEFAULT_SMTP_RELAY_PORT", 587) or 587)
                    m_acc.save(update_fields=["encrypted_password", "smtp_host", "smtp_port", "updated_at"])
            except Exception as m_err:
                logger.debug(f"[KerioAdminService] Ошибка синхронизации MailAccount: {m_err}")

        if is_individual_existing:
            # Обновляем пароль в существующем индивидуальном правиле
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
                "is_individual": True,
                "details": res,
            }
        else:
            # Создаем правило в Kerio Connect через Smtp.set
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
                "is_individual": not res.get("is_global", False),
                "details": res,
            }

    def update_user_password(
        self,
        login_name: str,
        new_password: str,
        domain_name: str = "barkol.ru",
        update_django: bool = True,
    ) -> Dict[str, Any]:
        """Синхронно обновляет пароль в Kerio Connect, правиле POP3, правиле Доставка SMTP, MailAccount и DataBaseUserWorkProfile.

        Args:
            login_name (str): Логин пользователя.
            new_password (str): Новый пароль в открытом виде.
            domain_name (str): Имя домена.
            update_django (bool): Обновить ли пароль в MailAccount и профиле пользователя на сайте.

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

        # 5. Django MailAccount и DataBaseUserWorkProfile.work_email_password
        if update_django:
            updated_accounts_count = 0
            if MailAccount:
                accounts = MailAccount.objects.filter(email__iexact=full_email).select_related("user", "user__user_work_profile")
                for acc in accounts:
                    acc.set_password(new_password)
                    acc.save(update_fields=["encrypted_password", "updated_at"])
                    if acc.user:
                        _sync_user_work_profile_password(acc.user, new_password)
                updated_accounts_count = accounts.count()
                report["steps"]["django_account"] = f"updated {updated_accounts_count} accounts"

            # 5.2 Гарантированная синхронизация пароля в профиле сотрудника по email / loginName
            if User and models:
                matched_users = User.objects.filter(
                    models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
                ).select_related("user_work_profile")
                for u in matched_users:
                    _sync_user_work_profile_password(u, new_password)

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
        delete_external: bool = True,
    ) -> Dict[str, Any]:
        """Удаляет пользователя, его правило загрузки POP3, правило Доставки SMTP из Kerio Connect и ящик в ISPmanager.

        Args:
            login_name (str): Логин пользователя.
            domain_name (str): Домен почтового ящика (по умолчанию 'barkol.ru').
            delete_external (bool): Удалить ли связанный ящик на внешнем сервере ISPmanager (Reg.ru). По умолчанию True.

        Returns:
            Dict[str, Any]: Отчет об удалении со статусом выполнения каждого шага.

        Raises:
            KerioObjectNotFoundError: Если пользователь не найден в Kerio Connect.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        report: Dict[str, Any] = {"login": clean_login, "email": full_email, "deleted": False, "success": False, "steps": {}}

        # 1. Внешний почтовый сервер (ISPmanager на Reg.ru)
        if delete_external:
            try:
                ext_deleted = self.external_provider.delete_mailbox(full_email)
                report["steps"]["external_server"] = "ok" if ext_deleted else "skipped_or_not_found"
            except Exception as ext_err:
                logger.warning(f"[KerioAdminService] Ошибка удаления ящика '{full_email}' в ISPmanager: {ext_err}")
                report["steps"]["external_server"] = f"warning: {ext_err}"

        # 2. Удаляем POP3 правило в Kerio Connect
        try:
            pop3_rule = self.pop3.get_account_for_user(clean_login)
            if pop3_rule and "id" in pop3_rule:
                self.pop3.remove_pop3_account(pop3_rule["id"])
                report["steps"]["kerio_pop3_download"] = "ok"
        except Exception as pop_err:
            logger.warning(f"[KerioAdminService] Ошибка удаления правила POP3 для {clean_login}: {pop_err}")
            report["steps"]["kerio_pop3_download"] = f"warning: {pop_err}"

        # 3. Удаляем Доставка SMTP правило
        try:
            self.smtp_delivery.remove_route_for_sender(full_email)
            report["steps"]["kerio_smtp_delivery"] = "ok"
        except Exception as smtp_exc:
            logger.warning(f"[KerioAdminService] Ошибка удаления правила Доставка SMTP: {smtp_exc}")
            report["steps"]["kerio_smtp_delivery"] = f"warning: {smtp_exc}"

        # 4. Удаляем пользователя в Kerio Connect
        domain_id = self.domains.get_domain_id(domain_name)
        k_user = self.users.get_user_by_login(clean_login, domain_id=domain_id)
        if not k_user:
            raise KerioObjectNotFoundError(f"Пользователь '{clean_login}' не найден в Kerio Connect.")

        self.users.remove_user(k_user["id"], domain_id=domain_id)
        report["steps"]["kerio_user"] = "ok"

        # 5. Удаляем связанный MailAccount если есть
        if MailAccount:
            try:
                deleted_count, _ = MailAccount.objects.filter(email__iexact=full_email).delete()
                report["steps"]["django_account"] = f"deleted {deleted_count} records"
            except Exception as d_err:
                logger.debug(f"[KerioAdminService] Ошибка удаления MailAccount: {d_err}")

        report["deleted"] = True
        report["success"] = True
        return report

    def create_external_mailbox_for_user(
        self,
        login_name: str,
        domain_name: str = "barkol.ru",
        password: Optional[str] = None,
        full_name: Optional[str] = None,
        quota_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Создает почтовый ящик в ISPmanager на Reg.ru для существующего пользователя Kerio Connect.

        Если пароль не передан явно, автоматически пытается извлечь его из связанного
        `DataBaseUserWorkProfile.work_email_password` или `MailAccount`.

        Args:
            login_name (str): Логин пользователя.
            domain_name (str): Домен ящика (по умолчанию 'barkol.ru').
            password (Optional[str]): Пароль ящика (если None, извлекается из профиля).
            full_name (Optional[str]): Имя владельца ящика.
            quota_mb (Optional[int]): Дисковая квота в МБ.

        Returns:
            Dict[str, Any]: Результат создания ящика в ISPmanager.

        Raises:
            KerioValidationError: Если пароль не найден и не передан.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        full_email = f"{clean_login}@{domain_name}"

        # Автоматический поиск пароля в профиле, если не указан
        if not password and MailAccount:
            try:
                acc = MailAccount.objects.filter(email__iexact=full_email).first()
                if acc:
                    password = acc.get_password()
            except Exception:
                pass

        if not password and User:
            try:
                u = User.objects.filter(
                    models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
                ).select_related("user_work_profile").first()
                if u and hasattr(u, "user_work_profile") and u.user_work_profile and u.user_work_profile.work_email_password:
                    password = u.user_work_profile.work_email_password
                if not full_name and u:
                    full_name = getattr(u, "title", "") or u.get_full_name() or u.username
            except Exception:
                pass

        if not password:
            raise KerioValidationError(
                f"Не удалось определить пароль для '{clean_login}'. Укажите пароль явно для создания ящика в ISPmanager."
            )

        res = self.external_provider.create_mailbox(
            email=full_email,
            password=password,
            full_name=full_name or clean_login,
            quota_mb=quota_mb,
        )
        return res

    def audit_mailboxes_sync(
        self,
        domain_name: str = "barkol.ru",
    ) -> Dict[str, Any]:
        """Выполняет комплексный аудит синхронизации почтовых ящиков между Kerio Connect и внешним ISPmanager (Reg.ru).

        Получает полный реестр пользователей Kerio Connect, сопоставляет его со списком ящиков в панели
        ISPmanager, правилами Загрузка POP3 и Доставка SMTP, и формирует аналитический отчет о расхождениях.

        Args:
            domain_name (str): Имя домена для аудита (по умолчанию 'barkol.ru').

        Returns:
            Dict[str, Any]: Словарь с результатами аудита:
                - success (bool): True при успешном сборе данных.
                - domain (str): Имя проверенного домена.
                - isp_provider_configured (bool): Флаг активности настроек ISPmanager.
                - isp_connected (bool): Статус подключения к панели ISPmanager.
                - summary (Dict[str, Any]): Сводная статистика (total_kerio, total_isp, synced_count, missing_in_isp_count, orphaned_in_isp_count, missing_pop3_count, missing_smtp_count).
                - users (List[Dict[str, Any]]): Список пользователей с детализацией статусов во всех системах.
                - orphans (List[Dict[str, Any]]): Почтовые ящики, присутствующие в ISPmanager, но отсутствующие в Kerio Connect.
                - message (str): Человекопонятное резюме аудита.
        """
        # 1. Пользователи Kerio Connect
        kerio_users_res = self.get_users_list(domain_name=domain_name, limit=1000)
        kerio_users = kerio_users_res.get("list", [])

        # 2. Ящики в ISPmanager
        isp_connected = False
        isp_error = None
        isp_mailboxes: List[Dict[str, Any]] = []

        if self.external_provider.is_configured:
            try:
                isp_mailboxes = self.external_provider.get_mailboxes(domain=domain_name if domain_name != "all" else None)
                isp_connected = True
            except Exception as e_isp:
                logger.warning(f"[KerioAdminService] Ошибка запроса ящиков из ISPmanager при аудите: {e_isp}")
                isp_connected = False
                isp_error = str(e_isp)
        else:
            isp_error = "Параметры подключения к ISPmanager не настроены в .env (ISPMANAGER_API_USER/PASSWORD)."

        # Строим карту ISPmanager ящиков для быстрого поиска
        isp_map: Dict[str, Dict[str, Any]] = {}
        for mb in isp_mailboxes:
            mb_email = str(mb.get("email", "")).strip().lower()
            mb_name = str(mb.get("name", "")).strip().lower()
            if mb_email:
                isp_map[mb_email] = mb
            if mb_name:
                isp_map[mb_name] = mb
                if "@" not in mb_name and domain_name and domain_name != "all":
                    isp_map[f"{mb_name}@{domain_name.lower()}"] = mb

        # Сопоставляем каждого пользователя Kerio с ISPmanager
        audit_users: List[Dict[str, Any]] = []
        matched_isp_emails: Set[str] = set()

        synced_count = 0
        missing_in_isp_count = 0
        missing_pop3_count = 0
        missing_smtp_count = 0

        for ku in kerio_users:
            login = ku.get("loginName", "")
            email = ku.get("email") or (f"{login}@{domain_name}" if "@" not in login else login)
            clean_login = login.strip().lower()
            clean_email = email.strip().lower()

            isp_box = isp_map.get(clean_email) or isp_map.get(clean_login) or isp_map.get(clean_login.split("@")[0])
            in_isp = bool(isp_box)

            if in_isp and isp_box:
                if isp_box.get("email"):
                    matched_isp_emails.add(str(isp_box["email"]).lower())
                if isp_box.get("name"):
                    matched_isp_emails.add(str(isp_box["name"]).lower())

            has_pop3 = bool(ku.get("has_pop3_download"))
            has_smtp = bool(ku.get("has_smtp_delivery"))
            is_indiv_smtp = bool(ku.get("is_individual_smtp_delivery"))

            if not has_pop3:
                missing_pop3_count += 1
            if not has_smtp:
                missing_smtp_count += 1

            if in_isp:
                synced_count += 1
                sync_status = "synced"
                sync_label = "Создан везде"
            else:
                missing_in_isp_count += 1
                sync_status = "missing_in_isp"
                sync_label = "Отсутствует в ISPmanager"

            audit_users.append({
                "login": clean_login,
                "email": clean_email,
                "full_name": ku.get("fullName", ""),
                "description": ku.get("description", ""),
                "is_enabled": ku.get("isEnabled", True),
                "in_kerio": True,
                "in_ispmanager": in_isp,
                "isp_quota": isp_box.get("quota") if isp_box else None,
                "isp_used": isp_box.get("used") if isp_box else None,
                "isp_status": isp_box.get("status") if isp_box else None,
                "isp_note": isp_box.get("note") if isp_box else None,
                "has_pop3": has_pop3,
                "pop3_details": ku.get("pop3_details"),
                "has_smtp_delivery": has_smtp,
                "is_individual_smtp_delivery": is_indiv_smtp,
                "smtp_delivery_details": ku.get("smtp_delivery_details"),
                "sync_status": sync_status,
                "sync_label": sync_label,
            })

        # Поиск сирот (ящики есть в ISPmanager, но нет в Kerio)
        orphans: List[Dict[str, Any]] = []
        for mb in isp_mailboxes:
            mb_email = str(mb.get("email", "")).strip().lower()
            mb_name = str(mb.get("name", "")).strip().lower()
            if mb_email not in matched_isp_emails and mb_name not in matched_isp_emails:
                orphans.append({
                    "email": mb.get("email") or f"{mb_name}@{domain_name}",
                    "name": mb_name,
                    "domain": mb.get("domain", domain_name),
                    "quota": mb.get("quota"),
                    "used": mb.get("used"),
                    "status": mb.get("status"),
                    "note": mb.get("note"),
                    "in_kerio": False,
                    "in_ispmanager": True,
                    "sync_status": "orphan_in_isp",
                    "sync_label": "Только в ISPmanager",
                })

        summary = {
            "total_kerio": len(kerio_users),
            "total_isp": len(isp_mailboxes),
            "synced_count": synced_count,
            "missing_in_isp_count": missing_in_isp_count,
            "orphaned_in_isp_count": len(orphans),
            "missing_pop3_count": missing_pop3_count,
            "missing_smtp_count": missing_smtp_count,
            "isp_provider_configured": self.external_provider.is_configured,
            "isp_connected": isp_connected,
            "isp_error": isp_error,
        }

        return {
            "success": True,
            "domain": domain_name,
            "summary": summary,
            "users": audit_users,
            "orphans": orphans,
            "message": (
                f"Аудит завершен: в Kerio Connect {len(kerio_users)} ящиков, "
                f"в ISPmanager {len(isp_mailboxes)} ящиков. "
                f"Синхронизировано: {synced_count}, отсутствуют в ISPmanager: {missing_in_isp_count}, "
                f"только в ISPmanager: {len(orphans)}."
            ),
        }

    def sync_user_email_to_portal_and_1c(
        self,
        login_name: str,
        domain_name: str = "barkol.ru",
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Синхронизирует корпоративный email ящика с профилем сотрудника DataBaseUser и 1С (ЗУП).

        Выполняет:
        1. Определение целевого email адреса (по переданному значению или login_name@domain_name).
        2. Поиск сотрудника портала в модели DataBaseUser (по username, email или связанному MailAccount).
        3. Запись email в профиль DataBaseUser (user.email) и сохранение в БД.
        4. Отправку PATCH-запроса через OData (update_1c_physical_person_email) в 1С ЗУП по person_ref_key.

        Args:
            login_name (str): Логин пользователя (например, 'i.ivanov' или 'i.ivanov@barkol.ru').
            domain_name (str): Домен почты (по умолчанию 'barkol.ru').
            email (Optional[str]): Явный email адрес (если не указан, формируется автоматически).

        Returns:
            Dict[str, Any]: Словарь с результатами синхронизации:
                - success (bool): Общий статус выполнения операции.
                - message (str): Человекочитаемое сообщение о результате.
                - email (str): Синхронизированный email адрес.
                - user_id (Optional[int]): ID пользователя портала DataBaseUser.
                - portal_synced (bool): Успешность сохранения email на портале.
                - one_c_synced (bool): Успешность синхронизации с 1С (ЗУП).
                - one_c_message (str): Детальный ответ шлюза 1С OData.

        Raises:
            KerioValidationError: Если не указан логин пользователя.
        """
        clean_login = login_name.split("@")[0].strip().lower()
        if not clean_login:
            raise KerioValidationError("Логин пользователя обязателен для синхронизации.")

        target_domain = domain_name.strip().lower() if domain_name else "barkol.ru"
        full_email = str(email).strip().lower() if email else f"{clean_login}@{target_domain}"

        portal_user = None
        if User and models:
            portal_user = User.objects.filter(
                models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
            ).select_related("user_work_profile").first()

            if not portal_user and MailAccount:
                acc = MailAccount.objects.filter(
                    models.Q(email__iexact=full_email) | models.Q(username__iexact=clean_login)
                ).select_related("user").first()
                if acc and acc.user:
                    portal_user = acc.user

        if not portal_user:
            return {
                "success": False,
                "message": f"Сотрудник на портале для учетной записи '{clean_login}' ({full_email}) не найден.",
                "email": full_email,
                "user_id": None,
                "portal_synced": False,
                "one_c_synced": False,
                "one_c_message": "Пользователь портала не найден",
            }

        # 1. Запись email в профиль сотрудника на портале
        portal_synced = False
        try:
            portal_user.email = full_email
            portal_user.save(update_fields=["email"])
            portal_synced = True
            logger.info(
                f"[KerioAdminService] Email '{full_email}' сохранен в профиль сотрудника {portal_user.username} (ID: {portal_user.pk})."
            )
        except Exception as p_exc:
            logger.error(
                f"[KerioAdminService] Ошибка сохранения email в профиль пользователя {portal_user.username}: {p_exc}"
            )

        # 2. Передача email в 1С (ЗУП) через OData
        one_c_synced = False
        one_c_message = ""
        person_key = getattr(portal_user, "person_ref_key", None)
        if person_key and str(person_key) not in ["", "00000000-0000-0000-0000-000000000000"]:
            try:
                from administration_app.utils import update_1c_physical_person_email
                one_c_synced, one_c_message = update_1c_physical_person_email(
                    person_ref_key=str(person_key),
                    email=full_email,
                    base_index=0,
                )
                if one_c_synced:
                    logger.info(
                        f"[KerioAdminService] Email '{full_email}' успешно синхронизирован с 1С (ЗУП) для физлица {person_key}."
                    )
                else:
                    logger.warning(
                        f"[KerioAdminService] Замечание синхронизации email с 1С для {portal_user.username}: {one_c_message}"
                    )
            except Exception as one_c_exc:
                one_c_message = str(one_c_exc)
                logger.error(f"[KerioAdminService] Ошибка вызова update_1c_physical_person_email: {one_c_exc}")
        else:
            one_c_message = "GUID физлица в 1С отсутствует (person_ref_key не указан)"
            logger.info(
                f"[KerioAdminService] Синхронизация с 1С пропущена ({one_c_message}) для {portal_user.username}."
            )

        # Формирование итогового сообщения
        if one_c_synced and portal_synced:
            msg = f"Email '{full_email}' успешно сохранен в профиле портала и синхронизирован с 1С (ЗУП)!"
        elif portal_synced and not one_c_synced and "GUID физлица" in one_c_message:
            msg = f"Email '{full_email}' сохранен на портале, но в 1С не передан (у сотрудника отсутствует GUID физлица)."
        elif portal_synced and not one_c_synced:
            msg = f"Email '{full_email}' сохранен на портале, но при передаче в 1С возникло замечание: {one_c_message}"
        else:
            msg = f"Ошибка сохранения email на портале. Замечание 1С: {one_c_message}"

        return {
            "success": portal_synced or one_c_synced,
            "message": msg,
            "email": full_email,
            "user_id": portal_user.pk,
            "portal_synced": portal_synced,
            "one_c_synced": one_c_synced,
            "one_c_message": one_c_message,
        }

