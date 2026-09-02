"""Селекторы аналитики, сводных показателей и онлайн-мониторинга для панели руководителя."""

from typing import Dict, Any, List, Optional
from django.db.models import Count, Avg, Q, F
from django.utils import timezone

from testing_app.models import (
    Testing,
    TestingGroup,
    TestingAssignment,
    TestingAttempt,
    Question,
    QuestionCategory,
)


def get_dashboard_kpi_metrics(testing_id: Optional[int] = None) -> Dict[str, Any]:
    """Рассчитывает ключевые показатели эффективности (KPI) по тестированию.

    Args:
        testing_id (Optional[int]): ID конкретного мероприятия или None для всей компании.

    Returns:
        Dict[str, Any]: Сводная статистика участников, статусов сдачи и процентов.
    """
    qs = TestingAssignment.objects.all()
    if testing_id:
        qs = qs.filter(testing_id=testing_id)

    total_assigned = qs.count()
    passed_count = qs.filter(status=TestingAssignment.Status.PASSED).count()
    in_progress_count = qs.filter(status=TestingAssignment.Status.IN_PROGRESS).count()
    not_started_count = qs.filter(status=TestingAssignment.Status.NOT_STARTED).count()
    failed_count = qs.filter(status=TestingAssignment.Status.FAILED).count()
    on_control_count = qs.filter(is_on_control=True).count()

    pass_rate = round((passed_count / float(total_assigned)) * 100, 1) if total_assigned > 0 else 0.0

    return {
        "total_assigned": total_assigned,
        "passed_count": passed_count,
        "in_progress_count": in_progress_count,
        "not_started_count": not_started_count,
        "failed_count": failed_count,
        "on_control_count": on_control_count,
        "pass_rate": pass_rate,
    }


def get_attempts_funnel_analytics(testing_id: Optional[int] = None) -> Dict[str, int]:
    """Формирует воронку успешности попыток (с какой попытки сдан тест).

    Args:
        testing_id (Optional[int]): ID конкретного мероприятия или None.

    Returns:
        Dict[str, int]: Количество успешных сдач, разбитых по номеру попытки (1..5).
    """
    qs = TestingAttempt.objects.filter(is_passed=True)
    if testing_id:
        qs = qs.filter(assignment__testing_id=testing_id)

    funnel = {
        "attempt_1": qs.filter(attempt_number=1).count(),
        "attempt_2": qs.filter(attempt_number=2).count(),
        "attempt_3": qs.filter(attempt_number=3).count(),
        "attempt_4": qs.filter(attempt_number=4).count(),
        "attempt_5": qs.filter(attempt_number__gte=5).count(),
    }
    return funnel


