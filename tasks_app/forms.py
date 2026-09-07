"""Формы для управления задачами, поручениями, подзадачами и комментариями (tasks_app).

Модуль предоставляет формы Django с кастомной стилизацией make_custom_field,
валидацией дат, сериализацией дней повторений и выбором ролей исполнителей.
"""

import json
from typing import Any, Dict

from django import forms
from django.core.exceptions import ValidationError

from administration_app.utils import make_custom_field
from customers_app.models import DataBaseUser
from tasks_app.models import Category, SubTask, Task, TaskComment, TaskRole, TaskStatus


class TaskForm(forms.ModelForm):
    """Основная форма создания и редактирования задачи / поручения.

    Предоставляет поля для настройки сроков, приоритета, категории,
    назначения ответственного и соисполнителей, а также параметров повторения.
    """

    repeat_days = forms.MultipleChoiceField(
        choices=[
            ('0', 'Понедельник'),
            ('1', 'Вторник'),
            ('2', 'Среда'),
            ('3', 'Четверг'),
            ('4', 'Пятница'),
            ('5', 'Суббота'),
            ('6', 'Воскресенье'),
        ],
        required=False,
        label="Дни недели для повторения"
    )

    class Meta:
        model = Task
        exclude = [
            'user', 'completed', 'completed_at', 'accepted_at',
            'submitted_review_at', 'eds_signature', 'eds_signed_by', 'eds_signed_at'
        ]
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'repeat_end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Введите подробное описание задачи...'}),
            'responsible': forms.Select(attrs={'class': 'form-control select2'}),
            'assignees': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
            'observers': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
            'shared_with': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует форму и настраивает QuerySet для пользователей и категорий.

        Args:
            *args: Позиционные аргументы формы.
            **kwargs: Именованные аргументы формы.
        """
        super().__init__(*args, **kwargs)

        active_users = DataBaseUser.objects.filter(is_active=True).order_by('last_name', 'first_name')
        self.fields['category'].queryset = Category.objects.all()
        self.fields['responsible'].queryset = active_users
        self.fields['responsible'].required = False
        self.fields['assignees'].queryset = active_users
        self.fields['observers'].queryset = active_users
        self.fields['shared_with'].queryset = active_users

        self.fields['responsible'].label = "Главный ответственный"
        self.fields['assignees'].label = "Соисполнители"
        self.fields['observers'].label = "Наблюдатели (контроль)"
        self.fields['shared_with'].label = "Общий доступ (шаринг)"

        for field_name in self.fields:
            make_custom_field(self.fields[field_name])

        # Предзаполнение repeat_days из сохраненной строки/JSON
        if self.instance and self.instance.pk and self.instance.repeat_days:
            if self.instance.repeat_days not in ('', '[]', 'null', 'None'):
                try:
                    if self.instance.repeat_days.startswith('['):
                        self.initial['repeat_days'] = json.loads(self.instance.repeat_days)
                    else:
                        self.initial['repeat_days'] = [
                            d.strip() for d in self.instance.repeat_days.split(',') if d.strip()
                        ]
                except (ValueError, json.JSONDecodeError):
                    self.initial['repeat_days'] = []

    def clean(self) -> Dict[str, Any]:
        """Выполняет кросс-полевую валидацию дат и параметров повторения.

        Returns:
            Dict[str, Any]: Очищенные валидированные данные формы.
        """
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')

        if start and end and end < start:
            self.add_error('end_date', 'Срок завершения (дедлайн) не может быть раньше даты начала.')

        repeat_days = cleaned_data.get('repeat_days')
        if repeat_days in ('[]', [], ''):
            cleaned_data['repeat_days'] = None

        return cleaned_data


class SubTaskForm(forms.ModelForm):
    """Форма быстрого добавления подзадачи / пункта чек-листа."""

    class Meta:
        model = SubTask
        fields = ['title', 'assigned_to']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Добавить новый пункт чек-листа...'
            }),
            'assigned_to': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Настраивает форму подзадачи.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = DataBaseUser.objects.filter(is_active=True).order_by('last_name')
        self.fields['assigned_to'].required = False
        for field in self.fields:
            make_custom_field(self.fields[field])


class TaskCommentForm(forms.ModelForm):
    """Форма добавления комментария в обсуждение задачи."""

    class Meta:
        model = TaskComment
        fields = ['text', 'parent']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Напишите комментарий, вопрос или отчет...'
            }),
            'parent': forms.HiddenInput(),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализация формы комментария.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        super().__init__(*args, **kwargs)
        self.fields['parent'].required = False
        for field in self.fields:
            make_custom_field(self.fields[field])


class TaskDelegationForm(forms.Form):
    """Форма делегирования задачи сотруднику."""

    assigned_to = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.none(),
        label="Сотрудник",
        widget=forms.Select(attrs={'class': 'form-control select2'})
    )
    role = forms.ChoiceField(
        choices=TaskRole.choices,
        label="Роль",
        initial=TaskRole.ASSIGNEE,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    comment = forms.CharField(
        required=False,
        label="Пояснение к поручению",
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Укажите инструкции или рамки поручения...'})
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализация формы делегирования.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = DataBaseUser.objects.filter(is_active=True).order_by('last_name')
        for field in self.fields:
            make_custom_field(self.fields[field])