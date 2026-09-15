"""Сервисный модуль формирования данных для интерактивного дашборда Django Unfold."""

from datetime import date, timedelta
from typing import Any, Dict
import logging

from django.db.models import Count, Q
from django.http import HttpRequest

logger = logging.getLogger(__name__)


def dashboard_callback(request: HttpRequest, context: Dict[str, Any]) -> Dict[str, Any]:
    """Формирует расширенный контекст аналитики и KPI для дашборда Django Unfold.

    Args:
        request (HttpRequest): Объект HTTP-запроса от текущего пользователя.
        context (Dict[str, Any]): Исходный контекст представления дашборда Unfold.

    Returns:
        Dict[str, Any]: Модифицированный контекст со сводной статистикой по доменам
            (полеты, СЭД, финансы, задачи, кадры, почта).
    """
    today = date.today()
    week_ahead = today + timedelta(days=7)

    # 1. Планирование полетов (flight_planning)
    try:
        from flight_planning.models import FlightCrew, AircraftMovement
        active_crews_today = FlightCrew.objects.filter(date=today).count()
        crews_this_week = FlightCrew.objects.filter(date__gte=today, date__lte=week_ahead).count()
        recent_crews = list(
            FlightCrew.objects.select_related("aircraft", "mpd", "created_by")
            .order_by("-date", "-created_at")[:5]
        )
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик полетов для дашборда: {e}")
        active_crews_today = 0
        crews_this_week = 0
        recent_crews = []

    # 2. Документооборот СЭД (logistics_app)
    try:
        from logistics_app.models import DocFlowDocument
        docflow_on_review = DocFlowDocument.objects.filter(status="ON_REVIEW").count()
        docflow_total_month = DocFlowDocument.objects.filter(created_at__year=today.year, created_at__month=today.month).count()
        recent_docflow = list(
            DocFlowDocument.objects.select_related("doc_type", "initiator", "responsible")
            .order_by("-created_at")[:5]
        )
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик СЭД для дашборда: {e}")
        docflow_on_review = 0
        docflow_total_month = 0
        recent_docflow = []

    # 3. Служебные записки и HR (hrdepartment_app)
    try:
        from hrdepartment_app.models import ApprovalOficialMemoProcess
        pending_memos = ApprovalOficialMemoProcess.objects.filter(
            cancellation=False,
            accepted_accounting=False
        ).count()
        recent_memos = list(
            ApprovalOficialMemoProcess.objects.select_related("document", "document__person")
            .order_by("-start_date_trip")[:5]
        )
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик HR для дашборда: {e}")
        pending_memos = 0
        recent_memos = []

    # 4. Задачи и поручения (tasks_app)
    try:
        from tasks_app.models import Task, TaskStatus
        in_progress_tasks = Task.objects.filter(status__in=[TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED, TaskStatus.ON_REVIEW]).count()
        overdue_tasks = Task.objects.filter(status=TaskStatus.OVERDUE).count()
        recent_tasks = list(
            Task.objects.select_related("user", "responsible", "category")
            .order_by("-created_at")[:5]
        )
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик задач для дашборда: {e}")
        in_progress_tasks = 0
        overdue_tasks = 0
        recent_tasks = []

    # 5. Пользователи и корпоративная почта (customers_app & mailbox_app)
    try:
        from customers_app.models import DataBaseUser
        total_active_users = DataBaseUser.objects.filter(is_active=True, is_ppa=False).count()
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик пользователей для дашборда: {e}")
        total_active_users = 0

    try:
        from mailbox_app.models import ScheduledEmail
        scheduled_emails_count = ScheduledEmail.objects.filter(status="PENDING").count()
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик почты для дашборда: {e}")
        scheduled_emails_count = 0

    # 6. Финансы и договоры (finance_app & contracts_app)
    try:
        from finance_app.models import PaymentSchedule, FinancialContract
        upcoming_payments_count = PaymentSchedule.objects.filter(
            payment_date__gte=today,
            payment_date__lte=week_ahead,
            status="PLANNED"
        ).count()
    except Exception as e:
        logger.warning(f"Ошибка сбора метрик финансов для дашборда: {e}")
        upcoming_payments_count = 0

    context.update({
        "kpi_metrics": {
            "active_crews_today": active_crews_today,
            "crews_this_week": crews_this_week,
            "docflow_on_review": docflow_on_review,
            "docflow_total_month": docflow_total_month,
            "pending_memos": pending_memos,
            "in_progress_tasks": in_progress_tasks,
            "overdue_tasks": overdue_tasks,
            "total_active_users": total_active_users,
            "scheduled_emails_count": scheduled_emails_count,
            "upcoming_payments_count": upcoming_payments_count,
        },
        "recent_crews": recent_crews,
        "recent_docflow": recent_docflow,
        "recent_memos": recent_memos,
        "recent_tasks": recent_tasks,
    })

    return context
