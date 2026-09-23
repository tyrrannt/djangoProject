"""Провайдер интеграции с Open-Meteo API для координатного прогнозирования погоды."""

from datetime import datetime, timezone as dt_timezone
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone

from .base import BaseWeatherProvider

logger = logging.getLogger(__name__)


class OpenMeteoProvider(BaseWeatherProvider):
    """Провайдер получения сеточных численных прогнозов погоды (ECMWF, GFS, ICON).

    Поддерживает пакетные запросы нескольких координат (батчинг), отказоустойчивые
    повторные попытки (retry), fallback на альтернативные численные модели атмосферы
    и сохранение исходных физических параметров в единицах СИ / ИКАО.
    """

    DEFAULT_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    DEFAULT_MODEL: str = "ecmwf_ifs"
    FALLBACK_MODELS: List[str] = ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Возвращает настройки конфигурации провайдера из Django settings.

        Returns:
            Dict[str, Any]: Словарь с URL, API-ключом, моделью по умолчанию и таймаутами.
        """
        base_url = getattr(settings, "OPEN_METEO_BASE_URL", cls.DEFAULT_BASE_URL)
        api_key = getattr(settings, "OPEN_METEO_API_KEY", None)
        default_model = getattr(settings, "OPEN_METEO_DEFAULT_MODEL", cls.DEFAULT_MODEL)
        timeout = getattr(settings, "OPEN_METEO_TIMEOUT", 25)
        retries = getattr(settings, "OPEN_METEO_RETRIES", 2)

        return {
            "base_url": base_url,
            "api_key": api_key,
            "default_model": default_model,
            "timeout": timeout,
            "retries": retries,
        }

    @classmethod
    def _open_url(cls, req: urllib.request.Request, timeout: int) -> str:
        """Выполняет прямое HTTP-соединение к Open-Meteo API без прокси (метео-трафик идет напрямую).

        ProxyHandler({}) гарантирует, что системные HTTP_PROXY / HTTPS_PROXY или прокси Telegram
        не перехватывают авиационный метео-трафик.
        """
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @classmethod
    def fetch_coordinate_forecasts_batch(
        cls,
        points: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        forecast_days: int = 2,
        logger_callback: Optional[Callable[[str, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Выполняет пакетный HTTP-запрос почасового прогноза для списка географических точек.

        Args:
            points (List[Dict[str, Any]]): Список точек, каждая должна содержать:
                - 'latitude': float
                - 'longitude': float
                - 'elevation': Optional[float] (MSL, м)
                - 'mpd_id': int (или объект mpd)
            model_name (Optional[str]): Имя модели (ecmwf_ifs, gfs_seamless, icon_seamless).
            forecast_days (int): Горизонт прогноза в сутках (по умолчанию 2 дня = 48 часов).
            logger_callback (Optional[Callable[[str, str], None]]): Callback для детального логирования шагов и ошибок.

        Returns:
            List[Dict[str, Any]]: Список результатов прогноза для каждой точки с массивом почасовых записей.
        """
        if not points:
            if logger_callback:
                logger_callback("Список координатных точек для запроса пуст", "warn")
            return []

        if len(points) > 5:
            all_results: List[Dict[str, Any]] = []
            chunk_size = 5
            for i in range(0, len(points), chunk_size):
                chunk_points = points[i : i + chunk_size]
                chunk_res = cls.fetch_coordinate_forecasts_batch(
                    chunk_points,
                    model_name=model_name,
                    forecast_days=forecast_days,
                    logger_callback=logger_callback,
                )
                all_results.extend(chunk_res)
            return all_results

        config = cls.get_config()
        selected_model = model_name or config["default_model"]
        base_url = config["base_url"]
        timeout = config["timeout"]
        api_key = config["api_key"]

        lats = [f"{p['latitude']:.4f}" for p in points]
        lons = [f"{p['longitude']:.4f}" for p in points]
        elevs = [f"{p.get('elevation', 0.0):.1f}" if p.get("elevation") is not None else "nan" for p in points]

        if logger_callback:
            logger_callback(
                f"Запрос метеомодели {selected_model.upper()} для {len(points)} точек: "
                f"координаты ({', '.join(lats)}; {', '.join(lons)})...",
                "queue",
            )

        query_dict: Dict[str, Any] = {
            "latitude": ",".join(lats),
            "longitude": ",".join(lons),
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "forecast_days": forecast_days,
            "hourly": (
                "temperature_2m,relative_humidity_2m,dew_point_2m,"
                "surface_pressure,pressure_msl,wind_speed_10m,wind_direction_10m,"
                "wind_gusts_10m,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
                "cloud_base,freezing_level_height,weather_code,precipitation,precipitation_probability,visibility"
            ),
        }

        if any(e != "nan" for e in elevs):
            query_dict["elevation"] = ",".join(elevs)

        if selected_model and selected_model != "best_match":
            query_dict["models"] = selected_model

        if api_key:
            query_dict["apikey"] = api_key

        url = f"{base_url}?{urllib.parse.urlencode(query_dict)}"
        headers = {
            "User-Agent": "BarkolAviationPortal/1.0 (Flight Planning Weather Module)",
            "Accept": "application/json",
        }

        req = urllib.request.Request(url, headers=headers)
        response_data: Union[Dict[str, Any], List[Dict[str, Any]]] = {}

        try:
            content = cls._open_url(req, timeout=timeout)
            response_data = json.loads(content)
        except urllib.error.HTTPError as exc:
            error_details = f"HTTP {exc.code} {exc.reason}"
            try:
                raw_body = exc.read().decode("utf-8", errors="ignore")
                if raw_body:
                    try:
                        err_json = json.loads(raw_body)
                        error_details += f" — {err_json.get('reason', raw_body[:150])}"
                    except Exception:
                        error_details += f" — {raw_body[:150]}"
            except Exception:
                pass

            if exc.code == 429:
                limit_msg = f"Превышен лимит запросов Open-Meteo API ({error_details}). Бесплатный лимит: 10 000 запросов/сутки."
                logger.error(limit_msg)
                if logger_callback:
                    logger_callback(limit_msg, "error")
                return []

            logger.warning(
                "Ошибка HTTP Open-Meteo [%s] для %s точек: %s. Пробуем fallback...",
                selected_model, len(points), error_details
            )
            if logger_callback:
                logger_callback(f"Ошибка ответа Open-Meteo ({selected_model.upper()}): {error_details}", "warn")

            next_model = None
            if selected_model not in ("gfs_seamless", "best_match"):
                next_model = "gfs_seamless"
            elif selected_model == "gfs_seamless":
                next_model = "best_match"

            if next_model:
                if logger_callback:
                    logger_callback(f"Автоматический запуск резервной модели прогнозирования {next_model.upper()}...", "step")
                return cls.fetch_coordinate_forecasts_batch(
                    points,
                    model_name=next_model,
                    forecast_days=forecast_days,
                    logger_callback=logger_callback,
                )
            return []
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Ошибка сети/таймаута Open-Meteo [%s] для %s точек: %s. Пробуем fallback...",
                selected_model, len(points), exc
            )

            next_model = None
            if selected_model not in ("gfs_seamless", "best_match"):
                next_model = "gfs_seamless"
            elif selected_model == "gfs_seamless":
                next_model = "best_match"

            if next_model:
                if logger_callback:
                    logger_callback(f"Сетевой сбой при обращении к {selected_model.upper()} ({exc}). Запуск резервной модели {next_model.upper()}...", "warn")
                return cls.fetch_coordinate_forecasts_batch(
                    points,
                    model_name=next_model,
                    forecast_days=forecast_days,
                    logger_callback=logger_callback,
                )

            timeout_msg = (
                f"Сетевой сбой при обращении к Open-Meteo: {exc}. "
                f"Сервер не ответил в течение {timeout} сек. "
                "Это задержка или блокировка сетевого соединения (таймаут), а не лимит запросов: при превышении лимита сервис возвращает HTTP 429."
            )
            if logger_callback:
                logger_callback(timeout_msg, "error")
            return []
        except Exception as exc:
            logger.exception("Критическая ошибка при запросе Open-Meteo: %s", exc)
            if logger_callback:
                logger_callback(f"Непредвиденная ошибка при запросе Open-Meteo: {exc}", "error")
            return []

        # Если точка была одна, API возвращает словарь; если несколько — список словарей
        if isinstance(response_data, dict):
            raw_results = [response_data]
        elif isinstance(response_data, list):
            raw_results = response_data
        else:
            raw_results = []

        parsed_batch: List[Dict[str, Any]] = []

        for idx, raw_item in enumerate(raw_results):
            if idx >= len(points):
                break
            point_info = points[idx]
            parsed_hours = cls._parse_hourly_payload(raw_item, selected_model)
            parsed_batch.append({
                "point": point_info,
                "model_name": selected_model,
                "elevation_msl_m": raw_item.get("elevation"),
                "hourly_records": parsed_hours,
            })

        return parsed_batch

    @classmethod
    def parse_single_point_hourly(
        cls,
        hourly: Dict[str, Any],
        model_name: str = "ecmwf_ifs",
    ) -> List[Dict[str, Any]]:
        """Парсит словарь 'hourly' Open-Meteo в список словарей параметров.

        Args:
            hourly (Dict[str, Any]): Словарь с почасовыми массивами параметров Open-Meteo.
            model_name (str): Наименование примененной модели (по умолчанию 'ecmwf_ifs').

        Returns:
            List[Dict[str, Any]]: Список почасовых словарей параметров.
        """
        return cls._parse_hourly_payload({"hourly": hourly}, model_name=model_name)

    @classmethod
    def parse_hourly_payload(
        cls,
        payload: Dict[str, Any],
        model_name: str = "ecmwf_ifs",
    ) -> List[Dict[str, Any]]:
        """Публичный метод парсинга ответа Open-Meteo по одной точке."""
        return cls._parse_hourly_payload(payload, model_name=model_name)

    @classmethod
    def _parse_hourly_payload(
        cls,
        payload: Dict[str, Any],
        model_name: str,
    ) -> List[Dict[str, Any]]:
        """Парсит почасовые массивы Open-Meteo в нормализованный список словарей параметров.

        Args:
            payload (Dict[str, Any]): Необработанный JSON-ответ по одной точке.
            model_name (str): Наименование примененной модели.

        Returns:
            List[Dict[str, Any]]: Список почасовых словарей со всеми метеорологическими полями.
        """
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            return []

        temps = hourly.get("temperature_2m") or []
        humidities = hourly.get("relative_humidity_2m") or []
        dew_points = hourly.get("dew_point_2m") or []
        surf_pressures = hourly.get("surface_pressure") or []
        msl_pressures = hourly.get("pressure_msl") or []
        wind_speeds = hourly.get("wind_speed_10m") or []
        wind_dirs = hourly.get("wind_direction_10m") or []
        wind_gusts = hourly.get("wind_gusts_10m") or []
        cloud_totals = hourly.get("cloud_cover") or []
        cloud_lows = hourly.get("cloud_cover_low") or []
        cloud_mids = hourly.get("cloud_cover_mid") or []
        cloud_highs = hourly.get("cloud_cover_high") or []
        cloud_bases = hourly.get("cloud_base") or []
        freezing_levels = hourly.get("freezing_level_height") or []
        weather_codes = hourly.get("weather_code") or []
        precips = hourly.get("precipitation") or []
        precip_probs = hourly.get("precipitation_probability") or []
        visibilities = hourly.get("visibility") or []

        now_utc = timezone.now()
        # Оценка времени инициализации модели (run_at): округляем текущее время вниз до кратного 6 часам (00, 06, 12, 18 UTC)
        run_hour = (now_utc.hour // 6) * 6
        model_run_at = datetime(now_utc.year, now_utc.month, now_utc.day, run_hour, 0, 0, tzinfo=dt_timezone.utc)

        records: List[Dict[str, Any]] = []

        for i, time_str in enumerate(times):
            try:
                # Open-Meteo возвращает ISO 8601 строку "YYYY-MM-DDTHH:MM"
                if "T" in time_str:
                    dt_part = datetime.fromisoformat(time_str)
                    if dt_part.tzinfo is None:
                        forecast_for = dt_part.replace(tzinfo=dt_timezone.utc)
                    else:
                        forecast_for = dt_part
                else:
                    forecast_for = now_utc
            except ValueError:
                continue

            t_val = temps[i] if i < len(temps) else None
            dp_val = dew_points[i] if i < len(dew_points) else None
            hum_val = humidities[i] if i < len(humidities) else None

            sp_hpa = surf_pressures[i] if i < len(surf_pressures) else None
            sp_mmhg = round(sp_hpa * 0.750062, 1) if sp_hpa is not None else None

            pmsl_hpa = msl_pressures[i] if i < len(msl_pressures) else None
            pmsl_mmhg = round(pmsl_hpa * 0.750062, 1) if pmsl_hpa is not None else None

            ws = wind_speeds[i] if i < len(wind_speeds) else None
            wd = int(wind_dirs[i]) if (i < len(wind_dirs) and wind_dirs[i] is not None) else None
            wg = wind_gusts[i] if i < len(wind_gusts) else None

            c_tot = int(cloud_totals[i]) if (i < len(cloud_totals) and cloud_totals[i] is not None) else None
            c_low = int(cloud_lows[i]) if (i < len(cloud_lows) and cloud_lows[i] is not None) else None
            c_mid = int(cloud_mids[i]) if (i < len(cloud_mids) and cloud_mids[i] is not None) else None
            c_high = int(cloud_highs[i]) if (i < len(cloud_highs) and cloud_highs[i] is not None) else None

            c_base = float(cloud_bases[i]) if (i < len(cloud_bases) and cloud_bases[i] is not None) else None
            fz_lvl = float(freezing_levels[i]) if (i < len(freezing_levels) and freezing_levels[i] is not None) else None
            w_code = int(weather_codes[i]) if (i < len(weather_codes) and weather_codes[i] is not None) else None
            precip = float(precips[i]) if (i < len(precips) and precips[i] is not None) else 0.0
            precip_prob = float(precip_probs[i]) if (i < len(precip_probs) and precip_probs[i] is not None) else None
            vis_m = float(visibilities[i]) if (i < len(visibilities) and visibilities[i] is not None) else None

            # Расчетная модельная оценка условий (VFR / MVFR / IFR / LIFR)
            flight_category = "VFR"
            ceiling = c_base
            vis = vis_m if vis_m is not None else 10000.0

            if (ceiling is not None and ceiling < 150.0) or (vis < 1600.0):
                flight_category = "LIFR"
            elif (ceiling is not None and ceiling < 305.0) or (vis < 5000.0):
                flight_category = "IFR"
            elif (ceiling is not None and ceiling <= 914.0) or (vis <= 8000.0):
                flight_category = "MVFR"
            else:
                flight_category = "VFR"

            records.append({
                "model_run_at": model_run_at,
                "forecast_for": forecast_for,
                "temperature": round(t_val, 1) if t_val is not None else None,
                "dew_point": round(dp_val, 1) if dp_val is not None else None,
                "relative_humidity": round(hum_val, 1) if hum_val is not None else None,
                "surface_pressure_hpa": round(sp_hpa, 1) if sp_hpa is not None else None,
                "surface_pressure_mmhg": sp_mmhg,
                "pressure_msl_hpa": round(pmsl_hpa, 1) if pmsl_hpa is not None else None,
                "pressure_mmhg": pmsl_mmhg,
                "wind_speed": round(ws, 1) if ws is not None else None,
                "wind_direction": wd,
                "wind_gust": round(wg, 1) if wg is not None else None,
                "cloud_cover_total": c_tot,
                "cloud_cover_low": c_low,
                "cloud_cover_mid": c_mid,
                "cloud_cover_high": c_high,
                "cloud_base_agl_m": c_base,
                "freezing_level_msl_m": fz_lvl,
                "weather_code": w_code,
                "precipitation_mm": round(precip, 2),
                "precipitation_probability": precip_prob,
                "visibility_m": vis_m,
                "model_flight_category": flight_category,
            })

        return records

    def fetch_current(self, latitude: float, longitude: float, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Получает ближайший почасовой срез прогноза для заданной координаты.

        Args:
            latitude (float): Широта точки.
            longitude (float): Долгота точки.
            **kwargs (Any): Дополнительные параметры (elevation, model_name).

        Returns:
            Optional[Dict[str, Any]]: Словарь параметров текущего часа или None.
        """
        pts = [{"latitude": latitude, "longitude": longitude, "elevation": kwargs.get("elevation")}]
        batch = self.fetch_coordinate_forecasts_batch(pts, model_name=kwargs.get("model_name"), forecast_days=1)
        if batch and batch[0].get("hourly_records"):
            return batch[0]["hourly_records"][0]
        return None

    def fetch_forecast(self, latitude: float, longitude: float, forecast_days: int = 2, **kwargs: Any) -> List[Dict[str, Any]]:
        """Получает полный массив почасового прогноза для заданной координаты.

        Args:
            latitude (float): Широта точки.
            longitude (float): Долгота точки.
            forecast_days (int): Горизонт прогноза в днях.
            **kwargs (Any): Дополнительные параметры (elevation, model_name).

        Returns:
            List[Dict[str, Any]]: Список почасовых записей прогноза.
        """
        pts = [{"latitude": latitude, "longitude": longitude, "elevation": kwargs.get("elevation")}]
        batch = self.fetch_coordinate_forecasts_batch(pts, model_name=kwargs.get("model_name"), forecast_days=forecast_days)
        if batch and batch[0].get("hourly_records"):
            return batch[0]["hourly_records"]
        return []
