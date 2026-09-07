"""Контроллеры и веб-представления для подсистемы задач и поручений (tasks_app).

Модуль реализует:
- Календарное представление FullCalendar v6 (TaskListView);
- Создание, редактирование, детальный просмотр и удаление задач;
- Интерактивный Workflow: принятие в работу, отправка на проверку, возврат, приемка (с/без ЭЦП);
- AJAX/HTMX-эндпоинты для подзадач (чек-листа), комментариев, файлов и делегирования;
- Почтовую рассылку уведомлений участникам поручения.
"""

import datetime
import io
import json
import logging
import os
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from administration_app.utils import get_task_title_with_icon, send_notification
from customers_app.models import DataBaseUser, Division
from tasks_app.forms import SubTaskForm, TaskCommentForm, TaskDelegationForm, TaskForm
from tasks_app.models import (
    Category,
    SubTask,
    Task,
    TaskAssignment,
    TaskComment,
    TaskFile,
    TaskHistory,
    TaskRole,
    TaskStatus,
)
from tasks_app.permissions import (
    can_accept_task,
    can_delegate_task,
    can_delete_task,
    can_edit_task,
    can_return_task,
    can_start_task,
    can_submit_for_review,
    can_toggle_subtask,
    can_view_task,
)
from tasks_app.services import (
    CommentService,
    NotificationService,
    ReportService,
    SubTaskService,
    TaskService,
)
from tasks_app.tasks import notify_task_participants_batch_task, send_task_notification_task

logger = logging.getLogger(__name__)

# Константы для валидации файлов
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc',
    '.docx', '.txt', '.xls', '.xlsx', '.zip', '.rar', '.7z'
]


@login_required
@require_POST
def create_task_ajax(request: HttpRequest) -> JsonResponse:
    """Быстрое создание задачи при перетаскивании или клике в календаре.

    Args:
        request (HttpRequest): Объект HTTP-запроса с параметрами POST.

    Returns:
        JsonResponse: JSON с параметрами созданного события или ошибкой.
    """
    title = request.POST.get('title')
    if not title:
        return JsonResponse({'error': 'Название задачи обязательно'}, status=400)

    start_date = parse_datetime(request.POST.get('start_date', ''))
    end_date = parse_datetime(request.POST.get('end_date', ''))

    current_tz = timezone.get_current_timezone()
    if start_date and timezone.is_naive(start_date):
        start_date = timezone.make_aware(start_date, current_tz)
    if end_date and timezone.is_naive(end_date):
        end_date = timezone.make_aware(end_date, current_tz)

    if start_date and end_date and end_date < start_date:
        return JsonResponse({'error': 'Дата завершения не может быть раньше даты начала'}, status=400)

    shared_ids = request.POST.getlist('shared_with[]')
    shared_users = DataBaseUser.objects.filter(id__in=shared_ids, is_active=True)

    task = Task.objects.create(
        user=request.user,
        responsible=request.user,
        title=title.strip(),
        start_date=start_date,
        end_date=end_date,
        priority=request.POST.get('priority', 'primary'),
        repeat=request.POST.get('freq', 'none'),
        status=TaskStatus.NEW
    )

    if shared_users.exists():
        task.shared_with.set(shared_users)
        task.assignees.set(shared_users)

    TaskHistory.log(
        task=task,
        user=request.user,
        action=TaskHistory.ActionType.CREATED,
        comment="Создана быстрая задача из календаря"
    )

    return JsonResponse({
        'id': task.id,
        'title': task.title,
        'start_date': task.start_date.isoformat() if task.start_date else None,
        'end_date': task.end_date.isoformat() if task.end_date else None,
        'url': task.get_absolute_url(),
        'color': task.priority,
        'status': task.status,
    })


@login_required
@require_POST
def upload_files_ajax(request: HttpRequest) -> JsonResponse:
    """Асинхронная загрузка вложений к задаче с валидацией размера и типа.

    Args:
        request (HttpRequest): Запрос с task_id и файлами в request.FILES.

    Returns:
        JsonResponse: Список загруженных файлов и возможные ошибки валидации.
    """
    task_id = request.POST.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'task_id обязателен'}, status=400)

    task = get_object_or_404(Task, pk=task_id)
    if not can_view_task(request.user, task):
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    files = request.FILES.getlist('files')
    if len(files) > 10:
        return JsonResponse({'error': 'Максимум 10 файлов за один раз'}, status=400)

    uploaded_files = []
    errors = []

    for file in files:
        if file.size > MAX_FILE_SIZE:
            errors.append(f'Файл "{file.name}" превышает 20MB')
            continue

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f'Неподдерживаемый тип файла: {file.name}')
            continue

        task_file = TaskFile.objects.create(
            task=task,
            uploaded_by=request.user,
            file=file,
            original_filename=file.name,
            file_size=file.size
        )
        uploaded_files.append({
            'id': task_file.id,
            'name': task_file.original_filename,
            'url': task_file.file.url,
            'size': task_file.file_size
        })

        TaskHistory.log(
            task=task,
            user=request.user,
            action=TaskHistory.ActionType.FILE_ADDED,
            new_value=task_file.original_filename,
            comment=f"Загружен файл {task_file.original_filename}"
        )

    if errors:
        return JsonResponse({'files': uploaded_files, 'errors': errors}, status=207)

    return JsonResponse({'files': uploaded_files})


