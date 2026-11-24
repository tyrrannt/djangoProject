# -*- coding: utf-8 -*-
"""Контроллеры пакетного формирования документов при приёме на работу и API доверенностей подписанта."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import FileResponse, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import FormView

from customers_app.forms import HirePackageForm
from customers_app.models import ConsentType, DataBaseUser, DocumentSigner
from customers_app.services_onboarding_docs import _sanitize_filename, generate_hire_package_zip
from hrdepartment_app.models import PowerOfAttorney


@login_required
def api_signer_poas(request: HttpRequest, signer_id: int) -> JsonResponse:
    """Возвращает сведения о подписанте и список доверенностей из реестра портала.

    Если у подписанта привязан ``employee``, в первую очередь возвращаются доверенности,
    где он указан поверенным (``grantee_name_user``); если таких записей нет —
    возвращаются все неаннулированные доверенности реестра, чтобы кадровик мог
    выбрать нужный документ.

    Args:
        request (HttpRequest): Входящий HTTP GET-запрос.
        signer_id (int): Идентификатор ``DocumentSigner``.

    Returns:
        JsonResponse: JSON с флагом ``acts_by_charter`` и списком доверенностей ``poas``.
    """
    signer = get_object_or_404(DocumentSigner, pk=signer_id)
    today = timezone.localdate()

    base_qs = PowerOfAttorney.objects.filter(cancellation_date__isnull=True).order_by("-issue_date", "-number")
    if signer.employee_id:
        personal_qs = base_qs.filter(grantee_name_user_id=signer.employee_id)
        poas_qs = personal_qs if personal_qs.exists() else base_qs
    else:
        poas_qs = base_qs

    poas_data = []
    for poa in poas_qs:
        issue_str = poa.issue_date.strftime("%d.%m.%Y") if poa.issue_date else "—"
        expiry_str = poa.expiry_date.strftime("%d.%m.%Y") if poa.expiry_date else "—"
        is_expired = bool(poa.expiry_date and poa.expiry_date < today)
        status_note = " [истекла]" if is_expired else ""
        poas_data.append(
            {
                "id": poa.pk,
                "number": poa.number,
                "issue_date": issue_str,
                "expiry_date": expiry_str,
                "is_expired": is_expired,
                "label": f"№ {poa.number} от {issue_str} (до {expiry_str}){status_note}",
            }
        )

    return JsonResponse(
        {
            "id": signer.pk,
            "short_name": signer.short_name,
            "acts_by_charter": signer.acts_by_charter,
            "poas": poas_data,
        }
    )


class HirePackageGenerateView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Представление пакетного формирования документов при приёме на работу (ZIP-архив)."""

    template_name = "customers_app/hire_package_form.html"
    form_class = HirePackageForm
    permission_required = "customers_app.add_biometricconsent"

    def get_initial(self):
        """Предзаполняет сотрудника (из ``?employee_id=``), дату и подписанта по умолчанию."""
        initial = super().get_initial()
        initial["consent_date"] = date.today()

        default_signer = DocumentSigner.objects.filter(is_active=True, is_default=True).first()
        if not default_signer:
            default_signer = DocumentSigner.objects.filter(is_active=True).first()
        if default_signer:
            initial["signer"] = default_signer

        initial["consent_types"] = ConsentType.objects.filter(is_active=True, is_required_on_hire=True)

        employee_id = self.request.GET.get("employee_id")
        if employee_id:
            try:
                emp = DataBaseUser.objects.get(pk=employee_id)
                initial["employee"] = emp
                if getattr(emp, "employment_contract_number", None):
                    initial["employment_contract_number"] = emp.employment_contract_number
                if getattr(emp, "employment_contract_date", None):
                    initial["employment_contract_date"] = emp.employment_contract_date
            except DataBaseUser.DoesNotExist:
                pass

        return initial

    def get_context_data(self, **kwargs):
        """Добавляет метаданные типов документов (каким нужен подписант и у каких есть шаблон)."""
        context = super().get_context_data(**kwargs)
        active_types = list(ConsentType.objects.select_related("template").filter(is_active=True).order_by("sort_order", "name"))
        context["title"] = "Пакет документов при приёме на работу"
        context["active_types"] = active_types
        context["signer_required_type_ids"] = [t.pk for t in active_types if t.requires_signer]
        return context

    def form_valid(self, form):
        """Создаёт записи документов в БД и отдаёт ZIP-архив с заполненными Word-файлами."""
        employee = form.cleaned_data["employee"]
        consent_types = form.cleaned_data["consent_types"]
        consent_date = form.cleaned_data["consent_date"]
        signer = form.cleaned_data.get("signer")
        powers_of_attorney = form.cleaned_data.get("powers_of_attorney")
        contract_number = form.cleaned_data.get("employment_contract_number") or ""
        contract_date = form.cleaned_data.get("employment_contract_date")
        comment = form.cleaned_data.get("comment") or ""

        render_errors = []
        zip_buffer, created_consents, skipped = generate_hire_package_zip(
            employee=employee,
            consent_types=consent_types,
            consent_date=consent_date,
            signer=signer,
            powers_of_attorney=powers_of_attorney,
            created_by=self.request.user,
            employment_contract_number=contract_number,
            employment_contract_date=contract_date,
            comment=comment,
            errors_out=render_errors,
        )

        # Если ни один из выбранных документов не удалось сформировать, возвращаемся в список с подробной причиной
        if len(skipped) == len(created_consents):
            details = "; ".join(render_errors) if render_errors else "не привязан Word-шаблон"
            messages.warning(
                self.request,
                f"Создано записей в реестре: {len(created_consents)}, но файлы не сформированы ({details}). "
                "Проверьте шаблоны в админ-панели (Шаблоны документов).",
            )
            return redirect("customers_app:biometric_consent_list")

        emp_slug = _sanitize_filename(employee.last_name or employee.username)
        zip_name = f"Пакет_приема_{emp_slug}_{consent_date.strftime('%Y%m%d')}.zip"
        return FileResponse(
            zip_buffer,
            as_attachment=True,
            filename=zip_name,
            content_type="application/zip",
        )
