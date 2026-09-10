"""Management-команда для интерактивной диагностики и тестирования ISPmanager API (Reg.ru хостинг).

Позволяет проверить параметры подключения (.env), протестировать сетевую доступность панели ISPmanager,
проинспектировать форму `email.edit`, получить список существующих ящиков и выполнить тестовое
создание/изменение/удаление учетных записей.
"""

import json
from typing import Any, Dict, List, Optional

import urllib3
from django.conf import settings
from django.core.management.base import BaseCommand

from mailbox_app.services.kerio.external_provider import ISPmanagerExternalMailProvider
from mailbox_app.services.kerio.utils import get_django_setting

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Command(BaseCommand):
    """Команда для диагностики и тестирования API панели ISPmanager (хостинг Reg.ru)."""

    help = (
        "Диагностирует подключение к ISPmanager API (Reg.ru), выводит список ящиков, "
        "инспектирует форму email.edit и тестирует создание/смену пароля ящиков."
    )

    def add_arguments(self, parser: Any) -> None:
        """Добавляет аргументы командной строки."""
        parser.add_argument(
            "--domain",
            type=str,
            default="barkol.ru",
            help="Почтовый домен для проверки и фильтрации (по умолчанию barkol.ru)",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=None,
            help="Переопределить URL панели ISPmanager (по умолчанию из ISPMANAGER_API_URL)",
        )
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Переопределить логин ISPmanager (по умолчанию из ISPMANAGER_API_USER)",
        )
        parser.add_argument(
            "--isp-password",
            type=str,
            default=None,
            help="Переопределить пароль ISPmanager (по умолчанию из ISPMANAGER_API_PASSWORD)",
        )
        parser.add_argument(
            "--create-user",
            type=str,
            default=None,
            help="Логин или email создаваемого ящика (например, a.administrator или a.administrator@barkol.ru)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help="Пароль создаваемого или обновляемого ящика",
        )
        parser.add_argument(
            "--full-name",
            type=str,
            default="",
            help="Имя владельца ящика / примечание",
        )
        parser.add_argument(
            "--quota",
            type=int,
            default=None,
            help="Размер дисковой квоты ящика в МБ",
        )
        parser.add_argument(
            "--change-password",
            type=str,
            default=None,
            help="Email ящика для изменения пароля (требуется --password)",
        )
        parser.add_argument(
            "--check-user",
            type=str,
            default=None,
            help="Email или логин ящика для проверки наличия на сервере Reg.ru",
        )
        parser.add_argument(
            "--delete-user",
            type=str,
            default=None,
            help="Email ящика для удаления на сервере Reg.ru",
        )
        parser.add_argument(
            "--inspect-form",
            action="store_true",
            help="Запросить и вывести подробную структуру формы email.edit (поля и их свойства)",
        )
        parser.add_argument(
            "--all-mailboxes",
            action="store_true",
            help="Вывести полный список всех почтовых ящиков домена (по умолчанию первые 25)",
        )
        parser.add_argument(
            "--raw",
            action="store_true",
            help="Выводить сырые JSON-ответы от API ISPmanager",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Основная точка входа выполнения команды."""
        domain: str = str(options.get("domain") or "barkol.ru").strip()
        custom_url: Optional[str] = options.get("url")
        custom_user: Optional[str] = options.get("user")
        custom_isp_password: Optional[str] = options.get("isp_password")
        create_user: Optional[str] = options.get("create_user")
        password_arg: Optional[str] = options.get("password")
        full_name_arg: str = str(options.get("full_name") or "").strip()
        quota_arg: Optional[int] = options.get("quota")
        change_password_user: Optional[str] = options.get("change_password")
        check_user_arg: Optional[str] = options.get("check_user")
        delete_user_arg: Optional[str] = options.get("delete_user")
        inspect_form_flag: bool = bool(options.get("inspect_form"))
        all_mailboxes_flag: bool = bool(options.get("all_mailboxes"))
        raw_flag: bool = bool(options.get("raw"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n========================================================"))
        self.stdout.write(self.style.MIGRATE_HEADING("  ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К ISPMANAGER API (REG.RU)"))
        self.stdout.write(self.style.MIGRATE_HEADING("========================================================\n"))

        # 1. Чтение конфигурации
        panel_url = custom_url or get_django_setting("ISPMANAGER_API_URL", "https://mail.barkol.ru:1500/ispmgr")
        api_user = custom_user or get_django_setting("ISPMANAGER_API_USER", "") or get_django_setting("ISPMANAGER_USER", "")
        api_password = (
            custom_isp_password
            or get_django_setting("ISPMANAGER_API_PASSWORD", "")
            or get_django_setting("ISPMANAGER_PASSWORD", "")
        )
        verify_ssl = bool(get_django_setting("ISPMANAGER_API_VERIFY_SSL", False))
        timeout = int(get_django_setting("ISPMANAGER_API_TIMEOUT", 10) or 10)

        masked_pass = f"{api_password[:2]}***{api_password[-2:]}" if len(api_password) > 4 else ("***" if api_password else "НЕ ЗАДАН")

        self.stdout.write(self.style.WARNING("1. Текущая конфигурация ISPmanager:"))
        self.stdout.write(f"   - URL панели (ISPMANAGER_API_URL): {panel_url}")
        self.stdout.write(f"   - Пользователь (ISPMANAGER_API_USER): {api_user or 'НЕ ЗАДАН'}")
        self.stdout.write(f"   - Пароль (ISPMANAGER_API_PASSWORD): {masked_pass}")
        self.stdout.write(f"   - Проверка SSL (ISPMANAGER_API_VERIFY_SSL): {verify_ssl}")
        self.stdout.write(f"   - Таймаут (ISPMANAGER_API_TIMEOUT): {timeout} сек.")
        self.stdout.write(f"   - Целевой домен: {domain}\n")

        if not api_user or not api_password:
            self.stdout.write(
                self.style.ERROR(
                    " ОШИБКА: Параметры ISPMANAGER_API_USER и/или ISPMANAGER_API_PASSWORD не указаны!\n"
                    " Укажите их в .env или передайте через флаги --user <user> --isp-password <pass>."
                )
            )
            return

        provider = ISPmanagerExternalMailProvider(
            panel_url=str(panel_url),
            api_username=str(api_user),
            api_password=str(api_password),
            verify_ssl=verify_ssl,
            timeout=timeout,
        )

        # 2. Проверка соединения и авторизации
        self.stdout.write(self.style.WARNING("2. Проверка сетевого соединения и авторизации:"))
        conn_res = provider.test_connection()
        if conn_res.get("success"):
            self.stdout.write(self.style.SUCCESS(f"    Авторизация в ISPmanager успешна! ({conn_res.get('message')})"))
            if raw_flag:
                self.stdout.write(f"   Сырой ответ: {json.dumps(conn_res.get('details', {}), ensure_ascii=False, indent=2)}")
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"    Не удалось подключиться к ISPmanager!\n"
                    f"   Сообщение: {conn_res.get('message')}\n"
                    f"   Ошибка: {conn_res.get('error')}"
                )
            )
            if raw_flag and "details" in conn_res:
                self.stdout.write(f"   Сырой ответ: {conn_res.get('details')}")
            self.stdout.write(
                self.style.NOTICE(
                    "\nПодсказка: Убедитесь, что IP адрес сервера разрешен в панели ISPmanager и порт 1500 доступен."
                )
            )

        # 3. Инспекция метаданных формы email.edit
        self.stdout.write(self.style.WARNING("\n3. Инспекция структуры формы `email.edit` (ISPmanager API):"))
        form_meta = provider.get_form_metadata("email.edit")
        if form_meta.get("success"):
            data = form_meta.get("data", {})
            doc = data.get("doc", {}) if isinstance(data, dict) else {}
            self.stdout.write(self.style.SUCCESS("    Метаданные формы `email.edit` получены успешно."))
            if raw_flag or inspect_form_flag:
                self.stdout.write(f"   Полная структура формы:\n{json.dumps(doc, ensure_ascii=False, indent=2)}")
            else:
                # Краткий вывод обнаруженных полей
                fields_found: List[str] = []
                for k, v in doc.items():
                    if k not in ("$", "tlist", "metadata", "lang"):
                        fields_found.append(k)
                if fields_found:
                    self.stdout.write(f"   Обнаруженные элементы/поля: {', '.join(fields_found)}")
        else:
            self.stdout.write(
                self.style.ERROR(f"    Не удалось получить структуру формы: {form_meta.get('error')}")
            )

        # 4. Список доменов и ящиков
        self.stdout.write(self.style.WARNING(f"\n4. Почтовые ящики на домене '{domain}':"))
        mailboxes = provider.get_mailboxes(domain=domain)
        if mailboxes:
            total_count = len(mailboxes)
            display_boxes = mailboxes if all_mailboxes_flag else mailboxes[:25]
            self.stdout.write(self.style.SUCCESS(f"    Всего найдено почтовых ящиков: {total_count}"))
            for idx, mb in enumerate(display_boxes, 1):
                mb_email = mb.get("email")
                mb_quota = mb.get("quota") or "не ограничено"
                mb_used = mb.get("used") or "0"
                mb_note = mb.get("note") or ""
                note_str = f" [{mb_note}]" if mb_note else ""
                self.stdout.write(f"   {idx:2d}. {mb_email:<35} | Занято: {mb_used} / Квота: {mb_quota}{note_str}")
            if not all_mailboxes_flag and total_count > 25:
                self.stdout.write(
                    self.style.NOTICE(
                        f"   ... (показаны первые 25 из {total_count} ящиков. Для полного списка используйте флаг --all-mailboxes)"
                    )
                )
        else:
            self.stdout.write(self.style.NOTICE(f"    Ящики на домене '{domain}' не найдены или список пуст."))

        # 5. Проверка существования конкретного ящика
        if check_user_arg:
            target_check = f"{check_user_arg}@{domain}" if "@" not in check_user_arg else check_user_arg
            self.stdout.write(self.style.WARNING(f"\n5. Проверка существования ящика '{target_check}':"))
            exists = provider.check_mailbox_exists(target_check)
            if exists:
                self.stdout.write(self.style.SUCCESS(f"    Ящик '{target_check}' НАЙДЕН на сервере Reg.ru."))
            else:
                self.stdout.write(self.style.ERROR(f"    Ящик '{target_check}' НЕ НАЙДЕН на сервере Reg.ru."))

        # 6. Создание ящика (если передан флаг --create-user)
        if create_user:
            target_create = f"{create_user}@{domain}" if "@" not in create_user else create_user
            create_pwd = password_arg or "TempSecret123!"
            self.stdout.write(self.style.WARNING(f"\n6. Тестовое создание ящика '{target_create}':"))
            self.stdout.write(f"   - Пароль: {create_pwd[:2]}***")
            self.stdout.write(f"   - ФИО / Примечание: {full_name_arg or 'Без примечания'}")
            self.stdout.write(f"   - Квота: {quota_arg or 'По умолчанию'} МБ")

            create_res = provider.create_mailbox(
                email=target_create,
                password=create_pwd,
                full_name=full_name_arg,
                quota_mb=quota_arg,
            )

            if create_res.get("success"):
                self.stdout.write(self.style.SUCCESS(f"    УСПЕХ: {create_res.get('message')}"))
                if raw_flag:
                    self.stdout.write(f"   Ответ: {json.dumps(create_res, ensure_ascii=False, indent=2)}")
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"    ОШИБКА создания ящика: {create_res.get('error')}\n"
                        f"   Детали: {create_res}"
                    )
                )

        # 7. Изменение пароля (если передан флаг --change-password)
        if change_password_user:
            target_change = (
                f"{change_password_user}@{domain}"
                if "@" not in change_password_user
                else change_password_user
            )
            if not password_arg:
                self.stdout.write(
                    self.style.ERROR("\n7. Ошибка: Для смены пароля необходимо указать --password <новый_пароль>!")
                )
            else:
                self.stdout.write(self.style.WARNING(f"\n7. Смена пароля для ящика '{target_change}':"))
                pwd_res = provider.change_password(email=target_change, new_password=password_arg)
                if pwd_res:
                    self.stdout.write(self.style.SUCCESS(f"    Пароль для ящика '{target_change}' успешно изменен!"))
                else:
                    self.stdout.write(self.style.ERROR(f"    Не удалось изменить пароль для ящика '{target_change}'."))

        # 8. Удаление ящика (если передан флаг --delete-user)
        if delete_user_arg:
            target_del = f"{delete_user_arg}@{domain}" if "@" not in delete_user_arg else delete_user_arg
            self.stdout.write(self.style.WARNING(f"\n8. Удаление ящика '{target_del}':"))
            del_res = provider.delete_mailbox(email=target_del)
            if del_res:
                self.stdout.write(self.style.SUCCESS(f"    Ящик '{target_del}' успешно удален в ISPmanager."))
            else:
                self.stdout.write(self.style.ERROR(f"    Не удалось удалить ящик '{target_del}'."))

        self.stdout.write(self.style.MIGRATE_HEADING("\n========================================================"))
        self.stdout.write(self.style.MIGRATE_HEADING("  ДИАГНОСТИКА ЗАВЕРШЕНА"))
        self.stdout.write(self.style.MIGRATE_HEADING("========================================================\n"))
