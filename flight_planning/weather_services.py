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
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction
from django.utils import timezone

from hrdepartment_app.models import PlaceProductionActivity
from .models import AviationWeatherForecast, AviationWeatherObservation

logger = logging.getLogger(__name__)

# Словари перевода метеоявлений ICAO на русский язык
WEATHER_INTENSITY = {
    "-": "Слабый",
    "+": "Сильный",
    "VC": "В окрестностях",
}

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
            cloud_match = re.match(r"^(FEW|SCT|BKN|OVC|VV)(\d{3})(?:CB|TCU)?$", t)
            if cloud_match:
                cov, height_hundreds = cloud_match.groups()
                height_ft = int(height_hundreds) * 100
                height_m = int(height_ft * 0.3048)

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
    def fetch_noaa_raw(
        cls,
        icao_codes: List[str],
        data_type: str = "metar",
        timeout: int = 10,
    ) -> Dict[str, str]:
        """Запрашивает сырые сводки METAR или TAF с открытого шлюза NOAA Aviation Weather Center.

        Args:
            icao_codes (List[str]): Список 4-буквенных ICAO кодов.
            data_type (str): 'metar' или 'taf'.
            timeout (int): Таймаут сетевого запроса в секундах.

        Returns:
            Dict[str, str]: Отображение {ICAO: raw_text}.
        """
        if not icao_codes:
            return {}

        clean_codes = [c.strip().upper() for c in icao_codes if len(c.strip()) == 4]
        if not clean_codes:
            return {}

        base_url = cls.NOAA_METAR_URL if data_type == "metar" else cls.NOAA_TAF_URL
        query_params = urllib.parse.urlencode({
            "ids": ",".join(clean_codes),
            "format": "raw",
        })
        url = f"{base_url}?{query_params}"

        headers = {
            "User-Agent": "BarkolAviationPortal/1.0 (Flight Operations Dept; info@barkol.ru)",
            "Accept": "text/plain",
        }

        req = urllib.request.Request(url, headers=headers)
        result: Dict[str, str] = {}

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

                    # Проверяем начало новой сводки
                    match = re.search(r"\b([A-Z]{4})\b", line_clean)
                    found_code = None
                    if match:
                        code_candidate = match.group(1)
                        if code_candidate in clean_codes:
                            found_code = code_candidate

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
            logger.warning(
                "Не удалось загрузить данные погоды NOAA [%s для %s]: %s",
                data_type, ",".join(clean_codes), exc
            )
        except Exception as exc:
            logger.exception(
                "Критическая ошибка при запросе NOAA [%s]: %s",
                data_type, exc
            )

        return result

    @classmethod
    def sync_mpd_weather(
        cls,
        mpd: PlaceProductionActivity,
        raw_metar: Optional[str] = None,
        raw_taf: Optional[str] = None,
    ) -> Tuple[Optional[AviationWeatherObservation], Optional[AviationWeatherForecast]]:
        """Синхронизирует и сохраняет фактическую погоду и прогноз для конкретного МПД.

        Args:
            mpd (PlaceProductionActivity): Объект МПД с заполненным icao_code.
            raw_metar (Optional[str]): Опциональная сырая строка METAR (если уже получена).
            raw_taf (Optional[str]): Опциональная сырая строка TAF (если уже получена).

        Returns:
            Tuple[Optional[AviationWeatherObservation], Optional[AviationWeatherForecast]]: Сохраненные объекты.
        """
        icao = (mpd.icao_code or "").strip().upper()
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

        return obs_obj, forecast_obj

    @classmethod
    def sync_all_active_mpds(cls) -> Dict[str, int]:
        """Выполняет массовую синхронизацию фактической погоды и прогнозов по всем активным МПД.

        Returns:
            Dict[str, int]: Статистика синхронизации:
                - 'total_mpds': Всего активных МПД с ICAO кодом.
                - 'metar_saved': Сохранено наблюдений METAR.
                - 'taf_saved': Сохранено прогнозов TAF.
        """
        active_mpds = PlaceProductionActivity.objects.filter(
            in_planning=True,
            weather_monitoring_enabled=True,
        ).exclude(icao_code="").exclude(icao_code__isnull=True)

        mpd_by_icao: Dict[str, PlaceProductionActivity] = {}
        for mpd in active_mpds:
            code = mpd.icao_code.strip().upper()
            if len(code) == 4:
                mpd_by_icao[code] = mpd

        if not mpd_by_icao:
            return {"total_mpds": 0, "metar_saved": 0, "taf_saved": 0}

        all_codes = list(mpd_by_icao.keys())
        metar_data = cls.fetch_noaa_raw(all_codes, data_type="metar")
        taf_data = cls.fetch_noaa_raw(all_codes, data_type="taf")

        metar_count = 0
        taf_count = 0

        for code, mpd in mpd_by_icao.items():
            raw_metar = metar_data.get(code)
            raw_taf = taf_data.get(code)
            obs, fc = cls.sync_mpd_weather(mpd, raw_metar=raw_metar, raw_taf=raw_taf)
            if obs:
                metar_count += 1
            if fc:
                taf_count += 1

        logger.info(
            "Завершена синхронизация погоды: обработано МПД %s, METAR %s, TAF %s",
            len(mpd_by_icao), metar_count, taf_count
        )

        return {
            "total_mpds": len(mpd_by_icao),
            "metar_saved": metar_count,
            "taf_saved": taf_count,
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
        if not icao:
            return {
                "mpd": mpd,
                "has_weather": False,
                "latest_observation": None,
                "latest_forecast": None,
            }

        latest_obs = AviationWeatherObservation.objects.filter(icao_code=icao).order_by("-observation_time").first()
        latest_forecast = AviationWeatherForecast.objects.filter(icao_code=icao).order_by("-issued_at").first()

        return {
            "mpd": mpd,
            "has_weather": bool(latest_obs or latest_forecast),
            "latest_observation": latest_obs,
            "latest_forecast": latest_forecast,
        }

    @classmethod
    def get_mpd_weather_timeline(
        cls,
        mpd: PlaceProductionActivity,
        target_date: date,
    ) -> Dict[str, Any]:
        """Возвращает почасовую хронологию погоды за выбранную дату и суточную статистику.

        Args:
            mpd (PlaceProductionActivity): Объект места деятельности.
            target_date (date): Дата запроса.

        Returns:
            Dict[str, Any]: Словарь с почасовым списком наблюдений, статистикой и действующими прогнозами.
        """
        icao = (mpd.icao_code or "").strip().upper()
        if not icao:
            return {
                "mpd": mpd,
                "target_date": target_date,
                "observations": [],
                "forecast": None,
                "stats": {},
            }

        start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=dt_timezone.utc)
        end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=dt_timezone.utc)

        observations = list(
            AviationWeatherObservation.objects.filter(
                icao_code=icao,
                observation_time__range=(start_dt, end_dt),
            ).order_by("-observation_time")
        )

        # Вычисляем суточную статистику
        temps = [o.temperature for o in observations if o.temperature is not None]
        winds = [o.wind_speed for o in observations if o.wind_speed is not None]
        gusts = [o.wind_gust for o in observations if o.wind_gust is not None]
        pressures = [o.pressure_mmhg for o in observations if o.pressure_mmhg is not None]

        stats = {
            "total_reports": len(observations),
            "min_temp": min(temps) if temps else None,
            "max_temp": max(temps) if temps else None,
            "max_wind": max(winds) if winds else None,
            "max_gust": max(gusts) if gusts else None,
            "min_pressure_mmhg": min(pressures) if pressures else None,
            "max_pressure_mmhg": max(pressures) if pressures else None,
        }

        # Данные для построения почасового графика (в хронологическом порядке)
        chronological_obs = list(reversed(observations))
        chart_labels = [o.observation_time.strftime("%H:%M") for o in chronological_obs]
        chart_temps = [round(o.temperature, 1) if o.temperature is not None else None for o in chronological_obs]
        chart_winds = [round(o.wind_speed, 1) if o.wind_speed is not None else None for o in chronological_obs]
        chart_gusts = [round(o.wind_gust, 1) if o.wind_gust is not None else None for o in chronological_obs]
        chart_pressures = [round(o.pressure_mmhg, 1) if o.pressure_mmhg is not None else None for o in chronological_obs]
        chart_categories = [o.flight_category for o in chronological_obs]

        chart_data = {
            "labels": chart_labels,
            "temperatures": chart_temps,
            "wind_speeds": chart_winds,
            "wind_gusts": chart_gusts,
            "pressures": chart_pressures,
            "categories": chart_categories,
        }

        # Ищем прогноз, действовавший на эту дату
        forecast = AviationWeatherForecast.objects.filter(
            icao_code=icao,
            valid_from__lte=end_dt,
            valid_to__gte=start_dt,
        ).order_by("-issued_at").first()

        return {
            "mpd": mpd,
            "target_date": target_date,
            "observations": observations,
            "forecast": forecast,
            "stats": stats,
            "chart_data": chart_data,
        }
