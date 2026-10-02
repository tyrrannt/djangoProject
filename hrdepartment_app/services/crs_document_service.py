"""Сервисный слой генерации Свидетельства о ТО (CRS) по Приложению № 1 к ФАП-367.

Модуль отвечает за:
- ICAO-транслитерацию ФИО авиационных специалистов (ICAO Doc 9303);
- Русскоязычное форматирование календарных дат прописью;
- Формирование полного контекста данных из карты-наряда OutfitCard (включая
  двуязычные наименования ВС, программы ТО, наработку СНЭ/ППР, отложенные дефекты MEL/CDL,
  номер допуска CRS и штамп ПЭП по ГОСТ Р 7.0.97-2025);
- Потоковую сборку и рендеринг официального шаблона Word (.docx) через docxtpl.
"""

import io
import os
import pathlib
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, Union

from django.conf import settings
from django.utils import timezone
from docxtpl import DocxTemplate

from hrdepartment_app.models import OutfitCard


def transliterate_icao(text: str) -> str:
    """Выполняет транслитерацию кириллического текста в латиницу по стандарту ICAO Doc 9303.

    Используется в авиационной документации (свидетельства пилотов, удостоверения
    инженерно-технического персонала, формы CRS / Release to Service).

    Args:
        text: Исходная строка на русском языке (например, "Хаваев Виталий Анатольевич").

    Returns:
        Строка латиницей по стандарту ICAO (например, "Khavaev Vitalii Anatolevich").
    """
    if not text:
        return ""

    table: Dict[str, str] = {
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
        "Ж": "Zh", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
        "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
        "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
        "Ъ": "Ie", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Iu", "Я": "Ia",
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
        "ъ": "ie", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia",
    }
    return "".join(table.get(char, char) for char in text)


def format_russian_date_words(target_date: Optional[date]) -> str:
    """Форматирует дату в официальный деловой вид: «28» июня 2026.

    Args:
        target_date: Объект date или datetime.

    Returns:
        Строка вида «ДД» месяца ГГГГ.
    """
    if not target_date:
        return ""

    months: Tuple[str, ...] = (
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    m_name = months[target_date.month] if 1 <= target_date.month <= 12 else ""
    return f"«{target_date.day:02d}» {m_name} {target_date.year}"


def format_hours_minutes(
    val: Union[float, Decimal, int, time, None],
    fallback: str = "0 ч. 00 м.",
) -> str:
    """Форматирует наработку ВС или время в вид '693 ч. 53 м.' или '09 ч. 05 м.'.

    Args:
        val: Число часов в виде float / Decimal (например, 693.88) или объект datetime.time.
        fallback: Значение по умолчанию, если val None или невалиден.

    Returns:
        Строка вида '693 ч. 53 м.' или '09 ч. 05 м.'.
    """
    if val is None:
        return fallback
    if isinstance(val, time):
        return f"{val.hour:02d} ч. {val.minute:02d} м."
    try:
        num = float(val)
    except (TypeError, ValueError):
        return fallback

    total_minutes = int(round(num * 60))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours} ч. {minutes:02d} м."


def get_aircraft_bilingual_type(type_prop_name: Optional[str]) -> str:
    """Возвращает русско-английское наименование типа ВС для графы 7 CRS.

    Args:
        type_prop_name: Наименование типа ВС из базы (например, 'МИ-8Т', 'АН-2').

    Returns:
        Двуязычная строка вида 'Ми-8 / Mi-8' или исходное наименование.
    """
    if not type_prop_name:
        return "Ми-8 / Mi-8"

    normalized = type_prop_name.strip().upper()
    mapping: Dict[str, str] = {
        "МИ-8Т": "Ми-8 / Mi-8",
        "МИ-8": "Ми-8 / Mi-8",
        "МИ-8МТВ": "Ми-8МТВ / Mi-8MTV",
        "АН-2": "Ан-2 / An-2",
        "CESSNA 172S": "Cessna 172S",
        "CESSNA 172": "Cessna 172S",
        "R-44": "Robinson R-44",
        "R-66": "Robinson R-66",
        "МИ-2": "Ми-2 / Mi-2",
        "BK-117": "Eurocopter BK-117",
    }
    return mapping.get(normalized, f"{type_prop_name} / {transliterate_icao(type_prop_name)}")


