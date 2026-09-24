# -*- coding: utf-8 -*-
"""Обработчик текстовых сообщений Telegram-бота компании БАРКОЛ (aiogram 3)."""

import logging
import uuid
from email.utils import parseaddr
from typing import Optional

from aiogram import Router, types
from asgiref.sync import sync_to_async

from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from ..keyboards import (
    article_keyboard,
    author_keyboard,
    main_menu,
    subscribe_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="text_router")


@router.message()
async def handle_text(message: types.Message) -> None:
    """Обрабатывает текстовые команды, нажатия Reply-кнопок, ввод УИН и email.

    Args:
        message: Входящее текстовое сообщение.
    """
    if not message.text:
        return

    text = message.text.strip()
    chat_id = message.chat.id
    logger.info("[TelegramBot] Текстовое сообщение от %s: %s", chat_id, text)

    # 1. Проверка УИН (UUID формата 36 символов, например: c4a1b2c3-d4e5-f6a7-b8c9-d0e1f2a3b4c5)
    if len(text) == 36:
        try:
            uuid.UUID(text)
            exists = await sync_to_async(DataBaseUser.objects.filter(person_ref_key=text).exists)()
            if exists:
                user_obj = await sync_to_async(DataBaseUser.objects.get)(person_ref_key=text)
                await sync_to_async(ChatID.objects.update_or_create)(
                    chat_id=chat_id,
                    ref_key=user_obj.person_ref_key,
                )
                user_obj.telegram_id = str(chat_id)
                await sync_to_async(user_obj.save)()
                logger.info("[TelegramBot] Пользователь %s привязал chat_id=%s по УИН", user_obj.title, chat_id)
                await message.answer(
                    f"✅ <b>Успешно!</b>\n\n"
                    f"Сотрудник: <b>{user_obj.title}</b>\n"
                    f"Telegram ID: <code>{chat_id}</code>\n\n"
                    f"Ваш профиль привязан к корпоративному порталу. Уведомления включены.",
                    reply_markup=main_menu,
                    parse_mode="HTML",
                )
            else:
                await message.answer(
                    "❌ Пользователь с таким УИН не найден в базе данных.\n"
                    "Проверьте правильность кода в профиле на портале.",
                    reply_markup=main_menu,
                )
        except ValueError:
            await message.answer(
                "❌ Некорректный формат УИН. Код должен быть в формате UUID (36 символов).\n"
                "Скопируйте его из своего профиля на портале.",
                reply_markup=main_menu,
            )
        return

    # 2. Кнопка «ПОЛЬЗОВАТЕЛИ»
    clean_lower = text.lower().strip()
    if clean_lower in ["пользователи", "👥 пользователи", "/users", "пользователь"]:
        await message.answer(
            "👥 <b>Раздел «Пользователи»</b>\nВыберите интересующий вариант:",
            reply_markup=author_keyboard,
            parse_mode="HTML",
        )
        return

    # 3. Кнопка «ПОДПИСКА»
    if clean_lower in ["подписка", "🔔 подписка", "/subscribe", "подписки"]:
        await message.answer(
            "🔔 <b>Управление подпиской на уведомления</b>\nВыберите действие:",
            reply_markup=subscribe_keyboard,
            parse_mode="HTML",
        )
        return

    # 4. Меню «СТАТЬИ»
    if clean_lower in ["статьи", "📚 статьи", "/articles", "статья"]:
        await message.answer(
            "📚 <b>База знаний и статьи</b>\nВыберите категорию:",
            reply_markup=article_keyboard,
            parse_mode="HTML",
        )
        return

    # 5. Проверка корпоративного email (@username@barkol.ru)
    if text.startswith("@") and "@" in text[1:]:
        check_email = parseaddr(text[1:])
        if check_email[1]:
            bot_message = (
                f"📧 Для подтверждения учётной записи перейдите по ссылке, "
                f"отправленной вам на корпоративный email <code>{check_email[1]}</code>."
            )
            await message.answer(bot_message, reply_markup=main_menu, parse_mode="HTML")
            return

    # 6. Fallback (неизвестное сообщение)
    await message.answer(
        "Я вас не понял. Пожалуйста, воспользуйтесь кнопками меню ниже "
        "или отправьте свой <b>УИН</b> из профиля портала для привязки аккаунта.",
        reply_markup=main_menu,
        parse_mode="HTML",
    )
