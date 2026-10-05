"""Сервисы формирования и почтовой отправки персонализированных бланков итогового тестирования АТП."""

import io
import logging
import pathlib
from typing import Any, Dict, List, Optional, Tuple

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor
from docxtpl import DocxTemplate
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from testing_app.models import (
    Testing,
    TestingAssignment,
    TestingGroup,
    TestingAuditLog,
    Question,
)

logger = logging.getLogger(__name__)

# Буквенные префиксы для вариантов ответов на русском языке
OPTION_LETTERS: Tuple[str, ...] = ("А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К")


def _set_cell_background(cell: Any, hex_color: str = "F4F6F9") -> None:
    """Устанавливает фоновый цвет ячейки таблицы Word через OXML-элемент shd.

    Args:
        cell: Объект ячейки docx.table._Cell.
        hex_color (str): Шестнадцатеричный код цвета без символа '#' (например, 'F4F6F9').
    """
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def _apply_table_grid_style(table: Any) -> None:
    """Безопасно назначает стиль таблицы с границами 'Table Grid'.

    Args:
        table: Объект таблицы docx.table.Table.
    """
    try:
        table.style = "Table Grid"
    except Exception:
        pass


def get_template_path_for_group(group: Optional[TestingGroup] = None) -> Tuple[pathlib.Path, str, bool]:
    """Определяет шаблон .docx на основе группы тестирования.

    Args:
        group (Optional[TestingGroup]): Группа тестирования (опционально).

    Returns:
        Tuple[pathlib.Path, str, bool]: (Путь к файлу шаблона .docx, Имя шаблона, Флаг допуска is_with_permit).
    """
    group_code = getattr(group, "code", "") if group else ""
    group_name = getattr(group, "name", "").lower() if group else ""

    # Группа "Обеспечение ТО ВС" -> без допуска
    if group_code == TestingGroup.Code.ENSURING or "без допуска" in group_name or "обеспечение" in group_name:
        template_name = "blank_atp_without_permit.docx"
        is_with_permit = False
    else:
        template_name = "blank_atp_with_permit.docx"
        is_with_permit = True

    primary_path = pathlib.Path(settings.BASE_DIR) / "static" / "DocxTemplates" / template_name
    if not primary_path.exists():
        fallback_name = (
            "Бланк итого тестирования АТП без допуска.docx"
            if not is_with_permit
            else "Бланк итого тестирования АТП.docx"
        )
        fallback_path = pathlib.Path(settings.BASE_DIR) / fallback_name
        if fallback_path.exists():
            return fallback_path, template_name, is_with_permit

    return primary_path, template_name, is_with_permit


def get_template_path_for_assignment(assignment: TestingAssignment) -> Tuple[pathlib.Path, str, bool]:
    """Определяет шаблон и базовое имя файла бланка на основе группы тестирования сотрудника.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на тестирование.

    Returns:
        Tuple[pathlib.Path, str, bool]: (Путь к файлу шаблона .docx, Имя шаблона, Флаг допуска is_with_permit).
    """
    return get_template_path_for_group(assignment.group)


