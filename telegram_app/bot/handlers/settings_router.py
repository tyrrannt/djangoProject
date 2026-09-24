# -*- coding: utf-8 -*-
"""Обработчик личного кабинета /profile и настроек уведомлений Telegram-бота (aiogram 3.31.0).

Предоставляет просмотр карточки сотрудника, интерактивную матрицу переключателей
уведомлений по категориям (задачи, СЗ, почта, дни рождения, полеты) и безопасную отвязку аккаунта.
"""

import logging
from typing import Optional, Tuple

from aiogram import F, Router, types
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from ..keyboards import (
    get_main_menu,
    get_notifications_keyboard,
    get_profile_keyboard,
    get_unlink_confirm_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="settings_router")


@sync_to_async
def get_user_profile_data(chat_id: int) -> Tuple[Optional[DataBaseUser], Optional[ChatID]]:
    """Извлекает связанного пользователя и объект подписки ChatID.

    Args:
        chat_id: Идентификатор чата Telegram.

    Returns:
        Tuple[Optional[DataBaseUser], Optional[ChatID]]: Кортеж (пользователь, объект_ChatID).
    """
    user = (
        DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True)
        .select_related("user_work_profile__job", "user_work_profile__divisions")
        .first()
    )
    chat_obj = ChatID.objects.filter(chat_id=str(chat_id)).first()
    return user, chat_obj


@sync_to_async
def unlink_user_account(chat_id: int) -> bool:
    """Выполняет безопасную отвязку Telegram-аккаунта сотрудника.

    Args:
        chat_id: Идентификатор чата Telegram.

    Returns:
        bool: True, если отвязка выполнена успешно, иначе False.
    """
    users = DataBaseUser.objects.filter(telegram_id=str(chat_id))
    for u in users:
        u.telegram_id = ""
        u.save(update_fields=["telegram_id"])

    chat_records = ChatID.objects.filter(chat_id=str(chat_id))
    for c in chat_records:
        c.is_active = False
        c.save(update_fields=["is_active"])

    return True


@sync_to_async
def toggle_chat_notification(chat_id: int, category: str) -> Optional[ChatID]:
    """Инвертирует булевый флаг категории уведомления для чата.

    Args:
        chat_id: Идентификатор чата Telegram.
        category: Ключ категории ('tasks', 'memos', 'birthdays', 'emails', 'flights').

    Returns:
        Optional[ChatID]: Обновленный экземпляр ChatID или None.
    """
    chat_obj, _ = ChatID.objects.get_or_create(chat_id=str(chat_id))
    field_map = {
        "tasks": "notify_tasks",
        "memos": "notify_memos",
        "birthdays": "notify_birthdays",
        "emails": "notify_emails",
        "flights": "notify_flights",
    }
    field_name = field_map.get(category)
    if field_name:
        current_val = getattr(chat_obj, field_name, True)
        setattr(chat_obj, field_name, not current_val)
        chat_obj.save(update_fields=[field_name])
    return chat_obj


def format_profile_text(user: Optional[DataBaseUser], chat_id: int) -> str:
    """Форматирует информационный текст карточки сотрудника в HTML.

    Args:
        user: Экземпляр пользователя DataBaseUser или None.
        chat_id: Идентификатор чата Telegram.

    Returns:
        str: Сформированный HTML-текст карточки.
    """
    if not user:
        return (
            "⚙️ <b>Профиль сотрудника</b>\n\n"
            f"Ваш Telegram ID: <code>{chat_id}</code>\n"
            "Статус: ⚠️ <b>Аккаунт не привязан к порталу</b>\n\n"
            "Для использования функций управления задачами и получения персонализированных "
            "уведомлений привяжите свой аккаунт, отправив <b>УИН</b> из профиля портала."
        )

    fio = user.title or f"{user.last_name} {user.first_name} {user.surname}".strip()
    job_name = "Не указана"
    div_name = "Не указано"
    int_phone = "-"

    if hasattr(user, "user_work_profile") and user.user_work_profile:
        wp = user.user_work_profile
        if wp.job:
            job_name = wp.job.name
        if wp.divisions:
            div_name = wp.divisions.name
        if wp.internal_phone:
            int_phone = wp.internal_phone

    email = user.email or "Не указан"
    personal_phone = user.personal_phone or "-"
    service_num = user.service_number or "-"

    return (
        f"⚙️ <b>Профиль сотрудника: {fio}</b>\n\n"
        f"🏢 <b>Подразделение:</b> {div_name}\n"
        f"💼 <b>Должность:</b> {job_name}\n"
        f"🔢 <b>Табельный номер:</b> <code>{service_num}</code>\n\n"
        f"📧 <b>Корп. почта:</b> <code>{email}</code>\n"
        f"📞 <b>Телефоны:</b> вн. <code>{int_phone}</code> | моб. <code>{personal_phone}</code>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{chat_id}</code>\n"
        f"Статус: 🟢 <b>Подключен к порталу БАРКОЛ</b>"
    )


