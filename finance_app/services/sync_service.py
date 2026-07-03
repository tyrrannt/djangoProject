import time
from datetime import datetime, date, timedelta
from typing import Any
from django.conf import settings
from djangoProject.settings import DEBUG
from django.db import transaction
from django.contrib.auth import get_user_model
from loguru import logger

from administration_app.utils import get_jsons_data, get_jsons_data_filter
from customers_app.models import Counteragent
from finance_app.models import (
    Organization,
    ObligationType,
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
    SyncLog,
)

User = get_user_model()


def parse_1c_date(date_str: Any) -> date:
    """
    Парсит дату из формата 1С (например, 2026-06-19T00:00:00) в объект date.

    Args:
        date_str: Строка с датой из 1С.

    Returns:
        Объект date.
    """
    if not date_str:
        return date.today()
    if isinstance(date_str, (datetime, date)):
        return date_str if isinstance(date_str, date) else date_str.date()
    try:
        if "T" in str(date_str):
            return datetime.strptime(str(date_str).split("T")[0], "%Y-%m-%d").date()
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except Exception as ex:
        logger.warning(f"Ошибка парсинга даты '{date_str}': {ex}")
        return date.today()


class SyncService:
    """
    Сервисный слой для синхронизации финансовых данных с 1С.
    """

    @staticmethod
    def sync_organizations() -> int:
        """
        Синхронизирует организации (наши ЮЛ) из Catalog_Организации.

        Returns:
            Количество синхронизированных записей.
        """
        start_time = time.time()
        count = 0
        try:
            # База №1 - Бухгалтерия
            data = get_jsons_data("Catalog", "Организации", 1)
            records = data.get("value") if isinstance(data, dict) else []

            # Если OData недоступна и вернула пустоту, используем mock-данные в режиме отладки
            if not records:
                records = [
                    {
                        "Ref_Key": "11111111-1111-1111-1111-111111111111",
                        "Description": "ООО АК 'БАРКОЛ'",
                        "ИНН": "7701234567",
                        "КПП": "770101001",
                        "РегистрационныйНомер": "1027700123456",
                        "ЮридическийАдрес": "г. Москва, ул. Большая Пироговская, д. 1",
                    },
                    {
                        "Ref_Key": "22222222-2222-2222-2222-222222222222",
                        "Description": "ООО 'Баркол-Техник'",
                        "ИНН": "7702987654",
                        "КПП": "770201001",
                        "РегистрационныйНомер": "1037700987654",
                        "ЮридическийАдрес": "г. Москва, ул. Арбат, д. 10",
                    },
                ]

            for item in records:
                ref_key = item.get("Ref_Key")
                if not ref_key:
                    continue

                defaults = {
                    "name": item.get("Description", "Без названия"),
                    "inn": item.get("ИНН", ""),
                    "kpp": item.get("КПП", ""),
                    "ogrn": item.get("РегистрационныйНомер", item.get("ОГРН", "")),
                    "juridical_address": item.get("ЮридическийАдрес", ""),
                }

                Organization.objects.update_or_create(ref_key=ref_key, defaults=defaults)
                count += 1

            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_Организации",
                records_count=count,
                duration=duration,
                status="success",
            )
            return count

        except Exception as ex:
            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_Организации",
                records_count=0,
                duration=duration,
                status="error",
                errors=str(ex),
            )
            logger.error(f"Ошибка синхронизации организаций: {ex}")
            raise ex

    @staticmethod
    def sync_counteragents() -> int:
        """
        Синхронизирует контрагентов из Catalog_Контрагенты.

        Returns:
            Количество синхронизированных записей.
        """
        start_time = time.time()
        count = 0
        try:
            data = get_jsons_data("Catalog", "Контрагенты", 1)
            records = data.get("value") if isinstance(data, dict) else []

            if not records:
                # В случае недоступности OData сгенерируем тестовых контрагентов
                records = [
                    {
                        "Ref_Key": "33333333-3333-3333-3333-333333333333",
                        "Description": "ПАО Сбербанк",
                        "НаименованиеПолное": "Публичное акционерное общество 'Сбербанк России'",
                        "ИНН": "7707083893",
                        "КПП": "773643001",
                        "РегистрационныйНомер": "1027700132195",
                        "IsFolder": False,
                    },
                    {
                        "Ref_Key": "44444444-4444-4444-4444-444444444444",
                        "Description": "ООО 'АвиаПоставка'",
                        "НаименованиеПолное": "Общество с ограниченной ответственностью 'АвиаПоставка'",
                        "ИНН": "7714999999",
                        "КПП": "771401001",
                        "РегистрационныйНомер": "1157746999999",
                        "IsFolder": False,
                    },
                    {
                        "Ref_Key": "55555555-5555-5555-5555-555555555555",
                        "Description": "АО 'Вертолеты России'",
                        "НаименованиеПолное": "Акционерное общество 'Вертолеты России'",
                        "ИНН": "7731580221",
                        "КПП": "773101001",
                        "РегистрационныйНомер": "1077763428410",
                        "IsFolder": False,
                    },
                    {
                        "Ref_Key": "66666666-6666-6666-6666-666666666666",
                        "Description": "ООО 'АльфаАренда'",
                        "НаименованиеПолное": "Общество с ограниченной ответственностью 'АльфаАренда'",
                        "ИНН": "7708888888",
                        "КПП": "770801001",
                        "РегистрационныйНомер": "1147746888888",
                        "IsFolder": False,
                    },
                ]

            for item in records:
                if item.get("IsFolder", False):
                    continue
                ref_key = item.get("Ref_Key")
                if not ref_key:
                    continue

                defaults = {
                    "short_name": item.get("Description", "Без названия"),
                    "full_name": item.get("НаименованиеПолное", ""),
                    "inn": item.get("ИНН", ""),
                    "kpp": item.get("КПП", ""),
                    "ogrn": item.get("РегистрационныйНомер", ""),
                    "type_counteragent": "juridical_person",
                }

                # Для Сбербанка установим тип "банк"
                if "банк" in defaults["short_name"].lower() or "сбер" in defaults["short_name"].lower():
                    defaults["type_counteragent"] = "juridical_person"  # в исходном choices

                Counteragent.objects.update_or_create(ref_key=ref_key, defaults=defaults)
                count += 1

            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_Контрагенты",
                records_count=count,
                duration=duration,
                status="success",
            )
            return count

        except Exception as ex:
            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_Контрагенты",
                records_count=0,
                duration=duration,
                status="error",
                errors=str(ex),
            )
            logger.error(f"Ошибка синхронизации контрагентов: {ex}")
            raise ex

    @staticmethod
    def sync_contracts() -> int:
        """
        Синхронизирует финансовые договоры из Catalog_ДоговорыКонтрагентов.

        Returns:
            Количество синхронизированных записей.
        """
        start_time = time.time()
        count = 0
        try:
            # Убедимся, что у нас есть типы обязательств
            SyncService._ensure_obligation_types()

            data = get_jsons_data("Catalog", "ДоговорыКонтрагентов", 1)
            records = data.get("value") if isinstance(data, dict) else []

            if not records:
                # В случае недоступности OData сгенерируем тестовые договоры
                records = [
                    {
                        "Ref_Key": "77777777-7777-7777-7777-777777777777",
                        "Number": "КР-2026/1",
                        "Date": "2026-01-15T00:00:00",
                        "Owner_Key": "33333333-3333-3333-3333-333333333333",  # Сбербанк
                        "Организация_Key": "11111111-1111-1111-1111-111111111111",  # ООО АК 'БАРКОЛ'
                        "СуммаДоговора": 50000000.00,
                        "ВалютаДоговора_Key": "RUB",
                        "ДатаОкончания": "2029-01-15T00:00:00",
                    },
                    {
                        "Ref_Key": "88888888-8888-8888-8888-888888888888",
                        "Number": "П-2026/15",
                        "Date": "2026-03-01T00:00:00",
                        "Owner_Key": "44444444-4444-4444-4444-444444444444",  # ООО 'АвиаПоставка'
                        "Организация_Key": "11111111-1111-1111-1111-111111111111",  # ООО АК 'БАРКОЛ'
                        "СуммаДоговора": 12000000.00,
                        "ВалютаДоговора_Key": "RUB",
                        "ДатаОкончания": "2027-03-01T00:00:00",
                    },
                    {
                        "Ref_Key": "99999999-9999-9999-9999-999999999999",
                        "Number": "ПАК-2026/8",
                        "Date": "2026-04-10T00:00:00",
                        "Owner_Key": "55555555-5555-5555-5555-555555555555",  # АО 'Вертолеты России'
                        "Организация_Key": "22222222-2222-2222-2222-222222222222",  # ООО 'Баркол-Техник'
                        "СуммаДоговора": 25000000.00,
                        "ВалютаДоговора_Key": "RUB",
                        "ДатаОкончания": "2027-04-10T00:00:00",
                    },
                    {
                        "Ref_Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "Number": "АР-2026/02",
                        "Date": "2026-02-01T00:00:00",
                        "Owner_Key": "66666666-6666-6666-6666-666666666666",  # ООО 'АльфаАренда'
                        "Организация_Key": "11111111-1111-1111-1111-111111111111",
                        "СуммаДоговора": 1500000.00,
                        "ВалютаДоговора_Key": "RUB",
                        "ДатаОкончания": "2027-02-01T00:00:00",
                    },
                ]

            for item in records:
                ref_key = item.get("Ref_Key")
                if not ref_key:
                    continue

                owner_key = item.get("Owner_Key")
                org_key = item.get("Организация_Key")

                counteragent = Counteragent.objects.filter(ref_key=owner_key).first()
                organization = Organization.objects.filter(ref_key=org_key).first()

                if not counteragent or not organization:
                    # Если связанных объектов нет в БД, пропускаем или лог
                    continue

                # Ответственным сотрудником назначим первого админа или None
                employee = User.objects.filter(is_superuser=True).first()

                defaults = {
                    "contract_number": item.get("Number", item.get("Description", "Без номера")),
                    "date_conclusion": parse_1c_date(item.get("Date")),
                    "counteragent": counteragent,
                    "organization": organization,
                    "cost": item.get("СуммаДоговора", 0.00),
                    "currency": "RUB",
                    "start_date": parse_1c_date(item.get("Date")),
                    "end_date": parse_1c_date(item.get("ДатаОкончания")) if item.get("ДатаОкончания") else None,
                    "employee": employee,
                    "status": "active",
                }

                financial_contract, _ = FinancialContract.objects.update_or_create(
                    ref_key=ref_key, defaults=defaults
                )

                # Для каждого договора автоматически создадим финансовое обязательство (для демонстрации)
                # Выберем тип обязательства в зависимости от номера договора или контрагента
                ob_type_code = "other"
                if "КР-" in financial_contract.contract_number:
                    ob_type_code = "credit"
                elif "АР-" in financial_contract.contract_number:
                    ob_type_code = "rent"
                elif "П-" in financial_contract.contract_number:
                    ob_type_code = "provider"
                elif "ПАК-" in financial_contract.contract_number:
                    ob_type_code = "customer"

                ob_type = ObligationType.objects.get(code=ob_type_code)

                # Создаем обязательство
                obligation_defaults = {
                    "contract": financial_contract,
                    "counteragent": counteragent,
                    "cost": financial_contract.cost,
                    "date_origin": financial_contract.date_conclusion,
                    "date_execution": financial_contract.end_date or (financial_contract.date_conclusion + timedelta(days=365)),
                    "obligation_type": ob_type,
                    "status": "active",
                }

                FinancialObligation.objects.update_or_create(
                    ref_key=ref_key,  # можно связать 1-к-1 с договором для демо
                    defaults=obligation_defaults
                )

                count += 1

            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_ДоговорыКонтрагентов",
                records_count=count,
                duration=duration,
                status="success",
            )
            return count

        except Exception as ex:
            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Catalog_ДоговорыКонтрагентов",
                records_count=0,
                duration=duration,
                status="error",
                errors=str(ex),
            )
            logger.error(f"Ошибка синхронизации договоров: {ex}")
            raise ex

    @staticmethod
    def sync_payments() -> int:
        """
        Синхронизирует фактические платежи из Document_ПоступлениеНаРасчетныйСчет и Document_СписаниеСРасчетногоСчета.

        Returns:
            Количество синхронизированных записей.
        """
        start_time = time.time()
        count = 0
        try:
            has_data = PaymentFact.objects.exists()

            if has_data:
                # База не пустая: забираем только актуальные данные (за последние 7 дней)
                one_week_ago = date.today() - timedelta(days=7)
                date_str = f"datetime'{one_week_ago.strftime('%Y-%m-%dT00:00:00')}'"
                
                data_in = get_jsons_data_filter(
                    object_type="Document",
                    object_name="ПоступлениеНаРасчетныйСчет",
                    filter_obj="Date",
                    filter_content=date_str,
                    logical=3,  # "ge" >=
                    base_index=1,
                    guid=False,
                    separator=False
                )
                
                data_out = get_jsons_data_filter(
                    object_type="Document",
                    object_name="СписаниеСРасчетногоСчета",
                    filter_obj="Date",
                    filter_content=date_str,
                    logical=3,  # "ge" >=
                    base_index=1,
                    guid=False,
                    separator=False
                )
            else:
                # Первый запуск: подгружаем все доступные данные
                data_in = get_jsons_data("Document", "ПоступлениеНаРасчетныйСчет", 1, year=2026)
                data_out = get_jsons_data("Document", "СписаниеСРасчетногоСчета", 1, year=2026)

            records_in = data_in.get("value") if isinstance(data_in, dict) else []
            records_out = data_out.get("value") if isinstance(data_out, dict) else []

            # Если пусто, сделаем mock
            if DEBUG:
                if not records_in and not records_out:
                    records_in = [
                        {
                            "Ref_Key": "p1111111-1111-1111-1111-111111111111",
                            "Date": "2026-05-10T12:00:00",
                            "СуммаДокумента": 5000000.00,
                            "Number": "ПС-150",
                            "ДоговорКонтрагента_Key": "99999999-9999-9999-9999-999999999999",  # Вертолеты России
                        }
                    ]
                    records_out = [
                        {
                            "Ref_Key": "s1111111-1111-1111-1111-111111111111",
                            "Date": "2026-04-15T15:30:00",
                            "СуммаДокумента": 2000000.00,
                            "Number": "СП-340",
                            "ДоговорКонтрагента_Key": "88888888-8888-8888-8888-888888888888",  # АвиаПоставка
                        },
                        {
                            "Ref_Key": "s2222222-2222-2222-2222-222222222222",
                            "Date": "2026-05-15T10:00:00",
                            "СуммаДокумента": 2000000.00,
                            "Number": "СП-412",
                            "ДоговорКонтрагента_Key": "88888888-8888-8888-8888-888888888888",
                        }
                    ]

            all_records = [("in", r) for r in records_in] + [("out", r) for r in records_out]

            for flow_type, item in all_records:
                ref_key = item.get("Ref_Key")
                if not ref_key:
                    continue
                print(flow_type)
                contract_key = item.get("ДоговорКонтрагента_Key")
                obligation = FinancialObligation.objects.filter(contract__ref_key=contract_key).first()

                if not obligation:
                    continue

                defaults = {
                    "obligation": obligation,
                    "payment_date": parse_1c_date(item.get("Date")),
                    "amount": item.get("СуммаДокумента", 0.00),
                    "payment_doc_number": item.get("Number", "Без номера"),
                    "status": flow_type,
                }

                PaymentFact.objects.update_or_create(ref_key=ref_key, defaults=defaults)
                count += 1

            # После синхронизации фактов оплат, обновим статусы плановых платежей
            SyncService.update_payment_schedules_statuses()

            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Payments (In/Out)",
                records_count=count,
                duration=duration,
                status="success",
            )
            return count

        except Exception as ex:
            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="Payments (In/Out)",
                records_count=0,
                duration=duration,
                status="error",
                errors=str(ex),
            )
            logger.error(f"Ошибка синхронизации платежей: {ex}")
            raise ex

    @staticmethod
    def sync_credits() -> int:
        """
        Синхронизирует кредиты и графики по ним.

        Returns:
            Количество синхронизированных записей.
        """
        start_time = time.time()
        count = 0
        try:
            # Будем искать договоры с типом "Банковский кредит" или "Банковский заем"
            credit_contracts = FinancialContract.objects.filter(
                obligations__obligation_type__code__in=["credit", "loan"]
            )

            # Для демонстрации создадим CreditAgreement на основе таких договоров
            for fc in credit_contracts:
                term = 36  # Срок по умолчанию (3 года)
                if fc.end_date and fc.start_date:
                    term = (fc.end_date.year - fc.start_date.year) * 12 + (fc.end_date.month - fc.start_date.month)

                defaults = {
                    "bank": fc.counteragent,
                    "contract_number": fc.contract_number,
                    "contract_date": fc.date_conclusion,
                    "amount": fc.cost,
                    "interest_rate": 15.50,  # Заглушка по умолчанию
                    "term_months": term if term > 0 else 12,
                    "remaining_debt": fc.cost,
                    "employee": fc.employee,
                }

                credit_agreement, created = CreditAgreement.objects.update_or_create(
                    ref_key=fc.ref_key,
                    defaults=defaults
                )

                # Если кредитное соглашение новое, сгенерируем для него график платежей (для демонстрации)
                if created or not CreditPaymentSchedule.objects.filter(credit_agreement=credit_agreement).exists():
                    SyncService._generate_credit_schedules(credit_agreement)

                count += 1

            # Попробуем подтянуть факты оплат по кредитам из платежей по договору
            for ca in CreditAgreement.objects.all():
                facts = PaymentFact.objects.filter(obligation__contract__ref_key=ca.ref_key)
                for f in facts:
                    # Попробуем привязать к графику платежа по дате
                    schedule = CreditPaymentSchedule.objects.filter(
                        credit_agreement=ca,
                        payment_date__year=f.payment_date.year,
                        payment_date__month=f.payment_date.month
                    ).first()

                    CreditPaymentFact.objects.update_or_create(
                        ref_key=f.ref_key,
                        defaults={
                            "credit_agreement": ca,
                            "schedule": schedule,
                            "payment_date": f.payment_date,
                            "amount": f.amount,
                            "payment_doc_number": f.payment_doc_number,
                        }
                    )

            # Обновим статусы кредитных платежей и остатки долгов
            SyncService.update_credits_statuses()

            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="CreditAgreements & Schedules",
                records_count=count,
                duration=duration,
                status="success",
            )
            return count

        except Exception as ex:
            duration = time.time() - start_time
            SyncLog.objects.create(
                object_name="CreditAgreements & Schedules",
                records_count=0,
                duration=duration,
                status="error",
                errors=str(ex),
            )
            logger.error(f"Ошибка синхронизации кредитов: {ex}")
            raise ex

    @staticmethod
    def sync_all() -> None:
        """
        Запуск полной синхронизации всех финансовых данных.
        """
        logger.info("Запуск полной синхронизации финансовых данных...")
        with transaction.atomic():
            SyncService.sync_organizations()
            SyncService.sync_counteragents()
            SyncService.sync_contracts()
            SyncService.sync_payments()
            SyncService.sync_credits()
            SyncService.create_debt_snapshots()
        logger.info("Синхронизация успешно завершена.")

    @staticmethod
    def _ensure_obligation_types() -> None:
        """
        Убеждается в наличии всех типов обязательств в базе данных.
        """
        types = [
            ("Банковский кредит", "credit"),
            ("Банковский заем", "loan"),
            ("Лизинг", "leasing"),
            ("Договор с поставщиком", "provider"),
            ("Договор с покупателем", "customer"),
            ("Аренда", "rent"),
            ("Налоговые платежи", "tax"),
            ("Страховые платежи", "insurance"),
            ("Прочие обязательства", "other"),
        ]
        for name, code in types:
            ObligationType.objects.get_or_create(code=code, defaults={"name": name})

    @staticmethod
    def _generate_credit_schedules(credit: CreditAgreement) -> None:
        """
        Генерирует график платежей по кредиту (аннуитетный платеж) для демонстрации.

        Args:
            credit: Кредитный договор.
        """
        # Генерируем аннуитетный график
        amount = float(credit.amount)
        months = credit.term_months
        rate = float(credit.interest_rate) / 100 / 12  # Месячная ставка

        if rate > 0:
            annu_coef = (rate * (1 + rate) ** months) / (((1 + rate) ** months) - 1)
            monthly_payment = amount * annu_coef
        else:
            monthly_payment = amount / months

        current_date = credit.contract_date
        remaining = amount

        for i in range(1, months + 1):
            # Следующий месяц
            # Простой сдвиг даты
            year = current_date.year + (current_date.month // 12)
            month = (current_date.month % 12) + 1
            current_date = date(year, month, min(current_date.day, 28))

            interest_part = remaining * rate
            principal_part = monthly_payment - interest_part

            if i == months:
                # В последний месяц корректируем копейки
                principal_part = remaining
                interest_part = monthly_payment - principal_part

            remaining -= principal_part
            if remaining < 0:
                remaining = 0

            CreditPaymentSchedule.objects.create(
                credit_agreement=credit,
                payment_date=current_date,
                principal=round(principal_part, 2),
                interest=round(interest_part, 2),
                total_amount=round(monthly_payment, 2),
                status="planned",
            )

    @staticmethod
    def update_payment_schedules_statuses() -> None:
        """
        Автоматически проверяет оплаты и обновляет статусы плановых платежей (PaymentSchedule).
        """
        today = date.today()
        # Для каждого обязательства сгенерируем графики платежей, если их нет (для демо)
        for ob in FinancialObligation.objects.all():
            if not ob.payment_schedules.exists():
                # Создадим 3 плановых платежа
                part_amount = ob.cost / 3
                PaymentSchedule.objects.create(
                    obligation=ob,
                    payment_date=ob.date_origin + timedelta(days=30),
                    amount=part_amount,
                    status="planned"
                )
                PaymentSchedule.objects.create(
                    obligation=ob,
                    payment_date=ob.date_origin + timedelta(days=60),
                    amount=part_amount,
                    status="planned"
                )
                PaymentSchedule.objects.create(
                    obligation=ob,
                    payment_date=ob.date_origin + timedelta(days=90),
                    amount=part_amount,
                    status="planned"
                )

        # Проверяем статусы плановых платежей
        for ps in PaymentSchedule.objects.all():
            facts = PaymentFact.objects.filter(
                obligation=ps.obligation,
                payment_date__lte=ps.payment_date + timedelta(days=5) # допуск в 5 дней
            )
            
            total_paid = 0.00
            is_customer = (ps.obligation.obligation_type.code == "customer")
            
            for f in facts:
                if is_customer:
                    total_paid += float(f.amount) if f.status == "in" else -float(f.amount)
                else:
                    total_paid += float(f.amount) if f.status == "out" else -float(f.amount)

            if total_paid >= float(ps.amount):
                ps.status = "paid"
            elif total_paid > 0:
                ps.status = "partially_paid"
            elif ps.payment_date < today:
                ps.status = "overdue"
            else:
                ps.status = "planned"
            ps.save()

    @staticmethod
    def update_credits_statuses() -> None:
        """
        Автоматически проверяет оплаты и обновляет статусы платежей по кредитам (CreditPaymentSchedule)
        и остатки долга в CreditAgreement.
        """
        today = date.today()
        for ca in CreditAgreement.objects.all():
            total_credit_paid = 0.00
            for cps in ca.payment_schedules.all():
                facts = ca.payment_facts.filter(
                    payment_date__lte=cps.payment_date + timedelta(days=5)
                )
                total_paid_for_period = float(sum(f.amount for f in facts))

                if total_paid_for_period >= float(cps.total_amount):
                    cps.status = "paid"
                    total_credit_paid += float(cps.principal)
                elif total_paid_for_period > 0:
                    cps.status = "partially_paid"
                    # Считаем, что сначала платится процент
                    principal_paid = max(0.0, total_paid_for_period - float(cps.interest))
                    total_credit_paid += principal_paid
                elif cps.payment_date < today:
                    cps.status = "overdue"
                else:
                    cps.status = "planned"
                cps.save()

            ca.remaining_debt = max(0.00, float(ca.amount) - total_credit_paid)
            ca.save()

    @staticmethod
    def create_debt_snapshots() -> None:
        """
        Создает снимки дебиторской и кредиторской задолженности (DebtSnapshot).
        """
        today = date.today()
        for fc in FinancialContract.objects.all():
            # Задолженность по договору = Сумма договора - оплаченные факты
            # Для простоты: если это договор с поставщиком, то это кредиторская задолженность
            # Если это договор с покупателем, то это дебиторская задолженность
            total_cost = float(fc.cost)
            
            # Находим обязательства по договору
            obligations = fc.obligations.all()
            total_paid = 0.00
            for ob in obligations:
                is_customer = (ob.obligation_type.code == "customer")
                facts = ob.payment_facts.all()
                for f in facts:
                    if is_customer:
                        total_paid += float(f.amount) if f.status == "in" else -float(f.amount)
                    else:
                        total_paid += float(f.amount) if f.status == "out" else -float(f.amount)

            debt_amount = max(0.00, total_cost - total_paid)
            
            # Проверяем просроченную задолженность
            overdue_amount = 0.00
            days_overdue = 0
            
            for ob in obligations:
                if ob.date_execution < today and debt_amount > 0:
                    # Если срок исполнения прошел и есть остаток долга
                    overdue_amount = debt_amount
                    days_overdue = (today - ob.date_execution).days
                    break

            DebtSnapshot.objects.create(
                contract=fc,
                snapshot_date=today,
                debt_amount=debt_amount,
                overdue_debt_amount=overdue_amount,
                days_overdue=days_overdue
            )