@login_required
@require_POST
def delete_file_ajax(request: HttpRequest) -> JsonResponse:
    """Удаляет файл из задачи с диска и базы данных.

    Args:
        request (HttpRequest): Запрос с параметром file_id.

    Returns:
        JsonResponse: Статус операции.
    """
    file_id = request.POST.get('file_id')
    if not file_id:
        return JsonResponse({'error': 'file_id обязателен'}, status=400)

    task_file = get_object_or_404(TaskFile, pk=file_id)
    task = task_file.task

    if not can_edit_task(request.user, task) and task_file.uploaded_by_id != request.user.id:
        return JsonResponse({'error': 'Нет прав на удаление этого файла'}, status=403)

    filename = task_file.original_filename or task_file.file.name
    task_file.delete()

    TaskHistory.log(
        task=task,
        user=request.user,
        action=TaskHistory.ActionType.FILE_DELETED,
        old_value=filename,
        comment=f"Удален файл {filename}"
    )

    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def subtask_toggle_ajax(request: HttpRequest) -> JsonResponse:
    """Переключает статус выполнения подзадачи через AJAX/HTMX.

    Args:
        request (HttpRequest): Запрос с subtask_id.

    Returns:
        JsonResponse: Обновленное состояние подзадачи и общий прогресс.
    """
    subtask_id = request.POST.get('subtask_id')
    if not subtask_id:
        return JsonResponse({'error': 'subtask_id обязателен'}, status=400)

    subtask = get_object_or_404(SubTask, pk=subtask_id)
    try:
        updated_subtask = SubTaskService.toggle_subtask(subtask, request.user)
    except PermissionDenied as err:
        return JsonResponse({'error': str(err)}, status=403)

    return JsonResponse({
        'status': 'ok',
        'subtask_id': updated_subtask.id,
        'is_completed': updated_subtask.is_completed,
        'progress_percent': updated_subtask.task.progress_percent,
        'completed_by': updated_subtask.completed_by.get_full_name() if updated_subtask.completed_by else ''
    })


@login_required
@require_POST
def subtask_add_ajax(request: HttpRequest) -> JsonResponse:
    """Добавляет новый пункт чек-листа к задаче.

    Args:
        request (HttpRequest): Запрос с task_id, title и опциональным assigned_to_id.

    Returns:
        JsonResponse: Данные созданной подзадачи и обновленный прогресс.
    """
    task_id = request.POST.get('task_id')
    title = request.POST.get('title', '').strip()
    if not task_id or not title:
        return JsonResponse({'error': 'task_id и текст подзадачи обязательны'}, status=400)

    task = get_object_or_404(Task, pk=task_id)
    assigned_to_id = request.POST.get('assigned_to_id')
    assigned_to = DataBaseUser.objects.filter(id=assigned_to_id).first() if assigned_to_id else None

    try:
        subtask = SubTaskService.create_subtask(task, request.user, title, assigned_to=assigned_to)
    except PermissionDenied as err:
        return JsonResponse({'error': str(err)}, status=403)

    return JsonResponse({
        'status': 'ok',
        'subtask': {
            'id': subtask.id,
            'title': subtask.title,
            'is_completed': subtask.is_completed,
            'assigned_to': subtask.assigned_to.get_full_name() if subtask.assigned_to else ''
        },
        'progress_percent': task.progress_percent
    })


@login_required
@require_POST
def subtask_delete_ajax(request: HttpRequest) -> JsonResponse:
    """Удаляет подзадачу из чек-листа.

    Args:
        request (HttpRequest): Запрос с subtask_id.

    Returns:
        JsonResponse: Статус операции и обновленный процент прогресса.
    """
    subtask_id = request.POST.get('subtask_id')
    if not subtask_id:
        return JsonResponse({'error': 'subtask_id обязателен'}, status=400)

    subtask = get_object_or_404(SubTask, pk=subtask_id)
    task = subtask.task
    try:
        SubTaskService.delete_subtask(subtask, request.user)
    except PermissionDenied as err:
        return JsonResponse({'error': str(err)}, status=403)

    return JsonResponse({
        'status': 'ok',
        'progress_percent': task.progress_percent
    })


