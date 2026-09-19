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

    Опрашивает открытый шлюз NOAA по всем активным МПД с включенным мониторингом,
    декодирует параметры погоды и сохраняет их в базу данных.

    Args:
        self: Экземпляр связанной задачи Celery (bind=True).

    Returns:
        Dict[str, Any]: Результат выполнения (статус и статистика по сохраненным сводкам).

    Raises:
        self.retry: При возникновении временных сетевых ошибок и таймаутов.
    """
    task_id = self.request.id
    logger.info("Старт задачи sync_all_aviation_weather_task [task_id=%s, attempt=%s]", task_id, self.request.retries + 1)

    try:
        stats = AviationWeatherService.sync_all_active_mpds()
        logger.info(
            "Успешно завершена sync_all_aviation_weather_task [task_id=%s]: обработано %s МПД (METAR: %s, TAF: %s)",
            task_id,
            stats.get("total_mpds", 0),
            stats.get("metar_saved", 0),
            stats.get("taf_saved", 0),
        )
        return {
            "status": "success",
            "stats": stats,
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
        Dict[str, Any]: Результат опроса конкретного МПД.
    """
    from .weather_providers import WeatherManagerService

    task_id = self.request.id
    logger.info("Старт задачи sync_mpd_weather_task [task_id=%s, mpd_id=%s]", task_id, mpd_id)

    try:
        mpd = PlaceProductionActivity.objects.filter(pk=mpd_id).first()
        if not mpd:
            logger.warning("МПД id=%s не найден, задача отменена", mpd_id)
            return {"status": "skipped", "reason": "MPD not found", "mpd_id": mpd_id}

        obs, fc = AviationWeatherService.sync_mpd_weather(mpd)
        coord_count = 0
        if mpd.latitude is not None and mpd.longitude is not None:
            coord_count = WeatherManagerService.sync_coordinate_forecasts_for_mpds([mpd])

        return {
            "status": "success",
            "mpd_id": mpd_id,
            "icao_code": mpd.icao_code,
            "has_metar": bool(obs),
            "has_taf": bool(fc),
            "coordinate_records_saved": coord_count,
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
        Dict[str, Any]: Статистика сохраненных почасовых точек.
    """
    from .weather_providers import WeatherManagerService

    try:
        mpd = PlaceProductionActivity.objects.filter(pk=mpd_id).first()
        if not mpd:
            return {"status": "skipped", "reason": "MPD not found", "mpd_id": mpd_id}

        count = WeatherManagerService.sync_coordinate_forecasts_for_mpds([mpd], force_model=force_model)
        return {"status": "success", "mpd_id": mpd_id, "saved_points": count}
    except Exception as exc:
        logger.exception("Ошибка в sync_mpd_coordinate_weather_task [mpd_id=%s]: %s", mpd_id, exc)
        raise exc

