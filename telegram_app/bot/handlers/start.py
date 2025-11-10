#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
from aiogram import Router, types
from aiogram.filters import Command
from loguru import logger
from ..keyboards import main_menu

router = Router()


@router.message(Command("start"))
async def start_command(message: types.Message):
    logger.info(f"Команда /start от {message.chat.id}")
    await message.answer(
        f"Здравствуйте, {message.from_user.first_name}! Для продолжения воспользуйтесь меню.",
        reply_markup=main_menu
    )
