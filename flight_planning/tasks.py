"""Асинхронные фоновые задачи Celery для модуля планирования полетов и авиационной метеорологии."""

import logging
from typing import Any, Dict, Optional

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist

from hrdepartment_app.models import PlaceProductionActivity
from .weather_services import AviationWeatherService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    name="flight_planning.tasks.sync_all_aviation_weather_task",
)
def sync_all_aviation_weather_task(self) -> Dict[str, Any]:
    """Периодическая фоновая задача массового сбора и архивирования метеосводок METAR и TAF.

    Опрашивает открытый шлюз NOAA по всем активным МПД и опорным метеостанциям РФ,
    декодирует параметры погоды (ветер, видимость, НГО, давление, QNH, категорию VFR/IFR),
    рассчитывает почасовые гидродинамические сеточные прогнозы ECMWF и сохраняет в БД.

    Args:
        self: Экземпляр связанной задачи Celery (bind=True).

    Returns:
        Dict[str, Any]: Детальный диагностический отчет с параметрами по каждому МПД для мониторинга.

    Raises:
        self.retry: При возникновении временных сетевых ошибок и таймаутов.
    """
    task_id = self.request.id
    logger.info("Старт задачи sync_all_aviation_weather_task [task_id=%s, attempt=%s]", task_id, self.request.retries + 1)

    try:
        raw_result = AviationWeatherService.sync_all_active_mpds()
        summary = raw_result.get("summary", {})
        total_mpds = summary.get("total_active_mpds", raw_result.get("total_mpds", 0))
        metar_saved = summary.get("metar_saved", raw_result.get("metar_saved", 0))
        taf_saved = summary.get("taf_saved", raw_result.get("taf_saved", 0))
        coord_saved = summary.get("coord_forecasts_saved", raw_result.get("coord_forecasts_saved", 0))
        duration = summary.get("duration_sec", 0)

        msg = (
            f"Метеоданные успешно обновлены: {total_mpds} МПД "
            f"(METAR: {metar_saved}, TAF: {taf_saved}, ECMWF точек: {coord_saved}) "
            f"за {duration} сек."
        )
        logger.info("Завершена sync_all_aviation_weather_task [task_id=%s]: %s", task_id, msg)

        return {
            "status": "SUCCESS",
            "message": msg,
            **raw_result,
        }
    except (ConnectionError, TimeoutError, OSError) as exc:
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            "Временный сетевой сбой при опросе метеоцентра [task_id=%s, retry_in=%ss]: %s",
            task_id,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        logger.exception(
            "Критическая ошибка в sync_all_aviation_weather_task [task_id=%s]: %s",
            task_id,
            exc,
        )
        raise exc


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    name="flight_planning.tasks.sync_mpd_weather_task",
)
def sync_mpd_weather_task(self, mpd_id: int) -> Dict[str, Any]:
    """Фоновая задача оперативного комплексного обновления погоды для конкретного МПД.

    Args:
        self: Экземпляр связанной задачи Celery (bind=True).
        mpd_id (int): Идентификатор места производственной деятельности.

    Returns:
        Dict[str, Any]: Информативный результат опроса конкретного МПД с расшифровкой метеоусловий.
    """
    from .weather_providers import WeatherManagerService

    task_id = self.request.id
    logger.info("Старт задачи sync_mpd_weather_task [task_id=%s, mpd_id=%s]", task_id, mpd_id)

    try:
        mpd = PlaceProductionActivity.objects.filter(pk=mpd_id).first()
        if not mpd:
            logger.warning("МПД id=%s не найден, задача отменена", mpd_id)
            return {"status": "SKIPPED", "reason": "MPD not found", "mpd_id": mpd_id}

        obs, fc = AviationWeatherService.sync_mpd_weather(mpd)
        coord_count = 0
        if mpd.latitude is not None and mpd.longitude is not None:
            coord_count = WeatherManagerService.sync_coordinate_forecasts_for_mpds([mpd])

        obs_time_str = obs.observation_time.strftime("%d.%m.%Y %H:%M UTC") if obs and obs.observation_time else None
        weather_summary = "Данные не поступили"
        if obs:
            summary_parts = []
            if obs.temperature is not None:
                summary_parts.append(f"{obs.temperature:+.0f}°C")
            if obs.wind_speed is not None:
                w_dir = f"{obs.wind_direction:03d}°" if obs.wind_direction is not None else "VRB"
                summary_parts.append(f"Ветер {w_dir} {obs.wind_speed:.0f} м/с")
            if obs.visibility_meters is not None:
                summary_parts.append(f"Вид. {obs.visibility_meters}м" if obs.visibility_meters < 10000 else "Вид. >10км")
            if obs.cloud_base_meters is not None:
                summary_parts.append(f"ВНГО {obs.cloud_base_meters}м")
            if obs.pressure_mmhg is not None:
                summary_parts.append(f"QNH {obs.pressure_mmhg:.1f} мм")
            if summary_parts:
                weather_summary = ", ".join(summary_parts)

        return {
            "status": "SUCCESS",
            "message": f"Погода для '{mpd.name}' ({mpd.icao_code or 'координаты'}) успешно обновлена.",
            "mpd_id": mpd_id,
            "mpd_name": mpd.name,
            "icao_code": mpd.icao_code or "—",
            "flight_category": obs.flight_category if obs else "N/A",
            "has_metar": bool(obs),
            "has_taf": bool(fc),
            "observation_time": obs_time_str,
            "weather_summary": weather_summary,
            "latest_raw_metar": obs.raw_text if obs else None,
            "coordinate_records_saved": coord_count,
            "sync_status": mpd.weather_sync_status,
        }
    except (ConnectionError, TimeoutError, OSError) as exc:
        countdown = 30 * (2 ** self.request.retries)
        logger.warning("Временный сбой при опросе погоды МПД %s [retry_in=%ss]: %s", mpd_id, countdown, exc)
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        logger.exception("Критическая ошибка в sync_mpd_weather_task [mpd_id=%s]: %s", mpd_id, exc)
        raise exc


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    name="flight_planning.tasks.sync_mpd_coordinate_weather_task",
)
def sync_mpd_coordinate_weather_task(self, mpd_id: int, force_model: Optional[str] = None) -> Dict[str, Any]:
    """Фоновая задача оперативного обновления координатного сеточного прогноза для МПД.

    Args:
        self: Экземпляр связанной задачи Celery.
        mpd_id (int): Идентификатор МПД.
        force_model (Optional[str]): Имя модели (ecmwf_ifs, gfs_seamless).

    Returns:
        Dict[str, Any]: Статистика сохраненных почасовых точек и статус.
    """
    from .weather_providers import WeatherManagerService

    try:
        mpd = PlaceProductionActivity.objects.filter(pk=mpd_id).first()
        if not mpd:
            return {"status": "SKIPPED", "reason": "MPD not found", "mpd_id": mpd_id}

        count = WeatherManagerService.sync_coordinate_forecasts_for_mpds([mpd], force_model=force_model)
        return {
            "status": "SUCCESS",
            "message": f"Координатный прогноз ECMWF для '{mpd.name}' успешно обновлен ({count} почасовых точек).",
            "mpd_id": mpd_id,
            "mpd_name": mpd.name,
            "saved_points": count,
            "model": force_model or "ecmwf_ifs",
        }
    except Exception as exc:
        logger.exception("Ошибка в sync_mpd_coordinate_weather_task [mpd_id=%s]: %s", mpd_id, exc)
        raise exc

