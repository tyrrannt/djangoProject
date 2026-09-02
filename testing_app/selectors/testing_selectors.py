"""Селекторы данных модуля периодического тестирования сотрудников."""

from typing import List, Dict, Any, Optional
from django.db.models import QuerySet, Q, Max
from django.utils import timezone

from customers_app.models import DataBaseUser
from testing_app.models import (
    Testing,
    TestingAssignment,
    TestingAttempt,
    AttemptQuestion,
    UserAnswer,
)


def get_user_assignments(user: DataBaseUser) -> QuerySet:
    """Возвращает список всех назначенных тестирований для конкретного сотрудника.

    Включает связанные объекты мероприятий, групп и оптимизированный предрасчет
    попыток сдачи.

    Args:
        user (DataBaseUser): Сотрудник.

    Returns:
        QuerySet: Список объектов TestingAssignment с предзагруженными связями.
    """
    return TestingAssignment.objects.filter(
        employee=user
    ).select_related(
        "testing",
        "group"
    ).prefetch_related(
        "attempts"
    ).order_by("-testing__start_datetime")


def get_attempt_questions_for_test_engine(attempt: TestingAttempt) -> List[Dict[str, Any]]:
    """Формирует безопасный список вопросов для клиентского веб-интерфейса тестирования.

    Исключает признак правильности (is_correct) из вариантов ответов (защита от DevTools).
    Сопоставляет каждый вопрос с текущим сохраненным черновиком ответа пользователя.

    Args:
        attempt (TestingAttempt): Активная попытка тестирования.

    Returns:
        List[Dict[str, Any]]: Список словарей с полями:
            - 'id': ID снимка AttemptQuestion;
            - 'order_num': Порядковый номер вопроса в тесте (1..N);
            - 'category_name': Название категории;
            - 'question_text': Текст формулировки вопроса;
            - 'options': Список вариантов ответов (без флага is_correct);
            - 'selected_option_id': ID выбранного в черновике варианта (или None);
            - 'is_answered': Булев флаг, дан ли ответ.
    """
    answers_map = {
        ua.attempt_question_id: ua
        for ua in attempt.answers.all()
    }

    questions_list = []
    attempt_questions = attempt.questions.order_by("order_num")

    for aq in attempt_questions:
        user_answer = answers_map.get(aq.id)
        selected_opt_id = user_answer.selected_option_id if user_answer else None

        # Очищенные варианты без поля is_correct
        client_options = aq.get_client_options()

        questions_list.append({
            "id": aq.id,
            "order_num": aq.order_num,
            "category_name": aq.category_name,
            "question_text": aq.question_text,
            "options": client_options,
            "selected_option_id": selected_opt_id,
            "is_answered": selected_opt_id is not None,
        })

    return questions_list


def get_attempt_results_detail(attempt: TestingAttempt) -> Dict[str, Any]:
    """Возвращает детальные результаты завершенной попытки тестирования.

    Включает текст вопросов, выбранные ответы, правильные ответы и пояснения
    для анализа результатов после завершения теста.

    Args:
        attempt (TestingAttempt): Завершенная попытка.

    Returns:
        Dict[str, Any]: Детализация результатов с полным анализом ответов.
    """
    answers_map = {
        ua.attempt_question_id: ua
        for ua in attempt.answers.all()
    }

    detailed_questions = []
    attempt_questions = attempt.questions.order_by("order_num")

    for aq in attempt_questions:
        ua = answers_map.get(aq.id)
        selected_opt_id = ua.selected_option_id if ua else None
        is_correct = ua.is_correct if ua else False

        detailed_questions.append({
            "order_num": aq.order_num,
            "category_name": aq.category_name,
            "question_text": aq.question_text,
            "explanation": aq.explanation,
            "options": aq.options_snapshot,
            "selected_option_id": selected_opt_id,
            "is_correct": is_correct,
            "seconds_spent": ua.seconds_spent if ua else 0,
        })

    return {
        "attempt": attempt,
        "assignment": attempt.assignment,
        "testing": attempt.assignment.testing,
        "questions": detailed_questions,
        "correct_count": attempt.correct_answers_count,
        "total_questions": attempt.total_questions,
        "score_percentage": attempt.score_percentage,
        "is_passed": attempt.is_passed,
        "certificate_uuid": attempt.certificate_uuid,
        "result_number": attempt.result_number,
    }
