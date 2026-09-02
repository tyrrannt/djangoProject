"""Движок тестирования: алгоритм равномерного распределения, снимки вопросов, серверный таймер и черновики."""

import random
import uuid
from datetime import timedelta
from typing import Dict, Any, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from testing_app.models import (
    Testing,
    TestingAssignment,
    TestingAttempt,
    AttemptQuestion,
    UserAnswer,
    Question,
    AnswerOption,
    TestingCategorySetting,
    TestingAuditLog,
)


def start_or_resume_attempt(assignment: TestingAssignment, user=None) -> Tuple[TestingAttempt, bool]:
    """Запускает новую попытку тестирования или возвращает текущую активную.

    Проверяет:
    1. Мероприятие находится в статусе ACTIVE, либо текущее время входит в интервал проведения.
    2. Сотрудник еще не сдал тест (status != PASSED).
    3. Лимит попыток не исчерпан (attempts_used < max_attempts).
    4. Если есть незавершенная попытка с неистекшим серверным таймером — возвращает ее (resumed=True).
    5. Если у незавершенной попытки вышло время — принудительно завершает ее по таймауту и продолжает проверку.

    Args:
        assignment (TestingAssignment): Назначение сотрудника на тестирование.
        user (Optional[User]): Пользователь, инициирующий запуск.

    Raises:
        ValidationError: Если условия запуска попытки не соблюдены.

    Returns:
        Tuple[TestingAttempt, bool]: (Объект попытки, Признак возобновления ранее начатой попытки).
    """
    testing = assignment.testing
    now = timezone.now()

    # Проверка статуса мероприятия и временных рамок
    if testing.status != Testing.Status.ACTIVE:
        if not (testing.start_datetime <= now <= testing.end_datetime):
            raise ValidationError("Тестирование в данный момент недоступно: мероприятие не активно.")

    # Проверка: тест уже успешно сдан
    if assignment.status == TestingAssignment.Status.PASSED:
        raise ValidationError("Вы уже успешно сдали данное тестирование. Повторная сдача не требуется.")

    # Проверка текущих активных попыток со статусом IN_PROGRESS
    active_attempt = assignment.attempts.filter(status=TestingAttempt.Status.IN_PROGRESS).order_by("-id").first()
    if active_attempt:
        remaining = active_attempt.get_remaining_seconds()
        if remaining > 0:
            # Возобновляем текущую попытку
            return active_attempt, True
        else:
            # Время вышло, завершаем старую попытку по таймауту
            finish_attempt(active_attempt, reason=TestingAttempt.CompletionReason.TIME_EXPIRED)

    # Проверка лимита попыток
    if assignment.attempts_used >= testing.max_attempts:
        raise ValidationError(
            f"Вы исчерпали максимальное количество попыток ({testing.max_attempts}). "
            "Обратитесь к ответственному за тестирование."
        )

    # Создание новой попытки
    new_attempt = create_new_attempt(assignment, user=user)
    return new_attempt, False


