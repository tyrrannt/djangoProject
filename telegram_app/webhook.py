import json
from aiogram import types, Bot, Dispatcher
from django.http import HttpRequest, HttpResponse
from loguru import logger

from .bot.loader import bot, dp
logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)

async def proceed_update(req: HttpRequest):
    upd = types.Update(**(json.loads(req.body)))
    Dispatcher.set_current(dp)
    Bot.set_current(bot)
    logger.error(f'Webhook - {req}')
    await dp.process_update(upd)
