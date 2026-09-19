"""Сервис-фасад управления авиационной и координатной метеорологией."""

from datetime import date, datetime, timezone as dt_timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from hrdepartment_app.models import PlaceProductionActivity
from flight_planning.models import (
    AviationWeatherForecast,
    AviationWeatherObservation,
    AviationWeatherStation,
    CoordinateWeatherForecast,
)
from .geo_service import GeoStationService
from .open_meteo_provider import OpenMeteoProvider

logger = logging.getLogger(__name__)


class WeatherManagerService:
    """Единый фасад получения, синхронизации и представления метеоданных для МПД."""

    @classmethod
    def sync_coordinate_forecasts_for_mpds(
        cls,
        mpds: List[PlaceProductionActivity],
        force_model: Optional[str] = None,
    ) -> int:
        """Синхронизирует сеточные почасовые прогнозы для переданного списка МПД.

        Выполняет пакетный запрос к Open-Meteo, определяет ближайшую опорную станцию
        для каждого МПД и сохраняет почасовые расчеты в модель CoordinateWeatherForecast.

        Args:
            mpds (List[PlaceProductionActivity]): Список объектов МПД с координатами.
            force_model (Optional[str]): Принудительное указание модели (ecmwf_ifs, gfs_seamless).

        Returns:
            int: Количество сохраненных / обновленных почасовых записей прогноза.
        """
        valid_points: List[Dict[str, Any]] = []
        mpd_by_id: Dict[int, PlaceProductionActivity] = {}

        for mpd in mpds:
            if mpd.latitude is not None and mpd.longitude is not None:
                valid_points.append({
                    "mpd_id": mpd.pk,
                    "latitude": float(mpd.latitude),
                    "longitude": float(mpd.longitude),
                    "elevation": float(mpd.elevation_msl_m) if mpd.elevation_msl_m is not None else None,
                })
                mpd_by_id[mpd.pk] = mpd

        if not valid_points:
            return 0

        # Пакетная выгрузка из Open-Meteo
        batch_results = OpenMeteoProvider.fetch_coordinate_forecasts_batch(
            valid_points,
            model_name=force_model,
        )

        total_saved = 0

        for result_item in batch_results:
            point_info = result_item["point"]
            mpd_id = point_info["mpd_id"]
            mpd = mpd_by_id.get(mpd_id)
            if not mpd:
                continue

            model_name = result_item["model_name"]
            elev_msl = result_item.get("elevation_msl_m") or mpd.elevation_msl_m
            hourly_records = result_item.get("hourly_records") or []

            # Поиск опорной метеостанции
            nearest_info = GeoStationService.find_nearest_station(
                latitude=float(mpd.latitude),
                longitude=float(mpd.longitude),
                mpd_elevation_msl_m=elev_msl,
            )
            nearest_station = nearest_info["station"] if nearest_info else None

            # Транзакционное сохранение почасовых точек
            with transaction.atomic():
                for rec in hourly_records:
                    rec_payload = dict(rec)
                    forecast_for = rec_payload.pop("forecast_for")
                    rec_payload["latitude"] = float(mpd.latitude)
                    rec_payload["longitude"] = float(mpd.longitude)
                    rec_payload["elevation_msl_m"] = elev_msl
                    rec_payload["provider"] = "open-meteo"
                    rec_payload["model"] = model_name
                    rec_payload["nearest_station"] = nearest_station

                    CoordinateWeatherForecast.objects.update_or_create(
                        mpd=mpd,
                        forecast_for=forecast_for,
                        model=model_name,
                        defaults=rec_payload,
                    )
                    total_saved += 1

        logger.info(
            "Синхронизированы координатные прогнозы: обработано %s МПД, сохранено %s записей",
            len(valid_points), total_saved
        )
        return total_saved

    @classmethod
    def get_mpd_weather_bundle(
        cls,
        mpd: PlaceProductionActivity,
        target_date: date,
    ) -> Dict[str, Any]:
        """Возвращает комплексный стандартизированный DTO-пакет погоды для МПД на целевую дату.

        Автоматически определяет оптимальный источник (настоящий METAR/TAF или координатная модель),
        подтягивает опорную метеостанцию и строит данные для графиков Chart.js.

        Args:
            mpd (PlaceProductionActivity): Объект места деятельности.
            target_date (date): Дата запроса.

        Returns:
            Dict[str, Any]: Унифицированная структура метеоданных:
                - 'source_type': 'METAR' или 'COORDINATE_MODEL'.
                - 'is_observation': bool (True для METAR, False для сеточной модели).
                - 'latest_current': Актуальное наблюдение или текущий срез прогноза.
                - 'nearest_station_info': Данные опорного аэродрома (дистанция, перепад высот, METAR).
                - 'hourly_timeline': Список хронологических записей за сутки.
                - 'stats': Суточная статистика (min/max temp, max wind/gust, pressure).
                - 'chart_data': Сериализованные массивы для Chart.js.
                - 'forecast_taf': Официальный прогноз TAF (если доступен).
        """
        start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=dt_timezone.utc)
        end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=dt_timezone.utc)

        pref = mpd.weather_source_preference or "AUTO"
        icao = (mpd.icao_code or "").strip().upper()

        use_metar = False
        metar_observations: List[AviationWeatherObservation] = []

        if pref in ("AUTO", "METAR_ONLY") and icao and len(icao) == 4:
            metar_observations = list(
                AviationWeatherObservation.objects.filter(
                    icao_code=icao,
                    observation_time__range=(start_dt, end_dt),
                ).order_by("-observation_time")
            )
            if metar_observations or pref == "METAR_ONLY":
                use_metar = True

        # Сценарий 1: Используем фактические наблюдения METAR
        if use_metar:
            latest_obs = metar_observations[0] if metar_observations else (
                AviationWeatherObservation.objects.filter(icao_code=icao).order_by("-observation_time").first()
            )
            taf = AviationWeatherForecast.objects.filter(
                icao_code=icao,
                valid_from__lte=end_dt,
                valid_to__gte=start_dt,
            ).order_by("-issued_at").first()

            temps = [o.temperature for o in metar_observations if o.temperature is not None]
            winds = [o.wind_speed for o in metar_observations if o.wind_speed is not None]
            gusts = [o.wind_gust for o in metar_observations if o.wind_gust is not None]
            pressures = [o.pressure_mmhg for o in metar_observations if o.pressure_mmhg is not None]

            stats = {
                "total_reports": len(metar_observations),
                "min_temp": min(temps) if temps else None,
                "max_temp": max(temps) if temps else None,
                "max_wind": max(winds) if winds else None,
                "max_gust": max(gusts) if gusts else None,
                "min_pressure_mmhg": min(pressures) if pressures else None,
                "max_pressure_mmhg": max(pressures) if pressures else None,
            }

            chronological = list(reversed(metar_observations))
            chart_data = {
                "labels": [o.observation_time.strftime("%H:%M") for o in chronological],
                "temperatures": [round(o.temperature, 1) if o.temperature is not None else None for o in chronological],
                "dew_points": [round(o.dew_point, 1) if o.dew_point is not None else None for o in chronological],
                "wind_speeds": [round(o.wind_speed, 1) if o.wind_speed is not None else None for o in chronological],
                "wind_gusts": [round(o.wind_gust, 1) if o.wind_gust is not None else None for o in chronological],
                "pressures": [round(o.pressure_mmhg, 1) if o.pressure_mmhg is not None else None for o in chronological],
                "cloud_bases": [o.cloud_base_meters for o in chronological],
                "categories": [o.flight_category for o in chronological],
            }

            return {
                "mpd": mpd,
                "target_date": target_date,
                "source_type": "METAR",
                "is_observation": True,
                "badge_label": f"METAR ({icao})",
                "badge_class": "success",
                "latest_current": latest_obs,
                "nearest_station_info": None,
                "hourly_timeline": metar_observations,
                "stats": stats,
                "chart_data": chart_data,
                "forecast_taf": taf,
            }

        # Сценарий 2: Используем сеточный координатный прогноз (ECMWF / GFS)
        coord_forecasts = list(
            CoordinateWeatherForecast.objects.filter(
                mpd=mpd,
                forecast_for__range=(start_dt, end_dt),
            ).order_by("forecast_for")
        )

        latest_coord = None
        now_utc = timezone.now()
        if coord_forecasts:
            # Ищем наиболее близкий к текущему времени прогноз
            closest = min(coord_forecasts, key=lambda f: abs((f.forecast_for - now_utc).total_seconds()))
            latest_coord = closest

        # Поиск опорного аэродрома и его свежего METAR
        nearest_info = None
        if mpd.latitude is not None and mpd.longitude is not None:
            station_match = GeoStationService.find_nearest_station(
                latitude=float(mpd.latitude),
                longitude=float(mpd.longitude),
                mpd_elevation_msl_m=mpd.elevation_msl_m,
            )
            if station_match:
                st = station_match["station"]
                latest_st_metar = AviationWeatherObservation.objects.filter(icao_code=st.icao_code).order_by("-observation_time").first()
                freshness_min = None
                if latest_st_metar and latest_st_metar.observation_time:
                    freshness_min = int((now_utc - latest_st_metar.observation_time).total_seconds() / 60)

                nearest_info = {
                    "station": st,
                    "distance_km": station_match["distance_km"],
                    "elevation_delta_m": station_match["elevation_delta_m"],
                    "latest_metar": latest_st_metar,
                    "freshness_minutes": freshness_min,
                }

        temps = [f.temperature for f in coord_forecasts if f.temperature is not None]
        winds = [f.wind_speed for f in coord_forecasts if f.wind_speed is not None]
        gusts = [f.wind_gust for f in coord_forecasts if f.wind_gust is not None]
        pressures = [f.surface_pressure_mmhg for f in coord_forecasts if f.surface_pressure_mmhg is not None]

        stats = {
            "total_reports": len(coord_forecasts),
            "min_temp": min(temps) if temps else None,
            "max_temp": max(temps) if temps else None,
            "max_wind": max(winds) if winds else None,
            "max_gust": max(gusts) if gusts else None,
            "min_pressure_mmhg": min(pressures) if pressures else None,
            "max_pressure_mmhg": max(pressures) if pressures else None,
        }

        chart_data = {
            "labels": [f.forecast_for.strftime("%H:%M") for f in coord_forecasts],
            "temperatures": [round(f.temperature, 1) if f.temperature is not None else None for f in coord_forecasts],
            "dew_points": [round(f.dew_point, 1) if f.dew_point is not None else None for f in coord_forecasts],
            "wind_speeds": [round(f.wind_speed, 1) if f.wind_speed is not None else None for f in coord_forecasts],
            "wind_gusts": [round(f.wind_gust, 1) if f.wind_gust is not None else None for f in coord_forecasts],
            "pressures": [round(f.surface_pressure_mmhg, 1) if f.surface_pressure_mmhg is not None else None for f in coord_forecasts],
            "cloud_bases": [f.cloud_base_agl_m for f in coord_forecasts],
            "freezing_levels": [f.freezing_level_msl_m for f in coord_forecasts],
            "categories": [f.model_flight_category for f in coord_forecasts],
        }

        model_label = latest_coord.model if latest_coord else "ECMWF"

        return {
            "mpd": mpd,
            "target_date": target_date,
            "source_type": "COORDINATE_MODEL",
            "is_observation": False,
            "badge_label": f"Модель ({model_label.upper()})",
            "badge_class": "info",
            "latest_current": latest_coord,
            "nearest_station_info": nearest_info,
            "hourly_timeline": coord_forecasts,
            "stats": stats,
            "chart_data": chart_data,
            "forecast_taf": None,
        }

    build_mpd_weather_bundle = get_mpd_weather_bundle

