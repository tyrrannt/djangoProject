# -*- coding: utf-8 -*-
"""Сервисный слой аналитики начислений: парсинг XML КНД 1151162 и read-only синхронизация с 1С OData."""

import datetime
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import requests
from decouple import config
from django.db import transaction

from customers_app.models import (
    DataBaseUser,
    Division,
    PayrollCalculationTypeCache,
    PayrollFnsLine,
    PayrollODataDetail,
    PayrollReportBatch,
)

ODATA_1C_ZUP_BASE = "http://{host}/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata"


def normalize_snils(value: str) -> str:
    """Оставляет только цифры СНИЛС (11 символов) для надёжного сопоставления."""
    return re.sub(r"\D+", "", value or "")


def _parse_decimal(raw: Any) -> Decimal:
    """Безопасно преобразует строку/число в Decimal."""
    if raw is None or raw == "":
        return Decimal("0.00")
    try:
        return Decimal(str(raw).replace(",", ".").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _parse_ru_date(raw: str) -> Optional[datetime.date]:
    """Парсит дату формата ДД.ММ.ГГГГ из XML ФНС."""
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def match_employee_for_report(
    snils: str = "",
    inn: str = "",
    last_name: str = "",
    first_name: str = "",
    surname: str = "",
    person_ref_key: str = "",
    employee_ref_key: str = "",
) -> Tuple[Optional[DataBaseUser], str]:
    """Сопоставляет запись отчёта с сотрудником портала (предпочитая активную учётку).

    Returns:
        Tuple[Optional[DataBaseUser], str]: Найденный ``DataBaseUser`` и ``person_ref_key``.
    """
    qs = DataBaseUser.objects.select_related("user_profile", "user_work_profile").order_by("-is_active", "-id")

    if employee_ref_key and employee_ref_key != "00000000-0000-0000-0000-000000000000":
        emp = qs.filter(ref_key=employee_ref_key).first()
        if emp:
            return emp, emp.person_ref_key or person_ref_key

    if person_ref_key and person_ref_key != "00000000-0000-0000-0000-000000000000":
        emp = qs.filter(person_ref_key=person_ref_key).first()
        if emp:
            return emp, emp.person_ref_key or person_ref_key

    norm_snils = normalize_snils(snils)
    if norm_snils:
        formatted_snils = f"{norm_snils[:3]}-{norm_snils[3:6]}-{norm_snils[6:9]} {norm_snils[9:11]}" if len(norm_snils) == 11 else snils
        emp = qs.filter(user_profile__snils__in=[snils.strip(), formatted_snils, norm_snils]).first()
        if not emp and len(norm_snils) == 11:
            for candidate in qs.exclude(user_profile__snils="").iterator():
                if candidate.user_profile and normalize_snils(candidate.user_profile.snils) == norm_snils:
                    emp = candidate
                    break
        if emp:
            return emp, emp.person_ref_key or person_ref_key

    clean_inn = (inn or "").strip()
    if clean_inn:
        emp = qs.filter(user_profile__inn=clean_inn).first()
        if emp:
            return emp, emp.person_ref_key or person_ref_key

    if last_name and first_name:
        emp = qs.filter(
            last_name__iexact=last_name.strip(),
            first_name__iexact=first_name.strip(),
            surname__iexact=(surname or "").strip(),
        ).first()
        if emp:
            return emp, emp.person_ref_key or person_ref_key

    return None, person_ref_key


def parse_knd_1151162_xml(xml_bytes: bytes) -> Dict[str, Any]:
    """Парсит XML-файл ФНС КНД 1151162 (Персонифицированные сведения о физлицах)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Некорректный XML-файл: {exc}") from exc

    if root.tag != "Файл":
        raise ValueError("Корневой элемент XML должен быть <Файл>.")

    doc_el = root.find("Документ")
    if doc_el is None:
        raise ValueError("В XML отсутствует элемент <Документ>.")

    knd = doc_el.attrib.get("КНД", "")
    if knd != "1151162":
        raise ValueError(f"Ожидался отчёт КНД 1151162, получен КНД '{knd}'.")

    np_el = doc_el.find("СвНП/НПЮЛ")
    meta = {
        "file_id": root.attrib.get("ИдФайл", "").strip(),
        "year": int(doc_el.attrib.get("ОтчетГод", 0) or 0),
        "month": int(doc_el.attrib.get("Период", 0) or 0),
        "correction_number": int(doc_el.attrib.get("НомКорр", 0) or 0),
        "doc_date": _parse_ru_date(doc_el.attrib.get("ДатаДок", "")),
        "org_name": np_el.attrib.get("НаимОрг", "") if np_el is not None else "",
        "org_inn": np_el.attrib.get("ИННЮЛ", "") if np_el is not None else "",
        "org_kpp": np_el.attrib.get("КПП", "") if np_el is not None else "",
    }
    if not meta["file_id"]:
        raise ValueError("В XML отсутствует атрибут ИдФайл.")
    if not (2000 <= meta["year"] <= 2100) or not (1 <= meta["month"] <= 12):
        raise ValueError(f"Некорректный отчётный период: {meta['month']}.{meta['year']}.")

    lines: List[Dict[str, Any]] = []
    for person_el in doc_el.findall("ПерсСвФЛ"):
        fio_el = person_el.find("ФИО")
        last_name = (fio_el.attrib.get("Фамилия", "") if fio_el is not None else "").strip()
        first_name = (fio_el.attrib.get("Имя", "") if fio_el is not None else "").strip()
        surname = (fio_el.attrib.get("Отчество", "") if fio_el is not None else "").strip()
        full_name = " ".join(part for part in (last_name, first_name, surname) if part)
        lines.append({
            "inn": person_el.attrib.get("ИННФЛ", "").strip(),
            "snils": person_el.attrib.get("СНИЛС", "").strip(),
            "last_name": last_name,
            "first_name": first_name,
            "surname": surname,
            "full_name": full_name,
            "total_amount": _parse_decimal(person_el.attrib.get("СумВыпл", "0")),
        })

    return {"meta": meta, "lines": lines}


@transaction.atomic
def import_knd_1151162_xml(xml_bytes: bytes, filename: str = "", user: Optional[DataBaseUser] = None) -> Tuple[PayrollReportBatch, int, int]:
    """Импортирует XML-файл КНД 1151162 в БД с привязкой к сотрудникам портала.

    Returns:
        Tuple[PayrollReportBatch, int, int]: (batch, total_lines, matched_lines)
    """
    parsed = parse_knd_1151162_xml(xml_bytes)
    meta = parsed["meta"]

    if PayrollReportBatch.objects.filter(file_id=meta["file_id"]).exists():
        raise ValueError(f"Файл с ИдФайл '{meta['file_id']}' уже был загружен ранее.")

    batch = PayrollReportBatch.objects.create(
        file_id=meta["file_id"],
        year=meta["year"],
        month=meta["month"],
        correction_number=meta["correction_number"],
        doc_date=meta["doc_date"],
        org_name=meta["org_name"],
        org_inn=meta["org_inn"],
        org_kpp=meta["org_kpp"],
        raw_filename=filename[:255],
        uploaded_by=user,
    )

    line_objs: List[PayrollFnsLine] = []
    matched = 0
    for row in parsed["lines"]:
        emp, person_key = match_employee_for_report(
            snils=row["snils"],
            inn=row["inn"],
            last_name=row["last_name"],
            first_name=row["first_name"],
            surname=row["surname"],
        )
        if emp:
            matched += 1
        line_objs.append(
            PayrollFnsLine(
                batch=batch,
                employee=emp,
                person_ref_key=person_key,
                inn=row["inn"],
                snils=row["snils"],
                last_name=row["last_name"],
                first_name=row["first_name"],
                surname=row["surname"],
                full_name=row["full_name"],
                total_amount=row["total_amount"],
            )
        )

    PayrollFnsLine.objects.bulk_create(line_objs, batch_size=500)
    return batch, len(line_objs), matched


def _odata_get_all(url: str, auth: Tuple[str, str], params: Optional[Dict[str, str]] = None, page_size: int = 1000) -> List[Dict[str, Any]]:
    """Выполняет строго read-only (GET) выгрузку всех страниц OData 1С."""
    all_rows: List[Dict[str, Any]] = []
    skip = 0
    base_params = dict(params or {})
    base_params["$format"] = "application/json;odata=nometadata"

    while True:
        page_params = dict(base_params)
        page_params["$top"] = str(page_size)
        page_params["$skip"] = str(skip)
        # 1С OData не воспринимает '+' вместо пробела, поэтому кодируем через %20
        query = urlencode(page_params, quote_via=quote)
        resp = requests.get(f"{url}?{query}", auth=auth, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("value", [])
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        skip += page_size

    return all_rows


def sync_calculation_types_cache() -> Dict[str, str]:
    """Обновляет локальный кэш видов начислений и удержаний из 1С (только GET)."""
    host = config("ODATA_1C_HOST", default="192.168.10.11").strip()
    auth = (config("HRM_LOGIN"), config("HRM_PASS"))
    base_url = ODATA_1C_ZUP_BASE.format(host=host)

    mapping: Dict[str, str] = {
        c.ref_key: c.description for c in PayrollCalculationTypeCache.objects.all()
    }

    for kind in ("ChartOfCalculationTypes_Начисления", "ChartOfCalculationTypes_Удержания"):
        rows = _odata_get_all(
            f"{base_url}/{kind}",
            auth=auth,
            params={"$select": "Ref_Key,Description"},
        )
        for row in rows:
            ref_key = (row.get("Ref_Key") or "").strip()
            desc = (row.get("Description") or "").strip()
            if not ref_key:
                continue
            PayrollCalculationTypeCache.objects.update_or_create(
                ref_key=ref_key,
                defaults={"kind": kind, "description": desc},
            )
            mapping[ref_key] = desc

    return mapping


@transaction.atomic
def sync_1c_odata_payroll_month(year: int, month: int) -> Dict[str, Any]:
    """Загружает детализацию начислений и удержаний за месяц из 1С ЗУП (строго GET read-only).

    Агрегирует записи по сотруднику, подразделению, группе и виду расчёта.
    """
    host = config("ODATA_1C_HOST", default="192.168.10.11").strip()
    auth = (config("HRM_LOGIN"), config("HRM_PASS"))
    base_url = ODATA_1C_ZUP_BASE.format(host=host)

    calc_names = sync_calculation_types_cache()

    period_str = f"{year:04d}-{month:02d}-01T00:00:00"
    raw_records = _odata_get_all(
        f"{base_url}/AccumulationRegister_НачисленияУдержанияПоСотрудникам_RecordType",
        auth=auth,
        params={
            "$filter": f"Period eq datetime'{period_str}'",
            "$select": (
                "Active,ФизическоеЛицо_Key,Сотрудник_Key,Подразделение_Key,"
                "НачислениеУдержание,НачислениеУдержание_Type,Сумма,"
                "ГруппаНачисленияУдержанияВыплаты,Сторно"
            ),
        },
    )

    divisions_by_ref = {d.ref_key: d for d in Division.objects.exclude(ref_key="")}
    users_by_ref = {}
    users_by_person = {}
    for u in DataBaseUser.objects.order_by("is_active", "id"):
        if u.ref_key:
            users_by_ref[u.ref_key] = u
        if u.person_ref_key:
            users_by_person[u.person_ref_key] = u

    aggregated: Dict[Tuple[str, str, str, str, str, str, bool], Decimal] = {}
    for rec in raw_records:
        if not rec.get("Active", True):
            continue
        emp_ref = (rec.get("Сотрудник_Key") or "").strip()
        person_ref = (rec.get("ФизическоеЛицо_Key") or "").strip()
        div_ref = (rec.get("Подразделение_Key") or "").strip()
        group_type = (rec.get("ГруппаНачисленияУдержанияВыплаты") or "").strip()
        calc_key = (rec.get("НачислениеУдержание") or "").strip()
        calc_type_str = (rec.get("НачислениеУдержание_Type") or "").strip()
        is_storno = bool(rec.get("Сторно", False))
        amount = _parse_decimal(rec.get("Сумма", 0))

        key = (emp_ref, person_ref, div_ref, group_type, calc_key, calc_type_str, is_storno)
        aggregated[key] = aggregated.get(key, Decimal("0.00")) + amount

    PayrollODataDetail.objects.filter(year=year, month=month).delete()

    detail_objs: List[PayrollODataDetail] = []
    for (emp_ref, person_ref, div_ref, group_type, calc_key, calc_type_str, is_storno), total_amt in aggregated.items():
        if total_amt == Decimal("0.00"):
            continue
        emp = users_by_ref.get(emp_ref) or users_by_person.get(person_ref)
        div = divisions_by_ref.get(div_ref)

        if "Удержания" in calc_type_str:
            category = "Удержания"
        elif "НДФЛ" in calc_type_str or "Налог" in calc_type_str:
            category = "НДФЛ"
        elif "Начисления" in calc_type_str:
            category = "Начисления"
        else:
            category = group_type or "Прочее"

        calc_name = calc_names.get(calc_key) or (
            "НДФЛ" if category == "НДФЛ" else (calc_type_str.replace("StandardODATA.", "") or calc_key or "Не указано")
        )

        detail_objs.append(
            PayrollODataDetail(
                year=year,
                month=month,
                employee=emp,
                person_ref_key=person_ref,
                employee_ref_key=emp_ref,
                division=div,
                division_ref_key=div_ref,
                group_type=group_type,
                calculation_type_key=calc_key,
                calculation_type_name=calc_name,
                calculation_category=category,
                amount=total_amt,
                is_storno=is_storno,
            )
        )

    PayrollODataDetail.objects.bulk_create(detail_objs, batch_size=500)
    return {
        "raw_count": len(raw_records),
        "saved_count": len(detail_objs),
        "year": year,
        "month": month,
    }