@login_required
@require_POST
def comment_add_ajax(request: HttpRequest) -> JsonResponse:
    """Добавляет комментарий к задаче.

    Args:
        request (HttpRequest): Запрос с task_id, text и опциональным parent_id.

    Returns:
        JsonResponse: Данные созданного комментария.
    """
    task_id = request.POST.get('task_id')
    text = request.POST.get('text', '').strip()
    parent_id = request.POST.get('parent_id')

    if not task_id or not text:
        return JsonResponse({'error': 'task_id и текст комментария обязательны'}, status=400)

    task = get_object_or_404(Task, pk=task_id)
    parent = TaskComment.objects.filter(id=parent_id, task=task).first() if parent_id else None

    try:
        comment = CommentService.add_comment(task, request.user, text, parent=parent)
    except (PermissionDenied, ValueError) as err:
        return JsonResponse({'error': str(err)}, status=400)

    return JsonResponse({
        'status': 'ok',
        'comment': {
            'id': comment.id,
            'author': comment.author.get_full_name() or comment.author.username,
            'text': comment.text,
            'created_at': comment.created_at.strftime('%d.%m.%Y %H:%M'),
            'parent_id': comment.parent_id
        }
    })


@login_required
@require_POST
def task_status_action_ajax(request: HttpRequest, pk: int) -> JsonResponse:
    """Обрабатывает смену статуса задачи (Workflow) через AJAX.

    Поддерживаемые действия:
    - start: Принять в работу (IN_PROGRESS);
    - submit_review: Отправить на проверку (ON_REVIEW);
    - accept: Окончательно принять (COMPLETED) с опциональной ЭЦП;
    - return: Вернуть на доработку (RETURNED);
    - cancel: Отменить задачу (CANCELLED).

    Args:
        request (HttpRequest): Запрос с action, reason, comment, eds_signature.
        pk (int): Первичный ключ задачи.

    Returns:
        JsonResponse: Результат операции со статусом задачи.
    """
    task = get_object_or_404(Task, pk=pk)
    action = request.POST.get('action')
    comment = request.POST.get('comment', '').strip()
    reason = request.POST.get('reason', '').strip()
    eds_signature = request.POST.get('eds_signature', '').strip() or None
    bypass_eds = request.POST.get('bypass_eds') in ['true', '1', True, 'yes']

    try:
        if action == 'start':
            task = TaskService.start_task(task, request.user)
        elif action == 'submit_review':
            task = TaskService.submit_for_review(task, request.user, comment=comment)
        elif action == 'accept':
            task = TaskService.accept_task(
                task, request.user, eds_signature=eds_signature, comment=comment, bypass_eds=bypass_eds
            )
        elif action == 'return':
            task = TaskService.return_task(task, request.user, reason=reason)
        elif action == 'cancel':
            task = TaskService.cancel_task(task, request.user, reason=reason)
        else:
            return JsonResponse({'error': f'Неизвестное действие: {action}'}, status=400)
    except (PermissionDenied, ValidationError) as err:
        return JsonResponse({'error': str(err)}, status=400)

    return JsonResponse({
        'status': 'ok',
        'task_status': task.status,
        'status_display': task.get_status_display(),
        'completed': task.completed,
        'progress_percent': task.progress_percent,
        'message': f'Статус задачи успешно обновлен: {task.get_status_display()}'
    })


