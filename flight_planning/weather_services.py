"""Сервисы парсинга и синхронизации авиационной метеорологии (METAR / TAF).

Предоставляет надежный парсер телеграмм METAR, SPECI и TAF в соответствии со стандартами ICAO (Doc 8896),
определяет летные категории метеоусловий (VFR, MVFR, IFR, LIFR), переводит авиационные метеоявления на русский язык
и обеспечивает синхронизацию с открытыми метеорологическими шлюзами (NOAA / Aviation Weather Center).
"""

from datetime import date, datetime, timezone as dt_timezone
import json
import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from hrdepartment_app.models import PlaceProductionActivity
from .models import (
    AviationWeatherForecast,
    AviationWeatherObservation,
    AviationWeatherStation,
    CoordinateWeatherForecast,
)

logger = logging.getLogger(__name__)

# Словари перевода метеоявлений ICAO на русский язык
WEATHER_INTENSITY = {
    "-": "Слабый",
    "+": "Сильный",
    "VC": "В окрестностях",
}

CYRILLIC_ICAO_MAP = {
    'А': 'A', 'Б': 'B', 'В': 'W', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ж': 'V',
    'З': 'Z', 'И': 'I', 'Й': 'J', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F',
    'Х': 'H', 'Ц': 'C', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH', 'Ы': 'Y', 'Э': 'E',
    'Ю': 'YU', 'Я': 'Q', 'Ь': 'X', 'Ъ': 'X',
}


def normalize_icao_code(code_str: Optional[str]) -> str:
    """Нормализует 4-буквенный ICAO код метеостанции или аэродрома.

    Очищает пробелы, переводит в верхний регистр и транслитерирует кириллические
    символы по стандарту ИКАО/АФТН РФ (например: 'УРВВ' -> 'URWW', 'УСРР' -> 'USRR', 'УННТ' -> 'UNNT').

    Args:
        code_str (Optional[str]): Исходный код или строка ввода.

    Returns:
        str: 4-буквенный код латиницей в верхнем регистре (или пустая строка/исходная при невозможности).
    """
    if not code_str:
        return ""
    code = code_str.strip().upper()
    if not code:
        return ""

    if re.match(r"^[A-Z0-9]{4}$", code):
        return code

    result = []
    for ch in code:
        if ch in CYRILLIC_ICAO_MAP:
            result.append(CYRILLIC_ICAO_MAP[ch])
        else:
            result.append(ch)

    translit_code = "".join(result)
    if len(translit_code) == 4 and re.match(r"^[A-Z0-9]{4}$", translit_code):
        return translit_code

    return code

WEATHER_DESCRIPTORS = {
    "MI": "тонкий",
    "PR": "частичный",
    "BC": "обрывки",
    "DR": "поземок",
    "BL": "метель (низовая)",
    "SH": "ливневый",
    "TS": "гроза",
    "FZ": "переохлажденный (замерзающий)",
}

WEATHER_PHENOMENA = {
    "DZ": "морось",
    "RA": "дождь",
    "SN": "снег",
    "SG": "снежные зерна",
    "PL": "ледяная крупа",
    "GR": "град",
    "GS": "мелкий град / снежная крупа",
    "UP": "неопределенные осадки",
    "BR": "дымка",
    "FG": "туман",
    "FU": "дым",
    "VA": "вулканический пепел",
    "DU": "пыль (широко распространенная)",
    "SA": "песок",
    "HZ": "мгла",
    "PO": "пыльные/песчаные вихри",
    "SQ": "шквал",
    "FC": "смерч/торнадо",
    "SS": "песчаная буря",
    "DS": "пыльная буря",
}


