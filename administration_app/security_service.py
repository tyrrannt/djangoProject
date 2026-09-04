"""Сервис мониторинга безопасности, защиты от брутфорса и интеграции с Fail2ban.

Обеспечивает отслеживание неудачных попыток входа, контроль превышения лимитов (Rate Limiting),
фиксацию временных блокировок IP в кэше, опрос состояния службы Fail2ban на сервере
и возможность оперативной разблокировки IP-адресов администраторами из веб-интерфейса.
"""

import ipaddress
import logging
import os
import re
import shutil
import subprocess
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY_EVENTS = "security_monitor_recent_events"
CACHE_KEY_ACTIVE_LOCKS = "security_monitor_active_locks"
MAX_STORED_EVENTS = 50


def _is_public_ip(ip_str: str) -> bool:
    """Проверяет, является ли переданная строка публичным IP-адресом.

    Args:
        ip_str (str): Строка IP-адреса.

    Returns:
        bool: True, если адрес публичный (не локальный и не loopback).
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local)
    except (ValueError, TypeError):
        return False


def record_security_event(
    ip: str,
    username: str,
    event_type: str,
    attempts: int = 1,
    max_attempts: int = 5,
    details: str = ""
) -> None:
    """Фиксирует событие безопасности (попытка входа, блокировка, разблокировка) в кэше.

    Сохраняет метаданные инцидента в оперативной кольцевой очереди событий для
    отображения в журнале мониторинга сервера и инкрементирует суточные счетчики.

    Args:
        ip (str): IP-адрес клиента.
        username (str): Имя пользователя, под которым выполнялся вход.
        event_type (str): Тип события: 'failed', 'lock', 'blocked', 'success', 'unban'.
        attempts (int): Текущий номер попытки. По умолчанию 1.
        max_attempts (int): Максимальное количество попыток до блокировки. По умолчанию 5.
        details (str): Пояснительный текст или причина.
    """
    if not ip:
        return

    now = timezone.now()
    now_str = now.strftime("%d.%m.%Y %H:%M:%S")
    today_str = now.strftime("%Y-%m-%d")

    # Формируем метку и стилевой класс
    if event_type == "lock":
        status_label = "Блокировка 15 мин"
        status_class = "danger"
    elif event_type == "blocked":
        status_label = "Отклонен (заблокирован)"
        status_class = "danger"
    elif event_type == "unban":
        status_label = "Разблокирован"
        status_class = "success"
    elif event_type == "success":
        status_label = "Успешный вход"
        status_class = "info"
    else:
        status_label = f"Попытка {attempts}/{max_attempts}"
        status_class = "warning"

    event_item = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": now_str,
        "raw_time": now.isoformat(),
        "ip": ip,
        "is_public": _is_public_ip(ip),
        "username": username or "—",
        "event_type": event_type,
        "status_label": status_label,
        "status_class": status_class,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "details": details or status_label,
    }

    try:
        # 1. Обновляем кольцевой список недавних событий
        events: List[Dict[str, Any]] = cache.get(CACHE_KEY_EVENTS) or []
        events.insert(0, event_item)
        if len(events) > MAX_STORED_EVENTS:
            events = events[:MAX_STORED_EVENTS]
        cache.set(CACHE_KEY_EVENTS, events, timeout=86400 * 7)

        # 2. Инкремент суточных счетчиков
        if event_type in ("failed", "lock", "blocked"):
            cnt_key = f"sec_stat_{today_str}_failed"
            try:
                if cache.get(cnt_key) is None:
                    cache.set(cnt_key, 1, timeout=86400 * 7)
                else:
                    cache.incr(cnt_key)
            except Exception:
                pass

        if event_type == "lock":
            lock_cnt_key = f"sec_stat_{today_str}_locked"
            try:
                if cache.get(lock_cnt_key) is None:
                    cache.set(lock_cnt_key, 1, timeout=86400 * 7)
                else:
                    cache.incr(lock_cnt_key)
            except Exception:
                pass

            # Фиксируем в реестре активных блокировок
            locks: Dict[str, Dict[str, Any]] = cache.get(CACHE_KEY_ACTIVE_LOCKS) or {}
            locks[ip] = {
                "ip": ip,
                "is_public": _is_public_ip(ip),
                "username": username,
                "locked_at": now_str,
                "expires_at": (now + timezone.timedelta(minutes=15)).strftime("%d.%m.%Y %H:%M:%S"),
                "reason": details or "Превышен лимит 5 попыток ввода пароля",
            }
            cache.set(CACHE_KEY_ACTIVE_LOCKS, locks, timeout=900)

        elif event_type == "unban":
            locks: Dict[str, Dict[str, Any]] = cache.get(CACHE_KEY_ACTIVE_LOCKS) or {}
            if ip in locks:
                del locks[ip]
                cache.set(CACHE_KEY_ACTIVE_LOCKS, locks, timeout=900)

    except Exception as ex:
        logger.debug(f"Ошибка сохранения события безопасности: {ex}")


def get_fail2ban_status() -> Dict[str, Any]:
    """Проверяет состояние службы Fail2ban на сервере и считывает список заблокированных IP.

    Осуществляет безопасный вызов fail2ban-client status django-login с жестким таймаутом,
    перехватывая любые системные исключения при отсутствии утилиты или нехватке прав.

    Returns:
        Dict[str, Any]: Словарь со статусом:
            - is_installed (bool): Установлен ли пакет fail2ban в ОС.
            - is_active (bool): Запущен ли демон и активен ли jail.
            - status_text (str): Описание текущего состояния.
            - banned_count (int): Число заблокированных IP на уровне ОС.
            - banned_ips (List[str]): Список заблокированных IP.
    """
    f2b_bin = shutil.which("fail2ban-client")
    if not f2b_bin:
        return {
            "is_installed": False,
            "is_active": False,
            "status_text": "Не установлен (активна встроенная защита Django Rate Limit)",
            "banned_count": 0,
            "banned_ips": [],
        }

    try:
        res = subprocess.run(
            [f2b_bin, "status", "django-login"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0:
            out = res.stdout
            banned_count = 0
            banned_ips = []
            m_cnt = re.search(r"Currently banned:\s*(\d+)", out)
            if m_cnt:
                banned_count = int(m_cnt.group(1))
            m_ips = re.search(r"Banned IP list:\s*(.*)", out)
            if m_ips:
                ips_str = m_ips.group(1).strip()
                if ips_str:
                    banned_ips = [ip.strip() for ip in ips_str.split() if ip.strip()]
            return {
                "is_installed": True,
                "is_active": True,
                "status_text": "Активен (Jail: django-login)",
                "banned_count": banned_count,
                "banned_ips": banned_ips,
            }
        else:
            return {
                "is_installed": True,
                "is_active": False,
                "status_text": "Служба остановлена (активна встроенная защита Django)",
                "banned_count": 0,
                "banned_ips": [],
            }
    except Exception as ex:
        logger.debug(f"Проверка fail2ban-client завершилась с ошибкой: {ex}")
        return {
            "is_installed": True,
            "is_active": False,
            "status_text": "Встроенная защита Django Cache активна",
            "banned_count": 0,
            "banned_ips": [],
        }


def get_security_monitor_data() -> Dict[str, Any]:
    """Формирует сводный пакет показателей безопасности для дашборда мониторинга сервера.

    Объединяет информацию о состоянии службы Fail2ban, текущих блокировках в кэше
    и журнал последних инцидентов подбора паролей.

    Returns:
        Dict[str, Any]: Словарь параметров:
            - is_protection_active (bool): Флаг активности защиты.
            - fail2ban (Dict[str, Any]): Статус службы Fail2ban.
            - active_locks_count (int): Общее число заблокированных IP.
            - active_locks (List[Dict[str, Any]]): Список действующих блокировок.
            - failed_today_count (int): Неудачных попыток входа сегодня.
            - locked_today_count (int): Число сработавших блокировок за сегодня.
            - recent_events (List[Dict[str, Any]]): Список недавних инцидентов.
    """
    today_str = timezone.now().strftime("%Y-%m-%d")

    # 1. Запрос статуса Fail2ban
    f2b_info = get_fail2ban_status()

    # 2. Считывание активных блокировок в Django Cache
    active_locks_dict: Dict[str, Dict[str, Any]] = cache.get(CACHE_KEY_ACTIVE_LOCKS) or {}
    verified_locks = []

    for ip, lock_data in list(active_locks_dict.items()):
        # Проверяем, действительно ли ключ блокировки еще жив в кэше
        if cache.get(f"login_lock_{ip}") or ip in f2b_info.get("banned_ips", []):
            lock_item = dict(lock_data)
            lock_item["in_fail2ban"] = ip in f2b_info.get("banned_ips", [])
            verified_locks.append(lock_item)
        else:
            # Истек таймаут кэша — удаляем
            del active_locks_dict[ip]

    cache.set(CACHE_KEY_ACTIVE_LOCKS, active_locks_dict, timeout=900)

    # Добавляем IP из Fail2ban, если их нет в кэше
    for f_ip in f2b_info.get("banned_ips", []):
        if not any(l["ip"] == f_ip for l in verified_locks):
            verified_locks.append({
                "ip": f_ip,
                "is_public": _is_public_ip(f_ip),
                "username": "—",
                "locked_at": "Блокировка ОС",
                "expires_at": "Fail2ban Jail",
                "reason": "Заблокирован на уровне iptables (Fail2ban)",
                "in_fail2ban": True,
            })

    # 3. Суточные счетчики
    failed_today = int(cache.get(f"sec_stat_{today_str}_failed") or 0)
    locked_today = int(cache.get(f"sec_stat_{today_str}_locked") or 0)

    # 4. Список недавних событий
    events = cache.get(CACHE_KEY_EVENTS) or []
    # Обновляем признак is_locked для каждого события
    for ev in events:
        ev["is_locked"] = any(l["ip"] == ev["ip"] for l in verified_locks) or bool(cache.get(f"login_lock_{ev['ip']}"))

    return {
        "is_protection_active": True,
        "fail2ban": f2b_info,
        "active_locks_count": len(verified_locks),
        "active_locks": verified_locks,
        "failed_today_count": failed_today,
        "locked_today_count": locked_today,
        "recent_events": events[:20],
    }


def unban_ip_address(ip_address: str, admin_username: str = "Администратор") -> Tuple[bool, str]:
    """Снимает временную блокировку с IP-адреса в кэше Django и в правилах Fail2ban.

    Args:
        ip_address (str): IP-адрес для разблокировки.
        admin_username (str): Имя пользователя-администратора, инициировавшего операцию.

    Returns:
        Tuple[bool, str]: Кортеж (успех операции, сообщение для пользователя).
    """
    clean_ip = (ip_address or "").strip()
    if not clean_ip:
        return False, "Не указан IP-адрес для разблокировки."

    try:
        ipaddress.ip_address(clean_ip)
    except ValueError:
        return False, f"Некорректный формат IP-адреса: '{clean_ip}'"

    # 1. Удаляем блокировку и счетчик попыток из кэша Django
    cache.delete(f"login_lock_{clean_ip}")
    cache.delete(f"login_attempts_{clean_ip}")

    # 2. Очищаем из реестра активных блокировок
    locks: Dict[str, Dict[str, Any]] = cache.get(CACHE_KEY_ACTIVE_LOCKS) or {}
    if clean_ip in locks:
        del locks[clean_ip]
        cache.set(CACHE_KEY_ACTIVE_LOCKS, locks, timeout=900)

    # 3. Если Fail2ban запущен, выполняем unbanip
    f2b_bin = shutil.which("fail2ban-client")
    unbanned_f2b = False
    if f2b_bin:
        try:
            res = subprocess.run(
                [f2b_bin, "set", "django-login", "unbanip", clean_ip],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                unbanned_f2b = True
        except Exception as ex:
            logger.debug(f"Ошибка вызова unbanip в Fail2ban: {ex}")

    # 4. Фиксируем событие разблокировки
    details = f"Разблокирован администратором {admin_username}"
    if unbanned_f2b:
        details += " (снят бан в Fail2ban и Django Cache)"
    else:
        details += " (очищен кэш блокировки Django)"

    record_security_event(
        ip=clean_ip,
        username=admin_username,
        event_type="unban",
        attempts=0,
        max_attempts=5,
        details=details
    )
    logger.info(f"SECURITY: {details} для IP {clean_ip}")

    return True, f"IP-адрес {clean_ip} успешно разблокирован. {details}."
