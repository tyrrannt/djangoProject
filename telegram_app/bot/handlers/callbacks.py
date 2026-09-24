# -*- coding: utf-8 -*-
"""Обработчик общих Inline-кнопок (CallbackQuery) Telegram-бота компании БАРКОЛ (aiogram 3)."""

import logging
from typing import Optional

from aiogram import Router, types
from asgiref.sync import sync_to_async

from customers_app.models import DataBaseUser

logger = logging.getLogger(__name__)

router = Router(name="callbacks_router")


@router.callback_query()
async def process_callback(call: types.CallbackQuery) -> None:
    """Обрабатывает нажатия на общие inline-кнопки (подписка, проверка, количество).

    Args:
        call: Объект события обратного вызова (CallbackQuery).
    """
    data = call.data or ""
    chat_id = call.message.chat.id if call.message else call.from_user.id
    logger.info("[TelegramBot] Callback '%s' от чата %s (пользователь %s)", data, chat_id, call.from_user.id)

    # Вспомогательная функция отправки сообщения в чат
    async def _reply(text: str) -> None:
        if call.message and hasattr(call.message, "answer"):
            await call.message.answer(text, parse_mode="HTML")
        else:
            await call.bot.send_message(chat_id=call.from_user.id, text=text, parse_mode="HTML")

    try:
        if data == "ПОДПИСАТЬСЯ":
            await call.answer()
            await _reply(
                "🔑 <b>Привязка аккаунта к порталу БАРКОЛ</b>\n\n"
                "1. Войдите в свой профиль на корпоративном портале.\n"
                "2. Скопируйте ваш <b>УИН</b> (36-значный уникальный код в формате UUID).\n"
                "3. Отправьте скопированный УИН ответным сообщением в этот чат."
            )

        elif data == "ПРОВЕРИТЬ":
            await call.answer()
            user_obj: Optional[DataBaseUser] = await sync_to_async(
                DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True).first
            )()
            if user_obj:
                await _reply(
                    f"✅ <b>Подписка активна!</b>\n\n"
                    f"Сотрудник: <b>{user_obj.title}</b>\n"
                    f"Telegram ID: <code>{chat_id}</code>\n"
                    f"Вы успешно получаете все корпоративные уведомления."
                )
            else:
                await _reply(
                    f"⚠️ <b>Аккаунт не привязан!</b>\n\n"
                    f"Ваш Telegram ID <code>{chat_id}</code> еще не зарегистрирован в базе данных портала.\n\n"
                    f"Чтобы привязать аккаунт, отправьте мне свой <b>УИН</b> из личного кабинета."
                )

        elif data == "Количество":
            await call.answer()
            count = await sync_to_async(
                DataBaseUser.objects.exclude(telegram_id="").exclude(telegram_id__isnull=True).count
            )()
            await _reply(f"📊 Количество сотрудников компании с подключенным Telegram: <b>{count}</b>")

        else:
            await call.answer()
            logger.warning("[TelegramBot] Неизвестный callback_data: %s", data)

    except Exception as exc:
        logger.exception("[TelegramBot] Ошибка обработки callback %s: %s", data, exc)
        try:
            await call.answer("Произошла ошибка при обработке запроса. Попробуйте позже.", show_alert=True)
        except Exception:
            pass
