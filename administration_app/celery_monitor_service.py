"""Сервис комплексного мониторинга, инспекции и управления задачами Celery в реальном времени.

Модуль обеспечивает сбор телеметрии воркеров, очередей Redis, активных и отложенных задач,
парсинг расписания Celery Beat с расчетом времени следующего запуска, чтение истории
выполнения и стеков ошибок из Celery Result Backend, а также безопасное интерактивное
управление (запуск с кастомными аргументами, отмена зависших задач, очистка очередей, пинг).
"""

import datetime
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from celery import current_app
from celery.result import AsyncResult
from celery.schedules import crontab
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import redis

from administration_app.utils import format_name_initials

logger = logging.getLogger(__name__)


# Словарь человекочитаемых названий и категорий для известных периодических и фоновых задач
TASK_METADATA_REGISTRY: Dict[str, Dict[str, str]] = {
    # hrdepartment_app
    "hrdepartment_app.tasks.report_card_separator": {
        "title": "Разделитель записей табеля 1С",
        "category": "Табель и персонал",
        "icon": "bx bx-calendar-check",
        "description": "Разбивает и упорядочивает импортированные из 1С записи табелей учета рабочего времени.",
    },
    "hrdepartment_app.tasks.get_database_user": {
        "title": "Синхронизация сотрудников с 1С ЗУП",
        "category": "Табель и персонал",
        "icon": "bx bx-user-check",
        "description": "Периодический опрос OData 1С для актуализации профилей, должностей и подразделений персонала.",
    },
    "hrdepartment_app.tasks.happy_birthday": {
        "title": "Контроль дней рождения и поздравления",
        "category": "Персонал",
        "icon": "bx bx-gift",
        "description": "Проверяет сегодняшних именинников и формирует записи поздравлений.",
    },
    "hrdepartment_app.tasks.birthday_telegram": {
        "title": "Публикация именинников в Telegram-канал",
        "category": "Telegram",
        "icon": "bx bxl-telegram",
        "description": "Ежедневная утренняя отправка поздравительного поста в корпоративный Telegram-канал.",
    },
    "hrdepartment_app.tasks.send_telegram_notify": {
        "title": "Отправка служебных уведомлений в Telegram",
        "category": "Telegram",
        "icon": "bx bx-bell",
        "description": "Пакетная рассылка системных оповещений и уведомлений в чаты сотрудников.",
    },
    "hrdepartment_app.tasks.expire_old_bookings": {
        "title": "Аннулирование устаревших бронирований",
        "category": "Служебные",
        "icon": "bx bx-time",
        "description": "Ежесуточная очистка и перевод в архив неподтвержденных бронирований оборудования и помещений.",
    },

    # finance_app
    "finance_app.tasks.sync_directories_task": {
        "title": "Синхронизация финансовых справочников 1С",
        "category": "Финансы",
        "icon": "bx bx-book-content",
        "description": "Обновляет справочники контрагентов, статей ДДС и банковских счетов из 1С Бухгалтерии.",
    },
    "finance_app.tasks.sync_debts_task": {
        "title": "Синхронизация задолженностей и взаиморасчетов",
        "category": "Финансы",
        "icon": "bx bx-credit-card",
        "description": "Загрузка актуального сальдо дебиторской и кредиторской задолженности из учетной системы.",
    },
    "finance_app.tasks.sync_payments_task": {
        "title": "Синхронизация платежей и выписок 1С",
        "category": "Финансы",
        "icon": "bx bx-money",
        "description": "Импорт входящих и исходящих безналичных банковских платежей.",
    },
    "finance_app.tasks.sync_credits_task": {
        "title": "Синхронизация кредитов, займов и лизингов",
        "category": "Финансы",
        "icon": "bx bx-wallet",
        "description": "Актуализация графиков гашения, остатков основного долга и начисленных процентов.",
    },
    "finance_app.tasks.send_upcoming_payment_notifications_task": {
        "title": "Уведомления о предстоящих платежах",
        "category": "Финансы",
        "icon": "bx bx-alarm",
        "description": "Оповещение финансовых контролеров о наступлении сроков оплаты по договорам.",
    },
    "finance_app.tasks.check_overdraft_tranches_task": {
        "title": "Контроль траншей овердрафта",
        "category": "Финансы",
        "icon": "bx bx-line-chart",
        "description": "Ежедневный аудит сроков действия открытых траншей овердрафта и кредитных линий.",
    },

    # testing_app
    "testing_app.tasks.check_expired_attempts_task": {
        "title": "Проверка истекших попыток тестирования",
        "category": "Обучение и тесты",
        "icon": "bx bx-timer",
        "description": "Автоматическое завершение и расчет результатов тестов с превышенным лимитом времени.",
    },
    "testing_app.tasks.send_deadline_reminders_task": {
        "title": "Напоминания о дедлайнах тестирования",
        "category": "Обучение и тесты",
        "icon": "bx bx-envelope",
        "description": "Рассылка писем сотрудникам, у которых заканчивается срок прохождения обязательных тестов.",
    },
    "testing_app.tasks.auto_activate_scheduled_testings_task": {
        "title": "Автоактивация запланированных тестирований",
        "category": "Обучение и тесты",
        "icon": "bx bx-play-circle",
        "description": "Перевод назначенных тестирований в статус активных при наступлении даты старта.",
    },

    # mailbox_app
    "mailbox_app.tasks.process_scheduled_emails_task": {
        "title": "Отправка отложенных e-mail писем",
        "category": "Почта",
        "icon": "bx bx-send",
        "description": "Обработка очереди исходящих почтовых сообщений и вложений.",
    },
    "mailbox_app.tasks.poll_mailboxes_unread_task": {
        "title": "Опрос почтовых ящиков на новые письма",
        "category": "Почта",
        "icon": "bx bx-envelope-open",
        "description": "Фоновая синхронизация IMAP/POP3 почтовых ящиков компании.",
    },

    # tasks_app
    "tasks_app.tasks.check_task_deadlines_task": {
        "title": "Контроль сроков и дедлайнов поручений",
        "category": "Задачи",
        "icon": "bx bx-list-check",
        "description": "Проверка наступления контрольных сроков задач и уведомление исполнителей.",
    },
    "tasks_app.tasks.create_recurring_tasks_task": {
        "title": "Генерация регулярных повторяющихся задач",
        "category": "Задачи",
        "icon": "bx bx-repeat",
        "description": "Создание новых экземпляров циклических задач по заданному графику повторения.",
    },

    # logistics_app
    "logistics_app.tasks.check_docflow_sla_deadlines_task": {
        "title": "Контроль SLA и сроков согласования СЭД",
        "category": "Документооборот (СЭД)",
        "icon": "bx bx-file",
        "description": "Проверка истечения сроков визирования этапов документов и эскалация просрочек.",
    },
    "logistics_app.tasks.send_docflow_assignment_notification_task": {
        "title": "Уведомление согласующего лица СЭД",
        "category": "Документооборот (СЭД)",
        "icon": "bx bx-mail-send",
        "description": "Отправка письма с ссылкой на документ при переходе маршрута на следующий шаг.",
    },

    # flight_planning
    "flight_planning.tasks.sync_all_aviation_weather_task": {
        "title": "Сбор авиационной метеорологии (METAR/TAF/ECMWF)",
        "category": "Авиация и полеты",
        "icon": "bx bx-cloud-rain",
        "description": "Пакетный сбор сводок METAR/TAF со шлюзов NOAA и расчет координатных прогнозов Open-Meteo (ECMWF) по всем активным МПД.",
    },
    "flight_planning.tasks.sync_mpd_weather_task": {
        "title": "Оперативное обновление погоды площадки МПД",
        "category": "Авиация и полеты",
        "icon": "bx bx-sun",
        "description": "Индивидуальный опрос фактических наблюдений METAR, прогноза TAF и координатной модели для выбранной площадки.",
    },
    "flight_planning.tasks.sync_mpd_coordinate_weather_task": {
        "title": "Расчет координатного сеточного прогноза",
        "category": "Авиация и полеты",
        "icon": "bx bx-wind",
        "description": "Обновление почасовых гидродинамических сеточных прогнозов ECMWF/GFS для географических координат МПД.",
    },
}


