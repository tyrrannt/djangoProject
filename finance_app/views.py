from datetime import date, datetime
from decimal import Decimal
from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from finance_app.services.finance_selector import FinanceSelector
from finance_app.services.report_service import ReportService
from finance_app.models import Organization, ObligationType, FinancialContract
from customers_app.models import Counteragent
from django.contrib.auth import get_user_model

User = get_user_model()


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Представление для отображения финансового дашборда.
    """
    template_name = "finance_app/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """
        Формирует контекст с показателями дашборда.

        Args:
            **kwargs: Дополнительные аргументы контекста.

        Returns:
            Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        
        year_str = self.request.GET.get('year')
        try:
            year = int(year_str) if year_str else date.today().year
        except ValueError:
            year = date.today().year
            
        month_str = self.request.GET.get('month')
        try:
            month = int(month_str) if month_str else None
        except ValueError:
            month = None
            
        dashboard_data = FinanceSelector.get_dashboard_data(self.request.user, year, month)
        context.update(dashboard_data)
        context["active_tab"] = "dashboard"
        
        context["available_years"] = list(range(2020, date.today().year + 3))
        context["selected_year"] = year
        context["available_months"] = [
            (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
            (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
            (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
        ]
        context["selected_month"] = month
        
        return context


class PaymentCalendarView(LoginRequiredMixin, View):
    """
    Представление для отображения интерактивного платежного календаря.
    """

    def get(self, request: Any) -> HttpResponse:
        """
        Обрабатывает GET-запрос. Возвращает либо страницу календаря,
        либо JSON с событиями (при AJAX запросе от FullCalendar).

        Args:
            request: HTTP-запрос.

        Returns:
            HTTP-ответ с HTML или JSON.
        """
        # Параметры фильтрации из GET-запроса
        org_id = request.GET.get("org")
        agent_id = request.GET.get("agent")
        contract_id = request.GET.get("contract")
        ob_type_id = request.GET.get("ob_type")
        employee_id = request.GET.get("employee")

        # Если это AJAX запрос на получение событий
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or "start" in request.GET:
            from django.http import JsonResponse
            
            start_str = request.GET.get("start")
            end_str = request.GET.get("end")
            
            try:
                # FullCalendar присылает даты в ISO формате (например, 2026-06-01T00:00:00)
                start_date = datetime.fromisoformat(start_str.split("T")[0]).date() if start_str else date.today() - timedelta(days=30)
                end_date = datetime.fromisoformat(end_str.split("T")[0]).date() if end_str else date.today() + timedelta(days=90)
            except Exception:
                start_date = date.today() - timedelta(days=30)
                end_date = date.today() + timedelta(days=90)

            events = FinanceSelector.get_calendar_events(
                user=request.user,
                start=start_date,
                end=end_date,
                org_id=org_id,
                agent_id=agent_id,
                contract_id=contract_id,
                ob_type_id=ob_type_id,
                employee_id=employee_id
            )

            # Форматируем события под стандарт FullCalendar
            fc_events = []
            for ev in events:
                # Цвет события в зависимости от типа и статуса
                # inflow - зеленый, outflow - синий, credit - фиолетовый, overdue - красный
                color = "#1E4620" if ev["type"] == "inflow" else "#1F497D"
                if ev["type"] == "credit":
                    color = "#5C2D91"
                if ev["status"] == "overdue":
                    color = "#B30000"

                fc_events.append({
                    "title": f"{ev['type_display']}: {ev['amount']:,.2f} руб. ({ev['counteragent']})",
                    "start": ev["date"].isoformat(),
                    "allDay": True,
                    "backgroundColor": color,
                    "borderColor": color,
                    "extendedProps": {
                        "contract": ev["contract"],
                        "counteragent": ev["counteragent"],
                        "amount": f"{ev['amount']:,.2f} руб.",
                        "status": ev["status_display"],
                        "type": ev["type_display"],
                        "obligation_type": ev["obligation_type"]
                    }
                })
            return JsonResponse(fc_events, safe=False)

        # Рендерим HTML страницу с фильтрами
        context = {
            "organizations": Organization.objects.all(),
            "counteragents": Counteragent.objects.all(),
            "contracts": FinanceSelector.apply_visibility_filter(request.user, FinancialContract.objects.all()),
            "obligation_types": ObligationType.objects.all(),
            "employees": User.objects.filter(is_active=True),
            "active_tab": "calendar",
            "filters": {
                "org": org_id,
                "agent": agent_id,
                "contract": contract_id,
                "ob_type": ob_type_id,
                "employee": employee_id,
            }
        }
        return render(request, "finance_app/calendar.html", context)


class ReportsListView(LoginRequiredMixin, TemplateView):
    """
    Представление для отображения списка финансовых отчетов.
    """
    template_name = "finance_app/reports_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """
        Формирует контекст со списком отчетов.

        Args:
            **kwargs: Дополнительные аргументы контекста.

        Returns:
            Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        
        try:
            selected_year = int(self.request.GET.get("year")) if self.request.GET.get("year") else date.today().year
            selected_month = int(self.request.GET.get("month")) if self.request.GET.get("month") else None
        except ValueError:
            selected_year = date.today().year
            selected_month = None

        context["selected_year"] = selected_year
        context["selected_month"] = selected_month
        context["available_years"] = range(2020, date.today().year + 3)
        context["available_months"] = [
            (1, "Январь"), (2, "Февраль"), (3, "Март"), (4, "Апрель"),
            (5, "Май"), (6, "Июнь"), (7, "Июль"), (8, "Август"),
            (9, "Сентябрь"), (10, "Октябрь"), (11, "Ноябрь"), (12, "Декабрь")
        ]

        context["active_tab"] = "reports"
        context["reports"] = [
            {"type": "contracts_registry", "name": "1. Реестр договоров", "desc": "Список всех финансовых договоров организации."},
            {"type": "credits_registry", "name": "2. Реестр кредитов", "desc": "Кредитные договоры банков, процентные ставки и остатки долгов."},
            {"type": "payment_calendar", "name": "3. Платежный календарь", "desc": "График плановых платежей и ожидаемых поступлений."},
            {"type": "creditor_debts", "name": "4. Кредиторская задолженность", "desc": "Контроль обязательств перед поставщиками и подрядчиками."},
            {"type": "debtor_debts", "name": "5. Дебиторская задолженность", "desc": "Контроль задолженности покупателей и ожидаемых поступлений."},
            {"type": "overdue_obligations", "name": "6. Просроченные обязательства", "desc": "Анализ просроченных оплат по договорам и кредитам."},
            {"type": "payment_plan_fact", "name": "7. План-факт оплат (Расходы)", "desc": "Сравнение запланированных расходов с фактическими оплатами."},
            {"type": "inflow_plan_fact", "name": "8. План-факт поступлений (Доходы)", "desc": "Сравнение плановых поступлений от клиентов с фактом."},
            {"type": "cash_flow", "name": "9. Движение денежных средств (ДДС)", "desc": "Реестр всех фактических поступлений и списаний с расчетных счетов."},
        ]
        return context


class ExportReportView(LoginRequiredMixin, View):
    """
    Представление для экспорта отчетов в форматы XLSX и PDF.
    """

    def get(self, request: Any, report_type: str) -> HttpResponse:
        """
        Генерирует файл отчета и возвращает его для скачивания.

        Args:
            request: HTTP-запрос.
            report_type: Кодовое имя отчета.

        Returns:
            HTTP-ответ с бинарным файлом.
        """
        export_format = request.GET.get("format", "xlsx").lower()
        
        valid_reports = [
            "contracts_registry", "credits_registry", "payment_calendar",
            "creditor_debts", "debtor_debts", "overdue_obligations",
            "payment_plan_fact", "inflow_plan_fact", "cash_flow"
        ]
        if report_type not in valid_reports:
            raise Http404("Отчет не найден")

        try:
            year = int(request.GET.get("year")) if request.GET.get("year") else None
            month = int(request.GET.get("month")) if request.GET.get("month") else None
        except ValueError:
            year = None
            month = None

        filename_prefix = f"report_{report_type}_{date.today():%Y%m%d}"

        if export_format == "pdf":
            pdf_data = ReportService.generate_pdf(report_type, request.user, year, month)
            response = HttpResponse(pdf_data, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename_prefix}.pdf"'
            return response
        else:
            xlsx_data = ReportService.generate_xlsx(report_type, request.user, year, month)
            response = HttpResponse(
                xlsx_data,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename_prefix}.xlsx"'
            return response


from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from finance_app.models import CreditAgreement, CentralBankKeyRate, CreditTranche, CreditPaymentFact
from finance_app.services.overdraft_service import OverdraftCalculationService
from finance_app.forms import CreditTrancheForm, CentralBankKeyRateForm, CreditAgreementForm, CreditPaymentFactForm

class OverdraftListView(LoginRequiredMixin, ListView):
    """
    Список кредитных договоров (овердрафтов) для расчета платежей.
    """
    model = CreditAgreement
    template_name = "finance_app/overdraft_list.html"
    context_object_name = "agreements"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "overdraft"
        
        total_debt = Decimal('0.00')
        total_unused_limit = Decimal('0.00')
        today = date.today()
        
        for agreement in context['agreements']:
            service = OverdraftCalculationService(agreement)
            result = service.calculate(today)
            total_debt += result['total_principal']
            total_unused_limit += result['current_unused_limit']
            
            # Сохраняем расчетные данные для вывода в таблицу
            agreement.calculated_debt = result['total_principal']
            agreement.calculated_unused_limit = result['current_unused_limit']
            
        context['total_debt'] = total_debt
        context['total_unused_limit'] = total_unused_limit
        return context

class OverdraftCreateView(LoginRequiredMixin, CreateView):
    model = CreditAgreement
    form_class = CreditAgreementForm
    template_name = "finance_app/overdraft_form.html"
    success_url = reverse_lazy("finance:overdraft_list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "overdraft"
        context["title"] = "Добавление договора овердрафта"
        return context

class OverdraftUpdateView(LoginRequiredMixin, UpdateView):
    model = CreditAgreement
    form_class = CreditAgreementForm
    template_name = "finance_app/overdraft_form.html"
    success_url = reverse_lazy("finance:overdraft_list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "overdraft"
        context["title"] = "Редактирование договора овердрафта"
        return context

class OverdraftDeleteView(LoginRequiredMixin, DeleteView):
    model = CreditAgreement
    success_url = reverse_lazy("finance:overdraft_list")
    
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class OverdraftDetailView(LoginRequiredMixin, DetailView):
    """
    Детальная страница расчета овердрафта по договору.
    """
    model = CreditAgreement
    template_name = "finance_app/overdraft_detail.html"
    context_object_name = "agreement"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        agreement = self.get_object()
        
        # Получаем дату окончания расчета, по умолчанию - сегодня
        end_date_str = self.request.GET.get('end_date')
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = date.today()

        service = OverdraftCalculationService(agreement)
        calc_result = service.calculate(end_date)
        
        context["calc_result"] = calc_result
        context["end_date"] = end_date
        context["tranche_form"] = CreditTrancheForm()
        context["payment_form"] = CreditPaymentFactForm()
        context["active_tab"] = "overdraft"
        return context

    def post(self, request, *args, **kwargs):
        """
        Обработка добавления нового транша или платежа.
        """
        agreement = self.get_object()
        if 'add_tranche' in request.POST:
            form = CreditTrancheForm(request.POST)
            if form.is_valid():
                tranche = form.save(commit=False)
                tranche.credit_agreement = agreement
                tranche.save()
        elif 'add_payment' in request.POST:
            form = CreditPaymentFactForm(request.POST)
            if form.is_valid():
                payment = form.save(commit=False)
                payment.credit_agreement = agreement
                payment.save()
        return redirect("finance:overdraft_detail", pk=agreement.pk)


class KeyRateSettingsView(LoginRequiredMixin, ListView):
    """
    Настройка ключевых ставок ЦБ.
    """
    model = CentralBankKeyRate
    template_name = "finance_app/key_rates.html"
    context_object_name = "rates"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["form"] = CentralBankKeyRateForm()
        context["active_tab"] = "settings"
        return context

    def post(self, request, *args, **kwargs):
        """
        Обработка добавления новой ставки.
        """
        form = CentralBankKeyRateForm(request.POST)
        if form.is_valid():
            form.save()
        return redirect("finance:key_rates")

class KeyRateUpdateView(LoginRequiredMixin, UpdateView):
    model = CentralBankKeyRate
    form_class = CentralBankKeyRateForm
    template_name = "finance_app/overdraft_form.html"
    success_url = reverse_lazy("finance:key_rates")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "settings"
        context["title"] = "Редактирование ставки"
        return context

class KeyRateDeleteView(LoginRequiredMixin, DeleteView):
    model = CentralBankKeyRate
    success_url = reverse_lazy("finance:key_rates")
    
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

class CreditTrancheUpdateView(LoginRequiredMixin, UpdateView):
    model = CreditTranche
    form_class = CreditTrancheForm
    template_name = "finance_app/overdraft_form.html"
    
    def get_success_url(self):
        return reverse_lazy("finance:overdraft_detail", kwargs={"pk": self.object.credit_agreement.pk})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "overdraft"
        context["title"] = "Редактирование транша"
        return context

class CreditTrancheDeleteView(LoginRequiredMixin, DeleteView):
    model = CreditTranche
    
    def get_success_url(self):
        return reverse_lazy("finance:overdraft_detail", kwargs={"pk": self.object.credit_agreement.pk})
        
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

class CreditPaymentUpdateView(LoginRequiredMixin, UpdateView):
    model = CreditPaymentFact
    form_class = CreditPaymentFactForm
    template_name = "finance_app/overdraft_form.html"
    
    def get_success_url(self):
        return reverse_lazy("finance:overdraft_detail", kwargs={"pk": self.object.credit_agreement.pk})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "overdraft"
        context["title"] = "Редактирование платежа"
        return context

class CreditPaymentDeleteView(LoginRequiredMixin, DeleteView):
    model = CreditPaymentFact
    
    def get_success_url(self):
        return reverse_lazy("finance:overdraft_detail", kwargs={"pk": self.object.credit_agreement.pk})
        
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)