def create_new_attempt(assignment: TestingAssignment, user=None) -> TestingAttempt:
    """Генерирует новую попытку тестирования на основе алгоритма равномерного распределения.

    Выбирает вопросы по квотам категорий (TestingCategorySetting).
    Для каждой категории вопросы сортируются по возрастанию times_used (наименее используемые первыми).
    При равенстве times_used применяется случайный выбор (random.sample).
    Создает неизменяемые снимки вопросов (AttemptQuestion) со случайным порядком вариантов ответов.
    Создает пустые черновики UserAnswer.
    Инкрементирует times_used у выбранных вопросов.

    Args:
        assignment (TestingAssignment): Назначение сотрудника.
        user (Optional[User]): Инициатор создания.

    Returns:
        TestingAttempt: Созданный объект попытки с привязанными снимками вопросов.
    """
    testing = assignment.testing
    category_settings = list(testing.category_settings.select_related("category").all())

    selected_questions: List[Question] = []
    category_questions_map: Dict[int, List[Question]] = {}

    # 1. Выборка вопросов по категориям с алгоритмом равномерного распределения
    for c_setting in category_settings:
        needed_count = c_setting.calculated_questions_count
        if needed_count <= 0:
            continue

        cat_id = c_setting.category_id
        active_questions = list(
            Question.objects.filter(
                category_id=cat_id,
                status=Question.Status.ACTIVE
            ).prefetch_related("options")
        )

        if len(active_questions) < needed_count:
            raise ValidationError(
                f"Недостаточно активных вопросов в категории «{c_setting.category.name}»: "
                f"требуется {needed_count}, доступно {len(active_questions)}."
            )

        # Сортировка: сначала наименее используемые вопросы
        active_questions.sort(key=lambda q: (q.times_used, random.random()))
        picked = active_questions[:needed_count]
        selected_questions.extend(picked)
        category_questions_map[cat_id] = picked

    # Резервный выбор: если категории не распределены, но задано questions_count
    if not selected_questions:
        needed_count = testing.questions_count
        active_questions = list(
            Question.objects.filter(
                status=Question.Status.ACTIVE
            ).prefetch_related("options")
        )
        if len(active_questions) < needed_count:
            raise ValidationError(
                f"Недостаточно активных вопросов для формирования теста: "
                f"требуется {needed_count}, доступно в банке {len(active_questions)}."
            )
        active_questions.sort(key=lambda q: (q.times_used, random.random()))
        selected_questions = active_questions[:needed_count]

    # Перемешивание общего порядка вопросов в тесте
    random.shuffle(selected_questions)

    with transaction.atomic():
        now = timezone.now()
        attempt_num = assignment.attempts_used + 1

        # Обновление счетчика и статуса назначения
        assignment.attempts_used = attempt_num
        assignment.status = TestingAssignment.Status.IN_PROGRESS
        assignment.save(update_fields=["attempts_used", "status"])

        planned_end = now + timedelta(minutes=testing.attempt_duration_minutes)

        attempt = TestingAttempt.objects.create(
            assignment=assignment,
            attempt_number=attempt_num,
            status=TestingAttempt.Status.IN_PROGRESS,
            started_at=now,
            planned_end_at=planned_end,
            total_questions=len(selected_questions)
        )

        # Создание неизменяемых снимков вопросов и черновиков ответов
        attempt_questions = []
        for order_idx, q in enumerate(selected_questions, 1):
            raw_options = list(q.options.all())
            random.shuffle(raw_options)

            options_snapshot = [
                {
                    "id": opt.id,
                    "order_num": opt_idx,
                    "text": opt.text,
                    "is_correct": opt.is_correct
                }
                for opt_idx, opt in enumerate(raw_options, 1)
            ]

            aq = AttemptQuestion.objects.create(
                attempt=attempt,
                source_question=q,
                category_name=q.category.name if q.category else "Общая",
                order_num=order_idx,
                question_text=q.text,
                options_snapshot=options_snapshot
            )
            attempt_questions.append(aq)

            # Создаем пустой черновик ответа
            UserAnswer.objects.create(
                attempt=attempt,
                attempt_question=aq,
                selected_option_id=None,
                is_correct=False
            )

            # Инкремент счетчика использования вопроса
            q.times_used += 1
            q.save(update_fields=["times_used"])

        TestingAuditLog.objects.create(
            user=user or assignment.employee,
            action="attempt_started",
            object_repr=f"Начата попытка №{attempt_num} сотрудником {assignment.employee.get_full_name()}",
            details={
                "testing": testing.title,
                "attempt_id": attempt.id,
                "questions_count": len(selected_questions),
                "planned_end_at": planned_end.isoformat()
            }
        )

    return attempt


def save_draft_answer(
    attempt: TestingAttempt,
    attempt_question_id: int,
    selected_option_id: int,
    spent_seconds: int = 0
) -> Dict[str, Any]:
    """Сохраняет выбранный сотрудником вариант ответа в черновик (автосохранение).

    Проверяет серверный таймер. Если время вышло, попытка автоматически
    завершается с причиной TIMEOUT и возвращается соответствующий флаг.

    Args:
        attempt (TestingAttempt): Текущая попытка тестирования.
        attempt_question_id (int): ID снимка вопроса AttemptQuestion.
        selected_option_id (int): ID выбранного варианта ответа.
        spent_seconds (int): Количество секунд, затраченных на ответ.

    Returns:
        Dict[str, Any]: Результат операции:
            - 'success' (bool): Успешность сохранения;
            - 'is_expired' (bool): Истек ли таймер попытки;
            - 'remaining_seconds' (int): Оставшееся время в секундах;
            - 'answered_count' (int): Количество вопросов, на которые дан ответ;
            - 'total_questions' (int): Общее число вопросов;
            - 'error' (Optional[str]): Текст ошибки при сбое.
    """
    if attempt.status != TestingAttempt.Status.IN_PROGRESS:
        return {
            "success": False,
            "is_expired": True,
            "remaining_seconds": 0,
            "answered_count": attempt.answers.filter(selected_option_id__isnull=False).count(),
            "total_questions": attempt.total_questions,
            "error": "Попытка тестирования уже завершена."
        }

    # Проверка серверного таймера
    remaining = attempt.get_remaining_seconds()
    if remaining <= 0:
        finish_attempt(attempt, reason=TestingAttempt.CompletionReason.TIME_EXPIRED)
        return {
            "success": False,
            "is_expired": True,
            "remaining_seconds": 0,
            "answered_count": attempt.answers.filter(selected_option_id__isnull=False).count(),
            "total_questions": attempt.total_questions,
            "error": "Время на выполнение тестирования истекло."
        }

    # Поиск вопроса и черновика ответа
    aq = attempt.questions.filter(id=attempt_question_id).first()
    if not aq:
        return {"success": False, "is_expired": False, "remaining_seconds": remaining, "error": "Вопрос не найден."}

    user_answer = attempt.answers.filter(attempt_question=aq).first()
    if not user_answer:
        return {"success": False, "is_expired": False, "remaining_seconds": remaining, "error": "Черновик ответа не найден."}

    # Проверка корректности выбранного варианта по снимку options_snapshot
    valid_option = None
    for opt in aq.options_snapshot:
        if opt["id"] == selected_option_id:
            valid_option = opt
            break

    if not valid_option:
        return {
            "success": False,
            "is_expired": False,
            "remaining_seconds": remaining,
            "error": f"Вариант ответа ID {selected_option_id} не принадлежит данному вопросу."
        }

    now = timezone.now()
    user_answer.selected_option_id = selected_option_id
    user_answer.is_correct = bool(valid_option.get("is_correct", False))
    user_answer.answered_at = now
    if spent_seconds > 0:
        user_answer.seconds_spent += spent_seconds
    user_answer.save()

    answered_count = attempt.answers.filter(selected_option_id__isnull=False).count()

    return {
        "success": True,
        "is_expired": False,
        "remaining_seconds": remaining,
        "answered_count": answered_count,
        "total_questions": attempt.total_questions,
        "selected_option_id": selected_option_id,
        "error": None
    }


