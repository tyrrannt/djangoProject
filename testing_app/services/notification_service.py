"""Сервисы почтовых уведомлений (Kerio Connect) для модуля периодического тестирования сотрудников."""

import logging
from datetime import timedelta
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.html import strip_tags

from testing_app.models import (
    Testing,
    TestingAssignment,
    TestingAttempt,
    TestingAuditLog,
)

logger = logging.getLogger(__name__)


def send_html_email(
    subject: str,
    html_content: str,
    recipient_email: str,
    user=None
) -> bool:
    """Универсальная функция безопасной отправки HTML-письма через корпоративный почтовый сервер Kerio Connect.

    Args:
        subject (str): Тема электронного письма.
        html_content (str): HTML-разметка тела письма.
        recipient_email (str): Адрес электронной почты получателя.
        user (Optional[User]): Пользователь для фиксации в аудите.

    Returns:
        bool: Успешность отправки письма.
    """
    if not recipient_email or "@" not in recipient_email:
        logger.warning("Отправка email отменена: некорректный или пустой адрес получателя: '%s'", recipient_email)
        return False

    plain_message = strip_tags(html_content.replace("<br>", "\n").replace("</p>", "\n"))
    from_email = getattr(settings, "EMAIL_HOST_USER", "ias@barkol.ru")

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient_email],
            fail_silently=False,
            html_message=html_content,
        )
        logger.info("Email успешно отправлен на '%s', тема: '%s'", recipient_email, subject)
        return True
    except Exception as exc:
        logger.error("Ошибка отправки email на '%s': %s", recipient_email, exc, exc_info=True)
        return False


