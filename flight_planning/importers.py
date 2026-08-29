# flight_planning/importers.py
"""Модуль импорта данных периодических мероприятий из внешних систем (Excel, CSV, TSV, буфер обмена).

Предоставляет надежные сервисы разбора табличных файлов (.xlsx, .csv, .tsv, текст)
с автоматическим распознаванием структуры колонок, сопоставлением сотрудников,
видов мероприятий и типов ВС, фильтрацией дубликатов и детальным протоколированием.
"""

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set

from django.db import transaction
from contracts_app.models import TypeProperty
from customers_app.models import DataBaseUser
from .models import PeriodicCheckType, PeriodicCheckRecord


class PeriodicCheckImporter:
    """Сервис импорта и валидации данных периодических мероприятий персонала.

    Выполняет синтаксический анализ таблиц в форматах XLSX (без внешних зависимостей),
    CSV/TSV и прямого текста из буфера обмена, сопоставляет записи с БД портала,
    предотвращает дублирование и формирует развернутый отчет по каждой строке.
    """

    DEFAULT_COLUMN_MAPPING = {
        'employee': 0,
        'job': 1,
        'code': 2,
        'crew_role': 3,
        'aircraft': 4,
        'start_date': 5,
        'end_date': 6,
        'name': 7,
        'doc_number': 8,
        'issued_by': 9,
    }

    @classmethod
    def parse_source(
        cls,
        file_obj=None,
        text_content: Optional[str] = None,
        filename: str = ""
    ) -> List[List[str]]:
        """Извлекает двумерный массив строковых ячеек из файла или текстового содержимого.

        Args:
            file_obj: Файловый объект Django UploadedFile или bytes/BytesIO.
            text_content (str, optional): Текстовые данные из буфера обмена (TSV/CSV).
            filename (str, optional): Имя загруженного файла для определения расширения.

        Returns:
            List[List[str]]: Список строк, каждая из которых является списком значений ячеек.
        """
        rows: List[List[str]] = []

        # 1. Если передан прямой текст из буфера обмена
        if text_content and text_content.strip():
            return cls._parse_text_table(text_content)

        # 2. Если передан файл
        if not file_obj:
            return rows

        fn = (filename or getattr(file_obj, 'name', '')).lower()

        # Читаем байты файла
        if hasattr(file_obj, 'read'):
            file_bytes = file_obj.read()
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
        elif isinstance(file_obj, bytes):
            file_bytes = file_obj
        else:
            return rows

        if fn.endswith('.xlsx'):
            rows = cls._parse_xlsx_bytes(file_bytes)
        else:
            # Пробуем декодировать как CSV/TSV текст
            text_decoded = cls._decode_bytes_to_text(file_bytes)
            rows = cls._parse_text_table(text_decoded)

        return rows

    @classmethod
    def _decode_bytes_to_text(cls, file_bytes: bytes) -> str:
        """Декодирует байты в строку с автоопределением кодировки (UTF-8, CP1251, UTF-8-BOM).

        Args:
            file_bytes (bytes): Исходные байты файла.

        Returns:
            str: Декодированная строка.
        """
        encodings = ['utf-8-sig', 'utf-8', 'cp1251', 'windows-1251', 'latin-1']
        for enc in encodings:
            try:
                return file_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return file_bytes.decode('utf-8', errors='replace')

    @classmethod
    def _parse_text_table(cls, text: str) -> List[List[str]]:
        """Разбирает текстовую таблицу (TSV/CSV/Clipboard) в матрицу строк.

        Args:
            text (str): Текст таблицы.

        Returns:
            List[List[str]]: Список строк с ячейками.
        """
        rows: List[List[str]] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return rows

        # Определяем разделитель по первой строке
        first_line = lines[0]
        if '\t' in first_line:
            delimiter = '\t'
        elif ';' in first_line:
            delimiter = ';'
        elif ',' in first_line:
            delimiter = ','
        else:
            delimiter = '\t'

        reader = csv.reader(lines, delimiter=delimiter)
        for r in reader:
            cleaned_row = [str(c).strip() for c in r]
            if any(cleaned_row):
                rows.append(cleaned_row)
        return rows

    @classmethod
    def _parse_xlsx_bytes(cls, file_bytes: bytes) -> List[List[str]]:
        """Разбирает XLSX-файл без внешних библиотек через zipfile и ElementTree.

        Args:
            file_bytes (bytes): Бинарные данные .xlsx файла.

        Returns:
            List[List[str]]: Таблица строк.
        """
        rows: List[List[str]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                # 1. Читаем таблицу разделяемых строк (xl/sharedStrings.xml)
                shared_strings: List[str] = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                    for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                        text = ''
                        t_elem = si.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                        if t_elem is not None and t_elem.text:
                            text = t_elem.text
                        else:
                            for r_elem in si.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}r'):
                                rt_elem = r_elem.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                                if rt_elem is not None and rt_elem.text:
                                    text += rt_elem.text
                        shared_strings.append(text)

                # 2. Находим первый лист книги
                sheet_path = 'xl/worksheets/sheet1.xml'
                if sheet_path not in z.namelist():
                    sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]
                    if sheets:
                        sheet_path = sheets[0]
                    else:
                        return rows

                sheet_tree = ET.fromstring(z.read(sheet_path))
                sheet_data = sheet_tree.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData')
                if sheet_data is None:
                    return rows

                for row_elem in sheet_data.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                    row_cells: Dict[int, str] = {}
                    max_col_idx = 0
                    for c_elem in row_elem.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                        r_attr = c_elem.get('r', '')  # напр. A1, B2, AA10
                        col_match = re.match(r'([A-Z]+)', r_attr)
                        if col_match:
                            col_letters = col_match.group(1)
                            col_idx = 0
                            for ch in col_letters:
                                col_idx = col_idx * 26 + (ord(ch) - ord('A') + 1)
                            col_idx -= 1
                        else:
                            col_idx = len(row_cells)

                        cell_type = c_elem.get('t', '')
                        v_elem = c_elem.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                        val = ''
                        if cell_type == 's' and v_elem is not None and v_elem.text:
                            s_idx = int(v_elem.text)
                            if 0 <= s_idx < len(shared_strings):
                                val = shared_strings[s_idx]
                        elif cell_type == 'inlineStr':
                            is_elem = c_elem.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is')
                            if is_elem is not None:
                                t_elem = is_elem.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                                if t_elem is not None and t_elem.text:
                                    val = t_elem.text
                        elif v_elem is not None and v_elem.text:
                            val = v_elem.text

                        row_cells[col_idx] = val.strip()
                        if col_idx > max_col_idx:
                            max_col_idx = col_idx

                    if row_cells:
                        row_list = [row_cells.get(i, '') for i in range(max_col_idx + 1)]
                        if any(c for c in row_list):
                            rows.append(row_list)
        except Exception:
            pass

        return rows

    @classmethod
    def find_header_mapping(cls, rows: List[List[str]]) -> Tuple[int, Dict[str, int]]:
        """Автоматически находит строку заголовков и сопоставляет названия колонок с индексами.

        Args:
            rows (List[List[str]]): Сырые строки таблицы.

        Returns:
            Tuple[int, Dict[str, int]]: Кортеж (индекс строки заголовка, словарь {имя_поля: индекс_колонки}).
        """
        keywords_map = {
            'employee': ['сотрудник', 'фио', 'пилот', 'работник', 'персонал', 'fio'],
            'job': ['должность', 'профессия', 'job', 'position'],
            'code': ['код проверки', 'код', 'шифр', 'check_code', 'code'],
            'crew_role': ['должность в экипаже', 'роль в экипаже', 'роль', 'crew_role', 'role'],
            'aircraft': ['тип вс', 'вс', 'тип', 'самолет', 'вертолет', 'aircraft', 'aircraft_type'],
            'start_date': ['дата прохождения', 'дата начала', 'начало', 'дата сдачи', 'start_date', 'passed_date'],
            'end_date': ['дата окончания', 'действует до', 'окончание', 'срок действия', 'end_date', 'valid_until'],
            'name': ['полное наименование', 'наименование', 'название', 'вид мероприятия', 'наименование мероприятия', 'check_name'],
            'doc_number': ['номер документа', 'сертификат', 'свидетельство', 'справка', 'номер', 'doc_number'],
            'issued_by': ['кем выдано', 'организация', 'инструктор', 'ауц', 'issued_by'],
        }

        # Ищем строку заголовка среди первых 10 строк
        for row_idx in range(min(10, len(rows))):
            row = rows[row_idx]
            mapping: Dict[str, int] = {}
            matched_keys: Set[str] = set()

            for col_idx, cell_value in enumerate(row):
                cell_clean = str(cell_value).strip().lower()
                if not cell_clean:
                    continue

                for field_key, variants in keywords_map.items():
                    if field_key in matched_keys:
                        continue
                    if any(var == cell_clean or cell_clean.startswith(var) or var in cell_clean for var in variants):
                        mapping[field_key] = col_idx
                        matched_keys.add(field_key)
                        break

            # Если строка содержит хотя бы 'employee' или 'code' или даты — считаем её строкой заголовков
            if 'employee' in mapping or ('code' in mapping and ('start_date' in mapping or 'end_date' in mapping)):
                return row_idx, mapping

        # Если явные заголовки не распознаны, используем стандартный порядок
        return -1, cls.DEFAULT_COLUMN_MAPPING

    @classmethod
    def parse_date(cls, val: Any) -> Optional[date]:
        """Универсальный парсер даты (поддерживает ДД.ММ.ГГ, ДД.ММ.ГГГГ, ГГГГ-ММ-ДД, Excel серийные номера).

        Args:
            val: Значение ячейки даты (строка, число, объект даты).

        Returns:
            Optional[date]: Распознанная дата или None.
        """
        if not val:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()

        val_str = str(val).strip()
        if not val_str or val_str in ['-', '*', 'none', 'null']:
            return None

        # Проверка числового формата Excel (напр. 45544)
        try:
            num = float(val_str)
            if 30000 <= num <= 70000:
                base = date(1899, 12, 30)
                return base + timedelta(days=int(num))
        except (ValueError, TypeError):
            pass

        # Очистка разделителей
        cleaned = re.sub(r'[/\\-]+', '.', val_str)

        # Формат DD.MM.YYYY
        m4 = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', cleaned)
        if m4:
            try:
                return date(int(m4.group(3)), int(m4.group(2)), int(m4.group(1)))
            except ValueError:
                return None

        # Формат DD.MM.YY
        m2 = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{2})$', cleaned)
        if m2:
            try:
                y_short = int(m2.group(3))
                y = 2000 + y_short if y_short < 50 else 1900 + y_short
                return date(y, int(m2.group(2)), int(m2.group(1)))
            except ValueError:
                return None

        # Формат YYYY.MM.DD
        my = re.match(r'^(\d{4})\.(\d{1,2})\.(\d{1,2})$', cleaned)
        if my:
            try:
                return date(int(my.group(1)), int(my.group(2)), int(my.group(3)))
            except ValueError:
                return None

        return None

    @classmethod
    def match_employee(cls, name_raw: str, job_raw: str = "") -> Optional[DataBaseUser]:
        """Интеллектуальное сопоставление сотрудника по ФИО, инициалам или табельному номеру.

        Args:
            name_raw (str): Сырое строковое представление ФИО сотрудника из отчета.
            job_raw (str, optional): Должность для уточнения при однофамильцах.

        Returns:
            Optional[DataBaseUser]: Найденный объект сотрудника или None.
        """
        if not name_raw:
            return None

        clean_name = re.sub(r'\s+', ' ', str(name_raw).strip())
        if not clean_name:
            return None

        # 1. Точное совпадение по title
        user = DataBaseUser.objects.filter(title__iexact=clean_name).first()
        if user:
            return user

        # 2. Поиск по табельному номеру / service_number
        if clean_name.isdigit():
            user = DataBaseUser.objects.filter(service_number=clean_name).first()
            if user:
                return user

        # 3. Разбор частей ФИО (Фамилия И.О. или Фамилия Имя Отчество)
        parts = re.split(r'[\s.]+', clean_name)
        parts = [p for p in parts if p]

        if not parts:
            return None

        last_name = parts[0]

        # Ищем по фамилии
        candidates = list(DataBaseUser.objects.filter(last_name__iexact=last_name, is_active=True))
        if not candidates:
            # Попробуем нестрогий поиск по началу title
            candidates = list(DataBaseUser.objects.filter(title__istartswith=last_name, is_active=True))

        if not candidates:
            # Попробуем среди неактивных (на случай архивных записей)
            candidates = list(DataBaseUser.objects.filter(last_name__iexact=last_name))

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            # Уточняем по первой букве имени
            if len(parts) >= 2 and parts[1]:
                first_letter = parts[1][0].upper()
                filtered = [
                    u for u in candidates
                    if (u.first_name and u.first_name.upper().startswith(first_letter))
                    or (u.title and first_letter in u.title)
                ]
                if len(filtered) == 1:
                    return filtered[0]
                if len(filtered) > 1 and len(parts) >= 3 and parts[2]:
                    # Уточняем по первой букве отчества
                    patr_letter = parts[2][0].upper()
                    filtered2 = [
                        u for u in filtered
                        if (u.surname and u.surname.upper().startswith(patr_letter))
                        or (u.title and patr_letter in u.title)
                    ]
                    if len(filtered2) == 1:
                        return filtered2[0]
                    candidates = filtered2 if filtered2 else filtered
                elif filtered:
                    candidates = filtered

            # Если все еще несколько кандидатов и передана должность, пробуем уточнить по должности
            if job_raw and len(candidates) > 1:
                clean_job = job_raw.lower()
                for c in candidates:
                    if hasattr(c, 'user_work_profile') and c.user_work_profile and c.user_work_profile.job:
                        if clean_job in str(c.user_work_profile.job).lower():
                            return c

            return candidates[0]

        return None

    @classmethod
    def match_aircraft_type(cls, ac_raw: str) -> Optional[TypeProperty]:
        """Сопоставляет строковое наименование типа ВС с моделью TypeProperty.

        Символы '*', '-', 'Все', пустые строки трактуются как универсальное мероприятие (None).

        Args:
            ac_raw (str): Название типа ВС из отчета.

        Returns:
            Optional[TypeProperty]: Объект TypeProperty или None.
        """
        if not ac_raw:
            return None
        clean_ac = str(ac_raw).strip()
        if not clean_ac or clean_ac in ['*', '-', 'все', 'любой', 'общий', 'none', 'null']:
            return None

        # 1. Точное совпадение
        tp = TypeProperty.objects.filter(type_property__iexact=clean_ac).first()
        if tp:
            return tp

        # 2. Нестрогое совпадение по подстроке (напр. "Ми-8" найдет "Ми-8")
        tp = TypeProperty.objects.filter(type_property__icontains=clean_ac).first()
        if tp:
            return tp

        # 3. Нормализация латиницы/кириллицы (Mi-8 -> Ми-8)
        norm_ac = clean_ac.replace('Mi-', 'Ми-').replace('MI-', 'Ми-')
        tp = TypeProperty.objects.filter(type_property__icontains=norm_ac).first()
        return tp

    @classmethod
    def match_or_create_check_type(
        cls,
        code_raw: str,
        name_raw: str = "",
        aircraft_type: Optional[TypeProperty] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        auto_create: bool = True
    ) -> Tuple[Optional[PeriodicCheckType], bool]:
        """Находит или автоматически создает вид периодического мероприятия.

        Args:
            code_raw (str): Краткий шифр/код мероприятия (напр. "ППР", "CRM", "ТР2").
            name_raw (str, optional): Полное наименование мероприятия.
            aircraft_type (TypeProperty, optional): Привязка к типу ВС.
            start_date (date, optional): Дата прохождения для расчета срока действия.
            end_date (date, optional): Дата окончания действия.
            auto_create (bool): Флаг автоматического создания при отсутствии.

        Returns:
            Tuple[Optional[PeriodicCheckType], bool]: (Объект PeriodicCheckType, Флаг создания True/False).
        """
        clean_code = str(code_raw).strip()
        clean_name = str(name_raw).strip()

        if not clean_code and not clean_name:
            return None, False

        # 1. Поиск по коду и конкретному типу ВС
        if clean_code:
            qs = PeriodicCheckType.objects.filter(code__iexact=clean_code)
            if aircraft_type:
                ct = qs.filter(aircraft_type=aircraft_type).first()
                if ct:
                    return ct, False
            # Поиск универсального с таким кодом
            ct = qs.filter(aircraft_type__isnull=True).first()
            if ct:
                return ct, False
            # Любой первый с таким кодом
            ct = qs.first()
            if ct:
                return ct, False

        # 2. Поиск по наименованию
        if clean_name:
            qs = PeriodicCheckType.objects.filter(name__iexact=clean_name)
            if aircraft_type:
                ct = qs.filter(aircraft_type=aircraft_type).first()
                if ct:
                    return ct, False
            ct = qs.filter(aircraft_type__isnull=True).first() or qs.first()
            if ct:
                return ct, False

        # 3. Автосоздание нового вида мероприятия
        if auto_create:
            # Расчет срока действия в месяцах
            validity_months = 12
            if start_date and end_date and end_date > start_date:
                diff_days = (end_date - start_date).days
                validity_months = max(1, round(diff_days / 30.4375))

            final_name = clean_name if clean_name else (clean_code if clean_code else "Периодическое мероприятие")
            final_code = clean_code if clean_code else clean_name[:50]

            new_check_type = PeriodicCheckType.objects.create(
                name=final_name,
                code=final_code,
                aircraft_type=aircraft_type,
                validity_months=validity_months,
                applies_to='crew',
                is_active=True,
                description=f"Автоматически создано при импорте из внешней системы ({datetime.now().strftime('%d.%m.%Y')})"
            )
            return new_check_type, True

        return None, False

    @classmethod
    def process(
        cls,
        file_obj=None,
        text_content: Optional[str] = None,
        filename: str = "",
        user: Optional[DataBaseUser] = None,
        dry_run: bool = True,
        auto_create_types: bool = True
    ) -> Dict[str, Any]:
        """Выполняет полный цикл разбора, сопоставления и импорта записей мероприятий.

        Args:
            file_obj: Загруженный файл (.xlsx, .csv, .tsv).
            text_content (str, optional): Текст из буфера обмена.
            filename (str, optional): Имя файла.
            user (DataBaseUser, optional): Пользователь, выполняющий импорт.
            dry_run (bool): Режим предпросмотра без сохранения в БД.
            auto_create_types (bool): Разрешение на создание отсутствующих видов мероприятий.

        Returns:
            Dict[str, Any]: Словарь с итоговой статистикой и списком детализированных результатов по строкам.
        """
        rows = cls.parse_source(file_obj=file_obj, text_content=text_content, filename=filename)

        if not rows:
            return {
                'success': False,
                'dry_run': dry_run,
                'total_rows': 0,
                'created_count': 0,
                'updated_count': 0,
                'duplicate_count': 0,
                'error_count': 0,
                'created_types_count': 0,
                'rows_result': [],
                'summary_message': 'Файл или текстовые данные пусты, либо формат не поддерживается.',
            }

        header_idx, col_map = cls.find_header_mapping(rows)
        data_rows = rows[header_idx + 1:] if header_idx >= 0 else rows

        total_rows = len(data_rows)
        created_count = 0
        updated_count = 0
        duplicate_count = 0
        error_count = 0
        created_types_count = 0

        rows_result: List[Dict[str, Any]] = []
        new_records_to_create: List[PeriodicCheckRecord] = []

        # Запускаем обработку строк в атомарной транзакции (если не dry_run)
        with transaction.atomic():
            for line_idx, row in enumerate(data_rows, start=(header_idx + 2 if header_idx >= 0 else 1)):
                # Извлекаем значения колонок по сопоставленной карте
                raw_employee = row[col_map['employee']] if len(row) > col_map.get('employee', 0) else ''
                raw_job = row[col_map['job']] if len(row) > col_map.get('job', 1) else ''
                raw_code = row[col_map['code']] if len(row) > col_map.get('code', 2) else ''
                raw_crew_role = row[col_map['crew_role']] if len(row) > col_map.get('crew_role', 3) else ''
                raw_aircraft = row[col_map['aircraft']] if len(row) > col_map.get('aircraft', 4) else ''
                raw_start = row[col_map['start_date']] if len(row) > col_map.get('start_date', 5) else ''
                raw_end = row[col_map['end_date']] if len(row) > col_map.get('end_date', 6) else ''
                raw_name = row[col_map['name']] if len(row) > col_map.get('name', 7) else ''
                raw_doc_num = row[col_map['doc_number']] if len(row) > col_map.get('doc_number', 8) else ''
                raw_issued_by = row[col_map['issued_by']] if len(row) > col_map.get('issued_by', 9) else ''

                # Пропуск пустых строк
                if not any([raw_employee, raw_code, raw_name, raw_start, raw_end]):
                    continue

                row_info: Dict[str, Any] = {
                    'row_number': line_idx,
                    'raw_employee': raw_employee,
                    'raw_job': raw_job,
                    'raw_code': raw_code,
                    'raw_aircraft': raw_aircraft,
                    'raw_start_date': raw_start,
                    'raw_end_date': raw_end,
                    'raw_name': raw_name,
                    'matched_employee_name': '',
                    'matched_check_type_name': '',
                    'matched_aircraft_name': '',
                    'parsed_start_date': '',
                    'parsed_end_date': '',
                    'status': 'error',
                    'status_display': 'Ошибка',
                    'message': '',
                }

                # 1. Сопоставление сотрудника
                employee = cls.match_employee(raw_employee, job_raw=raw_job)
                if not employee:
                    row_info['status'] = 'error'
                    row_info['status_display'] = 'Пропущено (Сотрудник не найден)'
                    row_info['message'] = f"Сотрудник '{raw_employee}' не найден в базе данных пользователей портала."
                    error_count += 1
                    rows_result.append(row_info)
                    continue

                row_info['matched_employee_name'] = str(employee.title or employee.get_full_name() or employee.username)

                # 2. Парсинг дат
                start_date = cls.parse_date(raw_start)
                end_date = cls.parse_date(raw_end)

                if not start_date or not end_date:
                    row_info['status'] = 'error'
                    row_info['status_display'] = 'Пропущено (Некорректная дата)'
                    row_info['message'] = f"Некорректный формат дат: начало='{raw_start}', окончание='{raw_end}'."
                    error_count += 1
                    rows_result.append(row_info)
                    continue

                row_info['parsed_start_date'] = start_date.strftime('%d.%m.%Y')
                row_info['parsed_end_date'] = end_date.strftime('%d.%m.%Y')

                # 3. Сопоставление типа ВС
                aircraft_type = cls.match_aircraft_type(raw_aircraft)
                row_info['matched_aircraft_name'] = aircraft_type.type_property if aircraft_type else "*"

                # 4. Сопоставление вида мероприятия
                check_type, created_type_flag = cls.match_or_create_check_type(
                    code_raw=raw_code,
                    name_raw=raw_name,
                    aircraft_type=aircraft_type,
                    start_date=start_date,
                    end_date=end_date,
                    auto_create=(auto_create_types and not dry_run)
                )

                if created_type_flag:
                    created_types_count += 1

                if not check_type:
                    if dry_run and auto_create_types:
                        check_type_name_preview = raw_name or raw_code or "Новое мероприятие"
                        row_info['matched_check_type_name'] = f"{check_type_name_preview} (будет создан новый вид)"
                    else:
                        row_info['status'] = 'error'
                        row_info['status_display'] = 'Пропущено (Вид мероприятия не найден)'
                        row_info['message'] = f"Вид мероприятия с кодом '{raw_code}' / названием '{raw_name}' не найден в справочнике."
                        error_count += 1
                        rows_result.append(row_info)
                        continue
                else:
                    row_info['matched_check_type_name'] = str(check_type.name)

                # 5. Проверка на дубликаты
                # Правило пользователя: если ФИО, Должность/Вид мероприятия, Даты начала и окончания совпадают -> дубликат
                if check_type:
                    existing = PeriodicCheckRecord.objects.filter(
                        employee=employee,
                        check_type=check_type,
                        aircraft_type=aircraft_type,
                        start_date=start_date,
                        end_date=end_date
                    ).first()

                    if existing:
                        row_info['status'] = 'duplicate'
                        row_info['status_display'] = 'Дубликат (Пропущено)'
                        row_info['message'] = f"Запись уже существует в журнале (ID: #{existing.id})."
                        duplicate_count += 1
                        rows_result.append(row_info)
                        continue

                # 6. Успешная запись (или готовность к импорту в режиме предпросмотра)
                if dry_run:
                    row_info['status'] = 'preview_ok'
                    row_info['status_display'] = 'Готово к импорту'
                    row_info['message'] = 'Данные корректны, будет создана новая запись в журнале.'
                    created_count += 1
                else:
                    # Создание записи в БД
                    new_record = PeriodicCheckRecord(
                        employee=employee,
                        check_type=check_type,
                        aircraft_type=aircraft_type,
                        start_date=start_date,
                        end_date=end_date,
                        document_number=raw_doc_num,
                        issued_by=raw_issued_by,
                        notes=f"Импортировано из внешней системы ({datetime.now().strftime('%d.%m.%Y %H:%M')})",
                        created_by=user
                    )
                    new_records_to_create.append(new_record)
                    row_info['status'] = 'created'
                    row_info['status_display'] = 'Успешно добавлено'
                    row_info['message'] = 'Новая запись внесена в журнал периодических мероприятий.'
                    created_count += 1

                rows_result.append(row_info)

            # Пакетное сохранение при реальном импорте
            if not dry_run and new_records_to_create:
                PeriodicCheckRecord.objects.bulk_create(new_records_to_create)

        mode_str = "Предпросмотр завершен" if dry_run else "Импорт завершен"
        summary_msg = (
            f"{mode_str}. Обработано строк: {total_rows}. "
            f"Успешно: {created_count}, дубликатов: {duplicate_count}, "
            f"пропущено с ошибками: {error_count}."
        )
        if created_types_count > 0:
            summary_msg += f" Автоматически создано видов мероприятий: {created_types_count}."

        return {
            'success': True,
            'dry_run': dry_run,
            'total_rows': total_rows,
            'created_count': created_count,
            'updated_count': updated_count,
            'duplicate_count': duplicate_count,
            'error_count': error_count,
            'created_types_count': created_types_count,
            'rows_result': rows_result,
            'summary_message': summary_msg,
        }

    @classmethod
    def generate_template_csv(cls) -> str:
        """Генерирует эталонный CSV-шаблон для загрузки периодических мероприятий.

        Returns:
            str: Содержимое CSV файла с заголовками и примерами.
        """
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'Сотрудник',
            'Должность',
            'Код проверки',
            'Должность в экипаже',
            'Тип ВС',
            'Дата прохождения',
            'Дата окончания',
            'Полное наименование',
            'Номер документа',
            'Кем выдано'
        ])
        writer.writerow([
            'Абраменко Н.Ф.',
            'БМ ВС Ми-8',
            'ППР',
            'БМ',
            'Ми-8',
            '09.09.2025',
            '09.09.2026',
            'Проверка практич работы (БМ)',
            '№ 102/25',
            'АУЦ Баркол'
        ])
        writer.writerow([
            'Абраменко Н.Ф.',
            'БМ ВС Ми-8',
            'CRM',
            '*',
            '*',
            '28.10.2024',
            '28.10.2027',
            'Человеческий фактор',
            'Сертификат 554',
            'АУЦ ГА'
        ])
        writer.writerow([
            'Абраменко Н.Ф.',
            'БМ ВС Ми-8',
            'ТР2',
            'БМ',
            'Ми-8',
            '24.02.2026',
            '24.09.2026',
            'Тренажер КВП (коммерч.) -КВТ',
            '№ 88-ТР',
            'КТС Ми-8'
        ])
        return output.getvalue()
