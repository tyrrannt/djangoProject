"""Команда управления Django для комплексной проверки методов Users, Domains, Delivery и SMTP в Kerio Connect API."""

from typing import Any, Dict, List
import json
import urllib3
from django.conf import settings
from django.core.management.base import BaseCommand

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.users import UserManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Command(BaseCommand):
    """Команда для проверки методов Users, Domains, Delivery и SMTP в Kerio Connect 9.4.1."""

    help = "Тестирует методы Users.get, Users.getDetails, Delivery.getPop3AccountList и зондирует методы SMTP Delivery в Kerio Connect."

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа."""
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

        # 2. Проверка универсального получения пользователей через user_mgr.get_users (без domain_id и с domain_id)
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

        # 3. Проверка поиска пользователей по логину (например grinyak, a.deryanin, a.abramov)
        self.stdout.write("\n[3] Тестирование поиска пользователей по loginName через get_user_by_id_or_login:")
        test_logins = ["grinyak", "a.deryanin", "a.abramov", "admin"]
        for t_login in test_logins:
            try:
                found_user = user_mgr.get_user_by_id_or_login(t_login)
                self.stdout.write(self.style.SUCCESS(f"    [OK] Найден '{t_login}': ID={found_user.get('id')}, ФИО='{found_user.get('fullName')}', enabled={found_user.get('isEnabled')}"))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"    [SKIP] Пользователь '{t_login}': {exc}"))

        # 4. Проверка Delivery.getPop3AccountList
        self.stdout.write("\n[4] Проверка правил сбора POP3 (Delivery.getPop3AccountList):")
        try:
            res = client.call("Delivery.getPop3AccountList", params={"query": {}})
            accs = res.get("list", []) if isinstance(res, dict) else res
            self.stdout.write(self.style.SUCCESS(f"    Успешно: найдено {len(accs)} правил POP3"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"    Ошибка Delivery.getPop3AccountList: {exc}"))

        # 5. Полный дамп Smtp.get и зондирование методов SMTP и маршрутизации
        self.stdout.write("\n[5] Полный анализ 'Smtp.get' и зондирование методов Доставки SMTP:")
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

        # 7. Автоматический краулер WebAdmin JS бандлов для извлечения всех зарегистрированных методов API
        self.stdout.write("\n[7] Сканирование JS-ресурсов WebAdmin Kerio Connect для поиска методов API:")
        discovered_api_methods = set()
        try:
            base_admin_url = api_url.split("/admin/api")[0] + "/admin/"
            self.stdout.write(f"    Загрузка WebAdmin главной страницы: {base_admin_url}")
            resp = client.session.get(base_admin_url, verify=False, timeout=10)
            if resp.status_code == 200:
                import re
                from urllib.parse import urljoin
                html = resp.text
                script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                self.stdout.write(f"    Найдено скриптов в HTML: {len(script_srcs)}")
                
                # Дополнительные стандартные пути ExtJS WebAdmin Kerio Connect
                standard_js_paths = [
                    "webadmin/app.js",
                    "webadmin/all-classes.js",
                    "webadmin/classes.json",
                    "app/all-classes.js",
                    "app.js",
                    "all-classes.js",
                ]
                all_urls_to_check = set([urljoin(base_admin_url, s) for s in script_srcs] + [urljoin(base_admin_url, p) for p in standard_js_paths])

                for js_url in all_urls_to_check:
                    try:
                        js_resp = client.session.get(js_url, verify=False, timeout=15)
                        if js_resp.status_code == 200 and len(js_resp.content) > 500:
                            self.stdout.write(self.style.SUCCESS(f"    [OK] Загружен JS бандл: {js_url} ({len(js_resp.content)} байт)"))
                            js_text = js_resp.text
                            # Поиск всех вызовов API вида "Interface.method"
                            matches = re.findall(r'["\']([A-Z][a-zA-Z0-9]+\.[a-zA-Z0-9]+)["\']', js_text)
                            for m in matches:
                                if "." in m and not m.startswith("Ext.") and not m.startswith("Kerio."):
                                    discovered_api_methods.add(m)
                    except Exception as j_exc:
                        pass
            else:
                self.stdout.write(self.style.WARNING(f"    Ответ WebAdmin: {resp.status_code}"))
        except Exception as c_exc:
            self.stdout.write(self.style.WARNING(f"    Краулер WebAdmin завершился с предупреждением: {c_exc}"))

        if discovered_api_methods:
            self.stdout.write(self.style.SUCCESS(f"    Всего извлечено уникальных методов API из WebAdmin: {len(discovered_api_methods)}"))
            delivery_smtp_methods = [m for m in sorted(discovered_api_methods) if any(k in m.lower() for k in ["delivery", "smtp", "route", "relay", "pop3", "mail"])]
            self.stdout.write(self.style.SUCCESS(f"    Методы Delivery / Smtp / Routing / Pop3 ({len(delivery_smtp_methods)}):"))
            for dm in delivery_smtp_methods:
                self.stdout.write(f"      - {dm}")
        else:
            self.stdout.write(self.style.NOTICE("    Прямое извлечение из JS не вернуло методов, используем встроенную базу зондирования."))

        # 8. Зондирование методов маршрутизации и правил Доставки SMTP
        self.stdout.write("\n[8] Зондирование методов маршрутизации и правил Доставки SMTP:")
        
        # Список интерфейсов и методов для тестирования
        interfaces_to_test = [
            "Delivery", "DeliveryRoutes", "DeliveryRouting", "SmtpDelivery",
            "SmtpRouting", "SmtpRoutes", "SmtpRelay", "Routing", "Routes",
            "RoutingRules", "Relay", "RelayRules", "MailDelivery", "MailRouting",
            "OutgoingRouting", "MessageRouting", "Smtp", "Server", "Domains"
        ]
        
        action_names = [
            "get", "getSettings", "getDelivery", "getDeliveryOptions", "getDeliveryRouteList",
            "getDeliveryRoutes", "getRouteList", "getRoutes", "getRouting", "getRoutingRules",
            "getRoutingRuleList", "getRelay", "getRelayOptions", "getInternetConnection",
            "getSmtpDelivery", "getDeliveryRules", "getForwarding", "getOptions"
        ]

        methods_to_probe = set([f"{i}.{a}" for i in interfaces_to_test for a in action_names])
        if discovered_api_methods:
            methods_to_probe.update([m for m in discovered_api_methods if any(k in m.lower() for k in ["delivery", "smtp", "route", "relay", "pop3", "mail"])])

        found_smtp_methods = []

        for method_name in sorted(methods_to_probe):
            # Пробуем вызов с пустыми параметрами, а затем с query/domainId
            for sample_params in [{}, {"query": {}}, {"domainId": domain_id} if domain_id else None]:
                if sample_params is None:
                    continue
                try:
                    res = client.call(method_name, params=sample_params)
                    self.stdout.write(self.style.SUCCESS(f"    [FOUND WORKING!] '{method_name}' с params={sample_params}:"))
                    res_str = json.dumps(res, ensure_ascii=False, indent=6)
                    if len(res_str) > 1500:
                        res_str = res_str[:1500] + "\n      ... (обрезано)"
                    self.stdout.write(f"      {res_str}")
                    found_smtp_methods.append(method_name)
                    break
                except Exception as exc:
                    err_msg = str(exc)
                    if "-32601" in err_msg:
                        # Method not found
                        break
                    elif "-32602" in err_msg:
                        self.stdout.write(self.style.NOTICE(f"    [METHOD EXISTS, NEEDS SPECIFIC PARAMS] '{method_name}': {err_msg}"))
                        found_smtp_methods.append(method_name)
                        break
                    else:
                        pass

        if found_smtp_methods:
            self.stdout.write(self.style.SUCCESS(f"\nНайденные рабочие методы доставки/маршрутизации: {list(set(found_smtp_methods))}"))
        else:
            self.stdout.write(self.style.WARNING("\nСпецифические методы маршрутизации не найдены."))

        client.logout()
        self.stdout.write(self.style.SUCCESS("Сессия успешно закрыта.\n"))
