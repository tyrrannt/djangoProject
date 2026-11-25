# -*- coding: utf-8 -*-
"""Контроллеры аналитики начислений: загрузка XML КНД 1151162, read-only OData 1С и отчёты."""

import datetime
import io
import json
from decimal import Decimal
from typing import Any, Dict, List

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from customers_app.models import (
    DataBaseUser,
    Division,
    PayrollCalculationTypeCache,
    PayrollFnsLine,
    PayrollODataDetail,
    PayrollReportBatch,
    StaffCategory,
)
from customers_app.services_payroll_reports import (
    import_knd_1151162_xml,
    normalize_snils,
    sync_1c_odata_payroll_month,
)

MONTH_NAMES_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


PAYROLL_GROUP_FULL = "Аналитика начислений (полный доступ)"
PAYROLL_GROUP_READ = "Аналитика начислений (чтение)"


def _get_payroll_access_level(user) -> str | None:
    """Определяет уровень доступа пользователя к аналитике начислений ('full', 'read' или None)."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser or user.groups.filter(name=PAYROLL_GROUP_FULL).exists():
        return "full"
    if user.groups.filter(name=PAYROLL_GROUP_READ).exists():
        return "read"
    return None


def _require_payroll_reports_access(request: HttpRequest, require_full: bool = False) -> str:
    """Проверяет доступ к зарплатной аналитике ('read' или 'full')."""
    level = _get_payroll_access_level(request.user)
    if level is None:
        raise PermissionDenied("Доступ к отчётам по начислениям разрешён только уполномоченным группам.")
    if require_full and level != "full":
        raise PermissionDenied("Недостаточно прав: требуется группа с полным доступом.")
    return level


def _get_selected_period(request: HttpRequest) -> tuple[int, int]:
    """Извлекает выбранный год и месяц (0 = весь год) из GET-параметров."""
    today = datetime.date.today()
    try:
        year = int(request.GET.get("year") or today.year)
    except ValueError:
        year = today.year
    try:
        month = int(request.GET.get("month") or 0)
    except ValueError:
        month = 0
    if not (0 <= month <= 12):
        month = 0
    return year, month


def _get_excluded_calc_keys() -> set[str]:
    """Возвращает GUID видов расчёта, выделяемых отдельно от основной ЗП."""
    return set(
        PayrollCalculationTypeCache.objects.filter(exclude_from_salary=True).values_list("ref_key", flat=True)
    )


def _is_excluded_detail(det: PayrollODataDetail, excluded_keys: set[str]) -> bool:
    """Проверяет, относится ли запись к выделяемым компенсациям (не в общую ЗП)."""
    if det.calculation_type_key and det.calculation_type_key in excluded_keys:
        return True
    return "компенсация питания" in (det.calculation_type_name or "").lower()


def _build_employee_summary_rows(
    year: int,
    month: int,
    division_id: str = "",
    search: str = "",
    staff_category_id: str = "",
) -> List[Dict[str, Any]]:
    """Собирает сводную таблицу по людям (склейка по person_ref_key / СНИЛС) за период."""
    fns_qs = PayrollFnsLine.objects.filter(batch__year=year).select_related(
        "employee",
        "employee__user_work_profile__divisions",
        "employee__user_work_profile__job",
        "employee__user_work_profile__job__staff_category",
        "employee__user_work_profile__staff_category",
    )
    odata_qs = PayrollODataDetail.objects.filter(year=year).select_related(
        "employee",
        "division",
        "employee__user_work_profile__job",
        "employee__user_work_profile__job__staff_category",
        "employee__user_work_profile__staff_category",
    )

    if month:
        fns_qs = fns_qs.filter(batch__month=month)
        odata_qs = odata_qs.filter(month=month)

    if division_id and division_id.isdigit():
        div_int = int(division_id)
        fns_qs = fns_qs.filter(employee__user_work_profile__divisions_id=div_int)
        odata_qs = odata_qs.filter(Q(division_id=div_int) | Q(employee__user_work_profile__divisions_id=div_int))

    people: Dict[str, Dict[str, Any]] = {}

    def _get_or_init_person(key: str, emp: DataBaseUser | None, full_name: str, snils: str, inn: str, div_name: str) -> Dict[str, Any]:
        if key not in people:
            job_name = ""
            if emp and emp.user_work_profile and emp.user_work_profile.job:
                job_name = str(emp.user_work_profile.job)
            if not div_name and emp and emp.user_work_profile and emp.user_work_profile.divisions:
                div_name = str(emp.user_work_profile.divisions)
            staff_cat = emp.get_staff_category() if emp else None
            people[key] = {
                "person_key": key,
                "employee_id": emp.pk if emp else None,
                "full_name": full_name or (str(emp) if emp else "Неизвестно"),
                "snils": snils or (emp.user_profile.snils if emp and emp.user_profile else ""),
                "inn": inn or (emp.user_profile.inn if emp and emp.user_profile else ""),
                "division": div_name,
                "job": job_name,
                "staff_category_id": staff_cat.pk if staff_cat else None,
                "staff_category_name": staff_cat.short_name if staff_cat else "Без категории",
                "is_active": emp.is_active if emp else False,
                "fns_total": Decimal("0.00"),
                "accrued_total": Decimal("0.00"),
                "compensation_total": Decimal("0.00"),
                "withheld_total": Decimal("0.00"),
            }
        return people[key]

    # Для КНД 1151162 при наличии корректировок за один месяц берём максимальный НомКорр
    latest_batches = {}
    for b in PayrollReportBatch.objects.filter(year=year).order_by("month", "-correction_number", "-uploaded_at"):
        if month and b.month != month:
            continue
        latest_batches.setdefault(b.month, b.pk)

    if latest_batches:
        for line in fns_qs.filter(batch_id__in=latest_batches.values()):
            key = line.person_ref_key or (f"snils:{normalize_snils(line.snils)}" if normalize_snils(line.snils) else f"fio:{line.full_name}")
            entry = _get_or_init_person(key, line.employee, line.full_name, line.snils, line.inn, "")
            entry["fns_total"] += line.total_amount

    excluded_keys = _get_excluded_calc_keys()
    for det in odata_qs:
        key = det.person_ref_key or (f"emp:{det.employee_ref_key}" if det.employee_ref_key else f"id:{det.pk}")
        div_name = str(det.division) if det.division else ""
        emp_name = str(det.employee) if det.employee else det.person_ref_key
        entry = _get_or_init_person(key, det.employee, emp_name, "", "", div_name)
        if det.group_type == "Начислено":
            if _is_excluded_detail(det, excluded_keys):
                entry["compensation_total"] += det.amount
            else:
                entry["accrued_total"] += det.amount
        elif det.group_type == "Удержано" or det.calculation_category in ("Удержания", "НДФЛ"):
            entry["withheld_total"] += det.amount

    rows = list(people.values())
    if staff_category_id:
        if staff_category_id == "none":
            rows = [r for r in rows if r["staff_category_id"] is None]
        elif staff_category_id.isdigit():
            cat_int = int(staff_category_id)
            rows = [r for r in rows if r["staff_category_id"] == cat_int]

    if search:
        q = search.strip().lower()
        rows = [
            r for r in rows
            if q in r["full_name"].lower() or q in r["snils"].lower() or q in r["division"].lower()
        ]

    for r in rows:
        r["net_total"] = r["accrued_total"] - r["withheld_total"]
        r["diff_fns_accrued"] = r["fns_total"] - r["accrued_total"]

    rows.sort(key=lambda x: x["full_name"])
    return rows


def _build_category_summary(employee_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Агрегирует ФОТ и численность по категориям персонала (АУП, ИТП, ЧЛЭ, Прочий)."""
    grouped: Dict[str, Dict[str, Any]] = {}
    total_accrued_all = sum((r["accrued_total"] for r in employee_rows), Decimal("0.00"))

    for r in employee_rows:
        cat_name = r["staff_category_name"]
        if cat_name not in grouped:
            grouped[cat_name] = {
                "name": cat_name,
                "employees_count": 0,
                "fns_total": Decimal("0.00"),
                "accrued_total": Decimal("0.00"),
                "compensation_total": Decimal("0.00"),
                "withheld_total": Decimal("0.00"),
                "net_total": Decimal("0.00"),
            }
        g = grouped[cat_name]
        g["employees_count"] += 1
        g["fns_total"] += r["fns_total"]
        g["accrued_total"] += r["accrued_total"]
        g["compensation_total"] += r["compensation_total"]
        g["withheld_total"] += r["withheld_total"]
        g["net_total"] += r["net_total"]

    result = list(grouped.values())
    for g in result:
        g["avg_accrued"] = (g["accrued_total"] / g["employees_count"]).quantize(Decimal("0.01")) if g["employees_count"] else Decimal("0.00")
        g["share_pct"] = ((g["accrued_total"] / total_accrued_all) * Decimal("100")).quantize(Decimal("0.1")) if total_accrued_all else Decimal("0.0")

    result.sort(key=lambda x: x["accrued_total"], reverse=True)
    return result


