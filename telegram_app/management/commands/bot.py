# -*- coding: utf-8 -*-
"""Команда управления Django для запуска асинхронного Telegram-бота компании БАРКОЛ (aiogram 3.31.0)."""

import asyncio
import datetime
import logging
from typing import List

from django.core.management import BaseCommand
from django.db.models import Q
from dateutil.relativedelta import relativedelta

from telegram_app.bot.main import main
from telegram_app.models import TelegramNotification
from telegram_app.services.telegram_service import UniversalTelegramService

logger = logging.getLogger(__name__)


def send_message_tg() -> List[str]:
    """Синхронная функция обработки очереди TelegramNotification для обратной совместимости.

    Использует UniversalTelegramService для гарантированной маршрутизации запросов
    через настроенный туннель wireproxy (TELEGRAM_PROXY).

    Returns:
        List[str]: Список информационных сообщений о результатах отправки.
    """
    time_list = [0, 15, 5]
    dt = datetime.datetime.now()
    result: List[str] = []

    try:
        notify_list = TelegramNotification.objects.filter(
            Q(send_time__hour=dt.hour) & Q(send_time__minute=dt.minute) & Q(send_date=dt.date())
        )
        for item in notify_list:
            for chat in item.respondents.all():
                if item.sending_counter > 0:
                    text_content = f"<b>{item.message}</b>"
                    if item.document_url:
                        text_content += f"\n<a href='{item.document_url}'>Ссылка на документ</a>"
                    text_content += (
                        f"\n<blockquote>Время отправки: "
                        f"{item.send_date.strftime('%d.%m.%Y') if item.send_date else ''} "
                        f"{item.send_time.strftime('%H:%M') if item.send_time else ''}</blockquote>"
                    )

                    success, err = UniversalTelegramService.send_message_sync(
                        chat_id=chat.chat_id,
                        text=text_content,
                        parse_mode="HTML",
                    )
                    if success:
                        msg_log = f"Сообщение для {chat.chat_id} отправлено: {item.message}"
                        result.append(msg_log)
                        logger.info("[TelegramBot:Legacy] %s", msg_log)
                    else:
                        logger.warning(
                            "[TelegramBot:Legacy] Ошибка отправки в чат %s: %s",
                            chat.chat_id,
                            err,
                        )

            item.sending_counter -= 1
            if 0 <= item.sending_counter < len(time_list):
                item.send_time = (dt + relativedelta(minutes=time_list[item.sending_counter])).time()
            item.save()

    except Exception as exc:
        err_msg = f"Ошибка legacy-обработчика telegram: {exc}"
        logger.exception("[TelegramBot:Legacy] %s", err_msg)
        result.append(err_msg)

    return result


class Command(BaseCommand):
    """Management-команда запуска асинхронного Telegram-бота компании БАРКОЛ."""

    help = "Запускает асинхронного Telegram-бота (aiogram 3.31.0) в режиме polling"

    def handle(self, *args, **options):
        """Точка входа команды 'python manage.py bot'."""
        self.stdout.write(self.style.SUCCESS("Запуск Telegram-бота компании БАРКОЛ на aiogram 3.31.0..."))
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("Бот остановлен пользователем."))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Критическая ошибка работы бота: {exc}"))
            raise
