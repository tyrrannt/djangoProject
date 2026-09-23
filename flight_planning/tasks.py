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
def sync_mpd_weather_task(
    self,
    mpd_id: int,
    mode: str = "all",
    force_model: Optional[str] = None,
    *args: Any,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Фоновая задача оперативного комплексного обновления погоды для конкретного МПД.

    Выполняет опрос сводок METAR/TAF и гидродинамической сеточной модели с фиксацией
    интерактивных событий в состоянии задачи (state='PROGRESS') для онлайн-мониторинга.

    Args:
        self: Экземпляр связанной задачи Celery (bind=True).
        mpd_id (int): Идентификатор места производственной деятельности.
        mode (str, optional): Режим синхронизации ('metar', 'coordinate', 'all'). Defaults to 'all'.
        force_model (Optional[str], optional): Принудительная модель (ecmwf_ifs, gfs_seamless). Defaults to None.
        *args: Дополнительные позиционные аргументы для обратной совместимости.
        **kwargs: Дополнительные именованные аргументы для обратной совместимости.

    Returns:
        Dict[str, Any]: Информативный результат с массивом хронологических логов и статистикой.
    """
    from django.utils import timezone
    from .weather_services import AviationWeatherService

    # Безопасное извлечение параметров при вызове с любой комбинацией args/kwargs
    if "mode" in kwargs and kwargs["mode"]:
        mode = str(kwargs["mode"])
    elif len(args) >= 1 and args[0]:
        mode = str(args[0])

    if "force_model" in kwargs and kwargs["force_model"]:
        force_model = str(kwargs["force_model"])
    elif "model" in kwargs and kwargs["model"]:
        force_model = str(kwargs["model"])
    elif len(args) >= 2 and args[1]:
        force_model = str(args[1])

    task_id = self.request.id
    logger.info("Старт задачи sync_mpd_weather_task [task_id=%s, mpd_id=%s, mode=%s, model=%s]", task_id, mpd_id, mode, force_model)

    try:
        mpd = PlaceProductionActivity.objects.filter(pk=mpd_id).first()
        if not mpd:
            logger.warning("МПД id=%s не найден, задача отменена", mpd_id)
            return {"status": "SKIPPED", "success": False, "reason": "MPD not found", "mpd_id": mpd_id, "logs": []}

        live_logs: list = []

        def on_progress(pct: int, msg: str, level: str) -> None:
            ts = timezone.now().strftime("%H:%M:%S")
            live_logs.append({"time": ts, "message": msg, "level": level})
            self.update_state(
                state="PROGRESS",
                meta={
                    "percent": pct,
                    "message": msg,
                    "level": level,
                    "logs": list(live_logs),
                    "mpd_id": mpd_id,
                    "mpd_name": mpd.name,
                },
            )

        on_progress(5, f"Инициализация фоновой задачи обновления метеоданных для «{mpd.name}» (ID: {task_id[:13]}...)", "start")

        result = AviationWeatherService.sync_mpd_weather_with_progress(
            mpd=mpd,
            mode=mode,
            force_model=force_model,
            progress_callback=on_progress,
        )

        return {
            "status": "SUCCESS" if result["success"] else "FAILURE",
            "success": result["success"],
            "has_warnings": result.get("has_warnings", False),
            "has_errors": result.get("has_errors", False),
            "message": f"Погода для «{mpd.name}» обновлена.",
            "mpd_id": mpd_id,
            "mpd_name": mpd.name,
            "logs": result["logs"],
            "stats": result.get("stats", {}),
            "error": result.get("error"),
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