def get_questions_for_blank(
    testing: Testing,
    assignment: Optional[TestingAssignment] = None,
) -> List[Dict[str, Any]]:
    """Формирует упорядоченный список вопросов и вариантов ответов для печатного бланка тестирования.

    Если для сотрудника уже была создана попытка тестирования (TestingAttempt), вопросы
    извлекаются из ее неизменяемого снимка (AttemptQuestion). В противном случае вопросы
    отбираются по квотам категорий мероприятия (TestingCategorySetting) или из общего банка.

    Args:
        testing (Testing): Мероприятие тестирования.
        assignment (Optional[TestingAssignment]): Назначение сотрудника (опционально).

    Returns:
        List[Dict[str, Any]]: Список словарей с данными вопросов и вариантов ответов:
            [
                {
                    "order_num": 1,
                    "category_name": "...",
                    "text": "...",
                    "explanation": "...",
                    "options": [
                        {"order_num": 1, "text": "...", "is_correct": False},
                        ...
                    ]
                },
                ...
            ]
    """
    # 1. Если передано назначение и у него есть попытки со снимками вопросов
    if assignment:
        attempt = (
            assignment.attempts.filter(questions__isnull=False)
            .prefetch_related("questions")
            .order_by("-id")
            .first()
        )
        if attempt and attempt.questions.exists():
            questions_data: List[Dict[str, Any]] = []
            for aq in attempt.questions.order_by("order_num"):
                options = []
                for opt_idx, opt in enumerate(aq.options_snapshot, 1):
                    options.append({
                        "order_num": opt.get("order_num") or opt.get("order") or opt_idx,
                        "text": opt.get("text", "").strip(),
                        "is_correct": bool(opt.get("is_correct")),
                    })
                questions_data.append({
                    "order_num": aq.order_num,
                    "category_name": aq.category_name,
                    "text": aq.question_text.strip(),
                    "explanation": aq.explanation.strip(),
                    "options": options,
                })
            return questions_data

    # 2. Если попытки нет или формируется общий бланк для мероприятия/группы
    selected_questions: List[Question] = []
    category_settings = list(testing.category_settings.select_related("category").order_by("id"))

    if category_settings:
        for c_setting in category_settings:
            needed_count = c_setting.calculated_questions_count or round(
                (c_setting.percentage / 100.0) * testing.questions_count
            )
            if needed_count <= 0:
                continue

            active_qs = list(
                Question.objects.filter(
                    category_id=c_setting.category_id,
                    status=Question.Status.ACTIVE,
                )
                .prefetch_related("options")
                .order_by("times_used", "id")[:needed_count]
            )
            selected_questions.extend(active_qs)

    # Резервный добор вопросов, если по категориям набралось меньше questions_count
    if len(selected_questions) < testing.questions_count:
        needed_more = testing.questions_count - len(selected_questions)
        already_ids = [q.id for q in selected_questions]
        additional_qs = list(
            Question.objects.filter(status=Question.Status.ACTIVE)
            .exclude(id__in=already_ids)
            .prefetch_related("options")
            .order_by("times_used", "id")[:needed_more]
        )
        selected_questions.extend(additional_qs)

    questions_data = []
    for idx, q in enumerate(selected_questions, 1):
        raw_options = list(q.options.order_by("order_num", "id"))
        options = [
            {
                "order_num": opt_idx,
                "text": opt.text.strip(),
                "is_correct": opt.is_correct,
            }
            for opt_idx, opt in enumerate(raw_options, 1)
        ]
        questions_data.append({
            "order_num": idx,
            "category_name": q.category.name if q.category else "Общая",
            "text": q.text.strip(),
            "explanation": (q.explanation or "").strip(),
            "options": options,
        })

    return questions_data


