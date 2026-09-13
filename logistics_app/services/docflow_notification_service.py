"""Сервис оповещений и почтовых уведомлений подсистемы СЭД (logistics_app)."""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.html import strip_tags

from customers_app.models import DataBaseUser
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowDocument,
    DocFlowRouteStep,
)

logger = logging.getLogger(__name__)


class DocFlowNotificationService:
    """Сервис формирования и отправки email и внутрипортальных уведомлений СЭД.

    Обеспечивает своевременное информирование участников о поступлении документов на согласование,
    возвратах на доработку, целевых откатах на предыдущие шаги, успешном финальном согласовании
    и контроле соблюдения сроков по SLA.
    """

    @classmethod
    def send_html_notification_email(
        cls,
        subject: str,
        html_content: str,
        recipient_emails: List[str],
    ) -> int:
        """Безопасно отправляет стилизованное HTML-письмо списку адресатов через Kerio Connect.

        Args:
            subject (str): Тема электронного письма.
            html_content (str): HTML-разметка тела письма.
            recipient_emails (List[str]): Список адресов получателей.

        Returns:
            int: Количество успешно отправленных писем.
        """
        valid_recipients = [
            email.strip()
            for email in recipient_emails
            if email and "@" in email and "." in email
        ]

        if not valid_recipients:
            logger.debug("DocFlowNotification: список получателей пуст, отправка отменена.")
            return 0

        plain_message = strip_tags(html_content.replace("<br>", "\n").replace("</p>", "\n"))
        from_email = getattr(settings, "EMAIL_HOST_USER", "office@barkol.ru")

        sent_count = 0
        for email in valid_recipients:
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=from_email,
                    recipient_list=[email],
                    fail_silently=False,
                    html_message=html_content,
                )
                sent_count += 1
                logger.info("Email СЭД успешно отправлен на '%s', тема: '%s'", email, subject)
            except Exception as exc:
                logger.error("Ошибка отправки email СЭД на '%s': %s", email, exc, exc_info=True)

        return sent_count

    @classmethod
    def _build_email_template(
        cls,
        header_title: str,
        greeting_text: str,
        document_info_rows: str,
        action_button_url: str,
        action_button_text: str = "Открыть документ в СЭД",
        footer_note: str = "",
    ) -> str:
        """Формирует адаптивный HTML-каркас корпоративного письма БАРКОЛ СЭД.

        Args:
            header_title (str): Заголовок баннера письма.
            greeting_text (str): Приветствие и основной текст события.
            document_info_rows (str): Табличные строки с реквизитами документа.
            action_button_url (str): Ссылка для перехода к карточке документа.
            action_button_text (str): Текст кнопки действия. Defaults to "Открыть документ в СЭД".
            footer_note (str): Дополнительный текст в подвале. Defaults to "".

        Returns:
            str: Скомпилированный HTML-код письма.
        """
        portal_url = getattr(settings, "PORTAL_URL", "https://corp.barkol.ru").rstrip("/")
        full_button_url = f"{portal_url}{action_button_url}" if action_button_url.startswith("/") else action_button_url

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; color: #1e293b;">
    <div style="max-width: 640px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06); border: 1px solid #e2e8f0;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #002b49 0%, #004b7a 100%); padding: 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 13px; letter-spacing: 1px; text-transform: uppercase; opacity: 0.85; margin-bottom: 4px;">ООО «Авиакомпания «БАРКОЛ»</div>
            <div style="font-size: 20px; font-weight: 700; margin: 0;">{header_title}</div>
        </div>

        <!-- Body -->
        <div style="padding: 28px 24px;">
            <p style="font-size: 15px; line-height: 1.6; margin-top: 0; margin-bottom: 20px; color: #334155;">
                {greeting_text}
            </p>

            <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px;">
                {document_info_rows}
            </table>

            <!-- Button -->
            <div style="text-align: center; margin: 32px 0 20px;">
                <a href="{full_button_url}" style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 13px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block; box-shadow: 0 2px 8px rgba(2, 132, 199, 0.35);">
                    {action_button_text} →
                </a>
            </div>

            {f'<p style="font-size: 13px; color: #64748b; text-align: center; margin-top: 16px;">{footer_note}</p>' if footer_note else ''}
        </div>

        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 16px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
            Корпоративный портал СЭД ООО «Авиакомпания «БАРКОЛ» &bull; Автоматическое уведомление
        </div>
    </div>
