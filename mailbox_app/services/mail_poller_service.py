"""Сервис фонового серверного опроса корпоративных и персональных почтовых ящиков.

Осуществляет периодическую проверку непрочитанных писем на сервере IMAP (Kerio Connect),
актуализирует кэш счетчиков для веб-интерфейса и отправляет системные Web Push уведомления.
"""

import email
from email.utils import parseaddr
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from customers_app.services.push_service import send_user_push
from mailbox_app.models import MailAccount, Mailbox
from mailbox_app.services.imap_service import (
    ImapMailService,
    decode_str,
    invalidate_mailbox_cache,
)

logger = logging.getLogger(__name__)

# Таймаут хранения состояния поллера в кэше (7 дней)
POLLER_STATE_TIMEOUT_SEC = 60 * 60 * 24 * 7


def poll_single_mailbox(
    account: Any, is_corporate: bool = False
) -> Dict[str, Any]:
    """Выполняет опрос одного почтового ящика (MailAccount или Mailbox).

    Проверяет состояние папки INBOX по протоколу IMAP, сравнивает текущие
    UID непрочитанных писем с предыдущим сохраненным состоянием, при обнаружении
    новых писем обновляет кэш и рассылает Web Push уведомления.

    Args:
        account (MailAccount | Mailbox): Экземпляр почтового ящика.
        is_corporate (bool): True, если опрашивается общий/корпоративный ящик Mailbox.

    Returns:
        Dict[str, Any]: Результат проверки ящика (статус, число непрочитанных, новые письма, ошибки).
    """
    email_addr = getattr(account, "email", "") or ""
    email_clean = email_addr.strip().lower()
    mailbox_name = getattr(account, "name", email_addr) or email_addr

    if not email_clean:
        return {"email": email_addr, "status": "skipped", "reason": "empty_email"}

    password = account.get_password()
    if not password:
        return {"email": email_addr, "status": "skipped", "reason": "empty_password"}

    cooldown_key = f"mailbox_poller_cooldown_{email_clean}"
    if cache.get(cooldown_key):
        return {
            "email": email_clean,
            "status": "skipped",
            "reason": "error_cooldown_10m",
            "elapsed_ms": 0.0,
        }

    state_key = f"mailbox_poller_state_{email_clean}"
    prev_state: Optional[Dict[str, Any]] = cache.get(state_key)

    t0 = time.perf_counter()
    try:
        with ImapMailService(
            host=account.imap_host,
            port=account.imap_port,
            email_addr=account.email,
            password=password,
            use_ssl=account.imap_use_ssl,
        ) as imap_svc:
            if not imap_svc.client:
                return {
                    "email": email_clean,
                    "status": "error",
                    "error": "Не удалось инициализировать IMAP клиент",
                }

            # Открываем INBOX в режиме только для чтения
            sel_status, _ = imap_svc.client.select("INBOX", readonly=True)
            if sel_status != "OK":
                sel_status, _ = imap_svc.client.select('"INBOX"', readonly=True)
                if sel_status != "OK":
                    return {
                        "email": email_clean,
                        "status": "error",
                        "error": "Не удалось открыть папку INBOX",
                    }

            # Получаем все текущие UNSEEN UIDs
            s_status, s_data = imap_svc.client.search(None, "UNSEEN")
            current_unseen_uids: Set[int] = set()
            if s_status == "OK" and s_data and s_data[0]:
                for u in s_data[0].split():
                    if u and u != b"0":
                        try:
                            current_unseen_uids.add(int(u))
                        except ValueError:
                            pass

            unseen_count = len(current_unseen_uids)
            new_uids = set()
            latest_mail_info = None

            if prev_state is None:
                # Первичный запуск поллера для ящика: фиксируем базу без спама пушами
                logger.info(
                    f"[MailPoller] Первичная регистрация ящика {email_clean}: {unseen_count} непрочитанных писем."
                )
            else:
                prev_uids = set(prev_state.get("uids", []))
                new_uids = current_unseen_uids - prev_uids

                if new_uids:
                    logger.info(
                        f"[MailPoller] 🔥 Обнаружены новые письма для {email_clean}: {len(new_uids)} шт. UIDs: {new_uids}"
                    )
                    # Извлекаем заголовки самого свежего из новых писем
                    max_new_uid = max(new_uids)
                    try:
                        f_status, f_data = imap_svc.client.fetch(
                            str(max_new_uid),
                            "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
                        )
                        if f_status == "OK" and f_data:
                            raw_hdr = b""
                            for item in f_data:
                                if isinstance(item, tuple):
                                    raw_hdr = item[1]

                            msg_obj = email.message_from_bytes(raw_hdr)
                            from_val = decode_str(msg_obj.get("From", ""))
                            from_name, from_email = parseaddr(from_val)
                            from_name = from_name or from_email or "Новый отправитель"
                            subj_val = decode_str(msg_obj.get("Subject", "Без темы"))

                            # Формируем целевой URL
                            detail_url = reverse(
                                "mailbox_app:email_detail",
                                kwargs={"folder": "INBOX", "uid": max_new_uid},
                            )
                            if is_corporate and hasattr(account, "id"):
                                detail_url += f"?mailbox={account.id}"

                            latest_mail_info = {
                                "uid": max_new_uid,
                                "from_name": from_name,
                                "from_email": from_email,
                                "subject": subj_val,
                                "url": detail_url,
                            }

                            # Рассылаем Push-уведомления
                            push_title = (
                                f"✉️ [{mailbox_name}] {from_name}"
                                if is_corporate
                                else f"✉️ {from_name}"
                            )
                            if len(new_uids) > 1:
                                push_title += f" (+{len(new_uids) - 1})"

                            push_body = subj_val or "Новое входящее сообщение"

                            if is_corporate and hasattr(account, "users"):
                                # Рассылаем всем прикрепленным сотрудникам
                                for target_user in account.users.filter(is_active=True):
                                    send_user_push(
                                        user=target_user,
                                        title=push_title,
                                        body=push_body,
                                        url=detail_url,
                                    )
                            elif hasattr(account, "user") and account.user and account.user.is_active:
                                # Личный ящик сотрудника
                                send_user_push(
                                    user=account.user,
                                    title=push_title,
                                    body=push_body,
                                    url=detail_url,
                                )
                    except Exception as fetch_err:
                        logger.warning(
                            f"[MailPoller] Ошибка чтения заголовков нового письма UID={max_new_uid} для {email_clean}: {fetch_err}"
                        )

            # При обнаружении новых писем или изменении счетчика инвалидируем кэш сообщений и папок
            if new_uids or (prev_state and unseen_count != prev_state.get("unseen_count", 0)) or (prev_state is None and unseen_count > 0):
                invalidate_mailbox_cache(email_clean)


            # Сохраняем состояние поллера
            new_state = {
                "uids": sorted(list(current_unseen_uids)),
                "unseen_count": unseen_count,
                "last_checked": time.time(),
                "latest_mail": latest_mail_info,
            }
            cache.set(state_key, new_state, timeout=POLLER_STATE_TIMEOUT_SEC)

            # Обновляем кэш статуса для AJAX эндпоинта /mail/api/unread_count/
            status_cache_key = f"mailbox_unread_status_{email_clean}"
            cache.set(
                status_cache_key,
                {
                    "success": True,
                    "unread_count": unseen_count,
                    "has_new": bool(new_uids),
                    "latest": latest_mail_info,
                    "mailbox_email": account.email,
                    "mailbox_name": mailbox_name,
                    "response_time_ms": round((time.perf_counter() - t0) * 1000, 1),
                },
                timeout=20,
            )

            # Синхронизируем счетчик в кэше дерева папок
            folders_cache_key = f"mailbox_folders_{email_clean}"
            cached_folders = cache.get(folders_cache_key)
            if cached_folders and isinstance(cached_folders, list):
                updated = False
                for f in cached_folders:
                    if f.get("root_type") == "inbox":
                        if f.get("unseen") != unseen_count:
                            f["unseen"] = unseen_count
                            updated = True
                        break
                if updated:
                    cache.set(folders_cache_key, cached_folders, timeout=1800)

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            # Сбрасываем счетчик ошибок при успешном сеансе связи
            cache.delete(cooldown_key)
            cache.delete(f"mailbox_poller_fail_count_{email_clean}")
            return {
                "email": email_clean,
                "status": "ok",
                "unseen_count": unseen_count,
                "new_messages_count": len(new_uids),
                "elapsed_ms": elapsed_ms,
            }

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.warning(
            f"[MailPoller] Ошибка при фоновом опросе ящика {email_clean}: {exc}"
        )
        fail_count_key = f"mailbox_poller_fail_count_{email_clean}"
        fail_count = (cache.get(fail_count_key) or 0) + 1
        cache.set(fail_count_key, fail_count, timeout=900)
        if fail_count >= 2:
            cache.set(cooldown_key, True, timeout=600)
            logger.info(
                f"[MailPoller] Ящик {email_clean} временно исключен из частого опроса на 10 мин "
                f"из-за повторных ошибок IMAP ({fail_count})."
            )
        return {
            "email": email_clean,
            "status": "error",
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
        }


