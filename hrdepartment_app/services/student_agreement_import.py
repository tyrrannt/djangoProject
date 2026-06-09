import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, NamedTuple
from django.db import transaction
from django.core.exceptions import ValidationError
import openpyxl

from customers_app.models import Counteragent, DataBaseUser
from contracts_app.models import Contract, TypeContract, TypeDocuments
from hrdepartment_app.models import StudentAgreement, TrainingProgram, EducationFormChoices, TrainingUnit


class ImportRowResult(NamedTuple):
    """
    Результат обработки одной строки из Excel.
    """
    row_number: int
    success: bool
    agreement_number: str | None
    employee_name: str | None
    status: str
    message: str | None


class StudentAgreementImportService:
    """
    Сервис для импорта ученических договоров из Excel.
    
    Содержит бизнес-логику чтения файла, валидации полей, поиска связанных
    объектов в базе данных (сотрудники, АУЦ, программы обучения, договоры),
    защиты от дубликатов и формирования отчета об импорте.
    """

    def clean_string(self, value: Any) -> str | None:
        """
        Очищает строковое значение от пробелов и спецсимволов.

        Args:
            value: Входное значение из ячейки Excel.

        Returns:
            Очищенная строка или None, если значение пустое.
        """
        if value is None:
            return None
        cleaned = str(value).strip().replace('\xa0', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned if cleaned else None

    def clean_agreement_number(self, value: Any) -> str | None:
        """
        Очищает номер договора от служебных символов.
        """
        value = self.clean_string(value)

        if not value:
            return None

        value = value.replace('№', '')
        value = re.sub(r'\s+', ' ', value)

        return value.strip()

    def parse_date(self, value: Any) -> datetime.date | None:
        """
        Преобразует значение ячейки Excel в дату.

        Args:
            value: Значение даты из Excel (datetime, date, str или None).

        Returns:
            Объект datetime.date или None.
        """
        if not value:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        
        # Если дата представлена строкой
        cleaned = self.clean_string(value)
        if not cleaned:
            return None
        
        # Попытка распарсить различные форматы дат
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
        return None

    def parse_decimal(self, value: Any) -> Decimal | None:
        """
        Преобразует значение в Decimal.

        Args:
            value: Числовое или строковое значение.

        Returns:
            Объект Decimal или None.
        """
        if value is None:
            return None
        cleaned = self.clean_string(value)
        if not cleaned:
            return None
        # Убираем пробелы и заменяем запятую на точку
        cleaned = cleaned.replace(' ', '').replace(',', '.')
        try:
            return Decimal(cleaned)
        except (ValueError, InvalidOperation):
            return None

    def parse_int(self, value: Any) -> int | None:
        """
        Преобразует значение в целое число.

        Args:
            value: Числовое или строковое значение.

        Returns:
            Целое число или None.
        """
        if value is None:
            return None
        cleaned = self.clean_string(value)
        if not cleaned:
            return None
        cleaned = cleaned.replace(' ', '')
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def import_from_excel(self, file_path: str) -> dict[str, Any]:
        """
        Импортирует данные из Excel-файла.

        Args:
            file_path: Абсолютный путь к файлу Excel.

        Returns:
            Словарь с результатами импорта и детализацией по каждой строке.
        """
        results: list[ImportRowResult] = []
        
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
        except Exception as e:
            return {
                "success": False,
                "error": f"Не удалось открыть файл Excel: {str(e)}",
                "total_rows": 0,
                "success_count": 0,
                "duplicate_count": 0,
                "failed_count": 0,
                "details": []
            }

        total_rows = 0
        success_count = 0
        duplicate_count = 0
        failed_count = 0

        # Получаем дефолтные типы для договоров
        try:
            default_type_doc = TypeDocuments.objects.get(pk=1)  # Договор
            default_type_contract = TypeContract.objects.get(pk=1)  # Обучение
        except (TypeDocuments.DoesNotExist, TypeContract.DoesNotExist):
            default_type_doc = TypeDocuments.objects.first()
            default_type_contract = TypeContract.objects.first()

        # Данные начинаются со строки 4
        for row_idx, row in enumerate(sheet.iter_rows(min_row=4, values_only=True), start=4):
            # Проверяем, пустая ли строка
            if not any(row):
                continue

            total_rows += 1

            # Разбираем столбцы по индексам
            raw_agreement_num = row[0]
            raw_agreement_date = row[1]
            raw_auc_name = row[2]
            raw_program_name = row[3]
            raw_unit_name = row[4]
            raw_contract_num = row[5]
            raw_contract_date = row[6]
            raw_place = row[7]
            raw_fio = row[8]
            raw_start_date = row[9]
            raw_end_date = row[10]
            raw_cost = row[11]
            raw_work_period = row[12]
            raw_note = row[13]
            if raw_unit_name:
                print(raw_unit_name)
            clean_unit_name = self.clean_string(raw_unit_name)
            if clean_unit_name:
                print(clean_unit_name)
            # Очистка и приведение типов
            agreement_num = self.clean_string(self.clean_agreement_number(raw_agreement_num))
            agreement_date = self.parse_date(raw_agreement_date)
            auc_name = self.clean_string(raw_auc_name)
            program_name = self.clean_string(raw_program_name)
            unit_name = [
                item.strip()
                for item in clean_unit_name.split(',')
                if item.strip()
            ] if clean_unit_name else []
            contract_num = self.clean_string(self.clean_agreement_number(raw_contract_num))
            contract_date = self.parse_date(raw_contract_date)
            place = self.clean_string(raw_place) or "Не указано"
            fio = self.clean_string(raw_fio)
            start_date = self.parse_date(raw_start_date)
            end_date = self.parse_date(raw_end_date)
            cost = self.parse_decimal(raw_cost)
            work_period = self.parse_int(raw_work_period)
            note = self.clean_string(raw_note) or ""

            # Валидация обязательных полей для модели StudentAgreement
            validation_errors = []
            if not agreement_num:
                agreement_num='БН'
            if not agreement_date:
                agreement_date=datetime.date(2000,1,1)
            if not fio:
                validation_errors.append("Отсутствует Ф.И.О. сотрудника")
            if not auc_name:
                validation_errors.append("Отсутствует наименование АУЦ")
            if not program_name:
                validation_errors.append("Отсутствует программа обучения")
            if not start_date:
                validation_errors.append("Отсутствует дата начала обучения")
            if not end_date:
                validation_errors.append("Отсутствует дата окончания обучения")
            if cost is None:
                cost=0
            if work_period is None:
                work_period=0

            if validation_errors:
                failed_count += 1
                results.append(ImportRowResult(
                    row_number=row_idx,
                    success=False,
                    agreement_number=agreement_num,
                    employee_name=fio,
                    status="Ошибка валидации",
                    message="; ".join(validation_errors)
                ))
                continue

            # Ищем сотрудника (DataBaseUser) по ФИО (поле title)
            employee = DataBaseUser.objects.filter(title__iexact=fio).first()
            if not employee:
                failed_count += 1
                results.append(ImportRowResult(
                    row_number=row_idx,
                    success=False,
                    agreement_number=agreement_num,
                    employee_name=fio,
                    status="Пользователь не найден",
                    message=f"Сотрудник '{fio}' не найден в базе данных"
                ))
                continue

            # Защита от дублирования ученического договора
            duplicate_exists = StudentAgreement.objects.filter(
                student_agreement_number=agreement_num,
                student_agreement_date=agreement_date,
                full_name__title=fio,
                training_center_name__short_name=auc_name
            ).exists()
            if duplicate_exists:
                duplicate_count += 1
                results.append(ImportRowResult(
                    row_number=row_idx,
                    success=False,
                    agreement_number=agreement_num,
                    employee_name=fio,
                    status="Дубликат",
                    message=f"Ученический договор № {agreement_num} от {agreement_date.strftime('%d.%m.%Y')} уже существует"
                ))
                continue

            # Начинаем транзакцию для импорта текущей строки
            try:
                with transaction.atomic():
                    # 1. Поиск или создание АУЦ (Counteragent)
                    counteragent = Counteragent.objects.filter(
                        short_name__iexact=auc_name
                    ).first()
                    
                    if not counteragent:
                        counteragent = Counteragent.objects.filter(
                            full_name__iexact=auc_name
                        ).first()

                    if counteragent:
                        # Если нашли контрагента, но у него не выставлен флаг образовательной организации, обновляем
                        if not counteragent.educational_organization:
                            counteragent.educational_organization = True
                            counteragent.save(update_fields=['educational_organization'])
                    else:
                        # Создаем нового контрагента
                        counteragent = Counteragent.objects.create(
                            short_name=auc_name,
                            full_name=auc_name,
                            educational_organization=True,
                            type_counteragent='juridical_person'
                        )

                    # 2. Поиск или создание программы обучения (TrainingProgram)
                    program = TrainingProgram.objects.filter(
                        program_name__iexact=program_name,
                        counteragent_name=counteragent
                    ).first()
                    
                    if not program:
                        program = TrainingProgram.objects.create(
                            program_name=program_name,
                            counteragent_name=counteragent
                        )

                    units = []

                    if unit_name:
                        for item in unit_name:
                            item = item.strip()

                            parts = [part.strip() for part in item.split('$')]

                            unit_name_short = parts[0]

                            unit_name_full = parts[1].strip() if len(parts) > 1 else ''
                            print(f"общее - {item} краткое - {unit_name_short} полное - {unit_name_full}")
                            unit, _ = TrainingUnit.objects.get_or_create(
                                unit_name_short=unit_name_short,
                                program_units=program,
                                defaults={
                                    'unit_name': unit_name_full
                                }
                            )

                            units.append(unit)

                    # 3. Поиск или создание основного договора (Contract), если указан номер
                    contract = None
                    if contract_num:
                        contract_qs = Contract.objects.filter(
                            contract_number=contract_num
                        )
                        if contract_date:
                            contract_qs = contract_qs.filter(date_conclusion=contract_date)
                        if counteragent:
                            contract_qs = contract_qs.filter(contract_counteragent=counteragent)
                        
                        contract = contract_qs.first()
                        
                        if not contract:
                            contract = None

                    # 4. Создание ученического договора (StudentAgreement)
                    agreement = StudentAgreement.objects.create(
                        student_agreement_number=agreement_num,
                        student_agreement_date=agreement_date,
                        counteragent_contract=contract,
                        training_center_name=counteragent,
                        training_program=program,
                        training_place=place,
                        form_education=EducationFormChoices.FULL_TIME,
                        remotely=True,
                        academic_hours=0,
                        full_name=employee,
                        training_start_date=start_date,
                        training_end_date=end_date,
                        training_cost=cost,
                        work_period_years=work_period,
                        note=note,
                        signed=True
                    )
                    if units:
                        agreement.training_unit.set(units)

                success_count += 1
                results.append(ImportRowResult(
                    row_number=row_idx,
                    success=True,
                    agreement_number=agreement_num,
                    employee_name=fio,
                    status="Успешно",
                    message="Запись успешно загружена"
                ))

            except Exception as e:
                failed_count += 1
                results.append(ImportRowResult(
                    row_number=row_idx,
                    success=False,
                    agreement_number=agreement_num,
                    employee_name=fio,
                    status="Ошибка БД",
                    message=f"Ошибка при сохранении в базу данных: {str(e)}"
                ))

        return {
            "success": True,
            "total_rows": total_rows,
            "success_count": success_count,
            "duplicate_count": duplicate_count,
            "failed_count": failed_count,
            "details": results
        }
