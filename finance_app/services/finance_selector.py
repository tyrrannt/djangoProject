from datetime import date, timedelta
from typing import Any
from django.db.models import Sum, Q, QuerySet, Max
from django.contrib.auth import get_user_model
from finance_app.models import (
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
)

User = get_user_model()


class FinanceSelector:
    """
    Селектор для получения финансовых данных и аналитики с учетом прав доступа.
    """

    @staticmethod
    def get_user_role(user: User) -> str:
        """
        Определяет роль пользователя в финансовом блоке.

        Args:
            user: Пользователь системы.

        Returns:
            Строка с ролью: 'admin', 'finance', 'director', 'user'.
        """
        if user.is_superuser or user.is_staff:
            return "admin"
        if user.groups.filter(name="Финансовый отдел").exists():
            return "finance"
        if user.groups.filter(name="Руководитель").exists():
            return "director"
        return "user"

    @classmethod
    def apply_visibility_filter(
        cls, user: User, queryset: QuerySet, employee_field: str = "employee"
    ) -> QuerySet:
        """
        Применяет фильтр видимости объектов в зависимости от роли пользователя.

        Пользователь видит только свои договоры/обязательства,
        остальные роли видят все данные.

        Args:
            user: Пользователь системы.
            queryset: Исходный QuerySet.
            employee_field: Имя поля связи с ответственным сотрудником.

        Returns:
            Отфильтрованный QuerySet.
        """
        role = cls.get_user_role(user)
        if role == "user":
            filter_kwargs = {employee_field: user}
            return queryset.filter(**filter_kwargs)
        return queryset

    @classmethod
    def get_dashboard_data(cls, user: User, year: int | None = None, month: int | None = None) -> dict[str, Any]:
        """
        Формирует данные для финансового дашборда с учетом прав доступа пользователя.

        Args:
            user: Пользователь системы.
            year: Год для фильтрации данных.

        Returns:
            Словарь с показателями и таблицами для дашборда.
        """
        today = date.today()
        selected_year = year or today.year

        # Базовые QuerySet с учетом прав
        contracts = cls.apply_visibility_filter(user, FinancialContract.objects.all())
        credits_qs = cls.apply_visibility_filter(user, CreditAgreement.objects.all())

        # Обязательства по договорам, которые видит пользователь
        obligations = FinancialObligation.objects.filter(contract__in=contracts)
        
        # Применяем фильтр по году и месяцу возникновения обязательства для задолженностей
        debt_obligations = obligations.filter(date_origin__year=selected_year)
        debt_credits_qs = credits_qs.filter(contract_date__year=selected_year)
        if month:
            debt_obligations = debt_obligations.filter(date_origin__month=month)
            debt_credits_qs = debt_credits_qs.filter(contract_date__month=month)
        
        # 1. Общая сумма обязательств (активных) за период
        total_obligations_sum = debt_obligations.filter(status="active").aggregate(total=Sum("cost"))["total"] or 0.00
        total_credits_sum = debt_credits_qs.aggregate(total=Sum("amount"))["total"] or 0.00
        total_sum = float(total_obligations_sum) + float(total_credits_sum)

        # 2. Сумма кредиторской задолженности
        # Договоры с поставщиками и т.д. (все, кроме покупателей)
        creditor_obligations = debt_obligations.exclude(obligation_type__code="customer")
        creditor_debt = 0.00
        for ob in creditor_obligations:
            paid_out = PaymentFact.objects.filter(obligation=ob, status="out").aggregate(total=Sum("amount"))["total"] or 0.00
            refunded_in = PaymentFact.objects.filter(obligation=ob, status="in").aggregate(total=Sum("amount"))["total"] or 0.00
            paid = float(paid_out) - float(refunded_in)
            creditor_debt += max(0.00, float(ob.cost) - float(paid))

        # Кредиты также входят в кредиторские обязательства
        credits_debt = debt_credits_qs.aggregate(total=Sum("remaining_debt"))["total"] or 0.00
        creditor_total_debt = creditor_debt + float(credits_debt)

        # 3. Сумма дебиторской задолженности (договоры с покупателями)
        debtor_obligations = debt_obligations.filter(obligation_type__code="customer")
        debtor_total_debt = 0.00
        for ob in debtor_obligations:
            paid_in = PaymentFact.objects.filter(obligation=ob, status="in").aggregate(total=Sum("amount"))["total"] or 0.00
            refunded_out = PaymentFact.objects.filter(obligation=ob, status="out").aggregate(total=Sum("amount"))["total"] or 0.00
            paid = float(paid_in) - float(refunded_out)
            debtor_total_debt += max(0.00, float(ob.cost) - float(paid))

        # 4. Сумма просроченной задолженности
        # Из PaymentSchedule и CreditPaymentSchedule
        overdue_schedules = PaymentSchedule.objects.filter(
            obligation__in=obligations,
            status="overdue"
        ).aggregate(total=Sum("amount"))["total"] or 0.00
        
        overdue_credits = CreditPaymentSchedule.objects.filter(
            credit_agreement__in=credits_qs,
            status="overdue"
        ).aggregate(total=Sum("total_amount"))["total"] or 0.00
        
        overdue_total = float(overdue_schedules) + float(overdue_credits)

        # 5. Фактические платежи (списания) за год/месяц
        outflow_qs = PaymentFact.objects.filter(
            obligation__in=obligations,
            payment_date__year=selected_year,
            status="out"
        )
        if month:
            outflow_qs = outflow_qs.filter(payment_date__month=month)
        outflow_facts = outflow_qs.aggregate(total=Sum("amount"))["total"] or 0.00
        
        credit_outflow_qs = CreditPaymentFact.objects.filter(
            credit_agreement__in=credits_qs,
            payment_date__year=selected_year
        )
        if month:
            credit_outflow_qs = credit_outflow_qs.filter(payment_date__month=month)
        credit_outflow_facts = credit_outflow_qs.aggregate(total=Sum("amount"))["total"] or 0.00
        
        current_month_obligations = float(outflow_facts) + float(credit_outflow_facts)

        # 6. Фактические поступления за год/месяц
        inflow_qs = PaymentFact.objects.filter(
            obligation__in=obligations,
            payment_date__year=selected_year,
            status="in"
        )
        if month:
            inflow_qs = inflow_qs.filter(payment_date__month=month)
        inflow_facts = inflow_qs.aggregate(total=Sum("amount"))["total"] or 0.00
        
        current_month_inflow = float(inflow_facts)

        # --- ТАБЛИЦЫ ---

        # Ближайшие платежи (расходы)
        upcoming_payments_list = []
        # Обычные плановые платежи (запланированы или частично оплачены, дата >= сегодня)
        scheds_qs = PaymentSchedule.objects.filter(
            obligation__in=creditor_obligations,
            status__in=["planned", "partially_paid"],
            payment_date__year=selected_year
        )
        if month:
            scheds_qs = scheds_qs.filter(payment_date__month=month)
        else:
            scheds_qs = scheds_qs.filter(payment_date__gte=today if selected_year == today.year else date(selected_year, 1, 1))
            
        scheds = scheds_qs.select_related("obligation__contract__counteragent", "obligation__contract").order_by("payment_date")[:10]
        
        for s in scheds:
            upcoming_payments_list.append({
                "date": s.payment_date,
                "contract": s.obligation.contract.contract_number,
                "counteragent": s.obligation.contract.counteragent.short_name,
                "amount": s.amount,
                "days_to": (s.payment_date - today).days,
                "type": "Договор"
            })

        # Платежи по кредитам
        credit_scheds_qs = CreditPaymentSchedule.objects.filter(
            credit_agreement__in=credits_qs,
            status__in=["planned", "partially_paid"],
            payment_date__year=selected_year
        )
        if month:
            credit_scheds_qs = credit_scheds_qs.filter(payment_date__month=month)
        else:
            credit_scheds_qs = credit_scheds_qs.filter(payment_date__gte=today if selected_year == today.year else date(selected_year, 1, 1))
            
        credit_scheds = credit_scheds_qs.select_related("credit_agreement__bank").order_by("payment_date")[:10]

        for cs in credit_scheds:
            upcoming_payments_list.append({
                "date": cs.payment_date,
                "contract": cs.credit_agreement.contract_number,
                "counteragent": cs.credit_agreement.bank.short_name,
                "amount": cs.total_amount,
                "days_to": (cs.payment_date - today).days,
                "type": "Кредит"
            })

        upcoming_payments_list = sorted(upcoming_payments_list, key=lambda x: x["date"])[:10]

        # Ближайшие поступления (доходы)
        upcoming_inflows_list = []
        inflow_scheds_qs = PaymentSchedule.objects.filter(
            obligation__in=debtor_obligations,
            status__in=["planned", "partially_paid"],
            payment_date__year=selected_year
        )
        if month:
            inflow_scheds_qs = inflow_scheds_qs.filter(payment_date__month=month)
        else:
            inflow_scheds_qs = inflow_scheds_qs.filter(payment_date__gte=today if selected_year == today.year else date(selected_year, 1, 1))
            
        inflow_scheds = inflow_scheds_qs.select_related("obligation__contract__counteragent", "obligation__contract").order_by("payment_date")[:10]

        for s in inflow_scheds:
            upcoming_inflows_list.append({
                "date": s.payment_date,
                "contract": s.obligation.contract.contract_number,
                "counteragent": s.obligation.contract.counteragent.short_name,
                "amount": s.amount,
                "days_to": (s.payment_date - today).days
            })

        upcoming_inflows_list = sorted(upcoming_inflows_list, key=lambda x: x["date"])[:10]

        # Просрочки
        overdue_list = []
        # Просроченные по договорам
        overdue_scheds_qs = PaymentSchedule.objects.filter(
            obligation__in=obligations,
            status="overdue",
            payment_date__year=selected_year
        )
        if month:
            overdue_scheds_qs = overdue_scheds_qs.filter(payment_date__month=month)
            
        overdue_scheds = overdue_scheds_qs.select_related("obligation__contract__counteragent", "obligation__contract").order_by("payment_date")
        
        for s in overdue_scheds:
            overdue_list.append({
                "counteragent": s.obligation.contract.counteragent.short_name,
                "contract": s.obligation.contract.contract_number,
                "amount": s.amount,
                "days_overdue": (today - s.payment_date).days,
                "type": "Оплата" if s.obligation.obligation_type.code != "customer" else "Поступление"
            })

        # Просроченные по кредитам
        overdue_credit_scheds_qs = CreditPaymentSchedule.objects.filter(
            credit_agreement__in=credits_qs,
            status="overdue",
            payment_date__year=selected_year
        )
        if month:
            overdue_credit_scheds_qs = overdue_credit_scheds_qs.filter(payment_date__month=month)
            
        overdue_credit_scheds = overdue_credit_scheds_qs.select_related("credit_agreement__bank").order_by("payment_date")

        for cs in overdue_credit_scheds:
            overdue_list.append({
                "counteragent": cs.credit_agreement.bank.short_name,
                "contract": cs.credit_agreement.contract_number,
                "amount": cs.total_amount,
                "days_overdue": (today - cs.payment_date).days,
                "type": "Кредит"
            })

        overdue_list = sorted(overdue_list, key=lambda x: -x["days_overdue"])[:10]

        return {
            "total_sum": total_sum,
            "creditor_total_debt": creditor_total_debt,
            "debtor_total_debt": debtor_total_debt,
            "overdue_total": overdue_total,
            "current_month_obligations": current_month_obligations,
            "current_month_inflow": current_month_inflow,
            "upcoming_payments": upcoming_payments_list,
            "upcoming_inflows": upcoming_inflows_list,
            "overdue_obligations": overdue_list,
        }

    @classmethod
    def get_calendar_events(
        cls,
        user: User,
        start: date,
        end: date,
        org_id: str | None = None,
        agent_id: str | None = None,
        contract_id: str | None = None,
        ob_type_id: str | None = None,
        employee_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Получает события для платежного календаря с учетом фильтров и прав доступа.

        Args:
            user: Пользователь системы.
            start: Начальная дата.
            end: Конечная дата.
            org_id: Фильтр по организации.
            agent_id: Фильтр по контрагенту.
            contract_id: Фильтр по договору.
            ob_type_id: Фильтр по типу обязательства.
            employee_id: Фильтр по ответственному сотруднику.

        Returns:
            Список событий. Каждое событие содержит дату, тип (платеж/поступление/кредит),
            сумму, контрагента и статус.
        """
        # Фильтруем договоры и кредиты по правам доступа
        contracts = cls.apply_visibility_filter(user, FinancialContract.objects.all())
        credits_qs = cls.apply_visibility_filter(user, CreditAgreement.objects.all())

        # Применяем фильтры пользователя
        if org_id:
            contracts = contracts.filter(organization_id=org_id)
            credits_qs = credits_qs.none()
        if agent_id:
            contracts = contracts.filter(counteragent_id=agent_id)
            credits_qs = credits_qs.filter(bank_id=agent_id)
        if contract_id:
            contracts = contracts.filter(id=contract_id)
            credits_qs = credits_qs.filter(id=contract_id)
        if employee_id:
            contracts = contracts.filter(employee_id=employee_id)
            credits_qs = credits_qs.filter(employee_id=employee_id)

        obligations = FinancialObligation.objects.filter(contract__in=contracts)
        if ob_type_id:
            obligations = obligations.filter(obligation_type_id=ob_type_id)
            credits_qs = credits_qs.none()

        events: list[dict[str, Any]] = []

        # 1. Обычные плановые платежи и поступления
        schedules = PaymentSchedule.objects.filter(
            obligation__in=obligations,
            payment_date__range=[start, end]
        ).select_related("obligation__contract__counteragent", "obligation__obligation_type", "obligation__contract")

        for s in schedules:
            is_inflow = s.obligation.obligation_type.code == "customer"
            events.append({
                "date": s.payment_date,
                "type": "inflow" if is_inflow else "outflow",
                "type_display": "Поступление" if is_inflow else "Платеж",
                "amount": s.amount,
                "counteragent": s.obligation.contract.counteragent.short_name,
                "contract": s.obligation.contract.contract_number,
                "status": s.status,
                "status_display": s.get_status_display(),
                "obligation_type": s.obligation.obligation_type.name,
            })

        # 2. Платежи по кредитам
        credit_schedules = CreditPaymentSchedule.objects.filter(
            credit_agreement__in=credits_qs,
            payment_date__range=[start, end]
        ).select_related("credit_agreement__bank")

        for cs in credit_schedules:
            events.append({
                "date": cs.payment_date,
                "type": "credit",
                "type_display": "Кредит",
                "amount": cs.total_amount,
                "counteragent": cs.credit_agreement.bank.short_name,
                "contract": cs.credit_agreement.contract_number,
                "status": cs.status,
                "status_display": cs.get_status_display(),
                "obligation_type": "Банковский кредит",
            })

        return sorted(events, key=lambda x: x["date"])
