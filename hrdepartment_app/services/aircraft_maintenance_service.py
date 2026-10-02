import csv
import datetime
import io
import logging
import math
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from contracts_app.models import Estate, TypeProperty
from customers_app.models import DataBaseUser
from hrdepartment_app.models import (
    AircraftHoursTracking,
    HoursTrackingSource,
    PeriodicWork,
    PeriodicWorkColor,
)

logger = logging.getLogger(__name__)


def get_aircraft_latest_hours(air_board: Estate) -> Optional[AircraftHoursTracking]:
    """Возвращает последнюю актуальную запись наработки для воздушного судна.

    Args:
        air_board (Estate): Воздушное судно.

    Returns:
        Optional[AircraftHoursTracking]: Последняя запись наработки или None.
    """
    if not air_board:
        return None
    return (
        AircraftHoursTracking.objects.filter(air_board=air_board)
        .order_by("-record_date", "-created_at")
        .first()
    )


def calculate_maintenance_approaches(
    air_board: Estate,
    current_hours: Optional[Union[Decimal, float]] = None,
) -> List[Dict[str, Any]]:
    """Рассчитывает подходы к периодическому техническому обслуживанию ВС (ФАП-367).

    Сопоставляет текущую наработку планера ВС (СНЭ) с нормативами периодических
    регламентных работ (PeriodicWork) для данного типа ВС. Вычисляет остаток часов
    до очередного регламента с учетом допустимых лагов (lag_minus / lag_plus)
    и формирует цветовой статус готовности (зеленый / желтый / красный).

    Args:
        air_board (Estate): Обслуживаемое воздушное судно.
        current_hours (Optional[Union[Decimal, float]]): Текущий налет СНЭ в часах.
            Если не указан, извлекается последняя запись из журнала AircraftHoursTracking.

    Returns:
        List[Dict[str, Any]]: Список словарей с характеристиками подходов:
            - work (PeriodicWork): Экземпляр периодической работы.
            - code (str): Код регламента (например, 'Ф-1', '100 часов').
            - name (str): Наименование регламента.
            - ratio (float): Норма-часы выполнения.
            - target_hours (float): Целевая наработка для проведения регламента.
            - current_hours (float): Текущий налет ВС.
            - remaining_hours (float): Остаток часов (положительный = до ТО, отрицательный = перелет).
            - lag_minus (int): Допустимый ранний лаг (часов).
            - lag_plus (int): Допустимый поздний лаг (часов).
            - status (str): Системный статус: 'ok', 'due', 'overdue'.
            - status_display (str): Текстовое описание статуса на русском языке.
            - color (str): Цвет статуса ('green', 'yellow', 'red').
            - badge_html (str): Готовый HTML-бейдж для отображения в интерфейсе.
    """
    if not air_board or not air_board.type_property:
        return []

    if current_hours is None:
        latest = get_aircraft_latest_hours(air_board)
        current_val = float(latest.flight_hours) if latest and latest.flight_hours else 0.0
    else:
        current_val = float(current_hours)

    periodic_works = (
        PeriodicWork.objects.filter(air_bord_type=air_board.type_property)
        .order_by("ratio", "name")
    )

    approaches: List[Dict[str, Any]] = []

    for work in periodic_works:
        ratio = float(work.ratio) if work.ratio else 0.0
        lag_minus = int(work.lag_minus) if work.lag_minus else 0
        lag_plus = int(work.lag_plus) if work.lag_plus else 0

        if ratio <= 0.0:
            continue

        # Определение целевого порога (target_hours)
        if current_val <= ratio:
            target_hours = ratio
        else:
            # Для периодических регламентов цикличность: определяем ближайший кратный порог
            multiples = math.ceil(current_val / ratio)
            target_hours = multiples * ratio

        remaining = round(target_hours - current_val, 1)

        # Классификация статуса по нормативным лагам ФАП-367:
        # 1. remaining < -lag_plus: Просрочено (красный) — превышен допустимый допуск «плюс»
        # 2. -lag_plus <= remaining <= lag_minus: В окне регламента / Требуется ТО (желтый)
        # 3. remaining > lag_minus: В ресурсе (зеленый) — до регламента более допустимого лага
        if remaining < -lag_plus:
            status = "overdue"
            status_display = f"Просрочен на {abs(remaining)} ч"
            color = "red"
            badge_html = f'<span class="badge bg-danger text-white"><i class="bx bx-error me-1"></i>Просрочен ({remaining} ч)</span>'
        elif remaining <= lag_minus:
            status = "due"
            status_display = f"Подход к ТО ({remaining} ч)"
            color = "yellow"
            badge_html = f'<span class="badge bg-warning text-dark"><i class="bx bx-time-five me-1"></i>Подход ({remaining} ч)</span>'
        else:
            status = "ok"
            status_display = f"В ресурсе ({remaining} ч)"
            color = "green"
            badge_html = f'<span class="badge bg-success text-white"><i class="bx bx-check-circle me-1"></i>Остаток {remaining} ч</span>'

        approaches.append({
            "work_id": work.pk,
            "code": work.code or f"#{work.pk}",
            "name": work.name or work.code,
            "ratio": ratio,
            "target_hours": target_hours,
            "current_hours": round(current_val, 1),
            "remaining_hours": remaining,
            "lag_minus": lag_minus,
            "lag_plus": lag_plus,
            "status": status,
            "status_display": status_display,
            "color": color,
            "badge_html": badge_html,
        })

    # Сортируем: сначала самые критичные (overdue -> due -> ok) и по возрастанию остатка часов
    status_priority = {"overdue": 0, "due": 1, "ok": 2}
    approaches.sort(key=lambda x: (status_priority.get(x["status"], 3), x["remaining_hours"]))

    return approaches


