# -*- coding: utf-8 -*-
"""Клавиатуры Telegram-бота компании БАРКОЛ (aiogram 3)."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Главное меню (Reply-кнопки внизу экрана)
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="👥 ПОЛЬЗОВАТЕЛИ"),
            KeyboardButton(text="🔔 ПОДПИСКА"),
        ]
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# Меню управления подпиской (Inline-кнопки под сообщением)
subscribe_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Привязать аккаунт (УИН)", callback_data="ПОДПИСАТЬСЯ")],
        [InlineKeyboardButton(text="🔍 Проверить статус подписки", callback_data="ПРОВЕРИТЬ")],
    ]
)

# Меню раздела пользователей
author_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Количество подключенных", callback_data="Количество")]
    ]
)

# Меню статей и базы знаний
article_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Корпоративный портал", url="https://corp.barkol.ru")]
    ]
)
