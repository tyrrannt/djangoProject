from datetime import date, timedelta
from typing import Any
from celery import shared_task
from core import logger

from finance_app.services.sync_service import SyncService
from finance_app.services.notification_service import NotificationService
from finance_app.models import PaymentSchedule, CreditPaymentSchedule


@shared_task(name="finance_app.tasks.sync_directories_task")
def sync_directories_task() -> str:
    """
    Периодическая задача Celery для синхронизации справочников с 1С (каждые 12 часов).

    Returns:
        Результат выполнения в виде строки.
    """
    logger.info("Celery task: Запуск синхронизации справочников...")
    try:
        orgs_count = SyncService.sync_organizations()
        agents_count = SyncService.sync_counteragents()
        contracts_count = SyncService.sync_contracts()
        msg = f"Успешно. Синхронизировано: Организаций={orgs_count}, Контрагентов={agents_count}, Договоров={contracts_count}"
        logger.info(msg)
        return msg
    except Exception as ex:
        err_msg = f"Ошибка синхронизации справочников: {ex}"
        logger.error(err_msg)
        return err_msg


@shared_task(name="finance_app.tasks.sync_debts_task")
def sync_debts_task() -> str:
    """
    Периодическая задача Celery для создания снимков задолженности (каждые 30 минут).

    Returns:
        Результат выполнения в виде строки.
    """
    logger.info("Celery task: Запуск расчета задолженности...")
    try:
        SyncService.create_debt_snapshots()
        msg = "Успешно: снимки задолженности рассчитаны."
        logger.info(msg)
        return msg
    except Exception as ex:
        err_msg = f"Ошибка расчета снимков задолженности: {ex}"
        logger.error(err_msg)
        return err_msg


@shared_task(name="finance_app.tasks.sync_payments_task")
def sync_payments_task() -> str:
    """
    Периодическая задача Celery для синхронизации платежей (каждые 15 минут).

    Returns:
        Результат выполнения в виде строки.
    """
    logger.info("Celery task: Запуск синхронизации платежей...")
    try:
        payments_count = SyncService.sync_payments()
        msg = f"Успешно. Синхронизировано платежей: {payments_count}"
        logger.info(msg)
        return msg
    except Exception as ex:
        err_msg = f"Ошибка синхронизации платежей: {ex}"
        logger.error(err_msg)
        return err_msg


@shared_task(name="finance_app.tasks.sync_credits_task")
def sync_credits_task() -> str:
    """
    Периодическая задача Celery для синхронизации кредитов (каждые 15 минут).

    Returns:
        Результат выполнения в виде строки.
    """
    logger.info("Celery task: Запуск синхронизации кредитов...")
    try:
        credits_count = SyncService.sync_credits()
        msg = f"Успешно. Синхронизировано кредитных договоров: {credits_count}"
        logger.info(msg)
        return msg
    except Exception as ex:
        err_msg = f"Ошибка синхронизации кредитов: {ex}"
        logger.error(err_msg)
        return err_msg


@shared_task(name="finance_app.tasks.send_upcoming_payment_notifications_task")
def send_upcoming_payment_notifications_task() -> str:
    """
    Периодическая задача Celery для отправки уведомлений о предстоящих и просроченных платежах.

    Отправляет уведомления за 30, 14, 7, 3, 1 день до платежа, а также
    ежедневно в случае возникновения просрочки.

    Returns:
        Результат выполнения в виде строки.
    """
    logger.info("Celery task: Запуск рассылки уведомлений по платежам...")
    today = date.today()
    notif_count = 0

    # 1. Предстоящие платежи (обычные обязательства)
    intervals = [30, 14, 7, 3, 1]
    for days in intervals:
        target_date = today + timedelta(days=days)
        schedules = PaymentSchedule.objects.filter(
            payment_date=target_date,
            status__in=["planned", "partially_paid"]
        ).select_related("obligation__contract__employee", "obligation__contract__counteragent")

        for s in schedules:
            user = s.obligation.contract.employee
            if user:
                message = (
                    f"Напоминание: Предстоит платеж по договору № {s.obligation.contract.contract_number} "
                    f"с {s.obligation.contract.counteragent.short_name} на сумму {s.amount} руб. через {days} дн. "
                    f"(Дата платежа: {s.payment_date:%d.%m.%Y})."
                )
                NotificationService.send_notification_to_user(user, message)
                notif_count += 1

    # 2. Предстоящие платежи по кредитам
    for days in intervals:
        target_date = today + timedelta(days=days)
        credit_schedules = CreditPaymentSchedule.objects.filter(
            payment_date=target_date,
            status__in=["planned", "partially_paid"]
        ).select_related("credit_agreement__employee", "credit_agreement__bank")

        for cs in credit_schedules:
            user = cs.credit_agreement.employee
            if user:
                message = (
                    f"Напоминание: Предстоит платеж по кредиту № {cs.credit_agreement.contract_number} "
                    f"в {cs.credit_agreement.bank.short_name} на сумму {cs.total_amount} руб. через {days} дн. "
                    f"(Дата платежа: {cs.payment_date:%d.%m.%Y})."
                )
                NotificationService.send_notification_to_user(user, message)
                notif_count += 1

    # 3. Просроченные платежи (ежедневно до устранения)
    overdue_schedules = PaymentSchedule.objects.filter(
        status="overdue"
    ).select_related("obligation__contract__employee", "obligation__contract__counteragent")

    for s in overdue_schedules:
        user = s.obligation.contract.employee
        if user:
            overdue_days = (today - s.payment_date).days
            message = (
                f"ВНИМАНИЕ: Просрочен платеж по договору № {s.obligation.contract.contract_number} "
                f"с {s.obligation.contract.counteragent.short_name} на сумму {s.amount} руб. "
                f"Количество дней просрочки: {overdue_days} дн. (Срок оплаты: {s.payment_date:%d.%m.%Y})."
            )
            NotificationService.send_notification_to_user(user, message)
            notif_count += 1

    # 4. Просроченные кредиты
    overdue_credits = CreditPaymentSchedule.objects.filter(
        status="overdue"
    ).select_related("credit_agreement__employee", "credit_agreement__bank")

    for cs in overdue_credits:
        user = cs.credit_agreement.employee
        if user:
            overdue_days = (today - cs.payment_date).days
            message = (
                f"ВНИМАНИЕ: Просрочен платеж по кредиту № {cs.credit_agreement.contract_number} "
                f"в {cs.credit_agreement.bank.short_name} на сумму {cs.total_amount} руб. "
                f"Количество дней просрочки: {overdue_days} дн. (Срок оплаты: {cs.payment_date:%d.%m.%Y})."
            )
            NotificationService.send_notification_to_user(user, message)
            notif_count += 1

    msg = f"Успешно. Отправлено уведомлений: {notif_count}"
    logger.info(msg)
    return msg


