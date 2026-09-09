"""Модуль генерации PDF-документов для приложения customers_app.

Содержит сервис и функции для формирования официальных печатных форм,
включая памятку сотрудника с учетными данными доступа к корпоративному порталу,
электронной почте и параметрами подключения почтовых клиентов (IMAP/SMTP).
"""

import io
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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

from customers_app.models import DataBaseUser

# Регистрация кириллических шрифтов DejaVuSans
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_FONTS_INITIALIZED = False


def register_dejavu_fonts() -> None:
    """Выполняет регистрацию кириллических шрифтов DejaVuSans для ReportLab.

    Проверяет наличие файлов шрифтов в операционной системе и регистрирует
    их в реестре pdfmetrics, предотвращая повторную регистрацию.
    """
    global _FONTS_INITIALIZED
    if _FONTS_INITIALIZED:
        return

    if os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        except Exception:
            pass

    if os.path.exists(FONT_BOLD_PATH):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))
        except Exception:
            pass

    _FONTS_INITIALIZED = True


register_dejavu_fonts()


def generate_employee_credentials_pdf(user: DataBaseUser) -> bytes:
    """Генерирует структурированный PDF-документ (памятку) с учетными данными сотрудника.

    Формирует официальную печатную форму формата A4 с реквизитами доступа к
    корпоративному порталу, корпоративной почте, параметрами ручной настройки
    почтовых клиентов (IMAP/SMTP) и правилами информационной безопасности.

    Args:
        user (DataBaseUser): Объект пользователя (сотрудника), для которого
            генерируется памятка с учетными данными.

    Returns:
        bytes: Бинарные данные сгенерированного PDF-документа.

    Raises:
        Exception: При критических ошибках сборки документа в ReportLab.
    """
    register_dejavu_fonts()

    buffer = io.BytesIO()

    # Поля документа A4 (portrait): 595.27 x 842.89 pt, поля 24 pt для гарантии размещения на 1 странице
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=20,
        bottomMargin=20,
    )

    elements: List[Any] = []
    styles = getSampleStyleSheet()

    font_normal = "DejaVuSans" if pdfmetrics.getRegisteredFont("DejaVuSans") else "Helvetica"
    font_bold = "DejaVuSans-Bold" if pdfmetrics.getRegisteredFont("DejaVuSans-Bold") else "Helvetica-Bold"

    # Стили текста
    header_company_style = ParagraphStyle(
        name="HeaderCompanyStyle",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#002b49"),
        alignment=2,  # По правому краю
    )

    header_sub_style = ParagraphStyle(
        name="HeaderSubStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#6c757d"),
        alignment=2,
    )

    doc_title_style = ParagraphStyle(
        name="DocTitleStyle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=13,
        leading=15,
        textColor=colors.HexColor("#002b49"),
        alignment=1,  # По центру
        spaceAfter=2,
    )

    doc_subtitle_style = ParagraphStyle(
        name="DocSubtitleStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#495057"),
        alignment=1,
        spaceAfter=6,
    )

    section_header_style = ParagraphStyle(
        name="SectionHeaderStyle",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=11,
        textColor=colors.white,
    )

    label_style = ParagraphStyle(
        name="LabelStyle",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333"),
    )

    val_style = ParagraphStyle(
        name="ValStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#111111"),
    )

    val_code_style = ParagraphStyle(
        name="ValCodeStyle",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor("#0056b3"),
    )

    table_th_style = ParagraphStyle(
        name="TableThStyle",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#002b49"),
        alignment=1,
    )

    table_td_style = ParagraphStyle(
        name="TableTdStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#212529"),
        alignment=1,
    )

    table_td_left = ParagraphStyle(
        name="TableTdLeft",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#333333"),
        alignment=0,
    )

    memo_text_style = ParagraphStyle(
        name="MemoTextStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#333333"),
    )

    footer_text_style = ParagraphStyle(
        name="FooterTextStyle",
        parent=styles["Normal"],
        fontName=font_normal,
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor("#888888"),
        alignment=1,
    )

    # 1. Шапка: Логотип + Реквизиты компании
    logo_path = os.path.join(settings.BASE_DIR, "static", "admin_templates", "img", "logo.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(settings.BASE_DIR, "static", "logo_small.png")

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    header_right = [
        Paragraph("ООО Авиакомпания «БАРКОЛ»", header_company_style),
        Paragraph("Информационно-аналитический отдел", header_sub_style),
        Paragraph(f"Дата формирования: {now_str}", header_sub_style),
    ]

    header_table_data = []
    if os.path.exists(logo_path):
        try:
            # Масштабируем логотип: ширина ~120pt, высота ~26pt
            logo_img = Image(logo_path, width=120, height=26)
            header_table_data.append([logo_img, header_right])
        except Exception:
            logo_p = Paragraph("<b>БАРКОЛ</b>", header_company_style)
            header_table_data.append([logo_p, header_right])
    else:
        logo_p = Paragraph("<b>ООО Авиакомпания «БАРКОЛ»</b>", header_company_style)
        header_table_data.append([logo_p, header_right])

    header_table = Table(header_table_data, colWidths=[200, 347])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(header_table)

    elements.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#002b49"),
            spaceBefore=3,
            spaceAfter=5,
        )
    )

    # 2. Название документа
    elements.append(Paragraph("ПАМЯТКА СОТРУДНИКА", doc_title_style))
    elements.append(
        Paragraph("Учетные данные для доступа к корпоративным информационным системам", doc_subtitle_style)
    )

    # Извлекаем профильные данные сотрудника
    work_profile = getattr(user, "user_work_profile", None)
    job_name = work_profile.job.name if (work_profile and work_profile.job) else "Не указана"
    division_name = (
        work_profile.divisions.name if (work_profile and work_profile.divisions) else "Не указано"
    )
    work_password = (
        work_profile.work_email_password if (work_profile and work_profile.work_email_password) else "—"
    )
    user_email = user.email or "—"
    user_fio = user.title or user.get_full_name() or user.username

    # 3. Секция: Сведения о сотруднике
    emp_sec_header = Table(
        [[Paragraph("1. Сведения о сотруднике", section_header_style)]],
        colWidths=[547],
    )
    emp_sec_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002b49")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(emp_sec_header)

    emp_table_data = [
        [
            Paragraph("ФИО работника:", label_style),
            Paragraph(f"<b>{user_fio}</b>", val_style),
            Paragraph("Табельный номер / Логин:", label_style),
            Paragraph(f"<b>{user.username}</b>", val_code_style),
        ],
        [
            Paragraph("Должность:", label_style),
            Paragraph(job_name, val_style),
            Paragraph("Подразделение:", label_style),
            Paragraph(division_name, val_style),
        ],
    ]
    emp_table = Table(emp_table_data, colWidths=[105, 170, 130, 142])
    emp_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdcdc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e9ecef")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(emp_table)
    elements.append(Spacer(1, 4))

    # 4. Секция: Корпоративный сайт (Интранет-портал)
    portal_sec_header = Table(
        [[Paragraph("2. Корпоративный портал", section_header_style)]],
        colWidths=[547],
    )
    portal_sec_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002b49")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(portal_sec_header)

    portal_table_data = [
        [
            Paragraph("Адрес портала (URL):", label_style),
            Paragraph("<b>https://corp.barkol.ru/</b>", val_code_style),
            Paragraph("Назначение:", label_style),
            Paragraph("Личный кабинет, служебные записки, расчетные листки, телефонный справочник", val_style),
        ],
        [
            Paragraph("Логин для входа:", label_style),
            Paragraph(f"<b>{user.username}</b>", val_code_style),
            Paragraph("Пароль:", label_style),
            Paragraph(f"<b>{work_password}</b>", val_code_style),
        ],
    ]
    portal_table = Table(portal_table_data, colWidths=[115, 155, 100, 177])
    portal_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdcdc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e9ecef")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(portal_table)
    elements.append(Spacer(1, 4))

    # 5. Секция: Электронная почта (Веб-интерфейс)
    mail_sec_header = Table(
        [[Paragraph("3. Корпоративная электронная почта", section_header_style)]],
        colWidths=[547],
    )
    mail_sec_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002b49")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(mail_sec_header)

    mail_table_data = [
        [
            Paragraph("Веб-почта (URL):", label_style),
            Paragraph("<b>https://ms.barkol.ru/</b>", val_code_style),
            Paragraph("Адрес почты (Логин):", label_style),
            Paragraph(f"<b>{user_email}</b>", val_code_style),
        ],
        [
            Paragraph("Пароль от почты:", label_style),
            Paragraph(f"<b>{work_password}</b>", val_code_style),
            Paragraph("Единый пароль:", label_style),
            Paragraph("Совпадает с паролем от портала компании", val_style),
        ],
    ]
    mail_table = Table(mail_table_data, colWidths=[115, 155, 120, 157])
    mail_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdcdc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e9ecef")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(mail_table)
    elements.append(Spacer(1, 4))

    # 6. Секция: Параметры ручной настройки почтовых клиентов (Outlook, Thunderbird, Android, iOS)
    client_sec_header = Table(
        [[Paragraph("4. Параметры настройки почтовых программ (Outlook, Thunderbird, Мобильные устройства)", section_header_style)]],
        colWidths=[547],
    )
    client_sec_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002b49")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(client_sec_header)

    client_table_data = [
        [
            Paragraph("Параметр", table_th_style),
            Paragraph("Сервер входящей почты (IMAP)", table_th_style),
            Paragraph("Сервер исходящей почты (SMTP)", table_th_style),
        ],
        [
            Paragraph("Имя сервера (Host):", table_td_left),
            Paragraph("<b>imap.barkol.ru</b>", table_td_style),
            Paragraph("<b>sm.barkol.ru</b>", table_td_style),
        ],
        [
            Paragraph("Порт подключения:", table_td_left),
            Paragraph("<b>993</b>", table_td_style),
            Paragraph("<b>465</b>", table_td_style),
        ],
        [
            Paragraph("Тип защиты (Шифрование):", table_td_left),
            Paragraph("SSL / TLS", table_td_style),
            Paragraph("SSL / TLS", table_td_style),
        ],
        [
            Paragraph("Имя пользователя (Логин):", table_td_left),
            Paragraph(f"Полный email (<b>{user_email}</b>)", table_td_style),
            Paragraph(f"Полный email (<b>{user_email}</b>)", table_td_style),
        ],
        [
            Paragraph("Аутентификация:", table_td_left),
            Paragraph("Обычный пароль", table_td_style),
            Paragraph("Обычный пароль (Аналогично IMAP)", table_td_style),
        ],
    ]
    client_table = Table(client_table_data, colWidths=[155, 196, 196])
    client_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdcdc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e9ecef")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(client_table)
    elements.append(Spacer(1, 4))

    # 7. Секция: Памятка по информационной безопасности и контакты
    security_sec_header = Table(
        [[Paragraph("5. Правила информационной безопасности и техническая поддержка", section_header_style)]],
        colWidths=[547],
    )
    security_sec_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002b49")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(security_sec_header)

    security_text = (
        "<b>Важно:</b> Учетные данные являются строго конфиденциальными. "
        "Категорически запрещается передавать логин и пароль третьим лицам.<br/>"
        "• В случае компрометации пароля немедленно обратитесь в службу информационных технологий.<br/>"
        "• <b>Техническая поддержка:</b> ИТ-отдел | Почта: <b>it_unit@barkol.ru</b> | Корпоративный портал: <b>https://corp.barkol.ru/</b>"
    )
    security_table = Table(
        [[Paragraph(security_text, memo_text_style)]],
        colWidths=[547],
    )
    security_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e1")),  # Светло-желтый фон
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ffe082")),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(security_table)

    # 8. Подвал документа
    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#b0bec5"),
            spaceBefore=5,
            spaceAfter=3,
        )
    )
    elements.append(
        Paragraph(
            "ООО Авиакомпания «БАРКОЛ» • Документ содержит конфиденциальную информацию • Выдано для служебного пользования",
            footer_text_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()
