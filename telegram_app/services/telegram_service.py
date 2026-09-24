# -*- coding: utf-8 -*-
"""Универсальный сервис взаимодействия с Telegram Bot API.

Предоставляет централизованный API для отправки сообщений, документов и интерактивных
кнопок (Inline Keyboards) с поддержкой локального туннеля wireproxy (TELEGRAM_PROXY),
а также асинхронной постановки задач в очередь Celery.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class UniversalTelegramService:
    """Централизованный сервис отправки сообщений и документов в Telegram."""

    @classmethod
    def get_token(cls) -> str:
        """Возвращает актуальный токен бота из настроек Django.

        Returns:
            str: Токен Telegram-бота.
        """
        token = getattr(settings, "TELEGRAM_TOKEN", None) or getattr(settings, "API_TOKEN", None)
        return str(token).strip() if token else ""

    @classmethod
    def get_proxies(cls) -> Optional[Dict[str, str]]:
        """Возвращает конфигурацию прокси для requests при наличии TELEGRAM_PROXY.

        Returns:
            Optional[Dict[str, str]]: Словарь настроек прокси для HTTP/HTTPS или None.
        """
        proxy_url = getattr(settings, "TELEGRAM_PROXY", None) or getattr(settings, "WEATHER_PROXY", None)
        if proxy_url and str(proxy_url).strip():
            proxy_clean = str(proxy_url).strip()
            return {"http": proxy_clean, "https": proxy_clean}
        return None

    @classmethod
    def send_message_sync(
        cls,
        chat_id: Union[str, int],
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = False,
        timeout: int = 10,
    ) -> Tuple[bool, Optional[str]]:
        """Выполняет синхронную отправку текстового сообщения через Telegram Bot API.

        Args:
            chat_id: Идентификатор чата получателя (Telegram chat_id).
            text: Текст сообщения с разметкой HTML или Markdown.
            parse_mode: Режим парсинга разметки ('HTML', 'MarkdownV2', 'Markdown'). Defaults to 'HTML'.
            reply_markup: Опциональная разметка клавиатуры (inline_keyboard / reply_keyboard). Defaults to None.
            disable_web_page_preview: Отключить предпросмотр веб-ссылок. Defaults to False.
            timeout: Таймаут HTTP-запроса в секундах. Defaults to 10.

        Returns:
            Tuple[bool, Optional[str]]: Кортеж (успех_отправки, описание_ошибки_или_None).
        """
        token = cls.get_token()
        if not token:
            error_msg = "Telegram Bot Token не задан в настройках Django (TELEGRAM_TOKEN)."
            logger.error("[UniversalTelegram] %s", error_msg)
            return False, error_msg

        if not chat_id:
            error_msg = "Не указан chat_id получателя сообщения."
            logger.warning("[UniversalTelegram] %s", error_msg)
            return False, error_msg

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        proxies = cls.get_proxies()

        try:
            response = requests.post(url, json=payload, proxies=proxies, timeout=timeout)
            if response.status_code == 200:
                logger.info(
                    "[UniversalTelegram] Сообщение успешно отправлено в чат %s",
                    chat_id,
                )
                return True, None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(
                    "[UniversalTelegram] Ошибка отправки в чат %s: %s",
                    chat_id,
                    error_msg,
                )
                return False, error_msg
        except requests.exceptions.RequestException as exc:
            error_msg = f"Исключение сети при отправке в чат {chat_id}: {exc}"
            logger.error("[UniversalTelegram] %s", error_msg)
            return False, str(exc)

    @classmethod
    def send_document_sync(
        cls,
        chat_id: Union[str, int],
        document_path: str,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Tuple[bool, Optional[str]]:
        """Синхронно отправляет файл документа (PDF, XLSX, DOCX) в Telegram-чат.

        Args:
            chat_id: Идентификатор чата получателя.
            document_path: Абсолютный путь к файлу документа на диске.
            caption: Опциональная подпись к документу. Defaults to None.
            parse_mode: Режим разметки подписи ('HTML'). Defaults to 'HTML'.
            reply_markup: Опциональная inline-клавиатура. Defaults to None.
            timeout: Таймаут передачи файла в секундах. Defaults to 30.

        Returns:
            Tuple[bool, Optional[str]]: Кортеж (успех_отправки, описание_ошибки_или_None).
        """
        token = cls.get_token()
        if not token:
            error_msg = "Telegram Bot Token не задан в настройках Django."
            logger.error("[UniversalTelegram] %s", error_msg)
            return False, error_msg

        if not os.path.exists(document_path):
            error_msg = f"Файл документа не найден по пути: {document_path}"
            logger.error("[UniversalTelegram] %s", error_msg)
            return False, error_msg

        url = f"https://api.telegram.org/bot{token}/sendDocument"
        data: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "parse_mode": parse_mode,
        }
        if caption:
            data["caption"] = caption

        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        proxies = cls.get_proxies()

        try:
            with open(document_path, "rb") as doc_file:
                files = {"document": doc_file}
                response = requests.post(url, data=data, files=files, proxies=proxies, timeout=timeout)

            if response.status_code == 200:
                logger.info(
                    "[UniversalTelegram] Документ %s успешно отправлен в чат %s",
                    document_path,
                    chat_id,
                )
                return True, None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(
                    "[UniversalTelegram] Ошибка отправки документа в чат %s: %s",
                    chat_id,
                    error_msg,
                )
                return False, error_msg
        except requests.exceptions.RequestException as exc:
            error_msg = f"Сетевая ошибка при отправке документа в чат {chat_id}: {exc}"
            logger.error("[UniversalTelegram] %s", error_msg)
            return False, str(exc)

    @classmethod
    def send_message_async(
        cls,
        chat_id: Union[str, int],
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = False,
    ) -> bool:
        """Ставит задачу отправки текстового сообщения в фоновую очередь Celery.

        Args:
            chat_id: Идентификатор чата получателя.
            text: Текст сообщения.
            parse_mode: Формат разметки. Defaults to 'HTML'.
            reply_markup: Клавиатура или inline-кнопки. Defaults to None.
            disable_web_page_preview: Отключение превью ссылок. Defaults to False.

        Returns:
            bool: True, если задача успешно поставлена в очередь брокера, иначе False.
        """
        if not chat_id:
            logger.warning("[UniversalTelegram:Async] chat_id пуст, отправка пропущена.")
            return False

        try:
            from telegram_app.tasks import send_universal_telegram_task

            send_universal_telegram_task.delay(
                chat_id=str(chat_id).strip(),
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            logger.info(
                "[UniversalTelegram:Async] Задача отправки в чат %s поставлена в очередь Celery.",
                chat_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "[UniversalTelegram:Async] Брокер Celery недоступен при постановке задачи Telegram: %s. "
                "Пропуск фоновой отправки без падения веб-запроса.",
                exc,
            )
            return False

    @classmethod
    def send_document_async(
        cls,
        chat_id: Union[str, int],
        document_path: str,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        auto_cleanup: bool = False,
    ) -> bool:
        """Ставит задачу отправки документа в фоновую очередь Celery с опцией автоудаления.

        Args:
            chat_id: Идентификатор чата получателя.
            document_path: Абсолютный путь к файлу документа.
            caption: Подпись к документу. Defaults to None.
            parse_mode: Формат разметки подписи. Defaults to 'HTML'.
            reply_markup: Inline-клавиатура. Defaults to None.
            auto_cleanup: Удалить ли файл с диска после отправки. Defaults to False.

        Returns:
            bool: True при успешной постановке в очередь Celery, иначе False.
        """
        if not chat_id or not document_path:
            logger.warning("[UniversalTelegram:Async] chat_id или document_path пусты, отправка пропущена.")
            return False

        try:
            from telegram_app.tasks import send_universal_telegram_document_task

            send_universal_telegram_document_task.delay(
                chat_id=str(chat_id).strip(),
                document_path=document_path,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                auto_cleanup=auto_cleanup,
            )
            logger.info(
                "[UniversalTelegram:Async] Задача отправки документа %s в чат %s поставлена в Celery.",
                document_path,
                chat_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "[UniversalTelegram:Async] Ошибка постановки задачи отправки документа в Celery: %s",
                exc,
            )
            return False

    @staticmethod
    def build_inline_keyboard(rows: List[List[Dict[str, str]]]) -> Dict[str, Any]:
        """Универсальный строитель разметки InlineKeyboardMarkup для Telegram API.

        Args:
            rows: Список строк кнопок, где каждая кнопка — словарь:
                {"text": "Название", "url": "https://..."} или
                {"text": "Название", "callback_data": "data:123"}.

        Returns:
            Dict[str, Any]: Структура {"inline_keyboard": [...]}.

        Example:
            >>> UniversalTelegramService.build_inline_keyboard([
            ...     [{"text": "✅ Согласовать", "callback_data": "bpmemo_approve:42"},
            ...      {"text": "❌ Отклонить", "callback_data": "bpmemo_reject:42"}],
            ...     [{"text": "📄 Открыть СЗ", "url": "https://corp.barkol.ru/hr/bpmemo/42/update/"}]
            ... ])
        """
        return {"inline_keyboard": rows}
