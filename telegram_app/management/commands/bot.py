# This is a sample Python script.
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import datetime
import time

from dateutil.relativedelta import relativedelta
from decouple import config
from django.core.management import BaseCommand
import telebot
from email.utils import parseaddr

from django.db.models import Q
from loguru import logger

from customers_app.models import DataBaseUser
from djangoProject.settings import API_TOKEN
from telegram_app.models import ChatID, TelegramNotification

action = ["ПОДПИСАТЬСЯ", "ПРОВЕРИТЬ"]
author_action = ["Количество"]
article_action = []

logger.add(
    "debug.json",
    format=config("LOG_FORMAT"),
    level=config("LOG_LEVEL"),
    rotation=config("LOG_ROTATION"),
    compression=config("LOG_COMPRESSION"),
    serialize=config("LOG_SERIALIZE"),
)


def main_bot(tok):
    bot = telebot.TeleBot(tok, skip_pending=True)
    keyboard = telebot.types.ReplyKeyboardMarkup(True)
    keyboard.row("ПОЛЬЗОВАТЕЛИ", "ПОДПИСКА")
    subscribe_button, author_button, article_button = [], [], []

    otvet = telebot.types.InlineKeyboardMarkup(row_width=2)
    author_otvet = telebot.types.InlineKeyboardMarkup(row_width=2)
    article_otvet = telebot.types.InlineKeyboardMarkup(row_width=2)

    for item in range(0, len(action)):
        subscribe_button.append(
            telebot.types.InlineKeyboardButton(
                f"{action[item]}", callback_data=action[item]
            )
        )
    for item in range(0, len(author_action)):
        author_button.append(
            telebot.types.InlineKeyboardButton(
                f"{author_action[item]}", callback_data=author_action[item]
            )
        )
    for item in range(0, len(article_action)):
        article_button.append(
            telebot.types.InlineKeyboardButton(
                f"{article_action[item]}", callback_data=article_action[item]
            )
        )

    for item in range(0, len(action)):
        otvet.add(subscribe_button[item])
    for item in range(0, len(author_action)):
        author_otvet.add(author_button[item])
    for item in range(0, len(article_action)):
        article_otvet.add(article_button[item])

    @bot.message_handler(commands=["start"])
    def start_message(message):
        print(message.chat.id)
        bot.send_message(
            message.chat.id,
            f"Здравствуйте {message.from_user.first_name}, для продолжения воспользуйтесь меню.",
            reply_markup=keyboard,
        )

    @bot.callback_query_handler(func=lambda call: True)
    def callback_inline(call):
        try:
            if call.message:
                if call.data == "ПОДПИСАТЬСЯ":
                    bot.send_message(
                        call.message.chat.id, "Отправь УИН из своего профиля"
                    )
                if call.data == "ПРОВЕРИТЬ":
                    if DataBaseUser.objects.filter(telegram_id=call.message.chat.id):
                        bot.send_message(
                            call.message.chat.id,
                            "Вы успешно подписаны на уведомления! ",
                        )
                    else:
                        bot.send_message(
                            call.message.chat.id,
                            "Не нашел вас в списке пользователей! Пройдите процес подписки на уведомления.",
                        )
                if call.data == "Количество":
                    msg = DataBaseUser.objects.all().exclude(telegram_id="")
                    message_to_user = (
                        f"Количество подписанных пользователей = {msg.count()}"
                    )
                    bot.send_message(
                        call.message.chat.id, message_to_user, parse_mode="HTML"
                    )

        except Exception as e:
            print(repr(e))

    @bot.message_handler(content_types=["text"])
    def commands(message):
        if len(message.text) == 36:
            if DataBaseUser.objects.filter(person_ref_key=message.text):
                user_obj = DataBaseUser.objects.get(person_ref_key=message.text)
                ChatID.objects.update_or_create(
                    chat_id=message.chat.id, ref_key=user_obj.person_ref_key
                )
                user_obj.telegram_id = message.chat.id
                user_obj.save()
                bot.send_message(
                    message.chat.id, "Вы успешно подписаны на уведомления! "
                )
            else:
                bot.send_message(
                    message.chat.id, "Не нашел вас в списке пользователей! "
                )
        if message.text.lower() == "пользователи":
            bot.send_message(
                message.chat.id, "Выберите вариант: ", reply_markup=author_otvet
            )

        if message.text.lower() == "статьи":
            bot.send_message(
                message.chat.id, "Выберите категорию: ", reply_markup=article_otvet
            )

        if message.text.lower() == "подписка":
            bot.send_message(message.chat.id, "Выберите вариант:", reply_markup=otvet)

        if message.text.lower()[:1] == "@":
            check_email = parseaddr(message.text.lower()[1:])
            if check_email[1] != "":
                verify_link = f"/telegram/{message.chat.id}:{check_email[1]}/"

                title = f"Подтверждение учетной записи {message.chat.id}"
                email_message = (
                    f"Для подтверждения учетной записи {message.chat.id}"
                    f" на портале https://reqsoft.ru перейдите по "
                    f"ссылке: \nhttps://reqsoft.ru{verify_link} "
                )
                bot_message = (
                    f"Для подтверждения учетной записи {message.chat.id}"
                    f" на портале https://reqsoft.ru перейдите по "
                    f"ссылке отправленной вам на email "
                )
                # send_mail(title, email_message, settings.EMAIL_HOST_USER, [check_email[1]], fail_silently=False,
                #           auth_user=settings.EMAIL_HOST_USER, auth_password=settings.EMAIL_HOST_PASSWORD)
                bot.send_message(message.chat.id, f"{bot_message}")

    bot.infinity_polling(timeout=10, long_polling_timeout=5)


