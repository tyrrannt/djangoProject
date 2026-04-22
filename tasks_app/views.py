from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

# Create your views here.

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from customers_app.models import DataBaseUser
from tasks_app.forms import TaskForm
from tasks_app.models import Task, Category, TaskFile


@login_required
@require_POST
def create_task_ajax(request):
    title = request.POST.get('title')
    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)

    start_date = parse_datetime(request.POST.get('start_date'))
    end_date = parse_datetime(request.POST.get('end_date'))

    # 1. Нормализуем часовые пояса: приводим обе даты к timezone-aware
    if start_date and timezone.is_naive(start_date):
        start_date = timezone.make_aware(start_date)
    if end_date and timezone.is_naive(end_date):
        end_date = timezone.make_aware(end_date)

    # 2. Безопасное сравнение
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
    uploaded_files = []
    for file in files:
        task_file = TaskFile.objects.create(
            task_id=task_id,
            file=file,
            original_filename=file.name  # ✅ Сохраняем исходное имя
        )
        uploaded_files.append({
            'name': task_file.original_filename,  # ✅ Возвращаем оригинальное имя
            'url': task_file.file.url,
            'size': task_file.file.size
        })
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

    # Удаляем физический файл с диска (save=False не сохраняет изменения в БД)
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
        # Фильтр по доступу
        if shared == 'my':
            base_qs = base_qs.filter(user=self.request.user)  # Только задачи, созданные текущим пользователем
        elif shared == 'shared':
            base_qs = base_qs.filter(shared_with=self.request.user)  # Только задачи, к которым есть доступ

        # Оптимизация: убираем N+1
        return base_qs.select_related('user', 'category').prefetch_related('files').distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['priorities'] = Task.PRIORITY_CHOICES

        repeat_tasks = []
        for task in context['tasks']:
            repeat_tasks.append({
                'title': self.get_task_title_with_icon(task),  # Получаем название задачи с иконкой task.title,
                'rrule': {
                    'freq': task.repeat,  # Используем поле repeat для freq
                    'dtstart': task.start_date.isoformat(),  # Начальная дата с временной зоной
                    'until': task.end_date.isoformat()  # Конечная дата с временной зоной
                },
                'url': reverse('tasks_app:task-update', args=[task.pk]),
                'color': task.priority,
            })
        context['repeat_tasks'] = repeat_tasks
        context['users'] = DataBaseUser.objects.filter(is_active=True).order_by('last_name').exclude(is_superuser=True)
        return context

    def get_task_title_with_icon(self, task):
        """
        Возвращает название задачи с иконкой в зависимости от приоритета.
        """
        if task.user != self.request.user:
            return f'<i class="fas fa-user-friends"></i> {task.title}'
        if task.priority == 'primary':
            return f'<i class="fas fa-star"></i> {task.title}'  # Звезда для основного приоритета
        elif task.priority == 'warning':
            return f'<i class="fas fa-exclamation-triangle"></i> {task.title}'  # Предупреждение для предупреждающего приоритета
        elif task.priority == 'info':
            return f'<i class="fas fa-info-circle"></i> {task.title}'  # Информация для информационного приоритета
        elif task.priority == 'danger':
            return f'<i class="fas fa-exclamation-circle"></i> {task.title}'  # Ошибка для опасного приоритета
        elif task.priority == 'dark':
            return f'<i class="fas fa-moon"></i> {task.title}'  # Луна для темного приоритета

        return task.title


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    success_url = reverse_lazy('tasks_app:task-list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)

        # Привязываем файлы к задаче (если они были загружены через Dropzone.js)
        task_id = form.instance.id
        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(task_id=task_id, file=file, original_filename=file.name)

        # Создаем повторяющуюся задачу
        if form.cleaned_data['repeat'] != 'none':
            new_task = form.instance.create_repeat_task()
            if new_task:
                messages.success(self.request, f"Создана повторяющаяся задача: {new_task.title}")

        # Сохраняем выбранные дни недели
        if form.cleaned_data['repeat_days']:
            form.instance.repeat_days = ','.join(form.cleaned_data['repeat_days'])

        return response


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self):
        # Получаем задачи, созданные текущим пользователем
        queryset = Task.objects.filter(user=self.request.user)

        # Добавляем задачи, к которым текущий пользователь имеет доступ
        queryset = queryset | Task.objects.filter(shared_with=self.request.user)
        return queryset.distinct()

    def form_valid(self, form):
        task = form.save(commit=False)
        if task.completed and not task.end_date:
            task.end_date = timezone.now()  # Устанавливаем дату завершения
        task.save()

        # Привязываем файлы к задаче (если они были загружены через Dropzone.js)
        task_id = form.instance.id
        files = self.request.FILES.getlist('files')
        for file in files:
            TaskFile.objects.create(task_id=task_id, file=file, original_filename=file.name)

        # Сохраняем выбранные дни недели, если есть
        if form.cleaned_data.get('repeat_days'):
            task.repeat_days = ','.join(form.cleaned_data['repeat_days'])
            task.save()

        return super().form_valid(form)


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)