def get_task_meta(task_name: str) -> Dict[str, str]:
    """Возвращает метаданные и человекочитаемое наименование задачи.

    Args:
        task_name (str): Полное имя функции задачи (например, 'finance_app.tasks.sync_debts_task').

    Returns:
        Dict[str, str]: Словарь с полями 'title', 'category', 'icon', 'description', 'short_name'.
    """
    if task_name in TASK_METADATA_REGISTRY:
        meta = dict(TASK_METADATA_REGISTRY[task_name])
        meta["short_name"] = task_name.split(".")[-1]
        return meta

    # Автоматическое форматирование для незарегистрированных задач
    parts = task_name.split(".")
    short_name = parts[-1]
    app_label = parts[0] if len(parts) > 1 else "celery"

    # Преобразование snake_case в заголовок
    words = short_name.replace("_task", "").replace("_", " ").strip()
    title = words.capitalize() if words else short_name

    return {
        "title": title,
        "category": app_label.replace("_app", "").capitalize(),
        "icon": "bx bx-cog",
        "description": f"Фоновая задача модуля {app_label}.",
        "short_name": short_name,
    }


def format_crontab_human(sched: Any) -> str:
    """Форматирует расписание задачи Celery Beat в человекочитаемую строку на русском языке.

    Args:
        sched (Any): Объект расписания Celery (crontab, int, float).

    Returns:
        str: Понятное описание графика (например, 'Каждые 5 минут', 'Ежедневно в 09:30').
    """
    if isinstance(sched, (int, float)):
        sec = int(sched)
        if sec < 60:
            return f"Каждые {sec} сек."
        elif sec % 3600 == 0:
            return f"Каждые {sec // 3600} ч."
        elif sec % 60 == 0:
            return f"Каждые {sec // 60} мин."
        return f"Интервал {sec} сек."

    if not hasattr(sched, "_orig_minute") and not hasattr(sched, "minute"):
        return str(sched)

    min_str = str(getattr(sched, "_orig_minute", sched.minute)).strip("{}'")
    hour_str = str(getattr(sched, "_orig_hour", sched.hour)).strip("{}'")
    dow_str = str(getattr(sched, "_orig_day_of_week", sched.day_of_week)).strip("{}'")
    dom_str = str(getattr(sched, "_orig_day_of_month", sched.day_of_month)).strip("{}'")
    mon_str = str(getattr(sched, "_orig_month_of_year", sched.month_of_year)).strip("{}'")

    # Разбор частых паттернов
    if min_str == "*/1" and hour_str in ("*", "*/*"):
        return "Каждую минуту"
    if min_str.startswith("*/") and hour_str in ("*", "*/*"):
        step = min_str.replace("*/", "")
        return f"Каждые {step} минут"
    if min_str == "0" and hour_str.startswith("*/"):
        step = hour_str.replace("*/", "")
        return f"Каждые {step} ч."
    if min_str.isdigit() and hour_str.isdigit():
        h = int(hour_str)
        m = int(min_str)
        dow_desc = ""
        if dow_str not in ("*", "*/*", "0-6", "sun-sat"):
            dow_map = {"0": "вс", "1": "пн", "2": "вт", "3": "ср", "4": "чт", "5": "пт", "6": "сб", "7": "вс"}
            dow_desc = f" ({dow_map.get(dow_str, dow_str)})"
        return f"Ежедневно в {h:02d}:{m:02d}{dow_desc}"
    if min_str.isdigit() and hour_str in ("*", "*/*"):
        m = int(min_str)
        return f"Каждый час в :{m:02d} мин."

    return f"crontab(m={min_str}, h={hour_str}, dow={dow_str})"