def send_message_tg():
    time_list = [0, 15, 5]
    dt = datetime.datetime.now()
    result = list()
    try:
        bot = telebot.TeleBot(API_TOKEN, skip_pending=True)
        notify_list = TelegramNotification.objects.filter(
            Q(send_time__hour=dt.hour) & Q(send_time__minute=dt.minute) & Q(send_date=dt.date())
        )
        for item in notify_list:
            for chat_id in item.respondents.all():
                if item.sending_counter > 0:
                    if item.document_url:
                        bot.send_message(
                            chat_id.chat_id,
                            f'<b>{item.message}</b>.\n <a href="{item.document_url}">Ссылка на документ</a>\n <blockquote>Время отправки: {item.send_date.strftime("%d.%m.%Y")} {item.send_time.strftime("%H:%M")}</blockquote>',
                            parse_mode="HTML",
                        )
                        result.append(
                            f"Сообщение для {chat_id.chat_id}: {item.message}. "
                            f"Ссылка на документ: {item.document_url}"
                        )
                        logger.info(
                            f"Сообщение для {chat_id.chat_id} отправлено. "
                            f"Текст: {item.message}. Ссылка: {item.document_url}"
                        )
                    else:
                        bot.send_message(
                            chat_id.chat_id, f"{item.message}", parse_mode="HTML"
                        )
                        result.append(
                            f"Сообщение для {chat_id.chat_id}: {item.message}."
                        )
                        logger.info(
                            f"Сообщение для {chat_id.chat_id} отправлено. Текст: {item.message}."
                        )
            item.sending_counter -= 1
            item.send_time = dt + relativedelta(minutes=time_list[item.sending_counter])
            item.save()
            time.sleep(1)

    except Exception as _ex:
        result.append(f"Ошибка telegram бота: {_ex}")
    return result

# def send_message_tg():
#     time_list = [0, 15, 5]
#     dt = datetime.datetime.now()
#     result = []
#
#     try:
#         bot = telebot.TeleBot(API_TOKEN, skip_pending=True)
#         notify_list = TelegramNotification.objects.filter(
#             send_time__hour=dt.hour,
#             send_time__minute=dt.minute,
#             send_date=dt.date()
#         )
#
#         for item in notify_list:
#             for chat_id in item.respondents.all():
#                 if item.sending_counter > 0:
#                     message_text = item.message
#                     if item.document_url:
#                         message_text += f'\n <a href="{item.document_url}">Ссылка на документ</a>\n <blockquote>Время отправки: {item.send_date.strftime("%d.%m.%Y")} {item.send_time.strftime("%H:%M")}</blockquote>'
#                         result.append(
#                             f"Сообщение для {chat_id.chat_id}: {item.message}. "
#                             f"Ссылка на документ: {item.document_url}"
#                         )
#                         logger.info(
#                             f"Сообщение для {chat_id.chat_id} отправлено. "
#                             f"Текст: {item.message}. Ссылка: {item.document_url}"
#                         )
#                     else:
#                         result.append(
#                             f"Сообщение для {chat_id.chat_id}: {item.message}."
#                         )
#                         logger.info(
#                             f"Сообщение для {chat_id.chat_id} отправлено. Текст: {item.message}."
#                         )
#
#                     bot.send_message(chat_id.chat_id, f'<b>{message_text}</b>', parse_mode="HTML")
#
#             item.sending_counter -= 1
#             item.send_time = dt + relativedelta(minutes=time_list[item.sending_counter])
#             item.save()
#             time.sleep(1)
#
#     except Exception as _ex:
#         result.append(f"Ошибка telegram бота: {_ex}")
#
#     return result


class Command(BaseCommand):
    help = "Запускет бота"

    def handle(self, *args, **options):
        main_bot(API_TOKEN)
