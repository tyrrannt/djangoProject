"""Сервис импорта реестров оборудования, СИ и инструмента из таблиц Excel (.xlsx / .xlsm) (ФАП-145).

Реализует:
1. Потоковое чтение и парсинг файлов Excel через openpyxl (включая листы с макросами .xlsm);
2. Автоматическое распознавание структуры колонок метрологического графика;
3. Синхронизацию 3-уровневой нормализации каталога:
   - Уровень 1: EquipmentName (категория, признак СИ);
   - Уровень 2: EquipmentTypeModel (номер в Госреестре СИ ФГИС «АРШИН», МПИ в мес., диапазон, класс);
   - Уровень 3: MaintenanceEquipment (экземпляр с S/N, кодом маркировки, датами поверки, ЦСМ, МПД);
4. Интеллектуальный маппинг мест базирования (PlaceProductionActivity);
5. Создание исторических записей в журнале поверок EquipmentVerificationRecord;
6. Поддержку режима симуляции (dry_run=True) с транзакционным откатом для предварительного аудита.
"""

import datetime
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import openpyxl
from django.db import transaction
from django.utils import timezone

from hrdepartment_app.models import (
    EquipmentName,
    EquipmentOperationalStatus,
    EquipmentType,
    EquipmentTypeModel,
    EquipmentVerificationRecord,
    EquipmentVerificationType,
    MaintenanceEquipment,
    PlaceProductionActivity,
)

logger = logging.getLogger(__name__)


@dataclass
class EquipmentImportRowResult:
    """Результат импорта отдельной строки таблицы."""

    row_index: int
    raw_number: Optional[Any]
    equipment_name: str
    type_model_name: str
    serial_number: str
    status: str
    mpd_name: str
    is_created: bool
    is_updated: bool
    message: str
    warning: Optional[str] = None


@dataclass
class EquipmentImportReport:
    """Сводный отчет по результатам импорта файла Excel."""

    success: bool
    dry_run: bool
    total_rows_read: int = 0
    created_equipment_count: int = 0
    updated_equipment_count: int = 0
    skipped_count: int = 0
    names_created: int = 0
    types_created: int = 0
    places_created: int = 0
    verifications_recorded: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    row_results: List[EquipmentImportRowResult] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Псевдоним для совместимости со свойством success."""
        return self.success

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует отчет в словарь для шаблонов и API."""
        return {
            "success": self.success,
            "dry_run": self.dry_run,
            "total_rows_read": self.total_rows_read,
            "created_equipment_count": self.created_equipment_count,
            "updated_equipment_count": self.updated_equipment_count,
            "skipped_count": self.skipped_count,
            "names_created": self.names_created,
            "types_created": self.types_created,
            "places_created": self.places_created,
            "verifications_recorded": self.verifications_recorded,
            "errors": self.errors,
            "warnings": self.warnings,
            "row_results_sample": [
                {
                    "row_index": r.row_index,
                    "equipment_name": r.equipment_name,
                    "type_model_name": r.type_model_name,
                    "serial_number": r.serial_number,
                    "mpd_name": r.mpd_name,
                    "status": r.status,
                    "action": "Создан" if r.is_created else ("Обновлен" if r.is_updated else "Пропущен"),
                    "message": r.message,
                }
                for r in self.row_results[:50]
            ],
        }


