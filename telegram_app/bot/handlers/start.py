# -*- coding: utf-8 -*-
"""Обработчик команды /start Telegram-бота компании БАРКОЛ (aiogram 3.31.0).

Реализует первичную авторизацию по deep link (/start <UUID>), валидацию привязки,
вывод статуса учетной записи и переключение адаптивного Reply-меню (сотрудник / гость).
"""

import logging
import uuid
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from asgiref.sync import sync_to_async
from django.db.models import Q

from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from ..keyboards import get_main_menu

logger = logging.getLogger(__name__)

router = Router(name="start_router")


@router.message(CommandStart())
@router.message(Command("start", ignore_case=True))
async def start_command(message: types.Message) -> None:
    """Обрабатывает команду /start, регистрирует пользователя по deep-link и отправляет главное меню.

    Args:
        message: Входящее сообщение от пользователя с командой /start.
    """
    chat_id = message.chat.id
    first_name = message.from_user.first_name if message.from_user else "пользователь"
    logger.info("[TelegramBot:Start] Команда /start от чата %s (%s)", chat_id, first_name)

    # 1. Проверка возможного deep link: /start <UUID>
    text_parts = (message.text or "").strip().split()
    if len(text_parts) > 1:
        param = text_parts[1].strip()
        if len(param) == 36:
            try:
                uuid.UUID(param)
                user_match = await sync_to_async(
                    DataBaseUser.objects.filter(
                        Q(person_ref_key=param) | Q(ref_key=param),
                        is_active=True,
                    ).first
                )()
                if user_match:
                    # Привязываем Telegram ID к пользователю и активируем ChatID
                    user_match.telegram_id = str(chat_id)
                    await sync_to_async(user_match.save)(update_fields=["telegram_id"])

                    chat_obj, _ = await sync_to_async(ChatID.objects.update_or_create)(
                        chat_id=str(chat_id),
                        defaults={
                            "ref_key": user_match.person_ref_key or user_match.ref_key,
                            "is_active": True,
                        },
                    )
                    logger.info(
                        "[TelegramBot:Start] Пользователь %s успешно привязал аккаунт по deep link (chat_id=%s)",
                        user_match.title,
                        chat_id,
                    )
                    success_msg = (
                        f"✅ Здравствуйте, <b>{user_match.title}</b>!\n\n"
                        f"Ваш Telegram-аккаунт успешно привязан к профилю на корпоративном портале.\n"
                        f"Уведомления активированы, меню переключено в рабочий режим!"
                    )
                    await message.answer(
                        success_msg,
                        reply_markup=get_main_menu(is_authenticated=True),
                        parse_mode="HTML",
                    )
                    return
            except ValueError:
                pass

    # 2. Проверка текущего статуса привязки
    user_linked: Optional[DataBaseUser] = await sync_to_async(
        DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True)
        .select_related("user_work_profile__job", "user_work_profile__divisions")
        .first
    )()

    if user_linked:
        job_title = ""
        if hasattr(user_linked, "user_work_profile") and user_linked.user_work_profile and user_linked.user_work_profile.job:
            job_title = f"\n💼 {user_linked.user_work_profile.job.name}"

        greeting_text = (
            f"Здравствуйте, <b>{user_linked.title}</b>!{job_title}\n\n"
            f"🆔 Ваш Telegram ID: <code>{chat_id}</code>\n"
            f"Статус: 🟢 <b>Подключен к порталу БАРКОЛ</b>\n\n"
            f"Используйте кнопки меню ниже или быстрые команды:\n"
            f"• <b>/tasks</b> — Мои задачи и поручения\n"
            f"• <b>/profile</b> — Профиль и настройка уведомлений\n"
            f"• <b>/help</b> — Инструкция и справка"
        )
        menu_markup = get_main_menu(is_authenticated=True)
    else:
        greeting_text = (
            f"Здравствуйте, <b>{first_name}</b>!\n\n"
            f"🆔 Ваш Telegram ID: <code>{chat_id}</code>\n"
            f"Статус: ⚠️ <b>Аккаунт не привязан к профилю</b>\n\n"
            f"Для привязки аккаунта отправьте мне свой <b>УИН</b> (GUID из 36 символов) "
            f"из личного кабинета на корпоративном портале или нажмите <b>🔐 Привязать аккаунт</b>."
        )
        menu_markup = get_main_menu(is_authenticated=False)

    await message.answer(
        greeting_text,
        reply_markup=menu_markup,
        parse_mode="HTML",
    )
