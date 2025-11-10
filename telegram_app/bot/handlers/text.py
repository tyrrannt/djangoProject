#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
import uuid
from aiogram import Router, types
from email.utils import parseaddr
from loguru import logger
from asgiref.sync import sync_to_async
from customers_app.models import DataBaseUser
from telegram_app.models import ChatID
from ..keyboards import subscribe_keyboard, author_keyboard, article_keyboard

router = Router()


@router.message()
async def handle_text(message: types.Message):
    text = message.text.strip()
    chat_id = message.chat.id
    logger.info(f"Текстовое сообщение от {chat_id}: {text}")

    # --- Проверка УИН ---
    if len(text) == 36:
        try:
            uuid.UUID(text)  # Проверка корректности UUID
            exists = await sync_to_async(DataBaseUser.objects.filter(person_ref_key=text).exists)()
            if exists:
                user_obj = await sync_to_async(DataBaseUser.objects.get)(person_ref_key=text)
                await sync_to_async(ChatID.objects.update_or_create)(
                    chat_id=chat_id,
                    ref_key=user_obj.person_ref_key
                )
                user_obj.telegram_id = chat_id
                await sync_to_async(user_obj.save)()
                await message.answer("Вы успешно подписаны на уведомления!")
            else:
                await message.answer("Не нашёл вас в списке пользователей.")
        except ValueError:
            await message.answer("Некорректный УИН. Попробуйте снова.")

    # --- Меню пользователей ---
    elif text.lower() == "пользователи":
        await message.answer("Выберите вариант:", reply_markup=author_keyboard)

    # --- Меню статей ---
    elif text.lower() == "статьи":
        await message.answer("Выберите категорию:", reply_markup=article_keyboard)

    # --- Меню подписки ---
    elif text.lower() == "подписка":
        await message.answer("Выберите вариант:", reply_markup=subscribe_keyboard)

    # --- Проверка email (@username@domain) ---
    elif text.startswith("@"):
        check_email = parseaddr(text[1:])
        if check_email[1]:
            verify_link = f"/telegram/{chat_id}:{check_email[1]}/"
            bot_message = (
                f"Для подтверждения учётной записи перейдите по ссылке, "
                f"отправленной вам на email."
            )
            await message.answer(bot_message)
