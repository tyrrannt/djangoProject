"""Сервисы формирования и почтовой отправки персонализированных бланков итогового тестирования АТП."""

import io
import logging
import pathlib
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional, Tuple

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
    user=None,
) -> Tuple[bytes, str]:
    """Генерирует бинарный поток заполненного файла бланка Word (.docx).

    Заполняет в шапке документа:
    - ФИО сотрудника;
    - Должность сотрудника;
    - Дату приказа / начала мероприятия в нижнем колонтитуле.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на мероприятие.
        user (Optional[User]): Пользователь, инициирующий генерацию.

    Returns:
        Tuple[bytes, str]: (Байты сформированного файла DOCX, Рекомендуемое имя файла для скачивания).

    Raises:
        FileNotFoundError: Если исходный файл шаблона не найден.
    """
    template_path, _, is_with_permit = get_template_path_for_assignment(assignment)
    if not template_path.exists():
        raise FileNotFoundError(f"Файл шаблона бланка не найден: {template_path}")

    employee = assignment.employee
    fio = employee.get_full_name() or getattr(employee, "title", "") or employee.username
    job_title = assignment.assigned_job_title or (
        employee.user_work_profile.job.name
        if hasattr(employee, "user_work_profile") and employee.user_work_profile and employee.user_work_profile.job
        else ""
    )

    testing = assignment.testing
    date_val = testing.order_date or testing.actual_event_start_datetime
    date_str = date_val.strftime("%d.%m.%Y") if date_val else timezone.now().strftime("%d.%m.%Y")

    short_fio = employee.last_name or fio.replace(" ", "_")
    type_suffix = "с_допуском" if is_with_permit else "без_допуска"
    download_filename = f"Бланк_итогового_тестирования_{type_suffix}_{short_fio}.docx"

    with zipfile.ZipFile(template_path, "r") as src_zip:
        out_buffer = io.BytesIO()
        with zipfile.ZipFile(out_buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            for item in src_zip.infolist():
                content = src_zip.read(item.filename)
                if item.filename == "word/header1.xml":
                    root = ET.fromstring(content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    tbl = root.find(".//w:tbl", ns)
                    if tbl is not None:
                        trs = tbl.findall(".//w:tr", ns)
                        if trs:
                            tcs = trs[0].findall(".//w:tc", ns)
                            if len(tcs) >= 3:
                                tc2 = tcs[2]
                                ps = tc2.findall(".//w:p", ns)
                                if len(ps) >= 3:
                                    # P0: ФИО
                                    p0_runs = ps[0].findall(".//w:r", ns)
                                    if p0_runs:
                                        for r in p0_runs[1:]:
                                            ps[0].remove(r)
                                        t0 = p0_runs[0].find(".//w:t", ns)
                                        if t0 is not None:
                                            t0.text = f"ФИО: {fio}"
                                    # P1: Должность
                                    p1_runs = ps[1].findall(".//w:r", ns)
                                    if p1_runs:
                                        for r in p1_runs[1:]:
                                            ps[1].remove(r)
                                        t1 = p1_runs[0].find(".//w:t", ns)
                                        if t1 is not None:
                                            t1.text = f"Должность: {job_title}"
                                    # P2: Очистка второй строки подчеркивания
                                    p2_runs = ps[2].findall(".//w:r", ns)
                                    for r in p2_runs:
                                        ps[2].remove(r)
                    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)

                elif item.filename == "word/footer1.xml":
                    root = ET.fromstring(content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    ps = root.findall(".//w:p", ns)
                    if len(ps) >= 2:
                        p1_runs = ps[1].findall(".//w:r", ns)
                        if p1_runs:
                            for r in p1_runs[1:]:
                                ps[1].remove(r)
                            t1 = p1_runs[0].find(".//w:t", ns)
                            if t1 is not None:
                                t1.text = date_str
                    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)

                dst_zip.writestr(item, content)

        out_buffer.seek(0)
        return out_buffer.getvalue(), download_filename


def send_testing_blank_by_email(
    assignment: TestingAssignment,
    recipient_email: Optional[str] = None,
    user=None,
) -> Tuple[bool, str]:
    """Формирует заполненный бланк Word и отправляет его во вложении на email сотрудника.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на мероприятие.
        recipient_email (Optional[str]): Адрес получателя (если не указан, берется email сотрудника).
        user (Optional[User]): Пользователь, инициирующий отправку.

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
