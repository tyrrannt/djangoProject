# -*- coding: utf-8 -*-
"""Обработчик команды /help и справочной системы Telegram-бота (aiogram 3.31.0).

Предоставляет пользователю структурированное руководство по возможностям бота,
доступным командам, порядку привязки аккаунта к порталу «Авиакомпания БАРКОЛ»
и правилам информационной безопасности.
"""

import logging
from typing import Optional

from aiogram import F, Router, types
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from customers_app.models import DataBaseUser
from ..keyboards import get_help_keyboard, get_main_menu

logger = logging.getLogger(__name__)

router = Router(name="help_router")


@router.message(Command("help", ignore_case=True))
@router.message(F.text.lower().in_(["ℹ️ справка и помощь", "ℹ️ справка", "справка", "помощь", "/help"]))
async def handle_help_command(message: types.Message) -> None:
    """Отображает структурированное руководство пользователя корпоративного бота.

    Args:
        message: Входящее сообщение от пользователя с командой /help или текстом кнопки.
    """
    chat_id = message.chat.id
    logger.info("[TelegramBot:Help] Запрос справки от chat_id=%s", chat_id)

    # Проверяем, привязан ли аккаунт
    user_linked: Optional[DataBaseUser] = await sync_to_async(
        DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True).first
    )()
    is_auth = user_linked is not None

    help_text = (
        "📖 <b>Справочник корпоративного бота «Авиакомпания БАРКОЛ»</b>\n\n"
        "Бот является персональным цифровым ассистентом сотрудника и обеспечивает "
        "оперативное информирование и выполнение производственных задач.\n\n"
        "🔹 <b>Основные команды бота:</b>\n"
        "• <b>/start</b> — Перезапуск бота, отображение Telegram ID и статуса привязки;\n"
        "• <b>/tasks</b> — Просмотр задач и поручений, смена статусов («В работу», «Завершить»);\n"
        "• <b>/profile</b> — Личный кабинет сотрудника, матрица уведомлений и отвязка аккаунта;\n"
        "• <b>/help</b> — Данное справочное руководство.\n\n"
        "🔹 <b>Как привязать профиль:</b>\n"
        "1. Откройте корпоративный портал в браузере и перейдите в свой профиль;\n"
        "2. Скопируйте ваш <b>УИН</b> (уникальный 36-значный идентификатор GUID);\n"
        "3. Отправьте его сообщением боту или запустите бота по ссылке из профиля.\n\n"
        "🔹 <b>Безопасность и уведомления:</b>\n"
        "• Бот защищен сквозной корпоративной авторизацией;\n"
        "• В разделе <b>/profile</b> можно выборочно настраивать категории уведомлений "
        "(задачи, служебные записки, дни рождения, корпоративная почта);\n"
        "• При утере телефона или необходимости смены аккаунта воспользуйтесь кнопкой отвязки.\n\n"
        "📞 <i>Техническая поддержка IT-отдела:</i> @barkol_support"
    )

    await message.answer(
        help_text,
        reply_markup=get_help_keyboard(is_authenticated=is_auth),
        parse_mode="HTML",
    )
