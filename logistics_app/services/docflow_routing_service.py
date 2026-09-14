"""Сервисный слой маршрутизации и визирования документов СЭД (logistics_app)."""

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser, Division
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
    - Построение цепочки этапов из системного шаблона либо динамически «на лету»;
    - Добавление и удаление ad-hoc этапов согласующих и исполнителей;
    - Запуск и активацию первого этапа согласования;
    - Обработку визирования с динамическим назначением исполнителя руководителем;
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
    def create_dynamic_initial_route(
        cls,
        document: DocFlowDocument,
        approver: Optional[DataBaseUser] = None,
        division: Optional[Division] = None,
        sla_hours: int = 24,
    ) -> List[DocFlowRouteStep]:
        """Создает первичный динамический этап согласования без жесткого шаблона.

        Если согласующий не указан явно, пытается автоматически определить руководителя
        подразделения автора (HEAD_OF_DEPARTMENT) либо назначает ответственного сотрудника.

        Args:
            document (DocFlowDocument): Документ СЭД.
            approver (Optional[DataBaseUser]): Конкретно назначенный согласующий.
            division (Optional[Division]): Подразделение визирования.
            sla_hours (int): Нормативный срок на рассмотрение в часах. Defaults to 24.

        Returns:
            List[DocFlowRouteStep]: Список созданных шагов маршрута.
        """
        with transaction.atomic():
            document.route_steps.all().delete()
            target_user = approver
            target_division = division

            if not target_user and not target_division:
                initiator = document.initiator
                user_work_profile = getattr(initiator, "user_work_profile", None) if initiator else None
                div = getattr(user_work_profile, "divisions", None) if user_work_profile else None
                if div:
                    target_division = div
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
                        target_user = head
                else:
                    target_user = document.responsible or document.initiator

            step_name = (
                f"Согласование: {target_user.title or target_user.get_full_name() or target_user.username}"
                if target_user
                else "Согласование руководителем"
            )

            step = DocFlowRouteStep.objects.create(
                document=document,
                step_order=1,
                step_name=step_name,
                step_type=DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
                assigned_user=target_user,
                assigned_division=target_division,
                status=DocFlowRouteStep.Status.PENDING,
                sla_hours=sla_hours or 24,
                can_rollback_to=True,
                allow_reviewer_file_edit=True,
            )
            logger.info("Документ UUID %s: сформирован динамический 1-й шаг маршрута на %s", document.id, target_user or target_division)
            return [step]

    @classmethod
    def add_ad_hoc_step(
        cls,
        document: DocFlowDocument,
        step_name: str,
        step_type: str = DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
        assigned_user: Optional[DataBaseUser] = None,
        assigned_users: Optional[List[DataBaseUser]] = None,
        assigned_division: Optional[Division] = None,
        sla_hours: int = 24,
        allow_reviewer_file_edit: bool = True,
        can_rollback_to: bool = True,
    ) -> DocFlowRouteStep:
        """Добавляет произвольный этап в цепочку маршрута черновика документа.

        Args:
            document (DocFlowDocument): Карточка документа СЭД.
            step_name (str): Наименование этапа.
            step_type (str): Тип выполнения шага. Defaults to SEQUENTIAL.
            assigned_user (Optional[DataBaseUser]): Персонально назначенный сотрудник.
            assigned_users (Optional[List[DataBaseUser]]): Группа для параллельного визирования.
            assigned_division (Optional[Division]): Назначенное подразделение.
            sla_hours (int): Нормативный срок в часах. Defaults to 24.
            allow_reviewer_file_edit (bool): Разрешить прикрепление файлов с правками. Defaults to True.
            can_rollback_to (bool): Разрешить откат на данный шаг. Defaults to True.

        Returns:
            DocFlowRouteStep: Созданный шаг маршрута.
        """
        with transaction.atomic():
            last_order = document.route_steps.order_by("-step_order").values_list("step_order", flat=True).first() or 0
            new_order = last_order + 1
            step = DocFlowRouteStep.objects.create(
                document=document,
                step_order=new_order,
                step_name=step_name.strip() or f"Этап №{new_order}",
                step_type=step_type,
                assigned_user=assigned_user,
                assigned_division=assigned_division,
                status=DocFlowRouteStep.Status.PENDING,
                sla_hours=sla_hours or 24,
                allow_reviewer_file_edit=allow_reviewer_file_edit,
                can_rollback_to=can_rollback_to,
            )
            if assigned_users:
                step.assigned_users.set(assigned_users)
            logger.info("Документ UUID %s: добавлен этап №%d «%s»", document.id, new_order, step.step_name)
            return step

    @classmethod
    def remove_ad_hoc_step(cls, document: DocFlowDocument, step_id: int) -> bool:
        """Удаляет шаг из маршрута черновика документа и перенумеровывает оставшиеся этапы.

        Args:
            document (DocFlowDocument): Карточка документа СЭД.
            step_id (int): Идентификатор удаляемого шага.

        Returns:
            bool: True в случае успешного удаления.

        Raises:
            ValueError: Если документ не в статусе черновика или шаг уже запущен.
        """
        with transaction.atomic():
            step = document.route_steps.filter(id=step_id).first()
            if not step:
                return False
            if document.status not in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK] or step.status != DocFlowRouteStep.Status.PENDING:
                raise ValueError("Удалять можно только ожидающие шаги в черновике или документе на доработке.")
            step.delete()
            remaining_steps = document.route_steps.order_by("step_order")
            for idx, s in enumerate(remaining_steps, start=1):
                if s.step_order != idx:
                    s.step_order = idx
                    s.save(update_fields=["step_order"])
            return True

    @classmethod
    def build_route_from_template(
        cls,
        document: DocFlowDocument,
        template_id: Optional[int] = None,
        fallback_to_dynamic: bool = True,
    ) -> List[DocFlowRouteStep]:
        """Формирует цепочку шагов маршрута согласования документа из шаблона.

        Если template_id не передан, используется шаблон по умолчанию для doc_type документа.
        Если шаблон не найден и fallback_to_dynamic=True, автоматически формируется
        первичный динамический маршрут согласования.

        Args:
            document (DocFlowDocument): Карточка документа СЭД.
            template_id (Optional[int]): Идентификатор конкретного шаблона DocFlowRouteTemplate.
            fallback_to_dynamic (bool): Создавать ли динамический маршрут при отсутствии шаблона. Defaults to True.

        Returns:
            List[DocFlowRouteStep]: Список созданных шагов маршрута.

        Raises:
            ValueError: Если подходящий шаблон маршрута не найден и fallback_to_dynamic=False.
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
            if fallback_to_dynamic:
                return cls.create_dynamic_initial_route(document)
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
        first_approver: Optional[DataBaseUser] = None,
        first_division: Optional[Division] = None,
        first_sla_hours: int = 24,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowDocument:
        """Запускает процесс согласования документа по маршруту.

        Переводит документ в статус ON_APPROVAL, генерирует регистрационный номер
        (при отсутствии), активирует 1-й шаг маршрута и рассылает первичные уведомления.

        Args:
            document (DocFlowDocument): Запускаемый документ СЭД.
            user (DataBaseUser): Инициатор запуска процесса.
            first_approver (Optional[DataBaseUser]): Конкретно выбранный согласующий 1-го этапа.
            first_division (Optional[Division]): Подразделение 1-го этапа.
            first_sla_hours (int): SLA 1-го этапа в часах. Defaults to 24.
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

            # Если шаги маршрута еще не были созданы, создаем
            if not doc_locked.route_steps.exists():
                if first_approver or first_division:
                    cls.create_dynamic_initial_route(
                        doc_locked,
                        approver=first_approver,
                        division=first_division,
                        sla_hours=first_sla_hours,
                    )
                else:
                    cls.build_route_from_template(doc_locked, fallback_to_dynamic=True)

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
                default_sla = doc_locked.doc_type.default_sla_hours if doc_locked.doc_type else 72
                doc_locked.deadline = timezone.now() + timedelta(hours=default_sla)
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
        next_step_action: str = "AUTO",
        next_executor: Optional[DataBaseUser] = None,
        next_executors: Optional[List[DataBaseUser]] = None,
        next_division: Optional[Division] = None,
        next_step_name: str = "",
        next_sla_hours: int = 48,
        next_step_instructions: str = "",
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> Dict[str, Any]:
        """Обрабатывает визирование (согласование) текущего активного этапа согласующим лицом.

        Фиксирует электронную подпись ПЭП, проверяет условия завершения шага,
        переводит документ на следующий шаг (по шаблону или динамически назначенному исполнителю)
        либо присваивает итоговый статус APPROVED.

        Args:
            document (DocFlowDocument): Согласуемый документ.
            step (DocFlowRouteStep): Текущий шаг маршрута.
            user (DataBaseUser): Согласующий сотрудник.
            comment (str): Комментарий / особое мнение. Defaults to "".
            is_minor_edit (bool): Флаг наличия редакционных правок. Defaults to False.
            next_step_action (str): Действие после шага ('AUTO', 'ASSIGN_EXECUTOR', 'FINISH'). Defaults to 'AUTO'.
            next_executor (Optional[DataBaseUser]): Назначенный исполнитель следующего этапа.
            next_executors (Optional[List[DataBaseUser]]): Группа назначенных исполнителей.
            next_division (Optional[Division]): Подразделение-исполнитель.
            next_step_name (str): Название следующего этапа. Defaults to "".
            next_sla_hours (int): Срок на исполнение в часах. Defaults to 48.
            next_step_instructions (str): Текст поручения / резолюции исполнителю. Defaults to "".
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

            # Формируем полный комментарий аудита с учетом поручения исполнителям
            full_comment = comment.strip()
            if next_step_instructions:
                instruction_note = f"[Поручение исполнителю]: {next_step_instructions.strip()}"
                full_comment = f"{full_comment}\n{instruction_note}".strip() if full_comment else instruction_note

            # Записываем действие в журнал аудита ПЭП
            DocFlowApprovalLog.objects.create(
                document=doc_locked,
                route_step=step_locked,
                user=user,
                action=action_type,
                comment=full_comment,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
                pep_signature_hash=sig_hash,
                pep_certificate_id=cert_id,
            )

            if is_step_finished:
                step_locked.status = DocFlowRouteStep.Status.APPROVED
                step_locked.completed_at = timezone.now()
                step_locked.save()

                # Вариант 1: Согласующий явно назначил следующего исполнителя (ASSIGN_EXECUTOR)
                if next_step_action == "ASSIGN_EXECUTOR" or next_executor or next_executors or next_division:
                    next_step = doc_locked.route_steps.filter(
                        step_order__gt=step_locked.step_order,
                        status=DocFlowRouteStep.Status.PENDING,
                    ).order_by("step_order").first()

                    st_type = (
                        DocFlowRouteStepTemplate.StepType.PARALLEL_AND
                        if next_executors and len(next_executors) > 1
                        else DocFlowRouteStepTemplate.StepType.SEQUENTIAL
                    )
                    st_name = next_step_name.strip() or "Исполнение служебной записки"
                    sla = next_sla_hours or 48

                    if next_step:
                        # Обновляем существующий ожидающий шаг
                        next_step.step_name = st_name
                        next_step.step_type = st_type
                        next_step.assigned_user = next_executor
                        next_step.assigned_division = next_division
                        next_step.sla_hours = sla
                        next_step.status = DocFlowRouteStep.Status.IN_PROGRESS
                        next_step.started_at = timezone.now()
                        next_step.due_date = timezone.now() + timedelta(hours=sla)
                        next_step.save()
                        if next_executors:
                            next_step.assigned_users.set(next_executors)
                    else:
                        # Динамически создаем новый шаг исполнения
                        new_order = step_locked.step_order + 1
                        next_step = DocFlowRouteStep.objects.create(
                            document=doc_locked,
                            step_order=new_order,
                            step_name=st_name,
                            step_type=st_type,
                            assigned_user=next_executor,
                            assigned_division=next_division,
                            status=DocFlowRouteStep.Status.IN_PROGRESS,
                            started_at=timezone.now(),
                            due_date=timezone.now() + timedelta(hours=sla),
                            sla_hours=sla,
                            can_rollback_to=True,
                            allow_reviewer_file_edit=True,
                        )
                        if next_executors:
                            next_step.assigned_users.set(next_executors)

                    doc_locked.current_step_order = next_step.step_order
                    doc_locked.save(update_fields=["current_step_order", "updated_at"])

                    DocFlowNotificationService.notify_step_assigned(next_step)
                    logger.info(
                        "Документ %s: руководителем назначен этап №%d «%s» на исполнителя %s",
                        doc_locked.reg_number,
                        next_step.step_order,
                        next_step.step_name,
                        next_executor or next_executors or next_division,
                    )
                    return {"status": "next_step", "document": doc_locked, "next_step": next_step}

                # Вариант 2: Согласующий явно выбрал завершение согласования
                elif next_step_action == "FINISH":
                    doc_locked.status = DocFlowDocument.Status.APPROVED
                    doc_locked.save(update_fields=["status", "updated_at"])
                    DocFlowNotificationService.notify_approval_complete(doc_locked)
                    logger.info("Документ %s: согласование принудительно финализировано руководителем (APPROVED)", doc_locked.reg_number)
                    return {"status": "completed", "document": doc_locked}

                # Вариант 3: Штатный автоматический переход по очереди шагов
                else:
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
