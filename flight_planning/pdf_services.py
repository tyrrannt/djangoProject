"""Модуль генерации PDF-отчетов по периодическим мероприятиям персонала flight_planning.

Предоставляет сервис формирования печатных форм в формате PDF на лету
с поддержкой кириллических шрифтов DejaVuSans, альбомной ориентацией A4,
нумерацией страниц ('Страница X из Y') и фирменной стилизацией Авиакомпании БАРКОЛ.
"""

import io
import os
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_FONTS_INITIALIZED = False


def register_cyrillic_fonts() -> None:
    """Регистрирует шрифты TrueType с поддержкой кириллицы (DejaVuSans) в ReportLab.

    Проверяет наличие файлов шрифтов в операционной системе и регистрирует
    их в реестре pdfmetrics, предотвращая повторную регистрацию.
    """
    global _FONTS_INITIALIZED
    if _FONTS_INITIALIZED:
        return

    registered = pdfmetrics.getRegisteredFontNames()
    if os.path.exists(FONT_PATH) and "DejaVuSans" not in registered:
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        except Exception:
            pass

    if os.path.exists(FONT_BOLD_PATH) and "DejaVuSans-Bold" not in registered:
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))
        except Exception:
            pass

    _FONTS_INITIALIZED = True


register_cyrillic_fonts()


