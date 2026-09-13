"""Контроллеры представлений подсистемы электронного документооборота (СЭД) logistics_app."""

import logging
from typing import Any, Dict, Optional

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

        # Формирование цепочки маршрута из шаблона
        route_template = form.cleaned_data.get("route_template")
        template_id = route_template.id if route_template else None
        try:
            DocFlowRoutingService.build_route_from_template(document, template_id=template_id)
        except Exception as exc:
            logger.warning("Не удалось автоматически построить маршрут для документа %s: %s", document.id, exc)

        # Если нажата кнопка «Сохранить и запустить согласование»
        if self.request.POST.get("form_action") == "start":
            try:
                DocFlowRoutingService.start_approval_process(
                    document=document,
                    user=self.request.user,
                    ip_address=get_client_ip(self.request),
                    user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.success(self.request, f"Документ {document.reg_number} успешно создан и отправлен на согласование!")
            except Exception as exc:
                messages.error(self.request, f"Документ сохранен как черновик, но запуск согласования не удался: {exc}")
        else:
            messages.success(self.request, "Карточка документа успешно сохранена в виде черновика.")

        return redirect("logistics_app:docflow_detail", pk=document.pk)


class DocFlowDocumentDetailView(LoginRequiredMixin, DetailView):
    """Детальная карточка документа СЭД с таймлайном, Stepper, файлами и аудит-логом."""

    model = DocFlowDocument
    template_name = "logistics_app/docflow_detail.html"
    context_object_name = "document"

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

        # Инициализация модальных форм действий
        context["approval_form"] = DocFlowApprovalActionForm()
        context["rollback_form"] = (
            DocFlowRollbackActionForm(document=doc, current_step=active_step)
            if active_step
            else None
        )
        context["rework_form"] = DocFlowReworkActionForm()
        context["file_upload_form"] = DocFlowFileUploadForm()
        context["comment_form"] = DocFlowCommentForm()

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
        """Наложение визы."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
        active_step = doc.route_steps.filter(status=DocFlowRouteStep.Status.IN_PROGRESS).first()

        if not active_step:
            messages.error(request, "В документе нет активного этапа для согласования.")
            return redirect("logistics_app:docflow_detail", pk=pk)

        form = DocFlowApprovalActionForm(request.POST)
        if form.is_valid():
            comment = form.cleaned_data.get("comment", "")
            is_minor_edit = form.cleaned_data.get("is_minor_edit", False)

            try:
                result = DocFlowRoutingService.process_approval(
                    document=doc,
                    step=active_step,
                    user=request.user,
                    comment=comment,
                    is_minor_edit=is_minor_edit,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                if result.get("status") == "completed":
                    messages.success(request, "Документ успешно согласован всеми инстанциями!")
                elif result.get("status") == "next_step":
                    messages.success(request, f"Ваша виза успешно наложена. Документ перешел на этап «{result['next_step'].step_name}».")
                else:
                    messages.info(request, "Ваша виза зафиксирована. Ожидается визирование остальных участников параллельного этапа.")
            except Exception as exc:
                messages.error(request, f"Ошибка наложения визы: {exc}")
        else:
            messages.error(request, "Пожалуйста, подтвердите наложение ПЭП.")

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
        """Загрузка версии."""
        doc = get_object_or_404(DocFlowDocument, pk=pk)
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

