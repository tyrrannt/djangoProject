# -*- coding: utf-8 -*-
"""Основной модуль запуска асинхронного Telegram-бота компании БАРКОЛ (aiogram 3.31.0)."""

import asyncio
import datetime
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from asgiref.sync import sync_to_async
from django.conf import settings

from .handlers import (
    bpmemo,
    callbacks,
    help_router,
    inline,
    settings_router,
    start,
    tasks_router,
    text,
)
from ..models import TelegramNotification

logger = logging.getLogger(__name__)


def is_proxy_alive(proxy_url: str) -> bool:
    """Проверяет доступность прокси-сервера (открыт ли сокет).

    Args:
        proxy_url: URL прокси-сервера.

    Returns:
        bool: True, если сокет успешно ответил, иначе False.
    """
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (80 if parsed.scheme == "http" else 1080)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        res = sock.connect_ex((host, port))
        sock.close()
        return res == 0
    except Exception:
        return False


def create_bot() -> Bot:
    """Создает и настраивает экземпляр Bot с поддержкой wireproxy (TELEGRAM_PROXY).

    Returns:
        Bot: Инициализированный экземпляр aiogram Bot.
    """
    token = getattr(settings, "TELEGRAM_TOKEN", None) or getattr(settings, "API_TOKEN", None)
    proxy_url = getattr(settings, "TELEGRAM_PROXY", None)

    session: Optional[AiohttpSession] = None
    if proxy_url and str(proxy_url).strip():
        proxy_clean = str(proxy_url).strip()
        if is_proxy_alive(proxy_clean):
            logger.info("[TelegramBot:Aiogram] Запуск через туннель wireproxy: %s", proxy_clean)
            session = AiohttpSession(proxy=proxy_clean)
        else:
            logger.warning(
                "[TelegramBot:Aiogram] Прокси %s недоступен (порт закрыт). Автоматическое прямое подключение!",
                proxy_clean,
            )

    return Bot(
        token=str(token).strip(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Создает и регистрирует все роутеры диспетчера aiogram 3.

    Returns:
        Dispatcher: Настроенный диспетчер событий.
    """
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(help_router.router)
    dp.include_router(tasks_router.router)
    dp.include_router(settings_router.router)
    dp.include_router(bpmemo.router)
    dp.include_router(callbacks.router)
    dp.include_router(inline.router)
    dp.include_router(text.router)
    return dp


async def background_notifier(bot: Bot) -> None:
    """Периодический фоновый поллер очереди TelegramNotification для обратной совместимости.

    Args:
        bot: Экземпляр aiogram Bot для отправки сообщений.
    """
    logger.info("[TelegramBot] Фоновый поллер TelegramNotification активен.")
    while True:
        try:
            now = datetime.datetime.now().astimezone()
            today = now.date()

            notifications = await sync_to_async(list)(
                TelegramNotification.objects.filter(send_date=today, sending_counter__gt=0)
            )

            for note in notifications:
                respondents = await sync_to_async(list)(note.respondents.all())
                for chat in respondents:
                    try:
                        text_msg = f"<b>{note.message}</b>"
                        if note.document_url:
                            text_msg += f"\n<a href='{note.document_url}'>Ссылка на документ</a>"
                        time_str = note.send_time.strftime("%H:%M") if note.send_time else ""
                        date_str = note.send_date.strftime("%d.%m.%Y") if note.send_date else ""
                        text_msg += f"\n\n<blockquote>Время: {date_str} {time_str}</blockquote>"

                        await bot.send_message(chat.chat_id, text_msg)
                        logger.info("[TelegramBot] Уведомление доставлено пользователю %s", chat.chat_id)
                    except Exception as send_err:
                        logger.error("[TelegramBot] Ошибка отправки пользователю %s: %s", chat.chat_id, send_err)

                note.sending_counter -= 1
                await sync_to_async(note.save)()

            await asyncio.sleep(60)

        except Exception as exc:
            logger.exception("[TelegramBot] Ошибка в background_notifier: %s", exc)
            await asyncio.sleep(60)


async def main() -> None:
    """Главная асинхронная корутина запуска поллинга бота."""
    logger.info("[TelegramBot] Инициализация aiogram 3.31.0...")
    bot = create_bot()
    dp = create_dispatcher()

    # Запуск фонового поллера очереди устаревших уведомлений
    asyncio.create_task(background_notifier(bot))

    try:
        logger.info("[TelegramBot] Сброс устаревшего вебхука Telegram перед поллингом...")
        await bot.delete_webhook(drop_pending_updates=True)

        # Регистрация системного меню команд Telegram
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Главное меню / Статус"),
                    BotCommand(command="tasks", description="Мои задачи и поручения"),
                    BotCommand(command="profile", description="Профиль и уведомления"),
                    BotCommand(command="help", description="Справка и команды"),
                ]
            )
            logger.info("[TelegramBot] Системные команды (/start, /tasks, /profile, /help) успешно зарегистрированы.")
        except Exception as cmd_err:
            logger.warning("[TelegramBot] Не удалось зарегистрировать команды set_my_commands: %s", cmd_err)

        logger.info("[TelegramBot] Бот успешно запущен в режиме polling.")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("[TelegramBot] Сессия бота корректно закрыта.")
