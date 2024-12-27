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

    PRIORITY_CHOICES = [
        ('primary', 'Основной'),
        ('warning', 'Предупреждающий'),
        ('info', 'Информационный'),
        ('danger', 'Опасный'),
        ('dark', 'Темный'),
    ]
    REPEAT_CHOICES = [
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
                                                  verbose_name='Интервал повторения')  # Например, раз в 2 недели
    repeat_days = models.CharField(max_length=20, blank=True, null=True,
                                   verbose_name='Дни недели')  # Например, "1,3" для понедельника и среды
    repeat_end_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата окончания повторения')

    def __str__(self):
        return self.title

    def get_rrule(self):
        """
        Возвращает объект rrule для задачи.
        """
        if self.repeat == 'none':
            return None

        freq = {
            'daily': DAILY,
            'weekly': WEEKLY,
            'monthly': MONTHLY,
            'yearly': YEARLY,
        }.get(self.repeat, WEEKLY)

        byweekday = None
        if self.repeat_days:
            byweekday = [int(day) for day in self.repeat_days.split(',')]

        return rrule(
            freq=freq,
            interval=self.repeat_interval,
            dtstart=self.start_date,
            until=self.repeat_end_date,
            byweekday=byweekday
        )

    def generate_repeat_dates(self):
        """
        Генерирует даты повторения задачи.
        """
        if self.repeat == 'none':
            return []

        rule = self.get_rrule()
        if not rule:
            return []

        return list(rule)

    def create_repeat_task(self):
        if self.repeat == 'none':
            return None

        new_task = Task(
            user=self.user,
            title=self.title,
            description=self.description,
            start_date=self.get_next_start_date(),
            end_date=self.get_next_end_date(),
            priority=self.priority,
            category=self.category,
            repeat=self.repeat,
        )
        new_task.save()
        return new_task

    def get_next_start_date(self):
        if self.repeat == 'daily':
            return self.start_date + timedelta(days=1)
        elif self.repeat == 'weekly':
            return self.start_date + timedelta(weeks=1)
        elif self.repeat == 'monthly':
            return self.start_date + timedelta(days=30)  # Упрощенный подход
        return None

    def get_next_end_date(self):
        if self.repeat == 'daily':
            return self.end_date + timedelta(days=1)
        elif self.repeat == 'weekly':
            return self.end_date + timedelta(weeks=1)
        elif self.repeat == 'monthly':
            return self.end_date + timedelta(days=30)  # Упрощенный подход
        return None

    def generate_repeat_dates(self, end_date=None):
        if end_date is None:
            end_date = timezone.now() + timedelta(days=365)  # Год вперед

        if self.end_date and self.end_date < end_date:
            end_date = self.end_date

        dates = []
        current_start = self.start_date
        current_end = self.end_date

        while current_start <= end_date:
            dates.append((current_start, current_end))
            if self.repeat == 'daily':
                current_start += timedelta(days=1)
                current_end += timedelta(days=1)
            elif self.repeat == 'weekly':
                current_start += timedelta(weeks=1)
                current_end += timedelta(weeks=1)
            elif self.repeat == 'monthly':
                current_start += timedelta(days=30)  # Упрощенный подход
                current_end += timedelta(days=30)

        return dates

    def get_absolute_url(self):
        return reverse('tasks_app:task-update', args=[str(self.id)])


class TaskFile(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='task_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name