def send_testing_assignment_notification(assignment_id: int) -> bool:
    """Отправляет сотруднику email-уведомление о назначении на периодическую проверку знаний.

    Args:
        assignment_id (int): ID назначения TestingAssignment.

    Returns:
        bool: Результат отправки.
    """
    assignment = TestingAssignment.objects.select_related(
        "employee", "testing", "group"
    ).filter(id=assignment_id).first()

    if not assignment:
        logger.warning("send_testing_assignment_notification: Назначение ID %s не найдено.", assignment_id)
        return False

    employee = assignment.employee
    testing = assignment.testing
    email = employee.email

    if not email:
        logger.warning("У сотрудника %s (ID %s) отсутствует email.", employee.get_full_name(), employee.id)
        return False

    subject = f"ООО «Авиакомпания «БАРКОЛ» — Назначение периодической проверки знаний (Приказ №{testing.order_number})"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #1E3A8A; color: #FFFFFF; padding: 20px; text-align: center;">
            <h3 style="margin: 0 0 5px 0; text-transform: uppercase;">ООО «Авиакомпания «БАРКОЛ»</h3>
            <p style="margin: 0; font-size: 13px; opacity: 0.9;">Инженерно-авиационная служба (ИАС)</p>
        </div>
        <div style="padding: 24px; color: #1E293B;">
            <p style="font-size: 16px; font-weight: bold; margin-top: 0;">Уважаемый(ая) {employee.get_full_name()}!</p>
            <p style="line-height: 1.5;">
                В соответствии с приказом <strong>№ {testing.order_number} от {testing.order_date.strftime('%d.%m.%Y')}</strong> 
                «{testing.order_name}» Вам назначено прохождение периодической проверки знаний по техническому обслуживанию ВС.
            </p>

            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
                <tr style="background-color: #F8FAFC;">
                    <td style="padding: 10px; border: 1px solid #E2E8F0; font-weight: bold; width: 40%;">Мероприятие:</td>
                    <td style="padding: 10px; border: 1px solid #E2E8F0;">{testing.title}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #E2E8F0; font-weight: bold;">Группа:</td>
                    <td style="padding: 10px; border: 1px solid #E2E8F0;">{assignment.group.name}</td>
                </tr>
                <tr style="background-color: #F8FAFC;">
                    <td style="padding: 10px; border: 1px solid #E2E8F0; font-weight: bold;">Период проведения:</td>
                    <td style="padding: 10px; border: 1px solid #E2E8F0;">
                        с <strong>{testing.start_datetime.strftime('%d.%m.%Y %H:%M')}</strong> 
                        по <strong>{testing.end_datetime.strftime('%d.%m.%Y %H:%M')}</strong>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #E2E8F0; font-weight: bold;">Параметры теста:</td>
                    <td style="padding: 10px; border: 1px solid #E2E8F0;">
                        {testing.questions_count} вопросов • Проходной балл: {testing.passing_score_percentage}%<br>
                        Время попытки: {testing.attempt_duration_minutes} мин • Попыток: {testing.max_attempts}
                    </td>
                </tr>
            </table>

            <p style="line-height: 1.5; color: #475569; font-size: 13px;">
                Пожалуйста, выделите достаточно времени и обеспечьте стабильное интернет-соединение перед началом попытки.
            </p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="/testing/my/" style="background-color: #1E3A8A; color: #FFFFFF; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    Перейти в личный кабинет тестирования
                </a>
            </div>
        </div>
        <div style="background-color: #F1F5F9; padding: 12px; text-align: center; font-size: 12px; color: #64748B;">
            Письмо сформировано автоматически корпоративным порталом ИАС ООО «Авиакомпания «БАРКОЛ». Отвечать на него не нужно.
        </div>
    </div>
    """

    success = send_html_email(subject, html_content, email, user=employee)
    if success:
        TestingAuditLog.objects.create(
            user=employee,
            action="notify_assigned",
            object_repr=f"Email о назначении отправлен сотруднику {employee.get_full_name()}",
            details={"testing_id": testing.id, "email": email}
        )
    return success


def send_testing_result_notification(attempt_id: int) -> bool:
    """Отправляет сотруднику email с результатами сдачи теста и ссылкой на сертификат.

    Args:
        attempt_id (int): ID попытки TestingAttempt.

    Returns:
        bool: Результат отправки.
    """
    attempt = TestingAttempt.objects.select_related(
        "assignment__employee", "assignment__testing"
    ).filter(id=attempt_id).first()

    if not attempt:
        return False

    assignment = attempt.assignment
    employee = assignment.employee
    testing = assignment.testing
    email = employee.email

    if not email:
        return False

    if attempt.is_passed:
        subject = f"Поздравляем! Проверка знаний успешно пройдена — ООО «Авиакомпания «БАРКОЛ»"
        status_box = f"""
        <div style="background-color: #DCFCE7; border: 1px solid #86EFAC; color: #166534; padding: 16px; border-radius: 6px; text-align: center; margin-bottom: 20px;">
            <h4 style="margin: 0 0 5px 0;">ТЕСТ УСПЕШНО СДАН!</h4>
            <div style="font-size: 18px; font-weight: bold;">Результат: {attempt.score_percentage}%</div>
            <div style="font-size: 12px; margin-top: 5px;">Регистрационный номер: <strong>{attempt.result_number}</strong></div>
        </div>
        """
        btn_action = f"""
        <div style="text-align: center; margin: 25px 0;">
            <a href="/testing/attempt/{attempt.id}/certificate/" style="background-color: #166534; color: #FFFFFF; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                Просмотреть и распечатать сертификат
            </a>
        </div>
        """
    else:
        rem_attempts = testing.max_attempts - assignment.attempts_used
        subject = f"Результаты тестирования — ООО «Авиакомпания «БАРКОЛ»"
        if rem_attempts > 0:
            status_desc = f"Набранный балл ({attempt.score_percentage}%) ниже порогового значения ({attempt.passing_score_percentage}%). У Вас осталось попыток: <strong>{rem_attempts}</strong>."
        else:
            status_desc = f"Набранный балл ({attempt.score_percentage}%) ниже порогового значения. Лимит попыток исчерпан. Вы поставлены на контроль аттестационной комиссии."

        status_box = f"""
        <div style="background-color: #FEE2E2; border: 1px solid #FCA5A5; color: #991B1B; padding: 16px; border-radius: 6px; text-align: center; margin-bottom: 20px;">
            <h4 style="margin: 0 0 5px 0;">ТЕСТИРОВАНИЕ НЕ ПРОЙДЕНО</h4>
            <div style="font-size: 18px; font-weight: bold;">Результат: {attempt.score_percentage}% (Порог: {attempt.passing_score_percentage}%)</div>
            <p style="margin: 10px 0 0 0; font-size: 13px;">{status_desc}</p>
        </div>
        """
        btn_action = f"""
        <div style="text-align: center; margin: 25px 0;">
            <a href="/testing/my/" style="background-color: #1E3A8A; color: #FFFFFF; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                Перейти в личный кабинет
            </a>
        </div>
        """

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #1E3A8A; color: #FFFFFF; padding: 20px; text-align: center;">
            <h3 style="margin: 0 0 5px 0; text-transform: uppercase;">ООО «Авиакомпания «БАРКОЛ»</h3>
            <p style="margin: 0; font-size: 13px; opacity: 0.9;">Итоги попытки №{attempt.attempt_number} проверки знаний</p>
        </div>
        <div style="padding: 24px; color: #1E293B;">
            <p style="font-size: 16px; font-weight: bold; margin-top: 0;">Уважаемый(ая) {employee.get_full_name()}!</p>
            <p>Вы завершили прохождение тестирования по мероприятию «{testing.title}».</p>

            {status_box}

            <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 15px;">
                <tr>
                    <td style="padding: 6px; color: #64748B;">Правильных ответов:</td>
                    <td style="padding: 6px; font-weight: bold;">{attempt.correct_answers_count} из {attempt.total_questions}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; color: #64748B;">Время завершения:</td>
                    <td style="padding: 6px; font-weight: bold;">{attempt.finished_at.strftime('%d.%m.%Y %H:%M') if attempt.finished_at else '—'}</td>
                </tr>
            </table>

            {btn_action}
        </div>
        <div style="background-color: #F1F5F9; padding: 12px; text-align: center; font-size: 12px; color: #64748B;">
            Корпоративный портал ИАС ООО «Авиакомпания «БАРКОЛ»
        </div>
    </div>
    """

    return send_html_email(subject, html_content, email, user=employee)


