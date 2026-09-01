"""Команда детальной диагностики и профилирования производительности почты Kerio Connect."""

import email
from email.utils import parseaddr, parsedate_to_datetime
import imaplib
import logging
import socket
import ssl
import time
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand
from customers_app.models import DataBaseUser
from mailbox_app.models import MailAccount
from mailbox_app.services.account_service import get_user_mail_account
from mailbox_app.services.imap_service import decode_imap_utf7


class Command(BaseCommand):
    """Выполняет пошаговое профилирование сетевого и IMAP взаимодействия с замером миллисекунд."""

    help = "Диагностика и профилирование скорости подключения к почтовому серверу Kerio Connect"

    def add_arguments(self, parser):
        parser.add_argument("--user", type=str, help="Username пользователя (по умолчанию первый с настроенной почтой)")
        parser.add_argument("--host", type=str, help="IMAP хост для проверки (по умолчанию из настроек)")
        parser.add_argument("--port", type=int, default=993, help="IMAP порт (по умолчанию 993)")
        parser.add_argument("--email", type=str, help="Email адрес для проверки")
        parser.add_argument("--password", type=str, help="Пароль для проверки")
        parser.add_argument("--no-ssl", action="store_true", help="Не использовать SSL")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== ДИАГНОСТИКА ПОЧТОВОГО СЕРВЕРА KERIO CONNECT ==="))

        # 1. Определение учетных данных
        username = options.get("user")
        host = options.get("host")
        port = options.get("port") or 993
        email_addr = options.get("email")
        password = options.get("password")
        use_ssl = not options.get("no_ssl")

        if not email_addr or not password:
            user = None
            if username:
                user = DataBaseUser.objects.filter(username=username).first()
            else:
                user = DataBaseUser.objects.filter(mail_account__isnull=False).first() or DataBaseUser.objects.filter(user_work_profile__work_email_password__isnull=False).first()

            if not user:
                self.stderr.write(self.style.ERROR("Ошибка: Не найден пользователь с настроенной почтой. Укажите --user или --email и --password."))
                return

            account = get_user_mail_account(user)
            if not account or not account.get_password():
                self.stderr.write(self.style.ERROR(f"Ошибка: У пользователя {user.username} не найден пароль почты."))
                return

            email_addr = account.email
            password = account.get_password()
            host = host or account.imap_host or getattr(settings, "EMAIL_IMAP_HOST", "192.168.10.242")
            port = account.imap_port or 993
            use_ssl = account.imap_use_ssl

        self.stdout.write(f"Тестируемый хост:   {host}:{port} (SSL: {use_ssl})")
        self.stdout.write(f"Почтовый ящик:     {email_addr}")
        self.stdout.write("-" * 60)

        results: List[Dict[str, Any]] = []

        def record(step_name: str, duration_ms: float, details: str = "", status: str = "OK"):
            results.append({
                "step": step_name,
                "ms": duration_ms,
                "details": details,
                "status": status,
            })
            status_style = self.style.SUCCESS("[OK]") if status == "OK" else self.style.ERROR(f"[{status}]")
            self.stdout.write(f"{step_name:<35} | {duration_ms:>8.2f} ms | {status_style} {details}")

        total_start = time.perf_counter()

        # Step 1: DNS Resolution
        t0 = time.perf_counter()
        ip_address = host
        try:
            ip_address = socket.gethostbyname(host)
            dns_time = (time.perf_counter() - t0) * 1000
            record("1. DNS Resolution", dns_time, f"IP: {ip_address}")
        except Exception as e:
            dns_time = (time.perf_counter() - t0) * 1000
            record("1. DNS Resolution", dns_time, f"Ошибка: {e}", status="ERR")

        # Step 2: TCP Socket Connect
        t0 = time.perf_counter()
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=5)
            tcp_time = (time.perf_counter() - t0) * 1000
            record("2. TCP Socket Connect", tcp_time, f"Подключено к {ip_address}:{port}")
        except Exception as e:
            tcp_time = (time.perf_counter() - t0) * 1000
            record("2. TCP Socket Connect", tcp_time, f"Ошибка подключения: {e}", status="ERR")
            return
        finally:
            if sock:
                sock.close()

        # Step 3: SSL Handshake
        ssl_ctx = ssl.create_default_context()
        if host.strip().replace(".", "").isdigit():
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        client = None
        t0 = time.perf_counter()
        try:
            if use_ssl:
                client = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_ctx)
            else:
                client = imaplib.IMAP4(host, port)
            ssl_time = (time.perf_counter() - t0) * 1000
            cipher_info = ""
            if use_ssl and hasattr(client, "ssl") and client.ssl:
                cipher_info = f"Cipher: {client.ssl.cipher()[0]}, TLS: {client.ssl.version()}"
            record("3. IMAP Connect + SSL Handshake", ssl_time, cipher_info)
        except Exception as e:
            ssl_time = (time.perf_counter() - t0) * 1000
            record("3. IMAP Connect + SSL Handshake", ssl_time, f"Ошибка: {e}", status="ERR")
            return

        # Step 4: IMAP Login
        t0 = time.perf_counter()
        try:
            status, res = client.login(email_addr, password)
            login_time = (time.perf_counter() - t0) * 1000
            record("4. IMAP Login", login_time, f"Статус: {status}")
        except Exception as e:
            login_time = (time.perf_counter() - t0) * 1000
            record("4. IMAP Login", login_time, f"Ошибка авторизации: {e}", status="ERR")
            client.logout()
            return

        # Step 5: IMAP Capabilities
        try:
            caps_status, caps_data = client.capability()
            caps_str = caps_data[0].decode("latin-1") if caps_data and caps_data[0] else ""
            server_info = "Kerio Connect" if "KERIO" in caps_str.upper() else "IMAP4rev1"
            record("5. IMAP Capability", 0.1, f"{server_info} (EXT: {caps_str[:50]}...)")
        except Exception:
            pass

        # Step 6: IMAP LIST (Получение списка папок)
        t0 = time.perf_counter()
        folder_names = []
        try:
            status, folder_list = client.list()
            list_time = (time.perf_counter() - t0) * 1000
            if folder_list:
                folder_names = [f.decode("latin-1") for f in folder_list if f]
            record("6. IMAP LIST (Папки)", list_time, f"Найдено папок: {len(folder_names)}")
        except Exception as e:
            list_time = (time.perf_counter() - t0) * 1000
            record("6. IMAP LIST (Папки)", list_time, f"Ошибка: {e}", status="ERR")

        # Step 7: IMAP SELECT "INBOX"
        t0 = time.perf_counter()
        msg_count = 0
        try:
            status, select_data = client.select('"INBOX"', readonly=True)
            select_time = (time.perf_counter() - t0) * 1000
            if select_data and select_data[0]:
                msg_count = int(select_data[0].decode("ascii", errors="ignore") or 0)
            record("7. IMAP SELECT 'INBOX'", select_time, f"Всего сообщений: {msg_count}")
        except Exception as e:
            select_time = (time.perf_counter() - t0) * 1000
            record("7. IMAP SELECT 'INBOX'", select_time, f"Ошибка: {e}", status="ERR")

        # Step 8: IMAP UID SEARCH ALL
        t0 = time.perf_counter()
        uids = []
        try:
            status, search_data = client.uid("search", None, "ALL")
            search_time = (time.perf_counter() - t0) * 1000
            if search_data and search_data[0]:
                uids = [u for u in search_data[0].split() if u and u != b"0"]
            record("8. IMAP UID SEARCH ALL", search_time, f"Найдено UIDs: {len(uids)}")
        except Exception as e:
            search_time = (time.perf_counter() - t0) * 1000
            record("8. IMAP UID SEARCH ALL", search_time, f"Ошибка: {e}", status="ERR")

        # Step 9: IMAP UID SEARCH UNSEEN
        t0 = time.perf_counter()
        unseen_uids = []
        try:
            status, unseen_data = client.uid("search", None, "UNSEEN")
            unseen_time = (time.perf_counter() - t0) * 1000
            if unseen_data and unseen_data[0]:
                unseen_uids = [u for u in unseen_data[0].split() if u and u != b"0"]
            record("9. IMAP UID SEARCH UNSEEN", unseen_time, f"Непрочитанных: {len(unseen_uids)}")
        except Exception as e:
            unseen_time = (time.perf_counter() - t0) * 1000
            record("9. IMAP UID SEARCH UNSEEN", unseen_time, f"Ошибка: {e}", status="ERR")

        # Step 10: IMAP UID FETCH Batch (25 последних писем)
        batch_uids = uids[-25:] if len(uids) >= 25 else uids
        batch_uids.reverse()  # Сначала новые
        batch_bytes = 0
        fetch_time = 0
        parse_time = 0

        if batch_uids:
            uids_seq = ",".join(u.decode("ascii") if isinstance(u, bytes) else str(u) for u in batch_uids)
            t0 = time.perf_counter()
            try:
                status, fetch_data = client.uid(
                    "fetch",
                    uids_seq,
                    "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE MESSAGE-ID CONTENT-TYPE)])"
                )
                fetch_time = (time.perf_counter() - t0) * 1000
                if fetch_data:
                    for item in fetch_data:
                        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                            batch_bytes += len(item[1])
                record("10. IMAP Batch FETCH (25)", fetch_time, f"Получено данных: {batch_bytes / 1024:.1f} KB")
            except Exception as e:
                fetch_time = (time.perf_counter() - t0) * 1000
                record("10. IMAP Batch FETCH (25)", fetch_time, f"Ошибка: {e}", status="ERR")

            # Step 11: Python Headers Parsing
            t0 = time.perf_counter()
            parsed_count = 0
            if fetch_data:
                for item in fetch_data:
                    if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                        msg = email.message_from_bytes(item[1])
                        subj = msg.get("Subject") or ""
                        f_name, f_email = parseaddr(msg.get("From") or "")
                        d_str = msg.get("Date") or ""
                        parsed_count += 1
            parse_time = (time.perf_counter() - t0) * 1000
            record("11. Python Parsing (25)", parse_time, f"Обработано сообщений: {parsed_count}")

        # Step 12: Logout
        t0 = time.perf_counter()
        try:
            client.logout()
            logout_time = (time.perf_counter() - t0) * 1000
            record("12. IMAP Logout / Close", logout_time, "Сессия завершена")
        except Exception:
            pass

        total_time = (time.perf_counter() - total_start) * 1000
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"ИТОГОВОЕ ВРЕМЯ (ПОЛНЫЙ ЦИКЛ БЕЗ КЭША): {total_time:.2f} ms ({total_time / 1000:.2f} сек)"))
        self.stdout.write("=" * 60)

        # Вывод детального отчета для копирования
        self.stdout.write("\n📋 СКОПИРУЙТЕ ЭТОТ БЛОК ДЛЯ АНАЛИЗА ЛОГОВ:")
        self.stdout.write("```json")
        diag_payload = {
            "target": f"{host}:{port}",
            "ssl": use_ssl,
            "account": email_addr,
            "total_ms": round(total_time, 2),
            "steps": results,
        }
        import json
        self.stdout.write(json.dumps(diag_payload, ensure_ascii=False, indent=2))
        self.stdout.write("```\n")
