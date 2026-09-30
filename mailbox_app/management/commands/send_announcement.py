"""Команда массовой отправки корпоративного HTML-оповещения (анонса) сотрудникам компании."""

import os
import time
from typing import Any, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from customers_app.models import DataBaseUser
from mailbox_app.services.email_service import UniversalEmailService


class Command(BaseCommand):
    """Выполняет рассылку корпоративного информационного HTML-письма сотрудникам.

    Поддерживает отправку индивидуальным адресатам, списку получателей, а также
    всем активным пользователям портала с валидным корпоративным email.
    """

    help = "Отправка корпоративного HTML-оповещения (анонса) по шаблону"

    def add_arguments(self, parser: Any) -> None:
        """Регистрирует аргументы командной строки.

        Args:
            parser (Any): Парсер аргументов командной строки.
        """
        parser.add_argument(
            "--to",
            type=str,
            help="Email получателя или список через запятую (например: user@barkol.ru,admin@barkol.ru)",
        )
        parser.add_argument(
            "--all-active-users",
            action="store_true",
            help="Выполнить рассылку всем активным сотрудникам портала с заполненным email",
        )
        parser.add_argument(
            "--subject",
            type=str,
            default="Запуск Системы добровольных сообщений (СДС) // Авиакомпания БАРКОЛ",
            help="Тема письма",
        )
        parser.add_argument(
            "--template",
            type=str,
            default=os.path.join(settings.BASE_DIR, "tickets_announcement_email.html"),
            help="Путь к HTML-файлу шаблона (по умолчанию tickets_announcement_email.html в корне)",
        )
        parser.add_argument(
            "--from-email",
            type=str,
            default=None,
            help="Email адрес отправителя (по умолчанию EMAIL_HOST_USER)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Задержка между отправками в секундах для снижения пиковой нагрузки на SMTP (по умолчанию 0.1 сек)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Тестовый режим без фактической отправки писем",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа в команду рассылки оповещения.

        Args:
            *args (Any): Позиционные аргументы.
            **options (Any): Именованные аргументы CLI.

        Raises:
            CommandError: В случае отсутствия файла шаблона или незаданных получателей.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== РАССЫЛКА КОРПОРАТИВНОГО ОПОВЕЩЕНИЯ ==="))

        template_path = options["template"]
        if not os.path.exists(template_path):
            raise CommandError(f"Файл шаблона не найден по пути: {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html_content = f.read()
        except Exception as exc:
            raise CommandError(f"Ошибка при чтении файла шаблона: {exc}")

        subject: str = options["subject"]
        from_email: Optional[str] = options.get("from_email")
        dry_run: bool = options.get("dry_run", False)
        delay: float = options.get("delay", 0.1)

        recipients: List[str] = []

        if options.get("to"):
            raw_to = options["to"].split(",")
            for addr in raw_to:
                clean_addr = addr.strip()
                if clean_addr and "@" in clean_addr:
                    recipients.append(clean_addr)

        if options.get("all_active_users"):
            users_qs = (
                DataBaseUser.objects.filter(is_active=True)
                .exclude(email__isnull=True)
                .exclude(email__exact="")
                .values_list("email", flat=True)
            )
            for addr in users_qs:
                clean_addr = addr.strip().lower()
                if clean_addr and "@" in clean_addr and clean_addr not in recipients:
                    recipients.append(clean_addr)

        if not recipients:
            raise CommandError(
                "Не указан ни один получатель. Используйте флаг --to <email> или --all-active-users."
            )

        self.stdout.write(f"Тема письма: {self.style.WARNING(subject)}")
        self.stdout.write(f"Шаблон: {self.style.WARNING(template_path)} (размер: {len(html_content)} байт)")
        self.stdout.write(f"Всего получателей: {self.style.WARNING(str(len(recipients)))}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\n[DRY RUN] Режим имитации. Письма отправлены не будут."))
            self.stdout.write("Список получателей:")
            for idx, r in enumerate(recipients, 1):
                self.stdout.write(f"  {idx}. {r}")
            self.stdout.write(self.style.SUCCESS("Проверка завершена успешно.\n"))
            return

        self.stdout.write("\nЗапуск отправки...")
        success_count = 0
        failed_recipients: List[str] = []

        for idx, recipient in enumerate(recipients, 1):
            try:
                sent, failed = UniversalEmailService.send_email_sync(
                    subject=subject,
                    recipient_list=[recipient],
                    html_message=html_content,
                    from_email=from_email,
                    fail_silently=True,
                )
                if sent > 0:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"[{idx}/{len(recipients)}] Успешно отправлено: {recipient}")
                    )
                else:
                    failed_recipients.append(recipient)
                    self.stdout.write(
                        self.style.ERROR(f"[{idx}/{len(recipients)}] Не удалось отправить: {recipient}")
                    )
            except Exception as exc:
                failed_recipients.append(recipient)
                self.stdout.write(
                    self.style.ERROR(f"[{idx}/{len(recipients)}] Ошибка отправки на {recipient}: {exc}")
                )

            if delay > 0 and idx < len(recipients):
                time.sleep(delay)

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Итого отправлено: {success_count} из {len(recipients)}")
        )
        if failed_recipients:
            self.stdout.write(
                self.style.ERROR(f"Ошибок: {len(failed_recipients)} адресов: {', '.join(failed_recipients)}")
            )
        self.stdout.write("=" * 50 + "\n")
