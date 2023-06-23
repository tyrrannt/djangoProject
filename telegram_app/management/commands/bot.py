# This is a sample Python script.
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import datetime

from django.core.management import BaseCommand
import telebot
from email.utils import parseaddr


from customers_app.models import DataBaseUser
from djangoProject.settings import API_TOKEN

action = ['Да', 'Нет']
author_action = ['Количество', 'Топ 5']
article_action = []
# for item in Hub.objects.all():
#     article_action.append(str(item))


def main_bot(tok):
    bot = telebot.TeleBot(tok)

    keyboard = telebot.types.ReplyKeyboardMarkup(True)
    keyboard.row('пользователи', 'статьи', 'подписка')
    subscribe_button, author_button, article_button = [], [], []

    otvet = telebot.types.InlineKeyboardMarkup(row_width=2)
    author_otvet = telebot.types.InlineKeyboardMarkup(row_width=2)
    article_otvet = telebot.types.InlineKeyboardMarkup(row_width=2)

    for item in range(0, len(action)):
        subscribe_button.append(telebot.types.InlineKeyboardButton(f"{action[item]}", callback_data=action[item]))
    for item in range(0, len(author_action)):
        author_button.append(
            telebot.types.InlineKeyboardButton(f"{author_action[item]}", callback_data=author_action[item]))
    for item in range(0, len(article_action)):
        article_button.append(
            telebot.types.InlineKeyboardButton(f"{article_action[item]}", callback_data=article_action[item]))

    for item in range(0, len(action)):
        otvet.add(subscribe_button[item])
    for item in range(0, len(author_action)):
        author_otvet.add(author_button[item])
    for item in range(0, len(article_action)):
        article_otvet.add(article_button[item])

    @bot.message_handler(commands=["start"])
    def start_message(message):
        print(message.chat.id)
        bot.send_message(message.chat.id, f"Привет!!! {message.from_user.first_name}", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_inline(call):
        try:
            if call.message:
                if call.data == 'Да':
                    bot.send_message(call.message.chat.id, 'Ёпта! Да не вопрос, шли e-mail в формате @ваш_email')
                if call.data == 'Нет':
                    bot.send_message(call.message.chat.id, 'Не очень то мы и огорчились!')
                if call.data == 'Количество':
                    msg = DataBaseUser.objects.all()
                    message_to_user = f'Количество пользователей = {msg.count()}'
                    bot.send_message(call.message.chat.id, message_to_user, parse_mode='HTML')
                if call.data == 'Топ 5':
                    msg = DataBaseUser.objects.all()
                    message_to_user = f'Количество пользователей = {msg.count()}'
                    bot.send_message(call.message.chat.id, message_to_user, parse_mode='HTML')
                # if call.data == 'Топ 5':
                #     msg = DataBaseUser.objects.all()
                #     author_list = list()
                #     for item in msg:
                #         rating = GeekHubUser.get_total_user_rating(item)
                #         author_list.append([rating, [str(item), str(item.pk)]])
                #     author_list.sort(key=lambda x: x[0])
                #     author_list.reverse()
                #
                #     message_list = 'Топ 5 авторов:\n'
                #     for item in range(0, 5):
                #         message_list += f'Никнейм = <a href="https://reqsoft.ru/auth/user/' \
                #                         f'{author_list[item][1][1]}/">{author_list[item][1][0]}</a>, ' \
                #                         f'Рейтинг = {author_list[item][0]}\n'
                #     bot.send_message(call.message.chat.id, message_list, parse_mode='HTML')
                # for item in range(0, len(article_action)):
                #     if call.data == article_action[item]:
                #         hub_item = Hub.objects.get(name=article_action[item])
                #         article_list = Article.objects.filter(hub=hub_item.pk).order_by('publication_date')[:5]
                #         message_article_list = 'Последние 5 статей в данной категории:\n\n'
                #         for item in range(0, len(article_list)):
                #             message_article_list += f'<a href="https://reqsoft.ru/article/{article_list[item].pk}/">' \
                #                                     f'{article_list[item].title}</a>\n\n'
                #         bot.send_message(call.message.chat.id, message_article_list, parse_mode='HTML')

        except Exception as e:
            print(repr(e))

    @bot.message_handler(content_types=["text"])
    def commands(message):
        if message.text.lower() == "пользователи":
            bot.send_message(message.chat.id, 'Выберите вариант: ', reply_markup=author_otvet)

        if message.text.lower() == "статьи":
            bot.send_message(message.chat.id, 'Выберите категорию: ', reply_markup=article_otvet)

        # if message.text.lower() == "подписка":
        #     registered_users = TelegramUsers.objects.filter(users_id=message.chat.id)
        #     if not registered_users:
        #         msg = TelegramUsers(users_id=message.chat.id)
        #         msg.save()
        #         try:
        #             bot.send_message(message.chat.id, "Вы успешно подписаны на наши новости."
        #                                               "Хотите привязать аккаунт Телеграма к аккаунту на сайте?",
        #                              reply_markup=otvet)
        #         except Exception as ex:
        #             print(ex)
        #     else:
        #         try:
        #             bot.send_message(message.chat.id, "Ёпта! Да Вы уже подписаны на наши новости!!!"
        #                                               "Хотите привязать аккаунт Телеграма к аккаунту на сайте?",
        #                              reply_markup=otvet)
        #         except Exception as ex:
        #             print(ex)

        if message.text.lower()[:1] == "@":
            check_email = parseaddr(message.text.lower()[1:])
            if check_email[1] != '':
                verify_link = f"/telegram/{message.chat.id}:{check_email[1]}/"

                title = f'Подтверждение учетной записи {message.chat.id}'
                email_message = f'Для подтверждения учетной записи {message.chat.id}' \
                                f' на портале https://reqsoft.ru перейдите по ' \
                                f'ссылке: \nhttps://reqsoft.ru{verify_link} '
                bot_message = f'Для подтверждения учетной записи {message.chat.id}' \
                              f' на портале https://reqsoft.ru перейдите по ' \
                              f'ссылке отправленной вам на email '
                # send_mail(title, email_message, settings.EMAIL_HOST_USER, [check_email[1]], fail_silently=False,
                #           auth_user=settings.EMAIL_HOST_USER, auth_password=settings.EMAIL_HOST_PASSWORD)
                bot.send_message(message.chat.id, f"{bot_message}")

    bot.infinity_polling()

def send_message_tg():
    # bot = telebot.TeleBot(API_TOKEN)
    # user_count = DataBaseUser.objects.all().exclude(is_active=False).count()
    # bot.send_message('823040035', f'Ахтунг {datetime.datetime.today()} -  {user_count}', parse_mode='HTML')
    # bot.send_message('1325250637', f'Ахтунг {datetime.datetime.today()} -  {user_count}', parse_mode='HTML')
    return 'Ok'

class Command(BaseCommand):
    help = 'Запускет бота'

    def handle(self, *args, **options):
        main_bot(API_TOKEN)