def poll_all_active_mailboxes(only_online_users: Optional[bool] = None) -> Dict[str, Any]:
    """Выполняет фоновый опрос почтовых ящиков корпоративной почты на наличие новых писем.

    По умолчанию опрашивает только те ящики, пользователи которых сейчас находятся в сети
    на портале (онлайн), что кардинально снижает нагрузку на сервер приложений,
    почтовый сервер Kerio Connect и устраняет задержки в очередях фоновых задач Celery.

    Args:
        only_online_users (Optional[bool]): Если True, проверяются только ящики пользователей в сети.
            Если None, значение берется из настройки settings.MAILBOX_POLL_ONLY_ONLINE_USERS (True).
            Если False, опрашиваются все активные ящики без исключения.

    Returns:
        Dict[str, Any]: Сводный отчет выполнения опроса (число обработанных ящиков, пропущенных,
            новых писем, время выполнения в мс, ошибки).
    """
    if only_online_users is None:
        filter_online = getattr(settings, "MAILBOX_POLL_ONLY_ONLINE_USERS", True)
    else:
        filter_online = bool(only_online_users)

    t_start = time.perf_counter()
    summary: Dict[str, Any] = {
        "processed": 0,
        "success": 0,
        "errors": 0,
        "skipped": 0,
        "skipped_offline": 0,
        "online_users_count": 0,
        "new_emails_total": 0,
        "details": [],
    }

    online_user_ids: Set[int] = set()
    if filter_online:
        try:
            from customers_app.consumers import get_online_user_ids
            online_user_ids = get_online_user_ids()
        except Exception as err:
            logger.warning("[MailPoller] Не удалось получить список пользователей онлайн: %s. Опрос всех ящиков.", err)
            online_user_ids = set()
            filter_online = False

    if filter_online:
        summary["online_users_count"] = len(online_user_ids)
        logger.info(
            f"[MailPoller] Запуск выборочного опроса (only_online=True). "
            f"Активных пользователей в сети: {len(online_user_ids)}."
        )

        if not online_user_ids:
            total_corp = Mailbox.objects.filter(is_active=True).count()
            total_pers = MailAccount.objects.filter(user__is_active=True).exclude(email="").count()
            summary["skipped_offline"] = total_corp + total_pers
            summary["total_time_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            logger.info(
                f"[MailPoller] На портале нет пользователей онлайн. "
                f"Опрос всех {total_corp + total_pers} ящиков пропущен (0 мс)."
            )
            return summary

    # 1. Корпоративные и ведомственные общие ящики
    if filter_online:
        # Опрашиваем корпоративные ящики, к которым прикреплен хотя бы один пользователь онлайн
        corp_mailboxes = Mailbox.objects.filter(
            is_active=True,
            users__id__in=online_user_ids,
        ).distinct()
        total_active_corp = Mailbox.objects.filter(is_active=True).count()
        skipped_corp_offline = max(0, total_active_corp - corp_mailboxes.count())
    else:
        corp_mailboxes = Mailbox.objects.filter(is_active=True)
        skipped_corp_offline = 0

    for mb in corp_mailboxes:
        res = poll_single_mailbox(mb, is_corporate=True)
        summary["processed"] += 1
        summary["details"].append(res)
        if res.get("status") == "ok":
            summary["success"] += 1
            summary["new_emails_total"] += res.get("new_messages_count", 0)
        elif res.get("status") == "skipped":
            summary["skipped"] += 1
        else:
            summary["errors"] += 1

    # 2. Персональные ящики активных сотрудников
    if filter_online:
        personal_accounts = (
            MailAccount.objects.filter(
                user__is_active=True,
                user_id__in=online_user_ids,
            )
            .select_related("user")
            .exclude(email="")
        )
        total_active_pers = MailAccount.objects.filter(user__is_active=True).exclude(email="").count()
        skipped_pers_offline = max(0, total_active_pers - personal_accounts.count())
    else:
        personal_accounts = (
            MailAccount.objects.filter(user__is_active=True)
            .select_related("user")
            .exclude(email="")
        )
        skipped_pers_offline = 0

    summary["skipped_offline"] = skipped_corp_offline + skipped_pers_offline

    for acc in personal_accounts:
        res = poll_single_mailbox(acc, is_corporate=False)
        summary["processed"] += 1
        summary["details"].append(res)
        if res.get("status") == "ok":
            summary["success"] += 1
            summary["new_emails_total"] += res.get("new_messages_count", 0)
        elif res.get("status") == "skipped":
            summary["skipped"] += 1
        else:
            summary["errors"] += 1

    total_time = round((time.perf_counter() - t_start) * 1000, 1)
    summary["total_time_ms"] = total_time
    logger.info(
        f"[MailPoller] Завершен опрос ящиков за {total_time} мс: "
        f"обработано={summary['processed']}, успех={summary['success']}, "
        f"пропущено_оффлайн={summary['skipped_offline']}, новых={summary['new_emails_total']}, "
        f"ошибок={summary['errors']}."
    )
    return summary
