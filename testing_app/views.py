"""Представления (Views) модуля периодического тестирования сотрудников."""

from urllib.parse import quote
import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.encoding import escape_uri_path
from django.views import View
from django.views.generic import (
    TemplateView,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    DetailView,
)

from testing_app.models import (
    Question,
    QuestionCategory,
    AnswerOption,
    Testing,
    TestingGroup,
    TestingGroupPosition,
    TestingCategorySetting,
    TestingAssignment,
    TestingAttempt,
    AttemptQuestion,
    UserAnswer,
    TestingAuditLog,
    LectureMaterial,
    VideoLecture,
    MaterialViewLog,
)
from testing_app.forms import (
    QuestionImportForm,
    QuestionCategoryForm,
    QuestionForm,
    AnswerOptionFormSet,
    TestingForm,
    GroupPositionsForm,
    ManualAssignmentForm,
    LectureMaterialForm,
    VideoLectureForm,
)
from testing_app.services.excel_service import (
    generate_question_import_template,
    import_questions_from_excel,
)
from testing_app.services.material_service import (
    log_material_access,
    get_material_dashboard_stats,
    get_material_access_report_qs,
    export_material_report_excel,
    export_material_report_csv,
)
from administration_app.utils import get_client_ip, get_device_info
from customers_app.models import Affiliation, Job, DataBaseUser, Division
from testing_app.services.event_service import (
    ensure_default_groups_exist,
    sync_group_positions,
    save_group_positions_and_employee_distribution,
    auto_assign_employees_by_positions,
    add_manual_assignment,
    remove_assignment,
    update_category_settings,
    change_testing_status,
)
from testing_app.services.engine_service import (
    start_or_resume_attempt,
    save_draft_answer,
    finish_attempt,
)
from testing_app.selectors.testing_selectors import (
    get_user_assignments,
    get_attempt_questions_for_test_engine,
    get_attempt_results_detail,
)
from testing_app.services.certificate_service import (
    get_certificate_context,
    verify_certificate_by_uuid,
    get_user_full_name_with_patronymic,
)
from testing_app.selectors.dashboard_selectors import (
    get_dashboard_kpi_metrics,
    get_attempts_funnel_analytics,
    get_groups_comparison_analytics,
    get_divisions_breakdown_analytics,
    get_top_hardest_questions,
    get_live_active_sessions,
)
from testing_app.services.report_service import (
    generate_testing_protocol_excel,
    generate_testing_protocol_csv,
)
from django.core.exceptions import ValidationError


def is_testing_manager_user(user) -> bool:
    """Проверяет, обладает ли пользователь правами ответственного за тестирование.

    Правами обладают только суперпользователи и члены группы 'Ответственные за тестирование'.
    Обычные сотрудники (включая тех, у кого выставлен флаг is_staff для других модулей портала)
    доступа к управлению тестированием, созданию, редактированию и удалению материалов не имеют.

    Args:
        user: Пользователь системы.

    Returns:
        bool: True, если пользователь суперпользователь или состоит в группе 'Ответственные за тестирование'.
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name="Ответственные за тестирование").exists()


class TestingManagerRequiredMixin(UserPassesTestMixin):
    """Миксин проверки прав доступа: только суперпользователи или группа 'Ответственные за тестирование'."""

    def test_func(self):
        return is_testing_manager_user(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "У вас нет прав для доступа к управлению тестированием.")
        return redirect("testing_app:my_tests")


class TestingIndexView(LoginRequiredMixin, View):
    """Главная точка входа модуля тестирования.

    Перенаправляет ответственных сотрудников в панель управления,
    а остальных пользователей — в личный кабинет тестирования.
    """

    def get(self, request, *args, **kwargs):
        if is_testing_manager_user(request.user):
            return redirect("testing_app:dashboard")
        return redirect("testing_app:my_tests")


class MyTestsView(LoginRequiredMixin, TemplateView):
    """Кабинет сотрудника: список назначенных и доступных тестирований."""

    template_name = "testing_app/my_tests.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignments = get_user_assignments(self.request.user)
        context["assignments"] = assignments
        return context


class ManagerDashboardView(LoginRequiredMixin, TestingManagerRequiredMixin, TemplateView):
    """Панель управления и онлайн-мониторинга ответственного за тестирование."""

    template_name = "testing_app/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        event_id_raw = self.request.GET.get("event_id")
        event_id = None
        if event_id_raw:
            try:
                event_id = int(event_id_raw)
            except (ValueError, TypeError):
                pass

        all_events = Testing.objects.order_by("-start_datetime")
        selected_event = Testing.objects.filter(id=event_id).first() if event_id else None

        context["events"] = all_events
        context["selected_event"] = selected_event
        context["selected_event_id"] = event_id or ""

        # Расчет аналитических показателей
        context["kpi"] = get_dashboard_kpi_metrics(event_id)
        context["funnel"] = get_attempts_funnel_analytics(event_id)
        context["groups_stats"] = get_groups_comparison_analytics(event_id)
        context["divisions_stats"] = get_divisions_breakdown_analytics(event_id)
        context["hardest_questions"] = get_top_hardest_questions(limit=5)
        context["live_sessions"] = get_live_active_sessions(event_id)
        context["materials_stats"] = get_material_dashboard_stats()

        return context


# ==============================================================================
# БАНК ВОПРОСОВ И КАТЕГОРИИ (ЭТАП 2)
# ==============================================================================

class QuestionBankListView(LoginRequiredMixin, TestingManagerRequiredMixin, ListView):
    """Список вопросов банка вопросов с фильтрацией, поиском и пагинацией.

    Attributes:
        model: Модель Question.
        template_name: Путь к шаблону списка вопросов.
        paginate_by: Количество вопросов на одну страницу.
    """

    model = Question
    template_name = "testing_app/questions_bank.html"
    context_object_name = "questions"
    paginate_by = 25

    def get_queryset(self):
        """Формирует QuerySet с учетом фильтрации по категории, статусу, сложности и тексту."""
        qs = Question.objects.select_related("category", "author").prefetch_related("options")

        # Фильтр по категории
        cat_id = self.request.GET.get("category")
        if cat_id:
            qs = qs.filter(category_id=cat_id)

        # Фильтр по статусу
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        # Фильтр по сложности
        difficulty = self.request.GET.get("difficulty")
        if difficulty:
            qs = qs.filter(difficulty=difficulty)

        # Поиск по тексту вопроса и пояснению
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(text__icontains=q) | Q(explanation__icontains=q))

        return qs.order_by("-id")

    def get_context_data(self, **kwargs):
        """Дополняет контекст статистикой по банку вопросов и списком категорий."""
        context = super().get_context_data(**kwargs)
        context["categories"] = QuestionCategory.objects.annotate(
            q_count=Count("questions")
        ).order_by("name")

        # Сводные показатели
        context["total_questions_count"] = Question.objects.count()
        context["active_questions_count"] = Question.objects.filter(status=Question.Status.ACTIVE).count()
        context["archived_questions_count"] = Question.objects.filter(status=Question.Status.ARCHIVED).count()
        context["categories_count"] = QuestionCategory.objects.count()

        # Текущие фильтры
        context["selected_category"] = self.request.GET.get("category", "")
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_difficulty"] = self.request.GET.get("difficulty", "")
        context["search_query"] = self.request.GET.get("q", "")

        return context


class QuestionTemplateDownloadView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Выгрузка эталонного Excel-шаблона для последующего импорта вопросов."""

    def get(self, request, *args, **kwargs):
        wb = generate_question_import_template()
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = "Шаблон_импорта_вопросов.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'
        wb.save(response)
        return response


