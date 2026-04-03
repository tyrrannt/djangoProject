from django import forms
from django.contrib.auth import get_user_model
from .models import Ticket, Message, Attachment, TicketStatus

User = get_user_model()


class TicketCreateForm(forms.ModelForm):
    """Форма создания заявки"""

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
        fields = ['responsible', 'status']
        widgets = {
            'responsible': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Показываем только сотрудников
        self.fields['responsible'].queryset = User.objects.filter(is_staff=True)


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