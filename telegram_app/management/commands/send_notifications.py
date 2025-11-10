#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
import asyncio
import datetime
import time
from dateutil.relativedelta import relativedelta
from django.core.management import BaseCommand
from django.db.models import Q
from telegram_app.models import TelegramNotification
from django.conf import settings
from aiogram import Bot
from loguru import logger


class Command(BaseCommand):
    help = "Рассылает уведомления пользователям Telegram"

    def handle(self, *args, **options):
        asyncio.run(self.send_notifications())

    async def send_notifications(self):
        bot = Bot(token=settings.API_TOKEN, parse_mode="HTML")
        dt = datetime.datetime.now()
        time_list = [0, 15, 5]
        result = []

        try:
            notify_list = TelegramNotification.objects.filter(
                Q(send_time__hour=dt.hour) &
                Q(send_time__minute=dt.minute) &
                Q(send_date=dt.date())
            )

            for item in notify_list:
                for chat in item.respondents.all():
                    if item.sending_counter > 0:
                        text = f"<b>{item.message}</b>"
                        if item.document_url:
                            text += f"\n<a href='{item.document_url}'>Ссылка на документ</a>"
                        await bot.send_message(chat.chat_id, text)

                        logger.info(f"Сообщение отправлено {chat.chat_id}: {item.message}")
                        item.sending_counter -= 1
                        item.send_time = dt + relativedelta(minutes=time_list[item.sending_counter])
                        item.save()
                        time.sleep(1)
        except Exception as e:
            logger.exception(f"Ошибка при рассылке: {e}")