</body>
</html>"""

    @classmethod
    def get_step_recipients(cls, step: DocFlowRouteStep) -> List[DataBaseUser]:
        """Возвращает список сотрудников, назначенных на данный этап маршрута.

        Args:
            step (DocFlowRouteStep): Экземпляр шага маршрута.

        Returns:
            List[DataBaseUser]: Список пользователей-согласующих.
        """
        recipients = set()

        if step.assigned_user:
            recipients.add(step.assigned_user)

        for user in step.assigned_users.all():
            recipients.add(user)

        if step.assigned_division:
            division_users = DataBaseUser.objects.filter(
                user_work_profile__divisions=step.assigned_division,
                is_active=True,
            )
            for user in division_users:
                recipients.add(user)

        return list(recipients)

    @classmethod
    def notify_step_assigned(
        cls,
        step: DocFlowRouteStep,
        is_rollback: bool = False,
        rollback_comment: str = "",
    ) -> int:
        """Отправляет уведомление согласующим лицам о поступлении документа на этап.

        Args:
            step (DocFlowRouteStep): Шаг маршрута согласования.
            is_rollback (bool): Является ли назначение результатом отката шага.
            rollback_comment (str): Комментарий причины отката. Defaults to "".

        Returns:
            int: Количество отправленных писем.
        """
        document = step.document
        recipients = cls.get_step_recipients(step)
        emails = [u.email for u in recipients if u.email]

        if not emails:
            return 0

        doc_title = document.title
        reg_num = document.reg_number or f"UUID:{str(document.id)[:8]}"

        if is_rollback:
            subject = f"СЭД БАРКОЛ: Повторное рассмотрение документа {reg_num} (Откат шага)"
            header = "Повторное согласование документа"
            greeting = f"Вам повторно поступил на рассмотрение документ <strong>«{doc_title}»</strong> в связи с возвратом на этап №{step.step_order}."
        else:
            subject = f"СЭД БАРКОЛ: Вам на согласование поступил документ {reg_num}"
            header = "Новый документ на согласовании"
            greeting = f"Вам на согласование поступил документ <strong>«{doc_title}»</strong> (Этап: {step.step_name})."

        deadline_str = step.due_date.strftime("%d.%m.%Y %H:%M") if step.due_date else "Не установлен"
        author_str = document.initiator.get_full_name() or document.initiator.username

        rows = f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b; width: 35%;">Рег. номер:</td>
                <td style="padding: 10px 0; font-weight: 600; color: #0f172a;">{reg_num}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Тип документа:</td>
                <td style="padding: 10px 0; color: #0f172a;">{document.doc_type.name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Инициатор (Автор):</td>
                <td style="padding: 10px 0; color: #0f172a;">{author_str}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Текущий этап:</td>
                <td style="padding: 10px 0; font-weight: 600; color: #0284c7;">Шаг {step.step_order}: {step.step_name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Срок рассмотрения (SLA):</td>
                <td style="padding: 10px 0; font-weight: 600; color: #e11d48;">до {deadline_str}</td>
            </tr>
        """
        if is_rollback and rollback_comment:
            rows += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; background-color: #fff1f2;">
                <td style="padding: 10px 8px; color: #be123c; font-weight: 600;">Причина возврата:</td>
                <td style="padding: 10px 8px; color: #881337;">{rollback_comment}</td>
            </tr>
            """

        html = cls._build_email_template(
            header_title=header,
            greeting_text=greeting,
            document_info_rows=rows,
            action_button_url=f"/logistics/docflow/{document.id}/",
            action_button_text="Рассмотреть и согласовать",
            footer_note="Пожалуйста, соблюдайте нормативный регламент времени рассмотрения документа.",
        )

        return cls.send_html_notification_email(subject, html, emails)

    @classmethod
    def notify_document_returned(
        cls,
        document: DocFlowDocument,
        reviewer: DataBaseUser,
        comment: str,
    ) -> int:
        """Уведомляет автора и ответственного о возврате документа на доработку.

        Args:
            document (DocFlowDocument): Документ СЭД.
            reviewer (DataBaseUser): Согласующий, вернувший документ.
            comment (str): Замечания и перечень необходимых правок.

        Returns:
            int: Количество отправленных писем.
        """
        recipients = {document.initiator}
        if document.responsible:
            recipients.add(document.responsible)

        emails = [u.email for u in recipients if u.email]
        if not emails:
            return 0

        reg_num = document.reg_number or f"UUID:{str(document.id)[:8]}"
        subject = f"СЭД БАРКОЛ: Документ {reg_num} возвращен на доработку"
        reviewer_name = reviewer.get_full_name() or reviewer.username

        greeting = f"Документ <strong>«{document.title}»</strong> возвращен на доработку согласующим лицом <strong>{reviewer_name}</strong>."

        rows = f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b; width: 35%;">Рег. номер:</td>
                <td style="padding: 10px 0; font-weight: 600; color: #0f172a;">{reg_num}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Тип документа:</td>
                <td style="padding: 10px 0; color: #0f172a;">{document.doc_type.name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0; background-color: #fff7ed;">
                <td style="padding: 10px 8px; color: #c2410c; font-weight: 600;">Замечания:</td>
                <td style="padding: 10px 8px; color: #7c2d12; line-height: 1.5;">{comment or 'Требуется устранение замечаний перед повторным согласованием.'}</td>
            </tr>
        """

        html = cls._build_email_template(
            header_title="Документ возвращен на доработку",
            greeting_text=greeting,
            document_info_rows=rows,
            action_button_url=f"/logistics/docflow/{document.id}/",
            action_button_text="Внести правки и загрузить версию",
            footer_note="После внесения правок загрузите новую версию файла и возобновите согласование.",
        )

        return cls.send_html_notification_email(subject, html, emails)

    @classmethod
    def notify_approval_complete(cls, document: DocFlowDocument) -> int:
        """Отправляет уведомление об успешном полном согласовании документа всем участникам.

        Args:
            document (DocFlowDocument): Успешно согласованный документ СЭД.

        Returns:
            int: Количество отправленных писем.
        """
        recipients = {document.initiator}
        if document.responsible:
            recipients.add(document.responsible)

        # Добавляем всех, кто визировал документ
        log_users = DataBaseUser.objects.filter(
            docflow_action_logs__document=document,
            docflow_action_logs__action__in=[
                DocFlowApprovalLog.Action.APPROVED,
                DocFlowApprovalLog.Action.APPROVED_WITH_COMMENTS,
            ],
        ).distinct()

        for u in log_users:
            recipients.add(u)

        emails = [u.email for u in recipients if u.email]
        if not emails:
            return 0

        reg_num = document.reg_number or f"UUID:{str(document.id)[:8]}"
        subject = f"СЭД БАРКОЛ: Документ {reg_num} успешно согласован"

        greeting = f"Документ <strong>«{document.title}»</strong> успешно прошел все этапы согласования и получил итоговую визу одобрения."

        rows = f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b; width: 35%;">Рег. номер:</td>
                <td style="padding: 10px 0; font-weight: 600; color: #059669;">{reg_num}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Тип документа:</td>
                <td style="padding: 10px 0; color: #0f172a;">{document.doc_type.name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Итоговый статус:</td>
                <td style="padding: 10px 0; font-weight: 700; color: #059669;">СОГЛАСОВАН / ПРИНЯТ</td>
            </tr>
        """

        html = cls._build_email_template(
            header_title="Документ успешно согласован",
            greeting_text=greeting,
            document_info_rows=rows,
            action_button_url=f"/logistics/docflow/{document.id}/",
            action_button_text="Просмотреть Лист согласования",
            footer_note="Сформирован электронный Лист согласования со штампами Простой Электронной Подписи (ПЭП).",
        )

        return cls.send_html_notification_email(subject, html, emails)

    @classmethod
    def notify_rejection(
        cls,
        document: DocFlowDocument,
        reviewer: DataBaseUser,
        comment: str,
    ) -> int:
        """Отправляет уведомление об отклонении документа.

        Args:
            document (DocFlowDocument): Отклоненный документ СЭД.
            reviewer (DataBaseUser): Согласующий, отклонивший документ.
            comment (str): Причина отклонения.

        Returns:
            int: Количество отправленных писем.
        """
        recipients = {document.initiator}
        if document.responsible:
            recipients.add(document.responsible)

        emails = [u.email for u in recipients if u.email]
        if not emails:
            return 0

        reg_num = document.reg_number or f"UUID:{str(document.id)[:8]}"
        subject = f"СЭД БАРКОЛ: Документ {reg_num} отклонен"
        reviewer_name = reviewer.get_full_name() or reviewer.username

        greeting = f"Документ <strong>«{document.title}»</strong> был отклонен сотрудником <strong>{reviewer_name}</strong>."

        rows = f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b; width: 35%;">Рег. номер:</td>
                <td style="padding: 10px 0; font-weight: 600; color: #dc2626;">{reg_num}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 0; color: #64748b;">Тип документа:</td>
                <td style="padding: 10px 0; color: #0f172a;">{document.doc_type.name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #e2e8f0; background-color: #fef2f2;">
                <td style="padding: 10px 8px; color: #991b1b; font-weight: 600;">Причина отказа:</td>
                <td style="padding: 10px 8px; color: #7f1d1d; line-height: 1.5;">{comment or 'Причина не указана.'}</td>
            </tr>
        """

        html = cls._build_email_template(
            header_title="Документ отклонен",
            greeting_text=greeting,
            document_info_rows=rows,
            action_button_url=f"/logistics/docflow/{document.id}/",
            action_button_text="Открыть карточку документа",
        )

        return cls.send_html_notification_email(subject, html, emails)

    @classmethod
    def check_sla_deadlines(cls) -> Dict[str, Any]:
        """Мониторинг соблюдения SLA: выявление приближающихся дедлайнов и просрочек.

        Returns:
            Dict[str, Any]: Сводка по обработанным напоминаниям и просрочкам.
        """
        now = timezone.now()
        approaching_threshold = now + timedelta(hours=4)

        # 1. Шаги с приближающимся дедлайном (осталось < 4ч, но дедлайн еще не наступил)
        approaching_steps = DocFlowRouteStep.objects.filter(
            status=DocFlowRouteStep.Status.IN_PROGRESS,
            due_date__gt=now,
            due_date__lte=approaching_threshold,
        ).select_related("document", "document__initiator", "assigned_user", "assigned_division")

        # 2. Просроченные шаги (дедлайн уже истек)
        overdue_steps = DocFlowRouteStep.objects.filter(
            status=DocFlowRouteStep.Status.IN_PROGRESS,
            due_date__lt=now,
        ).select_related("document", "document__initiator", "assigned_user", "assigned_division")

        approaching_sent = 0
        overdue_sent = 0

        for step in approaching_steps:
            recipients = cls.get_step_recipients(step)
            emails = [u.email for u in recipients if u.email]
            if emails:
                subject = f"Внимание: До истечения срока согласования документа {step.document.reg_number} осталось менее 4 часов"
                greeting = f"Напоминаем, что срок рассмотрения этапа <strong>«{step.step_name}»</strong> по документу <strong>«{step.document.title}»</strong> истекает <strong>{step.due_date.strftime('%d.%m.%Y %H:%M')}</strong>."
                rows = f"""
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px 0; color: #64748b;">Документ:</td>
                        <td style="padding: 10px 0; font-weight: 600;">{step.document.reg_number or step.document.title}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px 0; color: #64748b;">Дедлайн:</td>
                        <td style="padding: 10px 0; font-weight: 600; color: #d97706;">{step.due_date.strftime('%d.%m.%Y %H:%M')}</td>
                    </tr>
                """
                html = cls._build_email_template(
                    header_title="Приближение дедлайна SLA",
                    greeting_text=greeting,
                    document_info_rows=rows,
                    action_button_url=f"/logistics/docflow/{step.document.id}/",
                    action_button_text="Срочно рассмотреть документ",
                )
                approaching_sent += cls.send_html_notification_email(subject, html, emails)

        for step in overdue_steps:
            recipients = cls.get_step_recipients(step)
            # При просрочке добавляем также автора документа для контроля
            recipients.append(step.document.initiator)
            emails = list({u.email for u in recipients if u.email})
            if emails:
                subject = f"Срочно: Просрочено согласование документа {step.document.reg_number}"
                greeting = f"Внимание: Превышен нормативный срок рассмотрения этапа <strong>«{step.step_name}»</strong> по документу <strong>«{step.document.title}»</strong> (дедлайн был {step.due_date.strftime('%d.%m.%Y %H:%M')})."
                rows = f"""
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px 0; color: #64748b;">Документ:</td>
                        <td style="padding: 10px 0; font-weight: 600;">{step.document.reg_number or step.document.title}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0; background-color: #fef2f2;">
                        <td style="padding: 10px 8px; color: #991b1b; font-weight: 600;">Просрочено с:</td>
                        <td style="padding: 10px 8px; color: #7f1d1d; font-weight: 700;">{step.due_date.strftime('%d.%m.%Y %H:%M')}</td>
                    </tr>
                """
                html = cls._build_email_template(
                    header_title="Просрочка согласования документа",
                    greeting_text=greeting,
                    document_info_rows=rows,
                    action_button_url=f"/logistics/docflow/{step.document.id}/",
                    action_button_text="Немедленно согласовать",
                )
                overdue_sent += cls.send_html_notification_email(subject, html, emails)

        return {
            "approaching_count": approaching_steps.count(),
            "approaching_emails_sent": approaching_sent,
            "overdue_count": overdue_steps.count(),
            "overdue_emails_sent": overdue_sent,
        }
