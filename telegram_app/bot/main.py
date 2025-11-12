#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
import asyncio
import datetime

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from asgiref.sync import sync_to_async
from django.conf import settings
from core import logger
from decouple import config
from .handlers import start, text, callbacks, inline
from ..models import TelegramNotification

# logger.add(
#     "debug_bot.json",
#     format=config("LOG_FORMAT"),
#     level=config("LOG_LEVEL"),
#     rotation=config("LOG_ROTATION"),
#     compression=config("LOG_COMPRESSION"),
#     serialize=config("LOG_SERIALIZE"),
# )

bot = Bot(
    token=settings.API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
dp.include_router(start.router)
dp.include_router(text.router)
dp.include_router(callbacks.router)
dp.include_router(inline.router)


# === 🔔 Фоновая задача для рассылки уведомлений ===
async def background_notifier(bot: Bot):
    logger.info("Фоновая задача рассылки запущена.")
    while True:
        try:
            now = datetime.datetime.now().astimezone()
            today = now.date()

            # Ищем уведомления для сегодняшнего дня и с ненулевым счётчиком
            notifications = await sync_to_async(list)(
                TelegramNotification.objects.filter(send_date=today, sending_counter__gt=0)
            )

            for note in notifications:
                respondents = await sync_to_async(list)(note.respondents.all())
                for chat in respondents:
                    try:
                        text = f"<b>{note.message}</b>"
                        if note.document_url:
                            text += f"\n<a href='{note.document_url}'>Ссылка на документ</a>"
                        text += f"\n\n <blockquote>Время отправки: {note.send_date.strftime("%d.%m.%Y")} {note.send_time.strftime("%H:%M")}</blockquote>"
                        await bot.send_message(chat.chat_id, text)
                        logger.info(f"Сообщение отправлено пользователю {chat.chat_id}: {note.message}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке пользователю {chat.chat_id}: {e}")

                # уменьшаем счётчик и сохраняем
                note.sending_counter -= 1
                await sync_to_async(note.save)()

            # Проверяем каждые 60 секунд
            await asyncio.sleep(60)

        except Exception as e:
            logger.exception(f"Ошибка в фоновой задаче уведомлений: {e}")
            await asyncio.sleep(60)


# === 🚀 Запуск бота ===
async def main():
    logger.info("Бот запущен.")
    asyncio.create_task(background_notifier(bot))
    await dp.start_polling(bot)
