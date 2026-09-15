"""Сервисы формирования и почтовой отправки персонализированных бланков итогового тестирования АТП."""

import html
import io
import logging
import pathlib
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

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


def replace_docx_placeholders_in_xml(
    xml_bytes: bytes,
    context: Dict[str, Any],
) -> bytes:
    """Заменяет все переменные вида {переменная} в XML-файлах документа Word (.docx).

    Сохраняет 100% исходной OpenXML разметки, пространств имен (namespaces)
    и форматирования документа без их перегенерации через DOM-парсеры (ElementTree),
    что гарантирует полную совместимость с Microsoft Office Word (Word 2013-2024 / Office 365)
    и LibreOffice Writer.
    Корректно обрабатывает ситуации, когда текстовый процессор Word разбивает
    конструкцию {переменная} на несколько смежных XML-узлов <w:r>/<w:t>.

    Args:
        xml_bytes (bytes): Исходный XML-фрагмент (word/document.xml, word/header*.xml, word/footer*.xml и др.).
        context (Dict[str, Any]): Словарь подстановок ({переменная: значение}).

    Returns:
        bytes: Модифицированный XML-поток в кодировке UTF-8 с сохраненной структурой и пространствами имен.
    """
    if not xml_bytes or not context:
        return xml_bytes

    xml_text = xml_bytes.decode("utf-8", errors="ignore")
    normalized_context = {
        str(k).strip().lower(): str(v) if v is not None else ""
        for k, v in context.items()
    }

    var_pattern = re.compile(r"\{([^{}]+)\}")
    p_pattern = re.compile(r"(<w:p\b[^>]*>)(.*?)(</w:p>)", re.DOTALL)
    t_pattern = re.compile(r"(<w:t\b[^>]*>)(.*?)(</w:t>)", re.DOTALL)

    def process_paragraph(p_match: re.Match) -> str:
        p_open = p_match.group(1)
        p_body = p_match.group(2)
        p_close = p_match.group(3)

        t_matches = list(t_pattern.finditer(p_body))
        if not t_matches:
            return p_match.group(0)

        full_text = ""
        spans: List[Tuple[re.Match, str, int, int]] = []
        for tm in t_matches:
            raw_text = tm.group(2)
            unescaped = html.unescape(raw_text)
            start = len(full_text)
            end = start + len(unescaped)
            spans.append((tm, unescaped, start, end))
            full_text += unescaped

        if "{" not in full_text:
            return p_match.group(0)

        matches = list(var_pattern.finditer(full_text))
        if not matches:
            return p_match.group(0)

        replacements: List[Tuple[int, int, str]] = []
        for m in matches:
            key = m.group(1).strip().lower()
            if key in normalized_context:
                replacements.append((m.start(), m.end(), normalized_context[key]))

        if not replacements:
            return p_match.group(0)

        new_p_body: List[str] = []
        last_end = 0

        for tm, orig_txt, start, end in spans:
            new_p_body.append(p_body[last_end:tm.start()])
            last_end = tm.end()

            curr = start
            node_parts: List[str] = []
            while curr < end:
                in_repl = False
                for r_start, r_end, r_val in replacements:
                    if r_start <= curr < r_end:
                        if curr == r_start:
                            node_parts.append(r_val)
                        curr = min(r_end, end)
                        in_repl = True
                        break
                if not in_repl:
                    next_stop = end
                    for r_start, r_end, _ in replacements:
                        if curr < r_start < next_stop:
                            next_stop = r_start
                    node_parts.append(full_text[curr:next_stop])
                    curr = next_stop

            new_text_raw = "".join(node_parts)
            escaped_text = html.escape(new_text_raw, quote=False)

            t_tag_open = tm.group(1)
            if (" " in new_text_raw or new_text_raw.startswith(" ") or new_text_raw.endswith(" ")) and "xml:space" not in t_tag_open:
                t_tag_open = t_tag_open[:-1] + ' xml:space="preserve">'

            new_p_body.append(f"{t_tag_open}{escaped_text}{tm.group(3)}")

        new_p_body.append(p_body[last_end:])
        return p_open + "".join(new_p_body) + p_close

    result_text = p_pattern.sub(process_paragraph, xml_text)
    return result_text.encode("utf-8")


