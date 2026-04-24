# tasks_app/views.py
import datetime
import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from customers_app.models import DataBaseUser
from tasks_app.forms import TaskForm
from tasks_app.models import Task, Category, TaskFile

# Константы для валидации файлов
MAX_FILE_SIZE = 20 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.zip', 'rar']


@login_required
@require_POST
def create_task_ajax(request):
    title = request.POST.get('title')
    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)

    start_date = parse_datetime(request.POST.get('start_date'))
    end_date = parse_datetime(request.POST.get('end_date'))

    # ✅ ИСПРАВЛЕНО: правильная обработка часовых поясов
    from django.utils.timezone import get_current_timezone
    current_tz = get_current_timezone()

    if start_date and timezone.is_naive(start_date):
        start_date = timezone.make_aware(start_date, current_tz)
    if end_date and timezone.is_naive(end_date):
        end_date = timezone.make_aware(end_date, current_tz)

    # Безопасное сравнение
    if start_date and end_date and end_date < start_date:
        return JsonResponse({'error': 'Дата завершения не может быть раньше даты начала'}, status=400)

    # Безопасное получение shared_with
    shared_ids = request.POST.getlist('shared_with[]')
    shared_users = DataBaseUser.objects.filter(id__in=shared_ids, is_active=True)

    task = Task.objects.create(
        user=request.user,
        title=title,
        start_date=start_date,
        end_date=end_date,
        priority=request.POST.get('priority', 'primary'),
        repeat=request.POST.get('freq', 'none'),
    )
    if shared_users.exists():
        task.shared_with.set(shared_users)

    return JsonResponse({
        'id': task.id,
        'title': task.title,
        'start_date': task.start_date.isoformat() if task.start_date else None,
        'end_date': task.end_date.isoformat() if task.end_date else None,
        'url': task.get_absolute_url(),
        'color': task.priority
    })


@login_required
@require_POST
def upload_files_ajax(request):
    task_id = request.POST.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'task_id required'}, status=400)

    # Проверяем, что пользователь имеет доступ к задаче
    task = get_object_or_404(Task, pk=task_id)
    if task.user != request.user and not task.shared_with.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    files = request.FILES.getlist('files')

    # ✅ ДОБАВЛЕНО: валидация количества файлов
    if len(files) > 10:
        return JsonResponse({'error': 'Максимум 10 файлов за раз'}, status=400)

    uploaded_files = []
    errors = []

    for file in files:
        # ✅ ДОБАВЛЕНО: проверка размера файла
        if file.size > MAX_FILE_SIZE:
            errors.append(f'Файл "{file.name}" превышает 10MB')
            continue

        # ✅ ДОБАВЛЕНО: проверка расширения
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f'Неподдерживаемый тип файла: {file.name}')
            continue

        task_file = TaskFile.objects.create(
            task_id=task_id,
            file=file,
            original_filename=file.name
        )
        uploaded_files.append({
            'id': task_file.id,
            'name': task_file.original_filename,
            'url': task_file.file.url,
            'size': task_file.file.size
        })

    if errors:
        return JsonResponse({'files': uploaded_files, 'errors': errors}, status=207)

    return JsonResponse({'files': uploaded_files})


