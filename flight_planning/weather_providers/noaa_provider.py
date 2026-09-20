"""Провайдер интеграции со шлюзом NOAA Aviation Weather Center для сводок METAR и TAF."""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from .base import BaseWeatherProvider

logger = logging.getLogger(__name__)


def normalize_icao_code(raw_code: Optional[str]) -> str:
    """Нормализует код ICAO: удаляет пробелы, спецсимволы, переводит в верхний регистр.

    Также выполняет транслитерацию кириллических авиационных кодов РФ в латиницу.

    Args:
        raw_code (Optional[str]): Исходный ввод кода ICAO.

    Returns:
        str: 4-буквенный нормализованный латинский код ICAO или пустая строка.
    """
    if not raw_code:
        return ""

    s = str(raw_code).strip().upper()

    translit_map = {
        "У": "U", "С": "S", "Р": "R", "Н": "N", "Т": "T",
        "Л": "L", "И": "I", "Е": "E", "М": "M", "К": "K",
        "Х": "H", "В": "W", "О": "O", "П": "P", "Д": "D",
        "А": "A", "Б": "B", "Г": "G", "З": "Z", "Ж": "J",
        "Ф": "F", "Ц": "C", "Ч": "CH", "Ш": "SH", "Щ": "SCH",
        "Ы": "Y", "Э": "E", "Ю": "YU", "Я": "YA",
    }
    for ru_char, lat_char in translit_map.items():
        s = s.replace(ru_char, lat_char)

    clean = re.sub(r"[^A-Z0-9]", "", s)
    return clean[:4] if len(clean) >= 4 else clean


class NoaaWeatherProvider(BaseWeatherProvider):
    """Провайдер получения официальных сводок METAR и прогнозов TAF с открытого шлюза NOAA AWC."""

    NOAA_METAR_URL: str = "https://aviationweather.gov/api/data/metar"
    NOAA_TAF_URL: str = "https://aviationweather.gov/api/data/taf"

    normalize_icao_code = staticmethod(normalize_icao_code)

    @classmethod
    def fetch_raw(
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

        clean_codes_map = {}
        for c in icao_codes:
            norm = normalize_icao_code(c)
            if norm and len(norm) == 4:
                clean_codes_map[norm] = norm

        clean_codes = list(clean_codes_map.keys())
        if not clean_codes:
            return {}

        clean_codes_set = set(clean_codes)
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
            logger.warning("Сетевая ошибка при запросе %s из NOAA для %s: %s", data_type.upper(), clean_codes, exc)
        except Exception as exc:
            logger.exception("Непредвиденная ошибка при запросе %s из NOAA: %s", data_type.upper(), exc)

        return result

    def fetch_current(self, icao_code: str, **kwargs: Any) -> Optional[str]:
        """Получает текущую сводку METAR для одного кода ICAO.

        Args:
            icao_code (str): 4-буквенный международный код ICAO.
            **kwargs (Any): Дополнительные параметры (timeout).

        Returns:
            Optional[str]: Сырой текст METAR или None.
        """
        res = self.fetch_raw([icao_code], data_type="metar", timeout=kwargs.get("timeout", 10))
        norm = normalize_icao_code(icao_code)
        return res.get(norm)

    def fetch_forecast(self, icao_code: str, **kwargs: Any) -> Optional[str]:
        """Получает официальный прогноз TAF для одного кода ICAO.

        Args:
            icao_code (str): 4-буквенный международный код ICAO.
            **kwargs (Any): Дополнительные параметры (timeout).

        Returns:
            Optional[str]: Сырой текст TAF или None.
        """
        res = self.fetch_raw([icao_code], data_type="taf", timeout=kwargs.get("timeout", 10))
        norm = normalize_icao_code(icao_code)
        return res.get(norm)
