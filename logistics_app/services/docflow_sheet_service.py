"""Сервис формирования официального печатного листа согласования документа СЭД (PDF).

Модуль отвечает за генерацию официального листа визирования и протокола
наложения Простой Электронной Подписи (ПЭП) для системы СЭД АК «БАРКОЛ».
"""

import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowDocument,
    DocFlowFile,
    DocFlowFileVersion,
    DocFlowRouteStep,
)

logger = logging.getLogger(__name__)

# Регистрация кириллических шрифтов DejaVuSans
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_FONTS_INITIALIZED = False


def register_dejavu_fonts() -> None:
    """Выполняет регистрацию кириллических шрифтов DejaVuSans для ReportLab."""
    global _FONTS_INITIALIZED
    if _FONTS_INITIALIZED:
        return

    if os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать DejaVuSans: %s", exc)

    if os.path.exists(FONT_BOLD_PATH):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))
        except Exception as exc:
            logger.warning("Не удалось зарегистрировать DejaVuSans-Bold: %s", exc)

    _FONTS_INITIALIZED = True


register_dejavu_fonts()


class NumberedCanvas(canvas.Canvas):
    """Канвас с поддержкой двупроходной нумерации страниц и нижнего колонтитула."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализация холста."""
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Any] = []

    def showPage(self) -> None:
        """Сохранение состояния страницы."""
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        """Отрисовка нумерации страниц на всех сохраненных листах."""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        """Отрисовывает нижний колонтитул с номером страницы и отметкой времени.

        Args:
            page_count (int): Общее количество страниц в документе.
        """
        self.saveState()
        self.setFont("DejaVuSans", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Тонкая разделительная линия футера
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(42.5, 35, 552.5, 35)

        # Текст колонтитула
        now_str = timezone.now().strftime("%d.%m.%Y %H:%M")
        footer_text = f"СЭД ООО АК «БАРКОЛ» • Документ сформирован автоматически {now_str}"
        self.drawString(42.5, 23, footer_text)

        page_str = f"Страница {self._pageNumber} из {page_count}"
        self.drawRightString(552.5, 23, page_str)
        self.restoreState()


class DocFlowSheetGenerator:
    """Генератор официального PDF-листа согласования документа СЭД."""

    @classmethod
    def generate_approval_sheet_pdf(
            cls,
            document: DocFlowDocument,
            base_url: str = "https://portal.barkol.ru",
    ) -> bytes:
        """Генерирует бинарное содержимое PDF-листа согласования документа.

        Args:
            document (DocFlowDocument): Экземпляр документа СЭД.
            base_url (str): Базовый URL корпоративного портала для QR-верификации.

        Returns:
            bytes: Бинарные данные сгенерированного PDF-файла.
        """
        register_dejavu_fonts()

        buffer = io.BytesIO()
        doc_template = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=42.5,  # 15 мм
            rightMargin=42.5,
            topMargin=42.5,
            bottomMargin=50.0,
        )

        styles = getSampleStyleSheet()

        # Настройка кастомных типографических стилей
        font_regular = "DejaVuSans"
        font_bold = "DejaVuSans-Bold"

        style_org_header = ParagraphStyle(
            "OrgHeader",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#002b49"),
            alignment=1,  # Center
            spaceAfter=2,
        )

        style_title = ParagraphStyle(
            "SheetTitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#002b49"),
            alignment=1,
            spaceAfter=4,
        )

        style_subtitle = ParagraphStyle(
            "SheetSubtitle",
            parent=styles["Normal"],
            fontName=font_regular,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            alignment=1,
            spaceAfter=12,
        )

        style_section_title = ParagraphStyle(
            "SectionTitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#002b49"),
            spaceBefore=10,
            spaceAfter=6,
        )

        style_table_cell = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName=font_regular,
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#1e293b"),
        )

        style_table_header = ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#002b49"),
        )

        style_pep_box = ParagraphStyle(
            "PepBox",
            parent=styles["Normal"],
            fontName=font_regular,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#0f172a"),
        )

        style_pep_header = ParagraphStyle(
            "PepStampHeader",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=6.5,
            leading=8,
            textColor=colors.HexColor("#003366"),
            alignment=1,
        )

        style_pep_body = ParagraphStyle(
            "PepStampBody",
            parent=styles["Normal"],
            fontName=font_regular,
            fontSize=5.5,
            leading=7.2,
            textColor=colors.HexColor("#0f172a"),
        )

        story: List[Any] = []

        # 1. Шапка документа
        story.append(Paragraph("ООО АВИАКОМПАНИЯ «БАРКОЛ»", style_org_header))
        story.append(Paragraph("ЛИСТ СОГЛАСОВАНИЯ К ДОКУМЕНТУ", style_title))
        reg_num = document.reg_number or "ЧЕРНОВИК"
        reg_dt = (document.reg_date or document.created_at).strftime("%d.%m.%Y")
        story.append(Paragraph(f"№ {reg_num} от {reg_dt} г.", style_subtitle))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#002b49"), spaceAfter=10))

        # 2. Таблица ключевых реквизитов документа
        story.append(Paragraph("1. Реквизиты документа", style_section_title))

        counteragent_str = document.counteragent.name if document.counteragent else "Внутренний документ"
        deadline_str = document.deadline.strftime("%d.%m.%Y %H:%M") if document.deadline else "Не установлен"
        initiator_name = document.initiator.title or document.initiator.get_full_name() or document.initiator.username
        responsible_name = document.responsible.title or document.responsible.get_full_name() or document.responsible.username

        meta_data = [
            [
                Paragraph("<b>Вид документа:</b>", style_table_cell),
                Paragraph(f"{document.doc_type.name} ({document.get_flow_type_display()})", style_table_cell),
                Paragraph("<b>Срочность:</b>", style_table_cell),
                Paragraph(document.get_urgency_display(), style_table_cell),
            ],
            [
                Paragraph("<b>Тема:</b>", style_table_cell),
                Paragraph(document.title, style_table_cell),
                Paragraph("<b>Статус:</b>", style_table_cell),
                Paragraph(document.get_status_display(), style_table_cell),
            ],
            [
                Paragraph("<b>Контрагент:</b>", style_table_cell),
                Paragraph(counteragent_str, style_table_cell),
                Paragraph("<b>Дедлайн:</b>", style_table_cell),
                Paragraph(deadline_str, style_table_cell),
            ],
            [
                Paragraph("<b>Инициатор:</b>", style_table_cell),
                Paragraph(initiator_name, style_table_cell),
                Paragraph("<b>Ответственный:</b>", style_table_cell),
                Paragraph(responsible_name, style_table_cell),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[90, 165, 90, 165])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # 3. Таблица этапов маршрута и наложенных виз ПЭП
        story.append(Paragraph("2. Протокол согласования и визирования (ПЭП)", style_section_title))

        approval_headers = [
            Paragraph("№", style_table_header),
            Paragraph("Этап согласования", style_table_header),
            Paragraph("Согласующее лицо", style_table_header),
            Paragraph("Резолюция", style_table_header),
            Paragraph("Дата / Время", style_table_header),
            Paragraph("Штамп ПЭП", style_table_header),
        ]

        approval_rows: List[List[Any]] = [approval_headers]

        # Загружаем шаги маршрута
        steps = document.route_steps.select_related(
            "assigned_user",
            "assigned_division",
        ).prefetch_related("approved_users", "logs").order_by("step_order")

        for step in steps:
            # Поиск успешного лога визы для данного шага
            step_log = document.approval_logs.filter(
                route_step=step,
                action__in=[
                    DocFlowApprovalLog.Action.APPROVED,
                    DocFlowApprovalLog.Action.APPROVED_WITH_COMMENTS,
                ],
            ).order_by("-created_at").first()

            assignee_title = (
                (step.assigned_user.title or step.assigned_user.get_full_name() or step.assigned_user.username)
                if step.assigned_user
                else (step.assigned_division.name if step.assigned_division else "Группа согласующих")
            )

            status_badge = step.get_status_display()
            dt_str = "—"
            pep_content: Any = "—"

            if step_log:
                dt_str = step_log.created_at.strftime("%d.%m.%Y %H:%M:%S")
                pep_id = step_log.pep_certificate_id or "ПЭП-ВАЛИДНА"
                user_fio = step_log.user.title or step_log.user.get_full_name() or step_log.user.username
                comment_txt = step_log.comment or "Согласовано без замечаний"

                pep_stamp_table = Table(
                    [
                        [Paragraph("<b>ДОКУМЕНТ ПОДПИСАН<br/>ЭЛЕКТРОННОЙ ПОДПИСЬЮ</b>", style_pep_header)],
                        [Paragraph(f"<b>Сертификат:</b> {pep_id}", style_pep_body)],
                        [Paragraph(f"<b>Владелец:</b> {user_fio}", style_pep_body)],
                        [Paragraph(f"<b>Дата подписи:</b> {dt_str}", style_pep_body)],
                        [Paragraph("<b>Система:</b> СЭД АК «БАРКОЛ» (ПЭП)", style_pep_body)],
                    ],
                    colWidths=[120],
                )
                pep_stamp_table.setStyle(
                    TableStyle([
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#004085")),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f7ff")),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#b8daff")),
                        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ])
                )
                pep_content = pep_stamp_table
                resolution = f"<b>{status_badge}</b><br/>{comment_txt}"
            else:
                resolution = f"<i>{status_badge}</i>"

            approval_rows.append([
                Paragraph(str(step.step_order), style_table_cell),
                Paragraph(step.step_name, style_table_cell),
                Paragraph(assignee_title, style_table_cell),
                Paragraph(resolution, style_table_cell),
                Paragraph(dt_str, style_table_cell),
                pep_content if isinstance(pep_content, (Paragraph, Table)) else Paragraph(str(pep_content), style_table_cell),
            ])

        approval_table = Table(approval_rows, colWidths=[18, 102, 95, 110, 60, 125])
        approval_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(approval_table)
        story.append(Spacer(1, 10))

        # 4. Реестр прикрепленных версий файлов
        files = document.files.prefetch_related("versions", "versions__uploaded_by").all()
        if files.exists():
            story.append(Paragraph("3. Реестр версий прикрепленных файлов", style_section_title))
            file_headers = [
                Paragraph("Файл", style_table_header),
                Paragraph("Версия", style_table_header),
                Paragraph("Загрузил", style_table_header),
                Paragraph("Дата загрузки", style_table_header),
                Paragraph("Контрольная сумма (SHA-256)", style_table_header),
            ]
            file_rows: List[List[Any]] = [file_headers]

            for doc_file in files:
                current_ver = doc_file.versions.order_by("-version_number").first()
                if current_ver:
                    u_name = (current_ver.uploaded_by.title or current_ver.uploaded_by.get_full_name()) if current_ver.uploaded_by else "—"
                    u_date = current_ver.uploaded_at.strftime("%d.%m.%Y %H:%M")
                    h_sha = current_ver.file_hash[:24] + "..." if current_ver.file_hash else "—"

                    file_rows.append([
                        Paragraph(doc_file.title, style_table_cell),
                        Paragraph(f"v{current_ver.version_number}", style_table_cell),
                        Paragraph(u_name, style_table_cell),
                        Paragraph(u_date, style_table_cell),
                        Paragraph(f"<font name='DejaVuSans' size=6>{h_sha}</font>", style_table_cell),
                    ])

            file_table = Table(file_rows, colWidths=[140, 45, 110, 75, 140])
            file_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ])
            )
            story.append(file_table)

        # Сборка документа
        doc_template.build(story, canvasmaker=NumberedCanvas)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
