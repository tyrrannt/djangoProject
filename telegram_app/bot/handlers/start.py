# -*- coding: utf-8 -*-
"""Обработчик команды /start Telegram-бота компании БАРКОЛ (aiogram 3)."""

import logging
import uuid
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from asgiref.sync import sync_to_async

from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from ..keyboards import main_menu

logger = logging.getLogger(__name__)

router = Router(name="start_router")


@router.message(CommandStart())
@router.message(Command("start", ignore_case=True))
async def start_command(message: types.Message) -> None:
    """Обрабатывает команду /start, регистрирует пользователя по deep-link и отправляет главное меню.

    Args:
        message: Сообщение от пользователя с командой /start.
    """
    chat_id = message.chat.id
    first_name = message.from_user.first_name if message.from_user else "пользователь"
    logger.info("[TelegramBot] Команда /start от чата %s (%s)", chat_id, first_name)

    # Проверка возможного deep link: /start <UUID>
    text_parts = (message.text or "").strip().split()
    if len(text_parts) > 1:
        param = text_parts[1].strip()
        if len(param) == 36:
            try:
                uuid.UUID(param)
                exists = await sync_to_async(DataBaseUser.objects.filter(person_ref_key=param).exists)()
                if exists:
                    user_obj = await sync_to_async(DataBaseUser.objects.get)(person_ref_key=param)
                    await sync_to_async(ChatID.objects.update_or_create)(
                        chat_id=chat_id,
                        ref_key=user_obj.person_ref_key,
                    )
                    user_obj.telegram_id = str(chat_id)
                    await sync_to_async(user_obj.save)()
                    logger.info("[TelegramBot] Пользователь %s успешно привязал аккаунт по deep link", user_obj.title)
                    await message.answer(
                        f"✅ Здравствуйте, <b>{user_obj.title}</b>!\n\n"
                        f"Ваш Telegram-аккаунт успешно привязан к профилю на корпоративном портале.\n"
                        f"Уведомления активированы!",
                        reply_markup=main_menu,
                        parse_mode="HTML",
                    )
                    return
            except ValueError:
                pass

    # Проверка текущего статуса привязки
    user_linked: Optional[DataBaseUser] = await sync_to_async(
        DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True).first
    )()

    if user_linked:
        greeting_text = (
            f"Здравствуйте, <b>{user_linked.title}</b>!\n\n"
            f"Ваш Telegram ID: <code>{chat_id}</code>\n"
            f"Статус: ✅ <b>Подключен к порталу БАРКОЛ</b>\n\n"
            f"Для работы воспользуйтесь меню ниже."
        )
    else:
        greeting_text = (
            f"Здравствуйте, <b>{first_name}</b>!\n\n"
            f"Ваш Telegram ID: <code>{chat_id}</code>\n"
            f"Статус: ⚠️ <b>Не привязан к профилю</b>\n\n"
            f"Для привязки аккаунта отправьте мне свой <b>УИН</b> (GUID из 36 символов) "
            f"из профиля сотрудника на портале, либо нажмите <b>ПОДПИСКА</b> в меню ниже."
        )

    await message.answer(
        greeting_text,
        reply_markup=main_menu,
        parse_mode="HTML",
    )
