"""Модуль управления правами доступа и авторизации для приложения flight_planning.

Определяет константы групп пользователей, функции проверки полномочий,
декораторы для представлений (Function-Based Views) и классы разрешений
для Django REST Framework (DRF).
"""

from functools import wraps
from typing import Callable, Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


# Названия групп пользователей в системе
GROUP_FLIGHT_PLANNERS = "Планирование полетов"
GROUP_FLIGHT_MANAGEMENT = "Руководство полетов"
GROUP_FLIGHT_CREW = "Летный состав"


def is_flight_planner(user) -> bool:
    """Проверяет, обладает ли пользователь правами диспетчера/планировщика полетов.

    Полномочия диспетчера позволяют создавать, редактировать, перемещать и удалять
    экипажи, назначения и записи перемещений воздушных судов.

    Args:
        user (DataBaseUser): Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь является суперпользователем,
            обладает разрешением 'can_manage_flight_planning' или
            состоит в группе 'Планирование полетов', иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.has_perm("flight_planning.can_manage_flight_planning"):
        return True
    return user.groups.filter(name=GROUP_FLIGHT_PLANNERS).exists()


def can_view_flight_reports(user) -> bool:
    """Проверяет право пользователя на просмотр аналитических отчетов планирования.

    Отчеты доступны руководству и сотрудникам отдела планирования.

    Args:
        user (DataBaseUser): Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь имеет доступ к отчетам (планировщик, руководство
            или суперпользователь), иначе False.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_flight_planner(user):
        return True
    if user.has_perm("flight_planning.can_view_flight_reports"):
        return True
    return user.groups.filter(name=GROUP_FLIGHT_MANAGEMENT).exists()


def can_view_flight_planning(user) -> bool:
    """Проверяет базовое право пользователя на просмотр раздела планирования полетов.

    Доступ имеют сотрудники планирования, руководство и летный состав.

    Args:
        user (DataBaseUser): Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь аутентифицирован и имеет доступ к просмотру
            графиков/таблицы планирования.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_flight_planner(user) or can_view_flight_reports(user):
        return True
    if user.has_perm("flight_planning.can_view_flight_planning"):
        return True
    if user.groups.filter(name=GROUP_FLIGHT_CREW).exists():
        return True
    # Проверяем принадлежность к летному составу по профилю должности
    try:
        if (
            hasattr(user, "user_work_profile")
            and user.user_work_profile
            and user.user_work_profile.job
        ):
            job = user.user_work_profile.job
            if getattr(job, "type_of_job", None) == "1":
                return True
            job_name = (getattr(job, "name", "") or "").lower()
            if any(k in job_name for k in ("пилот", "командир", "квс", "бортмеханик", "бортинженер", "инструктор", "штурман", "летчик")):
                return True
    except Exception:
        pass
    return False


def flight_planner_required(view_func: Callable) -> Callable:
    """Декоратор представления, требующий прав планировщика/диспетчера полетов.

    При попытке доступа неавторизованного пользователя или пользователя без прав
    возвращает ошибку 403 Forbidden (JSON для API/AJAX запросов или PermissionDenied
    для обычных HTML-страниц).

    Args:
        view_func (Callable): Декорируемая функция представления.

    Returns:
        Callable: Обернутая функция представления.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Требуется авторизация."}, status=401)
            raise PermissionDenied("Требуется авторизация.")

        if not is_flight_planner(request.user):
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Недостаточно прав. Требуются права отдела планирования полетов."}, status=403)
            raise PermissionDenied("У вас нет прав для выполнения этой операции планирования полетов.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def flight_reports_required(view_func: Callable) -> Callable:
    """Декоратор представления для доступа к аналитическим отчетам.

    Args:
        view_func (Callable): Декорируемая функция представления отчета.

    Returns:
        Callable: Обернутая функция представления.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для просмотра отчетов.")

        if not can_view_flight_reports(request.user):
            raise PermissionDenied("У вас нет прав для просмотра аналитических отчетов по планированию полетов.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def flight_planning_view_required(view_func: Callable) -> Callable:
    """Декоратор представления для просмотра разделов планирования полетов.

    Args:
        view_func (Callable): Декорируемая функция представления.

    Returns:
        Callable: Обернутая функция представления.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация.")

        if not can_view_flight_planning(request.user):
            raise PermissionDenied("У вас нет прав для доступа к разделу планирования полетов.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


# DRF Permission Classes
class IsFlightPlanner(BasePermission):
    """Класс разрешений DRF для доступа только сотрудникам планирования."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Проверяет права пользователя на уровне запроса.

        Args:
            request (Request): Запрос DRF.
            view (APIView): Экземпляр представления DRF.

        Returns:
            bool: True при наличии прав планировщика, иначе False.
        """
        return bool(request.user and is_flight_planner(request.user))


class CanViewReports(BasePermission):
    """Класс разрешений DRF для доступа к отчетам (руководство и планировщики)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Проверяет права пользователя на просмотр отчетов в DRF.

        Args:
            request (Request): Запрос DRF.
            view (APIView): Экземпляр представления DRF.

        Returns:
            bool: True при наличии доступа к отчетам, иначе False.
        """
        return bool(request.user and can_view_flight_reports(request.user))


class CanViewFlightPlanning(BasePermission):
    """Класс разрешений DRF для базового просмотра данных планирования."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Проверяет базовые права на чтение данных планирования полетов.

        Args:
            request (Request): Запрос DRF.
            view (APIView): Экземпляр представления DRF.

        Returns:
            bool: True при наличии базовых прав на чтение, иначе False.
        """
        return bool(request.user and can_view_flight_planning(request.user))
