#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from django.conf import settings
from loguru import logger
from decouple import config
from .handlers import start, text, callbacks

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


async def main():
    logger.info("Бот запущен.")
    await dp.start_polling(bot)