class EquipmentExcelImportService:
    """Сервис импорта метрологического графика и реестров оборудования из Excel."""

    # Словарь ключевых слов для автоматического определения категории инструмента по п. 22 ФАП-145
    CATEGORY_PATTERNS = [
        (
            re.compile(
                r"(манометр|вольтметр|амперметр|термометр|ареометр|миллиомметр|ваттметр|секундомер|"
                r"весы|безмен|динамометр|люксметр|микрометр|штангенциркуль|нутромер|линейка|угломер|"
                r"мегаомметр|микроомметр|гигрометр|барометр|тахометр|осциллограф|частотомер|аттенюатор)",
                re.IGNORECASE,
            ),
            EquipmentType.MEASURING,
        ),
        (
            re.compile(
                r"(кпа|тестер|проверка|пульт|analyzer|probalancer|стенд|имитатор|генератор|"
                r"калибратор|установка разряда|уза)",
                re.IGNORECASE,
            ),
            EquipmentType.CONTROL_TEST,
        ),
        (
            re.compile(
                r"(ключ|винт|съемник|струбцина|монтаж|приспособление|насадка|оправка|головка|"
                r"клещи|кусачки|отвертка|пассатижи|зажим)",
                re.IGNORECASE,
            ),
            EquipmentType.SPECIAL_TOOL,
        ),
        (
            re.compile(
                r"(стремянка|тележка|лебедка|колодка|заглушка|чехол|баллон|стрела|трап|гидроподъемник)",
                re.IGNORECASE,
            ),
            EquipmentType.GROUND_EQUIPMENT,
        ),
        (
            re.compile(r"(эталон|калибр|гиря|мера|набор мер)", re.IGNORECASE),
            EquipmentType.STANDARD_REFERENCE,
        ),
    ]

    # Словарь сопоставления строковых названий локаций с каноническими МПД компании
    MPD_CANONICAL_MAP = {
        "мячков": ("Аэродром Мячково", "Мячково"),
        "лаборатори": ("Аэродром Мячково", "Мячково"),
        "всс": ("Аэродром Мячково", "Мячково"),
        "акб": ("Аэродром Мячково", "Мячково"),
        "уза": ("Аэродром Мячково", "Мячково"),
        "волгоград": ("ОП МПД «Аэропорт Волгоград»", "Волгоград"),
        "оренбург": ("ОП МПД \"Оренбург\"", "Оренбург"),
        "богородск": ("МПД «Богородск»", "Богородск"),
        "йошкар": ("МПД «Йошкар-Ола»", "Йошкар-Ола"),
        "саратов": ("МПД «Саратов» (Гагаринский)", "Саратов"),
        "шумейк": ("МПД «Саратов» (Гагаринский)", "Саратов"),
        "левцов": ("МПД «Левцово»", "Левцово"),
        "брянск": ("МПД «Брянск»", "Брянск"),
        "пенз": ("МПД «Пенза»", "Пенза"),
        "туношн": ("ОП МПД \"Туношна\"", "Туношна"),
        "владимир": ("МПД «Владимир»", "Владимир"),
        "протасов": ("МПД «Рязань» (Протасово)", "Рязань"),
        "рязан": ("МПД «Рязань» (Протасово)", "Рязань"),
        "борки": ("МПД «Борки»", "Борки"),
        "бугуруслан": ("МПД «Бугуруслан»", "Бугуруслан"),
        "лопатин": ("МПД «Лопатино»", "Лопатино"),
        "невск": ("МПД «Невская»", "Невская"),
        "переслегин": ("МПД «Переслегино»", "Переслегино"),
        "песь": ("МПД «Песь»", "Песь"),
        "хелипорт": ("МПД «ХелиПорт»", "ХелиПорт"),
        "хеллипорт": ("МПД «ХелиПорт»", "ХелиПорт"),
        "мурманск": ("МПД «Мурманск»", "Мурманск"),
        "иас": ("г. Москва (Офис ИАС)", "Офис ИАС"),
        "москв": ("г. Москва", "Москва"),
        "липецк": ("МПД «Липецк»", "Липецк"),
        "тюмен": ("Аэропорт Плеханово (Тюмень)", "Тюмень"),
        "плеханово": ("Аэропорт Плеханово (Тюмень)", "Тюмень"),
        "тобольск": ("Аэропорт Ремезов (Тобольск)", "Тобольск"),
        "сургут": ("Аэропорт Сургут", "Сургут"),
    }

    def __init__(self) -> None:
        """Инициализация кэшей для ускорения выборки и предотвращения повторных запросов к БД."""
        self._equipment_names_cache: Dict[str, EquipmentName] = {}
        self._type_models_cache: Dict[Tuple[int, str], EquipmentTypeModel] = {}
        self._mpd_cache: Dict[str, PlaceProductionActivity] = {}

    def _preload_caches(self) -> None:
        """Загружает существующие справочники в память."""
        for eq_name in EquipmentName.objects.all():
            self._equipment_names_cache[eq_name.name.lower().strip()] = eq_name

        for tm in EquipmentTypeModel.objects.select_related("equipment_name"):
            self._type_models_cache[(tm.equipment_name_id, tm.name.lower().strip())] = tm

        for place in PlaceProductionActivity.objects.all():
            if place.name:
                self._mpd_cache[place.name.lower().strip()] = place
            if place.short_name:
                self._mpd_cache[place.short_name.lower().strip()] = place

    def parse_date(self, val: Any) -> Optional[datetime.date]:
        """Универсальный парсер дат из ячеек Excel (datetime, date, строки)."""
        if val is None:
            return None
        if isinstance(val, datetime.datetime):
            return val.date()
        if isinstance(val, datetime.date):
            return val

        if isinstance(val, str):
            clean = val.strip()
            if not clean or clean.lower() in ("нет", "—", "-", "б/д", "б/н"):
                return None
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%Y.%m.%d"):
                try:
                    return datetime.datetime.strptime(clean, fmt).date()
                except ValueError:
                    continue
        return None

    def parse_interval(self, val: Any) -> Optional[int]:
        """Парсит межповерочный интервал в месяцах из числа или строки.

        Args:
            val: Исходное значение из ячейки Excel (int, float, str).

        Returns:
            Optional[int]: Интервал в месяцах либо None.
        """
        if val is None:
            return None
        try:
            return int(float(str(val).replace(",", ".").split()[0]))
        except (ValueError, TypeError, IndexError):
            return None

    def detect_category(
        self,
        name: str,
        has_arshin_type: bool = False,
        has_cert: bool = False,
        has_interval: bool = False,
    ) -> str:
        """Определяет нормативную категорию прибора по п. 22 ФАП-145."""
        clean_name = name.strip()
        for pattern, cat in self.CATEGORY_PATTERNS:
            if pattern.search(clean_name):
                return cat

        if has_arshin_type or has_cert or has_interval:
            return EquipmentType.MEASURING

        return EquipmentType.SPECIAL_TOOL

    def resolve_place_production_activity(
        self,
        target_str: Optional[str],
        current_str: Optional[str],
        report: EquipmentImportReport,
        dry_run: bool,
    ) -> Optional[PlaceProductionActivity]:
        """Сопоставляет строковое описание локации с объектом PlaceProductionActivity."""
        raw = (target_str or "").strip()
        if not raw or raw.lower() in ("none", "отложил в поверку", "цас", "ростест", "утерян"):
            raw = (current_str or "").strip()

        if not raw or raw.lower() in ("none", "утерян"):
            raw = "Участок ТО \"Мячково\""

        low_raw = raw.lower()

        # 1. Поиск по словарю сопоставления
        matched_key = None
        canonical_name = None
        short_name = None
        for key, (full_n, short_n) in self.MPD_CANONICAL_MAP.items():
            if key in low_raw:
                matched_key = key
                canonical_name = full_n
                short_name = short_n
                break

        if not canonical_name:
            canonical_name = raw
            short_name = raw[:30]

        # 2. Проверка в кэше
        for cache_key, mpd in self._mpd_cache.items():
            if short_name and short_name.lower() in cache_key:
                return mpd
            if canonical_name and canonical_name.lower() in cache_key:
                return mpd

        # 3. Поиск по базе
        existing = PlaceProductionActivity.objects.filter(
            name__icontains=short_name
        ).first()
        if existing:
            self._mpd_cache[existing.name.lower().strip()] = existing
            return existing

        # 4. Если МПД еще не заведено — создаем
        if not dry_run:
            new_place = PlaceProductionActivity.objects.create(
                name=canonical_name,
                short_name=short_name,
            )
            self._mpd_cache[new_place.name.lower().strip()] = new_place
            report.places_created += 1
            return new_place
        else:
            mock_place = PlaceProductionActivity(name=canonical_name, short_name=short_name)
            self._mpd_cache[canonical_name.lower().strip()] = mock_place
            report.places_created += 1
            return mock_place

    def import_from_excel(
        self,
        file_path_or_obj: Union[str, Any],
        sheet_name: str = "Все СИ и Инструмент",
        dry_run: bool = False,
        limit: Optional[int] = None,
    ) -> EquipmentImportReport:
        """Выполняет полный импорт реестра оборудования из Excel-файла.

        Args:
            file_path_or_obj: Путь к файлу на диске или UploadedFile из запроса.
            sheet_name: Имя целевого листа Excel (по умолчанию 'Все СИ и Инструмент').
            dry_run: Режим симуляции без фиксации изменений в БД.
            limit: Ограничение количества строк для быстрого тестирования.

        Returns:
            EquipmentImportReport: Сводный отчет о количестве созданных и обновленных записей.
        """
        report = EquipmentImportReport(success=False, dry_run=dry_run)
        self._preload_caches()

        if isinstance(file_path_or_obj, bytes):
            file_path_or_obj = io.BytesIO(file_path_or_obj)

        try:
            wb = openpyxl.load_workbook(file_path_or_obj, data_only=True, read_only=True)
            if sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
            else:
                sheet = wb.active
        except Exception as exc:
            report.errors.append(f"Ошибка чтения файла Excel: {exc}")
            return report

        # Находим строку заголовков и определяем индексы столбцов
        header_row: Optional[Tuple[Any, ...]] = None
        rows_iterator = sheet.iter_rows(values_only=True)

        for row in rows_iterator:
            if not row or not any(row):
                continue
            first_cell = str(row[0]).strip().lower() if row[0] is not None else ""
            second_cell = str(row[1]).strip().lower() if len(row) > 1 and row[1] is not None else ""
            if "n" in first_cell or "№" in first_cell or "наименование" in second_cell:
                header_row = row
                break

        if not header_row:
            report.errors.append("Не удалось найти строку заголовков в листе Excel.")
            return report

        # Считываем строки данных
        data_rows: List[Tuple[int, Tuple[Any, ...]]] = []
        for idx, row in enumerate(rows_iterator, start=2):
            if not row or not any(row):
                continue
            data_rows.append((idx, row))
            if limit and len(data_rows) >= limit:
                break

        report.total_rows_read = len(data_rows)

        # Выполняем импорт в атомарной транзакции
        try:
            with transaction.atomic():
                for row_idx, row in data_rows:
                    self._process_single_row(row_idx, row, report, dry_run)

                if dry_run:
                    # В режиме симуляции откатываем транзакцию
                    transaction.set_rollback(True)
                    report.success = True
                else:
                    report.success = True

        except Exception as exc:
            logger.exception("Исключение при импорте оборудования из Excel: %s", exc)
            report.errors.append(f"Критическая ошибка сохранения данных: {exc}")
            report.success = False

        return report

    def _process_single_row(
        self,
        row_idx: int,
        row: Tuple[Any, ...],
        report: EquipmentImportReport,
        dry_run: bool,
    ) -> None:
        """Обрабатывает одну строку таблицы и сохраняет сущности в БД."""
        # 1. Извлекаем значения ячеек по позициям
        raw_num = row[0] if len(row) > 0 else None
        raw_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        raw_type = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
        raw_serial = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
        raw_accuracy = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""
        raw_arshin_type = str(row[5]).strip() if len(row) > 5 and row[5] is not None else ""
        raw_cert_number = str(row[6]).strip() if len(row) > 6 and row[6] is not None else ""
        raw_range = str(row[7]).strip() if len(row) > 7 and row[7] is not None else ""
        raw_location = str(row[8]).strip() if len(row) > 8 and row[8] is not None else ""
        raw_interval = row[9] if len(row) > 9 else None
        raw_last_date = row[10] if len(row) > 10 else None
        raw_next_date = row[11] if len(row) > 11 else None
        raw_status = str(row[13]).strip() if len(row) > 13 and row[13] is not None else ""
        raw_verifier = str(row[15]).strip() if len(row) > 15 and row[15] is not None else ""
        raw_target_place = str(row[16]).strip() if len(row) > 16 and row[16] is not None else ""

        if not raw_name:
            report.skipped_count += 1
            return

        # 2. Очистка и нормализация наименования и модели
        name_clean = raw_name.strip()
        type_clean = raw_type.strip() if raw_type and raw_type.lower() not in ("none", "-", "—") else "Базовый"

        # Парсинг интервала МПИ (в месяцах)
        interval_val = self.parse_interval(raw_interval)

        has_cert = bool(raw_cert_number and raw_cert_number.lower() not in ("none", "-", "—"))
        has_arshin_type = bool(raw_arshin_type and raw_arshin_type.lower() not in ("none", "-", "—"))
        has_interval = interval_val is not None and interval_val > 0

        # 3. Уровень 1: EquipmentName
        name_key = name_clean.lower()
        eq_name = self._equipment_names_cache.get(name_key)
        if not eq_name:
            category = self.detect_category(name_clean, has_arshin_type, has_cert, has_interval)
            is_measuring = (category == EquipmentType.MEASURING) or has_arshin_type or has_cert

            if not dry_run:
                eq_name, _ = EquipmentName.objects.get_or_create(
                    name=name_clean,
                    defaults={
                        "category": category,
                        "is_measuring_instrument": is_measuring,
                        "description": f"Импортировано из метрологического графика. Первичная категория: {category}",
                    },
                )
            else:
                eq_name = EquipmentName(
                    name=name_clean,
                    category=category,
                    is_measuring_instrument=is_measuring,
                )
            self._equipment_names_cache[name_key] = eq_name
            report.names_created += 1

        # 4. Уровень 2: EquipmentTypeModel
        model_key = (eq_name.pk or 0, type_clean.lower())
        type_model = self._type_models_cache.get(model_key)
        if not type_model:
            acc_val = raw_accuracy if raw_accuracy and raw_accuracy.lower() not in ("none", "-", "—") else ""
            range_val = raw_range if raw_range and raw_range.lower() not in ("none", "-", "—") else ""

            if not dry_run:
                type_model, _ = EquipmentTypeModel.objects.get_or_create(
                    equipment_name=eq_name,
                    name=type_clean,
                    defaults={
                        "arshin_type_number": raw_arshin_type if has_arshin_type else "",
                        "default_interval_months": interval_val or 12,
                        "accuracy_class": acc_val,
                        "measurement_range": range_val,
                    },
                )
            else:
                type_model = EquipmentTypeModel(
                    equipment_name=eq_name,
                    name=type_clean,
                    arshin_type_number=raw_arshin_type if has_arshin_type else "",
                    default_interval_months=interval_val or 12,
                    accuracy_class=acc_val,
                    measurement_range=range_val,
                )
            self._type_models_cache[model_key] = type_model
            report.types_created += 1

        # 5. Разрешение МПД базирования (PlaceProductionActivity)
        mpd = self.resolve_place_production_activity(raw_target_place, raw_location, report, dry_run)
        mpd_name_display = mpd.short_name or mpd.name if mpd else (raw_target_place or raw_location or "Мячково")

        # 6. Нормализация серийного номера (S/N) и маркировочного кода (п. 23 ФАП-145)
        clean_serial = raw_serial.strip()
        marking_code = ""

        if not clean_serial or clean_serial.lower() in ("б/н", "б/н.", "бн", "б.н.", "none"):
            clean_serial = ""
            marking_code = "б/н"
        elif re.search(r"\s{2,}", clean_serial):
            # В ячейке содержится составной номер вида '847120    ИР-НО-50-17'
            parts = [p.strip() for p in re.split(r"\s{2,}", clean_serial) if p.strip()]
            clean_serial = parts[0]
            if len(parts) > 1:
                marking_code = parts[1]
        elif "инв." in clean_serial.lower():
            marking_code = clean_serial
            clean_serial = ""
        elif "ир-" in clean_serial.lower() or "ир " in clean_serial.lower():
            marking_code = clean_serial
            clean_serial = ""

        # 7. Парсинг дат и метрологических статусов
        last_date = self.parse_date(raw_last_date)
        next_date = self.parse_date(raw_next_date)

        if not next_date and last_date and interval_val:
            # Расчет следующей поверки по МПИ
            next_date = last_date + datetime.timedelta(days=int(interval_val * 30.4375))

        # Определение физического статуса
        status_clean = raw_status.lower()
        if "неисправ" in status_clean:
            oper_status = EquipmentOperationalStatus.DEFECTIVE
        elif "утерян" in status_clean:
            oper_status = EquipmentOperationalStatus.SCRAPPED
        elif "ремонт" in status_clean:
            oper_status = EquipmentOperationalStatus.IN_REPAIR
        else:
            oper_status = EquipmentOperationalStatus.SERVICEABLE

        # Вид поверки
        if last_date or has_cert or has_arshin_type or has_interval:
            verif_type = EquipmentVerificationType.VERIFICATION
        else:
            verif_type = EquipmentVerificationType.NOT_REQUIRED

        # Место нахождения
        location_desc = raw_location.strip() if raw_location and raw_location.lower() not in ("none", "-") else ""

        # Примечания
        notes_parts = []
        if raw_status and raw_status.lower() in ("хранение", "утерян"):
            notes_parts.append(f"Исходный статус: {raw_status}")
        if raw_target_place and raw_target_place.lower() not in ("none", "-"):
            notes_parts.append(f"Направление/получатель: {raw_target_place}")
        notes_str = "; ".join(notes_parts)

        # 8. Уровень 3: MaintenanceEquipment
        if not dry_run:
            equipment_qs = MaintenanceEquipment.objects.filter(type_model=type_model)
            if clean_serial:
                equipment_obj = equipment_qs.filter(serial_number=clean_serial).first()
            elif marking_code and marking_code != "б/н":
                equipment_obj = equipment_qs.filter(marking_code=marking_code).first()
            else:
                equipment_obj = equipment_qs.filter(
                    production_place=mpd,
                    location=location_desc,
                    arshin_verification_number=raw_cert_number if has_cert else "",
                ).first()

            is_created = False
            is_updated = False

            if equipment_obj:
                # Обновляем существующий прибор свежими реквизитами
                if last_date:
                    equipment_obj.last_verification_date = last_date
                if next_date:
                    equipment_obj.next_verification_date = next_date
                if interval_val:
                    equipment_obj.interval_value = interval_val
                    equipment_obj.interval_unit = "months"
                if has_cert:
                    equipment_obj.arshin_verification_number = raw_cert_number
                if raw_verifier and raw_verifier.lower() not in ("none", "-"):
                    equipment_obj.verification_organization = raw_verifier
                if mpd:
                    equipment_obj.production_place = mpd
                if location_desc:
                    equipment_obj.location = location_desc
                equipment_obj.operational_status = oper_status
                equipment_obj.save()
                is_updated = True
                report.updated_equipment_count += 1
            else:
                equipment_obj = MaintenanceEquipment.objects.create(
                    type_model=type_model,
                    name=f"{eq_name.name} ({type_model.name})" if type_model.name != "Базовый" else eq_name.name,
                    equipment_type=eq_name.category,
                    serial_number=clean_serial,
                    marking_code=marking_code,
                    operational_status=oper_status,
                    verification_type=verif_type,
                    last_verification_date=last_date,
                    next_verification_date=next_date,
                    interval_value=interval_val or 12,
                    interval_unit="months",
                    interval_source="Метрологический график организации",
                    arshin_verification_number=raw_cert_number if has_cert else "",
                    verification_organization=raw_verifier if raw_verifier and raw_verifier.lower() not in ("none", "-") else "",
                    location=location_desc,
                    production_place=mpd,
                    notes=notes_str,
                )
                is_created = True
                report.created_equipment_count += 1

            # Фиксируем историческую запись поверки
            if last_date and (has_cert or raw_verifier):
                EquipmentVerificationRecord.objects.get_or_create(
                    equipment=equipment_obj,
                    verification_date=last_date,
                    defaults={
                        "verification_type": verif_type,
                        "valid_until": next_date,
                        "arshin_number": raw_cert_number if has_cert else "",
                        "organization": raw_verifier if raw_verifier and raw_verifier.lower() not in ("none", "-") else "",
                        "result_serviceable": (oper_status == EquipmentOperationalStatus.SERVICEABLE),
                        "notes": "Первичная загрузка из метрологического графика",
                    },
                )
                report.verifications_recorded += 1

            msg = "Успешно создан" if is_created else "Обновлен"
            report.row_results.append(
                EquipmentImportRowResult(
                    row_index=row_idx,
                    raw_number=raw_num,
                    equipment_name=eq_name.name,
                    type_model_name=type_model.name,
                    serial_number=clean_serial or marking_code,
                    status=oper_status,
                    mpd_name=mpd_name_display,
                    is_created=is_created,
                    is_updated=is_updated,
                    message=msg,
                )
            )
        else:
            # В режиме симуляции просто увеличиваем счетчик
            report.created_equipment_count += 1
            report.row_results.append(
                EquipmentImportRowResult(
                    row_index=row_idx,
                    raw_number=raw_num,
                    equipment_name=eq_name.name,
                    type_model_name=type_model.name,
                    serial_number=clean_serial or marking_code,
                    status=oper_status,
                    mpd_name=mpd_name_display,
                    is_created=True,
                    is_updated=False,
                    message="Симуляция: готов к созданию",
                )
            )
