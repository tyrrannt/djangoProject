#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
from aiogram import Router, types
from loguru import logger
from customers_app.models import DataBaseUser
from asgiref.sync import sync_to_async

router = Router()


@router.callback_query()
async def process_callback(call: types.CallbackQuery):
    data = call.data
    chat_id = call.message.chat.id
    logger.info(f"Callback {data} от {chat_id}")

    try:
        if data == "ПОДПИСАТЬСЯ":
            await call.message.answer("Отправь УИН из своего профиля")

        elif data == "ПРОВЕРИТЬ":
            exists = await sync_to_async(DataBaseUser.objects.filter(telegram_id=chat_id).exists)()
            if exists:
                await call.message.answer("Вы успешно подписаны на уведомления!")
            else:
                await call.message.answer("Не нашёл вас в списке пользователей!")

        elif data == "Количество":
            count = await sync_to_async(DataBaseUser.objects.exclude(telegram_id="").count)()
            await call.message.answer(f"Количество подписанных пользователей = {count}")

        else:
            logger.warning(f"Неизвестный callback: {data}")

    except Exception as e:
        logger.exception(f"Ошибка в callback: {e}")
        await call.message.answer("Произошла ошибка, попробуйте позже.")