def get_maintenance_program_defaults(type_prop_name: Optional[str]) -> Dict[str, str]:
    """Возвращает стандартные реквизиты утвержденной программы ТО (графа 14).

    Args:
        type_prop_name: Наименование типа ВС из модели Estate/TypeProperty.

    Returns:
        Словарь с ключами: name, issue, revision, date.
    """
    prog_name = "Регламент технического обслуживания"
    issue = "Воздушный транспорт"
    revision = "—"
    doc_date = "30.08.1991"

    if type_prop_name:
        tp = type_prop_name.strip().upper()
        if "АН-2" in tp:
            prog_name = "Регламент технического обслуживания самолета Ан-2"
            issue = "Воздушный транспорт"
            revision = "—"
            doc_date = "15.04.1984"
        elif "CESSNA" in tp:
            prog_name = "Approved Maintenance Program (Cessna 172S AMM)"
            issue = "Textron Aviation"
            revision = "Rev. 14"
            doc_date = "01.07.2020"
        elif "R-44" in tp:
            prog_name = "Approved Maintenance Program (R-44 Maintenance Manual)"
            issue = "Robinson Helicopter Company"
            revision = "Rev. 35"
            doc_date = "10.03.2021"
        elif "R-66" in tp:
            prog_name = "Approved Maintenance Program (R-66 Maintenance Manual)"
            issue = "Robinson Helicopter Company"
            revision = "Rev. 20"
            doc_date = "15.09.2021"

    return {
        "name": prog_name,
        "issue": issue,
        "revision": revision,
        "date": doc_date,
    }


def build_work_scope_text(outfit_card: OutfitCard) -> str:
    """Формирует нормативное описание объема выполненных работ для графы 15.

    Пример: 'Ф-9 (675 ± 20 ч.) к./н. от 26.06.2026 № 90/442'

    Args:
        outfit_card: Экземпляр карты-наряда на ТО.

    Returns:
        Текстовая строка графы 15.
    """
    parts = []

    # Периодические регламенты
    for pw in outfit_card.periodic_work.all():
        if pw.ratio and pw.lag_plus is not None:
            parts.append(f"{pw.code} ({int(pw.ratio)} ± {int(pw.lag_plus)} ч.)")
        elif pw.code:
            parts.append(pw.code)

    # Оперативные регламенты
    for ow in outfit_card.operational_work.all():
        parts.append(ow.name or str(ow))

    # Дополнительные работы
    if outfit_card.other_work:
        parts.append(outfit_card.other_work.strip())

    works_str = ", ".join(parts) if parts else "Регламентные работы ТО"

    card_date_str = (
        outfit_card.outfit_card_date.strftime("%d.%m.%Y")
        if outfit_card.outfit_card_date
        else timezone.now().strftime("%d.%m.%Y")
    )
    card_number = outfit_card.outfit_card_number or str(outfit_card.pk)

    return f"{works_str} к./н. от {card_date_str} № {card_number}"