@login_required
@require_POST
def delete_file_ajax(request):
    file_id = request.POST.get('file_id')
    if not file_id:
        return JsonResponse({'error': 'file_id обязателен'}, status=400)

    task_file = get_object_or_404(TaskFile, pk=file_id)

    # Проверка прав: владелец задачи или пользователь с доступом
    if task_file.task.user != request.user and not task_file.task.shared_with.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Нет прав на удаление'}, status=403)

    # Удаляем физический файл с диска
    if task_file.file:
        task_file.file.delete(save=False)

    task_file.delete()
    return JsonResponse({'status': 'ok'})


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    context_object_name = 'tasks'

    def get_queryset(self):
        base_qs = Task.objects.filter(
            Q(user=self.request.user) | Q(shared_with=self.request.user)
        )

        category = self.request.GET.get('category')
        priority = self.request.GET.get('priority')
        shared = self.request.GET.get('shared')

        if category:
            base_qs = base_qs.filter(category__name=category)
        if priority:
            base_qs = base_qs.filter(priority=priority)
        if shared == 'my':
            base_qs = base_qs.filter(user=self.request.user)
        elif shared == 'shared':
            base_qs = base_qs.filter(shared_with=self.request.user)

        return base_qs.select_related('user', 'category').prefetch_related('files').distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['priorities'] = Task.PRIORITY_CHOICES

        calendar_events = []  # Переименуем для ясности
        for task in context['tasks']:
            if not task.start_date:
                continue

            # Базовые поля для всех событий
            event_data = {
                'id': str(task.id),
                'title': self.get_task_title_with_icon(task),
                'url': reverse('tasks_app:task-detail', args=[task.pk]),
                'color': task.priority,
                'className': f'fc-event-{task.priority}',
            }

            # Добавляем дату окончания если есть
            if task.end_date:
                event_data['end'] = task.end_date.isoformat()

            # Для повторяющихся задач используем rrule
            if task.repeat != 'none':
                # Формируем RRULE для FullCalendar (объект, а не строка)
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

                # Добавляем дни недели
                if task.repeat_days and task.repeat_days not in ('', '[]', 'null', 'None'):
                    try:
                        days_map = ['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su']
                        if task.repeat_days.startswith('['):
                            import json
                            days_list = json.loads(task.repeat_days)
                            byweekday = [days_map[int(d)] for d in days_list if d is not None]
                        else:
                            byweekday = [days_map[int(day.strip())] for day in task.repeat_days.split(',') if
                                         day.strip()]
                        if byweekday:
                            rrule_obj['byweekday'] = byweekday
                    except (ValueError, json.JSONDecodeError, IndexError, TypeError):
                        pass

                # Добавляем дату окончания повторений
                if task.repeat_end_date:
                    rrule_obj['until'] = task.repeat_end_date.isoformat()

                event_data['rrule'] = rrule_obj
            else:
                # Для обычных задач используем start/end
                event_data['start'] = task.start_date.isoformat()
                if task.end_date:
                    event_data['end'] = task.end_date.isoformat()

            calendar_events.append(event_data)

        context['repeat_tasks'] = calendar_events  # Сохраняем то же имя для совместимости
        context['users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name').exclude(is_superuser=True)

        return context

    def get_task_title_with_icon(self, task):
        """
        Возвращает название задачи с иконкой в зависимости от приоритета.
        """
        before = ''
        after = ''
        if task.completed:
            after = '<i class="fa-regular fa-square-check"></i>'
        elif task.end_date > datetime.today():
            after = '<i class="fa-solid fa-hourglass-half"></i>'
        else:
            after = '<i class="fa-solid fa-xmark"></i>'


        if task.user != self.request.user:
            before = f'<i class="fas fa-user-friends"></i>'
        if task.priority == 'primary':
            before = f'<i class="fas fa-star"></i>'
        elif task.priority == 'warning':
            before = f'<i class="fas fa-exclamation-triangle"></i>'
        elif task.priority == 'info':
            before = f'<i class="fas fa-info-circle"></i>'
        elif task.priority == 'danger':
            before = f'<i class="fas fa-exclamation-circle"></i>'
        elif task.priority == 'dark':
            before = f'<i class="fas fa-moon"></i>'
        return f'{before} {task.title} {after}'


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    success_url = reverse_lazy('tasks_app:task-list')

    def form_valid(self, form):
        form.instance.user = self.request.user

        # ✅ ИСПРАВЛЕНО: правильное сохранение repeat_days
        repeat_days = form.cleaned_data.get('repeat_days')
        if repeat_days:
            # Если это список (как приходит из формы)
            if isinstance(repeat_days, list):
                form.instance.repeat_days = ','.join(str(day) for day in repeat_days if day is not None)
            else:
                form.instance.repeat_days = str(repeat_days)
        else:
            form.instance.repeat_days = None  # ✅ Явно ставим None вместо '[]'

        response = super().form_valid(form)

        # Привязываем файлы к задаче
        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(task_id=form.instance.id, file=file, original_filename=file.name)

        return response


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user != self.request.user:
            raise PermissionDenied("Вы не можете редактировать чужие задачи")
        return obj

    def form_valid(self, form):
        task = form.save(commit=False)
        if task.completed and not task.end_date:
            task.end_date = timezone.now()

        # ✅ ИСПРАВЛЕНО: правильное сохранение repeat_days
        repeat_days = form.cleaned_data.get('repeat_days')
        if repeat_days:
            if isinstance(repeat_days, list):
                task.repeat_days = ','.join(str(day) for day in repeat_days if day is not None)
            else:
                task.repeat_days = str(repeat_days)
        else:
            task.repeat_days = None  # ✅ Явно ставим None

        task.save()
        form.save_m2m()

        # Привязываем новые файлы
        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(task_id=task.id, file=file, original_filename=file.name)

        return super().form_valid(form)


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


# ✅ ДОБАВЛЕНО: DetailView для просмотра задачи
class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    context_object_name = 'task'
    template_name = 'tasks_app/task_detail.html'

    def get_queryset(self):
        # Просмотр доступен для своих задач и шаред
        return Task.objects.filter(
            Q(user=self.request.user) | Q(shared_with=self.request.user)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.object.user == self.request.user
        return context


# tasks_app/views.py
class TaskStatusUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    fields = ['completed']

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def form_valid(self, form):
        task = form.save(commit=False)
        if task.completed and not task.end_date:
            task.end_date = timezone.now()
        elif not task.completed:
            task.end_date = None
        task.save()
        return JsonResponse({
            'status': 'ok',
            'completed': task.completed,
            'message': 'Статус задачи обновлен'
        })

    def form_invalid(self, form):
        return JsonResponse({
            'status': 'error',
            'error': 'Ошибка при обновлении статуса'
        }, status=400)

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)