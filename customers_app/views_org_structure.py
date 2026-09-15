"""Контроллеры представлений и API для интерактивного конструктора организационной структуры компании."""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from customers_app.models import (
    DataBaseUser,
    Division,
    Job,
    OrgNodeLeadershipHistory,
    OrgStructure,
    OrgStructureNode,
)
from customers_app.services.org_structure_service import OrgStructureService

logger = logging.getLogger(__name__)


def user_can_edit_org_structure(user: Any) -> bool:
    """Проверяет права пользователя на редактирование организационной структуры компании.

    Полный доступ имеют суперпользователи (администраторы), а доступ к редактированию —
    пользователи с явно выданным разрешением 'customers_app.change_orgstructure'.

    Args:
        user (Any): Экземпляр текущего пользователя.

    Returns:
        bool: True, если у пользователя есть права на редактирование, иначе False.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or user.has_perm("customers_app.change_orgstructure"))


class OrgStructureBuilderView(LoginRequiredMixin, TemplateView):
    """Интерактивный визуальный веб-конструктор организационной структуры компании.

    Предоставляет интерфейс холста (Flowchart Builder) с drag-and-drop узлов,
    соединением стрелками подчиненности, палитрой подразделений из справочника Division,
    назначением должностей и руководителей с историчностью и фильтрацией по дате.
    """

    template_name = "customers_app/org_structure_builder.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует контекст для конструктора оргструктуры.

        Args:
            **kwargs (Any): Дополнительные именованные аргументы контекста.

        Returns:
            Dict[str, Any]: Контекст с текущей структурой, списком версий и правами редактирования.
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user
        structure_id = self.request.GET.get("structure_id")
        date_str = self.request.GET.get("date")

        target_date = None
        if date_str:
            try:
                target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                target_date = None

        if structure_id:
            try:
                structure = OrgStructure.objects.get(id=structure_id)
            except OrgStructure.DoesNotExist:
                structure = OrgStructureService.get_active_org_structure(target_date)
        else:
            structure = OrgStructureService.get_active_org_structure(target_date)

        can_edit = user_can_edit_org_structure(user)

        context["title"] = "Организационная структура ООО «Авиакомпания «БАРКОЛ»"
        context["breadcrumbs"] = [
            {"name": "СЭД", "url": reverse("logistics_app:docflow_list")},
            {"name": "Оргструктура", "url": None},
        ]
        context["structure"] = structure
        context["all_structures"] = OrgStructure.objects.all().order_by("-start_date")
        context["can_edit"] = can_edit
        context["target_date"] = target_date.strftime("%Y-%m-%d") if target_date else timezone.now().strftime("%Y-%m-%d")
        context["divisions"] = Division.objects.all().order_by("name")
        context["jobs"] = Job.objects.all().order_by("name")

        return context


class OrgStructureDataApiView(LoginRequiredMixin, View):
    """AJAX API для получения данных оргструктуры в формате JSON."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Возвращает JSON с узлами, связями, руководителями и справочниками.

        Args:
            request (HttpRequest): HTTP-запрос с возможными GET-параметрами 'structure_id' и 'date'.

        Returns:
            JsonResponse: Структурированные данные оргструктуры.
        """
        structure_id = request.GET.get("structure_id")
        date_str = request.GET.get("date")

        target_date = None
        if date_str:
            try:
                target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                target_date = None

        sid = int(structure_id) if structure_id and structure_id.isdigit() else None
        data = OrgStructureService.get_org_chart_data(structure_id=sid, target_date=target_date)
        return JsonResponse(data)


class OrgStructureSaveLayoutApiView(LoginRequiredMixin, View):
    """AJAX API для пакетного сохранения координат и связей узлов на холсте."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Принимает JSON с измененными координатами и родительскими связями.

        Args:
            request (HttpRequest): HTTP POST запрос с телом JSON:
                - structure_id (int)
                - nodes (List[Dict])
                - layout_meta (Dict)

        Returns:
            JsonResponse: Статус сохранения.
        """
        if not user_can_edit_org_structure(request.user):
            return JsonResponse({"status": "error", "message": "Недостаточно прав для редактирования структуры."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            structure_id = int(payload.get("structure_id"))
            nodes_payload = payload.get("nodes", [])
            layout_meta = payload.get("layout_meta")

            result = OrgStructureService.save_org_chart_layout(
                structure_id=structure_id,
                nodes_payload=nodes_payload,
                layout_meta=layout_meta,
            )
            return JsonResponse(result)
        except Exception as exc:
            logger.exception("Ошибка при сохранении разметки оргструктуры: %s", exc)
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)


class OrgStructureNodeSaveApiView(LoginRequiredMixin, View):
    """AJAX API для создания или редактирования отдельного узла оргструктуры."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Создает новый узел или обновляет свойства существующего.

        Args:
            request (HttpRequest): HTTP POST запрос с JSON-телом данных узла.

        Returns:
            JsonResponse: JSON-объект сохраненного узла.
        """
        if not user_can_edit_org_structure(request.user):
            return JsonResponse({"status": "error", "message": "Недостаточно прав для редактирования узлов."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            structure_id = int(payload.get("structure_id"))
            node_data = payload.get("node_data", {})

            node = OrgStructureService.create_or_update_node(
                structure_id=structure_id,
                node_data=node_data,
            )

            leader_rec = node.get_current_leader()
            leader_info = None
            if leader_rec:
                leader_info = {
                    "id": leader_rec.id,
                    "employee_id": leader_rec.employee_id,
                    "employee_name": leader_rec.employee.title or leader_rec.employee.get_full_name(),
                    "job_name": leader_rec.job.name if leader_rec.job else "",
                    "date_from": leader_rec.date_from.strftime("%d.%m.%Y") if leader_rec.date_from else "",
                }

            return JsonResponse({
                "status": "success",
                "node": {
                    "id": node.id,
                    "title": node.get_display_name(),
                    "custom_name": node.custom_name,
                    "division_id": node.division_id,
                    "division_name": node.division.name if node.division else "",
                    "head_job_id": node.head_job_id,
                    "head_job_name": node.head_job.name if node.head_job else "",
                    "parent_id": node.parent_id,
                    "node_type": node.node_type,
                    "level": node.level,
                    "pos_x": node.pos_x,
                    "pos_y": node.pos_y,
                    "color_scheme": node.color_scheme,
                    "leader": leader_info,
                },
            })
        except Exception as exc:
            logger.exception("Ошибка при сохранении узла оргструктуры: %s", exc)
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)


class OrgStructureNodeDeleteApiView(LoginRequiredMixin, View):
    """AJAX API для удаления узла оргструктуры."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Удаляет узел с безопасным переподчинением дочерних элементов родителю.

        Args:
            request (HttpRequest): HTTP POST запрос с параметром node_id.

        Returns:
            JsonResponse: Статус удаления.
        """
        if not user_can_edit_org_structure(request.user):
            return JsonResponse({"status": "error", "message": "Недостаточно прав для удаления узлов."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            node_id = int(payload.get("node_id"))
            success = OrgStructureService.delete_org_node(node_id)
            return JsonResponse({"status": "success" if success else "error"})
        except Exception as exc:
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)


class OrgStructureAssignLeaderApiView(LoginRequiredMixin, View):
    """AJAX API для назначения руководителя на узел с исторической фиксацией."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Назначает сотрудника руководителем узла с записью в OrgNodeLeadershipHistory.

        Args:
            request (HttpRequest): HTTP POST запрос с параметрами:
                - node_id (int)
                - employee_id (int)
                - job_id (Optional[int])
                - date_from (Optional[str YYYY-MM-DD])
                - date_to (Optional[str YYYY-MM-DD])
                - order_number (str)
                - comment (str)

        Returns:
            JsonResponse: Данные созданной записи назначения.
        """
        if not user_can_edit_org_structure(request.user):
            return JsonResponse({"status": "error", "message": "Недостаточно прав для назначения руководства."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            node_id = int(payload.get("node_id"))
            employee_id = int(payload.get("employee_id"))
            job_id = int(payload.get("job_id")) if payload.get("job_id") else None

            date_from_str = payload.get("date_from")
            date_to_str = payload.get("date_to")

            date_from = datetime.datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else timezone.now().date()
            date_to = datetime.datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else None

            order_number = payload.get("order_number", "")
            comment = payload.get("comment", "")

            history_rec = OrgStructureService.assign_node_leader(
                node_id=node_id,
                employee_id=employee_id,
                job_id=job_id,
                date_from=date_from,
                date_to=date_to,
                order_number=order_number,
                comment=comment,
            )

            return JsonResponse({
                "status": "success",
                "leader": {
                    "id": history_rec.id,
                    "employee_id": history_rec.employee_id,
                    "employee_name": history_rec.employee.title or history_rec.employee.get_full_name(),
                    "job_name": history_rec.job.name if history_rec.job else "",
                    "date_from": history_rec.date_from.strftime("%d.%m.%Y"),
                    "date_to": history_rec.date_to.strftime("%d.%m.%Y") if history_rec.date_to else "н.в.",
                    "is_current": history_rec.is_current,
                    "order_number": history_rec.order_number,
                    "comment": history_rec.comment,
                },
            })
        except Exception as exc:
            logger.exception("Ошибка при назначении руководителя узла: %s", exc)
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)


class OrgStructureNodeHistoryApiView(LoginRequiredMixin, View):
    """AJAX API для получения хронологической истории руководителей узла."""

    def get(self, request: HttpRequest, node_id: int, *args: Any, **kwargs: Any) -> JsonResponse:
        """Возвращает список всех исторических назначений руководителей для указанного узла.

        Args:
            request (HttpRequest): HTTP GET запрос.
            node_id (int): Идентификатор узла оргструктуры.

        Returns:
            JsonResponse: Список назначений в хронологическом порядке.
        """
        history = OrgStructureService.get_node_leadership_history(node_id)
        return JsonResponse({"status": "success", "history": history})


class OrgStructureCreateVersionApiView(LoginRequiredMixin, View):
    """AJAX API для создания новой редакции оргструктуры с новой датой ввода в действие."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Создает новую версию структуры (с опциональным копированием узлов из предыдущей).

        Args:
            request (HttpRequest): HTTP POST запрос с параметрами:
                - title (str)
                - version_code (str)
                - start_date (str YYYY-MM-DD)
                - approved_by (str)
                - copy_from_id (Optional[int])

        Returns:
            JsonResponse: Данные созданной схемы структуры.
        """
        if not user_can_edit_org_structure(request.user):
            return JsonResponse({"status": "error", "message": "Недостаточно прав для создания версий структуры."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            title = payload.get("title", "Общая структурная схема ООО Авиакомпания «БАРКОЛ»")
            version_code = payload.get("version_code", "")
            start_date_str = payload.get("start_date")
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else timezone.now().date()
            approved_by = payload.get("approved_by", "Генеральный директор В.С. Бархотов")
            copy_from_id = payload.get("copy_from_id")

            # Создаем новую структуру
            new_structure = OrgStructure.objects.create(
                title=title,
                version_code=version_code,
                start_date=start_date,
                is_active=True,
                approved_by=approved_by,
                approval_date=start_date,
                description=payload.get("description", ""),
            )

            # Если указано копирование узлов
            if copy_from_id:
                old_structure = OrgStructure.objects.get(id=copy_from_id)
                new_structure.raw_layout_json = old_structure.raw_layout_json
                new_structure.save(update_fields=["raw_layout_json"])

                # Закрываем предыдущую структуру датой перед стартом новой
                if old_structure.is_active:
                    old_structure.end_date = start_date - datetime.timedelta(days=1)
                    old_structure.save(update_fields=["end_date"])

                # Маппинг старых ID узлов на новые
                old_to_new_map: Dict[int, OrgStructureNode] = {}
                old_nodes = old_structure.nodes.filter(is_active=True).order_by("level", "order", "id")

                # Первый проход: создаем узлы без parent
                for old_n in old_nodes:
                    new_n = OrgStructureNode.objects.create(
                        structure=new_structure,
                        division=old_n.division,
                        custom_name=old_n.custom_name,
                        head_job=old_n.head_job,
                        node_type=old_n.node_type,
                        level=old_n.level,
                        order=old_n.order,
                        pos_x=old_n.pos_x,
                        pos_y=old_n.pos_y,
                        color_scheme=old_n.color_scheme,
                        is_active=old_n.is_active,
                    )
                    old_to_new_map[old_n.id] = new_n

                    # Копируем действующего руководителя
                    leader = old_n.get_current_leader()
                    if leader:
                        OrgNodeLeadershipHistory.objects.create(
                            node=new_n,
                            job=leader.job,
                            employee=leader.employee,
                            date_from=start_date,
                            is_current=True,
                            order_number=leader.order_number,
                            comment="Перенос из редакции " + str(old_structure.version_code),
                        )

                # Второй проход: проставляем parent
                for old_n in old_nodes:
                    if old_n.parent_id and old_n.parent_id in old_to_new_map:
                        new_n = old_to_new_map[old_n.id]
                        new_n.parent = old_to_new_map[old_n.parent_id]
                        new_n.save(update_fields=["parent"])

            return JsonResponse({
                "status": "success",
                "structure": {
                    "id": new_structure.id,
                    "title": new_structure.title,
                    "version_code": new_structure.version_code,
                    "start_date": new_structure.start_date.strftime("%d.%m.%Y"),
                },
            })
        except Exception as exc:
            logger.exception("Ошибка при создании новой версии оргструктуры: %s", exc)
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)