def build_crs_context(outfit_card: OutfitCard) -> Dict[str, Any]:
    """Формирует словарь переменных для подстановки в docx-шаблон Свидетельства CRS.

    Поддерживает как русские наименования переменных ({{бортовой_номер}}),
    так и английские алиасы ({{aircraft_reg_number}}) для 100% совместимости.

    Args:
        outfit_card: Экземпляр карты-наряда на ТО ВС.

    Returns:
        Словарь контекста для DocxTemplate.render().
    """
    air_board = outfit_card.air_board
    aircraft_type_name = (
        air_board.type_property.type_property
        if air_board and air_board.type_property
        else ""
    )

    # 1. Порядковый номер свидетельства
    crs_num = (
        outfit_card.crs_number
        or f"{outfit_card.outfit_card_number or outfit_card.pk}/{outfit_card.outfit_card_date.year % 100 if outfit_card.outfit_card_date else '26'}"
    )

    # 2. Организация и сертификат (ФАП-145)
    from hrdepartment_app.models import CompanyMaintenanceCertificate
    active_cert = CompanyMaintenanceCertificate.objects.filter(is_active=True).order_by("-issue_date").first()
    if active_cert:
        org_name = active_cert.get_bilingual_organization()
        cert_text = active_cert.get_bilingual_certificate_text()
    else:
        org_name = "ООО АВИАКОМПАНИЯ «БАРКОЛ»  / AVIACOMPANY «BARKOL» ltd"
        cert_text = "от «25» декабря 2025 № 145-25-108 / № 145-25-108 Issued «25» December 2025"

    # 3. Заказ-задание
    card_num = outfit_card.outfit_card_number or str(outfit_card.pk)
    work_order = card_num.split("/")[0] if "/" in card_num else card_num

    # 4. Борт, тип, серийный номер
    reg_num = air_board.registration_number if air_board else "RA-00000"
    serial_num = (
        air_board.factory_number
        if air_board and air_board.factory_number
        else "—"
    )
    bilingual_type = get_aircraft_bilingual_type(aircraft_type_name)

    # 5. Наработка ВС
    hours_formatted = format_hours_minutes(outfit_card.flight_hours)
    cycles_formatted = f"{outfit_card.flight_cycles or 0} пос."

    # 6. Даты и время начала и окончания ТО (UTC)
    start_d = outfit_card.outfit_card_date or timezone.now().date()
    end_d = outfit_card.outfit_card_date_end or start_d

    if outfit_card.start_time:
        start_time_str = outfit_card.start_time.strftime("%H ч. %M м.")
    else:
        start_time_str = "12 ч. 00 м."

    if outfit_card.end_time:
        end_time_str = outfit_card.end_time.strftime("%H ч. %M м.")
    elif outfit_card.signed_at:
        end_time_str = outfit_card.signed_at.strftime("%H ч. %M м.")
    else:
        end_time_str = "05 ч. 00 м."

    start_text = f"{start_time_str}  {format_russian_date_words(start_d)}"
    end_text = f"{end_time_str}  {format_russian_date_words(end_d)}"

    # 7. Программа ТО
    prog_info = get_maintenance_program_defaults(aircraft_type_name)

    # 8. Объем работ
    work_scope = build_work_scope_text(outfit_card)

    # 9. Исключения (отложенные дефекты) - п. 16 CRS
    # Отметка "Да" ставится, если заполнено поле "Другие работы", но сам текст в графу не выводится
    has_exceptions = bool(outfit_card.other_work and outfit_card.other_work.strip())
    def_yes_mark = "[X]" if has_exceptions else "[ ]"
    def_no_mark = "[ ]" if has_exceptions else "[X]"

    # 10. Контрольный облет - п. 17 CRS
    test_flight_req_mark = "[X]" if getattr(outfit_card, "test_flight_required", False) else "[ ]"
    test_flight_no_req_mark = "[ ]" if getattr(outfit_card, "test_flight_required", False) else "[X]"

    # 11. Дата и время свидетельства (UTC)
    crs_date_words = format_russian_date_words(end_d)
    crs_time_utc = end_time_str

    # 12. Станция / МПД
    place_name = (
        outfit_card.outfit_card_place.name
        if outfit_card.outfit_card_place
        else "МПД Авиакомпания Баркол"
    )
    station_text = f"(ОП) {place_name}" if not place_name.startswith("(") else place_name

    # 13. Номер удостоверения подтверждающего персонала (бессрочное свидетельство специалиста по ТО ВС)
    staff = outfit_card.certifying_staff
    auth_number = (
        (staff.maintenance_staff_certificate.strip() if staff and getattr(staff, "maintenance_staff_certificate", "") else "")
        or outfit_card.crs_number
        or "III. № 0184728"
    )

    # 14. ФИО подтверждающего персонала
    staff = outfit_card.certifying_staff
    if staff:
        fio_ru = f"{staff.last_name or ''} {staff.first_name or ''} {staff.surname or ''}".strip()
        first_last_en = f"{transliterate_icao(staff.first_name or '')} {transliterate_icao(staff.last_name or '')}".strip()
    else:
        fio_ru = "Хаваев Виталий Анатольевич"
        first_last_en = "Vitalii Khavaev"

    # 15. Подпись / Штамп ПЭП по ГОСТ Р 7.0.97-2025
    if outfit_card.is_signed and outfit_card.signature_hash:
        short_hash = outfit_card.signature_hash[:12].upper()
        sig_date = (
            outfit_card.signed_at.strftime("%d.%m.%Y %H:%M UTC")
            if outfit_card.signed_at
            else end_d.strftime("%d.%m.%Y")
        )
        sig_text = f"ДОКУМЕНТ ПОДПИСАН ЭЦП\nСпециалист: {fio_ru}\nСертификат: {auth_number}\nДата: {sig_date}\nХэш ГОСТ: {short_hash}"
    elif staff:
        short_fio = f"{staff.last_name} {staff.first_name[:1]}.{staff.surname[:1]}." if staff.surname else f"{staff.last_name} {staff.first_name[:1]}."
        sig_text = f"{short_fio} [Подписано в СЭД]"
    else:
        sig_text = "____________________"

    return {
        # Русскоязычные переменные
        "номер_свидетельства": crs_num,
        "организация_выпуска": org_name,
        "сертификат_организации": cert_text,
        "заказ_задание": work_order,
        "эксплуатант": org_name,
        "тип_вс": bilingual_type,
        "бортовой_номер": reg_num,
        "заводской_номер": serial_num,
        "часы_налета": hours_formatted,
        "циклы": cycles_formatted,
        "программа_то": prog_info["name"],
        "начало_то": start_text,
        "окончание_то": end_text,
        "издание_программы": prog_info["issue"],
        "ревизия_программы": prog_info["revision"],
        "дата_программы": prog_info["date"],
        "выполненные_работы": work_scope,
        "отметка_дефекты_да": def_yes_mark,
        "отметка_дефекты_нет": def_no_mark,
        "облет_требуется": test_flight_req_mark,
        "облет_не_требуется": test_flight_no_req_mark,
        "дата_свидетельства": crs_date_words,
        "время_свидетельства_utc": crs_time_utc,
        "место_выполнения_работ": station_text,
        "номер_удостоверения": auth_number,
        "фио_специалиста": fio_ru,
        "фио_специалиста_en": first_last_en,
        "подпись_специалиста": sig_text,
        # Английские алиасы
        "crs_number": crs_num,
        "organization_name": org_name,
        "approval_certificate": cert_text,
        "work_order_number": work_order,
        "operator_name": org_name,
        "aircraft_type": bilingual_type,
        "aircraft_reg_number": reg_num,
        "aircraft_serial_number": serial_num,
        "flight_hours": hours_formatted,
        "flight_cycles": cycles_formatted,
        "maintenance_program_name": prog_info["name"],
        "start_maintenance_text": start_text,
        "end_maintenance_text": end_text,
        "maintenance_program_issue": prog_info["issue"],
        "maintenance_program_revision": prog_info["revision"],
        "maintenance_program_date": prog_info["date"],
        "work_scope": work_scope,
        "crs_date": crs_date_words,
        "crs_time_utc": crs_time_utc,
        "station_location": station_text,
        "authorization_number": auth_number,
        "certifying_staff_name": fio_ru,
        "certifying_staff_name_en": first_last_en,
        "certifying_staff_signature": sig_text,
    }