class TaskListView(LoginRequiredMixin, ListView):
    """Представление списка задач и интерактивного календаря FullCalendar v6."""

    model = Task
    context_object_name = 'tasks'
    template_name = 'tasks_app/task_list.html'

    def get_queryset(self) -> QuerySet:
        """Формирует QuerySet задач с учетом прав доступа и фильтров.

        Returns:
            QuerySet: Задачи, доступные текущему пользователю.
        """
        user = self.request.user
        base_qs = Task.objects.filter(
            Q(user=user) |
            Q(responsible=user) |
            Q(assignees=user) |
            Q(observers=user) |
            Q(shared_with=user)
        ).distinct()

        category = self.request.GET.get('category')
        priority = self.request.GET.get('priority')
        status_filter = self.request.GET.get('status')
        division_id = self.request.GET.get('division')
        tab = self.request.GET.get('tab', 'all')

        if category:
            base_qs = base_qs.filter(category__name=category)
        if priority:
            base_qs = base_qs.filter(priority=priority)
        if status_filter:
            base_qs = base_qs.filter(status=status_filter)
        if division_id and division_id.isdigit():
            base_qs = base_qs.filter(
                Q(user__user_work_profile__divisions_id=int(division_id)) |
                Q(responsible__user_work_profile__divisions_id=int(division_id)) |
                Q(assignees__user_work_profile__divisions_id=int(division_id))
            ).distinct()

        if tab == 'my':
            base_qs = base_qs.filter(user=user)
        elif tab == 'assigned':
            base_qs = base_qs.filter(Q(responsible=user) | Q(assignees=user))
        elif tab == 'review':
            base_qs = base_qs.filter(user=user, status=TaskStatus.ON_REVIEW)
        elif tab == 'overdue':
            base_qs = base_qs.filter(end_date__lt=timezone.now()).exclude(status=TaskStatus.COMPLETED)

        return base_qs.select_related('user', 'responsible', 'category').prefetch_related('files', 'subtasks')

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Дополняет контекст данными календаря, счетчиками и фильтрами.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Статистика задач
        all_user_tasks = Task.objects.filter(
            Q(user=user) | Q(responsible=user) | Q(assignees=user) | Q(observers=user) | Q(shared_with=user)
        ).distinct()

        context['total_count'] = all_user_tasks.count()
        context['my_created_count'] = all_user_tasks.filter(user=user).count()
        context['assigned_count'] = all_user_tasks.filter(Q(responsible=user) | Q(assignees=user)).count()
        context['on_review_count'] = all_user_tasks.filter(user=user, status=TaskStatus.ON_REVIEW).count()
        context['overdue_count'] = all_user_tasks.filter(
            end_date__lt=timezone.now()
        ).exclude(status=TaskStatus.COMPLETED).count()

        context['categories'] = Category.objects.all()
        context['priorities'] = Task.PRIORITY_CHOICES
        context['statuses'] = TaskStatus.choices
        context['divisions'] = Division.objects.all().order_by('name')
        context['selected_division'] = self.request.GET.get('division', '')
        context['users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name').exclude(is_superuser=True)

        calendar_events = []
        for task in context['tasks']:
            if not task.start_date:
                continue

            event_data = {
                'id': str(task.id),
                'title': get_task_title_with_icon(self, task),
                'url': reverse('tasks_app:task-detail', args=[task.pk]),
                'color': task.priority,
                'className': f'fc-event-{task.priority} status-{task.status}',
            }

            if task.end_date:
                event_data['end'] = task.end_date.isoformat()

            if task.repeat != 'none':
                freq_map = {
                    'daily': 'daily',
                    'weekly': 'weekly',
                    'monthly': 'monthly',
                    'yearly': 'yearly',
                }
                freq = freq_map.get(task.repeat, 'daily')
                rrule_obj = {
                    'freq': freq,
                    'dtstart': task.start_date.isoformat(),
                    'interval': task.repeat_interval or 1,
                }
                if task.repeat_days and task.repeat_days not in ('', '[]', 'null', 'None'):
                    try:
                        days_map = ['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su']
                        if task.repeat_days.startswith('['):
                            days_list = json.loads(task.repeat_days)
                            byweekday = [days_map[int(d)] for d in days_list if d is not None]
                        else:
                            byweekday = [
                                days_map[int(day.strip())] for day in task.repeat_days.split(',') if day.strip()
                            ]
                        if byweekday:
                            rrule_obj['byweekday'] = byweekday
                    except Exception:
                        pass

                if task.repeat_end_date:
                    rrule_obj['until'] = task.repeat_end_date.isoformat()

                event_data['rrule'] = rrule_obj
            else:
                event_data['start'] = task.start_date.isoformat()
                if task.end_date:
                    event_data['end'] = task.end_date.isoformat()

            calendar_events.append(event_data)

        context['repeat_tasks'] = calendar_events
        return context


