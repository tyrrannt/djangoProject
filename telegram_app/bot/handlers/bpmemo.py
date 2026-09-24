# -*- coding: utf-8 -*-
"""Обработчик интерактивных действий по служебным запискам в Telegram (aiogram 3)."""

import datetime
import logging
from typing import Optional

from aiogram import Router, types
from asgiref.sync import sync_to_async
from django.utils import timezone

from customers_app.models import DataBaseUser, HistoryChange
from hrdepartment_app.models import ApprovalOficialMemoProcess

logger = logging.getLogger(__name__)

router = Router(name="bpmemo_router")


@sync_to_async
def get_user_and_process(telegram_id: int, process_id: int):
    """Извлекает пользователя и процесс согласования по ID.

    Args:
        telegram_id: ID чата Telegram.
        process_id: Первичный ключ процесса ApprovalOficialMemoProcess.

    Returns:
        tuple: (user_obj, process_obj) или (None, None).
    """
    user_obj = DataBaseUser.objects.filter(telegram_id=str(telegram_id), is_active=True).first()
    process_obj = (
        ApprovalOficialMemoProcess.objects.filter(pk=process_id)
        .select_related("document", "person_agreement", "person_executor")
        .first()
    )
    return user_obj, process_obj


@sync_to_async
def approve_memo_process(process_id: int, user_obj: DataBaseUser) -> tuple[bool, str]:
    """Выполняет атомарное согласование служебной записки в базе данных.

    Args:
        process_id: ID процесса.
        user_obj: Пользователь, выполняющий действие.

    Returns:
        tuple[bool, str]: (успех, сообщение_об_ошибке_или_статусе).
    """
    process = (
        ApprovalOficialMemoProcess.objects.filter(pk=process_id)
        .select_related("document", "person_agreement", "person_executor")
        .first()
    )
    if not process:
        return False, "Процесс согласования не найден."

    if process.document_not_agreed:
        return False, "Данная служебная записка уже была согласована ранее."

    if process.cancellation:
        return False, "Служебная записка аннулирована, согласование невозможно."

    # Проверка прав: согласующее лицо, либо суперпользователь
    is_allowed = (
        process.person_agreement_id == user_obj.pk
        or user_obj.is_superuser
        or getattr(getattr(user_obj, "user_work_profile", None), "job", None)
        and user_obj.user_work_profile.job.right_to_approval
    )

    if not is_allowed:
        return False, "У вас нет прав на согласование данной служебной записки."

    # Устанавливаем статус согласования
    process.document_not_agreed = True
    process.person_agreement = user_obj
    process.save(update_fields=["document_not_agreed", "person_agreement"])

    if process.document:
        process.document.comments = "Документ согласован"
        process.document.save(update_fields=["comments"])

    # Запись в историю изменений
    try:
        now_str = timezone.now().strftime("%d.%m.%Y %H:%M")
        HistoryChange.objects.create(
            author=user_obj,
            body=f"<b>Согласовано через Telegram-бота</b> пользователем {user_obj.title} ({now_str})",
            content_object=process,
        )
    except Exception as hist_err:
        logger.warning("[TelegramBot:BPMemo] Ошибка записи в HistoryChange: %s", hist_err)

    # Запуск уведомлений следующего этапа через сервис
    try:
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService
        MemoNotificationService.dispatch_event(process.pk, "APPROVED")
    except Exception as notify_err:
        logger.warning("[TelegramBot:BPMemo] Ошибка запуска уведомлений APPROVED: %s", notify_err)

    return True, "Служебная записка успешно согласована!"


@sync_to_async
def reject_memo_process(process_id: int, user_obj: DataBaseUser, reason: str = "Отклонено в Telegram") -> tuple[bool, str]:
    """Фиксирует отклонение служебной записки руководителем.

    Args:
        process_id: ID процесса.
        user_obj: Пользователь.
        reason: Причина отклонения.

    Returns:
        tuple[bool, str]: (успех, сообщение).
    """
    process = ApprovalOficialMemoProcess.objects.filter(pk=process_id).select_related("document").first()
    if not process:
        return False, "Процесс не найден."

    if process.document:
        process.document.comments = f"Отклонено: {reason}"
        process.document.save(update_fields=["comments"])

    try:
        now_str = timezone.now().strftime("%d.%m.%Y %H:%M")
        HistoryChange.objects.create(
            author=user_obj,
            body=f"<b>Отклонено через Telegram-бота</b>: {reason} ({now_str})",
            content_object=process,
        )
    except Exception as hist_err:
        logger.warning("[TelegramBot:BPMemo] Ошибка истории при отклонении: %s", hist_err)

    try:
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService
        MemoNotificationService.dispatch_event(process.pk, "REJECTED")
    except Exception as notify_err:
        logger.warning("[TelegramBot:BPMemo] Ошибка уведомления REJECTED: %s", notify_err)

    return True, "Служебная записка отклонена."


@router.callback_query(lambda call: call.data and call.data.startswith("bpmemo_"))
async def handle_bpmemo_actions(call: types.CallbackQuery):
    """Обрабатывает нажатия на inline-кнопки согласования служебных записок."""
    parts = call.data.split(":")
    if len(parts) != 2:
        await call.answer("Некорректный формат данных кнопки.", show_alert=True)
        return

    action, process_id_str = parts[0], parts[1]
    try:
        process_id = int(process_id_str)
    except ValueError:
        await call.answer("Неверный ID документа.", show_alert=True)
        return

    user_obj, process_obj = await get_user_and_process(call.from_user.id, process_id)
    if not user_obj:
        await call.answer(
            "Ваш Telegram-аккаунт не привязан к профилю на корпоративном портале. Пройдите процедуру авторизации по УИН.",
            show_alert=True,
        )
        return

    if action == "bpmemo_approve":
        success, message = await approve_memo_process(process_id, user_obj)
        if success:
            await call.answer(message, show_alert=False)
            now_dt = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            original_text = call.message.html_text if hasattr(call.message, "html_text") else call.message.text
            updated_text = (
                f"{original_text}\n\n"
                f"✅ <b>СОГЛАСОВАНО через Telegram</b> ({now_dt})\n"
                f"<i>Согласующий: {user_obj.title}</i>"
            )
            try:
                await call.message.edit_text(updated_text, parse_mode="HTML", reply_markup=None)
            except Exception as edit_err:
                logger.debug("[TelegramBot] Не удалось отредактировать сообщение после согласования: %s", edit_err)
        else:
            await call.answer(message, show_alert=True)

    elif action == "bpmemo_reject":
        success, message = await reject_memo_process(process_id, user_obj)
        if success:
            await call.answer(message, show_alert=False)
            now_dt = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            original_text = call.message.html_text if hasattr(call.message, "html_text") else call.message.text
            updated_text = (
                f"{original_text}\n\n"
                f"❌ <b>ОТКЛОНЕНО через Telegram</b> ({now_dt})\n"
                f"<i>Руководитель: {user_obj.title}</i>"
            )
            try:
                await call.message.edit_text(updated_text, parse_mode="HTML", reply_markup=None)
            except Exception as edit_err:
                logger.debug("[TelegramBot] Не удалось отредактировать сообщение после отклонения: %s", edit_err)
        else:
            await call.answer(message, show_alert=True)