def _avg_non_empty(values: List[Decimal | None]) -> Decimal | None:
    """Считает среднее по непустым месяцам начисления (для корректного расчёта по уволенным и принятым)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return (sum(present, Decimal("0.00")) / Decimal(len(present))).quantize(Decimal("0.01"))


def _build_fns_avg_salary_report(year: int, staff_category_id: str = "", search: str = "") -> Dict[str, Any]:
    """Строит отчёт о средней зарплате по данным КНД 1151162 с разбивкой по группам персонала.

    Включает всех сотрудников группы за год (в т.ч. уволенных — по месяцам начисления).
    """
    latest_batches: Dict[int, int] = {}
    for b in PayrollReportBatch.objects.filter(year=year).order_by("month", "-correction_number", "-uploaded_at"):
        latest_batches.setdefault(b.month, b.pk)

    if not latest_batches:
        return {"groups": [], "chart_data": {"months": list(MONTH_NAMES_RU.values()), "line_datasets": [], "quarter_datasets": [], "pie_labels": [], "pie_values": []}}

    lines = (
        PayrollFnsLine.objects.filter(batch_id__in=latest_batches.values())
        .select_related(
            "batch",
            "employee",
            "employee__user_work_profile__job",
            "employee__user_work_profile__job__staff_category",
            "employee__user_work_profile__staff_category",
        )
    )

    people: Dict[str, Dict[str, Any]] = {}
    for line in lines:
        key = line.person_ref_key or (f"snils:{normalize_snils(line.snils)}" if normalize_snils(line.snils) else f"fio:{line.full_name}")
        emp = line.employee
        if key not in people:
            cat = emp.get_staff_category() if emp else None
            job_name = str(emp.user_work_profile.job) if emp and emp.user_work_profile and emp.user_work_profile.job else ""
            people[key] = {
                "person_key": key,
                "full_name": line.full_name or (str(emp) if emp else "Неизвестно"),
                "job": job_name,
                "is_active": emp.is_active if emp else False,
                "staff_category_id": cat.pk if cat else None,
                "staff_category_name": cat.short_name if cat else "Без категории",
                "staff_category_order": cat.sort_order if cat else 9999,
                "months": {m: None for m in range(1, 13)},
            }
        m = line.batch.month
        cur = people[key]["months"][m]
        people[key]["months"][m] = (cur or Decimal("0.00")) + line.total_amount

    rows = list(people.values())
    if staff_category_id:
        if staff_category_id == "none":
            rows = [r for r in rows if r["staff_category_id"] is None]
        elif staff_category_id.isdigit():
            cat_int = int(staff_category_id)
            rows = [r for r in rows if r["staff_category_id"] == cat_int]

    if search:
        q = search.strip().lower()
        rows = [r for r in rows if q in r["full_name"].lower() or q in r["job"].lower()]

    groups_map: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        ms = [r["months"][m] for m in range(1, 13)]
        r["months_list"] = ms
        r["q1"] = _avg_non_empty(ms[0:3])
        r["q2"] = _avg_non_empty(ms[3:6])
        r["q3"] = _avg_non_empty(ms[6:9])
        r["q4"] = _avg_non_empty(ms[9:12])
        r["h1"] = _avg_non_empty(ms[0:6])
        r["h2"] = _avg_non_empty(ms[6:12])
        r["year_avg"] = _avg_non_empty(ms)

        gname = r["staff_category_name"]
        if gname not in groups_map:
            groups_map[gname] = {
                "name": gname,
                "order": r["staff_category_order"],
                "rows": [],
            }
        groups_map[gname]["rows"].append(r)

    groups = sorted(groups_map.values(), key=lambda g: (g["order"], g["name"]))

    palette = ["#0d6efd", "#198754", "#fd7e14", "#6f42c1", "#6c757d"]
    line_datasets = []
    quarter_datasets = []
    pie_labels = []
    pie_values = []

    for idx_g, g in enumerate(groups):
        g["rows"].sort(key=lambda x: x["full_name"])
        for idx_r, r in enumerate(g["rows"], start=1):
            r["num"] = idx_r

        g["avg_months"] = [_avg_non_empty([r["months"][m] for r in g["rows"]]) for m in range(1, 13)]
        g["avg_q1"] = _avg_non_empty([r["q1"] for r in g["rows"]])
        g["avg_q2"] = _avg_non_empty([r["q2"] for r in g["rows"]])
        g["avg_q3"] = _avg_non_empty([r["q3"] for r in g["rows"]])
        g["avg_q4"] = _avg_non_empty([r["q4"] for r in g["rows"]])
        g["avg_h1"] = _avg_non_empty([r["h1"] for r in g["rows"]])
        g["avg_h2"] = _avg_non_empty([r["h2"] for r in g["rows"]])
        g["avg_year"] = _avg_non_empty([r["year_avg"] for r in g["rows"]])

        color = palette[idx_g % len(palette)]
        line_datasets.append({
            "label": g["name"],
            "data": [float(v) if v is not None else None for v in g["avg_months"]],
            "borderColor": color,
            "backgroundColor": color,
            "tension": 0.25,
            "spanGaps": True,
        })
        quarter_datasets.append({
            "label": g["name"],
            "data": [
                float(g["avg_q1"] or 0),
                float(g["avg_q2"] or 0),
                float(g["avg_q3"] or 0),
                float(g["avg_q4"] or 0),
            ],
            "backgroundColor": color,
        })
        total_group_sum = sum(
            (v for r in g["rows"] for v in r["months_list"] if v is not None),
            Decimal("0.00"),
        )
        pie_labels.append(g["name"])
        pie_values.append(float(total_group_sum))

    return {
        "groups": groups,
        "chart_data": {
            "months": [MONTH_NAMES_RU[m] for m in range(1, 13)],
            "line_datasets": line_datasets,
            "quarter_datasets": quarter_datasets,
            "pie_labels": pie_labels,
            "pie_values": pie_values,
        },
    }


def _build_shmakov_report(year: int) -> Dict[str, Any]:
    """Строит сравнительный отчёт для Шмакова Д.А. (текущий год vs предыдущий год) по КНД 1151162.

    Показывает сумму ФОТ, количество человек и долю (%) в каждой группе за оба года.
    Сотрудники по ГПХ (freelancer) и без назначенной категории автоматически относятся к 'Прочий персонал'.
    """
    prev_year = year - 1
    fixed_groups = ["АУП", "ИТП", "ЧЛЭ", "Прочий персонал"]
    extra_cats = list(
        StaffCategory.objects.filter(is_active=True)
        .exclude(short_name__in=fixed_groups)
        .order_by("sort_order", "name")
        .values_list("short_name", flat=True)
    )
    group_names = fixed_groups + extra_cats

    def _collect_year_data(target_year: int) -> Dict[int, Dict[str, Any]]:
        latest_batches: Dict[int, int] = {}
        for b in PayrollReportBatch.objects.filter(year=target_year).order_by("month", "-correction_number", "-uploaded_at"):
            latest_batches.setdefault(b.month, b.pk)

        month_data: Dict[int, Dict[str, Any]] = {
            m: {
                "groups": {g: {"amount": Decimal("0.00"), "people": set(), "count": 0, "share_pct": Decimal("0.0")} for g in group_names},
                "total_amount": Decimal("0.00"),
                "total_count": 0,
            }
            for m in range(1, 13)
        }
        if not latest_batches:
            return month_data

        lines = (
            PayrollFnsLine.objects.filter(batch_id__in=latest_batches.values())
            .select_related(
                "batch",
                "employee",
                "employee__user_work_profile__job__staff_category",
                "employee__user_work_profile__staff_category",
            )
        )
        for line in lines:
            m = line.batch.month
            emp = line.employee
            cat = emp.get_staff_category() if emp else None
            if not emp or emp.type_users == "freelancer" or not cat:
                gname = "Прочий персонал"
            else:
                gname = cat.short_name if cat.short_name in month_data[m]["groups"] else "Прочий персонал"

            pkey = line.person_ref_key or (f"snils:{normalize_snils(line.snils)}" if normalize_snils(line.snils) else f"fio:{line.full_name}")
            month_data[m]["groups"][gname]["amount"] += line.total_amount
            month_data[m]["groups"][gname]["people"].add(pkey)
            month_data[m]["total_amount"] += line.total_amount

        for m in range(1, 13):
            total_people = sum(len(month_data[m]["groups"][g]["people"]) for g in group_names)
            month_data[m]["total_count"] = total_people
            for g in group_names:
                cnt = len(month_data[m]["groups"][g]["people"])
                month_data[m]["groups"][g]["count"] = cnt
                month_data[m]["groups"][g]["share_pct"] = (
                    (Decimal(cnt) / Decimal(total_people) * Decimal("100")).quantize(Decimal("0.1"))
                    if total_people else Decimal("0.0")
                )
        return month_data

    prev_data = _collect_year_data(prev_year)
    curr_data = _collect_year_data(year)

    months_rows = []
    for m in range(1, 13):
        p_m = prev_data[m]
        c_m = curr_data[m]
        if p_m["total_count"] == 0 and c_m["total_count"] == 0:
            continue
        group_cells = []
        for g in group_names:
            p_g = p_m["groups"][g]
            c_g = c_m["groups"][g]
            diff_amt = c_g["amount"] - p_g["amount"]
            diff_pct = (
                ((diff_amt / p_g["amount"]) * Decimal("100")).quantize(Decimal("0.1"))
                if p_g["amount"] else None
            )
            group_cells.append({
                "name": g,
                "prev_amount": p_g["amount"],
                "prev_count": p_g["count"],
                "prev_share": p_g["share_pct"],
                "curr_amount": c_g["amount"],
                "curr_count": c_g["count"],
                "curr_share": c_g["share_pct"],
                "diff_amount": diff_amt,
                "diff_pct": diff_pct,
            })
        months_rows.append({
            "month": m,
            "month_name": MONTH_NAMES_RU[m],
            "groups": group_cells,
            "prev_total_amount": p_m["total_amount"],
            "prev_total_count": p_m["total_count"],
            "curr_total_amount": c_m["total_amount"],
            "curr_total_count": c_m["total_count"],
        })

    # Итого за год по каждой группе
    year_totals = []
    for idx_g, g in enumerate(group_names):
        p_sum = sum((r["groups"][idx_g]["prev_amount"] for r in months_rows), Decimal("0.00"))
        c_sum = sum((r["groups"][idx_g]["curr_amount"] for r in months_rows), Decimal("0.00"))
        p_avg_cnt = (
            (sum((Decimal(r["groups"][idx_g]["prev_count"]) for r in months_rows), Decimal("0")) / Decimal(len(months_rows))).quantize(Decimal("0.1"))
            if months_rows else Decimal("0.0")
        )
        c_avg_cnt = (
            (sum((Decimal(r["groups"][idx_g]["curr_count"]) for r in months_rows), Decimal("0")) / Decimal(len(months_rows))).quantize(Decimal("0.1"))
            if months_rows else Decimal("0.0")
        )
        year_totals.append({
            "name": g,
            "prev_amount": p_sum,
            "curr_amount": c_sum,
            "prev_avg_count": p_avg_cnt,
            "curr_avg_count": c_avg_cnt,
        })

    palette = ["#0d6efd", "#198754", "#fd7e14", "#6f42c1", "#6c757d"]
    monthly_share_datasets_curr = []
    monthly_share_datasets_prev = []
    for idx_g, g in enumerate(group_names):
        color = palette[idx_g % len(palette)]
        monthly_share_datasets_curr.append({
            "label": g,
            "data": [float(r["groups"][idx_g]["curr_share"]) for r in months_rows],
            "counts": [r["groups"][idx_g]["curr_count"] for r in months_rows],
            "backgroundColor": color,
        })
        monthly_share_datasets_prev.append({
            "label": g,
            "data": [float(r["groups"][idx_g]["prev_share"]) for r in months_rows],
            "counts": [r["groups"][idx_g]["prev_count"] for r in months_rows],
            "backgroundColor": color,
        })

    chart = {
        "labels": [r["month_name"] for r in months_rows],
        "prev_totals": [float(r["prev_total_amount"]) for r in months_rows],
        "curr_totals": [float(r["curr_total_amount"]) for r in months_rows],
        "prev_counts": [r["prev_total_count"] for r in months_rows],
        "curr_counts": [r["curr_total_count"] for r in months_rows],
        "group_names": group_names,
        "monthly_share_datasets_curr": monthly_share_datasets_curr,
        "monthly_share_datasets_prev": monthly_share_datasets_prev,
        "raw_table": {
            "prev_year": prev_year,
            "curr_year": year,
            "group_names": group_names,
            "months": [
                {
                    "month": r["month"],
                    "month_name": r["month_name"],
                    "groups": {
                        gc["name"]: {
                            "prev": float(gc["prev_amount"]),
                            "curr": float(gc["curr_amount"]),
                        }
                        for gc in r["groups"]
                    },
                }
                for r in months_rows
            ],
        },
    }

    return {
        "prev_year": prev_year,
        "curr_year": year,
        "group_names": group_names,
        "months_rows": months_rows,
        "year_totals": year_totals,
        "chart": chart,
    }


def _build_executive_charts_data(
    year: int,
    odata_qs,
    category_summary: List[Dict[str, Any]],
    avg_salary_groups: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Формирует управленческие графики для руководства по данным 1С OData и КНД 1151162."""
    excluded_keys = _get_excluded_calc_keys()

    # 1. Топ видов начислений (без выделенных компенсаций)
    accrual_totals: Dict[str, Decimal] = {}
    # 2. Топ подразделений по ФОТ
    division_totals: Dict[str, Decimal] = {}
    # 3. Помесячная динамика 1С (Начислено ЗП, Удержано/НДФЛ, Компенсация питания)
    monthly_1c = {
        m: {"accrued": Decimal("0.00"), "withheld": Decimal("0.00"), "comp": Decimal("0.00")}
        for m in range(1, 13)
    }

    for det in odata_qs.select_related("division", "employee__user_work_profile__divisions"):
        if det.group_type == "Начислено":
            is_exc = _is_excluded_detail(det, excluded_keys)
            if is_exc:
                monthly_1c[det.month]["comp"] += det.amount
            else:
                monthly_1c[det.month]["accrued"] += det.amount
                cname = det.calculation_type_name or "Прочее"
                accrual_totals[cname] = accrual_totals.get(cname, Decimal("0.00")) + det.amount

                div_name = ""
                if det.division:
                    div_name = str(det.division)
                elif det.employee and det.employee.user_work_profile and det.employee.user_work_profile.divisions:
                    div_name = str(det.employee.user_work_profile.divisions)
                else:
                    div_name = "Не указано"
                division_totals[div_name] = division_totals.get(div_name, Decimal("0.00")) + det.amount
        elif det.group_type == "Удержано" or det.calculation_category in ("Удержания", "НДФЛ"):
            monthly_1c[det.month]["withheld"] += det.amount

    sorted_accruals = sorted(accrual_totals.items(), key=lambda x: x[1], reverse=True)
    top_accruals = sorted_accruals[:8]
    other_accruals_sum = sum((v for _, v in sorted_accruals[8:]), Decimal("0.00"))
    if other_accruals_sum > 0:
        top_accruals.append(("Прочие начисления", other_accruals_sum))

    sorted_divisions = sorted(division_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    # 4. ФОТ по месяцам в разрезе категорий (по фактическим суммам КНД 1151162)
    palette = ["#0d6efd", "#198754", "#fd7e14", "#6f42c1", "#6c757d"]
    cat_fot_datasets = []
    for idx_g, g in enumerate(avg_salary_groups):
        month_sums = [Decimal("0.00")] * 12
        for r in g["rows"]:
            for m_idx, val in enumerate(r["months_list"]):
                if val is not None:
                    month_sums[m_idx] += val
        cat_fot_datasets.append({
            "label": g["name"],
            "data": [float(v) for v in month_sums],
            "backgroundColor": palette[idx_g % len(palette)],
        })

    return {
        "months": [MONTH_NAMES_RU[m] for m in range(1, 13)],
        "accrual_labels": [k for k, _ in top_accruals],
        "accrual_values": [float(v) for _, v in top_accruals],
        "division_labels": [k for k, _ in sorted_divisions],
        "division_values": [float(v) for _, v in sorted_divisions],
        "monthly_accrued": [float(monthly_1c[m]["accrued"]) for m in range(1, 13)],
        "monthly_withheld": [float(monthly_1c[m]["withheld"]) for m in range(1, 13)],
        "monthly_comp": [float(monthly_1c[m]["comp"]) for m in range(1, 13)],
        "pie_labels": [c["name"] for c in category_summary],
        "pie_values": [float(c["fns_total"] or c["accrued_total"]) for c in category_summary],
        "cat_fot_datasets": cat_fot_datasets,
    }


@login_required
def payroll_reports_dashboard(request: HttpRequest) -> HttpResponse:
    """Главная страница аналитики начислений (КНД 1151162 + 1С OData read-only)."""
    access_level = _require_payroll_reports_access(request)

    year, month = _get_selected_period(request)
    division_id = (request.GET.get("division") or "").strip()
    staff_category_id = (request.GET.get("staff_category") or "").strip()
    search = (request.GET.get("q") or "").strip()

    odata_qs = PayrollODataDetail.objects.filter(year=year)
    if month:
        odata_qs = odata_qs.filter(month=month)
    if division_id and division_id.isdigit():
        odata_qs = odata_qs.filter(Q(division_id=int(division_id)) | Q(employee__user_work_profile__divisions_id=int(division_id)))
    if search:
        odata_qs = odata_qs.filter(
            Q(employee__last_name__icontains=search)
            | Q(employee__first_name__icontains=search)
            | Q(calculation_type_name__icontains=search)
        )

    excluded_keys = _get_excluded_calc_keys()
    calc_breakdown = list(
        odata_qs.values("calculation_category", "group_type", "calculation_type_key", "calculation_type_name")
        .annotate(total=Sum("amount"), records=Count("id"))
        .order_by("calculation_category", "-total")
    )
    for item in calc_breakdown:
        item["is_excluded"] = (
            item["calculation_type_key"] in excluded_keys
            or "компенсация питания" in (item["calculation_type_name"] or "").lower()
        )

    employee_rows = _build_employee_summary_rows(
        year=year,
        month=month,
        division_id=division_id,
        search=search,
        staff_category_id=staff_category_id,
    )
    category_summary = _build_category_summary(employee_rows)
    avg_salary_report = _build_fns_avg_salary_report(
        year=year,
        staff_category_id=staff_category_id,
        search=search,
    )
    shmakov_report = _build_shmakov_report(year=year)
    exec_charts = _build_executive_charts_data(
        year=year,
        odata_qs=odata_qs,
        category_summary=category_summary,
        avg_salary_groups=avg_salary_report["groups"],
    )

    kpi = {
        "fns_total": sum((r["fns_total"] for r in employee_rows), Decimal("0.00")),
        "accrued_total": sum((r["accrued_total"] for r in employee_rows), Decimal("0.00")),
        "compensation_total": sum((r["compensation_total"] for r in employee_rows), Decimal("0.00")),
        "withheld_total": sum((r["withheld_total"] for r in employee_rows), Decimal("0.00")),
        "employees_count": len(employee_rows),
    }
    kpi["net_total"] = kpi["accrued_total"] - kpi["withheld_total"]

    batches = PayrollReportBatch.objects.filter(year=year).order_by("-month", "-correction_number", "-uploaded_at")
    divisions = Division.objects.filter(active=True).order_by("name")
    staff_categories = StaffCategory.objects.filter(is_active=True).order_by("sort_order", "name")
    available_years = sorted(
        {datetime.date.today().year, datetime.date.today().year - 1}
        | set(PayrollReportBatch.objects.values_list("year", flat=True))
        | set(PayrollODataDetail.objects.values_list("year", flat=True)),
        reverse=True,
    )

    return render(
        request,
        "customers_app/payroll_reports_dashboard.html",
        {
            "title": "Аналитика начислений и отчёты (КНД 1151162 + 1С)",
            "year": year,
            "month": month,
            "month_choices": MONTH_NAMES_RU,
            "available_years": available_years,
            "divisions": divisions,
            "selected_division": division_id,
            "staff_categories": staff_categories,
            "selected_staff_category": staff_category_id,
            "search": search,
            "calc_breakdown": calc_breakdown,
            "employee_rows": employee_rows,
            "category_summary": category_summary,
            "avg_salary_groups": avg_salary_report["groups"],
            "chart_data_json": json.dumps(exec_charts, ensure_ascii=False),
            "shmakov_report": shmakov_report,
            "shmakov_chart_json": json.dumps(shmakov_report["chart"], ensure_ascii=False),
            "shmakov_raw_json": json.dumps(shmakov_report["chart"]["raw_table"], ensure_ascii=False),
            "kpi": kpi,
            "batches": batches,
            "can_manage_payroll": access_level == "full",
        },
    )


@login_required
@require_POST
def payroll_upload_xml(request: HttpRequest) -> HttpResponse:
    """Загружает один или несколько XML-файлов ФНС КНД 1151162 в БД."""
    from django.urls import reverse

    _require_payroll_reports_access(request, require_full=True)

    uploaded_files = request.FILES.getlist("xml_file")
    if not uploaded_files:
        messages.error(request, "Выберите один или несколько XML-файлов КНД 1151162 для загрузки.")
        return redirect("customers_app:payroll_reports_dashboard")

    loaded_count = 0
    total_lines_all = 0
    matched_lines_all = 0
    errors: List[str] = []

    for uploaded_file in uploaded_files:
        try:
            batch, total_lines, matched_lines = import_knd_1151162_xml(
                xml_bytes=uploaded_file.read(),
                filename=uploaded_file.name,
                user=request.user,
            )
            loaded_count += 1
            total_lines_all += total_lines
            matched_lines_all += matched_lines
        except Exception as exc:
            errors.append(f"{uploaded_file.name}: {exc}")

    if loaded_count:
        messages.success(
            request,
            f"Загружено файлов: {loaded_count} из {len(uploaded_files)}. "
            f"Всего строк: {total_lines_all}, сопоставлено с порталом: {matched_lines_all}.",
        )
    if errors:
        messages.warning(
            request,
            "Не загружены следующие файлы: " + "; ".join(errors[:10])
            + (f" (и ещё {len(errors) - 10})" if len(errors) > 10 else ""),
        )

    return redirect(f"{reverse('customers_app:payroll_reports_dashboard')}?tab=import")


@login_required
@require_POST
def payroll_sync_odata(request: HttpRequest) -> HttpResponse:
    """Запускает read-only (GET) синхронизацию детализации начислений из 1С ЗУП за выбранный месяц."""
    _require_payroll_reports_access(request, require_full=True)

    try:
        year = int(request.POST.get("year") or datetime.date.today().year)
        month = int(request.POST.get("month") or datetime.date.today().month)
        if not (1 <= month <= 12):
            raise ValueError("Выберите конкретный месяц (1–12) для синхронизации с 1С.")
        result = sync_1c_odata_payroll_month(year=year, month=month)
        messages.success(
            request,
            f"1С OData (только чтение) за {month:02d}.{year}: получено {result['raw_count']} проводок, "
            f"сохранено {result['saved_count']} агрегированных строк.",
        )
    except Exception as exc:
        messages.error(request, f"Ошибка синхронизации с 1С OData: {exc}")
        return redirect("customers_app:payroll_reports_dashboard")

    from django.urls import reverse

    return redirect(f"{reverse('customers_app:payroll_reports_dashboard')}?year={year}&month={month}")


@login_required
def payroll_employee_card(request: HttpRequest, person_key: str) -> HttpResponse:
    """Карточка начислений и динамика по конкретному человеку (склейка по person_ref_key / СНИЛС)."""
    _require_payroll_reports_access(request)

    year, month = _get_selected_period(request)

    if person_key.startswith("snils:"):
        raw_snils = person_key.split(":", 1)[1]
        fns_qs = PayrollFnsLine.objects.filter(batch__year=year).select_related("batch", "employee")
        fns_lines = [l for l in fns_qs if normalize_snils(l.snils) == raw_snils]
        odata_qs = PayrollODataDetail.objects.none()
    elif person_key.startswith("emp:"):
        emp_ref = person_key.split(":", 1)[1]
        fns_lines = list(PayrollFnsLine.objects.filter(batch__year=year, employee__ref_key=emp_ref).select_related("batch", "employee"))
        odata_qs = PayrollODataDetail.objects.filter(year=year, employee_ref_key=emp_ref).select_related("division", "employee")
    elif person_key.startswith("fio:"):
        fio_val = person_key.split(":", 1)[1]
        fns_lines = list(PayrollFnsLine.objects.filter(batch__year=year, full_name=fio_val).select_related("batch", "employee"))
        odata_qs = PayrollODataDetail.objects.none()
    else:
        fns_lines = list(PayrollFnsLine.objects.filter(batch__year=year, person_ref_key=person_key).select_related("batch", "employee"))
        odata_qs = PayrollODataDetail.objects.filter(year=year, person_ref_key=person_key).select_related("division", "employee")

    # Помесячная динамика
    monthly_map: Dict[int, Dict[str, Any]] = {
        m: {
            "month": m,
            "month_name": MONTH_NAMES_RU[m],
            "fns": Decimal("0.00"),
            "accrued": Decimal("0.00"),
            "compensation": Decimal("0.00"),
            "withheld": Decimal("0.00"),
            "net": Decimal("0.00"),
        }
        for m in range(1, 13)
    }

    latest_fns_by_month: Dict[int, PayrollFnsLine] = {}
    for line in sorted(fns_lines, key=lambda x: (x.batch.month, x.batch.correction_number, x.batch.uploaded_at)):
        latest_fns_by_month[line.batch.month] = line
    for m, line in latest_fns_by_month.items():
        monthly_map[m]["fns"] = line.total_amount

    excluded_keys = _get_excluded_calc_keys()
    for det in odata_qs:
        if det.group_type == "Начислено":
            if _is_excluded_detail(det, excluded_keys):
                monthly_map[det.month]["compensation"] += det.amount
            else:
                monthly_map[det.month]["accrued"] += det.amount
        elif det.group_type == "Удержано" or det.calculation_category in ("Удержания", "НДФЛ"):
            monthly_map[det.month]["withheld"] += det.amount

    monthly_rows = []
    for m in range(1, 13):
        row = monthly_map[m]
        row["net"] = row["accrued"] - row["withheld"]
        if row["fns"] or row["accrued"] or row["compensation"] or row["withheld"]:
            monthly_rows.append(row)

    detail_qs = odata_qs.filter(month=month) if month else odata_qs
    calc_items = list(
        detail_qs.values("calculation_category", "group_type", "calculation_type_key", "calculation_type_name")
        .annotate(total=Sum("amount"))
        .order_by("calculation_category", "-total")
    )
    for item in calc_items:
        item["is_excluded"] = (
            item["calculation_type_key"] in excluded_keys
            or "компенсация питания" in (item["calculation_type_name"] or "").lower()
        )

    sample_emp = next((l.employee for l in fns_lines if l.employee), None) or next((d.employee for d in odata_qs if d.employee), None)
    person_title = (
        (str(sample_emp) if sample_emp else None)
        or (fns_lines[0].full_name if fns_lines else None)
        or person_key
    )

    return render(
        request,
        "customers_app/payroll_employee_card.html",
        {
            "title": f"Карточка начислений: {person_title}",
            "person_key": person_key,
            "person_title": person_title,
            "employee": sample_emp,
            "year": year,
            "month": month,
            "month_choices": MONTH_NAMES_RU,
            "monthly_rows": monthly_rows,
            "calc_items": calc_items,
            "total_fns": sum((r["fns"] for r in monthly_rows), Decimal("0.00")),
            "total_accrued": sum((r["accrued"] for r in monthly_rows), Decimal("0.00")),
            "total_compensation": sum((r["compensation"] for r in monthly_rows), Decimal("0.00")),
            "total_withheld": sum((r["withheld"] for r in monthly_rows), Decimal("0.00")),
            "total_net": sum((r["net"] for r in monthly_rows), Decimal("0.00")),
        },
    )


@login_required
def payroll_export_excel(request: HttpRequest) -> HttpResponse:
    """Экспортирует сводный отчёт и детализацию видов расчёта в Excel (.xlsx)."""
    _require_payroll_reports_access(request)

    year, month = _get_selected_period(request)
    division_id = (request.GET.get("division") or "").strip()
    staff_category_id = (request.GET.get("staff_category") or "").strip()
    search = (request.GET.get("q") or "").strip()

    rows = _build_employee_summary_rows(
        year=year,
        month=month,
        division_id=division_id,
        search=search,
        staff_category_id=staff_category_id,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сотрудники"
    ws.append(["ФИО", "Категория", "СНИЛС", "ИНН", "Подразделение", "Должность", "КНД 1151162 (ФНС)", "Начислено ЗП (1С)", "Компенсация питания / отдельно (1С)", "Удержано (1С)", "К выплате (ЗП)", "Разница (ФНС - ЗП 1С)"])

    for r in rows:
        ws.append([
            r["full_name"],
            r["staff_category_name"],
            r["snils"],
            r["inn"],
            r["division"],
            r["job"],
            float(r["fns_total"]),
            float(r["accrued_total"]),
            float(r["compensation_total"]),
            float(r["withheld_total"]),
            float(r["net_total"]),
            float(r["diff_fns_accrued"]),
        ])

    ws_cat = wb.create_sheet("Свод по категориям")
    ws_cat.append(["Категория", "Сотрудников", "КНД 1151162 (ФНС)", "Начислено ЗП (1С)", "Средняя ЗП", "Доля ФОТ %", "Компенсация (отд.)", "Удержано", "К выплате"])
    for c in _build_category_summary(rows):
        ws_cat.append([
            c["name"],
            c["employees_count"],
            float(c["fns_total"]),
            float(c["accrued_total"]),
            float(c["avg_accrued"]),
            float(c["share_pct"]),
            float(c["compensation_total"]),
            float(c["withheld_total"]),
            float(c["net_total"]),
        ])

    ws_avg = wb.create_sheet("Средняя ЗП (КНД 1151162)")
    avg_report = _build_fns_avg_salary_report(year=year, staff_category_id=staff_category_id, search=search)
    ws_avg.append([
        "Категория", "№ п/п", "ФИО", "Должность", "Статус",
        "Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
        "1 кв (ср.)", "2 кв (ср.)", "3 кв (ср.)", "4 кв (ср.)", "1 полуг. (ср.)", "2 полуг. (ср.)", "За год (ср.)",
    ])
    for g in avg_report["groups"]:
        for r in g["rows"]:
            ws_avg.append([
                g["name"],
                r["num"],
                r["full_name"],
                r["job"],
                "Активен" if r["is_active"] else "Уволен/архив",
                *[float(v) if v is not None else None for v in r["months_list"]],
                float(r["q1"]) if r["q1"] is not None else None,
                float(r["q2"]) if r["q2"] is not None else None,
                float(r["q3"]) if r["q3"] is not None else None,
                float(r["q4"]) if r["q4"] is not None else None,
                float(r["h1"]) if r["h1"] is not None else None,
                float(r["h2"]) if r["h2"] is not None else None,
                float(r["year_avg"]) if r["year_avg"] is not None else None,
            ])

    ws_shm = wb.create_sheet("Динамика ФОТ (год к году)")
    shm = _build_shmakov_report(year=year)
    shm_header = ["Месяц"]
    for g in shm["group_names"]:
        shm_header.extend([
            f"{g} ({shm['prev_year']} ₽)", f"{g} ({shm['prev_year']} чел.)", f"{g} ({shm['prev_year']} %)",
            f"{g} ({shm['curr_year']} ₽)", f"{g} ({shm['curr_year']} чел.)", f"{g} ({shm['curr_year']} %)",
        ])
    shm_header.extend([
        f"Всего {shm['prev_year']} ₽", f"Всего {shm['prev_year']} чел.",
        f"Всего {shm['curr_year']} ₽", f"Всего {shm['curr_year']} чел.",
    ])
    ws_shm.append(shm_header)
    for r in shm["months_rows"]:
        row_vals = [r["month_name"]]
        for gc in r["groups"]:
            row_vals.extend([
                float(gc["prev_amount"]), gc["prev_count"], float(gc["prev_share"]),
                float(gc["curr_amount"]), gc["curr_count"], float(gc["curr_share"]),
            ])
        row_vals.extend([
            float(r["prev_total_amount"]), r["prev_total_count"],
            float(r["curr_total_amount"]), r["curr_total_count"],
        ])
        ws_shm.append(row_vals)

    ws_calc = wb.create_sheet("Виды начислений и удержаний")
    ws_calc.append(["Категория", "Группа", "Вид расчёта", "Сумма"])
    odata_qs = PayrollODataDetail.objects.filter(year=year)
    if month:
        odata_qs = odata_qs.filter(month=month)
    for item in odata_qs.values("calculation_category", "group_type", "calculation_type_name").annotate(total=Sum("amount")).order_by("calculation_category", "-total"):
        ws_calc.append([item["calculation_category"], item["group_type"], item["calculation_type_name"], float(item["total"] or 0)])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    period_label = f"{year}_{month:02d}" if month else str(year)
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="payroll_report_{period_label}.xlsx"'
    return response


@login_required
@require_POST
def payroll_delete_batch(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Удаляет загруженный пакет КНД 1151162."""
    _require_payroll_reports_access(request, require_full=True)
    batch = get_object_or_404(PayrollReportBatch, pk=batch_id)
    batch.delete()
    messages.success(request, "Загруженный файл отчёта удалён.")
    return redirect("customers_app:payroll_reports_dashboard")