def append_questions_sheet_to_document(
    doc: Any,
    testing: Testing,
    questions_data: List[Dict[str, Any]],
    employee_info: Optional[Dict[str, Any]] = None,
    with_answers: bool = False,
) -> None:
    """Добавляет в документ Word структурированный экзаменационный лист с вопросами и протоколом.

    Формирует:
    1. Официальную шапку предприятия (ООО «Авиакомпания «БАРКОЛ», ИАС).
    2. Таблицу метаданных тестирования (приказ, сотрудник, должность, дата, лимит времени, проходной балл).
    3. Инструкцию по заполнению теста.
    4. Нумерованный перечень вопросов с вариантами ответов (квадраты ☐ для заполнения от руки, либо
       отметки ☑ с пояснениями для ключа комиссии).
    5. Итоговый протокол проверки, графы для подсчета правильных ответов, решения комиссии и подписей.

    Args:
        doc (Any): Экземпляр docx.Document, в который добавляются элементы листа.
        testing (Testing): Мероприятие тестирования.
        questions_data (List[Dict[str, Any]]): Список вопросов с вариантами ответов.
        employee_info (Optional[Dict[str, Any]]): Данные сотрудника (fio, job, division, group_name, date).
        with_answers (bool): Признак формирования ключа с правильными ответами для комиссии.
    """
    info = employee_info or {}
    fio = info.get("fio") or "________________________________________________"
    job = info.get("job") or "________________________________________________"
    division = info.get("division") or ""
    group_name = info.get("group_name") or ""
    test_date = info.get("date") or "«___» ____________ 20___ г."

    # 1. Шапка документа
    p_org = doc.add_paragraph()
    p_org.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_org.paragraph_format.space_before = Pt(0)
    p_org.paragraph_format.space_after = Pt(2)
    p_org.paragraph_format.line_spacing = 1.15

    r_org = p_org.add_run("ООО «АВИАКОМПАНИЯ «БАРКОЛ»\n")
    r_org.font.name = "Times New Roman"
    r_org.font.size = Pt(13)
    r_org.bold = True

    r_ias = p_org.add_run("ИНЖЕНЕРНО-АВИАЦИОННАЯ СЛУЖБА\n")
    r_ias.font.name = "Times New Roman"
    r_ias.font.size = Pt(10)
    r_ias.font.color.rgb = RGBColor(90, 90, 90)
    r_ias.bold = True

    r_title = p_org.add_run("ЛИСТ С ВОПРОСАМИ ИТОГОВОГО ТЕСТИРОВАНИЯ\n")
    r_title.font.name = "Times New Roman"
    r_title.font.size = Pt(14)
    r_title.bold = True

    if with_answers:
        r_mode = p_org.add_run("★ КЛЮЧ С ПРАВИЛЬНЫМИ ОТВЕТАМИ (ДЛЯ ЭКЗАМЕНАЦИОННОЙ КОМИССИИ) ★")
        r_mode.font.name = "Times New Roman"
        r_mode.font.size = Pt(11)
        r_mode.font.color.rgb = RGBColor(180, 0, 0)
        r_mode.bold = True
    else:
        r_mode = p_org.add_run("(бланк для письменного прохождения и сдачи комиссии)")
        r_mode.font.name = "Times New Roman"
        r_mode.font.size = Pt(9.5)
        r_mode.italic = True

    # 2. Таблица реквизитов мероприятия и слушателя
    order_date_str = testing.order_date.strftime("%d.%m.%Y") if testing.order_date else ""
    order_repr = f"Приказ № {testing.order_number} от {order_date_str}"
    if testing.order_name:
        order_repr += f" («{testing.order_name}»)"

    job_division_repr = job
    if division and division != job:
        job_division_repr += f" / {division}"

    total_q_count = len(questions_data) or testing.questions_count
    min_correct = round(total_q_count * (testing.passing_score_percentage / 100.0))
    reglament_str = (
        f"Время: {testing.attempt_duration_minutes} мин. | "
        f"Проходной балл: {testing.passing_score_percentage}% (не менее {min_correct} из {total_q_count})"
    )

    meta_rows = [
        ("Мероприятие / Программа:", testing.title),
        ("Основание проведения:", order_repr),
        ("Экзаменуемый (ФИО):", fio),
        ("Должность / Подразделение:", job_division_repr),
        ("Группа тестирования:", group_name or "По приказу"),
        ("Дата тестирования:", test_date),
        ("Регламент тестирования:", reglament_str),
    ]

    table = doc.add_table(rows=len(meta_rows), cols=2)
    _apply_table_grid_style(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for idx, (label, val) in enumerate(meta_rows):
        row = table.rows[idx]
        c0, c1 = row.cells[0], row.cells[1]
        c0.width = Inches(2.2)
        c1.width = Inches(4.8)

        _set_cell_background(c0, "F4F6F9")

        p0 = c0.paragraphs[0]
        p0.paragraph_format.space_before = Pt(2)
        p0.paragraph_format.space_after = Pt(2)
        r_l = p0.add_run(label)
        r_l.font.name = "Times New Roman"
        r_l.font.size = Pt(9.5)
        r_l.bold = True

        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_before = Pt(2)
        p1.paragraph_format.space_after = Pt(2)
        r_v = p1.add_run(val)
        r_v.font.name = "Times New Roman"
        r_v.font.size = Pt(9.5)

    # 3. Инструкция для экзаменуемого
    p_inst = doc.add_paragraph()
    p_inst.paragraph_format.space_before = Pt(6)
    p_inst.paragraph_format.space_after = Pt(8)
    p_inst.paragraph_format.line_spacing = 1.15
    if with_answers:
        r_inst = p_inst.add_run(
            "Инструкция для комиссии: Правильные варианты ответов отмечены символом ☑ и выделены полужирным "
            "шрифтом. Сопоставьте выбор слушателя в бланке с ключом и внесите результат в итоговый протокол."
        )
    else:
        r_inst = p_inst.add_run(
            "Инструкция для слушателя: Внимательно прочтите формулировку каждого вопроса и все варианты ответов. "
            "Отметьте один выбранный вариант ответа знаком «✓» или «X» в соответствующем квадрате ☐. "
            "Исправления и неразборчивые пометки не допускаются (вопрос аннулируется)."
        )
    r_inst.font.name = "Times New Roman"
    r_inst.font.size = Pt(9.5)
    r_inst.italic = True

    # 4. Перечень вопросов и вариантов ответов
    if not questions_data:
        p_empty = doc.add_paragraph()
        p_empty.paragraph_format.space_before = Pt(10)
        p_empty.paragraph_format.space_after = Pt(10)
        r_emp = p_empty.add_run(
            "Внимание: в данном мероприятии не настроены категории вопросов либо вопросы отсутствуют в банке."
        )
        r_emp.font.name = "Times New Roman"
        r_emp.font.size = Pt(11)
        r_emp.font.color.rgb = RGBColor(180, 0, 0)
        r_emp.bold = True
    else:
        for q_item in questions_data:
            p_q = doc.add_paragraph()
            p_q.paragraph_format.space_before = Pt(7)
            p_q.paragraph_format.space_after = Pt(2)
            p_q.paragraph_format.line_spacing = 1.15
            p_q.paragraph_format.keep_with_next = True

            rq_num = p_q.add_run(f"Вопрос № {q_item['order_num']}. ")
            rq_num.font.name = "Times New Roman"
            rq_num.font.size = Pt(11)
            rq_num.bold = True

            cat_name = q_item.get("category_name", "")
            if cat_name:
                rq_cat = p_q.add_run(f"[{cat_name}] ")
                rq_cat.font.name = "Times New Roman"
                rq_cat.font.size = Pt(10)
                rq_cat.font.color.rgb = RGBColor(100, 100, 100)

            rq_txt = p_q.add_run(q_item["text"])
            rq_txt.font.name = "Times New Roman"
            rq_txt.font.size = Pt(11)

            # Варианты ответов
            options = q_item.get("options", [])
            for opt_idx, opt in enumerate(options, 1):
                p_opt = doc.add_paragraph()
                p_opt.paragraph_format.left_indent = Inches(0.25)
                p_opt.paragraph_format.space_before = Pt(1)
                p_opt.paragraph_format.space_after = Pt(1)
                p_opt.paragraph_format.line_spacing = 1.15

                prefix = OPTION_LETTERS[opt_idx - 1] if opt_idx <= len(OPTION_LETTERS) else str(opt_idx)
                is_corr = opt.get("is_correct", False)

                if with_answers and is_corr:
                    ro_box = p_opt.add_run("☑  ")
                    ro_box.font.name = "Times New Roman"
                    ro_box.font.size = Pt(12)
                    ro_box.font.color.rgb = RGBColor(0, 120, 50)
                    ro_box.bold = True

                    ro_txt = p_opt.add_run(f"{prefix}) {opt['text']} ")
                    ro_txt.font.name = "Times New Roman"
                    ro_txt.font.size = Pt(10.5)
                    ro_txt.bold = True

                    ro_tag = p_opt.add_run("◄ [ПРАВИЛЬНЫЙ ОТВЕТ]")
                    ro_tag.font.name = "Times New Roman"
                    ro_tag.font.size = Pt(9.5)
                    ro_tag.font.color.rgb = RGBColor(0, 120, 50)
                    ro_tag.bold = True
                elif with_answers and not is_corr:
                    ro_box = p_opt.add_run("☐  ")
                    ro_box.font.name = "Times New Roman"
                    ro_box.font.size = Pt(12)
                    ro_box.font.color.rgb = RGBColor(90, 90, 90)

                    ro_txt = p_opt.add_run(f"{prefix}) {opt['text']}")
                    ro_txt.font.name = "Times New Roman"
                    ro_txt.font.size = Pt(10.5)
                    ro_txt.font.color.rgb = RGBColor(90, 90, 90)
                else:
                    ro_box = p_opt.add_run("☐  ")
                    ro_box.font.name = "Times New Roman"
                    ro_box.font.size = Pt(12)

                    ro_txt = p_opt.add_run(f"{prefix}) {opt['text']}")
                    ro_txt.font.name = "Times New Roman"
                    ro_txt.font.size = Pt(10.5)

            # Пояснение правильного ответа (только в режиме ключа)
            if with_answers and q_item.get("explanation"):
                p_exp = doc.add_paragraph()
                p_exp.paragraph_format.left_indent = Inches(0.25)
                p_exp.paragraph_format.space_before = Pt(2)
                p_exp.paragraph_format.space_after = Pt(4)
                p_exp.paragraph_format.line_spacing = 1.15

                re_lbl = p_exp.add_run("Пояснение: ")
                re_lbl.font.name = "Times New Roman"
                re_lbl.font.size = Pt(9.5)
                re_lbl.bold = True
                re_lbl.font.color.rgb = RGBColor(80, 80, 80)

                re_val = p_exp.add_run(q_item["explanation"])
                re_val.font.name = "Times New Roman"
                re_val.font.size = Pt(9.5)
                re_val.italic = True
                re_val.font.color.rgb = RGBColor(80, 80, 80)

    # 5. Итоговый протокол проверки и подписи
    p_proto_title = doc.add_paragraph()
    p_proto_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_proto_title.paragraph_format.space_before = Pt(12)
    p_proto_title.paragraph_format.space_after = Pt(4)
    p_proto_title.paragraph_format.keep_with_next = True

    r_pt = p_proto_title.add_run("РЕЗУЛЬТАТ ПРОВЕРКИ И ОЦЕНКА КОМИССИИ")
    r_pt.font.name = "Times New Roman"
    r_pt.font.size = Pt(12)
    r_pt.bold = True

    proto_table = doc.add_table(rows=3, cols=2)
    _apply_table_grid_style(proto_table)
    proto_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    c00 = proto_table.rows[0].cells[0]
    c01 = proto_table.rows[0].cells[1]
    c00.width = Inches(3.5)
    c01.width = Inches(3.5)

    _set_cell_background(c00, "F8F9FA")
    _set_cell_background(c01, "F8F9FA")

    p_r0 = c00.paragraphs[0]
    p_r0.paragraph_format.space_before = Pt(3)
    p_r0.paragraph_format.space_after = Pt(3)
    r_r0 = p_r0.add_run(
        f"Количество вопросов в тесте: {total_q_count}\n"
        f"Количество верных ответов: ______ из {total_q_count}\n"
        f"Итоговый результат: ______ %"
    )
    r_r0.font.name = "Times New Roman"
    r_r0.font.size = Pt(9.5)

    p_r1 = c01.paragraphs[0]
    p_r1.paragraph_format.space_before = Pt(3)
    p_r1.paragraph_format.space_after = Pt(3)
    r_r1 = p_r1.add_run(
        f"Проходной порог: {testing.passing_score_percentage}% (не менее {min_correct} верных)\n"
        f"Итоговая оценка:\n"
        f"☐  ЗАЧТЕНО                 ☐  НЕ ЗАЧТЕНО"
    )
    r_r1.font.name = "Times New Roman"
    r_r1.font.size = Pt(9.5)

    # Строка замечаний
    c10 = proto_table.rows[1].cells[0]
    c11 = proto_table.rows[1].cells[1]
    c10.merge(c11)
    p_notes = c10.paragraphs[0]
    p_notes.paragraph_format.space_before = Pt(3)
    p_notes.paragraph_format.space_after = Pt(3)
    r_notes = p_notes.add_run(
        "Замечания и особые отметки проверяющего:\n"
        "____________________________________________________________________________________"
    )
    r_notes.font.name = "Times New Roman"
    r_notes.font.size = Pt(9.5)

    # Строка подписей
    c20 = proto_table.rows[2].cells[0]
    c21 = proto_table.rows[2].cells[1]
    c20.width = Inches(3.5)
    c21.width = Inches(3.5)

    p_s1 = c20.paragraphs[0]
    p_s1.paragraph_format.space_before = Pt(3)
    p_s1.paragraph_format.space_after = Pt(3)
    r_s1 = p_s1.add_run(
        "Тест проверил (экзаменатор):\n\n"
        "___________________ / ___________________\n"
        "(подпись)                           (И.О. Фамилия)\n"
        "«___» ____________ 20___ г."
    )
    r_s1.font.name = "Times New Roman"
    r_s1.font.size = Pt(9.0)

    p_s2 = c21.paragraphs[0]
    p_s2.paragraph_format.space_before = Pt(3)
    p_s2.paragraph_format.space_after = Pt(3)
    r_s2 = p_s2.add_run(
        "С результатом ознакомлен (слушатель):\n\n"
        "___________________ / ___________________\n"
        "(подпись)                           (И.О. Фамилия)\n"
        "«___» ____________ 20___ г."
    )
    r_s2.font.name = "Times New Roman"
    r_s2.font.size = Pt(9.0)


def generate_filled_testing_blank_bytes(
    assignment: TestingAssignment,
    user: Optional[Any] = None,
    with_answers: bool = False,
    include_plan_page: bool = True,
) -> Tuple[bytes, str]:
    """Генерирует бинарный поток файла бланка Word (.docx) с предзаполненными данными и вопросами.

    Для мероприятий АТП первой страницей генерируется титульный план подготовки ИТП
    с подстановкой ФИО, должности и даты (DocxTemplate), после чего добавляется разрыв
    страницы и подробный «ЛИСТ С ВОПРОСАМИ ИТОГОВОГО ТЕСТИРОВАНИЯ» со всеми вопросами,
    вариантами ответов и протоколом проверки комиссии.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на мероприятие.
        user (Optional[Any]): Пользователь, инициирующий генерацию (опционально).
        with_answers (bool): Признак генерации экзаменационного ключа с ответами для комиссии.
        include_plan_page (bool): Включать ли первую титульную страницу плана подготовки.

    Returns:
        Tuple[bytes, str]: (Байты сформированного файла DOCX, Рекомендуемое имя файла для скачивания).
    """
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

    # Должность и подразделение
    wp = getattr(employee, "user_work_profile", None)
    job_title = assignment.assigned_job_title or (
        wp.job.name if wp and getattr(wp, "job", None) else ""
    )
    div_obj = (getattr(wp, "divisions", None) or getattr(wp, "division", None)) if wp else None
    division = assignment.assigned_division_title or (
        div_obj.name if div_obj else ""
    )

    # Даты и приказ
    testing = assignment.testing
    order_date_val = testing.order_date
    order_date_str = order_date_val.strftime("%d.%m.%Y") if order_date_val else ""

    event_start_val = testing.actual_event_start_datetime
    event_start_str = event_start_val.strftime("%d.%m.%Y") if event_start_val else ""

    today_str = timezone.now().strftime("%d.%m.%Y")
    default_date_str = order_date_str or event_start_str or today_str

    template_path, _, is_with_permit = get_template_path_for_assignment(assignment)
    type_suffix = "с_допуском" if is_with_permit else "без_допуска"
    file_fio_suffix = last_name or fio_full.replace(" ", "_")

    if with_answers:
        download_filename = f"Ключ_ответов_{type_suffix}_{file_fio_suffix}.docx"
    else:
        download_filename = f"Бланк_итогового_тестирования_{type_suffix}_{file_fio_suffix}.docx"

    # Создание или загрузка документа Word
    if include_plan_page and template_path.exists():
        doc = DocxTemplate(template_path)
        context: Dict[str, Any] = {
            "FIO": fio_full,
            "job": job_title,
            "date": default_date_str,
        }
        doc.render(context)
        doc.docx.add_page_break()
        target_doc = doc.docx
        save_target = doc
    else:
        target_doc = docx.Document()
        section = target_doc.sections[0]
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)
        save_target = target_doc

    # Получение перечня вопросов
    questions_data = get_questions_for_blank(testing, assignment=assignment)

    # Добавление листа с вопросами
    append_questions_sheet_to_document(
        doc=target_doc,
        testing=testing,
        questions_data=questions_data,
        employee_info={
            "fio": fio_full,
            "job": job_title,
            "division": division,
            "group_name": assignment.group.name if assignment.group else "",
            "date": default_date_str,
        },
        with_answers=with_answers,
    )

    out_buffer = io.BytesIO()
    save_target.save(out_buffer)
    out_buffer.seek(0)
    return out_buffer.getvalue(), download_filename