class MetarParser:
    """Парсер авиационных метеорологических сводок METAR и SPECI."""

    @staticmethod
    def decode_weather_phenomena(code_str: str) -> str:
        """Переводит код метеоявления ICAO в человекочитаемый текст на русском языке.

        Args:
            code_str (str): Кодовая группа метеоявления (например, '+SHSNRA', '-FZFG', 'TSRA').

        Returns:
            str: Расшифрованное описание на русском языке (например, 'Сильный ливневый снег с дождем').
        """
        code = code_str.strip()
        if not code:
            return ""

        intensity_prefix = ""
        if code.startswith("+"):
            intensity_prefix = "Сильный "
            code = code[1:]
        elif code.startswith("-"):
            intensity_prefix = "Слабый "
            code = code[1:]
        elif code.startswith("VC"):
            intensity_prefix = "В окрестностях: "
            code = code[2:]

        # Ищем дескрипторы
        descriptor_desc = ""
        for desc_code, desc_label in WEATHER_DESCRIPTORS.items():
            if code.startswith(desc_code):
                descriptor_desc = desc_label
                code = code[len(desc_code):]
                break

        # Ищем явления осадков и помутнения атмосферы
        phenomena_parts = []
        while len(code) >= 2:
            chunk = code[:2]
            if chunk in WEATHER_PHENOMENA:
                phenomena_parts.append(WEATHER_PHENOMENA[chunk])
                code = code[2:]
            else:
                break

        if not phenomena_parts and not descriptor_desc:
            return code_str

        all_phenomena = " с ".join(phenomena_parts) if len(phenomena_parts) > 1 else (phenomena_parts[0] if phenomena_parts else "")
        if descriptor_desc:
            full_str = f"{descriptor_desc} {all_phenomena}".strip()
        else:
            full_str = all_phenomena

        result = f"{intensity_prefix}{full_str}".strip()
        return result[0].upper() + result[1:] if result else code_str

    @classmethod
    def parse_metar(
        cls,
        raw_metar: str,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Выполняет полный разбор строки METAR или SPECI в структурированный словарь.

        Args:
            raw_metar (str): Исходная строка телеграммы METAR / SPECI.
            reference_time (Optional[datetime]): Опорное время для корректного определения года и месяца.

        Returns:
            Dict[str, Any]: Структурированные параметры метеонаблюдения:
                - icao_code (str): Код аэродрома.
                - observation_time (datetime): Дата/время фиксации UTC.
                - report_type (str): 'METAR' или 'SPECI'.
                - flight_category (str): 'VFR', 'MVFR', 'IFR', 'LIFR'.
                - wind_direction (Optional[int]): Направление ветра в градусах.
                - wind_speed (Optional[float]): Скорость ветра в м/с.
                - wind_gust (Optional[float]): Порывы ветра в м/с.
                - wind_variable (bool): Переменное направление ветра.
                - visibility_meters (Optional[int]): Видимость в метрах.
                - cavok (bool): Флаг CAVOK.
                - cloud_base_meters (Optional[int]): Высота нижней границы облачности (НГО) в м.
                - cloud_coverage (str): Тип облачности (FEW, SCT, BKN, OVC, VV).
                - temperature (Optional[float]): Температура в °C.
                - dew_point (Optional[float]): Точка росы в °C.
                - pressure_hpa (Optional[float]): Давление QNH в гПа.
                - pressure_mmhg (Optional[float]): Давление QNH в мм рт. ст.
                - weather_phenomena (str): Описание явлений на русском.
                - raw_text (str): Исходная строка.
        """
        cleaned = " ".join(raw_metar.strip().split())
        tokens = cleaned.split()

        now_utc = reference_time or timezone.now()
        report_type = "METAR"
        if tokens and tokens[0].upper() in ("METAR", "SPECI"):
            report_type = tokens[0].upper()
            tokens = tokens[1:]

        icao_code = ""
        obs_time: Optional[datetime] = None

        # Ищем ICAO код (4 буквы)
        if tokens and re.match(r"^[A-Z]{4}$", tokens[0].upper()):
            icao_code = tokens[0].upper()
            tokens = tokens[1:]

        # Ищем дату/время DDHHMMZ
        if tokens and re.match(r"^\d{6}Z$", tokens[0].upper()):
            time_token = tokens[0].upper()
            day = int(time_token[0:2])
            hour = int(time_token[2:4])
            minute = int(time_token[4:6])
            
            # Формируем datetime с учетом возможного перехода месяца
            year = now_utc.year
            month = now_utc.month
            # Если день в телеграмме сильно больше текущего, значит это прошлый месяц
            if day > now_utc.day + 1 and now_utc.day <= 2:
                month = month - 1 if month > 1 else 12
                if month == 12:
                    year -= 1
            try:
                obs_time = datetime(year, month, day, hour, minute, tzinfo=dt_timezone.utc)
            except ValueError:
                obs_time = now_utc
            tokens = tokens[1:]
        else:
            obs_time = now_utc

        # Пропускаем маркеры модификаторов
        while tokens and tokens[0].upper() in ("AUTO", "COR", "NIL", "RTD"):
            tokens = tokens[1:]

        # Инициализация параметров
        wind_direction: Optional[int] = None
        wind_speed: Optional[float] = None
        wind_gust: Optional[float] = None
        wind_variable = False
        visibility_meters: Optional[int] = None
        cavok = False
        cloud_base_meters: Optional[int] = None
        cloud_coverage = ""
        cloud_layers_list: List[Dict[str, Any]] = []
        temperature: Optional[float] = None
        dew_point: Optional[float] = None
        pressure_hpa: Optional[float] = None
        pressure_mmhg: Optional[float] = None
        weather_phenomena_list: List[str] = []

        for token in tokens:
            t = token.upper().rstrip("=")

            # 1. Ветер: 24005MPS, 24012G18MPS, 18010KT, VRB02MPS, 00000MPS
            wind_match = re.match(r"^(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(MPS|KT|KMH)$", t)
            if wind_match and wind_speed is None:
                dir_part, spd_part, gust_part, unit = wind_match.groups()
                if dir_part == "VRB":
                    wind_variable = True
                    wind_direction = None
                else:
                    wind_direction = int(dir_part)

                raw_spd = float(spd_part)
                raw_gust = float(gust_part) if gust_part else None

                # Переводим в м/с
                if unit == "KT":
                    wind_speed = round(raw_spd * 0.514444, 1)
                    wind_gust = round(raw_gust * 0.514444, 1) if raw_gust else None
                elif unit == "KMH":
                    wind_speed = round(raw_spd / 3.6, 1)
                    wind_gust = round(raw_gust / 3.6, 1) if raw_gust else None
                else:
                    wind_speed = round(raw_spd, 1)
                    wind_gust = round(raw_gust, 1) if raw_gust else None
                continue

            # Вариация ветра (180V240) - пропускаем
            if re.match(r"^\d{3}V\d{3}$", t):
                continue

            # 2. CAVOK
            if t == "CAVOK":
                cavok = True
                visibility_meters = 10000
                cloud_coverage = "CAVOK"
                continue

            # 3. Видимость в метрах (9999, 5000, 0800, 1400SW)
            vis_match = re.match(r"^(\d{4})(?:[A-Z]{1,2})?$", t)
            if vis_match and visibility_meters is None and not cavok:
                val = int(vis_match.group(1))
                visibility_meters = 10000 if val >= 9999 else val
                continue

            # Видимость в милях США (10SM, 1/2SM, 2 1/2SM)
            if t.endswith("SM") and visibility_meters is None and not cavok:
                sm_str = t[:-2]
                try:
                    if "/" in sm_str:
                        num, den = sm_str.split("/")
                        sm_val = float(num) / float(den)
                    else:
                        sm_val = float(sm_str)
                    visibility_meters = int(sm_val * 1609.34)
                except (ValueError, ZeroDivisionError):
                    pass
                continue

            # 4. Облачность: FEW010, SCT020, BKN030CB, OVC008, VV002, NSC, NCD, CLR, SKC
            cloud_match = re.match(r"^(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?$", t)
            if cloud_match:
                cov, height_hundreds, cloud_type = cloud_match.groups()
                height_ft = int(height_hundreds) * 100
                height_m = int(height_ft * 0.3048)

                cloud_layers_list.append({
                    "coverage": cov,
                    "altitude_ft": height_ft,
                    "altitude_m": height_m,
                    "type": cloud_type or "",
                    "raw": t,
                })

                # Потолок (НГО) определяется низшим слоем BKN, OVC или VV
                if cov in ("BKN", "OVC", "VV"):
                    if cloud_base_meters is None or height_m < cloud_base_meters:
                        cloud_base_meters = height_m
                        cloud_coverage = cov
                elif cloud_base_meters is None and not cloud_coverage:
                    # Если потолка нет, фиксируем хотя бы FEW/SCT
                    cloud_coverage = cov
                continue

            if t in ("NSC", "NCD", "CLR", "SKC") and not cloud_coverage:
                cloud_coverage = t
                continue

            # 5. Температура и точка росы: 14/06, M02/M08, 00/M00, 15/M02
            temp_match = re.match(r"^(M?\d{2})/(M?\d{2})?$", t)
            if temp_match and temperature is None:
                t_str, dp_str = temp_match.groups()
                t_val = -float(t_str[1:]) if t_str.startswith("M") else float(t_str)
                temperature = t_val
                if dp_str:
                    dp_val = -float(dp_str[1:]) if dp_str.startswith("M") else float(dp_str)
                    dew_point = dp_val
                continue

            # 6. Давление QNH: Q1018, Q0998, A2992
            qnh_match = re.match(r"^Q(\d{4})$", t)
            if qnh_match and pressure_hpa is None:
                pressure_hpa = float(qnh_match.group(1))
                pressure_mmhg = round(pressure_hpa * 0.750062, 1)
                continue

            alt_match = re.match(r"^A(\d{4})$", t)
            if alt_match and pressure_hpa is None:
                inhg = float(alt_match.group(1)) / 100.0
                pressure_hpa = round(inhg * 33.8639, 1)
                pressure_mmhg = round(pressure_hpa * 0.750062, 1)
                continue

            # 7. Явления погоды (SN, +RA, FZFG, -SHSN, TSRA, BR, HZ, etc.)
            phenom_match = re.match(r"^(\+|-|VC)?(MI|PR|BC|DR|BL|SH|TS|FZ)?(DZ|RA|SN|SG|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)+$", t)
            if phenom_match:
                decoded_ph = cls.decode_weather_phenomena(t)
                if decoded_ph:
                    weather_phenomena_list.append(decoded_ph)

        # Вычисление летной категории (Flight Category): VFR / MVFR / IFR / LIFR
        # VFR: Ceiling > 3000 ft (914 m) and Vis > 5 miles (8000 m)
        # MVFR: Ceiling 1000-3000 ft (305-914 m) or Vis 3-5 miles (5000-8000 m)
        # IFR: Ceiling 500-1000 ft (152-305 m) or Vis 1-3 miles (1600-5000 m)
        # LIFR: Ceiling < 500 ft (152 m) or Vis < 1 mile (1600 m)
        flight_category = "VFR"

        vis = visibility_meters if visibility_meters is not None else (10000 if cavok else 10000)
        ceiling = cloud_base_meters  # None означает отсутствие потолка (ясно/неограниченно)

        if (ceiling is not None and ceiling < 150) or (vis < 1600):
            flight_category = "LIFR"
        elif (ceiling is not None and ceiling < 305) or (vis < 5000):
            flight_category = "IFR"
        elif (ceiling is not None and ceiling <= 914) or (vis <= 8000):
            flight_category = "MVFR"
        else:
            flight_category = "VFR"

        weather_phenomena_str = ", ".join(weather_phenomena_list)

        return {
            "icao_code": icao_code,
            "observation_time": obs_time,
            "report_type": report_type,
            "flight_category": flight_category,
            "wind_direction": wind_direction,
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "wind_variable": wind_variable,
            "visibility_meters": visibility_meters,
            "cavok": cavok,
            "cloud_base_meters": cloud_base_meters,
            "cloud_coverage": cloud_coverage,
            "cloud_layers": cloud_layers_list,
            "temperature": temperature,
            "dew_point": dew_point,
            "pressure_hpa": pressure_hpa,
            "pressure_mmhg": pressure_mmhg,
            "weather_phenomena": weather_phenomena_str,
            "raw_text": cleaned,
        }


class TafParser:
    """Парсер авиационных прогнозов погоды по аэродромам TAF."""

    @classmethod
    def parse_taf(
        cls,
        raw_taf: str,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Парсит телеграмму TAF с извлечением времени действия и групп изменений.

        Args:
            raw_taf (str): Исходный текст телеграммы TAF.
            reference_time (Optional[datetime]): Опорное время UTC.

        Returns:
            Dict[str, Any]: Структура с полями:
                - icao_code (str): Код аэродрома.
                - issued_at (datetime): Время выпуска.
                - valid_from (datetime): Начало действия.
                - valid_to (datetime): Окончание действия.
                - forecast_json (dict): Расшифрованные периоды.
                - raw_text (str): Исходный текст.
        """
        cleaned = " ".join(raw_taf.strip().split())
        tokens = cleaned.split()

        now_utc = reference_time or timezone.now()
        if tokens and tokens[0].upper() == "TAF":
            tokens = tokens[1:]

        # Пропускаем маркеры AMD, COR
        while tokens and tokens[0].upper() in ("AMD", "COR"):
            tokens = tokens[1:]

        icao_code = ""
        if tokens and re.match(r"^[A-Z]{4}$", tokens[0].upper()):
            icao_code = tokens[0].upper()
            tokens = tokens[1:]

        issued_at: Optional[datetime] = None
        if tokens and re.match(r"^\d{6}Z$", tokens[0].upper()):
            time_token = tokens[0].upper()
            day = int(time_token[0:2])
            hour = int(time_token[2:4])
            minute = int(time_token[4:6])
            try:
                issued_at = datetime(now_utc.year, now_utc.month, day, hour, minute, tzinfo=dt_timezone.utc)
            except ValueError:
                issued_at = now_utc
            tokens = tokens[1:]
        else:
            issued_at = now_utc

        # Интервал действия: DDHH/DDHH (например, 1812/1918)
        valid_from: Optional[datetime] = None
        valid_to: Optional[datetime] = None

        if tokens and re.match(r"^\d{4}/\d{4}$", tokens[0].upper()):
            period_token = tokens[0].upper()
            from_day = int(period_token[0:2])
            from_hour = int(period_token[2:4])
            to_day = int(period_token[5:7])
            to_hour = int(period_token[7:9])

            try:
                valid_from = datetime(now_utc.year, now_utc.month, from_day, from_hour, 0, tzinfo=dt_timezone.utc)
                # Коррекция перехода месяца для окончания прогноза
                to_year = now_utc.year
                to_month = now_utc.month
                if to_day < from_day:
                    to_month = to_month + 1 if to_month < 12 else 1
                    if to_month == 1:
                        to_year += 1
                valid_to = datetime(to_year, to_month, to_day, to_hour, 0, tzinfo=dt_timezone.utc)
            except ValueError:
                valid_from = issued_at
                valid_to = issued_at + timezone.timedelta(hours=24)
            tokens = tokens[1:]
        else:
            valid_from = issued_at
            valid_to = issued_at + timezone.timedelta(hours=24)

        # Выделяем группы изменений (TEMPO, BECMG, PROB30, PROB40, FM)
        periods: List[Dict[str, str]] = []
        current_type = "BASE"
        current_tokens: List[str] = []

        for tok in tokens:
            tok_upper = tok.upper().rstrip("=")
            if tok_upper in ("TEMPO", "BECMG") or tok_upper.startswith("PROB") or tok_upper.startswith("FM"):
                if current_tokens:
                    periods.append({
                        "type": current_type,
                        "text": " ".join(current_tokens),
                    })
                    current_tokens = []
                current_type = tok_upper
            else:
                current_tokens.append(tok)

        if current_tokens:
            periods.append({
                "type": current_type,
                "text": " ".join(current_tokens),
            })

        forecast_json = {
            "periods": periods,
            "total_periods": len(periods),
        }

        return {
            "icao_code": icao_code,
            "issued_at": issued_at,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "forecast_json": forecast_json,
            "raw_text": cleaned,
        }


class AviationWeatherService:
    """Сервис получения и сохранения авиационных метеоданных."""

    NOAA_METAR_URL = "https://aviationweather.gov/api/data/metar"
    NOAA_TAF_URL = "https://aviationweather.gov/api/data/taf"

    @classmethod
    def _fetch_noaa_subbatch(
        cls,
        chunk: List[str],
        base_url: str,
        headers: Dict[str, str],
        clean_codes_set: Set[str],
        result: Dict[str, str],
        data_type: str,
        timeout: int,
        warnings_list: Optional[List[str]] = None,
    ) -> None:
        """Вспомогательный метод загрузки пачки кодов из NOAA с рекурсивным делением при таймауте.

        Args:
            chunk (List[str]): Список ICAO кодов в текущей подпачке.
            base_url (str): Базовый URL эндпоинта NOAA.
            headers (Dict[str, str]): HTTP-заголовки запроса.
            clean_codes_set (Set[str]): Множество отслеживаемых кодов.
            result (Dict[str, str]): Словарь для накопления результатов.
            data_type (str): 'metar' или 'taf'.
            timeout (int): Таймаут сетевого соединения.
            warnings_list (Optional[List[str]]): Список для логирования предупреждений.
        """
        if not chunk:
            return

        query_params = urllib.parse.urlencode({
            "ids": ",".join(chunk),
            "format": "raw",
        })
        url = f"{base_url}?{query_params}"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode("utf-8", errors="ignore")
                lines = content.strip().splitlines()

                current_code = ""
                current_lines = []

                for line in lines:
                    line_clean = line.strip()
                    if not line_clean:
                        continue

                    tokens = [re.sub(r"[^A-Z0-9]", "", tok) for tok in line_clean.split()]
                    found_code = None
                    for tok in tokens:
                        if tok in clean_codes_set:
                            found_code = tok
                            break

                    if found_code:
                        if current_code and current_lines:
                            result[current_code] = " ".join(current_lines)
                            current_lines = []
                        current_code = found_code
                        current_lines.append(line_clean)
                    elif current_code:
                        current_lines.append(line_clean)

                if current_code and current_lines:
                    result[current_code] = " ".join(current_lines)

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if len(chunk) > 1:
                mid = len(chunk) // 2
                cls._fetch_noaa_subbatch(chunk[:mid], base_url, headers, clean_codes_set, result, data_type, min(timeout, 12), warnings_list)
                cls._fetch_noaa_subbatch(chunk[mid:], base_url, headers, clean_codes_set, result, data_type, min(timeout, 12), warnings_list)
            else:
                warn_msg = f"Таймаут/сбой NOAA [{data_type} для {chunk[0]}]: {exc}"
                logger.warning(warn_msg)
                if warnings_list is not None:
                    warnings_list.append(warn_msg)
        except Exception as exc:
            logger.exception("Критическая ошибка при запросе NOAA [%s для %s]: %s", data_type, ",".join(chunk), exc)

    @classmethod
    def fetch_noaa_raw(
        cls,
        icao_codes: List[str],
        data_type: str = "metar",
        timeout: int = 25,
        warnings_list: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Запрашивает сырые текстовые сводки METAR или TAF с открытого шлюза NOAA/AWC.

        Выполняет пакетный HTTP GET запрос с адаптивным разбиением (batch_size=10),
        что исключает ошибки HTTP 502 / URI Too Long, и группирует многострочные сводки TAF.
        При возникновении таймаута пачка делится пополам для изоляции сбойных станций.

        Args:
            icao_codes (List[str]): Список 4-буквенных ICAO кодов.
            data_type (str, optional): Тип данных: 'metar' или 'taf'. Defaults to 'metar'.
            timeout (int, optional): Таймаут сетевого запроса в секундах. Defaults to 25.
            warnings_list (Optional[List[str]], optional): Опциональный список предупреждений.

        Returns:
            Dict[str, str]: Словарь {icao_code: raw_string}.
        """
        if not icao_codes:
            return {}

        clean_codes = [
            normalize_icao_code(c)
            for c in icao_codes
            if c and len(normalize_icao_code(c)) == 4
        ]
        if not clean_codes:
            return {}

        clean_codes_set = set(clean_codes)
        base_url = cls.NOAA_METAR_URL if data_type == "metar" else cls.NOAA_TAF_URL
        headers = {
            "User-Agent": "BarkolAviationPortal/1.0 (Flight Operations Dept; info@barkol.ru)",
            "Accept": "text/plain",
        }

        result: Dict[str, str] = {}
        batch_size = 10

        for i in range(0, len(clean_codes), batch_size):
            chunk = clean_codes[i : i + batch_size]
            cls._fetch_noaa_subbatch(chunk, base_url, headers, clean_codes_set, result, data_type, timeout, warnings_list)

        return result

    @classmethod
    def diagnose_icao(cls, icao_input: str) -> Dict[str, Any]:
        """Выполняет полную диагностику доступности сводок METAR/TAF для заданного кода.

        Args:
            icao_input (str): Введенная строка ICAO (латиница или кириллица, например 'URWW' или 'УРВВ').

        Returns:
            Dict[str, Any]: Диагностический отчет с сырыми данными, расшифровкой и рекомендациями.
        """
        raw_input = (icao_input or "").strip()
        normalized = normalize_icao_code(raw_input)
        is_valid_format = bool(normalized and len(normalized) == 4 and normalized.isalnum())

        if not is_valid_format:
            return {
                "raw_input": raw_input,
                "normalized_icao": normalized,
                "is_valid_format": False,
                "has_metar": False,
                "has_taf": False,
                "metar_raw": None,
                "taf_raw": None,
                "parsed_metar": None,
                "diagnostic_status": "invalid_format",
                "message": f"Некорректный формат кода '{raw_input}'. Код ICAO должен состоять ровно из 4 букв (например, URWW, USRR, UNNT, USTR).",
            }

        metar_dict = cls.fetch_noaa_raw([normalized], data_type="metar", timeout=8)
        taf_dict = cls.fetch_noaa_raw([normalized], data_type="taf", timeout=8)

        metar_raw = metar_dict.get(normalized)
        taf_raw = taf_dict.get(normalized)

        parsed_metar = None
        if metar_raw:
            try:
                parsed_metar = MetarParser.parse_metar(metar_raw)
            except Exception as exc:
                logger.warning("Ошибка парсинга тестового METAR %s: %s", normalized, exc)

        if metar_raw and taf_raw:
            status = "ok"
            msg = f"Метеостанция {normalized} активна: получены актуальная сводка METAR и прогноз TAF."
        elif metar_raw:
            status = "partial"
            msg = f"Для {normalized} получена фактическая сводка METAR. Прогноз TAF в данный момент отсутствует."
        elif taf_raw:
            status = "partial"
            msg = f"Для {normalized} получен прогноз TAF. Фактическая сводка METAR в данный момент отсутствует."
        else:
            status = "no_data"
            msg = (
                f"Шлюз NOAA не вернул данных по коду {normalized}. "
                f"Возможные причины: метеостанция не публикует сводки в международный шлюз AFTN/NOAA, "
                f"либо объект является ведомственной вертолетной площадкой / посадочной полосой. "
                f"Рекомендация: укажите код ближайшего узлового аэродрома с действующей метеостанцией (например, для объектов ХМАО — USRR (Сургут), USNN (Нижневартовск), USTR (Тюмень))."
            )

        return {
            "raw_input": raw_input,
            "normalized_icao": normalized,
            "is_valid_format": True,
            "has_metar": bool(metar_raw),
            "has_taf": bool(taf_raw),
            "metar_raw": metar_raw,
            "taf_raw": taf_raw,
            "parsed_metar": parsed_metar,
            "diagnostic_status": status,
            "message": msg,
        }

    @classmethod
    def sync_mpd_weather(
        cls,
        mpd: PlaceProductionActivity,
        raw_metar: Optional[str] = None,
        raw_taf: Optional[str] = None,
    ) -> Tuple[Optional[AviationWeatherObservation], Optional[AviationWeatherForecast]]:
        """Синхронизирует и сохраняет фактическую погоду и прогноз для конкретного МПД.

        Args:
            mpd (PlaceProductionActivity): Объект МПД с заполненным icao_code или координатами.
            raw_metar (Optional[str]): Опциональная сырая строка METAR (если уже получена).
            raw_taf (Optional[str]): Опциональная сырая строка TAF (если уже получена).

        Returns:
            Tuple[Optional[AviationWeatherObservation], Optional[AviationWeatherForecast]]: Сохраненные объекты.
        """
        from .weather_providers.geo_service import GeoStationService

        icao = (mpd.icao_code or "").strip().upper()
        if (not icao or len(icao) != 4) and (mpd.latitude is not None and mpd.longitude is not None):
            nearest_info = GeoStationService.find_nearest_station(
                latitude=float(mpd.latitude),
                longitude=float(mpd.longitude),
                mpd_elevation_msl_m=float(mpd.elevation_msl_m) if mpd.elevation_msl_m is not None else None,
            )
            if nearest_info and nearest_info.get("station") and nearest_info["station"].icao_code:
                icao = nearest_info["station"].icao_code.upper()

        if not icao or len(icao) != 4:
            return None, None

        # Если данные не переданы напрямую — запрашиваем из NOAA
        if raw_metar is None:
            metar_dict = cls.fetch_noaa_raw([icao], data_type="metar")
            raw_metar = metar_dict.get(icao)

        if raw_taf is None:
            taf_dict = cls.fetch_noaa_raw([icao], data_type="taf")
            raw_taf = taf_dict.get(icao)

        obs_obj: Optional[AviationWeatherObservation] = None
        forecast_obj: Optional[AviationWeatherForecast] = None

        if raw_metar:
            try:
                parsed_metar = MetarParser.parse_metar(raw_metar)
                parsed_metar["icao_code"] = icao
                parsed_metar["mpd"] = mpd

                with transaction.atomic():
                    obs_obj, _ = AviationWeatherObservation.objects.update_or_create(
                        icao_code=icao,
                        observation_time=parsed_metar["observation_time"],
                        defaults=parsed_metar,
                    )
            except Exception as exc:
                logger.error("Ошибка сохранения METAR для МПД %s (%s): %s", mpd.name, icao, exc)

        if raw_taf:
            try:
                parsed_taf = TafParser.parse_taf(raw_taf)
                parsed_taf["icao_code"] = icao
                parsed_taf["mpd"] = mpd

                with transaction.atomic():
                    forecast_obj, _ = AviationWeatherForecast.objects.update_or_create(
                        icao_code=icao,
                        issued_at=parsed_taf["issued_at"],
                        defaults=parsed_taf,
                    )
            except Exception as exc:
                logger.error("Ошибка сохранения TAF для МПД %s (%s): %s", mpd.name, icao, exc)

        # Обновляем аудит МПД
        if obs_obj or forecast_obj:
            mpd.weather_last_sync_at = timezone.now()
            mpd.weather_sync_status = "OK (METAR)"
            mpd.save(update_fields=["weather_last_sync_at", "weather_sync_status"])

        return obs_obj, forecast_obj

    @classmethod
    def sync_mpd_weather_with_progress(
        cls,
        mpd: PlaceProductionActivity,
        mode: str = "all",
        force_model: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str, str], None]] = None,
    ) -> Dict[str, Any]:
        """Синхронизирует метеоданные МПД с генерацией пошагового структурированного лога.

        Выполняет валидацию параметров МПД, геопривязку к опорной метеостанции ИКАО,
        опрос авиационных сводок METAR/TAF через шлюз NOAA AWC и расчет сеточной гидродинамической
        модели ECMWF IFS / GFS через Open-Meteo API с фиксацией каждого события.

        Args:
            mpd (PlaceProductionActivity): Объект места производственной деятельности.
            mode (str, optional): Режим синхронизации ('metar', 'coordinate', 'all'). Defaults to 'all'.
            force_model (Optional[str], optional): Принудительное указание численной модели атмосферы. Defaults to None.
            progress_callback (Optional[Callable[[int, str, str], None]], optional):
                Функция обратного вызова (percent: int, message: str, level: str) для передачи прогресса в Celery/UI.

        Returns:
            Dict[str, Any]: Словарь с итоговым результатом:
                - 'success' (bool): Общий статус завершения.
                - 'has_warnings' (bool): Присутствуют ли предупреждения.
                - 'has_errors' (bool): Присутствуют ли ошибки.
                - 'logs' (List[Dict[str, Any]]): Хронологический список логов событий.
                - 'stats' (Dict[str, Any]): Сводные количественные показатели.
                - 'error' (Optional[str]): Текст критической ошибки при сбое.
        """
        from .weather_providers.geo_service import GeoStationService
        from .weather_providers.weather_manager import WeatherManagerService

        logs: List[Dict[str, Any]] = []

        def emit(msg: str, level: str = "info", pct: int = 0) -> None:
            ts = timezone.now().strftime("%H:%M:%S")
            entry = {"time": ts, "level": level, "message": msg}
            logs.append(entry)
            if progress_callback:
                try:
                    progress_callback(pct, msg, level)
                except Exception as cb_err:
                    logger.debug("Ошибка вызова progress_callback: %s", cb_err)

        emit(f"Старт синхронизации метеоданных для МПД «{mpd.name}» (Режим: {mode.upper()})...", "start", 5)

        has_coords = mpd.latitude is not None and mpd.longitude is not None
        lat_val = float(mpd.latitude) if mpd.latitude is not None else None
        lon_val = float(mpd.longitude) if mpd.longitude is not None else None
        elev_val = float(mpd.elevation_msl_m) if mpd.elevation_msl_m is not None else None

        if has_coords:
            emit(
                f"Географические координаты МПД: {lat_val:.6f}° с.ш., {lon_val:.6f}° в.д., высота {elev_val or 0:.0f} м MSL",
                "info",
                10,
            )
        else:
            emit(
                "Географические координаты МПД не заполнены в карточке объекта",
                "warn" if mode == "metar" else "error",
                10,
            )

        nearest_info = None
        nearest_station = None
        if has_coords:
            nearest_info = GeoStationService.find_nearest_station(
                latitude=lat_val,
                longitude=lon_val,
                mpd_elevation_msl_m=elev_val,
            )
            if nearest_info and nearest_info.get("station"):
                nearest_station = nearest_info["station"]
                dist_km = nearest_info["distance_km"]
                st_name = nearest_station.name_ru or nearest_station.name_en or ""
                repr_txt = "Репрезентативна (≤15 км)" if nearest_info.get("is_representative") else f"Удаленная станция ({dist_km:.1f} км)"
                elev_delta_str = f", перепад высот: {nearest_info['elevation_delta_m']:+.0f} м" if nearest_info.get("elevation_delta_m") is not None else ""
                emit(
                    f"Определена опорная метеостанция ИКАО: {nearest_station.icao_code} ({st_name}), расстояние {dist_km:.1f} км{elev_delta_str}. Статус: {repr_txt}.",
                    "step",
                    20,
                )
            else:
                emit("Опорная метеостанция ИКАО поблизости (до 150 км) не обнаружена", "warn", 20)

        obs_obj: Optional[AviationWeatherObservation] = None
        forecast_obj: Optional[AviationWeatherForecast] = None
        target_icao = (mpd.icao_code or "").strip().upper()

        if not target_icao and nearest_station:
            target_icao = nearest_station.icao_code.upper()
            emit(f"Для запроса метеосводок используется ICAO код опорного аэродрома: {target_icao}", "info", 25)

        if mode in ("metar", "all"):
            if target_icao and len(target_icao) == 4:
                emit(f"Запрос авиационных сводок METAR / TAF для станции {target_icao} через шлюз NOAA AWC...", "queue", 30)

                # Запрос METAR
                metar_dict = cls.fetch_noaa_raw([target_icao], data_type="metar", timeout=15)
                raw_metar = metar_dict.get(target_icao)
                if raw_metar:
                    emit(f"Получена сырая сводка METAR ({target_icao}): {raw_metar}", "step", 40)
                    try:
                        parsed_metar = MetarParser.parse_metar(raw_metar)
                        parsed_metar["icao_code"] = target_icao
                        parsed_metar["mpd"] = mpd
                        with transaction.atomic():
                            obs_obj, _ = AviationWeatherObservation.objects.update_or_create(
                                icao_code=target_icao,
                                observation_time=parsed_metar["observation_time"],
                                defaults=parsed_metar,
                            )
                        cat = obs_obj.flight_category or "N/A"
                        w_spd = f"{obs_obj.wind_speed:.0f} м/с" if obs_obj.wind_speed is not None else "штиль"
                        vis = f"{obs_obj.visibility_meters} м" if obs_obj.visibility_meters is not None else "н/д"
                        qnh = f"{obs_obj.pressure_mmhg:.1f} мм рт.ст." if obs_obj.pressure_mmhg is not None else "н/д"
                        emit(
                            f"METAR успешно сохранен в БД. Категория полетов: {cat}, Ветер: {w_spd}, Видимость: {vis}, Давление QNH: {qnh}.",
                            "success",
                            45,
                        )
                    except Exception as err:
                        emit(f"Ошибка парсинга или сохранения сводки METAR: {err}", "error", 45)
                else:
                    emit(
                        f"Станция {target_icao} в настоящее время не передает регулярные сводки METAR в международную сеть NOAA (HTTP 204 No Content). Фактическая сводка недоступна.",
                        "warn",
                        45,
                    )

                # Запрос TAF
                taf_dict = cls.fetch_noaa_raw([target_icao], data_type="taf", timeout=15)
                raw_taf = taf_dict.get(target_icao)
                if raw_taf:
                    emit(f"Получен официальный прогноз погоды TAF ({target_icao})", "step", 50)
                    try:
                        parsed_taf = TafParser.parse_taf(raw_taf)
                        parsed_taf["icao_code"] = target_icao
                        parsed_taf["mpd"] = mpd
                        with transaction.atomic():
                            forecast_obj, _ = AviationWeatherForecast.objects.update_or_create(
                                icao_code=target_icao,
                                issued_at=parsed_taf["issued_at"],
                                defaults=parsed_taf,
                            )
                        v_from = forecast_obj.valid_from.strftime("%d.%m %H:%M") if forecast_obj.valid_from else ""
                        v_to = forecast_obj.valid_to.strftime("%d.%m %H:%M") if forecast_obj.valid_to else ""
                        emit(f"Прогноз TAF успешно сохранен (период действия: {v_from} — {v_to} UTC)", "success", 55)
                    except Exception as err:
                        emit(f"Ошибка парсинга или сохранения прогноза TAF: {err}", "warn", 55)
                else:
                    emit(f"Официальный прогноз TAF для станции {target_icao} не найден или отсутствует на сервере", "info", 55)
            else:
                emit("Код ICAO не задан и опорная станция не определена. Опрос METAR/TAF пропущен.", "warn", 55)

        coord_saved = 0
        model_name = force_model or getattr(settings, "OPEN_METEO_DEFAULT_MODEL", "ecmwf_ifs")

        if mode in ("coordinate", "all"):
            if not has_coords:
                emit("Сеточный гидродинамический расчет пропущен: отсутствуют географические координаты точки МПД", "warn", 85)
            else:
                emit(f"Запрос сеточной модели атмосферы {model_name.upper()} через Open-Meteo API (почасовой расчет на 2 суток)...", "queue", 65)

                def om_cb(msg: str, lvl: str) -> None:
                    emit(msg, lvl, 75)

                try:
                    coord_saved = WeatherManagerService.sync_coordinate_forecasts_for_mpds(
                        [mpd],
                        force_model=force_model,
                        logger_callback=om_cb,
                    )
                    if coord_saved > 0:
                        emit(f"Численный расчет погоды завершен: успешно сохранено {coord_saved} почасовых точек прогноза.", "success", 90)
                    else:
                        emit("От Open-Meteo не поступили почасовые данные или точка не была обработана.", "warn", 90)
                except Exception as err:
                    emit(f"Ошибка при синхронизации сеточного прогноза: {err}", "error", 90)

        # Финализация аудита МПД
        now_ts = timezone.now()
        mpd.weather_last_sync_at = now_ts
        if obs_obj and coord_saved > 0:
            mpd.weather_sync_status = f"OK (METAR + {model_name.upper()})"
        elif obs_obj:
            mpd.weather_sync_status = "OK (METAR)"
        elif coord_saved > 0:
            mpd.weather_sync_status = f"OK ({model_name.upper()})"
        else:
            mpd.weather_sync_status = "Данные не поступили"
        if mpd.pk:
            mpd.save(update_fields=["weather_last_sync_at", "weather_sync_status"])

        has_errors = any(entry["level"] == "error" for entry in logs)
        has_warnings = any(entry["level"] == "warn" for entry in logs)

        if not has_errors and (obs_obj or coord_saved > 0):
            emit(f"Синхронизация метеоданных для «{mpd.name}» успешно выполнена!", "success", 100)
            overall_success = True
        elif obs_obj or coord_saved > 0:
            emit(f"Синхронизация для «{mpd.name}» выполнена с предупреждениями (данные получены частично).", "warn", 100)
            overall_success = True
        else:
            emit(f"Синхронизация для «{mpd.name}» завершена без получения метеоданных.", "error", 100)
            overall_success = False

        return {
            "success": overall_success,
            "has_warnings": has_warnings,
            "has_errors": has_errors,
            "logs": logs,
            "stats": {
                "mpd_id": mpd.id,
                "mpd_name": mpd.name,
                "icao_code": target_icao,
                "has_metar": bool(obs_obj),
                "has_taf": bool(forecast_obj),
                "coordinate_points_saved": coord_saved,
                "model": model_name,
                "flight_category": obs_obj.flight_category if obs_obj else None,
                "sync_status": mpd.weather_sync_status,
                "sync_time": now_ts.strftime("%d.%m.%Y %H:%M:%S"),
            },
            "error": "Не удалось получить актуальные метеоданные" if not overall_success else None,
        }

    @classmethod
    def sync_all_active_mpds(cls) -> Dict[str, Any]:
        """Выполняет комплексную синхронизацию метеорологии: METAR/TAF опорных станций и координатные расчеты.

        1. Наполняет/актуализирует справочник опорных метеостанций AviationWeatherStation.
        2. Опрашивает шлюз NOAA по станциям и всем активным МПД (в планировании или с включенным мониторингом).
        3. Пакетно запрашивает сеточную модель Open-Meteo (ECMWF/GFS) для всех координатных МПД.
        4. Обновляет аудит времени синхронизации и статус на объектах PlaceProductionActivity.
        5. Формирует детальный диагностический отчет для мониторинга Celery-задач.

        Returns:
            Dict[str, Any]: Структурированный результат синхронизации:
                - 'total_mpds': Всего активных МПД.
                - 'metar_saved': Сохранено фактических наблюдений METAR.
                - 'taf_saved': Сохранено официальных прогнозов TAF.
                - 'coord_forecasts_saved': Сохранено почасовых модельных прогнозов.
                - 'mpds_updated': Количество обновленных МПД.
                - 'summary': Словарь сводных метрик (длительность, дата, количество).
                - 'mpd_results': Список детальных статусов по каждому МПД с расшифровкой погоды.
                - 'noaa_stations_summary': Статистика запроса к открытому шлюзу NOAA.
                - 'warnings': Список зафиксированных предупреждений и изолированных сбоев.
        """
        from .fixtures_stations import seed_aviation_weather_stations
        from .weather_providers import WeatherManagerService
        from .weather_providers.geo_service import GeoStationService

        start_time = time.time()
        warnings_list: List[str] = []

        # Проверяем и инициализируем базовые опорные метеостанции РФ
        if not AviationWeatherStation.objects.exists():
            seed_aviation_weather_stations()

        # 1. Сбор ICAO кодов со всех активных станций
        active_stations = AviationWeatherStation.objects.filter(is_active=True)
        station_by_icao = {st.icao_code.upper(): st for st in active_stations if st.icao_code}

        # Выбираем все МПД, участвующие в планировании или с активным мониторингом
        active_mpds = PlaceProductionActivity.objects.filter(
            Q(in_planning=True) | Q(weather_monitoring_enabled=True)
        ).distinct()

        mpd_by_icao: Dict[str, PlaceProductionActivity] = {}
        coordinate_mpds: List[PlaceProductionActivity] = []
        extra_station_icaos: Set[str] = set()

        for mpd in active_mpds:
            code = normalize_icao_code(mpd.icao_code)
            if len(code) == 4:
                mpd_by_icao[code] = mpd
            if mpd.latitude is not None and mpd.longitude is not None:
                coordinate_mpds.append(mpd)
                # Если собственного ICAO кода нет, но есть координаты — находим ближайшую метеостанцию
                if not code:
                    nearest_info = GeoStationService.find_nearest_station(
                        latitude=float(mpd.latitude),
                        longitude=float(mpd.longitude),
                        mpd_elevation_msl_m=float(mpd.elevation_msl_m) if mpd.elevation_msl_m is not None else None,
                    )
                    if nearest_info and nearest_info.get("station") and nearest_info["station"].icao_code:
                        extra_station_icaos.add(nearest_info["station"].icao_code.upper())

        all_target_icaos = list(set(list(station_by_icao.keys()) + list(mpd_by_icao.keys()) + list(extra_station_icaos)))

        metar_data = cls.fetch_noaa_raw(all_target_icaos, data_type="metar", timeout=25, warnings_list=warnings_list)
        taf_data = cls.fetch_noaa_raw(all_target_icaos, data_type="taf", timeout=25, warnings_list=warnings_list)

        metar_count = 0
        taf_count = 0

        # Сохранение METAR/TAF по станциям и МПД
        for code in all_target_icaos:
            raw_metar = metar_data.get(code)
            raw_taf = taf_data.get(code)
            station_obj = station_by_icao.get(code)
            mpd_obj = mpd_by_icao.get(code)

            if raw_metar:
                try:
                    parsed_metar = MetarParser.parse_metar(raw_metar)
                    parsed_metar["icao_code"] = code
                    parsed_metar["station"] = station_obj
                    if mpd_obj:
                        parsed_metar["mpd"] = mpd_obj

                    with transaction.atomic():
                        AviationWeatherObservation.objects.update_or_create(
                            icao_code=code,
                            observation_time=parsed_metar["observation_time"],
                            defaults=parsed_metar,
                        )
                        metar_count += 1
                except Exception as exc:
                    logger.error("Ошибка сохранения METAR для %s: %s", code, exc)
                    warnings_list.append(f"Ошибка сохранения METAR {code}: {exc}")

            if raw_taf:
                try:
                    parsed_taf = TafParser.parse_taf(raw_taf)
                    parsed_taf["icao_code"] = code
                    parsed_taf["station"] = station_obj
                    if mpd_obj:
                        parsed_taf["mpd"] = mpd_obj

                    with transaction.atomic():
                        AviationWeatherForecast.objects.update_or_create(
                            icao_code=code,
                            issued_at=parsed_taf["issued_at"],
                            defaults=parsed_taf,
                        )
                        taf_count += 1
                except Exception as exc:
                    logger.error("Ошибка сохранения TAF для %s: %s", code, exc)
                    warnings_list.append(f"Ошибка сохранения TAF {code}: {exc}")

        # 2. Пакетная синхронизация координатных прогнозов
        coord_saved = 0
        if coordinate_mpds:
            try:
                coord_saved = WeatherManagerService.sync_coordinate_forecasts_for_mpds(coordinate_mpds)
            except Exception as exc:
                logger.error("Ошибка фонового расчета координатной погоды: %s", exc)
                warnings_list.append(f"Сбой координатной гидродинамической модели ECMWF: {exc}")

        # 3. Обновление статусов и времени последней синхронизации на всех МПД
        mpds_updated = 0
        now_dt = timezone.now()
        mpd_results: List[Dict[str, Any]] = []

        for mpd in active_mpds:
            norm_code = normalize_icao_code(mpd.icao_code)
            has_icao_data = bool(norm_code and (metar_data.get(norm_code) or taf_data.get(norm_code)))
            has_coord_data = bool(mpd.latitude is not None and mpd.longitude is not None)

            status_parts = []
            if has_icao_data:
                status_parts.append("METAR")
            if has_coord_data:
                status_parts.append("ECMWF")

            sync_status_str = f"OK ({'+'.join(status_parts)})" if status_parts else "NO_DATA"
            mpd.weather_last_sync_at = now_dt
            mpd.weather_sync_status = sync_status_str
            mpd.save(update_fields=["weather_last_sync_at", "weather_sync_status"])
            mpds_updated += 1

            # Формирование детальной сводки по МПД
            latest_obs = None
            ref_icao = norm_code
            if norm_code:
                latest_obs = AviationWeatherObservation.objects.filter(icao_code=norm_code).order_by("-observation_time").first()
            if not latest_obs and mpd.latitude is not None and mpd.longitude is not None:
                nearest = GeoStationService.find_nearest_station(
                    float(mpd.latitude),
                    float(mpd.longitude),
                    float(mpd.elevation_msl_m) if mpd.elevation_msl_m is not None else None,
                )
                if nearest and nearest.get("station") and nearest["station"].icao_code:
                    ref_icao = f"{nearest['station'].icao_code} (опорный {nearest['distance_km']:.0f} км)"
                    latest_obs = AviationWeatherObservation.objects.filter(icao_code=nearest["station"].icao_code).order_by("-observation_time").first()

            weather_summary = "Данные не поступили"
            obs_time_str = None
            flight_category = "N/A"
            raw_text = ""
            if latest_obs:
                flight_category = latest_obs.flight_category or "VFR"
                obs_time_str = latest_obs.observation_time.strftime("%d.%m.%Y %H:%M UTC") if latest_obs.observation_time else None
                raw_text = latest_obs.raw_text or ""
                summary_parts = []
                if latest_obs.temperature is not None:
                    summary_parts.append(f"{latest_obs.temperature:+.0f}°C")
                if latest_obs.wind_speed is not None:
                    w_dir = f"{latest_obs.wind_direction:03d}°" if latest_obs.wind_direction is not None else "VRB"
                    wind_str = f"Ветер {w_dir} {latest_obs.wind_speed:.0f} м/с"
                    if latest_obs.wind_gust:
                        wind_str += f" (пор. {latest_obs.wind_gust:.0f} м/с)"
                    summary_parts.append(wind_str)
                if latest_obs.visibility_meters is not None:
                    summary_parts.append(f"Вид. {latest_obs.visibility_meters}м" if latest_obs.visibility_meters < 10000 else "Вид. >10км")
                if latest_obs.cloud_base_meters is not None:
                    summary_parts.append(f"ВНГО {latest_obs.cloud_base_meters}м")
                if latest_obs.pressure_mmhg is not None:
                    summary_parts.append(f"QNH {latest_obs.pressure_mmhg:.1f} мм")
                if summary_parts:
                    weather_summary = ", ".join(summary_parts)

            has_taf = False
            if norm_code:
                has_taf = AviationWeatherForecast.objects.filter(icao_code=norm_code).exists()

            mpd_results.append({
                "mpd_id": mpd.pk,
                "name": mpd.name,
                "icao_code": ref_icao or norm_code or "—",
                "sync_status": sync_status_str,
                "flight_category": flight_category,
                "observation_time": obs_time_str,
                "weather_summary": weather_summary,
                "has_taf": has_taf,
                "latest_raw_metar": raw_text,
            })

        duration_sec = round(time.time() - start_time, 2)
        summary_payload = {
            "total_active_mpds": len(active_mpds),
            "stations_monitored": len(station_by_icao),
            "metar_saved": metar_count,
            "taf_saved": taf_count,
            "coord_forecasts_saved": coord_saved,
            "mpds_updated": mpds_updated,
            "duration_sec": duration_sec,
            "executed_at": now_dt.strftime("%d.%m.%Y %H:%M:%S UTC"),
        }

        logger.info(
            "Завершена комплексная синхронизация погоды за %s сек: METAR %s, TAF %s, Coordinate Points %s, МПД %s",
            duration_sec, metar_count, taf_count, coord_saved, mpds_updated
        )

        return {
            "total_mpds": len(active_mpds),
            "metar_saved": metar_count,
            "taf_saved": taf_count,
            "coord_forecasts_saved": coord_saved,
            "mpds_updated": mpds_updated,
            "summary": summary_payload,
            "mpd_results": mpd_results,
            "noaa_stations_summary": {
                "total_requested": len(all_target_icaos),
                "metar_received": len(metar_data),
                "taf_received": len(taf_data),
            },
            "warnings": warnings_list,
        }

    @classmethod
    def get_mpd_current_weather(cls, mpd: PlaceProductionActivity) -> Dict[str, Any]:
        """Возвращает актуальный статус погоды и действующий прогноз для МПД.

        Args:
            mpd (PlaceProductionActivity): Объект места деятельности.

        Returns:
            Dict[str, Any]: Словарь с текущим метеонаблюдением (METAR) и прогнозом (TAF).
        """
        icao = (mpd.icao_code or "").strip().upper()
        latest_obs = None
        latest_forecast = None

        if icao:
            latest_obs = AviationWeatherObservation.objects.filter(icao_code=icao).order_by("-observation_time").first()
            latest_forecast = AviationWeatherForecast.objects.filter(icao_code=icao).order_by("-issued_at").first()

        latest_coord = None
        if not latest_obs and mpd.latitude is not None and mpd.longitude is not None:
            latest_coord = CoordinateWeatherForecast.objects.filter(mpd=mpd).order_by("-forecast_for").first()

        return {
            "mpd": mpd,
            "has_weather": bool(latest_obs or latest_forecast or latest_coord),
            "latest_observation": latest_obs,
            "latest_forecast": latest_forecast,
            "latest_coordinate_forecast": latest_coord,
        }

    @classmethod
    def get_mpd_weather_timeline(
        cls,
        mpd: PlaceProductionActivity,
        target_date: date,
    ) -> Dict[str, Any]:
        """Возвращает почасовую хронологию погоды за выбранную дату через WeatherManagerService.

        Args:
            mpd (PlaceProductionActivity): Объект места деятельности.
            target_date (date): Дата запроса.

        Returns:
            Dict[str, Any]: Стандартизированный DTO-пакет метеоданных для шаблонов и API.
        """
        from .weather_providers import WeatherManagerService
        bundle = WeatherManagerService.get_mpd_weather_bundle(mpd, target_date)
        bundle["forecast"] = bundle.get("forecast_taf")
        return bundle