def send_testing_deadline_reminders() -> Dict[str, int]:
    """Сканирует активные мероприятия и отправляет напоминания работникам за 3 дня и за 1 день до дедлайна.

    Returns:
        Dict[str, int]: Количество отправленных напоминаний ('reminders_3_days', 'reminders_1_day').
    """
    now = timezone.now()
    active_testings = Testing.objects.filter(status=Testing.Status.ACTIVE, end_datetime__gt=now)

    sent_3_days = 0
    sent_1_day = 0

    for testing in active_testings:
        time_left = testing.end_datetime - now
        days_left = time_left.total_seconds() / 86400.0

        is_3_day_window = 2.0 <= days_left <= 3.5
        is_1_day_window = 0.0 < days_left <= 1.5

        if not (is_3_day_window or is_1_day_window):
            continue

        urgency_text = "3 дня" if is_3_day_window else "1 день (последний срок!)"

        # Работники, которые еще не сдали тест
        pending_assignments = testing.assignments.filter(
            status__in=[TestingAssignment.Status.NOT_STARTED, TestingAssignment.Status.IN_PROGRESS]
        ).select_related("employee")

        for assign in pending_assignments:
            emp = assign.employee
            if not emp.email:
                continue

            subject = f"Внимание: До окончания проверки знаний осталось {urgency_text} — ООО «Авиакомпания «БАРКОЛ»"
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #DC2626; color: #FFFFFF; padding: 18px; text-align: center;">
                    <h3 style="margin: 0; text-transform: uppercase;">ВНИМАНИЕ! СРОК ТЕСТИРОВАНИЯ ИСТЕКАЕТ</h3>
                </div>
                <div style="padding: 24px; color: #1E293B;">
                    <p style="font-weight: bold;">Уважаемый(ая) {emp.get_full_name()}!</p>
                    <p>
                        Напоминаем, что срок прохождения проверки знаний по мероприятию 
                        <strong>«{testing.title}»</strong> (Приказ №{testing.order_number}) 
                        заканчивается <strong>{testing.end_datetime.strftime('%d.%m.%Y в %H:%M')}</strong>.
                    </p>
                    <div style="background-color: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px; margin: 15px 0; font-size: 14px;">
                        Осталось времени: <strong>{urgency_text}</strong>. Использовано попыток: <strong>{assign.attempts_used} из {testing.max_attempts}</strong>.
                    </div>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="/testing/my/" style="background-color: #DC2626; color: #FFFFFF; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                            Пройти тестирование сейчас
                        </a>
                    </div>
                </div>
            </div>
            """
            ok = send_html_email(subject, html_content, emp.email, user=emp)
            if ok:
                if is_3_day_window:
                    sent_3_days += 1
                else:
                    sent_1_day += 1

    return {"reminders_3_days": sent_3_days, "reminders_1_day": sent_1_day}


def check_and_expire_stale_attempts() -> int:
    """Проверяет незавершенные сессии тестирования и закрывает по таймауту сессии с истекшим таймером.

    Returns:
        int: Количество закрытых по таймауту сессий.
    """
    from testing_app.services.engine_service import finish_attempt

    now = timezone.now()
    stale_attempts = TestingAttempt.objects.filter(
        status=TestingAttempt.Status.IN_PROGRESS,
        planned_end_at__lt=now
    )

    count = 0
    for attempt in stale_attempts:
        try:
            finish_attempt(attempt, reason=TestingAttempt.CompletionReason.TIME_EXPIRED)
            count += 1
            logger.info("Сессия тестирования ID %s закрыта по таймауту.", attempt.id)
        except Exception as e:
            logger.error("Ошибка закрытия сессии ID %s по таймауту: %s", attempt.id, e)

    return count