@shared_task(name="finance_app.tasks.check_overdraft_tranches_task")
def check_overdraft_tranches_task() -> str:
    """
    Периодическая задача Celery для проверки сроков погашения траншей овердрафта.
    Отправляет email-уведомление ответственному сотруднику за 7 дней до истечения срока траншей (в виде сводной таблицы).
    """
    from finance_app.models import CreditAgreement
    from finance_app.services.overdraft_service import OverdraftCalculationService
    from finance_app.services.notification_service import NotificationService
    from collections import defaultdict

    logger.info("Celery task: Запуск проверки сроков траншей овердрафтов...")
    today = date.today()
    notif_count = 0

    # Находим все кредитные договоры (овердрафты)
    overdrafts = CreditAgreement.objects.all().select_related("employee", "bank")
    
    # Группируем подходящие транши по ответственным сотрудникам
    employee_notifications = defaultdict(lambda: {'user': None, 'tranches': []})

    for agreement in overdrafts:
        # Для расчета используем OverdraftCalculationService
        service = OverdraftCalculationService(agreement)
        calc_result = service.calculate(today)

        for tranche in calc_result.get("active_tranches", []):
            maturity_date = tranche.get("maturity_date")
            if not maturity_date:
                continue

            days_left = (maturity_date - today).days
            if 0 <= days_left <= 7:
                logger.info(tranche)
                user = agreement.employee
                if user:
                    employee_notifications[user.id]['user'] = user
                    bank_name = agreement.bank.short_name if agreement.bank else "Неизвестный банк"
                    employee_notifications[user.id]['tranches'].append({
                        'contract': agreement.contract_number,
                        'bank': bank_name,
                        'date': tranche.get("date"),
                        'amount': tranche.get("principal", 0),
                        'maturity': maturity_date
                    })

    # Рассылаем сводные таблицы каждому ответственному сотруднику
    for data in employee_notifications.values():
        user = data['user']
        tranches = data['tranches']
        
        if not tranches:
            continue
            
        message = "<b>УВЕДОМЛЕНИЕ О ПОГАШЕНИИ ТРАНШЕЙ ОВЕРДРАФТА</b><br><br>\n"
        message += "Через 7 дней наступает срок погашения по следующим траншам:<br><br>\n"
        
        # Используем тег pre для создания моноширинной таблицы, которая поддерживается и в e-mail, и в Telegram
        message += "<pre>\n"
        header = f"{'Договор':<18} | {'Сумма (ОД)':>15} | {'Срок до':<11}\n"
        message += header
        message += "-" * (len(header.strip()) + 1) + "\n"
        
        for t in tranches:
            c_num = str(t['contract'])[:18]
            amount_str = f"{t['amount']:,.2f}".replace(',', ' ')
            m_date = t['maturity'].strftime('%d.%m.%Y')
            
            row = f"{c_num:<18} | {amount_str:>15} | {m_date:<11}\n"
            message += row
            
        message += "</pre><br>\nПросьба принять необходимые меры."

        NotificationService.send_notification_to_user(user, message)
        notif_count += 1

    msg = f"Успешно. Отправлено сводных уведомлений по овердрафтам: {notif_count}"
    logger.info(msg)
    return msg
