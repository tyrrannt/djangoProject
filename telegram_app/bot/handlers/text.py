# -*- coding: utf-8 -*-
"""Обработчик текстовых сообщений и Reply-кнопок Telegram-бота (aiogram 3.31.0).

Осуществляет маршрутизацию текстовых команд, нажатий постоянного меню,
автоматическую привязку по 36-значному УИН (UUID), поддержку корпоративного email
и информативные уведомления о планируемых этапах дорожной карты.
"""

import logging
import uuid
from email.utils import parseaddr
from typing import Optional

from aiogram import Router, types
from asgiref.sync import sync_to_async
from django.db.models import Q

from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from .help_router import handle_help_command
from .settings_router import handle_profile_command
from .tasks_router import handle_tasks_command
from ..keyboards import (
    article_keyboard,
    author_keyboard,
    get_main_menu,
    subscribe_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="text_router")


@router.message()
async def handle_text(message: types.Message) -> None:
    """Обрабатывает текстовые сообщения, Reply-кнопки меню, ввод УИН и email.

    Args:
        message: Входящее текстовое сообщение.
    """
    if not message.text:
        return

    text = message.text.strip()
    clean_lower = text.lower().strip()
    chat_id = message.chat.id
    logger.info("[TelegramBot:Text] Сообщение от %s: %s", chat_id, text)

    # 1. Проверка УИН (UUID формата 36 символов, например: c4a1b2c3-d4e5-f6a7-b8c9-d0e1f2a3b4c5)
    if len(text) == 36:
        try:
            uuid.UUID(text)
            user_obj: Optional[DataBaseUser] = await sync_to_async(
                DataBaseUser.objects.filter(
                    Q(person_ref_key=text) | Q(ref_key=text),
                    is_active=True,
                ).first
            )()

            if user_obj:
                user_obj.telegram_id = str(chat_id)
                await sync_to_async(user_obj.save)(update_fields=["telegram_id"])

                await sync_to_async(ChatID.objects.update_or_create)(
                    chat_id=str(chat_id),
                    defaults={
                        "ref_key": user_obj.person_ref_key or user_obj.ref_key,
                        "is_active": True,
                    },
                )
                logger.info(
                    "[TelegramBot:Text] Пользователь %s успешно привязал chat_id=%s по УИН",
                    user_obj.title,
                    chat_id,
                )
                await message.answer(
                    f"✅ <b>Аккаунт успешно привязан!</b>\n\n"
                    f"Сотрудник: <b>{user_obj.title}</b>\n"
                    f"Telegram ID: <code>{chat_id}</code>\n\n"
                    f"Теперь вам доступны разделы управления задачами и служебными уведомлениями.",
                    reply_markup=get_main_menu(is_authenticated=True),
                    parse_mode="HTML",
                )
            else:
                await message.answer(
                    "❌ <b>Пользователь не найден</b>\n\n"
                    "Сотрудник с указанным УИН не найден в базе данных корпоративного портала.\n"
                    "Пожалуйста, проверьте код в вашем профиле на портале и отправьте его снова.",
                    reply_markup=get_main_menu(is_authenticated=False),
                    parse_mode="HTML",
                )
            return
        except ValueError:
            pass

    # 2. Роутинг основных разделов меню
    if clean_lower in ["📋 мои задачи", "мои задачи", "задачи", "/tasks", "поручения"]:
        await handle_tasks_command(message)
        return

    if clean_lower in ["⚙️ профиль", "⚙️ профиль и уведомления", "профиль", "/profile", "настройки"]:
        await handle_profile_command(message)
        return

    if clean_lower in ["ℹ️ справка и помощь", "ℹ️ справка", "справка", "помощь", "/help"]:
        await handle_help_command(message)
        return

    if clean_lower in ["🔐 привязать аккаунт", "привязать аккаунт", "авторизоваться"]:
        await message.answer(
            "🔑 <b>Привязка аккаунта сотрудника</b>\n\n"
            "Для привязки аккаунта выполните следующие шаги:\n"
            "1. Войдите на корпоративный портал БАРКОЛ;\n"
            "2. Перейдите в свой личный профиль;\n"
            "3. Скопируйте строку <b>УИН</b> (уникальный GUID из 36 символов);\n"
            "4. Вставьте и отправьте скопированный УИН ответным сообщением сюда в чат.\n\n"
            f"Ваш Telegram ID: <code>{chat_id}</code>",
            reply_markup=get_main_menu(is_authenticated=False),
            parse_mode="HTML",
        )
        return

    # 3. Информативные подсказки по разделам будущих этапов дорожной карты
    if clean_lower in ["📑 служебные записки", "служебные записки", "/memos"]:
        await message.answer(
            "📑 <b>Раздел «Служебные записки»</b>\n\n"
            "Реестры «На визировании» и «Мои служебные записки» развертываются в рамках Этапа 2 "
            "модернизации бота.\n\n"
            "<i>Примечание: согласование служебных записок уже активно работает через входящие "
            "интерактивные уведомления с кнопками «Согласовать» и «Отклонить».</i>",
            parse_mode="HTML",
        )
        return

    if clean_lower in ["👥 справочник коллег", "справочник коллег", "контакты", "/contacts"]:
        await message.answer(
            "👥 <b>Раздел «Справочник коллег»</b>\n\n"
            "Интерактивный поиск контактов, телефонов и должностей сотрудников компании "
            "будет активирован в рамках Этапа 3 дорожной карты.",
            parse_mode="HTML",
        )
        return

    if clean_lower in ["✈️ летный план / мпд", "✈️ летный план", "летный план", "мпд", "/flight"]:
        await message.answer(
            "✈️ <b>Раздел «Летный план и МПД»</b>\n\n"
            "Информация по назначениям экипажей, воздушным судам и метеорологическим "
            "сводкам METAR/TAF будет подключена в рамках Этапа 4 дорожной карты.",
            parse_mode="HTML",
        )
        return

    if clean_lower in ["🎂 дни рождения", "дни рождения"]:
        await message.answer(
            "🎂 <b>Раздел «Дни рождения»</b>\n\n"
            "Календарь корпоративных дней рождения сотрудников подразделений "
            "подключается в рамках Этапа 3 дорожной карты.",
            parse_mode="HTML",
        )
        return

    # 4. Устаревшие кнопки для обратной совместимости
    if clean_lower in ["пользователи", "👥 пользователи", "/users", "пользователь"]:
        await message.answer(
            "👥 <b>Раздел «Пользователи»</b>\nВыберите интересующий вариант:",
            reply_markup=author_keyboard,
            parse_mode="HTML",
        )
        return

    if clean_lower in ["подписка", "🔔 подписка", "/subscribe", "подписки"]:
        await message.answer(
            "🔔 <b>Управление подпиской на уведомления</b>\nВыберите действие:",
            reply_markup=subscribe_keyboard,
            parse_mode="HTML",
        )
        return

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
            await message.answer(bot_message, parse_mode="HTML")
            return

    # 6. Fallback (неизвестное сообщение)
    user_linked = await sync_to_async(
        DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True).exists
    )()
    await message.answer(
        "Я вас не понял. Пожалуйста, воспользуйтесь кнопками меню ниже "
        "или отправьте команду <b>/help</b> для получения справки.",
        reply_markup=get_main_menu(is_authenticated=user_linked),
        parse_mode="HTML",
    )