class TaskCreateView(LoginRequiredMixin, CreateView):
    """Представление создания новой задачи / поручения."""

    model = Task
    form_class = TaskForm
    template_name = 'tasks_app/task_form.html'
    success_url = reverse_lazy('tasks_app:task-list')

    def form_valid(self, form: TaskForm) -> HttpResponse:
        """Сохраняет новую задачу, выставляет автора и прикрепляет файлы.

        Args:
            form (TaskForm): Валидированная форма задачи.

        Returns:
            HttpResponse: Редирект на список задач.
        """
        form.instance.user = self.request.user
        if not form.instance.responsible_id:
            form.instance.responsible = self.request.user

        repeat_days = form.cleaned_data.get('repeat_days')
        if repeat_days:
            if isinstance(repeat_days, list):
                form.instance.repeat_days = ','.join(str(day) for day in repeat_days if day is not None)
            else:
                form.instance.repeat_days = str(repeat_days)
        else:
            form.instance.repeat_days = None

        response = super().form_valid(form)

        # Логируем создание в аудит
        TaskHistory.log(
            task=form.instance,
            user=self.request.user,
            action=TaskHistory.ActionType.CREATED,
            comment="Задача создана"
        )

        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(
                task=form.instance,
                uploaded_by=self.request.user,
                file=file,
                original_filename=file.name,
                file_size=file.size
            )

        messages.success(self.request, f"Поручение «{form.instance.title}» успешно создано.")
        return response


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    """Представление редактирования параметров задачи (только для автора)."""

    model = Task
    form_class = TaskForm
    template_name = 'tasks_app/task_form.html'
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self) -> QuerySet:
        return Task.objects.filter(user=self.request.user)

    def get_object(self, queryset: QuerySet = None) -> Task:
        obj = super().get_object(queryset)
        if not can_edit_task(self.request.user, obj):
            raise PermissionDenied("Вы не можете редактировать чужие задачи.")
        return obj

    def form_valid(self, form: TaskForm) -> HttpResponse:
        task = form.save(commit=False)

        repeat_days = form.cleaned_data.get('repeat_days')
        if repeat_days:
            if isinstance(repeat_days, list):
                task.repeat_days = ','.join(str(day) for day in repeat_days if day is not None)
            else:
                task.repeat_days = str(repeat_days)
        else:
            task.repeat_days = None

        task.save()
        form.save_m2m()

        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(
                task=task,
                uploaded_by=self.request.user,
                file=file,
                original_filename=file.name,
                file_size=file.size
            )

        TaskHistory.log(
            task=task,
            user=self.request.user,
            action=TaskHistory.ActionType.STATUS_CHANGED,
            comment="Параметры задачи обновлены"
        )

        messages.success(self.request, f"Задача «{task.title}» успешно обновлена.")
        return super().form_valid(form)


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    """Представление удаления задачи (только для автора)."""

    model = Task
    template_name = 'tasks_app/task_confirm_delete.html'
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self) -> QuerySet:
        return Task.objects.filter(user=self.request.user)


