# tasks_app/models.py
import os
import uuid

from dateutil.relativedelta import relativedelta
from django.db import models
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from dateutil.rrule import rrule, WEEKLY, MONTHLY, YEARLY, DAILY

from customers_app.models import DataBaseUser


class Category(models.Model):
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    name = models.CharField(max_length=100, verbose_name='Название категории')

    def __str__(self):
        return self.name


class Task(models.Model):
    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        indexes = [
            models.Index(fields=['user', 'completed']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['priority']),
        ]

    PRIORITY_CHOICES = [
        ('primary', 'Основной'),
        ('warning', 'Предупреждающий'),
        ('info', 'Информационный'),
        ('danger', 'Опасный'),
        ('dark', 'Темный'),
    ]
    REPEAT_CHOICES = [
        ('none', 'Нет'),  # ✅ ДОБАВЛЕНО!
        ('daily', 'Ежедневно'),
        ('weekly', 'Еженедельно'),
        ('monthly', 'Ежемесячно'),
        ('yearly', 'Ежегодно'),
        ('custom', 'Пользовательский интервал'),
    ]

    user = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE, related_name='tasks', verbose_name='Автор')
    shared_with = models.ManyToManyField(DataBaseUser, related_name='shared_tasks', blank=True,
                                         verbose_name='Доступ для')
    title = models.CharField(max_length=200, verbose_name='Заголовок')
    description = models.TextField(blank=True, null=True, verbose_name='Описание задачи')
    completed = models.BooleanField(default=False, verbose_name='Завершено')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    start_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата начала')
    end_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата завершения')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='primary', verbose_name='Важность')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='Категория')
    repeat = models.CharField(max_length=10, choices=REPEAT_CHOICES, default='none', verbose_name='Повторяемость')
    repeat_interval = models.PositiveIntegerField(default=1,
                                                  verbose_name='Интервал повторения')
    repeat_days = models.CharField(max_length=40, blank=True, null=True,
                                   verbose_name='Дни недели')  # Например, "0,2,4" для ПН,СР,ПТ
    repeat_end_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата окончания повторения')

    def __str__(self):
        return self.title

    def get_rrule(self):
        """
        Возвращает объект rrule для задачи.
        """
        if self.repeat == 'none' or not self.start_date:
            return None

        freq_map = {
            'daily': DAILY,
            'weekly': WEEKLY,
            'monthly': MONTHLY,
            'yearly': YEARLY,
        }
        freq = freq_map.get(self.repeat, WEEKLY)

        byweekday = None
        # ✅ ИСПРАВЛЕНО: проверка на пустые значения и '[]'
        if self.repeat_days and self.repeat_days not in ('', '[]', 'null', 'None'):
            try:
                # Пытаемся распарсить как JSON или просто строку с запятыми
                if self.repeat_days.startswith('['):
                    # Если это JSON-подобная строка типа '[0,2,4]'
                    import json
                    days_list = json.loads(self.repeat_days)
                    byweekday = [int(day) for day in days_list if day is not None]
                else:
                    # Обычная строка с запятыми "0,2,4"
                    byweekday = [int(day.strip()) for day in self.repeat_days.split(',') if day.strip()]
            except (ValueError, json.JSONDecodeError, TypeError):
                # В случае ошибки просто игнорируем
                byweekday = None

        # Создаем rrule
        try:
            return rrule(
                freq=freq,
                interval=self.repeat_interval or 1,
                dtstart=self.start_date,
                until=self.repeat_end_date if self.repeat_end_date else None,
                byweekday=byweekday
            )
        except (ValueError, TypeError) as e:
            # Логируем ошибку, но не падаем
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating rrule for task {self.id}: {e}")
            return None

    def get_next_occurrence(self):
        """
        Возвращает следующую дату начала и окончания для повторяющейся задачи.
        """
        if self.repeat == 'none' or not self.start_date:
            return None, None

        # Проверяем, не истек ли период повторения
        if self.repeat_end_date and self.repeat_end_date < timezone.now():
            return None, None

        rule = self.get_rrule()
        if not rule:
            return None, None

        # Получаем следующую дату после текущей
        after_date = timezone.now()
        next_start = rule.after(after_date, inc=False)

        if not next_start:
            return None, None

        # Если есть дата окончания, вычисляем длительность
        next_end = None
        if self.end_date and self.start_date:
            duration = self.end_date - self.start_date
            next_end = next_start + duration

        return next_start, next_end

    def create_next_task(self):
        """
        Создает следующую задачу на основе повторения.
        Возвращает созданную задачу или None.
        """
        next_start, next_end = self.get_next_occurrence()

        if not next_start:
            return None

        next_task = Task(
            user=self.user,
            title=self.title,
            description=self.description,
            start_date=next_start,
            end_date=next_end,
            priority=self.priority,
            category=self.category,
            repeat=self.repeat,
            repeat_interval=self.repeat_interval,
            repeat_days=self.repeat_days,
            repeat_end_date=self.repeat_end_date,
        )

        # Копируем shared_with пользователей
        next_task.save()
        next_task.shared_with.set(self.shared_with.all())

        return next_task

    def get_absolute_url(self):
        return reverse('tasks_app:task-update', args=[str(self.id)])


# 🔹 Функция для динамического пути
def get_task_file_path(instance, filename):
    # Расширение файла (приводим к нижнему регистру)
    ext = os.path.splitext(filename)[1].lower()
    # Уникальное имя
    new_name = f"{uuid.uuid4().hex}{ext}"

    # Год/Месяц загрузки
    date_path = timezone.now().strftime("%Y/%m")

    # Username автора задачи (с безопасной проверкой)
    username = "unknown"
    if instance.task and instance.task.user:
        username = getattr(instance.task.user, 'username', str(instance.task.user.id))

    return f"task_files/{date_path}/{username}/{new_name}"


class TaskFile(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=get_task_file_path, verbose_name="Файл")
    original_filename = models.CharField(max_length=255, blank=True, null=True, verbose_name="Оригинальное имя")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['task', '-uploaded_at']),
        ]

    def __str__(self):
        return self.original_filename or self.file.name

    def delete(self, *args, **kwargs):
        # Удаляем физический файл при удалении записи из БД
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)