def generate_filled_testing_blank_bytes(
    assignment: TestingAssignment,
    user: Optional[Any] = None,
) -> Tuple[bytes, str]:
    """Генерирует бинарный поток заполненного файла бланка Word (.docx).

    Заменяет исключительно переменные в формате {переменная} (например: {ФИО},
    {Должность}, {Дата}, {fio}, {job_title}, {date} и др.) в шаблоне документа Word.
    Все остальные элементы форматирования, шрифты, границы таблиц и текст остаются неизменными.

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

    start_date_val = testing.start_datetime
    start_date_str = start_date_val.strftime("%d.%m.%Y") if start_date_val else ""

    end_date_val = testing.end_datetime
    end_date_str = end_date_val.strftime("%d.%m.%Y") if end_date_val else ""

    today_str = timezone.now().strftime("%d.%m.%Y")
    default_date_str = order_date_str or event_start_str or today_str

    service_number = getattr(employee, "service_number", "") or ""

    # Формируем имя файла для скачивания
    file_fio_suffix = last_name or fio_full.replace(" ", "_")
    type_suffix = "с_допуском" if is_with_permit else "без_допуска"
    download_filename = f"Бланк_итогового_тестирования_{type_suffix}_{file_fio_suffix}.docx"

    # Словарь контекста для подстановки в {переменная}
    context: Dict[str, Any] = {
        # ФИО
        "fio": fio_full,
        "ФИО": fio_full,
        "фио": fio_full,
        "Ф.И.О.": fio_full,
        "fio_full": fio_full,
        "employee_name": fio_full,
        "сотрудник": fio_full,
        "short_fio": short_fio,
        "инициалы": short_fio,
        "фио_инициалы": short_fio,
        "last_name": last_name,
        "фамилия": last_name,
        "first_name": first_name,
        "имя": first_name,
        "surname": surname,
        "отчество": surname,
        "service_number": service_number,
        "табельный_номер": service_number,
        # Должность и подразделение
        "job": job_title,
        "job_title": job_title,
        "должность": job_title,
        "Должность": job_title,
        "position": job_title,
        "division": division,
        "подразделение": division,
        "Подразделение": division,
        # Даты
        "date": default_date_str,
        "дата": default_date_str,
        "Дата": default_date_str,
        "order_date": order_date_str,
        "дата_приказа": order_date_str,
        "event_start_date": event_start_str,
        "дата_начала_обучения": event_start_str,
        "start_date": start_date_str,
        "дата_начала": start_date_str,
        "end_date": end_date_str,
        "дата_окончания": end_date_str,
        "today": today_str,
        "сегодня": today_str,
        # Приказ и мероприятие
        "order_number": testing.order_number or "",
        "номер_приказа": testing.order_number or "",
        "Номер_приказа": testing.order_number or "",
        "order_name": testing.order_name or "",
        "наименование_приказа": testing.order_name or "",
        "event_title": testing.title,
        "мероприятие": testing.title,
        "наименование_мероприятия": testing.title,
        "group_name": assignment.group.name,
        "группа": assignment.group.name,
        "Группа": assignment.group.name,
        "passing_score": str(testing.passing_score_percentage),
        "проходной_процент": str(testing.passing_score_percentage),
        "проходной_балл": str(testing.passing_score_percentage),
        "status": assignment.get_status_display() if hasattr(assignment, "get_status_display") else assignment.status,
        "статус": assignment.get_status_display() if hasattr(assignment, "get_status_display") else assignment.status,
    }

    with zipfile.ZipFile(template_path, "r") as src_zip:
        files: Dict[str, bytes] = {}
        for item in src_zip.infolist():
            content = src_zip.read(item.filename)
            if (
                item.filename in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")
                or item.filename.startswith("word/header")
                or item.filename.startswith("word/footer")
            ):
                content = replace_docx_placeholders_in_xml(content, context)
            files[item.filename] = content

        # Гарантируем канонический порядок OPC (Open Packaging Conventions):
        # [Content_Types].xml должен идти первым, _rels/.rels вторым
        ordered_names: List[str] = []
        if "[Content_Types].xml" in files:
            ordered_names.append("[Content_Types].xml")
        if "_rels/.rels" in files:
            ordered_names.append("_rels/.rels")
        for fname in sorted(files.keys()):
            if fname not in ordered_names:
                ordered_names.append(fname)

        out_buffer = io.BytesIO()
        with zipfile.ZipFile(out_buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            for fname in ordered_names:
                dst_zip.writestr(fname, files[fname])

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