class QuestionImportView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Представление загрузки и пакетного импорта вопросов из файла Excel."""

    template_name = "testing_app/question_import.html"

    def get(self, request, *args, **kwargs):
        form = QuestionImportForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = QuestionImportForm(request.POST, request.FILES)
        import_result = None

        if form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            import_result = import_questions_from_excel(uploaded_file, user=request.user)

            if import_result["success"]:
                messages.success(
                    request,
                    f"Импорт успешно завершен! Создано вопросов: {import_result['created_questions']}, "
                    f"новых категорий: {import_result['created_categories']}."
                )
            else:
                messages.error(request, "При импорте возникли ошибки. Ознакомьтесь с деталями ниже.")

        return render(request, self.template_name, {
            "form": form,
            "import_result": import_result
        })


class QuestionCreateView(LoginRequiredMixin, TestingManagerRequiredMixin, CreateView):
    """Ручное создание вопроса с 4 вариантами ответа."""

    model = Question
    form_class = QuestionForm
    template_name = "testing_app/question_form.html"
    success_url = reverse_lazy("testing_app:questions_bank")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["options_formset"] = AnswerOptionFormSet(self.request.POST)
        else:
            initial_options = [{"order_num": i} for i in range(1, 5)]
            context["options_formset"] = AnswerOptionFormSet(initial=initial_options)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        options_formset = context["options_formset"]

        if not options_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        # Проверка: ровно 1 правильный ответ
        correct_count = 0
        for opt_form in options_formset:
            if opt_form.cleaned_data.get("is_correct"):
                correct_count += 1

        if correct_count != 1:
            form.add_error(None, "Среди 4 вариантов ответа должен быть выбран ровно 1 правильный ответ.")
            return self.render_to_response(self.get_context_data(form=form))

        form.instance.author = self.request.user
        self.object = form.save()

        options_formset.instance = self.object
        options_formset.save()

        TestingAuditLog.objects.create(
            user=self.request.user,
            action="question_create",
            object_repr=f"Создан вопрос ID {self.object.id}",
            details={"text": self.object.text[:100], "category": self.object.category.name}
        )

        messages.success(self.request, "Вопрос успешно создан и добавлен в банк вопросов.")
        return redirect(self.success_url)


class QuestionUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, UpdateView):
    """Редактирование вопроса и его вариантов ответа."""

    model = Question
    form_class = QuestionForm
    template_name = "testing_app/question_form.html"
    success_url = reverse_lazy("testing_app:questions_bank")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["options_formset"] = AnswerOptionFormSet(self.request.POST, instance=self.object)
        else:
            context["options_formset"] = AnswerOptionFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        options_formset = context["options_formset"]

        if not options_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        correct_count = sum(
            1 for opt_form in options_formset
            if opt_form.cleaned_data.get("is_correct")
        )
        if correct_count != 1:
            form.add_error(None, "Среди 4 вариантов ответа должен быть выбран ровно 1 правильный ответ.")
            return self.render_to_response(self.get_context_data(form=form))

        self.object = form.save()
        options_formset.instance = self.object
        options_formset.save()

        TestingAuditLog.objects.create(
            user=self.request.user,
            action="question_update",
            object_repr=f"Обновлен вопрос ID {self.object.id}",
            details={"text": self.object.text[:100], "category": self.object.category.name}
        )

        messages.success(self.request, "Вопрос успешно обновлен.")
        return redirect(self.success_url)


class QuestionToggleArchiveView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Переключение статуса вопроса между активным и архивным."""

    def post(self, request, pk, *args, **kwargs):
        question = get_object_or_404(Question, pk=pk)
        if question.status == Question.Status.ACTIVE:
            question.status = Question.Status.ARCHIVED
            messages.info(request, f"Вопрос #{question.id} переведен в архив.")
        else:
            question.status = Question.Status.ACTIVE
            messages.success(request, f"Вопрос #{question.id} возвращен в активный банк.")
        question.save()

        TestingAuditLog.objects.create(
            user=request.user,
            action="question_toggle_archive",
            object_repr=f"Вопрос ID {question.id} изменен статус на {question.status}"
        )
        return redirect(request.META.get("HTTP_REFERER", "testing_app:questions_bank"))