def estimate_next_run(sched: Any) -> Tuple[Optional[str], str]:
    """Вычисляет расчетное время и обратный отсчет до следующего запуска периодической задачи.

    Args:
        sched (Any): Объект расписания задачи.

    Returns:
        Tuple[Optional[str], str]: Кортеж (ISO строка времени, строка обратного отсчета 'через X мин').
    """
    now = timezone.now()
    try:
        if isinstance(sched, (int, float)):
            delta = datetime.timedelta(seconds=float(sched))
            next_time = now + delta
            sec_left = int(delta.total_seconds())
            return next_time.strftime("%d.%m.%Y %H:%M:%S"), f"через {sec_left} сек."

        if hasattr(sched, "remaining_estimate"):
            # Расчет через встроенный механизм Celery schedule
            rem = sched.remaining_estimate(now)
            sec_left = int(rem.total_seconds()) if hasattr(rem, "total_seconds") else int(rem)
            if sec_left < 0:
                sec_left = 0
            next_time = now + datetime.timedelta(seconds=sec_left)

            if sec_left < 60:
                countdown = f"через {sec_left} сек."
            elif sec_left < 3600:
                countdown = f"через {sec_left // 60} мин. {sec_left % 60} сек."
            else:
                countdown = f"через {sec_left // 3600} ч. {(sec_left % 3600) // 60} мин."

            return next_time.strftime("%d.%m.%Y %H:%M:%S"), countdown
    except Exception as exc:
        logger.debug("Не удалось рассчитать точное время следующего запуска: %s", exc)

    return None, "По расписанию"


