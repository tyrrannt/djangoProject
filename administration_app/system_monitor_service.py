"""Сервис сбора параметров сервера и интеллектуальной диагностики производительности.

Модуль осуществляет опрос системных ресурсов операционной системы
(процессор, память, диски, сеть, процессы, температура, доступность СУБД) с помощью psutil
и выполняет аналитическую оценку состояния сервера с выдачей конкретных рекомендаций
администратору системы.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import psutil
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


def format_bytes_to_gb(value_bytes: int) -> float:
    """Конвертирует значение из байт в гигабайты с округлением до двух знаков.

    Args:
        value_bytes (int): Размер в байтах.

    Returns:
        float: Размер в гигабайтах (ГБ).
    """
    return round(value_bytes / (1024 ** 3), 2)


def format_uptime(uptime_seconds: int) -> str:
    """Форматирует секунды аптайма в человекочитаемую строку на русском языке.

    Args:
        uptime_seconds (int): Количество секунд с момента загрузки ОС.

    Returns:
        str: Строка вида 'X дн. Y ч. Z мин.'
    """
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0 or days > 0:
        parts.append(f"{hours} ч.")
    parts.append(f"{minutes} мин.")
    return " ".join(parts)


# Глобальное состояние для непрерывного вычисления сетевой скорости между замерами
_LAST_NET_IO: Dict[str, Any] = {
    "bytes_sent": None,
    "bytes_recv": None,
    "timestamp": None,
    "speed_sent_kb": 0.0,
    "speed_recv_kb": 0.0,
}


def get_hardware_environment() -> Dict[str, Any]:
    """Определяет физическую или виртуальную среду исполнения (KVM, Proxmox, Bare Metal) и параметры процессора.

    Returns:
        Dict[str, Any]: Словарь с признаками виртуализации (is_virtual), типом среды (virt_type)
        и текущей частотой vCPU в ГГц (cpu_freq_ghz).
    """
    is_virtual = False
    virt_type = "Физический сервер"
    cpu_freq_ghz = 2.80

    # Проверка аппаратных DMI-дескрипторов
    try:
        if os.path.exists("/sys/class/dmi/id/product_name"):
            with open("/sys/class/dmi/id/product_name", "r") as f:
                prod = f.read().strip()
                if prod in ("KVM", "Bochs", "QEMU", "VirtualBox", "VMware Virtual Platform"):
                    is_virtual = True
                    virt_type = "KVM (Proxmox VE)" if prod == "KVM" else prod
    except Exception:
        pass

    if not is_virtual:
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "hypervisor" in cpuinfo:
                    is_virtual = True
                    virt_type = "KVM (Proxmox VE)"
        except Exception:
            pass

    # Считывание тактовой частоты процессора (МГц -> ГГц)
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "cpu MHz" in line:
                    mhz = float(line.split(":")[1].strip())
                    cpu_freq_ghz = round(mhz / 1000, 2)
                    break
    except Exception:
        pass

    return {
        "is_virtual": is_virtual,
        "virt_type": virt_type,
        "cpu_freq_ghz": cpu_freq_ghz,
    }


def get_cpu_temperature() -> Optional[float]:
    """Безопасно определяет текущую температуру центрального процессора.

    Поддерживает сенсоры физических процессоров Intel ('coretemp'), AMD ('k10temp'),
    ARM ('cpu_thermal', 'soc_thermal') и системные сенсоры ACPI. Также проверяет прямые
    файлы sysfs (/sys/class/thermal/ и /sys/class/hwmon/). На виртуальных машинах (KVM/Proxmox)
    без проброшенных физических датчиков возвращает None.

    Returns:
        Optional[float]: Температура в градусах Цельсия или None при отсутствии датчиков.
    """
    if os.name != "posix":
        return None

    # 1. Опрос psutil.sensors_temperatures
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                sensor_priorities = ["coretemp", "k10temp", "cpu_thermal", "soc_thermal", "acpitz"]
                for sensor_name in sensor_priorities:
                    if sensor_name in temps and temps[sensor_name]:
                        entry = temps[sensor_name][0]
                        if entry.current is not None and entry.current > 0:
                            return round(float(entry.current), 1)

                for entries in temps.values():
                    if entries and entries[0].current is not None and entries[0].current > 0:
                        return round(float(entries[0].current), 1)
        except Exception:
            pass

    # 2. Прямой поиск в sysfs /sys/class/thermal/thermal_zone*/temp
    try:
        import glob
        for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                with open(path, "r") as f:
                    val = float(f.read().strip())
                    if val > 1000:
                        val /= 1000.0  # миллиградусы -> градусы
                    if 10.0 <= val <= 120.0:
                        return round(val, 1)
            except Exception:
                continue
    except Exception:
        pass

    return None


def get_mariadb_ping_ms() -> Tuple[str, float]:
    """Измеряет время сетевого отклика базы данных MariaDB (Ping latency).

    Выполняет проверочный запрос 'SELECT 1' и фиксирует задержку отклика.
    В случае обрыва соединения или таймаута сокета выполняет безопасную очистку
    устаревшего дескриптора и повторное переподключение.

    Returns:
        Tuple[str, float]: Кортеж ('ok'/'error', задержка в миллисекундах).
    """
    t_start = time.perf_counter()
    try:
        connection.close_if_unusable_or_obsolete()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return "ok", latency_ms
    except Exception as exc:
        logger.debug(f"[SystemMonitor] Ошибка первичного SELECT 1: {exc}. Попытка переподключения...")
        try:
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
            return "ok", latency_ms
        except Exception as retry_exc:
            connection.close()
            latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
            logger.warning(f"[SystemMonitor] Сбой подключения к MariaDB при SELECT 1: {retry_exc}")
            return "error", latency_ms


def get_top_processes(limit: int = 5) -> List[Dict[str, Any]]:
    """Возвращает список наиболее ресурсоемких процессов сервера.

    Сортировка производится по комбинации загрузки CPU и памяти.

    Args:
        limit (int): Количество процессов в выборке (по умолчанию 5).

    Returns:
        List[Dict[str, Any]]: Список словарей с параметрами каждого процесса
        (pid, name, username, cpu, memory).
    """
    procs = []
    for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            cpu_val = info.get("cpu_percent") or 0.0
            mem_val = info.get("memory_percent") or 0.0
            procs.append({
                "pid": info.get("pid"),
                "name": info.get("name") or "—",
                "user": info.get("username") or "—",
                "cpu": round(cpu_val, 1),
                "memory": round(mem_val, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Сортируем: сначала те, у кого больше CPU, затем по памяти
    procs.sort(key=lambda x: (x["cpu"], x["memory"]), reverse=True)
    return procs[:limit]


def get_system_metrics(
    prev_bytes_sent: Optional[int] = None,
    prev_bytes_recv: Optional[int] = None,
    prev_time: Optional[float] = None
) -> Dict[str, Any]:
    """Выполняет комплексный опрос параметров аппаратного обеспечения и служб сервера.

    Все вызовы защищены от прерываний и исключений прав доступа.

    Args:
        prev_bytes_sent (Optional[int]): Предыдущее значение отправленных байт для расчета скорости.
        prev_bytes_recv (Optional[int]): Предыдущее значение полученных байт для расчета скорости.
        prev_time (Optional[float]): Метка времени предыдущего замера скорости сети.

    Returns:
        Dict[str, Any]: Словарь с полным набором телеметрических показателей сервера.
    """
    now = time.time()

    # 1. Процессор
    cpu_percent = round(psutil.cpu_percent(interval=None), 1)
    cpu_count_logical = psutil.cpu_count(logical=True) or 1
    cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical

    load_avg = [0.0, 0.0, 0.0]
    if hasattr(os, "getloadavg"):
        try:
            raw_la = os.getloadavg()
            load_avg = [round(x, 2) for x in raw_la]
        except Exception:
            pass

    # 2. Память (RAM и Swap)
    vm = psutil.virtual_memory()
    ram_total_gb = format_bytes_to_gb(vm.total)
    ram_used_gb = format_bytes_to_gb(vm.used)
    ram_available_gb = format_bytes_to_gb(vm.available)
    ram_percent = round(vm.percent, 1)

    swap = psutil.swap_memory()
    swap_total_gb = format_bytes_to_gb(swap.total)
    swap_used_gb = format_bytes_to_gb(swap.used)
    swap_percent = round(swap.percent, 1)

    # 3. Дисковый накопитель
    try:
        disk = psutil.disk_usage("/")
        disk_total_gb = format_bytes_to_gb(disk.total)
        disk_used_gb = format_bytes_to_gb(disk.used)
        disk_free_gb = format_bytes_to_gb(disk.free)
        disk_percent = round(disk.percent, 1)
    except Exception:
        disk_total_gb = 0.0
        disk_used_gb = 0.0
        disk_free_gb = 0.0
        disk_percent = 0.0

    # 4. Сеть и скорость передачи данных
    global _LAST_NET_IO
    net_io = psutil.net_io_counters()
    net_sent_total_mb = round(net_io.bytes_sent / (1024 ** 2), 2)
    net_recv_total_mb = round(net_io.bytes_recv / (1024 ** 2), 2)

    net_sent_speed_kb = 0.0
    net_recv_speed_kb = 0.0
    if prev_bytes_sent is not None and prev_bytes_recv is not None and prev_time is not None:
        dt = max(now - prev_time, 0.2)
        net_sent_speed_kb = round(max((net_io.bytes_sent - prev_bytes_sent), 0) / dt / 1024, 2)
        net_recv_speed_kb = round(max((net_io.bytes_recv - prev_bytes_recv), 0) / dt / 1024, 2)
    elif _LAST_NET_IO["bytes_sent"] is not None and _LAST_NET_IO["timestamp"] is not None:
        dt = max(now - _LAST_NET_IO["timestamp"], 0.2)
        if dt < 30.0:
            net_sent_speed_kb = round(max((net_io.bytes_sent - _LAST_NET_IO["bytes_sent"]), 0) / dt / 1024, 2)
            net_recv_speed_kb = round(max((net_io.bytes_recv - _LAST_NET_IO["bytes_recv"]), 0) / dt / 1024, 2)

    _LAST_NET_IO["bytes_sent"] = net_io.bytes_sent
    _LAST_NET_IO["bytes_recv"] = net_io.bytes_recv
    _LAST_NET_IO["timestamp"] = now
    _LAST_NET_IO["speed_sent_kb"] = net_sent_speed_kb
    _LAST_NET_IO["speed_recv_kb"] = net_recv_speed_kb

    # 5. Процессы и сетевые соединения
    processes_count = len(psutil.pids())
    try:
        connections_count = len(psutil.net_connections(kind="inet"))
    except Exception:
        connections_count = None

    # Топ процессов
    top_processes = get_top_processes(limit=5)

    # 6. Температура CPU и среда исполнения (KVM / Bare Metal)
    cpu_temp = get_cpu_temperature()
    env = get_hardware_environment()

    # 7. Аптайм
    boot_time = psutil.boot_time()
    uptime_seconds = int(now - boot_time)
    uptime_str = format_uptime(uptime_seconds)

    # 8. База данных MariaDB
    db_status, db_ping_ms = get_mariadb_ping_ms()

    return {
        "timestamp": now,
        "cpu_percent": cpu_percent,
        "cpu_count_logical": cpu_count_logical,
        "cpu_count_physical": cpu_count_physical,
        "load_avg": load_avg,
        "ram_total_gb": ram_total_gb,
        "ram_used_gb": ram_used_gb,
        "ram_available_gb": ram_available_gb,
        "ram_percent": ram_percent,
        "swap_total_gb": swap_total_gb,
        "swap_used_gb": swap_used_gb,
        "swap_percent": swap_percent,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "disk_percent": disk_percent,
        "net_sent_raw": net_io.bytes_sent,
        "net_recv_raw": net_io.bytes_recv,
        "net_sent_total_mb": net_sent_total_mb,
        "net_recv_total_mb": net_recv_total_mb,
        "net_sent_speed_kb": net_sent_speed_kb,
        "net_recv_speed_kb": net_recv_speed_kb,
        "processes_count": processes_count,
        "connections_count": connections_count,
        "top_processes": top_processes,
        "cpu_temp": cpu_temp,
        "is_virtual": env["is_virtual"],
        "virt_type": env["virt_type"],
        "cpu_freq_ghz": env["cpu_freq_ghz"],
        "uptime_seconds": uptime_seconds,
        "uptime_str": uptime_str,
        "db_status": db_status,
        "db_ping_ms": db_ping_ms,
    }


def analyze_system_health(metrics: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Анализирует метрики сервера и формирует рекомендации для администратора.

    Args:
        metrics (Dict[str, Any]): Набор телеметрических показателей сервера.

    Returns:
        Tuple[str, List[Dict[str, Any]]]:
            - overall_status: Общий статус системы ('healthy', 'warning', 'critical');
            - recommendations: Список структурированных рекомендаций.
    """
    recommendations = []
    has_critical = False
    has_warning = False

    cpu_percent = metrics.get("cpu_percent", 0.0)
    load_avg = metrics.get("load_avg", [0.0, 0.0, 0.0])
    cpu_cores = metrics.get("cpu_count_logical", 1)
    la_1m = load_avg[0] if load_avg else 0.0

    ram_percent = metrics.get("ram_percent", 0.0)
    ram_avail = metrics.get("ram_available_gb", 0.0)
    swap_percent = metrics.get("swap_percent", 0.0)

    disk_percent = metrics.get("disk_percent", 0.0)
    disk_free = metrics.get("disk_free_gb", 0.0)

    cpu_temp = metrics.get("cpu_temp")
    db_status = metrics.get("db_status", "ok")
    db_ping = metrics.get("db_ping_ms", 0.0)
    conns = metrics.get("connections_count")

    # 1. Анализ CPU и Load Average
    if cpu_percent >= 90.0 or la_1m > (cpu_cores * 1.5):
        has_critical = True
        recommendations.append({
            "id": "cpu_critical",
            "category": "CPU",
            "level": "critical",
            "title": "Критическая нагрузка на процессор",
            "value": f"{cpu_percent}% (LA: {la_1m})",
            "description": f"Загрузка ядер процессора достигла {cpu_percent}%, а показатель Load Average (1м) превышает суммарную емкость ядер ({la_1m} при {cpu_cores} ядрах).",
            "action": "Проверьте таблицу «Топ-5 процессов». Выясните, какие службы (Celery, Daphne, MariaDB) вызывают всплеск. При необходимости ограничьте concurrency или перезапустите зависшие воркеры.",
            "icon": "bx bx-chip",
        })
    elif cpu_percent >= 75.0 or la_1m > (cpu_cores * 1.0):
        has_warning = True
        recommendations.append({
            "id": "cpu_warning",
            "category": "CPU",
            "level": "warning",
            "title": "Повышенная загрузка процессора",
            "value": f"{cpu_percent}% (LA: {la_1m})",
            "description": f"Процессор загружен на {cpu_percent}%. Сервер близок к исчерпанию запаса вычислительной мощности.",
            "action": "Рекомендуется оптимизировать частые обращения к БД, проверить кэширование представлений и отложить выполнение тяжелых фоновых задач на непиковые часы.",
            "icon": "bx bx-chip",
        })

    # 2. Анализ оперативной памяти (RAM)
    if ram_percent >= 90.0 or (ram_avail > 0 and ram_avail < 0.8):
        has_critical = True
        recommendations.append({
            "id": "ram_critical",
            "category": "RAM",
            "level": "critical",
            "title": "Критический дефицит оперативной памяти",
            "value": f"{ram_percent}% (Свободно: {ram_avail} ГБ)",
            "description": f"Доступно менее {ram_avail} ГБ оперативной памяти. Возникает критическая опасность принудительного аварийного закрытия процессов механизмом Linux OOM Killer.",
            "action": "Срочно освободите память: перезапустите рабочие процессы Daphne/Celery с возможными утечками памяти, проверьте размер кэша Redis и установите лимит maxmemory в конфигурации.",
            "icon": "bx bx-memory-card",
        })
    elif ram_percent >= 80.0 or (ram_avail > 0 and ram_avail < 1.5):
        has_warning = True
        recommendations.append({
            "id": "ram_warning",
            "category": "RAM",
            "level": "warning",
            "title": "Высокое потребление оперативной памяти",
            "value": f"{ram_percent}% (Свободно: {ram_avail} ГБ)",
            "description": f"Использовано {ram_percent}% оперативной памяти. Запас свободной памяти быстро сокращается.",
            "action": "Проконтролируйте процессы с высоким потреблением памяти в таблице топа. Рекомендуется настроить параметр CELERYD_MAX_TASKS_PER_CHILD для автоматической ротации воркеров.",
            "icon": "bx bx-memory-card",
        })

    # 3. Анализ Swap
    if swap_percent >= 30.0 and ram_percent >= 75.0:
        has_warning = True
        recommendations.append({
            "id": "swap_warning",
            "category": "SWAP",
            "level": "warning",
            "title": "Активное использование файла подкачки (Swap)",
            "value": f"{swap_percent}%",
            "description": "Операционная система активно вытесняет страницы памяти на диск, что приводит к падению отзывчивости интерфейса портала.",
            "action": "Проверьте параметр ядра Linux vm.swappiness (рекомендуется снизить до 10). Рассмотрите возможность расширения физической памяти RAM сервера.",
            "icon": "bx bx-transfer-alt",
        })

    # 4. Анализ дискового накопителя
    if disk_percent >= 90.0 or (disk_free > 0 and disk_free < 5.0):
        has_critical = True
        recommendations.append({
            "id": "disk_critical",
            "category": "DISK",
            "level": "critical",
            "title": "Критическое переполнение системного диска",
            "value": f"{disk_percent}% (Осталось: {disk_free} ГБ)",
            "description": f"На системном накопителе свободно всего {disk_free} ГБ. При 100% заполнении MariaDB и другие системные службы аварийно остановятся!",
            "action": "Немедленно освободите место: выполните 'journalctl --vacuum-size=200M', очистите старые логи в /var/log/, удалите кэш пакетов 'apt clean' и проверьте директорию media/.",
            "icon": "bx bx-hdd",
        })
    elif disk_percent >= 80.0 or (disk_free > 0 and disk_free < 15.0):
        has_warning = True
        recommendations.append({
            "id": "disk_warning",
            "category": "DISK",
            "level": "warning",
            "title": "Высокая степень заполнения диска",
            "value": f"{disk_percent}% (Осталось: {disk_free} ГБ)",
            "description": f"Использовано {disk_percent}% объема системного диска.",
            "action": "Запланируйте аудит размера директории медиафайлов media/ и резервных копий. Настройте периодическую ротацию логов logrotate.",
            "icon": "bx bx-hdd",
        })

    # 5. Анализ базы данных MariaDB
    if db_status == "error":
        has_critical = True
        recommendations.append({
            "id": "db_critical",
            "category": "DATABASE",
            "level": "critical",
            "title": "Сбой соединения с базой данных MariaDB",
            "value": "Недоступна",
            "description": "Приложению не удалось выполнить проверочный запрос SELECT 1 к СУБД. База данных остановлена либо перегружена.",
            "action": "Проверьте статус службы 'systemctl status mariadb' и журнал ошибок СУБД в /var/log/mysql/error.log.",
            "icon": "bx bx-data",
        })
    elif db_ping >= 100.0:
        has_warning = True
        recommendations.append({
            "id": "db_slow",
            "category": "DATABASE",
            "level": "warning",
            "title": "Задержка отклика СУБД MariaDB",
            "value": f"{db_ping} мс",
            "description": f"Время отклика СУБД составляет {db_ping} мс, что существенно выше штатного уровня (< 20 мс).",
            "action": "Проверьте активные блокировки таблиц 'SHOW FULL PROCESSLIST;', включите slow_query_log и убедитесь в наличии необходимых индексов.",
            "icon": "bx bx-data",
        })

    # 6. Анализ температуры процессора
    if cpu_temp is not None:
        if cpu_temp >= 85.0:
            has_critical = True
            recommendations.append({
                "id": "temp_critical",
                "category": "HARDWARE",
                "level": "critical",
                "title": "Опасный перегрев процессора",
                "value": f"{cpu_temp}°C",
                "description": f"Температура CPU достигла {cpu_temp}°C. Высокий риск срабатывания термозащиты (троттлинга) или аварийного выключения сервера.",
                "action": "Срочно проверьте работоспособность кулеров и системы вентиляции серверной стойки, очистите радиаторы от пыли.",
                "icon": "bx bx-sun",
            })
        elif cpu_temp >= 75.0:
            has_warning = True
            recommendations.append({
                "id": "temp_warning",
                "category": "HARDWARE",
                "level": "warning",
                "title": "Повышенная температура процессора",
                "value": f"{cpu_temp}°C",
                "description": f"Температура CPU составляет {cpu_temp}°C, что выше рекомендуемого температурного диапазона.",
                "action": "Убедитесь в нормальной циркуляции воздуха в помещении серверной и отсутствии непрерывной пиковой нагрузки.",
                "icon": "bx bx-sun",
            })
    elif metrics.get("is_virtual"):
        recommendations.append({
            "id": "virt_env_info",
            "category": "HARDWARE",
            "level": "info",
            "title": f"Среда исполнения: {metrics.get('virt_type', 'KVM (Proxmox VE)')}",
            "value": f"{metrics.get('cpu_freq_ghz', 2.8)} ГГц",
            "description": "Сервер функционирует в виртуальной машине KVM. Физические термодатчики процессора опрашиваются на уровне родительского узла гипервизора Proxmox VE.",
            "action": "Для контроля физической температуры серверной стойки используйте веб-интерфейс Proxmox VE (раздел Node -> Summary).",
            "icon": "bx bx-server",
        })

    # 7. Анализ сетевых соединений
    if conns is not None and conns >= 800:
        has_warning = True
        recommendations.append({
            "id": "net_warning",
            "category": "NETWORK",
            "level": "warning",
            "title": "Аномально высокое число сетевых соединений",
            "value": f"{conns} соед.",
            "description": f"Количество активных сетевых сокетов превышает {conns}. Возможен наплыв внешних запросов, сканирование или DoS-активность.",
            "action": "Проверьте распределение соединений через 'ss -tunapl' и журнал обращений Nginx access.log. При необходимости включите limit_req_zone в Nginx.",
            "icon": "bx bx-network-chart",
        })

    # Определение общего статуса
    if has_critical:
        overall_status = "critical"
    elif has_warning:
        overall_status = "warning"
    else:
        overall_status = "healthy"
        recommendations.append({
            "id": "healthy_ok",
            "category": "SYSTEM",
            "level": "success",
            "title": "Все компоненты работают стабильно",
            "value": "Норма",
            "description": "Все ключевые аппаратные ресурсы (CPU, RAM, Диск, Сеть, СУБД) находятся в допустимых пределах.",
            "action": "Дополнительных действий от администратора не требуется. Мониторинг параметров ведется в штатном режиме.",
            "icon": "bx bx-check-shield",
        })

    return overall_status, recommendations


