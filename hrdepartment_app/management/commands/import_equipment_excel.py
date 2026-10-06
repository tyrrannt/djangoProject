"""Команда Django для импорта оборудования, средств измерений и КПА из Excel (.xlsx / .xlsm).

Использование:
    # 1. Тестовый прогон (симуляция без записи в базу данных):
    python3 manage.py import_equipment_excel --dry-run

    # 2. Реальный импорт всего метрологического графика:
    python3 manage.py import_equipment_excel

    # 3. Импорт с указанием другого файла или листа:
    python3 manage.py import_equipment_excel --file /path/to/file.xlsm --sheet "Все СИ и Инструмент"
"""

import os
from django.core.management.base import BaseCommand
from hrdepartment_app.services.equipment_import import EquipmentExcelImportService


class Command(BaseCommand):
    """Консольная команда импорта метрологического графика и оборудования ТО ВС (ФАП-145)."""

    help = "Импортирует оборудование, КПА и средства измерений из Excel (.xlsx/.xlsm) в 3-уровневый каталог"

    def add_arguments(self, parser):
        """Регистрация параметров командной строки."""
        parser.add_argument(
            "--file",
            type=str,
            default="/home/agy/djangoProject/Метрологический график 2.xlsm",
            help="Путь к файлу Excel (по умолчанию: /home/agy/djangoProject/Метрологический график 2.xlsm)",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default="Все СИ и Инструмент",
            help="Имя листа для импорта (по умолчанию: 'Все СИ и Инструмент')",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции: валидирует и показывает отчет без фиксации изменений в базе данных",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Ограничение количества обрабатываемых строк (для тестирования)",
        )

    def handle(self, *args, **options) -> None:
        """Основной обработчик команды импорта."""
        file_path = options["file"]
        sheet_name = options["sheet"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"Файл не найден по пути: '{file_path}'"))
            return

        mode_str = "РЕЖИМ СИМУЛЯЦИИ (DRY-RUN)" if dry_run else "БОЕВОЙ РЕЖИМ (ЗАПИСЬ В БД)"
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))
        self.stdout.write(self.style.MIGRATE_HEADING(f"СТАРТ ИМПОРТА ОБОРУДОВАНИЯ И СИ ТО (ФАП-145)"))
        self.stdout.write(self.style.MIGRATE_LABEL(f"Файл:  {file_path}"))
        self.stdout.write(self.style.MIGRATE_LABEL(f"Лист:  {sheet_name}"))
        self.stdout.write(self.style.WARNING(f"Режим: {mode_str}"))
        if limit:
            self.stdout.write(self.style.WARNING(f"Лимит: {limit} строк"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))

        service = EquipmentExcelImportService()
        report = service.import_from_excel(
            file_path_or_obj=file_path,
            sheet_name=sheet_name,
            dry_run=dry_run,
            limit=limit,
        )

        if not report.success and report.errors:
            self.stderr.write(self.style.ERROR("\nИмпорт завершился с ошибками:"))
            for err in report.errors:
                self.stderr.write(self.style.ERROR(f"  • {err}"))
            return

        # Итоговая сводка
        self.stdout.write("\n" + self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("ИТОГОВЫЙ ОТЧЕТ ИМПОРТА ОБОРУДОВАНИЯ:"))
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(f"• Всего строк прочитано:           {report.total_rows_read}")
        self.stdout.write(self.style.SUCCESS(f"• Создано единиц оборудования:     {report.created_equipment_count}"))
        self.stdout.write(self.style.WARNING(f"• Обновлено единиц оборудования:    {report.updated_equipment_count}"))
        self.stdout.write(f"• Пропущено пустых строк:          {report.skipped_count}")
        self.stdout.write(f"• Новых наименований (Уровень 1):  {report.names_created}")
        self.stdout.write(f"• Новых типов/моделей (Уровень 2): {report.types_created}")
        self.stdout.write(f"• Новых точек МПД (базирования):   {report.places_created}")
        self.stdout.write(f"• Записей в журнале поверок:       {report.verifications_recorded}")

        if report.warnings:
            self.stdout.write("\n" + self.style.WARNING("ПРЕДУПРЕЖДЕНИЯ:"))
            for warn in report.warnings[:20]:
                self.stdout.write(self.style.WARNING(f"  ⚠ {warn}"))

        if dry_run:
            self.stdout.write(
                "\n" + self.style.NOTICE(
                    "Внимание: Выполнен предварительный тест (--dry-run). База данных НЕ изменена.\n"
                    "Для реального сохранения запустите команду без флага --dry-run."
                )
            )
        else:
            self.stdout.write(
                "\n" + self.style.SUCCESS("Все данные успешно записаны и согласованы в базе данных!")
            )