def parse_schedule_hourly_distribution(schedule_obj: Any) -> Tuple[Set[int], int]:
    """Анализирует расписание задачи и вычисляет активные часы суток и частоту запусков в час.

    Args:
        schedule_obj (Any): Объект расписания (crontab, int, float).

    Returns:
        Tuple[Set[int], int]: Кортеж из множества часов суток (0..23) и количества запусков в каждый активный час.
    """
    all_hours = set(range(24))

    if isinstance(schedule_obj, (int, float)):
        sec = int(schedule_obj)
        runs_per_hour = max(1, 3600 // max(1, sec))
        return all_hours, runs_per_hour

    # Извлечение множества часов
    active_hours = set(range(24))
    if hasattr(schedule_obj, "hour"):
        raw_hour = getattr(schedule_obj, "_orig_hour", schedule_obj.hour)
        if isinstance(raw_hour, (set, list, tuple)):
            active_hours = {int(h) for h in raw_hour if str(h).isdigit() and 0 <= int(h) <= 23}
        elif isinstance(raw_hour, int):
            active_hours = {raw_hour} if 0 <= raw_hour <= 23 else all_hours
        elif isinstance(raw_hour, str):
            clean_h = raw_hour.strip("{}'\" ")
            if clean_h.startswith("*/"):
                try:
                    step = int(clean_h.replace("*/", ""))
                    active_hours = {h for h in range(24) if h % step == 0}
                except Exception:
                    active_hours = all_hours
            elif clean_h.isdigit():
                active_hours = {int(clean_h)}
            elif "," in clean_h:
                active_hours = {int(h.strip()) for h in clean_h.split(",") if h.strip().isdigit() and 0 <= int(h.strip()) <= 23}
            elif "-" in clean_h:
                try:
                    s_part, e_part = clean_h.split("-", 1)
                    active_hours = {h for h in range(int(s_part), int(e_part) + 1) if 0 <= h <= 23}
                except Exception:
                    active_hours = all_hours
            elif clean_h in ("*", "*/*"):
                active_hours = all_hours

    if not active_hours:
        active_hours = all_hours

    # Извлечение количества запусков в час (по минутам)
    runs_per_hour = 1
    if hasattr(schedule_obj, "minute"):
        raw_min = getattr(schedule_obj, "_orig_minute", schedule_obj.minute)
        if isinstance(raw_min, (set, list, tuple)):
            runs_per_hour = max(1, len(raw_min))
        elif isinstance(raw_min, int):
            runs_per_hour = 1
        elif isinstance(raw_min, str):
            clean_m = raw_min.strip("{}'\" ")
            if clean_m.startswith("*/"):
                try:
                    step = int(clean_m.replace("*/", ""))
                    runs_per_hour = max(1, 60 // max(1, step))
                except Exception:
                    runs_per_hour = 1
            elif clean_m == "*":
                runs_per_hour = 60
            elif "," in clean_m:
                runs_per_hour = max(1, len(clean_m.split(",")))
            elif "-" in clean_m:
                try:
                    s_part, e_part = clean_m.split("-", 1)
                    runs_per_hour = max(1, int(e_part) - int(s_part) + 1)
                except Exception:
                    runs_per_hour = 1
            else:
                runs_per_hour = 1

    return active_hours, runs_per_hour


class CeleryMonitorService:
    """Сервис сбора телеметрии, инспекции и интерактивного управления задачами Celery."""

    @classmethod
    def get_redis_client(cls) -> Optional[redis.Redis]:
        """Создает и возвращает настроенный клиент Redis с коротким таймаутом соединения.

        Returns:
            Optional[redis.Redis]: Экземпляр клиента Redis или None при недоступности.
        """
        try:
            broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
            client = redis.Redis.from_url(
                broker_url,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
                decode_responses=True,
            )
            client.ping()
            return client
        except Exception as exc:
            logger.warning("[CeleryMonitor] Ошибка подключения к Redis: %s", exc)
            return None

    @classmethod
    def get_workers_telemetry(cls) -> Dict[str, Any]:
        """Выполняет инспекцию состояния всех активных воркеров Celery.

        Returns:
            Dict[str, Any]: Словарь с перечнем воркеров, их параметрами, PID и счетчиками задач.
        """
        workers_data: List[Dict[str, Any]] = []
        is_alive = False

        try:
            inspector = current_app.control.inspect(timeout=1.2)
            if inspector:
                stats = inspector.stats() or {}
                active = inspector.active() or {}
                ping = inspector.ping() or {}
                registered = inspector.registered() or {}

                for worker_name in set(list(stats.keys()) + list(ping.keys())):
                    w_stats = stats.get(worker_name, {})
                    w_active = active.get(worker_name, [])
                    w_registered = registered.get(worker_name, [])
                    w_ping = ping.get(worker_name)

                    online = bool(w_ping and w_ping.get("ok") == "pong") or bool(w_stats)
                    if online:
                        is_alive = True

                    pool_info = w_stats.get("pool", {})
                    max_concurrency = pool_info.get("max-concurrency", 1)
                    processes = pool_info.get("processes", [])
                    total_processed = sum(w_stats.get("total", {}).values()) if isinstance(w_stats.get("total"), dict) else 0

                    workers_data.append({
                        "name": worker_name,
                        "online": online,
                        "pid": w_stats.get("pid"),
                        "concurrency": max_concurrency,
                        "process_pids": processes,
                        "active_tasks_count": len(w_active),
                        "total_processed_tasks": total_processed,
                        "registered_tasks_count": len(w_registered),
                        "broker": w_stats.get("broker", {}).get("hostname", "Redis"),
                        "clock": w_stats.get("clock", 0),
                    })
        except Exception as exc:
            logger.debug("[CeleryMonitor] Исключение при опросе воркеров через inspect: %s", exc)

        return {
            "workers": workers_data,
            "workers_count": len(workers_data),
            "online_count": sum(1 for w in workers_data if w["online"]),
            "is_any_worker_alive": is_alive,
        }

    @classmethod
    def get_active_tasks(cls) -> List[Dict[str, Any]]:
        """Возвращает список всех задач, выполняющихся в данный момент на воркерах.

        Returns:
            List[Dict[str, Any]]: Список словарей с реквизитами выполняющихся задач.
        """
        active_tasks: List[Dict[str, Any]] = []
        now_ts = time.time()

        try:
            inspector = current_app.control.inspect(timeout=1.2)
            if inspector:
                active_dict = inspector.active() or {}
                for worker_name, tasks in active_dict.items():
                    for t in tasks:
                        task_name = t.get("name", "")
                        meta = get_task_meta(task_name)
                        time_start = t.get("time_start", now_ts)
                        runtime_sec = round(max(0.0, now_ts - time_start), 1) if time_start else 0.0

                        active_tasks.append({
                            "id": t.get("id"),
                            "name": task_name,
                            "title": meta["title"],
                            "category": meta["category"],
                            "icon": meta["icon"],
                            "worker": worker_name,
                            "args": t.get("args", []),
                            "kwargs": t.get("kwargs", {}),
                            "args_repr": t.get("argsrepr", "()"),
                            "kwargs_repr": t.get("kwargsrepr", "{}"),
                            "time_start_ts": time_start,
                            "time_start_iso": datetime.datetime.fromtimestamp(time_start, tz=datetime.timezone.utc).strftime("%d.%m.%Y %H:%M:%S") if time_start else "—",
                            "runtime_sec": runtime_sec,
                            "acknowledged": t.get("acknowledged", True),
                        })
        except Exception as exc:
            logger.debug("[CeleryMonitor] Исключение при получении активных задач: %s", exc)

        # Сортировка по времени начала выполнения (сначала самые долго работающие)
        active_tasks.sort(key=lambda x: x.get("time_start_ts", 0))
        return active_tasks

    @classmethod
    def get_reserved_and_scheduled_tasks(cls) -> Dict[str, List[Dict[str, Any]]]:
        """Возвращает список задач, ожидающих в очереди воркеров (Reserved) и отложенных по таймеру (Scheduled/ETA).

        Returns:
            Dict[str, List[Dict[str, Any]]]: Словарь со списками 'reserved' и 'scheduled'.
        """
        reserved_list: List[Dict[str, Any]] = []
        scheduled_list: List[Dict[str, Any]] = []

        try:
            inspector = current_app.control.inspect(timeout=1.2)
            if inspector:
                # Reserved tasks (взяты воркером из очереди, ожидают освобождения слота)
                res_dict = inspector.reserved() or {}
                for worker_name, tasks in res_dict.items():
                    for t in tasks:
                        task_name = t.get("name", "")
                        meta = get_task_meta(task_name)
                        reserved_list.append({
                            "id": t.get("id"),
                            "name": task_name,
                            "title": meta["title"],
                            "category": meta["category"],
                            "icon": meta["icon"],
                            "worker": worker_name,
                            "args": t.get("args", []),
                            "kwargs": t.get("kwargs", {}),
                        })

                # Scheduled tasks (с отложенным временем исполнения ETA)
                sched_dict = inspector.scheduled() or {}
                for worker_name, tasks in sched_dict.items():
                    for t in tasks:
                        task_name = t.get("request", {}).get("name", t.get("name", ""))
                        meta = get_task_meta(task_name)
                        eta = t.get("eta")
                        scheduled_list.append({
                            "id": t.get("request", {}).get("id", t.get("id")),
                            "name": task_name,
                            "title": meta["title"],
                            "category": meta["category"],
                            "icon": meta["icon"],
                            "worker": worker_name,
                            "eta": eta,
                            "priority": t.get("priority", 0),
                        })
        except Exception as exc:
            logger.debug("[CeleryMonitor] Исключение при получении reserved/scheduled задач: %s", exc)

        return {
            "reserved": reserved_list,
            "scheduled": scheduled_list,
        }

    @classmethod
    def get_beat_schedule_list(cls) -> List[Dict[str, Any]]:
        """Формирует структурированный каталог всех периодических задач Celery Beat.

        Парсит конфигурацию `app.conf.beat_schedule`, рассчитывает человекочитаемое
        расписание, таймер следующего запуска и параметры по умолчанию.

        Returns:
            List[Dict[str, Any]]: Список словарей с описанием периодических задач.
        """
        beat_tasks: List[Dict[str, Any]] = []
        schedule_conf = getattr(current_app.conf, "beat_schedule", {})
        if not schedule_conf:
            try:
                from djangoProject.celery import app as direct_celery_app
                schedule_conf = getattr(direct_celery_app.conf, "beat_schedule", {})
            except Exception:
                schedule_conf = {}

        for key, entry in schedule_conf.items():
            task_name = entry.get("task", "")
            schedule_obj = entry.get("schedule")
            meta = get_task_meta(task_name)
            sched_human = format_crontab_human(schedule_obj)
            next_run_iso, countdown = estimate_next_run(schedule_obj)

            beat_tasks.append({
                "key": key,
                "task_name": task_name,
                "title": meta["title"],
                "category": meta["category"],
                "icon": meta["icon"],
                "description": meta["description"],
                "schedule_human": sched_human,
                "schedule_raw": str(schedule_obj),
                "next_run_iso": next_run_iso,
                "countdown": countdown,
                "args": entry.get("args", []),
                "kwargs": entry.get("kwargs", {}),
            })

        # Сортировка по категории, затем по наименованию
        beat_tasks.sort(key=lambda x: (x["category"], x["title"]))
        return beat_tasks

    @classmethod
    def get_task_history_from_redis(cls, limit: int = 40) -> List[Dict[str, Any]]:
        """Считывает историю завершенных задач и их результаты из Celery Result Backend (Redis).

        Args:
            limit (int): Максимальное количество последних задач для возврата.

        Returns:
            List[Dict[str, Any]]: Список завершенных задач с результатом или стеком ошибки.
        """
        history_tasks: List[Dict[str, Any]] = []
        r = cls.get_redis_client()
        if not r:
            return history_tasks

        try:
            # Сканируем ключи результатов Celery
            keys: List[str] = []
            for key in r.scan_iter(match="celery-task-meta-*", count=100):
                keys.append(key)
                if len(keys) >= limit * 3:
                    break

            if not keys:
                return history_tasks

            # Извлекаем значения через pipeline для высокой скорости
            pipe = r.pipeline()
            for k in keys:
                pipe.get(k)
            values = pipe.execute()

            for key, val_str in zip(keys, values):
                if not val_str:
                    continue
                try:
                    data = json.loads(val_str)
                    task_id = key.replace("celery-task-meta-", "")
                    status = data.get("status", "UNKNOWN")
                    result_raw = data.get("result")
                    traceback_str = data.get("traceback") or ""
                    date_done_str = data.get("date_done") or ""

                    # Форматирование результата для безопасного вывода
                    result_preview = ""
                    if status == "SUCCESS":
                        if isinstance(result_raw, (dict, list)):
                            result_preview = json.dumps(result_raw, ensure_ascii=False)[:120]
                        else:
                            result_preview = str(result_raw)[:120]
                    elif status == "FAILURE":
                        result_preview = str(result_raw)[:120] if result_raw else "Ошибка выполнения"

                    # Определение имени задачи (из метаданных или сопоставления)
                    task_name = data.get("task") or data.get("name") or ""
                    meta = get_task_meta(task_name) if task_name else {
                        "title": "Фоновая задача",
                        "category": "История",
                        "icon": "bx bx-history",
                        "description": "",
                        "short_name": task_id[:8],
                    }

                    # Форматирование даты
                    formatted_date = date_done_str
                    if date_done_str:
                        try:
                            dt = datetime.datetime.fromisoformat(date_done_str.replace("Z", "+00:00"))
                            formatted_date = dt.strftime("%d.%m.%Y %H:%M:%S")
                        except Exception:
                            pass

                    history_tasks.append({
                        "task_id": task_id,
                        "status": status,
                        "task_name": task_name,
                        "title": meta["title"],
                        "category": meta["category"],
                        "icon": meta["icon"],
                        "result_preview": result_preview,
                        "has_traceback": bool(traceback_str),
                        "date_done": formatted_date,
                        "date_done_raw": date_done_str,
                    })
                except Exception:
                    continue

            # Сортировка по дате завершения (сначала самые свежие)
            history_tasks.sort(key=lambda x: x.get("date_done_raw", ""), reverse=True)
            return history_tasks[:limit]

        except Exception as exc:
            logger.debug("[CeleryMonitor] Исключение при чтении истории из Redis: %s", exc)
            return []

    @classmethod
    def get_redis_queue_stats(cls) -> Dict[str, Any]:
        """Возвращает статистику брокера Redis и количество сообщений в очередях Celery.

        Returns:
            Dict[str, Any]: Словарь с показателями очередей, статусом подключения и памятью.
        """
        stats = {
            "connected": False,
            "host": getattr(settings, "REDIS_HOST", "127.0.0.1"),
            "default_queue_length": 0,
            "all_queues": {},
            "used_memory_human": "—",
            "connected_clients": 0,
            "total_keys": 0,
        }

        r = cls.get_redis_client()
        if not r:
            return stats

        try:
            stats["connected"] = True
            info = r.info()
            stats["used_memory_human"] = info.get("used_memory_human", "—")
            stats["connected_clients"] = info.get("connected_clients", 0)
            stats["total_keys"] = r.dbsize()

            # Проверяем стандартную очередь celery и возможные кастомные
            known_queues = ["celery", "default", "high_priority", "beat", "docflow"]
            for q_name in known_queues:
                if r.exists(q_name):
                    length = r.llen(q_name)
                    stats["all_queues"][q_name] = length
                    if q_name == "celery":
                        stats["default_queue_length"] = length

            if "celery" not in stats["all_queues"]:
                stats["all_queues"]["celery"] = 0

        except Exception as exc:
            logger.debug("[CeleryMonitor] Исключение при получении метрик очередей Redis: %s", exc)

        return stats

    @classmethod
    def get_task_details(cls, task_id: str) -> Dict[str, Any]:
        """Возвращает полную детальную информацию по конкретной задаче (результат, аргументы, Traceback).

        Args:
            task_id (str): UUID идентификатор задачи Celery.

        Returns:
            Dict[str, Any]: Полные данные задачи с форматированным стеком вызовов.
        """
        res = AsyncResult(task_id)
        status = res.status
        r = cls.get_redis_client()
        meta_dict: Dict[str, Any] = {}

        if r:
            try:
                raw = r.get(f"celery-task-meta-{task_id}")
                if raw:
                    meta_dict = json.loads(raw)
            except Exception:
                pass

        result_val = meta_dict.get("result") if meta_dict else (res.result if status == "SUCCESS" else None)
        traceback_str = meta_dict.get("traceback") or (res.traceback if hasattr(res, "traceback") else "") or ""
        date_done = meta_dict.get("date_done") or ""

        # Форматирование JSON для читабельности
        result_json_pretty = ""
        if result_val is not None:
            try:
                if isinstance(result_val, (dict, list)):
                    result_json_pretty = json.dumps(result_val, ensure_ascii=False, indent=2)
                else:
                    result_json_pretty = str(result_val)
            except Exception:
                result_json_pretty = str(result_val)

        return {
            "task_id": task_id,
            "status": status,
            "ready": res.ready(),
            "successful": res.successful() if res.ready() else False,
            "failed": res.failed() if res.ready() else False,
            "date_done": date_done,
            "result_pretty": result_json_pretty,
            "traceback": traceback_str,
            "children": meta_dict.get("children", []),
            "args": meta_dict.get("args"),
            "kwargs": meta_dict.get("kwargs"),
        }

    @classmethod
    def get_comprehensive_payload(cls) -> Dict[str, Any]:
        """Формирует агрегированный срез всех показателей для дашборда и WebSocket-трансляции.

        Returns:
            Dict[str, Any]: Полная телеметрия системы задач Celery.
        """
        workers_info = cls.get_workers_telemetry()
        active_tasks = cls.get_active_tasks()
        queues_info = cls.get_reserved_and_scheduled_tasks()
        beat_schedule = cls.get_beat_schedule_list()
        task_history = cls.get_task_history_from_redis(limit=40)
        redis_stats = cls.get_redis_queue_stats()

        success_count = sum(1 for t in task_history if t["status"] == "SUCCESS")
        failure_count = sum(1 for t in task_history if t["status"] == "FAILURE")

        # Расчет распределения периодических задач по часам суток (Workload Timeline 24h Matrix)
        schedule_conf = getattr(current_app.conf, "beat_schedule", {})
        if not schedule_conf:
            try:
                from djangoProject.celery import app as direct_celery_app
                schedule_conf = getattr(direct_celery_app.conf, "beat_schedule", {})
            except Exception:
                schedule_conf = {}

        hourly_data: Dict[int, Dict[str, Any]] = {
            h: {
                "hour": f"{h:02d}:00",
                "hour_num": h,
                "runs_count": 0,
                "tasks": [],
                "unique_tasks_count": 0,
            }
            for h in range(24)
        }

        for key, entry in schedule_conf.items():
            task_name = entry.get("task", "")
            schedule_obj = entry.get("schedule")
            meta = get_task_meta(task_name)
            sched_human = format_crontab_human(schedule_obj)
            active_hours, runs_per_hour = parse_schedule_hourly_distribution(schedule_obj)

            for h in active_hours:
                hourly_data[h]["runs_count"] += runs_per_hour
                hourly_data[h]["tasks"].append({
                    "key": key,
                    "title": meta["title"],
                    "task_name": task_name,
                    "category": meta["category"],
                    "icon": meta["icon"],
                    "schedule_human": sched_human,
                    "runs_per_hour": runs_per_hour,
                })

        for h in range(24):
            hourly_data[h]["unique_tasks_count"] = len(hourly_data[h]["tasks"])

        max_hourly_runs = max((d["runs_count"] for d in hourly_data.values()), default=1) or 1
        total_daily_runs = sum(d["runs_count"] for d in hourly_data.values())

        hourly_workload_list: List[Dict[str, Any]] = []
        for h in range(24):
            d = hourly_data[h]
            count = d["runs_count"]
            if count == 0:
                intensity = "intensity-none"
            elif count >= max_hourly_runs:
                intensity = "intensity-peak"
            elif count >= max_hourly_runs * 0.7:
                intensity = "intensity-high"
            elif count >= max_hourly_runs * 0.35:
                intensity = "intensity-medium"
            else:
                intensity = "intensity-low"

            d["intensity_class"] = intensity
            # Для обратной совместимости со старым шаблоном
            d["count"] = count
            hourly_workload_list.append(d)

        peak_hours = [d["hour"] for d in hourly_workload_list if d["runs_count"] == max_hourly_runs]

        return {
            "timestamp": timezone.now().strftime("%d.%m.%Y %H:%M:%S"),
            "kpi": {
                "workers_total": workers_info["workers_count"],
                "workers_online": workers_info["online_count"],
                "is_workers_alive": workers_info["is_any_worker_alive"],
                "active_tasks_count": len(active_tasks),
                "reserved_tasks_count": len(queues_info["reserved"]),
                "scheduled_tasks_count": len(queues_info["scheduled"]),
                "redis_queue_length": redis_stats["default_queue_length"],
                "beat_tasks_total": len(beat_schedule),
                "history_success_count": success_count,
                "history_failure_count": failure_count,
                "broker_connected": redis_stats["connected"],
                "total_daily_runs": total_daily_runs,
                "max_hourly_runs": max_hourly_runs,
            },
            "workers": workers_info["workers"],
            "active_tasks": active_tasks,
            "reserved_tasks": queues_info["reserved"],
            "scheduled_tasks": queues_info["scheduled"],
            "beat_schedule": beat_schedule,
            "history": task_history,
            "redis_stats": redis_stats,
            "hourly_workload": hourly_workload_list,
            "analytics": {
                "total_daily_runs": total_daily_runs,
                "max_hourly_runs": max_hourly_runs,
                "peak_hours_str": ", ".join(peak_hours) if peak_hours else "—",
                "hourly_workload": hourly_workload_list,
            },
        }

    @classmethod
    def run_task_manually(
        cls,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        admin_username: str = "",
        ip_address: str = "",
    ) -> Tuple[bool, str, Optional[str]]:
        """Осуществляет принудительный запуск фоновой задачи с заданными параметрами.

        Args:
            task_name (str): Полное имя функции задачи (например, 'hrdepartment_app.tasks.happy_birthday').
            args (Optional[List[Any]]): Позиционные аргументы задачи.
            kwargs (Optional[Dict[str, Any]]): Именованные аргументы задачи.
            admin_username (str): Логин администратора для аудита.
            ip_address (str): IP-адрес клиента для журнала безопасности.

        Returns:
            Tuple[bool, str, Optional[str]]: Кортеж (успех, сообщение, task_id).
        """
        args = args or []
        kwargs = kwargs or {}

        try:
            async_result = current_app.send_task(
                task_name,
                args=args,
                kwargs=kwargs,
            )
            task_id = async_result.id

            logger.info(
                "[CeleryMonitor] Ручной запуск задачи: task=%s, task_id=%s, args=%s, kwargs=%s, admin=%s, ip=%s",
                task_name,
                task_id,
                args,
                kwargs,
                admin_username,
                ip_address,
            )
            return True, f"Задача «{task_name}» успешно поставлена в очередь (Task ID: {task_id}).", task_id

        except Exception as exc:
            logger.error(
                "[CeleryMonitor] Ошибка при ручном запуске задачи %s: %s (admin=%s)",
                task_name,
                exc,
                admin_username,
                exc_info=True,
            )
            return False, f"Ошибка запуска задачи: {str(exc)}", None

    @classmethod
    def revoke_task(
        cls,
        task_id: str,
        terminate: bool = True,
        signal: str = "SIGTERM",
        admin_username: str = "",
        ip_address: str = "",
    ) -> Tuple[bool, str]:
        """Принудительно отзывает или прерывает выполнение активной задачи Celery.

        Args:
            task_id (str): UUID идентификатор задачи.
            terminate (bool): Флаг немедленного завершения процесса воркера (SIGTERM/SIGKILL).
            signal (str): Тип сигнала прерывания ('SIGTERM' или 'SIGKILL').
            admin_username (str): Логин администратора для аудита.
            ip_address (str): IP-адрес клиента.

        Returns:
            Tuple[bool, str]: Кортеж (успех, статусное сообщение).
        """
        if not task_id or not task_id.strip():
            return False, "Не указан ID задачи для отмены."

        try:
            current_app.control.revoke(
                task_id.strip(),
                terminate=terminate,
                signal=signal,
            )
            logger.warning(
                "[CeleryMonitor] Отмена/Снятие задачи: task_id=%s, terminate=%s, signal=%s, admin=%s, ip=%s",
                task_id,
                terminate,
                signal,
                admin_username,
                ip_address,
            )
            return True, f"Команда прерывания задачи {task_id} успешно передана воркерам."

        except Exception as exc:
            logger.error(
                "[CeleryMonitor] Ошибка при отзыве задачи %s: %s (admin=%s)",
                task_id,
                exc,
                admin_username,
                exc_info=True,
            )
            return False, f"Не удалось отменить задачу: {str(exc)}"

    @classmethod
    def purge_queue(
        cls,
        queue_name: str = "celery",
        admin_username: str = "",
        ip_address: str = "",
    ) -> Tuple[bool, str, int]:
        """Очищает накопившиеся необработанные задачи в очереди брокера.

        Args:
            queue_name (str): Имя очереди для очистки (по умолчанию 'celery').
            admin_username (str): Логин администратора для аудита.
            ip_address (str): IP-адрес клиента.

        Returns:
            Tuple[bool, str, int]: Кортеж (успех, сообщение, количество удаленных задач).
        """
        try:
            purged_count = current_app.control.purge() or 0
            logger.warning(
                "[CeleryMonitor] Очистка очереди брокера (Purge): queue=%s, purged_count=%d, admin=%s, ip=%s",
                queue_name,
                purged_count,
                admin_username,
                ip_address,
            )
            return True, f"Очередь брокера успешно очищена. Сброшено задач: {purged_count}.", purged_count

        except Exception as exc:
            logger.error("[CeleryMonitor] Ошибка очистки очереди: %s", exc, exc_info=True)
            return False, f"Ошибка при очистке очереди: {str(exc)}", 0

    @classmethod
    def ping_workers(cls) -> Dict[str, Any]:
        """Выполняет пинг всех воркеров Celery с измерением времени отклика (RTT).

        Returns:
            Dict[str, Any]: Результат пинга по каждому воркеру с latency в миллисекундах.
        """
        t0 = time.time()
        results: Dict[str, Any] = {}

        try:
            ping_resp = current_app.control.ping(timeout=1.5) or []
            elapsed_ms = round((time.time() - t0) * 1000, 1)

            for item in ping_resp:
                if isinstance(item, dict):
                    for w_name, status in item.items():
                        results[w_name] = {
                            "status": "online" if status.get("ok") == "pong" else "unknown",
                            "latency_ms": elapsed_ms,
                        }
        except Exception as exc:
            logger.debug("[CeleryMonitor] Ошибка пинга воркеров: %s", exc)

        return {
            "workers_ping": results,
            "total_responded": len(results),
            "timestamp": timezone.now().strftime("%H:%M:%S"),
        }
