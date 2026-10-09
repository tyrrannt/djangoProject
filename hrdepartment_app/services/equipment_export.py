"""Сервис генерации и экспорта ведомости учета оборудования, КПА и инструмента в Excel (ФАП-145, 102-ФЗ).

Формирует официальную стилизованную электронную ведомость в формате .xlsx, оптимизированную
для прямой печати на принтере (альбомная ориентация A4, вписывание по ширине, повторение шапки
на каждом листе, колонтитулы с нумерацией страниц, цветовая маркировка метрологического статуса
и итоговый блок подписей ответственных лиц ИАС).
"""

import io
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import timezone

from hrdepartment_app.models import (
    EquipmentOperationalStatus,
    EquipmentType,
    EquipmentVerificationType,
    MaintenanceEquipment,
)


def export_maintenance_equipment_to_excel(
    queryset: QuerySet[MaintenanceEquipment],
    filters_summary: Optional[str] = None,
    generated_by: Optional[str] = None,
) -> HttpResponse:
    """Генерирует официальную печатную ведомость учета оборудования и инструмента ТО ВС в Excel (.xlsx).

    Таблица настраивается под регламенты печати инженерно-авиационной службы (ИАС):
    - Альбомная ориентация (A4 Landscape);
    - Масштабирование таблицы по ширине листа (fit to 1 page wide);
    - Повторение строки заголовков столбцов на каждой напечатанной странице (print_title_rows);
    - Печать линий координатной сетки (gridLines);
    - Нижний колонтитул с автоматической нумерацией: «Страница X из Y»;
    - Цветовая дифференциация поверок (зеленый - годен, янтарный - истекает <=30 дн, красный - просрочен);
    - Сводный блок аналитики и подписей ответственных лиц в конце документа.

    Args:
        queryset (QuerySet[MaintenanceEquipment]): Отфильтрованная выборка оборудования для выгрузки.
        filters_summary (Optional[str]): Текстовое описание примененных фильтров для шапки отчета.
        generated_by (Optional[str]): ФИО или логин сотрудника, сформировавшего выгрузку.

    Returns:
        HttpResponse: HTTP-ответ с бинарным потоком файла Excel и заголовком Content-Disposition.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ведомость СИ и инструмента"

    # ==========================================
    # 1. Параметры страницы для печати (Print Setup)
    # ==========================================
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0  # Свободное распределение по вертикальным страницам
    ws.print_title_rows = "7:7"   # Повтор шапки таблицы на каждом листе при печати
    ws.print_options.gridLines = True
    ws.views.sheetView[0].showGridLines = True

    # Колонтитулы
    ws.oddFooter.center.text = "Страница &P из &N"
    ws.oddFooter.right.text = "ООО «АК БАРКОЛ» • ИАС • ФАП-145"
    ws.oddFooter.left.text = "Дата печати: &D"

    # ==========================================
    # 2. Шрифты, цвета и границы ячеек
    # ==========================================
    navy_dark = "002B49"
    navy_fill = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
    meta_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Статусные заливки метрологии
    valid_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # Мягкий зеленый
    valid_font = Font(name="Calibri", size=9, bold=True, color="166534")

    expiring_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Мягкий янтарный
    expiring_font = Font(name="Calibri", size=9, bold=True, color="92400E")

    expired_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # Мягкий красный
    expired_font = Font(name="Calibri", size=9, bold=True, color="991B1B")

    neutral_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")  # Серый
    neutral_font = Font(name="Calibri", size=9, color="475569")

    # Шрифты заголовков
    company_font = Font(name="Calibri", size=13, bold=True, color=navy_dark)
    sub_title_font = Font(name="Calibri", size=10, bold=True, color="475569")
    doc_title_font = Font(name="Calibri", size=12, bold=True, color=navy_dark)
    doc_rule_font = Font(name="Calibri", size=8.5, italic=True, color="64748B")
    meta_font = Font(name="Calibri", size=9, color="1E293B")
    tbl_hdr_font = Font(name="Calibri", size=9.5, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=9, color="0F172A")
    data_bold_font = Font(name="Calibri", size=9, bold=True, color="0F172A")
    summary_hdr_font = Font(name="Calibri", size=10, bold=True, color=navy_dark)
    signature_font = Font(name="Calibri", size=9.5, color="1E293B")

    # Границы
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )
    thick_bottom = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="medium", color=navy_dark),
    )
    double_bottom = Border(
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="double", color=navy_dark),
    )

    # ==========================================
    # 3. Формирование шапки документа (Строки 1–6)
    # ==========================================
    total_cols = 22

    # Строка 1: Компания
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    c1 = ws.cell(row=1, column=1, value="ООО АВИАКОМПАНИЯ «БАРКОЛ»")
    c1.font = company_font
    c1.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 20

    # Строка 2: Служба
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    c2 = ws.cell(row=2, column=1, value="ИНЖЕНЕРНО-АВИАЦИОННАЯ СЛУЖБА (ИАС)")
    c2.font = sub_title_font
    c2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 17

    # Строка 3: Наименование ведомости
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=total_cols)
    c3 = ws.cell(
        row=3,
        column=1,
        value="ВЕДОМОСТЬ УЧЕТА И МЕТРОЛОГИЧЕСКОГО СОСТОЯНИЯ ОБОРУДОВАНИЯ, КПА И ИНСТРУМЕНТА ТО ВС",
    )
    c3.font = doc_title_font
    c3.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 20

    # Строка 4: Ссылка на нормативные регламенты
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=total_cols)
    c4 = ws.cell(
        row=4,
        column=1,
        value="(в соответствии с требованиями Федеральных авиационных правил ФАП-145 и Федерального закона № 102-ФЗ «Об обеспечении единства измерений»)",
    )
    c4.font = doc_rule_font
    c4.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 15

    # Строка 5: Метаданные выгрузки
    now_str = timezone.now().strftime("%d.%m.%Y %H:%M")
    author_str = generated_by or "Пользователь портала"
    filt_str = filters_summary or "Все записи реестра (без ограничений)"
    total_records = queryset.count()

    meta_text = (
        f"Дата выгрузки: {now_str}  |  Сформировал: {author_str}  |  "
        f"Параметры отбора: [{filt_str}]  |  Записей в ведомости: {total_records} ед."
    )
    ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=total_cols)
    c5 = ws.cell(row=5, column=1, value=meta_text)
    c5.font = meta_font
    c5.fill = meta_fill
    c5.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[5].height = 20

    # Строка 6: Разделитель
    ws.row_dimensions[6].height = 6

    # ==========================================
    # 4. Заголовки столбцов таблицы (Строка 7)
    # ==========================================
    headers = [
        "№ п/п",
        "Наименование оборудования / инструмента",
        "Категория (ФАП-145)",
        "Тип / Марка / Модель",
        "Чертежный номер (P/N)",
        "Заводской номер (S/N)",
        "Код маркировки",
        "Диапазон измерений",
        "Класс точности",
        "Применимость к типам ВС",
        "Место базирования (МПД)",
        "Место хранения / размещения",
        "Вид контроля",
        "Дата посл. поверки",
        "Интервал (мес.)",
        "Срок действия (до)",
        "Остаток срока / Статус поверки",
        "№ свид. / записи АРШИН",
        "Поверитель (ЦСМ / лаборатория)",
        "Физический статус",
        "Ответственное лицо",
        "Примечание",
    ]

    ws.row_dimensions[7].height = 34
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=7, column=col_idx, value=header)
        cell.font = tbl_hdr_font
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thick_bottom

    # ==========================================
    # 5. Заполнение строк данными
    # ==========================================
    today = timezone.now().date()
    warning_date = today + timedelta(days=30)

    # Счетчики для сводки
    count_valid = 0
    count_expiring = 0
    count_expired = 0
    count_not_required = 0

    current_row = 8

    # Оптимизированная выборка связей
    items = queryset.select_related(
        "production_place",
        "responsible_person",
        "type_model",
        "type_model__equipment_name",
    ).prefetch_related("applicable_aircraft_types")

    for idx, eq in enumerate(items, 1):
        ws.row_dimensions[current_row].height = 20
        is_even = (idx % 2 == 0)
        row_bg = zebra_fill if is_even else None

        # 1. Наименование и модель
        if eq.type_model and eq.type_model.equipment_name:
            eq_name = eq.type_model.equipment_name.name
            type_model_str = eq.type_model.name
        else:
            eq_name = eq.name
            type_model_str = "—"

        # 2. Категория
        category_str = eq.get_equipment_type_display()

        # 3. P/N и S/N
        pn_str = eq.part_number or (eq.type_model.part_number if eq.type_model else "") or "—"
        sn_str = eq.serial_number or "б/н"
        marking_str = eq.marking_code or "—"

        # 3.1. Диапазон измерений и класс точности (ФАП-145, 102-ФЗ)
        range_str = eq.measurement_range or "—"
        accuracy_str = eq.accuracy_class or "—"

        # 4. Применимость к ВС
        ac_types = [t.type_property for t in eq.applicable_aircraft_types.all()]
        ac_types_str = ", ".join(ac_types) if ac_types else "Все типы ВС"

        # 5. МПД и размещение
        mpd_str = eq.production_place.name if eq.production_place else "—"
        location_str = eq.location or "—"

        # 6. Вид контроля и даты
        ctrl_type_str = eq.get_verification_type_display()
        last_date_str = eq.last_verification_date.strftime("%d.%m.%Y") if eq.last_verification_date else "—"
        interval_str = str(eq.interval_value) if eq.interval_value else "—"
        next_date_str = eq.next_verification_date.strftime("%d.%m.%Y") if eq.next_verification_date else "—"

        # 7. Метрологический статус и остаток дней
        metrology_code = eq.metrology_status
        days_left = eq.days_until_verification

        if metrology_code == "NOT_APPLICABLE":
            status_text = "Не требуется (исправен)"
            status_fill = neutral_fill
            status_font = neutral_font
            count_not_required += 1
        elif metrology_code == "EXPIRED":
            days_str = f"{abs(days_left)} дн." if days_left is not None else ""
            status_text = f"Просрочен ({days_str}) / Изолятор" if days_str else "Просрочен / Изолятор"
            status_fill = expired_fill
            status_font = expired_font
            count_expired += 1
        elif metrology_code == "EXPIRING":
            days_str = f"{days_left} дн." if days_left is not None else ""
            status_text = f"Истекает ({days_str})" if days_str else "Истекает"
            status_fill = expiring_fill
            status_font = expiring_font
            count_expiring += 1
        elif metrology_code == "VALID":
            days_str = f"осталось {days_left} дн." if days_left is not None else ""
            status_text = f"Годен ({days_str})" if days_str else "Годен к ТО"
            status_fill = valid_fill
            status_font = valid_font
            count_valid += 1
        else:
            status_text = "Нет сведений о поверке"
            status_fill = expired_fill
            status_font = expired_font
            count_expired += 1

        # 8. Номер свидетельства и поверитель
        arshin_str = eq.arshin_verification_number or "—"
        org_str = eq.verification_organization or "—"

        # 9. Физический статус
        phys_status_str = eq.get_operational_status_display()

        # 10. Ответственный и примечания
        resp_person = "—"
        if eq.responsible_person:
            resp_person = eq.responsible_person.title or eq.responsible_person.get_full_name() or eq.responsible_person.username

        notes_str = eq.notes or ""

        # Запись значений в строку (22 колонки)
        row_values = [
            idx,
            eq_name,
            category_str,
            type_model_str,
            pn_str,
            sn_str,
            marking_str,
            range_str,
            accuracy_str,
            ac_types_str,
            mpd_str,
            location_str,
            ctrl_type_str,
            last_date_str,
            interval_str,
            next_date_str,
            status_text,
            arshin_str,
            org_str,
            phys_status_str,
            resp_person,
            notes_str,
        ]

        for col_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = data_font
            cell.border = thin_border

            # Выравнивание по колонкам
            if col_idx in (1, 5, 6, 7, 8, 9, 14, 15, 16, 17, 20):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            # Фоновое оформление ячеек
            if col_idx == 17:
                # Столбец метрологического статуса
                cell.fill = status_fill
                cell.font = status_font
            elif col_idx == 20 and eq.operational_status in (
                EquipmentOperationalStatus.DEFECTIVE,
                EquipmentOperationalStatus.QUARANTINED,
            ):
                cell.fill = expired_fill
                cell.font = expired_font
            elif row_bg:
                cell.fill = row_bg

        current_row += 1

    # ==========================================
    # 6. Блок итоговой аналитики (Summary)
    # ==========================================
    summary_row = current_row + 1
    ws.row_dimensions[summary_row].height = 24
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=total_cols)
    summary_cell = ws.cell(row=summary_row, column=1)
    summary_cell.value = (
        f"ИТОГО ПО ВЕДОМОСТИ:  Всего оборудования: {total_records} ед.   |   "
        f"Годно к применению: {count_valid} ед.   |   "
        f"Истекает поверка (≤30 дн.): {count_expiring} ед.   |   "
        f"Просрочено / Изолятор брака: {count_expired} ед.   |   "
        f"Контроль не требуется: {count_not_required} ед."
    )
    summary_cell.font = summary_hdr_font
    summary_cell.fill = meta_fill
    summary_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    summary_cell.border = double_bottom

    # ==========================================
    # 7. Блок официальных подписей ответственных лиц
    # ==========================================
    sig_row_1 = summary_row + 2
    ws.row_dimensions[sig_row_1].height = 22
    ws.merge_cells(start_row=sig_row_1, start_column=2, end_row=sig_row_1, end_column=10)
    sig1 = ws.cell(
        row=sig_row_1,
        column=2,
        value="Ответственный за метрологическое обеспечение ТО ВС: ______________________ / ______________________",
    )
    sig1.font = signature_font
    sig1.alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells(start_row=sig_row_1, start_column=12, end_row=sig_row_1, end_column=21)
    sig2 = ws.cell(
        row=sig_row_1,
        column=12,
        value="Начальник ИАС (Главный инженер): ______________________ / ______________________",
    )
    sig2.font = signature_font
    sig2.alignment = Alignment(horizontal="left", vertical="center")

    sig_row_2 = sig_row_1 + 1
    ws.row_dimensions[sig_row_2].height = 20
    ws.merge_cells(start_row=sig_row_2, start_column=2, end_row=sig_row_2, end_column=10)
    sig_date = ws.cell(row=sig_row_2, column=2, value="Дата: «____» ________________ 202__ г.")
    sig_date.font = signature_font
    sig_date.alignment = Alignment(horizontal="left", vertical="center")

    # ==========================================
    # 8. Автоматический расчет оптимальной ширины колонок
    # ==========================================
    # Базовые комфортные ширины для альбомной печати (A4 Landscape)
    default_widths = {
        1: 6,    # № п/п
        2: 26,   # Наименование
        3: 18,   # Категория
        4: 16,   # Тип/Марка/Модель
        5: 15,   # P/N
        6: 15,   # S/N
        7: 15,   # Код маркировки
        8: 18,   # Диапазон измерений
        9: 14,   # Класс точности
        10: 16,  # Применимость к ВС
        11: 20,  # МПД
        12: 18,  # Размещение
        13: 16,  # Вид контроля
        14: 12,  # Дата посл. поверки
        15: 10,  # Интервал (мес)
        16: 12,  # Срок действия (до)
        17: 22,  # Статус поверки
        18: 22,  # № АРШИН
        19: 18,  # Поверитель
        20: 15,  # Физ. статус
        21: 18,  # Ответственный
        22: 20,  # Примечание
    }

    for col_idx in range(1, total_cols + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = default_widths.get(col_idx, 15)

    # ==========================================
    # 9. Сохранение в буфер и формирование HTTP-ответа
    # ==========================================
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename_timestamp = timezone.now().strftime("%Y%m%d_%H%M")
    filename = f"Metrological_Equipment_Barkol_{filename_timestamp}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
