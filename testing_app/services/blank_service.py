"""Сервисы формирования и почтовой отправки персонализированных бланков итогового тестирования АТП."""

import io
import logging
import pathlib
from typing import Any, Dict, Optional, Tuple

from docxtpl import DocxTemplate
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from testing_app.models import TestingAssignment, TestingGroup, TestingAuditLog

logger = logging.getLogger(__name__)


def get_template_path_for_assignment(assignment: TestingAssignment) -> Tuple[pathlib.Path, str, bool]:
    """Определяет шаблон и базовое имя файла бланка на основе группы тестирования сотрудника.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на тестирование.

    Returns:
        Tuple[pathlib.Path, str, bool]: (Путь к файлу шаблона .docx, Имя шаблона, Флаг допуска is_with_permit).
    """
    group_code = getattr(assignment.group, "code", "")
    group_name = getattr(assignment.group, "name", "").lower()

    # Группа "Обеспечение ТО ВС" -> без допуска
    if group_code == TestingGroup.Code.ENSURING or "без допуска" in group_name or "обеспечение" in group_name:
        template_name = "blank_atp_without_permit.docx"
        is_with_permit = False
    else:
        template_name = "blank_atp_with_permit.docx"
        is_with_permit = True

    primary_path = pathlib.Path(settings.BASE_DIR) / "static" / "DocxTemplates" / template_name
    if not primary_path.exists():
        fallback_name = "Бланк итого тестирования АТП без допуска.docx" if not is_with_permit else "Бланк итого тестирования АТП.docx"
        fallback_path = pathlib.Path(settings.BASE_DIR) / fallback_name
        if fallback_path.exists():
            return fallback_path, template_name, is_with_permit

    return primary_path, template_name, is_with_permit


def generate_filled_testing_blank_bytes(
    assignment: TestingAssignment,
    user: Optional[Any] = None,
) -> Tuple[bytes, str]:
    """Генерирует бинарный поток заполненного файла бланка Word (.docx) через DocxTemplate.

    Заполняет официальный шаблон документа Word (DocxTemplate) реквизитами сотрудника
    (ФИО, должность и дата) аналогично модулю медицинских направлений.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на мероприятие.
        user (Optional[Any]): Пользователь, инициирующий генерацию (опционально).

    Returns:
        Tuple[bytes, str]: (Байты сформированного файла DOCX, Рекомендуемое имя файла для скачивания).

    Raises:
        FileNotFoundError: Если исходный файл шаблона не найден.
    """
    template_path, _, is_with_permit = get_template_path_for_assignment(assignment)
    if not template_path.exists():
        raise FileNotFoundError(f"Файл шаблона бланка не найден: {template_path}")

    employee = assignment.employee
    
    # Формирование ФИО
    last_name = getattr(employee, "last_name", "") or ""
    first_name = getattr(employee, "first_name", "") or ""
    surname = getattr(employee, "surname", "") or ""
    
    if last_name and first_name:
        fio_full = f"{last_name} {first_name}"
        if surname:
            fio_full += f" {surname}"
    elif getattr(employee, "title", ""):
        fio_full = employee.title
    else:
        fio_full = employee.get_full_name() or employee.username

    # Краткое ФИО с инициалами (Иванов И.И.)
    if last_name and first_name:
        fn_init = f"{first_name[0]}." if first_name else ""
        sn_init = f"{surname[0]}." if surname else ""
        short_fio = f"{last_name} {fn_init}{sn_init}".strip()
    else:
        short_fio = fio_full

    # Должность и подразделение
    job_title = assignment.assigned_job_title or (
        employee.user_work_profile.job.name
        if hasattr(employee, "user_work_profile") and employee.user_work_profile and employee.user_work_profile.job
        else ""
    )
    division = assignment.assigned_division_title or (
        employee.user_work_profile.division.name
        if hasattr(employee, "user_work_profile") and employee.user_work_profile and employee.user_work_profile.division
        else ""
    )

    # Даты и приказ
    testing = assignment.testing
    order_date_val = testing.order_date
    order_date_str = order_date_val.strftime("%d.%m.%Y") if order_date_val else ""

    event_start_val = testing.actual_event_start_datetime
    event_start_str = event_start_val.strftime("%d.%m.%Y") if event_start_val else ""

    today_str = timezone.now().strftime("%d.%m.%Y")
    default_date_str = order_date_str or event_start_str or today_str

    service_number = getattr(employee, "service_number", "") or ""

    # Формируем имя файла для скачивания
    file_fio_suffix = last_name or fio_full.replace(" ", "_")
    type_suffix = "с_допуском" if is_with_permit else "без_допуска"
    download_filename = f"Бланк_итогового_тестирования_{type_suffix}_{file_fio_suffix}.docx"

    # Словарь контекста для подстановки в шаблон DocxTemplate
    context: Dict[str, Any] = {
        # ФИО
        "FIO": fio_full,
        # Должность и подразделение
        "job": job_title,
        # Даты
        "date": default_date_str,
    }

    doc = DocxTemplate(template_path)
    doc.render(context)

    out_buffer = io.BytesIO()
    doc.save(out_buffer)
    out_buffer.seek(0)
    return out_buffer.getvalue(), download_filename


