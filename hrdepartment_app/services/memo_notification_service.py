# -*- coding: utf-8 -*-
"""Сервисный слой уведомлений по процессам служебных записок (MemoNotificationService).

Обеспечивает централизованную обработку жизненного цикла служебных записок
(ApprovalOficialMemoProcess) компании БАРКОЛ, формирование печатных форм в изолированных
временных директориях, отправку через UniversalEmailService и UniversalTelegramService
в неблокирующем асинхронном режиме.
"""

import datetime
import logging
import os
import pathlib
import uuid
from typing import Any, Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from openpyxl import load_workbook

from administration_app.utils import ending_day, format_name_initials
from customers_app.models import DataBaseUser
from hrdepartment_app.models import (
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
)
from mailbox_app.services.email_service import UniversalEmailService
from telegram_app.services.telegram_service import UniversalTelegramService

logger = logging.getLogger(__name__)


class MemoNotificationService:
    """Сервис отправки многоканальных уведомлений по бизнес-процессам служебных записок."""

    @classmethod
    def get_portal_url(cls) -> str:
        """Возвращает базовый URL корпоративного портала.

        Returns:
            str: URL портала без завершающего слэша.
        """
        url = getattr(settings, "PORTAL_BASE_URL", "https://corp.barkol.ru")
        return str(url).rstrip("/")

    @classmethod
    def get_process_url(cls, process_id: int) -> str:
        """Формирует прямую веб-ссылку на карточку процесса согласования на портале.

        Args:
            process_id: Первичный ключ процесса.

        Returns:
            str: Полный URL для перехода к процессу.
        """
        return f"{cls.get_portal_url()}/hr/bpmemo/{process_id}/update/"

    @classmethod
    def dispatch_event(
        cls,
        process_id: int,
        event_type: str,
        actor_id: Optional[int] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Асинхронно ставит событие смены статуса СЗ в очередь Celery после фиксации транзакции.

        Args:
            process_id: ID процесса ApprovalOficialMemoProcess.
            event_type: Тип события ('SUBMITTED', 'APPROVED', 'LOCATION_SET',
                'ORDER_ISSUED', 'ORIGINALS_RECEIVED', 'TRANSFERRED_TO_ACCOUNTING',
                'COMPLETED', 'CANCELLED', 'REJECTED').
            actor_id: Опциональный ID пользователя, инициировавшего действие.
            extra_context: Дополнительные параметры (например, причина отмены).

        Returns:
            bool: True, если задача поставлена в очередь.
        """
        def _enqueue():
            try:
                from hrdepartment_app.tasks import process_memo_notification_task
                process_memo_notification_task.delay(
                    process_id=process_id,
                    event_type=event_type,
                    actor_id=actor_id,
                    extra_context=extra_context,
                )
                logger.info(
                    "[MemoNotify] Событие %s для процесса ID=%d передано в Celery.",
                    event_type,
                    process_id,
                )
            except Exception as exc:
                logger.error(
                    "[MemoNotify] Не удалось поставить задачу события %s (ID=%d) в Celery: %s",
                    event_type,
                    process_id,
                    exc,
                )

        transaction.on_commit(_enqueue)
        return True

    @classmethod
    def handle_event_sync(
        cls,
        process_id: int,
        event_type: str,
        actor_id: Optional[int] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Синхронный обработчик события, исполняемый в воркере Celery.

        Args:
            process_id: Первичный ключ процесса.
            event_type: Тип бизнес-события.
            actor_id: ID пользователя-инициатора.
            extra_context: Дополнительные параметры.

        Returns:
            bool: True при успешной обработке, False при ошибке.
        """
        process = (
            ApprovalOficialMemoProcess.objects.select_related(
                "document",
                "document__person",
                "document__person__user_work_profile",
                "document__person__user_work_profile__job",
                "document__person__user_work_profile__divisions",
                "document__purpose_trip",
                "person_executor",
                "person_agreement",
                "person_distributor",
                "person_department_staff",
                "person_clerk",
                "person_hr",
                "person_accounting",
                "order",
                "reason_cancellation",
            )
            .prefetch_related(
                "document__place_production_activity",
            )
            .filter(pk=process_id)
            .first()
        )

        if not process or not process.document:
            logger.warning("[MemoNotify] Процесс ID=%d или его документ не найден.", process_id)
            return False

        logger.info("[MemoNotify:Worker] Обработка события '%s' для СЗ ID=%d", event_type, process_id)

        try:
            if event_type == "SUBMITTED":
                return cls._notify_submitted(process)
            elif event_type == "APPROVED":
                return cls._notify_approved(process)
            elif event_type == "LOCATION_SET":
                return cls._notify_location_set(process)
            elif event_type == "ORDER_ISSUED":
                return cls._notify_order_issued(process)
            elif event_type == "ORIGINALS_RECEIVED":
                return cls._notify_originals_received(process)
            elif event_type == "TRANSFERRED_TO_ACCOUNTING":
                return cls._notify_transferred_accounting(process)
            elif event_type == "COMPLETED":
                return cls._notify_completed(process)
            elif event_type == "CANCELLED":
                return cls._notify_cancelled(process, extra_context)
            elif event_type == "REJECTED":
                return cls._notify_rejected(process, extra_context)
            else:
                logger.warning("[MemoNotify] Неизвестный тип события: %s", event_type)
                return False
        except Exception as exc:
            logger.exception("[MemoNotify] Критическая ошибка обработки события %s: %s", event_type, exc)
            return False

    # -------------------------------------------------------------------------
    # Обработчики конкретных этапов бизнес-процесса
    # -------------------------------------------------------------------------

    @classmethod
    def _notify_submitted(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление согласующего лица о новой поданной служебной записке."""
        doc = process.document
        person = doc.person
        url = cls.get_process_url(process.pk)
        places = [p.name for p in doc.place_production_activity.all()]
        places_str = ", ".join(places) if places else "Не указано"
        period_str = f"{doc.period_from.strftime('%d.%m.%Y')} — {doc.period_for.strftime('%d.%m.%Y')}"

        # Определение адресатов согласования
        agreement_users: List[DataBaseUser] = []
        if process.person_agreement:
            agreement_users.append(process.person_agreement)
        else:
            job_obj = getattr(getattr(process.person_executor, "user_work_profile", None), "job", None)
            if job_obj:
                directions = BusinessProcessDirection.objects.filter(person_executor=job_obj)
                jobs = [j for d in directions for j in d.person_agreement.all()]
                agreement_users = list(
                    DataBaseUser.objects.filter(
                        user_work_profile__job__in=jobs,
                        is_active=True,
                    ).distinct()
                )

        if not agreement_users:
            logger.warning("[MemoNotify:SUBMITTED] Не найдены согласующие лица для СЗ ID=%d", process.pk)
            return False

        # Формирование текста Telegram
        tg_text = (
            f"✈️ <b>Служебная записка на согласование</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Должность: {person.user_work_profile.job.name if person.user_work_profile and person.user_work_profile.job else ''}\n"
            f"Цель: {doc.purpose_trip}\n"
            f"Место: {places_str}\n"
            f"Период: {period_str}\n"
            f"Инициатор: {process.person_executor}\n"
        )

        reply_markup = UniversalTelegramService.build_inline_keyboard([
            [
                {"text": "✅ Согласовать", "callback_data": f"bpmemo_approve:{process.pk}"},
                {"text": "❌ Отклонить", "callback_data": f"bpmemo_reject:{process.pk}"},
            ],
            [
                {"text": "📄 Открыть на портале", "url": url},
            ],
        ])

        # Формирование Email
        email_subject = f"Служебная записка на согласование: {person} ({places_str})"
        email_html = (
            f"<h3>Служебная записка на согласование</h3>"
            f"<p>Уважаемый руководитель, на портале зарегистрирована служебная записка, требующая вашего согласования.</p>"
            f"<ul>"
            f"<li><b>Сотрудник:</b> {person}</li>"
            f"<li><b>Цель поездки:</b> {doc.purpose_trip}</li>"
            f"<li><b>Место:</b> {places_str}</li>"
            f"<li><b>Сроки:</b> {period_str}</li>"
            f"<li><b>Инициатор:</b> {process.person_executor}</li>"
            f"</ul>"
            f"<p><a href='{url}' style='background-color:#1E40AF;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;'>Перейти к согласованию</a></p>"
        )

        for user in agreement_users:
            if user.telegram_id:
                UniversalTelegramService.send_message_sync(
                    chat_id=user.telegram_id,
                    text=tg_text,
                    reply_markup=reply_markup,
                )
            if user.email:
                UniversalEmailService.send_async_email(
                    subject=email_subject,
                    recipient_list=[user.email],
                    html_message=email_html,
                )

        return True

    @classmethod
    def _notify_approved(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление распределителя жилья о согласовании СЗ руководителем."""
        doc = process.document
        person = doc.person
        url = cls.get_process_url(process.pk)
        places = [p.name for p in doc.place_production_activity.all()]
        places_str = ", ".join(places) if places else "Не указано"
        period_str = f"{doc.period_from.strftime('%d.%m.%Y')} — {doc.period_for.strftime('%d.%m.%Y')}"

        distributors: List[DataBaseUser] = []
        if process.person_distributor:
            distributors.append(process.person_distributor)
        else:
            distributors = list(
                DataBaseUser.objects.filter(
                    Q(user_work_profile__divisions__type_of_role="1")
                    & Q(user_work_profile__job__right_to_approval=True),
                    is_active=True,
                ).distinct()
            )

        tg_text = (
            f"🏢 <b>Утверждение места проживания</b>\n\n"
            f"Руководитель согласовал служебную записку:\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Место: {places_str}\n"
            f"Период: {period_str}\n"
            f"Согласующий: {process.person_agreement}\n\n"
            f"Пожалуйста, утвердите бронирование служебной квартиры или гостиницы."
        )

        reply_markup = UniversalTelegramService.build_inline_keyboard([
            [{"text": "🏨 Выбрать жилье на портале", "url": url}]
        ])

        for dist in distributors:
            if dist.telegram_id:
                UniversalTelegramService.send_message_sync(
                    chat_id=dist.telegram_id,
                    text=tg_text,
                    reply_markup=reply_markup,
                )

        return True

    @classmethod
    def _notify_location_set(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление кадровой службы о необходимости издания приказа."""
        doc = process.document
        person = doc.person
        url = cls.get_process_url(process.pk)
        accom_display = process.get_accommodation_display() if hasattr(process, "get_accommodation_display") else "Не указано"
        period_str = f"{doc.period_from.strftime('%d.%m.%Y')} — {doc.period_for.strftime('%d.%m.%Y')}"

        hr_staff: List[DataBaseUser] = []
        if process.person_department_staff:
            hr_staff.append(process.person_department_staff)
        else:
            hr_staff = list(
                DataBaseUser.objects.filter(
                    Q(user_work_profile__divisions__type_of_role="2")
                    & Q(user_work_profile__job__right_to_approval=True),
                    is_active=True,
                ).distinct()
            )

        tg_text = (
            f"📝 <b>Необходимо издать приказ по поездке</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Период: {period_str}\n"
            f"Проживание: {accom_display}\n\n"
            f"Все согласования пройдены. Пожалуйста, оформите приказ в отделе кадров."
        )

        reply_markup = UniversalTelegramService.build_inline_keyboard([
            [{"text": "📋 Оформить приказ на портале", "url": url}]
        ])

        for hr in hr_staff:
            if hr.telegram_id:
                UniversalTelegramService.send_message_sync(
                    chat_id=hr.telegram_id,
                    text=tg_text,
                    reply_markup=reply_markup,
                )

        return True

    @classmethod
    def _notify_order_issued(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Формирует служебное задание (PDF/XLSX) и отправляет сотруднику, инициатору и в летную службу."""
        doc = process.document
        person = doc.person
        executor = process.person_executor
        order = process.order

        if not order:
            logger.warning("[MemoNotify:ORDER] Приказ не привязан к процессу ID=%d", process.pk)
            return False

        # Генерация документа во временную директорию
        xlsx_path, pdf_path = cls._generate_memo_documents(process)

        # Выбираем результирующий файл вложения (предпочтительно PDF, с откатом на XLSX)
        attachment_path = pdf_path if (pdf_path and os.path.exists(pdf_path)) else xlsx_path
        attachment_bytes = None
        attachment_filename = f"Служебное_задание_Приказ_{order.document_number}.pdf" if (pdf_path and os.path.exists(pdf_path)) else f"Служебное_задание_{order.document_number}.xlsx"

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                attachment_bytes = f.read()

        # Формирование контекста письма
        delta = doc.period_for - doc.period_from
        places = [p.name for p in doc.place_production_activity.all()]
        type_trip_title = "поездку" if doc.type_trip == "1" else "командировку"

        email_context = {
            "greetings": "Уважаемый" if person.gender == "male" else "Уважаемая",
            "person": str(person),
            "place": ", ".join(places),
            "type_trip": f"Вы направляетесь в служебную {type_trip_title}",
            "type_trip_variant": f"направлении в служебную {type_trip_title}",
            "type_trip_variant_second": f"направление в служебную {type_trip_title}",
            "type_trip_second": "поездки" if doc.type_trip == "1" else "командировки",
            "purpose_trip": str(doc.purpose_trip),
            "order_number": str(order.document_number),
            "order_date": order.document_date.strftime("%d.%m.%Y"),
            "delta": str(ending_day(int(delta.days) + 1)),
            "period_from": doc.period_from.strftime("%d.%m.%Y"),
            "period_for": doc.period_for.strftime("%d.%m.%Y"),
            "accommodation": "Квартира" if process.accommodation == "1" else "Гостиница",
            "person_executor": format_name_initials(executor) if executor else "",
            "mail_to_copy": str(executor.email if executor else ""),
            "person_distributor": format_name_initials(process.person_distributor) if process.person_distributor else "",
            "Year": str(datetime.datetime.today().year),
            "type_trip_extension": "",
        }

        html_content = render_to_string("hrdepartment_app/email_template.html", email_context)
        subject_mail = f"Направление в служебную {type_trip_title}. Приказ № {order.document_number}"

        attachments_payload = None
        if attachment_bytes:
            attachments_payload = [{
                "filename": attachment_filename,
                "content": attachment_bytes,
                "mimetype": "application/pdf" if attachment_filename.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }]

        # Список получателей email
        recipients = []
        if person.email:
            recipients.append(person.email)
        if executor and executor.email and executor.email not in recipients:
            recipients.append(executor.email)

        # Если это СПК (летный состав), добавляем fly@barkol.ru
        if doc.type_trip == "2":
            fly_email = getattr(settings, "FLIGHT_DEPARTMENT_EMAIL", "fly@barkol.ru")
            if fly_email not in recipients:
                recipients.append(fly_email)

        if recipients:
            UniversalEmailService.send_async_email(
                subject=subject_mail,
                recipient_list=recipients,
                html_message=html_content,
                attachments=attachments_payload,
            )

        # Отправка Telegram командируемому
        if person.telegram_id:
            tg_text = (
                f"✈️ <b>Вам оформлена служебная {type_trip_title}!</b>\n\n"
                f"Приказ: <b>№ {order.document_number} от {order.document_date.strftime('%d.%m.%Y')}</b>\n"
                f"Место: {', '.join(places)}\n"
                f"Сроки: {doc.period_from.strftime('%d.%m.%Y')} — {doc.period_for.strftime('%d.%m.%Y')}\n"
                f"Проживание: {email_context['accommodation']}\n"
            )
            UniversalTelegramService.send_message_sync(chat_id=person.telegram_id, text=tg_text)

            if attachment_path and os.path.exists(attachment_path):
                UniversalTelegramService.send_document_sync(
                    chat_id=person.telegram_id,
                    document_path=attachment_path,
                    caption=f"Служебное задание (Приказ № {order.document_number})",
                )

        # Фиксируем статус отправки без каскадного срабатывания сигналов
        ApprovalOficialMemoProcess.objects.filter(pk=process.pk).update(email_send=True)

        # Очистка временных файлов
        cls._cleanup_temp_files([xlsx_path, pdf_path])
        return True

    @classmethod
    def _notify_originals_received(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление отдела кадров о получении оригиналов документов."""
        doc = process.document
        person = doc.person
        url = cls.get_process_url(process.pk)

        recipient = process.person_hr or process.person_department_staff
        if not recipient and process.document.person:
            recipient = process.person_executor

        if recipient and recipient.telegram_id:
            tg_text = (
                f"📑 <b>Получены оригиналы документов по поездке</b>\n\n"
                f"Сотрудник: <b>{person}</b>\n"
                f"Дата получения: {process.date_receipt_original.strftime('%d.%m.%Y') if process.date_receipt_original else datetime.date.today().strftime('%d.%m.%Y')}\n"
                f"Примечание: {process.originals_docs_comment or 'Без примечаний'}"
            )
            reply_markup = UniversalTelegramService.build_inline_keyboard([
                [{"text": "📄 Открыть карточку СЗ", "url": url}]
            ])
            UniversalTelegramService.send_message_sync(
                chat_id=recipient.telegram_id,
                text=tg_text,
                reply_markup=reply_markup,
            )
        return True

    @classmethod
    def _notify_transferred_accounting(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление бухгалтерии о передаче документов на расчет."""
        doc = process.document
        person = doc.person
        url = cls.get_process_url(process.pk)

        accountants: List[DataBaseUser] = []
        if process.person_accounting:
            accountants.append(process.person_accounting)
        else:
            accountants = list(
                DataBaseUser.objects.filter(
                    Q(user_work_profile__job__right_to_approval=True)
                    & Q(user_work_profile__divisions__name__icontains="бухгалтер"),
                    is_active=True,
                ).distinct()
            )

        tg_text = (
            f"💰 <b>Документы по служебной поездке переданы в бухгалтерию</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Аванс / Расходы: {process.prepaid_expense_summ} руб.\n"
            f"Пожалуйста, выполните проверку и закрытие авансового отчета."
        )
        reply_markup = UniversalTelegramService.build_inline_keyboard([
            [{"text": "💼 Открыть в бухгалтерии", "url": url}]
        ])

        for acc in accountants:
            if acc.telegram_id:
                UniversalTelegramService.send_message_sync(
                    chat_id=acc.telegram_id,
                    text=tg_text,
                    reply_markup=reply_markup,
                )
        return True

    @classmethod
    def _notify_completed(cls, process: ApprovalOficialMemoProcess) -> bool:
        """Уведомление командируемого и исполнителя о полном закрытии поездки."""
        doc = process.document
        person = doc.person
        executor = process.person_executor

        tg_text = (
            f"🎉 <b>Документооборот по служебной поездке завершен!</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Отчет проверен бухгалтерией, расходы утверждены."
        )

        for target in (person, executor):
            if target and target.telegram_id:
                UniversalTelegramService.send_message_sync(chat_id=target.telegram_id, text=tg_text)

        return True

    @classmethod
    def _notify_cancelled(cls, process: ApprovalOficialMemoProcess, extra_context: Optional[Dict[str, Any]]) -> bool:
        """Уведомление всех заинтересованных сторон об аннулировании служебной записки."""
        doc = process.document
        person = doc.person
        executor = process.person_executor
        order = process.order

        reason_text = (
            str(process.reason_cancellation)
            if process.reason_cancellation
            else (extra_context.get("reason", "Отменено руководством") if extra_context else "Отменено руководством")
        )

        current_context = {
            "title": doc.title if doc else "Служебная поездка",
            "order_number": str(order.document_number) if order else "--//--",
            "order_date": str(order.document_date.strftime("%d.%m.%Y")) if order and order.document_date else "--//--",
            "reason_cancellation": reason_text,
            "person_executor": str(executor) if executor else "",
            "person_distributor": str(process.person_distributor) if process.person_distributor else "",
            "person_department_staff": str(process.person_department_staff) if process.person_department_staff else "",
            "mail_to_copy": str(executor.email if executor else ""),
        }

        html_content = render_to_string("hrdepartment_app/email_cancel_bpmemo.html", current_context)
        subject_mail = f"Аннулирование служебной поездки: {person} (Приказ {current_context['order_number']})"

        recipients = []
        for u in (person, executor, process.person_distributor, process.person_department_staff):
            if u and u.email and u.email not in recipients:
                recipients.append(u.email)

        if recipients:
            UniversalEmailService.send_async_email(
                subject=subject_mail,
                recipient_list=recipients,
                html_message=html_content,
            )

        tg_text = (
            f"🚫 <b>Служебная поездка аннулирована!</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Приказ: {current_context['order_number']} от {current_context['order_date']}\n"
            f"Причина отмены: <i>{reason_text}</i>"
        )
        for u in (person, executor):
            if u and u.telegram_id:
                UniversalTelegramService.send_message_sync(chat_id=u.telegram_id, text=tg_text)

        return True

    @classmethod
    def _notify_rejected(cls, process: ApprovalOficialMemoProcess, extra_context: Optional[Dict[str, Any]]) -> bool:
        """Уведомление инициатора об отклонении служебной записки руководителем."""
        doc = process.document
        person = doc.person
        executor = process.person_executor
        reason = extra_context.get("reason", "Отклонено согласующим лицом") if extra_context else "Отклонено согласующим лицом"

        tg_text = (
            f"❌ <b>Служебная записка отклонена руководителем</b>\n\n"
            f"Сотрудник: <b>{person}</b>\n"
            f"Причина: <i>{reason}</i>\n"
            f"Пожалуйста, свяжитесь с руководителем или внесите корректировки."
        )

        if executor and executor.telegram_id:
            UniversalTelegramService.send_message_sync(chat_id=executor.telegram_id, text=tg_text)

        if executor and executor.email:
            UniversalEmailService.send_async_email(
                subject=f"Служебная записка отклонена: {person}",
                recipient_list=[executor.email],
                html_message=f"<p>{tg_text.replace(chr(10), '<br>')}</p>",
            )

        return True

    # -------------------------------------------------------------------------
    # Генерация печатных форм в безопасном изолированном окружении
    # -------------------------------------------------------------------------

    @classmethod
    def _generate_memo_documents(cls, process: ApprovalOficialMemoProcess) -> Tuple[Optional[str], Optional[str]]:
        """Генерирует Excel и PDF файл служебного задания с уникальными временными именами.

        Returns:
            Tuple[Optional[str], Optional[str]]: (путь_к_xlsx, путь_к_pdf).
        """
        doc = process.document
        person = doc.person
        order = process.order

        temp_dir = pathlib.Path(settings.BASE_DIR) / "media" / "temp_memos"
        temp_dir.mkdir(parents=True, exist_ok=True)

        unique_id = uuid.uuid4().hex[:8]
        output_xlsx_path = temp_dir / f"sp_{process.pk}_{unique_id}.xlsx"

        # Определение шаблона
        division_affil_pk = getattr(
            getattr(getattr(person, "user_work_profile", None), "job", None),
            "division_affiliation_id",
            None,
        )
        if division_affil_pk == 2:
            template_name = "spk.xlsx" if doc.type_trip == "2" else "sp.xlsx"
        else:
            template_name = "sp2k.xlsx" if doc.type_trip == "2" else "sp2.xlsx"

        template_path = pathlib.Path(settings.BASE_DIR) / "static" / "DocxTemplates" / template_name
        if not template_path.exists():
            logger.error("[MemoNotify:DocGen] Шаблон не найден: %s", template_path)
            return None, None

        try:
            wb = load_workbook(template_path)
            ws = wb.active
            delta = doc.period_for - doc.period_from
            places = [p.name for p in doc.place_production_activity.all()]

            ws["C3"] = str(person)
            ws["M3"] = str(person.service_number or "")
            ws["C4"] = str(getattr(getattr(person, "user_work_profile", None), "job", ""))
            ws["C5"] = str(getattr(getattr(person, "user_work_profile", None), "divisions", ""))
            ws["C6"] = f"Приказ № {order.document_number}"
            ws["F6"] = order.document_date.strftime("%d.%m.%y")
            ws["H6"] = f"на {ending_day(int(delta.days) + 1)}"
            ws["L6"] = doc.period_from.strftime("%d.%m.%y")
            ws["O6"] = doc.period_for.strftime("%d.%m.%y")
            ws["C8"] = ", ".join(places)
            ws["C9"] = str(doc.purpose_trip)

            if getattr(doc.purpose_trip, "title", "") == "Дежурства на ПСР":
                ws["H86"] = ", из них ПСР"
                ws["K86"] = "__________"

            agreement_text = ""
            if process.person_agreement:
                agreement_job = getattr(getattr(process.person_agreement, "user_work_profile", None), "job", "")
                agreement_text = f"{agreement_job}, {format_name_initials(process.person_agreement)}"
            ws["A90"] = agreement_text

            wb.save(output_xlsx_path)
            wb.close()
            logger.info("[MemoNotify:DocGen] Сформирован XLSX: %s", output_xlsx_path)
        except Exception as xlsx_err:
            logger.error("[MemoNotify:DocGen] Ошибка генерации XLSX: %s", xlsx_err, exc_info=True)
            return None, None

        # Конвертация в PDF через msoffice2pdf (с безопасным откатом)
        output_pdf_path = None
        try:
            from msoffice2pdf import convert
            pdf_result = convert(source=str(output_xlsx_path), output_dir=str(temp_dir), soft=0)
            if pdf_result and os.path.exists(str(pdf_result)):
                output_pdf_path = str(pdf_result)
                logger.info("[MemoNotify:DocGen] Успешно сконвертирован в PDF: %s", output_pdf_path)
        except Exception as conv_err:
            logger.warning("[MemoNotify:DocGen] Ошибка конвертации в PDF: %s. Будет использован XLSX.", conv_err)

        return str(output_xlsx_path), output_pdf_path

    @staticmethod
    def _cleanup_temp_files(paths: List[Optional[str]]) -> None:
        """Безопасно удаляет временные файлы с диска."""
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError as cleanup_err:
                    logger.debug("[MemoNotify:Cleanup] Не удалось удалить временный файл %s: %s", p, cleanup_err)
