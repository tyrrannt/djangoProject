#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="ПОЛЬЗОВАТЕЛИ"), KeyboardButton(text="ПОДПИСКА")]
    ],
    resize_keyboard=True
)

# Inline кнопки
subscribe_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="ПОДПИСАТЬСЯ", callback_data="ПОДПИСАТЬСЯ")],
        [InlineKeyboardButton(text="ПРОВЕРИТЬ", callback_data="ПРОВЕРИТЬ")]
    ]
)

author_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Количество", callback_data="Количество")]
    ]
)

article_keyboard = InlineKeyboardMarkup(inline_keyboard=[])