def get_nearest_maintenance_approach(
    air_board: Estate,
    current_hours: Optional[Union[Decimal, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Возвращает наиболее близкий или критичный подход к ТО для воздушного судна.

    Args:
        air_board (Estate): Воздушное судно.
        current_hours (Optional[Union[Decimal, float]]): Текущий налет.

    Returns:
        Optional[Dict[str, Any]]: Самый критичный подход к регламенту или None.
    """
    approaches = calculate_maintenance_approaches(air_board, current_hours=current_hours)
    return approaches[0] if approaches else None


def generate_aircraft_hours_excel_template() -> bytes:
    """Генерирует стилизованный эталонный файл Excel (.xlsx) для пакетного ввода наработки ВС.

    Создает таблицу со списком активных воздушных судов компании, заполненными
    бортовыми номерами, типами ВС и последними известными показателями наработки.

    Returns:
        bytes: Бинарное содержимое книги Excel (.xlsx).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Наработка ВС"

    # Стили оформления таблицы
    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color="D3D3D3"),
        right=Side(style="thin", color="D3D3D3"),
        top=Side(style="thin", color="D3D3D3"),
        bottom=Side(style="thin", color="D3D3D3"),
    )
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    headers = [
        "Бортовой номер ВС",
        "Тип ВС",
        "Дата фиксации (ДД.ММ.ГГГГ)",
        "Наработка СНЭ (ч)",
        "Наработка ППР (ч)",
        "Посадки / циклы",
        "Примечание",
    ]

    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    ws.row_dimensions[1].height = 26

    # Получаем действующие ВС
    active_aircraft = (
        Estate.objects.filter(decommission_date__isnull=True, type_property__isnull=False)
        .select_related("type_property")
        .order_by("type_property__type_property", "registration_number")
    )

    today_str = datetime.date.today().strftime("%d.%m.%Y")

    for row_idx, board in enumerate(active_aircraft, start=2):
        latest = get_aircraft_latest_hours(board)
        cur_hours = float(latest.flight_hours) if latest and latest.flight_hours else 0.0
        cur_tsor = float(latest.flight_hours_tsor) if latest and latest.flight_hours_tsor else 0.0
        cur_cycles = latest.flight_cycles if latest and latest.flight_cycles else 0

        row_data = [
            board.registration_number,
            str(board.type_property) if board.type_property else "",
            today_str,
            cur_hours,
            cur_tsor,
            cur_cycles,
            "",
        ]
        ws.append(row_data)

        ws.cell(row=row_idx, column=1).alignment = align_center
        ws.cell(row=row_idx, column=2).alignment = align_left
        ws.cell(row=row_idx, column=3).alignment = align_center
        ws.cell(row=row_idx, column=4).alignment = align_right
        ws.cell(row=row_idx, column=5).alignment = align_right
        ws.cell(row=row_idx, column=6).alignment = align_right
        ws.cell(row=row_idx, column=7).alignment = align_left

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.border = thin_border

        ws.row_dimensions[row_idx].height = 20

    # Автоматический подбор ширины колонок
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def _parse_date_value(val: Any) -> Optional[datetime.date]:
    """Вспомогательная функция парсинга даты из строки или datetime объекта."""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val

    s = str(val).strip()
    # Удаляем возможные суффиксы г. / года
    s = s.replace("г.", "").replace("года", "").replace("г", "").strip()

    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_decimal_value(val: Any, default: Decimal = Decimal("0.0")) -> Optional[Decimal]:
    """Вспомогательная функция парсинга десятичного числа с поддержкой запятых."""
    if val is None or str(val).strip() == "":
        return default
    s = str(val).strip().replace(" ", "").replace(",", ".")
    try:
        dec = Decimal(s)
        if dec < 0:
            return None
        return dec
    except (InvalidOperation, ValueError):
        return None


def _parse_int_value(val: Any, default: int = 0) -> Optional[int]:
    """Вспомогательная функция парсинга неотрицательного целого числа."""
    if val is None or str(val).strip() == "":
        return default
    s = str(val).strip().split(".")[0].split(",")[0]
    try:
        num = int(s)
        if num < 0:
            return None
        return num
    except (ValueError, TypeError):
        return None


def import_aircraft_hours_from_excel(
    file_obj: Union[UploadedFile, io.BytesIO],
    user: Optional[DataBaseUser] = None,
) -> Tuple[bool, int, List[str]]:
    """Парсит и валидирует Excel-файл со списком наработки ВС с транзакционным сохранением.

    Args:
        file_obj: Загруженный пользователем файл Excel (.xlsx).
        user (Optional[DataBaseUser]): Пользователь, выполняющий импорт.

    Returns:
        Tuple[bool, int, List[str]]: Кортеж:
            - bool: True если импорт выполнен успешно, False при ошибках валидации.
            - int: Количество успешно созданных записей наработки.
            - List[str]: Список текстовых сообщений об ошибках с номерами строк.
    """
    errors: List[str] = []

    try:
        wb = openpyxl.load_workbook(file_obj, data_only=True)
        sheet = wb.active
    except Exception as exc:
        return False, 0, [f"Не удалось открыть файл Excel: {exc}"]

    parsed_records: List[Dict[str, Any]] = []

    # Кэш ВС по регистрационным номерам (без дефисов и пробелов, в верхнем регистре)
    aircraft_qs = Estate.objects.all().select_related("type_property")
    aircraft_map: Dict[str, Estate] = {}
    for a in aircraft_qs:
        clean_reg = a.registration_number.strip().upper().replace(" ", "")
        aircraft_map[clean_reg] = a
        # Вариант без дефиса для гибкости (например RA-24123 -> RA24123)
        aircraft_map[clean_reg.replace("-", "")] = a

    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not any(row):
            continue

        raw_reg = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
        raw_date = row[2] if len(row) > 2 else None
        raw_hours = row[3] if len(row) > 3 else None
        raw_tsor = row[4] if len(row) > 4 else None
        raw_cycles = row[5] if len(row) > 5 else None
        raw_notes = str(row[6]).strip() if len(row) > 6 and row[6] is not None else ""

        if not raw_reg:
            errors.append(f"Строка {row_idx}: Не указан бортовой номер ВС (Колонка A).")
            continue

        clean_key = raw_reg.upper().replace(" ", "")
        clean_key_nohyphen = clean_key.replace("-", "")
        air_board = aircraft_map.get(clean_key) or aircraft_map.get(clean_key_nohyphen)

        if not air_board:
            errors.append(
                f"Строка {row_idx}: Воздушное судно с номером «{raw_reg}» не найдено в базе данных."
            )
            continue

        record_date = _parse_date_value(raw_date)
        if not record_date:
            errors.append(
                f"Строка {row_idx}: Некорректный формат даты «{raw_date}» (ожидается ДД.ММ.ГГГГ)."
            )
            continue

        flight_hours = _parse_decimal_value(raw_hours)
        if flight_hours is None:
            errors.append(
                f"Строка {row_idx}: Некорректное значение наработки СНЭ «{raw_hours}» (должно быть положительным числом)."
            )
            continue

        flight_hours_tsor = _parse_decimal_value(raw_tsor, default=Decimal("0.0"))
        if flight_hours_tsor is None:
            errors.append(
                f"Строка {row_idx}: Некорректное значение наработки ППР «{raw_tsor}»."
            )
            continue

        flight_cycles = _parse_int_value(raw_cycles, default=0)
        if flight_cycles is None:
            errors.append(
                f"Строка {row_idx}: Некорректное число посадок/циклов «{raw_cycles}»."
            )
            continue

        parsed_records.append({
            "air_board": air_board,
            "record_date": record_date,
            "flight_hours": flight_hours,
            "flight_hours_tsor": flight_hours_tsor,
            "flight_cycles": flight_cycles,
            "source": HoursTrackingSource.IMPORT,
            "notes": raw_notes or "Пакетный импорт из Excel",
            "created_by": user,
        })

    if errors:
        return False, 0, errors

    if not parsed_records:
        return False, 0, ["Файл не содержит строк данных для импорта."]

    created_count = 0
    with transaction.atomic():
        for item in parsed_records:
            AircraftHoursTracking.objects.create(**item)
            created_count += 1

    logger.info(
        "Successfully imported %d aircraft hours records from Excel by user %s",
        created_count,
        user,
    )
    return True, created_count, []


def import_aircraft_hours_from_csv(
    file_content: Union[str, bytes],
    user: Optional[DataBaseUser] = None,
) -> Tuple[bool, int, List[str]]:
    """Парсит и валидирует CSV-данные наработки ВС с транзакционным сохранением.

    Args:
        file_content: Содержимое файла CSV (строка или байты).
        user (Optional[DataBaseUser]): Пользователь, выполняющий импорт.

    Returns:
        Tuple[bool, int, List[str]]: Результат импорта (успех, кол-во, ошибки).
    """
    if isinstance(file_content, bytes):
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = file_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return False, 0, ["Не удалось определить кодировку CSV-файла (требуется UTF-8 или CP1251)."]
    else:
        text = file_content

    # Определение разделителя (запятая, точка с запятой, табуляция)
    first_line = text.strip().split("\n")[0] if text.strip() else ""
    delimiter = ";" if ";" in first_line else ("\t" if "\t" in first_line else ",")

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    if not rows or len(rows) < 2:
        return False, 0, ["CSV-файл пуст или содержит только строку заголовка."]

    # Используем логику через Excel-конвертер или напрямую построчно
    errors: List[str] = []
    parsed_records: List[Dict[str, Any]] = []

    aircraft_qs = Estate.objects.all().select_related("type_property")
    aircraft_map: Dict[str, Estate] = {}
    for a in aircraft_qs:
        clean_reg = a.registration_number.strip().upper().replace(" ", "")
        aircraft_map[clean_reg] = a
        aircraft_map[clean_reg.replace("-", "")] = a

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or not any(row):
            continue

        raw_reg = row[0].strip() if len(row) > 0 else ""
        raw_date = row[2].strip() if len(row) > 2 else ""
        raw_hours = row[3].strip() if len(row) > 3 else ""
        raw_tsor = row[4].strip() if len(row) > 4 else ""
        raw_cycles = row[5].strip() if len(row) > 5 else ""
        raw_notes = row[6].strip() if len(row) > 6 else ""

        if not raw_reg:
            errors.append(f"Строка {row_idx}: Не указан бортовой номер ВС.")
            continue

        clean_key = raw_reg.upper().replace(" ", "")
        clean_key_nohyphen = clean_key.replace("-", "")
        air_board = aircraft_map.get(clean_key) or aircraft_map.get(clean_key_nohyphen)

        if not air_board:
            errors.append(f"Строка {row_idx}: Борт «{raw_reg}» не найден в реестре ВС.")
            continue

        record_date = _parse_date_value(raw_date)
        if not record_date:
            errors.append(f"Строка {row_idx}: Некорректная дата «{raw_date}».")
            continue

        flight_hours = _parse_decimal_value(raw_hours)
        if flight_hours is None:
            errors.append(f"Строка {row_idx}: Некорректная наработка СНЭ «{raw_hours}».")
            continue

        flight_hours_tsor = _parse_decimal_value(raw_tsor, default=Decimal("0.0"))
        flight_cycles = _parse_int_value(raw_cycles, default=0)

        parsed_records.append({
            "air_board": air_board,
            "record_date": record_date,
            "flight_hours": flight_hours,
            "flight_hours_tsor": flight_hours_tsor,
            "flight_cycles": flight_cycles,
            "source": HoursTrackingSource.IMPORT,
            "notes": raw_notes or "Пакетный импорт из CSV",
            "created_by": user,
        })

    if errors:
        return False, 0, errors

    created_count = 0
    with transaction.atomic():
        for item in parsed_records:
            AircraftHoursTracking.objects.create(**item)
            created_count += 1

    return True, created_count, []