class QuestionCategoryListView(LoginRequiredMixin, TestingManagerRequiredMixin, ListView):
    """Управление справочником категорий вопросов."""

    model = QuestionCategory
    template_name = "testing_app/categories_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return QuestionCategory.objects.annotate(
            total_questions=Count("questions")
        ).order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = QuestionCategoryForm()
        return context


class QuestionCategoryCreateView(LoginRequiredMixin, TestingManagerRequiredMixin, CreateView):
    """Создание новой категории вопросов."""

    model = QuestionCategory
    form_class = QuestionCategoryForm
    success_url = reverse_lazy("testing_app:categories_list")

    def form_valid(self, form):
        category = form.save()
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="category_create",
            object_repr=f"Создана категория: {category.name}"
        )
        messages.success(self.request, f"Категория «{category.name}» успешно создана.")
        return redirect(self.success_url)


class QuestionCategoryUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, UpdateView):
    """Редактирование категории вопросов."""

    model = QuestionCategory
    form_class = QuestionCategoryForm
    success_url = reverse_lazy("testing_app:categories_list")

    def form_valid(self, form):
        category = form.save()
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="category_update",
            object_repr=f"Обновлена категория: {category.name}"
        )
        messages.success(self.request, f"Категория «{category.name}» успешно сохранена.")
        return redirect(self.success_url)


# ==============================================================================
# МЕРОПРИЯТИЯ ТЕСТИРОВАНИЯ И ГРУППЫ (ЭТАП 3)
# ==============================================================================

class TestingEventListView(LoginRequiredMixin, TestingManagerRequiredMixin, ListView):
    """Список мероприятий тестирования с фильтрацией по статусу и поиском."""

    model = Testing
    template_name = "testing_app/event_list.html"
    context_object_name = "events"
    paginate_by = 20

    def get_queryset(self):
        qs = Testing.objects.annotate(
            assignments_count=Count("assignments")
        ).order_by("-start_datetime")

        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(order_number__icontains=q) | Q(order_name__icontains=q))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["active_events_count"] = Testing.objects.filter(status=Testing.Status.ACTIVE).count()
        context["draft_events_count"] = Testing.objects.filter(status=Testing.Status.DRAFT).count()
        context["completed_events_count"] = Testing.objects.filter(status=Testing.Status.COMPLETED).count()
        return context


class TestingEventCreateView(LoginRequiredMixin, TestingManagerRequiredMixin, CreateView):
    """Создание нового мероприятия тестирования."""

    model = Testing
    form_class = TestingForm
    template_name = "testing_app/event_form.html"

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.updated_by = self.request.user
        self.object = form.save()

        # Автоматическое создание двух стандартных групп согласно разделу 9 ТЗ
        ensure_default_groups_exist(self.object)

        TestingAuditLog.objects.create(
            user=self.request.user,
            action="event_create",
            object_repr=f"Создано мероприятие '{self.object.title}' (Приказ №{self.object.order_number})"
        )
        messages.success(
            self.request,
            f"Мероприятие «{self.object.title}» успешно создано. Настройте группы должностей и категории вопросов."
        )
        return redirect("testing_app:event_detail", pk=self.object.pk)


class TestingEventUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, UpdateView):
    """Редактирование параметров мероприятия тестирования."""

    model = Testing
    form_class = TestingForm
    template_name = "testing_app/event_form.html"

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        self.object = form.save()
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="event_update",
            object_repr=f"Обновлены параметры мероприятия '{self.object.title}'"
        )
        messages.success(self.request, "Параметры мероприятия успешно сохранены.")
        return redirect("testing_app:event_detail", pk=self.object.pk)


class TestingEventDetailView(LoginRequiredMixin, TestingManagerRequiredMixin, DetailView):
    """Детальная страница мероприятия тестирования: 4 вкладки настроек."""

    model = Testing
    template_name = "testing_app/event_detail.html"
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.object

        # Гарантируем наличие двух стандартных групп
        group1, group2 = ensure_default_groups_exist(event)
        context["group1"] = group1
        context["group2"] = group2

        # 1. Форма привязки должностей к группам (резервная обратная совместимость)
        g1_jobs = list(group1.group_positions.values_list("job_id", flat=True))
        g2_jobs = list(group2.group_positions.values_list("job_id", flat=True))
        context["positions_form"] = GroupPositionsForm(initial={
            "group1_positions": g1_jobs,
            "group2_positions": g2_jobs
        })

        # Новая структура: единый пул должностей с привязкой к division_affiliation и ручное распределение по 3 окнам
        affiliations = Affiliation.objects.filter(job__isnull=False).distinct().order_by("name")
        affiliated_jobs = Job.objects.filter(
            division_affiliation__isnull=False
        ).select_related("division_affiliation").order_by("division_affiliation__name", "name")

        all_selected_job_ids = list(
            TestingGroupPosition.objects.filter(group__testing=event).values_list("job_id", flat=True).distinct()
        )
        selected_aff_ids = list(
            Job.objects.filter(id__in=all_selected_job_ids, division_affiliation__isnull=False)
            .values_list("division_affiliation_id", flat=True).distinct()
        )

        candidate_employees_qs = DataBaseUser.objects.filter(
            is_active=True,
            user_work_profile__job__division_affiliation__isnull=False
        ).select_related(
            "user_work_profile__job",
            "user_work_profile__job__division_affiliation",
            "user_work_profile__divisions"
        ).order_by("last_name", "first_name")

        current_assignments_map = {
            a.employee_id: a.group_id
            for a in event.assignments.all()
        }

        candidates_data = []
        for emp in candidate_employees_qs:
            profile = getattr(emp, "user_work_profile", None)
            job = profile.job if profile else None
            division = profile.divisions if profile else None
            assigned_group_id = current_assignments_map.get(emp.id, 0)

            candidates_data.append({
                "id": emp.id,
                "full_name": emp.get_full_name() or emp.username,
                "job_id": job.id if job else 0,
                "job_name": job.name if job else "—",
                "division_name": division.name if division else "—",
                "affiliation_id": job.division_affiliation_id if job else 0,
                "assigned_group_id": assigned_group_id,
            })

        context["affiliations"] = affiliations
        context["affiliated_jobs"] = affiliated_jobs
        context["selected_job_ids"] = all_selected_job_ids
        context["selected_aff_ids"] = selected_aff_ids
        context["candidates_json"] = json.dumps(candidates_data, ensure_ascii=False)

        # 2. Назначенные сотрудники по группам
        context["g1_assignments"] = event.assignments.filter(group=group1).select_related(
            "employee"
        ).order_by("assigned_division_title", "employee__last_name")
        context["g2_assignments"] = event.assignments.filter(group=group2).select_related(
            "employee"
        ).order_by("assigned_division_title", "employee__last_name")
        context["manual_assign_form"] = ManualAssignmentForm(testing=event)

        # 3. Настройки категорий вопросов
        cat_settings_map = {cs.category_id: cs for cs in event.category_settings.select_related("category")}
        all_categories = QuestionCategory.objects.filter(is_active=True).order_by("name")
        categories_data = []
        total_percentage = 0

        for cat in all_categories:
            cs = cat_settings_map.get(cat.id)
            pct = cs.percentage if cs else 0
            total_percentage += pct
            calc_q = cs.calculated_questions_count if cs else round((pct / 100.0) * event.questions_count)
            categories_data.append({
                "category": cat,
                "percentage": pct,
                "calculated_count": calc_q,
                "active_count": cat.active_questions_count(),
                "is_sufficient": cat.active_questions_count() >= calc_q if pct > 0 else True
            })

        context["categories_data"] = categories_data
        context["total_percentage"] = total_percentage

        # 4. Проверка критериев готовности к запуску согласно разделу 85 ТЗ
        context["readiness_errors"] = event.check_readiness()
        context["is_ready_to_launch"] = len(context["readiness_errors"]) == 0

        # Активная вкладка
        context["active_tab"] = self.request.GET.get("tab", "overview")

        return context


class TestingEventPositionsUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Обработчик сохранения единого пула должностей и ручного распределения сотрудников по 2 группам."""

    def post(self, request, pk, *args, **kwargs):
        event = get_object_or_404(Testing, pk=pk)

        # Проверяем, пришли ли данные из нового интерактивного интерфейса распределения
        if "selected_jobs" in request.POST or "group1_employees" in request.POST or "group2_employees" in request.POST:
            selected_jobs = request.POST.getlist("selected_jobs")
            g1_employees = request.POST.getlist("group1_employees")
            g2_employees = request.POST.getlist("group2_employees")

            try:
                stats = save_group_positions_and_employee_distribution(
                    testing=event,
                    selected_job_ids=selected_jobs,
                    group1_employee_ids=g1_employees,
                    group2_employee_ids=g2_employees,
                    user=request.user
                )
                messages.success(
                    request,
                    f"Состав групп успешно сохранен! "
                    f"Группа 1 («Обеспечение ТО ВС»): {stats['g1_count']} чел., "
                    f"Группа 2 («Выполнение ТО ВС»): {stats['g2_count']} чел. "
                    f"Всего назначено: {stats['total_assigned']} сотрудников."
                )
            except ValidationError as ve:
                messages.error(request, str(ve))
            except Exception as e:
                messages.error(request, f"Ошибка при сохранении: {e}")

            return redirect(f"{reverse('testing_app:event_detail', kwargs={'pk': event.pk})}?tab=positions")

        # Резервный путь через форму GroupPositionsForm
        form = GroupPositionsForm(request.POST)
        if form.is_valid():
            g1_jobs = [j.id for j in form.cleaned_data.get("group1_positions", [])]
            g2_jobs = [j.id for j in form.cleaned_data.get("group2_positions", [])]

            try:
                stats = sync_group_positions(event, g1_jobs, g2_jobs, user=request.user)
                messages.success(
                    request,
                    f"Должности групп сохранены! Автоматически назначено: {stats['created']}, "
                    f"обновлено: {stats['updated']}, удалено: {stats['removed']}. "
                    f"Всего сотрудников: {stats['total_assigned']}."
                )
            except ValidationError as ve:
                messages.error(request, str(ve))
        else:
            for err in form.non_field_errors():
                messages.error(request, err)

        return redirect(f"{reverse('testing_app:event_detail', kwargs={'pk': event.pk})}?tab=positions")


class TestingEventCategoriesUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Обработчик сохранения процентного распределения категорий вопросов."""

    def post(self, request, pk, *args, **kwargs):
        event = get_object_or_404(Testing, pk=pk)
        category_percentages = {}

        for key, value in request.POST.items():
            if key.startswith("cat_percent_"):
                try:
                    cat_id = int(key.replace("cat_percent_", ""))
                    pct = int(value or 0)
                    category_percentages[cat_id] = pct
                except (ValueError, TypeError):
                    pass

        try:
            update_category_settings(event, category_percentages, user=request.user)
            messages.success(request, "Процентное распределение категорий вопросов успешно сохранено!")
        except ValidationError as ve:
            messages.error(request, str(ve))

        return redirect(f"{reverse('testing_app:event_detail', kwargs={'pk': event.pk})}?tab=categories")


class TestingEventManualAssignView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Обработчик ручного добавления сотрудника в группу тестирования."""

    def post(self, request, pk, *args, **kwargs):
        event = get_object_or_404(Testing, pk=pk)
        form = ManualAssignmentForm(event, request.POST)

        if form.is_valid():
            group = form.cleaned_data["group"]
            employee = form.cleaned_data["employee"]
            try:
                add_manual_assignment(event, group, employee, user=request.user)
                messages.success(request, f"Сотрудник {employee.get_full_name()} успешно добавлен в группу «{group.name}».")
            except ValidationError as ve:
                messages.error(request, str(ve))
        else:
            messages.error(request, "Пожалуйста, корректно заполните форму ручного назначения.")

        return redirect(f"{reverse('testing_app:event_detail', kwargs={'pk': event.pk})}?tab=employees")


class TestingEventRemoveAssignView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Обработчик исключения сотрудника из мероприятия тестирования."""

    def post(self, request, pk, assign_id, *args, **kwargs):
        event = get_object_or_404(Testing, pk=pk)
        assignment = get_object_or_404(TestingAssignment, pk=assign_id, testing=event)

        try:
            remove_assignment(assignment, user=request.user)
            messages.success(request, "Сотрудник успешно исключен из тестирования.")
        except ValidationError as ve:
            messages.error(request, str(ve))

        return redirect(f"{reverse('testing_app:event_detail', kwargs={'pk': event.pk})}?tab=employees")