def finish_attempt(attempt: TestingAttempt, reason: str = TestingAttempt.CompletionReason.USER_COMPLETED) -> TestingAttempt:
    """Завершает попытку тестирования, производит подсчет баллов и обновляет статус назначения.

    Подсчитывает:
    - Общее число вопросов;
    - Количество правильных ответов;
    - Итоговый процент с округлением до одного десятичного знака;
    - Факт сдачи (is_passed = score_percentage >= passing_score_percentage).
    Если тест сдан:
    - Назначению присваивается статус PASSED;
    - Генерируется уникальный UUID сертификата и регистрационный номер результата.
    Если тест не сдан:
    - Если исчерпаны все попытки -> статус FAILED (или ON_CONTROL);
    - Иначе -> статус IN_PROGRESS (доступны повторные попытки).
    Обновляет times_correct в банке вопросов.

    Args:
        attempt (TestingAttempt): Завершаемая попытка.
        reason (str): Причина завершения (MANUAL, TIMEOUT, ADMIN_CLOSED).

    Returns:
        TestingAttempt: Завершенная попытка с рассчитанным результатом.
    """
    if attempt.status != TestingAttempt.Status.IN_PROGRESS:
        return attempt

    with transaction.atomic():
        now = timezone.now()
        attempt.status = TestingAttempt.Status.COMPLETED
        attempt.completion_reason = reason
        attempt.completed_at = now
        attempt.finished_at = now
        if attempt.started_at:
            attempt.duration_seconds = max(0, int((now - attempt.started_at).total_seconds()))

        # Подсчет правильных ответов
        total_q = attempt.total_questions or attempt.questions.count()
        correct_count = attempt.answers.filter(is_correct=True).count()

        score_pct = round((correct_count / float(total_q)) * 100, 1) if total_q > 0 else 0.0
        is_passed = score_pct >= attempt.passing_score_percentage

        attempt.correct_answers = correct_count
        attempt.correct_answers_count = correct_count
        attempt.score_percentage = score_pct
        attempt.is_passed = is_passed

        # Если тест сдан, формируем сертификат и номер результата
        if is_passed:
            attempt.certificate_uuid = uuid.uuid4()
            year = now.year
            attempt.result_number = f"БАРКОЛ-ТО-{year}-{attempt.id:06d}"

        attempt.save()

        # Обновление статуса назначения сотрудника
        assignment = attempt.assignment
        testing = assignment.testing

        if is_passed:
            assignment.status = TestingAssignment.Status.PASSED
        else:
            if assignment.attempts_used >= testing.max_attempts:
                assignment.status = TestingAssignment.Status.FAILED
                assignment.is_on_control = True
            else:
                assignment.status = TestingAssignment.Status.IN_PROGRESS

        assignment.save(update_fields=["status", "is_on_control"])

        # Обновление статистики банка вопросов (times_correct)
        for answer in attempt.answers.select_related("attempt_question__source_question"):
            src_q = answer.attempt_question.source_question
            if src_q and answer.is_correct:
                src_q.times_correct += 1
                src_q.save(update_fields=["times_correct"])

        TestingAuditLog.objects.create(
            user=assignment.employee,
            action="attempt_finished",
            object_repr=f"Завершена попытка №{attempt.attempt_number} ({'Сдано' if is_passed else 'Не сдано'})",
            details={
                "attempt_id": attempt.id,
                "score_percentage": float(score_pct),
                "correct_answers": correct_count,
                "total_questions": total_q,
                "reason": reason,
                "is_passed": is_passed,
                "certificate_uuid": str(attempt.certificate_uuid) if attempt.certificate_uuid else None
            }
        )

    # Асинхронная отправка почтового уведомления о результатах сдачи через Celery
    try:
        from testing_app.tasks import send_attempt_result_notification_task
        send_attempt_result_notification_task.delay(attempt.id)
    except Exception as exc:
        logger.warning("Не удалось поставить в очередь отправку результатов (Attempt ID %s): %s", attempt.id, exc)

    return attempt