def generate_event_testing_blank_bytes(
    testing: Testing,
    group: Optional[TestingGroup] = None,
    user: Optional[Any] = None,
    with_answers: bool = False,
    include_plan_page: bool = True,
) -> Tuple[bytes, str]:
    """Генерирует бинарный поток общего бланка мероприятия Word (.docx) для печати или ключа ответов.

    Позволяет менеджеру тестирования выгрузить чистый бланк мероприятия с вопросами
    для печати тиража (с незаполненными полями ФИО и должности), либо ключ ответов
    для членов экзаменационной комиссии.

    Args:
        testing (Testing): Мероприятие тестирования.
        group (Optional[TestingGroup]): Группа тестирования (опционально).
        user (Optional[Any]): Пользователь, инициирующий генерацию (опционально).
        with_answers (bool): Признак формирования ключа с правильными ответами для комиссии.
        include_plan_page (bool): Включать ли первую титульную страницу плана подготовки.

    Returns:
        Tuple[bytes, str]: (Байты сформированного файла DOCX, Рекомендуемое имя файла для скачивания).
    """
    target_group = group or testing.groups.first()
    template_path, _, is_with_permit = get_template_path_for_group(target_group)
    type_suffix = "с_допуском" if is_with_permit else "без_допуска"

    order_clean = "".join(c for c in testing.order_number if c.isalnum() or c in ("-", "_")) or "бн"
    group_name = target_group.name if target_group else ""

    if with_answers:
        download_filename = f"Ключ_ответов_Приказ_{order_clean}_{type_suffix}.docx"
    else:
        download_filename = f"Бланк_тестирования_Приказ_{order_clean}_{type_suffix}.docx"

    order_date_val = testing.order_date
    order_date_str = order_date_val.strftime("%d.%m.%Y") if order_date_val else ""
    today_str = timezone.now().strftime("%d.%m.%Y")
    default_date_str = order_date_str or today_str

    blank_fio = "________________________________________________"
    blank_job = "________________________________________________"

    if include_plan_page and template_path.exists():
        doc = DocxTemplate(template_path)
        context: Dict[str, Any] = {
            "FIO": blank_fio,
            "job": blank_job,
            "date": default_date_str,
        }
        doc.render(context)
        doc.docx.add_page_break()
        target_doc = doc.docx
        save_target = doc
    else:
        target_doc = docx.Document()
        section = target_doc.sections[0]
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)
        save_target = target_doc

    questions_data = get_questions_for_blank(testing, assignment=None)

    append_questions_sheet_to_document(
        doc=target_doc,
        testing=testing,
        questions_data=questions_data,
        employee_info={
            "fio": blank_fio,
            "job": blank_job,
            "division": "",
            "group_name": group_name,
            "date": default_date_str,
        },
        with_answers=with_answers,
    )

    out_buffer = io.BytesIO()
    save_target.save(out_buffer)
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

