"""Сервис генерации печатной формы «Опись вложения и накладная передачи посылки на МПД» (PDF)."""

import io
import logging
import os
from typing import Any, List, Optional

import qrcode
from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from logistics_app.models import Package
from logistics_app.services.docflow_sheet_service import register_dejavu_fonts

logger = logging.getLogger(__name__)

register_dejavu_fonts()


class PackageNumberedCanvas(canvas.Canvas):
    """Холст ReportLab с поддержкой двупроходной сквозной нумерации страниц."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует холст с буфером состояний страниц."""
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Any] = []

    def showPage(self) -> None:
        """Сохраняет состояние текущей страницы в буфер."""
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        """Отрисовывает сквозные колонтитулы на всех страницах и финализирует документ."""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        """Отрисовывает нижний колонтитул документа.

        Args:
            page_count (int): Общее количество страниц в документе.
        """
        self.saveState()
        self.setFont("DejaVuSans", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Нижняя разделительная черта
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 36, 559, 36)

        # Подвал: Организация и дата печати слева, номер страницы справа
        ts_str = timezone.now().strftime("%d.%m.%Y %H:%M")
        self.drawString(36, 24, f"ООО «Авиакомпания «БАРКОЛ» | Внутренняя логистика | Сформировано: {ts_str}")
        self.drawRightString(559, 24, f"Страница {self._pageNumber} из {page_count}")
        self.restoreState()


