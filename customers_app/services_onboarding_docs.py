# -*- coding: utf-8 -*-
"""Сервисный слой генерации кадровых документов и пакетной выгрузки при приёме на работу."""

import io
import logging
import re
import zipfile
from datetime import date
from typing import Iterable, List, Optional, Tuple

from django.db import transaction

from administration_app.services import TemplateService
from customers_app.customers_util import prepare_consent_context
from customers_app.models import BiometricConsent, ConsentType, DataBaseUser, DocumentSigner

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Очищает имя файла от недопустимых символов файловой системы.

    Args:
        name (str): Исходная строка имени файла.

    Returns:
        str: Безопасное имя файла без спецсимволов.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]+', '_', name or '').strip()
    return cleaned or 'document'


def generate_consent_number(consent_type: Optional[ConsentType] = None, target_date: Optional[date] = None) -> str:
    """Генерирует уникальный регистрационный номер кадрового документа/согласия.

    Формат: ``<ПРЕФИКС>-ГГГГММДД-XXX`` (например, ``ДМО-20261120-001``).

    Args:
        consent_type (Optional[ConsentType]): Тип документа (используется ``number_prefix``).
        target_date (Optional[date]): Дата документа (по умолчанию сегодня).

    Returns:
        str: Уникальный регистрационный номер.
    """
    doc_date = target_date or date.today()
    prefix_code = (consent_type.number_prefix.strip() if consent_type and consent_type.number_prefix else "БС")
    date_str = doc_date.strftime("%Y%m%d")
    prefix = f"{prefix_code}-{date_str}"

    last_consent = (
        BiometricConsent.objects.filter(consent_number__startswith=prefix)
        .order_by("-consent_number")
        .first()
    )
    if last_consent:
        try:
            last_num = int(last_consent.consent_number.split("-")[-1])
            new_num = last_num + 1
        except (ValueError, IndexError):
            new_num = BiometricConsent.objects.filter(consent_number__startswith=prefix).count() + 1
    else:
        new_num = 1

    return f"{prefix}-{new_num:03d}"


def render_consent_document(consent: BiometricConsent) -> Tuple[io.BytesIO, str, str]:
    """Рендерит заполненный Word/Excel документ для указанной записи согласия/документа.

    Args:
        consent (BiometricConsent): Запись документа сотрудника.

    Returns:
        Tuple[io.BytesIO, str, str]: Кортеж ``(buffer, filename, content_type)``.

    Raises:
        ValueError: Если для типа документа не настроен активный шаблон.
    """
    if not consent.consent_type or not consent.consent_type.template:
        raise ValueError("Для выбранного типа документа не настроен шаблон.")

    template = consent.consent_type.template
    context = prepare_consent_context(consent)

    if template.template_type == "word":
        buffer = TemplateService.render_word_template(template.unique_code, context)
        ext = "docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        buffer = TemplateService.render_excel_template(template.unique_code, context)
        ext = "xlsx"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    type_name = _sanitize_filename(consent.consent_type.name)
    emp_name = _sanitize_filename(consent.employee.last_name or consent.employee_full_name)
    filename = f"{type_name}_{emp_name}_{consent.consent_number}.{ext}"
    return buffer, filename, content_type


@transaction.atomic
def generate_hire_package_zip(
    employee: DataBaseUser,
    consent_types: Iterable[ConsentType],
    consent_date: date,
    signer: Optional[DocumentSigner] = None,
    powers_of_attorney: Optional[Iterable] = None,
    created_by: Optional[DataBaseUser] = None,
    employment_contract_number: str = "",
    employment_contract_date: Optional[date] = None,
    comment: str = "",
    errors_out: Optional[List[str]] = None,
) -> Tuple[io.BytesIO, List[BiometricConsent], List[str]]:
    """Создаёт пакет записей документов при приёме на работу и собирает их в ZIP-архив.

    Для типов документов с ``requires_signer=True`` автоматически привязываются
    выбранный подписант и доверенность(и) из реестра ``PowerOfAttorney``.

    Args:
        employee (DataBaseUser): Принимаемый на работу сотрудник.
        consent_types (Iterable[ConsentType]): Выбранные типы документов.
        consent_date (date): Дата подписания документов.
        signer (Optional[DocumentSigner]): Подписант со стороны работодателя.
        powers_of_attorney (Optional[Iterable]): Выбранные доверенности подписанта.
        created_by (Optional[DataBaseUser]): Сотрудник ОК, сформировавший пакет.
        employment_contract_number (str): Номер трудового договора (если задан).
        employment_contract_date (Optional[date]): Дата трудового договора (если задана).
        comment (str): Служебный комментарий к документам пакета.

    Returns:
        Tuple[io.BytesIO, List[BiometricConsent], List[str]]:
            - ``zip_buffer``: Поток ZIP-архива с заполненными ``.docx`` файлами;
            - ``created_consents``: Список созданных записей ``BiometricConsent``;
            - ``skipped_without_template``: Названия типов, у которых не привязан файл шаблона.
    """
    poa_list = list(powers_of_attorney) if powers_of_attorney else []
    created_consents: List[BiometricConsent] = []
    skipped_without_template: List[str] = []

    emp_position = ""
    if employee.user_work_profile and employee.user_work_profile.job:
        emp_position = str(employee.user_work_profile.job)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for ctype in consent_types:
            number = generate_consent_number(consent_type=ctype, target_date=consent_date)
            doc_signer = signer if ctype.requires_signer else None

            consent = BiometricConsent.objects.create(
                employee=employee,
                consent_type=ctype,
                consent_number=number,
                consent_date=consent_date,
                employee_full_name=employee.get_title(),
                employee_position=emp_position,
                signer=doc_signer,
                employment_contract_number=employment_contract_number or "",
                employment_contract_date=employment_contract_date,
                comment=comment or "",
                created_by=created_by,
                is_active=True,
            )
            if doc_signer and not doc_signer.acts_by_charter and poa_list:
                consent.powers_of_attorney.set(poa_list)

            created_consents.append(consent)

            if ctype.template:
                try:
                    doc_buf, filename, _ = render_consent_document(consent)
                    zf.writestr(filename, doc_buf.getvalue())
                except Exception as exc:
                    logger.exception(
                        "Ошибка рендеринга шаблона для типа документа '%s' (template=%s)",
                        ctype.name,
                        getattr(ctype.template, "unique_code", None),
                    )
                    if errors_out is not None:
                        errors_out.append(f"{ctype.name}: {exc}")
                    skipped_without_template.append(ctype.name)
            else:
                if errors_out is not None:
                    errors_out.append(f"{ctype.name}: не привязан шаблон документа")
                skipped_without_template.append(ctype.name)

    zip_buffer.seek(0)
    return zip_buffer, created_consents, skipped_without_template