def get_groups_comparison_analytics(testing_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Формирует сравнительную статистику по двум группам аттестуемых.

    Args:
        testing_id (Optional[int]): ID мероприятия или None.

    Returns:
        List[Dict[str, Any]]: Метрики по Группе 1 (Обеспечение ТО ВС) и Группе 2 (Выполнение ТО ВС).
    """
    groups_data = []
    groups_qs = TestingGroup.objects.all()
    if testing_id:
        groups_qs = groups_qs.filter(testing_id=testing_id)

    # Уникальные коды групп
    for code, label in TestingGroup.Code.choices:
        assignments = TestingAssignment.objects.filter(group__code=code)
        if testing_id:
            assignments = assignments.filter(testing_id=testing_id)

        total = assignments.count()
        passed = assignments.filter(status=TestingAssignment.Status.PASSED).count()
        in_progress = assignments.filter(status=TestingAssignment.Status.IN_PROGRESS).count()
        rate = round((passed / float(total)) * 100, 1) if total > 0 else 0.0

        groups_data.append({
            "code": code,
            "name": label,
            "total": total,
            "passed": passed,
            "in_progress": in_progress,
            "pass_rate": rate,
        })

    return groups_data


def get_divisions_breakdown_analytics(testing_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Формирует срез показателей сдачи в разрезе подразделений компании.

    Args:
        testing_id (Optional[int]): ID мероприятия или None.

    Returns:
        List[Dict[str, Any]]: Список подразделений с долей сдавших сотрудников.
    """
    qs = TestingAssignment.objects.all()
    if testing_id:
        qs = qs.filter(testing_id=testing_id)

    divisions = qs.values("assigned_division_title").annotate(
        total=Count("id"),
        passed=Count("id", filter=Q(status=TestingAssignment.Status.PASSED)),
        in_progress=Count("id", filter=Q(status=TestingAssignment.Status.IN_PROGRESS)),
        failed=Count("id", filter=Q(status=TestingAssignment.Status.FAILED))
    ).order_by("-total")

    results = []
    for div in divisions:
        title = div["assigned_division_title"] or "Не указано"
        tot = div["total"]
        pas = div["passed"]
        rate = round((pas / float(tot)) * 100, 1) if tot > 0 else 0.0
        results.append({
            "division_title": title,
            "total": tot,
            "passed": pas,
            "in_progress": div["in_progress"],
            "failed": div["failed"],
            "pass_rate": rate,
        })

    return results


def get_top_hardest_questions(limit: int = 5) -> List[Dict[str, Any]]:
    """Возвращает список наиболее сложных вопросов с наименьшим процентом правильных ответов.

    Позволяет выявить пробелы в знаниях персонала для организации дообучения.

    Args:
        limit (int): Количество вопросов для выборки.

    Returns:
        List[Dict[str, Any]]: Список сложных вопросов со статистикой показов и успешности.
    """
    # Выбираем вопросы, использованные хотя бы 2 раза
    questions = Question.objects.filter(
        status=Question.Status.ACTIVE,
        times_used__gte=2
    ).select_related("category")

    q_list = []
    for q in questions:
        rate = q.success_rate
        q_list.append({
            "id": q.id,
            "category_name": q.category.name,
            "text": q.text,
            "times_used": q.times_used,
            "times_correct": q.times_correct,
            "success_rate": rate,
            "difficulty": q.get_difficulty_display(),
        })

    # Сортируем по возрастанию процента успеха (самые сложные первыми)
    q_list.sort(key=lambda x: (x["success_rate"], -x["times_used"]))
    return q_list[:limit]


def get_live_active_sessions(testing_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Возвращает список онлайн-сессий сотрудников, сдающих тест прямо сейчас.

    Args:
        testing_id (Optional[int]): ID мероприятия или None.

    Returns:
        List[Dict[str, Any]]: Список активных сессий с прогрессом и таймером.
    """
    active_attempts = TestingAttempt.objects.filter(
        status=TestingAttempt.Status.IN_PROGRESS
    ).select_related(
        "assignment__employee",
        "assignment__testing",
        "assignment__group"
    ).prefetch_related(
        "answers"
    ).order_by("-started_at")

    if testing_id:
        active_attempts = active_attempts.filter(assignment__testing_id=testing_id)

    sessions = []
    now = timezone.now()

    for att in active_attempts:
        rem_seconds = att.get_remaining_seconds()
        # Если время истекло, пропускаем или помечаем
        if rem_seconds <= 0:
            continue

        answered = att.answers.filter(selected_option_id__isnull=False).count()
        total_q = att.total_questions or 1
        pct = round((answered / float(total_q)) * 100)

        mins = rem_seconds // 60
        secs = rem_seconds % 60
        timer_str = f"{mins:02d}:{secs:02d}"

        sessions.append({
            "attempt_id": att.id,
            "employee_name": att.assignment.employee.get_full_name(),
            "job_title": att.assignment.assigned_job_title,
            "division_title": att.assignment.assigned_division_title,
            "testing_title": att.assignment.testing.title,
            "group_name": att.assignment.group.name,
            "attempt_number": att.attempt_number,
            "started_at": att.started_at,
            "remaining_seconds": rem_seconds,
            "timer_display": timer_str,
            "answered_count": answered,
            "total_questions": total_q,
            "progress_percent": pct,
        })

    return sessions