@router.message(Command("profile", ignore_case=True))
@router.message(F.text.lower().in_(["⚙️ профиль", "⚙️ профиль и уведомления", "профиль", "/profile", "настройки"]))
async def handle_profile_command(message: types.Message) -> None:
    """Отображает профиль сотрудника и меню управления личным кабинетом.

    Args:
        message: Сообщение с командой /profile или нажатием Reply-кнопки.
    """
    chat_id = message.chat.id
    user, _ = await get_user_profile_data(chat_id)
    is_auth = user is not None

    text = format_profile_text(user, chat_id)
    await message.answer(
        text,
        reply_markup=get_profile_keyboard(is_authenticated=is_auth),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "profile_main")
async def handle_profile_main_callback(call: types.CallbackQuery) -> None:
    """Возвращает пользователя к главному экрану профиля.

    Args:
        call: Объект CallbackQuery.
    """
    await call.answer()
    chat_id = call.message.chat.id
    user, _ = await get_user_profile_data(chat_id)
    is_auth = user is not None

    text = format_profile_text(user, chat_id)
    if call.message:
        await call.message.edit_text(
            text,
            reply_markup=get_profile_keyboard(is_authenticated=is_auth),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "profile_notif")
async def handle_profile_notif_callback(call: types.CallbackQuery) -> None:
    """Отображает интерактивную матрицу персональных уведомлений.

    Args:
        call: Объект CallbackQuery.
    """
    await call.answer()
    chat_id = call.message.chat.id
    _, chat_obj = await get_user_profile_data(chat_id)
    if not chat_obj:
        chat_obj, _ = await sync_to_async(ChatID.objects.get_or_create)(chat_id=str(chat_id))

    notif_text = (
        "🔔 <b>Матрица персональных уведомлений</b>\n\n"
        "Нажмите на соответствующую категорию, чтобы включить или отключить "
        "получение мгновенных оповещений в Telegram:\n\n"
        "🟢 — Уведомления включены\n"
        "⚪ — Уведомления выключены"
    )
    if call.message:
        await call.message.edit_text(
            notif_text,
            reply_markup=get_notifications_keyboard(chat_obj),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("notif_toggle:"))
async def handle_notif_toggle_callback(call: types.CallbackQuery) -> None:
    """Переключает статус выбранной категории уведомлений.

    Args:
        call: Объект CallbackQuery с параметром категории.
    """
    category = call.data.split(":", 1)[1]
    chat_id = call.message.chat.id
    updated_chat = await toggle_chat_notification(chat_id, category)

    await call.answer("Настройки уведомлений обновлены!")
    if call.message and updated_chat:
        await call.message.edit_reply_markup(
            reply_markup=get_notifications_keyboard(updated_chat)
        )


@router.callback_query(F.data == "profile_unlink_ask")
async def handle_profile_unlink_ask(call: types.CallbackQuery) -> None:
    """Запрашивает подтверждение отвязки Telegram-аккаунта.

    Args:
        call: Объект CallbackQuery.
    """
    await call.answer()
    confirm_text = (
        "⚠️ <b>Внимание! Отвязка учетной записи</b>\n\n"
        "Вы уверены, что хотите отвязать этот Telegram-аккаунт от профиля сотрудника?\n\n"
        "После отвязки вы перестанете получать служебные уведомления, напоминания "
        "по задачам и не сможете согласовывать документы через бота."
    )
    if call.message:
        await call.message.edit_text(
            confirm_text,
            reply_markup=get_unlink_confirm_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "profile_unlink_confirm")
async def handle_profile_unlink_confirm(call: types.CallbackQuery) -> None:
    """Выполняет подтвержденную отвязку аккаунта и переключает главное меню.

    Args:
        call: Объект CallbackQuery.
    """
    chat_id = call.message.chat.id
    await unlink_user_account(chat_id)
    await call.answer("Аккаунт успешно отвязан!", show_alert=True)

    unlinked_text = (
        "🔓 <b>Аккаунт успешно отвязан!</b>\n\n"
        f"Ваш Telegram ID <code>{chat_id}</code> больше не связан с профилем на портале.\n"
        "При необходимости вы можете заново привязать аккаунт в любой момент."
    )
    if call.message:
        await call.message.edit_text(
            unlinked_text,
            reply_markup=get_profile_keyboard(is_authenticated=False),
            parse_mode="HTML",
        )
        # Отправляем обновленное гостевое Reply-меню
        await call.message.answer(
            "Главное меню переключено в гостевой режим:",
            reply_markup=get_main_menu(is_authenticated=False),
        )
