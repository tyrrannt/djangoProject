"""Контроллеры представлений подсистемы электронного документооборота (СЭД) logistics_app."""

import logging
from typing import Any, Dict, List, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from customers_app.models import DataBaseUser, Division
from logistics_app.forms import (
    DocFlowApprovalActionForm,
    DocFlowCommentForm,
    DocFlowDocumentForm,
    DocFlowDocumentTypeForm,
    DocFlowFileUploadForm,
    DocFlowReworkActionForm,
    DocFlowRollbackActionForm,
    DocFlowRouteStepForm,
    DocFlowRouteStepTemplateForm,
    DocFlowRouteStepTemplateFormSet,
    DocFlowRouteTemplateForm,
)
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowComment,
    DocFlowDocument,
    DocFlowDocumentType,
    DocFlowFile,
    DocFlowFileVersion,
    DocFlowRouteStep,
    DocFlowRouteStepTemplate,
    DocFlowRouteTemplate,
)
from logistics_app.services.docflow_routing_service import DocFlowRoutingService
from logistics_app.services.docflow_sheet_service import DocFlowSheetGenerator
from logistics_app.services.docflow_version_service import DocFlowVersionService

logger = logging.getLogger(__name__)


def get_client_ip(request: HttpRequest) -> Optional[str]:
    """Извлекает реальный IP-адрес клиента из HTTP-запроса."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class DocFlowDocumentListView(LoginRequiredMixin, ListView):
    """Реестр документов СЭД с поддержкой вкладок, поиска и HTMX-фильтрации.

    Вкладки:
    - `pending` (Требуют моего согласования): документы с активным шагом, назначенным на пользователя;
    - `my` (Мои документы): документы, где пользователь является автором или ответственным;
    - `all` (Все документы): полный реестр документов портала.
    """

    model = DocFlowDocument
    template_name = "logistics_app/docflow_list.html"
    context_object_name = "documents"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[DocFlowDocument]:
        """Формирует оптимизированную выборку документов с учетом вкладок и фильтров."""
        user = self.request.user
        tab = self.request.GET.get("tab", "pending")

        # Базовый оптимизированный QuerySet с устранением N+1
        qs = (
            DocFlowDocument.objects.select_related(
                "doc_type",
                "initiator",
                "responsible",
                "counteragent",
            )
            .prefetch_related(
                "route_steps",
                "files",
            )
            .order_by("-created_at")
        )

        # Базовое разграничение прав доступа по организационной иерархии подразделений
        if not (user.is_superuser or user.is_staff):
            from customers_app.services.org_structure_service import OrgStructureService
            accessible_div_ids = OrgStructureService.get_user_accessible_division_ids(user)

            hierarchy_filter = (
                Q(initiator__user_work_profile__divisions__in=accessible_div_ids)
                | Q(responsible__user_work_profile__divisions__in=accessible_div_ids)
                | Q(related_waybill__place_division__in=accessible_div_ids)
                | Q(route_steps__assigned_division__in=accessible_div_ids)
            )
            personal_filter = (
                Q(initiator=user)
                | Q(responsible=user)
                | Q(route_steps__assigned_user=user)
                | Q(route_steps__assigned_users=user)
                | Q(approval_logs__user=user)
            )
            qs = qs.filter(hierarchy_filter | personal_filter).distinct()

        # 1. Фильтрация по выбранной вкладке
        if tab == "pending":
            # Активный шаг назначен на текущего пользователя, его подразделение или группу
            user_work_profile = getattr(user, "user_work_profile", None)
            division = getattr(user_work_profile, "divisions", None) if user_work_profile else None

            pending_filter = (
                Q(route_steps__status=DocFlowRouteStep.Status.IN_PROGRESS)
                & (
                    Q(route_steps__assigned_user=user)
                    | Q(route_steps__assigned_users=user)
                    | (Q(route_steps__assigned_division=division) if division else Q())
                )
            )
            qs = qs.filter(pending_filter).distinct()
        elif tab == "my":
            qs = qs.filter(Q(initiator=user) | Q(responsible=user)).distinct()

        # 2. Дополнительные фильтры
        status_filter = self.request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        flow_type = self.request.GET.get("flow_type")
        if flow_type:
            qs = qs.filter(flow_type=flow_type)

        doc_type_id = self.request.GET.get("doc_type")
        if doc_type_id:
            qs = qs.filter(doc_type_id=doc_type_id)

        urgency = self.request.GET.get("urgency")
        if urgency:
            qs = qs.filter(urgency=urgency)

        # 3. Текстовый поиск
        search_query = self.request.GET.get("search", "").strip()
        if search_query:
            qs = qs.filter(
                Q(reg_number__icontains=search_query)
                | Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(counteragent__name__icontains=search_query)
                | Q(initiator__last_name__icontains=search_query)
            )

        return qs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет в контекст счетчики вкладок, списки типов и параметры фильтрации."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        user_work_profile = getattr(user, "user_work_profile", None)
        division = getattr(user_work_profile, "divisions", None) if user_work_profile else None

        # Подсчет бейджей для вкладок
        pending_filter = (
            Q(route_steps__status=DocFlowRouteStep.Status.IN_PROGRESS)
            & (
                Q(route_steps__assigned_user=user)
                | Q(route_steps__assigned_users=user)
                | (Q(route_steps__assigned_division=division) if division else Q())
            )
        )
        context["pending_count"] = DocFlowDocument.objects.filter(pending_filter).distinct().count()
        context["my_count"] = DocFlowDocument.objects.filter(Q(initiator=user) | Q(responsible=user)).distinct().count()

        if not (user.is_superuser or user.is_staff):
            from customers_app.services.org_structure_service import OrgStructureService
            accessible_div_ids = OrgStructureService.get_user_accessible_division_ids(user)
            hierarchy_q = (
                Q(initiator__user_work_profile__divisions__in=accessible_div_ids)
                | Q(responsible__user_work_profile__divisions__in=accessible_div_ids)
                | Q(related_waybill__place_division__in=accessible_div_ids)
                | Q(route_steps__assigned_division__in=accessible_div_ids)
            )
            personal_q = (
                Q(initiator=user)
                | Q(responsible=user)
                | Q(route_steps__assigned_user=user)
                | Q(route_steps__assigned_users=user)
                | Q(approval_logs__user=user)
            )
            context["all_count"] = DocFlowDocument.objects.filter(hierarchy_q | personal_q).distinct().count()
        else:
            context["all_count"] = DocFlowDocument.objects.count()

        context["current_tab"] = self.request.GET.get("tab", "pending")
        context["doc_types"] = DocFlowDocumentType.objects.filter(is_active=True)
        context["status_choices"] = DocFlowDocument.Status.choices
        context["flow_choices"] = DocFlowDocumentType.Category.choices
        context["urgency_choices"] = DocFlowDocument.Urgency.choices

        return context

    def render_to_response(self, context: Dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        """Поддержка HTMX-ответов для частичного обновления таблицы реестра."""
        if self.request.headers.get("HX-Request") and not self.request.headers.get("HX-Boosted"):
            return render(self.request, "logistics_app/partials/docflow_table_partial.html", context)
        return super().render_to_response(context, **response_kwargs)


class DocFlowDocumentCreateView(LoginRequiredMixin, CreateView):
    """Создание нового документа СЭД с первичным файлом и выбором маршрута."""

    model = DocFlowDocument
    form_class = DocFlowDocumentForm
    template_name = "logistics_app/docflow_form.html"

    def get_initial(self) -> Dict[str, Any]:
        """Предзаполняет начальные значения формы."""
        initial = super().get_initial()
        initial["flow_type"] = self.request.GET.get("flow_type", DocFlowDocumentType.Category.INBOUND)
        initial["responsible"] = self.request.user
        return initial

    def form_valid(self, form: DocFlowDocumentForm) -> HttpResponse:
        """Сохраняет документ, прикрепляет исходный файл и строит маршрут согласования."""
        document = form.save(commit=False)
        document.initiator = self.request.user
        if not document.responsible:
            document.responsible = self.request.user

        document.save()

        # Обработка загрузки первого файла
        initial_file = form.cleaned_data.get("initial_file")
        if initial_file:
            file_title = form.cleaned_data.get("initial_file_title") or initial_file.name
            doc_file = DocFlowFile.objects.create(
                document=document,
                title=file_title,
                is_main=True,
                current_version_number="1.0",
            )
            DocFlowVersionService.upload_new_file_version(
                doc_file=doc_file,
                file_obj=initial_file,
                user=self.request.user,
                comment="Исходная редакция документа",
                version_number="1.0",
                ip_address=get_client_ip(self.request),
                user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
            )

        # Формирование цепочки маршрута (динамический выбор или типовой шаблон)
        route_mode = form.cleaned_data.get("route_mode", "TEMPLATE")
        first_approver = form.cleaned_data.get("first_approver")
        first_approver_division = form.cleaned_data.get("first_approver_division")
        first_approver_sla = form.cleaned_data.get("first_approver_sla") or 24
        route_template = form.cleaned_data.get("route_template")

        try:
            if route_mode == "DYNAMIC" or first_approver or first_approver_division:
                DocFlowRoutingService.create_dynamic_initial_route(
                    document=document,
                    approver=first_approver,
                    division=first_approver_division,
                    sla_hours=first_approver_sla,
                )
            else:
                template_id = route_template.id if route_template else None
                DocFlowRoutingService.build_route_from_template(
                    document=document,
                    template_id=template_id,
                    fallback_to_dynamic=True,
                )
        except Exception as exc:
            logger.warning("Не удалось автоматически построить маршрут для документа %s: %s", document.id, exc)

        # Если нажата кнопка «Сохранить и запустить согласование»
        if self.request.POST.get("form_action") == "start":
            try:
                DocFlowRoutingService.start_approval_process(
                    document=document,
                    user=self.request.user,
                    first_approver=first_approver,
                    first_division=first_approver_division,
                    first_sla_hours=first_approver_sla,
                    ip_address=get_client_ip(self.request),
                    user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.success(self.request, f"Документ {document.reg_number} успешно создан и отправлен на согласование!")
            except Exception as exc:
                messages.error(self.request, f"Документ сохранен как черновик, но запуск согласования не удался: {exc}")
        else:
            messages.success(self.request, "Карточка документа успешно сохранена в виде черновика.")

        return redirect("logistics_app:docflow_detail", pk=document.pk)


class DocFlowDocumentUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование карточки документа СЭД в статусе Черновика или На доработке.

    Предоставляет возможность автору или ответственному корректировать тему,
    содержание, реквизиты, заменять файл проекта и изменять согласующих лиц.
    """

    model = DocFlowDocument
    form_class = DocFlowDocumentForm
    template_name = "logistics_app/docflow_form.html"

    def get_object(self, queryset: Optional[QuerySet[DocFlowDocument]] = None) -> DocFlowDocument:
        """Получает документ и проверяет права доступа на редактирование."""
        obj = super().get_object(queryset)
        user = self.request.user
        if not (user == obj.initiator or user == obj.responsible or user.is_superuser):
            raise PermissionDenied("Редактирование карточки документа доступно только автору или ответственному.")
        if obj.status not in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK]:
            raise PermissionDenied("Редактировать можно только документы в статусе «Черновик» или «На доработке».")
        return obj

    def get_initial(self) -> Dict[str, Any]:
        """Предзаполняет начальные значения формы при редактировании."""
        initial = super().get_initial()
        first_step = self.object.route_steps.filter(step_order=1).first()
        if first_step:
            if first_step.assigned_user:
                initial["first_approver"] = first_step.assigned_user
            if first_step.assigned_division:
                initial["first_approver_division"] = first_step.assigned_division
            initial["first_approver_sla"] = first_step.sla_hours
        return initial

    def form_valid(self, form: DocFlowDocumentForm) -> HttpResponse:
        """Сохраняет изменения, прикрепляет новую версию файла и обновляет маршрут при необходимости."""
        document = form.save()

        # Обработка загрузки обновленного файла
        initial_file = form.cleaned_data.get("initial_file")
        if initial_file:
            main_file = document.main_file
            if main_file:
                DocFlowVersionService.upload_new_file_version(
                    doc_file=main_file,
                    file_obj=initial_file,
                    user=self.request.user,
                    comment="Обновленный файл при редактировании карточки документа",
                    ip_address=get_client_ip(self.request),
                    user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                )
            else:
                file_title = form.cleaned_data.get("initial_file_title") or initial_file.name
                doc_file = DocFlowFile.objects.create(
                    document=document,
                    title=file_title,
                    is_main=True,
                    current_version_number="1.0",
                )
                DocFlowVersionService.upload_new_file_version(
                    doc_file=doc_file,
                    file_obj=initial_file,
                    user=self.request.user,
                    comment="Исходная редакция документа",
                    version_number="1.0",
                    ip_address=get_client_ip(self.request),
                    user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                )

        # Обновление маршрута если статус черновика и согласование не запущено
        route_mode = form.cleaned_data.get("route_mode", "TEMPLATE")
        first_approver = form.cleaned_data.get("first_approver")
        first_approver_division = form.cleaned_data.get("first_approver_division")
        first_approver_sla = form.cleaned_data.get("first_approver_sla") or 24
        route_template = form.cleaned_data.get("route_template")

        if document.status == DocFlowDocument.Status.DRAFT and not document.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).exists():
            if route_mode == "DYNAMIC" or first_approver or first_approver_division:
                DocFlowRoutingService.create_dynamic_initial_route(
                    document=document,
                    approver=first_approver,
                    division=first_approver_division,
                    sla_hours=first_approver_sla,
                )
            elif route_template:
                DocFlowRoutingService.build_route_from_template(
                    document=document,
                    template_id=route_template.id,
                    fallback_to_dynamic=True,
                )

        # Если нажата кнопка «Сохранить и запустить согласование»
        if self.request.POST.get("form_action") == "start":
            try:
                DocFlowRoutingService.start_approval_process(
                    document=document,
                    user=self.request.user,
                    first_approver=first_approver,
                    first_division=first_approver_division,
                    first_sla_hours=first_approver_sla,
                    ip_address=get_client_ip(self.request),
                    user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.success(self.request, f"Документ {document.reg_number} успешно сохранен и запущен на согласование!")
            except Exception as exc:
                messages.error(self.request, f"Документ сохранен, но запуск согласования не удался: {exc}")
        else:
            messages.success(self.request, "Изменения карточки документа успешно сохранены.")

        return redirect("logistics_app:docflow_detail", pk=document.pk)


class DocFlowDocumentDetailView(LoginRequiredMixin, DetailView):
    """Детальная карточка документа СЭД с таймлайном, Stepper, файлами и аудит-логом."""

    model = DocFlowDocument
    template_name = "logistics_app/docflow_detail.html"
    context_object_name = "document"

    def get_object(self, queryset: Optional[QuerySet[DocFlowDocument]] = None) -> DocFlowDocument:
        """Получает документ и выполняет иерархическую проверку прав доступа."""
        obj: DocFlowDocument = super().get_object(queryset)
        user = self.request.user

        if user.is_superuser or user.is_staff:
            return obj

        # 1. Личный доступ участника процесса
        if (
            user == obj.initiator
            or user == obj.responsible
            or obj.route_steps.filter(Q(assigned_user=user) | Q(assigned_users=user) | Q(approved_users=user)).exists()
            or obj.approval_logs.filter(user=user).exists()
        ):
            return obj

        # 2. Иерархический доступ по подразделению
        from customers_app.services.org_structure_service import OrgStructureService
        accessible_div_ids = OrgStructureService.get_user_accessible_division_ids(user)

        initiator_div_id = None
        if hasattr(obj.initiator, "user_work_profile") and obj.initiator.user_work_profile:
            initiator_div_id = obj.initiator.user_work_profile.divisions_id

        responsible_div_id = None
        if obj.responsible and hasattr(obj.responsible, "user_work_profile") and obj.responsible.user_work_profile:
            responsible_div_id = obj.responsible.user_work_profile.divisions_id

        waybill_div_id = None
        if obj.related_waybill and obj.related_waybill.place_division_id:
            waybill_div_id = obj.related_waybill.place_division_id

        route_step_div_ids = set(
            obj.route_steps.exclude(assigned_division__isnull=True).values_list("assigned_division_id", flat=True)
        )

        if (
            (initiator_div_id and initiator_div_id in accessible_div_ids)
            or (responsible_div_id and responsible_div_id in accessible_div_ids)
            or (waybill_div_id and waybill_div_id in accessible_div_ids)
            or bool(route_step_div_ids.intersection(accessible_div_ids))
        ):
            return obj

        raise PermissionDenied("У вас нет прав для просмотра документов данного подразделения.")

    def get_queryset(self) -> QuerySet[DocFlowDocument]:
        """Оптимизированная выборка документа со всеми связями."""
        return (
            DocFlowDocument.objects.select_related(
                "doc_type",
                "initiator",
                "responsible",
                "counteragent",
                "related_waybill",
                "related_package",
                "related_contract",
            )
            .prefetch_related(
                "files",
                "files__versions",
                "files__versions__uploaded_by",
                "route_steps",
                "route_steps__assigned_division",
                "route_steps__assigned_user",
                "route_steps__assigned_users",
                "route_steps__approved_users",
                "approval_logs",
                "approval_logs__user",
                "approval_logs__route_step",
                "comments",
                "comments__author",
                "comments__replies",
                "comments__replies__author",
            )
        )

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует расширенный контекст карточки документа СЭД."""
        context = super().get_context_data(**kwargs)
        doc: DocFlowDocument = self.object
        user = self.request.user
        user_work_profile = getattr(user, "user_work_profile", None)
        division = getattr(user_work_profile, "divisions", None) if user_work_profile else None

        # Активный шаг маршрута
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()
        context["active_step"] = active_step

        # Права пользователя на согласование текущего активного этапа
        can_approve = False
        if active_step and doc.status == DocFlowDocument.Status.ON_APPROVAL:
            if user.is_superuser:
                can_approve = True
            elif active_step.assigned_user == user:
                can_approve = True
            elif active_step.assigned_users.filter(id=user.id).exists():
                can_approve = True
            elif division and active_step.assigned_division == division:
                can_approve = True
        context["can_approve"] = can_approve

        # Доступность отката
        can_rollback = False
        if active_step and can_approve:
            can_rollback = doc.route_steps.filter(
                step_order__lt=active_step.step_order,
                can_rollback_to=True,
            ).exists()
        context["can_rollback"] = can_rollback

        # Права автора на редактирование и перезапуск
        context["can_author_edit"] = (
            user == doc.initiator or user == doc.responsible or user.is_superuser
        ) and doc.status in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK]

        # Права на загрузку новой версии файла (заблокировано для завершенных документов)
        can_upload_file = False
        if not doc.is_finalized:
            if doc.status in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK]:
                can_upload_file = (user == doc.initiator or user == doc.responsible or user.is_superuser)
            elif doc.status == DocFlowDocument.Status.ON_APPROVAL:
                can_upload_file = (can_approve and active_step and active_step.allow_reviewer_file_edit) or user.is_superuser
        context["can_upload_file"] = can_upload_file

        # Инициализация модальных форм действий
        context["approval_form"] = DocFlowApprovalActionForm()
        context["rollback_form"] = (
            DocFlowRollbackActionForm(document=doc, current_step=active_step)
            if active_step
            else None
        )
        context["rework_form"] = DocFlowReworkActionForm()
        context["file_upload_form"] = DocFlowFileUploadForm() if can_upload_file else None
        context["comment_form"] = DocFlowCommentForm()
        context["add_step_form"] = DocFlowRouteStepForm()

        return context

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Обрабатывает GET-запрос: отображение карточки либо экспорт листа согласования в PDF.

        Args:
            request (HttpRequest): Объект HTTP-запроса.

        Returns:
            HttpResponse: HTML-страница карточки или PDF-файл листа согласования.
        """
        self.object = self.get_object()
        if request.GET.get("export") == "pdf":
            try:
                base_url = f"{request.scheme}://{request.get_host()}"
                pdf_bytes = DocFlowSheetGenerator.generate_approval_sheet_pdf(self.object, base_url=base_url)
                reg_num_clean = (self.object.reg_number or "Черновик").replace("/", "_").replace(" ", "_")
                filename = f"Лист_согласования_{reg_num_clean}.pdf"

                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = f'inline; filename="{filename}"'
                return response
            except Exception as exc:
                logger.error("Ошибка формирования PDF листа согласования для документа %s: %s", self.object.id, exc)
                messages.error(request, f"Ошибка формирования PDF листа согласования: {exc}")

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class DocFlowStartApprovalView(LoginRequiredMixin, View):
    """Обработчик запуска процесса согласования документа."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Запуск маршрута."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)

        if doc.initiator != request.user and doc.responsible != request.user and not request.user.is_superuser:
            raise PermissionDenied("Только автор или ответственный может запустить согласование.")

        try:
            DocFlowRoutingService.start_approval_process(
                document=doc,
                user=request.user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, f"Маршрут согласования документа {doc.reg_number} успешно запущен!")
        except Exception as exc:
            messages.error(request, f"Ошибка запуска согласования: {exc}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowApproveStepView(LoginRequiredMixin, View):
    """Обработчик наложения визы согласования согласующим лицом."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Наложение визы и возможное динамическое назначение исполнителей следующего шага."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()

        if not active_step:
            messages.error(request, "В документе нет активного этапа для согласования.")
            return redirect("logistics_app:docflow_detail", pk=pk)

        form = DocFlowApprovalActionForm(request.POST)
        if form.is_valid():
            comment = form.cleaned_data.get("comment", "")
            is_minor_edit = form.cleaned_data.get("is_minor_edit", False)
            next_step_action = form.cleaned_data.get("next_step_action") or "AUTO"
            next_executor = form.cleaned_data.get("next_executor")
            next_executors = list(form.cleaned_data.get("next_executors") or [])
            next_division = form.cleaned_data.get("next_division")
            next_step_name = form.cleaned_data.get("next_step_name") or ""
            next_sla_hours = form.cleaned_data.get("next_sla_hours") or 48
            next_step_instructions = form.cleaned_data.get("next_step_instructions") or ""

            try:
                result = DocFlowRoutingService.process_approval(
                    document=doc,
                    step=active_step,
                    user=request.user,
                    comment=comment,
                    is_minor_edit=is_minor_edit,
                    next_step_action=next_step_action,
                    next_executor=next_executor,
                    next_executors=next_executors,
                    next_division=next_division,
                    next_step_name=next_step_name,
                    next_sla_hours=next_sla_hours,
                    next_step_instructions=next_step_instructions,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                if result.get("status") == "completed":
                    messages.success(request, "Документ успешно согласован и финализирован!")
                elif result.get("status") == "next_step":
                    messages.success(request, f"Ваша виза успешно наложена. Документ перешел на этап «{result['next_step'].step_name}».")
                else:
                    messages.info(request, "Ваша виза зафиксирована. Ожидается визирование остальных участников параллельного этапа.")
            except Exception as exc:
                messages.error(request, f"Ошибка наложения визы: {exc}")
        else:
            messages.error(request, f"Пожалуйста, проверьте форму: {form.errors}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowAddRouteStepView(LoginRequiredMixin, View):
    """Добавление произвольного (ad-hoc) этапа в маршрут черновика документа."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Обрабатывает POST-запрос добавления этапа маршрута."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        if doc.initiator != request.user and doc.responsible != request.user and not request.user.is_superuser:
            raise PermissionDenied("Добавление этапов доступно только автору или ответственному за документ.")
        if doc.status not in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK]:
            messages.error(request, "Добавлять этапы можно только в черновике или документе на доработке.")
            return redirect("logistics_app:docflow_detail", pk=pk)

        form = DocFlowRouteStepForm(request.POST)
        if form.is_valid():
            try:
                DocFlowRoutingService.add_ad_hoc_step(
                    document=doc,
                    step_name=form.cleaned_data.get("step_name"),
                    step_type=form.cleaned_data.get("step_type"),
                    assigned_user=form.cleaned_data.get("assigned_user"),
                    assigned_users=list(form.cleaned_data.get("assigned_users") or []),
                    assigned_division=form.cleaned_data.get("assigned_division"),
                    sla_hours=form.cleaned_data.get("sla_hours") or 24,
                    allow_reviewer_file_edit=form.cleaned_data.get("allow_reviewer_file_edit", True),
                    can_rollback_to=form.cleaned_data.get("can_rollback_to", True),
                )
                messages.success(request, f"Этап «{form.cleaned_data.get('step_name')}» успешно добавлен в маршрут!")
            except Exception as exc:
                messages.error(request, f"Ошибка добавления этапа: {exc}")
        else:
            messages.error(request, f"Ошибка валидации данных шага: {form.errors}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowDeleteRouteStepView(LoginRequiredMixin, View):
    """Удаление шага из цепочки маршрута черновика документа."""

    def post(self, request: HttpRequest, pk: Any, step_id: int) -> HttpResponse:
        """Обрабатывает POST-запрос удаления шага."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        if doc.initiator != request.user and doc.responsible != request.user and not request.user.is_superuser:
            raise PermissionDenied("Удаление этапов доступно только автору или ответственному за документ.")

        try:
            success = DocFlowRoutingService.remove_ad_hoc_step(doc, step_id=step_id)
            if success:
                messages.success(request, "Этап маршрута успешно удален.")
            else:
                messages.error(request, "Указанный этап не найден.")
        except Exception as exc:
            messages.error(request, f"Ошибка удаления этапа: {exc}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowRollbackStepView(LoginRequiredMixin, View):
    """Обработчик многошагового отката на выбранный пройденный этап."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Выполнение отката."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()

        if not active_step:
            messages.error(request, "В документе нет активного этапа для отката.")
            return redirect("logistics_app:docflow_detail", pk=pk)

        form = DocFlowRollbackActionForm(request.POST, document=doc, current_step=active_step)
        if form.is_valid():
            target_order = int(form.cleaned_data["target_step_order"])
            comment = form.cleaned_data["comment"]

            try:
                DocFlowRoutingService.process_rollback(
                    document=doc,
                    step=active_step,
                    user=request.user,
                    target_step_order=target_order,
                    comment=comment,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.warning(request, f"Документ успешно возвращен на этап №{target_order}.")
            except Exception as exc:
                messages.error(request, f"Ошибка выполнения отката: {exc}")
        else:
            messages.error(request, "Заполните обязательное поле замечаний для отката.")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowReturnReworkView(LoginRequiredMixin, View):
    """Обработчик возврата документа автору на доработку."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Возврат на доработку."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()

        form = DocFlowReworkActionForm(request.POST)
        if form.is_valid():
            comment = form.cleaned_data["comment"]
            try:
                DocFlowRoutingService.process_rework_return(
                    document=doc,
                    step=active_step,
                    user=request.user,
                    comment=comment,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.warning(request, "Документ возвращен автору на доработку с замечаниями.")
            except Exception as exc:
                messages.error(request, f"Ошибка возврата на доработку: {exc}")
        else:
            messages.error(request, "Укажите причину и перечень замечаний для возврата.")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowRestartRouteView(LoginRequiredMixin, View):
    """Возобновление маршрута согласования после устранения замечаний."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Возобновление."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)

        resume_mode = request.POST.get("resume_mode", "step") == "step"
        try:
            DocFlowRoutingService.restart_route_after_rework(
                document=doc,
                user=request.user,
                resume_from_returned_step=resume_mode,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, "Маршрут согласования успешно возобновлен!")
        except Exception as exc:
            messages.error(request, f"Ошибка возобновления маршрута: {exc}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowRejectView(LoginRequiredMixin, View):
    """Отклонение документа согласующим лицом."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Отклонение."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()

        reason = request.POST.get("reject_reason", "Отклонено согласующим лицом.")
        try:
            DocFlowRoutingService.process_rejection(
                document=doc,
                step=active_step,
                user=request.user,
                comment=reason,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.error(request, "Документ был окончательно отклонен.")
        except Exception as exc:
            messages.error(request, f"Ошибка отклонения документа: {exc}")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowUploadVersionView(LoginRequiredMixin, View):
    """Загрузка новой версии файла к документу."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Загрузка версии файла с обязательной проверкой неизменяемости документа."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)

        # 1. Защита завершенных / архивных / отклоненных документов от любых модификаций
        if doc.is_finalized:
            messages.error(
                request,
                f"Документ находится в завершенном статусе «{doc.get_status_display()}» и защищен от изменения файлов и загрузки новых версий."
            )
            return redirect("logistics_app:docflow_detail", pk=pk)

        # 2. Проверка прав пользователя на загрузку на текущем этапе
        user = request.user
        can_upload = False
        if doc.status in [DocFlowDocument.Status.DRAFT, DocFlowDocument.Status.ON_REWORK]:
            can_upload = (user == doc.initiator or user == doc.responsible or user.is_superuser)
        elif doc.status == DocFlowDocument.Status.ON_APPROVAL:
            active_step = doc.active_steps.first()
            if active_step:
                is_assigned = (
                    active_step.assigned_user == user
                    or active_step.assigned_users.filter(id=user.id).exists()
                    or (hasattr(user, "user_work_profile") and user.user_work_profile.divisions and active_step.assigned_division == user.user_work_profile.divisions)
                )
                can_upload = (is_assigned and active_step.allow_reviewer_file_edit) or user.is_superuser

        if not can_upload:
            messages.error(request, "У вас нет прав на загрузку новой редакции файла для данного документа на текущем этапе.")
            return redirect("logistics_app:docflow_detail", pk=pk)

        file_id = request.POST.get("doc_file_id")

        if file_id:
            doc_file = get_object_or_404(DocFlowFile, id=file_id, document=doc)
        else:
            doc_file = doc.main_file
            if not doc_file:
                doc_file = DocFlowFile.objects.create(
                    document=doc,
                    title="Основной документ",
                    is_main=True,
                )

        form = DocFlowFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            comment = form.cleaned_data.get("comment", "")
            is_reviewer_edit = form.cleaned_data.get("is_reviewer_edit", False)

            try:
                version = DocFlowVersionService.upload_new_file_version(
                    doc_file=doc_file,
                    file_obj=uploaded_file,
                    user=request.user,
                    comment=comment,
                    is_reviewer_edit=is_reviewer_edit,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.success(request, f"Успешно загружена версия v{version.version_number} файла «{doc_file.title}»!")
            except Exception as exc:
                messages.error(request, f"Ошибка сохранения версии файла: {exc}")
        else:
            messages.error(request, "Ошибка валидации файла. Пожалуйста, выберите корректный файл.")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowAddCommentView(LoginRequiredMixin, View):
    """Добавление комментария / сообщения в ветку обсуждения документа."""

    def post(self, request: HttpRequest, pk: Any) -> HttpResponse:
        """Отправка сообщения."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        form = DocFlowCommentForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.document = doc
            comment.author = request.user
            comment.save()

            # Фиксируем в аудит-логе
            DocFlowApprovalLog.objects.create(
                document=doc,
                user=request.user,
                action=DocFlowApprovalLog.Action.COMMENTED,
                comment=f"Добавлен комментарий: {comment.text[:100]}...",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            if request.headers.get("HX-Request"):
                return render(request, "logistics_app/partials/docflow_comment_item.html", {"comment": comment})

            messages.success(request, "Комментарий успешно добавлен.")
        else:
            messages.error(request, "Текст комментария не может быть пустым.")

        return redirect("logistics_app:docflow_detail", pk=pk)


class DocFlowVersionDownloadView(LoginRequiredMixin, View):
    """Безопасная отдача файла определенной версии документа."""

    def get(self, request: HttpRequest, version_id: int) -> HttpResponse:
        """Скачивание файла версии."""
        version = get_object_or_404(DocFlowFileVersion.objects.select_related("doc_file", "doc_file__document"), id=version_id)
        if not version.file:
            raise Http404("Файл не найден.")

        try:
            return FileResponse(
                version.file.open("rb"),
                as_attachment=True,
                filename=f"{version.doc_file.title}_v{version.version_number}.{version.file.name.split('.')[-1]}",
            )
        except Exception as exc:
            logger.error("Ошибка открытия файла версии ID %d: %s", version_id, exc)
            raise Http404("Не удалось прочитать файл с диска.")


# ==============================================================================
# УПРАВЛЕНИЕ ШАБЛОНАМИ МАРШРУТОВ СОГЛАСОВАНИЯ
# ==============================================================================

class DocFlowRouteTemplateListView(LoginRequiredMixin, ListView):
    """Справочник шаблонов маршрутов согласования СЭД."""

    model = DocFlowRouteTemplate
    template_name = "logistics_app/docflow_template_list.html"
    context_object_name = "templates"

    def get_queryset(self) -> QuerySet[DocFlowRouteTemplate]:
        """Оптимизированная выборка шаблонов со связанными шагами."""
        return (
            DocFlowRouteTemplate.objects.select_related("doc_type")
            .prefetch_related("steps", "steps__assigned_division", "steps__assigned_user")
            .order_by("doc_type__category", "doc_type__name", "name")
        )


class DocFlowRouteTemplateCreateView(LoginRequiredMixin, CreateView):
    """Создание нового шаблона маршрута согласования с этапами."""

    model = DocFlowRouteTemplate
    form_class = DocFlowRouteTemplateForm
    template_name = "logistics_app/docflow_template_form.html"
    success_url = reverse_lazy("logistics_app:docflow_template_list")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет шагов маршрута в контекст."""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["steps_formset"] = DocFlowRouteStepTemplateFormSet(self.request.POST)
        else:
            context["steps_formset"] = DocFlowRouteStepTemplateFormSet()
        context["users"] = DataBaseUser.objects.filter(is_active=True).order_by("last_name", "first_name")
        context["divisions"] = Division.objects.all().order_by("name")
        return context

    def form_valid(self, form: DocFlowRouteTemplateForm) -> HttpResponse:
        """Сохранение шаблона и связанных шагов в единой транзакции."""
        context = self.get_context_data()
        steps_formset = context["steps_formset"]
        if steps_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                steps_formset.instance = self.object
                steps_formset.save()
            messages.success(self.request, f"Шаблон маршрута «{self.object.name}» с этапами успешно создан!")
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form, steps_formset=steps_formset))


class DocFlowRouteTemplateUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование параметров шаблона маршрута и его этапов."""

    model = DocFlowRouteTemplate
    form_class = DocFlowRouteTemplateForm
    template_name = "logistics_app/docflow_template_form.html"
    success_url = reverse_lazy("logistics_app:docflow_template_list")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет шагов маршрута в контекст."""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["steps_formset"] = DocFlowRouteStepTemplateFormSet(self.request.POST, instance=self.object)
        else:
            context["steps_formset"] = DocFlowRouteStepTemplateFormSet(instance=self.object)
        context["users"] = DataBaseUser.objects.filter(is_active=True).order_by("last_name", "first_name")
        context["divisions"] = Division.objects.all().order_by("name")
        return context

    def form_valid(self, form: DocFlowRouteTemplateForm) -> HttpResponse:
        """Обновление шаблона и его шагов в транзакции."""
        context = self.get_context_data()
        steps_formset = context["steps_formset"]
        if steps_formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                steps_formset.instance = self.object
                steps_formset.save()
            messages.success(self.request, f"Шаблон маршрута «{self.object.name}» успешно обновлен!")
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form, steps_formset=steps_formset))


class DocFlowRouteTemplateDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление шаблона маршрута."""

    model = DocFlowRouteTemplate
    template_name = "logistics_app/docflow_template_confirm_delete.html"
    success_url = reverse_lazy("logistics_app:docflow_template_list")

    def delete(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Удаление."""
        messages.warning(request, "Шаблон маршрута удален.")
        return super().delete(request, *args, **kwargs)


# ==============================================================================
# УПРАВЛЕНИЕ ВИДАМИ ДОКУМЕНТОВ СЭД
# ==============================================================================

class DocFlowDocumentTypeListView(LoginRequiredMixin, ListView):
    """Справочник видов документов СЭД."""

    model = DocFlowDocumentType
    template_name = "logistics_app/docflow_type_list.html"
    context_object_name = "doc_types"

    def get_queryset(self) -> QuerySet[DocFlowDocumentType]:
        """Оптимизированная выборка видов документов со счетчиками шаблонов и документов."""
        return (
            DocFlowDocumentType.objects.annotate(
                templates_count=Count("route_templates", distinct=True),
                documents_count=Count("documents", distinct=True),
            )
            .order_by("category", "name")
        )


class DocFlowDocumentTypeCreateView(LoginRequiredMixin, CreateView):
    """Создание нового вида документа СЭД."""

    model = DocFlowDocumentType
    form_class = DocFlowDocumentTypeForm
    template_name = "logistics_app/docflow_type_form.html"
    success_url = reverse_lazy("logistics_app:docflow_type_list")

    def form_valid(self, form: DocFlowDocumentTypeForm) -> HttpResponse:
        """Сохранение нового вида документа."""
        self.object = form.save()
        messages.success(self.request, f"Вид документа «{self.object.name}» успешно добавлен!")
        return HttpResponseRedirect(self.get_success_url())


class DocFlowDocumentTypeUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование вида документа СЭД."""

    model = DocFlowDocumentType
    form_class = DocFlowDocumentTypeForm
    template_name = "logistics_app/docflow_type_form.html"
    success_url = reverse_lazy("logistics_app:docflow_type_list")

    def form_valid(self, form: DocFlowDocumentTypeForm) -> HttpResponse:
        """Обновление вида документа."""
        self.object = form.save()
        messages.success(self.request, f"Вид документа «{self.object.name}» успешно обновлен!")
        return HttpResponseRedirect(self.get_success_url())


class DocFlowDocumentTypeDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление вида документа СЭД."""

    model = DocFlowDocumentType
    template_name = "logistics_app/docflow_type_confirm_delete.html"
    success_url = reverse_lazy("logistics_app:docflow_type_list")

    def delete(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Удаление с проверкой наличия связанных документов."""
        doc_type = self.get_object()
        if doc_type.documents.exists():
            messages.error(
                request,
                f"Невозможно удалить вид «{doc_type.name}», так как в системе существуют зарегистрированные документы этого вида."
            )
            return HttpResponseRedirect(self.get_success_url())
        messages.warning(request, f"Вид документа «{doc_type.name}» удален.")
        return super().delete(request, *args, **kwargs)

