"""Формы ввода и валидации данных модуля заявок (tickets_app.forms).

Обеспечивает валидацию текстовых полей, списков загружаемых файлов,
контроль прав доступа к назначению ответственных и смене статусов.
"""

from typing import Any, Dict, List, Optional

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from administration_app.utils import make_custom_field
from .models import Attachment, Message, Ticket, TicketStatus, validate_file_extension

User = get_user_model()


class MultipleFileInput(forms.ClearableFileInput):
    """Виджет множественного выбора файлов для полей загрузки."""

    allow_multiple_selected = True

    def __init__(self, attrs: Optional[Dict[str, Any]] = None) -> None:
        """Инициализирует виджет с атрибутом multiple."""
        if attrs is None:
            attrs = {}
        attrs['multiple'] = 'multiple'
        super().__init__(attrs=attrs)


class MultipleFileField(forms.FileField):
    """Поле формы для валидации и приема нескольких файлов одновременно."""

    widget = MultipleFileInput

    def __init__(self, **kwargs: Any) -> None:
        """Инициализирует поле с виджетом множественной загрузки."""
        kwargs.setdefault('widget', self.widget)
        super().__init__(**kwargs)

    def to_python(self, data: Any) -> Optional[List[Any]]:
        """Преобразует входные данные в список загруженных файлов."""
        if data in self.empty_values:
            return None
        if isinstance(data, (list, tuple)):
            return [f for f in data if f]
        return [data]

    def clean(self, data: Any, initial: Any = None) -> Optional[List[Any]]:
        """Выполняет комплексную валидацию списка файлов.

        Args:
            data: Список файлов из запроса.
            initial: Исходное значение поля.

        Returns:
            Optional[List[Any]]: Проверенный список файлов.

        Raises:
            ValidationError: Если хотя бы один файл нарушает расширение или размер.
        """
        files = self.to_python(data)
        if not files:
            if self.required:
                raise ValidationError(self.error_messages['required'], code='required')
            return []

        for f in files:
            validate_file_extension(f)

        return files


class TicketCreateForm(forms.ModelForm):
    """Форма первичной подачи добровольного сообщения / заявки.

    Позволяет указать тему, описание, выбрать родительскую закрытую заявку
    для обжалования и прикрепить файлы.
    """

    attachments = MultipleFileField(
        label='Вложения',
        required=False,
        help_text='Можно выбрать несколько файлов. Разрешены: PDF, JPG, PNG (до 25 МБ каждый)',
    )

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'parent_ticket']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Краткая суть проблемы или инцидента',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Подробно опишите обстоятельства, место, время, факторы риска и предложения...',
            }),
            'parent_ticket': forms.Select(attrs={
                'class': 'form-select',
            }),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует форму и ограничивает выбор обжалований заявками автора."""
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.user:
            self.fields['parent_ticket'].queryset = Ticket.objects.filter(
                author=self.user,
                status__in=[TicketStatus.CLOSED, TicketStatus.RESOLVED],
            ).select_related('responsible')
        else:
            self.fields['parent_ticket'].queryset = Ticket.objects.none()

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_parent_ticket(self) -> Optional[Ticket]:
        """Валидирует допустимость обжалования выбранной заявки.

        Returns:
            Optional[Ticket]: Проверенная родительская заявка.

        Raises:
            ValidationError: Если заявка принадлежит другому автору или не завершена.
        """
        parent_ticket = self.cleaned_data.get('parent_ticket')
        if parent_ticket:
            if self.user and parent_ticket.author != self.user:
                raise forms.ValidationError('Разрешено обжаловать только собственные заявки.')

            allowed_statuses = [TicketStatus.CLOSED, TicketStatus.RESOLVED]
            if parent_ticket.status not in allowed_statuses:
                raise forms.ValidationError(
                    f'Обжалование возможно только для заявок в статусе: '
                    f'{", ".join(dict(TicketStatus.choices).values())}'
                )
        return parent_ticket


class TicketUpdateForm(forms.ModelForm):
    """Форма редактирования заявки (изменение темы/описания, назначение ответственного, смена статуса).

    Обеспечивает строгое разграничение прав: изменять ответственного и статус могут только
    пользователи с правами руководства или суперпользователи.
    """

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'responsible', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'responsible': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует форму с проверкой прав доступа к служебным полям."""
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        is_manager = False
        if self.user:
            is_manager = self.user.is_superuser or self.user.groups.filter(name='Руководство').exists()

        if not is_manager:
            self.fields['responsible'].disabled = True
            self.fields['status'].disabled = True
            self.fields['responsible'].required = False
            self.fields['status'].required = False

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_responsible(self) -> Optional[Any]:
        """Предотвращает подделку ответственного лица обычным пользователем."""
        is_manager = False
        if self.user:
            is_manager = self.user.is_superuser or self.user.groups.filter(name='Руководство').exists()

        if not is_manager and self.instance.pk:
            return self.instance.responsible

        responsible = self.cleaned_data.get('responsible')
        if not responsible and self.instance.pk:
            return self.instance.responsible
        return responsible

    def clean_status(self) -> str:
        """Предотвращает несанкционированную смену статуса обычным пользователем."""
        is_manager = False
        if self.user:
            is_manager = self.user.is_superuser or self.user.groups.filter(name='Руководство').exists()

        if not is_manager and self.instance.pk:
            return self.instance.status

        status = self.cleaned_data.get('status')
        if not status and self.instance.pk:
            return self.instance.status
        return status


class MessageForm(forms.ModelForm):
    """Форма отправки комментария / отчета о принятых мерах в переписку по заявке."""

    attachments = MultipleFileField(
        label='Прикрепить файлы',
        required=False,
        help_text='Разрешены: PDF, JPG, PNG (до 25 МБ каждый)',
    )

    class Meta:
        model = Message
        fields = ['text', 'is_internal']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Введите ваш комментарий или отчет о принятых мерах...',
            }),
            'is_internal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует поля формы стилизованными виджетами."""
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'is_internal':
                make_custom_field(self.fields[field])


class AttachmentForm(forms.ModelForm):
    """Форма добавления одиночного вложения."""

    class Meta:
        model = Attachment
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }