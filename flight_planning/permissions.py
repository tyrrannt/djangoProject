"""Модуль управления правами доступа и авторизации для приложения flight_planning (Летно-производственный комплекс).

Определяет константы ролевых групп, доменные функции проверки полномочий на основе
принадлежности сотрудников (division_affiliation / Летный / Инженерный / Общий состав),
декораторы для представлений (Function-Based Views) и классы разрешений для Django REST Framework (DRF).
"""

from functools import wraps
from typing import Callable, Any, Optional

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


# Названия ролевых групп Летно-производственного комплекса (ЛПК)
GROUP_LPC_MANAGEMENT = "[ЛПК] Руководство"
GROUP_LPC_FLIGHT_PLANNERS = "[ЛПК] Диспетчеры планирования"
GROUP_LPC_TECH_SERVICE = "[ЛПК] Инженерная служба (ИАС)"
GROUP_LPC_FLIGHT_SERVICE = "[ЛПК] Летная служба"
GROUP_LPC_HR_SAFETY = "[ЛПК] Кадры и охрана труда"
GROUP_LPC_CREW = "[ЛПК] Летный состав"

# Группы для обратной совместимости с историческими записями БД
GROUP_LEGACY_PLANNERS = "Планирование полетов"
GROUP_LEGACY_MANAGEMENT = "Руководство полетов"
GROUP_LEGACY_CREW = "Летный состав"
GROUP_COMPANY_LEADERSHIP = "Руководство"
GROUP_HR = "Отдел кадров"


def get_employee_affiliation_code(employee: Any) -> str:
    """Определяет символьный код принадлежности сотрудника к составу компании.

    Последовательно анализирует:
    1. division_affiliation в связанной должности сотрудника (Job);
    2. type_of_job в модели Job;
    3. Ключевые слова в наименовании должности сотрудника.

    Args:
        employee: Экземпляр пользователя (DataBaseUser) или объект с профилем работы.

    Returns:
        str: Код состава:
            - 'flight_crew': Летный состав (пилоты, бортмеханики, штурманы);
            - 'tech_crew': Инженерно-технический состав (ИАС, авиатехники, инженеры ТО);
            - 'general': Общий состав (руководство, кадры, прочий персонал).
    """
    if not employee:
        return "general"

    profile = getattr(employee, "user_work_profile", None)
    job = getattr(profile, "job", None) if profile else None
    if not job:
        return "general"

    # 1. Приоритетная проверка через справочник division_affiliation
    affil = getattr(job, "division_affiliation", None)
    if affil:
        affil_name = (getattr(affil, "name", "") or "").lower()
        if affil.pk == 2 or "летн" in affil_name:
            return "flight_crew"
        if affil.pk == 3 or "инженер" in affil_name:
            return "tech_crew"
        if affil.pk == 1 or "общ" in affil_name:
            return "general"

    # 2. Проверка через системное поле type_of_job
    type_of_job = getattr(job, "type_of_job", None)
    if type_of_job == "1":
        return "flight_crew"
    if type_of_job == "2":
        return "tech_crew"
    if type_of_job == "0":
        return "general"

    # 3. Fallback: анализ ключевых слов в наименовании должности
    job_name = (getattr(job, "name", "") or "").lower()
    flight_keywords = ("пилот", "командир", "квс", "бортмеханик", "бортинженер", "инструктор", "штурман", "летчик")
    if any(kw in job_name for kw in flight_keywords):
        return "flight_crew"

    tech_keywords = ("авиатехник", "техник по экспл", "инженер по экспл", "инженер отк", "инженер по то", "инженер-механик")
    if any(kw in job_name for kw in tech_keywords):
        return "tech_crew"

    return "general"


def is_leadership_viewer(user: Any) -> bool:
    """Проверяет, находится ли пользователь в статусе руководства с режимом «Только чтение».

    Пользователи групп руководства компании видят абсолютно все разделы, графики,
    перемещения ВС и допуски, но защищены от случайного редактирования (кнопки скрыты).
    Суперпользователь не является ограниченным наблюдателем и имеет полные права.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь входит в группу руководства и не является суперпользователем.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    leadership_groups = {GROUP_LPC_MANAGEMENT, GROUP_COMPANY_LEADERSHIP, GROUP_LEGACY_MANAGEMENT}
    return user.groups.filter(name__in=leadership_groups).exists()


def can_approve_flight_planning(user: Any) -> bool:
    """Проверяет право пользователя утверждать официальный план расстановки экипажей.

    Утверждать документы имеют право суперпользователи и члены руководящих групп.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True при наличии полномочий на утверждение документа.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.has_perm("flight_planning.can_approve_flight_planning"):
        return True
    leadership_groups = {GROUP_LPC_MANAGEMENT, GROUP_COMPANY_LEADERSHIP, GROUP_LEGACY_MANAGEMENT}
    return user.groups.filter(name__in=leadership_groups).exists()


def can_manage_flight_crews(user: Any) -> bool:
    """Проверяет право на управление шахматкой экипажей и назначениями полетов.

    Доступно диспетчерам планирования и суперпользователям.
    Для руководства в режиме наблюдателя возвращает False.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь может создавать/редактировать экипажи.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_leadership_viewer(user):
        return False
    if user.has_perm("flight_planning.can_manage_flight_planning"):
        return True
    planner_groups = {GROUP_LPC_FLIGHT_PLANNERS, GROUP_LEGACY_PLANNERS}
    return user.groups.filter(name__in=planner_groups).exists()


def is_flight_planner(user: Any) -> bool:
    """Псевдоним can_manage_flight_crews для обратной совместимости."""
    return can_manage_flight_crews(user)


def can_edit_aircraft_movements(user: Any) -> bool:
    """Проверяет право на добавление, изменение и удаление записей журнала перемещений ВС.

    Доступно сотрудникам Инженерной службы (ИАС), диспетчерам планирования и суперадминистраторам.
    Руководству компании доступно только чтение.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True, если пользователь имеет право редактировать дислокацию ВС.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_leadership_viewer(user):
        return False
    if user.has_perm("flight_planning.can_manage_aircraft_movements"):
        return True

    allowed_groups = {
        GROUP_LPC_TECH_SERVICE,
        GROUP_LPC_FLIGHT_PLANNERS,
        GROUP_LEGACY_PLANNERS,
    }
    return user.groups.filter(name__in=allowed_groups).exists()


def can_edit_checks_for_employee(user: Any, target_employee: Any) -> bool:
    """Проверяет право пользователя редактировать периодические проверки конкретного сотрудника.

    Разграничивает доступ по доменам ответственности на основе division_affiliation:
    - Летный состав: редактируют диспетчеры и Летная служба;
    - Инженерный состав: редактирует Инженерная служба (ИАС) и диспетчеры;
    - Общий состав: редактируют Кадры, Охрана труда и диспетчеры.

    Args:
        user: Текущий аутентифицированный пользователь (субъект).
        target_employee: Сотрудник, чьи данные редактируются (объект).

    Returns:
        bool: True, если редактирование разрешено.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_leadership_viewer(user):
        return False

    affil_code = get_employee_affiliation_code(target_employee)

    # 1. Летный состав
    if affil_code == "flight_crew":
        flight_editor_groups = {
            GROUP_LPC_FLIGHT_PLANNERS,
            GROUP_LPC_FLIGHT_SERVICE,
            GROUP_LEGACY_PLANNERS,
        }
        return user.groups.filter(name__in=flight_editor_groups).exists()

    # 2. Инженерный состав (ИАС)
    if affil_code == "tech_crew":
        tech_editor_groups = {
            GROUP_LPC_TECH_SERVICE,
            GROUP_LPC_FLIGHT_PLANNERS,
            GROUP_LEGACY_PLANNERS,
        }
        return user.groups.filter(name__in=tech_editor_groups).exists()

    # 3. Общий состав / кадры / охрана труда
    general_editor_groups = {
        GROUP_LPC_HR_SAFETY,
        GROUP_HR,
        GROUP_LPC_FLIGHT_PLANNERS,
        GROUP_LEGACY_PLANNERS,
    }
    return user.groups.filter(name__in=general_editor_groups).exists()


def can_edit_employee_statuses(user: Any, target_employee: Any) -> bool:
    """Проверяет право пользователя на учет состояний (отпуска, больничные, резерв) сотрудника.

    Работает по аналогичной доменной модели division_affiliation, что и учет проверок.

    Args:
        user: Текущий аутентифицированный пользователь.
        target_employee: Целевой сотрудник.

    Returns:
        bool: True, если редактирование состояния разрешено.
    """
    return can_edit_checks_for_employee(user, target_employee)


def can_manage_lpc_access(user: Any) -> bool:
    """Проверяет право на назначение и изменение ролей в Летно-производственном комплексе.

    Доступно суперпользователям и членам группы «Руководство».

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True при наличии прав администратора доступа.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=[GROUP_LPC_MANAGEMENT, GROUP_COMPANY_LEADERSHIP]).exists()


