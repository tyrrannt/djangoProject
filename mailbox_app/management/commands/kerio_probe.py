from typing import Any, Dict, List, Optional
import json
import urllib3
from django.conf import settings
from django.core.management.base import BaseCommand

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.service import KerioAdminService
from mailbox_app.services.kerio.smtp_delivery import SmtpDeliveryManager
from mailbox_app.services.kerio.users import UserManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Command(BaseCommand):
    """Команда для проверки методов Users, Domains, Delivery и SMTP в Kerio Connect 9.4.1."""

    help = "Тестирует методы Users.get, Users.getDetails, Delivery.getPop3AccountList, правила «Доставка SMTP» и выполняет диагностику SMTP/IMAP в Kerio Connect."

    def add_arguments(self, parser: Any) -> None:
        """Добавляет аргументы командной строки."""
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Логин или email сотрудника для проверки (например, a.administrator или a.administrator@barkol.ru)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help="Пароль учетной записи сотрудника для тестирования SMTP и IMAP",
        )
        parser.add_argument(
            "--test-smtp",
            action="store_true",
            help="Выполнить диагностику подключения и отправки SMTP для указанного пользователя",
        )
        parser.add_argument(
            "--fix-smtp-route",
            action="store_true",
            help="Автоматически создать или обновить правило «Доставка SMTP» (ретрансляция smtp.barkol.ru:587) для указанного пользователя",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа."""
        target_user_arg = options.get("user")
        target_password_arg = options.get("password")
        test_smtp_flag = options.get("test_smtp") or bool(target_user_arg)

        api_url = getattr(settings, "KERIO_API_URL", "https://192.168.10.242:4040/admin/api/jsonrpc/")
        username = getattr(settings, "KERIO_API_USER", "admin")
        password = getattr(settings, "KERIO_API_PASSWORD", "")

        client = KerioConnectAdminClient(
            api_url=api_url,
            username=username,
            password=password,
            verify_ssl=False,
            timeout=10,
        )

        client.login()
        self.stdout.write(self.style.SUCCESS(f"Авторизация успешна (токен {client.token[:12]}...)"))

        user_mgr = UserManager(client)

        # 1. Проверка Domains.get
        domain_id = None
        try:
            dom_res = client.call("Domains.get", params={"query": {}})
            dom_list = dom_res.get("list", []) if isinstance(dom_res, dict) else dom_res
            self.stdout.write(self.style.SUCCESS(f"[1] Domains.get: найдено {len(dom_list)} доменов"))
            for d in dom_list:
                d_id = d.get("id")
                d_name = d.get("name")
                self.stdout.write(f"    - Домен: {d_name} (ID: {d_id})")
                if not domain_id:
                    domain_id = d_id
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"[1] Domains.get ошибка: {exc}"))

        # 2. Проверка универсального получения пользователей через user_mgr.get_users
        self.stdout.write("\n[2] Проверка UserManager.get_users (автосбор всех пользователей доменов):")
        try:
            all_users_res = user_mgr.get_users(limit=1000)
            u_list = all_users_res.get("list", [])
            total = all_users_res.get("totalItems", len(u_list))
            self.stdout.write(self.style.SUCCESS(f"    Всего пользователей на сервере: {len(u_list)} (totalItems: {total})"))
            logins_sample = [u.get("loginName") for u in u_list[:10] if u.get("loginName")]
            self.stdout.write(f"    Примеры логинов: {', '.join(logins_sample)}")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка get_users: {exc}"))

        # 3. Проверка поиска целевого пользователя
        test_logins = [target_user_arg] if target_user_arg else ["a.administrator", "grinyak", "a.deryanin", "a.abramov", "admin"]
        self.stdout.write(f"\n[3] Поиск и статус пользователей ({', '.join(test_logins)}):")
        for t_login in test_logins:
            try:
                found_user = user_mgr.get_user_by_id_or_login(t_login)
                self.stdout.write(self.style.SUCCESS(f"    [OK] Найден '{t_login}': ID={found_user.get('id')}, ФИО='{found_user.get('fullName')}', enabled={found_user.get('isEnabled')}"))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"    [SKIP] Пользователь '{t_login}': {exc}"))

        # 4. Проверка правил сбора POP3 (Delivery.getPop3AccountList)
        self.stdout.write("\n[4] Проверка правил сбора POP3 (Delivery.getPop3AccountList):")
        try:
            res = client.call("Delivery.getPop3AccountList", params={"query": {}})
            accs = res.get("list", []) if isinstance(res, dict) else res
            self.stdout.write(self.style.SUCCESS(f"    Успешно: найдено {len(accs)} правил POP3"))
            if target_user_arg:
                matched_pop3 = [a for a in accs if target_user_arg.lower() in str(a.get("targetUser", "")).lower() or target_user_arg.lower() in str(a.get("deliveryAddress", "")).lower() or target_user_arg.lower() in str(a.get("userName", "")).lower()]
                if matched_pop3:
                    self.stdout.write(self.style.SUCCESS(f"    -> Найдено правило POP3 для '{target_user_arg}': {json.dumps(matched_pop3[0], ensure_ascii=False, indent=6)}"))
                else:
                    self.stdout.write(self.style.WARNING(f"    -> Правило POP3 для '{target_user_arg}' НЕ найдено в списке."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка Delivery.getPop3AccountList: {exc}"))

        # 5. Полный дамп Smtp.get
        self.stdout.write("\n[5] Полный анализ 'Smtp.get':")
        try:
            smtp_full_res = client.call("Smtp.get", params={})
            self.stdout.write(self.style.SUCCESS("    [Smtp.get] Полная структура настроек SMTP сервера:"))
            self.stdout.write(json.dumps(smtp_full_res, ensure_ascii=False, indent=4))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка Smtp.get: {exc}"))

        # 6. Проверка Domains.getSettings для каждого домена
        self.stdout.write("\n[6] Анализ настроек доменов (Domains.getSettings):")
        try:
            dom_res = client.call("Domains.get", params={"query": {}})
            dom_list = dom_res.get("list", []) if isinstance(dom_res, dict) else dom_res
            for d in dom_list:
                d_id = d.get("id")
                d_name = d.get("name")
                try:
                    d_settings = client.call("Domains.getSettings", params={"domainId": d_id})
                    self.stdout.write(self.style.SUCCESS(f"    [Domains.getSettings] Домен '{d_name}' ({d_id}):"))
                    self.stdout.write(json.dumps(d_settings, ensure_ascii=False, indent=6))
                except Exception as d_exc:
                    self.stdout.write(self.style.WARNING(f"    Не удалось получить настройки домена {d_name}: {d_exc}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка Domains.getSettings: {exc}"))

        # 7. Глубокий анализ kerioApiConstants.js и WebAdmin для поиска методов SMTP/Delivery маршрутов
        self.stdout.write("\n[7] Сканирование интерфейсов Kerio Connect для правил «Доставка SMTP» (SMTP Delivery):")
        try:
            import re
            base_admin_url = api_url.split("/admin/api")[0] + "/admin/"
            const_url = base_admin_url + "kerioApiConstants.js"
            c_resp = client.session.get(const_url, verify=False, timeout=10)
            if c_resp.status_code == 200:
                self.stdout.write(self.style.SUCCESS(f"    [OK] Загружен kerioApiConstants.js ({len(c_resp.content)} байт)"))
                const_text = c_resp.text
                
                # Ищем все ключевые слова
                lines = const_text.splitlines()
                matched_lines = [l.strip() for l in lines if any(k in l.lower() for k in ["delivery", "smtp", "relay", "route", "routing", "rule"])]
                self.stdout.write(f"    Строк с ключевыми словами в kerioApiConstants.js: {len(matched_lines)}")
                for ml in matched_lines[:40]:
                    self.stdout.write(f"      - {ml}")

                # Ищем идентификаторы интерфейсов и методов
                found_tokens = set(re.findall(r'([A-Za-z0-9_]+)', const_text))
                target_tokens = [t for t in found_tokens if any(k in t.lower() for k in ["route", "relay", "delivery", "smtp"]) and len(t) > 3]
                self.stdout.write(f"    Токены API: {', '.join(sorted(target_tokens)[:30])}")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"    Анализ kerioApiConstants.js: {exc}"))

        # 8. Проверка настроенных правил исходящей ретрансляции «Доставка SMTP» (SmtpDeliveryManager)
        self.stdout.write("\n[8] Проверка правил исходящей маршрутизации «Доставка SMTP» (SmtpDeliveryManager):")
        smtp_delivery_mgr = SmtpDeliveryManager(client)
        fix_route_flag = options.get("fix_smtp_route", False)

        try:
            routes = smtp_delivery_mgr.get_routes()
            self.stdout.write(self.style.SUCCESS(f"    Найдено настроенных правил доставки SMTP: {len(routes)}"))
            for r in routes:
                self.stdout.write(f"      - ID={r.get('id')}: Отправитель='{r.get('sender') or r.get('matchPattern')}', Сервер={r.get('server')}:{r.get('port')}, AuthUser='{r.get('userName')}', Active={r.get('isEnabled')}")

            if target_user_arg:
                target_user_clean = target_user_arg.split("@")[0].lower()
                target_email = f"{target_user_clean}@barkol.ru"
                matched_route = smtp_delivery_mgr.get_route_for_sender(target_email)

                if matched_route:
                    self.stdout.write(self.style.SUCCESS(f"    -> [OK] Найдено правило ретрансляции SMTP для '{target_email}': {json.dumps(matched_route, ensure_ascii=False, indent=6)}"))
                else:
                    self.stdout.write(self.style.WARNING(f"    -> [MISSING] Правило ретрансляции SMTP для '{target_email}' ОТСУТСТВУЕТ!"))
                    if fix_route_flag or target_password_arg:
                        self.stdout.write(self.style.NOTICE(f"    -> Создание правила ретрансляции SMTP для '{target_email}'..."))
                        try:
                            service_obj = KerioAdminService(client=client)
                            fix_res = service_obj.ensure_user_smtp_delivery_route(
                                login_name=target_user_clean,
                                password=target_password_arg,
                                domain_name="barkol.ru",
                            )
                            self.stdout.write(self.style.SUCCESS(f"    -> [SUCCESS] Правило ретрансляции SMTP успешно создано: {json.dumps(fix_res, ensure_ascii=False, indent=6)}"))
                        except Exception as fix_exc:
                            self.stdout.write(self.style.ERROR(f"    -> [ERROR] Не удалось создать правило ретрансляции SMTP: {fix_exc}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка SmtpDeliveryManager: {exc}"))

        # 9. Комплексная диагностика SMTP и IMAP подключения для пользователя
        if test_smtp_flag:
            target_user_clean = (target_user_arg or "a.administrator").split("@")[0].lower()
            target_email = f"{target_user_clean}@barkol.ru"
            
            # Пытаемся получить пароль из базы Django MailAccount если не указан явно
            target_pass = target_password_arg
            if not target_pass:
                try:
                    from mailbox_app.models import MailAccount
                    acc = MailAccount.objects.filter(email__iexact=target_email).first()
                    if acc:
                        target_pass = acc.get_password()
                        self.stdout.write(self.style.SUCCESS(f"\n[9] Получен сохраненный пароль из Django MailAccount для '{target_email}'"))
                except Exception:
                    pass

            self.stdout.write(f"\n[9] Комплексное тестирование подключения SMTP/IMAP для '{target_email}':")
            if not target_pass:
                self.stdout.write(self.style.WARNING("    Пароль не указан. Запустите с параметром --password <пароль> для проверки авторизации."))
            else:
                from mailbox_app.services.connection_test_service import test_imap_connection, test_smtp_connection

                servers_to_test = [
                    ("sm.barkol.ru", 465, "ssl", "Внутренний корпоративный SMTP шлюз (sm.barkol.ru:465 SSL)"),
                    ("smtp.barkol.ru", 587, "starttls", "Сервер ретрансляции SMTP Relay (smtp.barkol.ru:587 STARTTLS)"),
                    ("mail.barkol.ru", 465, "ssl", "Внешний почтовый сервер (mail.barkol.ru:465 SSL)"),
                    ("mail.barkol.ru", 587, "starttls", "Внешний почтовый сервер (mail.barkol.ru:587 STARTTLS)"),
                    ("192.168.10.242", 25, "plain", "Локальный Kerio Connect SMTP (192.168.10.242:25 Plain/STARTTLS)"),
                    ("192.168.10.242", 465, "ssl", "Локальный Kerio Connect SMTP (192.168.10.242:465 SSL)"),
                ]

                self.stdout.write("    --- ТЕСТИРОВАНИЕ SMTP СЕРВЕРОВ ---")
                for host, port, sec, desc in servers_to_test:
                    ok, msg = test_smtp_connection(
                        host=host,
                        port=port,
                        security=sec,
                        username=target_email,
                        password=target_pass,
                    )
                    if not ok:
                        # Пробуем без доменной части
                        ok2, msg2 = test_smtp_connection(
                            host=host,
                            port=port,
                            security=sec,
                            username=target_user_clean,
                            password=target_pass,
                        )
                        if ok2:
                            ok, msg = ok2, f"{msg2} (авторизован по короткому логину '{target_user_clean}')"

                    status_style = self.style.SUCCESS if ok else self.style.ERROR
                    self.stdout.write(status_style(f"    [{'OK' if ok else 'FAIL'}] {desc}: {msg}"))

                self.stdout.write("\n    --- ТЕСТИРОВАНИЕ IMAP СЕРВЕРОВ ---")
                imap_servers = [
                    ("imap.barkol.ru", 993, "ssl", "Корпоративный IMAP (imap.barkol.ru:993 SSL)"),
                    ("mail.barkol.ru", 993, "ssl", "Внешний IMAP (mail.barkol.ru:993 SSL)"),
                    ("192.168.10.242", 993, "ssl", "Локальный Kerio Connect IMAP (192.168.10.242:993 SSL)"),
                ]
                for host, port, sec, desc in imap_servers:
                    ok, msg = test_imap_connection(
                        host=host,
                        port=port,
                        security=sec,
                        username=target_email,
                        password=target_pass,
                    )
                    if not ok:
                        ok2, msg2 = test_imap_connection(
                            host=host,
                            port=port,
                            security=sec,
                            username=target_user_clean,
                            password=target_pass,
                        )
                        if ok2:
                            ok, msg = ok2, f"{msg2} (авторизован по короткому логину '{target_user_clean}')"

                    status_style = self.style.SUCCESS if ok else self.style.ERROR
                    self.stdout.write(status_style(f"    [{'OK' if ok else 'FAIL'}] {desc}: {msg}"))

        client.logout()
        self.stdout.write(self.style.SUCCESS("\nСессия успешно закрыта.\n"))
