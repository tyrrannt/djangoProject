# -*- coding: utf-8 -*-
"""Контроллеры управления справочником категорий персонала (АУП, ИТП, ЧЛЭ, Прочий персонал)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from customers_app.models import DataBaseUser, DataBaseUserWorkProfile, Job, StaffCategory
from customers_app.views_payroll_reports import PAYROLL_GROUP_FULL


def _require_staff_category_access(request: HttpRequest) -> None:
    """Доступ разрешён суперпользователям, staff и участникам группы полного доступа к аналитике."""
    user = request.user
    allowed = bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=PAYROLL_GROUP_FULL).exists()
        )
    )
    if not allowed:
        raise PermissionDenied("Доступ к настройке категорий персонала запрещён.")


@login_required
def staff_categories_manage(request: HttpRequest) -> HttpResponse:
    """Страница управления категориями персонала, привязкой должностей и исключениями по сотрудникам."""
    _require_staff_category_access(request)

    active_tab = request.GET.get("tab", "categories")
    job_search = (request.GET.get("job_q") or "").strip()
    emp_search = (request.GET.get("emp_q") or "").strip()

    categories = list(StaffCategory.objects.all().order_by("sort_order", "name"))

    jobs_qs = Job.objects.select_related("staff_category").order_by("name")
    if job_search:
        jobs_qs = jobs_qs.filter(name__icontains=job_search)
    jobs = list(jobs_qs)

    emp_qs = (
        DataBaseUser.objects.filter(is_active=True)
        .select_related("user_work_profile", "user_work_profile__job", "user_work_profile__job__staff_category", "user_work_profile__staff_category", "user_work_profile__divisions")
        .order_by("last_name", "first_name", "surname")
    )
    if emp_search:
        emp_qs = emp_qs.filter(
            Q(last_name__icontains=emp_search)
            | Q(first_name__icontains=emp_search)
            | Q(title__icontains=emp_search)
            | Q(user_work_profile__job__name__icontains=emp_search)
        )
    employees = list(emp_qs)

    # Подсчёт активных сотрудников по категориям
    cat_counts = {c.pk: 0 for c in categories}
    unassigned_count = 0
    for emp in DataBaseUser.objects.filter(is_active=True).select_related("user_work_profile__staff_category", "user_work_profile__job__staff_category"):
        cat = emp.get_staff_category()
        if cat and cat.pk in cat_counts:
            cat_counts[cat.pk] += 1
        else:
            unassigned_count += 1

    for c in categories:
        c.emp_count = cat_counts.get(c.pk, 0)

    return render(
        request,
        "customers_app/staff_categories_manage.html",
        {
            "title": "Категории персонала (АУП, ИТП, ЧЛЭ)",
            "categories": categories,
            "jobs": jobs,
            "employees": employees,
            "unassigned_count": unassigned_count,
            "active_tab": active_tab,
            "job_search": job_search,
            "emp_search": emp_search,
        },
    )


@login_required
@require_POST
def staff_categories_save_action(request: HttpRequest) -> HttpResponse:
    """Обрабатывает создание/обновление категорий и массовую привязку должностей/сотрудников."""
    _require_staff_category_access(request)
    action = request.POST.get("action", "")

    if action == "create_category":
        short_name = (request.POST.get("short_name") or "").strip()
        name = (request.POST.get("name") or short_name).strip()
        sort_order = int(request.POST.get("sort_order") or 100)
        if not short_name:
            messages.error(request, "Укажите краткое обозначение категории.")
        elif StaffCategory.objects.filter(short_name__iexact=short_name).exists():
            messages.error(request, f"Категория «{short_name}» уже существует.")
        else:
            StaffCategory.objects.create(short_name=short_name, name=name, sort_order=sort_order)
            messages.success(request, f"Категория «{short_name}» добавлена.")
        return redirect("customers_app:staff_categories_manage")

    if action == "delete_category":
        cat_id = request.POST.get("category_id")
        StaffCategory.objects.filter(pk=cat_id).delete()
        messages.success(request, "Категория удалена.")
        return redirect("customers_app:staff_categories_manage")

    if action == "bulk_assign_jobs":
        updated = 0
        for key, val in request.POST.items():
            if not key.startswith("job_cat_"):
                continue
            job_id = key.replace("job_cat_", "")
            if not job_id.isdigit():
                continue
            cat_id = int(val) if val.isdigit() else None
            Job.objects.filter(pk=int(job_id)).update(staff_category_id=cat_id)
            updated += 1
        messages.success(request, f"Обновлены категории по должностям ({updated} позиций).")
        return redirect("/users/staff-categories/?tab=jobs")

    if action == "bulk_assign_employees":
        updated = 0
        for key, val in request.POST.items():
            if not key.startswith("emp_cat_"):
                continue
            emp_id = key.replace("emp_cat_", "")
            if not emp_id.isdigit():
                continue
            cat_id = int(val) if val.isdigit() else None
            emp = DataBaseUser.objects.select_related("user_work_profile").filter(pk=int(emp_id)).first()
            if emp and emp.user_work_profile:
                DataBaseUserWorkProfile.objects.filter(pk=emp.user_work_profile_id).update(staff_category_id=cat_id)
                updated += 1
        messages.success(request, f"Сохранены индивидуальные категории сотрудников ({updated} записей).")
        return redirect("/users/staff-categories/?tab=employees")

    return redirect("customers_app:staff_categories_manage")