def can_view_flight_reports(user: Any) -> bool:
    """Проверяет право пользователя на просмотр аналитических отчетов ЛПК.

    Отчеты доступны руководству, диспетчерам планирования и инженерной службе.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True при наличии прав на просмотр отчетов.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.has_perm("flight_planning.can_view_flight_reports"):
        return True

    allowed_groups = {
        GROUP_LPC_MANAGEMENT,
        GROUP_COMPANY_LEADERSHIP,
        GROUP_LEGACY_MANAGEMENT,
        GROUP_LPC_FLIGHT_PLANNERS,
        GROUP_LEGACY_PLANNERS,
        GROUP_LPC_TECH_SERVICE,
    }
    return user.groups.filter(name__in=allowed_groups).exists()


def can_view_flight_planning(user: Any) -> bool:
    """Проверяет базовое право пользователя на просмотр раздела Летно-производственного комплекса.

    Доступ имеют: диспетчеры, руководство, летный состав, инженерная служба, кадры.

    Args:
        user: Экземпляр пользователя Django.

    Returns:
        bool: True, если раздел должен отображаться в меню и быть доступен для чтения.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.has_perm("flight_planning.can_view_flight_planning"):
        return True

    allowed_groups = {
        GROUP_LPC_MANAGEMENT,
        GROUP_COMPANY_LEADERSHIP,
        GROUP_LEGACY_MANAGEMENT,
        GROUP_LPC_FLIGHT_PLANNERS,
        GROUP_LEGACY_PLANNERS,
        GROUP_LPC_TECH_SERVICE,
        GROUP_LPC_FLIGHT_SERVICE,
        GROUP_LPC_HR_SAFETY,
        GROUP_LPC_CREW,
        GROUP_LEGACY_CREW,
    }
    if user.groups.filter(name__in=allowed_groups).exists():
        return True

    # Автоматический доступ для сотрудников летного или инженерного состава по их профилю
    affil_code = get_employee_affiliation_code(user)
    if affil_code in ("flight_crew", "tech_crew"):
        return True

    return False


# =====================================================================
# ДЕКОРАТОРЫ ПРЕДСТАВЛЕНИЙ (FBV DECORATORS)
# =====================================================================

def flight_crew_planner_required(view_func: Callable) -> Callable:
    """Декоратор представления, требующий прав диспетчера планирования полетов."""
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Требуется авторизация."}, status=401)
            raise PermissionDenied("Требуется авторизация.")

        if not can_manage_flight_crews(request.user):
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Недостаточно прав. Требуются полномочия диспетчера планирования полетов."}, status=403)
            raise PermissionDenied("У вас нет прав для управления экипажами и расстановкой полетов.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def flight_planner_required(view_func: Callable) -> Callable:
    """Псевдоним flight_crew_planner_required для обратной совместимости."""
    return flight_crew_planner_required(view_func)


def aircraft_movements_editor_required(view_func: Callable) -> Callable:
    """Декоратор представления, требующий прав на редактирование журнала перемещений ВС."""
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Требуется авторизация."}, status=401)
            raise PermissionDenied("Требуется авторизация.")

        if not can_edit_aircraft_movements(request.user):
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight_planning/api/"):
                return JsonResponse({"error": "Недостаточно прав. Требуются полномочия Инженерной службы (ИАС) или диспетчера."}, status=403)
            raise PermissionDenied("У вас нет прав для редактирования журнала перемещений воздушных судов.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def flight_reports_required(view_func: Callable) -> Callable:
    """Декоратор представления для доступа к аналитическим отчетам."""
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для просмотра отчетов.")

        if not can_view_flight_reports(request.user):
            raise PermissionDenied("У вас нет прав для просмотра аналитических отчетов Летно-производственного комплекса.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def flight_planning_view_required(view_func: Callable) -> Callable:
    """Декоратор представления для базового просмотра разделов ЛПК."""
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация.")

        if not can_view_flight_planning(request.user):
            raise PermissionDenied("У вас нет прав для доступа к разделу Летно-производственного комплекса.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def lpc_access_manager_required(view_func: Callable) -> Callable:
    """Декоратор представления для управления правами доступа и ролями ЛПК."""
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight/api/"):
                return JsonResponse({"status": "error", "error": "Требуется авторизация."}, status=401)
            raise PermissionDenied("Требуется авторизация.")

        if not can_manage_lpc_access(request.user):
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.startswith("/flight/api/"):
                return JsonResponse({"status": "error", "error": "Настройка ролей и прав доступа ЛПК разрешена только Руководству и администраторам."}, status=403)
            raise PermissionDenied("Настройка ролей и прав доступа ЛПК разрешена только Руководству и администраторам.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


# =====================================================================
# DRF PERMISSION CLASSES
# =====================================================================

class IsFlightCrewPlanner(BasePermission):
    """Класс разрешений DRF для управления экипажами."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and can_manage_flight_crews(request.user))


class IsFlightPlanner(BasePermission):
    """Псевдоним IsFlightCrewPlanner для обратной совместимости."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and can_manage_flight_crews(request.user))


class IsAircraftMovementEditor(BasePermission):
    """Класс разрешений DRF для редактирования журнала перемещений ВС."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and can_edit_aircraft_movements(request.user))


class CanViewReports(BasePermission):
    """Класс разрешений DRF для доступа к отчетам."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and can_view_flight_reports(request.user))


class CanViewFlightPlanning(BasePermission):
    """Класс разрешений DRF для базового просмотра данных ЛПК."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and can_view_flight_planning(request.user))