class NumberedCanvas(canvas.Canvas):
    """Кастомный двухпроходный холст ReportLab для нумерации страниц и колонтитулов."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        """Отрисовывает верхние и нижние колонтитулы на каждой странице."""
        self.saveState()
        self.setFont("DejaVuSans", 7.5)
        self.setFillColor(colors.HexColor("#64748b"))

        page_w, page_h = self._pagesize

        # Верхний разделитель и колонтитул
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(30, page_h - 22, page_w - 30, page_h - 22)
        self.drawString(30, page_h - 18, "АВИАКОМПАНИЯ «БАРКОЛ» // Контроль квалификации и периодических мероприятий персонала")
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.drawRightString(page_w - 30, page_h - 18, f"Сформировано: {now_str}")

        # Нижний разделитель и нумерация страниц
        self.line(30, 26, page_w - 30, 26)
        self.drawString(30, 16, "Служебный отчет // Не подлежит передаче третьим лицам")
        page_text = f"Страница {self._pageNumber} из {page_count}"
        self.drawRightString(page_w - 30, 16, page_text)

        self.restoreState()


def generate_periodic_checks_issues_pdf(
        records_data: List[Dict[str, Any]],
        meta: Optional[Dict[str, Any]] = None
) -> bytes:
    """Формирует официальный PDF-отчет по периодическим мероприятиям персонала на лету.

    Args:
        records_data (List[Dict[str, Any]]): Список структурированных записей мероприятий:
            - 'employee_name' (str): ФИО сотрудника.
            - 'job_title' (str): Должность сотрудника.
            - 'check_name' (str): Наименование периодического мероприятия.
            - 'aircraft_display' (str): Тип ВС ('*' или наименование).
            - 'start_date' (str): Дата прохождения / сдачи (ДД.ММ.ГГГГ).
            - 'end_date' (str): Дата окончания действия (ДД.ММ.ГГГГ).
            - 'status' (str): 'expired', 'warning', 'valid'.
            - 'status_label' (str): 'Просрочено (X дн.)', 'Истекает (X дн.)'.
            - 'document_number' (str): Номер документа/сертификата.
            - 'issued_by' (str): Кем выдано / АУЦ / инструктор.
        meta (Optional[Dict[str, Any]]): Метаданные отчета:
            - 'report_title' (str): Заголовок отчета.
            - 'report_subtitle' (str): Подзаголовок / условия фильтрации.
            - 'generated_by' (str): ФИО составителя отчета.
            - 'total_count' (int): Общее количество записей.
            - 'expired_count' (int): Количество просроченных записей.
            - 'warning_count' (int): Количество истекающих записей.

    Returns:
        bytes: Бинарный поток сгенерированного PDF-документа.
    """
    register_cyrillic_fonts()

    if meta is None:
        meta = {}

    buffer = io.BytesIO()

    # Геометрия Landscape A4: 841.89 x 595.27 pt
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=32,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Стили текста
    title_style = ParagraphStyle(
        name="BarkolReportTitle",
        fontName="DejaVuSans-Bold",
        fontSize=12,
        leading=15,
        alignment=0,  # Left
        textColor=colors.HexColor("#002b49")
    )
    subtitle_style = ParagraphStyle(
        name="BarkolReportSubtitle",
        fontName="DejaVuSans",
        fontSize=8.5,
        leading=11,
        alignment=0,
        textColor=colors.HexColor("#475569")
    )
    th_style = ParagraphStyle(
        name="BarkolTH",
        fontName="DejaVuSans-Bold",
        fontSize=7.5,
        leading=9.5,
        alignment=1,  # Center
        textColor=colors.HexColor("#ffffff")
    )
    td_style = ParagraphStyle(
        name="BarkolTD",
        fontName="DejaVuSans",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1e293b")
    )
    td_bold = ParagraphStyle(
        name="BarkolTDBold",
        fontName="DejaVuSans-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0f172a")
    )
    td_center = ParagraphStyle(
        name="BarkolTDCenter",
        fontName="DejaVuSans",
        fontSize=7.5,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor("#334155")
    )
    badge_expired = ParagraphStyle(
        name="BarkolBadgeExpired",
        fontName="DejaVuSans-Bold",
        fontSize=7,
        leading=9,
        alignment=1,
        textColor=colors.HexColor("#991b1b")
    )
    badge_warning = ParagraphStyle(
        name="BarkolBadgeWarning",
        fontName="DejaVuSans-Bold",
        fontSize=7,
        leading=9,
        alignment=1,
        textColor=colors.HexColor("#92400e")
    )

    story = []

    # 1. Шапка отчета
    report_title = meta.get("report_title", "ОТЧЕТ ПО ПЕРИОДИЧЕСКИМ МЕРОПРИЯТИЯМ ПЕРСОНАЛА")
    report_subtitle = meta.get("report_subtitle", f"Сформирован по состоянию на {datetime.now().strftime('%d.%m.%Y')}")

    header_table_data = [
        [
            Paragraph(f"<b>{report_title}</b>", title_style),
            Paragraph(f"<b>Составил:</b> {meta.get('generated_by', 'Диспетчер')}", subtitle_style)
        ],
        [
            Paragraph(report_subtitle, subtitle_style),
            Paragraph(f"<b>Дата среза:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style)
        ]
    ]
    header_table = Table(header_table_data, colWidths=[550, 230])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # 2. Сводная плашка KPI
    total_cnt = meta.get('total_count', len(records_data))
    expired_cnt = meta.get('expired_count', sum(1 for r in records_data if r.get('status') == 'expired'))
    warning_cnt = meta.get('warning_count', sum(1 for r in records_data if r.get('status') == 'warning'))

    kpi_table_data = [
        [
            Paragraph(f"<b>Всего позиций в отчете:</b> <font color='#002b49'><b>{total_cnt}</b></font>", td_style),
            Paragraph(f"<b>Просрочено:</b> <font color='#dc2626'><b>{expired_cnt}</b></font>", td_style),
            Paragraph(f"<b>Истекает (до 30 дн.):</b> <font color='#d97706'><b>{warning_cnt}</b></font>", td_style),
        ]
    ]
    kpi_table = Table(kpi_table_data, colWidths=[260, 260, 260])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    # 3. Основная таблица записей
    # Общая ширина таблицы: 25 + 130 + 110 + 145 + 55 + 60 + 60 + 115 + 80 = 780 pt
    col_widths = [25, 130, 110, 145, 55, 60, 60, 115, 80]
    headers = [
        Paragraph("№", th_style),
        Paragraph("Сотрудник (ФИО)", th_style),
        Paragraph("Должность", th_style),
        Paragraph("Вид мероприятия", th_style),
        Paragraph("Тип ВС", th_style),
        Paragraph("Сдача", th_style),
        Paragraph("Действует до", th_style),
        Paragraph("Статус годности", th_style),
        Paragraph("№ Документа", th_style),
    ]

    table_data = [headers]

    if not records_data:
        empty_row = [
            Paragraph("По заданным критериям просроченных или истекающих мероприятий не обнаружено.", td_style)
        ] + [Paragraph("", td_style)] * 8
        table_data.append(empty_row)
    else:
        for idx, rec in enumerate(records_data, start=1):
            st = rec.get("status", "")
            if st == "expired":
                status_p = Paragraph(f"<font color='#dc2626'><b>{rec.get('status_label', 'Просрочено')}</b></font>", badge_expired)
            elif st == "warning":
                status_p = Paragraph(f"<font color='#b45309'><b>{rec.get('status_label', 'Истекает')}</b></font>", badge_warning)
            else:
                status_p = Paragraph(rec.get("status_label", "Действует"), td_center)

            doc_info = rec.get("document_number") or "—"
            if rec.get("issued_by"):
                doc_info += f"<br/><font color='#64748b' size='6.5'>{rec.get('issued_by')}</font>"

            row = [
                Paragraph(str(idx), td_center),
                Paragraph(f"<b>{rec.get('employee_name', '—')}</b>", td_bold),
                Paragraph(rec.get("job_title", "—") or "—", td_style),
                Paragraph(f"<b>{rec.get('check_name', '—')}</b>", td_style),
                Paragraph(rec.get("aircraft_display", "*") or "*", td_center),
                Paragraph(rec.get("start_date", "—") or "—", td_center),
                Paragraph(f"<b>{rec.get('end_date', '—')}</b>", td_center),
                status_p,
                Paragraph(doc_info, td_style),
            ]
            table_data.append(row)

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#002b49")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]

    # Чередующаяся подсветка строк и подсветка статуса
    if records_data:
        for r_idx, rec in enumerate(records_data, start=1):
            st = rec.get("status", "")
            if st == "expired":
                table_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#fff1f2")))
            elif st == "warning":
                table_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#fffbeb")))
            else:
                if r_idx % 2 == 0:
                    table_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#f8fafc")))

    main_table.setStyle(TableStyle(table_styles))
    story.append(main_table)

    # 4. Сборка документа с NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
