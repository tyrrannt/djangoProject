import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import datetime

from hrdepartment_app.models import StudentAgreement
from customers_app.models import Counteragent, DataBaseUser
from hrdepartment_app.models import TrainingProgram, TrainingUnit


class Command(BaseCommand):
    help = "Импорт ученических договоров из Excel"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Путь к Excel файлу")

    @transaction.atomic
    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]

        df = pd.read_excel(file_path)

        df = df.fillna("")

        created_count = 0

        for _, row in df.iterrows():
            try:
                # --- Контрагент ---
                counteragent, _ = Counteragent.objects.get_or_create(
                    name=row["Наименование АУЦ"]
                )

                # --- Программа ---
                program = TrainingProgram.objects.get_or_create(
                    name=row["Программа обучения"]
                )

                # --- Сотрудник ---
                employee = DataBaseUser.objects.get(
                    full_name=row["Ф.И.О."]
                )

                # --- Создание договора ---
                agreement = StudentAgreement.objects.create(
                    student_agreement_number=row["№ Ученического договора с Работником"],
                    student_agreement_date=row["Дата Ученического договора"],
                    contract_number=row["№ Договора"],
                    contract_date=row["Дата договора"],
                    training_center_name=counteragent,
                    training_program=program,
                    training_place=row["Место оказания услуг"],
                    full_name=employee,
                    training_start_date=row["Дата начала"],
                    training_end_date=row["Дата окончания"],
                    training_cost=Decimal(str(row["Сумма обучения, руб."])),
                    work_period_years=int(row["Срок отработки (года)"]),
                    note=row.get("Примечание", "")
                )

                created_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Ошибка в строке {_}: {e}"
                ))
                raise  # откат всей транзакции

        self.stdout.write(self.style.SUCCESS(
            f"Импортировано договоров: {created_count}"
        ))
