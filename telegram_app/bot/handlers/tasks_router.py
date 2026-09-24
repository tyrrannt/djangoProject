# -*- coding: utf-8 -*-
"""Обработчик команды /tasks и модуля управления задачами Telegram-бота (aiogram 3.31.0).

Предоставляет просмотр назначенных и созданных задач с разделением по вкладкам,
индикацию сроков (просрочено / дедлайн сегодня / в работе / завершено),
детальный просмотр карточки и смену статусов («В работу», «Завершить») в 1 клик.
"""

import html
import logging
from typing import Any, Dict, List, Optional, Tuple

from aiogram import F, Router, types
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from django.db.models import F as DbF, Q
from django.utils import timezone

from customers_app.models import DataBaseUser
from tasks_app.models import Task, TaskStatus
from ..keyboards import (
    get_profile_keyboard,
    get_task_card_keyboard,
    get_tasks_filter_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="tasks_router")


@sync_to_async
def get_user_by_chat_id(chat_id: int) -> Optional[DataBaseUser]:
    """Получает активного пользователя DataBaseUser по идентификатору Telegram.

    Args:
        chat_id: Telegram ID чата.

    Returns:
        Optional[DataBaseUser]: Экземпляр пользователя или None.
    """
    return DataBaseUser.objects.filter(telegram_id=str(chat_id), is_active=True).first()