class TestingEventStatusChangeView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Смена статуса мероприятия с проверкой 14 критериев готовности согласно разделу 85 ТЗ."""

    def post(self, request, pk, *args, **kwargs):
        event = get_object_or_404(Testing, pk=pk)
        new_status = request.POST.get("status")

        success, errors = change_testing_status(event, new_status, user=request.user)
        if success:
            messages.success(request, f"Статус мероприятия успешно изменен на «{event.get_status_display()}».")
        else:
            messages.error(request, "Не удалось изменить статус! Проверьте чек-лист готовности:")
            for err in errors:
                messages.warning(request, f"• {err}")

        return redirect("testing_app:event_detail", pk=event.pk)


# ==============================================================================
# ДВИЖОК ТЕСТИРОВАНИЯ И ПРОХОЖДЕНИЕ ТЕСТА (ЭТАП 4)
# ==============================================================================

class StartTestAttemptView(LoginRequiredMixin, View):
    """Инициация или возобновление попытки сдачи теста сотрудником."""

    def post(self, request, assignment_id, *args, **kwargs):
        assignment = get_object_or_404(
            TestingAssignment.objects.select_related("testing", "employee"),
            pk=assignment_id
        )

        # Проверка прав: тест может проходить только сам назначенный сотрудник (или суперпользователь для проверки)
        if assignment.employee != request.user and not request.user.is_superuser:
            messages.error(request, "У вас нет доступа к прохождению данного тестирования.")
            return redirect("testing_app:my_tests")

        try:
            attempt, resumed = start_or_resume_attempt(assignment, user=request.user)
            if resumed:
                messages.info(request, "Вы вернулись к незавершенной попытке тестирования.")
            else:
                messages.success(request, f"Попытка №{attempt.attempt_number} начата. Желаем удачи!")
            return redirect("testing_app:test_session", attempt_id=attempt.id)
        except ValidationError as ve:
            messages.error(request, str(ve))
            return redirect("testing_app:my_tests")


class TestSessionView(LoginRequiredMixin, View):
    """Интерфейс прохождения теста с вопросами, вариантами и серверным таймером."""

    template_name = "testing_app/test_session.html"

    def get(self, request, attempt_id, *args, **kwargs):
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related("assignment__employee", "assignment__testing"),
            pk=attempt_id
        )

        # Проверка прав доступа
        if attempt.assignment.employee != request.user and not request.user.is_superuser:
            messages.error(request, "У вас нет доступа к этой попытке тестирования.")
            return redirect("testing_app:my_tests")

        # Если попытка уже завершена — направляем на страницу результатов
        if attempt.status == TestingAttempt.Status.COMPLETED:
            return redirect("testing_app:test_result", attempt_id=attempt.id)

        # Проверка серверного таймера
        remaining_seconds = attempt.get_remaining_seconds()
        if remaining_seconds <= 0:
            finish_attempt(attempt, reason=TestingAttempt.CompletionReason.TIME_EXPIRED)
            messages.warning(request, "Время, отведенное на тестирование, истекло.")
            return redirect("testing_app:test_result", attempt_id=attempt.id)

        questions = get_attempt_questions_for_test_engine(attempt)
        answered_count = attempt.answers.filter(selected_option_id__isnull=False).count()

        context = {
            "attempt": attempt,
            "assignment": attempt.assignment,
            "testing": attempt.assignment.testing,
            "questions": questions,
            "total_questions": len(questions),
            "answered_count": answered_count,
            "remaining_seconds": max(0, remaining_seconds),
        }
        return render(request, self.template_name, context)


class SaveDraftAnswerAjaxView(LoginRequiredMixin, View):
    """AJAX-эндпоинт для автосохранения выбранного ответа в черновик."""

    def post(self, request, attempt_id, *args, **kwargs):
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related("assignment__employee"),
            pk=attempt_id
        )

        if attempt.assignment.employee != request.user and not request.user.is_superuser:
            return JsonResponse({"success": False, "error": "Доступ запрещен."}, status=403)

        try:
            data = json.loads(request.body.decode("utf-8"))
            attempt_question_id = int(data.get("attempt_question_id"))
            selected_option_id = int(data.get("selected_option_id"))
            spent_seconds = int(data.get("spent_seconds", 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({"success": False, "error": "Некорректные параметры запроса."}, status=400)

        result = save_draft_answer(
            attempt=attempt,
            attempt_question_id=attempt_question_id,
            selected_option_id=selected_option_id,
            spent_seconds=spent_seconds
        )
        return JsonResponse(result)


class FinishTestAttemptView(LoginRequiredMixin, View):
    """Завершение тестирования сотрудником по кнопке 'Завершить тестирование'."""

    def post(self, request, attempt_id, *args, **kwargs):
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related("assignment__employee"),
            pk=attempt_id
        )

        if attempt.assignment.employee != request.user and not request.user.is_superuser:
            messages.error(request, "Доступ запрещен.")
            return redirect("testing_app:my_tests")

        if attempt.status == TestingAttempt.Status.IN_PROGRESS:
            finish_attempt(attempt, reason=TestingAttempt.CompletionReason.USER_COMPLETED)
            messages.success(request, "Тестирование успешно завершено! Ознакомьтесь с результатами.")

        return redirect("testing_app:test_result", attempt_id=attempt.id)


class TestAttemptResultView(LoginRequiredMixin, View):
    """Страница с детальными результатами сдачи теста."""

    template_name = "testing_app/test_result.html"

    def get(self, request, attempt_id, *args, **kwargs):
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related("assignment__employee", "assignment__testing"),
            pk=attempt_id
        )

        is_owner = (attempt.assignment.employee == request.user)
        is_manager = is_testing_manager_user(request.user)

        if not is_owner and not is_manager:
            messages.error(request, "У вас нет прав для просмотра этого протокола тестирования.")
            return redirect("testing_app:my_tests")

        context = get_attempt_results_detail(attempt)
        return render(request, self.template_name, context)


# ==============================================================================
# УВЕДОМЛЕНИЯ О РЕЗУЛЬТАТАХ И ПРОВЕРКА ПОДЛИННОСТИ (ЭТАП 5)
# ==============================================================================

class CertificateView(LoginRequiredMixin, View):
    """Отображение и печать бланка уведомления о прохождении проверки знаний."""

    template_name = "testing_app/certificate.html"

    def get(self, request, attempt_id, *args, **kwargs):
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related("assignment__employee", "assignment__testing", "assignment__group"),
            pk=attempt_id
        )

        if not attempt.is_passed:
            messages.error(request, "Уведомление формируется только при успешной сдаче тестирования.")
            return redirect("testing_app:test_result", attempt_id=attempt.id)

        is_owner = (attempt.assignment.employee == request.user)
        is_manager = is_testing_manager_user(request.user)

        if not is_owner and not is_manager:
            messages.error(request, "У вас нет прав для доступа к этому уведомлению.")
            return redirect("testing_app:my_tests")

        context = get_certificate_context(attempt, request=request)
        return render(request, self.template_name, context)


class AttemptTestSheetView(LoginRequiredMixin, View):
    """Отображение и печать официального экзаменационного листа (протокола) тестирования.

    Формирует структурированный печатный документ со всеми вопросами, вариантами,
    выбранными ответами сотрудника, затраченным временем и подписями для передачи в архив ИАС.
    """

    template_name = "testing_app/test_sheet.html"

    def get(self, request, attempt_id, *args, **kwargs):
        """Обрабатывает GET-запрос на просмотр и печать экзаменационного листа.

        Args:
            request (HttpRequest): Объект входящего HTTP-запроса.
            attempt_id (int): Идентификатор попытки тестирования.

        Returns:
            HttpResponse: Отрендеренная страница экзаменационного листа.
        """
        attempt = get_object_or_404(
            TestingAttempt.objects.select_related(
                "assignment__employee",
                "assignment__testing",
                "assignment__group"
            ),
            pk=attempt_id
        )

        is_owner = (attempt.assignment.employee == request.user)
        is_manager = is_testing_manager_user(request.user)

        if not is_owner and not is_manager:
            messages.error(request, "У вас нет прав для доступа к этому экзаменационному листу.")
            return redirect("testing_app:my_tests")

        context = get_attempt_results_detail(attempt)
        employee = attempt.assignment.employee
        context["employee_full_name"] = get_user_full_name_with_patronymic(employee)
        context["job_title"] = attempt.assignment.assigned_job_title
        context["division_title"] = attempt.assignment.assigned_division_title
        context["group_name"] = attempt.assignment.group.name
        context["company_name"] = "ООО Авиакомпания «БАРКОЛ»"

        # Форматирование времени прохождения
        duration_sec = attempt.duration_seconds or 0
        mins = duration_sec // 60
        secs = duration_sec % 60
        context["duration_formatted"] = f"{mins} мин. {secs:02d} сек." if mins > 0 else f"{secs} сек."

        return render(request, self.template_name, context)


class CertificateVerifyView(LoginRequiredMixin, View):
    """Закрытая страница проверки подлинности уведомления по QR-коду (строго с авторизацией)."""

    template_name = "testing_app/certificate_verify.html"

    def get(self, request, certificate_uuid, *args, **kwargs):
        cert_data = verify_certificate_by_uuid(str(certificate_uuid))

        # Запись в аудит факта проверки подлинности уведомления
        TestingAuditLog.objects.create(
            user=request.user,
            action="certificate_verify",
            object_repr=f"Проверка уведомления UUID {certificate_uuid}",
            details={
                "is_found": cert_data is not None,
                "viewer": request.user.get_full_name(),
                "ip": request.META.get("REMOTE_ADDR")
            }
        )

        return render(request, self.template_name, {
            "cert_data": cert_data,
            "searched_uuid": certificate_uuid
        })


# ==============================================================================
# ОНЛАЙН-МОНИТОРИНГ И ЭКСПОРТ ПРОТОКОЛОВ (ЭТАП 6)
# ==============================================================================

class LiveMonitoringAjaxView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """AJAX-эндпоинт для динамического обновления списка онлайн-сессий на дашборде."""

    def get(self, request, *args, **kwargs):
        event_id_raw = request.GET.get("event_id")
        event_id = None
        if event_id_raw:
            try:
                event_id = int(event_id_raw)
            except (ValueError, TypeError):
                pass

        sessions = get_live_active_sessions(event_id)
        return JsonResponse({"sessions": sessions, "count": len(sessions)})


class TestingProtocolExcelExportView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Выгрузка официального протокола проверки знаний в формате Microsoft Excel (.xlsx)."""

    def get(self, request, pk, *args, **kwargs):
        testing = get_object_or_404(Testing, pk=pk)
        wb = generate_testing_protocol_excel(testing)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        safe_num = str(testing.order_number).replace("/", "_").replace("\\", "_")
        filename = f"Протокол_проверки_знаний_Приказ_{safe_num}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'
        wb.save(response)

        TestingAuditLog.objects.create(
            user=request.user,
            action="export_protocol_excel",
            object_repr=f"Выгрузка протокола Excel: {testing.title}",
            details={"order_number": testing.order_number}
        )

        return response


