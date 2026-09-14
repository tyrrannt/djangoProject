"""Сервисный слой управления организационной структурой и иерархией подразделений.

Обеспечивает версионирование оргструктуры, расчет прав доступа по иерархии
(сверху вниз), исторический учет руководящего состава на любую дату и передачу
данных для интерактивного визуального конструктора блок-схем.
"""

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from customers_app.models import (
    DataBaseUser,
    Division,
    Job,
    OrgNodeLeadershipHistory,
    OrgStructure,
    OrgStructureNode,
)


class OrgStructureService:
    """Сервис для работы с организационной структурой и иерархической моделью доступа."""

    @staticmethod
    def get_active_org_structure(target_date: Optional[datetime.date] = None) -> Optional[OrgStructure]:
        """Возвращает актуальную схему оргструктуры на указанную дату или текущую активную.

        Args:
            target_date (Optional[datetime.date]): Дата, на которую запрашивается структура.
                Если не указана, используется текущая дата (timezone.now().date()).

        Returns:
            Optional[OrgStructure]: Экземпляр схемы оргструктуры или None.
        """
        if target_date is None:
            target_date = timezone.now().date()

        # Ищем структуру, действующую на указанную дату
        structure = (
            OrgStructure.objects.filter(
                start_date__lte=target_date,
                is_active=True,
            )
            .filter(Q(end_date__gte=target_date) | Q(end_date__isnull=True))
            .order_by("-start_date", "-created_at")
            .first()
        )

        if not structure:
            # Fallback: берем последнюю активную структуру
            structure = OrgStructure.objects.filter(is_active=True).order_by("-start_date").first()

        if not structure:
            # Fallback 2: берем любую последнюю созданную структуру
            structure = OrgStructure.objects.order_by("-created_at").first()

        return structure

    @staticmethod
    def get_user_org_node(
        user: DataBaseUser,
        structure: Optional[OrgStructure] = None,
        target_date: Optional[datetime.date] = None,
    ) -> Optional[OrgStructureNode]:
        """Определяет узел оргструктуры, к которому относится сотрудник.

        Сначала проверяет прямое назначение руководителем узла (OrgNodeLeadershipHistory),
        затем соответствие по подразделению (UserWorkProfile.divisions).

        Args:
            user (DataBaseUser): Объект пользователя.
            structure (Optional[OrgStructure]): Схема оргструктуры (если None, берется активная).
            target_date (Optional[datetime.date]): Дата проверки.

        Returns:
            Optional[OrgStructureNode]: Узел оргструктуры или None.
        """
        if not user or not user.is_authenticated:
            return None

        if structure is None:
            structure = OrgStructureService.get_active_org_structure(target_date)

        if not structure:
            return None

        if target_date is None:
            target_date = timezone.now().date()

        # 1. Проверяем, является ли пользователь назначенным руководителем узла
        leadership_record = (
            OrgNodeLeadershipHistory.objects.filter(
                node__structure=structure,
                node__is_active=True,
                employee=user,
                date_from__lte=target_date,
            )
            .filter(Q(date_to__gte=target_date) | Q(date_to__isnull=True))
            .select_related("node")
            .first()
        )
        if leadership_record:
            return leadership_record.node

        # 2. Проверяем привязку по рабочему профилю пользователя к Division
        if hasattr(user, "user_work_profile") and user.user_work_profile and user.user_work_profile.divisions:
            user_div = user.user_work_profile.divisions
            node = structure.nodes.filter(division=user_div, is_active=True).first()
            if node:
                return node

        return None

    @staticmethod
    def get_user_accessible_division_ids(
        user: DataBaseUser,
        target_date: Optional[datetime.date] = None,
    ) -> Set[int]:
        """Рассчитывает множество ID подразделений (Division.id), доступных пользователю по иерархии.

        Если пользователь относится к вышестоящему звену, ему доступны собственное
        подразделение и ВСЕ дочерние подразделения поддерева.
        Суперпользователи и сотрудники высшего руководства получают полный доступ.

        Args:
            user (DataBaseUser): Текущий пользователь.
            target_date (Optional[datetime.date]): Дата для расчета исторического доступа.

        Returns:
            Set[int]: Множество ID доступных подразделений из Division.
        """
        if not user or not user.is_authenticated:
            return set()

        # Суперпользователи имеют глобальный доступ ко всем подразделениям
        if user.is_superuser or user.is_staff:
            return set(Division.objects.values_list("id", flat=True))

        structure = OrgStructureService.get_active_org_structure(target_date)
        if not structure:
            # Если оргструктура не настроена, возвращаем подразделение пользователя
            if hasattr(user, "user_work_profile") and user.user_work_profile and user.user_work_profile.divisions_id:
                return {user.user_work_profile.divisions_id}
            return set()

        user_node = OrgStructureService.get_user_org_node(user, structure=structure, target_date=target_date)
        if not user_node:
            # Пользователь не привязан к узлу: возвращаем прямое подразделение из профиля
            if hasattr(user, "user_work_profile") and user.user_work_profile and user.user_work_profile.divisions_id:
                return {user.user_work_profile.divisions_id}
            return set()

        # Если узел корневой (Генеральный директор) -> полный доступ
        if user_node.level == 0 or user_node.parent is None:
            return set(Division.objects.values_list("id", flat=True))

        # Рекурсивно собираем все подразделения текущего узла и всех подчиненных
        accessible_ids = user_node.get_all_descendant_division_ids()

        # Всегда включаем собственное подразделение из рабочего профиля (если есть)
        if hasattr(user, "user_work_profile") and user.user_work_profile and user.user_work_profile.divisions_id:
            accessible_ids.add(user.user_work_profile.divisions_id)

        return accessible_ids

    @staticmethod
    def get_division_descendant_ids(
        division_id: int,
        target_date: Optional[datetime.date] = None,
    ) -> Set[int]:
        """Возвращает множество ID подразделений, подчиненных указанному division_id.

        Args:
            division_id (int): ID исходного подразделения.
            target_date (Optional[datetime.date]): Дата актуальности схемы.

        Returns:
            Set[int]: Множество ID дочерних подразделений (включая само division_id).
        """
        structure = OrgStructureService.get_active_org_structure(target_date)
        if not structure:
            return {division_id}

        node = structure.nodes.filter(division_id=division_id, is_active=True).first()
        if not node:
            return {division_id}

        return node.get_all_descendant_division_ids()

    @staticmethod
    def get_org_chart_data(
        structure_id: Optional[int] = None,
        target_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """Формирует полную структуру данных для интерактивного конструктора блок-схемы.

        Включает информацию о схеме, список всех узлов с координатами и связями,
        действующих руководителях и доступных справочниках подразделений и должностей.

        Args:
            structure_id (Optional[int]): ID схемы оргструктуры. Если None, берется активная.
            target_date (Optional[datetime.date]): Дата среза для определения руководителей.

        Returns:
            Dict[str, Any]: Словарь с ключами 'structure', 'nodes', 'divisions', 'jobs', 'users'.
        """
        if structure_id:
            structure = OrgStructure.objects.filter(id=structure_id).first()
        else:
            structure = OrgStructureService.get_active_org_structure(target_date)

        if not structure:
            return {
                "structure": None,
                "nodes": [],
                "divisions": list(Division.objects.values("id", "name", "code")),
                "jobs": list(Job.objects.values("id", "name", "code")),
                "users": [],
            }

        if target_date is None:
            target_date = timezone.now().date()

        nodes_qs = structure.nodes.filter(is_active=True).select_related(
            "division", "head_job", "parent"
        ).prefetch_related(
            "leadership_history__employee", "leadership_history__job"
        )

        nodes_data = []
        for node in nodes_qs:
            leader_rec = node.get_leader_on_date(target_date)
            leader_info = None
            if leader_rec:
                leader_info = {
                    "id": leader_rec.id,
                    "employee_id": leader_rec.employee_id,
                    "employee_name": leader_rec.employee.title or leader_rec.employee.get_full_name(),
                    "job_id": leader_rec.job_id or node.head_job_id,
                    "job_name": leader_rec.job.name if leader_rec.job else (node.head_job.name if node.head_job else ""),
                    "date_from": leader_rec.date_from.strftime("%d.%m.%Y") if leader_rec.date_from else "",
                    "date_to": leader_rec.date_to.strftime("%d.%m.%Y") if leader_rec.date_to else "",
                    "is_current": leader_rec.is_current,
                    "order_number": leader_rec.order_number or "",
                    "comment": leader_rec.comment or "",
                }

            nodes_data.append({
                "id": node.id,
                "title": node.get_display_name(),
                "custom_name": node.custom_name,
                "division_id": node.division_id,
                "division_name": node.division.name if node.division else "",
                "parent_id": node.parent_id,
                "head_job_id": node.head_job_id,
                "head_job_name": node.head_job.name if node.head_job else "",
                "node_type": node.node_type,
                "level": node.level,
                "order": node.order,
                "pos_x": node.pos_x,
                "pos_y": node.pos_y,
                "color_scheme": node.color_scheme,
                "leader": leader_info,
            })

        all_divisions = list(Division.objects.values("id", "name", "code").order_by("name"))
        all_jobs = list(Job.objects.values("id", "name", "code").order_by("name"))
        all_users = []
        for u in (
            DataBaseUser.objects.filter(is_active=True)
            .select_related("user_work_profile__job", "user_work_profile__divisions")
            .order_by("last_name", "first_name")
        ):
            work_prof = getattr(u, "user_work_profile", None)
            job_id = work_prof.job_id if work_prof and work_prof.job_id else None
            job_name = work_prof.job.name if work_prof and work_prof.job else ""
            division_id = work_prof.divisions_id if work_prof and work_prof.divisions_id else None
            division_name = work_prof.divisions.name if work_prof and work_prof.divisions else ""

            all_users.append({
                "id": u.id,
                "username": u.username,
                "last_name": u.last_name or "",
                "first_name": u.first_name or "",
                "title": u.title or u.get_full_name() or u.username,
                "job_id": job_id,
                "job_name": job_name,
                "division_id": division_id,
                "division_name": division_name,
            })

        all_structures = list(
            OrgStructure.objects.values(
                "id", "title", "version_code", "start_date", "is_active", "approved_by"
            ).order_by("-start_date")
        )

        return {
            "structure": {
                "id": structure.id,
                "title": structure.title,
                "version_code": structure.version_code,
                "start_date": structure.start_date.strftime("%d.%m.%Y") if structure.start_date else "",
                "end_date": structure.end_date.strftime("%d.%m.%Y") if structure.end_date else "",
                "is_active": structure.is_active,
                "approved_by": structure.approved_by,
                "approval_date": structure.approval_date.strftime("%d.%m.%Y") if structure.approval_date else "",
                "description": structure.description,
                "raw_layout_json": structure.raw_layout_json,
            },
            "all_structures": all_structures,
            "nodes": nodes_data,
            "divisions": all_divisions,
            "jobs": all_jobs,
            "users": all_users,
        }

    @staticmethod
    @transaction.atomic
    def save_org_chart_layout(
        structure_id: int,
        nodes_payload: List[Dict[str, Any]],
        layout_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Пакетно сохраняет координаты, иерархические связи и параметры узлов схемы.

        Args:
            structure_id (int): ID схемы оргструктуры.
            nodes_payload (List[Dict[str, Any]]): Список узлов со свойствами
                (id, pos_x, pos_y, parent_id, level, order, color_scheme, etc.).
            layout_meta (Optional[Dict[str, Any]]): Метаданные холста (zoom, pan_x, pan_y).

        Returns:
            Dict[str, Any]: Результат операции {'status': 'success', 'updated_count': int}.
        """
        structure = OrgStructure.objects.get(id=structure_id)

        if layout_meta:
            structure.raw_layout_json = layout_meta
            structure.save(update_fields=["raw_layout_json", "updated_at"])

        updated_count = 0
        for item in nodes_payload:
            node_id = item.get("id")
            if not node_id:
                continue

            node = OrgStructureNode.objects.filter(id=node_id, structure=structure).first()
            if not node:
                continue

            if "pos_x" in item:
                node.pos_x = int(item["pos_x"])
            if "pos_y" in item:
                node.pos_y = int(item["pos_y"])
            if "parent_id" in item:
                parent_id = item["parent_id"]
                node.parent_id = parent_id if parent_id and parent_id != node.id else None
            if "level" in item:
                node.level = int(item["level"])
            if "order" in item:
                node.order = int(item["order"])
            if "color_scheme" in item:
                node.color_scheme = str(item["color_scheme"])
            if "custom_name" in item:
                node.custom_name = str(item["custom_name"])
            if "division_id" in item:
                node.division_id = item["division_id"] or None
            if "head_job_id" in item:
                node.head_job_id = item["head_job_id"] or None
            if "node_type" in item:
                node.node_type = str(item["node_type"])

            node.save()
            updated_count += 1

        return {"status": "success", "updated_count": updated_count}

    @staticmethod
    def create_or_update_node(
        structure_id: int,
        node_data: Dict[str, Any],
    ) -> OrgStructureNode:
        """Создает новый узел или обновляет существующий.

        Args:
            structure_id (int): ID схемы оргструктуры.
            node_data (Dict[str, Any]): Данные узла (id, custom_name, division_id,
                head_job_id, parent_id, node_type, pos_x, pos_y, color_scheme).

        Returns:
            OrgStructureNode: Сохраненный узел оргструктуры.
        """
        structure = OrgStructure.objects.get(id=structure_id)
        node_id = node_data.get("id")

        if node_id:
            node = OrgStructureNode.objects.get(id=node_id, structure=structure)
        else:
            node = OrgStructureNode(structure=structure)

        if "custom_name" in node_data:
            node.custom_name = str(node_data["custom_name"])
        if "division_id" in node_data:
            node.division_id = node_data["division_id"] or None
        if "head_job_id" in node_data:
            node.head_job_id = node_data["head_job_id"] or None
        if "parent_id" in node_data:
            pid = node_data["parent_id"]
            node.parent_id = pid if pid and pid != node.id else None
        if "node_type" in node_data:
            node.node_type = node_data["node_type"]
        if "level" in node_data:
            node.level = int(node_data["level"])
        if "pos_x" in node_data:
            node.pos_x = int(node_data["pos_x"])
        if "pos_y" in node_data:
            node.pos_y = int(node_data["pos_y"])
        if "color_scheme" in node_data:
            node.color_scheme = str(node_data["color_scheme"])

        node.save()
        return node

    @staticmethod
    def delete_org_node(node_id: int) -> bool:
        """Удаляет узел оргструктуры и переназначает дочерние элементы родительскому узлу.

        Args:
            node_id (int): ID удаляемого узла.

        Returns:
            bool: True при успешном удалении.
        """
        node = OrgStructureNode.objects.filter(id=node_id).first()
        if not node:
            return False

        parent = node.parent
        # Переназначаем дочерние узлы родителю
        node.children.update(parent=parent)
        node.delete()
        return True

    @staticmethod
    @transaction.atomic
    def assign_node_leader(
        node_id: int,
        employee_id: int,
        job_id: Optional[int] = None,
        date_from: Optional[datetime.date] = None,
        date_to: Optional[datetime.date] = None,
        order_number: str = "",
        comment: str = "",
    ) -> OrgNodeLeadershipHistory:
        """Назначает сотрудника руководителем узла с фиксацией в историческом реестре.

        Если дата окончания не указана (date_to is None), предыдущие действующие
        руководители этого узла завершают свои полномочия датой date_from - 1 день.

        Args:
            node_id (int): ID узла оргструктуры.
            employee_id (int): ID сотрудника (DataBaseUser.id).
            job_id (Optional[int]): ID должности руководителя (Job.id).
            date_from (Optional[datetime.date]): Дата начала руководства (по умолчанию сегодня).
            date_to (Optional[datetime.date]): Дата окончания руководства (null = бессрочно).
            order_number (str): Реквизиты приказа о назначении.
            comment (str): Служебный комментарий (повышение, и.о. и т.д.).

        Returns:
            OrgNodeLeadershipHistory: Созданная запись исторического руководства.
        """
        node = OrgStructureNode.objects.get(id=node_id)
        employee = DataBaseUser.objects.get(id=employee_id)
        job = Job.objects.filter(id=job_id).first() if job_id else node.head_job

        if date_from is None:
            date_from = timezone.now().date()

        # Если новое назначение является действующим (date_to is None или в будущем),
        # завершаем текущие действующие назначения
        is_current = date_to is None or date_to >= timezone.now().date()
        if is_current:
            previous_current = OrgNodeLeadershipHistory.objects.filter(node=node, is_current=True)
            for prev in previous_current:
                prev.is_current = False
                if not prev.date_to or prev.date_to > date_from:
                    prev.date_to = date_from - datetime.timedelta(days=1)
                prev.save()

        history_record = OrgNodeLeadershipHistory.objects.create(
            node=node,
            job=job,
            employee=employee,
            date_from=date_from,
            date_to=date_to,
            is_current=is_current,
            order_number=order_number,
            comment=comment,
        )

        return history_record

    @staticmethod
    def get_node_leadership_history(node_id: int) -> List[Dict[str, Any]]:
        """Возвращает полный хронологический список истории руководителей узла.

        Args:
            node_id (int): ID узла оргструктуры.

        Returns:
            List[Dict[str, Any]]: Список словарей с данными о руководителях и периодах.
        """
        records = (
            OrgNodeLeadershipHistory.objects.filter(node_id=node_id)
            .select_related("employee", "job")
            .order_by("-date_from", "-id")
        )

        history = []
        for r in records:
            history.append({
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_name": r.employee.title or r.employee.get_full_name(),
                "job_name": r.job.name if r.job else "",
                "date_from": r.date_from.strftime("%d.%m.%Y") if r.date_from else "",
                "date_to": r.date_to.strftime("%d.%m.%Y") if r.date_to else "н.в.",
                "is_current": r.is_current,
                "order_number": r.order_number,
                "comment": r.comment,
            })
        return history