def get_crs_template_path(custom_path: Optional[str] = None) -> str:
    """Определяет абсолютный путь к файлу docx-шаблона CRS.

    Сначала проверяет наличие шаблона в static/DocxTemplates/crs_fap367_template.docx,
    затем в корне проекта (24429 Ф-9 90.442.docx).

    Args:
        custom_path: Пользовательский путь к файлу (если передан).

    Returns:
        Абсолютный путь к существующему docx файлу.

    Raises:
        FileNotFoundError: Если шаблон не найден ни по одному из стандартных путей.
    """
    if custom_path and os.path.exists(custom_path):
        return custom_path

    candidates = [
        pathlib.Path(settings.BASE_DIR) / "static" / "DocxTemplates" / "crs_fap367_template.docx",
        pathlib.Path(settings.BASE_DIR) / "24429 Ф-9 90.442.docx",
        pathlib.Path(settings.BASE_DIR) / "static" / "DocxTemplates" / "crs_fap367.docx",
    ]

    for p in candidates:
        if p.exists():
            return str(p)

    raise FileNotFoundError(f"Файл шаблона CRS не найден среди путей: {candidates}")


def generate_crs_docx(
    outfit_card: OutfitCard,
    template_path: Optional[str] = None,
) -> bytes:
    """Генерирует бинарный поток заполненного Свидетельства о ТО (CRS) в формате .docx.

    Args:
        outfit_card: Экземпляр карты-наряда на ТО ВС.
        template_path: Необязательный путь к кастомному файлу шаблона.

    Returns:
        Бинарное содержимое сгенерированного файла Word (.docx).

    Raises:
        FileNotFoundError: Если файл шаблона отсутствует на диске.
        Exception: При сбоях парсинга или рендеринга docxtpl.
    """
    path_to_template = get_crs_template_path(template_path)
    doc = DocxTemplate(path_to_template)

    context = build_crs_context(outfit_card)
    doc.render(context)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
