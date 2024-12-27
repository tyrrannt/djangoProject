import json
from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse


# Create your views here.

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from customers_app.models import DataBaseUser
from tasks_app.forms import TaskForm
from tasks_app.models import Task, Category, TaskFile


@csrf_exempt
def create_task_ajax(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        priority = request.POST.get('priority', 'primary')  # Получаем приоритет из запроса
        shared_with = request.POST.getlist('shared_with[]')  # Получаем список пользователей
        freq = request.POST.get('freq')
        print(request.POST)
        # Преобразуем строку в объект datetime
        start_date = parse_datetime(start_date_str)
        end_date = parse_datetime(end_date_str)

        # Создаем задачу с параметрами по умолчанию
        task = Task.objects.create(
            user=request.user,
            title=title,
            start_date=start_date,
            end_date=end_date,
            priority=priority,  # Устанавливаем приоритет
            repeat=freq,  # Устанавливаем повторение
        )

        # Добавляем пользователей, которым предоставлен доступ
        if shared_with:
            task.shared_with.set(shared_with)



        # Возвращаем данные о созданной задаче
        return JsonResponse({
            'id': task.id,
            'title': task.title,
            'start_date': task.start_date.strftime('%Y-%m-%d'),
            'end_date': task.end_date.strftime('%Y-%m-%d'),
            'url': task.get_absolute_url(),
            'color': task.priority  # Возвращаем цвет на основе приоритета
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def upload_files_ajax(request):
    if request.method == 'POST':
        files = request.FILES.getlist('files')  # Получаем список файлов
        task_id = request.POST.get('task_id')  # ID задачи (если нужно привязать файлы к задаче)

        uploaded_files = []
        for file in files:
            task_file = TaskFile.objects.create(task_id=task_id, file=file)
            uploaded_files.append({
                'name': task_file.file.name,
                'url': task_file.file.url,
                'size': task_file.file.size
            })

        return JsonResponse({'files': uploaded_files})
    return JsonResponse({'error': 'Invalid request'}, status=400)


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    context_object_name = 'tasks'

    def get_queryset(self):
        # Получаем задачи, созданные текущим пользователем
        queryset = Task.objects.filter(user=self.request.user)

        # Добавляем задачи, к которым текущий пользователь имеет доступ
        queryset = queryset | Task.objects.filter(shared_with=self.request.user)

        # Применяем фильтры
        category = self.request.GET.get('category')
        priority = self.request.GET.get('priority')
        shared = self.request.GET.get('shared')  # Добавляем фильтр по доступу

        if category:
            queryset = queryset.filter(category__name=category)
        if priority:
            queryset = queryset.filter(priority=priority)

        # Фильтр по доступу
        if shared == 'my':
            queryset = queryset.filter(user=self.request.user)  # Только задачи, созданные текущим пользователем
        elif shared == 'shared':
            queryset = queryset.filter(shared_with=self.request.user)  # Только задачи, к которым есть доступ

        return queryset.distinct()  # Убираем дубликаты

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
            TaskFile.objects.create(task_id=task_id, file=file)

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
            TaskFile.objects.create(task_id=task_id, file=file)

        return super().form_valid(form)

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    success_url = reverse_lazy('tasks_app:task-list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)