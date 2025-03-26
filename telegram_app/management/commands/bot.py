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

# Константы для кнопок
action = ["ПОДПИСАТЬСЯ", "ПРОВЕРИТЬ"]
author_action = ["Количество"]
article_action = []

# Настройка логгера
logger.add(
    "debug_bot.json",
    format=config("LOG_FORMAT"),
    level=config("LOG_LEVEL"),
    rotation=config("LOG_ROTATION"),
    compression=config("LOG_COMPRESSION"),
    serialize=config("LOG_SERIALIZE"),
)

def main_bot(tok):
    bot = telebot.TeleBot(tok, skip_pending=True)

    # Создаем клавиатуру
    keyboard = telebot.types.ReplyKeyboardMarkup(True)
    keyboard.row("ПОЛЬЗОВАТЕЛИ", "ПОДПИСКА")

    # Создаем inline-кнопки
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

    # Обработчик команды /start
    @bot.message_handler(commands=["start"])
    def start_message(message):
        logger.info(f"Start command received from {message.chat.id}")
        bot.send_message(
            message.chat.id,
            f"Здравствуйте {message.from_user.first_name}, для продолжения воспользуйтесь меню.",
            reply_markup=keyboard,
        )

    # Обработчик callback-запросов
    @bot.callback_query_handler(func=lambda call: True)
    def callback_inline(call):
        try:
            logger.info(f"Callback received: {call.data}")  # Логируем callback-данные
            if call.message:
                logger.info(f"Message chat ID: {call.message.chat.id}")  # Логируем ID чата
                if call.data == "ПОДПИСАТЬСЯ":
                    logger.info("User clicked 'ПОДПИСАТЬСЯ'")  # Логируем нажатие кнопки
                    bot.send_message(
                        call.message.chat.id, "Отправь УИН из своего профиля"
                    )
                elif call.data == "ПРОВЕРИТЬ":
                    logger.info("User clicked 'ПРОВЕРИТЬ'")  # Логируем нажатие кнопки
                    if DataBaseUser.objects.filter(telegram_id=call.message.chat.id):
                        bot.send_message(
                            call.message.chat.id,
                            "Вы успешно подписаны на уведомления! ",
                        )
                    else:
                        bot.send_message(
                            call.message.chat.id,
                            "Не нашел вас в списке пользователей! Пройдите процесс подписки на уведомления.",
                        )
                elif call.data == "Количество":
                    logger.info("User clicked 'Количество'")  # Логируем нажатие кнопки
                    msg = DataBaseUser.objects.all().exclude(telegram_id="")
                    message_to_user = (
                        f"Количество подписанных пользователей = {msg.count()}"
                    )
                    bot.send_message(
                        call.message.chat.id, message_to_user, parse_mode="HTML"
                    )
                else:
                    logger.warning(f"Unknown callback data: {call.data}")  # Логируем неизвестные данные
            else:
                logger.warning("Callback message is missing")  # Логируем отсутствие сообщения
        except Exception as e:
            logger.error(f"Error in callback_inline: {repr(e)}")  # Логируем ошибки

    # Обработчик текстовых сообщений
    @bot.message_handler(content_types=["text"])
    def commands(message):
        logger.info(f"Text message received: {message.text}")  # Логируем текст сообщения
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
        elif message.text.lower() == "пользователи":
            bot.send_message(
                message.chat.id, "Выберите вариант: ", reply_markup=author_otvet
            )
        elif message.text.lower() == "статьи":
            bot.send_message(
                message.chat.id, "Выберите категорию: ", reply_markup=article_otvet
            )
        elif message.text.lower() == "подписка":
            bot.send_message(message.chat.id, "Выберите вариант:", reply_markup=otvet)
        elif message.text.lower()[:1] == "@":
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
                bot.send_message(message.chat.id, f"{bot_message}")

    # Запуск бота
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

# Функция для отправки уведомлений
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

# Команда для запуска бота
class Command(BaseCommand):
    help = "Запускет бота"

    def handle(self, *args, **options):
        main_bot(API_TOKEN)