class TaskDetailView(LoginRequiredMixin, DetailView):
    """Детальная карточка задачи / поручения.

    Отображает параметры, чек-лист подзадач, ленту комментариев,
    журнал аудита действий, вложения и панель Workflow управления статусом.
    """

    model = Task
    context_object_name = 'task'
    template_name = 'tasks_app/task_detail.html'

    def get_queryset(self) -> QuerySet:
        user = self.request.user
        return Task.objects.filter(
            Q(user=user) | Q(responsible=user) | Q(assignees=user) | Q(observers=user) | Q(shared_with=user)
        ).distinct().select_related('user', 'responsible', 'category', 'eds_signed_by').prefetch_related(
            'files', 'subtasks', 'comments__author', 'comments__replies', 'history__user', 'assignments__assigned_to'
        )

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        task = self.object
        user = self.request.user

        context['can_edit'] = can_edit_task(user, task)
        context['can_delete'] = can_delete_task(user, task)
        context['can_start'] = can_start_task(user, task)
        context['can_submit_for_review'] = can_submit_for_review(user, task)
        context['can_accept'] = can_accept_task(user, task)
        context['can_return'] = can_return_task(user, task)
        context['can_delegate'] = can_delegate_task(user, task)

        context['subtask_form'] = SubTaskForm()
        context['comment_form'] = TaskCommentForm()
        context['delegation_form'] = TaskDelegationForm()
        context['now'] = timezone.now()
        context['all_active_users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name')

        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Обрабатывает асинхронную отправку email-уведомлений участникам задачи через Celery.

        Args:
            request (HttpRequest): Объект HTTP-запроса.
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.

        Returns:
            HttpResponse: Редирект на карточку задачи с сообщением о статусе.
        """
        task = self.get_object()

        if task.user != request.user:
            messages.error(request, "Только автор задачи может отправлять уведомления.")
            return redirect('tasks_app:task-detail', pk=task.pk)

        recipients = list(task.assignees.all()) + list(task.observers.all()) + list(task.shared_with.all())
        if task.responsible and task.responsible != request.user:
            recipients.append(task.responsible)
        recipients = list({u.id: u for u in recipients if u != request.user}.values())

        if not recipients:
            messages.warning(request, "Нет назначенных сотрудников или наблюдателей для отправки уведомления.")
            return redirect('tasks_app:task-detail', pk=task.pk)

        try:
            # Асинхронная отправка через Celery
            notify_task_participants_batch_task.delay(
                task_id=task.pk,
                sender_id=request.user.pk,
                event_type='assigned',
                comment='Уведомление отправлено автором поручения'
            )
            messages.success(request, f"Уведомления поставлены в очередь отправки ({len(recipients)} адресатов).")
        except Exception as err:
            logger.warning("Не удалось поставить в очередь Celery, синхронная отправка: %s", err)
            success_count = 0
            for recipient in recipients:
                if NotificationService.send_task_email_notification(task.pk, sender_id=request.user.pk, recipient_id=recipient.id, event_type='assigned'):
                    success_count += 1
            if success_count > 0:
                messages.success(request, f"Уведомления успешно отправлены ({success_count}).")
            else:
                messages.error(request, "Не удалось отправить уведомления. Проверьте настройки почты.")

        return redirect('tasks_app:task-detail', pk=task.pk)


class TaskStatusUpdateView(LoginRequiredMixin, UpdateView):
    """Устаревшее представление быстрого переключения статуса (для обратной совместимости)."""

    model = Task
    fields = ['completed']

    def get_queryset(self) -> QuerySet:
        return Task.objects.filter(
            Q(user=self.request.user) | Q(responsible=self.request.user) | Q(assignees=self.request.user)
        )

    def form_valid(self, form: Any) -> JsonResponse:
        task = form.save(commit=False)
        if task.completed:
            task.status = TaskStatus.COMPLETED
            task.completed_at = timezone.now()
        else:
            task.status = TaskStatus.IN_PROGRESS
            task.completed_at = None
        task.save()
        return JsonResponse({
            'status': 'ok',
            'completed': task.completed,
            'task_status': task.status,
            'message': 'Статус задачи обновлен'
        })

    def form_invalid(self, form: Any) -> JsonResponse:
        return JsonResponse({'status': 'error', 'error': 'Ошибка при обновлении статуса'}, status=400)

    @method_decorator(require_POST)
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def task_delegate_ajax(request: HttpRequest, pk: int) -> JsonResponse:
    """Делегирует или назначает задачу сотруднику через AJAX-запрос.

    Args:
        request (HttpRequest): Запрос с assigned_to, role и comment.
        pk (int): Первичный ключ задачи.

    Returns:
        JsonResponse: Статус операции и данные о назначении.
    """
    task = get_object_or_404(Task, pk=pk)
    assigned_to_id = request.POST.get('assigned_to')
    role = request.POST.get('role', TaskRole.ASSIGNEE)
    comment = request.POST.get('comment', '').strip()

    if not assigned_to_id:
        return JsonResponse({'error': 'Не выбран сотрудник для назначения'}, status=400)

    assigned_to = get_object_or_404(DataBaseUser, pk=assigned_to_id)
    try:
        assignment = TaskService.assign_user(
            task=task,
            assigned_by=request.user,
            assigned_to=assigned_to,
            role=role,
            comment=comment
        )
    except PermissionDenied as err:
        return JsonResponse({'error': str(err)}, status=403)

    return JsonResponse({
        'status': 'ok',
        'message': f'Поручение успешно выдано сотруднику {assigned_to.get_full_name()}',
        'assigned_to': assigned_to.get_full_name(),
        'role': assignment.get_role_display()
    })


@login_required
@require_POST
def task_kanban_move_ajax(request: HttpRequest) -> JsonResponse:
    """Обрабатывает Drag & Drop перемещение карточки задачи между колонками Канбана.

    Args:
        request (HttpRequest): Запрос с task_id и target_group.

    Returns:
        JsonResponse: Результат перемещения и обновленный статус.
    """
    task_id = request.POST.get('task_id')
    target_group = request.POST.get('target_group')

    if not task_id or not target_group:
        return JsonResponse({'error': 'task_id и target_group обязательны'}, status=400)

    task = get_object_or_404(Task, pk=task_id)

    try:
        if target_group == 'in_progress':
            task = TaskService.start_task(task, request.user)
        elif target_group == 'on_review':
            task = TaskService.submit_for_review(task, request.user, comment='Перемещено в колонку "На проверке"')
        elif target_group == 'completed':
            task = TaskService.accept_task(task, request.user, comment='Перемещено в колонку "Выполнено"')
        elif target_group == 'new':
            if task.user == request.user or request.user.is_superuser:
                task.status = TaskStatus.NEW
                task.completed = False
                task.save(update_fields=['status', 'completed', 'updated_at'])
                TaskHistory.log(
                    task=task,
                    user=request.user,
                    action=TaskHistory.ActionType.STATUS_CHANGED,
                    new_value=TaskStatus.NEW,
                    comment='Возвращено в статус "Новая"'
                )
            else:
                return JsonResponse({'error': 'Только автор может вернуть задачу в новые'}, status=403)
        else:
            return JsonResponse({'error': f'Неизвестная группа статусов: {target_group}'}, status=400)
    except (PermissionDenied, ValidationError) as err:
        return JsonResponse({'error': str(err)}, status=400)

    return JsonResponse({
        'status': 'ok',
        'new_status': task.status,
        'status_display': task.get_status_display(),
        'message': f'Задача «{task.title}» перемещена в {task.get_status_display()}'
    })


class TaskDashboardView(LoginRequiredMixin, ListView):
    """Сводный дашборд руководителя и сотрудника по задачам и поручениям."""

    template_name = 'tasks_app/task_dashboard.html'
    context_object_name = 'tasks'

    def get_queryset(self) -> QuerySet:
        user = self.request.user
        base_qs = Task.objects.filter(
            Q(user=user) | Q(responsible=user) | Q(assignees=user) | Q(observers=user) | Q(shared_with=user)
        ).distinct()

        division_id = self.request.GET.get('division')
        if division_id and division_id.isdigit():
            base_qs = base_qs.filter(
                Q(user__user_work_profile__divisions_id=int(division_id)) |
                Q(responsible__user_work_profile__divisions_id=int(division_id)) |
                Q(assignees__user_work_profile__divisions_id=int(division_id))
            ).distinct()

        return base_qs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        all_tasks = self.get_queryset().select_related('user', 'responsible', 'category').prefetch_related('subtasks')

        # Метрики
        context['total_tasks'] = all_tasks.count()
        context['in_progress_count'] = all_tasks.filter(
            status__in=[TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED, TaskStatus.NEW, TaskStatus.RETURNED]
        ).count()
        context['on_review_count'] = all_tasks.filter(status=TaskStatus.ON_REVIEW).count()
        context['overdue_count'] = all_tasks.filter(
            end_date__lt=timezone.now()
        ).exclude(status=TaskStatus.COMPLETED).count()
        context['completed_count'] = all_tasks.filter(status=TaskStatus.COMPLETED).count()

        # Срочные и просроченные поручения
        context['urgent_tasks'] = all_tasks.filter(
            end_date__isnull=False
        ).exclude(
            status=TaskStatus.COMPLETED
        ).order_by('end_date')[:6]

        # Задачи под моим контролем (где я автор)
        context['my_created_tasks'] = all_tasks.filter(user=user).exclude(status=TaskStatus.COMPLETED)[:5]

        # Мне поручено (где я ответственный или исполнитель)
        context['my_assigned_tasks'] = all_tasks.filter(
            Q(responsible=user) | Q(assignees=user)
        ).exclude(user=user).exclude(status=TaskStatus.COMPLETED)[:5]

        # Лента последней активности аудита
        context['recent_history'] = TaskHistory.objects.filter(
            task__in=all_tasks
        ).select_related('task', 'user').order_by('-created_at')[:10]

        # Загрузка сотрудников (Топ активных ответственных)
        active_responsibles = DataBaseUser.objects.filter(
            responsible_tasks__in=all_tasks
        ).distinct().annotate(
            tasks_total=Count('responsible_tasks', distinct=True)
        ).order_by('-tasks_total')[:8]

        workload_data = []
        for emp in active_responsibles:
            emp_tasks = all_tasks.filter(responsible=emp)
            workload_data.append({
                'employee': emp,
                'total': emp_tasks.count(),
                'in_progress': emp_tasks.filter(status=TaskStatus.IN_PROGRESS).count(),
                'on_review': emp_tasks.filter(status=TaskStatus.ON_REVIEW).count(),
                'overdue': emp_tasks.filter(end_date__lt=timezone.now()).exclude(status=TaskStatus.COMPLETED).count(),
                'completed': emp_tasks.filter(status=TaskStatus.COMPLETED).count(),
            })
        context['employee_workload'] = workload_data
        context['divisions'] = Division.objects.all().order_by('name')
        context['selected_division'] = self.request.GET.get('division', '')
        context['now'] = timezone.now()

        return context


class TaskKanbanView(LoginRequiredMixin, ListView):
    """Канбан-доска со столбцами статусов Workflow и Drag & Drop."""

    template_name = 'tasks_app/task_kanban.html'
    context_object_name = 'tasks'

    def get_queryset(self) -> QuerySet:
        user = self.request.user
        base_qs = Task.objects.filter(
            Q(user=user) | Q(responsible=user) | Q(assignees=user) | Q(observers=user) | Q(shared_with=user)
        ).distinct()

        category = self.request.GET.get('category')
        priority = self.request.GET.get('priority')
        responsible_id = self.request.GET.get('responsible')
        division_id = self.request.GET.get('division')
        tab = self.request.GET.get('tab', 'all')

        if category:
            base_qs = base_qs.filter(category__name=category)
        if priority:
            base_qs = base_qs.filter(priority=priority)
        if responsible_id:
            base_qs = base_qs.filter(responsible_id=responsible_id)
        if division_id and division_id.isdigit():
            base_qs = base_qs.filter(
                Q(user__user_work_profile__divisions_id=int(division_id)) |
                Q(responsible__user_work_profile__divisions_id=int(division_id)) |
                Q(assignees__user_work_profile__divisions_id=int(division_id))
            ).distinct()

        if tab == 'my':
            base_qs = base_qs.filter(user=user)
        elif tab == 'assigned':
            base_qs = base_qs.filter(Q(responsible=user) | Q(assignees=user))

        return base_qs.select_related('user', 'responsible', 'category').prefetch_related(
            'files', 'subtasks', 'comments', 'assignees'
        )

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tasks = list(self.get_queryset())

        context['col_new'] = [t for t in tasks if t.status in ('draft', 'new', 'assigned')]
        context['col_in_progress'] = [t for t in tasks if t.status in ('in_progress', 'returned')]
        context['col_on_review'] = [t for t in tasks if t.status == 'on_review']
        context['col_completed'] = [t for t in tasks if t.status == 'completed']

        context['categories'] = Category.objects.all()
        context['priorities'] = Task.PRIORITY_CHOICES
        context['divisions'] = Division.objects.all().order_by('name')
        context['selected_division'] = self.request.GET.get('division', '')
        context['users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name').exclude(is_superuser=True)
        context['now'] = timezone.now()

        return context


class TaskDisciplineReportView(LoginRequiredMixin, ListView):
    """Представление аналитического отчета по исполнительской дисциплине и поручениям."""

    template_name = 'tasks_app/task_discipline_report.html'
    context_object_name = 'tasks'

    def get_queryset(self) -> QuerySet:
        """Пустой QuerySet, так как данные формируются сервисным слоем ReportService."""
        return Task.objects.none()

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует контекст с агрегированными KPI, статистикой по подразделениям и сотрудникам."""
        context = super().get_context_data(**kwargs)
        date_from_str = self.request.GET.get('date_from')
        date_to_str = self.request.GET.get('date_to')
        division_id_str = self.request.GET.get('division')
        employee_id_str = self.request.GET.get('employee')

        date_from = None
        date_to = None
        division_id = None
        employee_id = None

        if date_from_str:
            try:
                date_from = datetime.datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = datetime.datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if division_id_str and division_id_str.isdigit():
            division_id = int(division_id_str)
        if employee_id_str and employee_id_str.isdigit():
            employee_id = int(employee_id_str)

        report_data = ReportService.get_discipline_report_data(
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
            employee_id=employee_id,
            current_user=self.request.user
        )

        context.update(report_data)
        context['divisions'] = Division.objects.all().order_by('name')
        context['all_active_users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name').exclude(is_superuser=True)
        return context


@login_required
def task_discipline_export_excel_view(request: HttpRequest) -> HttpResponse:
    """Генерирует и отдает Excel-файл (.xlsx) отчета по исполнительской дисциплине.

    Args:
        request (HttpRequest): Запрос с GET-параметрами date_from, date_to, division, employee.

    Returns:
        HttpResponse: Поток файла .xlsx со стилизацией ООО «Авиакомпания «БАРКОЛ».
    """
    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')
    division_id_str = request.GET.get('division')
    employee_id_str = request.GET.get('employee')

    date_from = None
    date_to = None
    division_id = None
    employee_id = None

    if date_from_str:
        try:
            date_from = datetime.datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = datetime.datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if division_id_str and division_id_str.isdigit():
        division_id = int(division_id_str)
    if employee_id_str and employee_id_str.isdigit():
        employee_id = int(employee_id_str)

    report_data = ReportService.get_discipline_report_data(
        date_from=date_from,
        date_to=date_to,
        division_id=division_id,
        employee_id=employee_id,
        current_user=request.user
    )

    wb = ReportService.generate_discipline_report_excel(report_data)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Discipline_Report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response