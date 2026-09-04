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
        return {
            "email": email_clean,
            "status": "error",
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
        }


def poll_all_active_mailboxes() -> Dict[str, Any]:
    """Выполняет фоновый опрос всех активных почтовых ящиков корпоративной почты.

    Собирает все активные общие ящики (Mailbox) и персональные ящики сотрудников (MailAccount),
    выполняет поочередную проверку новых сообщений, рассылает уведомления и актуализирует кэш.

    Returns:
        Dict[str, Any]: Сводный отчет выполнения опроса (количество ящиков, новые письма, задержки, ошибки).
    """
    logger.info("[MailPoller] Запуск периодического фонового опроса всех активных ящиков.")
    t_start = time.perf_counter()
    summary: Dict[str, Any] = {
        "processed": 0,
        "success": 0,
        "errors": 0,
        "skipped": 0,
        "new_emails_total": 0,
        "details": [],
    }

    # 1. Корпоративные и ведомственные общие ящики
    corp_mailboxes = Mailbox.objects.filter(is_active=True)
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
    personal_accounts = (
        MailAccount.objects.filter(user__is_active=True)
        .select_related("user")
        .exclude(email="")
    )
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
        f"всего={summary['processed']}, успех={summary['success']}, новых={summary['new_emails_total']}, ошибок={summary['errors']}."
    )
    return summary