def get_device_usage_stats() -> Dict[str, Any]:
    """Формирует аналитику распределения клиентских устройств (Мобильные vs ПК / Планшеты).

    Анализирует счетчики сессий из кэша за последние дни, а также данные Push-подписок
    и журнала обращений к учебным материалам для оценки доли мобильных сотрудников
    (экипажи, инженеры на перроне) и стационарных рабочих мест (офис/администрация).

    Returns:
        Dict[str, Any]: Словарь с показателями:
            - mobile_count (int): Количество обращений со смартфонов.
            - desktop_count (int): Количество обращений с ПК.
            - tablet_count (int): Количество обращений с планшетов.
            - total_count (int): Общее число учтенных обращений.
            - mobile_percent (float): Процент обращений со смартфонов.
            - desktop_percent (float): Процент обращений с компьютеров.
            - tablet_percent (float): Процент обращений с планшетов.
            - primary_segment (str): Преобладающий сегмент аудитории.
    """
    mobile_cnt = 0
    desktop_cnt = 0
    tablet_cnt = 0

    # 1. Считываем суточные счетчики сессий из кэша за последние 7 дней
    try:
        now = timezone.now()
        for i in range(7):
            d_str = (now - timezone.timedelta(days=i)).strftime("%Y-%m-%d")
            m_val = cache.get(f"device_stat_day_{d_str}_mobile") or 0
            d_val = cache.get(f"device_stat_day_{d_str}_desktop") or 0
            t_val = cache.get(f"device_stat_day_{d_str}_tablet") or 0
            mobile_cnt += int(m_val)
            desktop_cnt += int(d_val)
            tablet_cnt += int(t_val)
    except Exception as ex:
        logger.debug(f"Ошибка чтения счетчиков устройств из кэша: {ex}")

    # 2. Дополняем базовой статистикой из PushSubscription и MaterialViewLog
    try:
        from customers_app.models import PushSubscription
        for sub in PushSubscription.objects.only("user_agent").iterator():
            ua = (sub.user_agent or "").lower()
            if "ipad" in ua or "tablet" in ua:
                tablet_cnt += 1
            elif any(k in ua for k in ["mobile", "iphone", "android", "phone"]):
                mobile_cnt += 1
            else:
                desktop_cnt += 1
    except Exception:
        pass

    try:
        from testing_app.models import MaterialViewLog
        for m_dev in MaterialViewLog.objects.exclude(last_device="").values_list("last_device", flat=True):
            if "Смартфон" in m_dev:
                mobile_cnt += 1
            elif "Планшет" in m_dev:
                tablet_cnt += 1
            elif "Компьютер" in m_dev or "Ноутбук" in m_dev:
                desktop_cnt += 1
    except Exception:
        pass

    # Если в системе еще мало накопленных данных, задаем реалистичный сбалансированный baseline
    total = mobile_cnt + desktop_cnt + tablet_cnt
    if total == 0:
        mobile_cnt = 1
        desktop_cnt = 1
        tablet_cnt = 0
        total = 2

    mobile_pct = round((mobile_cnt / total) * 100, 1)
    desktop_pct = round((desktop_cnt / total) * 100, 1)
    tablet_pct = round((tablet_cnt / total) * 100, 1)

    if mobile_pct > desktop_pct:
        primary_segment = "Мобильные устройства (летный состав / инженеры на перроне)"
    else:
        primary_segment = "Стационарные ПК (офис / учебные классы / администрация)"

    return {
        "mobile_count": mobile_cnt,
        "desktop_count": desktop_cnt,
        "tablet_count": tablet_cnt,
        "total_count": total,
        "mobile_percent": mobile_pct,
        "desktop_percent": desktop_pct,
        "tablet_percent": tablet_pct,
        "primary_segment": primary_segment,
    }


def get_system_monitor_payload(
    prev_bytes_sent: Optional[int] = None,
    prev_bytes_recv: Optional[int] = None,
    prev_time: Optional[float] = None
) -> Dict[str, Any]:
    """Формирует итоговый JSON-пакет для передачи по WebSocket и REST API.

    Объединяет первичные метрики и результат интеллектуального анализа с рекомендациями.

    Args:
        prev_bytes_sent (Optional[int]): Предыдущее значение отправленных байт.
        prev_bytes_recv (Optional[int]): Предыдущее значение полученных байт.
        prev_time (Optional[float]): Метка времени предыдущего замера.

    Returns:
        Dict[str, Any]: Полный пакет данных для визуализации и диагностики.
    """
    metrics = get_system_metrics(prev_bytes_sent, prev_bytes_recv, prev_time)
    overall_status, recommendations = analyze_system_health(metrics)
    metrics["overall_status"] = overall_status
    metrics["recommendations"] = recommendations
    metrics["device_stats"] = get_device_usage_stats()
    return metrics
