from django import forms
from django.contrib.auth import get_user_model

from administration_app.utils import make_custom_field
from .models import Ticket, Message, Attachment, TicketStatus

User = get_user_model()


class MultipleFileInput(forms.ClearableFileInput):
    """Виджет для множественной загрузки файлов"""
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs['multiple'] = 'multiple'
        super().__init__(attrs=attrs)


class TicketCreateForm(forms.ModelForm):
    """Форма создания заявки"""
    attachments = forms.FileField(
        label='Вложения',
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png',
        }),
        help_text='Можно выбрать несколько файлов. Разрешены: PDF, JPG, PNG',
    )

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'parent_ticket']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Краткая суть проблемы'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Подробно опишите проблему или предложение'
            }),
            'parent_ticket': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Показываем только закрытые заявки автора для обжалования
        if self.user:
            self.fields['parent_ticket'].queryset = Ticket.objects.filter(
                author=self.user,
                status__in=[TicketStatus.CLOSED, TicketStatus.RESOLVED]
            ).select_related('responsible')
        else:
            self.fields['parent_ticket'].queryset = Ticket.objects.none()

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_parent_ticket(self):
        parent_ticket = self.cleaned_data.get('parent_ticket')

        if parent_ticket:
            # 1. Проверка на авторство
            if self.user and parent_ticket.author != self.user:
                raise forms.ValidationError('Можно обжаловать только свои заявки.')

            # 2. Проверка статуса родительской заявки
            allowed_statuses = [TicketStatus.CLOSED, TicketStatus.RESOLVED]
            if parent_ticket.status not in allowed_statuses:
                raise forms.ValidationError(
                    f'Обжалование возможно только для заявок в статусе: '
                    f'{", ".join(dict(TicketStatus.choices).values())}'
                )

        return parent_ticket


class TicketUpdateForm(forms.ModelForm):
    """Форма редактирования заявки (для назначения ответственного)"""

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'responsible', 'status']
        widgets = {
            'responsible': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Делаем поля необязательными на уровне формы
        self.fields['responsible'].required = False
        self.fields['status'].required = False

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_responsible(self):
        # 2. Если поле пустое в POST-запросе, возвращаем старое значение из instance
        responsible = self.cleaned_data.get('responsible')
        if not responsible and self.instance.pk:
            return self.instance.responsible
        return responsible

    def clean_status(self):
        # Аналогично для статуса
        status = self.cleaned_data.get('status')
        if not status and self.instance.pk:
            return self.instance.status
        return status


class MessageForm(forms.ModelForm):
    """Форма добавления сообщения"""

    class Meta:
        model = Message
        fields = ['text', 'is_internal']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Введите сообщение...'
            }),
            'is_internal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AttachmentForm(forms.ModelForm):
    """Форма добавления вложения"""

    class Meta:
        model = Attachment
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }