# -*- coding: utf-8 -*-
"""Модуль клавиатур Telegram-бота компании БАРКОЛ (aiogram 3.31.0).

Предоставляет постоянные Reply-клавиатуры главного меню с разделением прав
(авторизованный сотрудник / гость), инлайн-клавиатуры для задач,
профиля, настройки персональных матриц уведомлений и справочной службы.
"""

from typing import Any, Dict, List, Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_main_menu(is_authenticated: bool = True) -> ReplyKeyboardMarkup:
    """Формирует адаптивную постоянную Reply-клавиатуру главного меню.

    Args:
        is_authenticated: Флаг авторизации сотрудника в системе.

    Returns:
        ReplyKeyboardMarkup: Объект клавиатуры Telegram с флагом is_persistent=True.
    """
    if is_authenticated:
        keyboard = [
            [
                KeyboardButton(text="📋 Мои задачи"),
                KeyboardButton(text="📑 Служебные записки"),
            ],
            [
                KeyboardButton(text="👥 Справочник коллег"),
                KeyboardButton(text="✈️ Летный план / МПД"),
            ],
            [
                KeyboardButton(text="🎂 Дни рождения"),
                KeyboardButton(text="⚙️ Профиль"),
            ],
        ]
    else:
        keyboard = [
            [
                KeyboardButton(text="🔐 Привязать аккаунт"),
                KeyboardButton(text="ℹ️ Справка и помощь"),
            ],
        ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


# Постоянное главное меню по умолчанию (обратная совместимость)
main_menu = get_main_menu(is_authenticated=True)


def get_tasks_filter_keyboard(
    active_tab: str = "assigned",
    page: int = 1,
    total_pages: int = 1,
    tasks_list: Optional[List[Dict[str, Any]]] = None,
) -> InlineKeyboardMarkup:
    """Формирует инлайн-клавиатуру реестра задач с вкладками и пагинацией.

    Args:
        active_tab: Активная вкладка ('assigned', 'authored', 'completed').
        page: Текущий номер страницы.
        total_pages: Общее количество страниц.
        tasks_list: Список словарей с краткими данными задач.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура с вкладками, списком и навигацией.
    """
    # 1. Верхний ряд: вкладки фильтрации
    tab_assigned_icon = "👉 " if active_tab == "assigned" else ""
    tab_authored_icon = "👉 " if active_tab == "authored" else ""
    tab_completed_icon = "👉 " if active_tab == "completed" else ""

    inline_keyboard: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"{tab_assigned_icon}📥 Мне",
                callback_data="task_tab:assigned:1",
            ),
            InlineKeyboardButton(
                text=f"{tab_authored_icon}📤 От меня",
                callback_data="task_tab:authored:1",
            ),
            InlineKeyboardButton(
                text=f"{tab_completed_icon}✅ Завершенные",
                callback_data="task_tab:completed:1",
            ),
        ]
    ]

    # 2. Список задач (по 1 кнопке на строку)
    if tasks_list:
        for t in tasks_list:
            badge = t.get("badge", "🔹")
            task_id = t.get("id")
            title = t.get("title", f"Задача #{task_id}")
            # Ограничиваем длину текста кнопки
            truncated = (title[:32] + "…") if len(title) > 33 else title
            btn_text = f"{badge} #{task_id} {truncated}"
            inline_keyboard.append(
                [
                    InlineKeyboardButton(
                        text=btn_text,
                        callback_data=f"task_view:{task_id}:{active_tab}:{page}",
                    )
                ]
            )

    # 3. Ряд пагинации
    nav_row: List[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"task_tab:{active_tab}:{page - 1}",
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"Стр. {page}/{max(1, total_pages)}",
            callback_data=f"task_tab:{active_tab}:{page}",
        )
    )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=f"task_tab:{active_tab}:{page + 1}",
            )
        )
    inline_keyboard.append(nav_row)

    # 4. Кнопка обновления
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить список",
                callback_data=f"task_tab:{active_tab}:{page}",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_task_card_keyboard(
    task_id: int,
    can_accept: bool = False,
    can_complete: bool = False,
    absolute_url: str = "",
    back_tab: str = "assigned",
    back_page: int = 1,
) -> InlineKeyboardMarkup:
    """Формирует инлайн-клавиатуру для детальной карточки задачи.

    Args:
        task_id: Идентификатор задачи.
        can_accept: Разрешено ли действие «Принять в работу».
        can_complete: Разрешено ли действие «Завершить задачу».
        absolute_url: Относительный путь задачи на веб-портале.
        back_tab: Вкладка, из которой был совершен переход.
        back_page: Номер страницы списка для возврата.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура управления задачей.
    """
    keyboard: List[List[InlineKeyboardButton]] = []

    # Кнопки изменения статуса
    action_row: List[InlineKeyboardButton] = []
    if can_accept:
        action_row.append(
            InlineKeyboardButton(
                text="▶️ В работу",
                callback_data=f"task_act:in_progress:{task_id}:{back_tab}:{back_page}",
            )
        )
    if can_complete:
        action_row.append(
            InlineKeyboardButton(
                text="✅ Завершить",
                callback_data=f"task_act:completed:{task_id}:{back_tab}:{back_page}",
            )
        )
    if action_row:
        keyboard.append(action_row)

    # Ссылка на портал
    full_portal_url = f"https://corp.barkol.ru{absolute_url}" if absolute_url else "https://corp.barkol.ru/tasks/"
    keyboard.append(
        [
            InlineKeyboardButton(
                text="🔗 Открыть на портале",
                url=full_portal_url,
            )
        ]
    )

    # Возврат к списку
    keyboard.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к списку задач",
                callback_data=f"task_back:{back_tab}:{back_page}",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_profile_keyboard(is_authenticated: bool = True) -> InlineKeyboardMarkup:
    """Формирует инлайн-клавиатуру личного кабинета сотрудника.

    Args:
        is_authenticated: Авторизован ли пользователь.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура профиля.
    """
    if is_authenticated:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔔 Настройка уведомлений",
                        callback_data="profile_notif",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔓 Отвязать аккаунт",
                        callback_data="profile_unlink_ask",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🌐 Портал БАРКОЛ",
                        url="https://corp.barkol.ru",
                    )
                ],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔑 Привязать аккаунт (УИН)",
                    callback_data="ПОДПИСАТЬСЯ",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Портал БАРКОЛ",
                    url="https://corp.barkol.ru",
                )
            ],
        ]
    )


