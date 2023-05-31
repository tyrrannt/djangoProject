from djangoProject.settings import API_TOKEN
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2


bot = Bot(token=API_TOKEN)
# storage = RedisStorage2()
dp = Dispatcher(bot)
