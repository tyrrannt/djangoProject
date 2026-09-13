"""Сервисный слой маршрутизации и визирования документов СЭД (logistics_app)."""

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowDocument,
    DocFlowRouteStep,
    DocFlowRouteStepTemplate,
    DocFlowRouteTemplate,
)
from logistics_app.services.docflow_notification_service import DocFlowNotificationService

logger = logging.getLogger(__name__)


class DocFlowRoutingService:
    """Сервис управления жизненным циклом и маршрутами согласования документов СЭД.

    Реализует:
    - Построение цепочки этапов из системного шаблона;
    - Запуск и активацию первого этапа согласования;
    - Обработку визирования (последовательного, параллельного «И» / «ИЛИ», руководителя);
    - Наложение Простой Электронной Подписи (ПЭП) и аудит-трейл;
    - Многошаговый откат на любой предшествующий этап;
    - Возврат автору на доработку и последующее возобновление маршрута;
    - Отклонение и делегирование задач рассмотрения.
    """

    @classmethod
    def generate_pep_signature(
        cls,
        user: DataBaseUser,
        document: DocFlowDocument,
        action: str,
    ) -> Tuple[str, str]:
        """Генерирует криптографический слепок ПЭП и уникальный идентификатор сертификата.

        Формирует SHA-256 хэш на основе идентификаторов пользователя, документа,
        временной метки, типа действия и секретного ключа портала.

        Args:
            user (DataBaseUser): Пользователь, накладывающий визу ПЭП.
            document (DocFlowDocument): Согласуемый документ.
            action (str): Тип действия (APPROVED, APPROVED_WITH_COMMENTS и т.д.).

        Returns:
            Tuple[str, str]: Кортеж (pep_signature_hash, pep_certificate_id).
        """
        now_iso = timezone.now().isoformat()
        secret = getattr(settings, "SECRET_KEY", "barkol-portal-docflow-secret")
        raw_payload = f"{user.id}:{document.id}:{now_iso}:{action}:{secret}"
        signature_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        certificate_id = f"PEP-{user.id:04d}-{uuid.uuid4().hex[:8].upper()}"
        return signature_hash, certificate_id

    @classmethod
    def build_route_from_template(
        cls,
        document: DocFlowDocument,
        template_id: Optional[int] = None,
    ) -> List[DocFlowRouteStep]:
        """Формирует цепочку шагов маршрута согласования документа из шаблона.

        Если template_id не передан, используется шаблон по умолчанию для doc_type документа.

        Args:
            document (DocFlowDocument): Карточка документа СЭД.
            template_id (Optional[int]): Идентификатор конкретного шаблона DocFlowRouteTemplate.

        Returns:
            List[DocFlowRouteStep]: Список созданных шагов маршрута.

        Raises:
            ValueError: Если подходящий шаблон маршрута не найден.
        """
        if template_id:
            template = DocFlowRouteTemplate.objects.filter(id=template_id).first()
        else:
            template = DocFlowRouteTemplate.objects.filter(
                doc_type=document.doc_type,
                is_default=True,
            ).first() or DocFlowRouteTemplate.objects.filter(
                doc_type=document.doc_type,
            ).first()

        if not template:
            raise ValueError(f"Шаблон маршрута для типа «{document.doc_type.name}» не найден.")

        with transaction.atomic():
            # Удаляем старые незапущенные шаги (если пересоздаем черновик)
            document.route_steps.all().delete()

            created_steps = []
            step_templates = template.steps.all().order_by("step_order")

            for st in step_templates:
                step = DocFlowRouteStep.objects.create(
                    document=document,
                    step_order=st.step_order,
                    step_name=st.step_name,
                    step_type=st.step_type,
                    assigned_division=st.assigned_division,
                    assigned_user=st.assigned_user,
                    status=DocFlowRouteStep.Status.PENDING,
                    sla_hours=st.sla_hours,
                    can_rollback_to=st.can_rollback_to,
                    allow_reviewer_file_edit=st.allow_reviewer_file_edit,
                )

                # Переносим группу пользователей для параллельного согласования
                if st.assigned_users.exists():
                    step.assigned_users.set(st.assigned_users.all())

                # Динамическое определение руководителя подразделения автора
                if st.step_type == DocFlowRouteStepTemplate.StepType.HEAD_OF_DEPARTMENT:
                    initiator = document.initiator
                    user_work_profile = getattr(initiator, "user_work_profile", None) if initiator else None
                    div = getattr(user_work_profile, "divisions", None) if user_work_profile else None
                    if div:
                        head = (
                            DataBaseUser.objects.filter(
                                user_work_profile__divisions=div,
                                user_work_profile__job__right_to_approval=True,
                                is_active=True,
                            ).first()
                            or DataBaseUser.objects.filter(
                                user_work_profile__divisions=div,
                                is_active=True,
                                user_work_profile__job__name__icontains="начальник",
                            ).first()
                            or DataBaseUser.objects.filter(
                                user_work_profile__divisions=div,
                                is_active=True,
                            ).first()
                        )
                        if head:
                            step.assigned_user = head
                            step.save(update_fields=["assigned_user"])
                        else:
                            step.assigned_division = div
                            step.save(update_fields=["assigned_division"])

                created_steps.append(step)

            logger.info(
                "Документ UUID %s: успешно сформирован маршрут из %d шагов по шаблону «%s»",
                document.id,
                len(created_steps),
                template.name,
            )
            return created_steps

    @classmethod
    def start_approval_process(
        cls,
        document: DocFlowDocument,
        user: DataBaseUser,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Запускает процесс согласования документа по маршруту.

        Переводит документ в статус ON_APPROVAL, генерирует регистрационный номер
        (при отсутствии), активирует 1-й шаг маршрута и рассылает первичные уведомления.

        Args:
            document (DocFlowDocument): Запускаемый документ СЭД.
            user (DataBaseUser): Инициатор запуска процесса.
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowDocument: Обновленный документ.

        Raises:
            ValueError: Если документ не готов к запуску или отсутствуют шаги.
        """
        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)

            if doc_locked.status not in [
                DocFlowDocument.Status.DRAFT,
                DocFlowDocument.Status.ON_REGISTRATION,
                DocFlowDocument.Status.ON_REWORK,
            ]:
                raise ValueError(f"Невозможно запустить согласование для документа в статусе {doc_locked.get_status_display()}.")

            # Гарантируем регистрационный номер и дату
            if not doc_locked.reg_number:
                doc_locked.assign_registration_number(save=False)
            if not doc_locked.reg_date:
                doc_locked.reg_date = timezone.now().date()

            # Если шаги маршрута еще не были созданы, строим из шаблона
            if not doc_locked.route_steps.exists():
                cls.build_route_from_template(doc_locked)

            first_step = doc_locked.route_steps.order_by("step_order").first()
            if not first_step:
                raise ValueError("В документе отсутствуют шаги маршрута согласования.")

            # Активируем первый шаг
            first_step.status = DocFlowRouteStep.Status.IN_PROGRESS
            first_step.started_at = timezone.now()
            first_step.due_date = timezone.now() + timedelta(hours=first_step.sla_hours)
            first_step.save()

            # Переводим документ в статус «На согласовании»
            doc_locked.status = DocFlowDocument.Status.ON_APPROVAL
            doc_locked.current_step_order = first_step.step_order
            if not doc_locked.deadline:
                doc_locked.deadline = timezone.now() + timedelta(hours=doc_locked.doc_type.default_sla_hours)
            doc_locked.save()

            # Фиксируем запуск в журнале аудита
            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=first_step,
                user=user,
                action=DocFlowApprovalLog.Action.STARTED,
                comment=f"Маршрут согласования успешно запущен с этапа №{first_step.step_order}: «{first_step.step_name}».",
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            # Отправляем уведомление согласующим первого этапа
            DocFlowNotificationService.notify_step_assigned(first_step)

            logger.info("Документ %s: согласование успешно запущено пользователем %s", doc_locked.reg_number, user)
            return doc_locked

    @classmethod
    def process_approval(
        cls,
        document: DocFlowDocument,
        step: DocFlowRouteStep,
        user: DataBaseUser,
        comment: str = "",
        is_minor_edit: bool = False,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> Dict[str, Any]:
        """Обрабатывает визирование (согласование) текущего активного этапа согласующим лицом.

        Фиксирует электронную подпись ПЭП, проверяет условия завершения шага
        (консенсус для параллельного «И» или одиночное решение), переводит документ
        на следующий шаг либо присваивает итоговый статус APPROVED.

        Args:
            document (DocFlowDocument): Согласуемый документ.
            step (DocFlowRouteStep): Текущий шаг маршрута.
            user (DataBaseUser): Согласующий сотрудник.
            comment (str): Комментарий / особое мнение. Defaults to "".
            is_minor_edit (bool): Флаг наличия редакционных правок. Defaults to False.
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            Dict[str, Any]: Результат обработки ('status': 'next_step' | 'completed' | 'parallel_waiting').

        Raises:
            ValueError: Если шаг не активен или согласующий не имеет прав на визирование.
        """
        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)
            step_locked = DocFlowRouteStep.objects.select_for_update().get(id=step.id)

            if step_locked.status != DocFlowRouteStep.Status.IN_PROGRESS:
                raise ValueError("Данный шаг не находится в процессе согласования.")

            # Добавляем сотрудника в список фактически согласовавших
            step_locked.approved_users.add(user)

            # Формируем штамп Простой Электронной Подписи
            action_type = (
                DocFlowApprovalLog.Action.APPROVED_WITH_COMMENTS
                if (comment and is_minor_edit)
                else DocFlowApprovalLog.Action.APPROVED
            )
            sig_hash, cert_id = cls.generate_pep_signature(user, doc_locked, action_type)

            # Проверяем условия завершения текущего шага
            is_step_finished = True
            if step_locked.step_type == DocFlowRouteStepTemplate.StepType.PARALLEL_AND:
                assigned_count = step_locked.assigned_users.count()
                approved_count = step_locked.approved_users.count()
                is_step_finished = approved_count >= assigned_count

            # Записываем действие в журнал аудита ПЭП
            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=step_locked,
                user=user,
                action=action_type,
                comment=comment,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
                pep_signature_hash=sig_hash,
                pep_certificate_id=cert_id,
            )

            if is_step_finished:
                step_locked.status = DocFlowRouteStep.Status.APPROVED
                step_locked.completed_at = timezone.now()
                step_locked.save()

                # Ищем следующий шаг маршрута
                next_step = doc_locked.route_steps.filter(
                    step_order__gt=step_locked.step_order,
                    status=DocFlowRouteStep.Status.PENDING,
                ).order_by("step_order").first()

                if next_step:
                    next_step.status = DocFlowRouteStep.Status.IN_PROGRESS
                    next_step.started_at = timezone.now()
                    next_step.due_date = timezone.now() + timedelta(hours=next_step.sla_hours)
                    next_step.save()

                    doc_locked.current_step_order = next_step.step_order
                    doc_locked.save(update_fields=["current_step_order", "updated_at"])

                    DocFlowNotificationService.notify_step_assigned(next_step)

                    logger.info(
                        "Документ %s: этап №%d завершен, переход на этап №%d (%s)",
                        doc_locked.reg_number,
                        step_locked.step_order,
                        next_step.step_order,
                        next_step.step_name,
                    )
                    return {"status": "next_step", "document": doc_locked, "next_step": next_step}
                else:
                    # Все этапы успешно пройдены — документ финализирован
                    doc_locked.status = DocFlowDocument.Status.APPROVED
                    doc_locked.save(update_fields=["status", "updated_at"])

                    DocFlowNotificationService.notify_approval_complete(doc_locked)

                    logger.info("Документ %s: согласование успешно завершено со статусом APPROVED", doc_locked.reg_number)
                    return {"status": "completed", "document": doc_locked}
            else:
                step_locked.save()
                logger.info(
                    "Документ %s: параллельный этап №%d ожидает виз остальных участников",
                    doc_locked.reg_number,
                    step_locked.step_order,
                )
                return {"status": "parallel_waiting", "document": doc_locked, "step": step_locked}

    @classmethod
    def process_rollback(
        cls,
        document: DocFlowDocument,
        step: DocFlowRouteStep,
        user: DataBaseUser,
        target_step_order: int,
        comment: str,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Откатывает процесс согласования на выбранный предшествующий этап маршрута.

        Текущий шаг переводится в RETURNED, промежуточные шаги сбрасываются в PENDING,
        целевой этап активируется заново, а согласующему целевого этапа уходит уведомление.

        Args:
            document (DocFlowDocument): Документ СЭД.
            step (DocFlowRouteStep): Текущий активный шаг.
            user (DataBaseUser): Согласующий сотрудник, выполняющий откат.
            target_step_order (int): Порядковый номер шага, на который выполняется откат.
            comment (str): Обязательное мотивированное обоснование отката.
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowDocument: Обновленный документ СЭД.

        Raises:
            ValueError: При попытке отката на некорректный шаг или отсутствии комментария.
        """
        if not comment or not comment.strip():
            raise ValueError("Для выполнения отката шага необходимо указать замечания/причину.")

        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)
            step_locked = DocFlowRouteStep.objects.select_for_update().get(id=step.id)

            if target_step_order >= step_locked.step_order:
                raise ValueError("Откат возможен только на предшествующие этапы маршрута.")

            target_step = doc_locked.route_steps.filter(step_order=target_step_order).first()
            if not target_step:
                raise ValueError(f"Целевой этап №{target_step_order} не найден в маршруте.")

            if not target_step.can_rollback_to:
                raise ValueError(f"Откат на этап «{target_step.step_name}» запрещен регламентом.")

            # Фиксируем текущий шаг как возвращенный
            step_locked.status = DocFlowRouteStep.Status.RETURNED
            step_locked.completed_at = timezone.now()
            step_locked.save()

            # Сбрасываем промежуточные этапы между целевым и текущим
            intermediate_steps = doc_locked.route_steps.filter(
                step_order__gt=target_step_order,
                step_order__lt=step_locked.step_order,
            )
            for inter_step in intermediate_steps:
                inter_step.status = DocFlowRouteStep.Status.PENDING
                inter_step.started_at = None
                inter_step.completed_at = None
                inter_step.approved_users.clear()
                inter_step.save()

            # Активируем целевой этап заново
            target_step.status = DocFlowRouteStep.Status.IN_PROGRESS
            target_step.started_at = timezone.now()
            target_step.completed_at = None
            target_step.due_date = timezone.now() + timedelta(hours=target_step.sla_hours)
            target_step.approved_users.clear()
            target_step.save()

            # Обновляем текущий указатель шага документа
            doc_locked.current_step_order = target_step.step_order
            doc_locked.status = DocFlowDocument.Status.ON_APPROVAL
            doc_locked.save(update_fields=["current_step_order", "status", "updated_at"])

            # Фиксируем откат в журнале аудита
            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=step_locked,
                user=user,
                action=DocFlowApprovalLog.Action.ROLLBACK_TO_STEP,
                target_step_order=target_step_order,
                comment=f"Откат с этапа №{step_locked.step_order} на этап №{target_step_order} ({target_step.step_name}). Замечания: {comment}",
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            # Отправляем уведомление участникам целевого этапа
            DocFlowNotificationService.notify_step_assigned(
                target_step,
                is_rollback=True,
                rollback_comment=comment,
            )

            logger.info(
                "Документ %s: откат с шага №%d на шаг №%d сотрудником %s",
                doc_locked.reg_number,
                step_locked.step_order,
                target_step_order,
                user,
            )
            return doc_locked

    @classmethod
    def process_rework_return(
        cls,
        document: DocFlowDocument,
        step: Optional[DocFlowRouteStep],
        user: DataBaseUser,
        comment: str,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Возвращает документ автору/инициатору на доработку.

        Переводит документ в статус ON_REWORK, приостанавливает маршрут
        и отправляет уведомление автору документа с перечнем замечаний.

        Args:
            document (DocFlowDocument): Документ СЭД.
            step (Optional[DocFlowRouteStep]): Текущий шаг, с которого выполнен возврат.
            user (DataBaseUser): Согласующий сотрудник.
            comment (str): Замечания и перечень требуемых правок.
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowDocument: Обновленный документ.

        Raises:
            ValueError: При отсутствии комментария с замечаниями.
        """
        if not comment or not comment.strip():
            raise ValueError("Для возврата документа на доработку необходимо указать замечания.")

        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)

            if step:
                step_locked = DocFlowRouteStep.objects.select_for_update().get(id=step.id)
                step_locked.status = DocFlowRouteStep.Status.RETURNED
                step_locked.completed_at = timezone.now()
                step_locked.save()

            doc_locked.status = DocFlowDocument.Status.ON_REWORK
            doc_locked.save(update_fields=["status", "updated_at"])

            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=step,
                user=user,
                action=DocFlowApprovalLog.Action.RETURNED_TO_AUTHOR,
                comment=comment,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            DocFlowNotificationService.notify_document_returned(doc_locked, user, comment)

            logger.info("Документ %s: возвращен на доработку сотрудником %s", doc_locked.reg_number, user)
            return doc_locked

    @classmethod
    def restart_route_after_rework(
        cls,
        document: DocFlowDocument,
        user: DataBaseUser,
        resume_from_returned_step: bool = True,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Возобновляет маршрут согласования после загрузки исправлений автором.

        Предоставляет гибкость:
        - Либо возобновление с этапа, который вернул документ на доработку (по умолчанию);
        - Либо полный перезапуск маршрута с Шага 1.

        Args:
            document (DocFlowDocument): Документ СЭД в статусе ON_REWORK.
            user (DataBaseUser): Автор / Ответственный сотрудник.
            resume_from_returned_step (bool): Возобновить с шага замечания (True) или с Шага 1 (False).
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowDocument: Обновленный документ СЭД в статусе ON_APPROVAL.
        """
        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)

            active_step = None
            if resume_from_returned_step:
                returned_step = doc_locked.route_steps.filter(
                    status=DocFlowRouteStep.Status.RETURNED,
                ).order_by("step_order").first()

                if returned_step:
                    returned_step.status = DocFlowRouteStep.Status.IN_PROGRESS
                    returned_step.started_at = timezone.now()
                    returned_step.completed_at = None
                    returned_step.due_date = timezone.now() + timedelta(hours=returned_step.sla_hours)
                    returned_step.approved_users.clear()
                    returned_step.save()

                    active_step = returned_step
                    doc_locked.current_step_order = returned_step.step_order

            if not active_step:
                # Полный перезапуск с Шага 1
                for s in doc_locked.route_steps.all():
                    s.status = DocFlowRouteStep.Status.PENDING
                    s.started_at = None
                    s.completed_at = None
                    s.approved_users.clear()
                    s.save()

                first_step = doc_locked.route_steps.order_by("step_order").first()
                if first_step:
                    first_step.status = DocFlowRouteStep.Status.IN_PROGRESS
                    first_step.started_at = timezone.now()
                    first_step.due_date = timezone.now() + timedelta(hours=first_step.sla_hours)
                    first_step.save()
                    active_step = first_step
                    doc_locked.current_step_order = first_step.step_order

            doc_locked.status = DocFlowDocument.Status.ON_APPROVAL
            doc_locked.save(update_fields=["status", "current_step_order", "updated_at"])

            restart_mode_str = f"с этапа №{active_step.step_order} («{active_step.step_name}»)" if active_step else "с Шага 1"
            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=active_step,
                user=user,
                action=DocFlowApprovalLog.Action.RESTARTED,
                comment=f"Маршрут возобновлен после доработки {restart_mode_str}.",
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            if active_step:
                DocFlowNotificationService.notify_step_assigned(active_step)

            logger.info("Документ %s: маршрут успешно возобновлен пользователем %s", doc_locked.reg_number, user)
            return doc_locked

    @classmethod
    def process_rejection(
        cls,
        document: DocFlowDocument,
        step: Optional[DocFlowRouteStep],
        user: DataBaseUser,
        comment: str,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Отклоняет документ и окончательно завершает процесс согласования.

        Args:
            document (DocFlowDocument): Отклоняемый документ СЭД.
            step (Optional[DocFlowRouteStep]): Текущий шаг.
            user (DataBaseUser): Согласующий сотрудник.
            comment (str): Причина отклонения.
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowDocument: Документ со статусом REJECTED.
        """
        with transaction.atomic():
            doc_locked = DocFlowDocument.objects.select_for_update().get(id=document.id)

            if step:
                step_locked = DocFlowRouteStep.objects.select_for_update().get(id=step.id)
                step_locked.status = DocFlowRouteStep.Status.REJECTED
                step_locked.completed_at = timezone.now()
                step_locked.save()

            doc_locked.status = DocFlowDocument.Status.REJECTED
            doc_locked.save(update_fields=["status", "updated_at"])

            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=step,
                user=user,
                action=DocFlowApprovalLog.Action.REJECTED,
                comment=comment,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            DocFlowNotificationService.notify_rejection(doc_locked, user, comment)

            logger.info("Документ %s: отклонен сотрудником %s", doc_locked.reg_number, user)
            return doc_locked

    @classmethod
    def delegate_step(
        cls,
        step: DocFlowRouteStep,
        user: DataBaseUser,
        target_user: DataBaseUser,
        comment: str = "",
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowRouteStep:
        """Делегирует рассмотрение этапа согласования другому сотруднику.

        Args:
            step (DocFlowRouteStep): Шаг маршрута.
            user (DataBaseUser): Текущий исполнитель / руководитель.
            target_user (DataBaseUser): Назначаемый согласующий сотрудник.
            comment (str): Примечание к делегированию. Defaults to "".
            ip_address (Optional[str]): IP-адрес клиента. Defaults to None.
            user_agent (str): User-Agent браузера. Defaults to "".

        Returns:
            DocFlowRouteStep: Обновленный шаг маршрута.
        """
        with transaction.atomic():
            step_locked = DocFlowRouteStep.objects.select_for_update().get(id=step.id)
            old_assignee = step_locked.assigned_user

            step_locked.assigned_user = target_user
            step_locked.save(update_fields=["assigned_user"])

            DocFlowApprovalLog.objects.create(
                document=step_locked.document,
                route_step=step_locked,
                user=user,
                action=DocFlowApprovalLog.Action.DELEGATED,
                comment=f"Шаг переназначен с {old_assignee or 'группы'} на {target_user}. {comment}".strip(),
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            DocFlowNotificationService.notify_step_assigned(step_locked)

            logger.info(
                "Документ %s (Шаг №%d): делегирован сотруднику %s",
                step_locked.document.reg_number,
                step_locked.step_order,
                target_user,
            )
            return step_locked
