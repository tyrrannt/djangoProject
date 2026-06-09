import os
from django.core.management.base import BaseCommand, CommandError
from hrdepartment_app.services.student_agreement_import import StudentAgreementImportService


class Command(BaseCommand):
    """
    Команда Django для импорта ученических договоров из файла Excel.

    Позволяет администратору системы загружать данные ученических договоров,
    избегая дублирования и предоставляя детальный отчет об успешных и неуспешных записях.
    """
    help = 'Импортирует ученические договоры из Excel-файла с защитой от дублирования и выводом ошибок'

    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--file',
            type=str,
            default='/home/proxmox/djangoProject/journal.xlsx',
            help='Абсолютный путь к Excel-файлу с записями (по умолчанию: /home/proxmox/djangoProject/journal.xlsx)'
        )

    def handle(self, *args, **options) -> None:
        """
        Основной метод выполнения команды.
        """
        file_path = options['file']

        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"Файл по пути '{file_path}' не найден."))
            return

        self.stdout.write(self.style.MIGRATE_LABEL(f"Начало импорта из файла: {file_path}"))
        
        service = StudentAgreementImportService()
        result = service.import_from_excel(file_path)

        if not result.get("success", True):
            self.stderr.write(self.style.ERROR(result.get("error", "Произошла неизвестная ошибка при импорте.")))
            return

        # Выводим отчет по каждой записи
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.MIGRATE_HEADING("ДЕТАЛЬНЫЙ ОТЧЕТ ПО ЗАПИСЯМ:"))
        self.stdout.write("="*80)

        for detail in result["details"]:
            agreement_str = f"Договор № {detail.agreement_number}" if detail.agreement_number else "Без договора"
            employee_str = f"Сотрудник: {detail.employee_name}" if detail.employee_name else "Сотрудник не указан"
            
            if detail.success:
                # Успешно загруженная запись
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[Строка {detail.row_number:02d}] УСПЕШНО | {agreement_str} | {employee_str}"
                    )
                )
            else:
                # Запись не загрузилась
                if detail.status == "Дубликат":
                    # Дубликат (пропущен)
                    self.stdout.write(
                        self.style.WARNING(
                            f"[Строка {detail.row_number:02d}] ДУБЛИКАТ | {agreement_str} | {employee_str} -> {detail.message}"
                        )
                    )
                else:
                    # Ошибка валидации, БД или отсутствие пользователя
                    self.stdout.write(
                        self.style.ERROR(
                            f"[Строка {detail.row_number:02d}] ПРОПУЩЕНО ({detail.status}) | {agreement_str} | {employee_str} -> {detail.message}"
                        )
                    )

        # Выводим общую статистику
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.MIGRATE_HEADING("ОБЩАЯ СТАТИСТИКА ИМПОРТА:"))
        self.stdout.write("="*80)
        self.stdout.write(f"Всего строк обработано: {result['total_rows']}")
        self.stdout.write(self.style.SUCCESS(f"Успешно загружено:      {result['success_count']}"))
        self.stdout.write(self.style.WARNING(f"Пропущено дубликатов:  {result['duplicate_count']}"))
        self.stdout.write(self.style.ERROR(f"Ошибок при импорте:     {result['failed_count']}"))
        self.stdout.write("="*80 + "\n")