class PackageSheetGenerator:
    """Генератор официальной печатной формы описи вложения и накладной передачи посылки."""

    @classmethod
    def generate_qr_code_image(cls, data: str, size_pt: float = 65) -> Image:
        """Генерирует объект изображения Flowable с QR-кодом для быстрого открытия на смартфоне.

        Args:
            data (str): Текст или URL для кодирования в QR.
            size_pt (float): Размер QR-кода в пунктах. Defaults to 65.

        Returns:
            Image: Flowable элемент ReportLab.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return Image(buffer, width=size_pt, height=size_pt)

    @classmethod
    def generate_pdf(cls, package: Package, base_url: str = "https://corp.barkol.ru") -> bytes:
        """Формирует PDF-документ описи вложения посылки (алиас для generate_packing_slip_pdf).

        Args:
            package (Package): Экземпляр посылки с заполненными позициями.
            base_url (str): Базовый URL портала для QR-кода. Defaults to "https://corp.barkol.ru".

        Returns:
            bytes: Бинарные данные PDF документа.
        """
        return cls.generate_packing_slip_pdf(package=package, base_url=base_url)

    @classmethod
    def generate_packing_slip_pdf(cls, package: Package, base_url: str = "https://corp.barkol.ru") -> bytes:
        """Формирует официальный PDF-документ описи вложения формата A4.

        Args:
            package (Package): Экземпляр посылки с заполненными позициями.
            base_url (str): Базовый URL портала для QR-кода. Defaults to "https://corp.barkol.ru".

        Returns:
            bytes: Бинарные данные PDF документа.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=48,
        )

        styles = getSampleStyleSheet()

        # Типографика документа
        style_header_company = ParagraphStyle(
            "CompanyHeader",
            fontName="DejaVuSans-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#002b49"),
            alignment=TA_LEFT,
        )
        style_title = ParagraphStyle(
            "DocTitle",
            fontName="DejaVuSans-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#002b49"),
            alignment=TA_CENTER,
            spaceAfter=4,
        )
        style_subtitle = ParagraphStyle(
            "DocSubTitle",
            fontName="DejaVuSans-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#0284c7"),
            alignment=TA_CENTER,
            spaceAfter=10,
        )
        style_section = ParagraphStyle(
            "SectionHeader",
            fontName="DejaVuSans-Bold",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#002b49"),
            spaceBefore=8,
            spaceAfter=4,
        )
        style_cell = ParagraphStyle(
            "TableCell",
            fontName="DejaVuSans",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1e293b"),
        )
        style_cell_bold = ParagraphStyle(
            "TableCellBold",
            fontName="DejaVuSans-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#002b49"),
        )
        style_cell_center = ParagraphStyle(
            "TableCellCenter",
            fontName="DejaVuSans",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1e293b"),
            alignment=TA_CENTER,
        )
        style_th = ParagraphStyle(
            "TableTH",
            fontName="DejaVuSans-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#002b49"),
            alignment=TA_CENTER,
        )
        style_note = ParagraphStyle(
            "NoteStyle",
            fontName="DejaVuSans",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#64748b"),
        )

        story: List[Any] = []

        # 1. Шапка документа: Организация слева, QR-код справа
        qr_url = f"{base_url}/logistics/package/{package.pk}/"
        qr_flowable = cls.generate_qr_code_image(qr_url, size_pt=60)

        header_table = Table(
            [
                [
                    Paragraph(
                        "<b>ООО АВИАКОМПАНИЯ «БАРКОЛ»</b><br/>"
                        "<font size='8' color='#64748b'>СЛУЖБА МАТЕРИАЛЬНО-ТЕХНИЧЕСКОГО ОБЕСПЕЧЕНИЯ И ЛОГИСТИКИ</font>",
                        style_header_company,
                    ),
                    qr_flowable,
                ]
            ],
            colWidths=[450, 73],
        )
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ])
        )
        story.append(header_table)
        story.append(Spacer(1, 8))

        # Заголовок описи
        track_no = package.track_number or package.number_of_dispatch or f"#{package.id}"
        created_dt = package.created_at.strftime("%d.%m.%Y")
        story.append(Paragraph("ОПИСЬ ВЛОЖЕНИЯ И НАКЛАДНАЯ ПЕРЕДАЧИ ГРУЗА", style_title))
        story.append(Paragraph(f"№ {track_no} от {created_dt} г.", style_subtitle))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#002b49"), spaceAfter=8))

        # 2. Реквизиты отправления (Маршрут, Рейс, Участники)
        trip_info = package.trip.trip_number if package.trip else "Вне рейса (ожидание / индивидуальная доставка)"
        driver_info = package.trip.driver_display if package.trip else "—"
        vehicle_info = package.trip.vehicle_display if package.trip else "—"
        sender_div = package.sender_division.name if package.sender_division else "—"
        weight_str = f"{package.weight_kg} кг" if package.weight_kg else "Не взвешивалось"

        meta_data = [
            [
                Paragraph("<b>Пункт отправления:</b>", style_cell_bold),
                Paragraph(package.origin_display, style_cell),
                Paragraph("<b>Пункт назначения (МПД):</b>", style_cell_bold),
                Paragraph(package.destination_display, style_cell),
            ],
            [
                Paragraph("<b>Отправитель:</b>", style_cell_bold),
                Paragraph(f"{package.sender_display}<br/><font color='#64748b'>{sender_div}</font>", style_cell),
                Paragraph("<b>Получатель на МПД:</b>", style_cell_bold),
                Paragraph(package.recipient_display, style_cell),
            ],
            [
                Paragraph("<b>Рейс автомобиля:</b>", style_cell_bold),
                Paragraph(trip_info, style_cell),
                Paragraph("<b>Транспорт / Машина:</b>", style_cell_bold),
                Paragraph(vehicle_info, style_cell),
            ],
            [
                Paragraph("<b>Водитель / Перевозчик:</b>", style_cell_bold),
                Paragraph(driver_info, style_cell),
                Paragraph("<b>Мест / Вес / Тара:</b>", style_cell_bold),
                Paragraph(f"{package.places_count} мест | {weight_str} | {package.get_package_type_display()}", style_cell),
            ],
            [
                Paragraph("<b>Срочность:</b>", style_cell_bold),
                Paragraph(package.get_urgency_display(), style_cell),
                Paragraph("<b>Текущий статус:</b>", style_cell_bold),
                Paragraph(package.get_status_display(), style_cell),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[90, 170, 95, 168])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # 3. Таблица описи вложения
        story.append(Paragraph("Опись вложенных материальных ценностей (ТМЦ / запчасти / документы):", style_section))

        items = list(package.items.all())
        items_table_data = [
            [
                Paragraph("№", style_th),
                Paragraph("Наименование", style_th),
                Paragraph("P/N (Каталожный)", style_th),
                Paragraph("S/N (Заводской)", style_th),
                Paragraph("Кол-во", style_th),
                Paragraph("Ед.", style_th),
                Paragraph("Примечание", style_th),
            ]
        ]

        if items:
            for item in items:
                name_text = f"<b>{item.name}</b>"
                specs_snippets = []
                if item.catalog_item:
                    specs_snippets.append(f"<font color='#0284c7'>[{item.catalog_item.category.name}]</font>")
                elif item.maintenance_equipment:
                    specs_snippets.append("<font color='#d97706'>[Инструмент ТО]</font>")
                elif item.docflow_document:
                    specs_snippets.append("<font color='#0284c7'>[СЭД документ]</font>")

                if isinstance(item.item_specs, dict) and item.item_specs:
                    if item.item_specs.get("doc_number"):
                        specs_snippets.append(f"№ {item.item_specs['doc_number']}")
                    if item.item_specs.get("doc_date"):
                        specs_snippets.append(f"от {item.item_specs['doc_date']}")
                    if item.item_specs.get("grade"):
                        specs_snippets.append(f"кат: {item.item_specs['grade']}")
                    if item.item_specs.get("batch_number"):
                        specs_snippets.append(f"парт. {item.item_specs['batch_number']}")
                    if item.item_specs.get("verification_status"):
                        specs_snippets.append(f"({item.item_specs['verification_status']})")

                if specs_snippets:
                    name_text += f"<br/><font size='7' color='#475569'>{' | '.join(specs_snippets)}</font>"

                items_table_data.append([
                    Paragraph(str(item.item_order), style_cell_center),
                    Paragraph(name_text, style_cell),
                    Paragraph(item.part_number or "—", style_cell_center),
                    Paragraph(item.serial_number or "—", style_cell_center),
                    Paragraph(f"<b>{item.quantity_sent:g}</b>", style_cell_center),
                    Paragraph(item.unit, style_cell_center),
                    Paragraph(item.sender_comment or "—", style_cell),
                ])
        else:
            items_table_data.append([
                Paragraph("1", style_cell_center),
                Paragraph(package.description or "Содержимое согласно маркировке упаковки", style_cell),
                Paragraph("—", style_cell_center),
                Paragraph("—", style_cell_center),
                Paragraph("1", style_cell_center),
                Paragraph("место", style_cell_center),
                Paragraph("—", style_cell),
            ])

        items_table = Table(
            items_table_data,
            colWidths=[24, 185, 80, 75, 45, 34, 80],
            repeatRows=1,
        )
        items_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#002b49")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(items_table)
        story.append(Spacer(1, 12))

        # 4. Блок подписей и приемочной отметки
        signatures_data = [
            [
                Paragraph("<b>1. Сдал (Отправитель):</b>", style_cell_bold),
                Paragraph("<b>2. Принял к перевозке (Водитель):</b>", style_cell_bold),
                Paragraph("<b>3. Принял на МПД (Получатель):</b>", style_cell_bold),
            ],
            [
                Paragraph(
                    f"Должность: ___________________<br/>"
                    f"ФИО: {package.sender_display}<br/>"
                    f"Подпись: ____________________<br/>"
                    f"Дата: «___» _________ 202_ г.",
                    style_cell,
                ),
                Paragraph(
                    f"Должность: Водитель-экспедитор<br/>"
                    f"ФИО: {driver_info}<br/>"
                    f"Подпись: ____________________<br/>"
                    f"Дата: «___» _________ 202_ г.",
                    style_cell,
                ),
                Paragraph(
                    f"Должность: ___________________<br/>"
                    f"ФИО: {package.recipient_display}<br/>"
                    f"Подпись: ____________________<br/>"
                    f"Дата: «___» _________ 202_ г.",
                    style_cell,
                ),
            ],
            [
                Paragraph("<i>Тара и упаковка опломбированы, повреждений нет.</i>", style_note),
                Paragraph("<i>Груз принят к транспортировке без замечаний.</i>", style_note),
                Paragraph("<i>Количество и целостность проверены на месте.</i>", style_note),
            ],
        ]

        signatures_table = Table(signatures_data, colWidths=[174, 174, 175])
        signatures_table.setStyle(
            TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )

        story.append(KeepTogether([
            Paragraph("Отметки о передаче и приемочном контроле:", style_section),
            signatures_table,
            Spacer(1, 6),
            Paragraph(
                "<b>Отметки о претензиях / расхождениях:</b> ____________________________________________________________________________________<br/>"
                "_______________________________________________________________________________________________________________________",
                style_note,
            ),
        ]))

        doc.build(story, canvasmaker=PackageNumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()