class TestingProtocolCsvExportView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Выгрузка протокола проверки знаний в текстовом формате CSV (UTF-8-sig)."""

    def get(self, request, pk, *args, **kwargs):
        testing = get_object_or_404(Testing, pk=pk)
        csv_content = generate_testing_protocol_csv(testing)

        response = HttpResponse(
            csv_content.encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8-sig"
        )
        safe_num = str(testing.order_number).replace("/", "_").replace("\\", "_")
        filename = f"Протокол_проверки_знаний_Приказ_{safe_num}.csv"
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'

        TestingAuditLog.objects.create(
            user=request.user,
            action="export_protocol_csv",
            object_repr=f"Выгрузка протокола CSV: {testing.title}",
            details={"order_number": testing.order_number}
        )

        return response


# ==============================================================================
# ЛЕКЦИОННЫЙ МАТЕРИАЛ (ЭТАП 7)
# ==============================================================================

class LectureListView(LoginRequiredMixin, ListView):
    """Список лекционных материалов для теоретической подготовки сотрудников.

    Обычным сотрудникам отображаются только актуальные материалы,
    ответственным за тестирование — все с возможностью управления и добавления.
    """

    model = LectureMaterial
    template_name = "testing_app/lecture_list.html"
    context_object_name = "lectures"
    paginate_by = 12

    def get_queryset(self):
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        qs = LectureMaterial.objects.all().select_related("created_by")

        if not is_manager:
            qs = qs.filter(is_actual=True)
        else:
            status_filter = self.request.GET.get("status")
            if status_filter == "actual":
                qs = qs.filter(is_actual=True)
            elif status_filter == "archived":
                qs = qs.filter(is_actual=False)

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager"] = is_testing_manager_user(user)
        context["active_tab"] = "lectures"
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class LectureDetailView(LoginRequiredMixin, DetailView):
    """Просмотр лекционного материала со встроенным отображением скана (PDF).

    При открытии лекции фиксируется обращение сотрудника в журнале MaterialViewLog.
    """

    model = LectureMaterial
    template_name = "testing_app/lecture_detail.html"
    context_object_name = "lecture"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        if not obj.is_actual and not is_manager:
            raise Http404("Лекционный материал перенесен в архив или недоступен.")
        return obj

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Фиксируем обращение сотрудника к лекционному материалу
        ip_addr = get_client_ip(request)
        dev_info = get_device_info(request)
        log_material_access(request.user, self.object, ip_addr, dev_info.get("device_type"))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        context["is_manager"] = is_manager
        context["active_tab"] = "lectures"
        if is_manager:
            context["recent_views"] = (
                self.object.view_logs.select_related("user")
                .prefetch_related("user__user_work_profile__job", "user__user_work_profile__divisions")
                .order_by("-last_viewed_at")[:10]
            )
        return context


class LectureCreateView(LoginRequiredMixin, TestingManagerRequiredMixin, CreateView):
    """Создание нового лекционного материала ответственным за тестирование."""

    model = LectureMaterial
    form_class = LectureMaterialForm
    template_name = "testing_app/lecture_form.html"
    success_url = reverse_lazy("testing_app:lecture_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Лекционный материал «{self.object.title}» успешно добавлен.")
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="create_lecture",
            object_repr=f"Создание лекции: {self.object.title}",
            details={"lecture_id": self.object.id}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "lectures"
        context["page_title"] = "Добавление лекционного материала"
        return context


class LectureUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, UpdateView):
    """Редактирование лекционного материала ответственным за тестирование."""

    model = LectureMaterial
    form_class = LectureMaterialForm
    template_name = "testing_app/lecture_form.html"
    success_url = reverse_lazy("testing_app:lecture_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Лекционный материал «{self.object.title}» успешно обновлен.")
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="update_lecture",
            object_repr=f"Обновление лекции: {self.object.title}",
            details={"lecture_id": self.object.id}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "lectures"
        context["page_title"] = f"Редактирование: {self.object.title}"
        return context


class LectureDeleteView(LoginRequiredMixin, TestingManagerRequiredMixin, DeleteView):
    """Удаление лекционного материала ответственным за тестирование."""

    model = LectureMaterial
    template_name = "testing_app/lecture_confirm_delete.html"
    success_url = reverse_lazy("testing_app:lecture_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        title = obj.title
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Лекционный материал «{title}» успешно удален.")
        TestingAuditLog.objects.create(
            user=request.user,
            action="delete_lecture",
            object_repr=f"Удаление лекции: {title}",
            details={"title": title}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "lectures"
        return context


# ==============================================================================
# ВИДЕО ЛЕКЦИИ (ЭТАП 7)
# ==============================================================================

class VideoLectureListView(LoginRequiredMixin, ListView):
    """Список видеолекций для дистанционного обучения сотрудников.

    Обычным сотрудникам доступны только актуальные видеоматериалы.
    """

    model = VideoLecture
    template_name = "testing_app/video_lecture_list.html"
    context_object_name = "videos"
    paginate_by = 12

    def get_queryset(self):
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        qs = VideoLecture.objects.all().select_related("created_by")

        if not is_manager:
            qs = qs.filter(is_actual=True)
        else:
            status_filter = self.request.GET.get("status")
            if status_filter == "actual":
                qs = qs.filter(is_actual=True)
            elif status_filter == "archived":
                qs = qs.filter(is_actual=False)

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager"] = is_testing_manager_user(user)
        context["active_tab"] = "videos"
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class VideoLectureDetailView(LoginRequiredMixin, DetailView):
    """Просмотр видеолекции с встроенным HTML5 видеоплеером.

    При открытии страницы видеолекции фиксируется факт обращения сотрудника в журнале.
    """

    model = VideoLecture
    template_name = "testing_app/video_lecture_detail.html"
    context_object_name = "video"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        if not obj.is_actual and not is_manager:
            raise Http404("Видеолекция перенесена в архив или недоступна.")
        return obj

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Фиксируем обращение к видеолекции
        ip_addr = get_client_ip(request)
        dev_info = get_device_info(request)
        log_material_access(request.user, self.object, ip_addr, dev_info.get("device_type"))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_manager = is_testing_manager_user(user)
        context["is_manager"] = is_manager
        context["active_tab"] = "videos"
        if is_manager:
            context["recent_views"] = (
                self.object.view_logs.select_related("user")
                .prefetch_related("user__user_work_profile__job", "user__user_work_profile__divisions")
                .order_by("-last_viewed_at")[:10]
            )
        return context


class VideoLectureCreateView(LoginRequiredMixin, TestingManagerRequiredMixin, CreateView):
    """Создание новой видеолекции ответственным за тестирование."""

    model = VideoLecture
    form_class = VideoLectureForm
    template_name = "testing_app/video_lecture_form.html"
    success_url = reverse_lazy("testing_app:video_lecture_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Видеолекция «{self.object.title}» успешно добавлена.")
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="create_video_lecture",
            object_repr=f"Создание видеолекции: {self.object.title}",
            details={"video_id": self.object.id}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "videos"
        context["page_title"] = "Добавление видеолекции"
        return context


class VideoLectureUpdateView(LoginRequiredMixin, TestingManagerRequiredMixin, UpdateView):
    """Редактирование параметров видеолекции ответственным за тестирование."""

    model = VideoLecture
    form_class = VideoLectureForm
    template_name = "testing_app/video_lecture_form.html"
    success_url = reverse_lazy("testing_app:video_lecture_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Видеолекция «{self.object.title}» успешно обновлена.")
        TestingAuditLog.objects.create(
            user=self.request.user,
            action="update_video_lecture",
            object_repr=f"Обновление видеолекции: {self.object.title}",
            details={"video_id": self.object.id}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "videos"
        context["page_title"] = f"Редактирование видеолекции: {self.object.title}"
        return context


class VideoLectureDeleteView(LoginRequiredMixin, TestingManagerRequiredMixin, DeleteView):
    """Удаление видеолекции ответственным за тестирование."""

    model = VideoLecture
    template_name = "testing_app/video_lecture_confirm_delete.html"
    success_url = reverse_lazy("testing_app:video_lecture_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        title = obj.title
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Видеолекция «{title}» успешно удалена.")
        TestingAuditLog.objects.create(
            user=request.user,
            action="delete_video_lecture",
            object_repr=f"Удаление видеолекции: {title}",
            details={"title": title}
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "videos"
        return context


# ==============================================================================
# ОТЧЕТ ОБ ОБРАЩЕНИЯХ К МАТЕРИАЛАМ (ЭТАП 7)
# ==============================================================================

class MaterialAccessReportView(LoginRequiredMixin, TestingManagerRequiredMixin, ListView):
    """Сводный отчет по обращениям сотрудников к лекционному и видеоматериалу."""

    template_name = "testing_app/material_access_report.html"
    context_object_name = "logs"
    paginate_by = 25

    def get_queryset(self):
        return get_material_access_report_qs(
            material_type=self.request.GET.get("material_type"),
            material_id=self.request.GET.get("material_id"),
            search_query=self.request.GET.get("q"),
            division_id=self.request.GET.get("division_id"),
            date_from=self.request.GET.get("date_from"),
            date_to=self.request.GET.get("date_to"),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "material_report"
        context["is_manager"] = True

        # Справочники для фильтров
        context["divisions"] = Division.objects.all().order_by("name")
        context["lectures_list"] = LectureMaterial.objects.all().order_by("title")
        context["videos_list"] = VideoLecture.objects.all().order_by("title")

        # Текущие фильтры
        context["filter_material_type"] = self.request.GET.get("material_type", "")
        context["filter_material_id"] = self.request.GET.get("material_id", "")
        context["filter_q"] = self.request.GET.get("q", "")
        context["filter_division_id"] = self.request.GET.get("division_id", "")
        context["filter_date_from"] = self.request.GET.get("date_from", "")
        context["filter_date_to"] = self.request.GET.get("date_to", "")

        # Общие KPI отчета
        stats = get_material_dashboard_stats()
        context["materials_stats"] = stats
        return context


class MaterialAccessReportExcelExportView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Выгрузка отчета об обращениях к материалам в формате Microsoft Excel (.xlsx)."""

    def get(self, request, *args, **kwargs):
        qs = get_material_access_report_qs(
            material_type=request.GET.get("material_type"),
            material_id=request.GET.get("material_id"),
            search_query=request.GET.get("q"),
            division_id=request.GET.get("division_id"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
        )
        wb = export_material_report_excel(qs)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        date_str = timezone.now().strftime("%Y-%m-%d")
        filename = f"Отчет_обращений_к_материалам_{date_str}.xlsx"

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'

        TestingAuditLog.objects.create(
            user=request.user,
            action="export_materials_excel",
            object_repr="Выгрузка отчета по материалам Excel",
            details={"rows_count": qs.count()}
        )
        return response


class MaterialAccessReportCsvExportView(LoginRequiredMixin, TestingManagerRequiredMixin, View):
    """Выгрузка отчета об обращениях к материалам в текстовом формате CSV (UTF-8)."""

    def get(self, request, *args, **kwargs):
        qs = get_material_access_report_qs(
            material_type=request.GET.get("material_type"),
            material_id=request.GET.get("material_id"),
            search_query=request.GET.get("q"),
            division_id=request.GET.get("division_id"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
        )
        csv_content = export_material_report_csv(qs)

        date_str = timezone.now().strftime("%Y-%m-%d")
        filename = f"Отчет_обращений_к_материалам_{date_str}.csv"

        response = HttpResponse(
            csv_content.encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8-sig"
        )
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'

        TestingAuditLog.objects.create(
            user=request.user,
            action="export_materials_csv",
            object_repr="Выгрузка отчета по материалам CSV",
            details={"rows_count": qs.count()}
        )
        return response