def get_notifications_keyboard(chat_obj: Any) -> InlineKeyboardMarkup:
    """Формирует интерактивную матрицу переключателей категорий уведомлений.

    Args:
        chat_obj: Экземпляр модели ChatID с булевыми полями notify_*.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура с toggle-кнопками.
    """
    def _status_icon(val: bool) -> str:
        return "🟢 Вкл" if val else "⚪ Откл"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{_status_icon(getattr(chat_obj, 'notify_tasks', True))} 📋 Задачи",
                    callback_data="notif_toggle:tasks",
                ),
                InlineKeyboardButton(
                    text=f"{_status_icon(getattr(chat_obj, 'notify_memos', True))} 📑 СЗ",
                    callback_data="notif_toggle:memos",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{_status_icon(getattr(chat_obj, 'notify_birthdays', True))} 🎂 Дни рождения",
                    callback_data="notif_toggle:birthdays",
                ),
                InlineKeyboardButton(
                    text=f"{_status_icon(getattr(chat_obj, 'notify_emails', True))} 📧 Почта",
                    callback_data="notif_toggle:emails",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{_status_icon(getattr(chat_obj, 'notify_flights', True))} ✈️ Рейсы и экипажи",
                    callback_data="notif_toggle:flights",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад в профиль",
                    callback_data="profile_main",
                )
            ],
        ]
    )


def get_unlink_confirm_keyboard() -> InlineKeyboardMarkup:
    """Формирует клавиатуру подтверждения отвязки профиля.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура с кнопками подтверждения и отмены.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Да, подтверждаю отвязку",
                    callback_data="profile_unlink_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="profile_main",
                )
            ],
        ]
    )


def get_help_keyboard(is_authenticated: bool = False) -> InlineKeyboardMarkup:
    """Формирует клавиатуру справки и технической поддержки.

    Args:
        is_authenticated: Авторизован ли пользователь.

    Returns:
        InlineKeyboardMarkup: Инлайн-клавиатура раздела справки.
    """
    first_btn = (
        InlineKeyboardButton(text="📋 Мои задачи", callback_data="task_tab:assigned:1")
        if is_authenticated
        else InlineKeyboardButton(text="🔑 Привязать аккаунт", callback_data="ПОДПИСАТЬСЯ")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [first_btn],
            [
                InlineKeyboardButton(
                    text="🌐 Корпоративный портал",
                    url="https://corp.barkol.ru",
                )
            ],
        ]
    )


# Устаревшие клавиатуры для сохранения полной обратной совместимости
subscribe_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Привязать аккаунт (УИН)", callback_data="ПОДПИСАТЬСЯ")],
        [InlineKeyboardButton(text="🔍 Проверить статус подписки", callback_data="ПРОВЕРИТЬ")],
    ]
)

author_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Количество подключенных", callback_data="Количество")]
    ]
)

article_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Корпоративный портал", url="https://corp.barkol.ru")]
    ]
)
