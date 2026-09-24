# -*- coding: utf-8 -*-
"""Асинхронные задачи Celery для взаимодействия с Telegram Bot API."""

import logging
import os
from typing import Any, Dict, Optional, Union

from celery import shared_task
import requests

from telegram_app.services.telegram_service import UniversalTelegramService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="telegram_app.tasks.send_universal_telegram_task",
)
def send_universal_telegram_task(
    self,
    chat_id: Union[str, int],
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
    disable_web_page_preview: bool = False,
) -> bool:
    """Асинхронная задача отправки текстового сообщения в Telegram с автоматическим retry.

    Args:
        self: Экземпляр текущей задачи Celery.
        chat_id: Идентификатор целевого чата.
        text: Текст сообщения.
        parse_mode: Режим форматирования текста ('HTML'). Defaults to 'HTML'.
        reply_markup: Опциональная разметка кнопок (InlineKeyboardMarkup). Defaults to None.
        disable_web_page_preview: Отключение генерации превью для ссылок. Defaults to False.

    Returns:
        bool: True при успешной отправке.

    Raises:
        self.retry: При сетевых сбоях и ошибках взаимодействия с Telegram API.
    """
    logger.info(
        "[Celery:Telegram] Попытка %d/%d отправки сообщения в чат %s",
        self.request.retries + 1,
        self.max_retries + 1,
        chat_id,
    )

    success, error_msg = UniversalTelegramService.send_message_sync(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_web_page_preview,
    )

    if not success:
        logger.warning(
            "[Celery:Telegram] Ошибка отправки в чат %s: %s. Планирование повтора...",
            chat_id,
            error_msg,
        )
        countdown = (2 ** self.request.retries) * 5
        raise self.retry(
            exc=requests.exceptions.RequestException(error_msg),
            countdown=countdown,
        )

    return True


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="telegram_app.tasks.send_universal_telegram_document_task",
)
def send_universal_telegram_document_task(
    self,
    chat_id: Union[str, int],
    document_path: str,
    caption: Optional[str] = None,
    parse_mode: str = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
    auto_cleanup: bool = False,
) -> bool:
    """Асинхронная задача отправки документа в Telegram с поддержкой удаления файла.

    Args:
        self: Экземпляр текущей задачи Celery.
        chat_id: Идентификатор целевого чата.
        document_path: Абсолютный путь к файлу на сервере.
        caption: Опциональный текст подписи к файлу. Defaults to None.
        parse_mode: Режим разметки подписи. Defaults to 'HTML'.
        reply_markup: Опциональная разметка inline-кнопок. Defaults to None.
        auto_cleanup: Удалить ли локальный файл после успешной отправки. Defaults to False.

    Returns:
        bool: True при успешной отправке.

    Raises:
        self.retry: При сбоях отправки документа.
    """
    logger.info(
        "[Celery:TelegramDoc] Отправка файла %s в чат %s (попытка %d)",
        document_path,
        chat_id,
        self.request.retries + 1,
    )

    success, error_msg = UniversalTelegramService.send_document_sync(
        chat_id=chat_id,
        document_path=document_path,
        caption=caption,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )

    if not success:
        logger.warning(
            "[Celery:TelegramDoc] Сбой отправки документа в чат %s: %s",
            chat_id,
            error_msg,
        )
        countdown = (2 ** self.request.retries) * 5
        raise self.retry(
            exc=requests.exceptions.RequestException(error_msg),
            countdown=countdown,
        )

    if auto_cleanup and os.path.exists(document_path):
        try:
            os.remove(document_path)
            logger.info("[Celery:TelegramDoc] Временный файл %s успешно удален", document_path)
        except OSError as cleanup_err:
            logger.warning("[Celery:TelegramDoc] Не удалось удалить временный файл %s: %s", document_path, cleanup_err)

    return True
