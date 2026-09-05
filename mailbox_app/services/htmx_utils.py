"""Утилиты и миксины для бесшовной интеграции HTMX в почтовом приложении mailbox_app.

Модуль предоставляет вспомогательные функции проверки HTMX-запросов,
генерации заголовков управления, выбора шаблонов-фрагментов (partials)
и миксин двухрежимного рендеринга HtmxResponseMixin.
"""

from typing import Any, Dict, List, Optional
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def is_htmx_request(request: HttpRequest) -> bool:
    """Проверяет, был ли входящий HTTP-запрос инициирован библиотекой HTMX.

    Определяет наличие стандартного заголовка `HX-Request: true` в заголовках
    HTTP-запроса или в словаре метаданных WSGI/ASGI `HTTP_HX_REQUEST`.

    Args:
        request (HttpRequest): Объект входящего запроса Django.

    Returns:
        bool: True, если запрос отправлен через HTMX, иначе False.

    Example:
        >>> if is_htmx_request(request):
        ...     return render(request, "mailbox_app/partials/_folder_content.html", context)
    """
    if not request:
        return False
    return (
        request.headers.get("HX-Request") == "true"
        or request.META.get("HTTP_HX_REQUEST") == "true"
    )


def get_htmx_target(request: HttpRequest) -> str:
    """Возвращает идентификатор целевого DOM-элемента HTMX-запроса.

    Извлекает значение заголовка `HX-Target` (например, 'mailboxMainContent'
    или 'folderBadge_INBOX').

    Args:
        request (HttpRequest): Объект входящего запроса Django.

    Returns:
        str: ID целевого DOM-элемента без символа '#', либо пустая строка.
    """
    if not request:
        return ""
    return request.headers.get("HX-Target") or request.META.get("HTTP_HX_TARGET", "")


def get_htmx_trigger(request: HttpRequest) -> str:
    """Возвращает идентификатор элемента, инициировавшего HTMX-запрос.

    Извлекает значение заголовка `HX-Trigger`.

    Args:
        request (HttpRequest): Объект входящего запроса Django.

    Returns:
        str: ID элемента-триггера либо пустая строка.
    """
    if not request:
        return ""
    return request.headers.get("HX-Trigger") or request.META.get("HTTP_HX_TRIGGER", "")


def render_htmx(
    request: HttpRequest,
    full_template: str,
    partial_template: str,
    context: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> HttpResponse:
    """Выполняет двухрежимный рендеринг страницы: partial для HTMX и полный шаблон для прямого захода.

    Если запрос пришел от HTMX (`HX-Request: true`), выполняется рендеринг
    только частичного шаблона-фрагмента (`partial_template`), не содержащего
    тегов <html>, <head> и глобального меню.
    При обычном запросе (прямой переход по ссылке, открытие вкладки, F5)
    рендерится полноценная страница (`full_template`).

    Args:
        request (HttpRequest): Объект запроса Django.
        full_template (str): Путь к полному шаблону страницы (например, 'mailbox_app/folder.html').
        partial_template (str): Путь к частичному шаблону (например, 'mailbox_app/partials/_folder_content.html').
        context (Optional[Dict[str, Any]]): Словарь контекста для рендеринга шаблона.
        **kwargs: Дополнительные именованные параметры, передаваемые в django.shortcuts.render.

    Returns:
        HttpResponse: Сгенерированный HTTP-ответ с HTML-разметкой.
    """
    if context is None:
        context = {}

    template_to_use = partial_template if is_htmx_request(request) else full_template
    return render(request, template_to_use, context, **kwargs)


def htmx_redirect(url: str) -> HttpResponse:
    """Формирует HTTP-ответ с клиентским HTMX-перенаправлением через заголовок HX-Redirect.

    Позволяет выполнить переход пользователя на новый URL на стороне клиента
    без перезагрузки базового каркаса страницы, если клиент поддерживает HTMX.

    Args:
        url (str): Целевой URL для перенаправления.

    Returns:
        HttpResponse: Ответ со статусом 200/204 и заголовком HX-Redirect.
    """
    response = HttpResponse(status=204)
    response["HX-Redirect"] = url
    return response


class HtmxResponseMixin:
    """Миксин для Class-Based Views (CBV), поддерживающий двухрежимный выбор шаблона.

    Автоматически переключает шаблон на `partial_template_name`, если запрос
    поступил от HTMX, сохраняя `template_name` для стандартных прямых обращений.

    Attributes:
        partial_template_name (Optional[str]): Путь к частичному фрагменту шаблона.
    """

    partial_template_name: Optional[str] = None

    def get_template_names(self) -> List[str]:
        """Возвращает список имен шаблонов в зависимости от типа запроса.

        Returns:
            List[str]: Список путей к шаблонам для рендеринга.
        """
        if is_htmx_request(self.request) and self.partial_template_name:
            return [self.partial_template_name]
        return super().get_template_names()