@sync_to_async
def fetch_tasks_page_data(
    user: DataBaseUser,
    tab: str = "assigned",
    page: int = 1,
    per_page: int = 5,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Выбирает страницу задач сотрудника по заданной вкладке.

    Args:
        user: Пользователь DataBaseUser.
        tab: Вкладка фильтрации ('assigned', 'authored', 'completed').
        page: Номер запрашиваемой страницы (1-based).
        per_page: Количество задач на страницу.

    Returns:
        Tuple[List[Dict[str, Any]], int, int]: (список_задач, номер_страницы, всего_страниц).
    """
    now = timezone.now()
    today = now.date()

    if tab == "authored":
        qs = Task.objects.filter(user=user).exclude(
            status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
        ).order_by(DbF("end_date").asc(nulls_last=True), "-created_at")
    elif tab == "completed":
        qs = Task.objects.filter(
            Q(responsible=user) | Q(assignees=user) | Q(user=user),
            status=TaskStatus.COMPLETED,
        ).distinct().order_by("-completed_at", "-updated_at")
    else:  # 'assigned' по умолчанию
        qs = Task.objects.filter(
            Q(responsible=user) | Q(assignees=user)
        ).exclude(
            status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
        ).distinct().order_by(DbF("end_date").asc(nulls_last=True), "-created_at")

    total_count = qs.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    safe_page = min(max(1, page), total_pages)
    offset = (safe_page - 1) * per_page

    tasks_slice = list(qs[offset : offset + per_page])
    result_list: List[Dict[str, Any]] = []

    for task in tasks_slice:
        # Расчет бейджа статуса и дедлайна
        badge = "🔹"
        if task.status == TaskStatus.COMPLETED:
            badge = "✅"
        elif task.end_date and task.end_date < now:
            badge = "🔴"
        elif task.end_date and task.end_date.date() == today:
            badge = "🟡"
        elif task.status == TaskStatus.IN_PROGRESS:
            badge = "🔵"
        elif task.status in (TaskStatus.NEW, TaskStatus.ASSIGNED):
            badge = "⚪"

        result_list.append(
            {
                "id": task.id,
                "title": task.title,
                "badge": badge,
                "status": task.status,
            }
        )

    return result_list, safe_page, total_pages


@sync_to_async
def fetch_task_details_data(task_id: int, user: DataBaseUser) -> Optional[Dict[str, Any]]:
    """Извлекает детальные данные задачи и проверяет права на действия.

    Args:
        task_id: Идентификатор задачи.
        user: Пользователь, запрашивающий карточку.

    Returns:
        Optional[Dict[str, Any]]: Словарь с полями карточки или None, если задача не найдена.
    """
    task = (
        Task.objects.filter(id=task_id)
        .select_related("user", "responsible", "category")
        .prefetch_related("assignees")
        .first()
    )
    if not task:
        return None

    is_author = task.user_id == user.id
    is_responsible = task.responsible_id == user.id
    is_assignee = user in task.assignees.all()
    can_manage = is_author or is_responsible or is_assignee

    now = timezone.now()
    is_overdue = bool(task.end_date and task.end_date < now and task.status != TaskStatus.COMPLETED)
    end_date_str = task.end_date.strftime("%d.%m.%Y %H:%M") if task.end_date else "Не назначен"

    # Права на действия
    can_accept = (is_responsible or is_assignee) and task.status in (TaskStatus.NEW, TaskStatus.ASSIGNED)
    can_complete = (is_responsible or is_assignee or is_author) and task.status == TaskStatus.IN_PROGRESS

    cat_name = task.category.name if task.category else "Общая"
    author_name = task.user.title if task.user else "Не указан"
    responsible_name = task.responsible.title if task.responsible else "Не назначен"

    try:
        abs_url = task.get_absolute_url()
    except Exception:
        abs_url = f"/tasks/{task.id}/"

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description or "Без дополнительного описания.",
        "status": task.status,
        "status_display": task.get_status_display(),
        "priority_display": task.get_priority_display(),
        "category_name": cat_name,
        "author_name": author_name,
        "responsible_name": responsible_name,
        "end_date_str": end_date_str,
        "is_overdue": is_overdue,
        "progress_percent": task.progress_percent,
        "can_accept": can_accept,
        "can_complete": can_complete,
        "can_manage": can_manage,
        "absolute_url": abs_url,
    }


@sync_to_async
def execute_task_action(task_id: int, user: DataBaseUser, action: str) -> Tuple[bool, str]:
    """Выполняет перевод статуса задачи («В работу» / «Завершить»).

    Args:
        task_id: Идентификатор задачи.
        user: Пользователь, выполняющий действие.
        action: Код действия ('in_progress', 'completed').

    Returns:
        Tuple[bool, str]: Кортеж (успех, сообщение_для_пользователя).
    """
    task = (
        Task.objects.filter(id=task_id)
        .prefetch_related("assignees")
        .first()
    )
    if not task:
        return False, "Задача не найдена."

    is_author = task.user_id == user.id
    is_responsible = task.responsible_id == user.id
    is_assignee = user in task.assignees.all()

    if action == "in_progress":
        if not (is_responsible or is_assignee or is_author):
            return False, "Недостаточно прав для взятия задачи в работу."
        task.status = TaskStatus.IN_PROGRESS
        task.accepted_at = timezone.now()
        task.save(update_fields=["status", "accepted_at", "updated_at"])
        logger.info("[TelegramBot:Tasks] Задача #%s переведена в статус 'В работу' пользователем %s", task_id, user.title)
        return True, "Задача успешно принята в работу!"

    elif action == "completed":
        if not (is_responsible or is_assignee or is_author):
            return False, "Недостаточно прав для завершения задачи."
        task.status = TaskStatus.COMPLETED
        task.completed = True
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed", "completed_at", "updated_at"])
        logger.info("[TelegramBot:Tasks] Задача #%s завершена пользователем %s", task_id, user.title)
        return True, "Поздравляем! Задача успешно завершена."

    return False, "Неизвестное действие."


def format_task_list_text(tab: str, total_count: int) -> str:
    """Формирует текстовый заголовок реестра задач.

    Args:
        tab: Идентификатор активной вкладки.
        total_count: Общее количество задач.

    Returns:
        str: Заголовок для сообщения в Telegram.
    """
    titles = {
        "assigned": "📥 <b>Задачи, назначенные мне</b>",
        "authored": "📤 <b>Задачи, созданные мной</b>",
        "completed": "✅ <b>Завершенные задачи</b>",
    }
    title = titles.get(tab, "📋 <b>Список задач</b>")
    return (
        f"{title}\n\n"
        f"Всего задач в разделе: <b>{total_count}</b>\n"
        f"🔴 — Просрочено | 🟡 — Срок сегодня | 🔵 — В работе | ⚪ — Новая\n\n"
        f"<i>Выберите задачу из списка ниже для просмотра подробностей:</i>"
    )


def format_task_card_text(details: Dict[str, Any]) -> str:
    """Формирует визуальную карточку задачи в формате HTML.

    Args:
        details: Словарь с атрибутами задачи.

    Returns:
        str: Отформатированный текст карточки.
    """
    task_id = details["id"]
    title = html.escape(details["title"])
    description = html.escape(details["description"])
    status_disp = details["status_display"]
    priority_disp = details["priority_display"]
    cat_name = html.escape(details["category_name"])
    author_name = html.escape(details["author_name"])
    responsible_name = html.escape(details["responsible_name"])
    end_date_str = details["end_date_str"]
    progress = details["progress_percent"]

    overdue_badge = " 🔴 <b>(ПРОСРОЧЕНО!)</b>" if details["is_overdue"] else ""

    return (
        f"📋 <b>Задача #{task_id}</b>\n"
        f"<b>{title}</b>\n\n"
        f"📌 <b>Категория:</b> {cat_name}\n"
        f"⚡ <b>Приоритет:</b> {priority_disp}\n"
        f"📊 <b>Статус:</b> {status_disp}\n"
        f"📈 <b>Прогресс:</b> {progress}%\n"
        f"⏰ <b>Дедлайн:</b> <code>{end_date_str}</code>{overdue_badge}\n\n"
        f"👤 <b>Постановщик:</b> {author_name}\n"
        f"🎯 <b>Ответственный:</b> {responsible_name}\n\n"
        f"📝 <b>Описание:</b>\n"
        f"<blockquote>{description}</blockquote>"
    )


@router.message(Command("tasks", ignore_case=True))
@router.message(F.text.lower().in_(["📋 мои задачи", "мои задачи", "задачи", "/tasks", "поручения"]))
async def handle_tasks_command(message: types.Message) -> None:
    """Обрабатывает команду /tasks и нажатие кнопки «Мои задачи».

    Args:
        message: Сообщение от пользователя.
    """
    chat_id = message.chat.id
    user = await get_user_by_chat_id(chat_id)
    if not user:
        await message.answer(
            "⚠️ <b>Аккаунт не привязан</b>\n\n"
            "Чтобы управлять задачами прямо из Telegram, необходимо привязать свой "
            "аккаунт к порталу. Отправьте ваш <b>УИН</b> (GUID из 36 символов) из профиля.",
            reply_markup=get_profile_keyboard(is_authenticated=False),
            parse_mode="HTML",
        )
        return

    tab = "assigned"
    page = 1
    tasks_list, cur_page, total_pages = await fetch_tasks_page_data(user, tab=tab, page=page)
    text = format_task_list_text(tab, len(tasks_list))

    await message.answer(
        text,
        reply_markup=get_tasks_filter_keyboard(
            active_tab=tab,
            page=cur_page,
            total_pages=total_pages,
            tasks_list=tasks_list,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task_tab:"))
async def handle_task_tab_callback(call: types.CallbackQuery) -> None:
    """Переключает вкладку или страницу в реестре задач.

    Args:
        call: Объект CallbackQuery.
    """
    await call.answer()
    parts = call.data.split(":")
    tab = parts[1] if len(parts) > 1 else "assigned"
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    chat_id = call.message.chat.id
    user = await get_user_by_chat_id(chat_id)
    if not user:
        if call.message:
            await call.message.answer("Сессия истекла. Пожалуйста, выполните /start")
        return

    tasks_list, cur_page, total_pages = await fetch_tasks_page_data(user, tab=tab, page=page)
    text = format_task_list_text(tab, len(tasks_list))

    if call.message:
        await call.message.edit_text(
            text,
            reply_markup=get_tasks_filter_keyboard(
                active_tab=tab,
                page=cur_page,
                total_pages=total_pages,
                tasks_list=tasks_list,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("task_view:"))
async def handle_task_view_callback(call: types.CallbackQuery) -> None:
    """Отображает детальную карточку задачи.

    Args:
        call: Объект CallbackQuery с параметрами task_id:tab:page.
    """
    await call.answer()
    parts = call.data.split(":")
    task_id = int(parts[1])
    back_tab = parts[2] if len(parts) > 2 else "assigned"
    back_page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    chat_id = call.message.chat.id
    user = await get_user_by_chat_id(chat_id)
    if not user:
        return

    details = await fetch_task_details_data(task_id, user)
    if not details:
        await call.answer("Задача не найдена или была удалена.", show_alert=True)
        return

    text = format_task_card_text(details)
    kb = get_task_card_keyboard(
        task_id=task_id,
        can_accept=details["can_accept"],
        can_complete=details["can_complete"],
        absolute_url=details["absolute_url"],
        back_tab=back_tab,
        back_page=back_page,
    )

    if call.message:
        await call.message.edit_text(
            text,
            reply_markup=kb,
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("task_act:"))
async def handle_task_action_callback(call: types.CallbackQuery) -> None:
    """Выполняет действие над задачей («В работу», «Завершить»).

    Args:
        call: Объект CallbackQuery с параметрами action:task_id:back_tab:back_page.
    """
    parts = call.data.split(":")
    action = parts[1]
    task_id = int(parts[2])
    back_tab = parts[3] if len(parts) > 3 else "assigned"
    back_page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1

    chat_id = call.message.chat.id
    user = await get_user_by_chat_id(chat_id)
    if not user:
        await call.answer("Требуется авторизация!", show_alert=True)
        return

    success, msg = await execute_task_action(task_id, user, action)
    await call.answer(msg, show_alert=True)

    if success and call.message:
        # Перезагружаем карточку с обновленным состоянием
        details = await fetch_task_details_data(task_id, user)
        if details:
            text = format_task_card_text(details)
            kb = get_task_card_keyboard(
                task_id=task_id,
                can_accept=details["can_accept"],
                can_complete=details["can_complete"],
                absolute_url=details["absolute_url"],
                back_tab=back_tab,
                back_page=back_page,
            )
            await call.message.edit_text(
                text,
                reply_markup=kb,
                parse_mode="HTML",
            )


@router.callback_query(F.data.startswith("task_back:"))
async def handle_task_back_callback(call: types.CallbackQuery) -> None:
    """Возвращает из карточки задачи обратно в реестр.

    Args:
        call: Объект CallbackQuery с параметрами back_tab:back_page.
    """
    await call.answer()
    parts = call.data.split(":")
    tab = parts[1] if len(parts) > 1 else "assigned"
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    chat_id = call.message.chat.id
    user = await get_user_by_chat_id(chat_id)
    if not user:
        return

    tasks_list, cur_page, total_pages = await fetch_tasks_page_data(user, tab=tab, page=page)
    text = format_task_list_text(tab, len(tasks_list))

    if call.message:
        await call.message.edit_text(
            text,
            reply_markup=get_tasks_filter_keyboard(
                active_tab=tab,
                page=cur_page,
                total_pages=total_pages,
                tasks_list=tasks_list,
            ),
            parse_mode="HTML",
        )