def send_testing_blank_by_email(
    assignment: TestingAssignment,
    recipient_email: Optional[str] = None,
    user: Optional[Any] = None,
) -> Tuple[bool, str]:
    """Формирует заполненный бланк Word и отправляет его во вложении на email сотрудника.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на мероприятие.
        recipient_email (Optional[str]): Адрес получателя (если не указан, берется email сотрудника).
        user (Optional[Any]): Пользователь, инициирующий отправку (опционально).

    Returns:
        Tuple[bool, str]: (Успешность отправки, Текстовое сообщение о результате).
    """
    employee = assignment.employee
    target_email = recipient_email or employee.email
    if not target_email or "@" not in target_email:
        return False, "У сотрудника не указан корректный адрес электронной почты в профиле."

    try:
        docx_bytes, filename = generate_filled_testing_blank_bytes(assignment, user=user)
    except Exception as err:
        logger.error("[BlankService] Ошибка формирования бланка: %s", err, exc_info=True)
        return False, f"Не удалось сформировать файл бланка: {err}"

    testing = assignment.testing
    subject = f"ООО АК «БАРКОЛ» — Бланк итогового тестирования АТП (Приказ №{testing.order_number})"
    fio = employee.get_full_name() or employee.username

    order_date_str = testing.order_date.strftime("%d.%m.%Y") if testing.order_date else ""
    body_text = (
        f"Здравствуйте, {fio}!\n\n"
        f"Во вложении направляем Ваш персонализированный бланк итогового тестирования по программе "
        f"авиационно-технической подготовки (Приказ №{testing.order_number} от {order_date_str}).\n\n"
        f"Мероприятие: {testing.title}\n"
        f"Группа: {assignment.group.name}\n"
        f"Должность: {assignment.assigned_job_title}\n\n"
        f"Инженерно-авиационная служба ООО «Авиакомпания «БАРКОЛ»."
    )

    from_email = getattr(settings, "EMAIL_HOST_USER", "ias@barkol.ru")

    try:
        email_message = EmailMessage(
            subject=subject,
            body=body_text,
            from_email=from_email,
            to=[target_email],
        )
        email_message.attach(
            filename,
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        email_message.send(fail_silently=False)

        TestingAuditLog.objects.create(
            testing=testing,
            assignment=assignment,
            user=user or employee,
            action=TestingAuditLog.Action.STATUS_CHANGED,
            details={"action": "send_blank_email", "email": target_email, "filename": filename},
        )
        logger.info("[BlankService] Бланк успешно отправлен на %s для %s", target_email, fio)
        return True, f"Бланк успешно отправлен на Ваш email ({target_email})!"
    except Exception as exc:
        logger.error("[BlankService] Ошибка отправки бланка на %s: %s", target_email, exc, exc_info=True)
        return False, f"Ошибка при отправке письма на {target_email}: {exc}"

