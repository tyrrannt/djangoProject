# -*- coding: utf-8 -*-
"""Представления API для интерактивной ознакомительной экскурсии по порталу (Onboarding Tour)."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from customers_app.models import DataBaseUser


@login_required
@require_POST
def onboarding_complete_api(request: HttpRequest) -> JsonResponse:
    """Фиксирует в БД завершение или пропуск ознакомительной экскурсии текущим пользователем.

    Обновление выполняется напрямую через ``QuerySet.update()`` во избежание
    побочных эффектов сигналов ``post_save`` и лишних проверок профиля.

    Args:
        request (HttpRequest): Входящий авторизованный HTTP POST-запрос.

    Returns:
        JsonResponse: JSON-ответ со статусом ``ok``, флагом ``onboarding_completed=True``
        и ISO-меткой времени завершения ``completed_at``.
    """
    now = timezone.now()
    DataBaseUser.objects.filter(pk=request.user.pk).update(
        onboarding_completed=True,
        onboarding_completed_at=now,
    )
    return JsonResponse(
        {
            "status": "ok",
            "onboarding_completed": True,
            "completed_at": now.isoformat(),
        }
    )


@login_required
@require_POST
def onboarding_reset_api(request: HttpRequest) -> JsonResponse:
    """Сбрасывает отметку прохождения ознакомительной экскурсии для текущего пользователя.

    Args:
        request (HttpRequest): Входящий авторизованный HTTP POST-запрос.

    Returns:
        JsonResponse: JSON-ответ со статусом ``ok`` и флагом ``onboarding_completed=False``.
    """
    DataBaseUser.objects.filter(pk=request.user.pk).update(
        onboarding_completed=False,
        onboarding_completed_at=None,
    )
    return JsonResponse(
        {
            "status": "ok",
            "onboarding_completed": False,
        }
    )
